"""M11 migration/ORM proofs (frozen R3 plan §20.7).

0012 is exactly additive: a populated 0011 database upgrades cleanly with
predecessor rows preserved; ORM and migration DDL are mechanically
equivalent; downgrade is lossless-or-refused with preflight BEFORE any DDL;
no backfill.
"""

import sqlite3

import pytest
from alembic import command
from alembic.config import Config

BASE_DIR = __import__("pathlib").Path(__file__).resolve().parents[1]
VERSIONS = BASE_DIR / "server" / "alembic" / "versions"


def _cfg() -> Config:
    cfg = Config(str(BASE_DIR / "server" / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "server" / "alembic"))
    return cfg


def _point_at(data_dir, monkeypatch) -> None:
    import soloring.settings as settings_mod

    monkeypatch.setenv("SOLORING_DATA_DIR", str(data_dir))
    monkeypatch.setattr(settings_mod, "_settings", None)


def _upgrade(tmp_path, monkeypatch, target="head"):
    _point_at(tmp_path, monkeypatch)
    command.upgrade(_cfg(), target)


def _downgrade(tmp_path, monkeypatch, target):
    _point_at(tmp_path, monkeypatch)
    command.downgrade(_cfg(), target)


def _con(tmp_path):
    return sqlite3.connect(tmp_path / "soloring.db")


def _populate_predecessor(con) -> dict:
    """Seed one row in every predecessor liveness table at 0011."""
    import hashlib

    pid = "11111111-1111-1111-1111-111111111111"
    bh = hashlib.sha256(b"m11-mig").hexdigest()
    con.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) "
        "VALUES (?, 'P', '2026-01-01T00:00:00.000Z', '2026-01-01T00:00:00.000Z')",
        (pid,),
    )
    con.execute(
        "INSERT INTO blobs (hash, path, size_bytes, created_at) VALUES "
        "(?, ?, 14, '2026-01-01T00:00:00.000Z')",
        (bh, f"sha256/{bh[:2]}/{bh[2:4]}/{bh}"),
    )
    aid = "22222222-2222-2222-2222-222222222222"
    con.execute(
        "INSERT INTO assets (id, project_id, blob_hash, kind, created_at) "
        "VALUES (?, ?, ?, 'reference', '2026-01-01T00:00:00.000Z')",
        (aid, pid, bh),
    )
    con.commit()
    return {"project_id": pid, "blob_hash": bh, "asset_id": aid}


def test_0012_upgrade_from_populated_0011_preserves_predecessor_rows(
    tmp_path, monkeypatch
):
    """M11-MIG:01 — additive populated upgrade."""
    _upgrade(tmp_path, monkeypatch, "0011_m10_derived_spatial_execution")
    con = _con(tmp_path)
    seeded = _populate_predecessor(con)
    con.close()

    _upgrade(tmp_path, monkeypatch, "0012_m11_reusable_production_revisions")

    con = _con(tmp_path)
    row = con.execute(
        "SELECT id, project_id, blob_hash, kind FROM assets WHERE id = ?",
        (seeded["asset_id"],),
    ).fetchone()
    assert row == (seeded["asset_id"], seeded["project_id"], seeded["blob_hash"], "reference")
    # Predecessor schema untouched: no new columns on predecessor tables.
    asset_cols = [r[1] for r in con.execute("PRAGMA table_info(assets)")]
    assert "production_object_id" not in asset_cols and len(asset_cols) == 12
    con.close()


def test_0012_exact_orm_migration_parity(tmp_path, monkeypatch):
    """M11-MIG:02 — exact table/constraint/index parity between ORM and 0012."""
    _upgrade(tmp_path, monkeypatch, "0012_m11_reusable_production_revisions")

    def snapshot(con) -> dict:
        out = {}
        for (tbl,) in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'production_%'"
        ):
            cols = tuple(sorted((r[1], r[2], r[3]) for r in con.execute(f'PRAGMA table_info("{tbl}")')))
            fks = tuple(sorted(con.execute(f'PRAGMA foreign_key_list("{tbl}")')))
            idx = tuple(sorted(
                r[0] for r in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",
                    (tbl,),
                )
            ))
            out[tbl] = (cols, fks, idx)
        return out

    mig = snapshot(_con(tmp_path))

    from sqlalchemy import create_engine

    from soloring.db import models  # noqa: F401
    from soloring.db.base import Base

    eng = create_engine(f"sqlite:///{tmp_path}/orm.db")
    Base.metadata.create_all(eng)
    eng.dispose()
    orm = snapshot(sqlite3.connect(tmp_path / "orm.db"))

    assert set(mig) == {
        "production_objects", "production_revisions",
        "production_revision_closures", "production_revision_source_assets",
    }
    assert set(mig) == set(orm)
    for tbl in mig:
        assert mig[tbl] == orm[tbl], f"ORM/migration drift on {tbl}: {mig[tbl]} vs {orm[tbl]}"


def test_0012_empty_downgrade_to_0011(tmp_path, monkeypatch):
    """M11-MIG:03 — unused schema removable; 0011 tables never dropped."""
    _upgrade(tmp_path, monkeypatch)
    _downgrade(tmp_path, monkeypatch, "0011_m10_derived_spatial_execution")
    con = _con(tmp_path)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "production_objects" not in tables
    assert "derived_spatial_artifacts" in tables  # 0011 DDL never re-ran
    ver = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    con.close()
    assert ver == "0011_m10_derived_spatial_execution"


