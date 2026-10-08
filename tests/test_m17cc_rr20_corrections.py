"""M17C-C RR20 correction (frozen register RR20-M17CC-01) — public
Shot-duration representability at the persistence boundary.

RR19 made historical/recovery duration authority obey the physical
signed-SQLite-INTEGER storage domain. RR20 is the converse mismatch:
the public authoring boundary (`ShotCreate`/`ShotPatch`
``duration_ms: int|None Field(ge=0)`` — no upper bound) accepted
``2^63`` at request validation and then escaped as a raw SQLite
binding ``OverflowError`` (the create path catching only
``IntegrityError``; the PATCH fence checking only the M16-event
relationship, which any positive value satisfies; no API
``OverflowError`` handler).

The correction: the ONE shared signed-SQLite-INTEGER maximum lives
in the LOWEST domain layer — ``soloring.domain.storage`` — consumed
by BOTH the public Shot API schemas (``le=SQLITE_INT_MAX`` — the
stable typed validation envelope refuses out-of-range durations
BEFORE any bind) and the M16 ``require_shot_duration`` primitive
(which re-exports the same constant; the API schema does NOT depend
upward on the M16 continuity package). No migration, no DB CHECK, no
event-grammar change: ``None``/``0``/positive stay lawful where they
already were, ``2^53 … 2^63-1`` inclusive remain accepted, and the
M16 event-coordinate ``SAFE_INT_MAX`` ceiling is untouched.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

_SQLITE_MAX = 9_223_372_036_854_775_807  # 2^63 - 1
_SAFE_MAX = 9_007_199_254_740_991        # 2^53 - 1


def _live_root(client):
    return client._transport.app.state.settings.data_dir


async def _shot_count(client, project_id):
    from sqlalchemy import text
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        return (await conn.execute(text(
            "SELECT COUNT(*) FROM shots WHERE project_id = :p"),
            {"p": project_id})).scalar_one()


async def _shot_duration(client, shot_id):
    from sqlalchemy import text
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        return (await conn.execute(text(
            "SELECT duration_ms FROM shots WHERE id = :s"),
            {"s": shot_id})).scalar_one()


# ---------------------------------------------------------------------------
# Primitive/schema regressions — the shared bound and its two consumers
# ---------------------------------------------------------------------------

def test_rr20_shared_bound_primitive_and_schema_regressions():
    """The ONE shared signed-SQLite maximum (the low domain layer)
    feeds BOTH consumers with no duplicated literal; the schemas
    accept the signed maximum and refuse signed-max+1 through the
    stable typed validation envelope; the M16 duration primitive
    agrees; bool is never admitted as duration authority; and no
    accidental SAFE_INT_MAX cap exists on Shot duration (a broad
    change to require_plain_int cannot satisfy this)."""
    import pydantic

    from soloring.api.schemas.shots import ShotCreate, ShotPatch
    from soloring.continuity.intra_shot_canonical import (
        SAFE_INT_MAX, require_plain_int, require_shot_duration,
    )
    from soloring.domain.storage import SQLITE_INT_MAX
    from soloring.errors import SoloRingError

    assert SQLITE_INT_MAX == _SQLITE_MAX > SAFE_INT_MAX

    for schema, base in ((ShotCreate, {"subject": "x"}),
                         (ShotPatch, {})):
        lawful = schema(**base, duration_ms=_SQLITE_MAX)
        assert lawful.duration_ms == _SQLITE_MAX
        assert schema(**base, duration_ms=_SAFE_MAX + 1).duration_ms \
            == _SAFE_MAX + 1
        for bad in (_SQLITE_MAX + 1, 2**64):
            with pytest.raises(pydantic.ValidationError):
                schema(**base, duration_ms=bad)

    # the primitive agrees with the schema bound, bool never admitted
    assert require_shot_duration(
        _SQLITE_MAX, field="x", minimum=1) == _SQLITE_MAX
    with pytest.raises(SoloRingError):
        require_shot_duration(_SQLITE_MAX + 1, field="x", minimum=1)
    with pytest.raises(SoloRingError):
        require_shot_duration(True, field="x", minimum=1)

    # the event-coordinate ceiling stays — a require_plain_int change
    # cannot satisfy this battery
    with pytest.raises(SoloRingError):
        require_plain_int(_SAFE_MAX + 1, field="time_ms")


# ---------------------------------------------------------------------------
# Points 1+2: the POST boundaries
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr20_post_boundaries(client, factory):
    """(1) POST with duration_ms = 2^63-1 succeeds with the EXACT
    integer persisted and read back; (2) POST with 2^63 returns the
    stable typed validation response, creates ZERO Shot rows, and
    never surfaces OverflowError."""
    r = await client.post("/projects", json={"name": "rr20-post"})
    assert r.status_code == 201, r.text
    project_id = r.json()["id"]
    before = await _shot_count(client, project_id)

    # (1) the positive boundary — exact persisted/read-back integer
    r = await client.post(
        f"/projects/{project_id}/shots",
        json={"subject": "max", "duration_ms": _SQLITE_MAX})
    assert r.status_code == 201, r.text
    shot_id = r.json()["id"]
    assert r.json()["duration_ms"] == _SQLITE_MAX
    assert await _shot_duration(client, shot_id) == _SQLITE_MAX

    # (2) the negative boundary — typed validation, zero rows, never
    # a raw OverflowError (422 is FastAPI's RequestValidationError
    # envelope for the schema bound)
    r = await client.post(
        f"/projects/{project_id}/shots",
        json={"subject": "over", "duration_ms": _SQLITE_MAX + 1})
    assert r.status_code == 422, r.text
    assert "OverflowError" not in r.text
    assert "duration_ms" in r.text
    assert await _shot_count(client, project_id) == before + 1


# ---------------------------------------------------------------------------
# Points 3+4: the PATCH boundaries
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr20_patch_boundaries(client):
    """(3) PATCH to 2^63-1 succeeds with the exact persisted value;
    (4) PATCH to 2^63 typed-refuses and leaves the previous duration
    unchanged after the request."""
    r = await client.post("/projects", json={"name": "rr20-patch"})
    assert r.status_code == 201, r.text
    project_id = r.json()["id"]
    r = await client.post(
        f"/projects/{project_id}/shots",
        json={"subject": "s", "duration_ms": 5000})
    assert r.status_code == 201, r.text
    shot_id = r.json()["id"]

    # (3) the positive boundary
    r = await client.patch(
        f"/shots/{shot_id}", json={"duration_ms": _SQLITE_MAX})
    assert r.status_code == 200, r.text
    assert r.json()["duration_ms"] == _SQLITE_MAX
    assert await _shot_duration(client, shot_id) == _SQLITE_MAX

    # (4) the negative boundary — typed, prior value byte-unchanged
    r = await client.patch(
        f"/shots/{shot_id}", json={"duration_ms": _SQLITE_MAX + 1})
    assert r.status_code == 422, r.text
    assert "OverflowError" not in r.text
    assert await _shot_duration(client, shot_id) == _SQLITE_MAX


# ---------------------------------------------------------------------------
# Point 5: PATCH refusal with ACTIVE M16 state — deterministic
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr20_patch_refusal_with_active_m16_event(
        client, factory):
    """(5) With an active lawful intra-Shot event staged, PATCH to
    2^63 refuses through the storage/admission boundary WITHOUT SQL
    mutation — the Shot duration AND the event rows remain unchanged,
    proving the correction is not dependent on event-set comparison
    ordering (the schema gate fires before any fence or SQL)."""
    from tests.m16_seed_b import event, post_event, seed_feature_world, \
        state

    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid, event(fid, 1000, state(), state("fresh")))
    assert await _shot_duration(client, sid) == 5000

    from sqlalchemy import text
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        events_before = (await conn.execute(text(
            "SELECT COUNT(*), COALESCE(MAX(time_ms), 0) FROM "
            "shot_intra_shot_events WHERE shot_id = :s AND "
            "deleted_at IS NULL"), {"s": sid})).one()

    r = await client.patch(
        f"/shots/{sid}", json={"duration_ms": _SQLITE_MAX + 1})
    assert r.status_code == 422, r.text
    assert "OverflowError" not in r.text
    assert await _shot_duration(client, sid) == 5000

    async with engine.connect() as conn:
        events_after = (await conn.execute(text(
            "SELECT COUNT(*), COALESCE(MAX(time_ms), 0) FROM "
            "shot_intra_shot_events WHERE shot_id = :s AND "
            "deleted_at IS NULL"), {"s": sid})).one()
    assert events_after == events_before


# ---------------------------------------------------------------------------
# Point 6: RR19 preservation — the canonical-TEXT recovery adversary
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr20_rr19_text_adversary_still_refused(client, factory,
                                                       tmp_path):
    """(6) The RR19 frozen recovery adversary — intent.duration_ms =
    2^63 injected into canonical snapshot_json TEXT with the snapshot
    hash and the pinning proposal's source hash coherently moved —
    stays typed-refused by direct M16 recovery and the full staged
    restore through the captured-duration storage law."""
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

    root = tmp_path / "rr20-rr19-text"
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

    with pytest.raises(RecoveryCorruption) as direct:
        verify_m16_intra_shot_state(root / "soloring.db")
    assert "above the signed SQLite INTEGER storage domain" \
        in str(direct.value), str(direct.value)

    _rehash_manifest(root)
    dest = tmp_path / "rr20-refused-restore"
    with pytest.raises(RecoveryCorruption) as restored:
        await rb_restore(root, dest)
    assert "above the signed SQLite INTEGER storage domain" \
        in str(restored.value), str(restored.value)
    assert not dest.exists()


# ---------------------------------------------------------------------------
# Point 7: RR18 separation preservation — 2^53 lawful end to end
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr20_rr18_separation_preserved(client, factory):
    """(7) The RR18 lawful frozen state — duration_ms = 2^53 (above
    the event grammar's SAFE_INT_MAX, inside the storage domain)
    with a safe event time — remains green through authoring, event
    creation, and capture with the exact persisted integer."""
    from tests.m16_seed_b import event, post_event, seed_feature_world, \
        state

    base = await seed_feature_world(client, factory,
                                    duration=_SAFE_MAX + 1)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid, event(fid, 1, state(), state("fresh")))
    assert await _shot_duration(client, sid) == _SAFE_MAX + 1

    from tests.m17cc_capture_helper import capture as _capture
    revision, _ = await _capture(client, sid)
    snap = json.loads(revision.snapshot_json)
    assert snap["intent"]["duration_ms"] == _SAFE_MAX + 1
