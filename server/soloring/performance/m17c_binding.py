"""M17C PF-03 dialogue-bound vocal/facial synchronization services.

M17C is additive to the published M17B Performance authority. Generic M17B
candidates/revisions remain lawful without a binding. Dialogue-bound creation
adds one immutable candidate companion; adoption and retargeting copy that
semantic closure exactly into successor companion rows.
"""

from __future__ import annotations

import hashlib
import json
from fractions import Fraction

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.domain.now import db_now
from soloring.errors import ErrorCode, SoloRingError, not_found
from soloring.performance import revision as revision_svc
from soloring.performance.m17c_contract import (
    BINDING_FIELDS,
    PERFORMANCE_REQUIRED_ARTICULATION_MISSING,
    PERFORMANCE_VOCAL_ALIGNMENT_MISMATCH,
    PERFORMANCE_VOCAL_BINDING_INVALID,
    PERFORMANCE_VOCAL_BINDING_NOT_FOUND,
    PERFORMANCE_VOCAL_INTERVAL_INVALID,
    PERFORMANCE_VOCAL_PROJECT_MISMATCH,
    PERFORMANCE_VOCAL_SUBJECT_MISMATCH,
    REQUIRED_ARTICULATION,
    corrupt,
    invalid,
    strict_int,
)
from soloring.performance.m17c_models import (
    PerformanceCandidateVocalBinding,
    PerformanceRevisionVocalBinding,
)
from soloring.performance.models import (
    DialogueAlignment,
    DialogueLine,
    DialogueLineRevision,
    PerformanceCandidate,
    PerformanceRevision,
    VocalCandidate,
    VocalPerformanceRevision,
)
from soloring.performance.temporal import canonical_rational, performance_ms

_BINDING_INPUT_KEYS = {
    "vocal_performance_revision_id",
    "source_start_sample",
    "source_end_sample_exclusive",
    "sample_rate_hz",
    "performance_origin_ms",
}
_ORIGIN_KEYS = {"num", "den"}
_VOCAL_COPY_FIELDS = (
    "dialogue_line_revision_id",
    "retained_audio_blob_hash",
    "native_sample_rate_hz",
    "retained_sample_count",
    "trim_start_sample",
    "trim_end_sample_exclusive",
    "source_kind",
    "provenance_schema_version",
    "provenance_json",
    "provenance_hash",
)


def _binding_document(raw: dict) -> tuple[dict, tuple[int, int]]:
    if not isinstance(raw, dict) or set(raw) != _BINDING_INPUT_KEYS:
        got = sorted(raw) if isinstance(raw, dict) else type(raw).__name__
        raise invalid(
            PERFORMANCE_VOCAL_BINDING_INVALID,
            "vocal_binding keys must be exactly "
            f"{sorted(_BINDING_INPUT_KEYS)} (got {got!r})",
        )
    vp_id = raw["vocal_performance_revision_id"]
    if not isinstance(vp_id, str) or not vp_id:
        raise invalid(
            PERFORMANCE_VOCAL_BINDING_INVALID,
            "vocal_performance_revision_id must be a nonempty exact id",
        )
    start = strict_int(raw["source_start_sample"], "source_start_sample")
    end = strict_int(
        raw["source_end_sample_exclusive"], "source_end_sample_exclusive")
    rate = strict_int(raw["sample_rate_hz"], "sample_rate_hz")
    if start < 0 or start >= end:
        raise invalid(
            PERFORMANCE_VOCAL_INTERVAL_INVALID,
            "vocal source interval must satisfy 0 <= start < end",
        )
    if rate <= 0:
        raise invalid(
            PERFORMANCE_VOCAL_BINDING_INVALID,
            "sample_rate_hz must be positive",
        )
    origin = raw["performance_origin_ms"]
    if not isinstance(origin, dict) or set(origin) != _ORIGIN_KEYS:
        raise invalid(
            PERFORMANCE_VOCAL_BINDING_INVALID,
            "performance_origin_ms must contain exactly num and den",
        )
    on = strict_int(origin["num"], "performance_origin_ms.num")
    od = strict_int(origin["den"], "performance_origin_ms.den")
    cn, cd = canonical_rational(on, od)
    if (cn, cd) != (on, od):
        raise invalid(
            PERFORMANCE_VOCAL_BINDING_INVALID,
            "performance_origin_ms must already be canonical-reduced",
        )
    doc = {
        "binding_schema_version": 1,
        "synchronization_basis_version": 1,
        "vocal_performance_revision_id": vp_id,
        "source_start_sample": start,
        "source_end_sample_exclusive": end,
        "sample_rate_hz": rate,
        "performance_origin_ms": {"num": cn, "den": cd},
    }
    return doc, (cn, cd)


