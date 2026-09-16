"""M16:RECOVERY — full-depth 0017 verification (frozen R6 §16.2/§22).

B-eligible-in-C cells: RECOVERY 01/02/05 essence — the 0017 restore
verifies M13+M14+M15+M16 history, and corrupted M16 rows fail restore.
"""

from __future__ import annotations

import json

from sqlalchemy import text

from tests.m16_seed_b import (
    event,
    post_event,
    put_transition,
    seed_feature_world,
    state,
)
from tests.test_m16_capture import _capture


async def _stamp_alembic(client, head="0017_m16_intra_shot_consequences"):
    """The conftest engine builds schema via create_all (no
    alembic_version); the recovery machinery requires the table."""
    from sqlalchemy import text as _text

    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        await conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
        await conn.execute(_text(
            "CREATE TABLE IF NOT EXISTS alembic_version "
            "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
        await conn.execute(_text("DELETE FROM alembic_version"))
        await conn.execute(_text(
            "INSERT INTO alembic_version (version_num) VALUES (:h)"),
            {"h": head})
        await conn.commit()


async def _seed_world_with_history(client, factory):
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    await put_transition(client, fid, sid, operation="set", value="fresh")
    revision, _ = await _capture(client, sid)
    return base, sid, fid, revision


async def _backup_and_restore(client, tmp_path, tag):
    from soloring.recovery.backup import backup, restore
    from soloring.settings import Settings

    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        await conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    settings = Settings(
        data_dir=client._transport.app.state.settings.data_dir)
    backup_root = tmp_path / f"backup-{tag}"
    await backup(settings, backup_root)
    dest = tmp_path / f"restored-{tag}"
    await restore(backup_root, dest)
    manifest = json.loads(
        (backup_root / "backup-manifest.json").read_text(encoding="utf-8"))
    return manifest, dest


async def test_recovery_01_restore_verifies_m16_depth(client, factory,
                                                      tmp_path):
    """0017 backup→restore round-trips working events AND immutable
    schema-7 companions; the manifest records the 0017 head."""
    base, sid, fid, revision = await _seed_world_with_history(
        client, factory)
    await _stamp_alembic(client)
    manifest, dest = await _backup_and_restore(client, tmp_path, "depth")
    assert manifest["alembic_version"] == "0017_m16_intra_shot_consequences"
    import sqlite3

    con = sqlite3.connect(str(dest / "soloring.db"))
    try:
        head = con.execute(
            "SELECT version_num FROM alembic_version").fetchone()[0]
        events = con.execute(
            "SELECT COUNT(*) FROM shot_intra_shot_events "
            "WHERE deleted_at IS NULL").fetchone()[0]
        children = con.execute(
            "SELECT COUNT(*) FROM shot_revision_intra_shot_events "
            "WHERE shot_revision_id = ?", (revision.id,)).fetchone()[0]
    finally:
        con.close()
    assert head == "0017_m16_intra_shot_consequences"
    assert events == 1
    assert children == 1


async def test_recovery_02_working_event_corruption_fails(client, factory,
                                                           tmp_path):
    """A corrupted working event hash fails the 0017 backup/restore —
    fail-closed at whichever gate sees it first."""
    from soloring.recovery.backup import backup, restore
    from soloring.settings import Settings

    base, sid, fid, revision = await _seed_world_with_history(
        client, factory)
    await _stamp_alembic(client)
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE shot_intra_shot_events SET event_hash = :h "
            "WHERE shot_id = :s"),
            {"h": "0" * 64, "s": sid})
    settings = Settings(
        data_dir=client._transport.app.state.settings.data_dir)
    backup_root = tmp_path / "backup-corrupt"
    backup_failed = False
    try:
        await backup(settings, backup_root)
    except Exception:
        backup_failed = True
    if not backup_failed:
        import sqlite3

        con = sqlite3.connect(str(backup_root / "soloring.db"))
        con.execute("UPDATE shot_intra_shot_events SET event_hash = :h",
                    {"h": "1" * 64})
        con.commit()
        con.close()
        dest = tmp_path / "refused"
        try:
            await restore(backup_root, dest)
        except Exception as exc:
            assert "canonical" in str(exc).lower()                 or "intra" in str(exc).lower()                 or "corrupt" in str(exc).lower()
        else:
            raise AssertionError(
                "corrupted M16 event restored without refusal")
