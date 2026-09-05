"""M6 migration tests (plan §67–§70).

Populated 0005 -> 0006 preserves all production state with ZERO semantic
inference; every M6 table, named constraint, and index exists; the pair
CHECK added through ADD COLUMN is live on the migrated database; no
populated table is rebuilt (plan §70: the deferred structural-rebuild
preservation obligation stays deferred); downgrade restores a valid 0005.
"""

from __future__ import annotations

import sqlite3 as sq
from pathlib import Path

from alembic import command
from alembic.config import Config

from soloring.settings import BASE_DIR

_M6_TABLES = {
    "creative_entities", "entity_revisions",
    "character_revision_specs", "location_revision_specs",
    "prop_revision_specs", "costume_revision_specs", "vehicle_revision_specs",
    "entity_approved_revisions",
    "sequences", "scenes",
    "shot_entity_dependencies", "shot_revision_entity_dependencies",
}

_REQUIRED_INDEXES = [
    "ix_creative_entities_project_kind",
    "ix_creative_entities_project_created",
    "ix_entity_revisions_entity_id_created",
    "ix_sequences_project_active",
    "ix_scenes_sequence_active",
    # After 0007 these are active-only partial UNIQUE INDEXES, not
    # table-level constraints.
    "uq_sequences_project_id_position",
    "uq_scenes_sequence_id_position",
    "uq_shots_scene_position",
    "ix_shot_entity_dependencies_entity_id",
    "ix_shot_revisions_continuity_spec_hash",
    "ix_shot_revision_entity_dependencies_entity_revision_id",
    "ix_shot_revision_entity_dependencies_entity_id",
]

# Named constraints across the M6 tables plus the ALTER-added ones.
_CONSTRAINTS_TO_VERIFY = [
    ("creative_entities", "pk_creative_entities"),
    ("creative_entities", "fk_creative_entities_project_id_projects"),
    ("creative_entities", "ck_creative_entities_kind"),
    ("creative_entities", "ck_creative_entities_name_nonempty"),
    ("creative_entities", "ck_creative_entities_name_maxlen"),
    ("entity_revisions", "uq_entity_revisions_entity_id_revision_number"),
    ("entity_revisions", "uq_entity_revisions_entity_id_spec_hash"),
    ("entity_revisions", "uq_entity_revisions_id_entity_id"),
    ("entity_revisions", "ck_entity_revisions_spec_hash_len"),
    ("entity_revisions", "ck_entity_revisions_schema_version_positive"),
    ("character_revision_specs",
     "fk_character_revision_specs_revision_id_entity_revisions"),
    ("entity_approved_revisions",
     "fk_entity_approved_revisions_revision_id_entity_revisions"),
    ("sequences", "ck_sequences_position_nonneg"),
    ("scenes", "ck_scenes_position_nonneg"),
    # ALTER-added via ADD COLUMN — names must survive in stored DDL (§35).
    ("shots", "ck_shots_scene_pair"),
    ("shots", "ck_shots_scene_position_nonneg"),
    ("shot_revisions", "ck_shot_revisions_continuity_spec_hash_len"),
    ("shot_entity_dependencies", "pk_shot_entity_dependencies"),
    ("shot_entity_dependencies",
     "uq_shot_entity_dependencies_shot_id_role_position"),
    ("shot_entity_dependencies", "ck_shot_entity_dependencies_role"),
    ("shot_revision_entity_dependencies",
     "pk_shot_revision_entity_dependencies"),
    ("shot_revision_entity_dependencies",
     "fk_shot_revision_entity_dependencies_entity_revision_id_entity_revisions"),
    ("shot_revision_entity_dependencies",
     "ck_shot_revision_entity_dependencies_source"),
]


def _cfg() -> Config:
    cfg = Config(str(BASE_DIR / "server" / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "server" / "alembic"))
    return cfg


def _point_at(data_dir: Path, monkeypatch) -> None:
    import soloring.settings as settings_mod

    monkeypatch.setenv("SOLORING_DATA_DIR", str(data_dir))
    monkeypatch.setattr(settings_mod, "_settings", None)


def _connect(db_file: Path) -> sq.Connection:
    con = sq.connect(str(db_file))
    con.execute("PRAGMA foreign_keys=ON")
    return con


