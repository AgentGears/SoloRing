"""M17C-C RR19 correction (frozen register RR19-M17CC-01) — the
predecessor Shot-duration primitive models the actual STORAGE domain.

RR18 correctly removed the JS-safe event-coordinate ceiling
(``SAFE_INT_MAX = 2^53-1`` — an event-grammar law) from the duration
operand, but removed EVERY upper bound. The claimed remaining bound —
SQLite INTEGER storage — is mechanically absent for durations
recovered from ``shot_revisions.snapshot_json`` (a TEXT column): a
coherently rehashed ordinary source revision could carry
``intent.duration_ms = 2^63`` past ``_verify_proposal_source``,
certifying malformed durable authority the production writer cannot
create through the INTEGER ``shots.duration_ms`` column.

The correction: ``require_shot_duration`` now enforces the ACTUAL
predecessor storage domain — a plain non-bool JSON integer, the
caller-specified minimum, and the maximum signed SQLite INTEGER
(``SQLITE_INT_MAX = 2^63-1``, a named constant — deliberately NOT
``SAFE_INT_MAX``). Lawful durations anywhere in
[2^53, 2^63-1] stay accepted; the event-coordinate ceiling stays
exactly where it belongs (time_ms / ordinal); the stale
``captured_intent_duration_ms`` docstring (which still attributed
duration validation to ``require_plain_int`` — the exact RR18
conflation) is corrected.

The battery brackets both boundaries through the real supported
paths: the positive boundary (2^63-1 with time_ms = 1) from Shot
authoring through capture, history, direct recovery, full restore,
and a source-pinned proposal; the negative boundary (2^63 in
canonical TEXT with coherent snapshot/proposal hashes — source-hash
coherence PROVEN to pass, so the duration-storage law owns the
rejection before any range arithmetic); and the separation
regressions (2^53 stays green; time/ordinal overflow stays red — a
change to ``require_plain_int``'s event ceiling cannot satisfy this
battery).
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from tests.m17cc_capture_helper import capture as _capture

_SQLITE_MAX = 9_223_372_036_854_775_807  # 2^63 - 1
_SAFE_MAX = 9_007_199_254_740_991        # 2^53 - 1


def _live_root(client):
    return client._transport.app.state.settings.data_dir


# ---------------------------------------------------------------------------
# The positive boundary: duration = 2^63−1, time_ms = 1, lawful end to end
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr19_storage_max_duration_lawful_end_to_end(
        client, factory, tmp_path):
    """The exact positive frozen state — duration_ms = 2^63-1 (the
    signed SQLite INTEGER storage maximum) with event time_ms = 1 —
    through the real supported path: Shot authoring persists it; M16
    event creation is lawful; capture stores the EXACT integer in
    outer intent.duration_ms AND the immutable companion parent;
    historical inspection succeeds; direct M16 recovery succeeds;
    full staged restore succeeds; and a source-pinned proposal with a
    safe interior time verifies."""
    from soloring.continuity.intra_shot_canonical import (
        SQLITE_INT_MAX, proposal_storage,
    )
    from soloring.recovery.backup import backup as rb_backup
    from soloring.recovery.backup import restore as rb_restore
    from soloring.recovery.m16_verifier import (
        verify_m16_intra_shot_state,
    )
    from tests.m16_seed_b import event, post_event, seed_feature_world, \
        state
    from tests.test_m16_recovery import _settings, _stamp_alembic
    from tests.test_m17c_sr26_regressions import _backup_m17c

    assert SQLITE_INT_MAX == _SQLITE_MAX

    # Shot authoring persists the storage-maximum duration
    base = await seed_feature_world(client, factory,
                                    duration=_SQLITE_MAX)
    sid, fid = base["shot_id"], base["feature_id"]

    # M16 event creation at safe time_ms = 1 is lawful
    await post_event(
        client, sid, event(fid, 1, state(), state("fresh")))

    # capture stores the EXACT integer in both authority surfaces
    revision, _ = await _capture(client, sid)
    snap = json.loads(revision.snapshot_json)
    assert snap["intent"]["duration_ms"] == _SQLITE_MAX
    con = sqlite3.connect(_live_root(client) / "soloring.db")
    try:
        companion = con.execute(
            "SELECT duration_ms FROM "
            "shot_revision_intra_shot_specs WHERE shot_revision_id = ?",
            (revision.id,)).fetchone()[0]
    finally:
        con.close()
    assert companion == _SQLITE_MAX
    assert companion == snap["intent"]["duration_ms"]

    # historical inspection succeeds
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 200, r.text

    # direct M16 recovery succeeds
    await _stamp_alembic(client)
    direct_root = tmp_path / "rr19-direct"
    await rb_backup(await _settings(client), direct_root)
    verify_m16_intra_shot_state(direct_root / "soloring.db")

    # a source-pinned proposal with a safe interior time verifies
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
            "'00000000-0000-4000-8000-0000000000f1', ?, 'imported', "
            "?, ?, NULL, NULL, 'human', NULL, NULL, NULL, ?, ?, "
            "strftime('%Y-%m-%dT%H:%M:%mfZ','now'))",
            (sid, revision.id, revision.snapshot_hash, pj, ph))
        con.commit()
    finally:
        con.close()
    verify_m16_intra_shot_state(direct_root / "soloring.db")

    # the full staged restore succeeds (successor chain, head 0023)
    root = await _backup_m17c(client, tmp_path, "rr19-max")
    dest = tmp_path / "rr19-restored"
    await rb_restore(root, dest)
    assert (dest / "soloring.db").is_file()


# ---------------------------------------------------------------------------
# The negative boundary: 2^63 in canonical TEXT is refused typed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr19_above_storage_max_refused_by_both_surfaces(
        client, factory, tmp_path):
    """The exact negative frozen state: a lawful ordinary source
    ShotRevision suitable for the proposal path, with
    intent.duration_ms = 2^63 injected into canonical snapshot_json
    TEXT, snapshot_hash recomputed, and the pinning proposal's
    source_shot_revision_hash coherently updated (source-hash
    coherence PROVEN to pass — the revision's hash matches the
    proposal pin exactly), unrelated authority unchanged. Direct M16
    recovery and full staged restore refuse through typed corruption
    BEFORE range arithmetic, with the duration-STORAGE law owning the
    rejection."""
    from soloring.domain.canonical import (
        canonical_hash as ch, canonical_json_str as cj,
    )
    from soloring.recovery.backup import RecoveryCorruption, backup \
        as rb_backup
    from soloring.recovery.backup import restore as rb_restore
    from soloring.recovery.m16_verifier import (
        verify_m16_intra_shot_state,
    )
    from tests.test_m16_recovery import _settings, _stamp_alembic
    from tests.test_m16_recovery_proposals import (
        _valid_proposal_review_world,
    )
    from tests.test_m17c_sr26_regressions import _rehash_manifest

    world = await _valid_proposal_review_world(client, factory)
    source_rev_id = world["revision"].id
    await _stamp_alembic(client)

    root = tmp_path / "rr19-above-max"
    await rb_backup(await _settings(client), root)

    con = sqlite3.connect(root / "soloring.db")
    try:
        snap = json.loads(con.execute(
            "SELECT snapshot_json FROM shot_revisions WHERE id = ?",
            (source_rev_id,)).fetchone()[0])
        snap["intent"]["duration_ms"] = _SQLITE_MAX + 1  # 2^63
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
        # source-hash coherence PASSES by construction: the pin equals
        # the recomputed revision hash exactly
        pinned, actual = con.execute(
            "SELECT p.source_shot_revision_hash, r.snapshot_hash FROM "
            "shot_intra_shot_event_proposals p JOIN shot_revisions r "
            "ON r.id = p.source_shot_revision_id WHERE "
            "p.source_shot_revision_id = ?",
            (source_rev_id,)).fetchone()
    finally:
        con.close()
    assert pinned == actual == new_hash

    # direct M16 recovery: typed corruption BEFORE range arithmetic,
    # owned by the duration-storage law
    with pytest.raises(RecoveryCorruption) as direct:
        verify_m16_intra_shot_state(root / "soloring.db")
    message = str(direct.value)
    assert "source revision intent violates the frozen M16 " \
        "representation" in message, message
    assert "above the signed SQLite INTEGER storage domain" in message, \
        message

    # the full staged restore refuses through the same typed law (the
    # manifest is rehashed so the restore reaches semantic verification)
    _rehash_manifest(root)
    dest = tmp_path / "rr19-refused"
    with pytest.raises(RecoveryCorruption) as restored:
        await rb_restore(root, dest)
    assert "above the signed SQLite INTEGER storage domain" \
        in str(restored.value), str(restored.value)
    assert not dest.exists()


# ---------------------------------------------------------------------------
# The separation regressions: 2^53 stays green; event overflow stays red
# ---------------------------------------------------------------------------

def test_rr19_separation_regressions():
    """A fix that changes or removes require_plain_int's event ceiling
    cannot satisfy these: the 2^53 duration (RR18's lawful case) and
    the full [2^53, 2^63-1] band stay lawful while time_ms and
    ordinal above SAFE_INT_MAX stay refused — the two domains remain
    mechanically distinct."""
    from soloring.continuity.intra_shot_canonical import (
        SAFE_INT_MAX, SQLITE_INT_MAX, captured_intent_duration_ms,
        require_interior_time, require_plain_int,
        require_shot_duration,
    )
    from soloring.errors import SoloRingError

    # the lawful band, including both frozen boundary points
    for lawful in (SAFE_INT_MAX + 1, 2**60, SQLITE_INT_MAX):
        assert require_shot_duration(
            lawful, field="x", minimum=1) == lawful
        assert captured_intent_duration_ms(
            {"intent": {"duration_ms": lawful}}) == lawful
        assert require_interior_time(1, lawful) == (1, lawful)

    # the event-coordinate ceiling stays exactly where it belongs
    with pytest.raises(SoloRingError):
        require_plain_int(SAFE_INT_MAX + 1, field="time_ms")
    with pytest.raises(SoloRingError):
        require_plain_int(SAFE_INT_MAX + 1, field="ordinal")
    with pytest.raises(SoloRingError):
        require_interior_time(SAFE_INT_MAX + 1, SQLITE_INT_MAX)

    # the malformed shapes stay refused (RR17 totality intact)
    for bad in (True, 5000.0, "5000", -1, SQLITE_INT_MAX + 1):
        with pytest.raises(SoloRingError):
            require_shot_duration(bad, field="x", minimum=1)
