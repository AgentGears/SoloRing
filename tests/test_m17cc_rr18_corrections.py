"""M17C-C RR18 correction (frozen register RR18-M17CC-01) — the
predecessor Shot-duration domain is separated from the JS-safe M16
event-coordinate domain.

RR17's shared captured-intent helper validated the captured Shot
``duration_ms`` through ``require_plain_int``, whose 2^53-1 ceiling
is an EVENT-grammar law (time_ms / ordinal / positions) — not the
Shot-duration law. The published predecessor domain (ShotCreate /
ShotPatch ``ge=0``; the ``shots.duration_ms`` CHECK ``NULL OR >= 0``;
the M16 writer fence ``type is int`` + ``> 0`` + ``time < duration``;
the intra-shot companion ``> 0``) has NO such ceiling, so SoloRing
could author, capture, and durably persist a lawful large-duration
ShotRevision that RR17's history/recovery path then falsely rejected.

The correction: ONE explicit duration-domain primitive —
``intra_shot_canonical.require_shot_duration`` (a plain JSON integer;
bool/float/string/negative rejected; NO JS-safe ceiling; minimum 0
for the published domain, 1 where event semantics require a genuine
duration) — used by ``captured_intent_duration_ms()`` and for the
DURATION operand of ``require_interior_time()`` only (the TIME
operand keeps ``require_plain_int`` with the JS-safe ceiling). The
event grammar, the public Shot ceiling, and the interior rule are
unchanged.

The battery proves the exact frozen state — duration_ms =
SAFE_INT_MAX + 1 with event time_ms = 1 — through all eight frozen
points, with the negative controls making a broad relaxation of
``require_plain_int`` unable to satisfy it: the time/ordinal overflow
negatives still refuse while the large duration passes.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from tests.m17cc_capture_helper import capture as _capture

_BIG = 9_007_199_254_740_991 + 1  # SAFE_INT_MAX + 1 = 2^53


def _live_root(client):
    return client._transport.app.state.settings.data_dir


# ---------------------------------------------------------------------------
# The eight frozen points at duration = SAFE_INT_MAX + 1, time = 1
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr18_large_duration_lawful_end_to_end(
        client, factory, tmp_path):
    """The exact frozen positive state: (1) Shot create AND duration
    PATCH accept the lawful positive duration; (2) M16 event creation
    at safe time_ms=1 succeeds; (3) capture succeeds and the EXACT
    large integer appears identically in outer intent.duration_ms and
    the immutable intra-shot companion parent; (4) historical
    inspection succeeds; (5) direct M16 recovery succeeds; (6) full
    staged backup/restore succeeds; (7) a proposal pinned to that
    revision with a safe interior event time validates; (8) the
    time_ms and ordinal overflow negatives still refuse."""
    from soloring.continuity.intra_shot_canonical import proposal_storage
    from soloring.recovery.backup import RecoveryCorruption, backup \
        as rb_backup
    from soloring.recovery.backup import restore as rb_restore
    from soloring.recovery.m16_verifier import (
        verify_m16_intra_shot_state,
    )
    from tests.m16_seed_b import event, post_event, seed_feature_world, \
        state
    from tests.test_m16_recovery import _settings, _stamp_alembic
    from tests.test_m17c_sr26_regressions import _backup_m17c

    # (1a) Shot creation accepts the large lawful duration
    base = await seed_feature_world(client, factory, duration=_BIG)
    sid, fid = base["shot_id"], base["feature_id"]

    # (1b) duration PATCH accepts it too (drop to a normal duration
    # and PATCH back up to the exact frozen value)
    r = await client.patch(f"/shots/{sid}", json={"duration_ms": 5000})
    assert r.status_code == 200, r.text
    r = await client.patch(f"/shots/{sid}", json={"duration_ms": _BIG})
    assert r.status_code == 200, r.text

    # (2) a safe M16 event at time_ms = 1 is lawful under the large
    # duration (1 < duration)
    await post_event(
        client, sid, event(fid, 1, state(), state("fresh")))

    # (3) capture succeeds and persists the EXACT integer in both the
    # outer intent and the immutable companion parent
    revision, _ = await _capture(client, sid)
    snap = json.loads(revision.snapshot_json)
    assert snap["schema_version"] == 7
    assert snap["intent"]["duration_ms"] == _BIG
    con = sqlite3.connect(_live_root(client) / "soloring.db")
    try:
        companion = con.execute(
            "SELECT duration_ms FROM "
            "shot_revision_intra_shot_specs WHERE shot_revision_id = ?",
            (revision.id,)).fetchone()[0]
    finally:
        con.close()
    assert companion == _BIG
    assert companion == snap["intent"]["duration_ms"]

    # (4) historical inspection succeeds on the lawful large duration
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 200, r.text

    # (5) direct M16 recovery succeeds
    await _stamp_alembic(client)
    direct_root = tmp_path / "rr18-direct"
    await rb_backup(await _settings(client), direct_root)
    verify_m16_intra_shot_state(direct_root / "soloring.db")

    # (7) a proposal pinned to that revision with a safe interior
    # event time validates (the proposal path's duration operand is
    # the same large captured duration)
    _, pj, ph = proposal_storage(
        candidate_event={
            "time_ms": 1, "ordinal": 0,
            "target": {"kind": "entity_feature", "id": fid},
            "before": state(), "after": state("fresh")},
        persistence_suggestion="persist")
    con = sqlite3.connect(direct_root / "soloring.db")
    try:
        con.execute(
            "INSERT INTO shot_intra_shot_event_proposals "
            "(id, shot_id, source_kind, source_shot_revision_id, "
            "source_shot_revision_hash, source_generation_id, "
            "source_take_id, proposer_kind, analyzer_id, "
            "analyzer_version, analyzer_parameters_hash, "
            "proposal_json, proposal_hash, created_at) VALUES ("
            "'00000000-0000-4000-8000-0000000000e1', ?, 'imported', "
            "?, ?, NULL, NULL, 'human', NULL, NULL, NULL, ?, ?, "
            "strftime('%Y-%m-%dT%H:%M:%mfZ','now'))",
            (sid, revision.id, revision.snapshot_hash, pj, ph))
        con.commit()
    finally:
        con.close()
    verify_m16_intra_shot_state(direct_root / "soloring.db")

    # (6) the full staged backup/restore succeeds (successor chain,
    # head 0023)
    root = await _backup_m17c(client, tmp_path, "rr18-large")
    dest = tmp_path / "rr18-restored"
    await rb_restore(root, dest)
    assert (dest / "soloring.db").is_file()

    # (8) the negative controls: the EVENT-coordinate ceiling and the
    # ordinal ceiling still refuse (a broad relaxation of
    # require_plain_int cannot satisfy this battery)
    from tests.test_m16_grammar import _event
    from soloring.continuity.intra_shot_canonical import (
        SAFE_INT_MAX, require_plain_int,
    )
    from soloring.errors import SoloRingError
    with pytest.raises(SoloRingError):
        require_plain_int(SAFE_INT_MAX + 1, field="ordinal")
    with pytest.raises(SoloRingError):
        _event(time_ms=SAFE_INT_MAX + 1)
    with pytest.raises(SoloRingError):
        _event(ordinal=SAFE_INT_MAX + 1)


# ---------------------------------------------------------------------------
# The RR17 corruption shapes remain typed refusals
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("bad_duration", ["5000", True, 5000.0])
async def test_rr18_rr17_shapes_still_refuse(client, factory, tmp_path,
                                              bad_duration):
    """The RR17 totality is intact: bool/float/string captured
    durations still terminate as typed recovery corruption (the new
    primitive only removed the ceiling — the type and negativity
    discipline is unchanged)."""
    from soloring.recovery.backup import RecoveryCorruption, backup \
        as rb_backup
    from soloring.recovery.m16_verifier import (
        verify_m16_intra_shot_state,
    )
    from tests.m16_seed_b import event, post_event, seed_feature_world, \
        state
    from tests.test_m16_recovery import _settings, _stamp_alembic

    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid, event(fid, 1000, state(), state("fresh")))
    revision, _ = await _capture(client, sid)
    await _stamp_alembic(client)

    root = tmp_path / f"rr18-rr17-{type(bad_duration).__name__}"
    await rb_backup(await _settings(client), root)

    from soloring.domain.canonical import (
        canonical_hash as ch, canonical_json_str as cj,
    )
    con = sqlite3.connect(root / "soloring.db")
    try:
        snap = json.loads(con.execute(
            "SELECT snapshot_json FROM shot_revisions WHERE id = ?",
            (revision.id,)).fetchone()[0])
        snap["intent"]["duration_ms"] = bad_duration
        con.execute(
            "UPDATE shot_revisions SET snapshot_json = ?, "
            "snapshot_hash = ? WHERE id = ?",
            (cj(snap), ch(snap), revision.id))
        con.execute(
            "UPDATE shot_intra_shot_event_proposals SET "
            "source_shot_revision_hash = ? WHERE "
            "source_shot_revision_id = ?",
            (ch(snap), revision.id))
        con.commit()
    finally:
        con.close()

    with pytest.raises(RecoveryCorruption) as rec:
        verify_m16_intra_shot_state(root / "soloring.db")
    assert "captured intent violates the frozen M16 " \
        "representation" in str(rec.value), str(rec.value)
