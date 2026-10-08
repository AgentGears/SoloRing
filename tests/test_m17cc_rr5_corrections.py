"""M17C-C RR5 correction (frozen register RR5-M17CC-01..02).

RR5-01 — the mutable-vs-immutable distinction restored: a present
paired vocal mapping's immutable corruption law is the VP AUTHORITATIVE
TRIM, not the mutable Performance binding window. A lawful same-VP
public re-segmentation inside the trim but outside the old binding is
MUTABLE WORKING DRIFT: readiness reports BLOCKED_TIMING_MISMATCH
(data), Shot detail stays 200 with the commissioned null posture,
capture returns the typed 409, nothing persists. Only an interval
actually OUTSIDE the VP trim is corruption (500 + recovery refusal).

RR5-02 — the shared predecessor verifier is TOTAL over persisted
SQLite storage classes: position/source-start/source-end/rate must be
actual non-bool integers in their lawful domains (position via the ONE
shared validate_mapping_position; the pairs via the ONE shared
canonical_rational — actual integer pair, positive denominator,
canonical reduction/zero, i64 bounds). A storage-valid non-integral
REAL (e.g. source_start_sample = 48000.5, or a REAL denominator) with
exact canonical JSON/hash recompute refuses as the TYPED structural
law on live readiness AND capture AND M17A recovery — never a raw
TypeError/OverflowError through math.gcd or Fraction, never successful
certification.
"""

from __future__ import annotations

import json
import shutil
import sqlite3

import pytest

from soloring.domain.canonical import (
    canonical_hash as _ch, canonical_json_str as _cj,
)
from tests.m17cc_capture_helper import capture as _capture
from tests.test_m17cc_persist import _lawful
from tests.test_m17c_shot_mapping import _bound_world

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
    """Recompute mapping_json/mapping_hash from the row's OWN current
    fields (a fully coherent corruption — the byte law passes by
    construction, whatever storage classes the row now carries)."""
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
    return canonical


# ---------------------------------------------------------------------------
# RR5-01 — the supported public re-segmentation stays working-state data
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr5_public_resegmentation_is_blocked_data(client):
    """The decisive RR5-01 proof: the PUBLIC M17A PUT moves the same
    VP from the binding interval [48000,96000) to [0,48000) — inside
    the VP trim (the whole 144000 samples), outside the old binding.
    The PUT succeeds; readiness reports BLOCKED_TIMING_MISMATCH (never
    500); Shot detail stays 200 with the commissioned nulls; capture
    returns the typed 409; revision/parent/child counts do not
    change."""
    from soloring.errors import SoloRingError

    world, revision = await _stage_lawful(client)
    before = await _counts(client, world["shot"])

    r = await client.put(
        f"/shots/{world['shot']}/vocal-segments/0",
        json={
            "vocal_performance_revision_id": world["vp"]["id"],
            "source_start_sample": 0,
            "source_end_sample_exclusive": 48000,
            "sample_rate_hz": 48000,
            "performance_origin_ms": {"num": 0, "den": 1},
            "shot_anchor_ms": {"num": 0, "den": 1},
        })
    assert r.status_code == 200, r.text

    # readiness: BLOCKED working data, never a 500
    red = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert red["ready"] is False
    assert "BLOCKED_TIMING_MISMATCH" in [
        s["readiness"] for s in red["segments"]], red

    # Shot detail: the commissioned non-READY null posture, 200
    detail = (await client.get(f"/shots/{world['shot']}")).json()
    assert detail["working_snapshot_hash"] is None
    assert detail["working_state_differs_from_approved"] is None

    # capture: the typed 409 with diagnostics, nothing persisted
    with pytest.raises(SoloRingError) as excinfo:
        await _attempt_capture(client, world["shot"])
    assert excinfo.value.code == "PERFORMANCE_CAPTURE_NOT_READY"
    assert excinfo.value.status_code == 409

    after = await _counts(client, world["shot"])
    assert after == before


