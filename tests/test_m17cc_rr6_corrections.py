"""M17C-C RR6 correction (frozen register RR6-M17CC-01..02).

RR6-01 — the binding-subinterval contract, one law at both seams:

  binding.start <= vocal.start < vocal.end <= binding.end
  PLUS the exact binding-induced Performance timing.

Live: binding containment is a READINESS gate (BLOCKED_TIMING_MISMATCH)
placed BEFORE the induced-timing equality — outside-VP-trim stays
corruption (RR5-01), inside-trim outside-binding drift (including a
coherently dual-rewritten Performance row) is data and can NEVER
reach READY or capture. §12: whole-binding equality replaced by
containment + the exact induced interval recomputed from the immutable
binding origin/source-start/captured samples/rate (matching §13.4) —
a lawful inside-binding SUBSEGMENT capture passes its first historical
inspection.

RR6-02 — the persisted-position storage-class proof: a staged
`position = 0.5` row must terminate as typed RECOVERY_CORRUPTION
through the shared position law.
"""

from __future__ import annotations

import shutil
import sqlite3

import pytest

from soloring.domain.canonical import (
    canonical_hash as _ch, canonical_json_str as _cj,
)
from tests.m17cc_capture_helper import capture as _capture
from tests.test_m17cc_persist import _lawful
from tests.test_m17c_shot_mapping import _bound_world, _seg_body

_PARENTS = "shot_revision_performance_specs"
_CHILDREN = "shot_revision_performance_segments"
_HEAD = "0023_m17cc_capture_closure_preimage"


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
    async def _one(stmt, params=None):
        return (await _row(client, stmt, params))["n"]

    return (await _one("SELECT COUNT(*) AS n FROM shot_revisions "
                       "WHERE shot_id = :s", {"s": shot_id}),
            await _one(f"SELECT COUNT(*) AS n FROM {_PARENTS}"),
            await _one(f"SELECT COUNT(*) AS n FROM {_CHILDREN}"))


async def _attempt_capture(client, shot_id):
    from soloring.domain.revisions import capture_revision_with_visual
    from tests.conftest import make_tracked_maker
    factory = make_tracked_maker(_engine(client))
    async with factory() as session:
        return await capture_revision_with_visual(
            session, shot_id,
            settings=client._transport.app.state.settings)


def _recompute_mapping_row(client, world):
    """Recompute the vocal row's mapping_json/mapping_hash from its
    own current fields (a fully coherent corruption)."""
    con = sqlite3.connect(
        client._transport.app.state.settings.data_dir / "soloring.db")
    row = con.execute(
        "SELECT * FROM shot_vocal_segment_mappings WHERE shot_id = ? "
        "AND position = 0", (world["shot"],)).fetchone()
    cols = [d[0] for d in con.execute(
        "SELECT * FROM shot_vocal_segment_mappings "
        "LIMIT 0").description]
    r = dict(zip(cols, row))
    canonical = {
        "mapping_schema_version": 1,
        "vocal_performance_revision_id": r["vocal_performance_revision_id"],
        "source_start_sample": r["source_start_sample"],
        "source_end_sample_exclusive":
            r["source_end_sample_exclusive"],
        "sample_rate_hz": r["sample_rate_hz"],
        "performance_origin_ms": {
            "num": r["performance_origin_num"],
            "den": r["performance_origin_den"]},
        "shot_anchor_ms": {"num": r["shot_anchor_num"],
                           "den": r["shot_anchor_den"]},
    }
    con.execute(
        "UPDATE shot_vocal_segment_mappings SET mapping_json = ?, "
        "mapping_hash = ? WHERE shot_id = ? AND position = 0",
        (_cj(canonical), _ch(canonical), world["shot"]))
    con.commit()
    con.close()


