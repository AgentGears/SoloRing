"""M17C-C RR4 correction (frozen register RR4-M17CC-01) — the complete
predecessor vocal-mapping integrity contract before fresh capture.

The shared row-local verifier now carries the complete PERSISTED
STRUCTURAL law (canonical rationals: positive denominator, gcd-reduced,
zero only as 0/1 — the same rule M17A recovery enforces, now ONE law
in ONE place), and the live caller seam adds the CROSS-ROW authority
checks: a present paired vocal mapping's sample_rate_hz must AGREE
with the immutable synchronization binding (whose own rate == VP
native rate is a binding-table law verified at both grades), and its
source interval must lie INSIDE the binding's authoritative interval
(the §8.3 creation law proven at admission time). ABSENCE stays lawful
BLOCKED_BINDING_INTEGRITY data (RR-02 exact).

The frozen proofs:
1. RATE-ONLY coherent corruption: change sample_rate_hz, recompute the
   exact canonical JSON/hash → readiness/capture 500 before
   persistence, counts unchanged, M17A recovery refuses the staged
   state (mapping rate != VP native rate);
2. CANONICAL-RATIONAL coherent corruption: anchor 1/1 → 2/2 with exact
   recomputed canonical JSON/hash (the document law passes; the
   shared rational law refuses) → same refusal chain, recovery refuses
   on the same law;
3. clean control, the RR3 semantic-forgery/noncanonical-byte proofs,
   and the supported DELETE all remain green.
"""

from __future__ import annotations

import json
import math
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


def _rewrite_row(client, world, *, sql_set, params):
    """Apply the column tamper, then recompute the row's mapping_json
    and mapping_hash from its OWN post-tamper fields (a fully COHERENT
    corruption — the RR3 byte law passes by construction)."""
    con = sqlite3.connect(
        client._transport.app.state.settings.data_dir / "soloring.db")
    con.execute(sql_set, params)
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
    # the recomputed bytes/hash ARE the row's own canonical form —
    # the RR3 byte law passes by construction
    check = con.execute(
        "SELECT mapping_json, mapping_hash FROM "
        "shot_vocal_segment_mappings WHERE shot_id = ? "
        "AND position = 0", (world["shot"],)).fetchone()
    con.close()
    assert check[0] == _cj(canonical)
    assert check[1] == _ch(canonical)
    return canonical


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["rate", "rational"])
async def test_rr4_coherent_predecessor_corruption_refuses(client,
                                                            tmp_path,
                                                            mode):
    """The frozen adversarial pair. RATE: sample_rate_hz changed to
    another positive value, exact canonical JSON/hash recomputed (the
    byte law passes; the binding-rate authority law refuses). RATIONAL:
    the vocal anchor 1/1 rewritten as 2/2 (NOT gcd-reduced) with exact
    recomputed canonical JSON/hash (the byte law passes; the shared
    canonical-rational law refuses). Both: readiness + capture fail
    closed 500 BEFORE persistence, counts unchanged, M17A recovery
    independently refuses the staged state on the same underlying
    law."""
    from soloring.errors import SoloRingError
    from soloring.recovery.m17a_verifier import (
        verify_m17a_dialogue_vocal_state,
    )

    world, first_revision = await _stage_lawful(client)

    if mode == "rate":
        # another POSITIVE rate the DB permits (ck_svsm only requires
        # > 0); every other column untouched
        _rewrite_row(
            client, world,
            sql_set="UPDATE shot_vocal_segment_mappings SET "
                    "sample_rate_hz = ? WHERE shot_id = ? "
                    "AND position = 0",
            params=(44100, world["shot"]))
        live_reason = "disagrees with the immutable synchronization " \
                      "binding rate"
        recovery_reason = "mapping rate != VP native rate"
    else:
        # 1/1 rewritten as 2/2 — same Fraction value, NOT reduced
        row = await _row(client, (
            "SELECT shot_anchor_num, shot_anchor_den FROM "
            "shot_vocal_segment_mappings WHERE shot_id = :s "
            "AND position = 0"), {"s": world["shot"]})
        assert (row["shot_anchor_num"], row["shot_anchor_den"]) \
            == (0, 1) or math.gcd(
                abs(row["shot_anchor_num"]),
                row["shot_anchor_den"]) == 1
        _rewrite_row(
            client, world,
            sql_set="UPDATE shot_vocal_segment_mappings SET "
                    "shot_anchor_num = shot_anchor_num * 2, "
                    "shot_anchor_den = shot_anchor_den * 2 "
                    "WHERE shot_id = ? AND position = 0",
            params=(world["shot"],))
        live_reason = "is not in canonical reduced form"
        recovery_reason = "canonical rehash fail: " \
                          "shot_anchor_ms rational"

    before = await _counts(client, world["shot"])

    # readiness fails closed with the precise law
    r = await client.get(
        f"/shots/{world['shot']}/performance-readiness")
    assert r.status_code == 500, r.text
    assert live_reason in r.json()["message"], r.text

    # capture fails with the SAME corruption before the builder
    with pytest.raises(SoloRingError) as excinfo:
        await _attempt_capture(client, world["shot"])
    assert excinfo.value.status_code == 500
    assert live_reason in excinfo.value.message

    # nothing was persisted by either refused path
    after = await _counts(client, world["shot"])
    assert after == before

    # M17A recovery independently refuses the same staged state on the
    # same underlying law (hand-staged copy — the backup API itself
    # runs the same chain and refuses during staging)
    data_dir = client._transport.app.state.settings.data_dir
    root = tmp_path / f"rr4-{mode}-staged"
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
    assert recovery_reason in rec.value.message, rec.value.message


