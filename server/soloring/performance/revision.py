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
from soloring.performance.profile import PROFILE_ID, build_canonical_payload

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
_PATH_FORMS = re.compile(
    r"^(file://|/|\./|\.\./|[A-Za-z]:[\\/]|\\\\)")


def _invalid(code: ErrorCode, message: str) -> SoloRingError:
    return SoloRingError(code, message, status_code=422)


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
                                       channels: list[dict]) -> None:
    """Per-keyframe alignment provenance law (frozen R7 §6.5): the
    referenced M17A DialogueAlignment must exist, belong to the same
    Project through its source VP, and that VP's speaker must equal
    the Performance subject. The link is audit evidence only."""
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
            if dlr.speaker_subject_id != subject_id:
                raise _invalid(
                    ErrorCode.PERFORMANCE_ALIGNMENT_SUBJECT_MISMATCH,
                    "alignment's source VP speaker != Performance "
                    "subject")
            from soloring.performance.models import DialogueLine
            line = await session.get(DialogueLine, dlr.dialogue_line_id)
            from soloring.domain.models import Project
            project = await session.get(Project, line.project_id)
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
        session, subject_id=subject_id, channels=normalized)

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
    if not revision.adoption_id or not revision.adopted_by.strip():
        raise SoloRingError(
            ErrorCode.INTERNAL_INVARIANT_VIOLATION,
            "adopted PerformanceRevision has invalid adoption "
            "metadata — corruption", status_code=500)


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
        session: AsyncSession, *, candidate_id: str,
        adopted_by: str) -> PerformanceRevision:
    """Frozen R7 §10. Sequential duplicates return the winner with
    original adoption metadata; concurrent duplicates converge
    through UNIQUE(adopted_candidate_id) — the loser rolls back and
    re-reads the winner (route-level retry handles the transaction
    boundary exactly as M17A adoption does)."""
    candidate = await get_performance_candidate(
        session, candidate_id=candidate_id)
    if not isinstance(adopted_by, str) or not adopted_by.strip() \
            or len(adopted_by) > 255:
        raise _invalid(ErrorCode.PERFORMANCE_PAYLOAD_INVALID,
                       "adopted_by must be nonempty (whitespace test) "
                       "<= 255 code points, persisted exactly")
    from soloring.continuity.models import CreativeEntity
    entity = await session.get(CreativeEntity, candidate.subject_id)
    if entity is not None and entity.deleted_at is not None:
        raise _invalid(
            ErrorCode.PERFORMANCE_SUBJECT_DELETED,
            "subject is deleted — first adoption requires an active "
            "subject")

    existing = (await session.execute(
        select(PerformanceRevision).where(
            PerformanceRevision.adopted_candidate_id == candidate.id))
    ).scalar_one_or_none()
    if existing is not None:
        revalidate_winner(existing, candidate)
        return existing

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
