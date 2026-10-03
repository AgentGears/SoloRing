"""M17C-C second-review corrections (frozen register SR-M17CC-01..05).

Five defects confirmed at the reconciled second review of proof head
83d5c99, corrected under one commission:

SR-01 — sparse public Performance positions could project fully READY
  and capture into schema 8, minting durable history whose OWN first
  §12 read and recovery verification reject it (both require dense
  zero-based embedded positions). The captured-history grammar stays
  dense canonical [0..n-1]; the READINESS projection now refuses to
  certify a non-dense working set as READY (BLOCKED_POSITIONS_NOT_
  DENSE — a working-state data classification, exactly like the other
  lawful blocked postures), so sparse sets can never reach capture.

SR-02 — §12 certified captured rationals only as int-pairs with a
  positive denominator (no reduction/canonical-zero/bool exclusion)
  and never proved a generic captured interval inside the immutable
  PerformanceRevision temporal domain. §12 now enforces the SAME
  canonical law through the ONE shared temporal primitive plus a
  nonempty interval for every child and PR-domain containment for
  generic children — recovery parity.

SR-03 — embedded JSON scalars were compared to relational companion
  columns with plain ==/!=, so Python cross-type aliases (False == 0,
  1.0 == 1) satisfied field identity: a coherently rehashed graph
  declaring position:false passed BOTH §12 and recovery against a
  relational integer 0. Both seams now compare through the ONE
  shared type-exact projection helper.

SR-04 — §12 authenticated the PF-03 binding but exposed the
  referenced PR/VP semantic fields without the closure recovery
  enforces. §12 now proves PR↔Shot project coherence for every
  child, and subject↔VP-speaker agreement, VP native-rate agreement,
  captured-sample containment in the immutable VP trim, and VP
  dialogue-line lineage project coherence before any VP field
  answers as historical truth. No current working surface is read.

SR-05 — GPI recovery verification ran .strip()/len() on hash columns
  without certifying storage classes: a 64-byte BLOB passes the
  TEXT-affinity length CHECK and bytes.strip(str) raises a raw
  TypeError; REAL/bool/None coordinates were silently accepted. The
  verifier now certifies the persisted types FIRST — malformed GPI
  storage terminates as typed RECOVERY_CORRUPTION.

The frozen battery proves each correction at BOTH surfaces (the §12
live history read on the corrupted LIVE database + an independently
corrupted pre-corruption STAGED copy for recovery — the backup is
always taken while the world is still lawful), with the
coherent-adversary shapes the review specified, plus the dense
lawful control.
"""

from __future__ import annotations

import sqlite3

import pytest

from tests.m17cc_capture_helper import capture as _capture
from tests.test_m17cc_persist import _lawful
from tests.test_m17c_shot_mapping import _bound_world, _seg_body

_HEAD = "0023_m17cc_capture_closure_preimage"
_CHILDREN = "shot_revision_performance_segments"
_PARENTS = "shot_revision_performance_specs"


def _engine(client):
    return client._transport.app.state.engine


async def _sql(client, stmt, params=None):
    from sqlalchemy import text
    async with _engine(client).begin() as conn:
        await conn.execute(text(stmt), params or {})


async def _scalar(client, stmt, params=None):
    from sqlalchemy import text
    async with _engine(client).connect() as conn:
        return (await conn.execute(
            text(stmt), params or {})).scalar_one()


async def _stage_lawful(client):
    """The dense lawful world: dialogue child at 0 + generic child
    at 1, captured into schema 8."""
    world = await _bound_world(client)
    await _lawful(client, world, extra=True)
    revision, _visual = await _capture(client, world["shot"])
    return world, revision


async def _lawful_backup(client, tmp_path, tag):
    """A backup copy taken while the world is STILL LAWFUL (always
    before any corruption of the live database)."""
    from tests.test_m17c_sr26_regressions import _backup_m17c
    return await _backup_m17c(client, tmp_path, f"sr-{tag}")


def _live_root(client):
    return client._transport.app.state.settings.data_dir


