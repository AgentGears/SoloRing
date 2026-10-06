"""M17C-C RR21 correction (frozen register RR21-M17CC-01 — HIGH) —
the exact web round-trip for authoritative Shot duration.

RR18–RR20 establish `[0, 2^63-1]` as the lawful backend
Shot-duration domain, but the web boundary transported duration
through JavaScript `number` (IEEE-754): `res.json()` rounded
`2^53+1` before the editor rendered it, every form save
unconditionally rebuilt `duration_ms` via `Number(...)`, and the
backend accepted the rounded value — so an ordinary editor session
on an unrelated field SILENTLY REWROTE lawful durable authority.

The correction: ONE additive exact transport coordinate —
``duration_ms_dec``, the backend integer's canonical decimal string
(derived on ``ShotRead`` and ``IntraShotRead`` from the row's OWN
durable integer; transport data, never a second authority domain) —
plus the DELIBERATE canonical-decimal admission contract on
ShotCreate/ShotPatch (a bare digit string converted to the exact
integer; sign/exponent/point/whitespace/leading-zero aliases and
floats refuse as ordinary validation). The frontend keeps duration
as the exact decimal string end to end (``exactDuration.ts`` —
grammar + domain via BigInt, never through ``number``);
``ShotForm`` initializes AND submits from the string; the M16
timeline renders and guards against ``duration_ms_dec``.

The battery proves the exact round-trip through the REAL production
paths — the actual HTTP JSON responses (the same wire bytes
``res.json()`` parses) and the actual PATCH wire the client sends —
at the strongest adversary ``2^53+1`` (its JS-rounded value stays
backend-lawful, demonstrating silent mutation rather than mere
rejection) and at the storage maximum ``2^63-1``, plus the fences.
"""

from __future__ import annotations

import json

import pytest

_SQLITE_MAX = 9_223_372_036_854_775_807  # 2^63 - 1
_JS_ROUNDED = 9_007_199_254_740_992      # what IEEE-754 does to 2^53+1
_STRONG = 9_007_199_254_740_993          # 2^53 + 1
_OTHER_UNSAFE = 9_007_199_254_740_995    # another lawful unsafe integer
_SAFE_MAX = 9_007_199_254_740_991        # 2^53 - 1


async def _duration_column(client, shot_id):
    from sqlalchemy import text
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        return (await conn.execute(text(
            "SELECT duration_ms FROM shots WHERE id = :s"),
            {"s": shot_id})).scalar_one()


# ---------------------------------------------------------------------------
# The exact round-trip at 2^53+1 and 2^63−1 (production paths)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("exact", [_STRONG, _SQLITE_MAX])
async def test_rr21_exact_web_round_trip(client, factory, exact):
    """The production wire round-trip for the exact integer: the
    GET /shots/{id} JSON carries duration_ms_dec as the exact
    decimal string (json.loads parses it losslessly — the same bytes
    res.json() parses); an unrelated-field PATCH omitting duration
    (the web form's untouched exact string re-submitted as the
    canonical decimal) leaves the column EXACT; a deliberate edit to
    another exact decimal persists exactly; the intra-shot
    projection carries the same exact coordinate; and the fences
    hold (2^63 authoring refused; ambiguous decimal aliases
    refused)."""
    r = await client.post("/projects", json={"name": "rr21"})
    assert r.status_code == 201, r.text
    project_id = r.json()["id"]

    # (1) persist the exact integer through the supported authoring
    # path — the canonical decimal string (the web transport form)
    r = await client.post(
        f"/projects/{project_id}/shots",
        json={"subject": "s", "duration_ms": str(exact)})
    assert r.status_code == 201, r.text
    shot_id = r.json()["id"]
    assert await _duration_column(client, shot_id) == exact

    # (2) the production GET response: duration_ms_dec is the exact
    # decimal string in the RAW wire JSON (what res.json() parses —
    # a JSON string parses losslessly; the legacy number field is
    # the one that cannot be authoritative)
    r = await client.get(f"/shots/{shot_id}")
    assert r.status_code == 200, r.text
    wire = json.loads(r.text)
    assert wire["duration_ms_dec"] == str(exact)
    assert int(wire["duration_ms_dec"]) == exact

    # (3) the unrelated-field save: the web form re-submits the
    # UNTOUCHED exact transport string alongside the title change —
    # the durable column stays the exact integer
    r = await client.patch(
        f"/shots/{shot_id}",
        json={"title": "renamed",
              "duration_ms": wire["duration_ms_dec"]})
    assert r.status_code == 200, r.text
    assert await _duration_column(client, shot_id) == exact
    # the response re-derives the exact coordinate
    assert r.json()["duration_ms_dec"] == str(exact)

    # (4) a deliberate edit to another lawful exact decimal
    if exact == _STRONG:
        r = await client.patch(
            f"/shots/{shot_id}",
            json={"duration_ms": str(_OTHER_UNSAFE)})
        assert r.status_code == 200, r.text
        assert await _duration_column(client, shot_id) == _OTHER_UNSAFE
        # ... and back
        r = await client.patch(
            f"/shots/{shot_id}", json={"duration_ms": str(exact)})
        assert r.status_code == 200, r.text
        assert await _duration_column(client, shot_id) == exact

    # (5) 2^63−1 specifically must NOT become ...8000 nor 422: the
    # parametrized exact == SQLITE_MAX leg proves the round-trip at
    # the storage maximum; a JSON-number PATCH of the JS-rounded
    # ...8000 would 422 — the exact-string path never does
    r = await client.patch(
        f"/shots/{shot_id}", json={"duration_ms": str(exact)})
    assert r.status_code == 200, r.text
    assert r.json()["duration_ms_dec"] == str(exact)

    # (6) the M16 projection surface carries the same exact
    # coordinate (an event-bearing shot at the unsafe duration)
    from tests.m16_seed_b import event as m16_event, post_event, \
        seed_feature_world, state
    base = await seed_feature_world(client, factory, duration=exact)
    sid6, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid6, m16_event(fid, 1, state(), state("fresh")))
    r = await client.get(f"/shots/{sid6}/intra-shot")
    assert r.status_code == 200, r.text
    assert r.json()["duration_ms_dec"] == str(exact)


