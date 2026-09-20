"""VocalCandidate / VocalPerformanceRevision / current-selection
services (frozen R5 §4.3-4.5, §9.2-§9.4). Adoption is THE A7 approval
transition: idempotent per candidate (UNIQUE adopted_candidate_id),
never touches Take approval, and never changes the current selection.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select

from sqlalchemy.ext.asyncio import AsyncSession

from soloring.assets.blob_store import BlobStore
from soloring.domain.now import db_now
from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.domain.ids import new_uuid
from soloring.errors import (ErrorCode, SoloRingError, not_found,
                             validation_error)
from soloring.performance.audio_inspection import inspect_wave
from soloring.performance.dialogue import get_dialogue_line_revision
from soloring.performance.models import (DialogueLineRevision,
                                         VocalCandidate,
                                         VocalPerformanceRevision,
                                         VocalPerformanceSelection)

_SOURCE_KINDS = ("recorded", "adr", "imported", "generated")
_GENERATED_FIELDS = ("generator_id", "generator_version", "workflow_id",
                     "workflow_version")


def _provenance_v1(doc: dict) -> dict:
    """Canonical CLOSED provenance schema v1 (source review finding 5):
    exact fields only — caller extras are rejected, never silently
    discarded before canonical hashing; schema_version must be exactly 1
    so a different declared version cannot be rewritten into v1."""
    if not isinstance(doc, dict):
        raise SoloRingError(ErrorCode.PROVENANCE_SCHEMA_INVALID,
                            "provenance must be a JSON object",
                            status_code=422)
    if doc.get("schema_version") != 1:
        raise SoloRingError(
            ErrorCode.PROVENANCE_SCHEMA_INVALID,
            f"provenance schema_version must be exactly 1 (got "
            f"{doc.get('schema_version')!r})", status_code=422)
    kind = doc.get("source_kind")
    if kind not in _SOURCE_KINDS:
        raise SoloRingError(
            ErrorCode.PROVENANCE_SCHEMA_INVALID,
            f"source_kind must be one of {_SOURCE_KINDS}",
            status_code=422)
    if kind == "generated":
        keys = set(doc) - {"schema_version", "source_kind"}
        if keys != set(_GENERATED_FIELDS):
            raise SoloRingError(
                ErrorCode.PROVENANCE_SCHEMA_INVALID,
                "generated provenance requires exactly "
                f"{sorted(_GENERATED_FIELDS)} (got extras "
                f"{sorted(keys - set(_GENERATED_FIELDS))}, missing "
                f"{sorted(set(_GENERATED_FIELDS) - keys)})",
                status_code=422)
        out = {"schema_version": 1, "source_kind": "generated"}
        for key in _GENERATED_FIELDS:
            v = doc[key]
            if not isinstance(v, str) or not v.strip() or len(v) > 255:
                raise SoloRingError(
                    ErrorCode.PROVENANCE_SCHEMA_INVALID,
                    f"generated provenance {key} must be nonempty "
                    "<= 255 code points", status_code=422)
            out[key] = v.strip()
        return out
    if set(doc) != {"schema_version", "source_kind"}:
        raise SoloRingError(
            ErrorCode.PROVENANCE_SCHEMA_INVALID,
            f"{kind} provenance carries fields beyond schema_version/"
            "source_kind — the canonical schema is closed",
            status_code=422)
    return {"schema_version": 1, "source_kind": kind}


async def _verify_blob(session: AsyncSession, settings, blob_hash: str
                       ) -> dict:
    """Verify a retained Blob through the established BlobStore seam
    (source review finding 8): physical bytes are verified by the same
    primitive the repository uses everywhere — no parallel re-implementation
    — and failures carry the durable typed codes (finding 9)."""
    from soloring.assets.models import Blob
    row = await session.get(Blob, blob_hash)
    if row is None:
        raise not_found(ErrorCode.BLOB_NOT_FOUND,
                        f"blob {blob_hash!r} not found")
    store = BlobStore(settings)
    physical = await store.verify_physical_bytes(
        blob_hash, expected_size=row.size_bytes)
    if not physical.ok:
        if physical.reason == "missing":
            raise SoloRingError(
                ErrorCode.BLOB_BYTES_MISSING,
                f"blob {blob_hash!r} bytes are missing from the Blob "
                "root", status_code=422)
        if physical.reason == "hash_mismatch":
            raise SoloRingError(
                ErrorCode.BLOB_HASH_MISMATCH,
                f"blob {blob_hash!r} physical bytes hash to "
                f"{physical.actual_hash}", status_code=422)
        raise SoloRingError(
            ErrorCode.BLOB_HASH_MISMATCH,
            f"blob {blob_hash!r} physical verification failed "
            f"({physical.reason})", status_code=422)
    data = store.path_for_hash(blob_hash).read_bytes()
    return {"row": row, "data": data}


async def create_vocal_candidate(
        session: AsyncSession, settings, *,
        dialogue_line_revision_id: str,
        retained_audio_blob_hash: str,
        source_provenance: dict,
        trim_start_sample: int | None = None,
        trim_end_sample_exclusive: int | None = None) -> VocalCandidate:
    rev = await get_dialogue_line_revision(
        session, revision_id=dialogue_line_revision_id)
    prov = _provenance_v1(source_provenance)
    prov_json = canonical_json_str(prov)
    prov_hash = canonical_hash(prov)
    blob = await _verify_blob(session, settings, retained_audio_blob_hash)
    info = inspect_wave(blob["data"])
    count = info["sample_frame_count"]
    if trim_start_sample is None and trim_end_sample_exclusive is None:
        ts, te = 0, count
    elif trim_start_sample is None or trim_end_sample_exclusive is None:
        raise SoloRingError(ErrorCode.INVALID_AUDIO_TRIM,
                            "exactly one trim coordinate supplied; "
                            "supply both or neither",
                            status_code=422)
    else:
        ts, te = trim_start_sample, trim_end_sample_exclusive
    if not (0 <= ts < te <= count):
        raise SoloRingError(ErrorCode.INVALID_AUDIO_TRIM,
                            f"trim [{ts}, {te}) invalid for "
                            f"{count} sample frames",
                            status_code=422)
    candidate = VocalCandidate(
        id=new_uuid(), dialogue_line_revision_id=rev.id,
        retained_audio_blob_hash=retained_audio_blob_hash,
        native_sample_rate_hz=info["sample_rate_hz"],
        retained_sample_count=count,
        trim_start_sample=ts, trim_end_sample_exclusive=te,
        source_kind=prov["source_kind"],
        provenance_schema_version=1,
        provenance_json=prov_json, provenance_hash=prov_hash,
        created_at=await db_now(session))
    session.add(candidate)
    await session.flush()
    return candidate


async def get_vocal_candidate(session: AsyncSession, *,
                              candidate_id: str) -> VocalCandidate:
    c = await session.get(VocalCandidate, candidate_id)
    if c is None:
        raise not_found(ErrorCode.VOCAL_CANDIDATE_NOT_FOUND,
                        f"vocal candidate {candidate_id!r} not found")
    return c


def _closure_equals(vp: VocalPerformanceRevision,
                    c: VocalCandidate) -> bool:
    return (vp.dialogue_line_revision_id == c.dialogue_line_revision_id
            and vp.retained_audio_blob_hash == c.retained_audio_blob_hash
            and vp.native_sample_rate_hz == c.native_sample_rate_hz
            and vp.retained_sample_count == c.retained_sample_count
            and vp.trim_start_sample == c.trim_start_sample
            and vp.trim_end_sample_exclusive == c.trim_end_sample_exclusive
            and vp.source_kind == c.source_kind
            and vp.provenance_schema_version ==
            c.provenance_schema_version
            and vp.provenance_json == c.provenance_json
            and vp.provenance_hash == c.provenance_hash)


async def adopt_vocal_candidate(session: AsyncSession, *,
                                candidate_id: str,
                                adopted_by: str
                                ) -> VocalPerformanceRevision:
    async def _existing() -> VocalPerformanceRevision | None:
        return (await session.execute(
            select(VocalPerformanceRevision).where(
                VocalPerformanceRevision.adopted_candidate_id == c.id))
        ).scalar_one_or_none()

    c = await get_vocal_candidate(session, candidate_id=candidate_id)
    if not isinstance(adopted_by, str) or not adopted_by.strip():
        raise validation_error("adopted_by must be nonempty")
    existing = await _existing()
    if existing is not None:
        return existing
    rev = await session.get(DialogueLineRevision,
                            c.dialogue_line_revision_id)
    if rev is None:
        raise SoloRingError(ErrorCode.VOCAL_ADOPTION_CORRUPT,
                            "candidate line revision missing",
                            status_code=409)
    if rev.speaker_subject_id is None:
        raise SoloRingError(ErrorCode.VOCAL_ADOPTION_CORRUPT,
                            "line revision lacks a speaker",
                            status_code=409)
    (n,) = (await session.execute(
        select(func.max(VocalPerformanceRevision.revision_number)).where(
            VocalPerformanceRevision.dialogue_line_revision_id == rev.id))
    ).one()
    vp = VocalPerformanceRevision(
        id=new_uuid(), dialogue_line_revision_id=rev.id,
        revision_number=(n or 0) + 1,
        speaker_subject_id=rev.speaker_subject_id,
        retained_audio_blob_hash=c.retained_audio_blob_hash,
        native_sample_rate_hz=c.native_sample_rate_hz,
        retained_sample_count=c.retained_sample_count,
        trim_start_sample=c.trim_start_sample,
        trim_end_sample_exclusive=c.trim_end_sample_exclusive,
        source_kind=c.source_kind,
        provenance_schema_version=c.provenance_schema_version,
        provenance_json=c.provenance_json,
        provenance_hash=c.provenance_hash,
        adopted_candidate_id=c.id, adoption_id=new_uuid(),
        adopted_by=adopted_by.strip(), adopted_at=await db_now(session))
    if not _closure_equals(vp, c):
        raise SoloRingError(ErrorCode.VOCAL_ADOPTION_CORRUPT,
                            "adoption closure does not equal the "
                            "candidate closure",
                            status_code=409)
    if vp.speaker_subject_id != rev.speaker_subject_id:
        raise SoloRingError(
            ErrorCode.VOCAL_ADOPTION_CORRUPT,
            "VP speaker != DialogueLineRevision speaker — corruption, "
            "never silently reconciled", status_code=409)
    session.add(vp)
    # a UNIQUE(adopted_candidate_id) conflict propagates to the caller:
    # the API route converges it transaction-safely (rollback + re-run
    # sees the committed winner) — mid-transaction re-query cannot see
    # the winner under SQLite's read snapshot (source review finding 6)
    await session.flush()
    return vp


async def get_vocal_performance_revision(
        session: AsyncSession, *, revision_id: str
) -> VocalPerformanceRevision:
    vp = await session.get(VocalPerformanceRevision, revision_id)
    if vp is None:
        raise not_found(ErrorCode.VOCAL_PERFORMANCE_NOT_FOUND,
                        f"vocal performance revision {revision_id!r} "
                        "not found")
    return vp


async def list_vocal_candidates(session: AsyncSession, *,
                                dialogue_line_revision_id: str
                                ) -> list[dict]:
    await get_dialogue_line_revision(
        session, revision_id=dialogue_line_revision_id)
    rows = (await session.execute(
        select(VocalCandidate).where(
            VocalCandidate.dialogue_line_revision_id ==
            dialogue_line_revision_id)
        .order_by(VocalCandidate.created_at, VocalCandidate.id))
    ).scalars().all()
    return [{"id": r.id,
             "retained_audio_blob_hash": r.retained_audio_blob_hash,
             "native_sample_rate_hz": r.native_sample_rate_hz,
             "retained_sample_count": r.retained_sample_count,
             "trim_start_sample": r.trim_start_sample,
             "trim_end_sample_exclusive": r.trim_end_sample_exclusive,
             "source_kind": r.source_kind,
             "provenance_hash": r.provenance_hash,
             "created_at": r.created_at} for r in rows]


async def list_vocal_performances(session: AsyncSession, *,
                                  dialogue_line_revision_id: str
                                  ) -> list[dict]:
    return await list_vocal_performances_full(
        session, dialogue_line_revision_id=dialogue_line_revision_id)


async def list_vocal_performances_full(session: AsyncSession, *,
                                       dialogue_line_revision_id: str
                                       ) -> list[dict]:
    await get_dialogue_line_revision(
        session, revision_id=dialogue_line_revision_id)
    rows = (await session.execute(
        select(VocalPerformanceRevision).where(
            VocalPerformanceRevision.dialogue_line_revision_id ==
            dialogue_line_revision_id)
        .order_by(VocalPerformanceRevision.revision_number))
    ).scalars().all()
    return [{"id": r.id,
             "dialogue_line_revision_id": r.dialogue_line_revision_id,
             "revision_number": r.revision_number,
             "speaker_subject_id": r.speaker_subject_id,
             "retained_audio_blob_hash": r.retained_audio_blob_hash,
             "native_sample_rate_hz": r.native_sample_rate_hz,
             "retained_sample_count": r.retained_sample_count,
             "trim_start_sample": r.trim_start_sample,
             "trim_end_sample_exclusive": r.trim_end_sample_exclusive,
             "adopted_candidate_id": r.adopted_candidate_id,
             "adoption_id": r.adoption_id,
             "adopted_by": r.adopted_by,
             "adopted_at": r.adopted_at} for r in rows]


async def get_current_selection(session: AsyncSession, *,
                                dialogue_line_revision_id: str) -> dict:
    await get_dialogue_line_revision(
        session, revision_id=dialogue_line_revision_id)
    row = await session.get(VocalPerformanceSelection,
                            dialogue_line_revision_id)
    if row is None:
        # every revision is created with its UNSET row atomically; a
        # missing row is corruption, not a lawful state
        raise SoloRingError(ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                            "selection row missing for revision",
                            status_code=500)
    return _selection_view(row)


def _selection_view(row: VocalPerformanceSelection) -> dict:
    if row.selected_vocal_performance_revision_id is None:
        return {"dialogue_line_revision_id":
                row.dialogue_line_revision_id,
                "state": "UNSET",
                "selected_vocal_performance_revision_id": None}
    return {"dialogue_line_revision_id": row.dialogue_line_revision_id,
            "state": "SELECTED",
            "selected_vocal_performance_revision_id":
            row.selected_vocal_performance_revision_id,
            "selected_by": row.selected_by,
            "selected_at": row.selected_at}


async def set_current_selection(session: AsyncSession, *,
                                dialogue_line_revision_id: str,
                                vocal_performance_revision_id: str | None,
                                selected_by: str) -> dict:
    await get_dialogue_line_revision(
        session, revision_id=dialogue_line_revision_id)
    if not isinstance(selected_by, str) or not selected_by.strip():
        raise validation_error("selected_by must be nonempty")
    row = await session.get(VocalPerformanceSelection,
                            dialogue_line_revision_id)
    if row is None:
        raise SoloRingError(ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                            "selection row missing for revision",
                            status_code=500)
    if vocal_performance_revision_id is None:
        row.selected_vocal_performance_revision_id = None
        row.selected_by = None
        row.selected_at = None
        row.updated_at = await db_now(session)
        await session.flush()
        return _selection_view(row)
    vp = await get_vocal_performance_revision(
        session, revision_id=vocal_performance_revision_id)
    if vp.dialogue_line_revision_id != dialogue_line_revision_id:
        raise SoloRingError(
            ErrorCode.VOCAL_SELECTION_LINE_MISMATCH,
            "selected VocalPerformanceRevision binds a different "
            "DialogueLineRevision", status_code=409)
    row.selected_vocal_performance_revision_id = vp.id
    row.selected_by = selected_by.strip()
    row.selected_at = await db_now(session)
    row.updated_at = await db_now(session)
    await session.flush()
    return _selection_view(row)