def _populate_0005(cfg: Config, db_file: Path) -> dict:
    """A realistic populated pre-M6 database: project, shot, revision,
    generation, inputs, take, asset, blob."""
    import hashlib

    command.upgrade(cfg, "0005_soft_cancel_selection")
    bh = hashlib.sha256(b"blob").hexdigest()
    hex64 = "ab" * 32
    con = _connect(db_file)
    try:
        con.executescript(
            f"""
            INSERT INTO projects(id, name, created_at, updated_at)
              VALUES ('p1', 'P', 't', 't');
            INSERT INTO shots(id, project_id, shot_number, subject,
                              created_at, updated_at)
              VALUES ('s1', 'p1', 1, 'Eva enters', 't', 't');
            INSERT INTO blobs(hash, path, size_bytes, created_at)
              VALUES ('{bh}', 'sha256/ab/cd/file', 10, 't');
            INSERT INTO assets(id, project_id, blob_hash, kind, created_at)
              VALUES ('a1', 'p1', '{bh}', 'reference', 't');
            INSERT INTO shot_references(shot_id, asset_id, role, position,
                                        created_at)
              VALUES ('s1', 'a1', 'character', 0, 't');
            INSERT INTO shot_revisions(id, shot_id, revision_number,
                                       snapshot_json, snapshot_hash, created_at)
              VALUES ('r1', 's1', 1, '{{"schema_version":1}}', '{hex64}', 't');
            INSERT INTO generations(id, shot_id, shot_revision_id,
                                    generation_number, status, operation,
                                    executor, workflow_id, workflow_version,
                                    workflow_template_hash, manifest_hash,
                                    compiled_prompt, prompt_compiler_version,
                                    parameters_json, workflow_spec_json,
                                    workflow_spec_hash, created_at, updated_at,
                                    queued_at)
              VALUES ('g1', 's1', 'r1', 1, 'succeeded', 'generate', 'fake',
                                      'wf', 1, '{hex64}', '{hex64}', 'p', '1',
                                      '{{}}', '{{}}', '{hex64}', 't', 't', 't');
            INSERT INTO generation_inputs(generation_id, asset_id, input_key,
                                          reference_role, position, blob_hash)
              VALUES ('g1', 'a1', 'reference_image', 'character', 0, '{bh}');
            """
        )
        con.commit()
    finally:
        con.close()
    return {"blob_hash": bh}


def test_populated_0005_to_0006_preserves_state_and_zero_inference(
    tmp_path: Path, monkeypatch
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "soloring.db"
    _point_at(data_dir, monkeypatch)
    cfg = _cfg()
    _populate_0005(cfg, db_file)

    command.upgrade(cfg, "head")

    con = _connect(db_file)
    try:
        # Zero semantic inference (plan §69): every legacy row unchanged,
        # new columns NULL.
        assert con.execute(
            "SELECT scene_id, scene_position FROM shots WHERE id='s1'"
        ).fetchone() == (None, None)
        assert con.execute(
            "SELECT continuity_spec_json, continuity_spec_hash "
            "FROM shot_revisions WHERE id='r1'"
        ).fetchone() == (None, None)
        assert con.execute(
            "SELECT status, operation FROM generations WHERE id='g1'"
        ).fetchone() == ("succeeded", "generate")
        assert con.execute(
            "SELECT COUNT(*) FROM generation_inputs WHERE generation_id='g1'"
        ).fetchone()[0] == 1
        # No CreativeEntity was inferred from role='character' (M6-F11).
        assert con.execute("SELECT COUNT(*) FROM creative_entities"
                           ).fetchone()[0] == 0
        assert con.execute(
            "SELECT COUNT(*) FROM entity_revisions").fetchone()[0] == 0

        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'"
        )}
        assert _M6_TABLES <= tables

        assert con.execute("PRAGMA foreign_key_check").fetchall() == []

        idx = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )}
        for name in _REQUIRED_INDEXES:
            assert name in idx, f"missing index {name}"

        sql = {r[0]: r[1] for r in con.execute(
            "SELECT tbl_name, sql FROM sqlite_master WHERE type='table'"
        )}
        for table, cname in _CONSTRAINTS_TO_VERIFY:
            assert cname in sql[table], f"missing constraint {cname} on {table}"

        # No populated table was rebuilt (plan §70): no batch temp tables and
        # the ALTER path left the original column order intact with the new
        # columns appended.
        assert not [t for t in tables if t.startswith("_alembic_tmp")]
        shot_cols = [r[1] for r in con.execute("PRAGMA table_info(shots)")]
        assert shot_cols[-2:] == ["scene_id", "scene_position"]
        sr_cols = [r[1] for r in con.execute("PRAGMA table_info(shot_revisions)")]
        assert sr_cols[-2:] == ["continuity_spec_json", "continuity_spec_hash"]

        # The pair CHECK added via ADD COLUMN is LIVE on migrated data.
        for stmt in (
            "UPDATE shots SET scene_position = 0 WHERE id = 's1'",
            "UPDATE shots SET scene_id = 'some-scene' WHERE id = 's1'",
        ):
            try:
                con.execute(stmt)
                con.commit()
                raised = False
            except sq.IntegrityError:
                raised = True
                con.rollback()
            assert raised, f"pair CHECK not enforced: {stmt}"
        con.execute(
            "INSERT INTO projects(id, name, created_at, updated_at) "
            "VALUES ('p2','P2','t','t')"
        )
        con.execute(
            "INSERT INTO shots(id, project_id, shot_number, subject, scene_id, "
            "scene_position, created_at, updated_at) "
            "VALUES ('s2','p2',1,'x','sc',0,'t','t')"
        )
        con.commit()
        # Unique index live: duplicate (scene_id, scene_position) rejected,
        # NULL pairs never clash.
        con.execute(
            "INSERT INTO shots(id, project_id, shot_number, subject, "
            "created_at, updated_at) VALUES ('s3','p2',2,'y','t','t')"
        )
        con.execute(
            "INSERT INTO shots(id, project_id, shot_number, subject, "
            "created_at, updated_at) VALUES ('s4','p2',3,'z','t','t')"
        )
        con.commit()  # two NULL/NULL rows coexist
        try:
            con.execute(
                "INSERT INTO shots(id, project_id, shot_number, subject, "
                "scene_id, scene_position, created_at, updated_at) "
                "VALUES ('s5','p2',4,'w','sc',0,'t','t')"
            )
            con.commit()
            raised = False
        except sq.IntegrityError:
            raised = True
            con.rollback()
        assert raised, "uq_shots_scene_position not enforced"

        assert con.execute("SELECT version_num FROM alembic_version"
                           ).fetchone()[0] == "0012_m11_reusable_production_revisions"
    finally:
        con.close()


