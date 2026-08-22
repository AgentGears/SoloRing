"""Generation endpoints (v0.1 §41, §95-§98, §99): create/list/detail/SSE.

POST /shots/{id}/generations captures execution identity atomically and
returns 202 — no model execution happens in the API request. SSE is pure
observation over short DB sessions; the database is authoritative.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from soloring.db.timeutil import DB_NOW_SQL as _NOW

from soloring.api.deps import get_session
from soloring.api.schemas.generations import GenerationSummary
from soloring.generation import rerun
from soloring.generation import service as generation_service
from soloring.settings import get_settings

router = APIRouter(tags=["generations"])

_TERMINAL = ("succeeded", "failed", "interrupted", "cancelled")


@router.post(
    "/shots/{shot_id}/generations",
    response_model=GenerationSummary,
    status_code=202,
)
async def create_generation(
    shot_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> GenerationSummary:
    generation = await generation_service.create_generation_request(
        session, shot_id,
        settings=getattr(request.app.state, 'settings', None)
        or get_settings(),
    )
    return generation


@router.get("/shots/{shot_id}/generations", response_model=list[GenerationSummary])
async def list_generations(
    shot_id: str, session: AsyncSession = Depends(get_session)
) -> list[GenerationSummary]:
    return await generation_service.list_generations(session, shot_id)


@router.get("/generations/{generation_id}", response_model=GenerationSummary)
async def get_generation(
    generation_id: str, session: AsyncSession = Depends(get_session)
) -> GenerationSummary:
    from sqlalchemy import text as _text

    generation = await generation_service.get_generation_or_404(
        session, generation_id
    )
    summary = GenerationSummary.model_validate(generation)
    # workflow_spec_json is a DEFERRED column; load it explicitly inside
    # the session context rather than triggering lazy IO.
    spec_json = (
        await session.execute(
            _text(
                "SELECT workflow_spec_json FROM generations WHERE id = :g"
            ),
            {"g": generation_id},
        )
    ).scalar()
    _project_m9(summary, spec_json)
    return summary


def _project_m9(summary: GenerationSummary, spec_json: str | None) -> None:
    """§35: additive M9 projection from the CAPTURED spec bytes — never
    current profile/package/M8 state (§74)."""
    import json as _json

    if spec_json is None:
        return
    try:
        spec = _json.loads(spec_json)
    except (TypeError, ValueError):
        return
    if not isinstance(spec, dict) or spec.get("schema_version") != 2:
        return
    realization = spec.get("realization") or {}
    profile = realization.get("profile") or {}
    model = spec.get("model") or {}
    summary.workflow_spec_schema_version = 2
    summary.manifest_hash = getattr(generation, "manifest_hash", None)
    summary.workflow_template_hash = getattr(
        generation, "workflow_template_hash", None
    )
    summary.realization_profile_id = profile.get("id")
    summary.realization_profile_version = profile.get("version")
    summary.realization_profile_hash = profile.get("hash")
    summary.visual_reference_pack_hash = realization.get(
        "visual_reference_pack_hash"
    )
    summary.realization_summary = {
        "channels": [
            {
                "channel": c.get("channel"),
                "input_key": c.get("input_key"),
                "bindings": [
                    {
                        "facet_key": b.get("facet_key"),
                        "required": b.get("required"),
                        "asset_id": (b.get("item") or {}).get("asset_id"),
                        "blob_hash": (b.get("item") or {}).get("blob_hash"),
                        "role": (b.get("item") or {}).get("role"),
                        "view_key": (b.get("item") or {}).get("view_key"),
                    }
                    for b in c.get("bindings", [])
                ],
            }
            for c in realization.get("channels", [])
        ],
        "omitted_optional": realization.get("omitted_optional", []),
        "parameter_overrides": realization.get("parameter_overrides", {}),
        "execution_model_fingerprint_hash": model.get(
            "execution_model_fingerprint_hash"
        ),
    }


async def _observe(factory: async_sessionmaker[AsyncSession], generation_id: str):
    """One short read of the SSE projection (§97); session closed on return."""
    async with factory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT id, status, progress_current, progress_total, "
                    "current_node, cancel_requested_at, error_code, error_message, "
                    "updated_at FROM generations WHERE id = :gid"
                ),
                {"gid": generation_id},
            )
        ).mappings().first()
    return row


def _event(row) -> str:
    payload = {
        "id": row["id"],
        "status": row["status"],
        "progress_current": row["progress_current"],
        "progress_total": row["progress_total"],
        "current_node": row["current_node"],
        "cancel_requested": row["cancel_requested_at"] is not None,
        "cancel_requested_at": row["cancel_requested_at"],
        "error_code": row["error_code"],
        "error_message": row["error_message"],
        "updated_at": row["updated_at"],
    }
    return f"data: {json.dumps(payload)}\n\n"


async def sse_events(
    factory,
    interval: float,
    generation_id: str,
    disconnected=None,
) -> AsyncIterator[str]:
    """SSE event generator (§95-§98): short DB session per poll, immediate
    first event, close after the terminal event. Pure observation — the
    database is authoritative. Exposed separately for direct testing.
    """
    while True:
        if disconnected is not None and await disconnected():
            return
        row = await _observe(factory, generation_id)
        if row is None:
            yield "data: {\"error_code\": \"GENERATION_NOT_FOUND\"}\n\n"
            return
        yield _event(row)
        if row["status"] in _TERMINAL:
            return
        await asyncio.sleep(interval)


class CancelResult(BaseModel):
    generation_id: str
    status: str
    cancel_requested: bool


@router.post("/generations/{generation_id}/cancel", response_model=CancelResult)
async def cancel_generation(
    generation_id: str,
    session: AsyncSession = Depends(get_session),
) -> CancelResult:
    """Persisted cancellation intent (v0.1 §69-§75).

    The whole read-decide-write is ONE ``BEGIN IMMEDIATE`` unit (audit F5):
    a concurrent worker claim takes the same lock, so the API can never
    observe a queued row that a claim has already moved to preparing —
    the claim-vs-cancel TOCTOU is structurally closed, not rowcount-hoped.

    queued              → cancelled immediately (no executor interaction).
    preparing (no durable handle) → cancelled transactionally.
    preparing (handle) / submitted / running
                        → intent persisted; the current or recovering owner
                          reconciles with the executor.
    importing / terminal → 409 GENERATION_NOT_CANCELLABLE: durable import is
                          already publication, not execution.
    """
    from soloring.domain.ids import is_uuid
    from soloring.domain.now import db_now
    from soloring.errors import ErrorCode, SoloRingError, not_found

    if not is_uuid(generation_id):
        raise not_found(
            ErrorCode.GENERATION_NOT_FOUND,
            f"Generation {generation_id} not found.",
        )

    engine = session.bind
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            row = (await conn.execute(
                text(
                    "SELECT status, executor_job_id, "
                    "executor_submission_state FROM generations "
                    "WHERE id = :gid"
                ),
                {"gid": generation_id},
            )).one_or_none()

            if row is None:
                await conn.rollback()
                raise not_found(
                    ErrorCode.GENERATION_NOT_FOUND,
                    f"Generation {generation_id} not found.",
                )

            if row.status == "importing":
                await conn.rollback()
                raise SoloRingError(
                    ErrorCode.GENERATION_NOT_CANCELLABLE,
                    "Generation import has already started.",
                    status_code=409,
                )
            if row.status in _TERMINAL:
                await conn.rollback()
                raise SoloRingError(
                    ErrorCode.GENERATION_NOT_CANCELLABLE,
                    f"Generation is already {row.status}.",
                    status_code=409,
                )

            if row.status == "queued":
                claimed = (await conn.execute(
                    text(
                        "UPDATE generations SET status = 'cancelled', "
                        f"completed_at = {_NOW}, updated_at = {_NOW} "
                        "WHERE id = :gid AND status = 'queued'"
                    ).bindparams(gid=generation_id)
                )).rowcount
                await conn.commit()
                assert claimed == 1  # impossible to lose under IMMEDIATE
                return CancelResult(
                    generation_id=generation_id, status="cancelled",
                    cancel_requested=False,
                )

            if (
                row.status == "preparing"
                and row.executor_job_id is None
                # Re-audit R3: "no handle" no longer proves "no external
                # execution". A durably marked submission_possible attempt
                # may already have reached the executor (the POST response
                # was lost before the prompt id persisted) — such work is
                # NEVER terminal-cancelled as definitely unsubmitted; the
                # persisted intent lets recovery rediscover and reconcile.
                and row.executor_submission_state == "not_started"
            ):
                claimed = (await conn.execute(
                    text(
                        "UPDATE generations SET status = 'cancelled', "
                        f"completed_at = {_NOW}, updated_at = {_NOW} "
                        "WHERE id = :gid AND status = 'preparing' "
                        "AND executor_job_id IS NULL "
                        "AND executor_submission_state = 'not_started'"
                    ).bindparams(gid=generation_id)
                )).rowcount
                await conn.commit()
                assert claimed == 1
                return CancelResult(
                    generation_id=generation_id, status="cancelled",
                    cancel_requested=False,
                )

            # preparing-with-handle / submission-possible / submitted /
            # running: persist the intent (§69); the owner (or the
            # recovering successor) reconciles with the executor.
            now = await db_now(session)
            await conn.execute(
                text(
                    "UPDATE generations SET cancel_requested_at = :now, "
                    "cancel_reason = 'user request', updated_at = :now2 "
                    "WHERE id = :gid"
                ).bindparams(now=now, now2=now, gid=generation_id)
            )
            status_after = (await conn.execute(
                text("SELECT status FROM generations WHERE id = :gid"),
                {"gid": generation_id},
            )).scalar_one()
            await conn.commit()
            return CancelResult(
                generation_id=generation_id, status=status_after,
                cancel_requested=True,
            )
        except Exception:
            import contextlib

            with contextlib.suppress(Exception):
                await conn.rollback()
            raise


@router.post(
    "/generations/{generation_id}/rerun",
    response_model=GenerationSummary,
    status_code=202,
)
async def rerun_generation(
    generation_id: str, session: AsyncSession = Depends(get_session)
) -> GenerationSummary:
    """Exact Rerun (M6 plan §11–§14): a new execution attempt of a terminal
    source Generation's durable historical specification.

    The §12 spec fields and every historical GenerationInput are copied
    verbatim; all execution-attempt state initializes fresh-queue (the total
    §13 rule — mechanically enforced by writing only the columns the shared
    create-generation INSERT enumerates). Active sources -> 409
    GENERATION_ACTIVE; missing -> 404. Like creation, this only enqueues.
    """
    return await rerun.create_rerun(session, generation_id)


@router.get("/generations/{generation_id}/events")
async def generation_events(
    generation_id: str, request: Request
) -> StreamingResponse:
    factory = request.app.state.session_factory
    interval = get_settings().sse_poll_interval_seconds
    return StreamingResponse(
        sse_events(factory, interval, generation_id, request.is_disconnected),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
