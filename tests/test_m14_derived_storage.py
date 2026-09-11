"""M14B-2 — derived observation storage + migration 0015 (frozen R2
§§22/23; proof cells MAT:11/12/13, HIST:09/11, EXEC:04).

Convergence identity (same complete coordinate + same bytes converges;
same coordinate + different bytes is an invariant failure), the composite
artifact-id/Blob-hash FK binding, the three-condition fail-closed
downgrade preflight, the eight-path recovery Blob-FK inventory, and the
structural no-fake-Asset proof.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from soloring.domain.canonical import canonical_hash, canonical_json_str

BASE_DIR = Path(__file__).resolve().parents[1]
NOW = "2026-09-10T00:00:00Z"


def _cfg() -> Config:
    cfg = Config(str(BASE_DIR / "server" / "alembic.ini"))
    cfg.set_main_option("script_location",
                        str(BASE_DIR / "server" / "alembic"))
    return cfg


def _point_at(data_dir, monkeypatch) -> None:
    import soloring.settings as settings_mod

    monkeypatch.setenv("SOLORING_DATA_DIR", str(data_dir))
    monkeypatch.setattr(settings_mod, "_settings", None)


def _upgrade(tmp_path, monkeypatch, target="head"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    _point_at(tmp_path, monkeypatch)
    command.upgrade(_cfg(), target)


def _downgrade(tmp_path, monkeypatch, target):
    _point_at(tmp_path, monkeypatch)
    command.downgrade(_cfg(), target)


def _con(tmp_path):
    con = sqlite3.connect(tmp_path / "soloring.db")
    con.row_factory = sqlite3.Row
    return con


def _connect(db):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return conn


async def _seed_project_and_blob(db, *, blob=b"mesh-depth-bytes") -> tuple:
    conn = _connect(db)
    pid = str(uuid.uuid4())
    blob_hash = __import__("hashlib").sha256(blob).hexdigest()
    conn.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) "
        "VALUES (?, 'P', ?, ?)", (pid, NOW, NOW))
    conn.execute(
        "INSERT INTO blobs (hash, path, size_bytes, detected_media_type, "
        "created_at) VALUES (?, ?, ?, NULL, ?)",
        (blob_hash, f"sha256/{blob_hash[:2]}/{blob_hash[2:4]}/{blob_hash}",
         len(blob), NOW))
    conn.commit()
    conn.close()
    return pid, blob_hash


def _coordinate(project_id: str, spec_hash: str, *, contract="a" * 64,
                params="b" * 64) -> dict:
    return {
        "project_id": project_id,
        "observation_spec_hash": spec_hash,
        "artifact_role": "observation.world_depth",
        "materializer_id": "soloring.observation.mesh_depth",
        "materializer_version": 1,
        "materializer_contract_hash": contract,
        "parameters_hash": params,
    }


def _insert_artifact(db, coordinate: dict, *, artifact_id=None,
                      blob_hash=None, provenance=None) -> str:
    conn = _connect(db)
    artifact_id = artifact_id or str(uuid.uuid4())
    blob_hash = blob_hash or "c" * 64
    parameters = {"width": 832, "height": 480, "frames": 17,
                  "time_base_num": 1, "time_base_den": 17, "mode": "L",
                  "background": 255}
    provenance = provenance or {"project_id": coordinate["project_id"]}
    conn.execute(
        "INSERT INTO derived_observation_artifacts "
        "(id, project_id, observation_spec_hash, artifact_role, "
        "materializer_id, materializer_version, "
        "materializer_contract_hash, parameters_json, parameters_hash, "
        "provenance_json, provenance_hash, blob_hash, created_at) VALUES "
        "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (artifact_id, coordinate["project_id"],
         coordinate["observation_spec_hash"],
         coordinate["artifact_role"], coordinate["materializer_id"],
         coordinate["materializer_version"],
         coordinate["materializer_contract_hash"],
         canonical_json_str(parameters), coordinate["parameters_hash"],
         canonical_json_str(provenance), canonical_hash(provenance),
         blob_hash, NOW))
    conn.commit()
    conn.close()
    return artifact_id


# ---- upgrade + schema/constraint evidence ---------------------------------

async def test_migration_upgrade_creates_exact_schema(tmp_path, monkeypatch):
    db = tmp_path / "soloring.db"; _upgrade(tmp_path, monkeypatch)
    conn = _connect(db)
    head = conn.execute(
        "SELECT version_num FROM alembic_version").fetchone()[0]
    assert head == "0015_m14_world_observation_execution"

    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "derived_observation_artifacts" in tables
    assert "generation_derived_observation_inputs" in tables

    # composite FK on (artifact_id, blob_hash) is DB-enforced; the Blob
    # is pinned through the artifact row (no independent blobs FK — the
    # physical FK inventory stays exactly eight paths)
    fks = {(r["from"], r["table"]) for r in conn.execute(
        "PRAGMA foreign_key_list('generation_derived_observation_inputs')")}
    assert fks == {
        ("derived_observation_artifact_id",
         "derived_observation_artifacts"),
        ("blob_hash", "derived_observation_artifacts"),
        ("generation_id", "generations")}

    # convergence coordinate uniqueness is DB-enforced
    indexes = [r["sql"] for r in conn.execute(
        "SELECT sql FROM sqlite_master WHERE tbl_name = "
        "'derived_observation_artifacts' AND sql LIKE '%uq_doa%'")]
    assert any("parameters_hash" in sql and
               "materializer_contract_hash" in sql for sql in indexes)
    conn.close()


async def test_same_coordinate_same_bytes_converges(tmp_path, monkeypatch):
    """MAT:11 — identical concurrent publication converges on one row.

    The storage contract is convergence-by-identity: a second insert of
    the SAME complete coordinate with the SAME bytes is the convergence
    case (INSERT OR IGNORE — one row, same id) and any second row with
    different bytes is an invariant failure."""
    db = tmp_path / "soloring.db"; _upgrade(tmp_path, monkeypatch)
    pid, blob_hash = await _seed_project_and_blob(db)
    coordinate = _coordinate(pid, "d" * 64)
    first_id = _insert_artifact(db, coordinate, blob_hash=blob_hash)

    # convergence: same coordinate + same bytes is idempotent
    conn = _connect(db)
    second_id = str(uuid.uuid4())
    conn.execute(
        "INSERT OR IGNORE INTO derived_observation_artifacts "
        "(id, project_id, observation_spec_hash, artifact_role, "
        "materializer_id, materializer_version, "
        "materializer_contract_hash, parameters_json, parameters_hash, "
        "provenance_json, provenance_hash, blob_hash, created_at) VALUES "
        "(?, ?, ?, ?, ?, ?, ?, "
        "(SELECT parameters_json FROM derived_observation_artifacts "
        " WHERE id = ?), ?, "
        "(SELECT provenance_json FROM derived_observation_artifacts "
        " WHERE id = ?), ?, ?, ?)",
        (second_id, coordinate["project_id"],
         coordinate["observation_spec_hash"], coordinate["artifact_role"],
         coordinate["materializer_id"], coordinate["materializer_version"],
         coordinate["materializer_contract_hash"], first_id,
         coordinate["parameters_hash"], first_id,
         "0" * 64, blob_hash, NOW))
    conn.commit()
    count = conn.execute(
        "SELECT COUNT(*) FROM derived_observation_artifacts WHERE "
        "observation_spec_hash = ?", ("d" * 64,)).fetchone()[0]
    surviving = conn.execute(
        "SELECT id FROM derived_observation_artifacts WHERE "
        "observation_spec_hash = ?", ("d" * 64,)).fetchone()["id"]
    conn.close()
    assert count == 1, "same coordinate + same bytes converges on one row"
    assert surviving == first_id, (
        "converged identity is the first-written row; the second writer "
        "never rewrites or replaces it")


async def test_same_coordinate_different_bytes_invariant(tmp_path, monkeypatch):
    """MAT:12 — same complete coordinate + different bytes fails."""
    db = tmp_path / "soloring.db"; _upgrade(tmp_path, monkeypatch)
    pid, _ = await _seed_project_and_blob(db)
    coordinate = _coordinate(pid, "e" * 64)
    _insert_artifact(db, coordinate, blob_hash="1" * 64)
    with pytest.raises(Exception, match="UNIQUE"):
        _insert_artifact(db, coordinate, artifact_id=str(uuid.uuid4()),
                         blob_hash="2" * 64)


async def test_materializer_contract_hash_in_convergence_identity(
        tmp_path, monkeypatch):
    """MAT:13 — different materializer-contract hash = different
    coordinate, never a collision."""
    db = tmp_path / "soloring.db"; _upgrade(tmp_path, monkeypatch)
    pid, _ = await _seed_project_and_blob(db)
    first = _coordinate(pid, "f" * 64, contract="a" * 64)
    second = _coordinate(pid, "f" * 64, contract="b" * 64)
    _insert_artifact(db, first, blob_hash="1" * 64)
    _insert_artifact(db, second, blob_hash="2" * 64)  # distinct coordinate
    conn = _connect(db)
    count = conn.execute(
        "SELECT COUNT(*) FROM derived_observation_artifacts WHERE "
        "observation_spec_hash = ?", ("f" * 64,)).fetchone()[0]
    conn.close()
    assert count == 2


# ---- downgrade preflight ---------------------------------------------------

async def test_downgrade_empty_tables_succeeds(tmp_path, monkeypatch):
    """Empty-safe: all three conditions true → downgrade proceeds."""
    db = tmp_path / "soloring.db"; _upgrade(tmp_path, monkeypatch)
    try:
        _downgrade(tmp_path, monkeypatch, "0014_m13_authority_complete_world")
        result = None
    except Exception as exc:
        result = exc
    assert result is None, str(result)
    conn = _connect(db)
    head = conn.execute("SELECT version_num FROM alembic_version"
                        ).fetchone()[0]
    assert head == "0014_m13_authority_complete_world"
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "derived_observation_artifacts" not in tables
    conn.close()


async def test_downgrade_schema4_history_refuses(tmp_path, monkeypatch):
    """HIST:11 — schema-4 Generations present (even with EMPTY derived
    tables) → downgrade refuses before DDL."""
    db = tmp_path / "soloring.db"; _upgrade(tmp_path, monkeypatch)
    conn = _connect(db)
    conn.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) "
        "VALUES ('p1', 'P', 't', 't')")
    conn.execute(
        "INSERT INTO shots (id, project_id, shot_number, subject, "
        "duration_ms) VALUES ('s1', 'p1', 1, 'x', 1000)")
    conn.execute(
        "INSERT INTO shot_revisions (id, shot_id, revision_number, "
        "snapshot_hash, snapshot_json, created_at) VALUES "
        "('r1', 's1', 1, '" + "0" * 64 + "', '{}', 't')")
    conn.execute(
        "INSERT INTO generations (id, shot_id, shot_revision_id, "
        "generation_number, operation, executor, status, workflow_id, "
        "workflow_version, workflow_template_hash, manifest_hash, model, "
        "model_version, compiled_prompt, prompt_compiler_version, "
        "parameters_json, workflow_spec_json, workflow_spec_hash, "
        "created_at) VALUES ('g1', 's1', 'r1', 1, 'generate', 'comfy', "
        "'queued', 'w', 1, '" + "1" * 64 + "', '" + "2" * 64 + "', "
        "'m', 'v', 'p', '1', '{}', "
        "'{\"schema_version\": 4}', '" + "3" * 64 + "', 't')")
    conn.commit()
    conn.close()

    try:
        _downgrade(tmp_path, monkeypatch, "0014_m13_authority_complete_world")
        result = None
    except Exception as exc:
        result = exc
    assert result is not None
    assert "0015 downgrade refused" in str(result)
    assert "schema 4" in str(result)
    conn = _connect(db)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "derived_observation_artifacts" in tables, (
        "downgrade must refuse BEFORE destructive DDL")
    conn.close()


async def test_downgrade_nonempty_derived_state_refuses(
        tmp_path, monkeypatch):
    _upgrade(tmp_path, monkeypatch)
    db = tmp_path / "soloring.db"
    pid, blob = await _seed_project_and_blob(db)
    db = tmp_path / "soloring.db"
    _insert_artifact(db, _coordinate(pid, "9" * 64), blob_hash=blob)
    try:
        _downgrade(tmp_path, monkeypatch, "0014_m13_authority_complete_world")
        result = None
    except Exception as exc:
        result = exc
    assert result is not None
    assert "0015 downgrade refused" in str(result)
    assert "derived_observation_artifacts" in str(result)


async def test_downgrade_nonempty_binding_refuses(tmp_path, monkeypatch):
    db = tmp_path / "soloring.db"; _upgrade(tmp_path, monkeypatch)
    pid, blob = await _seed_project_and_blob(db)
    conn = _connect(db)
    conn.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) "
        "VALUES ('p1', 'P', 't', 't')")
    conn.execute(
        "INSERT INTO shots (id, project_id, shot_number, subject, "
        "duration_ms) VALUES ('s1', 'p1', 1, 'x', 1000)")
    conn.execute(
        "INSERT INTO shot_revisions (id, shot_id, revision_number, "
        "snapshot_hash, snapshot_json, created_at) VALUES "
        "('r1', 's1', 1, '" + "0" * 64 + "', '{}', 't')")
    conn.execute(
        "INSERT INTO generations (id, shot_id, shot_revision_id, "
        "generation_number, operation, executor, status, workflow_id, "
        "workflow_version, workflow_template_hash, manifest_hash, model, "
        "model_version, compiled_prompt, prompt_compiler_version, "
        "parameters_json, workflow_spec_json, workflow_spec_hash, "
        "created_at) VALUES ('g1', 's1', 'r1', 1, 'generate', 'comfy', "
        "'queued', 'w', 1, '" + "1" * 64 + "', '" + "2" * 64 + "', "
        "'m', 'v', 'p', '1', '{}', '{}', '" + "3" * 64 + "', 't')")
    conn.commit()
    conn.close()
    artifact_id = _insert_artifact(db, _coordinate(pid, "8" * 64),
                                   blob_hash=blob)
    conn = _connect(db)
    conn.execute(
        "INSERT INTO generation_derived_observation_inputs "
        "(generation_id, input_key, position, artifact_role, "
        "derived_observation_artifact_id, blob_hash) VALUES "
        "('g1', 'world_depth', 0, 'observation.world_depth', ?, ?)",
        (artifact_id, blob))
    conn.commit()
    conn.close()

    try:
        _downgrade(tmp_path, monkeypatch, "0014_m13_authority_complete_world")
        result = None
    except Exception as exc:
        result = exc
    assert result is not None
    assert "0015 downgrade refused" in str(result)
    assert "generation_derived_observation_inputs" in str(result)


# ---- eight-path recovery inventory ----------------------------------------

async def test_recovery_blob_fk_inventory_eight_paths(
        tmp_path, monkeypatch):
    """The 0015 policy = predecessor seven + derived_observation_artifacts."""
    from soloring.recovery.backup import (
        M11_BLOB_FK_COLUMNS,
        M14_BLOB_FK_COLUMNS,
        M14_ALEMBIC_HEAD,
        SUPPORTED_RESTORE_ALEMBIC_HEADS,
        _blob_fk_policy_for_head,
    )

    assert len(M11_BLOB_FK_COLUMNS) == 7
    assert M14_BLOB_FK_COLUMNS == frozenset(
        set(M11_BLOB_FK_COLUMNS)
        | {("derived_observation_artifacts", "blob_hash")})
    assert len(M14_BLOB_FK_COLUMNS) == 8
    assert _blob_fk_policy_for_head(M14_ALEMBIC_HEAD) == M14_BLOB_FK_COLUMNS
    assert SUPPORTED_RESTORE_ALEMBIC_HEADS == frozenset({
        "0011_m10_derived_spatial_execution",
        "0012_m11_reusable_production_revisions",
        "0013_m12_composition_occurrences",
        "0014_m13_authority_complete_world",
        "0015_m14_world_observation_execution",
    }), SUPPORTED_RESTORE_ALEMBIC_HEADS

    # the physical 0015 schema carries the eighth FK path
    db = tmp_path / "soloring.db"; _upgrade(tmp_path, monkeypatch)
    conn = _connect(db)
    physical = set()
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%'")]
    for table in tables:
        quoted = table.replace('"', '""')
        for row in conn.execute(f'PRAGMA foreign_key_list("{quoted}")'):
            if row["table"] == "blobs":
                physical.add((table, row["from"]))
    policy = set(M14_BLOB_FK_COLUMNS) - {
        ("generation_derived_observation_inputs", "blob_hash")}
    assert policy <= physical, (
        "policy paths missing from the physical schema",
        policy - physical)
    extra = physical - policy
    assert extra <= {
        ("generation_derived_observation_inputs", "blob_hash")}, (
        "physical paths beyond the frozen inventory", extra)
    conn.close()


# ---- structural no-fake-Asset proof ----------------------------------------

async def test_no_fake_asset_or_generation_input_for_m14_closure(
        tmp_path, monkeypatch):
    """EXEC:04 — M14 production-world closure appears only through
    WorkflowSpec 4 and the two M14 tables: no Asset row or
    GenerationInput row references a ProductionRevision, Composition,
    binding, retained Blob, WorldObservationSpec, or derived
    observation artifact."""
    db = tmp_path / "soloring.db"; _upgrade(tmp_path, monkeypatch)
    conn = _connect(db)

    # generation_inputs has exactly ONE FK target family: assets.id
    fks = {(r["from"], r["table"]) for r in conn.execute(
        "PRAGMA foreign_key_list('generation_inputs')")}
    referenced = {target for _, target in fks}
    assert referenced <= {"generations", "assets", "blobs"}, referenced

    # no table FKs from assets to any M14/production-family table
    asset_fks = {(r["from"], r["table"]) for r in conn.execute(
        "PRAGMA foreign_key_list('assets')")}
    for _, target in asset_fks:
        assert "derived_observation" not in target
        assert "production" not in target
        assert "composition" not in target

    # the M14 binding table references ONLY generations + the M14
    # artifact family — never assets, and never blobs directly (the
    # composite FK pins the Blob through the artifact row)
    gdoi_fks = {(r["from"], r["table"]) for r in conn.execute(
        "PRAGMA foreign_key_list('generation_derived_observation_inputs')")}
    for _, target in gdoi_fks:
        assert target != "assets"
    assert {target for _, target in gdoi_fks} == {
        "generations", "derived_observation_artifacts"}
    conn.close()
