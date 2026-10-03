"""C3 corrective regressions (final bounded cycle): cheap structural VP
authority closure on authoritative reads (C3-01) with a direct
retained-media cost-boundary spy, and the branch-specific inverse
recovery proof (C3-02, asserted in the DR26 file)."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.m17c_seed import dialogue_bound_body, make_vp
from tests.test_m17c_binding_transitions import _create_bound, _adopt


async def _sql(client, stmt, params=None):
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(stmt), params or {})


async def _bound_world(client):
    world = await make_vp(client)
    candidate = await _create_bound(client, world)
    revision = await _adopt(client, candidate["id"])
    return world, candidate, revision


def _corrupt(resp):
    assert resp.status_code == 500, resp.text
    assert resp.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"


# ---------------------------------------------------------------------------
# C3-01 — GETs prove the cheap FULL structural VP authority closure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_c3_01_vp_upstream_structural_tamper_refuses_gets_and_recovery(
        client, tmp_path):
    """Repoint ONLY the VP's dialogue_line_revision_id at an alternate
    same-project/same-speaker DLR. Every shallow GET check stays
    apparently valid (speaker, project, rate, trim, binding hashes,
    alignments, retained audio all unchanged) — only the structural
    VP↔VocalCandidate closure can refuse."""
    world, candidate, revision = await _bound_world(client)

    # lawful alternate DLR: same dialogue line (same project/speaker),
    # a second revision of it
    alt_dlr = (await client.post(
        f"/dialogue-lines/{world['line_id']}/revisions",
        json={
            "speaker_subject_id": world["subject_id"],
            "language": "en",
            "wording": "C3 alternate same-speaker DLR.",
        },
    )).json()
    await _sql(
        client,
        "UPDATE vocal_performance_revisions "
        "SET dialogue_line_revision_id = :d WHERE id = :v",
        {"d": alt_dlr["id"], "v": world["vp"]["id"]})

    _corrupt(await client.get(
        f"/performance-candidates/{candidate['id']}/vocal-binding"))
    _corrupt(await client.get(
        f"/performance-revisions/{revision['id']}/vocal-binding"))

    # recovery refuses the same staged state (via the M17A structural
    # closure law on the VP row — the same invariant the GET now
    # enforces cheaply)
    import sqlite3
    from tests.test_m17c_sr26_regressions import (
        _backup_m17c, _restore_refuses)
    # back up the LAWFUL state first (backup runs the full chain)
    await _sql(
        client,
        "UPDATE vocal_performance_revisions "
        "SET dialogue_line_revision_id = :d WHERE id = :v",
        {"d": world["dialogue_line_revision_id"], "v": world["vp"]["id"]})
    root = await _backup_m17c(client, tmp_path, "c3a")
    con = sqlite3.connect(root / "soloring.db")
    con.execute(
        "UPDATE vocal_performance_revisions "
        "SET dialogue_line_revision_id = ? WHERE id = ?",
        (alt_dlr["id"], world["vp"]["id"]))
    con.commit()
    con.close()
    await _restore_refuses(root, tmp_path, "c3a")


@pytest.mark.asyncio
async def test_c3_01_gets_do_not_touch_retained_vp_media(client,
                                                         monkeypatch):
    """Direct cost-boundary proof: spy the VP retained-audio blob
    verification seam and assert that both lawful binding GETs succeed
    WITHOUT invoking it. The seam is `soloring.performance.vocal.
    _verify_blob` — the only path that reads/hashes the VP audio blob
    in the M17C verifier stack (the candidate payload blob used by
    verify_candidate_integrity is a different storage path and is not
    patched, so the proof is unambiguous)."""
    world, candidate, revision = await _bound_world(client)

    import soloring.performance.vocal as vocal_module
    calls = []

    async def _spy(session, settings, blob_hash):
        calls.append(blob_hash)
        raise AssertionError(
            "authoritative binding GET must not read the retained VP "
            f"audio blob (spied seam invoked for {blob_hash!r})")

    monkeypatch.setattr(vocal_module, "_verify_blob", _spy)

    ok_c = await client.get(
        f"/performance-candidates/{candidate['id']}/vocal-binding")
    assert ok_c.status_code == 200, ok_c.text
    ok_r = await client.get(
        f"/performance-revisions/{revision['id']}/vocal-binding")
    assert ok_r.status_code == 200, ok_r.text
    assert calls == [], (
        "the retained VP media seam was invoked by an authoritative "
        f"GET: {calls}")
