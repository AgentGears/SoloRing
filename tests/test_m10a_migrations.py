"""M10A migration gate tests (frozen r3 §7.4 / §102.3).

0010/0011 create only new tables; predecessor rows remain byte-identical;
downgrades are lossless-or-refused with the preflight running BEFORE any DDL.
"""
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

BASE_DIR = Path(__file__).resolve().parents[1]
VERSIONS = BASE_DIR / "server" / "alembic" / "versions"
PY = sys.executable


def _cfg() -> Config:
    cfg = Config(str(BASE_DIR / "server" / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "server" / "alembic"))
    return cfg


def _point_at(data_dir: Path, monkeypatch) -> None:
    import soloring.settings as settings_mod

    monkeypatch.setenv("SOLORING_DATA_DIR", str(data_dir))
    monkeypatch.setattr(settings_mod, "_settings", None)


def _upgrade(tmp_path, monkeypatch, target="head"):
    _point_at(tmp_path, monkeypatch)
    command.upgrade(_cfg(), target)


def _downgrade(tmp_path, monkeypatch, target):
    _point_at(tmp_path, monkeypatch)
    command.downgrade(_cfg(), target)


def test_migrations_present_and_chained():
    files = sorted(p.name for p in VERSIONS.glob("0*.py"))
    assert files[-2:] == ["0011_m10_derived_spatial_execution.py",
                          "0012_m11_reusable_production_revisions.py"]
    m10 = (VERSIONS / "0010_m10_spatial_cinematic_continuity.py").read_text()
    assert 'down_revision: Union[str, None] = "0009_m8_visual_identity"' in m10
    m11 = (VERSIONS / "0011_m10_derived_spatial_execution.py").read_text()
    assert 'down_revision: Union[str, None] = "0010_m10_spatial_cinematic_continuity"' in m11


def test_head_creates_all_17_m10_tables(tmp_path, monkeypatch):
    db = tmp_path / "soloring.db"
    _upgrade(tmp_path, monkeypatch)
    con = sqlite3.connect(db)
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    expected = {
        "spatial_worlds", "spatial_world_states", "spatial_frames",
        "spatial_world_state_frames", "spatial_axes", "spatial_world_state_axes",
        "spatial_world_revisions", "spatial_world_revision_frames",
        "spatial_world_revision_axes", "spatial_tracks", "spatial_transitions",
        "shot_spatial_plans", "shot_revision_spatial_worlds",
        "shot_revision_spatial_track_states", "shot_revision_spatial_plans",
        "derived_spatial_artifacts", "generation_derived_spatial_inputs",
    }
    assert expected <= tables


def test_partial_uniques_exist(tmp_path, monkeypatch):
    db = tmp_path / "soloring.db"
    _upgrade(tmp_path, monkeypatch)
    con = sqlite3.connect(db)
    idx = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL")}
    con.close()
    for name in ("uq_spatial_worlds_active_location", "uq_swsf_one_bound_entity",
                 "uq_st_active_world_entity", "uq_str_active_coordinate"):
        assert name in idx, name


def test_empty_schema_downgrades_cleanly_to_0009(tmp_path, monkeypatch):
    db = tmp_path / "soloring.db"
    _upgrade(tmp_path, monkeypatch)
    _downgrade(tmp_path, monkeypatch, "0009_m8_visual_identity")
    con = sqlite3.connect(db)
    ver = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    left = con.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND "
        "(name LIKE 'spatial_%' OR name LIKE 'shot_revision_spatial%' OR "
        " name LIKE 'shot_spatial%' OR name = 'derived_spatial_artifacts' OR "
        " name = 'generation_derived_spatial_inputs')").fetchone()[0]
    con.close()
    assert ver == "0009_m8_visual_identity"
    assert left == 0


def test_populated_m10_table_refuses_downgrade(tmp_path, monkeypatch):
    db = tmp_path / "soloring.db"
    _upgrade(tmp_path, monkeypatch)
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys=OFF")
    con.execute("INSERT INTO spatial_worlds (id, project_id, location_entity_id, key,"
                " name, requirement, created_at, updated_at) VALUES"
                " ('w1','p1','e1','lobby','Lobby','optional','t','t')")
    con.commit()
    con.close()
    with pytest.raises(RuntimeError, match="refused.*spatial_worlds"):
        _downgrade(tmp_path, monkeypatch, "0009_m8_visual_identity")
    con = sqlite3.connect(db)
    ver = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    con.close()
    assert ver == "0010_m10_spatial_cinematic_continuity"  # 0011 (empty) dropped; 0010 DDL never ran


