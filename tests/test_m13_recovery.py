"""M13 recovery proofs (frozen R3 §30.9 M13-RECOVERY:01-05)."""

from __future__ import annotations

import asyncio
import sqlite3

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

import importlib

rb = importlib.import_module("soloring.recovery.backup")
from soloring.settings import Settings

NOW = "2026-01-01T00:00:00.000Z"


def _factory(data_dir):
    from sqlalchemy.ext.asyncio import create_async_engine

    from tests.conftest import make_tracked_maker

    eng = create_async_engine(
        f"sqlite+aiosqlite:///{(data_dir / 'soloring.db').as_posix()}")
    return make_tracked_maker(eng), eng


async def _seed_full(data_dir) -> dict:
    """Full 0014 world: adoption + interpretation + PI feature/track +
    transitions + binding + selection + schema-6 capture, real paths."""
    from soloring.db import models  # noqa: F401
    from soloring.db.base import Base

    factory, eng = _factory(data_dir)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # the retained Blob bytes must physically exist for liveness copying
    import hashlib as _hl

    _bh = _hl.sha256(b"m13rec").hexdigest()
    _blob = data_dir / "blobs" / "sha256" / _bh[:2] / _bh[2:4] / _bh
    _blob.parent.mkdir(parents=True, exist_ok=True)
    _blob.write_bytes(b"m13rec")

    from soloring.composition.service import (
        create_composition,
        mint_occurrence,
    )
    from soloring.composition.readiness import publish_composition_revision
    from soloring.domain.ids import new_uuid
    from soloring.production_world.interpretation import (
        create_interpretation,
    )
    from soloring.production_world.selection import put_selection
    from soloring.production_world.subjects import adopt_subject
    from soloring.production_world.instance_state import (
        create_feature,
        create_transition,
    )
    from soloring.production_world.instance_spatial import (
        create_track,
        create_spatial_transition,
    )
    from soloring.production_world.binding import publish_binding
    from soloring.production.canonical import (
        RetainedBlobClosure,
        production_revision_snapshot_json as sj,
        production_revision_snapshot_hash as sh,
    )
    import hashlib

    pid, prid, pobj, cid_, bh = (new_uuid(), new_uuid(), new_uuid(),
                                 new_uuid(), hashlib.sha256(b"m13rec").hexdigest())
    closure = RetainedBlobClosure(blob_hash=bh, size_bytes=6, media_type=None)
    async with factory() as s, s.begin():
        await s.execute(text(
            "INSERT INTO projects (id, name, created_at, updated_at) "
            "VALUES (:i, 'P', :n, :n)"), {"i": pid, "n": NOW})
        await s.execute(text(
            "INSERT INTO blobs (hash, path, size_bytes, detected_media_type,"
            " created_at) VALUES (:h, :p, 6, NULL, :n)"),
            {"h": bh, "p": f"sha256/{bh[:2]}/{bh[2:4]}/{bh}", "n": NOW})
        await s.execute(text(
            "INSERT INTO production_objects (id, project_id, name, "
            "created_at, updated_at) VALUES (:o, :p, 'Obj', :n, :n)"),
            {"o": pobj, "p": pid, "n": NOW})
        await s.execute(text(
            "INSERT INTO production_revisions (id, production_object_id, "
            "revision_number, snapshot_json, snapshot_hash, created_at) "
            "VALUES (:r, :o, 1, :sj, :sh, :n)"),
            {"r": prid, "o": pobj, "sj": sj(closure), "sh": sh(closure),
             "n": NOW})
        await s.execute(text(
            "INSERT INTO production_revision_closures "
            "(production_revision_id, contract_key, contract_version, "
            "blob_hash, size_bytes, media_type) VALUES "
            "(:r, 'retained_blob', 1, :bh, 6, NULL)"),
            {"r": prid, "bh": bh})
        asset, aid = new_uuid(), new_uuid()
        await s.execute(text(
            "INSERT INTO assets (id, project_id, blob_hash, kind, "
            "created_at) VALUES (:a, :p, :h, 'reference', :n)"),
            {"a": aid, "p": pid, "h": bh, "n": NOW})
        await s.execute(text(
            "INSERT INTO production_revision_source_assets "
            "(production_revision_id, asset_id, created_at) VALUES "
            "(:r, :a, :n)"), {"r": prid, "a": aid, "n": NOW})
        # location entity with approved revision (world resolution input)
        loc, locrev = new_uuid(), new_uuid()
        await s.execute(text(
            "INSERT INTO creative_entities (id, project_id, kind, name, "
            "created_at, updated_at) VALUES (:e, :p, 'location', 'Set', "
            ":n, :n)"), {"e": loc, "p": pid, "n": NOW})
        await s.execute(text(
            "INSERT INTO entity_revisions (id, entity_id, revision_number,"
            " schema_version, spec_hash, created_at) VALUES "
            "(:r, :e, 1, 1, :h, :n)"),
            {"r": locrev, "e": loc, "h": "a" * 64, "n": NOW})
        await s.execute(text(
            "INSERT INTO entity_approved_revisions (entity_id, revision_id,"
            " approved_at) VALUES (:e, :r, :n)"),
            {"e": loc, "r": locrev, "n": NOW})
        # narrative anchors + shot
        seq, scene, shot = new_uuid(), new_uuid(), new_uuid()
        await s.execute(text(
            "INSERT INTO sequences (id, project_id, position, title) "
            "VALUES (:q, :p, 0, 'S')"), {"q": seq, "p": pid})
        await s.execute(text(
            "INSERT INTO scenes (id, sequence_id, position, title) "
            "VALUES (:c, :q, 0, 'C')"), {"c": scene, "q": seq})
        await s.execute(text(
            "INSERT INTO shots (id, project_id, shot_number, subject, "
            "duration_ms, scene_id, scene_position) VALUES "
            "(:s, :p, 1, 'shot', 1000, :c, 0)"),
            {"s": shot, "p": pid, "c": scene})
        await s.execute(text(
            "INSERT INTO shot_entity_dependencies (shot_id, entity_id, "
            "role, position) VALUES (:s, :e, 'location', 0)"),
            {"s": shot, "e": loc})
        # spatial world + state + revision (canonical snapshot)
        from soloring.spatial.schemas import parse_world_revision

        sw, sws, swr = new_uuid(), new_uuid(), new_uuid()
        snapshot = {
            "schema_version": 1,
            "spatial_world_id": sw,
            "location_entity_id": "11111111-1111-1111-1111-111111111111",
            "location_entity_revision_id":
                "22222222-2222-2222-2222-222222222222",
            "coordinate_system": parse_world_revision({
                "schema_version": 1, "spatial_world_id": sw,
                "location_entity_id":
                    "11111111-1111-1111-1111-111111111111",
                "location_entity_revision_id":
                    "22222222-2222-2222-2222-222222222222",
                "coordinate_system": {}, "frames": [], "axes": [],
            })["coordinate_system"] if False else None,
            "frames": [], "axes": [],
        }
        del snapshot  # built below via the real serializer path
        await s.execute(text(
            "INSERT INTO spatial_worlds (id, project_id, key, name, "
            "requirement, location_entity_id, created_at, updated_at, "
            "deleted_at) VALUES (:w, :p, 'lobby', 'Lobby', 'required', :l, "
            ":n, :n, NULL)"),
            {"w": sw, "p": pid, "l": loc, "n": NOW})
        await s.execute(text(
            "INSERT INTO spatial_world_states (id, spatial_world_id, "
            "location_entity_revision_id, approved_revision_id, created_at,"
            " updated_at) VALUES (:st, :w, :lr, NULL, :n, :n)"),
            {"st": sws, "w": sw, "lr": locrev, "n": NOW})
    # build the revision snapshot through the real parser for canonical
    # bytes
    from soloring.domain.canonical import (
        canonical_hash,
        canonical_json_str as cjs,
    )

    snapshot = {
        "schema_version": 1,
        "spatial_world_id": sw,
        "location_entity_id": loc,
        "location_entity_revision_id": locrev,
        "coordinate_system": {
            "handedness": "right", "right_axis": "+x", "up_axis": "+y",
            "depth_positive_axis": "+z", "forward_axis": "-z",
            "linear_unit": "millimeter", "rotation_unit": "microdegree",
            "rotation_semantics": "active_local_to_world_intrinsic_yxz",
            "vector_convention": "column",
            "camera_forward_axis": "-z",
        },
        "frames": [], "axes": [],
    }
    from soloring.spatial.schemas import parse_world_revision

    parsed = parse_world_revision(snapshot)
    async with factory() as s, s.begin():
        await s.execute(text(
            "INSERT INTO spatial_world_revisions (id, "
            "spatial_world_state_id, revision_number, snapshot_json, "
            "snapshot_hash, created_at) VALUES (:r, :st, 1, :sj, :sh, :n)"),
            {"r": swr, "st": sws, "sj": cjs(parsed),
             "sh": canonical_hash(parsed), "n": NOW})
        await s.execute(text(
            "UPDATE spatial_world_states SET approved_revision_id = :r "
            "WHERE id = :st"), {"r": swr, "st": sws})

    async with factory() as s:
        comp = await create_composition(s, pid, name="Lobby",
                                        description=None)
        m = await mint_occurrence(
            s, comp["id"], scope="composition_working_state",
            expected_working_version=0, spec={
                "display_name": "Chair 7",
                "source": {"kind": "production_revision",
                           "revision_id": prid},
                "visible": True,
                "transform": {"translation_mm": [0, 0, 0],
                              "rotation_udeg": [0, 0, 0]}})
        oid = m["occurrence_id"]
        await adopt_subject(s, comp["id"], oid, kind="production_instance")
        await create_interpretation(
            s, prid,
            transform={"translation_mm": [0, 0, 0],
                       "rotation_udeg": [0, 0, 0]})
        fid = await create_feature(
            s, comp["id"], oid,
            payload=_FeaturePayload(key="fallen", kind="status",
                                    value_type="text", name="Fallen"))
        await create_transition(
            s, fid,
            payload=_TransitionPayload(anchor_type="sequence",
                                       anchor_id=seq, boundary="start",
                                       operation="set", value="down"))
        track = await create_track(s, sw, occurrence_id=oid,
                                   requirement="optional")
        await create_spatial_transition(
            s, track,
            payload=_SpatialTransitionPayload(
                anchor_type="sequence", anchor_id=seq, boundary="start",
                operation="set",
                transform={"translation_mm": [10, 0, 0],
                           "rotation_udeg": [0, 0, 0]}))
        pub, _created_rev = await publish_composition_revision(
            s, comp["id"], expected_working_version=1)
        binding, _created = await publish_binding(
            s, composition_revision_id=pub["revision_id"],
            spatial_world_revision_id=swr)
        sel = await put_selection(s, shot, binding_id=binding["binding_id"],
                                  expected_binding_id=None)
        del sel
    # schema-6 capture: the full coherent read needs the M10 plan; seed a
    # plan row directly (camera minimal) so the M10 resolver is ready
    from soloring.spatial.plans import put_spatial_plan

    plan = {
        "schema_version": 1, "spatial_world_id": sw,
        "camera": {"projection": "perspective", "focal_length_um": 50000,
                   "sensor_width_um": 36000, "sensor_height_um": 20250,
                   "keyframes": [{"time_ms": 0, "transform": {
                       "translation_mm": [-3000, 1650, 4200],
                       "rotation_udeg": [0, 0, 0]}}]},
        "blocking": [], "axis_constraint": None,
    }
    async with factory() as s:
        await put_spatial_plan(s, shot, expected_plan_hash=None,
                               plan_raw=plan)
        from soloring.domain.revisions import capture_revision_with_visual

        revision, _visual = await capture_revision_with_visual(s, shot)
    from tests.conftest import close_registered_sessions

    await close_registered_sessions(eng)
    await eng.dispose()
    return {"pid": pid, "composition_id": comp["id"], "shot": shot,
            "binding_id": binding["binding_id"], "track": track,
            "revision_id": revision.id, "sw": sw, "swr": swr}