def _row_document(row) -> dict:
    return {
        "binding_schema_version": row.binding_schema_version,
        "synchronization_basis_version": row.synchronization_basis_version,
        "vocal_performance_revision_id": row.vocal_performance_revision_id,
        "source_start_sample": row.source_start_sample,
        "source_end_sample_exclusive": row.source_end_sample_exclusive,
        "sample_rate_hz": row.sample_rate_hz,
        "performance_origin_ms": {
            "num": row.performance_origin_num,
            "den": row.performance_origin_den,
        },
    }


def _verify_binding_bytes(row) -> dict:
    if row.binding_schema_version != 1 or row.synchronization_basis_version != 1:
        raise corrupt("M17C vocal binding schema/basis version is not 1")
    cn, cd = canonical_rational(
        row.performance_origin_num, row.performance_origin_den)
    if (cn, cd) != (row.performance_origin_num, row.performance_origin_den):
        raise corrupt("M17C vocal binding stores a noncanonical rational")
    doc = _row_document(row)
    expected_json = canonical_json_str(doc)
    expected_hash = canonical_hash(doc)
    if row.binding_json != expected_json or row.binding_hash != expected_hash:
        raise corrupt("M17C vocal binding canonical bytes/hash diverge")
    return doc


async def verify_vocal_performance_integrity(
    session: AsyncSession,
    settings,
    vp: VocalPerformanceRevision,
    *,
    expected_project_id: str | None = None,
) -> str:
    """Live M17A-recovery-parity verifier for a VP seeding new authority."""
    vc = await session.get(VocalCandidate, vp.adopted_candidate_id)
    if vc is None:
        raise corrupt("bound VocalPerformanceRevision adopted candidate missing")
    count = (await session.execute(
        select(func.count()).select_from(VocalPerformanceRevision).where(
            VocalPerformanceRevision.adopted_candidate_id == vc.id)
    )).scalar_one()
    if count != 1:
        raise corrupt("bound VocalCandidate is not adopted exactly once")
    if any(getattr(vp, f) != getattr(vc, f) for f in _VOCAL_COPY_FIELDS):
        raise corrupt("bound VocalPerformanceRevision closure != adopted candidate")

    try:
        provenance = json.loads(vc.provenance_json)
    except json.JSONDecodeError as exc:
        raise corrupt("bound VocalCandidate provenance is not JSON") from exc
    from soloring.performance.vocal import _provenance_v1, _verify_blob
    try:
        normalized = _provenance_v1(provenance)
    except SoloRingError as exc:
        raise corrupt(
            f"bound VocalCandidate provenance violates its closed grammar: {exc.message}"
        ) from exc
    if normalized != provenance or canonical_json_str(normalized) != vc.provenance_json:
        raise corrupt("bound VocalCandidate provenance is not canonical")
    if canonical_hash(normalized) != vc.provenance_hash:
        raise corrupt("bound VocalCandidate provenance hash diverges")
    if normalized["source_kind"] != vc.source_kind:
        raise corrupt("bound VocalCandidate source_kind/provenance disagree")

    try:
        blob = await _verify_blob(session, settings, vp.retained_audio_blob_hash)
    except SoloRingError as exc:
        raise corrupt(f"bound VP retained audio integrity failed: {exc.message}") from exc
    if hashlib.sha256(blob["data"]).hexdigest() != vp.retained_audio_blob_hash:
        raise corrupt("bound VP retained audio bytes do not rehash")
    from soloring.performance.audio_inspection import inspect_wave
    try:
        info = inspect_wave(blob["data"])
    except SoloRingError as exc:
        raise corrupt(f"bound VP retained WAVE is invalid: {exc.message}") from exc
    if info["sample_rate_hz"] != vp.native_sample_rate_hz or \
            info["sample_frame_count"] != vp.retained_sample_count:
        raise corrupt("bound VP WAVE properties disagree with stored authority")
    if not (0 <= vp.trim_start_sample < vp.trim_end_sample_exclusive <=
            vp.retained_sample_count):
        raise corrupt("bound VP authoritative trim is illegal")

    dlr = await session.get(DialogueLineRevision, vp.dialogue_line_revision_id)
    if dlr is None:
        raise corrupt("bound VP DialogueLineRevision is missing")
    if vc.dialogue_line_revision_id != dlr.id:
        raise corrupt("bound VocalCandidate and VP name different line revisions")
    if vp.speaker_subject_id != dlr.speaker_subject_id:
        raise corrupt("bound VP speaker != DialogueLineRevision speaker")
    line = await session.get(DialogueLine, dlr.dialogue_line_id)
    if line is None:
        raise corrupt("bound VP DialogueLine is missing")
    from soloring.continuity.models import CreativeEntity
    speaker = await session.get(CreativeEntity, vp.speaker_subject_id)
    if speaker is None or speaker.project_id != line.project_id:
        raise corrupt("bound VP speaker does not belong to DialogueLine project")
    if expected_project_id is not None and line.project_id != expected_project_id:
        raise invalid(
            PERFORMANCE_VOCAL_PROJECT_MISMATCH,
            "bound VP/DialogueLine belongs to another Project",
        )
    return line.project_id


