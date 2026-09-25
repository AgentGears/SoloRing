"""M17B PerformanceCandidate creation and PerformanceRevision adoption
(frozen R7 §§8–10).

Candidate creation validates the closed provenance envelope, builds the
canonical channel payload through the frozen profile builder, places
the exact bytes through BlobStore, and persists one immutable
candidate row — failure atomicity: no partial candidate ever exists.

Adoption is THE PF-01 authority transition: it copies the candidate
closure exactly, server-generates one adoption_id, and converges under
duplicate adoption (sequential and concurrent) through
UNIQUE(adopted_candidate_id) with full winner revalidation.
"""

from __future__ import annotations

import hashlib
import json
import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.assets.blob_store import BlobStore
from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.domain.ids import new_uuid
from soloring.domain.now import db_now
from soloring.errors import ErrorCode, SoloRingError, not_found
from soloring.performance.models import (PerformanceCandidate,
                                         PerformanceRevision)
from soloring.performance.profile import (
    PROFILE_ID,
    build_canonical_payload,
    validate_temporal_domain,
)

SOURCE_KINDS = ("authored", "performance_capture", "tracking",
                "reconstruction", "generated", "simulated", "procedural",
                "imported", "retargeted")

_PROVENANCE_KEYS = {"schema_version", "source_kind", "producer_id",
                    "producer_version", "source_identity",
                    "parameters_sha256", "retarget"}
_RETARGET_KEYS = {"source_performance_revision_id",
                  "from_production_revision_id",
                  "to_production_revision_id",
                  "compatibility_assessment_id", "accepted_review_id"}
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_PATH_FORMS = re.compile(r"^(?i:file)://|/|\./|\.\.\/|[A-Za-z]:[/\\]|\\")


def _invalid(code: ErrorCode, message: str) -> SoloRingError:
    return SoloRingError(code, message, status_code=422)


_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{12}$")


def validate_adoption_metadata(*, adoption_id, adopted_by,
                               adopted_at) -> None:
    """Shared persisted adoption-metadata grammar (correction CR-B/
    CR-D): exact UUID for adoption_id, nonblank exact adopted_by
    <= 255 code points, adopted_at present."""
    if not isinstance(adoption_id, str) or not _UUID_RE.fullmatch(
            adoption_id):
        raise _invalid(
            ErrorCode.PERFORMANCE_PAYLOAD_INVALID,
            "adoption_id must be an exact UUID")
    if not isinstance(adopted_by, str) or not adopted_by.strip() \
            or len(adopted_by) > 255:
        raise _invalid(
            ErrorCode.PERFORMANCE_PAYLOAD_INVALID,
            "adopted_by must be nonempty (whitespace test) exact "
            "UTF-8 <= 255 code points")
    if not isinstance(adopted_at, str) or not adopted_at:
        raise _invalid(
            ErrorCode.PERFORMANCE_PAYLOAD_INVALID,
            "adopted_at must be present")


def validate_review_metadata(*, decision, reviewed_by, rationale) -> None:
    """Shared persisted review-metadata grammar (correction CR-D)."""
    if decision not in ("ACCEPT_FOR_NEW_CANDIDATE", "REJECT"):
        raise _invalid(
            ErrorCode.PERFORMANCE_PAYLOAD_INVALID,
            "review decision must be ACCEPT_FOR_NEW_CANDIDATE or "
            "REJECT")
    if not isinstance(reviewed_by, str) or not reviewed_by.strip() \
            or len(reviewed_by) > 255:
        raise _invalid(
            ErrorCode.PERFORMANCE_PAYLOAD_INVALID,
            "reviewed_by must be nonempty (whitespace test) exact "
            "UTF-8 <= 255 code points")
    if rationale is not None and (not isinstance(rationale, str)
                                   or len(rationale) > 4096):
        raise _invalid(
            ErrorCode.PERFORMANCE_PAYLOAD_INVALID,
            "rationale must be null or exact UTF-8 free text <= 4096 "
            "code points")


