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
            "SELECT shot_id, event_hash FROM shot_intra_shot_events "
            "WHERE id = ?", (source_event_id,))
        if not ev or ev[0][1] != source_hash:
            _corrupt(f"review {rid} source event hash mismatch")
        if ev[0][0] != shot_id:
            _corrupt(f"review {rid} source event belongs to another Shot")
        if decision not in ("adopt_persistence", "decline_persistence"):
            _corrupt(f"review {rid} illegal event decision {decision!r}")
        # exact frozen event review-basis root (R6 §7.5.1), recomputed
        # from the reviewed event's stored coordinates — never the
        # operation's self-assertion
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
    else:
        _corrupt(f"review {rid} unknown source kind {source_kind!r}")

    if "review_basis_hash" not in doc:
        _corrupt(f"review {rid} operation lacks review_basis_hash")
    if doc["review_basis_hash"] != review_basis_hash:
        _corrupt(f"review {rid} recorded basis disagrees with operation")

    # result references — the frozen migration shape (ck_pcr_result_shape):
    # ignore carries nothing; adopt_event_only and decline_persistence
    # carry a result EVENT and no transition; adopt_persistence carries a
    # result event and EXACTLY ONE owning-domain transition whose own
    # Shot/end anchor must agree with the review's Shot.
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
    table, column = {
        "entity_feature": ("continuity_feature_transitions",
                           "feature_id"),
        "entity_relation": ("continuity_relation_transitions",
                            "relation_id"),
        "production_instance_feature":
            ("production_instance_feature_transitions", "feature_id"),
    }[kind]
    tr = rows(
        f"SELECT anchor_type, anchor_id, boundary, {column}, operation, "
        f"state, value_json, value_hash FROM {table[kind]} "
        "WHERE id = ?", (tid,))
    if not tr:
        _corrupt(f"review {rid} result transition missing")
    if (tr[0][0] != "shot" or tr[0][1] != shot_id or tr[0][2] != "end"):
        _corrupt(
            f"review {rid} result transition is not this Shot's "
            "Shot/end owning-domain handoff")

    # the transition's TARGET and SEMANTIC VALUE must equal the result
    # event's target and terminal state — a same-Shot/end transition for
    # a different target (or a different value) is NOT this review's
    # handoff
    res_ev = rows(
        "SELECT target_kind, entity_feature_id, entity_relation_id, "
        "production_instance_feature_id, persistence_mode, "
        "after_state_json FROM shot_intra_shot_events WHERE id = ?",
        (result_event_id,))[0]
    res_kind = res_ev[0]
    res_target = res_ev[1] or res_ev[2] or res_ev[3]
    if res_kind != kind or tr[0][3] != res_target:
        _corrupt(
            f"review {rid} result transition targets a different "
            "target than the result event")
    if res_ev[4] != "require_handoff":
        _corrupt(
            f"review {rid} adopt_persistence result event is not "
            "persistent")
    import json as _json

    terminal = _json.loads(res_ev[5])
    if kind == "entity_relation":
        expected = ("active" if terminal["active"] else "inactive")
        if tr[0][5] != expected:
            _corrupt(
                f"review {rid} result transition state does not equal "
                "the result event terminal state")
    elif terminal.get("present"):
        if tr[0][4] != "set" or tr[0][7] != terminal.get("value_hash"):
            _corrupt(
                f"review {rid} result transition value does not equal "
                "the result event terminal state")
    elif tr[0][4] != "clear" or tr[0][6] is not None:
        _corrupt(
            f"review {rid} clear transition does not equal canonical "
            "terminal absence")


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
