"""M17C-C RR12 corrections (frozen register RR12-M17CC-01..02).

RR12-01 — the captured vocal preimage's persisted scalar law. The
  §12/recovery projection equality proves same-type-and-value against
  the embedded JSON, NOT that the shared type is lawful authority: a
  coherent SQLite REAL coordinate (child REAL + embedded JSON float,
  mapping hash and the complete segment/spec/snapshot hash chain
  recomputed, binding containment still satisfied) passed every
  projection/hash law and then reached Fraction((float - int) * 1000,
  rate) — a raw TypeError on BOTH surfaces. The ONE shared
  transport-neutral `captured_vocal_preimage_error` now certifies the
  preimage BEFORE it is hashed or used arithmetically: actual
  non-bool persisted integers for the source coordinates/rate
  (0 <= start < end, rate > 0) and vocal_mapping_position (the ONE
  shared position-domain primitive), and an actual canonical-reduced
  integer rational for the captured origin (the ONE shared temporal
  primitive). §12 → typed internal invariant; recovery →
  RECOVERY_CORRUPTION. No divergent history/recovery grammar.

RR12-02 — the captured Performance grammar's schema discriminator is
  now an ACTUAL non-bool integer exactly 2 through the ONE shared
  `is_actual_int_schema` law consumed by both §12's grammar and
  recovery's capture-state grammar (the explicit grammar-v1
  diagnostic preserved) — ordinary numeric equality admitted JSON
  2.0, a value the canonical writer cannot emit.

The frozen battery proves each correction with the coherent
adversaries the review specified, at BOTH surfaces (the §12 live
read on the corrupted LIVE database + an independently corrupted
pre-corruption STAGED copy for recovery — the backup is always taken
while the world is still lawful), plus the lawful controls.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from tests.m17cc_capture_helper import capture as _capture
from tests.test_m17cc_persist import _lawful
from tests.test_m17c_shot_mapping import _bound_world

_HEAD = "0023_m17cc_capture_closure_preimage"
_CHILDREN = "shot_revision_performance_segments"
_PARENTS = "shot_revision_performance_specs"


def _engine(client):
    return client._transport.app.state.engine


async def _stage_lawful(client):
    world = await _bound_world(client)
    await _lawful(client, world, extra=True)
    revision, _visual = await _capture(client, world["shot"])
    return world, revision


async def _lawful_backup(client, tmp_path, tag):
    from tests.test_m17c_sr26_regressions import _backup_m17c
    return await _backup_m17c(client, tmp_path, f"rr12-{tag}")


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


def _coherent_vocal_scalar_rewrite(db_root, revision_id, position,
                                   updates):
    """THE strong coherent shape over the captured VOCAL preimage:
    rewrite the child's vocal-group/origin columns AND the embedded
    vocal object / origin value, rebuild BOTH mapping hashes from the
    row's own post-tamper preimage, and refresh the complete
    segment/spec/snapshot canonical hash chain — so every projection,
    hash-closure, and anchoring law passes by construction and only
    the persisted-scalar law can refuse."""
    from soloring.domain.canonical import (
        canonical_hash as ch, canonical_json_str as cj,
    )
    from soloring.performance.m17cc_capture_read import (
        _child_preimage_vocal, expected_mapping_hashes,
    )
    con = sqlite3.connect(db_root / "soloring.db")
    con.row_factory = sqlite3.Row
    try:
        row = dict(con.execute(
            f"SELECT * FROM {_CHILDREN} WHERE shot_revision_id = ? "
            "AND position = ?", (revision_id, position)).fetchone())
        spec = json.loads(con.execute(
            f"SELECT spec_json FROM {_PARENTS} WHERE "
            "shot_revision_id = ?", (revision_id,)).fetchone()[0])
        snap = json.loads(con.execute(
            "SELECT snapshot_json FROM shot_revisions WHERE id = ?",
            (revision_id,)).fetchone()[0])
        seg = spec["segments"][position]
        snap_seg = snap["performance"]["segments"][position]
        row.update(updates)
        origin_keys = {k for k in updates
                       if k.startswith("vocal_performance_origin")}
        vocal_keys = {k for k in updates
                      if k.startswith(("source_", "sample_rate"))}
        if origin_keys:
            origin = {"num": row["vocal_performance_origin_num"],
                      "den": row["vocal_performance_origin_den"]}
            seg["vocal_performance_origin_ms"] = origin
            snap_seg["vocal_performance_origin_ms"] = origin
        if vocal_keys:
            embedded_vocal = {k: row[k] for k in
                              ("vocal_performance_revision_id",
                               "vocal_binding_hash",
                               "source_start_sample",
                               "source_end_sample_exclusive",
                               "sample_rate_hz")}
            seg["vocal"] = embedded_vocal
            snap_seg["vocal"] = dict(embedded_vocal)
        vocal = _child_preimage_vocal(row)
        perf_hash, vocal_hash = expected_mapping_hashes(
            row["performance_revision_id"],
            {"num": row["performance_start_num"],
             "den": row["performance_start_den"]},
            {"num": row["performance_end_num"],
             "den": row["performance_end_den"]},
            {"num": row["shot_anchor_num"],
             "den": row["shot_anchor_den"]},
            row["vocal_mapping_position"], vocal)
        seg["performance_mapping_hash"] = perf_hash
        seg["vocal_mapping_hash"] = vocal_hash
        snap_seg["performance_mapping_hash"] = perf_hash
        snap_seg["vocal_mapping_hash"] = vocal_hash
        seg_json, seg_hash = cj(seg), ch(seg)
        con.execute(
            f"UPDATE {_PARENTS} SET spec_json = ?, spec_hash = ? "
            "WHERE shot_revision_id = ?",
            (cj(spec), ch(spec), revision_id))
        con.execute(
            "UPDATE shot_revisions SET snapshot_json = ?, "
            "snapshot_hash = ? WHERE id = ?",
            (cj(snap), ch(snap), revision_id))
        sets = dict(updates)
        sets.update({"performance_mapping_hash": perf_hash,
                     "vocal_mapping_hash": vocal_hash,
                     "segment_json": seg_json,
                     "segment_hash": seg_hash})
        columns = ", ".join(f"{c} = :{c}" for c in sets)
        params = dict(sets)
        params.update({"__rid": revision_id, "__pos": position})
        con.execute(
            f"UPDATE {_CHILDREN} SET {columns} WHERE "
            "shot_revision_id = :__rid AND position = :__pos", params)
        con.commit()
    finally:
        con.close()


def _coherent_schema_float_rewrite(db_root, revision_id):
    """RR12-02's coherent shape: the Performance parent/snapshot
    discriminator goes from integer 2 to JSON 2.0 with the parent
    canonical hash and outer snapshot bytes/hash refreshed — children
    untouched."""
    from soloring.domain.canonical import (
        canonical_hash as ch, canonical_json_str as cj,
    )
    con = sqlite3.connect(db_root / "soloring.db")
    try:
        spec = json.loads(con.execute(
            f"SELECT spec_json FROM {_PARENTS} WHERE "
            "shot_revision_id = ?", (revision_id,)).fetchone()[0])
        snap = json.loads(con.execute(
            "SELECT snapshot_json FROM shot_revisions WHERE id = ?",
            (revision_id,)).fetchone()[0])
        assert spec["schema_version"] == 2
        assert snap["performance"]["schema_version"] == 2
        spec["schema_version"] = 2.0
        snap["performance"]["schema_version"] = 2.0
        con.execute(
            f"UPDATE {_PARENTS} SET spec_json = ?, spec_hash = ? "
            "WHERE shot_revision_id = ?",
            (cj(spec), ch(spec), revision_id))
        con.execute(
            "UPDATE shot_revisions SET snapshot_json = ?, "
            "snapshot_hash = ? WHERE id = ?",
            (cj(snap), ch(snap), revision_id))
        con.commit()
    finally:
        con.close()


# ---------------------------------------------------------------------------
# RR12-01 — the captured vocal preimage's persisted scalar law
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr1201_real_coordinate_refused_before_arithmetic(
        client, tmp_path):
    """The decisive adversary: a coherent SQLite REAL
    source_start_sample = 48000.5 — the child column REAL (typeof
    proven), the embedded vocal object carrying JSON 48000.5, the
    mapping hash rebuilt from the malformed preimage, and the
    complete segment/spec/snapshot hash chain recomputed. Both
    surfaces must refuse THROUGH THE SHARED SCALAR LAW — typed, and
    BEFORE the §8.3 Fraction arithmetic that previously raised a raw
    TypeError."""
    world, revision = await _stage_lawful(client)
    root = await _lawful_backup(client, tmp_path, "real-coordinate")

    # the lawful dialogue-bound control: green before the tamper
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 200, r.text

    updates = {"source_start_sample": 48000.5}
    _coherent_vocal_scalar_rewrite(
        _live_root(client), revision.id, 0, updates)

    con = sqlite3.connect(_live_root(client) / "soloring.db")
    try:
        stored = con.execute(
            f"SELECT typeof(source_start_sample) FROM {_CHILDREN} "
            "WHERE shot_revision_id = ? AND position = 0",
            (revision.id,)).fetchone()[0]
    finally:
        con.close()
    assert stored == "real", stored

    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 500, r.text
    message = r.json()["message"]
    assert "captured vocal preimage violates its persisted scalar " \
        "law" in message, message
    assert "source_start_sample 48000.5 is not a persisted integer" \
        in message, message

    _coherent_vocal_scalar_rewrite(root, revision.id, 0, updates)
    _verify_staged_raises(
        root, "captured vocal preimage violates its persisted scalar "
        "law: source_start_sample 48000.5 is not a persisted integer")


@pytest.mark.asyncio
@pytest.mark.parametrize("updates,fragment", [
    ({"vocal_performance_origin_num": 2,
      "vocal_performance_origin_den": 2},
     "captured vocal_performance_origin 2/2 is not in canonical "
     "reduced form"),
    ({"vocal_performance_origin_num": 0.5},
     "captured vocal_performance_origin 0.5/1 is not a persisted "
     "integer pair"),
])
async def test_rr1201_malformed_origin_refused_by_both(
        client, tmp_path, updates, fragment):
    """The origin adversaries: a coherent NONCANONICAL integer
    rational (2/2 — child columns and embedded value and all hashes
    rebuilt over it) and a coherent REAL scalar (0.5, typeof real).
    Both surfaces typed-refuse through the ONE shared captured-
    preimage law."""
    world, revision = await _stage_lawful(client)
    root = await _lawful_backup(client, tmp_path,
                                f"origin-{list(updates)[0]}")

    _coherent_vocal_scalar_rewrite(
        _live_root(client), revision.id, 0, updates)
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 500, r.text
    assert fragment in r.json()["message"], r.text

    _coherent_vocal_scalar_rewrite(root, revision.id, 0, updates)
    _verify_staged_raises(root, fragment)


# ---------------------------------------------------------------------------
# RR12-02 — the inner Performance schema discriminator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr1202_schema_float_refused_by_both(client, tmp_path):
    """The coherent discriminator rewrite: the Performance parent
    spec and outer snapshot both go from integer 2 to JSON 2.0 with
    the parent canonical hash and snapshot bytes/hash refreshed, all
    children untouched. Both §12 and recovery must refuse typed —
    2.0 == 2 is Python numeric equality, not the frozen integer the
    canonical writer emits."""
    world, revision = await _stage_lawful(client)
    root = await _lawful_backup(client, tmp_path, "schema-float")

    _coherent_schema_float_rewrite(_live_root(client), revision.id)
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 500, r.text
    assert "declares unknown schema 2.0" in r.json()["message"], \
        r.text

    _coherent_schema_float_rewrite(root, revision.id)
    _verify_staged_raises(root, "unknown schema")


# ---------------------------------------------------------------------------
# Lawful controls
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr12_lawful_controls_green(client):
    """The lawful dialogue-bound captured history stays green under
    the new scalar law (integer coordinates/rate/position, canonical
    origin, integer discriminator 2), at both surfaces."""
    from soloring.recovery.m17c_verifier import verify_m17c_binding_state

    world, revision = await _stage_lawful(client)
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 200, r.text
    seg = r.json()["performance"]["segments"][0]
    assert seg["vocal"]["vocal_performance_revision"][
        "native_sample_rate_hz"] == 48000

    import tempfile
    from pathlib import Path
    from tests.test_m17c_sr26_regressions import _backup_m17c
    tmp = Path(tempfile.mkdtemp())
    root = await _backup_m17c(client, tmp, "rr12-clean")
    verify_m17c_binding_state(
        root / "soloring.db", root / "blobs", head=_HEAD)
