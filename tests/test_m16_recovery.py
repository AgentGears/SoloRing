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


async def _settings(client):
    from soloring.settings import Settings

    return Settings(
        data_dir=client._transport.app.state.settings.data_dir)



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


async def test_recovery_01(client, factory,
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


async def test_recovery_02(client, factory,
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


async def test_recovery_03(client, factory, tmp_path):
    """RECOVERY:03 — a valid imported proposal backs up cleanly; a
    coherent tamper of its pinned source revision hash then fails the
    0017 restore at source coherence (not at generic canonicality)."""
    import hashlib
    import json as _json
    import sqlite3

    from soloring.continuity.intra_shot_canonical import proposal_storage
    from soloring.domain.canonical import canonical_json_bytes
    from soloring.recovery.backup import backup, restore

    base, sid, fid, revision = await _seed_world_with_history(
        client, factory)
    await _stamp_alembic(client)
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        start_state = (await conn.execute(text(
            "SELECT value_json FROM shot_revision_feature_states "
            "WHERE shot_revision_id = :r AND feature_id = :f"),
            {"r": revision.id, "f": fid})).fetchall()
    before = {"present": False} if not start_state else {
        "present": True, "value": _json.loads(start_state[0][0]),
        "value_hash": revision.snapshot_hash}
    after = {"present": False} if start_state else {
        "present": True, "value": "healing",
        "value_hash": hashlib.sha256(b'"healing"').hexdigest()}
    value, pj, ph = proposal_storage(
        candidate_event={
            "time_ms": 1500, "ordinal": 0,
            "target": {"kind": "entity_feature", "id": fid},
            "before": before, "after": after},
        persistence_suggestion="persist")
    pid = "00000000-0000-4000-8000-0000000000b1"
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO shot_intra_shot_event_proposals "
            "(id, shot_id, source_kind, source_shot_revision_id, "
            "source_shot_revision_hash, source_generation_id, "
            "source_take_id, proposer_kind, analyzer_id, "
            "analyzer_version, analyzer_parameters_hash, proposal_json, "
            "proposal_hash, created_at) VALUES ("
            ":pid, :s, 'imported', :r, :h, NULL, NULL, 'human', NULL, "
            "NULL, NULL, :pj, :ph, "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"),
            {"pid": pid, "s": sid, "r": revision.id,
             "h": revision.snapshot_hash, "pj": pj, "ph": ph})
    backup_root = tmp_path / "bk-p"
    await backup(await _settings(client), backup_root)

    # coherent tree tamper: only the pinned source revision hash moves
    db_file = backup_root / "soloring.db"
    con = sqlite3.connect(str(db_file))
    con.execute(
        "UPDATE shot_intra_shot_event_proposals SET "
        "source_shot_revision_hash = :h", {"h": "1" * 64})
    con.commit()
    con.close()
    manifest_path = backup_root / "backup-manifest.json"
    manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["database_sha256"] = hashlib.sha256(
        db_file.read_bytes()).hexdigest()
    manifest_path.write_bytes(canonical_json_bytes(manifest))

    try:
        await restore(backup_root, tmp_path / "ref-p")
    except Exception as exc:
        assert "revision hash mismatch" in str(exc).lower() \
            or "source" in str(exc).lower(), str(exc)
    else:
        raise AssertionError("coherently tampered proposal restored")


async def test_recovery_04(client, factory, tmp_path):
    """RECOVERY:04 — a VALID decline_persistence review (correct frozen
    basis root, correct result shape) backs up cleanly; mutating ONLY
    the recorded basis hash then fails at the basis recompute, after
    canonical operation verification has passed."""
    import hashlib
    import json as _json
    import sqlite3

    from soloring.continuity.intra_shot_canonical import (
        event_review_basis_hash,
    )
    from soloring.domain.canonical import (
        canonical_hash as _ch,
        canonical_json_bytes,
        canonical_json_str as _cjs,
    )
    from soloring.recovery.backup import backup, restore

    base, sid, fid, revision = await _seed_world_with_history(
        client, factory)
    await _stamp_alembic(client)
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        ev = (await conn.execute(text(
            "SELECT id, event_hash FROM shot_intra_shot_events "
            "WHERE shot_id = :s AND deleted_at IS NULL"),
            {"s": sid})).one()
    # decline_persistence carries expected_handoff = null (frozen
    # §7.5.1); the operation records the same fields the basis derives
    # from, plus the basis root itself
    basis = event_review_basis_hash(
        source_event_id=ev[0], source_hash=ev[1],
        decision="decline_persistence",
        expected_working_snapshot_hash=revision.snapshot_hash,
        expected_event_set_hash=revision.snapshot_hash,
        expected_handoff=None)
    op = {
        "schema_version": 1,
        "source": {"kind": "event", "id": ev[0], "hash": ev[1]},
        "decision": "decline_persistence",
        "expected_working_snapshot_hash": revision.snapshot_hash,
        "expected_event_set_hash": revision.snapshot_hash,
        "expected_handoff": None,
        "review_basis_hash": basis,
    }
    op_json = _cjs(op)
    rid = "00000000-0000-4000-8000-0000000000c1"
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO persistent_consequence_reviews "
            "(id, shot_id, source_kind, source_event_id, "
            "source_proposal_id, source_hash, decision, "
            "review_basis_hash, result_event_id, "
            "entity_feature_transition_id, entity_relation_transition_id, "
            "production_instance_feature_transition_id, operation_json, "
            "operation_hash, created_at) VALUES ("
            ":rid, :s, 'event', :eid, NULL, :sh, "
            "'decline_persistence', :bh, :eid, NULL, NULL, NULL, :oj, "
            ":oh, strftime('%Y-%m-%dT%H:%M:%fZ','now'))"),
            {"rid": rid, "s": sid, "eid": ev[0], "sh": ev[1],
             "bh": basis, "oj": op_json, "oh": _ch(op)})
    backup_root = tmp_path / "bk-r"
    await backup(await _settings(client), backup_root)

    # coherent mutation: ONLY the recorded basis column moves — the
    # operation document (and its hash) stay canonical, so the failure
    # must come from the basis recompute itself
    db_file = backup_root / "soloring.db"
    con = sqlite3.connect(str(db_file))
    con.execute(
        "UPDATE persistent_consequence_reviews SET "
        "review_basis_hash = :b WHERE id = :rid",
        {"b": "2" * 64, "rid": rid})
    con.commit()
    con.close()
    manifest_path = backup_root / "backup-manifest.json"
    manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["database_sha256"] = hashlib.sha256(
        db_file.read_bytes()).hexdigest()
    manifest_path.write_bytes(canonical_json_bytes(manifest))

    try:
        await restore(backup_root, tmp_path / "ref-r")
    except Exception as exc:
        assert "basis" in str(exc).lower(), str(exc)
    else:
        raise AssertionError("mutated review basis restored")


