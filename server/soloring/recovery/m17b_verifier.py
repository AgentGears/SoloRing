"""M17B performance/retarget semantic recovery verifier (frozen R7
§14.3).

Runs against the staged DB (and the active Blob root) during backup
and restore at head 0019. Fail-closed on any incoherence; a restore
at 0018 or earlier invents ZERO M17B state (the verifier is only
invoked for head 0019 by the successor chain).

Subject activity is an admission-time requirement: an already-existing
row whose subject was later soft-deleted remains historically valid.
"""

from __future__ import annotations

import json
import sqlite3
from fractions import Fraction
from pathlib import Path

from soloring.errors import SoloRingError

_M17B_TABLES = ("performance_candidates", "performance_revisions",
                "performance_retarget_assessments",
                "performance_retarget_reviews")

_SOURCE_KINDS = ("authored", "performance_capture", "tracking",
                 "reconstruction", "generated", "simulated",
                 "procedural", "imported", "retargeted")
_PROVENANCE_KINDS = ("AUTHORED", "DERIVED", "DERIVED_THEN_EDITED")
_PROFILE_ID = "performance-profile/1"

_EVALUATOR_ID = "soloring.performance_physical_retarget"
_REASONS = {
    "SAME_EXACT_PHYSICAL_REVISION": "COMPATIBLE_AS_IS",
    "SAME_PRODUCTION_OBJECT_DIFFERENT_REVISION": "REQUIRES_REVIEW",
    "DIFFERENT_PRODUCTION_OBJECT": "INCOMPATIBLE",
}


def _corrupt(msg: str) -> Exception:
    return SoloRingError("RECOVERY_CORRUPTION", msg, status_code=500)


def verify_m17b_performance_state(staged_db: Path,
                                  blob_root: Path | None = None) -> None:
    if blob_root is None:
        from soloring.settings import get_settings
        blob_root = get_settings().blob_dir
    con = sqlite3.connect(staged_db)
    con.row_factory = sqlite3.Row
    try:
        present = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if not set(_M17B_TABLES) <= present:
            raise _corrupt("M17B tables missing from staged schema")
        _verify_candidates(con, blob_root)
        _verify_revisions(con)
        _verify_assessments(con)
        _verify_reviews(con)
        _verify_retargeted(con)
    finally:
        con.close()


def _canonical(obj) -> str:
    from soloring.domain.canonical import canonical_json_str
    return canonical_json_str(obj)


def _hash(obj) -> str:
    from soloring.domain.canonical import canonical_hash
    return canonical_hash(obj)


def _blob_bytes(blob_root: Path, h: str) -> bytes:
    import hashlib
    p = blob_root / "sha256" / h[:2] / h[2:4] / h
    if not p.is_file():
        raise _corrupt(f"M17B payload blob {h} missing from Blob root")
    data = p.read_bytes()
    if hashlib.sha256(data).hexdigest() != h:
        raise _corrupt(f"M17B payload blob {h} bytes do not rehash")
    return data


def _check_rational(num, den, what: str) -> None:
    import math
    if den <= 0 or math.gcd(abs(num), den) != 1 or (num == 0
                                                     and den != 1):
        raise _corrupt(f"{what} rational {num}/{den} is not canonical")