async def verify_candidate_integrity(
        session: AsyncSession, settings, candidate: PerformanceCandidate,
        *, row_lookup=None, blob_reader=None) -> dict:
    """Full immutable candidate-closure integrity (correction CR-B).

    Verifies temporal canonicality, profile/kind row fields, the
    physical retained Blob (bytes + dual-hash agreement), the exact
    closed payload grammar with byte-identical canonical re-emission,
    the closed provenance grammar + canonical hash, and alignment
    provenance integrity. Pure with respect to CURRENT state: only
    immutable candidate fields and immutable referenced rows are read.

    ``row_lookup``/``blob_reader`` let the recovery verifier inject
    its own staged-DB readers (sqlite3 rows + root path) without
    importing transport behavior into recovery.
    """
    from soloring.performance.revision import (
        build_provenance_envelope)

    if candidate.performance_profile_id != PROFILE_ID:
        raise _invalid(
            ErrorCode.PERFORMANCE_PROFILE_UNSUPPORTED,
            "candidate profile id is not performance-profile/1")
    if candidate.payload_schema_version != 1 or \
            candidate.provenance_schema_version != 1:
        raise _invalid(
            ErrorCode.PERFORMANCE_PAYLOAD_INVALID,
            "candidate schema versions must be 1")
    validate_temporal_domain(
        candidate.temporal_start_num, candidate.temporal_start_den,
        candidate.temporal_end_num, candidate.temporal_end_den)

    # physical retained bytes + dual-hash agreement
    if candidate.canonical_channel_payload_sha256 != \
            candidate.canonical_channel_payload_blob_hash:
        raise _invalid(
            ErrorCode.BLOB_HASH_MISMATCH,
            "candidate dual payload hash columns disagree")
    payload_hash = candidate.canonical_channel_payload_blob_hash
    if row_lookup is not None:
        data = blob_reader(payload_hash)
    else:
        from soloring.assets.models import Blob
        if await session.get(Blob, payload_hash) is None:
            raise _invalid(
                ErrorCode.BLOB_NOT_FOUND,
                f"candidate payload blob row {payload_hash!r} missing")
        store = BlobStore(settings)
        data = store.path_for_hash(payload_hash).read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != payload_hash:
        raise _invalid(
            ErrorCode.BLOB_HASH_MISMATCH,
            f"candidate payload physical bytes hash to {actual}")

    # exact closed payload grammar + canonical re-emission equality
    try:
        doc = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise _invalid(
            ErrorCode.PERFORMANCE_PAYLOAD_INVALID,
            "retained payload is not UTF-8 JSON")
    rebuilt, _ = build_canonical_payload(
        doc, performance_kind=candidate.performance_kind,
        performance_profile_id=candidate.performance_profile_id,
        start_num=candidate.temporal_start_num,
        start_den=candidate.temporal_start_den,
        end_num=candidate.temporal_end_num,
        end_den=candidate.temporal_end_den)
    if rebuilt != data:
        raise _invalid(
            ErrorCode.PERFORMANCE_PAYLOAD_INVALID,
            "retained payload is not the canonical serialization of "
            "its own document")

    # closed provenance grammar + canonical hash
    try:
        prov_doc = json.loads(candidate.provenance_json)
    except json.JSONDecodeError:
        raise _invalid(
            ErrorCode.PERFORMANCE_PROVENANCE_INVALID,
            "candidate provenance is not JSON")
    envelope = build_provenance_envelope(prov_doc)
    if envelope.get("source_kind") != candidate.source_kind:
        raise _invalid(
            ErrorCode.PERFORMANCE_PROVENANCE_INVALID,
            "candidate provenance/column source_kind disagree")
    if canonical_json_str(envelope) != candidate.provenance_json or \
            canonical_hash(envelope) != candidate.provenance_hash:
        raise _invalid(
            ErrorCode.PERFORMANCE_PROVENANCE_INVALID,
            "candidate provenance bytes/hash do not recompute")

    # subject/project agreement (the recovery verifier's law; second
    # Codex review P1): a schema-valid candidate whose project is not
    # the subject's project is corruption and must not be promoted
    if row_lookup is None:
        from soloring.continuity.models import CreativeEntity
        subject = await session.get(CreativeEntity,
                                    candidate.subject_id)
        if subject is None or subject.project_id != \
                candidate.project_id:
            raise _invalid(
                ErrorCode.PERFORMANCE_PROJECT_MISMATCH,
                "candidate subject/project disagreement — the "
                "candidate does not belong to its subject's project")

    # alignment provenance integrity (same immutable law as creation)
    if row_lookup is None:
        from soloring.performance.revision import (
            _verify_alignment_provenance)
        await _verify_alignment_provenance(
            session, subject_id=candidate.subject_id,
            project_id=candidate.project_id,
            channels=doc["channels"])

    # retarget evidence resolution (the recovery verifier's law;
    # second Codex review P1 + final-diff review): a retargeted
    # candidate may only be promoted when its provenance actually
    # resolves — source revision, exact assessment coordinate,
    # REQUIRES_REVIEW verdict, an owned ACCEPT review — AND its
    # semantic closure equals the referenced source revision
    # byte/scalar-exact (the creation-time copy law)
    if row_lookup is None and envelope["source_kind"] == "retargeted":
        await _verify_retarget_evidence(session, candidate, envelope)
    return {"payload_document": doc, "envelope": envelope}


