"""M8A — schema core + facet/anchor services (frozen plan §§14–18, 25,
37–39, 68, 74–76; M8A gate).

Covers: migration 0009 head + downgrade preflight (populated refusal),
constraint/active-uniqueness behavior, target/project integrity (incl.
cross-Project rejections), value-hash authority (server-derived M7
canonicalization), deletion guards, and the closed error vocabulary.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from soloring.api.schemas.projects import ProjectCreate
from soloring.continuity import entities as entity_svc
from soloring.domain import projects as project_svc


async def _seed_project(factory, name="P"):
    async with factory() as s:
        return (await project_svc.create_project(
            s, ProjectCreate(name=name))).id


async def _entity(client, pid, kind="character", name="Eva"):
    r = await client.post(
        f"/projects/{pid}/entities", json={"kind": kind, "name": name}
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _entity_with_revision(client, factory, pid, name="Eva",
                                kind="character"):
    e = await _entity(client, pid, kind, name)
    r = await client.post(
        f"/entities/{e['id']}/revisions", json={"spec": {"description": "d"}}
    )
    assert r.status_code == 201, r.text
    rev_id = r.json()["id"]
    r = await client.put(
        f"/entities/{e['id']}/approved-revision",
        json={
            "revision_id": rev_id,
            "expected_approved_revision_id": None,
        },
    )
    assert r.status_code == 200, r.text
    return e, rev_id


async def _feature(client, entity_id, key="forehead_injury",
                   enum_values=None):
    payload = {
        "key": key, "kind": "injury", "value_type": "enum",
        "name": "Injury",
        "enum_values": enum_values or ["none", "fresh", "healing", "scarred"],
    }
    r = await client.post(
        f"/entities/{entity_id}/continuity-features", json=payload
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _facet(client, pid, target_kind, *, entity_id=None, feature_id=None,
                 facet_key="face", requirement="required", **kw):
    payload = {
        "target_kind": target_kind, "facet_key": facet_key,
        "requirement": requirement,
    }
    if entity_id is not None:
        payload["entity_id"] = entity_id
    if feature_id is not None:
        payload["feature_id"] = feature_id
    payload.update(kw)
    r = await client.post(f"/projects/{pid}/visual-facets", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


# --- Migration posture ------------------------------------------------------


async def test_migration_head_is_0009_and_downgrade_refuses_state(
    tmp_path, monkeypatch
):
    from alembic import command
    from alembic.config import Config
    from soloring.settings import BASE_DIR

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("SOLORING_DATA_DIR", str(data_dir))
    import soloring.settings as settings_mod

    monkeypatch.setattr(settings_mod, "_settings", None)
    cfg = Config(str(BASE_DIR / "server" / "alembic.ini"))
    cfg.set_main_option(
        "script_location", str(BASE_DIR / "server" / "alembic")
    )
    command.upgrade(cfg, "head")

    import sqlite3

    con = sqlite3.connect(str(data_dir / "soloring.db"))
    try:
        rev = con.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
        tables = {
            r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert rev[0] == "0009_m8_visual_identity"
        for t in (
            "visual_facets", "visual_facet_value_policies", "visual_anchors",
            "visual_anchor_items", "visual_anchor_revisions",
            "visual_anchor_revision_items", "shot_revision_visual_anchors",
            "shot_revision_visual_anchor_items",
        ):
            assert t in tables
        # Downgrade on the empty M8 schema is allowed.
        command.downgrade(cfg, "0008_narrative_continuity_state")
        after = {
            r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "visual_facets" not in after
        # Re-upgrade, populate ONE facet row, downgrade must now refuse.
        command.upgrade(cfg, "head")
        con.execute(
            "INSERT INTO visual_facets (id, project_id, target_kind, "
            "entity_id, facet_key, requirement) VALUES ('f1','p1','entity',"
            "'e1','face','optional')"
        )
        con.commit()
    finally:
        con.close()
    with pytest.raises(Exception) as excinfo:
        command.downgrade(cfg, "0008_narrative_continuity_state")
    assert "never destroyed" in str(excinfo.value)


async def test_schema4_snapshot_downgrade_refusal(
    tmp_path, monkeypatch
):
    from alembic import command
    from alembic.config import Config
    from soloring.settings import BASE_DIR

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("SOLORING_DATA_DIR", str(data_dir))
    import soloring.settings as settings_mod

    monkeypatch.setattr(settings_mod, "_settings", None)
    cfg = Config(str(BASE_DIR / "server" / "alembic.ini"))
    cfg.set_main_option(
        "script_location", str(BASE_DIR / "server" / "alembic")
    )
    command.upgrade(cfg, "head")
    import sqlite3

    con = sqlite3.connect(str(data_dir / "soloring.db"))
    try:
        con.execute("PRAGMA foreign_keys = OFF")
        con.execute(
            "INSERT INTO shot_revisions (id, shot_id, revision_number, "
            "snapshot_json, snapshot_hash) VALUES ('r1','s1',1,"
            "'{\"schema_version\":4}', '" + "h" * 64 + "')"
        )
        con.commit()
        con.execute("PRAGMA foreign_keys = ON")
    finally:
        con.close()
    with pytest.raises(Exception) as excinfo:
        command.downgrade(cfg, "0008_narrative_continuity_state")
    assert "schema-4" in str(excinfo.value)


# --- VisualFacet lifecycle --------------------------------------------------


async def test_facet_create_list_patch_roundtrip(client, factory):
    pid = await _seed_project(factory)
    eva = await _entity(client, pid)

    f = await _facet(
        client, pid, "entity", entity_id=eva["id"], facet_key="face",
        label="  Face  ", description="  hero look  ",
    )
    assert f["target_kind"] == "entity"
    assert f["requirement"] == "required"
    assert f["facet_key"] == "face"

    r = await client.get(f"/projects/{pid}/visual-facets")
    assert [row["id"] for row in r.json()] == [f["id"]]

    r = await client.patch(
        f"/visual-facets/{f['id']}",
        json={"requirement": "optional", "description": None},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["requirement"] == "optional"
    assert body["description"] is None

    # Target identity fields are not in the PATCH schema.
    r = await client.patch(
        f"/visual-facets/{f['id']}", json={"facet_key": "other"}
    )
    assert r.status_code == 422


async def test_facet_key_grammar_and_shape_validation(client, factory):
    pid = await _seed_project(factory)
    eva = await _entity(client, pid)

    bad_keys = ["", "UPPER", "has space", "x" * 129, "-leading", "_lead"]
    for key in bad_keys:
        r = await client.post(
            f"/projects/{pid}/visual-facets",
            json={
                "target_kind": "entity", "entity_id": eva["id"],
                "facet_key": key,
            },
        )
        assert r.status_code == 422, (key, r.text)
        assert r.json()["error_code"] == "VALIDATION_ERROR"

    # Shape: entity facet with feature_id, and vice versa.
    r = await client.post(
        f"/projects/{pid}/visual-facets",
        json={"target_kind": "entity", "facet_key": "face"},
    )
    assert r.status_code == 422
    r = await client.post(
        f"/projects/{pid}/visual-facets",
        json={
            "target_kind": "entity", "entity_id": eva["id"],
            "feature_id": "x",
        },
    )
    assert r.status_code == 422
    r = await client.post(
        f"/projects/{pid}/visual-facets",
        json={"target_kind": "feature", "facet_key": "f"},
    )
    assert r.status_code == 422


async def test_facet_active_uniqueness_and_slot_freeing(client, factory):
    pid = await _seed_project(factory)
    eva = await _entity(client, pid)

    f1 = await _facet(client, pid, "entity", entity_id=eva["id"])
    r = await client.post(
        f"/projects/{pid}/visual-facets",
        json={
            "target_kind": "entity", "entity_id": eva["id"],
            "facet_key": "face",
        },
    )
    assert r.status_code == 409
    assert r.json()["error_code"] == "VISUAL_FACET_TARGET_INVALID"

    # Soft-delete frees the active coordinate (required facets are guarded
    # — §38 — so flip to optional first).
    await client.patch(
        f"/visual-facets/{f1['id']}", json={"requirement": "optional"}
    )
    assert (
        await client.delete(f"/visual-facets/{f1['id']}")
    ).status_code == 204
    await _facet(client, pid, "entity", entity_id=eva["id"])


async def test_facet_cross_project_target_rejected(client, factory):
    pid_a = await _seed_project(factory, "A")
    pid_b = await _seed_project(factory, "B")
    foreign = await _entity(client, pid_b)

    r = await client.post(
        f"/projects/{pid_a}/visual-facets",
        json={
            "target_kind": "entity", "entity_id": foreign["id"],
            "facet_key": "face",
        },
    )
    assert r.status_code == 409
    assert r.json()["error_code"] == "VISUAL_FACET_TARGET_INVALID"


async def test_facet_delete_guards(client, factory):
    pid = await _seed_project(factory)
    eva = await _entity(client, pid)
    f = await _facet(client, pid, "entity", entity_id=eva["id"])

    # Required facet cannot be deleted.
    r = await client.delete(f"/visual-facets/{f['id']}")
    assert r.status_code == 409
    assert r.json()["error_code"] == "VISUAL_FACET_DELETE_BLOCKED"
    assert r.json()["details"]["reason"] == "required"

    # Optional but with an active anchor still cannot.
    await client.patch(
        f"/visual-facets/{f['id']}", json={"requirement": "optional"}
    )
    # A second revision of the FACET'S OWN entity (r3-gate B: a
    # different Entity's revision is no longer a legal binding).
    r = await client.post(
        f"/entities/{eva['id']}/revisions",
        json={"spec": {"description": "second"}},
    )
    rev2 = r.json()["id"]
    r = await client.post(
        f"/visual-facets/{f['id']}/anchors",
        json={"entity_revision_id": rev2},
    )
    assert r.status_code == 201, r.text
    r = await client.delete(f"/visual-facets/{f['id']}")
    assert r.status_code == 409
    assert r.json()["details"]["reason"] == "active_anchors"

    anchor_id = (
        (await client.get(f"/visual-facets/{f['id']}/anchors")).json()[0]
        ["id"]
    )
    assert (
        await client.delete(f"/visual-anchors/{anchor_id}")
    ).status_code == 204
    assert (
        await client.delete(f"/visual-facets/{f['id']}")
    ).status_code == 204
    # Idempotent.
    assert (
        await client.delete(f"/visual-facets/{f['id']}")
    ).status_code == 204


# --- Value policies: server-derived M7 authority (§11, §16) ------------------


async def test_value_policies_server_derived_and_atomic(client, factory):
    pid = await _seed_project(factory)
    eva = await _entity(client, pid)
    feat = await _feature(client, eva["id"])

    f = await _facet(
        client, pid, "feature", feature_id=feat["id"],
        facet_key="cut-realization",
    )

    r = await client.put(
        f"/visual-facets/{f['id']}/value-policies",
        json={"policies": [
            {"value": "none", "policy": "not_applicable"},
            {"value": "fresh", "policy": "required"},
        ]},
    )
    assert r.status_code == 200, r.text
    rows = r.json()
    by_json = {row["feature_value_json"]: row for row in rows}
    assert by_json['"none"']["policy"] == "not_applicable"
    assert by_json['"fresh"']["policy"] == "required"
    import hashlib

    for row in rows:
        assert row["feature_value_hash"] == hashlib.sha256(
            row["feature_value_json"].encode("utf-8")
        ).hexdigest()

    # Illegal value (not an enum member) → 422, atomic full-set rejection.
    r = await client.put(
        f"/visual-facets/{f['id']}/value-policies",
        json={"policies": [
            {"value": "fresh", "policy": "required"},
            {"value": "bogus", "policy": "optional"},
        ]},
    )
    assert r.status_code == 422
    assert (
        r.json()["error_code"] == "VISUAL_FACET_VALUE_POLICY_INVALID"
    )
    # Previous set untouched.
    r = await client.get(f"/visual-facets/{f['id']}/value-policies")
    assert len(r.json()) == 2

    # Entity facets may not own value policies.
    e2 = await _entity(client, pid, name="Other")
    ef = await _facet(client, pid, "entity", entity_id=e2["id"])
    r = await client.put(
        f"/visual-facets/{ef['id']}/value-policies",
        json={"policies": [{"value": "fresh", "policy": "required"}]},
    )
    assert r.status_code == 422
    assert (
        r.json()["error_code"] == "VISUAL_FACET_VALUE_POLICY_INVALID"
    )


# --- VisualAnchor state binding (§17–18, §25) --------------------------------


async def test_entity_anchor_binding_and_active_uniqueness(client, factory):
    pid = await _seed_project(factory)
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    f = await _facet(client, pid, "entity", entity_id=eva["id"])

    r = await client.post(
        f"/visual-facets/{f['id']}/anchors",
        json={"entity_revision_id": rev1},
    )
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["entity_revision_id"] == rev1
    assert a["feature_value_hash"] is None
    assert a["approved_revision_id"] is None

    # Same exact state binding again → conflict.
    r = await client.post(
        f"/visual-facets/{f['id']}/anchors",
        json={"entity_revision_id": rev1},
    )
    assert r.status_code == 409
    assert r.json()["error_code"] == "VISUAL_ANCHOR_TARGET_INVALID"

    # Cross-Project EntityRevision rejected.
    pid_b = await _seed_project(factory, "B")
    eva_b, rev_b = await _entity_with_revision(
        client, factory, pid_b, name="Foreign"
    )
    r = await client.post(
        f"/visual-facets/{f['id']}/anchors",
        json={"entity_revision_id": rev_b},
    )
    assert r.status_code == 409
    assert r.json()["error_code"] == "VISUAL_ANCHOR_TARGET_INVALID"


async def test_feature_anchor_requires_value_and_context(client, factory):
    pid = await _seed_project(factory)
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    feat = await _feature(client, eva["id"])
    f = await _facet(
        client, pid, "feature", feature_id=feat["id"],
        facet_key="cut-realization",
    )

    # Missing context → rejected.
    r = await client.post(
        f"/visual-facets/{f['id']}/anchors", json={"value": "fresh"},
    )
    assert r.status_code == 409
    assert r.json()["error_code"] == "VISUAL_ANCHOR_TARGET_INVALID"

    r = await client.post(
        f"/visual-facets/{f['id']}/anchors",
        json={"value": "fresh", "visual_context_entity_revision_id": rev1},
    )
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["feature_value_json"] == '"fresh"'
    assert len(a["feature_value_hash"]) == 64
    assert a["visual_context_entity_revision_id"] == rev1

    # Same value + same context → duplicate binding conflict.
    r = await client.post(
        f"/visual-facets/{f['id']}/anchors",
        json={"value": "fresh", "visual_context_entity_revision_id": rev1},
    )
    assert r.status_code == 409

    # Same value, NEW revision context → distinct binding allowed (§13).
    r = await client.post(
        f"/entities/{eva['id']}/revisions",
        json={"spec": {"description": "2"}},
    )
    rev2 = r.json()["id"]
    await client.put(
        f"/entities/{eva['id']}/approved-revision",
        json={
            "revision_id": rev2,
            "expected_approved_revision_id": rev1,
        },
    )
    r = await client.post(
        f"/visual-facets/{f['id']}/anchors",
        json={"value": "fresh", "visual_context_entity_revision_id": rev2},
    )
    assert r.status_code == 201, r.text


async def test_feature_anchor_cross_project_context_rejected(
    client, factory,
):
    pid = await _seed_project(factory, "A")
    pid_b = await _seed_project(factory, "B")
    eva, _ = await _entity_with_revision(client, factory, pid)
    eva_b, rev_b = await _entity_with_revision(
        client, factory, pid_b, name="Foreign"
    )
    feat = await _feature(client, eva["id"])
    f = await _facet(
        client, pid, "feature", feature_id=feat["id"], facet_key="cut",
    )
    r = await client.post(
        f"/visual-facets/{f['id']}/anchors",
        json={
            "value": "fresh",
            "visual_context_entity_revision_id": rev_b,
        },
    )
    assert r.status_code == 409
    assert r.json()["error_code"] == "VISUAL_ANCHOR_TARGET_INVALID"


async def test_anchor_delete_blocked_while_approved_pointer_present(
    client, factory, engine,
):
    """§39 guard via direct pointer presence (approval lands in M8B; here
    we set the pointer by direct SQL to prove the fence reads it)."""
    pid = await _seed_project(factory)
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    f = await _facet(client, pid, "entity", entity_id=eva["id"])
    r = await client.post(
        f"/visual-facets/{f['id']}/anchors",
        json={"entity_revision_id": rev1},
    )
    anchor_id = r.json()["id"]

    assert (
        await client.delete(f"/visual-anchors/{anchor_id}")
    ).status_code == 204  # no pointer: fine

    r = await client.post(
        f"/visual-facets/{f['id']}/anchors",
        json={"entity_revision_id": rev1},
    )
    anchor_id = r.json()["id"]
    async with engine.begin() as conn:
        # FK enforcement is on; insert a real revision row first so the
        # approved pointer is FK-valid (M8B will own this via the API).
        await conn.execute(
            text(
                "INSERT INTO visual_anchor_revisions "
                "(id, visual_anchor_id, revision_number, snapshot_json, "
                " snapshot_hash) VALUES (:rid, :aid, 1, '{}', :sh)"
            ),
            {
                "rid": "00000000-0000-4000-8000-0000000000aa",
                "aid": anchor_id,
                "sh": "h" * 64,
            },
        )
        await conn.execute(
            text(
                "UPDATE visual_anchors SET approved_revision_id = "
                ":rid WHERE id = :a"
            ),
            {
                "rid": "00000000-0000-4000-8000-0000000000aa",
                "a": anchor_id,
            },
        )
    r = await client.delete(f"/visual-anchors/{anchor_id}")
    assert r.status_code == 409
    assert r.json()["error_code"] == "VISUAL_ANCHOR_DELETE_BLOCKED"


async def test_m7_regression_semantic_surface_untouched(client, factory):
    """The M7 relation surface still behaves identically alongside the M8
    tables (M8A gate: M7 regression)."""
    from tests.test_m7d_relations import (
        _predicate, _relation, _seed_project as _m7_seed,
    )

    pid = await _m7_seed(factory)
    from tests.test_m7d_relations import _entity

    eva = await _entity(client, pid, name="Eva")
    bag = await _entity(client, pid, kind="prop", name="Bag")
    p = await _predicate(client, pid, key="carries")
    r = await client.post(
        f"/projects/{pid}/continuity-relations",
        json={
            "subject_entity_id": eva["id"], "predicate_id": p["id"],
            "object_entity_id": bag["id"],
        },
    )
    assert r.status_code == 201, r.text


async def test_anchor_rejects_same_project_wrong_entity_revision(
    client, factory, engine,
):
    """r3-gate B: §13/§68 — an EntityRevision of a DIFFERENT Entity (same
    Project) is a wrong-EntityRevision target: 409
    VISUAL_ANCHOR_TARGET_INVALID, never an accepted binding."""
    pid = await _seed_project(factory)
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    alice, alice_rev = await _entity_with_revision(
        client, factory, pid, name="Alice"
    )
    f = await _facet(client, pid, "entity", entity_id=eva["id"],
                     facet_key="face")
    r = await client.post(
        f"/visual-facets/{f['id']}/anchors",
        json={"entity_revision_id": alice_rev},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error_code"] == "VISUAL_ANCHOR_TARGET_INVALID"
    assert "does not belong to" in body["message"]


async def test_feature_anchor_rejects_wrong_owner_context_revision(
    client, factory, engine,
):
    """r3-gate B: §13/§68 — a feature anchor's visual-context
    EntityRevision must belong to the Entity OWNING the ContinuityFeature;
    a same-Project revision of another Entity is rejected 409."""
    pid = await _seed_project(factory)
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    alice, alice_rev = await _entity_with_revision(
        client, factory, pid, name="Alice"
    )
    feat = await _feature(client, eva["id"])
    f = await _facet(
        client, pid, "feature", feature_id=feat["id"], facet_key="cut",
    )
    r = await client.post(
        f"/visual-facets/{f['id']}/anchors",
        json={"value": "fresh",
              "visual_context_entity_revision_id": alice_rev},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error_code"] == "VISUAL_ANCHOR_TARGET_INVALID"
    assert "owner of" in body["message"]

    # Positive control: the OWNING entity's revision is accepted.
    r = await client.post(
        f"/visual-facets/{f['id']}/anchors",
        json={"value": "fresh",
              "visual_context_entity_revision_id": rev1},
    )
    assert r.status_code == 201, r.text
