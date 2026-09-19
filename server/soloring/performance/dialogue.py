"""DialogueLine / DialogueLineRevision services (frozen R5 §4.1-4.2,
§9.1). Append-only semantic authority; no update/delete surface; no
implicit current/latest revision; canonical spec JSON v1 hashing.
"""

from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.domain.now import db_now
from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.domain.ids import new_uuid
from soloring.errors import ErrorCode, SoloRingError, not_found, validation_error
from soloring.performance.models import (DialogueLine,
                                         DialogueLineRevision,
                                         VocalPerformanceSelection)

_LANGUAGE_RE = re.compile(r"^[a-z]{2,8}(-[a-z0-9]{1,8})*$")
_MAX_WORDING = 20000


def _validate_language(language: str) -> str:
    tag = language.strip().lower()
    if not tag or len(tag) > 64 or not _LANGUAGE_RE.match(tag):
        raise validation_error(
            f"INVALID_LANGUAGE_TAG: {language!r}",
            details={"grammar": "primary 2-8 letters, optional "
                                "'-' + 1-8 letters/digits, <= 64 chars"})
    return tag


def _validate_wording(wording: str) -> str:
    if not isinstance(wording, str):
        raise validation_error("INVALID_DIALOGUE_WORDING: not a string")
    w = wording.strip()
    if not w or len(w) > _MAX_WORDING:
        raise validation_error(
            "INVALID_DIALOGUE_WORDING: empty or over 20000 characters")
    return w


async def create_dialogue_line(session: AsyncSession, *,
                               project_id: str) -> DialogueLine:
    from soloring.domain.models import Project
    project = await session.get(Project, project_id)
    if project is None:
        raise not_found(ErrorCode.PROJECT_NOT_FOUND,
                        f"project {project_id!r} not found")
    line = DialogueLine(id=new_uuid(), project_id=project_id,
                        created_at=await db_now(session))
    session.add(line)
    await session.flush()
    return line


async def list_dialogue_lines(session: AsyncSession, *, project_id: str,
                              cursor: tuple | None = None,
                              limit: int = 50) -> dict:
    limit = max(1, min(200, limit))
    stmt = select(DialogueLine).where(
        DialogueLine.project_id == project_id)
    if cursor is not None:
        stmt = stmt.where(
            (DialogueLine.created_at, DialogueLine.id) > cursor)
    stmt = stmt.order_by(DialogueLine.created_at,
                         DialogueLine.id).limit(limit + 1)
    rows = (await session.execute(stmt)).scalars().fetchall()
    more = len(rows) > limit
    rows = rows[:limit]
    return {"lines": [
        {"id": r.id, "project_id": r.project_id, "created_at": r.created_at}
        for r in rows],
        "next_cursor": (rows[-1].created_at, rows[-1].id)
        if rows and more else None}


async def get_dialogue_line(session: AsyncSession, *,
                            line_id: str) -> DialogueLine:
    line = await session.get(DialogueLine, line_id)
    if line is None:
        raise not_found(ErrorCode.DIALOGUE_LINE_NOT_FOUND,
                        f"dialogue line {line_id!r} not found")
    return line


def _spec_v1(speaker_subject_id: str, wording: str,
             language: str) -> dict:
    return {"schema_version": 1,
            "speaker_subject_id": speaker_subject_id,
            "wording": wording,
            "language": language}


async def create_dialogue_line_revision(
        session: AsyncSession, *, dialogue_line_id: str,
        speaker_subject_id: str, wording: str,
        language: str) -> DialogueLineRevision:
    from soloring.continuity.models import CreativeEntity
    line = await get_dialogue_line(session, line_id=dialogue_line_id)
    entity = await session.get(CreativeEntity, speaker_subject_id)
    if entity is None:
        raise not_found(ErrorCode.SPEAKER_NOT_FOUND,
                        f"speaker entity {speaker_subject_id!r} not found")
    if entity.project_id != line.project_id:
        raise SoloRingError(
            ErrorCode.SPEAKER_PROJECT_MISMATCH,
            "speaker entity belongs to another project",
            status_code=422)
    w = _validate_wording(wording)
    lang = _validate_language(language)
    spec = _spec_v1(speaker_subject_id, w, lang)
    spec_json = canonical_json_str(spec)
    spec_hash = canonical_hash(spec)
    existing = (await session.execute(
        select(DialogueLineRevision).where(
            DialogueLineRevision.dialogue_line_id == line.id,
            DialogueLineRevision.spec_hash == spec_hash)
    )).scalar_one_or_none()
    if existing is not None:
        return existing
    (n,) = (await session.execute(
        select(func.max(DialogueLineRevision.revision_number)).where(
            DialogueLineRevision.dialogue_line_id == line.id))
    ).one()
    rev = DialogueLineRevision(
        id=new_uuid(), dialogue_line_id=line.id,
        revision_number=(n or 0) + 1,
        speaker_subject_id=speaker_subject_id,
        language=lang, wording=w, schema_version=1,
        spec_json=spec_json, spec_hash=spec_hash,
        created_at=await db_now(session))
    session.add(rev)
    # explicit UNSET current-selection row, atomically with the revision
    session.add(VocalPerformanceSelection(
        dialogue_line_revision_id=rev.id,
        selected_vocal_performance_revision_id=None,
        selected_by=None, selected_at=None, updated_at=await db_now(session)))
    await session.flush()
    return rev


async def get_dialogue_line_revision(
        session: AsyncSession, *, revision_id: str
) -> DialogueLineRevision:
    rev = await session.get(DialogueLineRevision, revision_id)
    if rev is None:
        raise not_found(ErrorCode.DIALOGUE_LINE_REVISION_NOT_FOUND,
                        f"dialogue line revision {revision_id!r} not found")
    return rev


async def list_dialogue_line_revisions(
        session: AsyncSession, *, dialogue_line_id: str) -> list[dict]:
    await get_dialogue_line(session, line_id=dialogue_line_id)
    rows = (await session.execute(
        select(DialogueLineRevision).where(
            DialogueLineRevision.dialogue_line_id == dialogue_line_id)
        .order_by(DialogueLineRevision.revision_number))).scalars().all()
    return [{"id": r.id, "revision_number": r.revision_number,
             "speaker_subject_id": r.speaker_subject_id,
             "language": r.language, "wording": r.wording,
             "spec_hash": r.spec_hash, "created_at": r.created_at}
            for r in rows]