def _verify_payload_document(doc, *, kind: str, sn, sd, en, ed) -> None:
    """Full closed-key grammar + semantic law revalidation of a
    retained canonical payload document."""
    import re
    from soloring.performance.profile import CHANNELS
    if not isinstance(doc, dict) or set(doc) != {
            "schema_version", "performance_profile_id", "channels"}:
        raise _corrupt("payload document keys are not the exact "
                       "closed set")
    if doc["schema_version"] != 1 or \
            doc["performance_profile_id"] != _PROFILE_ID:
        raise _corrupt("payload document identity fields disagree")
    channels = doc["channels"]
    if not channels:
        raise _corrupt("payload declares no channels")
    start_ms, end_ms = Fraction(sn, sd), Fraction(en, ed)
    if start_ms >= end_ms:
        raise _corrupt("payload temporal domain inverted")
    face = body = 0
    keys = [c.get("channel_key") for c in channels]
    if keys != sorted(keys) or len(set(keys)) != len(keys):
        raise _corrupt("payload channels are not uniquely sorted by "
                       "channel_key")
    for ch in channels:
        if not isinstance(ch, dict) or set(ch) != {
                "channel_key", "domain", "role", "semantic_key",
                "value_grammar", "keyframes"}:
            raise _corrupt("channel keys are not the exact closed set")
        key = ch["channel_key"]
        if key not in CHANNELS:
            raise _corrupt(f"unknown channel {key!r} in retained "
                           "payload")
        dom, role, sem, gram, lo, hi = CHANNELS[key]
        if (ch["domain"], ch["role"], ch["semantic_key"],
                ch["value_grammar"]) != (dom, role, sem, gram):
            raise _corrupt(f"channel {key!r} descriptors disagree "
                           "with the frozen registry")
        kfs = ch["keyframes"]
        if not kfs:
            raise _corrupt(f"channel {key!r} has no keyframes")
        times = []
        for kf in kfs:
            if not isinstance(kf, dict) or set(kf) != {
                    "time_ms", "value", "provenance"}:
                raise _corrupt("keyframe keys are not the exact "
                               "closed set")
            t = kf["time_ms"]
            if not isinstance(t, dict) or set(t) != {"num", "den"}:
                raise _corrupt("time_ms keys are not the exact closed "
                               "set")
            _check_rational(t["num"], t["den"], "keyframe")
            tms = Fraction(t["num"], t["den"])
            if not (start_ms <= tms < end_ms):
                raise _corrupt(f"keyframe {t['num']}/{t['den']} "
                               "outside the payload temporal domain")
            v = kf["value"]
            if isinstance(v, bool) or not isinstance(v, int) or \
                    not (lo <= v <= hi):
                raise _corrupt(f"channel {key!r} keyframe value "
                               "violates its integer bounds")
            prov = kf["provenance"]
            if not isinstance(prov, dict) or set(prov) != {
                    "kind", "source_alignment_id"}:
                raise _corrupt("keyframe provenance keys are not the "
                               "exact closed set")
            if prov["kind"] not in _PROVENANCE_KINDS:
                raise _corrupt("keyframe provenance kind outside the "
                               "frozen vocabulary")
            if prov["kind"] == "AUTHORED" and \
                    prov["source_alignment_id"] is not None:
                raise _corrupt("AUTHORED keyframe carries an "
                               "alignment id")
            times.append(tms)
        if times != sorted(times) or len(set(times)) != len(times):
            raise _corrupt(f"channel {key!r} keyframes are not "
                           "uniquely time-sorted")
        if dom == "face":
            face += 1
        else:
            body += 1
    if kind == "BODY" and face:
        raise _corrupt("BODY payload carries face channels")
    if kind == "FACIAL" and body:
        raise _corrupt("FACIAL payload carries body channels")
    if kind == "BODY_FACIAL" and (not body or not face):
        raise _corrupt("BODY_FACIAL payload lacks a required domain")


def _verify_alignment_link(con: sqlite3.Connection, aid: str,
                           subject_id: str, project_of_line) -> None:
    row = con.execute("SELECT vocal_performance_revision_id FROM "
                      "dialogue_alignments WHERE id = ?",
                      (aid,)).fetchone()
    if row is None:
        raise _corrupt(f"referenced alignment {aid} missing")
    vp = con.execute(
        "SELECT dialogue_line_revision_id, speaker_subject_id FROM "
        "vocal_performance_revisions WHERE id = ?",
        (row["vocal_performance_revision_id"],)).fetchone()
    if vp is None:
        raise _corrupt("alignment references a missing VP")
    if vp["speaker_subject_id"] != subject_id:
        raise _corrupt("alignment VP speaker != performance subject")
    line = con.execute(
        "SELECT project_id FROM dialogue_lines WHERE id = (SELECT "
        "dialogue_line_id FROM dialogue_line_revisions WHERE id = ?)",
        (vp["dialogue_line_revision_id"],)).fetchone()
    if line is None or line["project_id"] != project_of_line:
        raise _corrupt("alignment provenance crosses projects")


