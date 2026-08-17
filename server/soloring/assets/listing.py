"""Project Asset listing (M2 plan §3.3).

Persistent reference-asset discovery: Project-scoped, deterministic
(created_at, id) ordering, optional AssetKind filter (default reference,
invalid values → VALIDATION_ERROR envelope). detected_media_type comes from
the referenced Blob row — never inferred from upload_mime_type.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.assets.models import Asset, Blob
from soloring.domain.enums import AssetKind
from soloring.domain.projects import _get_active
from soloring.errors import validation_error


def parse_kind_filter(kind: str | None) -> AssetKind:
    if kind is None:
        return AssetKind.REFERENCE
    try:
        return AssetKind(kind)
    except ValueError:
        raise validation_error(
            f"Invalid asset kind filter: {kind!r}. "
            "Allowed values: reference, output."
        ) from None


async def list_project_assets(
    session: AsyncSession, project_id: str, kind: str | None
) -> list[tuple[Asset, str | None]]:
    """Active-Project asset rows with their Blob-derived media type.

    Returns (asset, detected_media_type) pairs ordered by (created_at, id).
    """
    await _get_active(session, project_id)  # raises PROJECT_NOT_FOUND
    asset_kind = parse_kind_filter(kind)
    res = await session.execute(
        select(Asset, Blob.detected_media_type)
        .join(Blob, Asset.blob_hash == Blob.hash)
        .where(Asset.project_id == project_id, Asset.kind == asset_kind.value)
        .order_by(Asset.created_at, Asset.id)
    )
    return [(asset, detected) for asset, detected in res.all()]
