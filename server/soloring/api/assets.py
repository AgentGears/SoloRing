"""Asset HTTP routes (plan §22, §45; M2 §3.3).

POST /projects/{id}/assets is the streamed reference-upload pipeline. It
deliberately does not use the request-scoped session dependency: the pipeline
opens its own short DB units around a DB-free streaming phase (plan §47).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.api.deps import get_session
from soloring.api.schemas.assets import AssetRead
from soloring.assets import listing, service as asset_service
from soloring.assets.blob_store import BlobStore
from soloring.assets.models import Asset, Blob
from soloring.assets.upload import upload_reference_asset

router = APIRouter(tags=["assets"])


def _asset_read(asset: Asset, detected_media_type: str | None) -> AssetRead:
    h = asset.blob_hash
    return AssetRead(
        id=asset.id,
        project_id=asset.project_id,
        take_id=asset.take_id,
        kind=asset.kind,
        blob_hash=h,
        detected_media_type=detected_media_type,
        upload_mime_type=asset.upload_mime_type,
        original_filename=asset.original_filename,
        width=asset.width,
        height=asset.height,
        duration_ms=asset.duration_ms,
        fps=asset.fps,
        created_at=asset.created_at,
        # Backend-canonical form (M2 §3.3.3); the browser client maps to /api.
        blob_url=f"/blobs/{h[0:2]}/{h[2:4]}/{h}",
    )


async def _with_detected(session: AsyncSession, asset: Asset) -> AssetRead:
    detected = (
        await session.execute(
            select(Blob.detected_media_type).where(Blob.hash == asset.blob_hash)
        )
    ).scalar_one_or_none()
    return _asset_read(asset, detected)


@router.post(
    "/projects/{project_id}/assets",
    response_model=AssetRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_asset(
    project_id: str,
    request: Request,
    file: UploadFile = File(...),
) -> AssetRead:
    settings = request.app.state.settings
    factory = request.app.state.session_factory
    blob_store = BlobStore(settings)
    asset, detected = await upload_reference_asset(
        factory, settings, blob_store, project_id, file
    )
    return _asset_read(asset, detected)


@router.get("/projects/{project_id}/assets", response_model=list[AssetRead])
async def list_project_assets(
    project_id: str,
    kind: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[AssetRead]:
    rows = await listing.list_project_assets(session, project_id, kind)
    return [_asset_read(asset, detected) for asset, detected in rows]


@router.get("/assets/{asset_id}", response_model=AssetRead)
async def get_asset(
    asset_id: str, session: AsyncSession = Depends(get_session)
) -> AssetRead:
    asset = await asset_service.get_asset(session, asset_id)
    return await _with_detected(session, asset)
