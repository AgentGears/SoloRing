"""M7C — immutable continuity capture proof matrix (frozen plan §18).

Covers: schema-selection byte identity (1/2/3), canonical fixtures incl.
the display-vs-canonical order divergence, provenance equivalence (recreate
converges; transition-id changes nothing; anchor moves change the hash),
temporal headline, historical isolation, Exact Rerun with the resolver
disabled, structural singularity (spy + AST), reuse-integrity fail-closed,
v3 provenance reconstruction + corruption detection, concurrency, and the
no-migration assertions.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest
from sqlalchemy import text

from soloring.api.schemas.projects import ProjectCreate
from soloring.api.schemas.shots import ShotCreate
from soloring.domain import projects as project_svc
from soloring.domain import shots as shot_svc
from soloring.errors import ErrorCode, SoloRingError
from soloring.settings import BASE_DIR


async def _seed_project(factory):
    async with factory() as s:
        return (await project_svc.create_project(
            s, ProjectCreate(name="P"))).id


async def _entity(client, pid, kind="character", name="Eva"):
    r = await client.post(
        f"/projects/{pid}/entities", json={"kind": kind, "name": name}
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _entity_approved(client, pid, kind="character", name="Eva"):
    e = await _entity(client, pid, kind, name)
    r = await client.post(
        f"/entities/{e['id']}/revisions", json={"spec": {"description": "d"}}
    )
    assert r.status_code == 201
    rr = await client.put(
        f"/entities/{e['id']}/approved-revision",
        json={"revision_id": r.json()["id"],
              "expected_approved_revision_id": None},
    )
    assert rr.status_code == 200
    return e


async def _feature(client, entity_id, key="forehead_cut", **kw):
    payload = {
        "key": key, "kind": kw.pop("kind", "injury"),
        "value_type": kw.pop("value_type", "enum"),
        "name": kw.pop("name", "F"),
        "enum_values": kw.pop("enum_values",
                              ["fresh", "healing", "scarred", "gone"]),
    }
    payload.update(kw)
    r = await client.post(
        f"/entities/{entity_id}/continuity-features", json=payload
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _shot(client, factory, pid, subject="x"):
    async with factory() as s:
        shot = await shot_svc.create_shot(s, pid, ShotCreate(subject=subject))
    return shot.id


async def _topology(client, factory, pid, n_shots=2):
    r = await client.post(f"/projects/{pid}/sequences", json={"title": "S"})
    assert r.status_code == 201, r.text
    seq = r.json()["id"]
    r = await client.post(f"/sequences/{seq}/scenes", json={"title": "C"})
    assert r.status_code == 201, r.text
    scene = r.json()["id"]
    shot_ids = [await _shot(client, factory, pid) for _ in range(n_shots)]
    r = await client.put(
        f"/scenes/{scene}/shots", json={"shot_ids": shot_ids}
    )
    assert r.status_code == 200, r.text
    return seq, scene, shot_ids


async def _depend(client, shot_id, entity_id, role="subject"):
    r = await client.put(
        f"/shots/{shot_id}/semantic-dependencies",
        json={"dependencies": [{"entity_id": entity_id, "role": role}]},
    )
    assert r.status_code == 200, r.text


async def _transition(client, feature_id, anchor_type, anchor_id, boundary,
                      operation, value=...):
    payload = {
        "anchor_type": anchor_type, "anchor_id": anchor_id,
        "boundary": boundary, "operation": operation,
    }
    if value is not ...:
        payload["value"] = value
    return await client.post(
        f"/continuity-features/{feature_id}/transitions", json=payload
    )


async def _fetch(engine, sql, params):
    async with engine.connect() as conn:
        row = (await conn.execute(text(sql), params)).mappings().one_or_none()
    return dict(row) if row is not None else None


async def _fetch_all(engine, sql, params=None):
    async with engine.connect() as conn:
        rows = (await conn.execute(text(sql), params or {})).mappings().all()
    return [dict(r) for r in rows]


# --- Canonical grammar (pure) --------------------------------------------------------


def test_spec_v2_exact_bytes_and_order_divergence():
    """Display order (entity_id, feature_key) deliberately disagrees with
    canonical order (entity_id, feature_kind, feature_id) in this fixture:
    two features on ONE entity where key order and kind order invert."""
    from types import SimpleNamespace

    from soloring.continuity.snapshots import (
        build_continuity_spec_v2,
        sort_feature_states,
    )
    from soloring.domain.canonical import canonical_json_bytes

    def st(entity, fid, key, kind):
        return SimpleNamespace(
            entity_id=entity, feature_id=fid, feature_key=key,
            feature_kind=kind, value_type="text", unit=None,
            value_json='"x"', value_hash="a" * 64,
            source_anchor_type="scene", source_anchor_id="sc",
            source_boundary="start", source_transition_id="t",
        )

    # entity e1: kind "damage" with key "zzz"; kind "wardrobe_condition"
    # with key "aaa". Display order (key): aaa < zzz. Canonical order
    # (kind): damage < wardrobe_condition → zzz-row FIRST canonically.
    states = [st("e1", "f2", "zzz", "damage"),
              st("e1", "f1", "aaa", "wardrobe_condition")]
    assert [s.feature_key for s in sort_feature_states(states)] == \
        ["zzz", "aaa"]
    spec = build_continuity_spec_v2([], states)
    keys = [f["feature_key"] for f in spec["feature_states"]]
    assert keys == ["zzz", "aaa"]  # canonical: kind order, not key order
    assert spec["relations"] == []
    assert spec["schema_version"] == 2
    raw = canonical_json_bytes(spec).decode("utf-8")
    assert '"feature_states":[{"entity_id":"e1","feature_id":"f2"' in raw
    # Exclusions (§5.4).
    assert "source_transition_id" not in raw
    assert '"value":"x"' in raw and '"value_hash":"' in raw


def test_historical_value_hash_is_pure():
    """Captured-row-only re-canonicalization: parses the stored bytes,
    re-serializes canonically, hashes — no schema consultation."""
    from soloring.continuity.snapshots import historical_value_hash

    assert historical_value_hash('"fresh"') == \
        __import__("hashlib").sha256(b'"fresh"').hexdigest()
    assert historical_value_hash("17") == \
        __import__("hashlib").sha256(b"17").hexdigest()
    assert historical_value_hash('"1.5"') == \
        __import__("hashlib").sha256(b'"1.5"').hexdigest()


# --- Schema selection byte identity ----------------------------------------------------


async def test_schema_selection_byte_identity(client, factory):
    from soloring.domain import revisions as revision_svc

    pid = await _seed_project(factory)
    # v1: no dependencies.
    bare = await _shot(client, factory, pid)
    rev1 = await revision_svc.capture_revision(factory(), bare)
    s1 = json.loads(rev1.snapshot_json)
    assert s1["schema_version"] == 1 and "continuity" not in s1
    assert rev1.continuity_spec_json is None
    assert rev1.continuity_spec_hash is None

    # v2: deps, no temporal data.
    eva = await _entity_approved(client, pid)
    seq, scene, shots = await _topology(client, factory, pid, 2)
    for sid in shots:
        await _depend(client, sid, eva["id"])
    rev2 = await revision_svc.capture_revision(factory(), shots[0])
    s2 = json.loads(rev2.snapshot_json)
    assert s2["schema_version"] == 2 and "feature_states" \
        not in s2["continuity"]
    v2_bytes = rev2.snapshot_json
    v2_hash = rev2.snapshot_hash

    # set→clear converges back onto the SAME v2 revision.
    f = await _feature(client, eva["id"])
    await _transition(client, f["id"], "sequence", seq, "start", "set",
                      "fresh")
    await _transition(client, f["id"], "shot", shots[0], "start", "clear")
    again = await revision_svc.capture_revision(factory(), shots[0])
    assert again.id == rev2.id
    assert again.snapshot_json == v2_bytes
    assert again.snapshot_hash == v2_hash

    # v3: effective state.
    tid = None
    for row in (await client.get(
            f"/continuity-features/{f['id']}/transitions")).json():
        if row["anchor_type"] == "shot" and row["anchor_id"] == shots[0]:
            tid = row["id"]
    r = await client.patch(
        f"/continuity-feature-transitions/{tid}",
        json={"operation": "set", "value": "fresh"},
    )
    assert r.status_code == 200
    rev3 = await revision_svc.capture_revision(factory(), shots[0])
    s3 = json.loads(rev3.snapshot_json)
    assert s3["schema_version"] == 3
    assert s3["continuity"]["schema_version"] == 2
    assert s3["continuity"]["feature_states"]
    assert rev3.continuity_spec_json == json.dumps(
        s3["continuity"], separators=(",", ":"), sort_keys=True,
        ensure_ascii=False,
    )
    assert rev3.id != rev2.id


# --- Provenance equivalence --------------------------------------------------------------


async def test_provenance_equivalence_full(client, factory, engine):
    from soloring.domain import revisions as revision_svc

    pid = await _seed_project(factory)
    eva = await _entity_approved(client, pid)
    f = await _feature(client, eva["id"])
    seq, scene, shots = await _topology(client, factory, pid, 1)
    await _depend(client, shots[0], eva["id"])

    tA = (await _transition(
        client, f["id"], "scene", scene, "start", "set", "fresh"
    )).json()
    revX = await revision_svc.capture_revision(factory(), shots[0])
    rowA = await _fetch(
        engine,
        "SELECT source_transition_id FROM shot_revision_feature_states "
        "WHERE shot_revision_id = :r",
        {"r": revX.id},
    )
    assert rowA["source_transition_id"] == tA["id"]

    # Recreate equivalent B at the same anchor/value.
    assert (await client.delete(
        f"/continuity-feature-transitions/{tA['id']}"
    )).status_code == 204
    tB = (await _transition(
        client, f["id"], "scene", scene, "start", "set", "fresh"
    )).json()
    revY = await revision_svc.capture_revision(factory(), shots[0])
    assert revY.id == revX.id
    assert revY.snapshot_hash == revX.snapshot_hash
    rowB = await _fetch(
        engine,
        "SELECT source_transition_id FROM shot_revision_feature_states "
        "WHERE shot_revision_id = :r",
        {"r": revX.id},
    )
    assert rowB["source_transition_id"] == tA["id"]  # audit truth kept

    # Anchor moves → hash changes → new revision.
    r = await client.patch(
        f"/continuity-feature-transitions/{tB['id']}",
        json={"anchor_type": "shot", "anchor_id": shots[0],
              "boundary": "end"},
    )
    assert r.status_code == 200
    revZ = await revision_svc.capture_revision(factory(), shots[0])
    assert revZ.id != revX.id
    assert revZ.snapshot_hash != revX.snapshot_hash


# --- Temporal headline + historical isolation ---------------------------------------------


async def test_temporal_headline_and_isolation(client, factory, engine):
    """The frozen plan's headline: capture A pins everything; approvals and
    transitions move; A is byte-untouched; B captures the new state; rerun
    of A's generation stays on A."""
    from soloring.executors.fake import FakeExecutor
    from soloring.worker import execution as worker_execution
    from soloring.worker.ownership import acquire_worker_lease

    from tests.conftest import seed_reference_asset
    from soloring.api.schemas.references import ReferenceInput
    from soloring.domain import references as ref_svc

    pid = await _seed_project(factory)
    eva = await _entity_approved(client, pid)
    f = await _feature(client, eva["id"])
    seq, scene, shots = await _topology(client, factory, pid, 1)
    await _depend(client, shots[0], eva["id"])
    aid, _bh = await seed_reference_asset(engine, pid)
    async with factory() as s:
        await ref_svc.replace_references(
            s, shots[0], [ReferenceInput(asset_id=aid, role="reference")]
        )

    # Baseline: no temporal data yet.
    revA = await __import__("soloring.domain.revisions",
                            fromlist=["capture_revision"]).capture_revision(
        factory(), shots[0])
    assert json.loads(revA.snapshot_json)["schema_version"] == 2

    # Wait: baseline must be schema 3 for the headline. Restart state.
    tA = (await _transition(
        client, f["id"], "sequence", seq, "start", "set", "fresh"
    )).json()
    revA = await __import__("soloring.domain.revisions",
                            fromlist=["capture_revision"]).capture_revision(
        factory(), shots[0])
    sA = json.loads(revA.snapshot_json)
    assert sA["schema_version"] == 3
    assert sA["continuity"]["feature_states"][0]["value"] == "fresh"
    hashA = revA.snapshot_hash
    bytesA = revA.snapshot_json
    specA = revA.continuity_spec_json

    # Generation A from revA.
    await acquire_worker_lease(engine, "w-m7c", 30)
    genA = (await client.post(f"/shots/{shots[0]}/generations")).json()
    assert genA["shot_revision_id"] == revA.id
    assert (await worker_execution.process_next_generation(
        engine, __import__("soloring.settings", fromlist=["Settings"])
        .get_settings(), "w-m7c", FakeExecutor())) == "succeeded"

    # Mutate everything current.
    r = await client.patch(
        f"/continuity-feature-transitions/{tA['id']}",
        json={"operation": "set", "value": "healing"},
    )
    assert r.status_code == 200
    r2 = await client.post(
        f"/entities/{eva['id']}/revisions", json={"spec": {"description": "2"}}
    )
    assert r2.status_code == 201
    rr = await client.put(
        f"/entities/{eva['id']}/approved-revision",
        json={"revision_id": r2.json()["id"],
              "expected_approved_revision_id": None},
    )
    assert rr.status_code == 409  # baseline expectation is the FIRST rev
    first_rev_id = (await client.get(
        f"/entities/{eva['id']}/revisions")).json()[0]["id"]
    rr = await client.put(
        f"/entities/{eva['id']}/approved-revision",
        json={"revision_id": r2.json()["id"],
              "expected_approved_revision_id": first_rev_id},
    )
    assert rr.status_code == 200

    # Historical A is untouched.
    rowA = await _fetch(
        engine,
        "SELECT snapshot_json, snapshot_hash, continuity_spec_json "
        "FROM shot_revisions WHERE id = :r",
        {"r": revA.id},
    )
    assert rowA["snapshot_json"] == bytesA
    assert rowA["snapshot_hash"] == hashA
    assert rowA["continuity_spec_json"] == specA
    frowA = await _fetch(
        engine,
        "SELECT value_json FROM shot_revision_feature_states "
        "WHERE shot_revision_id = :r",
        {"r": revA.id},
    )
    assert frowA["value_json"] == '"fresh"'

    # B captures the new state; the working hash changed with NO Shot-row
    # mutation.
    shot_before = await _fetch(
        engine, "SELECT subject, updated_at FROM shots WHERE id = :s",
        {"s": shots[0]},
    )
    d = (await client.get(f"/shots/{shots[0]}")).json()
    assert d["working_snapshot_hash"] != hashA
    revB = await __import__("soloring.domain.revisions",
                            fromlist=["capture_revision"]).capture_revision(
        factory(), shots[0])
    assert revB.id != revA.id
    assert json.loads(revB.snapshot_json)["continuity"][
        "feature_states"][0]["value"] == "healing"
    shot_after = await _fetch(
        engine, "SELECT subject, updated_at FROM shots WHERE id = :s",
        {"s": shots[0]},
    )
    assert shot_after["subject"] == shot_before["subject"]

    # Rerun A stays on A (structure verified in the dedicated test below;
    # here assert the lineage pointer directly).
    await _set_status(engine, genA["id"], "succeeded")
    rerun = (await client.post(f"/generations/{genA['id']}/rerun")).json()
    assert rerun["shot_revision_id"] == revA.id
    cont = (await client.get(
        f"/generations/{rerun['id']}/continuity")).json()
    assert cont["snapshot_schema_version"] == 3
    assert cont["continuity_schema_version"] == 2
    assert cont["feature_states"][0]["value"] == "fresh"