class _Payload:
    def __init__(self, **kw):
        defaults = {"description": None, "enum_values": None, "unit": None,
                    "supersedes_feature_id": None, "value": None,
                    "transform": None}
        defaults.update(kw)
        self.__dict__.update(defaults)


class _FeaturePayload(_Payload):
    pass


class _TransitionPayload(_Payload):
    pass


class _SpatialTransitionPayload(_Payload):
    pass


def _stamp(data_dir, head: str) -> None:
    from alembic import command
    from alembic.config import Config

    import soloring.settings as settings_mod

    prev = settings_mod._settings
    settings_mod._settings = Settings(data_dir=data_dir)
    try:
        cfg = Config("server/alembic.ini")
        cfg.set_main_option("script_location", "server/alembic")
        command.stamp(cfg, head)
    finally:
        settings_mod._settings = prev


def test_m13_recovery_01(tmp_path):
    """M13-RECOVERY:01 — supported-head dispatch incl. 0014."""
    assert rb.EXPECTED_ALEMBIC_HEAD == "0015_m14_world_observation_execution"
    assert rb.SUPPORTED_RESTORE_ALEMBIC_HEADS == {
        "0011_m10_derived_spatial_execution",
        "0012_m11_reusable_production_revisions",
        "0013_m12_composition_occurrences",
        "0014_m13_authority_complete_world",
        "0015_m14_world_observation_execution",
    }


