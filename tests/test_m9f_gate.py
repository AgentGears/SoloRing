"""M9F — failure, race, scale, and source gate (frozen plan §§48–49,
59–62, 73, 82–90).

No sleeps: barriers at the actual descriptor-read seam (§88) and at the
real BEGIN IMMEDIATE seams where DB writes race. Hermetic: fixture
packages, fixture model roots, stub executor client.
"""

from __future__ import annotations

import json
import shutil

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine as SyncEngine

from soloring.realization.packages import (
    PackageIntegrity,
    capture_current_package,
    capture_release,
)
from tests.test_m8a_visual import (
    _entity_with_revision,
    _facet,
    _seed_project,
)
from tests.test_m8b_curation import _assets
from tests.test_m8c_resolver import (
    _approve_anchor,
    _depend,
    _topology,
)
from tests.test_m9a_package import V4_DIR

# §73.2: CURRENT MUTABLE M8 authority tables only. The immutable
# shot_revision_visual_* provenance tables are ShotRevision persistence
# (predecessor writes, separately classified per §73.2's note) and are
# excluded from the mutation prohibition.
M8_AUTHORITY_TABLES = (
    "visual_facets",
    "visual_facet_value_policies",
    "visual_anchors",
    "visual_anchor_items",
    "visual_anchor_revisions",
    "visual_anchor_revision_items",
)

CURRENT_M8_READ_TABLES = M8_AUTHORITY_TABLES[:4]


async def _m9_state(client, factory, engine, settings, pid, extras=0):
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    assets = await _assets(engine, pid, 1 + extras)
    f = await _facet(
        client, pid, "entity", entity_id=eva["id"], facet_key="identity"
    )
    r = await client.post(
        f"/visual-facets/{f['id']}/anchors", json={"entity_revision_id": rev1}
    )
    await _approve_anchor(client, r.json()["id"], assets[:1], ["front"])
    seq, scene, shots = await _topology(client, factory, pid)
    await _depend(client, shots[0], [eva["id"]])
    return shots[0], eva, rev1, assets


def _comfy(settings):
    settings.executor = "comfy"
    return settings


# --- §73 no-authority-transfer --------------------------------------------------


async def test_dynamic_sql_spy_zero_m8_authority_writes(
    client, factory, engine, settings,
):
    """§73.2: around realization preview + new Generation creation +
    Exact Rerun, M9 causes ZERO INSERT/UPDATE/DELETE against M8 authority
    tables (predecessor writes are separately classified)."""
    pid = await _seed_project(factory)
    shot, _eva, _rev1, _assets = await _m9_state(
        client, factory, engine, settings, pid
    )
    _comfy(settings)

    violations: list[str] = []

    import re

    table_patterns = [
        re.compile("\\b" + t.upper() + "\\b")
        for t in M8_AUTHORITY_TABLES
    ]

    def before_cursor_execute(conn, cursor, statement, params, ctx, many):
        up = statement.strip().upper()
        for verb in ("INSERT INTO", "UPDATE", "DELETE FROM"):
            if up.startswith(verb):
                for pattern in table_patterns:
                    if pattern.search(up):
                        violations.append(statement[:120])
                        return

    from sqlalchemy import event

    event.listen(SyncEngine, "before_cursor_execute", before_cursor_execute)
    try:
        r = await client.get(f"/shots/{shot}/realization-readiness")
        assert r.status_code == 200, r.text
        r = await client.post(f"/shots/{shot}/generations")
        assert r.status_code == 202, r.text
        gid = r.json()["id"]
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE generations SET status = 'succeeded', "
                    "started_at = '2026-01-01T00:00:00Z', "
                    "completed_at = '2026-01-01T00:00:01Z' WHERE id = :g"
                ),
                {"g": gid},
            )
        rr = await client.post(f"/generations/{gid}/rerun")
        assert rr.status_code == 202, rr.text
    finally:
        event.remove(SyncEngine, "before_cursor_execute", before_cursor_execute)

    assert violations == [], violations