def _vocal_performance_interval(row) -> tuple[Fraction, Fraction]:
    start = Fraction(row.performance_origin_num, row.performance_origin_den)
    end = performance_ms(
        row.source_end_sample_exclusive,
        origin_num=row.performance_origin_num,
        origin_den=row.performance_origin_den,
        source_start_sample=row.source_start_sample,
        sample_rate_hz=row.sample_rate_hz,
    )
    return start, end


def _candidate_domain(candidate: PerformanceCandidate) -> tuple[Fraction, Fraction]:
    return (
        Fraction(candidate.temporal_start_num, candidate.temporal_start_den),
        Fraction(candidate.temporal_end_num, candidate.temporal_end_den),
    )


async def _verify_alignment_exact_vp(
    session: AsyncSession, payload_document: dict, vp_id: str
) -> None:
    seen: set[str] = set()
    for channel in payload_document["channels"]:
        for keyframe in channel["keyframes"]:
            aid = keyframe["provenance"]["source_alignment_id"]
            if aid is None or aid in seen:
                continue
            seen.add(aid)
            alignment = await session.get(DialogueAlignment, aid)
            if alignment is None:
                raise not_found(
                    ErrorCode.PERFORMANCE_ALIGNMENT_NOT_FOUND,
                    f"dialogue alignment {aid!r} not found",
                )
            if alignment.vocal_performance_revision_id != vp_id:
                raise invalid(
                    PERFORMANCE_VOCAL_ALIGNMENT_MISMATCH,
                    "dialogue-bound keyframe cites an alignment derived from "
                    "a different VocalPerformanceRevision",
                )


def _verify_articulation(payload_document: dict,
                         interval: tuple[Fraction, Fraction]) -> None:
    lo, hi = interval
    by_key = {ch["channel_key"]: ch for ch in payload_document["channels"]}
    for key in REQUIRED_ARTICULATION:
        channel = by_key.get(key)
        if channel is None:
            raise invalid(
                PERFORMANCE_REQUIRED_ARTICULATION_MISSING,
                f"dialogue-bound performance requires articulation channel {key!r}",
            )
        if not any(
            lo <= Fraction(kf["time_ms"]["num"], kf["time_ms"]["den"]) < hi
            for kf in channel["keyframes"]
        ):
            raise invalid(
                PERFORMANCE_REQUIRED_ARTICULATION_MISSING,
                f"articulation channel {key!r} has no keyframe inside the "
                "bound vocal interval",
            )