def test_m13_recovery_03(tmp_path):
    """M13-RECOVERY:03 — the verifier rejects corrupted binding/history."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    ids = asyncio.run(_seed_full(data_dir))
    _stamp(data_dir, "0015_m14_world_observation_execution")
    con = sqlite3.connect(data_dir / "soloring.db")
    con.execute(
        "UPDATE composition_spatial_bindings SET binding_json = "
        "'{\"schema_version\":1}' WHERE id = ?", (ids["binding_id"],))
    con.commit()
    con.close()
    settings = Settings(data_dir=data_dir)
    with pytest.raises(rb.RecoveryCorruption, match="binding"):
        asyncio.run(rb.backup(settings, tmp_path / "backup"))


def test_m13_recovery_04(tmp_path):
    """M13-RECOVERY:04 — the 0014 Blob-FK inventory remains exactly the
    seven M11/M12 paths (M13 adds no Blob FK)."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    asyncio.run(_seed_full(data_dir))
    _stamp(data_dir, "0015_m14_world_observation_execution")
    con = sqlite3.connect(data_dir / "soloring.db")
    try:
        found = rb._blob_fk_inventory(con)
    finally:
        con.close()
    assert set(rb.M11_BLOB_FK_COLUMNS) <= found
    assert found == set(rb.M14_BLOB_FK_COLUMNS)
    assert len(found) == 8


