"""Wrong-domain transition + malformed expected_handoff regressions."""

from __future__ import annotations

import hashlib
import json as _json
import sqlite3

from sqlalchemy import text

from soloring.continuity.intra_shot_canonical import (
    event_review_basis_hash,
)
from soloring.domain.canonical import (
    canonical_hash as _ch,
    canonical_json_bytes,
    canonical_json_str as _cjs,
)
from tests.m16_seed_b import (
    event,
    get_intra,
    post_event,
    put_relation_transition,
    put_transition,
    seed_feature_world,
    seed_relation_world,
    state,
)
from tests.test_m16_capture import _capture
from tests.test_m16_recovery import _settings, _stamp_alembic


def _rehash_manifest(backup_root):
    # checkpoint any WAL sidecar into the main file first: the restore
    # copies only soloring.db, so mutations left in a -wal would be
    # silently invisible to the staged verification
    con = sqlite3.connect(str(backup_root / "soloring.db"))
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()
    manifest_path = backup_root / "backup-manifest.json"
    manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["database_sha256"] = hashlib.sha256(
        (backup_root / "soloring.db").read_bytes()).hexdigest()
    manifest_path.write_bytes(canonical_json_bytes(manifest))


async def _valid_direct_adopt_review(client, factory):
    """A valid direct adopt_persistence review: require_handoff event at
    1000 on a feature, exact Shot/end transition, correct §7.5.1 basis
    with expected_handoff {target, anchor, semantic_hash}."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    ev = await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    await put_transition(client, fid, sid, operation="set", value="fresh")
    revision, _ = await _capture(client, sid)
    await _stamp_alembic(client)
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        tr = (await conn.execute(text(
            "SELECT id FROM continuity_feature_transitions WHERE "
            "feature_id = :f AND anchor_id = :s AND boundary = 'end' "
            "AND deleted_at IS NULL"),
            {"f": fid, "s": sid})).one()

    semantic = {
        "domain": "entity_feature",
        "target": {"kind": "entity_feature", "id": fid},
        "anchor": {"anchor_type": "shot", "anchor_id": sid,
                   "boundary": "end"},
        "operation": "set", "state": state("fresh"),
    }
    semantic_hash = _ch(semantic)
    eh = {
        "target": {"kind": "entity_feature", "id": fid},
        "anchor": {"anchor_type": "shot", "anchor_id": sid,
                   "boundary": "end"},
        "semantic_hash": semantic_hash,
    }
    basis = event_review_basis_hash(
        source_event_id=ev["id"], source_hash=ev["event_hash"],
        decision="adopt_persistence",
        expected_working_snapshot_hash=revision.snapshot_hash,
        expected_event_set_hash=(await get_intra(
            client, sid))["event_set_hash"],
        expected_handoff=eh)
    op = {
        "schema_version": 1,
        "source": {"kind": "event", "id": ev["id"],
                   "hash": ev["event_hash"]},
        "decision": "adopt_persistence",
        "expected_working_snapshot_hash": revision.snapshot_hash,
        "expected_event_set_hash": (await get_intra(
            client, sid))["event_set_hash"],
        "expected_handoff": eh,
        "review_basis_hash": basis,
        "result": {"event_id": ev["id"],
                   "event_hash": ev["event_hash"],
                   "transition": {"kind": "entity_feature",
                                  "semantic_hash": semantic_hash}},
    }
    rid = "00000000-0000-4000-8000-0000000000g1"
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO persistent_consequence_reviews "
            "(id, shot_id, source_kind, source_event_id, "
            "source_proposal_id, source_hash, decision, "
            "review_basis_hash, result_event_id, "
            "entity_feature_transition_id, entity_relation_transition_id, "
            "production_instance_feature_transition_id, operation_json, "
            "operation_hash, created_at) VALUES ("
            ":rid, :s, 'event', :eid, NULL, :sh, 'adopt_persistence', "
            ":bh, :eid, :tid, NULL, NULL, :oj, :oh, "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"),
            {"rid": rid, "s": sid, "eid": ev["id"],
             "sh": ev["event_hash"], "bh": basis, "tid": tr[0],
             "oj": _cjs(op), "oh": _ch(op)})
    return {"base": base, "sid": sid, "fid": fid, "ev": ev,
            "review_id": rid, "op": op, "tr": tr[0]}


async def _backup(client, tmp_path, tag):
    from soloring.recovery.backup import backup

    root = tmp_path / f"bk-{tag}"
    await backup(await _settings(client), root)
    return root


async def test_recovery_direct_adopt_valid_restores(client, factory,
                                                    tmp_path):
    """The valid direct adopt_persistence review restores cleanly."""
    world = await _valid_direct_adopt_review(client, factory)
    await _backup(client, tmp_path, "dav")
    from soloring.recovery.backup import restore

    await restore(tmp_path / "bk-dav", tmp_path / "ref-dav")


async def test_recovery_wrong_domain_transition_fails(client, factory,
                                                      tmp_path):
    """A review whose row + operation move the transition reference to
    the RELATION domain while the reviewed event targets a FEATURE
    fails the domain binding (the relation transition itself is real
    and Shot/end-anchored on the same Shot)."""
    from soloring.recovery.backup import restore
    from tests.m16_seed_b import seed_relation_world

    world = await _valid_direct_adopt_review(client, factory)
    sid = world["sid"]
    # a REAL relation with a real Shot/end transition on the same Shot
    rel_world = None
    engine = client._transport.app.state.engine
    # create a relation world sharing the same project/shot is complex;
    # instead insert a relation + transition bound to this Shot directly
    from soloring.domain.ids import new_uuid

    rel_id = new_uuid()
    pred_id = new_uuid()
    second_entity = new_uuid()
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO creative_entities (id, project_id, kind, name, "
            "created_at) VALUES (:e, :proj, 'prop', 'RelObj', "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"),
            {"e": second_entity, "proj": world["base"]["project_id"]})
        await conn.execute(text(
            "INSERT INTO continuity_predicates (id, project_id, key, "
            "name, created_at, updated_at) VALUES ("
            ":p, :proj, 'holds', 'Holds', "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now'), "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"),
            {"p": pred_id, "proj": world["base"]["project_id"]})
        await conn.execute(text(
            "INSERT INTO continuity_relations (id, project_id, "
            "subject_entity_id, predicate_id, object_entity_id, "
            "created_at) VALUES ("
            ":r, :proj, :sub, :pred, :obj, "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"),
            {"r": rel_id, "proj": world["base"]["project_id"],
             "sub": world["base"]["entity_id"],
             "pred": pred_id, "obj": second_entity})
        await conn.execute(text(
            "INSERT INTO continuity_relation_transitions (id, "
            "relation_id, anchor_type, anchor_id, boundary, state, "
            "created_at, updated_at) VALUES ("
            ":t, :r, 'shot', :s, 'end', 'active', "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now'), "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"),
            {"t": new_uuid(), "r": rel_id, "s": sid})

    backup_root = await _backup(client, tmp_path, "wd")
    rel_tr = sqlite3.connect(str(backup_root / "soloring.db")).execute(
        "SELECT id FROM continuity_relation_transitions WHERE "
        "relation_id = ?", (rel_id,)).fetchone()[0]
    con = sqlite3.connect(str(backup_root / "soloring.db"))
    op = _json.loads(con.execute(
        "SELECT operation_json FROM persistent_consequence_reviews "
        "WHERE id = ?", (world["review_id"],)).fetchone()[0])
    op["result"]["transition"] = {"kind": "entity_relation",
                                  "semantic_hash":
                                      op["result"]["transition"][
                                          "semantic_hash"]}
    con.execute(
        "UPDATE persistent_consequence_reviews SET "
        "entity_feature_transition_id = NULL, "
        "entity_relation_transition_id = :tid, operation_json = :oj, "
        "operation_hash = :oh WHERE id = :rid",
        {"tid": rel_tr, "oj": _cjs(op), "oh": _ch(op),
         "rid": world["review_id"]})
    con.commit()
    con.close()
    _rehash_manifest(backup_root)
    try:
        await restore(backup_root, tmp_path / "ref-wd")
    except Exception as exc:
        assert "domain" in str(exc).lower()             or "target" in str(exc).lower(), str(exc)
    else:
        raise AssertionError("wrong-domain transition restored")


async def test_recovery_foreign_expected_handoff_target_fails(
        client, factory, tmp_path):
    """A coherently re-hashed basis whose expected_handoff targets a
    FOREIGN feature fails the §7.5.1 coordinate check."""
    from soloring.recovery.backup import restore

    world = await _valid_direct_adopt_review(client, factory)
    backup_root = await _backup(client, tmp_path, "fh")
    con = sqlite3.connect(str(backup_root / "soloring.db"))
    op = _json.loads(con.execute(
        "SELECT operation_json FROM persistent_consource_reviews "
        "WHERE id = ?", (world["review_id"],)).fetchone()[0]
        if False else con.execute(
        "SELECT operation_json FROM "
        "persistent_consequence_reviews WHERE id = ?",
        (world["review_id"],)).fetchone()[0])
    foreign = "00000000-0000-4000-8000-0000000000ff"
    eh = dict(op["expected_handoff"])
    eh["target"] = {"kind": "entity_feature", "id": foreign}
    op["expected_handoff"] = eh
    op["result"]["transition"]["semantic_hash"] = eh["semantic_hash"]
    basis = event_review_basis_hash(
        source_event_id=world["ev"]["id"],
        source_hash=world["ev"]["event_hash"],
        decision="adopt_persistence",
        expected_working_snapshot_hash=op[
            "expected_working_snapshot_hash"],
        expected_event_set_hash=op["expected_event_set_hash"],
        expected_handoff=eh)
    op["review_basis_hash"] = basis
    con.execute(
        "UPDATE persistent_consequence_reviews SET "
        "review_basis_hash = :bh, operation_json = :oj, "
        "operation_hash = :oh WHERE id = :rid",
        {"bh": basis, "oj": _cjs(op), "oh": _ch(op),
         "rid": world["review_id"]})
    con.commit()
    con.close()
    _rehash_manifest(backup_root)
    try:
        await restore(backup_root, tmp_path / "ref-fh")
    except Exception as exc:
        assert "expected_handoff" in str(exc).lower() \
            or "target" in str(exc).lower(), str(exc)
    else:
        raise AssertionError("foreign expected_handoff target restored")
