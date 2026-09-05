"""Production Library HTTP routes (frozen R3 plan §11).

Candidate selection reuses the existing Project Asset surface. Detail uses
the §10.1 metadata-verification tier (no full physical re-hash on browse);
``physical_integrity`` states exactly what this view proved.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.api.deps import get_session
from soloring.api.schemas.production import (
    ClosureRead,
    ProductionObjectCreate,
    ProductionObjectPatch,
    ProductionObjectRead,
    PublicationReadinessRead,
    PublicationReadinessRequest,
    PublishRequest,
    ReadinessIssue,
    RevisionDetail,
    RevisionSummary,
    SourceAssetSummary,
)
from soloring.assets.blob_store import BlobStore
from soloring.production import service as prod
from soloring.production.readiness import resolve_publication_readiness

router = APIRouter(tags=["production"])


def _blob_url(blob_hash: str) -> str:
    return f"/blobs/{blob_hash[0:2]}/{blob_hash[2:4]}/{blob_hash}"


def _object_read(o: dict) -> ProductionObjectRead:
    return ProductionObjectRead(**o)


@router.post(
    "/projects/{project_id}/production-objects",
    response_model=ProductionObjectRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_production_object(
    project_id: str,
    body: ProductionObjectCreate,
    session: AsyncSession = Depends(get_session),
) -> ProductionObjectRead:
    return _object_read(
        await prod.create_production_object(
            session, project_id, name=body.name, description=body.description
        )
    )


@router.get(
    "/projects/{project_id}/production-objects",
    response_model=list[ProductionObjectRead],
)
async def list_production_objects(
    project_id: str, session: AsyncSession = Depends(get_session)
) -> list[ProductionObjectRead]:
    return [
        _object_read(o)
        for o in await prod.list_production_objects(session, project_id)
    ]


@router.get(
    "/production-objects/{production_object_id}",
    response_model=ProductionObjectRead,
)
async def get_production_object(
    production_object_id: str, session: AsyncSession = Depends(get_session)
) -> ProductionObjectRead:
    return _object_read(
        await prod.get_production_object(session, production_object_id)
    )


@router.patch(
    "/production-objects/{production_object_id}",
    response_model=ProductionObjectRead,
)
async def patch_production_object(
    production_object_id: str,
    body: ProductionObjectPatch,
    session: AsyncSession = Depends(get_session),
) -> ProductionObjectRead:
    return _object_read(
        await prod.patch_production_object(
            session,
            production_object_id,
            name=body.name,
            description=body.description,
        )
    )


@router.post(
    "/production-objects/{production_object_id}/publication-readiness",
    response_model=PublicationReadinessRead,
)
async def publication_readiness(
    production_object_id: str,
    body: PublicationReadinessRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> PublicationReadinessRead:
    blob_store = BlobStore(request.app.state.settings)
    r = await resolve_publication_readiness(
        session,
        blob_store,
        production_object_id=production_object_id,
        source_asset_id=body.asset_id,
    )
    return PublicationReadinessRead(
        production_object_id=r.production_object_id,
        source_asset_id=r.source_asset_id,
        ready=r.ready,
        issues=[ReadinessIssue(**i) for i in r.issues_as_dicts()],
        proposed_snapshot_hash=r.snapshot_hash,
        closure=ClosureRead(
            contract_key="retained_blob",
            contract_version=1,
            blob_hash=r.closure.blob_hash,
            size_bytes=r.closure.size_bytes,
            media_type=r.closure.media_type,
        ) if r.closure else None,
    )


@router.post("/production-objects/{production_object_id}/revisions")
async def publish_revision(
    production_object_id: str,
    body: PublishRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    blob_store = BlobStore(request.app.state.settings)
    detail, created = await prod.publish_production_revision(
        session,
        blob_store,
        production_object_id=production_object_id,
        source_asset_id=body.asset_id,
    )
    blob_url = _blob_url(detail["closure"]["blob_hash"])
    sources = await _sources(session, detail["revision_id"])
    payload = {
        **detail,
        "blob_url": blob_url,
        "sources": sources,
        "physical_integrity": "not_full_hash_verified_in_this_view",
    }
    return JSONResponse(
        payload,
        status_code=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


async def _sources(session: AsyncSession, revision_id: str) -> list[dict]:
    async with session.bind.connect() as conn:
        return await prod.verify_source_provenance(conn, revision_id)


@router.get(
    "/production-objects/{production_object_id}/revisions",
    response_model=list[RevisionSummary],
)
async def list_revisions(
    production_object_id: str, session: AsyncSession = Depends(get_session)
) -> list[RevisionSummary]:
    # Parent authority is verified first: unknown/inactive → 404.
    await prod.get_production_object(session, production_object_id)
    return [
        RevisionSummary(**r)
        for r in await prod.list_production_revisions(
            session, production_object_id
        )
    ]


@router.get(
    "/production-revisions/{revision_id}", response_model=RevisionDetail
)
async def get_revision(
    revision_id: str, session: AsyncSession = Depends(get_session)
) -> RevisionDetail:
    async with session.bind.connect() as conn:
        meta = await prod.load_production_revision_metadata_verified(
            conn, revision_id=revision_id
        )
    return RevisionDetail(
        **meta,
        blob_url=_blob_url(meta["closure"]["blob_hash"]),
        sources=[
            SourceAssetSummary(**s)
            for s in await _sources(session, revision_id)
        ],
        physical_integrity="not_full_hash_verified_in_this_view",
    )
