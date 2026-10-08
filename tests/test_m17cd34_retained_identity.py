"""M17C-D FPR34-04/05 — the retained-authority identity regressions
(non-live): (1) TWO lawful releases sharing ONE workflow ID — each
Generation reconstructs its OWN release (the authenticated
document's pointers address its exact captured release's
content-verified profile/fingerprint artifacts; no global
workflow-id uniqueness — the predecessor scan refused two lawful
releases); (2) a PATCH of a facet requirement AFTER capture —
worker recompilation and recovery both keep using the CAPTURED
requirement (from the authenticated document's compiled
realization), never today's mutable visual_facets row."""

from __future__ import annotations

import hashlib
import json

import pytest

from tests.test_m17cd33_retained3 import (
    _drive_to_payload, _schema3_v5_generation,
)


def _bump_profile(docs):
    """A lawful re-release mutation: the SAME workflow's realization
    profile, revision 2 (the descriptor re-pins automatically, so
    the package stays capture-coherent with a DISTINCT profile
    hash under the SAME workflow_id)."""
    import copy

    profile = copy.deepcopy(docs["realization-profile.json"])
    profile["profile_version"] = 2
    docs["realization-profile.json"] = profile
    return docs


def _profile_hashes_for_workflow(client) -> dict:
    """The retained realization-profile artifacts currently in the
    store, keyed by workflow_id (the FPR34-05 defect's trigger
    condition: more than one under a single workflow_id). The
    profiles live in the CONTENT-ADDRESSED artifact store, not a
    table — walk the store directly."""
    settings = client._transport.app.state.settings
    root = settings.data_dir / "workflow-artifacts" / (
        "realization_profiles")
    out: dict[str, list[str]] = {}
    for path in sorted(root.rglob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        out.setdefault(doc.get("workflow_id"), []).append(path.stem)
    return out


@pytest.mark.asyncio
async def test_two_releases_sharing_workflow_id_each_reconstruct(
        client, factory, tmp_path, monkeypatch):
    """FPR34-05's mandatory proof: two lawful releases of ONE
    workflow (the profile re-released at version 2) — both retained
    in the artifact store at once — and each Generation drives the
    FULL worker path (the pointer-addressed profile/fingerprint
    resolution + the frozen M9 recompilation + the lower
    reconstruction comparison) against its OWN release."""
    # release A: the frozen production profile (version 1)
    world_a, gen_a, spec_a, pkg_a = await _schema3_v5_generation(
        client, factory, tmp_path, v2=True)
    # release B: the SAME workflow re-released with profile
    # version 2 — a second lawful world + Generation
    world_b, gen_b, spec_b, pkg_b = await _schema3_v5_generation(
        client, factory, tmp_path, v2=True,
        profile_mutate=_bump_profile)

    assert spec_a["realization"]["profile"]["hash"] != \
        spec_b["realization"]["profile"]["hash"]
    assert spec_a["realization"]["profile"]["version"] == 1
    assert spec_b["realization"]["profile"]["version"] == 2

    # the defect's trigger condition is REAL: the store now holds
    # TWO retained realization profiles for the SAME workflow_id
    by_workflow = _profile_hashes_for_workflow(client)
    assert len(by_workflow["wan21_spatial_v1"]) == 2, by_workflow

    # each Generation drives to payload — the pointer resolution
    # reconstructs EACH against its own release (the predecessor
    # global scan refused here: 'expected exactly one ... found 2')
    stub_a, outcome_a, err_a = await _drive_to_payload(
        client, gen_a, pkg_a / "execution-model-fingerprint.json",
        monkeypatch)
    assert err_a is None and stub_a.payload is not None

    stub_b, outcome_b, err_b = await _drive_to_payload(
        client, gen_b, pkg_b / "execution-model-fingerprint.json",
        monkeypatch)
    assert err_b is None and stub_b.payload is not None


@pytest.mark.asyncio
async def test_patch_facet_requirement_then_recover_uses_captured(
        client, factory, tmp_path, monkeypatch):
    """FPR34-04's mandatory proof: the facet's requirement is
    PATCHed (optional -> required — a lawful user action) AFTER the
    Generation's capture and BEFORE the backup. The staged backup
    therefore carries TODAY's requirement, but recovery's
    recompilation uses the CAPTURED requirement from the
    authenticated document — the old law (reading the staged
    visual_facets row) recompiled a REQUIRED facet and refused;
    the captured law verifies GREEN with the generation's original
    semantics."""
    from tests.test_m17c_sr26_regressions import _backup_m17c
    from tests.test_m17cc_recovery import _one, _stage_blob, _verify
    from soloring.performance.execution_translation import (
        translate_captured_performance,
    )

    world, generation_id, spec, pkg = await _schema3_v5_generation(
        client, factory, tmp_path, v2=True)

    # the world's ONE visual facet — the captured authority's
    # requirement is OPTIONAL (the spec's compiled realization
    # records it: required=false on its binding, or omitted)
    engine = client._transport.app.state.engine
    from sqlalchemy import text

    async with engine.connect() as conn:
        facet = (await conn.execute(text(
            "SELECT id, requirement FROM visual_facets "
            "WHERE project_id = :pid"),
            {"pid": world["project_id"]})).mappings().one()
    assert facet["requirement"] == "optional"

    # complete the schema-5 write unit the fake lane skipped: the
    # GPI rows via the lawful translation (BEFORE the backup, so
    # the rows are part of the backed-up state)
    app = client._transport.app
    revision_id = (await _one_live(client, (
        "SELECT shot_revision_id FROM generations WHERE id = :g"),
        {"g": generation_id}))["shot_revision_id"]
    async with app.state.session_factory() as session:
        translation = await translate_captured_performance(
            session, app.state.settings, revision_id=revision_id,
            parameters={"fps_num": 25, "fps_den": 1,
                        "frame_count": 25})

    # the ADVERSARY: PATCH the facet requirement AFTER capture
    r = await client.patch(
        f"/visual-facets/{facet['id']}",
        json={"requirement": "required"})
    assert r.status_code == 200, r.text
    assert r.json()["requirement"] == "required"

    # the backup now carries the PATCHED (today's) requirement
    root = await _backup_m17c(client, tmp_path, "m34-patch-recover")
    for digest, data in translation.placed_bytes:
        target = (root / "blobs" / "sha256" / digest[:2] /
                  digest[2:4] / digest)
        if target.is_file():
            continue
        _stage_blob(root, digest, data)
    import sqlite3

    con = sqlite3.connect(root / "soloring.db")
    try:
        parent = _one(root, (
            "SELECT created_at FROM generations WHERE id = ?"),
            (generation_id,))
        existing = con.execute(
            "SELECT COUNT(*) FROM generation_performance_inputs "
            "WHERE generation_id = ?",
            (generation_id,)).fetchone()[0]
        if not existing:
            for row in translation.gpi_rows:
                con.execute(
                    "INSERT INTO generation_performance_inputs ("
                    "generation_id, input_key, position, "
                    "artifact_role, "
                    "shot_revision_segment_position, "
                    "performance_revision_id, "
                    "vocal_performance_revision_id, blob_hash, "
                    "binding_hash, segment_hash, "
                    "translation_identity, derived_input_hash, "
                    "created_at) VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (generation_id, row["input_key"],
                     row["position"], row["artifact_role"],
                     row["shot_revision_segment_position"],
                     row["performance_revision_id"],
                     row["vocal_performance_revision_id"],
                     row["blob_hash"], row["binding_hash"],
                     row["segment_hash"],
                     row["translation_identity"],
                     row["derived_input_hash"],
                     parent["created_at"]))
            con.commit()
    finally:
        con.close()

    # proof the staged state carries the PATCHED requirement (the
    # adversary really reached the backup)
    staged_facet = _one(root, (
        "SELECT requirement FROM visual_facets WHERE id = ?"),
        (facet["id"],))
    assert staged_facet["requirement"] == "required"

    # the CAPTURED law: recovery verifies GREEN — the
    # recompilation's requirement map came from the authenticated
    # document (optional), not the staged mutable row (required)
    _verify(root)


async def _one_live(client, sql, params):
    from sqlalchemy import text

    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        return (await conn.execute(
            text(sql), params)).mappings().one()