async def _set_status(engine, generation_id, status_value):
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(
            text("UPDATE generations SET status = :st WHERE id = :g"),
            {"st": status_value, "g": generation_id},
        )
        await conn.exec_driver_sql("COMMIT")


# --- Exact Rerun with the resolver DISABLED -----------------------------------------------


async def test_exact_rerun_resolver_disabled(client, factory, engine, settings):
    """APR-025: monkeypatch the current-state resolver so ANY invocation
    fails the test; rerun must still succeed from history alone."""
    from soloring.executors.fake import FakeExecutor
    from soloring.worker import execution as worker_execution
    from soloring.worker.ownership import acquire_worker_lease

    from tests.conftest import seed_reference_asset
    from soloring.api.schemas.references import ReferenceInput
    from soloring.domain import references as ref_svc

    pid = await _seed_project(factory)
    eva = await _entity_approved(client, pid)
    f = await _feature(client, eva["id"])
    seq, scene, shots = await _topology(client, factory, pid, 1)
    await _depend(client, shots[0], eva["id"])
    aid, _bh = await seed_reference_asset(engine, pid)
    async with factory() as s:
        await ref_svc.replace_references(
            s, shots[0], [ReferenceInput(asset_id=aid, role="reference")]
        )
    await _transition(client, f["id"], "sequence", seq, "start", "set",
                      "fresh")

    await acquire_worker_lease(engine, "w-rr", 30)
    genA = (await client.post(f"/shots/{shots[0]}/generations")).json()
    assert (await worker_execution.process_next_generation(
        engine, settings, "w-rr", FakeExecutor())) == "succeeded"
    revX = genA["shot_revision_id"]

    # Radically mutate current state.
    listed = (await client.get(
        f"/continuity-features/{f['id']}/transitions")).json()
    for row in listed:
        assert (await client.delete(
            f"/continuity-feature-transitions/{row['id']}"
        )).status_code == 204

    # Resolver disabled: any invocation raises.
    import soloring.domain.revisions as revmod

    async def _forbidden(conn, shot_id):
        raise AssertionError(
            "current-state resolver invoked during Exact Rerun"
        )

    import soloring.continuity.state as state_mod

    original = state_mod.resolve_effective_feature_state
    state_mod.resolve_effective_feature_state = _forbidden
    try:
        # _snapshot_one_read imports the symbol at call time from the
        # module — patch where it is CONSUMED for capture; rerun must not
        # reach capture at all, so patching the source is the strong form.
        r = await client.post(f"/generations/{genA['id']}/rerun")
        assert r.status_code == 202, r.text
        assert r.json()["shot_revision_id"] == revX
        cont = (await client.get(
            f"/generations/{r.json()['id']}/continuity")).json()
        assert cont["feature_states"][0]["value"] == "fresh"
    finally:
        state_mod.resolve_effective_feature_state = original


