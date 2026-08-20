"""M8 VisualFacet/VisualAnchor endpoints (frozen plan §67)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.api.deps import get_session
from soloring.api.schemas.visual import (
    ValuePolicyPut,
    ValuePolicyRead,
    VisualAnchorCreate,
    VisualAnchorRead,
    VisualFacetCreate,
    VisualFacetPatch,
    VisualFacetRead,
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


@router.get("/visual-anchors/{anchor_id}", response_model=VisualAnchorRead)
async def get_visual_anchor(
    anchor_id: str, session: AsyncSession = Depends(get_session)
) -> VisualAnchorRead:
    from soloring.visual import facets as facet_svc

    return VisualAnchorRead(**await facet_svc.get_anchor(session, anchor_id))


@router.delete(
    "/visual-anchors/{anchor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_visual_anchor(
    anchor_id: str, session: AsyncSession = Depends(get_session)
) -> None:
    from soloring.visual import facets as facet_svc

    await facet_svc.delete_anchor(session, anchor_id)
