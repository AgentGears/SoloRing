"""M17C-C RR17 correction (frozen register RR17-M17CC-01) — the
nested M16 captured-intent semantic boundary is total.

After RR16 made the OUTER snapshot parse total, M16's first semantic
reads still assumed the nested ``intent`` member was a dictionary:
``snapshot.get("intent", {}).get("duration_ms")`` raised raw
``AttributeError`` on a canonical, hash-authenticated snapshot
carrying ``intent: []`` — reachable through BOTH historical
inspection (which calls the shared history verifier before its final
outer bytes/hash comparison) and full restore (where M16's
enumeration reaches the same nested access before M17C-C's envelope
authentication). A second manifestation ran the raw
``1 <= t < duration`` boundary over uncertified data in
``_verify_proposal_source``, so a coherently persisted non-integer
``duration_ms`` raised raw ``TypeError`` in the comparison.

The correction: ONE shared predecessor helper —
``intra_shot_canonical.captured_intent_duration_ms`` — certifies the
nested facts BEFORE any consumer performs ``.get()``, equality, or
range arithmetic (``intent`` a JSON object; ``duration_ms`` null or
a plain JSON integer through the frozen ``require_plain_int``
discipline), consumed by BOTH ``intra_shot_history`` (failing the
typed historical invariant before the duration-equality law) and
``m16_verifier._verify_proposal_source`` (typed recovery corruption,
the interior-time law now through the frozen ``require_interior_time``
instead of a raw comparison; null captured duration preserved).
``load_outer_snapshot`` stays scoped exactly as RR16 froze it, and
the m16 enumeration now surfaces the shared history module's typed
laws as the recovery corruption contract on the restore path.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from tests.m17cc_capture_helper import capture as _capture


def _live_root(client):
    return client._transport.app.state.settings.data_dir


async def _stage_schema8_wrapping_intrashot(client, factory):
    """A lawful schema-8 ShotRevision wrapping GENUINE schema-7
    intra-shot history: one event-bearing capture (schema 7 with
    intra_shot), then a generic performance mapping on the SAME shot
    and a second capture (schema 8 wrapping both)."""
    from tests.m16_seed_b import event, post_event, seed_feature_world, \
        state
    from tests.test_m17c_shot_mapping import _seg_body

    base = await seed_feature_world(client, factory)
    sid, fid, eid = (base["shot_id"], base["feature_id"],
                     base["entity_id"])
    await post_event(
        client, sid, event(fid, 1000, state(), state("fresh")))
    schema7_revision, _ = await _capture(client, sid)
    snap7 = json.loads(schema7_revision.snapshot_json)
    assert snap7["schema_version"] == 7
    assert "intra_shot" in snap7

    from tests.m17b_seed import (
        HEAD_YAW, candidate_body, channel as m17b_channel,
        kf as m17b_kf,
    )
    candidate = (await client.post(
        f"/creative-entities/{eid}/performance-candidates",
        json=candidate_body(
            [m17b_channel(HEAD_YAW, [m17b_kf(0, 1, 0)])]),
    )).json()
    pr = (await client.post(
        f"/performance-candidates/{candidate['id']}/adopt",
        json={"adopted_by": "s17"})).json()
    r = await client.put(
        f"/shots/{sid}/performance-segments/0",
        json=_seg_body(pr["id"], 0, 1000, 0))
    assert r.status_code == 200, r.text
    schema8_revision, _ = await _capture(client, sid)
    snap8 = json.loads(schema8_revision.snapshot_json)
    assert snap8["schema_version"] == 8
    assert "intra_shot" in snap8 and "performance" in snap8
    return base, schema7_revision, schema8_revision


def _rewrite_snapshot(db_path, revision_id, mutate):
    """Apply ``mutate(snap)`` to the revision's decoded snapshot and
    persist the CANONICAL bytes + recomputed hash (outer
    self-authentication passes by construction; only the targeted
    semantic law can refuse). Returns the new hash."""
    from soloring.domain.canonical import (
        canonical_hash as ch, canonical_json_str as cj,
    )
    con = sqlite3.connect(db_path)
    try:
        snap = json.loads(con.execute(
            "SELECT snapshot_json FROM shot_revisions WHERE id = ?",
            (revision_id,)).fetchone()[0])
        mutate(snap)
        new_hash = ch(snap)
        con.execute(
            "UPDATE shot_revisions SET snapshot_json = ?, "
            "snapshot_hash = ? WHERE id = ?",
            (cj(snap), new_hash, revision_id))
        con.commit()
        return new_hash
    finally:
        con.close()


# ---------------------------------------------------------------------------
# The history / full-restore adversary
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr17_history_intent_list_refused_both_surfaces(
        client, factory, tmp_path):
    """The frozen history adversary: a lawful schema-8 capture
    wrapping genuine schema-7 intra-shot history, with ONLY the outer
    ``intent`` changed to ``[]`` and the canonical snapshot bytes/hash
    recomputed (outer self-authentication passes by construction —
    schema discriminator, intra_shot, Performance block, and every
    companion row unchanged). Historical inspection refuses through
    the typed historical invariant — never AttributeError — and the
    full staged restore refuses through RecoveryCorruption — never
    AttributeError."""
    from soloring.recovery import restore as rb_restore
    from soloring.recovery.backup import RecoveryCorruption
    from tests.test_m17c_sr26_regressions import (
        _backup_m17c, _rehash_manifest,
    )

    base, schema7_revision, schema8_revision = (
        await _stage_schema8_wrapping_intrashot(client, factory))

    # the lawful control: historical inspection green on the wrapped
    # intra-shot history through the schema-8 continuity read
    r = await client.get(
        f"/shot-revisions/{schema8_revision.id}/continuity")
    assert r.status_code == 200, r.text

    # the coherent tamper on the staged copy (for the restore leg)
    root = await _backup_m17c(client, tmp_path, "rr17-intent-list")
    _rewrite_snapshot(
        root / "soloring.db", schema8_revision.id,
        lambda snap: snap.__setitem__("intent", []))

    # historical inspection on the LIVE database with the same
    # coherent rewrite: the typed historical invariant, never
    # AttributeError (the coherent outer hash does not rescue it)
    _rewrite_snapshot(
        _live_root(client) / "soloring.db", schema8_revision.id,
        lambda snap: snap.__setitem__("intent", []))
    r = await client.get(
        f"/shot-revisions/{schema8_revision.id}/continuity")
    assert r.status_code == 500, r.text
    message = r.json()["message"]
    assert "captured intent violates the frozen M16 representation" \
        in message, message

    # the full staged restore: typed RecoveryCorruption, never
    # AttributeError (the manifest is rehashed so the restore reaches
    # semantic verification rather than failing artifact
    # authentication first)
    _rehash_manifest(root)
    dest = tmp_path / "rr17-refused-intent-list"
    with pytest.raises(RecoveryCorruption) as rec:
        await rb_restore(root, dest)
    assert "captured intent violates the frozen M16 representation" \
        in str(rec.value), str(rec.value)
    assert not dest.exists()


# ---------------------------------------------------------------------------
# The proposal-duration adversary (+ cross-type regressions)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("bad_duration", ["5000", True, 5000.0])
async def test_rr17_proposal_duration_refused_typed(
        client, factory, tmp_path, bad_duration):
    """The frozen proposal adversary: a lawful M16 proposal pinned to
    a lawful ShotRevision, with ``intent`` kept an object but
    ``duration_ms`` replaced by a canonical non-integer (the string is
    the decisive frozen case; True and 5000.0 are the cross-type
    regressions — Python numeric equality must not weaken the
    actual-integer requirement). The ShotRevision canonical bytes/hash
    are recomputed AND every pinning proposal's relational
    source_shot_revision_hash is coherently updated, so source-hash
    coherence passes and the refusal is the duration-representation
    law itself — typed recovery corruption BEFORE any raw comparison,
    never TypeError."""
    from soloring.recovery.backup import RecoveryCorruption, backup \
        as rb_backup
    from soloring.recovery.m16_verifier import (
        verify_m16_intra_shot_state,
    )
    from tests.test_m16_recovery import _settings
    from tests.test_m16_recovery_proposals import (
        _valid_proposal_review_world,
    )

    world = await _valid_proposal_review_world(client, factory)
    source_rev_id = world["revision"].id

    root = tmp_path / f"rr17-proposal-{type(bad_duration).__name__}"
    await rb_backup(await _settings(client), root)

    new_hash = _rewrite_snapshot(
        root / "soloring.db", source_rev_id,
        lambda snap: snap["intent"].__setitem__(
            "duration_ms", bad_duration))

    con = sqlite3.connect(root / "soloring.db")
    try:
        pinned = con.execute(
            "SELECT COUNT(*) FROM shot_intra_shot_event_proposals "
            "WHERE source_shot_revision_id = ?",
            (source_rev_id,)).fetchone()[0]
        assert pinned >= 1
        con.execute(
            "UPDATE shot_intra_shot_event_proposals SET "
            "source_shot_revision_hash = ? WHERE "
            "source_shot_revision_id = ?",
            (new_hash, source_rev_id))
        con.commit()
    finally:
        con.close()

    # full M16 recovery: typed recovery corruption BEFORE any raw
    # comparison — the RecoveryCorruption class itself is the
    # never-TypeError proof
    with pytest.raises(RecoveryCorruption) as rec:
        verify_m16_intra_shot_state(root / "soloring.db")
    assert "source revision intent violates the frozen M16 " \
        "representation" in str(rec.value), str(rec.value)