@pytest.mark.asyncio
async def test_rr5_outside_trim_tamper_still_corruption(client,
                                                         tmp_path):
    """The other side of the restored distinction: a COHERENT present
    row whose interval lies OUTSIDE the VP authoritative trim is
    corruption — readiness/capture 500, counts unchanged, M17A
    recovery refuses the staged state."""
    from soloring.errors import SoloRingError
    from soloring.recovery.m17a_verifier import (
        verify_m17a_dialogue_vocal_state,
    )

    world, revision = await _stage_lawful(client)
    # outside the binding AND outside the VP trim (the trim is the
    # whole 144000 retained samples)
    await _sql(client, (
        "UPDATE shot_vocal_segment_mappings SET source_start_sample "
        "= 144000, source_end_sample_exclusive = 150000 "
        "WHERE shot_id = :s AND position = 0"), {"s": world["shot"]})
    _recompute_mapping_row(client, world)

    before = await _counts(client, world["shot"])

    r = await client.get(
        f"/shots/{world['shot']}/performance-readiness")
    assert r.status_code == 500, r.text
    assert "outside the VP authoritative trim" in r.json()["message"], \
        r.text

    with pytest.raises(SoloRingError) as excinfo:
        await _attempt_capture(client, world["shot"])
    assert excinfo.value.status_code == 500
    assert "outside the VP authoritative trim" in excinfo.value.message

    after = await _counts(client, world["shot"])
    assert after == before

    # M17A recovery independently refuses the same staged state
    data_dir = client._transport.app.state.settings.data_dir
    root = tmp_path / "rr5-trim-staged"
    root.mkdir()
    src_db = data_dir / "soloring.db"
    con = sqlite3.connect(src_db)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()
    shutil.copy(src_db, root / "soloring.db")
    shutil.copytree(data_dir / "blobs", root / "blobs")
    with pytest.raises(SoloRingError) as rec:
        verify_m17a_dialogue_vocal_state(
            root / "soloring.db", blob_root=root / "blobs")
    assert rec.value.code == "RECOVERY_CORRUPTION"
    assert "outside VP authoritative trim" in rec.value.message


# ---------------------------------------------------------------------------
# RR5-02 — the shared law is total over SQLite storage classes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["real_coordinate",
                                  "real_rational_den"])
async def test_rr5_real_storage_class_refuses_typed(client, tmp_path,
                                                    mode):
    """Storage-valid non-integral REAL values staged directly with
    exact canonical JSON/hash recompute: the shared law refuses
    BEFORE any exact timing arithmetic; live readiness and capture
    return the TYPED corruption (never a raw TypeError through
    Fraction); counts unchanged; M17A recovery independently refuses
    the staged database (also typed)."""
    from soloring.errors import SoloRingError
    from soloring.recovery.m17a_verifier import (
        verify_m17a_dialogue_vocal_state,
    )

    world, revision = await _stage_lawful(client)

    if mode == "real_coordinate":
        await _sql(client, (
            "UPDATE shot_vocal_segment_mappings SET "
            "source_start_sample = 48000.5 "
            "WHERE shot_id = :s AND position = 0"),
            {"s": world["shot"]})
        reason = "is not a persisted integer"
    else:
        # a NON-integral REAL: SQLite INTEGER affinity stores exactly-
        # integral REALs as integers, so 2.5 is required for the row
        # to genuinely carry the non-integer storage class
        await _sql(client, (
            "UPDATE shot_vocal_segment_mappings SET "
            "performance_origin_den = 2.5 "
            "WHERE shot_id = :s AND position = 0"),
            {"s": world["shot"]})
        reason = "is not a persisted integer pair"

    canonical = _recompute_mapping_row(client, world)
    # the recomputed bytes/hash ARE the row's own form — the RR3 byte
    # law passes by construction; only the storage-class law can refuse
    con = sqlite3.connect(
        client._transport.app.state.settings.data_dir / "soloring.db")
    stored = con.execute(
        "SELECT mapping_json FROM shot_vocal_segment_mappings "
        "WHERE shot_id = ? AND position = 0",
        (world["shot"],)).fetchone()[0]
    con.close()
    assert stored == _cj(canonical)

    before = await _counts(client, world["shot"])

    # live readiness: the TYPED corruption, never a raw TypeError
    r = await client.get(
        f"/shots/{world['shot']}/performance-readiness")
    assert r.status_code == 500, r.text
    assert "fails its persisted canonical structural law" \
        in r.json()["message"], r.text
    assert reason in r.json()["message"], r.text

    with pytest.raises(SoloRingError) as excinfo:
        await _attempt_capture(client, world["shot"])
    assert excinfo.value.status_code == 500
    assert reason in excinfo.value.message

    after = await _counts(client, world["shot"])
    assert after == before

    # M17A recovery independently refuses the same staged database —
    # also typed, never green, never a raw exception
    data_dir = client._transport.app.state.settings.data_dir
    root = tmp_path / f"rr5-{mode}-staged"
    root.mkdir()
    src_db = data_dir / "soloring.db"
    con = sqlite3.connect(src_db)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()
    shutil.copy(src_db, root / "soloring.db")
    shutil.copytree(data_dir / "blobs", root / "blobs")
    with pytest.raises(SoloRingError) as rec:
        verify_m17a_dialogue_vocal_state(
            root / "soloring.db", blob_root=root / "blobs")
    assert rec.value.code == "RECOVERY_CORRUPTION"
    assert reason in rec.value.message, rec.value.message


