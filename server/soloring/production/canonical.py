"""Schema-1 canonical Production Revision grammar (frozen R3 plan §6).

Owns only the M11 schema grammar/builder. Canonical serialization and
hashing are imported from the one shared serializer (``domain.canonical``)
— M11 introduces no second serializer.
"""

from __future__ import annotations

from dataclasses import dataclass

from soloring.domain.canonical import canonical_hash, canonical_json_bytes, canonical_json_str

CONTRACT_KEY = "retained_blob"
CONTRACT_VERSION = 1
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class RetainedBlobClosure:
    """The exact retained_blob/v1 consumption facts (plan §3.4)."""

    blob_hash: str
    size_bytes: int
    media_type: str | None


def build_production_revision_snapshot(closure: RetainedBlobClosure) -> dict:
    """Exact schema-1 canonical document (plan §6.2).

    No optional keys are omitted; ``media_type`` is explicitly ``null`` when
    unknown. Nothing else — no names, paths, Asset identity, creator detail —
    ever enters this document.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "consumption": {
            "contract_key": CONTRACT_KEY,
            "contract_version": CONTRACT_VERSION,
            "blob_hash": closure.blob_hash,
            "size_bytes": closure.size_bytes,
            "media_type": closure.media_type,
        },
    }


def production_revision_snapshot_bytes(closure: RetainedBlobClosure) -> bytes:
    return canonical_json_bytes(build_production_revision_snapshot(closure))


def production_revision_snapshot_json(closure: RetainedBlobClosure) -> str:
    return canonical_json_str(build_production_revision_snapshot(closure))


def production_revision_snapshot_hash(closure: RetainedBlobClosure) -> str:
    return canonical_hash(build_production_revision_snapshot(closure))