# the semantic fields a retarget candidate copies byte/scalar-exact
# from its source revision (creation law == recovery law; the payload
# hash columns carry the payload equality)
_RETARGET_COPY_FIELDS = (
    "project_id", "subject_id", "performance_kind",
    "performance_profile_id", "temporal_start_num",
    "temporal_start_den", "temporal_end_num", "temporal_end_den",
    "canonical_channel_payload_blob_hash",
    "canonical_channel_payload_sha256", "payload_schema_version")


async def _verify_retarget_evidence(session: AsyncSession,
                                    candidate, envelope: dict) -> None:
    """Live mirror of the recovery verifier's retarget law chain:
    the envelope's retarget block must resolve to a real
    REQUIRES_REVIEW assessment at the exact recorded coordinate with
    an owned ACCEPT_FOR_NEW_CANDIDATE review, and the candidate's
    semantic closure must equal the referenced source revision —
    valid evidence references plus a divergent payload is still
    corruption, not a lawful retarget.

    Third-Codex hardening: the referenced assessment's scope/report/
    verdict are RECOMPUTED from immutable rows through the same
    builders the assessment service uses (a stored verdict is never
    trusted), and the source revision's own adoption lineage is
    revalidated against its adopted candidate (closure + adoption
    metadata) before it may seed new authority."""
    ret = envelope.get("retarget") or {}
    from soloring.performance.models import (
        PerformanceRevision as PR,
        PerformanceRetargetAssessment,
        PerformanceRetargetReview)
    source = await session.get(PR, ret.get(
        "source_performance_revision_id"))
    if source is None:
        raise _invalid(
            ErrorCode.PERFORMANCE_PROVENANCE_INVALID,
            "retarget provenance source revision does not resolve")
    # source-revision adoption lineage (recovery parity): the source
    # must still reproduce its own adopted candidate's closure and
    # carry lawful adoption metadata before it can seed authority
    source_candidate = await session.get(
        type(candidate), source.adopted_candidate_id)
    if source_candidate is None or not closure_matches(
            source, source_candidate):
        raise _invalid(
            ErrorCode.PERFORMANCE_PROVENANCE_INVALID,
            "retarget source revision does not reproduce its own "
            "adopted candidate closure — tampered authority cannot "
            "seed new authority")
    validate_adoption_metadata(adoption_id=source.adoption_id,
                               adopted_by=source.adopted_by,
                               adopted_at=source.adopted_at)
    for f in _RETARGET_COPY_FIELDS:
        if getattr(candidate, f) != getattr(source, f):
            raise _invalid(
                ErrorCode.PERFORMANCE_PROVENANCE_INVALID,
                f"retarget candidate semantic closure diverges from "
                f"its source revision on {f} — retargeting never "
                "edits semantic performance bytes")
    a = await session.get(PerformanceRetargetAssessment,
                          ret.get("compatibility_assessment_id"))
    if a is None:
        raise _invalid(
            ErrorCode.PERFORMANCE_PROVENANCE_INVALID,
            "retarget provenance assessment does not resolve")
    if (a.performance_revision_id,
            a.from_production_revision_id,
            a.to_production_revision_id) != (
            ret.get("source_performance_revision_id"),
            ret.get("from_production_revision_id"),
            ret.get("to_production_revision_id")):
        raise _invalid(
            ErrorCode.PERFORMANCE_PROVENANCE_INVALID,
            "retarget provenance coordinate mismatch")
    # assessment recomputation (recovery parity): recompute scope and
    # report through the ASSESSMENT SERVICE's own builders — a stored
    # verdict/verdict row that does not recompute is corruption
    from soloring.performance.retarget import (
        EVALUATOR_ID, EVALUATOR_VERSION, _build_report, _build_scope,
        _evaluate)
    from soloring.production.models import ProductionRevision
    from_pr = await session.get(ProductionRevision,
                                a.from_production_revision_id)
    to_pr = await session.get(ProductionRevision,
                              a.to_production_revision_id)
    if from_pr is None or to_pr is None:
        raise _invalid(
            ErrorCode.PERFORMANCE_PROVENANCE_INVALID,
            "retarget assessment physical revision does not resolve")
    # persisted-row laws (recovery parity, third-Codex P1-1
    # completion): assessment project equality, duplicated snapshot
    # hashes, and both ProductionObjects' project ownership — none of
    # which the recomputed scope/report bytes can express
    from soloring.performance.retarget import (
        verify_assessment_persisted_laws)
    await verify_assessment_persisted_laws(
        session, source, a, from_pr, to_pr)
    if a.evaluator_id != EVALUATOR_ID or \
            a.evaluator_version != EVALUATOR_VERSION or \
            a.schema_version != 1:
        raise _invalid(
            ErrorCode.PERFORMANCE_PROVENANCE_INVALID,
            "retarget assessment evaluator identity drift")
    scope = _build_scope(
        performance=source,
        payload_sha=source.canonical_channel_payload_sha256,
        from_pr=from_pr, to_pr=to_pr)
    from soloring.domain.canonical import (canonical_hash,
                                           canonical_json_str)
    scope_json = canonical_json_str(scope)
    scope_hash = canonical_hash(scope)
    if a.scope_json != scope_json or a.scope_hash != scope_hash:
        raise _invalid(
            ErrorCode.PERFORMANCE_PROVENANCE_INVALID,
            "retarget assessment scope does not recompute from "
            "immutable rows")
    verdict, reason = _evaluate(from_pr, to_pr)
    report = _build_report(
        scope_hash=scope_hash, performance_id=source.id,
        from_id=from_pr.id, to_id=to_pr.id, verdict=verdict,
        reason=reason, from_obj=str(from_pr.production_object_id),
        to_obj=str(to_pr.production_object_id))
    if a.report_json != canonical_json_str(report) or \
            a.report_hash != canonical_hash(report) or \
            a.overall_verdict != verdict:
        raise _invalid(
            ErrorCode.PERFORMANCE_PROVENANCE_INVALID,
            "retarget assessment stored report/verdict != evaluator "
            "recomputation")
    if a.overall_verdict != "REQUIRES_REVIEW":
        raise _invalid(
            ErrorCode.PERFORMANCE_PROVENANCE_INVALID,
            "retarget seeded from a non-REQUIRES_REVIEW assessment")
    review = await session.get(PerformanceRetargetReview,
                               ret.get("accepted_review_id"))
    if review is None or review.assessment_id != a.id or \
            review.decision != "ACCEPT_FOR_NEW_CANDIDATE":
        raise _invalid(
            ErrorCode.PERFORMANCE_PROVENANCE_INVALID,
            "retarget accepted review does not satisfy the review "
            "law chain")