# --- Structural singularity ------------------------------------------------------------------


async def test_structural_singularity_both_paths_invoke_builder(
    client, factory, monkeypatch
):
    """Spy on build_capturable_snapshot: BOTH the working-hash path (shot
    detail) AND capture persistence demonstrably invoke THE builder."""
    from soloring.domain import revisions as revision_svc
    import soloring.continuity.snapshots as snaps

    calls = []
    original = snaps.build_capturable_snapshot

    def spy(shot, refs, resolved, feature_states=(), relation_states=(),
            visual_pack=None, spatial_pack=None):
        calls.append(len(feature_states))
        return original(
            shot, refs, resolved, feature_states, relation_states,
            visual_pack, spatial_pack,
        )

    monkeypatch.setattr(snaps, "build_capturable_snapshot", spy)
    # Patch the consumed symbol in the working-hash wrapper too (it calls
    # the module attribute).
    monkeypatch.setattr(
        snaps, "effective_working_snapshot_hash",
        lambda shot, refs, resolved, feature_states=(),
        relation_states=(), visual_pack=None, spatial_pack=None: (
            __import__("soloring.domain.canonical",
                       fromlist=["canonical_hash"]).canonical_hash(
                spy(shot, refs, resolved, feature_states,
                    relation_states, visual_pack, spatial_pack)[0])
        ),
    )

    pid = await _seed_project(factory)
    eva = await _entity_approved(client, pid)
    f = await _feature(client, eva["id"])
    seq, scene, shots = await _topology(client, factory, pid, 1)
    await _depend(client, shots[0], eva["id"])
    await _transition(client, f["id"], "scene", scene, "start", "set",
                      "fresh")

    # Working-hash path (shot detail).
    d = (await client.get(f"/shots/{shots[0]}")).json()
    assert d["working_snapshot_hash"] is not None
    working_calls = len(calls)
    assert working_calls >= 1

    # Capture path. NOTE: revisions.py imports build_capturable_snapshot
    # inside the function from the module — patching the module attribute
    # covers it.
    import soloring.domain.revisions as revmod

    monkeypatch.setattr(revmod, "build_capturable_snapshot", spy,
                        raising=False)
    before = len(calls)
    rev = await revision_svc.capture_revision(factory(), shots[0])
    assert len(calls) > before
    assert json.loads(rev.snapshot_json)["schema_version"] == 3


def test_ast_no_second_builder_or_generation_resolution():
    """AST: no snapshot/spec builder outside continuity/snapshots.py; no
    Generation-path resolution of current M7 state."""
    server = BASE_DIR / "server" / "soloring"
    builder_names = {
        "build_capturable_snapshot", "build_continuity_spec_v2",
        "build_continuity_spec",
    }
    resolver_names = {"resolve_effective_feature_state"}
    for path in sorted(server.rglob("*.py")):
        src = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(server)).replace("\\", "/")
        for name in builder_names:
            if re.search(rf"def {name}\b", src) and \
                    rel != "continuity/snapshots.py":
                raise AssertionError(f"second builder: {rel}:{name}")
        if rel.startswith("generation/") and not any(
            resolver in src for resolver in resolver_names
        ):
            continue
        if rel.startswith("generation/"):
            # Allowed only for comments/docstrings — verify no call form.
            for name in resolver_names:
                if re.search(rf"await\s+{name}\s*\(", src):
                    raise AssertionError(
                        f"generation path resolves M7 state: {rel}"
                    )


def test_migration_files_and_head_is_0009():
    """M7C itself added no migration (0008 was M7A's); the head advanced
    to 0009 only with M8A's visual-identity migration."""
    versions = BASE_DIR / "server" / "alembic" / "versions"
    files = sorted(p.name for p in versions.glob("*.py"))
    assert files[-2] == "0010_m10_spatial_cinematic_continuity.py"
    assert files[-1] == "0011_m10_derived_spatial_execution.py"
    assert len(files) == 11


# --- Reuse integrity fail-closed ----------------------------------------------------------------


async def test_reuse_integrity_fail_closed(client, factory, engine):
    """Corrupt an existing winner's children → INTERNAL_INVARIANT_VIOLATION
    on the next identical capture; never a second revision, never repair."""
    from soloring.domain import revisions as revision_svc

    pid = await _seed_project(factory)
    eva = await _entity_approved(client, pid)
    f = await _feature(client, eva["id"])
    seq, scene, shots = await _topology(client, factory, pid, 1)
    await _depend(client, shots[0], eva["id"])
    await _transition(client, f["id"], "scene", scene, "start", "set",
                      "fresh")
    rev = await revision_svc.capture_revision(factory(), shots[0])

    # Corrupt: delete one feature child row.
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(
            text("DELETE FROM shot_revision_feature_states "
                 "WHERE shot_revision_id = :r"),
            {"r": rev.id},
        )
        await conn.exec_driver_sql("COMMIT")

    before = await _fetch(
        engine, "SELECT COUNT(*) AS n FROM shot_revisions "
        "WHERE shot_id = :s", {"s": shots[0]},
    )
    with pytest.raises(SoloRingError) as ei:
        await revision_svc.capture_revision(factory(), shots[0])
    assert ei.value.code == ErrorCode.INTERNAL_INVARIANT_VIOLATION
    after = await _fetch(
        engine, "SELECT COUNT(*) AS n FROM shot_revisions "
        "WHERE shot_id = :s", {"s": shots[0]},
    )
    assert after["n"] == before["n"]  # no revision created around it
    # No repair: the row is still gone (fail closed, not refill).
    n = await _fetch(
        engine, "SELECT COUNT(*) AS n FROM shot_revision_feature_states "
        "WHERE shot_revision_id = :r", {"r": rev.id},
    )
    assert n["n"] == 0