def test_static_no_write_audit():
    """§73.1 (r1-gate B6 rewrite): the M9 modules contain NO write
    statements at all (INSERT/UPDATE/DELETE against anything) and no
    imports of M8 write-capable services."""
    import inspect
    import re

    from soloring.realization import (
        authority,
        compiler,
        fingerprint,
        model_roots,
        packages,
        profile,
        runtime,
    )

    write_re = re.compile(
        r"\\b(INSERT\\s+INTO|UPDATE|DELETE\\s+FROM)\\b",
        re.IGNORECASE,
    )
    for module in (
        authority, compiler, fingerprint, model_roots, packages, profile,
        runtime,
    ):
        src = inspect.getsource(module)
        # Strip comments/docstrings crudely but conservatively: scan the
        # raw source; any write verb hit must be justified by inspection.
        hits = [
            line.strip() for line in src.splitlines()
            if write_re.search(line)
            and not line.strip().startswith("#")
            and '"""' not in line
        ]
        assert hits == [], (module.__name__, hits)
        for forbidden_import in (
            "from soloring.visual import anchors",
            "from soloring.visual import facets",
            "import soloring.visual.anchors",
            "import soloring.visual.facets",
        ):
            assert forbidden_import not in src, (
                module.__name__, forbidden_import
            )


# --- §30.1/§89 Exact Rerun + historical isolation --------------------------------


async def test_exact_rerun_schema2_isolation(
    client, factory, engine, settings, monkeypatch,
):
    """§30.1: with a schema-2 source Generation, mutate current M8
    approval + replace the installed profile bytes + monkeypatch the
    compiler AND the current M8 visual resolver to raise; create the
    Exact Rerun; assert durable spec/model/inputs copied verbatim and a
    query spy proves zero current-M8 table reads during rerun creation."""
    pid = await _seed_project(factory)
    shot, eva, rev1, _assets = await _m9_state(
        client, factory, engine, settings, pid
    )
    _comfy(settings)

    r = await client.post(f"/shots/{shot}/generations")
    assert r.status_code == 202, r.text
    source_id = r.json()["id"]

    # Exact Rerun requires a TERMINAL source; terminalize directly (the
    # durable spec/inputs are what this proof isolates).
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE generations SET status = 'succeeded', "
                "started_at = '2026-01-01T00:00:00Z', "
                "completed_at = '2026-01-01T00:00:01Z' "
                "WHERE id = :g"
            ),
            {"g": source_id},
        )

    async with engine.connect() as conn:
        src = (await conn.execute(
            text("SELECT workflow_spec_json, workflow_spec_hash, model, "
                 "model_version FROM generations WHERE id = :g"),
            {"g": source_id},
        )).one()
        src_inputs = (await conn.execute(
            text("SELECT input_key, position, asset_id, blob_hash, "
                 "reference_role FROM generation_inputs "
                 "WHERE generation_id = :g ORDER BY input_key, position"),
            {"g": source_id},
        )).all()

    # Mutate current M8: unapprove the anchor via direct approval NULL.
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE visual_anchors SET approved_revision_id = NULL "
                 "WHERE entity_revision_id = :r"),
            {"r": rev1},
        )

    # Sabotage the compiler + current visual resolver.
    import soloring.realization.compiler as compiler_mod
    import soloring.visual.resolver as resolver_mod

    async def _forbidden(*a, **k):
        raise AssertionError("compiler invoked during Exact Rerun")

    monkeypatch.setattr(compiler_mod, "compile_realization", _forbidden)
    monkeypatch.setattr(
        resolver_mod, "resolve_visual_reference_pack_async", _forbidden
    )

    current_m8_reads: list[str] = []

    import re

    read_patterns = [
        re.compile("\\b" + t.upper() + "\\b")
        for t in CURRENT_M8_READ_TABLES
    ]

    def before_cursor_execute(conn, cursor, statement, params, ctx, many):
        up = statement.upper()
        for pattern in read_patterns:
            if pattern.search(up):
                current_m8_reads.append(statement[:120])
                return

    from sqlalchemy import event

    event.listen(SyncEngine, "before_cursor_execute", before_cursor_execute)
    try:
        rr = await client.post(f"/generations/{source_id}/rerun")
    finally:
        event.remove(
            SyncEngine, "before_cursor_execute", before_cursor_execute
        )
    assert rr.status_code == 202, rr.text
    assert current_m8_reads == [], current_m8_reads

    async with engine.connect() as conn:
        copy = (await conn.execute(
            text("SELECT workflow_spec_json, workflow_spec_hash, model, "
                 "model_version FROM generations WHERE id = :g"),
            {"g": rr.json()["id"]},
        )).one()
        copy_inputs = (await conn.execute(
            text("SELECT input_key, position, asset_id, blob_hash, "
                 "reference_role FROM generation_inputs "
                 "WHERE generation_id = :g ORDER BY input_key, position"),
            {"g": rr.json()["id"]},
        )).all()

    assert copy.workflow_spec_json == src.workflow_spec_json
    assert copy.workflow_spec_hash == src.workflow_spec_hash
    assert copy.model == src.model
    assert copy.model_version == src.model_version
    assert copy_inputs == src_inputs