@pytest.mark.asyncio
async def test_rr21_admission_contract_and_fences(client):
    """The deliberate decimal-string admission contract and the
    preserved fences: ambiguous numeric strings (sign, exponent,
    point, whitespace, leading zeros) refuse as ordinary validation;
    2^63 authoring still refuses typed (RR20); a 2^63 decimal string
    also refuses (the RR20 bound applies to the exact-integer
    admission path); and the number form still round-trips a
    JS-safe-ambiguous float."""
    r = await client.post("/projects", json={"name": "rr21-f"})
    assert r.status_code == 201, r.text
    project_id = r.json()["id"]
    r = await client.post(
        f"/projects/{project_id}/shots", json={"subject": "s"})
    assert r.status_code == 201, r.text
    shot_id = r.json()["id"]

    for bad in ("+1", "-1", "1.0", " 1", "1 ", "01", "1e3"):
        r = await client.patch(
            f"/shots/{shot_id}", json={"duration_ms": bad})
        assert r.status_code == 422, (bad, r.text)
        assert "canonical decimal" in r.text or "duration_ms" in r.text
    assert await _duration_column(client, shot_id) is None

    # the RR20 fence: above-storage authoring refused (both forms)
    r = await client.patch(
        f"/shots/{shot_id}",
        json={"duration_ms": _SQLITE_MAX + 1})
    assert r.status_code == 422, r.text
    r = await client.patch(
        f"/shots/{shot_id}",
        json={"duration_ms": str(_SQLITE_MAX + 1)})
    assert r.status_code == 422, r.text
    assert await _duration_column(client, shot_id) is None

    # the JS-rounded value of 2^53+1 is itself a DISTINCT lawful
    # integer — the exact-string path never silently lands on it
    r = await client.patch(
        f"/shots/{shot_id}", json={"duration_ms": str(_STRONG)})
    assert r.status_code == 200, r.text
    assert await _duration_column(client, shot_id) == _STRONG
    assert _STRONG != _JS_ROUNDED


# ---------------------------------------------------------------------------
# Point 7: the preserved predecessor fences
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr21_predecessor_fences_preserved(client, factory,
                                                  tmp_path):
    """The RR19 recovery adversary (2^63 in canonical TEXT with
    coherent hashes) still refuses; the RR18 lawful 2^53-duration
    capture still works; the event-coordinate SAFE_INT_MAX ceiling
    still refuses (unit level)."""
    from soloring.continuity.intra_shot_canonical import (
        SAFE_INT_MAX, require_plain_int,
    )
    from soloring.domain.canonical import (
        canonical_hash as ch, canonical_json_str as cj,
    )
    from soloring.errors import SoloRingError
    from soloring.recovery.backup import RecoveryCorruption, backup \
        as rb_backup
    from soloring.recovery.m16_verifier import (
        verify_m16_intra_shot_state,
    )
    from tests.m16_seed_b import event, post_event, seed_feature_world, \
        state
    from tests.test_m16_recovery import _settings, _stamp_alembic
    from tests.test_m16_recovery_proposals import (
        _valid_proposal_review_world,
    )
    from tests.m17cc_capture_helper import capture as _capture
    import sqlite3

    # RR19: the TEXT adversary
    world = await _valid_proposal_review_world(client, factory)
    source_rev_id = world["revision"].id
    await _stamp_alembic(client)
    root = tmp_path / "rr21-rr19"
    await rb_backup(await _settings(client), root)
    con = sqlite3.connect(root / "soloring.db")
    try:
        snap = json.loads(con.execute(
            "SELECT snapshot_json FROM shot_revisions WHERE id = ?",
            (source_rev_id,)).fetchone()[0])
        snap["intent"]["duration_ms"] = _SQLITE_MAX + 1
        new_hash = ch(snap)
        con.execute(
            "UPDATE shot_revisions SET snapshot_json = ?, "
            "snapshot_hash = ? WHERE id = ?",
            (cj(snap), new_hash, source_rev_id))
        con.execute(
            "UPDATE shot_intra_shot_event_proposals SET "
            "source_shot_revision_hash = ? WHERE "
            "source_shot_revision_id = ?",
            (new_hash, source_rev_id))
        con.commit()
    finally:
        con.close()
    with pytest.raises(RecoveryCorruption):
        verify_m16_intra_shot_state(root / "soloring.db")

    # RR18: the lawful 2^53-band capture (2^53+1 through the real
    # authoring path, an event, capture with the exact integer)
    base = await seed_feature_world(client, factory, duration=_STRONG)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid, event(fid, 1, state(), state("fresh")))
    revision, _ = await _capture(client, sid)
    snap = json.loads(revision.snapshot_json)
    assert snap["intent"]["duration_ms"] == _STRONG

    # the event-coordinate ceiling
    with pytest.raises(SoloRingError):
        require_plain_int(SAFE_INT_MAX + 1, field="time_ms")
