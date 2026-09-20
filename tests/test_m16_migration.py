"""M16 migration proofs (frozen R6 §20 / proof map M16:MIG:01-07)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

BASE_DIR = Path(__file__).resolve().parents[1]
M16_TABLES = {
    "shot_intra_shot_events",
    "shot_revision_intra_shot_specs",
    "shot_revision_intra_shot_events",
    "shot_intra_shot_event_proposals",
    "persistent_consequence_reviews",
}


def _cfg() -> Config:
    cfg = Config(str(BASE_DIR / "server" / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "server" / "alembic"))
    return cfg


def _point(data_dir: Path, monkeypatch) -> None:
    import soloring.settings as settings_mod

    monkeypatch.setenv("SOLORING_DATA_DIR", str(data_dir))
    monkeypatch.setattr(settings_mod, "_settings", None)


def _upgrade(data_dir: Path, monkeypatch, target="head") -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    _point(data_dir, monkeypatch)
    command.upgrade(_cfg(), target)


def _downgrade(data_dir: Path, monkeypatch, target="0016") -> None:
    _point(data_dir, monkeypatch)
    command.downgrade(_cfg(), target)


def _con(data_dir: Path) -> sqlite3.Connection:
    return sqlite3.connect(data_dir / "soloring.db")


def _tables(con) -> set[str]:
    return {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}


def _blob_fk_inventory(con) -> set[tuple[str, str, str]]:
    out = set()
    for table in _tables(con):
        for row in con.execute(f"PRAGMA foreign_key_list('{table}')"):
            if row[2] == "blobs":
                out.add((table, row[3], row[4]))
    return out


def test_mig_01(tmp_path, monkeypatch):
    """0017 adds exactly the five frozen M16 tables."""
    _upgrade(tmp_path, monkeypatch, "0016")
    con = _con(tmp_path)
    before = _tables(con)
    con.close()
    # pinned to the 0017 era: head (0018) would add the seven M17A tables
    _upgrade(tmp_path, monkeypatch, "0017")
    con = _con(tmp_path)
    after = _tables(con)
    con.close()
    assert after - before == M16_TABLES
    assert before - after == set()


def _index_signature(con, table: str):
    result = []
    for row in con.execute(f"PRAGMA index_list('{table}')"):
        name, unique, partial = row[1], row[2], row[4]
        if name.startswith("sqlite_autoindex_"):
            continue
        cols = tuple(r[2] for r in con.execute(f"PRAGMA index_info('{name}')"))
        sql = con.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (name,)
        ).fetchone()[0]
        result.append((name, unique, partial, cols, sql))
    return sorted(result)


def _fk_signature(con, table: str):
    return sorted((r[2], r[3], r[4], r[5], r[6])
                  for r in con.execute(f"PRAGMA foreign_key_list('{table}')"))


def _column_signature(con, table: str):
    return [(r[1], r[2], r[3], r[4], r[5])
            for r in con.execute(f"PRAGMA table_info('{table}')")]


def test_mig_02(tmp_path, monkeypatch):
    """ORM and migration schema/index/FK sets are identical for all five tables."""
    import sqlalchemy as sa

    _upgrade(tmp_path / "mig", monkeypatch, "head")
    from soloring.db.base import Base
    import soloring.db.models  # noqa: F401

    orm_path = tmp_path / "orm.db"
    engine = sa.create_engine(f"sqlite:///{orm_path}")
    Base.metadata.create_all(engine)
    engine.dispose()
    mig = _con(tmp_path / "mig")
    orm = sqlite3.connect(orm_path)
    try:
        for table in sorted(M16_TABLES):
            assert _column_signature(mig, table) == _column_signature(orm, table), table
            assert _fk_signature(mig, table) == _fk_signature(orm, table), table
            assert _index_signature(mig, table) == _index_signature(orm, table), table
    finally:
        mig.close()
        orm.close()


def _event_insert(con, *, event_id="e1", deleted_at=None, time_ms=100, ordinal=0,
                  target_kind="entity_feature", ef="f1", er=None, pf=None):
    con.execute(
        "INSERT INTO shot_intra_shot_events "
        "(id,shot_id,time_ms,ordinal,target_kind,entity_feature_id,entity_relation_id,"
        "production_instance_feature_id,before_state_json,before_state_hash,"
        "after_state_json,after_state_hash,persistence_mode,source_kind,"
        "source_proposal_id,event_json,event_hash,created_at,updated_at,deleted_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (event_id, "s1", time_ms, ordinal, target_kind, ef, er, pf,
         '{"present":false}', "a" * 64,
         '{"present":true,"value":"fresh","value_hash":"' + "b" * 64 + '"}',
         "c" * 64, "transient", "authored", None, "{}", "d" * 64,
         "2026-01-01T00:00:00.000Z", "2026-01-01T00:00:00.000Z", deleted_at))


def test_mig_03(tmp_path, monkeypatch):
    """The target-kind/FK XOR CHECK is present and enforced by SQLite."""
    _upgrade(tmp_path, monkeypatch, "head")
    con = _con(tmp_path)
    con.execute("PRAGMA foreign_keys=OFF")
    with pytest.raises(sqlite3.IntegrityError, match="ck_sise_target_xor"):
        _event_insert(con, ef=None)
    con.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="ck_sise_target_xor"):
        _event_insert(con, target_kind="entity_feature", ef="f1", er="r1")
    con.close()


def test_mig_04(tmp_path, monkeypatch):
    """Coordinate uniqueness is active-only; a tombstone frees the slot."""
    _upgrade(tmp_path, monkeypatch, "head")
    con = _con(tmp_path)
    con.execute("PRAGMA foreign_keys=OFF")
    _event_insert(con, event_id="e1")
    with pytest.raises(sqlite3.IntegrityError):
        _event_insert(con, event_id="e2")
    con.rollback()
    _event_insert(con, event_id="e1")
    con.execute("UPDATE shot_intra_shot_events SET deleted_at='x' WHERE id='e1'")
    _event_insert(con, event_id="e2")
    con.commit()
    assert con.execute(
        "SELECT COUNT(*) FROM shot_intra_shot_events WHERE time_ms=100 AND ordinal=0"
    ).fetchone()[0] == 2
    sql = con.execute(
        "SELECT sql FROM sqlite_master WHERE name='uq_sise_active_coordinate'"
    ).fetchone()[0]
    assert "WHERE deleted_at IS NULL" in sql
    con.close()


def test_mig_05(tmp_path, monkeypatch):
    """Captured source/proposal/transition FKs are physically restrictive."""
    _upgrade(tmp_path, monkeypatch, "head")
    con = _con(tmp_path)
    fks = con.execute(
        "PRAGMA foreign_key_list('shot_revision_intra_shot_events')"
    ).fetchall()
    by_from = {r[3]: r for r in fks}
    expected = {
        "source_event_id": "shot_intra_shot_events",
        "source_proposal_id": "shot_intra_shot_event_proposals",
        "entity_feature_transition_id": "continuity_feature_transitions",
        "entity_relation_transition_id": "continuity_relation_transitions",
        "production_instance_feature_transition_id":
            "production_instance_feature_transitions",
    }
    for column, parent in expected.items():
        row = by_from[column]
        assert row[2] == parent
        assert row[6].upper() == "RESTRICT"
    con.close()


def _insert_one(con, table: str):
    con.execute("PRAGMA foreign_keys=OFF")
    if table == "shot_intra_shot_event_proposals":
        con.execute(
            "INSERT INTO shot_intra_shot_event_proposals VALUES "
            "('p','s','imported','r',?,NULL,NULL,'human',NULL,NULL,NULL,'{}',?,'n')",
            ("a" * 64, "b" * 64))
    elif table == "shot_intra_shot_events":
        _event_insert(con)
    elif table == "shot_revision_intra_shot_specs":
        con.execute(
            "INSERT INTO shot_revision_intra_shot_specs VALUES ('r',1,1000,'{}',?)",
            ("a" * 64,))
    elif table == "shot_revision_intra_shot_events":
        con.execute(
            "INSERT INTO shot_revision_intra_shot_events "
            "(shot_revision_id,position,source_event_id,time_ms,ordinal,target_kind,"
            "captured_target_identity_json,captured_target_identity_hash,"
            "captured_before_state_json,captured_before_state_hash,"
            "captured_after_state_json,captured_after_state_hash,persistence_mode,"
            "event_json,event_hash,entity_feature_transition_id,"
            "entity_relation_transition_id,production_instance_feature_transition_id,"
            "captured_handoff_json,captured_handoff_hash,source_proposal_id) VALUES "
            "('r',0,'e',1,0,'entity_feature','{}',?,'{}',?,'{}',?,'transient',"
            "'{}',?,NULL,NULL,NULL,NULL,NULL,NULL)",
            ("a" * 64, "b" * 64, "c" * 64, "d" * 64))
    elif table == "persistent_consequence_reviews":
        con.execute(
            "INSERT INTO persistent_consequence_reviews "
            "(id,shot_id,source_kind,source_event_id,source_proposal_id,source_hash,"
            "decision,review_basis_hash,result_event_id,entity_feature_transition_id,"
            "entity_relation_transition_id,production_instance_feature_transition_id,"
            "operation_json,operation_hash,created_at) VALUES "
            "('x','s','proposal',NULL,'p',?,'ignore',?,NULL,NULL,NULL,NULL,'{}',?,'n')",
            ("a" * 64, "b" * 64, "c" * 64))
    else:  # pragma: no cover
        raise AssertionError(table)
    con.commit()


def test_mig_06(tmp_path, monkeypatch):
    """Downgrade refuses before DDL when any one of the five tables has a row."""
    for i, table in enumerate(sorted(M16_TABLES)):
        root = tmp_path / str(i)
        _upgrade(root, monkeypatch, "head")
        con = _con(root)
        _insert_one(con, table)
        con.close()
        with pytest.raises(Exception, match="0017 downgrade refused"):
            _downgrade(root, monkeypatch, "0016")
        con = _con(root)
        assert M16_TABLES <= _tables(con)
        con.close()


def test_mig_07(tmp_path, monkeypatch):
    """Empty roundtrip preserves predecessor rows and exact eight Blob-FK paths."""
    _upgrade(tmp_path, monkeypatch, "0016")
    con = _con(tmp_path)
    now = "2026-01-01T00:00:00.000Z"
    con.execute(
        "INSERT INTO projects (id,name,created_at,updated_at) VALUES ('p','P',?,?)",
        (now, now))
    con.commit()
    before = con.execute("SELECT id,name FROM projects WHERE id='p'").fetchone()
    blob_before = _blob_fk_inventory(con)
    assert len(blob_before) == 8
    con.close()

    # pinned to the 0017 era: head (0018) raises the Blob-FK inventory
    # to eleven and its empty downgrade is refused by design
    _upgrade(tmp_path, monkeypatch, "0017")
    con = _con(tmp_path)
    assert _blob_fk_inventory(con) == blob_before
    con.close()
    _downgrade(tmp_path, monkeypatch, "0016")
    con = _con(tmp_path)
    assert con.execute("SELECT id,name FROM projects WHERE id='p'").fetchone() == before
    assert _blob_fk_inventory(con) == blob_before
    con.close()
    _upgrade(tmp_path, monkeypatch, "0017")
    con = _con(tmp_path)
    assert con.execute("SELECT id,name FROM projects WHERE id='p'").fetchone() == before
    assert _blob_fk_inventory(con) == blob_before
    con.close()