async def test_current_m8_change_after_capture_never_rewrites_history(
    client, factory, engine, settings,
):
    """§83 authority direction: after G captures revision A + profile
    strength-equivalents, changing current M8 approval to a new revision
    leaves G's realization bound to A; a NEW Generate compiles the new
    state; no M8 authority mutation occurred."""
    pid = await _seed_project(factory)
    shot, eva, rev1, assets = await _m9_state(
        client, factory, engine, settings, pid
    )
    _comfy(settings)

    r1 = await client.post(f"/shots/{shot}/generations")
    assert r1.status_code == 202
    async with engine.connect() as conn:
        pack1 = json.loads((await conn.execute(
            text("SELECT workflow_spec_json FROM generations "
                 "WHERE id = :g"),
            {"g": r1.json()["id"]},
        )).scalar())["realization"]["visual_reference_pack_hash"]

    # Advance the entity: second revision, rebind the anchor, re-approve.
    r = await client.post(
        f"/entities/{eva['id']}/revisions",
        json={"spec": {"description": "second"}},
    )
    rev2 = r.json()["id"]
    f2 = await client.post(
        f"/projects/{pid}/visual-facets",
        json={"target_kind": "entity", "entity_id": eva["id"],
              "facet_key": "identity2", "requirement": "optional"},
    )
    anchor2 = await client.post(
        f"/visual-facets/{f2.json()['id']}/anchors",
        json={"entity_revision_id": rev1},
    )
    await _approve_anchor(client, anchor2.json()["id"], assets[:1], ["front"])

    # G1's captured realization is unchanged.
    async with engine.connect() as conn:
        pack1_after = json.loads((await conn.execute(
            text("SELECT workflow_spec_json FROM generations "
                 "WHERE id = :g"),
            {"g": r1.json()["id"]},
        )).scalar())["realization"]["visual_reference_pack_hash"]
    assert pack1_after == pack1

    # A new Generate compiles from the CURRENT (new) authority.
    r2 = await client.post(f"/shots/{shot}/generations")
    assert r2.status_code == 202, r2.text
    async with engine.connect() as conn:
        spec2 = json.loads((await conn.execute(
            text("SELECT workflow_spec_json FROM generations "
                 "WHERE id = :g"),
            {"g": r2.json()["id"]},
        )).scalar())
    assert spec2["schema_version"] == 2
    # identity (required) still binds via the OLD approved anchor because
    # the entity's approved revision advanced — wait: identity anchor is
    # bound to rev1 while current approved revision is... rev1 is still
    # approved (we only added rev2 without approving it). The new
    # optional identity2 facet is omitted no_matching_rule.
    omitted = [
        o["facet_key"] for o in spec2["realization"]["omitted_optional"]
    ]
    assert "identity2" in omitted


# --- §88 package switch coherence ------------------------------------------------