async def test_recovery_05(client, factory, tmp_path):
    """RECOVERY:05 — a valid captured history backs up cleanly; a
    coherently re-hashed PI/feature identity that changes the OWNER
    entity fails restore at the §8.4 identity binding."""
    import hashlib
    import json as _json
    import sqlite3

    from soloring.domain.canonical import (
        canonical_hash as _ch,
        canonical_json_bytes,
        canonical_json_str as _cjs,
    )
    from soloring.recovery.backup import backup, restore

    base, sid, fid, revision = await _seed_world_with_history(
        client, factory)
    await _stamp_alembic(client)
    backup_root = tmp_path / "bk-c"
    await backup(await _settings(client), backup_root)

    db_file = backup_root / "soloring.db"
    con = sqlite3.connect(str(db_file))
    row = con.execute(
        "SELECT captured_target_identity_json FROM "
        "shot_revision_intra_shot_events "
        "WHERE shot_revision_id = ?", (revision.id,)).fetchone()
    identity = _json.loads(row[0])
    identity["entity_id"] = "00000000-0000-4000-8000-0000000000ff"
    tampered = _cjs(identity)
    con.execute(
        "UPDATE shot_revision_intra_shot_events SET "
        "captured_target_identity_json = :j, "
        "captured_target_identity_hash = :h WHERE shot_revision_id = :r",
        {"j": tampered, "h": _ch(identity), "r": revision.id})
    con.commit()
    con.close()
    manifest_path = backup_root / "backup-manifest.json"
    manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["database_sha256"] = hashlib.sha256(
        db_file.read_bytes()).hexdigest()
    manifest_path.write_bytes(canonical_json_bytes(manifest))

    try:
        await restore(backup_root, tmp_path / "ref-c")
    except Exception as exc:
        assert "identity" in str(exc).lower() \
            or "disagrees" in str(exc).lower(), str(exc)
    else:
        raise AssertionError("coherently re-hashed identity restored")


async def test_recovery_06(client, factory,
                                                 tmp_path):
    """A captured after-state whose hash breaks the re-fold fails."""
    from soloring.recovery.backup import backup, restore

    base, sid, fid, revision = await _seed_world_with_history(
        client, factory)
    await _stamp_alembic(client)
    engine = client._transport.app.state.engine
    import hashlib
    import json as _json

    from soloring.domain.canonical import canonical_json_bytes

    backup_root = tmp_path / "bk-f"
    await backup(await _settings(client), backup_root)
    import sqlite3

    db_file = backup_root / "soloring.db"
    con = sqlite3.connect(str(db_file))
    con.execute(
        "UPDATE shot_revision_intra_shot_events SET "
        "captured_after_state_hash = :h", {"h": "0" * 64})
    con.commit()
    con.close()
    manifest_path = backup_root / "backup-manifest.json"
    manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["database_sha256"] = hashlib.sha256(
        db_file.read_bytes()).hexdigest()
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    try:
        await restore(backup_root, tmp_path / "ref-f")
    except Exception as exc:
        assert "hash" in str(exc).lower() or "intra" in str(exc).lower()
    else:
        raise AssertionError("re-fold mismatch restored")

async def test_recovery_07(client, factory):
    """0011-0016 remain accepted; 0017 is the expected head."""
    import importlib

    _rb = importlib.import_module("soloring.recovery.backup")

    EH = _rb.EXPECTED_ALEMBIC_HEAD
    SH = _rb.SUPPORTED_RESTORE_ALEMBIC_HEADS
    policy = _rb._blob_fk_policy_for_head

    assert EH == "0017_m16_intra_shot_consequences"
    assert set(SH) == {
        "0011_m10_derived_spatial_execution",
        "0012_m11_reusable_production_revisions",
        "0013_m12_composition_occurrences",
        "0014_m13_authority_complete_world",
        "0015_m14_world_observation_execution",
        "0016_m15_revision_compatibility",
        "0017_m16_intra_shot_consequences",
    }

async def test_recovery_08(client, factory):
    """0017 keeps the exact published 8-path inventory; unknown heads
    stay unsupported."""
    import importlib

    _rb = importlib.import_module("soloring.recovery.backup")

    EH = _rb.EXPECTED_ALEMBIC_HEAD
    SH = _rb.SUPPORTED_RESTORE_ALEMBIC_HEADS
    policy = _rb._blob_fk_policy_for_head

    inventory = policy("0017_m16_intra_shot_consequences")
    assert len(inventory) == 8
    try:
        policy("0099_m99_future")
    except Exception:
        pass
    else:
        raise AssertionError("unknown head admitted")
