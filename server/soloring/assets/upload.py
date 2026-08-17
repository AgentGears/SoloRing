"""Streamed reference-asset upload (plan §22, §23, §24, §25, §27).

Session discipline (plan §47): SHORT database units, each closed before the
next phase; no session is ever open while bytes are streamed or files are
placed. Units: (1) verify active Project; (2) after hashing, check Blob row
registration (repair discrimination); (3) persist Blob/Asset. The caller
supplies the session factory; this module opens and closes its own sessions.

Blob identity derives from bytes; Asset identity derives from provenance: the
same bytes converge to one physical Blob and one blobs row, while every
successful explicit upload creates a fresh Asset.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from soloring.assets.blob_store import BlobStore
from soloring.assets.media import detect_media_type
from soloring.assets.models import Asset
from soloring.assets.service import get_blob, insert_blob_if_absent
from soloring.domain.ids import new_uuid
from soloring.domain.normalize import basename_filename
from soloring.domain.projects import _get_active
from soloring.errors import ErrorCode, SoloRingError
from soloring.settings import Settings

log = logging.getLogger("soloring.assets.upload")

# Leading bytes retained for magic-byte detection (plan §20).
_HEAD_BYTES = 16


async def _stream_to_temp(
    file: UploadFile, temp_path: Path, settings: Settings
) -> tuple[str, int, str | None]:
    """Stream bounded chunks to temp, hashing and counting bytes (§22.2).

    Returns (sha256_hex, total_bytes, detected_media_type). Raises
    UPLOAD_TOO_LARGE / EMPTY_UPLOAD with the temp file cleaned by the caller.
    """
    hasher = hashlib.sha256()
    total = 0
    head = b""

    fh = await asyncio.to_thread(open, temp_path, "wb")
    try:
        while True:
            chunk = await file.read(settings.upload_chunk_bytes)
            if not chunk:
                break
            total += len(chunk)
            if total > settings.max_upload_bytes:
                raise SoloRingError(
                    ErrorCode.UPLOAD_TOO_LARGE,
                    "Upload exceeds the configured maximum size.",
                    status_code=413,
                )
            hasher.update(chunk)
            if len(head) < _HEAD_BYTES:
                head = (head + chunk)[:_HEAD_BYTES]
            await asyncio.to_thread(fh.write, chunk)
    finally:
        await asyncio.to_thread(fh.close)

    if total == 0:
        raise SoloRingError(
            ErrorCode.EMPTY_UPLOAD, "Zero-byte uploads are not valid.", status_code=400
        )

    return hasher.hexdigest(), total, detect_media_type(head)


async def upload_reference_asset(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    blob_store: BlobStore,
    project_id: str,
    file: UploadFile,
) -> tuple[Asset, str | None]:
    """Returns (asset, detected_media_type) so responses need no re-query."""
    # --- Phase 1: short DB read — verify the active Project, then close (§22.1).
    async with session_factory() as session:
        await _get_active(session, project_id)

    # --- Phase 2: DB-free streaming + hashing + atomic placement.
    temp_path = blob_store.tmp_path()
    placed = False
    try:
        blob_hash, total, detected = await _stream_to_temp(file, temp_path, settings)
        relative_path = blob_store.relative_path_for_hash(blob_hash)

        # Row-registration check BEFORE placement (short session, closed
        # before any file I/O). Every writer in this pipeline places bytes
        # before registering its row, so a row visible at this point means
        # the bytes were previously placed; if placement then finds the
        # physical file missing, the bytes were genuinely lost -> integrity
        # repair (plan §27.2). A row that appears only AFTER this check is
        # ordinary concurrent convergence and must NOT be reported as repair.
        async with session_factory() as session:
            row_registered_before_place = await get_blob(session, blob_hash) is not None

        placed = await blob_store.place(blob_hash, temp_path)

        # --- Phase 3: short DB transaction — re-check project, converge Blob,
        # always create a fresh reference Asset (§25).
        async with session_factory() as session:
            await _get_active(session, project_id)  # may have been deleted mid-upload
            _blob, _existed = await insert_blob_if_absent(
                session, blob_hash, relative_path, total, detected
            )
            if placed and row_registered_before_place:
                # Verified upload repaired a registered Blob whose bytes were
                # missing (plan §27.2). Repair is never silent.
                log.error(
                    "BLOB REPAIR: registered Blob %s had missing physical bytes; "
                    "restored from verified upload to %s",
                    blob_hash,
                    relative_path,
                )
            asset = Asset(
                id=new_uuid(),
                project_id=project_id,
                blob_hash=blob_hash,
                kind="reference",
                upload_mime_type=file.content_type,
                original_filename=basename_filename(file.filename),
            )
            session.add(asset)
            await session.commit()
            await session.refresh(asset)
            return asset, detected
    finally:
        # Temp is always consumed by place(); this covers every failure path
        # before placement (§50.8: temp removed on every failure path).
        with contextlib.suppress(FileNotFoundError):
            await asyncio.to_thread(temp_path.unlink)
