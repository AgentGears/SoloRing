"""M7A — Feature identity + typed canonicalization + migration 0008 tests.

Gates (plan §56): exact canonical value byte fixtures; Decimal
transport/string rules pinned; invalid enum rejected; key reuse rejected
(tombstone-inclusive); lineage same-Entity validation; single-successor
lineage; feature delete blocked by active transition references; semantic
fields immutable; display rename has no semantic side effect; migration
empty upgrade/downgrade; any M7 row (incl. tombstoned-only) causes
downgrade refusal; schema-v3 ShotRevision JSON refuses downgrade even with
empty M7 tables; malformed JSON refuses downgrade; existing Generation
behavior unchanged (full suite).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from soloring.continuity.values import (
    canonical_decimal_string,
    canonicalize_value,
    is_valid_key,
    validate_enum_values,
)
from soloring.domain.ids import new_uuid
from soloring.errors import ErrorCode, SoloRingError
from soloring.settings import BASE_DIR

# --- §7 canonical byte fixtures ----------------------------------------------------


def test_boolean_bytes():
    j, h = canonicalize_value("boolean", True)
    assert j == "true"
    j, h = canonicalize_value("boolean", False)
    assert j == "false"
    for bad in (0, 1, "true", None):
        with pytest.raises(SoloRingError) as ei:
            canonicalize_value("boolean", bad)
        assert ei.value.code == ErrorCode.INVALID_CONTINUITY_VALUE


def test_enum_bytes_exact_membership():
    enums = ["fresh", "healing", "scarred", "gone"]
    j, h = canonicalize_value("enum", "fresh", enum_values=enums)
    assert j == '"fresh"'
    assert len(h) == 64
    for bad in ("Fresh", "FRESH", "fresh ", "missing"):
        with pytest.raises(SoloRingError):
            canonicalize_value("enum", bad, enum_values=enums)


def test_integer_bytes_and_bounds():
    assert canonicalize_value("integer", 17)[0] == "17"
    assert canonicalize_value("integer", -4)[0] == "-4"
    assert canonicalize_value("integer", 0)[0] == "0"
    for bad in (True, False, 1.0, "17", None):
        with pytest.raises(SoloRingError):
            canonicalize_value("integer", bad)
    with pytest.raises(SoloRingError):
        canonicalize_value("integer", 9007199254740992)
    with pytest.raises(SoloRingError):
        canonicalize_value("integer", -9007199254740992)


def test_decimal_transport_string_only():
    accepted = {
        "1": "1",
        "1.0": "1",
        "1.500": "1.5",
        "0001.50": "1.5",
        "-0": "0",
        "-0.000": "0",
        "1000.00": "1000",
        "00012.3400": "12.34",
        "-0.005": "-0.005",
    }
    for raw, expected in accepted.items():
        j, h = canonicalize_value("decimal", raw)
        assert j == f'"{expected}"', raw
        assert len(h) == 64
    for bad in (1.5, "1e3", "NaN", "Infinity", "-Infinity", " 1.5 ", "+1.5",
                ".5", "5.", "1.", "", "-", "0x10"):
        with pytest.raises(SoloRingError) as ei:
            canonicalize_value("decimal", bad)
        assert ei.value.code == ErrorCode.INVALID_CONTINUITY_VALUE


def test_decimal_frozen_limits_reject_not_round():
    # 19 fractional digits exceeds the frozen scale of 18.
    with pytest.raises(SoloRingError, match="scale"):
        canonicalize_value("decimal", "0." + "0" * 18 + "1")
    # 39 significant digits exceeds the frozen precision of 38.
    with pytest.raises(SoloRingError, match="precision"):
        canonicalize_value("decimal", "1" * 38 + "2")
    # Boundary values pass: 38 digits, scale 18.
    j, _ = canonicalize_value("decimal", "1" * 20 + "." + "1" * 18)
    assert j == '"' + "1" * 20 + "." + "1" * 18 + '"'


def test_decimal_helper_direct():
    assert canonical_decimal_string("1") == "1"
    assert canonical_decimal_string("-0") == "0"
    assert canonical_decimal_string("1000.00") == "1000"
    assert canonical_decimal_string("00012.3400") == "12.34"


def test_text_rules():
    j, _ = canonicalize_value("text", "left inner  spacing\tkept")
    assert j == '"left inner  spacing\\tkept"'
    assert canonicalize_value("text", "Éva — 柱")[0] == '"Éva — 柱"'
    for bad in ("", "   ", " padded", "padded ", "x" * 4097, 7, None):
        with pytest.raises(SoloRingError):
            canonicalize_value("text", bad)


def test_value_hash_is_sha256_of_value_json():
    import hashlib

    j, h = canonicalize_value("enum", "fresh", enum_values=["fresh"])
    assert h == hashlib.sha256(b'"fresh"').hexdigest()


def test_key_regex():
    for good in ("a", "forehead_cut", "left_headlight", "x" * 64, "a123_b"):
        assert is_valid_key(good), good
    for bad in ("", "A", "1abc", "_x", "x-y", "x y", "x" * 65, 7, None,
                "é"):
        assert not is_valid_key(bad), bad


def test_enum_list_validation():
    assert validate_enum_values(["fresh", "healing"]) == ["fresh", "healing"]
    # order preserved — distinct declarations are distinct schemas
    assert validate_enum_values(["gone", "healing", "fresh"]) == [
        "gone", "healing", "fresh"
    ]
    for bad in (
        [], "notalist", ["a", "a"], [" "], [" a"], ["a "], [""],
        ["x" * 129], ["ok"] * 65, [7],
    ):
        with pytest.raises(SoloRingError) as ei:
            validate_enum_values(bad)
        assert ei.value.code == ErrorCode.INVALID_CONTINUITY_FEATURE


# --- Feature CRUD / lifecycle --------------------------------------------------------


async def _seed_project_and_entity(client, factory):
    from soloring.api.schemas.projects import ProjectCreate
    from soloring.domain import projects as project_svc

    async with factory() as s:
        pid = (await project_svc.create_project(
            s, ProjectCreate(name="P")
        )).id
    r = await client.post(
        f"/projects/{pid}/entities",
        json={"kind": "character", "name": "Eva"},
    )
    assert r.status_code == 201, r.text
    return pid, r.json()


async def _create_feature(client, entity_id, **overrides):
    payload = {
        "key": "forehead_cut",
        "kind": "injury",
        "value_type": "enum",
        "name": "Forehead Cut",
        "enum_values": ["fresh", "healing", "scarred", "gone"],
    }
    payload.update(overrides)
    payload = {k: v for k, v in payload.items() if v is not False or k != "enum_values"}
    r = await client.post(
        f"/entities/{entity_id}/continuity-features", json=payload
    )
    return r


async def test_feature_crud_and_validation(client, factory):
    pid, eva = await _seed_project_and_entity(client, factory)

    r = await _create_feature(client, eva["id"])
    assert r.status_code == 201, r.text
    feature = r.json()
    assert feature["key"] == "forehead_cut"
    # Frozen enum storage: exact canonical serializer bytes, order kept.
    assert feature["enum_values_json"] == (
        '["fresh","healing","scarred","gone"]'
    )

    # Tombstone-inclusive key uniqueness.
    r = await _create_feature(client, eva["id"])
    assert r.status_code == 409
    assert r.json()["error_code"] == "CONTINUITY_FEATURE_KEY_CONFLICT"

    # Semantic validation rejections.
    r = await _create_feature(
        client, eva["id"], key="Bad-Key", name="X"
    )
    assert r.status_code == 422
    r = await _create_feature(client, eva["id"], kind="mood")
    assert r.status_code == 422
    r = await _create_feature(client, eva["id"], value_type="float")
    assert r.status_code == 422
    r = await _create_feature(
        client, eva["id"], value_type="boolean", enum_values=["a"]
    )
    assert r.status_code == 422
    r = await _create_feature(
        client, eva["id"], value_type="boolean", unit="pts"
    )
    assert r.status_code == 422
    r = await _create_feature(
        client, eva["id"], value_type="enum", enum_values=["a", "a"]
    )
    assert r.status_code == 422
    r = await _create_feature(client, eva["id"], name="   ")
    assert r.status_code == 422

    # unit legal on numeric types.
    r = await _create_feature(
        client, eva["id"], key="ammo_count", kind="status",
        value_type="integer", name="Ammo", enum_values=None, unit="rounds",
    )
    assert r.status_code == 201, r.text
    assert r.json()["unit"] == "rounds"

    # PATCH: display metadata only; semantic fields forbidden by schema.
    r = await client.patch(
        f"/continuity-features/{feature['id']}", json={"name": "Forehead Wound"}
    )
    assert r.status_code == 200 and r.json()["name"] == "Forehead Wound"
    r = await client.patch(
        f"/continuity-features/{feature['id']}", json={"key": "other_key"}
    )
    assert r.status_code == 422
    r = await client.patch(
        f"/continuity-features/{feature['id']}", json={}
    )
    assert r.status_code == 200

    # Delete idempotent; deleted feature hidden; key still unrecyclable.
    assert (await client.delete(
        f"/continuity-features/{feature['id']}"
    )).status_code == 204
    assert (await client.delete(
        f"/continuity-features/{feature['id']}"
    )).status_code == 204
    assert (await client.get(
        f"/entities/{eva['id']}/continuity-features"
    )).json() != [] # ammo_count remains
    r = await _create_feature(client, eva["id"])
    assert r.status_code == 409
    assert (await client.get(
        f"/continuity-features/{feature['id']}"
    )).status_code == 404


async def _fetch(engine, sql, params):
    async with engine.connect() as conn:
        row = (await conn.execute(text(sql), params)).mappings().one_or_none()
    return dict(row) if row is not None else None


async def test_rename_leaves_semantic_columns_untouched(
    client, factory, engine
):
    pid, eva = await _seed_project_and_entity(client, factory)
    feature = (await _create_feature(client, eva["id"])).json()
    before = await _fetch(
        engine,
        "SELECT key, kind, value_type, enum_values_json, unit, "
        "supersedes_feature_id, deleted_at FROM continuity_features "
        "WHERE id = :f",
        {"f": feature["id"]},
    )
    r = await client.patch(
        f"/continuity-features/{feature['id']}",
        json={"name": "Renamed", "description": "new description"},
    )
    assert r.status_code == 200
    after = await _fetch(
        engine,
        "SELECT key, kind, value_type, enum_values_json, unit, "
        "supersedes_feature_id, deleted_at FROM continuity_features "
        "WHERE id = :f",
        {"f": feature["id"]},
    )
    assert after == before


async def test_lineage_rules(client, factory):
    pid, eva = await _seed_project_and_entity(client, factory)
    v1 = (await _create_feature(client, eva["id"])).json()

    r = await _create_feature(
        client, eva["id"], key="forehead_cut_v2", name="V2",
        enum_values=["fresh", "infected", "healing", "scarred", "gone"],
        supersedes_feature_id=v1["id"],
    )
    assert r.status_code == 201, r.text

    # Single-successor lineage: a second direct successor is rejected.
    r = await _create_feature(
        client, eva["id"], key="forehead_cut_v3", name="V3",
        enum_values=["a", "b"],
        supersedes_feature_id=v1["id"],
    )
    assert r.status_code == 409
    assert r.json()["error_code"] == (
        "CONTINUITY_FEATURE_SUPERSESSION_CONFLICT"
    )

    # Cross-entity predecessor rejected.
    r = await client.post(
        f"/projects/{pid}/entities", json={"kind": "prop", "name": "Gun"}
    )
    gun = r.json()
    r = await _create_feature(
        client, gun["id"], key="wear", kind="surface_condition",
        value_type="text", name="Wear", enum_values=None,
        supersedes_feature_id=v1["id"],
    )
    assert r.status_code == 409
    assert r.json()["error_code"] == (
        "CONTINUITY_FEATURE_SUPERSESSION_CONFLICT"
    )

    # Unknown predecessor rejected.
    r = await _create_feature(
        client, gun["id"], key="wear2", kind="surface_condition",
        value_type="text", name="Wear2", enum_values=None,
        supersedes_feature_id=str(new_uuid()),
    )
    assert r.status_code == 409


async def test_feature_delete_blocked_by_active_transitions(
    client, factory, engine
):
    pid, eva = await _seed_project_and_entity(client, factory)
    feature = (await _create_feature(client, eva["id"])).json()

    # Dormant table: seed an active transition row directly (M7B owns the
    # API), mirroring the M6A ENTITY_IN_USE test technique.
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(
            text(
                "INSERT INTO continuity_feature_transitions "
                "(id, feature_id, anchor_type, anchor_id, boundary, "
                " operation, value_json, value_hash, created_at, updated_at) "
                "VALUES (:id, :fid, 'shot', :aid, 'end', 'set', "
                "'\"fresh\"', :vh, strftime('%Y-%m-%dT%H:%M:%fZ','now'), "
                "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
            ),
            {
                "id": new_uuid(),
                "fid": feature["id"],
                "aid": new_uuid(),
                "vh": "a" * 64,
            },
        )
        await conn.exec_driver_sql("COMMIT")

    r = await client.delete(f"/continuity-features/{feature['id']}")
    assert r.status_code == 409
    assert r.json()["error_code"] == "CONTINUITY_FEATURE_IN_USE"

    # Removing the reference (soft-delete the transition) unblocks.
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(
            text(
                "UPDATE continuity_feature_transitions SET deleted_at = "
                "strftime('%Y-%m-%dT%H:%M:%fZ','now')"
            )
        )
        await conn.exec_driver_sql("COMMIT")
    assert (await client.delete(
        f"/continuity-features/{feature['id']}"
    )).status_code == 204


# --- Migration 0008 gates --------------------------------------------------------------


def _cfg() -> Config:
    cfg = Config(str(BASE_DIR / "server" / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "server" / "alembic"))
    return cfg


def _point_at(data_dir: Path, monkeypatch) -> None:
    import soloring.settings as settings_mod

    monkeypatch.setenv("SOLORING_DATA_DIR", str(data_dir))
    monkeypatch.setattr(settings_mod, "_settings", None)


def test_0008_empty_upgrade_and_clean_downgrade(tmp_path, monkeypatch):
    import sqlite3 as sq

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "soloring.db"
    _point_at(data_dir, monkeypatch)
    cfg = _cfg()
    command.upgrade(cfg, "head")

    con = sq.connect(str(db_file))
    con.execute("PRAGMA foreign_keys=ON")
    try:
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        for t in ("continuity_features", "continuity_feature_transitions",
                  "continuity_predicates", "continuity_relations",
                  "continuity_relation_transitions",
                  "shot_revision_feature_states",
                  "shot_revision_relation_states"):
            assert t in tables
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
        idx = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )}
        for i in ("uq_continuity_features_supersedes",
                  "uq_continuity_feature_transitions_active_coordinate",
                  "uq_continuity_relations_active_identity",
                  "uq_continuity_relation_transitions_active_coordinate"):
            assert i in idx
    finally:
        con.close()

    command.downgrade(cfg, "0007_active_narrative_uniqueness")
    con = sq.connect(str(db_file))
    try:
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        for t in ("continuity_features", "continuity_predicates",
                  "shot_revision_feature_states"):
            assert t not in tables
        assert con.execute("SELECT version_num FROM alembic_version"
                           ).fetchone()[0] == "0007_active_narrative_uniqueness"
    finally:
        con.close()


def test_0008_downgrade_refuses_any_m7_row_incl_tombstoned(
    tmp_path, monkeypatch
):
    import sqlite3 as sq

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "soloring.db"
    _point_at(data_dir, monkeypatch)
    cfg = _cfg()
    command.upgrade(cfg, "head")

    con = sq.connect(str(db_file))
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(
        "INSERT INTO projects(id, name, created_at, updated_at) "
        "VALUES ('p1','P','t','t'); "
        "INSERT INTO creative_entities(id, project_id, kind, name, "
        "created_at, updated_at) "
        "VALUES ('e1','p1','character','Eva','t','t'); "
        "INSERT INTO continuity_features(id, entity_id, key, kind, "
        "value_type, name, created_at, updated_at, deleted_at) "
        "VALUES ('f1','e1','forehead_cut','injury','text','Cut','t','t','td'); "
    )
    con.commit()
    con.close()

    with pytest.raises(RuntimeError, match="tombstoned|contains"):
        command.downgrade(cfg, "0007_active_narrative_uniqueness")

    con = sq.connect(str(db_file))
    try:
        # Refused BEFORE any DDL: schema and version untouched.
        assert con.execute("SELECT version_num FROM alembic_version"
                           ).fetchone()[0] == "0008_narrative_continuity_state"
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        assert "continuity_features" in tables
    finally:
        con.close()


def test_0008_downgrade_refuses_schema_v3_json(tmp_path, monkeypatch):
    import sqlite3 as sq

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "soloring.db"
    _point_at(data_dir, monkeypatch)
    cfg = _cfg()
    command.upgrade(cfg, "head")

    hex64 = "a" * 64
    con = sq.connect(str(db_file))
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(
        "INSERT INTO projects(id, name, created_at, updated_at) "
        "VALUES ('p1','P','t','t'); "
        "INSERT INTO shots(id, project_id, shot_number, subject, "
        "created_at, updated_at) VALUES ('s1','p1',1,'x','t','t'); "
        f"INSERT INTO shot_revisions(id, shot_id, revision_number, "
        f"snapshot_json, snapshot_hash, continuity_spec_json, "
        f"continuity_spec_hash, created_at) "
        f"VALUES ('r1','s1',1,'{{\"schema_version\": 3}}','{hex64}', "
        f"'{{\"schema_version\": 2, \"dependencies\": []}}','{hex64}','t'); "
    )
    con.commit()
    con.close()

    with pytest.raises(RuntimeError, match="schema_version"):
        command.downgrade(cfg, "0007_active_narrative_uniqueness")
    con = sq.connect(str(db_file))
    try:
        assert con.execute("SELECT version_num FROM alembic_version"
                           ).fetchone()[0] == "0008_narrative_continuity_state"
    finally:
        con.close()


def test_0008_downgrade_refuses_malformed_json(tmp_path, monkeypatch):
    import sqlite3 as sq

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "soloring.db"
    _point_at(data_dir, monkeypatch)
    cfg = _cfg()
    command.upgrade(cfg, "head")

    hex64 = "a" * 64
    con = sq.connect(str(db_file))
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(
        "INSERT INTO projects(id, name, created_at, updated_at) "
        "VALUES ('p1','P','t','t'); "
        "INSERT INTO shots(id, project_id, shot_number, subject, "
        "created_at, updated_at) VALUES ('s1','p1',1,'x','t','t'); "
        f"INSERT INTO shot_revisions(id, shot_id, revision_number, "
        f"snapshot_json, snapshot_hash, created_at) "
        f"VALUES ('r1','s1',1,'{{not json','{hex64}','t'); "
    )
    con.commit()
    con.close()

    with pytest.raises(RuntimeError, match="malformed"):
        command.downgrade(cfg, "0007_active_narrative_uniqueness")


def test_0008_downgrade_refuses_missing_schema_version(tmp_path, monkeypatch):
    import sqlite3 as sq

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "soloring.db"
    _point_at(data_dir, monkeypatch)
    cfg = _cfg()
    command.upgrade(cfg, "head")

    hex64 = "a" * 64
    con = sq.connect(str(db_file))
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(
        "INSERT INTO projects(id, name, created_at, updated_at) "
        "VALUES ('p1','P','t','t'); "
        "INSERT INTO shots(id, project_id, shot_number, subject, "
        "created_at, updated_at) VALUES ('s1','p1',1,'x','t','t'); "
        f"INSERT INTO shot_revisions(id, shot_id, revision_number, "
        f"snapshot_json, snapshot_hash, created_at) "
        f"VALUES ('r1','s1',1,'{{\"intent\": {{}}}}','{hex64}','t'); "
    )
    con.commit()
    con.close()

    with pytest.raises(RuntimeError, match="schema_version"):
        command.downgrade(cfg, "0007_active_narrative_uniqueness")

# --- M7A re-gate regressions (blockers 1–4) ---------------------------------------


async def test_unit_transport_is_rejected_not_normalized(client, factory):
    """Blocker 1: untrimmed/whitespace-only units are 422, never stripped."""
    pid, eva = await _seed_project_and_entity(client, factory)
    r = await _create_feature(
        client, eva["id"], key="ammo_count", kind="status",
        value_type="integer", name="Ammo", enum_values=None,
        unit=" rounds ",
    )
    assert r.status_code == 422
    assert r.json()["error_code"] == "INVALID_CONTINUITY_FEATURE"
    r = await _create_feature(
        client, eva["id"], key="ammo_count", kind="status",
        value_type="integer", name="Ammo", enum_values=None,
        unit="   ",
    )
    assert r.status_code == 422
    # Trimmed units still accepted.
    r = await _create_feature(
        client, eva["id"], key="ammo_count", kind="status",
        value_type="integer", name="Ammo", enum_values=None,
        unit="rounds",
    )
    assert r.status_code == 201
    assert r.json()["unit"] == "rounds"


async def test_invalid_key_uses_stable_feature_code(client, factory):
    """Blocker 2: schema/key failures carry INVALID_CONTINUITY_FEATURE."""
    pid, eva = await _seed_project_and_entity(client, factory)
    r = await _create_feature(client, eva["id"], key="Bad-Key")
    assert r.status_code == 422
    assert r.json()["error_code"] == "INVALID_CONTINUITY_FEATURE"
    # Lookup failures carry the dedicated 404 code, not the 422 schema code.
    r = await client.get(f"/continuity-features/{str(new_uuid())}")
    assert r.status_code == 404
    assert r.json()["error_code"] == "CONTINUITY_FEATURE_NOT_FOUND"


async def test_entity_delete_blocked_by_active_features(client, factory):
    """Blocker 3: ENTITY_IN_USE while the Entity owns active Features."""
    pid, eva = await _seed_project_and_entity(client, factory)
    feature = (await _create_feature(client, eva["id"])).json()

    r = await client.delete(f"/entities/{eva['id']}")
    assert r.status_code == 409
    assert r.json()["error_code"] == "ENTITY_IN_USE"

    # Removing the Feature unblocks deletion.
    assert (await client.delete(
        f"/continuity-features/{feature['id']}"
    )).status_code == 204
    assert (await client.delete(f"/entities/{eva['id']}")).status_code == 204


async def test_project_cascade_tombstones_features(client, factory, engine):
    """Blocker 3: Project deletion takes active Features with its Entities;
    direct Feature GETs no longer expose active working state."""
    pid, eva = await _seed_project_and_entity(client, factory)
    feature = (await _create_feature(client, eva["id"])).json()

    assert (await client.delete(f"/projects/{pid}")).status_code == 204
    row = await _fetch(
        engine,
        "SELECT deleted_at FROM continuity_features WHERE id = :f",
        {"f": feature["id"]},
    )
    assert row["deleted_at"] is not None
    r = await client.get(f"/continuity-features/{feature['id']}")
    assert r.status_code == 404


async def test_feature_hidden_when_parent_entity_deleted(
    client, factory, engine
):
    """Defense in depth: even a Feature row that somehow remains active
    under a tombstoned Entity is absent from direct reads."""
    pid, eva = await _seed_project_and_entity(client, factory)
    feature = (await _create_feature(client, eva["id"])).json()
    # Force the illegal state directly (deletion is now blocked by the API).
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(
            text("UPDATE creative_entities SET deleted_at = "
                 "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :e"),
            {"e": eva["id"]},
        )
        await conn.exec_driver_sql("COMMIT")
    assert (await client.get(
        f"/continuity-features/{feature['id']}"
    )).status_code == 404


def test_0008_downgrade_refuses_v2_snapshot_with_null_continuity(
    tmp_path, monkeypatch
):
    """Blocker 4: the reviewer's exact reproduction — structurally
    impossible pre-M7 row, M7 tables empty — must refuse side-effect-free."""
    import sqlite3 as sq

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "soloring.db"
    _point_at(data_dir, monkeypatch)
    cfg = _cfg()
    command.upgrade(cfg, "head")

    hex64 = "a" * 64
    con = sq.connect(str(db_file))
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(
        "INSERT INTO projects(id, name, created_at, updated_at) "
        "VALUES ('p1','P','t','t'); "
        "INSERT INTO shots(id, project_id, shot_number, subject, "
        "created_at, updated_at) VALUES ('s1','p1',1,'x','t','t'); "
        f"INSERT INTO shot_revisions(id, shot_id, revision_number, "
        f"snapshot_json, snapshot_hash, created_at) "
        f"VALUES ('r1','s1',1,'{{\"schema_version\": 2}}','{hex64}','t'); "
    )
    con.commit()
    con.close()

    with pytest.raises(RuntimeError, match="structurally inconsistent"):
        command.downgrade(cfg, "0007_active_narrative_uniqueness")
    con = sq.connect(str(db_file))
    try:
        assert con.execute("SELECT version_num FROM alembic_version"
                           ).fetchone()[0] == "0008_narrative_continuity_state"
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        assert "continuity_features" in tables  # untouched by refusal
    finally:
        con.close()


def test_0008_downgrade_refuses_v1_snapshot_with_non_null_continuity(
    tmp_path, monkeypatch
):
    """Blocker 4 mirror: schema-1 snapshot carrying continuity columns."""
    import sqlite3 as sq

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "soloring.db"
    _point_at(data_dir, monkeypatch)
    cfg = _cfg()
    command.upgrade(cfg, "head")

    hex64 = "a" * 64
    con = sq.connect(str(db_file))
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(
        "INSERT INTO projects(id, name, created_at, updated_at) "
        "VALUES ('p1','P','t','t'); "
        "INSERT INTO shots(id, project_id, shot_number, subject, "
        "created_at, updated_at) VALUES ('s1','p1',1,'x','t','t'); "
        f"INSERT INTO shot_revisions(id, shot_id, revision_number, "
        f"snapshot_json, snapshot_hash, continuity_spec_json, "
        f"continuity_spec_hash, created_at) "
        f"VALUES ('r1','s1',1,'{{\"schema_version\": 1}}','{hex64}', "
        f"'{{\"schema_version\": 1, \"dependencies\": []}}','{hex64}','t'); "
    )
    con.commit()
    con.close()

    with pytest.raises(RuntimeError, match="structurally inconsistent"):
        command.downgrade(cfg, "0007_active_narrative_uniqueness")


def test_0008_downgrade_refuses_v2_with_inconsistent_spec_version(
    tmp_path, monkeypatch
):
    """v2 snapshot whose spec declares something other than spec schema 1."""
    import sqlite3 as sq

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "soloring.db"
    _point_at(data_dir, monkeypatch)
    cfg = _cfg()
    command.upgrade(cfg, "head")

    hex64 = "a" * 64
    con = sq.connect(str(db_file))
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(
        "INSERT INTO projects(id, name, created_at, updated_at) "
        "VALUES ('p1','P','t','t'); "
        "INSERT INTO shots(id, project_id, shot_number, subject, "
        "created_at, updated_at) VALUES ('s1','p1',1,'x','t','t'); "
        f"INSERT INTO shot_revisions(id, shot_id, revision_number, "
        f"snapshot_json, snapshot_hash, continuity_spec_json, "
        f"continuity_spec_hash, created_at) "
        f"VALUES ('r1','s1',1,'{{\"schema_version\": 2}}','{hex64}', "
        f"'{{\"schema_version\": 0, \"dependencies\": []}}','{hex64}','t'); "
    )
    con.commit()
    con.close()

    with pytest.raises(RuntimeError, match="structurally inconsistent"):
        command.downgrade(cfg, "0007_active_narrative_uniqueness")


def test_0008_downgrade_accepts_consistent_v2_pairing(tmp_path, monkeypatch):
    """The consistent form (v2 snapshot + spec schema 1 + hash) downgrades
    cleanly once 0007's own preflight is satisfied (no coordinate reuse)."""
    import sqlite3 as sq

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "soloring.db"
    _point_at(data_dir, monkeypatch)
    cfg = _cfg()
    command.upgrade(cfg, "head")

    hex64 = "a" * 64
    con = sq.connect(str(db_file))
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(
        "INSERT INTO projects(id, name, created_at, updated_at) "
        "VALUES ('p1','P','t','t'); "
        "INSERT INTO shots(id, project_id, shot_number, subject, "
        "created_at, updated_at) VALUES ('s1','p1',1,'x','t','t'); "
        f"INSERT INTO shot_revisions(id, shot_id, revision_number, "
        f"snapshot_json, snapshot_hash, continuity_spec_json, "
        f"continuity_spec_hash, created_at) "
        f"VALUES ('r1','s1',1,'{{\"schema_version\": 2}}','{hex64}', "
        f"'{{\"schema_version\": 1, \"dependencies\": []}}','{hex64}','t'); "
    )
    con.commit()
    con.close()

    command.downgrade(cfg, "0007_active_narrative_uniqueness")
    con = sq.connect(str(db_file))
    try:
        assert con.execute("SELECT version_num FROM alembic_version"
                           ).fetchone()[0] == "0007_active_narrative_uniqueness"
    finally:
        con.close()