async def verify_candidate_vocal_binding(
    session: AsyncSession,
    settings,
    candidate: PerformanceCandidate,
    row: PerformanceCandidateVocalBinding,
    *,
    payload_document: dict | None = None,
) -> dict:
    if row.performance_candidate_id != candidate.id:
        raise corrupt("candidate vocal-binding parent id diverges")
    if candidate.performance_kind not in ("FACIAL", "BODY_FACIAL"):
        raise invalid(
            PERFORMANCE_VOCAL_BINDING_INVALID,
            "dialogue-bound performance must be FACIAL or BODY_FACIAL",
        )
    _verify_binding_bytes(row)
    vp = await session.get(VocalPerformanceRevision,
                           row.vocal_performance_revision_id)
    if vp is None:
        raise not_found(
            ErrorCode.VOCAL_PERFORMANCE_NOT_FOUND,
            f"vocal performance revision {row.vocal_performance_revision_id!r} "
            "not found",
        )
    await verify_vocal_performance_integrity(
        session, settings, vp, expected_project_id=candidate.project_id)
    if candidate.subject_id != vp.speaker_subject_id:
        raise invalid(
            PERFORMANCE_VOCAL_SUBJECT_MISMATCH,
            "Performance subject != bound VP speaker",
        )
    if row.sample_rate_hz != vp.native_sample_rate_hz:
        raise invalid(
            ErrorCode.SAMPLE_RATE_MISMATCH,
            "vocal binding sample rate != bound VP native sample rate",
        )
    if not (vp.trim_start_sample <= row.source_start_sample <
            row.source_end_sample_exclusive <= vp.trim_end_sample_exclusive):
        raise invalid(
            PERFORMANCE_VOCAL_INTERVAL_INVALID,
            "vocal binding source interval lies outside the bound VP trim",
        )
    bound_interval = _vocal_performance_interval(row)
    domain = _candidate_domain(candidate)
    if not (domain[0] <= bound_interval[0] < bound_interval[1] <= domain[1]):
        raise invalid(
            PERFORMANCE_VOCAL_INTERVAL_INVALID,
            "induced vocal Performance interval lies outside candidate domain",
        )
    if payload_document is None:
        payload_document = (await revision_svc.verify_candidate_integrity(
            session, settings, candidate))["payload_document"]
    await _verify_alignment_exact_vp(
        session, payload_document, row.vocal_performance_revision_id)
    _verify_articulation(payload_document, bound_interval)
    return {"vp": vp, "payload_document": payload_document,
            "performance_interval": bound_interval}


async def create_dialogue_bound_performance_candidate(
    session: AsyncSession,
    settings,
    *,
    subject_id: str,
    performance_kind: str,
    performance_profile_id: str,
    temporal_start_num: int,
    temporal_start_den: int,
    temporal_end_num: int,
    temporal_end_den: int,
    channels: list[dict],
    source_provenance: dict,
    vocal_binding: dict,
) -> tuple[PerformanceCandidate, PerformanceCandidateVocalBinding]:
    if performance_kind not in ("FACIAL", "BODY_FACIAL"):
        raise invalid(
            PERFORMANCE_VOCAL_BINDING_INVALID,
            "dialogue-bound candidate route accepts FACIAL or BODY_FACIAL only",
        )
    doc, (on, od) = _binding_document(vocal_binding)
    candidate = await revision_svc.create_performance_candidate(
        session,
        settings,
        subject_id=subject_id,
        performance_kind=performance_kind,
        performance_profile_id=performance_profile_id,
        temporal_start_num=temporal_start_num,
        temporal_start_den=temporal_start_den,
        temporal_end_num=temporal_end_num,
        temporal_end_den=temporal_end_den,
        channels=channels,
        source_provenance=source_provenance,
    )
    row = PerformanceCandidateVocalBinding(
        performance_candidate_id=candidate.id,
        vocal_performance_revision_id=doc["vocal_performance_revision_id"],
        source_start_sample=doc["source_start_sample"],
        source_end_sample_exclusive=doc["source_end_sample_exclusive"],
        sample_rate_hz=doc["sample_rate_hz"],
        performance_origin_num=on,
        performance_origin_den=od,
        synchronization_basis_version=1,
        binding_schema_version=1,
        binding_json=canonical_json_str(doc),
        binding_hash=canonical_hash(doc),
        created_at=await db_now(session),
    )
    integrity = await revision_svc.verify_candidate_integrity(
        session, settings, candidate)
    await verify_candidate_vocal_binding(
        session, settings, candidate, row,
        payload_document=integrity["payload_document"])
    session.add(row)
    await session.flush()
    return candidate, row


async def get_candidate_vocal_binding(
    session: AsyncSession, *, candidate_id: str
) -> PerformanceCandidateVocalBinding:
    row = await session.get(PerformanceCandidateVocalBinding, candidate_id)
    if row is None:
        raise not_found(
            PERFORMANCE_VOCAL_BINDING_NOT_FOUND,
            f"performance candidate {candidate_id!r} has no vocal binding",
        )
    return row


async def get_revision_vocal_binding(
    session: AsyncSession, *, revision_id: str
) -> PerformanceRevisionVocalBinding:
    row = await session.get(PerformanceRevisionVocalBinding, revision_id)
    if row is None:
        raise not_found(
            PERFORMANCE_VOCAL_BINDING_NOT_FOUND,
            f"performance revision {revision_id!r} has no vocal binding",
        )
    return row