_CLOSURE_FIELDS = (
    "project_id", "subject_id", "performance_kind",
    "performance_profile_id", "temporal_start_num",
    "temporal_start_den", "temporal_end_num", "temporal_end_den",
    "canonical_channel_payload_blob_hash",
    "canonical_channel_payload_sha256", "payload_schema_version",
    "source_kind", "provenance_schema_version", "provenance_json",
    "provenance_hash")


def closure_matches(revision: PerformanceRevision,
                    candidate: PerformanceCandidate) -> bool:
    """Frozen R7 §4.2: the revision's copied closure is byte/scalar
    identical to its adopted candidate."""
    return all(getattr(revision, f) == getattr(candidate, f)
               for f in _CLOSURE_FIELDS)


def revalidate_winner(revision: PerformanceRevision,
                      candidate: PerformanceCandidate) -> None:
    """Duplicate-adoption winner revalidation: fail closed on any
    copied-closure divergence; a uniqueness conflict alone is not
    proof of a valid winner."""
    if not closure_matches(revision, candidate):
        raise SoloRingError(
            ErrorCode.INTERNAL_INVARIANT_VIOLATION,
            "adopted PerformanceRevision closure does not reproduce "
            "its candidate closure — corruption, never repaired",
            status_code=500)
    validate_adoption_metadata(adoption_id=revision.adoption_id,
                               adopted_by=revision.adopted_by,
                               adopted_at=revision.adopted_at)