def _recompute_perf_mapping_row(client, world, pr_id):
    """Recompute the Performance mapping row's mapping_json/hash from
    its own current fields (the dual half of the coherent rewrite)."""
    con = sqlite3.connect(
        client._transport.app.state.settings.data_dir / "soloring.db")
    row = con.execute(
        "SELECT * FROM shot_performance_segment_mappings WHERE "
        "shot_id = ? AND position = 0", (world["shot"],)).fetchone()
    cols = [d[0] for d in con.execute(
        "SELECT * FROM shot_performance_segment_mappings "
        "LIMIT 0").description]
    r = dict(zip(cols, row))
    doc = {
        "mapping_schema_version": 1,
        "performance_revision_id": pr_id,
        "performance_start_ms": {
            "num": r["performance_start_num"],
            "den": r["performance_start_den"]},
        "performance_end_ms": {
            "num": r["performance_end_num"],
            "den": r["performance_end_den"]},
        "shot_anchor_ms": {"num": r["shot_anchor_num"],
                           "den": r["shot_anchor_den"]},
        "vocal_mapping_position": r["vocal_mapping_position"],
    }
    con.execute(
        "UPDATE shot_performance_segment_mappings SET "
        "mapping_json = ?, mapping_hash = ? WHERE shot_id = ? "
        "AND position = 0",
        (_cj(doc), _ch(doc), world["shot"]))
    con.commit()
    con.close()


# ---------------------------------------------------------------------------
# RR6-01 positive: the supported public subsegment path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr6_inside_binding_subsegment_captures_and_reads(client):
    """The mandatory positive proof: binding [48000,96000); the same
    VP's vocal mapping publicly moved to the inside-binding
    subsegment [60000,84000); the Performance mapping publicly moved
    to the exact induced [250,750). READY, schema-8 capture, the
    FIRST §12 inspection green, recovery green."""
    from soloring.recovery.m17a_verifier import (
        verify_m17a_dialogue_vocal_state,
    )
    from soloring.recovery.m17c_verifier import verify_m17c_binding_state
    from tests.test_m17c_sr26_regressions import _backup_m17c
    import tempfile
    from pathlib import Path

    world, first_revision = await _stage_lawful(client)

    # the supported public vocal PUT: same VP, inside the binding
    r = await client.put(
        f"/shots/{world['shot']}/vocal-segments/0",
        json={
            "vocal_performance_revision_id": world["vp"]["id"],
            "source_start_sample": 60000,
            "source_end_sample_exclusive": 84000,
            "sample_rate_hz": 48000,
            "performance_origin_ms": {"num": 0, "den": 1},
            "shot_anchor_ms": {"num": 250, "den": 1},
        })
    assert r.status_code == 200, r.text

    # the supported public Performance PUT: the exact induced values
    # (origin 0 + (60000-48000)*1000/48000 = 250; end 750)
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 250, 750, 250, vp=0))
    assert r.status_code == 200, r.text

    red = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert red["ready"] is True, red

    revision, _visual = await _capture(client, world["shot"])
    snap = json.loads((await _row(client, (
        "SELECT snapshot_json FROM shot_revisions WHERE id = :r"),
        {"r": revision.id}))["snapshot_json"]) if False else None
    from soloring.domain.canonical import canonical_json_str
    raw = (await _row(client, (
        "SELECT snapshot_json FROM shot_revisions WHERE id = :r"),
        {"r": revision.id}))["snapshot_json"]
    import json as _json
    snap = _json.loads(raw)
    assert snap["schema_version"] == 8

    # the FIRST §12 inspection is green (containment + induced law)
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 200, r.text
    perf = r.json()["performance"]
    assert perf is not None
    seg = perf["segments"][0]
    assert seg["vocal"]["sample_interval"] == {
        "source_start_sample": 60000,
        "source_end_sample_exclusive": 84000,
        "sample_rate_hz": 48000}
    assert seg["performance_start_ms"] == {"num": 250, "den": 1}
    assert seg["performance_end_ms"] == {"num": 750, "den": 1}

    # recovery green on both verifiers
    tmp = Path(tempfile.mkdtemp())
    root = await _backup_m17c(client, tmp, "rr6-positive")
    verify_m17a_dialogue_vocal_state(
        root / "soloring.db", blob_root=root / "blobs")
    verify_m17c_binding_state(
        root / "soloring.db", root / "blobs", head=_HEAD)