def _verify_staged_raises(root, fragment):
    from soloring.errors import SoloRingError
    from soloring.recovery.m17c_verifier import (
        verify_m17c_binding_state,
    )
    with pytest.raises(SoloRingError) as rec:
        verify_m17c_binding_state(
            root / "soloring.db", root / "blobs", head=_HEAD)
    assert rec.value.code == "RECOVERY_CORRUPTION"
    assert fragment in rec.value.message, rec.value.message


# ---------------------------------------------------------------------------
# SR-01 — sparse public positions never READY / never captured
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sr01_sparse_positions_blocked_not_captured(client):
    """A lawful public mapping ONLY at position 1 (the exact review
    path): the PUT stays accepted working state, but readiness is NOT
    ready (BLOCKED_POSITIONS_NOT_DENSE on every segment), capture
    refuses as the typed non-ready 409, and NO revision/companion rows
    appear. Filling position 0 restores READY — the dense set stays
    lawful."""
    from soloring.errors import SoloRingError
    from tests.m17b_seed import (
        HEAD_YAW, candidate_body, channel as m17b_channel,
        kf as m17b_kf,
    )
    from tests.test_m17cc_rr5_corrections import _attempt_capture

    world = await _bound_world(client)
    body_candidate = (await client.post(
        f"/creative-entities/{world['subject_id']}/"
        "performance-candidates",
        json=candidate_body(
            [m17b_channel(HEAD_YAW, [m17b_kf(0, 1, 0)])]),
    )).json()
    body_pr = (await client.post(
        f"/performance-candidates/{body_candidate['id']}/adopt",
        json={"adopted_by": "s3"})).json()

    # the sparse public mapping: ONLY position 1 exists
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/1",
        json=_seg_body(body_pr["id"], 0, 1000, 0))
    assert r.status_code == 200, r.text

    red = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert red["ready"] is False, red
    assert [s["readiness"] for s in red["segments"]] == \
        ["BLOCKED_POSITIONS_NOT_DENSE"] * len(red["segments"])
    assert "dense canonical [0..n-1]" in red["segments"][0][
        "readiness_diagnostics"]["reason"]

    before = (
        await _scalar(client, (
            "SELECT COUNT(*) FROM shot_revisions WHERE shot_id = :s"),
            {"s": world["shot"]}),
        await _scalar(client, f"SELECT COUNT(*) FROM {_PARENTS}"),
        await _scalar(client, f"SELECT COUNT(*) FROM {_CHILDREN}"))

    # capture refuses — the sparse set is lawful BLOCKED data (409),
    # never a partial/invalid durable revision
    with pytest.raises(SoloRingError) as exc:
        await _attempt_capture(client, world["shot"])
    assert exc.value.status_code == 409, exc.value.message

    after = (
        await _scalar(client, (
            "SELECT COUNT(*) FROM shot_revisions WHERE shot_id = :s"),
            {"s": world["shot"]}),
        await _scalar(client, f"SELECT COUNT(*) FROM {_PARENTS}"),
        await _scalar(client, f"SELECT COUNT(*) FROM {_CHILDREN}"))
    assert after == before

    # the dense control: filling position 0 restores READY and the
    # normal capture path (the same dense [0,1] world every prior
    # battery proves green)
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 1000, 0, vp=0))
    assert r.status_code == 200, r.text
    red = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert red["ready"] is True, red
    revision, _visual = await _capture(client, world["shot"])
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 200, r.text
    assert len(r.json()["performance"]["segments"]) == 2


