"""Asset response schema (plan §46).

`blob_url` is a stable API-relative URL; absolute storage paths are never
exposed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AssetRead(BaseModel):
    """Shared Asset contract for upload, detail, and Project list (§3.3.2).

    `blob_url` is backend-canonical `/blobs/...`; the browser client maps it.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    take_id: str | None
    kind: str
    blob_hash: str
    detected_media_type: str | None
    upload_mime_type: str | None
    original_filename: str | None
    width: int | None
    height: int | None
    duration_ms: int | None
    fps: float | None
    created_at: str
    blob_url: str
