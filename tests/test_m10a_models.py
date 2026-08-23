"""M10A ORM/migration parity gate for frozen r3 migrations 0010/0011."""
from __future__ import annotations

import re
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from soloring.db.base import Base
from soloring.db import models as _registered_models  # noqa: F401

BASE_DIR = Path(__file__).resolve().parents[1]

M10_TABLES = (
    "spatial_worlds", "spatial_world_states", "spatial_frames",
    "spatial_world_state_frames", "spatial_axes", "spatial_world_state_axes",
    "spatial_world_revisions", "spatial_world_revision_frames",
    "spatial_world_revision_axes", "spatial_tracks", "spatial_transitions",
    "shot_spatial_plans", "shot_revision_spatial_worlds",
    "shot_revision_spatial_track_states", "shot_revision_spatial_plans",
    "derived_spatial_artifacts", "generation_derived_spatial_inputs",
)


def _cfg() -> Config:
    cfg = Config(str(BASE_DIR / "server" / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "server" / "alembic"))
    return cfg


def _point_at(data_dir: Path, monkeypatch) -> None:
    import soloring.settings as settings_mod
    monkeypatch.setenv("SOLORING_DATA_DIR", str(data_dir))
    monkeypatch.setattr(settings_mod, "_settings", None)


def _norm_sql(value) -> str | None:
    if value is None:
        return None
    return re.sub(r"\s+", " ", str(value).strip()).replace('"', "").lower()


def _signature(engine, table: str) -> dict:
    i = inspect(engine)
    cols = tuple((c["name"], str(c["type"]).upper(), bool(c["nullable"]), c.get("default"), int(bool(c.get("primary_key")))) for c in i.get_columns(table))
    pk = i.get_pk_constraint(table)
    fks = tuple(sorted((fk.get("name"), tuple(fk["constrained_columns"]), fk["referred_table"], tuple(fk["referred_columns"]), (fk.get("options") or {}).get("ondelete")) for fk in i.get_foreign_keys(table)))
    uniques = tuple(sorted((u.get("name"), tuple(u["column_names"])) for u in i.get_unique_constraints(table)))
    checks = tuple(sorted((c.get("name"), _norm_sql(c.get("sqltext"))) for c in i.get_check_constraints(table)))
    indexes = []
    for idx in i.get_indexes(table):
        opts = idx.get("dialect_options") or {}
        where = _norm_sql(opts.get("sqlite_where")) if "sqlite_where" in opts else None
        indexes.append((idx.get("name"), tuple(idx["column_names"]), bool(idx.get("unique")), where))
    return {"columns": cols, "pk": (pk.get("name"), tuple(pk.get("constrained_columns") or ())), "fks": fks, "uniques": uniques, "checks": checks, "indexes": tuple(sorted(indexes))}


def test_m10_orm_metadata_contains_exact_table_set():
    present = set(Base.metadata.tables)
    assert set(M10_TABLES) <= present
    assert len([name for name in present if name in M10_TABLES]) == 17


def test_m10_orm_matches_alembic_head_semantically(tmp_path, monkeypatch):
    metadata_db = tmp_path / "metadata.db"
    migrated_dir = tmp_path / "migrated"
    migrated_dir.mkdir()

    metadata_engine = create_engine(f"sqlite:///{metadata_db}")
    Base.metadata.create_all(metadata_engine)
    _point_at(migrated_dir, monkeypatch)
    command.upgrade(_cfg(), "head")
    migrated_engine = create_engine(f"sqlite:///{migrated_dir / 'soloring.db'}")
    try:
        for table in M10_TABLES:
            assert _signature(metadata_engine, table) == _signature(migrated_engine, table), table
    finally:
        metadata_engine.dispose()
        migrated_engine.dispose()


def test_rf1_support_index_is_in_metadata():
    table = Base.metadata.tables["derived_spatial_artifacts"]
    idx = {i.name: i for i in table.indexes}
    assert "ix_dsa_spec_runtime" in idx
    assert tuple(c.name for c in idx["ix_dsa_spec_runtime"].columns) == ("spec_hash", "runtime_fingerprint_hash")