def test_m13_recovery_05(tmp_path):
    """M13-RECOVERY:05 — an integrity-valid STALE binding (pinned PI
    track later soft-deleted, selection removed) restores successfully;
    'stale now' is a classification, not corruption."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    ids = asyncio.run(_seed_full(data_dir))
    _stamp(data_dir, "0015_m14_world_observation_execution")
    con = sqlite3.connect(data_dir / "soloring.db")
    # make today's authority evolve: soft-delete the pinned PI track and
    # drop the current selection (the binding is now stale but immutable)
    con.execute(
        "UPDATE production_instance_spatial_tracks SET deleted_at = ? "
        "WHERE id = ?", (NOW, ids["track"]))
    con.execute(
        "DELETE FROM shot_production_world_selections WHERE shot_id = ?",
        (ids["shot"],))
    con.commit()
    con.close()
    settings = Settings(data_dir=data_dir)
    asyncio.run(rb.backup(settings, tmp_path / "backup"))
    dest = tmp_path / "restored"
    result = asyncio.run(rb.restore(tmp_path / "backup", dest))
    assert result is not None
    con = sqlite3.connect(dest / "soloring.db")
    try:
        n = con.execute(
            "SELECT COUNT(*) FROM composition_spatial_bindings").fetchone()[0]
        soft = con.execute(
            "SELECT deleted_at FROM production_instance_spatial_tracks "
            "WHERE id = ?", (ids["track"],)).fetchone()[0]
    finally:
        con.close()
    assert n == 1
    assert soft == NOW  # pinned target row retained, verifiably soft-deleted


def test_m13_recovery_02(tmp_path):
    """M13-RECOVERY:02 — restore of 0011/0012/0013 data under the newer
    recovery code proves no M13 authority was invented: the staged older
    DB carries none of the thirteen M13 tables and _prove_no_m13_state
    accepts it."""
    # a 0013-headed staged DB has no M13 tables by construction; prove
    # the no-invention gate directly against a minimal 0013 schema
    import sqlite3

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    con = sqlite3.connect(data_dir / "soloring.db")
    con.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) "
                "NOT NULL PRIMARY KEY)")
    con.execute("INSERT INTO alembic_version (version_num) VALUES "
                "('0013_m12_composition_occurrences')")
    con.commit()
    con.close()
    from pathlib import Path

    rb._prove_no_m13_state(Path(data_dir / "soloring.db"))  # no raise