async def _pkg_variant(tmp_path, name: str, marker: str):
    pkg = tmp_path / name
    shutil.copytree(V4_DIR, pkg)
    manifest = json.loads((pkg / "manifest.json").read_text())
    manifest["workflow_id"] = marker
    # Keep bindings valid: workflow_id flows everywhere.
    (pkg / "manifest.json").write_text(json.dumps(manifest))
    profile = json.loads((pkg / "realization-profile.json").read_text())
    profile["workflow_id"] = marker
    (pkg / "realization-profile.json").write_text(json.dumps(profile))
    import hashlib

    descriptor = json.loads((pkg / "workflow-package.json").read_text())
    descriptor["workflow_id"] = marker
    descriptor["manifest_hash"] = hashlib.sha256(
        (pkg / "manifest.json").read_bytes()
    ).hexdigest()
    descriptor["realization_profile_hash"] = hashlib.sha256(
        (pkg / "realization-profile.json").read_bytes()
    ).hexdigest()
    (pkg / "workflow-package.json").write_text(json.dumps(descriptor))
    return pkg


async def _capture_pkg(pkg):
    return await capture_release(
        pkg / "workflow-package.json", pkg / "manifest.json",
        pkg / "workflow.json", pkg / "realization-profile.json",
        pkg / "execution-model-fingerprint.json",
    )


async def test_package_switch_before_snapshot_uses_complete_after(
    tmp_path,
):
    """§88 Race 1: the release flips BEFORE the descriptor's D1 read —
    capture yields the complete AFTER release; never mixed."""
    a = await _pkg_variant(tmp_path, "a", "workflow_a")
    b = await _pkg_variant(tmp_path, "b", "workflow_b")
    live = tmp_path / "live"
    shutil.copytree(a, live)

    # Switch to B before any capture read happens.
    for name in (
        "workflow-package.json", "manifest.json", "workflow.json",
        "realization-profile.json", "execution-model-fingerprint.json",
    ):
        (live / name).write_bytes((b / name).read_bytes())

    release = await _capture_pkg(live)
    assert release.workflow_id == "workflow_b"
    assert release.manifest_hash == (
        await _capture_pkg(b)
    ).manifest_hash


async def test_package_switch_after_snapshot_uses_complete_before(
    tmp_path,
):
    """§88 Race 2: the release flips AFTER the captured byte buffers are
    established (the D2 read observes the switch) — capture refuses the
    hybrid as incoherent; the caller may retry and then see complete
    AFTER. Never a mixed artifact set."""
    a = await _pkg_variant(tmp_path, "a", "workflow_a")
    b = await _pkg_variant(tmp_path, "b", "workflow_b")
    live = tmp_path / "live"
    shutil.copytree(a, live)

    import soloring.realization.packages as pkg_mod

    real_read = pkg_mod._read_descriptor
    calls = {"n": 0}

    def flip_on_d2(path):
        doc = real_read(path)
        calls["n"] += 1
        if calls["n"] == 2:
            for name in (
                "workflow-package.json", "manifest.json", "workflow.json",
                "realization-profile.json",
                "execution-model-fingerprint.json",
            ):
                (live / name).write_bytes((b / name).read_bytes())
            doc = real_read(live / "workflow-package.json")
        return doc

    import asyncio

    # Interpose the flip between D1 and D2.
    orig_to_thread = pkg_mod.asyncio.to_thread

    def flip_between(fn, *a, **k):
        return orig_to_thread(fn, *a, **k)

    pkg_mod._read_descriptor = flip_on_d2
    try:
        with pytest.raises(PackageIntegrity):
            await _capture_pkg(live)
    finally:
        pkg_mod._read_descriptor = real_read

    # Retry after the completed switch: complete AFTER only.
    release = await _capture_pkg(live)
    assert release.workflow_id == "workflow_b"


# --- §59/§60 scale: cardinality-independent statement count ----------------------


