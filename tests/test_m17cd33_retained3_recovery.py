"""M17C-D FPR33-05 (recovery half) — retained-schema-3 v5-over-v1
and v5-over-v2 recovery adversaries over REAL captured states (the
generation created through the genuine capture path, backed up, and
staged) — never hand-built dictionaries. The complete §13.6 laws
run green on the lawful staged state; coherent re-signed tampering
of the v2 realization coordinates refuses under recovery."""

from __future__ import annotations

import json

import pytest

from tests.test_m17cd33_retained3 import _schema3_v5_generation


async def _staged_state(client, factory, tmp_path, *, v2: bool):
    from tests.test_m17c_sr26_regressions import _backup_m17c

    world, generation_id, spec, pkg = await _schema3_v5_generation(
        client, factory, tmp_path, v2=v2)
    # complete the schema-5 write unit the fake lane skipped: the
    # GPI rows via the lawful translation (the captured-shape
    # staging the recovery batteries use)
    from soloring.performance.execution_translation import (
        translate_captured_performance,
    )

    app = client._transport.app
    async with app.state.session_factory() as session:
        translation = await translate_captured_performance(
            session, app.state.settings,
            revision_id=spec["segment_ref"] if False else
            (await _revision_id(client, generation_id)),
            parameters={"fps_num": 25, "fps_den": 1,
                        "frame_count": 25})
    root = await _backup_m17c(client, tmp_path,
                              f"m33r3-{'v2' if v2 else 'v1'}")
    import hashlib as _hl

    for digest, data in translation.placed_bytes:
        from tests.test_m17cc_recovery import _stage_blob

        # only re-stage when the backup did NOT already carry the
        # identical bytes (the comfy-lane creation places the same
        # digests; a rewrite with identical content is a no-op, but
        # a MISMATCHED rewrite under a frozen digest would be a
        # self-inflicted corruption)
        target = (root / "blobs" / "sha256" / digest[:2] /
                  digest[2:4] / digest)
        if target.is_file():
            assert _hl.sha256(target.read_bytes()).hexdigest() ==                 digest, (
                "the battery's re-derivation disagrees with the "
                "creation-placed bytes under the same digest")
            continue
        _stage_blob(root, digest, data)
    import sqlite3

    con = sqlite3.connect(root / "soloring.db")
    try:
        from tests.test_m17cc_recovery import _one, _sql

        parent = _one(root, (
            "SELECT created_at FROM generations WHERE id = ?"),
            (generation_id,))
        existing = con.execute(
            "SELECT COUNT(*) FROM generation_performance_inputs "
            "WHERE generation_id = ?",
            (generation_id,)).fetchone()[0]
        if existing:
            con.close()
            return root, generation_id, spec, translation
        for row in translation.gpi_rows:
            con.execute(
                "INSERT INTO generation_performance_inputs ("
                "generation_id, input_key, position, artifact_role, "
                "shot_revision_segment_position, "
                "performance_revision_id, "
                "vocal_performance_revision_id, blob_hash, "
                "binding_hash, segment_hash, translation_identity, "
                "derived_input_hash, created_at) VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (generation_id, row["input_key"], row["position"],
                 row["artifact_role"],
                 row["shot_revision_segment_position"],
                 row["performance_revision_id"],
                 row["vocal_performance_revision_id"],
                 row["blob_hash"], row["binding_hash"],
                 row["segment_hash"], row["translation_identity"],
                 row["derived_input_hash"], parent["created_at"]))
        con.commit()
    finally:
        con.close()
    return root, generation_id, spec, translation


async def _revision_id(client, generation_id):
    return (await _row(client, (
        "SELECT shot_revision_id FROM generations WHERE id = :g"),
        {"g": generation_id}))["shot_revision_id"]


async def _row(client, sql, params):
    engine = client._transport.app.state.engine
    from sqlalchemy import text

    async with engine.connect() as conn:
        return (await conn.execute(text(sql), params)).mappings().one()


@pytest.mark.asyncio
async def test_retained3_v5_over_v1_recovery_green(client, factory,
                                                   tmp_path):
    from tests.test_m17cc_recovery import _verify

    root, generation_id, spec, translation = await _staged_state(
        client, factory, tmp_path, v2=False)
    _verify(root)


@pytest.mark.asyncio
async def test_retained3_v5_over_v2_recovery_green(client, factory,
                                                   tmp_path):
    from tests.test_m17cc_recovery import _verify

    root, generation_id, spec, translation = await _staged_state(
        client, factory, tmp_path, v2=True)
    _verify(root)


@pytest.mark.asyncio
async def test_retained3_v2_realization_tamper_refused(client, factory,
                                                       tmp_path):
    """A coherent re-signed mutation of an OMITTED realization
    coordinate (visual_reference_pack_hash) refuses under recovery
    — the FPR33-03 law over the captured retained-3 v2 shape."""
    from soloring.domain.canonical import (
        canonical_hash as ch, canonical_json_str as cj,
    )
    from tests.test_m17cc_recovery import (
        _one, _sql, _verify_refuses,
    )

    root, generation_id, spec, translation = await _staged_state(
        client, factory, tmp_path, v2=True)
    spec_doc = json.loads(_one(root, (
        "SELECT workflow_spec_json FROM generations WHERE id = ?"),
        (generation_id,))["workflow_spec_json"])
    spec_doc["realization"][
        "visual_reference_pack_hash"] = "9" * 64
    _sql(root, (
        "UPDATE generations SET workflow_spec_json = ?, "
        "workflow_spec_hash = ? WHERE id = ?"),
        (cj(spec_doc), ch(spec_doc), generation_id))
    _verify_refuses(root, "visual_reference_pack_hash")