def _seed_m11_row(con, seeded, table):
    if table == "production_objects":
        con.execute(
            "INSERT INTO production_objects (id, project_id, name, created_at, updated_at) "
            "VALUES ('33333333-3333-3333-3333-333333333333', ?, 'Bare', "
            "'2026-01-02T00:00:00.000Z', '2026-01-02T00:00:00.000Z')",
            (seeded["project_id"],),
        )
    else:
        _seed_m11_row(con, seeded, "production_objects")
        rid = "44444444-4444-4444-4444-444444444444"
        con.execute(
            "INSERT INTO production_revisions (id, production_object_id, revision_number, "
            "snapshot_json, snapshot_hash, created_at) VALUES "
            "(?, '33333333-3333-3333-3333-333333333333', 1, '{}', "
            "'" + "0" * 64 + "', '2026-01-02T00:00:00.000Z')",
            (rid,),
        )
        if table == "production_revision_closures":
            con.execute(
                "INSERT INTO production_revision_closures (production_revision_id, "
                "contract_key, contract_version, blob_hash, size_bytes, media_type) "
                "VALUES (?, 'retained_blob', 1, ?, 14, NULL)",
                (rid, seeded["blob_hash"]),
            )
        elif table == "production_revision_source_assets":
            con.execute(
                "INSERT INTO production_revision_closures (production_revision_id, "
                "contract_key, contract_version, blob_hash, size_bytes, media_type) "
                "VALUES (?, 'retained_blob', 1, ?, 14, NULL)",
                (rid, seeded["blob_hash"]),
            )
            con.execute(
                "INSERT INTO production_revision_source_assets (production_revision_id, "
                "asset_id, created_at) VALUES (?, ?, '2026-01-02T00:00:00.000Z')",
                (rid, seeded["asset_id"]),
            )
    con.commit()


@pytest.mark.parametrize("table", [
    "production_objects",
    "production_revisions",
    "production_revision_closures",
    "production_revision_source_assets",
])
def test_0012_populated_tables_refuse_downgrade_before_ddl(tmp_path, monkeypatch, table):
    """M11-MIG:04 — any M11 row blocks downgrade; refusal precedes DDL."""
    _upgrade(tmp_path, monkeypatch, "0011_m10_derived_spatial_execution")
    con = _con(tmp_path)
    seeded = _populate_predecessor(con)
    con.close()
    _upgrade(tmp_path, monkeypatch, "head")
    con = _con(tmp_path)
    _seed_m11_row(con, seeded, table)
    con.close()

    with pytest.raises(RuntimeError, match="downgrade refused"):
        _downgrade(tmp_path, monkeypatch, "0011_m10_derived_spatial_execution")

    # Refused BEFORE destructive DDL: all four tables still exist.
    con = _con(tmp_path)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    ver = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    con.close()
    assert "production_objects" in tables and "production_revision_source_assets" in tables
    assert ver == "0012_m11_reusable_production_revisions"


def test_0012_bare_production_object_refuses_downgrade_without_becoming_adopted_revision(
    tmp_path, monkeypatch
):
    """M11-MIG:04b — a bare object blocks downgrade yet is not a revision."""
    _upgrade(tmp_path, monkeypatch, "head")
    con = _con(tmp_path)
    seeded = _populate_predecessor(con)
    _seed_m11_row(con, seeded, "production_objects")
    revisions = con.execute("SELECT COUNT(*) FROM production_revisions").fetchone()[0]
    con.close()
    assert revisions == 0  # no revision exists: bare object ≠ adopted revision

    with pytest.raises(RuntimeError, match="production_objects contains 1 row"):
        _downgrade(tmp_path, monkeypatch, "0011_m10_derived_spatial_execution")


def test_0012_does_not_backfill_existing_assets_or_projects(tmp_path, monkeypatch):
    """M11-MIG:05 — no invented adoption."""
    _upgrade(tmp_path, monkeypatch, "0011_m10_derived_spatial_execution")
    con = _con(tmp_path)
    _populate_predecessor(con)
    con.close()
    _upgrade(tmp_path, monkeypatch, "head")
    con = _con(tmp_path)
    for tbl in ("production_objects", "production_revisions",
                "production_revision_closures", "production_revision_source_assets"):
        n = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        assert n == 0, f"{tbl} was backfilled"
    con.close()


def test_0012_foreign_key_check_clean(tmp_path, monkeypatch):
    """M11-MIG:06 — relational integrity."""
    _upgrade(tmp_path, monkeypatch, "head")
    con = _con(tmp_path)
    seeded = _populate_predecessor(con)
    _seed_m11_row(con, seeded, "production_revision_source_assets")
    violations = con.execute("PRAGMA foreign_key_check").fetchall()
    con.close()
    assert violations == []


def test_migration_head_is_0012(tmp_path, monkeypatch):
    """M11-MIG:07 — exact new head."""
    _upgrade(tmp_path, monkeypatch)
    con = _con(tmp_path)
    ver = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    files = sorted(p.name for p in VERSIONS.glob("0*.py"))
    con.close()
    assert ver == "0012_m11_reusable_production_revisions"
    assert files[-1] == "0012_m11_reusable_production_revisions.py"
