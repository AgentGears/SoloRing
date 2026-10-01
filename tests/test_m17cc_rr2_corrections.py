"""M17C-C RR2 correction (frozen register RR2-M17CC-01) — the
fresh-capture admission seam.

The frozen law: a PRESENT paired ShotVocalSegmentMapping must satisfy
its complete persisted canonical structure (mapping_schema_version,
the exact canonical document reconstructed from the row's own fields,
canonical mapping_json, and mapping_hash == the canonical digest)
BEFORE any of its bytes enter grammar-v2 capture identity. ABSENCE
stays the lawful BLOCKED_BINDING_INTEGRITY data (RR-02 preserved
exactly); PRESENT-but-noncanonical is corruption and fails closed.

Mandatory proofs (frozen by the commission):
1. corrupt only mapping_hash (another storage-valid 64-hex) → the
   Performance mapping itself remains admissible, but capture fails
   with the corruption posture BEFORE builder/persistence;
2. corrupt only mapping_json (semantic columns + hash untouched) →
   same refusal;
3. revision/parent/children counts unchanged after each refusal;
4. clean control: the identical lawful world captures schema 8 and is
   immediately valid under §12 AND recovery;
5. the RR-02 supported-delete case still reports blocked data (the
   verifier does not convert absence into corruption).
"""

from __future__ import annotations

import pytest

from tests.m17cc_capture_helper import capture as _capture
from tests.test_m17cc_persist import _lawful
from tests.test_m17c_shot_mapping import _bound_world

_PARENTS = "shot_revision_performance_specs"
_CHILDREN = "shot_revision_performance_segments"


def _engine(client):
    return client._transport.app.state.engine


async def _sql(client, stmt, params=None):
    from sqlalchemy import text
    async with _engine(client).begin() as conn:
        await conn.execute(text(stmt), params or {})


async def _row(client, stmt, params=None):
    from sqlalchemy import text
    async with _engine(client).connect() as conn:
        return dict((await conn.execute(
            text(stmt), params or {})).mappings().one())


async def _stage_lawful(client):
    world = await _bound_world(client)
    await _lawful(client, world, extra=True)
    revision, _visual = await _capture(client, world["shot"])
    return world, revision


async def _counts(client, shot_id):
    return {
        "revisions": (await _row(client, (
            "SELECT COUNT(*) AS n FROM shot_revisions WHERE "
            "shot_id = :s"), {"s": shot_id}))["n"],
        "parents": (await _row(client, (
            f"SELECT COUNT(*) AS n FROM {_PARENTS}")))["n"],
        "children": (await _row(client, (
            f"SELECT COUNT(*) AS n FROM {_CHILDREN}")))["n"],
    }

async def _attempt_capture(client, shot_id):
    from soloring.domain.revisions import capture_revision_with_visual
    from tests.conftest import make_tracked_maker
    factory = make_tracked_maker(_engine(client))
    async with factory() as session:
        return await capture_revision_with_visual(
            session, shot_id,
            settings=client._transport.app.state.settings)


async def _capture_fragments_before_corruption(client, world):
    """Prove the world is otherwise admissible: readiness READY."""
    red = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert red["ready"] is True, red


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["mapping_hash", "mapping_json"])
async def test_rr2_precapture_vocal_corruption_refuses(client, mode):
    """Corrupt ONLY the paired vocal mapping's persisted canonical
    bytes/hash BEFORE capture: the Performance mapping remains
    admissible, readiness would otherwise be READY — and the corrupted
    PRESENT row makes the readiness projection itself fail closed
    (capture never reaches the builder or persistence)."""
    from soloring.errors import SoloRingError

    world, first_revision = await _stage_lawful(client)

    # the world was READY and captured cleanly BEFORE corruption
    assert (await _counts(client, world["shot"]))["revisions"] == 1

    # delete the first capture's companions so the post-refusal count
    # comparison is against a clean slate? No — the frozen proof wants
    # counts UNCHANGED by the refused attempt; keep the lawful capture
    # and compare before/after the refusal.
    if mode == "mapping_hash":
        await _sql(client, (
            "UPDATE shot_vocal_segment_mappings SET mapping_hash = "
            ":h WHERE shot_id = :s AND position = 0"),
            {"h": "e" * 64, "s": world["shot"]})
    else:
        # semantic columns + hash untouched; ONLY the stored document
        # bytes become noncanonical
        await _sql(client, (
            "UPDATE shot_vocal_segment_mappings SET mapping_json = "
            ":j WHERE shot_id = :s AND position = 0"),
            {"j": '{"mapping_schema_version": 1, "forged": true}',
             "s": world["shot"]})

    before = await _counts(client, world["shot"])

    # the readiness PROJECTION fails closed on the present-but-
    # noncanonical row (the same law the capture read consumes)
    r = await client.get(
        f"/shots/{world['shot']}/performance-readiness")
    assert r.status_code == 500, r.text
    assert "fails its persisted canonical structural law" \
        in r.json()["message"], r.text
    # the precise reason names the corrupted member
    reason = ("mapping_hash is not the canonical digest"
              if mode == "mapping_hash"
              else "mapping_json is not the canonical document")
    assert reason in r.json()["message"], r.text

    # capture fails with the corruption posture BEFORE the builder
    with pytest.raises(SoloRingError) as excinfo:
        await _attempt_capture(client, world["shot"])
    assert excinfo.value.status_code == 500
    assert "fails its persisted canonical structural law" \
        in excinfo.value.message

    # nothing was persisted by either refused path
    after = await _counts(client, world["shot"])
    assert after == before


@pytest.mark.asyncio
async def test_rr2_clean_control_still_captures(client):
    """The identical lawful world captures schema 8 and the fresh
    capture is IMMEDIATELY valid under §12 and recovery."""
    from soloring.recovery.m17c_verifier import verify_m17c_binding_state

    world, revision = await _stage_lawful(client)

    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 200, r.text
    assert r.json()["performance"] is not None

    from tests.test_m17c_sr26_regressions import _backup_m17c
    import tempfile
    from pathlib import Path
    tmp = Path(tempfile.mkdtemp())
    root = await _backup_m17c(client, tmp, "rr2-clean")
    verify_m17c_binding_state(
        root / "soloring.db", root / "blobs",
        head="0023_m17cc_capture_closure_preimage")


@pytest.mark.asyncio
async def test_rr2_supported_delete_still_blocked_data(client):
    """RR-02 preserved EXACTLY: the supported DELETE of the paired
    vocal mapping remains BLOCKED_BINDING_INTEGRITY data — the new
    verifier never converts ABSENCE into corruption."""
    world, revision = await _stage_lawful(client)
    r = await client.delete(f"/shots/{world['shot']}/vocal-segments/0")
    assert r.status_code in (200, 204), r.text

    red = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert red["ready"] is False
    assert "BLOCKED_BINDING_INTEGRITY" in [
        s["readiness"] for s in red["segments"]]

    detail = (await client.get(f"/shots/{world['shot']}")).json()
    assert detail["working_snapshot_hash"] is None
    assert detail["working_state_differs_from_approved"] is None
