"""M16-P0 predecessor historical-closure repairs (frozen R6 PRE:01-06)."""

from __future__ import annotations

import importlib
import sqlite3
import uuid
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from soloring.domain.canonical import canonical_hash, canonical_json_str

# Import the recovery MODULE, not the package-level public ``backup`` callable.
# Importing the package installs the M16-P0 successor semantic extension first.
recovery = importlib.import_module("soloring.recovery.backup")


def _touch_db(path: Path) -> None:
    sqlite3.connect(path).close()


def test_pre_01(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """0015 semantic dispatch is exactly M11 -> M12 -> M13 -> M14."""
    db = tmp_path / "0015.db"
    _touch_db(db)
    seen: list[str] = []
    monkeypatch.setattr(recovery, "_verify_m11_production_state",
                        lambda _: seen.append("m11"))
    monkeypatch.setattr(recovery, "_verify_m12_composition_state",
                        lambda _: seen.append("m12"))
    monkeypatch.setattr(recovery, "_verify_m13_world_state",
                        lambda _: seen.append("m13"))
    monkeypatch.setattr(recovery, "_verify_m14_observation_state",
                        lambda _: seen.append("m14"))
    monkeypatch.setattr(recovery, "_verify_m15_compatibility_state",
                        lambda _: seen.append("m15"))

    recovery._verify_head_semantics(db, recovery.M14_ALEMBIC_HEAD)
    assert seen == ["m11", "m12", "m13", "m14"]


def test_pre_02(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """0016 semantic dispatch adds M15 after the complete predecessor chain."""
    db = tmp_path / "0016.db"
    _touch_db(db)
    seen: list[str] = []
    monkeypatch.setattr(recovery, "_verify_m11_production_state",
                        lambda _: seen.append("m11"))
    monkeypatch.setattr(recovery, "_verify_m12_composition_state",
                        lambda _: seen.append("m12"))
    monkeypatch.setattr(recovery, "_verify_m13_world_state",
                        lambda _: seen.append("m13"))
    monkeypatch.setattr(recovery, "_verify_m14_observation_state",
                        lambda _: seen.append("m14"))
    monkeypatch.setattr(recovery, "_verify_m15_compatibility_state",
                        lambda _: seen.append("m15"))

    recovery._verify_head_semantics(db, recovery.M15_ALEMBIC_HEAD)
    assert seen == ["m11", "m12", "m13", "m14", "m15"]


def test_pre_03(tmp_path: Path) -> None:
    """Corrupt M14 canonical/hash evidence fails recovery semantics."""
    db = tmp_path / "m14-corrupt.db"
    con = sqlite3.connect(db)
    con.executescript(
        """
        CREATE TABLE projects (id TEXT PRIMARY KEY);
        CREATE TABLE blobs (hash TEXT PRIMARY KEY, size_bytes INTEGER);
        CREATE TABLE derived_observation_artifacts (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            observation_spec_hash TEXT NOT NULL,
            artifact_role TEXT NOT NULL,
            materializer_id TEXT NOT NULL,
            materializer_version INTEGER NOT NULL,
            materializer_contract_hash TEXT NOT NULL,
            parameters_json TEXT NOT NULL,
            parameters_hash TEXT NOT NULL,
            provenance_json TEXT NOT NULL,
            provenance_hash TEXT NOT NULL,
            blob_hash TEXT NOT NULL
        );
        CREATE TABLE generations (id TEXT PRIMARY KEY);
        CREATE TABLE generation_derived_observation_inputs (
            generation_id TEXT,
            input_key TEXT,
            position INTEGER,
            artifact_role TEXT,
            derived_observation_artifact_id TEXT,
            blob_hash TEXT
        );
        """
    )
    project_id = str(uuid.uuid4())
    artifact_id = str(uuid.uuid4())
    params = {"schema_version": 1}
    con.execute("INSERT INTO projects VALUES (?)", (project_id,))
    con.execute("INSERT INTO blobs VALUES (?, 1)", ("b" * 64,))
    con.execute(
        "INSERT INTO derived_observation_artifacts VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            artifact_id, project_id, "a" * 64,
            "observation.world_depth", "ignored-before-corrupt-hash", 1,
            "c" * 64, canonical_json_str(params), "s" * 64,
            canonical_json_str({}), canonical_hash({}), "b" * 64,
        ),
    )
    con.commit()
    con.close()

    with pytest.raises(recovery.RecoveryCorruption, match="parameters_json"):
        recovery._verify_m14_observation_state(db)


def _dimension_results() -> dict:
    return {
        "production_lineage": {"status": "SATISFIED", "evidence": None},
        "retained_consumption": {"status": "SATISFIED", "evidence": None},
        "media_type": {"status": "SATISFIED", "evidence": None},
        "spatial_interpretation": {"status": "NOT_APPLICABLE", "evidence": None},
        "persistent_state_subject_identity": {
            "status": "SATISFIED", "evidence": None,
        },
    }


def test_pre_04(tmp_path: Path) -> None:
    """Corrupt M15 assessment scope/report evidence fails at head 0016."""
    db = tmp_path / "m15-corrupt.db"
    con = sqlite3.connect(db)
    con.executescript(
        """
        CREATE TABLE projects (id TEXT PRIMARY KEY);
        CREATE TABLE production_objects (id TEXT PRIMARY KEY, project_id TEXT);
        CREATE TABLE production_revisions (
            id TEXT PRIMARY KEY, production_object_id TEXT, snapshot_hash TEXT
        );
        CREATE TABLE composition_occurrences (
            id TEXT, composition_id TEXT, PRIMARY KEY (id, composition_id)
        );
        CREATE TABLE production_compatibility_assessments (
            id TEXT PRIMARY KEY, project_id TEXT, production_object_id TEXT,
            from_revision_id TEXT, from_revision_hash TEXT,
            to_revision_id TEXT, to_revision_hash TEXT,
            schema_version INTEGER, evaluator_id TEXT, evaluator_version INTEGER,
            scope_json TEXT, scope_hash TEXT, report_json TEXT, report_hash TEXT,
            overall_verdict TEXT, created_at TEXT
        );
        CREATE TABLE production_compatibility_uses (
            assessment_id TEXT, position INTEGER, composition_id TEXT,
            occurrence_id TEXT, composition_working_version INTEGER,
            use_contract_json TEXT, use_contract_hash TEXT,
            dimension_results_json TEXT, dimension_results_hash TEXT,
            verdict TEXT, translator_id TEXT, translator_version INTEGER,
            translator_parameters_json TEXT, translator_parameters_hash TEXT,
            translator_output_hash TEXT
        );
        CREATE TABLE composition_occurrence_revision_tracking (
            composition_id TEXT, occurrence_id TEXT, mode TEXT,
            policy_version INTEGER
        );
        CREATE TABLE production_update_operations (
            id TEXT, project_id TEXT, assessment_id TEXT,
            assessment_report_hash TEXT, schema_version INTEGER,
            operation_json TEXT, operation_hash TEXT, created_at TEXT
        );
        CREATE TABLE production_update_items (
            operation_id TEXT, assessment_id TEXT,
            assessment_use_position INTEGER, position INTEGER,
            composition_id TEXT, occurrence_id TEXT,
            from_revision_id TEXT, to_revision_id TEXT, verdict TEXT,
            review_accepted INTEGER, translator_id TEXT,
            translator_version INTEGER, translator_parameters_hash TEXT,
            translator_output_hash TEXT, working_version_before INTEGER,
            working_version_after INTEGER, before_spec_hash TEXT,
            after_spec_hash TEXT
        );
        """
    )
    project_id, object_id = str(uuid.uuid4()), str(uuid.uuid4())
    source_id, target_id = str(uuid.uuid4()), str(uuid.uuid4())
    assessment_id = str(uuid.uuid4())
    composition_id, occurrence_id = str(uuid.uuid4()), str(uuid.uuid4())
    con.execute("INSERT INTO projects VALUES (?)", (project_id,))
    con.execute("INSERT INTO production_objects VALUES (?,?)", (object_id, project_id))
    con.execute("INSERT INTO production_revisions VALUES (?,?,?)",
                (source_id, object_id, "2" * 64))
    con.execute("INSERT INTO production_revisions VALUES (?,?,?)",
                (target_id, object_id, "3" * 64))
    con.execute("INSERT INTO composition_occurrences VALUES (?,?)",
                (occurrence_id, composition_id))
    contract = {
        "consumer_kind": "composition_working_occurrence/v1",
        "composition_id": composition_id,
        "occurrence_id": occurrence_id,
        "composition_working_version": 0,
        "working_spec": {},
        "authority_subject": None,
        "placement_contract": {"owner": "A6_COMPOSITION"},
        "active_instance_feature_contracts": [],
        "active_instance_spatial_tracks": [],
        "source_revision": {"id": source_id},
        "target_revision": {"id": target_id},
    }
    dimensions = _dimension_results()
    con.execute(
        "INSERT INTO production_compatibility_assessments VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            assessment_id, project_id, object_id, source_id, "2" * 64,
            target_id, "3" * 64, 1,
            "soloring.production_revision_compatibility", 1,
            "[]", "0" * 64, "{}", "0" * 64,
            "COMPATIBLE_AS_IS", "2026-09-15T00:00:00.000Z",
        ),
    )
    con.execute(
        "INSERT INTO production_compatibility_uses VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            assessment_id, 0, composition_id, occurrence_id, 0,
            canonical_json_str(contract), canonical_hash(contract),
            canonical_json_str(dimensions), canonical_hash(dimensions),
            "COMPATIBLE_AS_IS", None, None, None, None, None,
        ),
    )
    con.commit()
    con.close()

    with pytest.raises(recovery.RecoveryCorruption, match="scope_json"):
        recovery._verify_m15_compatibility_state(db)