# ---------------------------------------------------------------------------
# RR6-01 negative: the coherent outside-binding dual rewrite
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr6_dual_rewrite_stays_blocked_and_uncapturable(client):
    """The mandatory negative proof: vocal [36000,84000) (inside the
    VP trim, OUTSIDE the binding) + the Performance mapping coherently
    rewritten to the induced [-250,750) — both with exact canonical
    JSON/hash. Not corruption (inside the trim): readiness reports
    BLOCKED_TIMING_MISMATCH data; Shot detail keeps the commissioned
    nulls; capture returns the typed 409; counts unchanged. Recovery
    is NOT run against this drift (the predecessor contract separates
    immutable structural validity from mutable readiness — the live
    state alone proves the admission gate)."""
    from soloring.errors import SoloRingError

    world, first_revision = await _stage_lawful(client)
    before = await _counts(client, world["shot"])

    # the vocal half: inside the VP trim [0,144000), outside the
    # binding [48000,96000); coherent bytes/hash
    await _sql(client, (
        "UPDATE shot_vocal_segment_mappings SET "
        "source_start_sample = 36000, source_end_sample_exclusive "
        "= 84000 WHERE shot_id = :s AND position = 0"),
        {"s": world["shot"]})
    _recompute_mapping_row(client, world)
    # the Performance half: the exact binding-induced interval for
    # those samples (origin 0 + (36000-48000)*1000/48000 = -250;
    # end 750); coherent bytes/hash
    await _sql(client, (
        "UPDATE shot_performance_segment_mappings SET "
        "performance_start_num = -250, performance_start_den = 1, "
        "performance_end_num = 750, performance_end_den = 1 "
        "WHERE shot_id = :s AND position = 0"),
        {"s": world["shot"]})
    _recompute_perf_mapping_row(client, world, world["pr"]["id"])

    # readiness: BLOCKED working data, never a 500, never READY
    red = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert red["ready"] is False
    assert "BLOCKED_TIMING_MISMATCH" in [
        s["readiness"] for s in red["segments"]], red

    # the commissioned null posture
    detail = (await client.get(f"/shots/{world['shot']}")).json()
    assert detail["working_snapshot_hash"] is None
    assert detail["working_state_differs_from_approved"] is None

    # capture: the typed 409, nothing persisted
    with pytest.raises(SoloRingError) as excinfo:
        await _attempt_capture(client, world["shot"])
    assert excinfo.value.code == "PERFORMANCE_CAPTURE_NOT_READY"
    assert excinfo.value.status_code == 409

    after = await _counts(client, world["shot"])
    assert after == before


# ---------------------------------------------------------------------------
# RR6-02: the persisted-position storage-class proof
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr6_persisted_position_real_refuses_typed(client,
                                                           tmp_path):
    """Stage shot_vocal_segment_mappings.position = 0.5 in a copied
    database: the M17A recovery verifier terminates as TYPED
    RECOVERY_CORRUPTION through the shared position law — never a raw
    exception, never successful certification."""
    from soloring.errors import SoloRingError
    from soloring.recovery.m17a_verifier import (
        verify_m17a_dialogue_vocal_state,
    )

    world, revision = await _stage_lawful(client)

    data_dir = client._transport.app.state.settings.data_dir
    root = tmp_path / "rr6-position-staged"
    root.mkdir()
    src_db = data_dir / "soloring.db"
    con = sqlite3.connect(src_db)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()
    shutil.copy(src_db, root / "soloring.db")
    shutil.copytree(data_dir / "blobs", root / "blobs")
    # the malformed persisted position (PK column: update via the
    # deferred no-FK route)
    staged = sqlite3.connect(root / "soloring.db")
    staged.execute("PRAGMA foreign_keys = OFF")
    staged.execute(
        "UPDATE shot_vocal_segment_mappings SET position = 0.5 "
        "WHERE shot_id = ? AND position = 0", (world["shot"],))
    staged.commit()
    staged.close()

    with pytest.raises(SoloRingError) as rec:
        verify_m17a_dialogue_vocal_state(
            root / "soloring.db", blob_root=root / "blobs")
    assert rec.value.code == "RECOVERY_CORRUPTION"
    assert "position" in rec.value.message, rec.value.message
    assert "persisted integer domain" in rec.value.message, \
        rec.value.message


@pytest.mark.asyncio
async def test_rr6_clean_control_still_green(client):
    """The clean canonical control stays READY and capturable under
    the containment law (the original whole-binding fixture IS the
    trivial containment case)."""
    world, revision = await _stage_lawful(client)
    red = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert red["ready"] is True
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 200, r.text
    assert r.json()["performance"] is not None
