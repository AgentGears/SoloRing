"""Blob/Asset repositories (plan §17, §18, §25)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.assets.models import Asset, Blob
from soloring.domain.ids import is_uuid
from soloring.errors import ErrorCode, not_found


async def insert_blob_if_absent(
    session: AsyncSession,
    blob_hash: str,
    relative_path: str,
    size_bytes: int,
    detected_media_type: str | None,
) -> tuple[Blob, bool]:
    """Converge the Blob row (plan §25): INSERT ... ON CONFLICT DO NOTHING,
    then SELECT the canonical row. Returns (blob, already_existed).
    Duplicate bytes never deduplicate ASSET provenance."""
    stmt = (
        sqlite_insert(Blob)
        .values(
            hash=blob_hash,
            path=relative_path,
            size_bytes=size_bytes,
            detected_media_type=detected_media_type,
        )
        .on_conflict_do_nothing(index_elements=[Blob.hash])
    )
    result = await session.execute(stmt)
    existed = result.rowcount == 0
    blob = await session.get(Blob, blob_hash)
    assert blob is not None  # inserted or already present
    return blob, existed


async def get_asset(session: AsyncSession, asset_id: str) -> Asset:
    if not is_uuid(asset_id):
        raise not_found(ErrorCode.ASSET_NOT_FOUND, f"Asset {asset_id} not found.")
    asset = await session.get(Asset, asset_id)
    if asset is None:
        raise not_found(ErrorCode.ASSET_NOT_FOUND, f"Asset {asset_id} not found.")
    return asset


async def get_blob(session: AsyncSession, blob_hash: str) -> Blob | None:
    return await session.scalar(select(Blob).where(Blob.hash == blob_hash))