def _semantic_binding_equal(candidate_row, revision_row) -> bool:
    return all(getattr(candidate_row, f) == getattr(revision_row, f)
               for f in BINDING_FIELDS)


async def verify_revision_vocal_binding(
    session: AsyncSession,
    settings,
    revision: PerformanceRevision,
    row: PerformanceRevisionVocalBinding,
) -> dict:
    if row.performance_revision_id != revision.id:
        raise corrupt("revision vocal-binding parent id diverges")
    candidate = await session.get(PerformanceCandidate,
                                  revision.adopted_candidate_id)
    if candidate is None:
        raise corrupt("dialogue-bound revision adopted candidate is missing")
    candidate_row = await session.get(
        PerformanceCandidateVocalBinding, candidate.id)
    if candidate_row is None:
        raise corrupt("dialogue-bound revision source candidate binding is missing")
    if not _semantic_binding_equal(candidate_row, row):
        raise corrupt("revision vocal binding != adopted candidate binding closure")
    await verify_candidate_vocal_binding(
        session, settings, candidate, candidate_row)
    _verify_binding_bytes(row)
    return {"candidate": candidate, "candidate_binding": candidate_row}


async def adoption_binding_precheck(
    session: AsyncSession,
    settings,
    candidate: PerformanceCandidate,
) -> PerformanceCandidateVocalBinding | None:
    row = await session.get(PerformanceCandidateVocalBinding, candidate.id)
    if row is not None:
        await verify_candidate_vocal_binding(session, settings, candidate, row)
    return row


async def converge_revision_binding(
    session: AsyncSession,
    settings,
    candidate: PerformanceCandidate,
    revision: PerformanceRevision,
    candidate_binding: PerformanceCandidateVocalBinding | None,
    *,
    allow_create: bool,
) -> PerformanceRevisionVocalBinding | None:
    existing = await session.get(PerformanceRevisionVocalBinding, revision.id)
    if candidate_binding is None:
        if existing is not None:
            raise corrupt(
                "generic M17B candidate has an unexpected revision vocal binding")
        return None
    if existing is not None:
        await verify_revision_vocal_binding(session, settings, revision, existing)
        return existing
    if not allow_create:
        raise corrupt(
            "adopted dialogue-bound winner is missing its revision vocal binding")
    row = PerformanceRevisionVocalBinding(
        performance_revision_id=revision.id,
        **{field: getattr(candidate_binding, field) for field in BINDING_FIELDS},
        created_at=await db_now(session),
    )
    session.add(row)
    await session.flush()
    await verify_revision_vocal_binding(session, settings, revision, row)
    return row


async def preserve_retarget_binding(
    session: AsyncSession,
    settings,
    *,
    source_revision: PerformanceRevision,
    candidate: PerformanceCandidate,
) -> PerformanceCandidateVocalBinding | None:
    source = await session.get(PerformanceRevisionVocalBinding,
                               source_revision.id)
    existing = await session.get(PerformanceCandidateVocalBinding,
                                 candidate.id)
    if source is None:
        if existing is not None:
            raise corrupt("non-dialogue retarget candidate unexpectedly has binding")
        return None
    await verify_revision_vocal_binding(session, settings, source_revision, source)
    if existing is not None:
        for field in BINDING_FIELDS:
            if getattr(existing, field) != getattr(source, field):
                raise corrupt("retarget candidate vocal binding diverges from source")
        await verify_candidate_vocal_binding(session, settings, candidate, existing)
        return existing
    row = PerformanceCandidateVocalBinding(
        performance_candidate_id=candidate.id,
        **{field: getattr(source, field) for field in BINDING_FIELDS},
        created_at=await db_now(session),
    )
    session.add(row)
    await session.flush()
    await verify_candidate_vocal_binding(session, settings, candidate, row)
    return row


def binding_view(row) -> dict:
    return {
        "vocal_performance_revision_id": row.vocal_performance_revision_id,
        "source_start_sample": row.source_start_sample,
        "source_end_sample_exclusive": row.source_end_sample_exclusive,
        "sample_rate_hz": row.sample_rate_hz,
        "performance_origin_ms": {
            "num": row.performance_origin_num,
            "den": row.performance_origin_den,
        },
        "synchronization_basis_version": row.synchronization_basis_version,
        "binding_schema_version": row.binding_schema_version,
        "binding_hash": row.binding_hash,
        "created_at": row.created_at,
    }
