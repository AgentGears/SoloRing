"""M8 VisualFacet/VisualAnchor endpoints (frozen plan §67)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.api.deps import get_session
from soloring.api.schemas.visual import (
    ApproveRequest,
    UnapproveRequest,
    ValuePolicyPut,
    ValuePolicyRead,
    VisualAnchorCreate,
    VisualAnchorDetail,
    VisualAnchorRead,
    VisualAnchorRevisionRead,
    VisualAnchorRevisionSummary,
    VisualFacetCreate,
    VisualFacetPatch,
    VisualFacetRead,
    WorkingSetPut,
)

router = APIRouter(tags=["visual"])


# --- VisualFacets ---------------------------------------------------------------


@router.get(
    "/projects/{project_id}/visual-facets",
    response_model=list[VisualFacetRead],
)
async def list_visual_facets(
    project_id: str, session: AsyncSession = Depends(get_session)
) -> list[VisualFacetRead]:
    from soloring.visual import facets as facet_svc

    return [
        VisualFacetRead(**r)
        for r in await facet_svc.list_facets(session, project_id)
    ]


@router.post(
    "/projects/{project_id}/visual-facets",
    response_model=VisualFacetRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_visual_facet(
    project_id: str,
    payload: VisualFacetCreate,
    session: AsyncSession = Depends(get_session),
) -> VisualFacetRead:
    from soloring.visual import facets as facet_svc

    fid = await facet_svc.create_facet(session, project_id, payload)
    return VisualFacetRead(**await facet_svc.get_facet(session, fid))


@router.get("/visual-facets/{facet_id}", response_model=VisualFacetRead)
async def get_visual_facet(
    facet_id: str, session: AsyncSession = Depends(get_session)
) -> VisualFacetRead:
    from soloring.visual import facets as facet_svc

    return VisualFacetRead(**await facet_svc.get_facet(session, facet_id))


@router.patch("/visual-facets/{facet_id}", response_model=VisualFacetRead)
async def patch_visual_facet(
    facet_id: str,
    payload: VisualFacetPatch,
    session: AsyncSession = Depends(get_session),
) -> VisualFacetRead:
    from soloring.visual import facets as facet_svc

    await facet_svc.patch_facet(session, facet_id, payload)
    return VisualFacetRead(**await facet_svc.get_facet(session, facet_id))


@router.delete(
    "/visual-facets/{facet_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_visual_facet(
    facet_id: str, session: AsyncSession = Depends(get_session)
) -> None:
    from soloring.visual import facets as facet_svc

    await facet_svc.delete_facet(session, facet_id)


# --- Feature-value policies (§16) ------------------------------------------------


@router.get(
    "/visual-facets/{facet_id}/value-policies",
    response_model=list[ValuePolicyRead],
)
async def list_value_policies(
    facet_id: str, session: AsyncSession = Depends(get_session)
) -> list[ValuePolicyRead]:
    from soloring.visual import facets as facet_svc

    return [
        ValuePolicyRead(**r)
        for r in await facet_svc.list_value_policies(session, facet_id)
    ]


@router.put(
    "/visual-facets/{facet_id}/value-policies",
    response_model=list[ValuePolicyRead],
)
async def put_value_policies(
    facet_id: str,
    payload: ValuePolicyPut,
    session: AsyncSession = Depends(get_session),
) -> list[ValuePolicyRead]:
    from soloring.visual import facets as facet_svc

    return [
        ValuePolicyRead(**r)
        for r in await facet_svc.put_value_policies(
            session, facet_id, payload
        )
    ]


# --- State-specific VisualAnchors (§17) ------------------------------------------


@router.get(
    "/visual-facets/{facet_id}/anchors",
    response_model=list[VisualAnchorRead],
)
async def list_visual_anchors(
    facet_id: str, session: AsyncSession = Depends(get_session)
) -> list[VisualAnchorRead]:
    from soloring.visual import facets as facet_svc

    return [
        VisualAnchorRead(**r)
        for r in await facet_svc.list_anchors(session, facet_id)
    ]


@router.post(
    "/visual-facets/{facet_id}/anchors",
    response_model=VisualAnchorRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_visual_anchor(
    facet_id: str,
    payload: VisualAnchorCreate,
    session: AsyncSession = Depends(get_session),
) -> VisualAnchorRead:
    from soloring.visual import facets as facet_svc

    aid = await facet_svc.create_anchor(session, facet_id, payload)
    return VisualAnchorRead(**await facet_svc.get_anchor(session, aid))


@router.get(
    "/visual-anchors/{anchor_id}", response_model=VisualAnchorDetail
)
async def get_visual_anchor(
    anchor_id: str, session: AsyncSession = Depends(get_session)
) -> VisualAnchorDetail:
    from soloring.visual import anchors as anchor_svc
    from soloring.visual import facets as facet_svc

    detail = await anchor_svc.get_anchor_detail(session, anchor_id)
    base = await facet_svc.get_anchor(session, anchor_id)
    detail["created_at"] = base["created_at"]
    detail["updated_at"] = base["updated_at"]
    return VisualAnchorDetail(**detail)


@router.put(
    "/visual-anchors/{anchor_id}/items", response_model=VisualAnchorDetail
)
async def put_visual_anchor_items(
    anchor_id: str,
    payload: WorkingSetPut,
    session: AsyncSession = Depends(get_session),
) -> VisualAnchorDetail:
    from soloring.visual import anchors as anchor_svc

    await anchor_svc.put_working_set(session, anchor_id, payload)
    return await get_visual_anchor(anchor_id, session)


@router.get(
    "/visual-anchors/{anchor_id}/revisions",
    response_model=list[VisualAnchorRevisionSummary],
)
async def list_visual_anchor_revisions(
    anchor_id: str, session: AsyncSession = Depends(get_session)
) -> list[VisualAnchorRevisionSummary]:
    from soloring.visual import anchors as anchor_svc

    return [
        VisualAnchorRevisionSummary(**r)
        for r in await anchor_svc.list_revisions(session, anchor_id)
    ]


@router.post(
    "/visual-anchors/{anchor_id}/revisions",
    response_model=VisualAnchorRevisionSummary,
    status_code=status.HTTP_201_CREATED,
)
async def capture_visual_anchor_revision(
    anchor_id: str, session: AsyncSession = Depends(get_session)
) -> VisualAnchorRevisionSummary:
    from soloring.visual import anchors as anchor_svc

    rid = await anchor_svc.capture_revision(session, anchor_id)
    row = await anchor_svc.get_revision(session, rid)
    return VisualAnchorRevisionSummary(
        id=row["id"],
        visual_anchor_id=row["visual_anchor_id"],
        revision_number=row["revision_number"],
        snapshot_hash=row["snapshot_hash"],
        created_at=row["created_at"],
    )


@router.get(
    "/visual-anchor-revisions/{revision_id}",
    response_model=VisualAnchorRevisionRead,
)
async def get_visual_anchor_revision(
    revision_id: str, session: AsyncSession = Depends(get_session)
) -> VisualAnchorRevisionRead:
    from soloring.visual import anchors as anchor_svc

    return VisualAnchorRevisionRead(
        **await anchor_svc.get_revision(session, revision_id)
    )


@router.post(
    "/visual-anchor-revisions/{revision_id}/approve",
    status_code=status.HTTP_200_OK,
)
async def approve_visual_anchor_revision(
    revision_id: str,
    payload: ApproveRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    from soloring.visual import anchors as anchor_svc

    await anchor_svc.approve_revision(
        session, revision_id, payload.expected_approved_revision_id
    )
    return {"approved": revision_id}


@router.post(
    "/visual-anchors/{anchor_id}/unapprove",
    status_code=status.HTTP_200_OK,
)
async def unapprove_visual_anchor(
    anchor_id: str,
    payload: UnapproveRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    from soloring.visual import anchors as anchor_svc

    await anchor_svc.unapprove_anchor(
        session, anchor_id, payload.expected_approved_revision_id
    )
    return {"unapproved": anchor_id}


@router.delete(
    "/visual-anchors/{anchor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_visual_anchor(
    anchor_id: str, session: AsyncSession = Depends(get_session)
) -> None:
    from soloring.visual import facets as facet_svc

    await facet_svc.delete_anchor(session, anchor_id)
