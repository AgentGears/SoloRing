"""Canonical VisualAnchorRevision snapshot + working-set semantics.

THE single canonical builder for VisualAnchorRevision snapshots (frozen
plan §§28–30): one serializer (``domain.canonical``), exact stored bytes ==
exact hashed bytes, position-authoritative order, no policy/timestamp/
pointer fields in the bytes. Working-vs-approved comparison (§33) uses the
same builder — never a second hash implementation (APR-012).
"""

from __future__ import annotations

from dataclasses import dataclass

from soloring.domain.canonical import canonical_hash, canonical_json_str

REVISION_SNAPSHOT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class WorkingItem:
    """One frozen working item as loaded for canonicalization."""

    asset_id: str
    blob_hash: str
    role: str
    view_key: str | None
    position: int


@dataclass(frozen=True)
class AnchorBinding:
    """The semantic identity of one VisualAnchor (immutable)."""

    visual_facet_id: str
    facet_key: str
    target_kind: str  # 'entity' | 'feature'
    entity_id: str | None
    feature_id: str | None
    entity_revision_id: str | None
    feature_value_hash: str | None
    feature_value_json: str | None
    visual_context_entity_revision_id: str | None


def build_revision_snapshot(
    binding: AnchorBinding, items: list[WorkingItem]
) -> dict:
    """Canonical VisualAnchorRevision snapshot value (§28).

    Items are ordered by (position, asset_id) — position is authoritative
    global pack order; asset_id is the corruption-safe tiebreaker only
    (§29). The value is canonicalized through the ONE serializer; field
    order in the dict is irrelevant because the serializer sorts keys.
    """
    ordered = sorted(items, key=lambda it: (it.position, it.asset_id))
    if binding.target_kind == "entity":
        state_binding = {
            "kind": "entity_revision",
            "entity_revision_id": binding.entity_revision_id,
        }
        target = {"kind": "entity", "entity_id": binding.entity_id}
    else:
        state_binding = {
            "kind": "feature_value",
            "feature_value_hash": binding.feature_value_hash,
            "feature_value_json": binding.feature_value_json,
            "visual_context_entity_revision_id": (
                binding.visual_context_entity_revision_id
            ),
        }
        target = {"kind": "feature", "feature_id": binding.feature_id}
    return {
        "schema_version": REVISION_SNAPSHOT_SCHEMA_VERSION,
        "visual_facet": {
            "visual_facet_id": binding.visual_facet_id,
            "facet_key": binding.facet_key,
            "target": target,
        },
        "state_binding": state_binding,
        "items": [
            {
                "asset_id": it.asset_id,
                "blob_hash": it.blob_hash,
                "role": it.role,
                "view_key": it.view_key,
                "position": it.position,
            }
            for it in ordered
        ],
    }


def revision_snapshot_bytes(snapshot: dict) -> tuple[str, str]:
    """(snapshot_json, snapshot_hash) — exact stored == exact hashed."""
    return canonical_json_str(snapshot), canonical_hash(snapshot)
