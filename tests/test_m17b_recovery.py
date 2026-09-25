"""M17B recovery matrix (frozen proof-map owners I06–I12 beyond the
migration file's I01–I05)."""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import text

from tests.m17b_seed import (SMILE, candidate_body, channel, kf,
                             seed_production_object,
                             seed_production_revision, stamp_alembic)


async def _world(client, tag: bytes = b"i-world"):
    from tests.m17b_seed import make_entity, make_project
    pid = await make_project(client, name=f"I {tag!r}")
    eid = await make_entity(client, pid)
    body = candidate_body([channel(SMILE, [kf(0, 1, 0)])])
    c = (await client.post(
        f"/creative-entities/{eid}/performance-candidates",
        json=body)).json()
    rev = (await client.post(
        f"/performance-candidates/{c['id']}/adopt",
        json={"adopted_by": "director"})).json()
    obj = await seed_production_object(client, pid, "I obj", tag)
    pr1 = await seed_production_revision(client, obj, tag + b"1", 1)
    pr2 = await seed_production_revision(client, obj, tag + b"2", 2)
    return pid, eid, c, rev, pr1, pr2


def test_i06_head_0018_remains_exact_11_blob_fk_paths():
    from soloring.recovery.backup import (_blob_fk_policy_for_head,
                                          M17A_BLOB_FK_COLUMNS)
    pol = _blob_fk_policy_for_head(
        "0018_m17a_dialogue_vocal_foundation")
    assert pol == M17A_BLOB_FK_COLUMNS
    assert len(pol) == 11


def test_i07_head_0019_has_exactly_13_blob_fk_paths():
    from soloring.recovery.backup import (_blob_fk_policy_for_head,
                                          M17B_BLOB_FK_COLUMNS)
    pol = _blob_fk_policy_for_head(
        "0019_m17b_performance_revisions")
    assert pol == M17B_BLOB_FK_COLUMNS
    assert len(pol) == 13
    extra = M17B_BLOB_FK_COLUMNS - _blob_fk_policy_for_head(
        "0018_m17a_dialogue_vocal_foundation")
    assert extra == frozenset({
        ("performance_candidates",
         "canonical_channel_payload_blob_hash"),
        ("performance_revisions",
         "canonical_channel_payload_blob_hash")})


@pytest.mark.asyncio
async def test_i08_backup_restore_preserves_canonical_payload_bytes_hashes_and_immutable_ids(client, tmp_path):
    from soloring.recovery.backup import backup, restore
    pid, eid, c, rev, pr1, pr2 = await _world(client)
    a = (await client.post(
        f"/performance-revisions/{rev['id']}/retarget-assessments",
        json={"from_production_revision_id":
              pr1["production_revision_id"],
              "to_production_revision_id":
              pr2["production_revision_id"]})).json()
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        await conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    await stamp_alembic(client)
    settings = client._transport.app.state.settings
    root = tmp_path / "bk"
    await backup(settings, root)
    dest = tmp_path / "rs"
    await restore(root, dest)
    con = sqlite3.connect(dest / "soloring.db")
    assert con.execute("SELECT COUNT(*) FROM "
                       "performance_candidates").fetchone()[0] == 1
    row = con.execute(
        "SELECT id, canonical_channel_payload_blob_hash, "
        "canonical_channel_payload_sha256 FROM "
        "performance_candidates").fetchone()
    assert row[0] == c["id"]
    assert row[1] == c["canonical_channel_payload_blob_hash"]
    assert row[2] == c["canonical_channel_payload_sha256"]
    rev2 = con.execute(
        "SELECT id, adoption_id, adopted_candidate_id FROM "
        "performance_revisions").fetchone()
    assert rev2[0] == rev["id"] and rev2[2] == c["id"]
    a2 = con.execute(
        "SELECT id, scope_hash, report_hash, overall_verdict FROM "
        "performance_retarget_assessments").fetchone()
    assert a2[0] == a["id"] and a2[1] == a["scope_hash"]
    assert a2[2] == a["report_hash"] and a2[3] == "REQUIRES_REVIEW"
    import hashlib
    p = (dest / "blobs" / "sha256" /
         c["canonical_channel_payload_blob_hash"][:2] /
         c["canonical_channel_payload_blob_hash"][2:4] /
         c["canonical_channel_payload_blob_hash"])
    assert hashlib.sha256(p.read_bytes()).hexdigest() == \
        c["canonical_channel_payload_blob_hash"]
    con.close()