# ---------------------------------------------------------------------------
# SR-02 — §12 canonical-rational + PR-domain parity with recovery
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("mode,s12_fragment,recovery_fragment", [
    ("unreduced_rational",
     "not in canonical reduced form",
     "is not canonical"),
    ("out_of_domain",
     "captured interval lies outside the immutable PerformanceRevision "
     "domain",
     "captured interval lies outside the immutable PerformanceRevision "
     "domain"),
])
async def test_sr02_coherent_timing_rewrites_refused_by_both(
        client, tmp_path, mode, s12_fragment, recovery_fragment):
    """The two review adversaries, each a FULLY COHERENT rewrite of
    the captured GENERIC segment (child columns, embedded segment,
    recomputed mapping hashes, segment/spec/snapshot bytes+hashes):
    (a) unreduced 2/2 start; (b) a canonical interval beyond the
    immutable PR temporal end. §12 and staged recovery must BOTH
    refuse — the §12/recovery semantic divergence is closed."""
    from tests.test_m17cc_recovery import _coherent_child_rewrite

    world, revision = await _stage_lawful(client)
    root = await _lawful_backup(client, tmp_path, f"sr02-{mode}")

    if mode == "unreduced_rational":
        updates = {"performance_start_ms": {"num": 2, "den": 2}}
    else:
        temporal_end = await _scalar(client, (
            "SELECT temporal_end_num FROM performance_revisions "
            "WHERE id = (SELECT performance_revision_id FROM "
            f"{_CHILDREN} WHERE shot_revision_id = :r "
            "AND position = 1)"), {"r": revision.id})
        updates = {"performance_end_ms":
                   {"num": temporal_end + 1000, "den": 1}}

    # §12 (live): the coherent rewrite on the live database refuses
    # through the new §12 timing law
    _coherent_child_rewrite(
        _live_root(client), revision.id, 1, updates)
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 500, r.text
    assert s12_fragment in r.json()["message"], r.text

    # staged recovery: the independent pre-corruption copy refuses
    # the same coherent shape through its own law
    _coherent_child_rewrite(root, revision.id, 1, updates)
    _verify_staged_raises(root, recovery_fragment)


# ---------------------------------------------------------------------------
# SR-03 — type-exact projection (False == 0 refused)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sr03_position_false_type_alias_refused_by_both(
        client, tmp_path):
    """The decisive cross-type adversary: the embedded segment's
    position 0 becomes JSON false, with EVERY canonical hash
    recomputed coherently (segment/spec/snapshot + mapping hashes),
    while the relational child stays integer 0 (typeof proven) —
    False == 0 must NOT satisfy projection identity at either §12 or
    recovery."""
    from tests.test_m17cc_recovery import _coherent_child_rewrite

    world, revision = await _stage_lawful(client)
    root = await _lawful_backup(client, tmp_path, "sr03-false")

    _coherent_child_rewrite(
        _live_root(client), revision.id, 0, {"position": False})
    con = sqlite3.connect(_live_root(client) / "soloring.db")
    try:
        stored_type = con.execute(
            f"SELECT typeof(position) FROM {_CHILDREN} WHERE "
            "shot_revision_id = ? AND position = 0",
            (revision.id,)).fetchone()[0]
    finally:
        con.close()
    assert stored_type == "integer"

    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 500, r.text
    assert "declares position False" in r.json()["message"], r.text

    _coherent_child_rewrite(root, revision.id, 0, {"position": False})
    _verify_staged_raises(
        root, "disagrees with the embedded captured ordering")


# ---------------------------------------------------------------------------
# SR-04 — §12 authenticates the PR/VP semantic closure it exposes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,s12_fragment,recovery_fragment",
    [("vp_speaker",
      "subject disagrees with the VP speaker",
      "subject != bound VP speaker"),
     ("pr_project",
      "crosses projects: PR project",
      "crosses projects")])
async def test_sr04_immutable_semantic_mutations_fail_closed(
        client, tmp_path, mode, s12_fragment, recovery_fragment):
    """The review adversaries: raw-mutate the immutable authority §12
    exposes — the VP's speaker, or the PR's project — leaving the
    captured graph and authenticated binding untouched. §12 must fail
    closed (typed 500) AND staged recovery must refuse (the
    history/recovery divergence is closed). Recovery's refusal fires
    from its own earliest applicable law over the mutated immutable
    row (the candidate-binding subject law / the mapping project law)
    — fail-closed either way, never green."""
    world, revision = await _stage_lawful(client)
    root = await _lawful_backup(client, tmp_path, f"sr04-{mode}")

    def _mutate(db_root):
        con = sqlite3.connect(db_root / "soloring.db")
        try:
            if mode == "vp_speaker":
                con.execute(
                    "UPDATE vocal_performance_revisions SET "
                    "speaker_subject_id = "
                    "'00000000-0000-4000-8000-0000000000ee' "
                    "WHERE id = ?", (world["vp"]["id"],))
            else:
                con.execute(
                    "UPDATE performance_revisions SET project_id = "
                    "'00000000-0000-4000-8000-0000000000dd' "
                    "WHERE id = ?", (world["pr"]["id"],))
            con.commit()
        finally:
            con.close()

    _mutate(_live_root(client))
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 500, r.text
    assert s12_fragment in r.json()["message"], r.text

    _mutate(root)
    _verify_staged_raises(root, recovery_fragment)


