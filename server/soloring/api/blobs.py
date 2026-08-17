"""Blob serving (plan §28, §29, §30).

Address syntax and prefix matching are validated BEFORE any DB lookup or
filesystem access (§28.1). Serving uses `detected_media_type` or
application/octet-stream — never upload_mime_type. Physical paths derive from
the validated hash and are never exposed in responses.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.api.deps import get_session
from soloring.assets import service as asset_service
from soloring.assets.blob_store import BlobStore
from soloring.errors import ErrorCode, SoloRingError

log = logging.getLogger("soloring.api.blobs")

router = APIRouter(tags=["blobs"])

_HEX = set("0123456789abcdef")
_CHUNK = 1 << 16


def _validate_address(prefix1: str, prefix2: str, blob_hash: str) -> None:
    """Structural validation before lookup/filesystem access (plan §28.1)."""
    if len(blob_hash) != 64 or not set(blob_hash) <= _HEX:
        raise SoloRingError(
            ErrorCode.VALIDATION_ERROR, "Malformed blob hash.", status_code=400
        )
    if prefix1 != blob_hash[0:2] or prefix2 != blob_hash[2:4]:
        raise SoloRingError(
            ErrorCode.VALIDATION_ERROR, "Blob address prefix mismatch.", status_code=400
        )


def _parse_range(header: str, size: int) -> tuple[int, int] | None:
    """Single-range parser (plan §29).

    Returns an inclusive (start, end), or None for malformed/unsatisfiable
    (both produce 416). Multipart ranges are out of scope -> 416.
    """
    if not header.startswith("bytes="):
        return None
    spec = header[len("bytes="):]
    if "," in spec or "-" not in spec:
        return None
    first, last = spec.split("-", 1)
    if first == "":
        # suffix form: bytes=-N (last N bytes)
        if not last.isdigit():
            return None
        suffix = int(last)
        if suffix == 0:
            return None
        return (0, size - 1) if suffix >= size else (size - suffix, size - 1)
    if not first.isdigit():
        return None
    start = int(first)
    if last == "":
        end = size - 1
    else:
        if not last.isdigit():
            return None
        end = int(last)
    if start > end or start >= size:
        return None  # unsatisfiable / malformed
    return (start, min(end, size - 1))


async def _file_slice(path: Path, start: int, end: int):
    fh = await asyncio.to_thread(open, path, "rb")
    try:
        await asyncio.to_thread(fh.seek, start)
        remaining = end - start + 1
        while remaining > 0:
            data = await asyncio.to_thread(fh.read, min(_CHUNK, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data
    finally:
        await asyncio.to_thread(fh.close)


async def _serve(
    request: Request,
    session: AsyncSession,
    prefix1: str,
    prefix2: str,
    blob_hash: str,
    *,
    head_only: bool,
):
    _validate_address(prefix1, prefix2, blob_hash)

    blob = await asset_service.get_blob(session, blob_hash)
    if blob is None:
        raise SoloRingError(
            ErrorCode.BLOB_NOT_FOUND, f"Blob {blob_hash} not found.", status_code=404
        )

    store = BlobStore(request.app.state.settings)
    path = store.path_for_hash(blob_hash)  # derived from validated hash only

    def _size() -> int | None:
        try:
            return path.stat().st_size
        except FileNotFoundError:
            return None

    size = await asyncio.to_thread(_size)
    if size is None:
        # Registered row with missing physical bytes (plan §27.1).
        log.error(
            "BLOB INTEGRITY: registered Blob %s is missing its physical bytes at %s",
            blob_hash,
            path,
        )
        raise SoloRingError(
            ErrorCode.BLOB_NOT_FOUND, f"Blob {blob_hash} not found.", status_code=404
        )

    media = blob.detected_media_type or "application/octet-stream"
    base = {
        "ETag": f'"{blob_hash}"',  # quoted SHA-256 (plan §30)
        "Cache-Control": "public, max-age=31536000, immutable",
        "Accept-Ranges": "bytes",
    }

    range_header = request.headers.get("range")
    if range_header is None:
        headers = {**base, "Content-Length": str(size)}
        if head_only:
            return Response(status_code=200, media_type=media, headers=headers)
        return StreamingResponse(
            _file_slice(path, 0, size - 1),
            status_code=200,
            media_type=media,
            headers=headers,
        )

    rng = _parse_range(range_header, size)
    if rng is None:
        return Response(
            status_code=416,
            media_type=media,
            headers={**base, "Content-Range": f"bytes */{size}"},
        )
    start, end = rng
    headers = {
        **base,
        "Content-Range": f"bytes {start}-{end}/{size}",
        "Content-Length": str(end - start + 1),
    }
    if head_only:
        return Response(status_code=206, media_type=media, headers=headers)
    return StreamingResponse(
        _file_slice(path, start, end),
        status_code=206,
        media_type=media,
        headers=headers,
    )


@router.get("/blobs/{prefix1}/{prefix2}/{blob_hash}")
async def get_blob_content(
    prefix1: str,
    prefix2: str,
    blob_hash: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    return await _serve(
        request, session, prefix1, prefix2, blob_hash, head_only=False
    )


@router.head("/blobs/{prefix1}/{prefix2}/{blob_hash}")
async def head_blob_content(
    prefix1: str,
    prefix2: str,
    blob_hash: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    return await _serve(request, session, prefix1, prefix2, blob_hash, head_only=True)