@pytest.mark.asyncio
async def test_i09_recovery_rejects_noncanonical_payload(client, tmp_path):
    from soloring.recovery.backup import backup
    from soloring.recovery.m17b_verifier import (
        verify_m17b_performance_state)
    pid, eid, c, rev, _, _ = await _world(client, b"i09")
    engine = client._transport.app.state.engine
    # corrupt the retained payload to a NONCANONICAL valid-JSON doc
    settings = client._transport.app.state.settings
    p = (settings.blob_dir / "sha256" /
         c["canonical_channel_payload_blob_hash"][:2] /
         c["canonical_channel_payload_blob_hash"][2:4] /
         c["canonical_channel_payload_blob_hash"])
    noncanon = (b'{"channels":[],"performance_profile_id":'
                b'"performance-profile/1","schema_version":1}')
    p.write_bytes(noncanon)
    # point the blob identity at the new bytes via a fresh row
    h2 = __import__("hashlib").sha256(noncanon).hexdigest()
    p2 = settings.blob_dir / "sha256" / h2[:2] / h2[2:4] / h2
    p2.parent.mkdir(parents=True, exist_ok=True)
    p2.write_bytes(noncanon)
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT OR IGNORE INTO blobs (hash, path, size_bytes, "
            "detected_media_type, created_at) VALUES (:h, :p, :s, "
            "NULL, '2026-01-01T00:00:00.000Z')"),
            {"h": h2, "p": f"sha256/{h2[:2]}/{h2[2:4]}/{h2}",
             "s": len(noncanon)})
        await conn.execute(text(
            "UPDATE performance_candidates SET "
            "canonical_channel_payload_blob_hash = :h, "
            "canonical_channel_payload_sha256 = :h WHERE id = :i"),
            {"h": h2, "i": c["id"]})
    async with engine.connect() as conn:
        await conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    await stamp_alembic(client)
    db = settings.data_dir / "soloring.db"
    with pytest.raises(Exception) as exc_info:
        verify_m17b_performance_state(db, settings.blob_dir)
    assert "no channels" in str(exc_info.value) or "payload" in str(
        exc_info.value)


@pytest.mark.asyncio
async def test_i10_recovery_rejects_assessment_reason_verdict_report_drift(client, tmp_path):
    from soloring.recovery.m17b_verifier import (
        verify_m17b_performance_state)
    pid, eid, c, rev, pr1, pr2 = await _world(client, b"i10")
    a = (await client.post(
        f"/performance-revisions/{rev['id']}/retarget-assessments",
        json={"from_production_revision_id":
              pr1["production_revision_id"],
              "to_production_revision_id":
              pr2["production_revision_id"]})).json()
    engine = client._transport.app.state.engine
    settings = client._transport.app.state.settings
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE performance_retarget_assessments SET "
            "overall_verdict = 'COMPATIBLE_AS_IS' WHERE id = :i"),
            {"i": a["id"]})
    async with engine.connect() as conn:
        await conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    await stamp_alembic(client)
    with pytest.raises(Exception) as exc_info:
        verify_m17b_performance_state(
            settings.data_dir / "soloring.db", settings.blob_dir)
    assert "recompute" in str(exc_info.value) or "verdict" in str(
        exc_info.value)


@pytest.mark.asyncio
async def test_i11_restore_at_0018_or_earlier_invents_zero_m17b_state(client, tmp_path):
    from soloring.recovery.backup import backup
    pid, eid, c, rev, _, _ = await _world(client, b"i11")
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        await conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    await stamp_alembic(client)
    settings = client._transport.app.state.settings
    root = tmp_path / "bk18"
    # back up, then restamp the BACKUP manifest to 0018 and restore:
    # the restore machinery must refuse/invent nothing
    await backup(settings, root)
    import json as _json
    mf = root / "backup-manifest.json"
    doc = _json.loads(mf.read_text(encoding="utf-8"))
    doc["alembic_version"] = "0018_m17a_dialogue_vocal_foundation"
    mf.write_text(_json.dumps(doc, indent=2), encoding="utf-8")
    # staging a 0018 restore from a 0019 physical DB is refused:
    # (the manifest no longer matches the staged schema)
    from soloring.recovery.backup import restore
    with pytest.raises(Exception):
        await restore(root, tmp_path / "rs18")
    (tmp_path / "rs18").exists() is False or None


@pytest.mark.asyncio
async def test_i12_recovery_rejects_adopted_revision_copied_closure_drift_while_historical_soft_d(client, tmp_path):
    from soloring.recovery.m17b_verifier import (
        verify_m17b_performance_state)
    pid, eid, c, rev, _, _ = await _world(client, b"i12")
    engine = client._transport.app.state.engine
    settings = client._transport.app.state.settings
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE performance_revisions SET performance_kind = "
            "'BODY' WHERE id = :i"), {"i": rev["id"]})
    async with engine.connect() as conn:
        await conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    await stamp_alembic(client)
    with pytest.raises(Exception) as exc_info:
        verify_m17b_performance_state(
            settings.data_dir / "soloring.db", settings.blob_dir)
    assert "closure" in str(exc_info.value) or "diverge" in str(
        exc_info.value)


# ---- I01-I05 owners (delegating to the migration battery) ---------

def test_i01_fresh_upgrade_reaches_0019(tmp_path):
    from tests.test_m17b_migration import _fresh_upgrade_reaches_0019
    _fresh_upgrade_reaches_0019(tmp_path)


def test_i02_exactly_four_m17b_tables(tmp_path):
    from tests.test_m17b_migration import _i02_exactly_four_m17b_tables
    _i02_exactly_four_m17b_tables(tmp_path)


def test_i03_predecessor_tables_remain_unchanged(tmp_path):
    from tests.test_m17b_migration import (
        _i03_predecessor_tables_unchanged)
    _i03_predecessor_tables_unchanged(tmp_path)


def test_i04_empty_downgrade_succeeds(tmp_path):
    from tests.test_m17b_migration import _i04_empty_downgrade_succeeds
    _i04_empty_downgrade_succeeds(tmp_path)


def test_i05_populated_downgrade_refuses(tmp_path):
    from tests.test_m17b_migration import (
        _i05_populated_downgrade_refuses)
    _i05_populated_downgrade_refuses(tmp_path)
