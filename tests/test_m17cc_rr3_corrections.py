"""M17C-C RR3 correction (frozen register RR3-M17CC-01) — the exact
canonical serialized form of the stored vocal mapping.

The frozen law (§11.4, enforcement of an EXISTING rule): a PRESENT
paired ShotVocalSegmentMapping's stored mapping_json must be EXACTLY
the canonical serialized form over the row's own fields —
`mapping_json == canonical_json_str(canonical)` — with the independent
digest law `mapping_hash == canonical_hash(canonical)`. Decoding alone
proves semantic equality, not canonical serialization: a pretty-printed,
reordered, or duplicate-key form that decodes to the canonical document
is not a serialization the canonical writer could ever emit, and both
the live PF-02/capture path and the M17A recovery verifier (sharing the
ONE law) must refuse it.

The frozen proofs:
1. the SEMANTIC-FORGERY case (mapping_json replaced by a different
   document) — retained from RR2, a distinct failure mode;
2. the BYTE-CANONICALITY case: start from the lawful mapping_json,
   deserialize it, write a semantically identical but NONCANONICAL
   serialization (pretty-printed + reordered), leaving every semantic
   column and mapping_hash untouched → readiness 500, capture fails
   before builder/persistence, counts unchanged, M17A recovery
   independently refuses the same stored row;
3. the clean canonical control: READY, schema-8 capture, §12 valid,
   recovery valid;
4. the supported paired-vocal DELETE: still blocked data, not
   corruption (RR-02 exact).
"""

from __future__ import annotations

import json
import sqlite3

import pytest

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


def _counts(client):
    async def _one(stmt, params=None):
        return (await _row(client, stmt, params))["n"]

    class _C:
        async def snapshot(self, shot_id):
            self.revisions = await _one(
                "SELECT COUNT(*) AS n FROM shot_revisions WHERE "
                "shot_id = :s", {"s": shot_id})
            self.parents = await _one(
                f"SELECT COUNT(*) AS n FROM {_PARENTS}")
            self.children = await _one(
                f"SELECT COUNT(*) AS n FROM {_CHILDREN}")
            return self

        def __eq__(self, other):
            return (self.revisions == other.revisions
                    and self.parents == other.parents
                    and self.children == other.children)
    return _C()


async def _attempt_capture(client, shot_id):
    from soloring.domain.revisions import capture_revision_with_visual
    from tests.conftest import make_tracked_maker
    factory = make_tracked_maker(_engine(client))
    async with factory() as session:
        return await capture_revision_with_visual(
            session, shot_id,
            settings=client._transport.app.state.settings)


def _pretty_noncanonical(doc: dict) -> str:
    """A semantically identical but NONCANONICAL serialization: keys
    in INSERTION order (the decoded doc preserves file order), pretty
    indentation, and a spacing style the canonical writer never
    emits."""
    reordered = dict(reversed(list(doc.items())))
    return json.dumps(reordered, indent=2)


@pytest.mark.asyncio
async def test_rr3_semantically_identical_noncanonical_bytes_refuse(
        client, tmp_path):
    """The DECISIVE byte-canonicality proof: only the SERIALIZATION of
    the lawful mapping_json changes (decode → pretty/reorder → write);
    every semantic column and mapping_hash stay untouched. Readiness
    and capture fail closed with the precise noncanonical-form reason;
    counts are unchanged; M17A recovery independently refuses the same
    stored row."""
    from soloring.errors import SoloRingError
    from soloring.recovery.m17a_verifier import (
        verify_m17a_dialogue_vocal_state,
    )

    world, first_revision = await _stage_lawful(client)

    # the lawful row, captured cleanly before the corruption
    lawful = await _row(client, (
        "SELECT mapping_json, mapping_hash FROM "
        "shot_vocal_segment_mappings WHERE shot_id = :s "
        "AND position = 0"), {"s": world["shot"]})
    doc = json.loads(lawful["mapping_json"])

    # ONLY the serialized bytes become noncanonical — semantics and
    # hash identical
    await _sql(client, (
        "UPDATE shot_vocal_segment_mappings SET mapping_json = :j "
        "WHERE shot_id = :s AND position = 0"),
        {"j": _pretty_noncanonical(doc), "s": world["shot"]})
    tampered = await _row(client, (
        "SELECT mapping_json, mapping_hash FROM "
        "shot_vocal_segment_mappings WHERE shot_id = :s "
        "AND position = 0"), {"s": world["shot"]})
    assert tampered["mapping_hash"] == lawful["mapping_hash"]
    assert json.loads(tampered["mapping_json"]) == doc

    before = await _counts(client).snapshot(world["shot"])

    # readiness fails closed with the byte-canonicality reason
    r = await client.get(
        f"/shots/{world['shot']}/performance-readiness")
    assert r.status_code == 500, r.text
    assert "fails its persisted canonical structural law" \
        in r.json()["message"], r.text
    assert "not its canonical serialized form" \
        in r.json()["message"], r.text

    # capture fails with the same corruption BEFORE the builder
    with pytest.raises(SoloRingError) as excinfo:
        await _attempt_capture(client, world["shot"])
    assert excinfo.value.status_code == 500
    assert "not its canonical serialized form" in excinfo.value.message

    # nothing was persisted by either refused path
    after = await _counts(client).snapshot(world["shot"])
    assert after == before

    # M17A recovery independently refuses the same stored row (the
    # shared law, recovery transport). The backup API itself would run
    # the same verification chain and refuse — so hand-stage the
    # database copy for the direct verifier call.
    import shutil
    data_dir = client._transport.app.state.settings.data_dir
    root = tmp_path / "rr3-bytes-staged"
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
    assert "canonical rehash fail" in rec.value.message
    assert "not its canonical serialized form" in rec.value.message


@pytest.mark.asyncio
async def test_rr3_semantic_forgery_case_retained(client):
    """The RR2 forged-document case (a DIFFERENT failure mode: the
    decoded object itself is not the canonical document) still refuses
    with its precise reason."""
    from soloring.errors import SoloRingError

    world, first_revision = await _stage_lawful(client)
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

    with pytest.raises(SoloRingError) as excinfo:
        await _attempt_capture(client, world["shot"])
    assert "mapping_json is not the canonical document" \
        in excinfo.value.message


@pytest.mark.asyncio
async def test_rr3_clean_control_and_supported_delete(client, tmp_path):
    """The clean canonical control (READY, schema-8 capture, §12
    valid, recovery valid) and the RR-02 supported DELETE (still
    blocked data, never corruption)."""
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
    root = await _backup_m17c(client, tmp_path, "rr3-clean")
    verify_m17a_dialogue_vocal_state(
        root / "soloring.db", blob_root=root / "blobs")
    verify_m17c_binding_state(
        root / "soloring.db", root / "blobs", head=_HEAD)

    # the supported DELETE: absence stays lawful blocked data
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