def _verify_candidates(con: sqlite3.Connection, blob_root: Path) -> None:
    for r in con.execute("SELECT * FROM performance_candidates"):
        if r["performance_kind"] not in ("BODY", "FACIAL",
                                         "BODY_FACIAL"):
            raise _corrupt("candidate performance_kind outside law")
        if r["performance_profile_id"] != _PROFILE_ID:
            raise _corrupt("candidate profile id outside law")
        if r["source_kind"] not in _SOURCE_KINDS:
            raise _corrupt("candidate source_kind outside law")
        if r["payload_schema_version"] != 1 or \
                r["provenance_schema_version"] != 1:
            raise _corrupt("candidate schema versions != 1")
        for what, num, den in (
                ("start", r["temporal_start_num"],
                 r["temporal_start_den"]),
                ("end", r["temporal_end_num"], r["temporal_end_den"])):
            _check_rational(num, den, f"candidate {what}")
        if Fraction(r["temporal_start_num"],
                    r["temporal_start_den"]) >= \
                Fraction(r["temporal_end_num"],
                         r["temporal_end_den"]):
            raise _corrupt("candidate temporal domain inverted")
        if r["canonical_channel_payload_sha256"] != \
                r["canonical_channel_payload_blob_hash"]:
            raise _corrupt("candidate dual payload hash columns "
                           "disagree")
        subject = con.execute(
            "SELECT project_id FROM creative_entities WHERE id = ?",
            (r["subject_id"],)).fetchone()
        if subject is None or \
                subject["project_id"] != r["project_id"]:
            raise _corrupt("candidate subject/project disagreement")
        if con.execute("SELECT 1 FROM blobs WHERE hash = ?",
                       (r["canonical_channel_payload_blob_hash"],
                        )).fetchone() is None:
            raise _corrupt("candidate payload blob row missing")
        data = _blob_bytes(blob_root,
                           r["canonical_channel_payload_blob_hash"])
        doc = json.loads(data.decode("utf-8"))
        _verify_payload_document(
            doc, kind=r["performance_kind"],
            sn=r["temporal_start_num"], sd=r["temporal_start_den"],
            en=r["temporal_end_num"], ed=r["temporal_end_den"])
        if _canonical(doc) != data.decode("utf-8"):
            raise _corrupt("retained payload bytes are not the "
                           "canonical serialization")
        for ch in doc["channels"]:
            for kf in ch["keyframes"]:
                aid = kf["provenance"]["source_alignment_id"]
                if aid is not None:
                    _verify_alignment_link(con, aid, r["subject_id"],
                                           r["project_id"])
        prov = json.loads(r["provenance_json"])
        if _canonical(prov) != r["provenance_json"] or \
                _hash(prov) != r["provenance_hash"]:
            raise _corrupt("candidate provenance rehash fail")
        if prov.get("source_kind") != r["source_kind"]:
            raise _corrupt("candidate provenance/column source_kind "
                           "disagree")


def _verify_revisions(con: sqlite3.Connection) -> None:
    for r in con.execute("SELECT * FROM performance_revisions"):
        c = con.execute("SELECT * FROM performance_candidates WHERE "
                        "id = ?", (r["adopted_candidate_id"],)).fetchone()
        if c is None:
            raise _corrupt("revision adopted-candidate lineage "
                           "missing")
        for f in ("project_id", "subject_id", "performance_kind",
                  "performance_profile_id", "temporal_start_num",
                  "temporal_start_den", "temporal_end_num",
                  "temporal_end_den",
                  "canonical_channel_payload_blob_hash",
                  "canonical_channel_payload_sha256",
                  "payload_schema_version", "source_kind",
                  "provenance_schema_version", "provenance_json",
                  "provenance_hash"):
            if r[f] != c[f]:
                raise _corrupt(
                    f"revision copied closure diverges on {f} — "
                    "corruption, never repaired")
        if not r["adoption_id"] or not r["adopted_by"].strip():
            raise _corrupt("revision adoption metadata invalid")
        n = con.execute("SELECT COUNT(*) FROM performance_revisions "
                        "WHERE adopted_candidate_id = ?",
                        (r["adopted_candidate_id"],)).fetchone()[0]
        if n != 1:
            raise _corrupt("candidate adopted more than once")


def _verify_assessments(con: sqlite3.Connection) -> None:
    for r in con.execute("SELECT * FROM "
                         "performance_retarget_assessments"):
        perf = con.execute(
            "SELECT * FROM performance_revisions WHERE id = ?",
            (r["performance_revision_id"],)).fetchone()
        if perf is None:
            raise _corrupt("assessment source revision missing")
        if perf["project_id"] != r["project_id"]:
            raise _corrupt("assessment project mismatch")
        from_pr = con.execute(
            "SELECT * FROM production_revisions WHERE id = ?",
            (r["from_production_revision_id"],)).fetchone()
        to_pr = con.execute(
            "SELECT * FROM production_revisions WHERE id = ?",
            (r["to_production_revision_id"],)).fetchone()
        if from_pr is None or to_pr is None:
            raise _corrupt("assessment physical revision missing")
        if r["from_production_revision_hash"] != \
                from_pr["snapshot_hash"] or \
                r["to_production_revision_hash"] != \
                to_pr["snapshot_hash"]:
            raise _corrupt("assessment snapshot-hash duplication "
                           "disagrees")
        from_obj = str(from_pr["production_object_id"])
        to_obj = str(to_pr["production_object_id"])
        if from_pr["id"] == to_pr["id"]:
            reason = "SAME_EXACT_PHYSICAL_REVISION"
        elif from_obj == to_obj:
            reason = "SAME_PRODUCTION_OBJECT_DIFFERENT_REVISION"
        else:
            reason = "DIFFERENT_PRODUCTION_OBJECT"
        verdict = _REASONS[reason]

        scope = {"schema_version": 1, "evaluator_id": _EVALUATOR_ID,
                 "evaluator_version": 1,
                 "performance_revision_id": perf["id"],
                 "subject_id": perf["subject_id"],
                 "performance_kind": perf["performance_kind"],
                 "performance_profile_id":
                     perf["performance_profile_id"],
                 "performance_payload_sha256":
                     perf["canonical_channel_payload_sha256"],
                 "from_production_revision_id": from_pr["id"],
                 "from_production_revision_hash":
                     from_pr["snapshot_hash"],
                 "from_production_object_id": from_obj,
                 "to_production_revision_id": to_pr["id"],
                 "to_production_revision_hash":
                     to_pr["snapshot_hash"],
                 "to_production_object_id": to_obj}
        scope_json = _canonical(scope)
        scope_hash = _hash(scope)
        if r["scope_json"] != scope_json or \
                r["scope_hash"] != scope_hash:
            raise _corrupt("assessment scope does not recompute "
                           "byte-exact from immutable rows")

        report = {"schema_version": 1, "evaluator_id": _EVALUATOR_ID,
                  "evaluator_version": 1, "scope_hash": scope_hash,
                  "performance_revision_id": perf["id"],
                  "from_production_revision_id": from_pr["id"],
                  "to_production_revision_id": to_pr["id"],
                  "verdict": verdict, "reason_code": reason,
                  "from_production_object_id": from_obj,
                  "to_production_object_id": to_obj}
        report_json = _canonical(report)
        report_hash = _hash(report)
        if r["report_json"] != report_json or \
                r["report_hash"] != report_hash:
            raise _corrupt("assessment report does not recompute "
                           "byte-exact")
        if r["overall_verdict"] != verdict:
            raise _corrupt("stored verdict != evaluator recomputation")
        if r["evaluator_id"] != _EVALUATOR_ID or \
                r["evaluator_version"] != 1 or r["schema_version"] != 1:
            raise _corrupt("assessment evaluator identity drift")