@pytest.mark.asyncio
async def test_rr5_clean_control_and_prior_proofs_green(client):
    """The clean control (READY, schema-8 capture, §12 + recovery
    valid) and the prior-register proofs stay green under the total
    law: the RR3 noncanonical-byte case, the RR4 canonical-rational
    case, and the supported DELETE."""
    from soloring.recovery.m17a_verifier import (
        verify_m17a_dialogue_vocal_state,
    )
    from soloring.recovery.m17c_verifier import verify_m17c_binding_state

    world, revision = await _stage_lawful(client)

    red = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert red["ready"] is True

    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 200, r.text
    assert r.json()["performance"] is not None

    from tests.test_m17c_sr26_regressions import _backup_m17c
    import tempfile
    from pathlib import Path
    tmp = Path(tempfile.mkdtemp())
    root = await _backup_m17c(client, tmp, "rr5-clean")
    verify_m17a_dialogue_vocal_state(
        root / "soloring.db", blob_root=root / "blobs")
    verify_m17c_binding_state(
        root / "soloring.db", root / "blobs", head=_HEAD)

    # RR3 noncanonical bytes still refuse
    lawful = await _row(client, (
        "SELECT mapping_json FROM shot_vocal_segment_mappings "
        "WHERE shot_id = :s AND position = 0"), {"s": world["shot"]})
    doc = json.loads(lawful["mapping_json"])
    await _sql(client, (
        "UPDATE shot_vocal_segment_mappings SET mapping_json = :j "
        "WHERE shot_id = :s AND position = 0"),
        {"j": json.dumps(dict(reversed(list(doc.items()))), indent=2),
         "s": world["shot"]})
    r = await client.get(
        f"/shots/{world['shot']}/performance-readiness")
    assert r.status_code == 500, r.text
    assert "not its canonical serialized form" in r.json()["message"]
    # restore the lawful bytes for the remaining proofs
    await _sql(client, (
        "UPDATE shot_vocal_segment_mappings SET mapping_json = :j "
        "WHERE shot_id = :s AND position = 0"),
        {"j": _cj(doc), "s": world["shot"]})

    # RR4 canonical rational still refuses (2/2 with recompute)
    await _sql(client, (
        "UPDATE shot_vocal_segment_mappings SET "
        "shot_anchor_num = shot_anchor_num * 2, "
        "shot_anchor_den = shot_anchor_den * 2 "
        "WHERE shot_id = :s AND position = 0"), {"s": world["shot"]})
    _recompute_mapping_row(client, world)
    r = await client.get(
        f"/shots/{world['shot']}/performance-readiness")
    assert r.status_code == 500, r.text
    assert "is not in canonical reduced form" in r.json()["message"]
    await _sql(client, (
        "UPDATE shot_vocal_segment_mappings SET "
        "shot_anchor_num = shot_anchor_num / 2, "
        "shot_anchor_den = shot_anchor_den / 2 "
        "WHERE shot_id = :s AND position = 0"), {"s": world["shot"]})
    _recompute_mapping_row(client, world)

    # supported DELETE: absence stays blocked data
    r = await client.delete(f"/shots/{world['shot']}/vocal-segments/0")
    assert r.status_code in (200, 204), r.text
    red = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert red["ready"] is False
    assert "BLOCKED_BINDING_INTEGRITY" in [
        s["readiness"] for s in red["segments"]]
