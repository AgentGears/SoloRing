"""DialogueAlignment retained derived evidence (frozen R5 §4.7/§7,
§9.6). Evidence INPUT, never authority: exact analyzer + derivation-
run provenance; no-dedupe identity (every ingestion is a distinct
immutable artifact); canonical alignment schema v1 over the exact
source sample coordinate, bounded by the VP authoritative trim.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.domain.now import db_now
from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.domain.ids import new_uuid
from soloring.errors import ErrorCode, SoloRingError, not_found, validation_error
from soloring.performance.models import DialogueAlignment
from soloring.performance.vocal import (_blob_relative_path,
                                        get_vocal_performance_revision)

_TS_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
_LABEL_MAX = 256
_ARRAYS = ("words", "phonemes", "viseme_classes")


def _validate_alignment_document(doc: dict, *, trim_start: int,
                                 trim_end_exclusive: int) -> None:
    if not isinstance(doc, dict) or doc.get("schema_version") != 1:
        raise SoloRingError(ErrorCode.ALIGNMENT_INVALID,
                            "alignment document must be schema_version 1",
                            status_code=422)
    entries = []
    for arr in _ARRAYS:
        values = doc.get(arr, [])
        if not isinstance(values, list):
            raise SoloRingError(ErrorCode.ALIGNMENT_INVALID,
                                f"{arr} must be an array",
                                status_code=422)
        for e in values:
            if not isinstance(e, dict):
                raise SoloRingError(ErrorCode.ALIGNMENT_INVALID,
                                    f"{arr} entries must be objects",
                                    status_code=422)
            s, t, label = (e.get("start_sample"),
                           e.get("end_sample_exclusive"),
                           e.get("label"))
            if not isinstance(s, int) or not isinstance(t, int) \
                    or not isinstance(label, str):
                raise SoloRingError(
                    ErrorCode.ALIGNMENT_INVALID,
                    f"{arr} entry requires integer samples and a "
                    "string label", status_code=422)
            if not (trim_start <= s < t <= trim_end_exclusive):
                raise SoloRingError(
                    ErrorCode.ALIGNMENT_INVALID,
                    f"{arr} interval [{s}, {t}) outside the VP "
                    f"authoritative trim [{trim_start}, "
                    f"{trim_end_exclusive})", status_code=422)
            if not label.strip() or len(label) > _LABEL_MAX:
                raise SoloRingError(
                    ErrorCode.ALIGNMENT_INVALID,
                    f"{arr} label must be nonempty <= "
                    f"{_LABEL_MAX} code points", status_code=422)
            entries.append((arr, s, t, label))
    seen = set()
    for _, s, t, label in sorted(entries, key=lambda x: (x[1], x[2],
                                                         x[3])):
        key = (s, t, label)
        if key in seen:
            raise SoloRingError(ErrorCode.ALIGNMENT_INVALID,
                                f"duplicate canonicalized entry "
                                f"{key}", status_code=422)
        seen.add(key)


def _validate_run_provenance(run: dict) -> None:
    if not isinstance(run, dict) or run.get("schema_version") != 1:
        raise SoloRingError(
            ErrorCode.ALIGNMENT_PROVENANCE_INCOMPLETE,
            "derivation run must be schema_version 1",
            status_code=422)
    ts = run.get("run_timestamp_utc")
    if not isinstance(ts, str) or not _TS_RE.match(ts):
        raise SoloRingError(
            ErrorCode.ALIGNMENT_PROVENANCE_INCOMPLETE,
            "run_timestamp_utc must be "
            "YYYY-MM-DDTHH:MM:SS.ffffffZ", status_code=422)
    host = run.get("host_context")
    if not isinstance(host, str) or not host.strip() \
            or len(host) > 1024:
        raise SoloRingError(
            ErrorCode.ALIGNMENT_PROVENANCE_INCOMPLETE,
            "host_context must be trimmed nonempty UTF-8 <= 1024 "
            "code points", status_code=422)
    digest = run.get("input_digest")
    if not isinstance(digest, dict) \
            or not isinstance(
                digest.get("vocal_performance_revision_id"), str) \
            or not isinstance(
                digest.get("retained_audio_blob_sha256"), str) \
            or not re.fullmatch(r"[0-9a-f]{64}",
                                digest["retained_audio_blob_sha256"]):
        raise SoloRingError(
            ErrorCode.ALIGNMENT_PROVENANCE_INCOMPLETE,
            "input_digest requires the VP id and the 64-hex retained "
            "audio blob SHA-256", status_code=422)


async def put_dialogue_alignment(
        session: AsyncSession, settings, *,
        vocal_performance_revision_id: str,
        analyzer_id: str, analyzer_version: str,
        model_identity: str, runtime_identity: str,
        parameters_sha256: str,
        alignment_document: dict,
        derivation_run: dict) -> DialogueAlignment:
    vp = await get_vocal_performance_revision(
        session, revision_id=vocal_performance_revision_id)
    for name, v in (("analyzer_id", analyzer_id),
                    ("analyzer_version", analyzer_version),
                    ("model_identity", model_identity),
                    ("runtime_identity", runtime_identity)):
        if not isinstance(v, str) or not v.strip():
            raise SoloRingError(
                ErrorCode.ALIGNMENT_PROVENANCE_INCOMPLETE,
                f"{name} must be nonempty", status_code=422)
    if not isinstance(parameters_sha256, str) \
            or not re.fullmatch(r"[0-9a-f]{64}", parameters_sha256):
        raise SoloRingError(
            ErrorCode.ALIGNMENT_PROVENANCE_INCOMPLETE,
            "parameters_sha256 must be 64 lowercase hex",
            status_code=422)
    _validate_run_provenance(derivation_run)
    if derivation_run["input_digest"][
            "vocal_performance_revision_id"] != vp.id:
        raise SoloRingError(
            ErrorCode.ALIGNMENT_SOURCE_MISMATCH,
            "derivation run input digest names a different VP",
            status_code=422)
    if derivation_run["input_digest"][
            "retained_audio_blob_sha256"] != \
            vp.retained_audio_blob_hash:
        raise SoloRingError(
            ErrorCode.ALIGNMENT_SOURCE_MISMATCH,
            "derivation run audio digest != VP retained audio blob",
            status_code=422)
    _validate_alignment_document(
        alignment_document, trim_start=vp.trim_start_sample,
        trim_end_exclusive=vp.trim_end_sample_exclusive)
    canonical = {k: alignment_document.get(k, [])
                 for k in ("schema_version",) + _ARRAYS}
    canonical = {"schema_version": 1}
    for arr in _ARRAYS:
        vals = alignment_document.get(arr, [])
        canonical[arr] = [
            {"start_sample": e["start_sample"],
             "end_sample_exclusive": e["end_sample_exclusive"],
             "label": e["label"]} for e in vals]
        canonical[arr].sort(key=lambda e: (e["start_sample"],
                                          e["end_sample_exclusive"],
                                          e["label"]))
    body = canonical_json_str(canonical).encode("utf-8")
    retained_sha = hashlib.sha256(body).hexdigest()
    # place retained canonical bytes through the content-addressed
    # Blob layout (fixture-independent evidence storage)
    rel = _blob_relative_path(retained_sha)
    target = settings.blob_dir / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.is_file():
        target.write_bytes(body)
    from soloring.assets.models import Blob
    if await session.get(Blob, retained_sha) is None:
        session.add(Blob(hash=retained_sha, path=rel.as_posix(),
                         size_bytes=len(body),
                         detected_media_type="application/json",
                         created_at=await db_now(session)))
    run_json = canonical_json_str(derivation_run)
    run_hash = canonical_hash(derivation_run)
    row = DialogueAlignment(
        id=new_uuid(), vocal_performance_revision_id=vp.id,
        analyzer_id=analyzer_id.strip(),
        analyzer_version=analyzer_version.strip(),
        model_identity=model_identity.strip(),
        runtime_identity=runtime_identity.strip(),
        parameters_sha256=parameters_sha256,
        alignment_schema_version=1,
        retained_blob_hash=retained_sha, retained_sha256=retained_sha,
        derivation_run_json=run_json,
        derivation_run_hash=run_hash,
        created_at=await db_now(session))
    session.add(row)
    await session.flush()
    return row


async def list_dialogue_alignments(session: AsyncSession, *,
                                   vocal_performance_revision_id: str
                                   ) -> list[dict]:
    await get_vocal_performance_revision(
        session, revision_id=vocal_performance_revision_id)
    rows = (await session.execute(
        select(DialogueAlignment).where(
            DialogueAlignment.vocal_performance_revision_id ==
            vocal_performance_revision_id)
        .order_by(DialogueAlignment.created_at,
                  DialogueAlignment.id))).scalars().all()
    return [{"id": r.id,
             "vocal_performance_revision_id":
             r.vocal_performance_revision_id,
             "analyzer_id": r.analyzer_id,
             "analyzer_version": r.analyzer_version,
             "model_identity": r.model_identity,
             "runtime_identity": r.runtime_identity,
             "parameters_sha256": r.parameters_sha256,
             "retained_sha256": r.retained_sha256,
             "derivation_run_hash": r.derivation_run_hash,
             "created_at": r.created_at} for r in rows]