def build_provenance_envelope(provenance: dict) -> dict:
    """Validate the closed candidate-provenance envelope (frozen R7
    §8) and return the canonical envelope object. The retarget
    subobject's cross-row equality chain is validated by the retarget
    service at candidate creation; here the grammar alone is closed."""
    if not isinstance(provenance, dict):
        raise _invalid(ErrorCode.PERFORMANCE_PROVENANCE_INVALID,
                       "provenance must be a JSON object")
    keys = set(provenance)
    if keys != _PROVENANCE_KEYS:
        raise _invalid(
            ErrorCode.PERFORMANCE_PROVENANCE_INVALID,
            f"provenance keys must be exactly {sorted(_PROVENANCE_KEYS)}"
            f" — the schema is closed (got {sorted(keys)}; unknown="
            f"{sorted(keys - _PROVENANCE_KEYS)}, missing="
            f"{sorted(_PROVENANCE_KEYS - keys)})")
    if provenance["schema_version"] != 1:
        raise _invalid(ErrorCode.PERFORMANCE_PROVENANCE_INVALID,
                       "provenance schema_version must be exactly 1")
    kind = provenance["source_kind"]
    if kind not in SOURCE_KINDS:
        raise _invalid(
            ErrorCode.PERFORMANCE_PROVENANCE_INVALID,
            f"source_kind must be one of {SOURCE_KINDS}")
    for field in ("producer_id", "producer_version"):
        v = provenance[field]
        if not isinstance(v, str) or not v.strip() or len(v) > 255:
            raise _invalid(
                ErrorCode.PERFORMANCE_PROVENANCE_INVALID,
                f"{field} must be nonempty (whitespace test) and "
                "<= 255 code points, persisted exactly")
    si = provenance["source_identity"]
    if si is not None:
        if not isinstance(si, str) or not si or len(si) > 1024:
            raise _invalid(
                ErrorCode.PERFORMANCE_PROVENANCE_INVALID,
                "source_identity must be null or nonempty UTF-8 "
                "<= 1024 code points")
        if _PATH_FORMS.match(si):
            raise _invalid(
                ErrorCode.PERFORMANCE_SOURCE_IDENTITY_INVALID,
                "source_identity is audit provenance only and may not "
                "be a mutable local filesystem-path form "
                "(file://, absolute, ./, ../, drive, UNC)")
    psha = provenance["parameters_sha256"]
    if psha is not None and (not isinstance(psha, str)
                             or not _HEX64.fullmatch(psha)):
        raise _invalid(
            ErrorCode.PERFORMANCE_PROVENANCE_INVALID,
            "parameters_sha256 must be null or exactly 64 lowercase "
            "hex characters")
    retarget = provenance["retarget"]
    if kind != "retargeted":
        if retarget is not None:
            raise _invalid(
                ErrorCode.PERFORMANCE_PROVENANCE_INVALID,
                f"source_kind {kind!r} requires retarget = null")
    else:
        if not isinstance(retarget, dict) \
                or set(retarget) != _RETARGET_KEYS:
            raise _invalid(
                ErrorCode.PERFORMANCE_PROVENANCE_INVALID,
                f"retarget provenance keys must be exactly "
                f"{sorted(_RETARGET_KEYS)} — the schema is closed")
        for field in _RETARGET_KEYS:
            v = retarget[field]
            if not isinstance(v, str) or not re.fullmatch(
                    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-"
                    r"[0-9a-f]{12}", v):
                raise _invalid(
                    ErrorCode.PERFORMANCE_PROVENANCE_INVALID,
                    f"retarget.{field} must be an exact UUID string")
    return dict(provenance)


