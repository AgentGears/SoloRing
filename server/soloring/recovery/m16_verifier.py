"""Full M16-depth recovery verification for head 0017 (frozen R6 §16.2).

Read-only: no proposal/review product operation is performed — only the
canonical/source/basis integrity of whatever rows exist. Every failure
RAISES RecoveryCorruption (no bare calls). History is enumerated from
the OUTER schema-7 snapshots, so a revision missing all companions is
corruption, not an escape.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from soloring.continuity.intra_shot_canonical import (
    MAX_PROPOSAL_CANONICAL_BYTES,
    proposal_value,
)
from soloring.continuity.intra_shot_history import (
    verify_intra_shot_history_sync,
    verify_working_event_row,
)
from soloring.domain.canonical import canonical_hash, canonical_json_str

_HEX = frozenset("0123456789abcdef")


def _corrupt(message: str):
    from soloring.recovery.backup import RecoveryCorruption

    raise RecoveryCorruption(message)


def _is_hash(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and set(value) <= _HEX)


def _pair(raw: str, digest: str, what: str):
    try:
        value = json.loads(raw)
    except (ValueError, TypeError) as exc:
        _corrupt(f"{what} is not valid JSON: {exc}")
    if canonical_json_str(value) != raw:
        _corrupt(f"{what} is not canonical JSON")
    if not _is_hash(digest) or canonical_hash(value) != digest:
        _corrupt(f"{what} hash mismatch")
    return value


def _verify_proposal_source(row, rows) -> None:
    (pid, shot_id, source_kind, source_rev_id, source_rev_hash,
     source_gen_id, source_take_id, proposer_kind, analyzer_id,
     analyzer_version, analyzer_params_hash, proposal_json,
     proposal_hash) = row
    doc = _pair(proposal_json, proposal_hash, f"proposal {pid}")

    # exact Proposal Grammar v1 (candidate shape + suggestion vocabulary)
    try:
        rebuilt = proposal_value(
            candidate_event=doc["candidate_event"],
            persistence_suggestion=doc["persistence_suggestion"])
    except Exception as exc:  # noqa: BLE001 — typed failure below
        _corrupt(f"proposal {pid} violates Proposal Grammar v1: {exc}")
    if canonical_json_str(rebuilt) != proposal_json:
        _corrupt(f"proposal {pid} is not the canonical grammar value")

    rev = rows(
        "SELECT snapshot_hash FROM shot_revisions WHERE id = ?",
        (source_rev_id,))
    if not rev:
        _corrupt(f"proposal {pid} pins missing source ShotRevision")
    if rev[0][0] != source_rev_hash:
        _corrupt(f"proposal {pid} source revision hash mismatch")
    snap = json.loads(rows(
        "SELECT snapshot_json FROM shot_revisions WHERE id = ?",
        (source_rev_id,))[0][0])
    if snap.get("intent", {}).get("duration_ms") is not None:
        duration = snap["intent"]["duration_ms"]
        t = doc["candidate_event"]["time_ms"]
        if not 1 <= t < duration:
            _corrupt(
                f"proposal {pid} time is not interior to the captured "
                "source duration")

    if source_kind == "generation":
        if source_gen_id is None or source_take_id is not None:
            _corrupt(f"proposal {pid} generation source shape invalid")
        gen = rows(
            "SELECT shot_id, shot_revision_id FROM generations "
            "WHERE id = ?", (source_gen_id,))
        if not gen:
            _corrupt(f"proposal {pid} pins missing Generation")
        if gen[0][0] != shot_id or gen[0][1] != source_rev_id:
            _corrupt(
                f"proposal {pid} Generation/Shot/ShotRevision lineage "
                "mismatch")
    elif source_kind == "take":
        if source_gen_id is None or source_take_id is None:
            _corrupt(f"proposal {pid} take source shape invalid")
        take = rows(
            "SELECT t.generation_id, g.shot_id, g.shot_revision_id "
            "FROM takes t JOIN generations g ON g.id = t.generation_id "
            "WHERE t.id = ?", (source_take_id,))
        if not take:
            _corrupt(f"proposal {pid} pins missing Take")
        # Take→Generation identity equality: the pinned generation id
        # must BE the Take's own generation
        if take[0][0] != source_gen_id:
            _corrupt(
                f"proposal {pid} pinned generation is not the Take's "
                "own generation")
        if take[0][1] != shot_id or take[0][2] != source_rev_id:
            _corrupt(
                f"proposal {pid} Take/Generation/Shot/ShotRevision "
                "lineage mismatch")
    elif source_kind == "imported":
        if source_gen_id is not None or source_take_id is not None:
            _corrupt(f"proposal {pid} imported source shape invalid")
    else:
        _corrupt(f"proposal {pid} unknown source kind {source_kind!r}")

    if proposer_kind == "human":
        if (analyzer_id is not None or analyzer_version is not None
                or analyzer_params_hash is not None):
            _corrupt(f"proposal {pid} human proposer carries analyzer data")
    elif proposer_kind == "analyzer":
        if (not isinstance(analyzer_id, str) or not analyzer_id
                or not isinstance(analyzer_version, str)
                or not analyzer_version
                or not _is_hash(analyzer_params_hash)):
            _corrupt(
                f"proposal {pid} analyzer proposer lacks exact "
                "id/version/parameter hash")
    else:
        _corrupt(f"proposal {pid} unknown proposer kind {proposer_kind!r}")


def _verify_review(row, rows) -> None:
    from soloring.continuity.intra_shot_canonical import (
        event_review_basis_hash as event_basis,
        proposal_review_basis_hash as proposal_basis,
    )

    (rid, shot_id, source_kind, source_event_id, source_proposal_id,
     source_hash, decision, review_basis_hash, result_event_id,
     ef_transition, er_transition, pf_transition, operation_json,
     operation_hash) = row
    doc = _pair(operation_json, operation_hash, f"review {rid}")

    if source_kind == "event":
        if source_proposal_id is not None or source_event_id is None:
            _corrupt(f"review {rid} event source shape invalid")
        ev = rows(
            "SELECT shot_id FROM shot_intra_shot_events WHERE id = ?",
            (source_event_id,))
        if not ev:
            _corrupt(f"review {rid} source event missing")
        if ev[0][0] != shot_id:
            _corrupt(f"review {rid} source event belongs to another Shot")
        if decision not in ("adopt_persistence", "decline_persistence"):
            _corrupt(f"review {rid} illegal event decision {decision!r}")
        # IMMUTABLE evidence semantics: recovery certifies the recorded
        # review, not today's mutable event/transition rows. The
        # operation document carries the exact committed source
        # coordinates; the basis root is recomputed from THEM.
        src_doc = doc.get("source")
        if (not isinstance(src_doc, dict)
                or src_doc.get("kind") != "event"
                or src_doc.get("id") != source_event_id
                or src_doc.get("hash") != source_hash):
            _corrupt(
                f"review {rid} operation source record disagrees with "
                "the review row's source coordinates")
        recomputed = event_basis(
            source_event_id=source_event_id, source_hash=source_hash,
            decision=decision,
            expected_working_snapshot_hash=doc.get(
                "expected_working_snapshot_hash", ""),
            expected_event_set_hash=doc.get("expected_event_set_hash", ""),
            expected_handoff=doc.get("expected_handoff"))
        if recomputed != review_basis_hash:
            _corrupt(
                f"review {rid} recorded basis is not the frozen event "
                "review-basis root")
        # the committed RESULT evidence is immutable-recorded: every
        # decision records the resulting event hash; adopt_persistence
        # additionally records the transition kind + exact semantic
        # hash. Current rows are provenance anchors only — later edits
        # make an exact RETRY conflict but never invalidate history.
        result = doc.get("result")
        if not isinstance(result, dict):
            _corrupt(f"review {rid} operation lacks the result record")
        if result.get("event_id") != result_event_id:
            _corrupt(
                f"review {rid} result record disagrees with the row's "
                "result event")
        if not _is_hash(result.get("event_hash")):
            _corrupt(f"review {rid} result event hash missing")
        if decision == "adopt_persistence":
            tr = result.get("transition")
            if not isinstance(tr, dict) or not _is_hash(
                    tr.get("semantic_hash")):
                _corrupt(
                    f"review {rid} adopt_persistence lacks the committed "
                    "transition semantic hash")
            kinds = {kind for kind, tid in (
                ("entity_feature", ef_transition),
                ("entity_relation", er_transition),
                ("production_instance_feature", pf_transition))
                if tid is not None}
            if len(kinds) != 1 or tr.get("kind") not in kinds:
                _corrupt(
                    f"review {rid} result transition kind disagrees "
                    "with the row's transition columns")
    elif source_kind == "proposal":
        if source_event_id is not None or source_proposal_id is None:
            _corrupt(f"review {rid} proposal source shape invalid")
        pr = rows(
            "SELECT shot_id, proposal_hash FROM "
            "shot_intra_shot_event_proposals WHERE id = ?",
            (source_proposal_id,))
        if not pr or pr[0][1] != source_hash:
            _corrupt(f"review {rid} source proposal hash mismatch")
        if pr[0][0] != shot_id:
            _corrupt(
                f"review {rid} source proposal belongs to another Shot")
        if decision not in ("adopt_event_only", "adopt_persistence",
                            "ignore"):
            _corrupt(f"review {rid} illegal proposal decision {decision!r}")
        # exact frozen proposal review-basis root (R6 §7.5.2): the sole
        # normative construction — canonical hash of
        # {batch_basis_hash, proposal_id, proposal_hash, decision}
        batch_basis = doc.get("batch_basis_hash")
        if not _is_hash(batch_basis):
            _corrupt(f"review {rid} operation lacks a batch basis hash")
        # the batch hash itself must derive from the frozen §7.5.2
        # batch object recorded in the operation — never a supplied
        # arbitrary 64-hex value
        batch_doc = doc.get("batch_basis")
        if not isinstance(batch_doc, dict):
            _corrupt(
                f"review {rid} operation lacks the frozen batch basis "
                "object")
        from soloring.continuity.intra_shot_canonical import (
            proposal_batch_basis_hash as batch_basis_root,
        )

        try:
            recomputed_batch = batch_basis_root(**batch_doc)
        except Exception:
            _corrupt(
                f"review {rid} batch basis object violates the frozen "
                "grammar")
        if recomputed_batch != batch_basis:
            _corrupt(
                f"review {rid} batch basis hash is not the frozen batch "
                "object root")
        recomputed = proposal_basis(
            batch_basis_hash=batch_basis,
            proposal_id=source_proposal_id,
            proposal_hash=source_hash, decision=decision)
        if recomputed != review_basis_hash:
            _corrupt(
                f"review {rid} recorded basis is not the frozen proposal "
                "review-basis root")
        # §7.5.2 membership: this review's exact
        # {proposal_id, proposal_hash, decision} must be IN the batch
        # object's reviews set
        reviews = batch_doc.get("reviews")
        if not isinstance(reviews, list):
            _corrupt(f"review {rid} batch object lacks reviews")
        entry = {
            "proposal_id": source_proposal_id,
            "proposal_hash": source_hash,
            "decision": decision,
        }
        members = [r for r in reviews if isinstance(r, dict)]
        if entry not in members:
            _corrupt(
                f"review {rid} is not a member of the batch object "
                "that roots it")
        # §7.5.2 completeness: the persisted review rows rooted at this
        # batch must be EXACTLY the batch's member set
        persisted = rows(
            "SELECT source_proposal_id, source_hash, decision FROM "
            "persistent_consequence_reviews WHERE source_kind = "
            "'proposal'")
        rooted = {
            (row[0], row[1], row[2]) for row in persisted
            if row[0] is not None
            and _review_batch_root(rows, row[0]) == batch_basis}
        expected = {
            (r["proposal_id"], r["proposal_hash"], r["decision"])
            for r in members}
        if rooted != expected:
            _corrupt(
                f"review {rid} batch members disagree with the persisted "
                "review rows for that batch")
    else:
        _corrupt(f"review {rid} unknown source kind {source_kind!r}")

    if "review_basis_hash" not in doc:
        _corrupt(f"review {rid} operation lacks review_basis_hash")
    if doc["review_basis_hash"] != review_basis_hash:
        _corrupt(f"review {rid} recorded basis disagrees with operation")

    # result references are IMMUTABLE-recorded: the row's result event
    # must exist (provenance anchor, any current semantics) and belong
    # to this Shot; semantic agreement was verified above against the
    # operation's own recorded hashes, never against today's rows.
    if decision == "ignore":
        if (result_event_id is not None or ef_transition is not None
                or er_transition is not None or pf_transition is not None):
            _corrupt(f"review {rid} ignore carries results")
        return
    if not _result_event_exists(rows, result_event_id):
        _corrupt(f"review {rid} result event missing")
    res = rows(
        "SELECT shot_id FROM shot_intra_shot_events WHERE id = ?",
        (result_event_id,))[0]
    if res[0] != shot_id:
        _corrupt(f"review {rid} result event belongs to another Shot")
    if decision in ("adopt_event_only", "decline_persistence"):
        if (ef_transition is not None or er_transition is not None
                or pf_transition is not None):
            _corrupt(
                f"review {rid} {decision} must not carry transitions")
        return
    populated = [(kind, tid) for kind, tid in (
        ("entity_feature", ef_transition),
        ("entity_relation", er_transition),
        ("production_instance_feature", pf_transition)) if tid is not None]
    if len(populated) != 1:
        _corrupt(
            f"review {rid} adopt_persistence requires exactly one "
            "owning-domain transition id")
    kind, tid = populated[0]
    # the transition row is a provenance anchor: it must exist and be
    # this Shot's Shot/end handoff in the right domain (columns are
    # domain-specific), but its CURRENT value is not the historical
    # semantic source
    if kind == "entity_relation":
        tr_row = rows(
            "SELECT anchor_type, anchor_id, boundary FROM "
            "continuity_relation_transitions WHERE id = ?", (tid,))
    else:
        table = {
            "entity_feature": "continuity_feature_transitions",
            "production_instance_feature":
                "production_instance_feature_transitions",
        }[kind]
        tr_row = rows(
            f"SELECT anchor_type, anchor_id, boundary FROM {table} "
            "WHERE id = ?", (tid,))
    if not tr_row:
        _corrupt(f"review {rid} result transition missing")
    if (tr_row[0][0] != "shot" or tr_row[0][1] != shot_id
            or tr_row[0][2] != "end"):
        _corrupt(
            f"review {rid} result transition is not this Shot's "
            "Shot/end owning-domain handoff")


def _review_batch_root(rows, proposal_id):
    row = rows(
        "SELECT operation_json FROM "
        "persistent_consequence_reviews WHERE source_kind = 'proposal' "
        "AND source_proposal_id = ?", (proposal_id,)).fetchall()
    if not row:
        return None
    import json as _json

    try:
        return _json.loads(row[0][0]).get("batch_basis_hash")
    except (ValueError, TypeError):
        return None


def _result_event_exists(rows, event_id) -> bool:
    if not isinstance(event_id, str):
        return False
    return bool(rows(
        "SELECT 1 FROM shot_intra_shot_events WHERE id = ?", (event_id,)))


def verify_m16_intra_shot_state(staged_db: Path) -> None:
    con = sqlite3.connect(str(staged_db))
    try:
        def rows(query, params=()):
            return con.execute(query, params).fetchall()

        for row in rows(
                "SELECT id, shot_id, time_ms, ordinal, target_kind, "
                "entity_feature_id, entity_relation_id, "
                "production_instance_feature_id, before_state_json, "
                "before_state_hash, after_state_json, after_state_hash, "
                "persistence_mode, source_kind, source_proposal_id, "
                "event_json, event_hash FROM shot_intra_shot_events "
                "WHERE deleted_at IS NULL"):
            verify_working_event_row(_Row(row, WORKING_EVENT_COLUMNS))
            if row[13] == "proposal_adoption":
                if row[14] is None:
                    _corrupt(
                        f"working event {row[0]} claims proposal_adoption "
                        "without a source proposal")
                pr = rows(
                    "SELECT proposal_hash FROM "
                    "shot_intra_shot_event_proposals WHERE id = ?",
                    (row[14],))
                if not pr:
                    _corrupt(
                        f"working event {row[0]} pins missing proposal "
                        f"{row[14]}")

        # History is enumerated from the OUTER schema-7 snapshots: a
        # schema-7 revision without companions is corruption, and a
        # companion parent without schema 7 is corruption.
        for rev_id, snapshot_json in rows(
                "SELECT id, snapshot_json FROM shot_revisions"):
            snap = json.loads(snapshot_json)
            if snap.get("schema_version") == 7:
                verify_intra_shot_history_sync(
                    con, rev_id, snapshot=snap)
        for (rev_id,) in rows(
                "SELECT DISTINCT shot_revision_id FROM "
                "shot_revision_intra_shot_events"):
            snap = rows(
                "SELECT snapshot_json FROM shot_revisions WHERE id = ?",
                (rev_id,))
            if not snap:
                _corrupt(
                    f"intra_shot companions reference missing "
                    f"ShotRevision {rev_id}")
            if json.loads(snap[0][0]).get("schema_version") != 7:
                _corrupt(
                    f"ShotRevision {rev_id} carries companions without "
                    "outer schema 7")

        for row in rows(
                "SELECT id, shot_id, source_kind, "
                "source_shot_revision_id, source_shot_revision_hash, "
                "source_generation_id, source_take_id, proposer_kind, "
                "analyzer_id, analyzer_version, analyzer_parameters_hash, "
                "proposal_json, proposal_hash FROM "
                "shot_intra_shot_event_proposals"):
            _verify_proposal_source(row, rows)

        for row in rows(
                "SELECT id, shot_id, source_kind, source_event_id, "
                "source_proposal_id, source_hash, decision, "
                "review_basis_hash, result_event_id, "
                "entity_feature_transition_id, "
                "entity_relation_transition_id, "
                "production_instance_feature_transition_id, "
                "operation_json, operation_hash FROM "
                "persistent_consequence_reviews"):
            _verify_review(row, rows)
    finally:
        con.close()


WORKING_EVENT_COLUMNS = (
    "id", "shot_id", "time_ms", "ordinal", "target_kind",
    "entity_feature_id", "entity_relation_id",
    "production_instance_feature_id", "before_state_json",
    "before_state_hash", "after_state_json", "after_state_hash",
    "persistence_mode", "source_kind", "source_proposal_id",
    "event_json", "event_hash",
)


class _Row:
    def __init__(self, values, columns):
        self._map = dict(zip(columns, values))

    def __getattr__(self, name):
        return self._map[name]