# ---------------------------------------------------------------------------
# SR-05 — GPI recovery total over SQLite storage classes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("column,value,kind,fragment", [
    ("derived_input_hash", b"a" * 64, "blob",
     "is not persisted text"),
    ("position", 1.5, "real",
     "is not a persisted nonnegative integer"),
    ("shot_revision_segment_position", 2.5, "real",
     "is not a persisted nonnegative integer"),
])
async def test_sr05_gpi_storage_classes_typed_corruption(
        client, tmp_path, column, value, kind, fragment):
    """The decisive GPI adversaries, staged through raw SQLite on a
    lawful schema-8 + Generation world: a genuine 64-byte BLOB
    derived_input_hash (typeof proven 'blob' — it passes the schema's
    length CHECK) and genuine REAL coordinates. Recovery terminates
    as typed RECOVERY_CORRUPTION — never a raw bytes.strip TypeError,
    never acceptance."""
    from tests.test_m17cc_recovery import (
        _TRANSLATION_ID, _insert_gpi, _materialize_translation,
        _stage_with_generation,
    )

    root, world, revision_id, gen_id, blob = (
        await _stage_with_generation(client, tmp_path,
                                     f"sr05-{column}"))
    _materialize_translation(root, gen_id, _TRANSLATION_ID)
    _insert_gpi(root, gen_id, revision_id, blob,
                role="performance.controls", key="performance:0",
                position=0, seg_pos=0)

    con = sqlite3.connect(root / "soloring.db")
    try:
        con.execute(
            f"UPDATE generation_performance_inputs SET {column} = ? "
            "WHERE generation_id = ?", (value, gen_id))
        con.commit()
        stored = con.execute(
            f"SELECT typeof({column}) FROM "
            "generation_performance_inputs WHERE generation_id = ?",
            (gen_id,)).fetchone()[0]
    finally:
        con.close()
    assert stored == kind, stored

    _verify_staged_raises(root, fragment)


# ---------------------------------------------------------------------------
# Clean control — the dense lawful world stays green everywhere
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sr_clean_control_lawful_world_green(client):
    """The lawful dense world (one dialogue-bound child at 0 + one
    generic child at 1) stays fully green under every new law:
    readiness READY, §12 answers both children (canonical rationals,
    in-domain generic interval, closed VP semantic fields), and
    backup + M17A + M17C recovery pass."""
    from soloring.recovery.m17a_verifier import (
        verify_m17a_dialogue_vocal_state,
    )
    from soloring.recovery.m17c_verifier import verify_m17c_binding_state
    from tests.test_m17c_sr26_regressions import _backup_m17c
    import tempfile
    from pathlib import Path

    world, revision = await _stage_lawful(client)

    red = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert red["ready"] is True, red

    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 200, r.text
    segments = r.json()["performance"]["segments"]
    assert [s["position"] for s in segments] == [0, 1]
    assert segments[0]["vocal"] is not None
    assert segments[1]["vocal"] is None
    # the generic child answers with its canonical in-domain interval
    assert segments[1]["performance_start_ms"] == {"num": 0, "den": 1}
    assert segments[1]["performance_end_ms"] == {"num": 1000, "den": 1}
    # the exposed VP speaker is the verified historical authority
    assert segments[0]["vocal"]["vocal_performance_revision"][
        "speaker_subject_id"] == world["subject_id"]

    tmp = Path(tempfile.mkdtemp())
    root = await _backup_m17c(client, tmp, "sr-clean")
    verify_m17a_dialogue_vocal_state(
        root / "soloring.db", blob_root=root / "blobs")
    verify_m17c_binding_state(
        root / "soloring.db", root / "blobs", head=_HEAD)