def test_schema5_snapshot_refuses_0010_downgrade(tmp_path, monkeypatch):
    db = tmp_path / "soloring.db"
    _upgrade(tmp_path, monkeypatch)
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys=OFF")
    con.execute("INSERT INTO shot_revisions (id, shot_id, revision_number, snapshot_json,"
                " snapshot_hash, created_at) VALUES ('r1','s1',1,?, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','t')",
                (json.dumps({"schema_version": 5}),))
    con.commit()
    con.close()
    with pytest.raises(RuntimeError, match="refused"):
        _downgrade(tmp_path, monkeypatch, "0009_m8_visual_identity")


def test_malformed_snapshot_is_refusal_not_crash(tmp_path, monkeypatch):
    db = tmp_path / "soloring.db"
    _upgrade(tmp_path, monkeypatch)
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys=OFF")
    con.execute("INSERT INTO shot_revisions (id, shot_id, revision_number, snapshot_json,"
                " snapshot_hash, created_at) VALUES ('r1','s1',1,'not json', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','t')")
    con.commit()
    con.close()
    with pytest.raises(RuntimeError, match="refused.*malformed"):
        _downgrade(tmp_path, monkeypatch, "0009_m8_visual_identity")


def test_populated_0011_refuses_0011_downgrade(tmp_path, monkeypatch):
    db = tmp_path / "soloring.db"
    _upgrade(tmp_path, monkeypatch)
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys=OFF")
    con.execute("INSERT INTO derived_spatial_artifacts (id, project_id,"
                " spec_schema_version, spec_json, spec_hash,"
                " spatial_continuity_schema_version, spatial_continuity_hash,"
                " artifact_kind, artifact_schema_version, algorithm_id,"
                " algorithm_version, runtime_fingerprint_json,"
                " runtime_fingerprint_hash, determinism_class, blob_hash,"
                " media_type, created_at) VALUES"
                " ('a1','p1',1,'{}','" + "x" * 64 + "',1,'" + "y" * 64 + "',"
                "'boxdepth_control_video',1,'soloring.boxdepth.rasterizer','1.0.0',"
                "'{}','" + "z" * 64 + "','D0','" + "b" * 64 + "','application/x-npy','t')")
    con.commit()
    con.close()
    with pytest.raises(RuntimeError, match="refused.*derived_spatial_artifacts"):
        _downgrade(tmp_path, monkeypatch, "0010_m10_spatial_cinematic_continuity")
    con = sqlite3.connect(db)
    ver = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    con.close()
    assert ver == "0011_m10_derived_spatial_execution"


def test_d0_only_check_enforced(tmp_path, monkeypatch):
    db = tmp_path / "soloring.db"
    _upgrade(tmp_path, monkeypatch)
    con = sqlite3.connect(db)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO derived_spatial_artifacts (id, project_id,"
                    " spec_schema_version, spec_json, spec_hash,"
                    " spatial_continuity_schema_version, spatial_continuity_hash,"
                    " artifact_kind, artifact_schema_version, algorithm_id,"
                    " algorithm_version, runtime_fingerprint_json,"
                    " runtime_fingerprint_hash, determinism_class, blob_hash,"
                    " media_type, created_at) VALUES"
                    " ('a1','p1',1,'{}','" + "x" * 64 + "',1,'" + "y" * 64 + "',"
                    "'k',1,'alg','1','{}','" + "z" * 64 + "','D1','" + "b" * 64 + "',"
                    "'m','t')")
    con.close()


def test_transition_operation_shape_check(tmp_path, monkeypatch):
    db = tmp_path / "soloring.db"
    _upgrade(tmp_path, monkeypatch)
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys=OFF")
    con.execute("INSERT INTO spatial_tracks (id, spatial_world_id, entity_id,"
                " requirement, created_at, updated_at) VALUES"
                " ('t1','w1','e1','optional','t','t')")
    # 'set' with NULL transforms violates the shape CHECK
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO spatial_transitions (id, spatial_track_id, anchor_type,"
                    " anchor_id, boundary, operation, created_at, updated_at)"
                    " VALUES ('x1','t1','shot','s1','start','set','t','t')")
    con.close()