@pytest.mark.asyncio
async def test_rr4_clean_control_and_rr3_cases_green(client, tmp_path):
    """The clean canonical control (READY, schema-8 capture, §12 +
    M17C recovery valid, M17A recovery valid) and the RR3
    semantic-forgery + noncanonical-byte proofs remain green under the
    completed law."""
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
    root = await _backup_m17c(client, tmp_path, "rr4-clean")
    verify_m17a_dialogue_vocal_state(
        root / "soloring.db", blob_root=root / "blobs")
    verify_m17c_binding_state(
        root / "soloring.db", root / "blobs", head=_HEAD)

    # the RR3 proofs still hold under the completed law
    lawful = await _row(client, (
        "SELECT mapping_json FROM shot_vocal_segment_mappings "
        "WHERE shot_id = :s AND position = 0"), {"s": world["shot"]})
    doc = json.loads(lawful["mapping_json"])

    # semantic forgery
    await _sql(client, (
        "UPDATE shot_vocal_segment_mappings SET mapping_json = :j "
        "WHERE shot_id = :s AND position = 0"),
        {"j": '{"mapping_schema_version": 1, "forged": true}',
         "s": world["shot"]})
    r = await client.get(
        f"/shots/{world['shot']}/performance-readiness")
    assert r.status_code == 500, r.text
    assert "mapping_json is not the canonical document" \
        in r.json()["message"], r.text

    # noncanonical bytes of the canonical value
    await _sql(client, (
        "UPDATE shot_vocal_segment_mappings SET mapping_json = :j "
        "WHERE shot_id = :s AND position = 0"),
        {"j": json.dumps(dict(reversed(list(doc.items()))), indent=2),
         "s": world["shot"]})
    r = await client.get(
        f"/shots/{world['shot']}/performance-readiness")
    assert r.status_code == 500, r.text
    assert "not its canonical serialized form" in r.json()["message"], \
        r.text


@pytest.mark.asyncio
async def test_rr4_supported_delete_still_blocked_data(client):
    """RR-02 preserved exactly: the supported DELETE of the paired
    vocal mapping remains BLOCKED_BINDING_INTEGRITY data — the
    completed structural/authority laws apply only to a PRESENT row."""
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
