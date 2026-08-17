"""Deterministic magic-byte media detection (plan §20).

M1 detects only JPEG and PNG signatures. Everything else is `None` (unknown,
served as application/octet-stream). No probing libraries in M1.
"""

from __future__ import annotations

_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89\x50\x4e\x47"  # first 4 bytes of the PNG signature


def detect_media_type(head: bytes) -> str | None:
    """Return the detected media type from leading bytes, or None if unknown."""
    if head.startswith(_JPEG_MAGIC):
        return "image/jpeg"
    if head.startswith(_PNG_MAGIC):
        return "image/png"
    return None
