"""Canonical JSON serialization (plan §12, §13).

Exactly one serializer is permitted. The exact stored bytes are the exact hashed
bytes, so snapshot identity is byte-stable regardless of dict insertion order.
"""

from __future__ import annotations

import hashlib
import json


def canonical_json_bytes(value: object) -> bytes:
    """Canonical UTF-8 bytes: sorted keys, minimal separators, no ASCII escape."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def canonical_json_str(value: object) -> str:
    """The canonical bytes decoded back to a str (the persisted snapshot_json)."""
    return canonical_json_bytes(value).decode("utf-8")


def canonical_hash(value: object) -> str:
    """SHA-256 hex of the canonical bytes (the persisted snapshot_hash)."""
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()