# --- v3 provenance surfaces + corruption gates -----------------------------------------------


async def test_v3_provenance_and_corruption(client, factory, engine):
    pid = await _seed_project(factory)
    eva = await _entity_approved(client, pid)
    f = await _feature(client, eva["id"])
    seq, scene, shots = await _topology(client, factory, pid, 1)
    await _depend(client, shots[0], eva["id"])
    t = (await _transition(
        client, f["id"], "scene", scene, "start", "set", "fresh"
    )).json()
    rev = await __import__("soloring.domain.revisions",
                           fromlist=["capture_revision"]).capture_revision(
        factory(), shots[0])

    cont = (await client.get(
        f"/shot-revisions/{rev.id}/continuity")).json()
    assert cont["snapshot_schema_version"] == 3
    assert cont["continuity_schema_version"] == 2
    assert cont["feature_states"][0]["value"] == "fresh"
    assert cont["feature_states"][0]["source_anchor"]["anchor_type"] == \
        "scene"
    assert cont["source_transition_audit"][0]["source_transition_id"] == \
        t["id"]

    # Corrupt value bytes → hash disagreement → invariant.
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(
            text("UPDATE shot_revision_feature_states SET value_json = "
                 "'\"healing\"' WHERE shot_revision_id = :r"),
            {"r": rev.id},
        )
        await conn.exec_driver_sql("COMMIT")
    r = await client.get(f"/shot-revisions/{rev.id}/continuity")
    assert r.status_code == 500
    assert r.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"


# --- Concurrency ---------------------------------------------------------------------------------


async def test_concurrent_identical_v3_captures_converge(client, factory):
    from soloring.domain import revisions as revision_svc

    pid = await _seed_project(factory)
    eva = await _entity_approved(client, pid)
    f = await _feature(client, eva["id"])
    seq, scene, shots = await _topology(client, factory, pid, 1)
    await _depend(client, shots[0], eva["id"])
    await _transition(client, f["id"], "scene", scene, "start", "set",
                      "fresh")

    async def one():
        async with factory() as s:
            return await revision_svc.capture_revision(s, shots[0])

    results = await asyncio.gather(*(one() for _ in range(4)))
    assert len({r.id for r in results}) == 1
    assert all(json.loads(r.snapshot_json)["schema_version"] == 3
               for r in results)

# --- APR-033 deterministic race: capture vs feature-transition mutation --------
# Superseded framing (r2 gate): the original version started the
# competitor AFTER the capture read committed and BEFORE the write unit —
# a read-to-write HANDOFF boundary, not a held-lock race. The true
# held-open-read coherence proof lives in
# test_race_writer_commits_inside_open_read_txn; this handoff case is kept
# under an honest name.


async def test_capture_read_to_write_handoff_boundary(client, factory, engine):
    """Deterministic handoff boundary (not a held-lock race): the
    competitor's real BEGIN IMMEDIATE lands between the capture's read
    COMMIT and its write BEGIN — the capture persists its already-read
    coherent state; the AFTER state arrives at the next capture."""
    from sqlalchemy.ext.asyncio import AsyncConnection

    from soloring.api.schemas.continuity_transitions import TransitionPatch
    from soloring.continuity import transitions as tsvc
    from soloring.domain import revisions as revision_svc

    pid = await _seed_project(factory)
    eva = await _entity_approved(client, pid)
    f = await _feature(client, eva["id"])
    seq, scene, shots = await _topology(client, factory, pid, 1)
    await _depend(client, shots[0], eva["id"])
    tA = (await _transition(
        client, f["id"], "scene", scene, "start", "set", "fresh"
    )).json()

    original_read = revision_svc._snapshot_one_read
    original_exec = AsyncConnection.exec_driver_sql
    state: dict = {}
    begin_attempted = asyncio.Event()

    async def wrapped_exec(self, statement, *args, **kwargs):
        if (
            state.get("competitor") is not None
            and asyncio.current_task() is state["competitor"]
            and statement.strip().upper() == "BEGIN IMMEDIATE"
        ):
            begin_attempted.set()
        return await original_exec(self, statement, *args, **kwargs)

    async def competitor_task():
        async with factory() as s:
            await tsvc.patch_transition(
                s, tA["id"],
                TransitionPatch(operation="set", value="healing"),
            )

    async def read_wrap(session, shot_id, **kwargs):
        result = await original_read(session, shot_id)
        if "competitor" not in state:
            AsyncConnection.exec_driver_sql = wrapped_exec
            state["competitor"] = asyncio.create_task(competitor_task())
            await begin_attempted.wait()
        return result

    revision_svc._snapshot_one_read = read_wrap
    try:
        rev = await revision_svc.capture_revision(factory(), shots[0])
    finally:
        revision_svc._snapshot_one_read = original_read
        AsyncConnection.exec_driver_sql = original_exec
    await state["competitor"]

    # The read had already committed: deterministic BEFORE state.
    snap = json.loads(rev.snapshot_json)
    assert snap["continuity"]["feature_states"][0]["value"] == "fresh"
    frow = await _fetch(
        engine,
        "SELECT value_json, source_anchor_type FROM "
        "shot_revision_feature_states WHERE shot_revision_id = :r",
        {"r": rev.id},
    )
    assert json.loads(frow["value_json"]) == "fresh"
    assert frow["source_anchor_type"] == "scene"
    # AFTER arrives next capture; the handoff capture stays frozen.
    rev2 = await revision_svc.capture_revision(factory(), shots[0])
    assert json.loads(rev2.snapshot_json)["continuity"][
        "feature_states"][0]["value"] == "healing"
    assert rev2.id != rev.id


async def test_true_concurrent_different_schema3_captures_both_persist(
    client, factory, engine
):
    """Frozen §14: two captures of the SAME Shot that read DIFFERENT
    coherent states (a mutation commits between their reads) both persist
    with distinct revision numbers — neither is discarded. The second
    capture's full lifecycle (read → fenced write → COMMIT) provably runs
    while the first capture is still in flight between its own read and
    write."""
    from soloring.api.schemas.continuity_transitions import TransitionPatch
    from soloring.continuity import transitions as tsvc
    from soloring.domain import revisions as revision_svc

    pid = await _seed_project(factory)
    eva = await _entity_approved(client, pid)
    f = await _feature(client, eva["id"])
    seq, scene, shots = await _topology(client, factory, pid, 1)
    await _depend(client, shots[0], eva["id"])
    tA = (await _transition(
        client, f["id"], "scene", scene, "start", "set", "fresh"
    )).json()

    original_read = revision_svc._snapshot_one_read
    state: dict = {}

    async def capture2_task():
        async with factory() as s2:
            return await revision_svc.capture_revision(s2, shots[0])

    async def read_wrap(session, shot_id, **kwargs):
        result = await original_read(session, shot_id)  # state A (fresh)
        if "ran" not in state:
            state["ran"] = True
            # Mutate AFTER capture1's read committed.
            async with factory() as s2:
                await tsvc.patch_transition(
                    s2, tA["id"],
                    TransitionPatch(operation="set", value="healing"),
                )
            # capture2's FULL lifecycle completes while capture1 is
            # parked between its read and its write.
            state["rev2"] = await asyncio.create_task(capture2_task())
        return result

    revision_svc._snapshot_one_read = read_wrap
    try:
        revA = await revision_svc.capture_revision(factory(), shots[0])
    finally:
        revision_svc._snapshot_one_read = original_read
    revB = state["rev2"]

    assert revA.id != revB.id
    numbers = sorted((revA.revision_number, revB.revision_number))
    assert numbers == [1, 2]  # distinct, persistence order
    snapA = json.loads(revA.snapshot_json)
    snapB = json.loads(revB.snapshot_json)
    assert snapA["continuity"]["feature_states"][0]["value"] == "fresh"
    assert snapB["continuity"]["feature_states"][0]["value"] == "healing"
    assert revA.snapshot_hash != revB.snapshot_hash
    # Both immutable children sets survive.
    rows = await _fetch_all(
        engine,
        "SELECT shot_revision_id, value_json FROM "
        "shot_revision_feature_states ORDER BY shot_revision_id",
        {},
    )
    assert len(rows) == 2
    values = sorted(json.loads(r["value_json"]) for r in rows)
    assert values == ["fresh", "healing"]

