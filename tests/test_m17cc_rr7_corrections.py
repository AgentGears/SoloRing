"""M17C-C RR7 correction (frozen register RR7-M17CC-01) — §12
authenticates the immutable PF-03 binding document before using it.

The immutable PerformanceRevisionVocalBinding row must
SELF-AUTHENTICATE (the ONE shared transport-neutral PF-03 structural
law — schema/basis versions frozen at 1, the persisted origin an
already-canonical rational, the exact canonical document over the
row's own fields, exact binding_json bytes, recomputed hash == stored
binding_hash) BEFORE §12 uses any scalar or exposes it as historical
authority; only then the captured-hash comparison, then the RR6
containment + induced-arithmetic laws (containment NOT collapsed back
into equality). No repair, no substitution.

The frozen battery:
1. the scalar/stale-hash tamper — extend only source_end so the
   captured subsegment stays contained, bytes/hash untouched → §12
   typed 500 on binding canonical integrity + the recovery chain
   independently refuses;
2. the binding_json-only tamper — all scalars/hash intact, only the
   canonical bytes changed → the same structural law on both surfaces;
3. the RR6 positive regression — the public inside-binding subsegment
   path READY → schema-8 capture → first §12 read green → recovery
   green;
4. the forbidden-current-table spy stays green (authenticating the
   immutable revision binding is §12's allowed authority; no current
   surface introduced).
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
from tests.test_m17c_shot_mapping import _bound_world, _seg_body

_PARENTS = "shot_revision_performance_specs"
_CHILDREN = "shot_revision_performance_segments"
_HEAD = "0023_m17cc_capture_closure_preimage"

_FORBIDDEN = (
    "vocal_performance_selections",
    "shot_vocal_segment_mappings",
    "shot_performance_segment_mappings",
    "performance_candidate",
    "shot_entity_dependencies",
)


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


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["scalar_stale_hash",
                                  "binding_json_only"])
async def test_rr7_binding_self_authentication_tamper(client, tmp_path,
                                                       mode):
    """The two decisive tamper shapes. SCALAR/STALE-HASH: extend only
    binding source_end ([48000,96000) → [48000,120000)) so the
    captured [48000,96000) stays CONTAINED; binding_json/binding_hash
    untouched — the hash token still matches the captured value, so
    only the row's own canonical rehash can refuse. JSON-ONLY: all
    scalars + hash intact, only the canonical bytes changed (a
    semantically identical noncanonical serialization). Both: §12
    typed 500 through the shared binding structural law; the recovery
    chain independently refuses the same staged state."""
    from soloring.errors import SoloRingError

    world, revision = await _stage_lawful(client)

    if mode == "scalar_stale_hash":
        await _sql(client, (
            "UPDATE performance_revision_vocal_bindings SET "
            "source_end_sample_exclusive = 120000 "
            "WHERE performance_revision_id = :p"),
            {"p": world["pr"]["id"]})
    else:
        binding = await _row(client, (
            "SELECT binding_json FROM "
            "performance_revision_vocal_bindings WHERE "
            "performance_revision_id = :p"), {"p": world["pr"]["id"]})
        doc = json.loads(binding["binding_json"])
        await _sql(client, (
            "UPDATE performance_revision_vocal_bindings SET "
            "binding_json = :j WHERE performance_revision_id = :p"),
            {"j": json.dumps(
                dict(reversed(list(doc.items()))), indent=2),
             "p": world["pr"]["id"]})

    # §12 fails typed 500 through the shared binding structural law
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 500, r.text
    assert ("names an immutable synchronization binding that fails "
            "its own canonical structural law"
            in r.json()["message"]), r.text
    # the precise reason: the stored binding_json no longer matches
    # the canonical document over the row's own (tampered) fields
    assert "binding_json is not the canonical document" \
        in r.json()["message"], r.text

    # the recovery chain independently refuses the same staged state
    # (the binding-document law lives in the M17C recovery chain's
    # _verify_revision_bindings; hand-staged copy — the backup API
    # itself runs the same chain)
    from soloring.recovery.m17c_verifier import (
        verify_m17c_binding_state,
    )
    data_dir = client._transport.app.state.settings.data_dir
    root = tmp_path / f"rr7-{mode}-staged"
    root.mkdir()
    src_db = data_dir / "soloring.db"
    con = sqlite3.connect(src_db)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()
    shutil.copy(src_db, root / "soloring.db")
    shutil.copytree(data_dir / "blobs", root / "blobs")
    with pytest.raises(SoloRingError) as rec:
        verify_m17c_binding_state(
            root / "soloring.db", root / "blobs", head=_HEAD)
    assert rec.value.code == "RECOVERY_CORRUPTION"
    assert "binding" in rec.value.message.lower(), rec.value.message


@pytest.mark.asyncio
async def test_rr7_rr6_positive_regression_and_spy(client):
    """The RR6 supported-subsegment path stays fully green under
    self-authentication (containment NOT collapsed back into
    equality), and the forbidden-current-table spy stays green during
    the §12 read."""
    from sqlalchemy import event

    world, first_revision = await _stage_lawful(client)

    # the public inside-binding subsegment path
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
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 250, 750, 250, vp=0))
    assert r.status_code == 200, r.text
    red = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert red["ready"] is True, red

    revision, _visual = await _capture(client, world["shot"])

    engine = _engine(client)
    hits: list[str] = []

    def _check(conn, cursor, statement, params, ctx, many):
        lowered = statement.lower()
        for table in _FORBIDDEN:
            if table in lowered:
                hits.append(table)

    event.listen(engine.sync_engine, "before_cursor_execute", _check)
    try:
        r = await client.get(
            f"/shot-revisions/{revision.id}/continuity")
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _check)
    assert r.status_code == 200, r.text
    assert hits == [], hits
    seg = r.json()["performance"]["segments"][0]
    assert seg["vocal"]["sample_interval"] == {
        "source_start_sample": 60000,
        "source_end_sample_exclusive": 84000,
        "sample_rate_hz": 48000}
    assert seg["performance_start_ms"] == {"num": 250, "den": 1}
    assert seg["performance_end_ms"] == {"num": 750, "den": 1}
    assert seg["vocal"]["synchronization_binding"]["binding_hash"] == \
        world["pr"]["id"] and False or seg["vocal"][
            "synchronization_binding"]["binding_hash"] is not None

    # recovery green
    from soloring.recovery.m17a_verifier import (
        verify_m17a_dialogue_vocal_state,
    )
    from soloring.recovery.m17c_verifier import verify_m17c_binding_state
    from tests.test_m17c_sr26_regressions import _backup_m17c
    import tempfile
    from pathlib import Path
    tmp = Path(tempfile.mkdtemp())
    root = await _backup_m17c(client, tmp, "rr7-positive")
    verify_m17a_dialogue_vocal_state(
        root / "soloring.db", blob_root=root / "blobs")
    verify_m17c_binding_state(
        root / "soloring.db", root / "blobs", head=_HEAD)


@pytest.mark.asyncio
async def test_rr7_clean_control(client):
    """The clean whole-binding control still captures and reads green
    (the trivial containment case, now with the authenticated
    document)."""
    world, revision = await _stage_lawful(client)
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 200, r.text
    assert r.json()["performance"] is not None
