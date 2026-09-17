"""M16-A authoritative intra-Shot event authoring routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.api.deps import get_session
from soloring.api.schemas.intra_shot import (
    IntraShotEventCreate,
    IntraShotEventPatch,
    IntraShotEventRead,
    IntraShotRead,
    ProposalCreate,
    ProposalReviewBatch,
    ProposalReviewDecision,
)
from soloring.continuity import (
    intra_shot_adoption,
    intra_shot_resolver,
    intra_shot_service,
)

router = APIRouter(tags=["intra-shot"])


@router.get(
    "/shots/{shot_id}/intra-shot",
    response_model=IntraShotRead,
)
async def read_intra_shot(
    shot_id: str,
    limit: int = 100,
    cursor: int = 0,
    session: AsyncSession = Depends(get_session),
) -> IntraShotRead:
    if type(cursor) is not int or cursor < 0:
        from soloring.errors import validation_error

        raise validation_error("cursor must be a nonnegative integer")
    if type(limit) is not int or not 1 <= limit <= 500:
        from soloring.errors import validation_error

        raise validation_error("limit must be between 1 and 500")
    projection = await intra_shot_resolver.resolve_intra_shot_read(
        session, shot_id)
    events = projection["events"][cursor:cursor + limit + 1]
    more = len(events) > limit
    projection["events"] = events[:limit]
    projection["next_cursor"] = cursor + limit if more else None
    return IntraShotRead(**{
        **projection, "shot_id": shot_id})


@router.post(
    "/shots/{shot_id}/intra-shot/proposals",
    status_code=status.HTTP_201_CREATED,
)
async def create_intra_shot_proposal(
    shot_id: str,
    payload: ProposalCreate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await intra_shot_adoption.ingest_proposal(
        session, shot_id, payload)


@router.get("/shots/{shot_id}/intra-shot/proposals")
async def list_intra_shot_proposals(
    shot_id: str,
    limit: int = 100,
    cursor: int = 0,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await intra_shot_adoption.list_proposals(
        session, shot_id, cursor=cursor, limit=limit)


@router.post(
    "/intra-shot/events/{event_id}/persistence/adopt",
)
async def adopt_intra_shot_persistence(
    event_id: str,
    payload: ProposalReviewDecision,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = payload.model_dump(exclude_unset=True) if hasattr(
        payload, "model_dump") else dict(payload)
    return await intra_shot_adoption.adopt_event_persistence(
        session, event_id,
        expected_event_hash=body["expected_event_hash"],
        expected_event_set_hash=body["expected_event_set_hash"])


@router.post(
    "/intra-shot/events/{event_id}/persistence/decline",
)
async def decline_intra_shot_persistence(
    event_id: str,
    payload: ProposalReviewDecision,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = payload.model_dump(exclude_unset=True) if hasattr(
        payload, "model_dump") else dict(payload)
    return await intra_shot_adoption.decline_event_persistence(
        session, event_id,
        expected_event_hash=body["expected_event_hash"],
        expected_event_set_hash=body["expected_event_set_hash"])


@router.post(
    "/intra-shot/proposals/{proposal_id}/review",
)
async def review_intra_shot_proposal(
    proposal_id: str,
    payload: ProposalReviewDecision,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = payload.model_dump(exclude_unset=True) if hasattr(
        payload, "model_dump") else dict(payload)
    shot_id = await intra_shot_adoption._proposal_shot(
        session, proposal_id)
    return await intra_shot_adoption.review_proposals(
        session, shot_id, [{
            "proposal_id": proposal_id,
            "expected_proposal_hash": body["expected_proposal_hash"],
            "decision": body["decision"],
        }])


@router.post(
    "/shots/{shot_id}/intra-shot/proposals/review-batch",
)
async def review_intra_shot_proposals_batch(
    shot_id: str,
    payload: ProposalReviewBatch,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await intra_shot_adoption.review_proposals(
        session, shot_id,
        [dict(r) for r in payload.model_dump()["reviews"]])


@router.post(
    "/shots/{shot_id}/intra-shot/events",
    response_model=IntraShotEventRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_intra_shot_event(
    shot_id: str,
    payload: IntraShotEventCreate,
    session: AsyncSession = Depends(get_session),
) -> IntraShotEventRead:
    return IntraShotEventRead(**await intra_shot_service.create_event(
        session, shot_id, payload))


@router.patch(
    "/intra-shot/events/{event_id}",
    response_model=IntraShotEventRead,
)
async def patch_intra_shot_event(
    event_id: str,
    payload: IntraShotEventPatch,
    session: AsyncSession = Depends(get_session),
) -> IntraShotEventRead:
    return IntraShotEventRead(**await intra_shot_service.patch_event(
        session, event_id, payload))


@router.delete(
    "/intra-shot/events/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_intra_shot_event(
    event_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    await intra_shot_service.delete_event(session, event_id)