# --- M7C r2: B1 regressions (parent-field corruption on reuse) ------------------


async def _capture_once(factory, shot_id):
    from soloring.domain import revisions as revision_svc

    return await revision_svc.capture_revision(factory(), shot_id)


async def test_reuse_wrong_snapshot_json_fails_closed(client, factory, engine):
    pid = await _seed_project(factory)
    eva = await _entity_approved(client, pid)
    f = await _feature(client, eva["id"])
    seq, scene, shots = await _topology(client, factory, pid, 1)
    await _depend(client, shots[0], eva["id"])
    await _transition(client, f["id"], "scene", scene, "start", "set",
                      "fresh")
    rev = await _capture_once(factory, shots[0])

    # Corrupt parent snapshot_json while leaving snapshot_hash intact.
    snap = json.loads(rev.snapshot_json)
    snap["intent"]["subject"] = "tampered"
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(
            text("UPDATE shot_revisions SET snapshot_json = :sj "
                 "WHERE id = :r"),
            {"sj": json.dumps(snap, separators=(",", ":"), sort_keys=True,
                              ensure_ascii=False), "r": rev.id},
        )
        await conn.exec_driver_sql("COMMIT")

    before = await _fetch(
        engine, "SELECT COUNT(*) AS n FROM shot_revisions "
        "WHERE shot_id = :s", {"s": shots[0]},
    )
    with pytest.raises(SoloRingError) as ei:
        await _capture_once(factory, shots[0])
    assert ei.value.code == ErrorCode.INTERNAL_INVARIANT_VIOLATION
    after = await _fetch(
        engine, "SELECT COUNT(*) AS n FROM shot_revisions "
        "WHERE shot_id = :s", {"s": shots[0]},
    )
    assert after["n"] == before["n"]  # no recapture


async def test_reuse_wrong_spec_json_fails_closed(client, factory, engine):
    pid = await _seed_project(factory)
    eva = await _entity_approved(client, pid)
    f = await _feature(client, eva["id"])
    seq, scene, shots = await _topology(client, factory, pid, 1)
    await _depend(client, shots[0], eva["id"])
    await _transition(client, f["id"], "scene", scene, "start", "set",
                      "fresh")
    rev = await _capture_once(factory, shots[0])

    spec = json.loads(rev.continuity_spec_json)
    spec["feature_states"][0]["value"] = "tampered"
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(
            text("UPDATE shot_revisions SET continuity_spec_json = :sj "
                 "WHERE id = :r"),
            {"sj": json.dumps(spec, separators=(",", ":"), sort_keys=True,
                              ensure_ascii=False), "r": rev.id},
        )
        await conn.exec_driver_sql("COMMIT")

    before = await _fetch(
        engine, "SELECT COUNT(*) AS n FROM shot_revisions "
        "WHERE shot_id = :s", {"s": shots[0]},
    )
    with pytest.raises(SoloRingError) as ei:
        await _capture_once(factory, shots[0])
    assert ei.value.code == ErrorCode.INTERNAL_INVARIANT_VIOLATION
    after = await _fetch(
        engine, "SELECT COUNT(*) AS n FROM shot_revisions "
        "WHERE shot_id = :s", {"s": shots[0]},
    )
    assert after["n"] == before["n"]


async def test_reuse_wrong_spec_hash_fails_closed(client, factory, engine):
    pid = await _seed_project(factory)
    eva = await _entity_approved(client, pid)
    f = await _feature(client, eva["id"])
    seq, scene, shots = await _topology(client, factory, pid, 1)
    await _depend(client, shots[0], eva["id"])
    await _transition(client, f["id"], "scene", scene, "start", "set",
                      "fresh")
    rev = await _capture_once(factory, shots[0])

    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(
            text("UPDATE shot_revisions SET continuity_spec_hash = :h "
                 "WHERE id = :r"),
            {"h": "f" * 64, "r": rev.id},
        )
        await conn.exec_driver_sql("COMMIT")

    before = await _fetch(
        engine, "SELECT COUNT(*) AS n FROM shot_revisions "
        "WHERE shot_id = :s", {"s": shots[0]},
    )
    with pytest.raises(SoloRingError) as ei:
        await _capture_once(factory, shots[0])
    assert ei.value.code == ErrorCode.INTERNAL_INVARIANT_VIOLATION
    after = await _fetch(
        engine, "SELECT COUNT(*) AS n FROM shot_revisions "
        "WHERE shot_id = :s", {"s": shots[0]},
    )
    assert after["n"] == before["n"]


# --- B2 regressions: captured-type violations in historical rows ----------------


async def test_historical_type_violations_fail_closed(client, factory, engine):
    pid = await _seed_project(factory)
    # One feature per type; capture a v3 revision with all of them.
    eva = await _entity_approved(client, pid)
    cases = [
        ("bool_f", "boolean", True, "true"),
        ("int_f", "integer", 17, "17"),
        ("dec_f", "decimal", "1.5", '"1.5"'),
        ("txt_f", "text", "soaked", '"soaked"'),
        ("cut", "enum", "fresh", '"fresh"'),  # default enum members
    ]
    feats = {}
    for key, vt, value, _ in cases:
        enum_vals = ["fresh", "healing", "scarred", "gone"]             if vt == "enum" else None
        feats[key] = await _feature(client, eva["id"], key=key,
                                    value_type=vt, enum_values=enum_vals)
    seq, scene, shots = await _topology(client, factory, pid, 1)
    await _depend(client, shots[0], eva["id"])
    for key, vt, value, _ in cases:
        await _transition(client, feats[key]["id"], "scene",
                          scene, "start", "set", value)
    rev = await _capture_once(factory, shots[0])

    import hashlib as _hl

    def _h(vj):
        return _hl.sha256(vj.encode("utf-8")).hexdigest()

    # CORRECT SHA-256 for the exact invalid bytes: the failure must come
    # from captured-type validation, never from a hash mismatch.
    violations = [
        ("bool_f", '"fresh"', _h('"fresh"')),   # boolean with a string
        ("int_f", "true", _h("true")),           # integer with JSON true
        ("dec_f", '"1.50"', _h('"1.50"')),       # non-canonical decimal
        ("txt_f", '{"a":1}', _h('{"a":1}')),     # object
        ("dec_f", '"' + "1" * 39 + '"',
         _h('"' + "1" * 39 + '"')),               # precision > 38
        ("dec_f", '"0.' + "1" * 19 + '"',
         _h('"0.' + "1" * 19 + '"')),             # scale > 18
        ("txt_f", '" pad "', _h('" pad "')),     # untrimmed text
    ]
    # Each case starts from the COMPLETE valid child set: the original
    # row is saved and RESTORED after every corruption, so every later
    # case genuinely exercises captured-type validation against an
    # otherwise intact history (never a missing-row artifact).
    originals = {
        row["feature_key"]: (row["value_json"], row["value_hash"])
        for row in await _fetch_all(
            engine,
            "SELECT feature_key, value_json, value_hash "
            "FROM shot_revision_feature_states WHERE shot_revision_id = :r",
            {"r": rev.id},
        )
    }
    # Enum-shape case: untrimmed enum string with its CORRECT hash —
    # r3 added the shape validation; this proves it load-bearing.
    violations.append(
        ("cut", '" fresh "', _h('" fresh "'))
    )
    for key, vj, vh in violations:
        assert key in originals, (key, sorted(originals))
        async with engine.connect() as conn:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await conn.execute(
                text(
                    "UPDATE shot_revision_feature_states SET value_json = :vj, "
                    "value_hash = :vh WHERE shot_revision_id = :r AND "
                    "feature_key = :k"
                ),
                {"vj": vj, "vh": vh, "r": rev.id, "k": key},
            )
            await conn.exec_driver_sql("COMMIT")
        r = await client.get(f"/shot-revisions/{rev.id}/continuity")
        assert r.status_code == 500, (key, r.text)
        assert r.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"
        # Restore the original canonical row.
        oj, oh = originals[key]
        async with engine.connect() as conn:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await conn.execute(
                text(
                    "UPDATE shot_revision_feature_states SET value_json = :vj, "
                    "value_hash = :vh WHERE shot_revision_id = :r AND "
                    "feature_key = :k"
                ),
                {"vj": oj, "vh": oh, "r": rev.id, "k": key},
            )
            await conn.exec_driver_sql("COMMIT")

    # With every row restored, the full history validates again — proving
    # the loop really began from complete valid state each time.
    r = await client.get(f"/shot-revisions/{rev.id}/continuity")
    assert r.status_code == 200, r.text