def _verify_reviews(con: sqlite3.Connection) -> None:
    for r in con.execute("SELECT * FROM "
                         "performance_retarget_reviews"):
        if con.execute(
                "SELECT 1 FROM "
                "performance_retarget_assessments WHERE id = ?",
                (r["assessment_id"],)).fetchone() is None:
            raise _corrupt("review assessment missing")
        if r["decision"] not in ("ACCEPT_FOR_NEW_CANDIDATE", "REJECT"):
            raise _corrupt("review decision outside law")
        if not r["reviewed_by"].strip():
            raise _corrupt("review reviewer empty")
        if r["rationale"] is not None and len(r["rationale"]) > 4096:
            raise _corrupt("review rationale over bound")


def _verify_retargeted(con: sqlite3.Connection) -> None:
    for r in con.execute(
            "SELECT * FROM performance_candidates WHERE source_kind = "
            "'retargeted'"):
        prov = json.loads(r["provenance_json"])
        ret = prov.get("retarget")
        if not isinstance(ret, dict) or set(ret) != {
                "source_performance_revision_id",
                "from_production_revision_id",
                "to_production_revision_id",
                "compatibility_assessment_id", "accepted_review_id"}:
            raise _corrupt("retarget provenance keys not exact")
        perf = con.execute(
            "SELECT * FROM performance_revisions WHERE id = ?",
            (ret["source_performance_revision_id"],)).fetchone()
        if perf is None:
            raise _corrupt("retarget source revision missing")
        a = con.execute(
            "SELECT * FROM performance_retarget_assessments WHERE "
            "id = ?", (ret["compatibility_assessment_id"],)).fetchone()
        if a is None:
            raise _corrupt("retarget assessment missing")
        if (a["performance_revision_id"],
                a["from_production_revision_id"],
                a["to_production_revision_id"]) != (
                ret["source_performance_revision_id"],
                ret["from_production_revision_id"],
                ret["to_production_revision_id"]):
            raise _corrupt("retarget provenance coordinate mismatch")
        if a["overall_verdict"] != "REQUIRES_REVIEW":
            raise _corrupt("retarget seeded from a non-REQUIRES_REVIEW "
                           "assessment")
        review = con.execute(
            "SELECT * FROM performance_retarget_reviews WHERE id = ?",
            (ret["accepted_review_id"],)).fetchone()
        if review is None:
            raise _corrupt("accepted review missing")
        if review["assessment_id"] != a["id"] or \
                review["decision"] != "ACCEPT_FOR_NEW_CANDIDATE":
            raise _corrupt("accepted review does not satisfy the "
                           "review law chain")
        for f in ("project_id", "subject_id", "performance_kind",
                  "performance_profile_id", "temporal_start_num",
                  "temporal_start_den", "temporal_end_num",
                  "temporal_end_den",
                  "canonical_channel_payload_blob_hash",
                  "canonical_channel_payload_sha256",
                  "payload_schema_version"):
            if r[f] != perf[f]:
                raise _corrupt("retarget candidate semantic closure "
                               "diverged from its source revision")
