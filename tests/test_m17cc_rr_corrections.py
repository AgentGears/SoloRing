"""M17C-C re-review corrections (frozen register RR-M17CC-01..04) —
the reviewer's verification demands, one battery.

- RR-01 / FPR-03: the observation compiler receives the LITERAL
  schema-6 view — schema_version: 6, the performance layer removed,
  and (for an 8-over-7-over-6 chain) the M16 successor layer removed
  too — proven with a compiler SPY for both 8-over-6 and 8-over-7.
- RR-02: a supported DELETE of the paired vocal mapping is the lawful
  BLOCKED_BINDING_INTEGRITY working state — readiness reports blocked,
  Shot detail succeeds with hash/differs NULL (the posture FROZEN by
  the correction commission: a blocked state is never hashed into a
  second uncapturable canon), capture returns the typed 409, and no
  revision/companion write occurs.
- RR-03 / FPR-04: the mapping preimage + hashes are SNAPSHOT-ANCHORED
  (grammar v2) — a COHERENT child-side rewrite of vocal_mapping_position
  (or the vocal origin) WITH the recomputed mapping hash refuses at
  BOTH §12 and recovery because it disagrees with the independent
  snapshot identity; grammar-v1 blocks are refused, never silently
  reinterpreted.
- RR-04: the M16 boundary validator POSITIVELY certifies the schema-8
  generation refusal — its structural check fails when the fence is
  deleted or relocated below a Generation-owned durable side effect.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from tests.m17cc_capture_helper import capture as _capture
from tests.test_m17cc_persist import _lawful
from tests.test_m17c_shot_mapping import _bound_world, _seg_body

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


async def _stage(client, *, extra=True):
    world = await _bound_world(client)
    await _lawful(client, world, extra=extra)
    revision, _visual = await _capture(client, world["shot"])
    return world, revision


async def _backup(client, tmp_path, tag):
    from tests.test_m17c_sr26_regressions import _backup_m17c
    return await _backup_m17c(client, tmp_path, f"m17cc-rr-{tag}")


async def _performance_world_on(client, base, subject_id, pid):
    """The dialogue-bound performance plane over an existing world."""
    from tests.m17c_seed import ARTICULATION, dialogue_bound_body, make_vp

    vp_world = await make_vp(client, pid=pid, eid=subject_id)
    r = await client.put(
        f"/dialogue-line-revisions/"
        f"{vp_world['dialogue_line_revision_id']}/vocal-selection",
        json={"vocal_performance_revision_id": vp_world["vp"]["id"],
              "selected_by": "d"})
    assert r.status_code == 200, r.text
    r = await client.put(
        f"/shots/{base['shot']}/vocal-segments/0",
        json={
            "vocal_performance_revision_id": vp_world["vp"]["id"],
            "source_start_sample": 48000,
            "source_end_sample_exclusive": 96000,
            "sample_rate_hz": 48000,
            "performance_origin_ms": {"num": 0, "den": 1},
            "shot_anchor_ms": {"num": 0, "den": 1},
        })
    assert r.status_code == 200, r.text
    candidate = (await client.post(
        f"/creative-entities/{subject_id}/"
        "dialogue-bound-performance-candidates",
        json=dialogue_bound_body(
            vp_world["vp"]["id"],
            articulation_time={key: (600, 1) for key in ARTICULATION}),
    )).json()
    pr = (await client.post(
        f"/performance-candidates/{candidate['id']}/adopt",
        json={"adopted_by": "d"})).json()
    r = await client.put(
        f"/shots/{base['shot']}/performance-segments/0",
        json=_seg_body(pr["id"], 0, 1000, 0, vp=0))
    assert r.status_code == 200, r.text
    return pr


# ---------------------------------------------------------------------------
# RR-01 — the observation compiler's literal schema-6 view
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("with_intra", [False, True])
async def test_rr01_observation_compiler_gets_literal_schema6(
        client, tmp_path, with_intra):
    """An observation-capable package on an 8-over-6 (and 8-over-7-over-6)
    capture: the readiness surface reaches compile_world_observation_spec
    with a projection that literally declares schema_version 6 and (for
    the 8-over-7 chain) carries no intra_shot key. The projection is for
    M14 consumption only — the captured ShotRevision is untouched."""
    import soloring.observation as observation_pkg
    from soloring.observation.compiler import (
        compile_world_observation_spec as _real_compiler,
    )
    from tests.test_m13_history import _captured_world
    from tests.test_m14_execution import _observation_package, _comfy

    b, sel, rev6 = await _captured_world(client, tag=b"rr-o36")
    if with_intra:
        # an intra-shot event over the world's PI subject turns the
        # chain into 8-over-7-over-6 (production_world retained)
        from tests.m16_seed_b import event, post_event, state
        r = await client.post(
            f"/entities/{b['eva']}/continuity-features",
            json={"key": "rrcut", "kind": "injury", "value_type":
                  "enum", "name": "RRCut",
                  "enum_values": ["fresh", "healing"]})
        assert r.status_code == 201, r.text
        fid = r.json()["id"]
        await post_event(client, b["shot"], event(
            fid, 1000, state(), state("fresh")))

    await _performance_world_on(client, b, b["eva"], b["pid"])
    revision, _visual = await _capture(client, b["shot"])
    snap = json.loads((await _row(client, (
        "SELECT snapshot_json FROM shot_revisions WHERE id = :r"),
        {"r": revision.id}))["snapshot_json"])
    assert snap["schema_version"] == 8
    assert "production_world" in snap
    if with_intra:
        assert "intra_shot" in snap

    # the captured revision is NEVER rewritten by the read
    before_bytes = (await _row(client, (
        "SELECT snapshot_json FROM shot_revisions WHERE id = :r"),
        {"r": revision.id}))["snapshot_json"]

    pkg = await _observation_package(tmp_path / "pkg")
    settings = _comfy(client, pkg)

    calls: list[dict] = []

    def _spy(**kwargs):
        calls.append(kwargs["captured_schema_6"])
        return _real_compiler(**kwargs)

    import unittest.mock as mock
    with mock.patch.object(
            observation_pkg, "compile_world_observation_spec", _spy):
        from soloring.observation.readiness import (
            observation_readiness,
        )
        session_factory = client._transport.app.state.session_factory
        async with session_factory() as session:
            result = await observation_readiness(
                session, settings, b["shot"])

    assert result["readiness"] != "not-applicable", result
    assert "carries no production world" not in str(
        result.get("explanation", ""))
    # the compiler was REACHED with the literal schema-6 view
    assert len(calls) == 1, calls
    assert calls[0]["schema_version"] == 6
    if with_intra:
        assert "intra_shot" not in calls[0]
    assert "performance" not in calls[0]
    assert "production_world" in calls[0]

    after_bytes = (await _row(client, (
        "SELECT snapshot_json FROM shot_revisions WHERE id = :r"),
        {"r": revision.id}))["snapshot_json"]
    assert after_bytes == before_bytes


# ---------------------------------------------------------------------------
# RR-02 — the supported paired-vocal DELETE stays a lawful blocked state
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr02_supported_vocal_delete_blocked_not_corrupt(client):
    world, revision = await _stage(client)

    # the supported DELETE of the paired vocal mapping
    r = await client.delete(f"/shots/{world['shot']}/vocal-segments/0")
    assert r.status_code in (200, 204), r.text

    # readiness reports the lawful blocked working state
    red = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert red["ready"] is False
    states = [s["readiness"] for s in red["segments"]]
    assert "BLOCKED_BINDING_INTEGRITY" in states, states

    # Shot detail SUCCEEDS with the frozen null posture — no 500
    detail = (await client.get(f"/shots/{world['shot']}")).json()
    assert detail["working_snapshot_hash"] is None
    assert detail["working_state_differs_from_approved"] is None

    # capture returns the typed 409 with diagnostics — no 500
    from soloring.errors import SoloRingError
    from tests.conftest import make_tracked_maker
    engine = _engine(client)
    factory = make_tracked_maker(engine)
    from soloring.domain.revisions import capture_revision_with_visual
    with pytest.raises(SoloRingError) as excinfo:
        async with factory() as session:
            await capture_revision_with_visual(
                session, world["shot"],
                settings=client._transport.app.state.settings)
    assert excinfo.value.code == "PERFORMANCE_CAPTURE_NOT_READY"
    assert excinfo.value.status_code == 409
    assert "segments" in excinfo.value.details

    # no revision/companion write occurred for the refused capture
    n_rev = (await _row(client, (
        "SELECT COUNT(*) AS n FROM shot_revisions WHERE shot_id = :s"),
        {"s": world["shot"]}))["n"]
    assert n_rev == 1  # only the pre-DELETE lawful capture
    n_children = (await _row(client, (
        f"SELECT COUNT(*) AS n FROM {_CHILDREN} WHERE "
        "shot_revision_id = :r"), {"r": revision.id}))["n"]
    assert n_children == 2


# ---------------------------------------------------------------------------
# RR-03 — the snapshot-anchored mapping preimage
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("field", [
    "vocal_mapping_position", "vocal_performance_origin_num",
])
async def test_rr03_coherent_preimage_rewrite_refuses(client, tmp_path,
                                                       field):
    """The DECISIVE adversarial proof: change the preimage field AND
    recompute the mapping hash from the changed preimage. Both §12 and
    recovery refuse because the result disagrees with the independent
    SNAPSHOT identity — not because a dependent hash was forgotten."""
    from soloring.errors import SoloRingError
    from soloring.performance.m17cc_capture_read import (
        _child_preimage_vocal, expected_mapping_hashes,
    )
    from soloring.recovery.m17c_verifier import verify_m17c_binding_state

    world, revision = await _stage(client)
    root = await _backup(client, tmp_path, f"cpi-{field}")

    def _tamper(db):
        con = sqlite3.connect(db)
        row = con.execute(
            f"SELECT * FROM {_CHILDREN} WHERE shot_revision_id = ? "
            "AND position = 0", (revision.id,)).fetchone()
        cols = [d[0] for d in con.execute(
            f"SELECT * FROM {_CHILDREN} LIMIT 0").description]
        forged = dict(zip(cols, row))
        if field == "vocal_mapping_position":
            forged["vocal_mapping_position"] = \
                forged["vocal_mapping_position"] + 1
        else:
            forged["vocal_performance_origin_num"] = \
                forged["vocal_performance_origin_num"] + 1
        perf_hash, vocal_hash = expected_mapping_hashes(
            forged["performance_revision_id"],
            {"num": forged["performance_start_num"],
             "den": forged["performance_start_den"]},
            {"num": forged["performance_end_num"],
             "den": forged["performance_end_den"]},
            {"num": forged["shot_anchor_num"],
             "den": forged["shot_anchor_den"]},
            forged["vocal_mapping_position"],
            _child_preimage_vocal(forged))
        con.execute(
            f"UPDATE {_CHILDREN} SET {field} = ?, "
            "performance_mapping_hash = ?, vocal_mapping_hash = ? "
            "WHERE shot_revision_id = ? AND position = 0",
            (forged[field], perf_hash, vocal_hash,
             revision.id))
        con.commit()
        con.close()

    # §12 refuses via the snapshot anchor
    _tamper(client._transport.app.state.settings.data_dir
            / "soloring.db")
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 500, r.text
    assert "disagrees with the embedded captured segment" \
        in r.json()["message"], r.text

    # recovery refuses via the snapshot anchor
    _tamper(root / "soloring.db")
    with pytest.raises(SoloRingError) as excinfo:
        verify_m17c_binding_state(root / "soloring.db", root / "blobs",
                                  head=_HEAD)
    assert excinfo.value.code == "RECOVERY_CORRUPTION"
    assert "disagrees with the embedded captured segment" \
        in excinfo.value.message


@pytest.mark.asyncio
async def test_rr03_grammar_v1_block_refused(client):
    """A grammar-v1 performance block (0023-era companion-only
    preimage) is REFUSED by both surfaces — pre-anchor captures are
    never silently certified as having the new anchor."""
    from soloring.domain.canonical import (
        canonical_hash as _ch, canonical_json_str as _cj,
    )

    world, revision = await _stage(client)

    def _demote(db):
        con = sqlite3.connect(db)
        snap = json.loads(con.execute(
            "SELECT snapshot_json FROM shot_revisions WHERE id = ?",
            (revision.id,)).fetchone()[0])
        snap["performance"]["schema_version"] = 1
        spec = json.loads(con.execute(
            f"SELECT spec_json FROM {_PARENTS} WHERE "
            "shot_revision_id = ?", (revision.id,)).fetchone()[0])
        spec["schema_version"] = 1
        con.execute(
            "UPDATE shot_revisions SET snapshot_json = ?, "
            "snapshot_hash = ? WHERE id = ?",
            (_cj(snap), _ch(snap), revision.id))
        con.execute(
            f"UPDATE {_PARENTS} SET spec_json = ?, spec_hash = ? "
            "WHERE shot_revision_id = ?",
            (_cj(spec), _ch(spec), revision.id))
        con.commit()
        con.close()

    _demote(client._transport.app.state.settings.data_dir / "soloring.db")
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 500, r.text
    assert "grammar-v1 performance block" in r.json()["message"], r.text


# ---------------------------------------------------------------------------
# RR-04 — the boundary validator positively certifies the fence
# ---------------------------------------------------------------------------

def test_rr04_validator_requires_the_schema8_fence():
    from scripts.m16_validate_boundary import schema8_fence_check

    from pathlib import Path
    src = (Path(__file__).resolve().parents[1]
           / "server/soloring/generation/service.py").read_text(
               encoding="utf-8")
    # the REAL source passes
    assert schema8_fence_check(src) == [], schema8_fence_check(src)

    # M17C-D evolution (frozen plan R2-FINAL): the fence certifies
    # the ADMISSION STRUCTURE — deletion of either admission refusal
    # → the check fails
    for token in ("INTRA_SHOT_REALIZATION_UNSUPPORTED",
                  "PERFORMANCE_SPATIAL_COMPOSITION_UNSUPPORTED"):
        doctored = src.replace(token, "SOME_OTHER_CODE")
        assert schema8_fence_check(doctored) != []

    # deletion of the gate itself → the check fails
    doctored = src.replace("if snapshot_schema == 8:",
                           "if snapshot_schema == 88:")
    assert schema8_fence_check(doctored) != []

    # relocation: the fence moved below the first Generation-owned
    # durable side effect (the release placement) → the check fails
    fence_start = src.find("    if snapshot_schema == 8:")
    det = src.find('details={"shot_revision_id": revision.id})',
                   fence_start)
    fence_end = det + len('details={"shot_revision_id": revision.id})')
    fence_block = src[fence_start:fence_end]
    place_idx = src.find("        await _artifact_store.place_release("
                         "release)")
    assert place_idx > fence_end
    line_end = src.find("\n", place_idx) + 1
    relocated = (src[:fence_start] + src[fence_end:line_end]
                 + fence_block + src[line_end:])
    assert schema8_fence_check(relocated) != []