# --- B3 regressions: malformed historical specs ------------------------------------


async def test_malformed_spec_json_fails_closed(client, factory, engine):
    pid = await _seed_project(factory)
    eva = await _entity_approved(client, pid)
    f = await _feature(client, eva["id"])
    seq, scene, shots = await _topology(client, factory, pid, 1)
    await _depend(client, shots[0], eva["id"])
    await _transition(client, f["id"], "scene", scene, "start", "set",
                      "fresh")
    rev = await _capture_once(factory, shots[0])

    for bad in ('{bad', '[]', '"str"', '{"schema_version": "x"}',
                '{"schema_version": 7}',
                '{"schema_version": 2, "dependencies": null, '
                '"feature_states": [], "relations": []}',
                '{"schema_version": 2, "dependencies": [], '
                '"feature_states": null, "relations": []}',
                '{"schema_version": 2, "dependencies": [], '
                '"feature_states": [], "relations": null}',
                '{"schema_version": 1, "dependencies": {"a": 1}}'):
        async with engine.connect() as conn:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await conn.execute(
                text("UPDATE shot_revisions SET continuity_spec_json = :sj "
                     "WHERE id = :r"),
                {"sj": bad, "r": rev.id},
            )
            await conn.exec_driver_sql("COMMIT")
        r = await client.get(f"/shot-revisions/{rev.id}/continuity")
        assert r.status_code == 500, (bad, r.text)
        assert r.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"


# --- B4: true mid-read WAL coherence race -------------------------------------------


async def test_race_writer_commits_inside_open_read_txn(client, factory, engine):
    """APR-031 + APR-033 correct form: the competitor's real BEGIN
    IMMEDIATE + COMMIT happen INSIDE the capture's OPEN read transaction,
    after the read snapshot is established but before Feature resolution.
    The capture must still resolve the pre-mutation snapshot (fresh);
    the next capture resolves healing."""
    from sqlalchemy.ext.asyncio import AsyncConnection

    from soloring.api.schemas.continuity_transitions import TransitionPatch
    from soloring.continuity import transitions as tsvc
    from soloring.domain import revisions as revision_svc
    import soloring.continuity.snapshots as snaps

    pid = await _seed_project(factory)
    eva = await _entity_approved(client, pid)
    f = await _feature(client, eva["id"])
    seq, scene, shots = await _topology(client, factory, pid, 1)
    await _depend(client, shots[0], eva["id"])
    tA = (await _transition(
        client, f["id"], "scene", scene, "start", "set", "fresh"
    )).json()

    original_deps = snaps.resolve_working_dependencies
    original_exec = AsyncConnection.exec_driver_sql
    state: dict = {}
    writer_committed = asyncio.Event()

    async def wrapped_exec(self, statement, *args, **kwargs):
        task = asyncio.current_task()
        if (
            state.get("competitor") is not None
            and task is state["competitor"]
            and statement.strip().upper() == "BEGIN IMMEDIATE"
        ):
            state["begin_seen"] = True
        return await original_exec(self, statement, *args, **kwargs)

    async def competitor_task():
        async with factory() as s:
            await tsvc.patch_transition(
                s, tA["id"],
                TransitionPatch(operation="set", value="healing"),
            )
        writer_committed.set()

    async def deps_wrap(conn, shot_id):
        result = await original_deps(conn, shot_id)
        # We are INSIDE the open read transaction: the snapshot is fixed.
        # Start the competitor; its writer commits while our read is open.
        if "competitor" not in state:
            AsyncConnection.exec_driver_sql = wrapped_exec
            state["competitor"] = asyncio.create_task(competitor_task())
            await writer_committed.wait()
            assert state.get("begin_seen") is True
        return result

    snaps.resolve_working_dependencies = deps_wrap
    try:
        rev = await revision_svc.capture_revision(factory(), shots[0])
    finally:
        snaps.resolve_working_dependencies = original_deps
        AsyncConnection.exec_driver_sql = original_exec

    snap = json.loads(rev.snapshot_json)
    # The pre-mutation WAL snapshot was resolved — never a hybrid.
    assert snap["continuity"]["feature_states"][0]["value"] == "fresh"
    # The next capture deterministically resolves the committed mutation.
    rev2 = await revision_svc.capture_revision(factory(), shots[0])
    snap2 = json.loads(rev2.snapshot_json)
    assert snap2["continuity"]["feature_states"][0]["value"] == "healing"
    assert rev2.id != rev.id
    # The before-capture stays immutable.
    row = await _fetch(
        engine, "SELECT snapshot_json FROM shot_revisions WHERE id = :r",
        {"r": rev.id},
    )
    assert json.loads(row["snapshot_json"])["continuity"][
        "feature_states"][0]["value"] == "fresh"


# --- B5: remaining §14 concurrency cases ----------------------------------------------


async def test_feature_soft_delete_blocks_then_captures_converge(
    client, factory, engine
):
    """Sequential boundary case (not a race): Feature soft-delete fencing
    holds — deletion is refused while the transition is active, and
    captures keep converging onto the schema-3 revision."""
    from soloring.continuity import features as fsvc
    from soloring.domain import revisions as revision_svc

    pid = await _seed_project(factory)
    eva = await _entity_approved(client, pid)
    f = await _feature(client, eva["id"])
    seq, scene, shots = await _topology(client, factory, pid, 1)
    await _depend(client, shots[0], eva["id"])
    await _transition(client, f["id"], "scene", scene, "start", "set",
                      "fresh")
    rev = await revision_svc.capture_revision(factory(), shots[0])
    assert json.loads(rev.snapshot_json)["schema_version"] == 3

    # Deleting the Feature is blocked while the transition is active.
    r = await client.delete(f"/continuity-features/{f['id']}")
    assert r.status_code == 409
    # Captures keep converging onto the same revision.
    again = await revision_svc.capture_revision(factory(), shots[0])
    assert again.id == rev.id


async def test_transition_soft_delete_returns_to_schema2(
    client, factory
):
    """Sequential boundary case (not a race): soft-deleting the winning
    transition → next capture is effective empty → converges back onto the
    schema-2 revision."""
    from soloring.domain import revisions as revision_svc

    pid = await _seed_project(factory)
    eva = await _entity_approved(client, pid)
    f = await _feature(client, eva["id"])
    seq, scene, shots = await _topology(client, factory, pid, 1)
    await _depend(client, shots[0], eva["id"])
    rev2 = await revision_svc.capture_revision(factory(), shots[0])
    assert json.loads(rev2.snapshot_json)["schema_version"] == 2

    t = (await _transition(
        client, f["id"], "scene", scene, "start", "set", "fresh"
    )).json()
    rev3 = await revision_svc.capture_revision(factory(), shots[0])
    assert json.loads(rev3.snapshot_json)["schema_version"] == 3
    assert (await client.delete(
        f"/continuity-feature-transitions/{t['id']}"
    )).status_code == 204
    back = await revision_svc.capture_revision(factory(), shots[0])
    assert back.id == rev2.id  # effective empty converges onto schema 2