async def _verify_subject(session: AsyncSession, *, subject_id: str,
                          project_id: str) -> None:
    from soloring.continuity.models import CreativeEntity
    entity = await session.get(CreativeEntity, subject_id)
    if entity is None:
        raise not_found(ErrorCode.PERFORMANCE_SUBJECT_NOT_FOUND,
                        f"subject entity {subject_id!r} not found")
    if entity.deleted_at is not None:
        raise _invalid(
            ErrorCode.PERFORMANCE_SUBJECT_DELETED,
            f"subject entity {subject_id!r} is deleted — admission "
            "requires an active subject")
    if entity.project_id != project_id:
        raise _invalid(
            ErrorCode.PERFORMANCE_PROJECT_MISMATCH,
            "subject entity belongs to another project")


async def _verify_alignment_provenance(session: AsyncSession, *,
                                       subject_id: str,
                                       project_id: str,
                                       channels: list[dict]) -> None:
    """Per-keyframe alignment provenance law (frozen R7 §6.5, completed
    by the publication review): the referenced M17A DialogueAlignment
    must exist, its source VP's speaker must equal the Performance
    subject, AND the alignment's dialogue line must belong to the SAME
    Project as the Performance candidate/subject (the same law the
    recovery verifier enforces through _verify_alignment_link). The
    link is audit evidence only."""
    from soloring.performance.models import DialogueAlignment
    seen = set()
    for ch in channels:
        for kf in ch["keyframes"]:
            aid = kf["provenance"]["source_alignment_id"]
            if aid is None or aid in seen:
                continue
            seen.add(aid)
            row = await session.get(DialogueAlignment, aid)
            if row is None:
                raise not_found(ErrorCode.PERFORMANCE_ALIGNMENT_NOT_FOUND,
                                f"dialogue alignment {aid!r} not found")
            from soloring.performance.models import (
                VocalPerformanceRevision as VPR)
            vp = await session.get(
                VPR, row.vocal_performance_revision_id)
            if vp is None:
                raise SoloRingError(
                    ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                    "alignment references a missing VP — corruption",
                    status_code=500)
            if vp.dialogue_line_revision_id is None:
                raise SoloRingError(
                    ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                    "VP lacks its line revision — corruption",
                    status_code=500)
            from soloring.performance.models import DialogueLineRevision
            dlr = await session.get(
                DialogueLineRevision, vp.dialogue_line_revision_id)
            if dlr is None:
                raise SoloRingError(
                    ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                    "VP line revision missing — corruption",
                    status_code=500)
            # third-Codex P1-3: the speaker law is the ALIGNMENT'S OWN
            # VP speaker (recovery parity — recovery checks
            # vocal_performance_revisions.speaker_subject_id), not the
            # dialogue-line revision's speaker; a tampered VP with a
            # different speaker must refuse here, not at backup time
            if vp.speaker_subject_id != subject_id:
                raise _invalid(
                    ErrorCode.PERFORMANCE_ALIGNMENT_SUBJECT_MISMATCH,
                    "alignment's source VP speaker != Performance "
                    "subject")
            from soloring.performance.models import DialogueLine
            line = await session.get(DialogueLine, dlr.dialogue_line_id)
            if line is None or line.project_id is None:
                raise SoloRingError(
                    ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                    "alignment line missing — corruption",
                    status_code=500)
            if line.project_id != project_id:
                raise _invalid(
                    ErrorCode.PERFORMANCE_ALIGNMENT_PROJECT_MISMATCH,
                    "alignment's dialogue line belongs to another "
                    "project than the Performance candidate")
            from soloring.performance.models import VocalCandidate
            vc = await session.get(
                VocalCandidate, vp.adopted_candidate_id)
            blob_project = None
            if vc is not None:
                from soloring.performance.models import (
                    DialogueLineRevision as _DLR2)
                vdlr = await session.get(_DLR2,
                                         vc.dialogue_line_revision_id)
                vline = await session.get(DialogueLine,
                                          vdlr.dialogue_line_id)
                blob_project = vline.project_id
            if blob_project is not None and blob_project != \
                    line.project_id:
                raise _invalid(
                    ErrorCode.PERFORMANCE_ALIGNMENT_PROJECT_MISMATCH,
                    "alignment provenance crosses projects")


