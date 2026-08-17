"""Reference HTTP routes (plan §11, §45)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.api.deps import get_session
from soloring.api.schemas.references import ReferenceRead, ReferenceSet
from soloring.domain import references

router = APIRouter(tags=["references"])


@router.get(
    "/shots/{shot_id}/references",
    response_model=list[ReferenceRead],
)
async def get_references(
    shot_id: str, session: AsyncSession = Depends(get_session)
) -> list[ReferenceRead]:
    """The persisted reference set in canonical server order (M2C).

    Deliberate v0.1 §99 amendment: M1 exposed only the PUT; reading the
    current set is required for reference editing and refresh-safe UI.
    """
    return await references.list_references(session, shot_id)


@router.put(
    "/shots/{shot_id}/references",
    response_model=list[ReferenceRead],
)
async def put_references(
    shot_id: str,
    payload: ReferenceSet,
    session: AsyncSession = Depends(get_session),
) -> list[ReferenceRead]:
    return await references.replace_references(session, shot_id, payload.references)