@pytest.mark.asyncio
async def test_pre_05(monkeypatch: pytest.MonkeyPatch) -> None:
    """Historical continuity accepts the published M13 outer schema 6."""
    from soloring.api import continuity as continuity_api
    from soloring.production_world.resolver import production_world_hash

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    revision_id, shot_id = str(uuid.uuid4()), str(uuid.uuid4())
    binding_id = str(uuid.uuid4())
    composition_revision_id = str(uuid.uuid4())
    spatial_world_revision_id = str(uuid.uuid4())
    pack = {
        "schema_version": 1,
        "binding": {
            "binding_id": binding_id,
            "binding_hash": "4" * 64,
            "value": {
                "schema_version": 1,
                "composition_revision": {
                    "revision_id": composition_revision_id,
                    "snapshot_hash": "5" * 64,
                },
                "spatial_world_revision": {
                    "revision_id": spatial_world_revision_id,
                    "snapshot_hash": "6" * 64,
                },
                "subjects": [],
                "entries": [],
            },
        },
        "instance_feature_states": [],
        "instance_spatial_states": [],
    }
    snapshot = {
        "schema_version": 6,
        "intent": {"duration_ms": 1000},
        "references": [],
        "production_world": pack,
    }
    async with engine.begin() as conn:
        await conn.exec_driver_sql(
            "CREATE TABLE shot_revisions (id TEXT PRIMARY KEY, shot_id TEXT, "
            "snapshot_json TEXT, snapshot_hash TEXT, continuity_spec_json TEXT, "
            "continuity_spec_hash TEXT)"
        )
        await conn.exec_driver_sql(
            "CREATE TABLE shot_revision_production_worlds ("
            "shot_revision_id TEXT PRIMARY KEY, production_world_hash TEXT, "
            "binding_id TEXT, binding_hash TEXT, composition_revision_id TEXT, "
            "composition_revision_hash TEXT, spatial_world_revision_id TEXT, "
            "spatial_world_revision_hash TEXT)"
        )
        await conn.exec_driver_sql(
            "CREATE TABLE shot_revision_production_instance_feature_states ("
            "shot_revision_id TEXT, position INTEGER, occurrence_id TEXT, "
            "feature_id TEXT, value_json TEXT, value_hash TEXT)"
        )
        await conn.exec_driver_sql(
            "CREATE TABLE shot_revision_production_instance_spatial_states ("
            "shot_revision_id TEXT, position INTEGER, composition_id TEXT, "
            "occurrence_id TEXT, production_instance_track_id TEXT, "
            "requirement TEXT, x_mm INTEGER, y_mm INTEGER, z_mm INTEGER, "
            "yaw_udeg INTEGER, pitch_udeg INTEGER, roll_udeg INTEGER, "
            "source_transition_id TEXT, source_anchor_type TEXT, "
            "source_anchor_id TEXT, source_boundary TEXT)"
        )
        await conn.exec_driver_sql(
            "INSERT INTO shot_revisions VALUES (?,?,?,?,NULL,NULL)",
            (revision_id, shot_id, canonical_json_str(snapshot),
             canonical_hash(snapshot)),
        )
        await conn.exec_driver_sql(
            "INSERT INTO shot_revision_production_worlds VALUES (?,?,?,?,?,?,?,?)",
            (revision_id, production_world_hash(pack), binding_id, "4" * 64,
             composition_revision_id, "5" * 64,
             spatial_world_revision_id, "6" * 64),
        )

    async def _no_spatial(*_args, **_kwargs):
        return None

    monkeypatch.setattr(continuity_api, "_captured_spatial_provenance", _no_spatial)
    async with maker() as session:
        out = await continuity_api._revision_continuity(session, revision_id)
    assert out["snapshot_schema_version"] == 6
    await engine.dispose()


