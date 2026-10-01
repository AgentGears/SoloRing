"""M17C-C migration 0022 schema-8 capture storage laws (slice 1,
schema/storage-only per the sequencing contract)."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / "server"
PY = sys.executable
HEAD = "0023_m17cc_capture_closure_preimage"
TABLES = {
    "shot_revision_performance_specs",
    "shot_revision_performance_segments",
    "generation_performance_inputs",
}


def _run(db: Path, *args: str, expect: int = 0):
    env = {
        "SystemRoot": "C:\\Windows",
        "SOLORING_DATABASE_URL": f"sqlite:///{db.as_posix()}",
        "SOLORING_DATA_DIR": db.parent.as_posix(),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(
        [PY, "-m", "alembic", *args],
        cwd=SERVER,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == expect, (result.stderr or "")[-2000:]
    result.stdout = result.stdout or ""
    result.stderr = result.stderr or ""
    return result


def test_m17cc_0022_fresh_upgrade_creates_capture_tables(tmp_path):
    db = tmp_path / "m17cc.db"
    _run(db, "upgrade", "head")
    con = sqlite3.connect(db)
    version = con.execute(
        "SELECT version_num FROM alembic_version").fetchone()[0]
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    assert version == HEAD
    assert TABLES <= tables
    # the M17C-B surfaces are untouched by the successor step
    assert "shot_performance_segment_mappings" in tables
    assert "performance_candidate_vocal_bindings" in tables


def test_m17cc_0022_empty_downgrade_succeeds(tmp_path):
    db = tmp_path / "m17cc-empty.db"
    _run(db, "upgrade", "head")
    _run(db, "downgrade", "0021_m17c_shot_performance_mappings")
    con = sqlite3.connect(db)
    version = con.execute(
        "SELECT version_num FROM alembic_version").fetchone()[0]
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    assert version == "0021_m17c_shot_performance_mappings"
    assert not (TABLES & tables)
    assert "shot_performance_segment_mappings" in tables


def test_m17cc_0022_populated_specs_refuse_downgrade(tmp_path):
    db = tmp_path / "m17cc-spec.db"
    _run(db, "upgrade", "head")
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO shot_revision_performance_specs ("
        "shot_revision_id, schema_version, spec_json, spec_hash) "
        "VALUES ('r', 1, '{}', '" + "a" * 64 + "')")
    con.commit()
    con.close()
    result = _run(db, "downgrade",
                  "0021_m17c_shot_performance_mappings", expect=1)
    assert "shot_revision_performance_specs" in \
        (result.stdout + result.stderr)
    con = sqlite3.connect(db)
    assert con.execute(
        "SELECT version_num FROM alembic_version").fetchone()[0] == HEAD
    con.close()


def test_m17cc_0022_populated_segments_refuse_downgrade(tmp_path):
    db = tmp_path / "m17cc-seg.db"
    _run(db, "upgrade", "head")
    con = sqlite3.connect(db)
    # isolate the SEGMENTS fence: raw sqlite3 starts with foreign_keys
    # OFF, so a child row WITHOUT its parent is insertable and the
    # specs fence (count 0) passes, refusing exactly at segments
    con.execute(
        "INSERT INTO shot_revision_performance_segments ("
        "shot_revision_id, position, subject_id, "
        "performance_revision_id, performance_payload_blob_hash, "
        "performance_payload_sha256, performance_profile_id, "
        "performance_kind, performance_start_num, "
        "performance_start_den, performance_end_num, "
        "performance_end_den, shot_anchor_num, shot_anchor_den, "
        "performance_mapping_hash, segment_json, segment_hash) "
        "VALUES ('r', 0, 's', 'p', '" + "b" * 64 + "', '" + "b" * 64 +
        "', 'performance-profile/1', 'FACIAL', 0, 1, 1000, 1, 0, 1, '" +
        "c" * 64 + "', '{}', '" + "c" * 64 + "')")
    con.commit()
    con.close()
    result = _run(db, "downgrade",
                  "0021_m17c_shot_performance_mappings", expect=1)
    assert "shot_revision_performance_segments" in \
        (result.stdout + result.stderr)
    con = sqlite3.connect(db)
    assert con.execute(
        "SELECT version_num FROM alembic_version").fetchone()[0] == HEAD
    con.close()


def test_m17cc_0022_populated_derived_inputs_refuse_downgrade(tmp_path):
    db = tmp_path / "m17cc-gpi.db"
    _run(db, "upgrade", "head")
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO generation_performance_inputs ("
        "generation_id, input_key, position, artifact_role, "
        "shot_revision_segment_position, performance_revision_id, "
        "blob_hash, segment_hash, translation_identity, "
        "derived_input_hash, created_at) VALUES "
        "('g', 'performance.controls', 0, 'performance.controls', 0, "
        "'p', '" + "d" * 64 + "', '" + "e" * 64 + "', 't/1', '" +
        "f" * 64 + "', '2026-01-01T00:00:00.000Z')")
    con.commit()
    con.close()
    result = _run(db, "downgrade",
                  "0021_m17c_shot_performance_mappings", expect=1)
    assert "generation_performance_inputs" in \
        (result.stdout + result.stderr)
    con = sqlite3.connect(db)
    assert con.execute(
        "SELECT version_num FROM alembic_version").fetchone()[0] == HEAD
    con.close()


def test_m17cc_0022_segment_vocal_group_all_or_none_check(tmp_path):
    """The dialogue-bound vocal group is one all-or-none group at the
    STORAGE layer: a half-populated row is mechanically unlawful."""
    db = tmp_path / "m17cc-check.db"
    _run(db, "upgrade", "head")
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO shot_revision_performance_specs ("
        "shot_revision_id, schema_version, spec_json, spec_hash) "
        "VALUES ('r', 1, '{}', '" + "a" * 64 + "')")
    import pytest
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO shot_revision_performance_segments ("
            "shot_revision_id, position, subject_id, "
            "performance_revision_id, performance_payload_blob_hash, "
            "performance_payload_sha256, performance_profile_id, "
            "performance_kind, performance_start_num, "
            "performance_start_den, performance_end_num, "
            "performance_end_den, shot_anchor_num, shot_anchor_den, "
            "performance_mapping_hash, vocal_performance_revision_id, "
            "segment_json, segment_hash) "
            "VALUES ('r', 0, 's', 'p', '" + "b" * 64 + "', '" + "b" * 64 +
            "', 'performance-profile/1', 'FACIAL', 0, 1, 1000, 1, 0, 1, '" +
            "c" * 64 + "', 'v', '{}', '" + "c" * 64 + "')")
    con.close()


def test_m17cc_0022_staged_real_0021_upgrade_preserves_m17cb_rows(
        client, tmp_path):
    """A REAL 0021-staged database (a lawful M17C-B backup reshaped to
    the 0021 identity) upgraded to 0022 retains every M17C-B row and
    passes the M17C verifier at its exact head."""
    from soloring.recovery.m17c_verifier import verify_m17c_binding_state
    from tests.test_m17c_shot_mapping import _bound_world, _seg_body
    from tests.test_m17c_sr26_regressions import _backup_m17c

    async def _stage():
        world = await _bound_world(client)
        r = await client.put(
            f"/shots/{world['shot']}/performance-segments/0",
            json=_seg_body(world["pr"]["id"], 0, 1000, 0, vp=0))
        assert r.status_code == 200, r.text
        root = await _backup_m17c(client, tmp_path, "m17cc-stage")
        return root, world

    import asyncio
    loop = asyncio.new_event_loop()
    try:
        root, world = loop.run_until_complete(_stage())
    finally:
        loop.close()
    # reshape the (create_all-schema) backup into a GENUINE 0021
    # database: drop the three tables successor 0022 creates, stamp
    # 0021, and rewrite the manifest canonically with the recomputed
    # database hash (mirrors _retarget_backup's contract)
    import hashlib
    import json

    from soloring.domain.canonical import canonical_json_bytes
    con = sqlite3.connect(root / "soloring.db")
    for t in TABLES:
        con.execute(f"DROP TABLE {t}")
    con.execute("UPDATE alembic_version SET version_num = ?",
                ("0021_m17c_shot_performance_mappings",))
    con.commit()
    con.close()
    manifest_path = root / "backup-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["alembic_version"] = "0021_m17c_shot_performance_mappings"
    manifest["database_sha256"] = hashlib.sha256(
        (root / "soloring.db").read_bytes()).hexdigest()
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    env = {
        "SystemRoot": "C:\\Windows",
        "SOLORING_DATABASE_URL":
            f"sqlite:///{(root / 'soloring.db').as_posix()}",
        "SOLORING_DATA_DIR": root.as_posix(),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    up = subprocess.run(
        [PY, "-m", "alembic", "upgrade", "head"],
        cwd=SERVER, capture_output=True, text=True, env=env)
    assert up.returncode == 0, up.stderr[-800:]

    con = sqlite3.connect(root / "soloring.db")
    try:
        head = con.execute(
            "SELECT version_num FROM alembic_version").fetchone()[0]
        assert head == HEAD
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert TABLES <= tables
        bindings = con.execute(
            "SELECT COUNT(*) FROM performance_revision_vocal_bindings "
            "WHERE performance_revision_id = ?",
            (world["pr"]["id"],)).fetchone()[0]
        mappings = con.execute(
            "SELECT COUNT(*) FROM shot_performance_segment_mappings "
            "WHERE shot_id = ?", (world["shot"],)).fetchone()[0]
    finally:
        con.close()
    assert bindings == 1
    assert mappings == 1
    # the upgraded database passes the M17C verifier at 0022
    # (0021-equivalent semantics; the capture tables carry no rows)
    verify_m17c_binding_state(root / "soloring.db",
                              root / "blobs", head=HEAD)
