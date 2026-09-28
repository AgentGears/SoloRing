"""M17C-B recovery battery (B-F7, frozen under the PR #26 primary
review).

- Clean backup/restore round trip preserving PF-02 working-mapping
  rows byte-for-byte at head 0021.
- Lawful BLOCKED working states (paired vocal mapping deleted through
  the supported API) survive a full round trip as blocked working
  state — recovery preserves them (B-F4).
- Staged migration proof: a REAL 0020-stamped database (frozen c502b81
  identity; working-mapping table lawfully absent) upgraded to 0021
  retains every PF-03 row, gains the working-mapping table, and passes
  the full M17C recovery verifier afterwards. No rebuild of valid
  M17C-A databases is required.
- Adversarial matrix: recovery refuses canonical-hash tamper,
  noncanonical persisted rational, cross-project performance revision
  (coherently rehashed so only the project law can refuse), both
  mode/position shape violations (coherently rehashed), and a paired
  vocal mapping whose VP diverges from the immutable revision binding.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from soloring.domain.canonical import canonical_hash, canonical_json_str
from tests.test_m17c_sr26_regressions import _backup_m17c, _restore_refuses
from tests.test_m17c_shot_mapping import (
    _bound_world,
    _generic_world,
    _seg_body,
)

_HEAD_0021 = "0021_m17c_shot_performance_mappings"
_HEAD_0020 = "0020_m17c_perf_capture_r2"
_TABLE = "shot_performance_segment_mappings"


async def _lawful_put(client, world):
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 1000, 0, vp=0))
    assert r.status_code == 200, r.text


def _doc(pr_id, s_num=0, s_den=1, e_num=1000, e_den=1,
         a_num=0, a_den=1, vocal_position=0):
    return {
        "mapping_schema_version": 1,
        "performance_revision_id": pr_id,
        "performance_start_ms": {"num": s_num, "den": s_den},
        "performance_end_ms": {"num": e_num, "den": e_den},
        "shot_anchor_ms": {"num": a_num, "den": a_den},
        "vocal_mapping_position": vocal_position,
    }


def _tamper(root: Path, stmt: str, params: tuple) -> None:
    con = sqlite3.connect(root / "soloring.db")
    con.execute(stmt, params)
    con.commit()
    con.close()


# ---------------------------------------------------------------------------
# Clean round trip at head 0021
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bf07_clean_roundtrip_preserves_working_mappings(
        client, tmp_path):
    from soloring.recovery import restore as rb_restore
    world = await _bound_world(client)
    await _lawful_put(client, world)
    root = await _backup_m17c(client, tmp_path, "bf-clean")

    before = sqlite3.connect(root / "soloring.db")
    before.row_factory = sqlite3.Row
    row_before = dict(before.execute(
        f"SELECT * FROM {_TABLE} WHERE shot_id = ? AND position = 0",
        (world["shot"],)).fetchone())
    before.close()

    dest = tmp_path / "restored"
    await rb_restore(root, dest)
    con = sqlite3.connect(dest / "soloring.db")
    con.row_factory = sqlite3.Row
    try:
        head = con.execute(
            "SELECT version_num FROM alembic_version").fetchone()[0]
        row_after = dict(con.execute(
            f"SELECT * FROM {_TABLE} WHERE shot_id = ? AND position = 0",
            (world["shot"],)).fetchone())
    finally:
        con.close()
    assert head == _HEAD_0021
    assert row_after == row_before


# ---------------------------------------------------------------------------
# B-F4/B-F7: lawful BLOCKED working state round trips
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bf07_blocked_missing_pair_state_roundtrips(
        client, tmp_path):
    from soloring.recovery import restore as rb_restore
    world = await _bound_world(client)
    await _lawful_put(client, world)
    d = await client.delete(f"/shots/{world['shot']}/vocal-segments/0")
    assert d.status_code == 204, d.text
    readiness = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert readiness["segments"][0]["readiness"] == \
        "BLOCKED_BINDING_INTEGRITY"

    root = await _backup_m17c(client, tmp_path, "bf-blocked")
    dest = tmp_path / "restored"
    await rb_restore(root, dest)  # lawful blocked state: restore passes
    con = sqlite3.connect(dest / "soloring.db")
    try:
        mapping = con.execute(
            f"SELECT COUNT(*) FROM {_TABLE} WHERE shot_id = ?",
            (world["shot"],)).fetchone()[0]
        vocal = con.execute(
            "SELECT COUNT(*) FROM shot_vocal_segment_mappings "
            "WHERE shot_id = ?", (world["shot"],)).fetchone()[0]
    finally:
        con.close()
    assert mapping == 1
    assert vocal == 0


# ---------------------------------------------------------------------------
# Staged migration proof: real 0020 database -> 0021
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bf07_staged_0020_upgrades_to_0021_retaining_pf03(
        client, tmp_path):
    from soloring.recovery.m17c_verifier import verify_m17c_binding_state
    world = await _bound_world(client)
    root = await _backup_m17c(client, tmp_path, "bf-staged")

    # reshape the backup into a REAL 0020-stamped database: stamp the
    # frozen c502b81 identity and remove the table 0021 creates (a
    # 0020 database never had it)
    con = sqlite3.connect(root / "soloring.db")
    con.execute("UPDATE alembic_version SET version_num = ?",
                (_HEAD_0020,))
    con.execute(f"DROP TABLE {_TABLE}")
    con.commit()
    pf03_before = {
        "candidate_binding": con.execute(
            "SELECT binding_hash FROM performance_candidate_vocal_bindings"
            " WHERE performance_candidate_id = ?",
            (world["candidate"]["id"],)).fetchone()[0],
        "revision_binding": con.execute(
            "SELECT binding_hash FROM performance_revision_vocal_bindings"
            " WHERE performance_revision_id = ?",
            (world["pr"]["id"],)).fetchone()[0],
    }
    con.close()

    repo = Path(__file__).resolve().parents[1]
    env = {
        "SystemRoot": "C:\\Windows",
        "SOLORING_DATABASE_URL":
            f"sqlite:///{(root / 'soloring.db').as_posix()}",
        "SOLORING_DATA_DIR": root.as_posix(),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    up = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(repo / "server"), capture_output=True, text=True, env=env)
    assert up.returncode == 0, up.stderr[-800:]

    con = sqlite3.connect(root / "soloring.db")
    con.row_factory = sqlite3.Row
    try:
        head = con.execute(
            "SELECT version_num FROM alembic_version").fetchone()[0]
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        mappings = con.execute(
            f"SELECT COUNT(*) FROM {_TABLE}").fetchone()[0]
        pf03_after = {
            "candidate_binding": con.execute(
                "SELECT binding_hash FROM "
                "performance_candidate_vocal_bindings WHERE "
                "performance_candidate_id = ?",
                (world["candidate"]["id"],)).fetchone()[0],
            "revision_binding": con.execute(
                "SELECT binding_hash FROM "
                "performance_revision_vocal_bindings WHERE "
                "performance_revision_id = ?",
                (world["pr"]["id"],)).fetchone()[0],
        }
        modes = [r[0] for r in con.execute(
            "SELECT sync_mode FROM "
            "performance_revision_sync_classifications")]
    finally:
        con.close()
    assert head == _HEAD_0021
    assert _TABLE in tables
    assert mappings == 0
    assert pf03_after == pf03_before
    assert modes == ["VOCAL_V1"]
    # the upgraded database passes the FULL M17C recovery verification
    # at its exact head (successor semantics chain + binding verifier +
    # 0021 schema proof + empty mapping pass)
    verify_m17c_binding_state(root / "soloring.db", root / "blobs",
                              head=_HEAD_0021)


# ---------------------------------------------------------------------------
# Adversarial matrix — recovery refuses
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bf07_refuses_mapping_hash_tamper(client, tmp_path):
    world = await _bound_world(client)
    await _lawful_put(client, world)
    root = await _backup_m17c(client, tmp_path, "bf-hash")
    _tamper(
        root,
        f"UPDATE {_TABLE} SET mapping_hash = ? "
        "WHERE shot_id = ? AND position = 0",
        ("d" * 64, world["shot"]))
    exc = await _restore_refuses(root, tmp_path, "bf-hash")
    assert "canonical bytes/hash diverge" in str(exc)


@pytest.mark.asyncio
async def test_bf07_refuses_noncanonical_rational(client, tmp_path):
    world = await _bound_world(client)
    await _lawful_put(client, world)
    root = await _backup_m17c(client, tmp_path, "bf-rat")
    _tamper(
        root,
        f"UPDATE {_TABLE} SET performance_start_num = 0, "
        "performance_start_den = 5 WHERE shot_id = ? AND position = 0",
        (world["shot"],))
    exc = await _restore_refuses(root, tmp_path, "bf-rat")
    assert "stores a noncanonical rational" in str(exc)


@pytest.mark.asyncio
async def test_bf07_refuses_cross_project_revision(client, tmp_path):
    """Retarget the mapping to a REAL PerformanceRevision of another
    project with canonical JSON/hash coherently recomputed, so ONLY the
    project law can refuse."""
    from tests.m17b_seed import (
        SMILE,
        candidate_body,
        channel as m17b_channel,
        kf as m17b_kf,
        make_entity,
    )
    world = await _bound_world(client)
    await _lawful_put(client, world)
    other_project = (await client.post(
        "/projects", json={"name": "BFOther"})).json()
    other_entity = await make_entity(
        client, other_project["id"], "OtherSubject")
    other_candidate = (await client.post(
        f"/creative-entities/{other_entity}/performance-candidates",
        json=candidate_body(
            [m17b_channel(SMILE, [m17b_kf(0, 1, 0)])]),
    )).json()
    other_pr = (await client.post(
        f"/performance-candidates/{other_candidate['id']}/adopt",
        json={"adopted_by": "bf"})).json()

    root = await _backup_m17c(client, tmp_path, "bf-xproj")
    doc = _doc(other_pr["id"])
    _tamper(
        root,
        f"UPDATE {_TABLE} SET performance_revision_id = ?, "
        "mapping_json = ?, mapping_hash = ? "
        "WHERE shot_id = ? AND position = 0",
        (other_pr["id"], canonical_json_str(doc), canonical_hash(doc),
         world["shot"]))
    exc = await _restore_refuses(root, tmp_path, "bf-xproj")
    assert "crosses projects" in str(exc)


@pytest.mark.asyncio
async def test_bf07_refuses_v1_null_position_shape(client, tmp_path):
    world = await _bound_world(client)
    await _lawful_put(client, world)
    root = await _backup_m17c(client, tmp_path, "bf-shape1")
    doc = _doc(world["pr"]["id"], vocal_position=None)
    _tamper(
        root,
        f"UPDATE {_TABLE} SET vocal_mapping_position = NULL, "
        "mapping_json = ?, mapping_hash = ? "
        "WHERE shot_id = ? AND position = 0",
        (canonical_json_str(doc), canonical_hash(doc), world["shot"]))
    exc = await _restore_refuses(root, tmp_path, "bf-shape1")
    assert "without vocal_mapping_position" in str(exc)


@pytest.mark.asyncio
async def test_bf07_refuses_generic_position_shape(client, tmp_path):
    world = await _generic_world(client)
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 2000, 0))
    assert r.status_code == 200, r.text
    root = await _backup_m17c(client, tmp_path, "bf-shape2")
    doc = _doc(world["pr"]["id"], e_num=2000, vocal_position=0)
    _tamper(
        root,
        f"UPDATE {_TABLE} SET vocal_mapping_position = 0, "
        "mapping_json = ?, mapping_hash = ? "
        "WHERE shot_id = ? AND position = 0",
        (canonical_json_str(doc), canonical_hash(doc), world["shot"]))
    exc = await _restore_refuses(root, tmp_path, "bf-shape2")
    assert "carries vocal_mapping_position but the PerformanceRevision " \
        "is not VOCAL_V1" in str(exc)


# NOTE (SR2-03 supersession): this file previously carried
# test_bf07_refuses_paired_vp_divergence, which coherently rehashed a
# paired vocal mapping to a REAL alternate VP and asserted restore
# refusal. The M17C-B second review overturned that premise: the
# supported M17A vocal PUT can lawfully repoint an existing working
# vocal position to the now-current selection, so paired-VP divergence
# is mutable working drift — live readiness reports
# BLOCKED_BINDING_INTEGRITY and recovery preserves the row. The
# end-to-end API lifecycle + backup/restore proof now lives in
# tests/test_m17c_sr2_regressions.py (SR2-03).
