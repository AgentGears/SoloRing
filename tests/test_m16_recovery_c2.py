"""M16:RECOVERY (part 2) — adversarial 0017 depth proofs (frozen §22)."""

from __future__ import annotations

from sqlalchemy import text

from tests.m16_seed_b import (
    event,
    post_event,
    put_transition,
    seed_feature_world,
    state,
)
from tests.test_m16_capture import _capture
from tests.test_m16_recovery_c import (
    _backup_and_restore,
    _seed_world_with_history,
    _stamp_alembic,
)


async def _settings(client):
    from soloring.settings import Settings

    return Settings(data_dir=client._transport.app.state.settings.data_dir)


async def test_recovery_03_proposal_corruption_fails(client, factory,
                                                     tmp_path):
    """A proposal with a corrupted hash/grammar fails the 0017 gate."""
    from soloring.recovery.backup import backup, restore

    base, sid, fid, revision = await _seed_world_with_history(
        client, factory)
    await _stamp_alembic(client)
    engine = client._transport.app.state.engine
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
            {"pid": "00000000-0000-4000-8000-0000000000b1",
             "s": sid, "r": revision.id, "h": revision.snapshot_hash,
             "pj": "{}", "ph": "0" * 64})
    backup_root = tmp_path / "bk-p"
    try:
        await backup(await _settings(client), backup_root)
    except Exception:
        pass
    try:
        await restore(backup_root, tmp_path / "ref-p")
    except Exception as exc:
        assert "proposal" in str(exc).lower()
    else:
        raise AssertionError("corrupted proposal restored")


async def test_recovery_04_review_basis_drift_fails(client, factory,
                                                    tmp_path):
    """A review whose recorded basis disagrees with the operation fails."""
    from soloring.recovery.backup import backup, restore

    base, sid, fid, revision = await _seed_world_with_history(
        client, factory)
    await _stamp_alembic(client)
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        event_id, event_hash = (await conn.execute(text(
            "SELECT id, event_hash FROM shot_intra_shot_events "
            "WHERE shot_id = :s AND deleted_at IS NULL"),
            {"s": sid})).one()
    from soloring.domain.canonical import canonical_json_str

    op = {"review_basis_hash": "0" * 64, "decision": "decline_persistence"}
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
            {"rid": "00000000-0000-4000-8000-0000000000c1",
             "s": sid, "eid": event_id, "sh": event_hash,
             "bh": "0" * 64,
             "oj": canonical_json_str(op),
             "oh": "0" * 64})
    backup_root = tmp_path / "bk-r"
    try:
        await backup(await _settings(client), backup_root)
    except Exception:
        pass
    try:
        await restore(backup_root, tmp_path / "ref-r")
    except Exception as exc:
        assert "review" in str(exc).lower() or "proposal" in str(exc).lower()
    else:
        raise AssertionError("basis-drifted review restored")


async def test_recovery_05_companion_corruption_fails(client, factory,
                                                      tmp_path):
    """A tampered captured target-identity column fails the 0017 gate."""
    from soloring.recovery.backup import backup, restore

    base, sid, fid, revision = await _seed_world_with_history(
        client, factory)
    await _stamp_alembic(client)
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE shot_revision_intra_shot_events SET "
            "captured_target_identity_json = :j "
            "WHERE shot_revision_id = :r"),
            {"j": "{}", "r": revision.id})
    backup_root = tmp_path / "bk-c"
    try:
        await backup(await _settings(client), backup_root)
    except Exception:
        pass
    try:
        await restore(backup_root, tmp_path / "ref-c")
    except Exception as exc:
        assert "intra_shot" in str(exc).lower() \
            or "companion" in str(exc).lower() \
            or "canonical" in str(exc).lower()
    else:
        raise AssertionError("corrupted companions restored")


async def test_recovery_06_refold_mismatch_fails(client, factory,
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


async def test_recovery_07_historical_heads_exact_policies(client, factory):
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


async def test_recovery_08_blob_fk_inventory_exactly_eight(client, factory):
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