@pytest.mark.asyncio
async def test_pre_06(monkeypatch: pytest.MonkeyPatch) -> None:
    """Schema-1 legacy historical behavior remains byte/meaning compatible."""
    from soloring.api import continuity as continuity_api

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    revision_id, shot_id = str(uuid.uuid4()), str(uuid.uuid4())
    snapshot = {
        "schema_version": 1,
        "intent": {"duration_ms": None},
        "references": [],
    }
    async with engine.begin() as conn:
        await conn.exec_driver_sql(
            "CREATE TABLE shot_revisions (id TEXT PRIMARY KEY, shot_id TEXT, "
            "snapshot_json TEXT, snapshot_hash TEXT, continuity_spec_json TEXT, "
            "continuity_spec_hash TEXT)"
        )
        await conn.exec_driver_sql(
            "INSERT INTO shot_revisions VALUES (?,?,?,?,NULL,NULL)",
            (revision_id, shot_id, canonical_json_str(snapshot),
             canonical_hash(snapshot)),
        )

    async def _no_spatial(*_args, **_kwargs):
        return None

    monkeypatch.setattr(continuity_api, "_captured_spatial_provenance", _no_spatial)
    async with maker() as session:
        out = await continuity_api._revision_continuity(session, revision_id)
    assert out["snapshot_schema_version"] == 1
    assert out["continuity_schema_version"] is None
    assert out["dependencies"] == []
    assert out["feature_states"] == []
    assert out["relations"] == []
    await engine.dispose()