def test_orm_create_all_matches_migrated_schema(tmp_path: Path, monkeypatch) -> None:
    """Every M6 table carries the same set of named constraints/indexes under
    ORM create_all and under migration (the 0002 parity lesson)."""
    import asyncio
    import re

    from soloring.db import models  # noqa: F401  (register on Base.metadata)
    from soloring.db.base import Base

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "soloring.db"
    _point_at(data_dir, monkeypatch)
    command.upgrade(_cfg(), "head")

    orm_file = data_dir / "orm.db"

    async def create() -> None:
        from sqlalchemy.ext.asyncio import create_async_engine

        eng = create_async_engine(f"sqlite+aiosqlite:///{orm_file}")
        async with eng.begin() as c:
            await c.run_sync(Base.metadata.create_all)
        await eng.dispose()

    asyncio.run(create())

    def named(db: str, table: str) -> set[str]:
        con = sq.connect(db)
        try:
            rows = con.execute(
                "SELECT sql FROM sqlite_master WHERE tbl_name = ? "
                "AND sql IS NOT NULL", (table,)
            ).fetchall()
            idx = con.execute(
                "SELECT name FROM sqlite_master WHERE tbl_name = ? "
                "AND type = 'index' AND sql IS NOT NULL", (table,)
            ).fetchall()
        finally:
            con.close()
        names: set[str] = set()
        for (ddl,) in rows:
            names |= set(re.findall(r"CONSTRAINT (\w+)", ddl))
        names |= {r[0] for r in idx}
        return names

    for table in sorted(_M6_TABLES):
        assert named(str(db_file), table) == named(str(orm_file), table), (
            f"constraint-name drift on {table}"
        )
    # The ALTER-added shots/shot_revisions constraints match too.
    for table in ("shots", "shot_revisions"):
        assert named(str(db_file), table) == named(str(orm_file), table), (
            f"constraint-name drift on {table}"
        )
    # M7 tables (0008) hold to the same strict parity.
    for table in ("continuity_features", "continuity_feature_transitions",
                  "continuity_predicates", "continuity_relations",
                  "continuity_relation_transitions",
                  "shot_revision_feature_states",
                  "shot_revision_relation_states"):
        assert named(str(db_file), table) == named(str(orm_file), table), (
            f"constraint-name drift on {table}"
        )


def test_downgrade_0006_to_0005_restores_clean_0005(
    tmp_path: Path, monkeypatch
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "soloring.db"
    _point_at(data_dir, monkeypatch)
    cfg = _cfg()
    _populate_0005(cfg, db_file)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0005_soft_cancel_selection")

    con = _connect(db_file)
    try:
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'"
        )}
        for t in _M6_TABLES:
            assert t not in tables, f"{t} should be removed on downgrade"
        shot_cols = [r[1] for r in con.execute("PRAGMA table_info(shots)")]
        assert "scene_id" not in shot_cols and "scene_position" not in shot_cols
        sr_cols = [r[1] for r in con.execute("PRAGMA table_info(shot_revisions)")]
        assert "continuity_spec_json" not in sr_cols
        assert "continuity_spec_hash" not in sr_cols

        # Production state survived the round-trip untouched.
        assert con.execute(
            "SELECT subject, shot_number FROM shots WHERE id='s1'"
        ).fetchone() == ("Eva enters", 1)
        assert con.execute(
            "SELECT snapshot_hash FROM shot_revisions WHERE id='r1'"
        ).fetchone() is not None

        assert not [t for t in tables if t.startswith("_alembic_tmp")]
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
        assert con.execute("SELECT version_num FROM alembic_version"
                           ).fetchone()[0] == "0005_soft_cancel_selection"
    finally:
        con.close()
