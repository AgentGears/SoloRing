"""Publication readiness resolver (frozen R3 plan §8).

One deterministic resolver used by both preview and publish. Registered-byte
corruption raises immediately; legitimate blockers are explicit readiness
issues. The DB read closes before physical file hashing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.assets.blob_store import BlobStore
from soloring.errors import ErrorCode, SoloRingError, internal_invariant, not_found
from soloring.production.canonical import (
    RetainedBlobClosure,
    production_revision_snapshot_hash,
    production_revision_snapshot_json,
)

SOURCE_PROJECT_MISMATCH = "SOURCE_PROJECT_MISMATCH"
SOURCE_BLOB_EMPTY = "SOURCE_BLOB_EMPTY"
SOURCE_MEDIA_TYPE_INVALID = "SOURCE_MEDIA_TYPE_INVALID"

_MEDIA_TYPE_MAX = 255


@dataclass(frozen=True)
class ProductionPublicationIssue:
    code: str
    message: str
    details: Mapping[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "details": dict(self.details)}


def _media_type_valid(media_type: str | None) -> bool:
    """Closure grammar: NULL, or trimmed non-empty <=255 chars (plan §3.5)."""
    if media_type is None:
        return True
    return (
        1 <= len(media_type.strip()) <= _MEDIA_TYPE_MAX
        and media_type == media_type.strip()
    )


@dataclass(frozen=True)
class ProductionPublicationReadiness:
    production_object_id: str
    source_asset_id: str
    ready: bool
    issues: tuple[ProductionPublicationIssue, ...]
    snapshot_json: str | None = None
    snapshot_hash: str | None = None
    closure: RetainedBlobClosure | None = None

    def issues_as_dicts(self) -> list[dict]:
        return [i.as_dict() for i in self.issues]


async def resolve_publication_readiness(
    session: AsyncSession,
    blob_store: BlobStore,
    *,
    production_object_id: str,
    source_asset_id: str,
) -> ProductionPublicationReadiness:
    """One deterministic readiness computation (preview and publish alike)."""
    issues: list[ProductionPublicationIssue] = []

    # §8.1: ONE explicit coherent read over active Project + Production
    # Object + source Asset + registered Blob — a single joined SELECT on a
    # single connection, so the frozen facts come from one SQLite snapshot
    # and can never describe a state that did not coexist.
    async with session.bind.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT po.id AS object_id, po.project_id AS object_project_id, "
                    "p.deleted_at AS project_deleted_at, "
                    "a.id AS asset_id, a.project_id AS asset_project_id, "
                    "a.blob_hash AS blob_hash, b.size_bytes AS size_bytes, "
                    "b.detected_media_type AS media_type "
                    "FROM production_objects po "
                    "JOIN projects p ON p.id = po.project_id "
                    "LEFT JOIN assets a ON a.id = :aid "
                    "LEFT JOIN blobs b ON b.hash = a.blob_hash "
                    "WHERE po.id = :oid"
                ),
                {"oid": production_object_id, "aid": source_asset_id},
            )
        ).first()
    if row is None or row.project_deleted_at is not None:
        raise not_found(
            ErrorCode.PRODUCTION_OBJECT_NOT_FOUND,
            f"production object {production_object_id!r} not found",
        )

    if row.asset_id is None or row.blob_hash is None:
        # Existing contract: unresolvable Asset identity is ASSET_NOT_FOUND.
        raise not_found(
            ErrorCode.ASSET_NOT_FOUND,
            f"asset {source_asset_id!r} not found",
        )
    asset = row

    if not BlobStore.validate_hash(asset.blob_hash):
        raise internal_invariant(
            "registered blob hash is not canonical",
            details={"blob_hash": asset.blob_hash},
        )

    if asset.asset_project_id != row.object_project_id:
        issues.append(
            ProductionPublicationIssue(
                SOURCE_PROJECT_MISMATCH,
                "candidate Asset belongs to another Project",
                {
                    "asset_project_id": asset.asset_project_id,
                    "object_project_id": row.object_project_id,
                },
            )
        )
    if asset.size_bytes <= 0:
        issues.append(
            ProductionPublicationIssue(
                SOURCE_BLOB_EMPTY,
                "registered Blob has zero bytes; not publishable under retained_blob/v1",
                {"size_bytes": asset.size_bytes},
            )
        )
    if not _media_type_valid(asset.media_type):
        issues.append(
            ProductionPublicationIssue(
                SOURCE_MEDIA_TYPE_INVALID,
                "registered Blob media_type is blank/whitespace, untrimmed, or "
                "longer than 255 characters; not publishable under the M11 "
                "closure grammar",
                {},
            )
        )

    if issues:
        return ProductionPublicationReadiness(
            production_object_id=production_object_id,
            source_asset_id=source_asset_id,
            ready=False,
            issues=tuple(issues),
        )

    # Physical verification outside the DB read; corruption fails closed.
    verification = await blob_store.verify_physical_bytes(
        asset.blob_hash, asset.size_bytes
    )
    if not verification.ok:
        raise internal_invariant(
            "registered Blob physical bytes failed verification",
            details={
                "blob_hash": asset.blob_hash,
                "expected_size": asset.size_bytes,
                "reason": verification.reason,
                "actual_hash": verification.actual_hash,
                "actual_size": verification.actual_size,
            },
        )

    closure = RetainedBlobClosure(
        blob_hash=asset.blob_hash,
        size_bytes=asset.size_bytes,
        media_type=asset.media_type,
    )
    return ProductionPublicationReadiness(
        production_object_id=production_object_id,
        source_asset_id=source_asset_id,
        ready=True,
        issues=(),
        snapshot_json=production_revision_snapshot_json(closure),
        snapshot_hash=production_revision_snapshot_hash(closure),
        closure=closure,
    )
