"""Valid proposal-review recovery fixture + four independent corruptions."""

from __future__ import annotations

import hashlib
import json as _json
import sqlite3

from sqlalchemy import text

from soloring.continuity.intra_shot_canonical import (
    proposal_batch_basis_hash,
    proposal_batch_basis_value,
    proposal_review_basis_hash,
    proposal_storage,
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
    put_transition,
    seed_feature_world,
    state,
)
from tests.test_m16_capture import _capture
from tests.test_m16_proposals import _capture_revision, _ingest
from tests.test_m16_recovery import _settings, _stamp_alembic

async def _valid_proposal_review_world(client, factory):
    """One event-bearing Shot + a valid imported proposal + a valid
    adopt_persistence proposal review over it (correct batch object,
    membership, basis roots, and committed result evidence)."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    # NO working events or transitions: the ONLY event is the adopted
    # candidate itself, created below — matching §12.3 exactly
    revision, _ = await _capture(client, sid)
    await _stamp_alembic(client)
    engine = client._transport.app.state.engine

    value, pj, ph = proposal_storage(
        candidate_event={
            "time_ms": 1500, "ordinal": 0,
            "target": {"kind": "entity_feature", "id": fid},
            "before": state(), "after": state("fresh")},
        persistence_suggestion="persist")
    pid = "00000000-0000-4000-8000-0000000000d1"
    pid2 = "00000000-0000-4000-8000-0000000000d2"
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
    # a second valid imported proposal (used by the completeness
    # corruption: an orphan review rooted at the FIRST batch)
    value2, pj2, ph2 = proposal_storage(
        candidate_event={
            "time_ms": 1600, "ordinal": 0,
            "target": {"kind": "entity_feature", "id": fid},
            "before": state(), "after": state("scarred")
            if False else state("healing")},
        persistence_suggestion="transient")
    # distinct semantics: healing -> fresh is taken; use a distinct chain
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
            {"pid": pid2, "s": sid, "r": revision.id,
             "h": revision.snapshot_hash, "pj": pj2, "ph": ph2})

    # §12.3: adopt_persistence creates the CANDIDATE itself as a
    # require_handoff event (1500ms, absent -> fresh) plus the exact A2
    # handoff (set fresh)
    res = await post_event(
        client, sid,
        event(fid, 1500, state(), state("fresh"),
              persistence="require_handoff"))
    assert res is not None
    await put_transition(
        client, fid, sid, operation="set", value="fresh")
    result_event_id = res["id"]
    async with engine.connect() as conn:
        transition = (await conn.execute(text(
            "SELECT id FROM continuity_feature_transitions WHERE "
            "feature_id = :f AND anchor_id = :s AND boundary = 'end' "
            "AND deleted_at IS NULL"),
            {"f": fid, "s": sid})).one()
    # the committed transition semantic hash: the canonical §4.8 handoff
    # of the ADOPTED candidate's terminal state (set fresh)
    from soloring.domain.canonical import canonical_hash as _ch2

    semantic_handoff = {
        "domain": "entity_feature",
        "target": {"kind": "entity_feature", "id": fid},
        "anchor": {"anchor_type": "shot", "anchor_id": sid,
                   "boundary": "end"},
        "operation": "set",
        "state": state("fresh"),
    }
    transition_semantic_hash = _ch2(semantic_handoff)
    batch_reviews = [{
        "proposal_id": pid,
        "proposal_hash": ph,
        "decision": "adopt_persistence",
    }]
    _ = pid2
    # the recorded batch object is the EXACT canonical value that was
    # hashed (schema_version, reviews sorted by proposal UUID)
    batch_doc = proposal_batch_basis_value(
        shot_id=sid,
        source_shot_revision_id=revision.id,
        source_shot_revision_hash=revision.snapshot_hash,
        expected_working_snapshot_hash=revision.snapshot_hash,
        expected_event_set_hash=revision.snapshot_hash,
        reviews=batch_reviews)
    batch_basis = _ch(batch_doc)
    basis = proposal_review_basis_hash(
        batch_basis_hash=batch_basis, proposal_id=pid,
        proposal_hash=ph, decision="adopt_persistence")
    op = {
        "schema_version": 1,
        "source": {"kind": "proposal", "id": pid, "hash": ph},
        "decision": "adopt_persistence",
        "batch_basis_hash": batch_basis,
        "batch_basis": batch_doc,
        "review_basis_hash": basis,
        "result": {
            "event_id": result_event_id,
            "event_hash": res["event_hash"],
            "transition": {"kind": "entity_feature",
                           "semantic_hash": transition_semantic_hash},
        },
    }
    rid = "00000000-0000-4000-8000-0000000000e1"
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO persistent_consequence_reviews "
            "(id, shot_id, source_kind, source_event_id, "
            "source_proposal_id, source_hash, decision, "
            "review_basis_hash, result_event_id, "
            "entity_feature_transition_id, entity_relation_transition_id, "
            "production_instance_feature_transition_id, operation_json, "
            "operation_hash, created_at) VALUES ("
            ":rid, :s, 'proposal', NULL, :pid, :sh, "
            "'adopt_persistence', :bh, :eid, :tid, NULL, NULL, :oj, "
            ":oh, strftime('%Y-%m-%dT%H:%M:%fZ','now'))"),
            {"rid": rid, "s": sid, "pid": pid, "sh": ph,
             "bh": basis, "eid": result_event_id, "tid": transition[0],
             "oj": _cjs(op), "oh": _ch(op)})
    return {
        "base": base, "sid": sid, "fid": fid, "revision": revision,
        "proposal_id": pid, "review_id": rid, "op": op,
        "proposal2_hash": ph2,
        "batch_basis": batch_basis, "batch_doc": batch_doc,
        "result_event_id": result_event_id,
    }


async def _roundtrip(client, tmp_path, tag):
    from soloring.recovery.backup import backup, restore

    backup_root = tmp_path / f"bk-{tag}"
    await backup(await _settings(client), backup_root)
    dest = tmp_path / f"restored-{tag}"
    await restore(backup_root, dest)
    return backup_root


def _retamper(backup_root, sql, params):
    con = sqlite3.connect(str(backup_root / "soloring.db"))
    con.execute(sql, params)
    con.commit()
    con.close()
    manifest_path = backup_root / "backup-manifest.json"
    manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["database_sha256"] = hashlib.sha256(
        (backup_root / "soloring.db").read_bytes()).hexdigest()
    manifest_path.write_bytes(canonical_json_bytes(manifest))


def _rewrite_op(backup_root, review_id, mutate):
    con = sqlite3.connect(str(backup_root / "soloring.db"))
    row = con.execute(
        "SELECT operation_json FROM persistent_consequence_reviews "
        "WHERE id = ?", (review_id,)).fetchone()
    op = _json.loads(row[0])
    mutate(op)
    con.execute(
        "UPDATE persistent_consequence_reviews SET operation_json = :oj,"
        " operation_hash = :oh WHERE id = :rid",
        {"oj": _cjs(op), "oh": _ch(op), "rid": review_id})
    con.commit()
    con.close()
    manifest_path = backup_root / "backup-manifest.json"
    manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["database_sha256"] = hashlib.sha256(
        (backup_root / "soloring.db").read_bytes()).hexdigest()
    manifest_path.write_bytes(canonical_json_bytes(manifest))


async def test_recovery_proposal_review_valid_restores(client, factory,
                                                       tmp_path):
    """A fully valid adopt_persistence proposal review (batch object,
    membership, basis roots, committed result evidence) restores
    cleanly at 0017."""
    world = await _valid_proposal_review_world(client, factory)
    await _roundtrip(client, tmp_path, "valid")


async def test_recovery_proposal_result_hash_corrupt(client, factory,
                                                     tmp_path):
    world = await _valid_proposal_review_world(client, factory)
    backup_root = await _roundtrip(client, tmp_path, "rh")
    _rewrite_op(backup_root, world["review_id"], lambda op: (
        op["result"].update(event_hash="0" * 64)))
    from soloring.recovery.backup import restore

    try:
        await restore(backup_root, tmp_path / "ref-rh")
    except Exception as exc:
        assert "result" in str(exc).lower() or "hash" in str(exc).lower()
    else:
        raise AssertionError("corrupt result event hash restored")


async def test_recovery_proposal_transition_evidence_corrupt(
        client, factory, tmp_path):
    world = await _valid_proposal_review_world(client, factory)
    backup_root = await _roundtrip(client, tmp_path, "te")
    _rewrite_op(backup_root, world["review_id"], lambda op: (
        op["result"]["transition"].update(semantic_hash="0" * 64)))
    from soloring.recovery.backup import restore

    try:
        await restore(backup_root, tmp_path / "ref-te")
    except Exception as exc:
        assert "transition" in str(exc).lower() \
            or "semantic" in str(exc).lower()
    else:
        raise AssertionError("corrupt transition evidence restored")


async def test_recovery_proposal_batch_membership_corrupt(
        client, factory, tmp_path):
    world = await _valid_proposal_review_world(client, factory)
    backup_root = await _roundtrip(client, tmp_path, "bm")
    # swap the member entry for a foreign proposal id — the batch hash
    # and per-review root are recomputed so ONLY membership fails
    con = sqlite3.connect(str(backup_root / "soloring.db"))

    def mutate(op):
        foreign = "00000000-0000-4000-8000-0000000000f9"
        op["batch_basis"]["reviews"][0]["proposal_id"] = foreign
        bb = op["batch_basis"]
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
            proposal_hash=world["op"]["source"]["hash"],
            decision="adopt_persistence")
    row = con.execute(
        "SELECT operation_json FROM persistent_consequence_reviews "
        "WHERE id = ?", (world["review_id"],)).fetchone()
    op = _json.loads(row[0])
    mutate(op)
    con.execute(
        "UPDATE persistent_consequence_reviews SET operation_json = :oj,"
        " operation_hash = :oh, review_basis_hash = :bh "
        "WHERE id = :rid",
        {"oj": _cjs(op), "oh": _ch(op),
         "bh": op["review_basis_hash"], "rid": world["review_id"]})
    con.commit()
    con.close()
    manifest_path = backup_root / "backup-manifest.json"
    manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["database_sha256"] = hashlib.sha256(
        (backup_root / "soloring.db").read_bytes()).hexdigest()
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    from soloring.recovery.backup import restore

    try:
        await restore(backup_root, tmp_path / "ref-bm")
    except Exception as exc:
        assert "member" in str(exc).lower() \
            or "batch" in str(exc).lower()
    else:
        raise AssertionError("foreign batch member restored")


async def test_recovery_proposal_batch_completeness_corrupt(
        client, factory, tmp_path):
    """An EXTRA persisted proposal-review row rooted at the batch (not
    in the batch object) fails completeness."""
    world = await _valid_proposal_review_world(client, factory)
    backup_root = await _roundtrip(client, tmp_path, "bc")
    orphan = "00000000-0000-4000-8000-0000000000e2"
    con = sqlite3.connect(str(backup_root / "soloring.db"))
    op = _json.loads(con.execute(
        "SELECT operation_json FROM persistent_consequence_reviews "
        "WHERE id = ?", (world["review_id"],)).fetchone()[0])
    # a second proposal row rooted at the SAME batch but for a DIFFERENT
    # (source_hash) review basis of the same proposal — the partial
    # unique index (source_proposal_id, source_hash) blocks exact-dup,
    # so completeness corruption is exercised via a foreign proposal id
    foreign_pid = "00000000-0000-4000-8000-0000000000d2"
    foreign_hash = world["proposal2_hash"]
    foreign_op = {**op, "decision": "ignore",
                  "batch_basis_hash": op["batch_basis_hash"],
                  "source": {"kind": "proposal", "id": foreign_pid,
                             "hash": foreign_hash},
                  "review_basis_hash": proposal_review_basis_hash(
                      batch_basis_hash=op["batch_basis_hash"],
                      proposal_id=foreign_pid,
                      proposal_hash=foreign_hash, decision="ignore")}
    con.execute(
        "INSERT INTO persistent_consequence_reviews "
        "(id, shot_id, source_kind, source_event_id, "
        "source_proposal_id, source_hash, decision, "
        "review_basis_hash, result_event_id, "
        "entity_feature_transition_id, entity_relation_transition_id, "
        "production_instance_feature_transition_id, operation_json, "
        "operation_hash, created_at) VALUES ("
        ":rid, :s, 'proposal', NULL, :pid, :sh, 'ignore', :bh, NULL, "
        "NULL, NULL, NULL, :oj, :oh, "
        "strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
        {"rid": orphan, "s": world["sid"],
         "pid": foreign_pid, "sh": foreign_hash,
         "bh": foreign_op["review_basis_hash"],
         "oj": _cjs(foreign_op), "oh": _ch(foreign_op)})
    con.commit()
    con.close()
    manifest_path = backup_root / "backup-manifest.json"
    manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["database_sha256"] = hashlib.sha256(
        (backup_root / "soloring.db").read_bytes()).hexdigest()
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    from soloring.recovery.backup import restore

    try:
        await restore(backup_root, tmp_path / "ref-bc")
    except Exception as exc:
        assert "batch" in str(exc).lower() \
            or "member" in str(exc).lower()
    else:
        raise AssertionError("orphan batch review restored")

async def test_recovery_d_written_review_rows_restore(client, factory,
                                                       tmp_path):
    """D-written review rows survive backup/restore at C depth: a
    single-source mixed-decision batch (authority adoption + ignore) on
    an event-free Shot records the §7.5.2 nullable basis values as JSON
    null — never "" — and a separate ignore-only batch records a null
    working hash. The staged restore runs the full certified verifier
    over these real D rows."""
    base = await seed_feature_world(
        client, factory, extra_feature_keys=("wardrobe",))
    sid = base["shot_id"]
    revision = await _capture_revision(client, sid)
    r1, _ = await _ingest(client, sid, base["feature_id"], revision)
    r2, _ = await _ingest(
        client, sid, base["wardrobe_feature_id"], revision, t=1600)
    p1, p2 = r1.json(), r2.json()
    # single-source mixed-decision batch BEFORE any event exists: the
    # recorded batch basis carries expected_event_set_hash = null
    rr = await client.post(
        f"/shots/{sid}/intra-shot/proposals/review-batch",
        json={"reviews": [
            {"proposal_id": p1["id"],
             "expected_proposal_hash": p1["proposal_hash"],
             "decision": "adopt_persistence"},
            {"proposal_id": p2["id"],
             "expected_proposal_hash": p2["proposal_hash"],
             "decision": "ignore"}]})
    assert rr.status_code == 200, rr.text
    # ignore-only batch: no authority member, so the working hash is
    # recorded as null as well
    r3, _ = await _ingest(
        client, sid, base["wardrobe_feature_id"], revision, t=1700)
    p3 = r3.json()
    sep = await client.post(
        f"/shots/{sid}/intra-shot/proposals/review-batch",
        json={"reviews": [
            {"proposal_id": p3["id"],
             "expected_proposal_hash": p3["proposal_hash"],
             "decision": "ignore"}]})
    assert sep.status_code == 200, sep.text
    await _stamp_alembic(client)
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT operation_json FROM "
            "persistent_consequence_reviews WHERE source_kind = "
            "'proposal' ORDER BY created_at"))).fetchall()
    docs = {_json.loads(r[0])["source"]["id"]: _json.loads(r[0])
            for r in rows}
    assert len(docs) == 3
    for d in docs.values():
        bb = d["batch_basis"]
        for field in ("expected_working_snapshot_hash",
                      "expected_event_set_hash"):
            # null or a real 64-hex hash — an empty string is not a
            # legal value anywhere in the frozen §7.5.2 grammar
            assert bb[field] is None or len(bb[field]) == 64
    # the event-free Shot batch recorded a null event set; the
    # ignore-only batch recorded a null working hash
    assert docs[p1["id"]]["batch_basis"][
        "expected_event_set_hash"] is None
    assert docs[p3["id"]]["batch_basis"][
        "expected_working_snapshot_hash"] is None
    # backup -> staged restore: the certified C-depth verifier must
    # accept every one of these D-written rows
    await _roundtrip(client, tmp_path, "dwrite")

async def test_recovery_proposal_batch_shape_noncanonical(client, factory,
                                                          tmp_path):
    """A recorded batch object that is not the EXACT canonical value
    (missing schema_version) fails restore even though its extracted
    fields re-derive the recorded basis root."""
    world = await _valid_proposal_review_world(client, factory)
    backup_root = await _roundtrip(client, tmp_path, "nc")
    con = sqlite3.connect(str(backup_root / "soloring.db"))
    op = _json.loads(con.execute(
        "SELECT operation_json FROM persistent_consequence_reviews "
        "WHERE id = ?", (world["review_id"],)).fetchone()[0])
    del op["batch_basis"]["schema_version"]
    # keep every recorded root consistent with the mutated field set so
    # ONLY the exact-canonical-shape rule can fail
    bb = op["batch_basis"]
    op["batch_basis_hash"] = proposal_batch_basis_hash(
        shot_id=bb["shot_id"],
        source_shot_revision_id=bb["source_shot_revision_id"],
        source_shot_revision_hash=bb["source_shot_revision_hash"],
        expected_working_snapshot_hash=bb["expected_working_snapshot_hash"],
        expected_event_set_hash=bb["expected_event_set_hash"],
        reviews=bb["reviews"])
    op["review_basis_hash"] = proposal_review_basis_hash(
        batch_basis_hash=op["batch_basis_hash"],
        proposal_id=world["proposal_id"],
        proposal_hash=world["op"]["source"]["hash"],
        decision="adopt_persistence")
    con.execute(
        "UPDATE persistent_consequence_reviews SET operation_json = :oj,"
        " operation_hash = :oh, review_basis_hash = :bh WHERE id = :rid",
        {"oj": _cjs(op), "oh": _ch(op), "bh": op["review_basis_hash"],
         "rid": world["review_id"]})
    con.commit()
    con.close()
    manifest_path = backup_root / "backup-manifest.json"
    manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["database_sha256"] = hashlib.sha256(
        (backup_root / "soloring.db").read_bytes()).hexdigest()
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    from soloring.recovery.backup import restore

    try:
        await restore(backup_root, tmp_path / "ref-nc")
    except Exception as exc:
        assert "canonical" in str(exc).lower()
    else:
        raise AssertionError("non-canonical batch object restored")
