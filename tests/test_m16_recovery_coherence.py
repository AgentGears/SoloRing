"""Coherent-rehash regressions for the H-round recovery bindings."""

from __future__ import annotations

import hashlib
import json as _json
import sqlite3

from sqlalchemy import text

from soloring.domain.canonical import (
    canonical_hash as _ch,
    canonical_json_bytes,
    canonical_json_str as _cjs,
)
from tests.test_m16_recovery import _settings, _stamp_alembic
from tests.test_m16_recovery_proposals import (
    _valid_proposal_review_world,
)


def _rehash_manifest(backup_root):
    manifest_path = backup_root / "backup-manifest.json"
    manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["database_sha256"] = hashlib.sha256(
        (backup_root / "soloring.db").read_bytes()).hexdigest()
    manifest_path.write_bytes(canonical_json_bytes(manifest))


def _load_op(con, review_id):
    return _json.loads(con.execute(
        "SELECT operation_json FROM persistent_consequence_reviews "
        "WHERE id = ?", (review_id,)).fetchone()[0])


def _store_op(con, review_id, op):
    con.execute(
        "UPDATE persistent_consequence_reviews SET operation_json = :oj,"
        " operation_hash = :oh WHERE id = :rid",
        {"oj": _cjs(op), "oh": _ch(op), "rid": review_id})


async def _backup(client, tmp_path, tag):
    from soloring.recovery.backup import backup

    root = tmp_path / f"bk-{tag}"
    await backup(await _settings(client), root)
    return root


async def test_recovery_foreign_batch_source_fails(client, factory,
                                                   tmp_path):
    """A well-formed batch object rooted in a DIFFERENT source
    ShotRevision (and Shot) fails, even with the review as a member."""
    from soloring.recovery.backup import restore
    from soloring.continuity.intra_shot_canonical import (
        proposal_batch_basis_hash,
        proposal_review_basis_hash,
    )

    world = await _valid_proposal_review_world(client, factory)
    backup_root = await _backup(client, tmp_path, "fbs")
    con = sqlite3.connect(str(backup_root / "soloring.db"))
    op = _load_op(con, world["review_id"])
    foreign_rev = "00000000-0000-4000-8000-0000000000aa"
    bb = dict(op["batch_basis"])
    bb["shot_id"] = "00000000-0000-4000-8000-0000000000bb"
    bb["source_shot_revision_id"] = foreign_rev
    bb["source_shot_revision_hash"] = "3" * 64
    op["batch_basis"] = bb
    op["batch_basis_hash"] = proposal_batch_basis_hash(
        shot_id=bb["shot_id"],
        source_shot_revision_id=bb["source_shot_revision_id"],
        source_shot_revision_hash=bb["source_shot_revision_hash"],
        expected_working_snapshot_hash=bb[
            "expected_working_snapshot_hash"],
        expected_event_set_hash=bb["expected_event_set_hash"],
        reviews=bb["reviews"])
    op["review_basis_hash"] = proposal_review_basis_hash(
        batch_basis_hash=op["batch_basis_hash"],
        proposal_id=world["proposal_id"],
        proposal_hash=op["source"]["hash"],
        decision="adopt_persistence")
    _store_op(con, world["review_id"], op)
    con.execute(
        "UPDATE persistent_consequence_reviews SET "
        "review_basis_hash = :bh WHERE id = :rid",
        {"bh": op["review_basis_hash"], "rid": world["review_id"]})
    con.commit()
    con.close()
    _rehash_manifest(backup_root)
    try:
        await restore(backup_root, tmp_path / "ref-fbs")
    except Exception as exc:
        assert "shot" in str(exc).lower() \
            or "source" in str(exc).lower(), str(exc)
    else:
        raise AssertionError("foreign batch source restored")


async def test_recovery_wrong_target_result_reference_fails(
        client, factory, tmp_path):
    """A same-Shot result event on an UNRELATED target fails the
    provenance target binding (coherently re-hashed operation)."""
    from tests.m16_seed_b import (
        event as _event,
        post_event,
        seed_feature_world,
        state,
    )
    from tests.test_m16_recovery_proposals import (
        _valid_proposal_review_world,
    )
    from soloring.recovery.backup import restore

    world = await _valid_proposal_review_world(client, factory)
    # a second feature on the same Shot; a second (unrelated) event
    base = world["base"]
    other = await _add_second_feature(client, factory, base)
    other_event = await post_event(
        client, world["sid"],
        _event(other, 1800, state(), state("torn"), ordinal=1))
    backup_root = await _backup(client, tmp_path, "wt")
    con = sqlite3.connect(str(backup_root / "soloring.db"))
    op = _load_op(con, world["review_id"])
    # point the row + record at the unrelated event (same Shot)
    op["result"]["event_id"] = other_event["id"]
    op["result"]["event_hash"] = other_event["event_hash"]
    _store_op(con, world["review_id"], op)
    con.execute(
        "UPDATE persistent_consequence_reviews SET result_event_id = :eid"
        " WHERE id = :rid",
        {"eid": other_event["id"], "rid": world["review_id"]})
    con.commit()
    con.close()
    _rehash_manifest(backup_root)
    try:
        await restore(backup_root, tmp_path / "ref-wt")
    except Exception as exc:
        # the failure may fire at either invariant: the derived-candidate
        # hash check (result != candidate) or the provenance target
        # binding — both are correct rejections of the wrong-target row
        assert "target" in str(exc).lower()             or "candidate" in str(exc).lower(), str(exc)
    else:
        raise AssertionError("wrong-target result reference restored")


async def _add_second_feature(client, factory, base):
    fid = (await client.post(
        f"/entities/{base['entity_id']}/continuity-features",
        json={"key": "wardrobe", "kind": "wardrobe_condition",
              "value_type": "text", "name": "Wardrobe"})).json()["id"]
    return fid
