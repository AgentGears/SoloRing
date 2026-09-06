"""Composition HTTP routes (frozen M12 R3 §14).

Pagination is cursor-based over stable keys; scope is mandatory on all
occurrence mutations; 409 COMPOSITION_EDIT_CONFLICT is a decision point,
never a blind retry signal.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.api.deps import get_session
from soloring.api.schemas.compositions import (
    ApplyRequest,
    ApplyResult,
    CompositionCreate,
    CompositionDetail,
    CompositionPatch,
    CompositionRead,
    IdentityOperationRequest,
    MintResult,
    OccurrenceMint,
    OccurrencePatch,
    OccurrenceRead,
    PatchResult,
    PreviewResult,
    PublishRequest,
    ReadinessResult,
    RevisionDetail,
    RevisionSummary,
)
from soloring.composition import service as comp
from soloring.composition.impacts import (
    apply_identity_operation,
    preview_identity_operation,
    verify_identity_history,
)
from soloring.composition.readiness import (
    load_composition_revision_detail,
    publish_composition_revision,
    resolve_publication_readiness,
)

router = APIRouter(tags=["compositions"])

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


def _cursor_clause(cursor: str | None, order_key: str) -> str:
    if not cursor:
        return ""
    return f" AND {order_key} > :cursor "


@router.post(
    "/projects/{project_id}/compositions",
    response_model=CompositionDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_composition(
    project_id: str,
    body: CompositionCreate,
    session: AsyncSession = Depends(get_session),
) -> CompositionDetail:
    return CompositionDetail(
        **await comp.create_composition(
            session, project_id, name=body.name, description=body.description)
    )


@router.get(
    "/projects/{project_id}/compositions",
    response_model=list[CompositionRead],
)
async def list_compositions(
    project_id: str,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=DEFAULT_LIMIT, le=MAX_LIMIT),
    session: AsyncSession = Depends(get_session),
) -> list[CompositionRead]:
    async with session.bind.connect() as conn:
        await comp._require_active_project(conn, project_id)
        sql = (
            "SELECT id, project_id, name, description, metadata_version, "
            "working_version, created_at, updated_at FROM compositions "
            "WHERE project_id = :pid"
        )
        params: dict = {"pid": project_id, "lim": limit}
        if cursor:
            sql += " AND (created_at, id) > (:c_created, :c_id)"
            created, ident = cursor.split("|", 1)
            params.update({"c_created": created, "c_id": ident})
        sql += " ORDER BY created_at, id LIMIT :lim"
        rows = (await conn.execute(text(sql), params)).all()
    return [CompositionRead(**dict(r._mapping)) for r in rows]


@router.get(
    "/compositions/{composition_id}", response_model=CompositionDetail
)
async def get_composition(
    composition_id: str, session: AsyncSession = Depends(get_session)
) -> CompositionDetail:
    return CompositionDetail(
        **await comp.get_composition(session, composition_id))


@router.patch(
    "/compositions/{composition_id}", response_model=CompositionDetail
)
async def patch_composition(
    composition_id: str,
    body: CompositionPatch,
    session: AsyncSession = Depends(get_session),
) -> CompositionDetail:
    return CompositionDetail(**await comp.patch_composition_metadata(
        session, composition_id,
        expected_metadata_version=body.expected_metadata_version,
        name=body.name, description=body.description))


@router.get(
    "/compositions/{composition_id}/occurrences",
    response_model=list[OccurrenceRead],
)
async def list_occurrences(
    composition_id: str,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=DEFAULT_LIMIT, le=MAX_LIMIT),
    session: AsyncSession = Depends(get_session),
) -> list[OccurrenceRead]:
    async with session.bind.connect() as conn:
        await comp._require_composition(conn, composition_id)
        sql = ("SELECT * FROM composition_working_occurrences WHERE "
               "composition_id = :cid")
        params: dict = {"cid": composition_id, "lim": limit}
        if cursor:
            sql += " AND occurrence_id > :cur"
            params["cur"] = cursor
        sql += " ORDER BY occurrence_id LIMIT :lim"
        rows = (await conn.execute(text(sql), params)).all()
    return [OccurrenceRead(**dict(r._mapping)) for r in rows]


@router.post(
    "/compositions/{composition_id}/occurrences",
    response_model=MintResult,
    status_code=status.HTTP_201_CREATED,
)
async def mint_occurrence(
    composition_id: str,
    body: OccurrenceMint,
    session: AsyncSession = Depends(get_session),
) -> MintResult:
    spec = {
        "display_name": body.display_name,
        "source": {"kind": body.source.kind,
                   "revision_id": body.source.revision_id},
        "visible": body.visible,
        "transform": {"translation_mm": body.transform.translation_mm,
                      "rotation_udeg": body.transform.rotation_udeg},
    }
    out = await comp.mint_occurrence(
        session, composition_id, scope=body.scope,
        expected_working_version=body.expected_working_version, spec=spec)
    return MintResult(occurrence_id=out["occurrence_id"],
                      working_version=out["working_version"])


@router.patch(
    "/compositions/{composition_id}/occurrences/{occurrence_id}",
    response_model=PatchResult,
)
async def patch_occurrence(
    composition_id: str,
    occurrence_id: str,
    body: OccurrencePatch,
    session: AsyncSession = Depends(get_session),
) -> PatchResult:
    out = await comp.patch_working_occurrence(
        session, composition_id, occurrence_id, scope=body.scope,
        expected_working_version=body.expected_working_version,
        display_name=body.display_name, visible=body.visible,
        transform=(None if body.transform is None else {
            "translation_mm": body.transform.translation_mm,
            "rotation_udeg": body.transform.rotation_udeg}),
        source=(None if body.source is None else {
            "kind": body.source.kind, "revision_id": body.source.revision_id}),
    )
    return PatchResult(**out)


@router.post(
    "/compositions/{composition_id}/identity-operations/preview",
    response_model=PreviewResult,
)
async def preview_operation(
    composition_id: str,
    body: IdentityOperationRequest,
    session: AsyncSession = Depends(get_session),
) -> PreviewResult:
    return PreviewResult(**await preview_identity_operation(
        session, composition_id,
        request=body.model_dump()))


@router.post(
    "/compositions/{composition_id}/identity-operations",
    response_model=ApplyResult,
)
async def apply_operation(
    composition_id: str,
    body: ApplyRequest,
    session: AsyncSession = Depends(get_session),
) -> ApplyResult:
    out = await apply_identity_operation(
        session, composition_id, scope=body.scope,
        expected_working_version=body.expected_working_version,
        expected_request_fingerprint=body.expected_request_fingerprint,
        expected_impact_fingerprint=body.expected_impact_fingerprint,
        request=body.request.model_dump())
    return ApplyResult(**out)


@router.get(
    "/compositions/{composition_id}/identity-history",
    response_model=list[dict],
)
async def identity_history(
    composition_id: str,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=DEFAULT_LIMIT, le=MAX_LIMIT),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    history = await verify_identity_history(session, composition_id)
    if cursor:
        history = [h for h in history if h["operation_id"] > cursor]
    return history[:limit]


@router.get(
    "/compositions/{composition_id}/publication-readiness",
    response_model=ReadinessResult,
)
async def publication_readiness(
    composition_id: str, session: AsyncSession = Depends(get_session)
) -> ReadinessResult:
    r = await resolve_publication_readiness(session, composition_id)
    return ReadinessResult(**r)


@router.post("/compositions/{composition_id}/publish")
async def publish(
    composition_id: str,
    body: PublishRequest,
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    detail, created = await publish_composition_revision(
        session, composition_id,
        expected_working_version=body.expected_working_version)
    payload = {"created": created, "revision": detail}
    return JSONResponse(
        payload,
        status_code=status.HTTP_201_CREATED if created
        else status.HTTP_200_OK,
    )


@router.get(
    "/compositions/{composition_id}/revisions",
    response_model=list[RevisionSummary],
)
async def list_revisions(
    composition_id: str,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=DEFAULT_LIMIT, le=MAX_LIMIT),
    session: AsyncSession = Depends(get_session),
) -> list[RevisionSummary]:
    async with session.bind.connect() as conn:
        await comp._require_composition(conn, composition_id)
        sql = ("SELECT id, revision_number, snapshot_hash, created_at FROM "
               "composition_revisions WHERE composition_id = :cid")
        params: dict = {"cid": composition_id, "lim": limit}
        if cursor:
            sql += " AND revision_number > :cur"
            params["cur"] = int(cursor)
        sql += " ORDER BY revision_number LIMIT :lim"
        rows = (await conn.execute(text(sql), params)).all()
    return [
        RevisionSummary(revision_id=r.id, revision_number=r.revision_number,
                        snapshot_hash=r.snapshot_hash, created_at=r.created_at)
        for r in rows
    ]


@router.get(
    "/composition-revisions/{revision_id}", response_model=RevisionDetail
)
async def revision_detail(
    revision_id: str, session: AsyncSession = Depends(get_session)
) -> RevisionDetail:
    return RevisionDetail(
        **await load_composition_revision_detail(session, revision_id))