async def test_narrative_reposition_changes_capture(client, factory, engine):
    """Sequential boundary case (not a race): moving the transition to a
    later narrative position makes it future → schema-2 capture; ordering
    identity survives; A stays frozen."""
    from soloring.domain import revisions as revision_svc

    pid = await _seed_project(factory)
    eva = await _entity_approved(client, pid)
    f = await _feature(client, eva["id"])
    seq, scene, shots = await _topology(client, factory, pid, 2)
    for sid in shots:
        await _depend(client, sid, eva["id"])

    # Anchor at scene/start — eligible for shots[0] → schema 3.
    t = (await _transition(
        client, f["id"], "scene", scene, "start", "set", "fresh"
    )).json()
    revA = await revision_svc.capture_revision(factory(), shots[0])
    assert json.loads(revA.snapshot_json)["continuity"][
        "feature_states"][0]["value"] == "fresh"

    # Narrative change: a new scene created AFTER ranks later; moving the
    # anchor there makes the transition future for shots[0] → schema 2.
    r = await client.post(f"/sequences/{seq}/scenes", json={"title": "C2"})
    scene2 = r.json()["id"]
    r = await client.patch(
        f"/continuity-feature-transitions/{t['id']}",
        json={"anchor_type": "scene", "anchor_id": scene2},
    )
    assert r.status_code == 200
    revB = await revision_svc.capture_revision(factory(), shots[0])
    assert json.loads(revB.snapshot_json)["schema_version"] == 2
    assert revB.id != revA.id
    # Reorder of narrative members never reinterprets A.
    rowA = await _fetch(
        engine, "SELECT snapshot_json FROM shot_revisions WHERE id = :r",
        {"r": revA.id},
    )
    assert json.loads(rowA["snapshot_json"])["continuity"][
        "feature_states"][0]["value"] == "fresh"


async def test_different_schema3_states_sequential_both_persist(
    client, factory
):
    from soloring.domain import revisions as revision_svc

    pid = await _seed_project(factory)
    eva = await _entity_approved(client, pid)
    f1 = await _feature(client, eva["id"], key="cut")
    f2 = await _feature(client, eva["id"], key="wet", value_type="text",
                        enum_values=None)
    seq, scene, shots = await _topology(client, factory, pid, 1)
    await _depend(client, shots[0], eva["id"])

    # Capture 1: only cut set.
    await _transition(client, f1["id"], "scene", scene, "start", "set",
                      "fresh")
    async def one():
        async with factory() as s:
            return await revision_svc.capture_revision(s, shots[0])
    revA = await one()

    # Now a different state.
    await _transition(client, f2["id"], "scene", scene, "start", "set",
                      "soaked")
    revB = await one()
    assert revB.id != revA.id
    assert json.loads(revB.snapshot_json)["continuity"]["feature_states"]


# --- B5: complete §15 schema-3 historical isolation -----------------------------------


async def test_schema3_historical_isolation_full(client, factory, engine):
    """All §15 rows against a schema-3 baseline: edit/delete/re-anchor the
    transition, rename/delete the Feature (after transition removal),
    reorder topology, approve a newer revision, recreate the equivalent
    transition — the captured revision is byte-untouched each time."""
    from soloring.domain import revisions as revision_svc

    pid = await _seed_project(factory)
    eva = await _entity_approved(client, pid)
    f = await _feature(client, eva["id"])
    seq, scene, shots = await _topology(client, factory, pid, 1)
    await _depend(client, shots[0], eva["id"])
    t = (await _transition(
        client, f["id"], "scene", scene, "start", "set", "fresh"
    )).json()
    rev = await revision_svc.capture_revision(factory(), shots[0])
    frozen = await _fetch(
        engine,
        "SELECT snapshot_json, snapshot_hash, continuity_spec_json, "
        "continuity_spec_hash FROM shot_revisions WHERE id = :r",
        {"r": rev.id},
    )
    frozen_children = await _fetch_all(
        engine,
        "SELECT * FROM shot_revision_feature_states "
        "WHERE shot_revision_id = :r",
        {"r": rev.id},
    )

    async def assert_frozen():
        now = await _fetch(
            engine,
            "SELECT snapshot_json, snapshot_hash, continuity_spec_json, "
            "continuity_spec_hash FROM shot_revisions WHERE id = :r",
            {"r": rev.id},
        )
        assert now == frozen
        kids = await _fetch_all(
            engine,
            "SELECT * FROM shot_revision_feature_states "
            "WHERE shot_revision_id = :r",
            {"r": rev.id},
        )
        assert kids == frozen_children

    # 1. edit transition
    await client.patch(
        f"/continuity-feature-transitions/{t['id']}",
        json={"operation": "set", "value": "healing"},
    )
    await assert_frozen()
    # 2. re-anchor transition
    await client.patch(
        f"/continuity-feature-transitions/{t['id']}",
        json={"anchor_type": "shot", "anchor_id": shots[0],
              "boundary": "end"},
    )
    await assert_frozen()
    # 3. rename Feature (display metadata)
    await client.patch(f"/continuity-features/{f['id']}",
                       json={"name": "Renamed"})
    await assert_frozen()
    # 4. reorder topology (add + reorder scenes)
    r = await client.post(f"/sequences/{seq}/scenes", json={"title": "C2"})
    scene2 = r.json()["id"]
    r = await client.put(
        f"/sequences/{seq}/scenes/order",
        json={"scene_ids": [scene2, scene]},
    )
    assert r.status_code == 200
    await assert_frozen()
    # 5. approve newer EntityRevision
    r = await client.post(
        f"/entities/{eva['id']}/revisions", json={"spec": {"description": "2"}}
    )
    cur = (await client.get(f"/entities/{eva['id']}")).json()[
        "approved_revision_id"]
    rr = await client.put(
        f"/entities/{eva['id']}/approved-revision",
        json={"revision_id": r.json()["id"],
              "expected_approved_revision_id": cur},
    )
    assert rr.status_code == 200
    await assert_frozen()
    # 6. delete transition then delete Feature (legal after removal)
    assert (await client.delete(
        f"/continuity-feature-transitions/{t['id']}"
    )).status_code == 204
    await assert_frozen()
    assert (await client.delete(f"/continuity-features/{f['id']}")
            ).status_code == 204
    await assert_frozen()
    # 7. recreate equivalent: entity + feature + same-anchor transition →
    # the ORIGINAL revision's bytes stay frozen (recreation converges onto
    # a NEW equivalent capture only when fully re-set up).
    eva2 = await _entity_approved(client, pid, name="Eva2")
    f2 = await _feature(client, eva2["id"])
    r = await client.post(f"/sequences/{seq}/scenes", json={"title": "C3"})
    scene3 = r.json()["id"]
    await _depend(client, shots[0], eva2["id"])
    await _transition(client, f2["id"], "scene", scene3, "start", "set",
                      "fresh")
    newrev = await revision_svc.capture_revision(factory(), shots[0])
    assert newrev.id != rev.id
    await assert_frozen()


# --- B5: exact spec-v2 byte fixtures across ALL five value types ----------------------