async def create_performance_candidate(
        session: AsyncSession, settings, *, subject_id: str,
        performance_kind: str, performance_profile_id: str,
        temporal_start_num: int, temporal_start_den: int,
        temporal_end_num: int, temporal_end_den: int,
        channels: dict, source_provenance: dict) -> PerformanceCandidate:
    """Frozen R7 §9: validate, canonicalize, BlobStore-place, persist —
    or leave nothing. Caller hashes and caller filesystem paths are
    never accepted. Repeated identical submissions are distinct lawful
    evidence rows (no semantic dedupe)."""
    from soloring.continuity.models import CreativeEntity
    entity = await session.get(CreativeEntity, subject_id)
    if entity is None:
        raise not_found(ErrorCode.PERFORMANCE_SUBJECT_NOT_FOUND,
                        f"subject entity {subject_id!r} not found")
    await _verify_subject(session, subject_id=subject_id,
                          project_id=entity.project_id)

    envelope = build_provenance_envelope(source_provenance)
    if envelope["source_kind"] == "retargeted":
        raise _invalid(
            ErrorCode.PERFORMANCE_PROVENANCE_INVALID,
            "retargeted candidates are created only through the "
            "retarget-candidate service")

    payload = {"schema_version": 1,
               "performance_profile_id": performance_profile_id,
               "channels": channels}
    body, normalized = build_canonical_payload(
        payload, performance_kind=performance_kind,
        performance_profile_id=performance_profile_id,
        start_num=temporal_start_num, start_den=temporal_start_den,
        end_num=temporal_end_num, end_den=temporal_end_den)
    payload_sha = hashlib.sha256(body).hexdigest()
    from soloring.performance.profile import validate_temporal_domain
    sn, sd, en, ed = validate_temporal_domain(
        temporal_start_num, temporal_start_den,
        temporal_end_num, temporal_end_den)

    await _verify_alignment_provenance(
        session, subject_id=subject_id, project_id=entity.project_id,
        channels=normalized)

    store = BlobStore(settings)
    tmp = store.tmp_path()
    tmp.write_bytes(body)
    await store.place(payload_sha, tmp)
    from soloring.assets.models import Blob
    if await session.get(Blob, payload_sha) is None:
        session.add(Blob(hash=payload_sha,
                         path=store.relative_path_for_hash(payload_sha),
                         size_bytes=len(body),
                         detected_media_type="application/json",
                         created_at=await db_now(session)))

    prov_json = canonical_json_str(envelope)
    prov_hash = canonical_hash(envelope)
    candidate = PerformanceCandidate(
        id=new_uuid(), project_id=entity.project_id,
        subject_id=subject_id,
        performance_kind=performance_kind,
        performance_profile_id=PROFILE_ID,
        temporal_start_num=sn, temporal_start_den=sd,
        temporal_end_num=en, temporal_end_den=ed,
        canonical_channel_payload_blob_hash=payload_sha,
        canonical_channel_payload_sha256=payload_sha,
        payload_schema_version=1,
        source_kind=envelope["source_kind"],
        provenance_schema_version=1,
        provenance_json=prov_json, provenance_hash=prov_hash,
        created_at=await db_now(session))
    session.add(candidate)
    await session.flush()
    return candidate