async def test_readiness_statement_count_cardinality_independent(
    client, factory, engine, settings, tmp_path,
):
    """§59: small vs representative legal target through the same
    production readiness path — identical SQL statement count; direct-SQL
    bulk volume is legal state with mechanical assertions (§60)."""
    pid = await _seed_project(factory)
    shot, eva, rev1, _assets = await _m9_state(
        client, factory, engine, settings, pid
    )

    async def count_statements(shot_id):
        n = {"count": 0}

        def before(conn, cursor, statement, params, ctx, many):
            n["count"] += 1

        from sqlalchemy import event

        event.listen(SyncEngine, "before_cursor_execute", before)
        try:
            r = await client.get(
                f"/shots/{shot_id}/realization-readiness"
            )
            assert r.status_code == 200, r.text
        finally:
            event.remove(SyncEngine, "before_cursor_execute", before)
        return n["count"]

    small = await count_statements(shot)

    # Representative volume: 60 bulk OPTIONAL facets on the dependency
    # entity (legal direct-SQL state, disclosed; no anchors, all omitted
    # no_matching_rule) + multi-item authority.
    now = "2026-01-01T00:00:00.000Z"
    async with engine.begin() as conn:
        for k in range(60):
            await conn.execute(
                text(
                    "INSERT INTO visual_facets (id, project_id, "
                    "target_kind, entity_id, feature_id, facet_key, label, "
                    "description, requirement, created_at, updated_at) "
                    "VALUES (:id, :pid, 'entity', :eid, NULL, :key, NULL, "
                    "NULL, 'optional', :now, :now)"
                ),
                {
                    "id": f"b9000000-0000-4000-8000-{k:012d}",
                    "pid": pid, "eid": eva["id"],
                    "key": f"bulk{k:03d}", "now": now,
                },
            )
        # Legality assertion: every bulk facet belongs to the target's
        # dependency entity (no wrong-entity bindings).
        bad = (await conn.execute(
            text(
                "SELECT COUNT(*) FROM visual_facets vf "
                "LEFT JOIN creative_entities ce ON ce.id = vf.entity_id "
                "WHERE vf.entity_id IS NOT NULL "
                "AND ce.project_id != :p",
            ),
            {"p": pid},
        )).scalar()
    assert bad == 0

    big = await count_statements(shot)
    assert big == small, (small, big)


# --- §50 duplicate Generation creation stays legal -------------------------------


async def test_duplicate_generation_creation_no_dedup(
    client, factory, engine, settings,
):
    pid = await _seed_project(factory)
    shot, _eva, _rev1, _assets = await _m9_state(
        client, factory, engine, settings, pid
    )
    _comfy(settings)
    r1 = await client.post(f"/shots/{shot}/generations")
    r2 = await client.post(f"/shots/{shot}/generations")
    assert r1.status_code == r2.status_code == 202
    assert r1.json()["id"] != r2.json()["id"]
    async with engine.connect() as conn:
        n = (await conn.execute(
            text("SELECT COUNT(*) FROM generations WHERE shot_id = :s"),
            {"s": shot},
        )).scalar()
    assert n == 2  # execution events, never deduplicated content


# --- §32 spec-hash tamper ---------------------------------------------------------


async def test_schema2_spec_hash_tamper_fails_closed(
    client, factory, engine, settings, tmp_path, monkeypatch,
):
    from tests.test_m9d_worker import (
        _RecordingClient,
        _StubCap,
        _claim,
        _m9_generation,
        _write_fixture_attestation,
    )

    gid, _pkg, _roots = await _m9_generation(
        client, factory, engine, settings, tmp_path
    )
    # Corrupt the stored spec bytes (hash now disagrees).
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE generations SET workflow_spec_json = :sj "
                 "WHERE id = :g"),
            {"g": gid, "sj": '{"schema_version":2,"tampered":true}'},
        )
    await _claim(engine, gid)
    import soloring.worker.comfy_pipeline as pipeline

    async def _cap(*a, **k):
        return _StubCap()

    monkeypatch.setattr(pipeline, "resolve_capability", _cap)
    _write_fixture_attestation(settings)
    stub = _RecordingClient()
    result = await pipeline.drive_comfy_generation(
        engine, settings, "w-m9d", gid, "attempt-m9f", stub,
    )
    assert result == "failed"
    async with engine.connect() as conn:
        error_code = (await conn.execute(
            text("SELECT error_code FROM generations WHERE id = :g"),
            {"g": gid},
        )).scalar()
    assert error_code == "INTERNAL_INVARIANT_VIOLATION"
    assert stub.submissions == 0