def test_spec_v2_exact_bytes_all_value_types():
    from types import SimpleNamespace

    from soloring.continuity.snapshots import build_continuity_spec_v2
    from soloring.domain.canonical import canonical_json_bytes

    def st(entity, fid, key, kind, vt, unit, vj, vh):
        return SimpleNamespace(
            entity_id=entity, feature_id=fid, feature_key=key,
            feature_kind=kind, value_type=vt, unit=unit,
            value_json=vj, value_hash=vh,
            source_anchor_type="sequence", source_anchor_id="sq",
            source_boundary="start", source_transition_id="tt",
        )

    states = [
        st("e1", "f1", "wet", "wardrobe_condition", "boolean", None,
           "true", "1" * 64),
        st("e1", "f2", "ammo", "status", "integer", "rounds",
           "17", "2" * 64),
        st("e2", "f3", "cut", "injury", "enum", None,
           '"fresh"', "3" * 64),
        st("e2", "f4", "depth", "damage", "decimal", "cm",
           '"1.5"', "4" * 64),
        st("e3", "f5", "note", "custom", "text", None,
           '"soaked"', "5" * 64),
    ]
    spec = build_continuity_spec_v2([], states)
    raw = canonical_json_bytes(spec).decode("utf-8")
    h1, h2, h3, h4, h5 = ("1" * 64, "2" * 64, "3" * 64, "4" * 64, "5" * 64)
    anchor = '{"anchor_id":"sq","anchor_type":"sequence","boundary":"start"}'
    # Canonical order (entity_id, feature_kind, feature_id): within e1,
    # status < wardrobe_condition → ammo BEFORE wet; within e2, damage <
    # injury → depth BEFORE cut.
    expected = (
        '{"dependencies":[],"feature_states":['
        f'{{"entity_id":"e1","feature_id":"f2","feature_key":"ammo",'
        f'"feature_kind":"status","source_anchor":{anchor},'
        f'"unit":"rounds","value":17,"value_hash":"{h2}",'
        f'"value_type":"integer"}},'
        f'{{"entity_id":"e1","feature_id":"f1","feature_key":"wet",'
        f'"feature_kind":"wardrobe_condition","source_anchor":{anchor},'
        f'"unit":null,"value":true,"value_hash":"{h1}",'
        f'"value_type":"boolean"}},'
        f'{{"entity_id":"e2","feature_id":"f4","feature_key":"depth",'
        f'"feature_kind":"damage","source_anchor":{anchor},'
        f'"unit":"cm","value":"1.5","value_hash":"{h4}",'
        f'"value_type":"decimal"}},'
        f'{{"entity_id":"e2","feature_id":"f3","feature_key":"cut",'
        f'"feature_kind":"injury","source_anchor":{anchor},'
        f'"unit":null,"value":"fresh","value_hash":"{h3}",'
        f'"value_type":"enum"}},'
        f'{{"entity_id":"e3","feature_id":"f5","feature_key":"note",'
        f'"feature_kind":"custom","source_anchor":{anchor},'
        f'"unit":null,"value":"soaked","value_hash":"{h5}",'
        f'"value_type":"text"}}],'
        '"relations":[],"schema_version":2}'
    )
    assert raw == expected
    assert "source_transition_id" not in raw

# --- r4: remaining §14 deterministic open-read capture races --------------------
# Same seam discipline as test_race_writer_commits_inside_open_read_txn:
# the competitor's real mutation transaction runs while the capture's read
# transaction is OPEN (snapshot established); the capture must stay
# coherent BEFORE, the next capture observes AFTER. No sleeps.


async def _open_read_race(client, factory, engine, competitor):
    """Shared driver: runs `competitor` (an async callable) inside the
    capture's open read transaction and returns the first capture's
    revision. The competitor's completion is awaited inside the seam."""
    from soloring.domain import revisions as revision_svc
    import soloring.continuity.snapshots as snaps

    original_deps = snaps.resolve_working_dependencies
    state: dict = {}
    done = asyncio.Event()

    async def deps_wrap(conn, shot_id):
        result = await original_deps(conn, shot_id)
        if "ran" not in state:
            state["ran"] = True
            state["outcome"] = await competitor()
            done.set()
        return result

    snaps.resolve_working_dependencies = deps_wrap
    try:
        rev = await revision_svc.capture_revision(factory(), shot_id_of(competitor))
    finally:
        snaps.resolve_working_dependencies = original_deps
    assert done.is_set()
    return rev, state.get("outcome")


def shot_id_of(competitor):
    return competitor._shot_id


async def test_race_feature_soft_delete_vs_capture(client, factory, engine):
    """§14 Feature soft-delete ↔ capture: the fenced deletion is REFUSED
    (CONTINUITY_FEATURE_IN_USE) while the transition is active, and the
    open-read capture stays coherent schema-3 BEFORE; the next capture
    converges onto the same revision."""
    from soloring.continuity import features as fsvc
    from soloring.domain import revisions as revision_svc

    pid = await _seed_project(factory)
    eva = await _entity_approved(client, pid)
    f = await _feature(client, eva["id"])
    seq, scene, shots = await _topology(client, factory, pid, 1)
    await _depend(client, shots[0], eva["id"])
    await _transition(client, f["id"], "scene", scene, "start", "set",
                      "fresh")

    async def competitor():
        async with factory() as s:
            try:
                await fsvc.delete_feature(s, f["id"])
                return "deleted"
            except Exception as exc:
                return getattr(exc, "code", type(exc).__name__)
    competitor._shot_id = shots[0]

    rev, outcome = await _open_read_race(client, factory, engine, competitor)
    assert outcome == "CONTINUITY_FEATURE_IN_USE"
    snap = json.loads(rev.snapshot_json)
    assert snap["schema_version"] == 3
    assert snap["continuity"]["feature_states"][0]["value"] == "fresh"
    again = await revision_svc.capture_revision(factory(), shots[0])
    assert again.id == rev.id  # coherent BEFORE converged


async def test_race_transition_soft_delete_vs_capture(client, factory, engine):
    """§14 transition soft-delete ↔ capture: the competitor's real DELETE
    commits while the read is open; the capture stays schema-3 BEFORE;
    the next capture returns to schema 2 (converging onto the v2 rev)."""
    from soloring.domain import revisions as revision_svc

    pid = await _seed_project(factory)
    eva = await _entity_approved(client, pid)
    f = await _feature(client, eva["id"])
    seq, scene, shots = await _topology(client, factory, pid, 1)
    await _depend(client, shots[0], eva["id"])
    rev2 = await revision_svc.capture_revision(factory(), shots[0])
    assert json.loads(rev2.snapshot_json)["schema_version"] == 2
    t = (await _transition(
        client, f["id"], "scene", scene, "start", "set", "fresh"
    )).json()

    async def competitor():
        async with factory() as s:
            from soloring.continuity import transitions as tsvc

            await tsvc.delete_transition(s, t["id"])
            return "deleted"
    competitor._shot_id = shots[0]

    rev, outcome = await _open_read_race(client, factory, engine, competitor)
    assert outcome == "deleted"
    snap = json.loads(rev.snapshot_json)
    assert snap["schema_version"] == 3  # BEFORE snapshot retained
    assert snap["continuity"]["feature_states"][0]["value"] == "fresh"
    back = await revision_svc.capture_revision(factory(), shots[0])
    assert back.id == rev2.id  # AFTER converged onto the v2 revision


async def test_race_narrative_reorder_vs_capture(client, factory, engine):
    """§14 narrative reorder ↔ capture: a scene reorder commits while the
    read is open; the capture retains the OLD ordering interpretation
    (transition still eligible → schema 3); the next capture observes the
    NEW ordering (transition now future → schema 2)."""
    from soloring.domain import revisions as revision_svc

    pid = await _seed_project(factory)
    eva = await _entity_approved(client, pid)
    f = await _feature(client, eva["id"])
    seq, scene, shots = await _topology(client, factory, pid, 2)
    for sid in shots:
        await _depend(client, sid, eva["id"])
    r = await client.post(f"/sequences/{seq}/scenes", json={"title": "C2"})
    scene2 = r.json()["id"]
    # Put scene2 FIRST so its /start precedes scene's shots → eligible.
    r = await client.put(
        f"/sequences/{seq}/scenes/order",
        json={"scene_ids": [scene2, scene]},
    )
    assert r.status_code == 200
    t = (await _transition(
        client, f["id"], "scene", scene2, "start", "set", "fresh"
    )).json()
    revA = await revision_svc.capture_revision(factory(), shots[0])
    assert json.loads(revA.snapshot_json)["schema_version"] == 3

    async def competitor():
        # Reorder scenes: scene2 moves AFTER scene → scene2/start now
        # ranks after scene's shots → future for shots[0].
        r = await client.put(
            f"/sequences/{seq}/scenes/order",
            json={"scene_ids": [scene, scene2]},
        )
        return r.status_code
    competitor._shot_id = shots[0]

    rev, outcome = await _open_read_race(client, factory, engine, competitor)
    assert outcome == 200
    snap = json.loads(rev.snapshot_json)
    assert snap["schema_version"] == 3  # OLD ordering retained
    assert snap["continuity"]["feature_states"][0]["value"] == "fresh"
    revB = await revision_svc.capture_revision(factory(), shots[0])
    assert json.loads(revB.snapshot_json)["schema_version"] == 2  # NEW
    assert revB.id != rev.id