async def get_performance_candidate(session: AsyncSession, *,
                                    candidate_id: str
                                    ) -> PerformanceCandidate:
    c = await session.get(PerformanceCandidate, candidate_id)
    if c is None:
        raise not_found(ErrorCode.PERFORMANCE_CANDIDATE_NOT_FOUND,
                        f"performance candidate {candidate_id!r} "
                        "not found")
    return c


async def get_performance_revision(session: AsyncSession, *,
                                   revision_id: str
                                   ) -> PerformanceRevision:
    r = await session.get(PerformanceRevision, revision_id)
    if r is None:
        raise not_found(ErrorCode.PERFORMANCE_REVISION_NOT_FOUND,
                        f"performance revision {revision_id!r} "
                        "not found")
    return r


async def adopt_performance_candidate(
        session: AsyncSession, settings, *, candidate_id: str,
        adopted_by: str) -> PerformanceRevision:
    """Frozen R7 §10 as corrected (CR-E/CR-B + publication review): the
    existing winner returns FIRST regardless of later subject soft
    deletion — activity is a first-admission rule, not an eternal
    historical-validity rule — and every authority transition (first
    or replay) verifies full candidate integrity before inserting or
    returning. ``settings`` is the RUNNING APP's Settings (routes bind
    request.app.state.settings — the same data root the engine and
    candidate placement used); the process-global get_settings()
    singleton is deliberately never consulted here."""
    candidate = await get_performance_candidate(
        session, candidate_id=candidate_id)
    if not isinstance(adopted_by, str) or not adopted_by.strip() \
            or len(adopted_by) > 255:
        raise _invalid(ErrorCode.PERFORMANCE_PAYLOAD_INVALID,
                       "adopted_by must be nonempty (whitespace test) "
                       "<= 255 code points, persisted exactly")

    existing = (await session.execute(
        select(PerformanceRevision).where(
            PerformanceRevision.adopted_candidate_id == candidate.id))
    ).scalar_one_or_none()
    if existing is not None:
        # historical replay: winner + source-candidate integrity,
        # never vetoed by current subject state
        await verify_candidate_integrity(session, settings, candidate)
        revalidate_winner(existing, candidate)
        return existing

    # first adoption: active-subject admission + full integrity
    from soloring.continuity.models import CreativeEntity
    entity = await session.get(CreativeEntity, candidate.subject_id)
    if entity is None or entity.deleted_at is not None:
        raise _invalid(
            ErrorCode.PERFORMANCE_SUBJECT_DELETED,
            "subject is deleted — first adoption requires an active "
            "subject; later soft deletion never invalidates adopted "
            "history")
    await verify_candidate_integrity(session, settings, candidate)

    revision = PerformanceRevision(
        id=new_uuid(), **{f: getattr(candidate, f)
                          for f in _CLOSURE_FIELDS},
        adopted_candidate_id=candidate.id,
        adoption_id=new_uuid(),
        adopted_by=adopted_by, adopted_at=await db_now(session))
    revalidate_winner(revision, candidate)
    session.add(revision)
    try:
        await session.flush()
    except IntegrityError:
        # concurrent duplicate adoption converges through the unique
        # constraint; the losing transaction must roll back to release
        # its snapshot before re-reading the committed winner
        raise
    return revision

