"""CapturedVisualAuthority (frozen plan §10).

ONE server-owned value shape for M9: built from current coherent M8
state for preview, or reconstructed (+hash-validated) from a historical
ShotRevision schema 4 for Generation capture. Cross-facet order is
exactly M8 VisualReferencePack order — M9 invents no second ordering.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from soloring.domain.canonical import canonical_hash
from soloring.errors import internal_invariant


@dataclass(frozen=True)
class CapturedItem:
    asset_id: str
    blob_hash: str
    role: str
    view_key: str | None
    position: int


@dataclass(frozen=True)
class CapturedFacet:
    visual_facet_id: str
    facet_key: str
    requirement: str  # 'required' | 'optional' — allocation input
    target_kind: str
    entity_id: str | None
    entity_revision_id: str | None
    feature_id: str | None
    feature_value_hash: str | None
    feature_value_json: str | None
    visual_context_entity_revision_id: str | None
    visual_anchor_id: str
    visual_anchor_revision_id: str
    visual_anchor_snapshot_hash: str
    items: tuple[CapturedItem, ...]


@dataclass(frozen=True)
class CapturedVisualAuthority:
    visual_reference_pack_hash: str
    facets: tuple[CapturedFacet, ...]


def build_captured_authority(
    pack: dict, facet_requirements: dict[str, str]
) -> CapturedVisualAuthority:
    """Pure conversion of a canonical VisualReferencePack value (§49
    shape, already in §50 order) + the per-facet requirement map from the
    SAME coherent read into the capture-shaped authority value.

    Preview and historical adapters both call this with their pack; the
    shape is identical by construction (§10.2)."""
    facets: list[CapturedFacet] = []
    for anchor in pack.get("anchors", []):
        fid = anchor["visual_facet_id"]
        requirement = facet_requirements.get(fid)
        if requirement not in ("required", "optional"):
            raise internal_invariant(
                f"CapturedVisualAuthority facet {fid} lacks a valid "
                "requirement value from the same coherent read."
            )
        target = anchor["target"]
        # §7.3 (B2): the M8 pack encodes feature anchors as kind
        # "feature"; the M9 rule selector vocabulary is "feature_value".
        # Normalized ONCE here — the one adapter boundary — so captured
        # Feature authority matches exact feature_value rules.
        target_kind = target["kind"]
        if target_kind == "feature":
            target_kind = "feature_value"
        items = tuple(
            CapturedItem(
                asset_id=it["asset_id"],
                blob_hash=it["blob_hash"],
                role=it["role"],
                view_key=it["view_key"],
                position=it["position"],
            )
            for it in sorted(
                anchor.get("items", []), key=lambda i: i["position"]
            )
        )
        facets.append(CapturedFacet(
            visual_facet_id=fid,
            facet_key=anchor["facet_key"],
            requirement=requirement,
            target_kind=target_kind,
            entity_id=target.get("entity_id"),
            entity_revision_id=target.get("entity_revision_id"),
            feature_id=target.get("feature_id"),
            feature_value_hash=target.get("feature_value_hash"),
            feature_value_json=target.get("feature_value_json"),
            visual_context_entity_revision_id=(
                target.get("visual_context_entity_revision_id")
            ),
            visual_anchor_id=anchor["visual_anchor_id"],
            visual_anchor_revision_id=anchor["visual_anchor_revision_id"],
            visual_anchor_snapshot_hash=anchor["visual_anchor_snapshot_hash"],
            items=items,
        ))
    return CapturedVisualAuthority(
        visual_reference_pack_hash=canonical_hash(pack),
        facets=tuple(facets),
    )


async def reconstruct_pack(
    conn: AsyncConnection, revision_id: str
) -> tuple[dict, str]:
    """§10.1 historical reconstruction from captured normalized M8
    provenance: batch-load anchor + item rows, rebuild the canonical §49
    pack value in captured position order, recompute its hash, and
    require exact equality with the ShotRevision's stored pack hash.

    A mismatch is INTERNAL_INVARIANT_VIOLATION — never an M9 readiness
    issue."""
    anchors = (
        await conn.execute(
            text(
                "SELECT position, visual_facet_id, facet_key, "
                "visual_anchor_id, visual_anchor_revision_id, "
                "visual_anchor_snapshot_hash, target_kind, entity_id, "
                "entity_revision_id, feature_id, feature_value_hash, "
                "feature_value_json, "
                "visual_context_entity_revision_id FROM "
                "shot_revision_visual_anchors WHERE shot_revision_id = :r "
                "ORDER BY position"
            ),
            {"r": revision_id},
        )
    ).mappings().all()
    items = (
        await conn.execute(
            text(
                "SELECT anchor_position, item_position, asset_id, "
                "blob_hash, role, view_key FROM "
                "shot_revision_visual_anchor_items "
                "WHERE shot_revision_id = :r "
                "ORDER BY anchor_position, item_position"
            ),
            {"r": revision_id},
        )
    ).mappings().all()
    items_by_anchor: dict[int, list[dict]] = {}
    for it in items:
        items_by_anchor.setdefault(it["anchor_position"], []).append({
            "asset_id": it["asset_id"],
            "blob_hash": it["blob_hash"],
            "role": it["role"],
            "view_key": it["view_key"],
            "position": it["item_position"],
        })

    snap_json = (
        await conn.execute(
            text("SELECT snapshot_json FROM shot_revisions WHERE id = :r"),
            {"r": revision_id},
        )
    ).scalar_one_or_none()
    if snap_json is None:
        raise internal_invariant(
            f"ShotRevision {revision_id} disappeared mid-reconstruction."
        )
    snapshot = json.loads(snap_json)
    if snapshot.get("schema_version") not in (4, 5):
        raise internal_invariant(
            f"ShotRevision {revision_id} is not schema 4/5; M9 authority "
            "reconstruction requires captured visual provenance."
        )
    # M10E §9.2: schema 5 = schema 4 + the captured spatial_continuity
    # pack; the M9 authority plane reads ONLY the embedded
    # visual_reference_pack, which schema 5 preserves verbatim.
    stored_pack = snapshot.get("visual_reference_pack")
    if not isinstance(stored_pack, dict):
        raise internal_invariant(
            f"ShotRevision {revision_id} schema-4/5 snapshot lacks its "
            "visual_reference_pack value."
        )

    rebuilt: dict = {"schema_version": 1, "anchors": []}
    for a in anchors:
        if a["target_kind"] == "entity":
            target = {
                "kind": "entity",
                "entity_id": a["entity_id"],
                "entity_revision_id": a["entity_revision_id"],
            }
        else:
            target = {
                "kind": "feature",
                "feature_id": a["feature_id"],
                "feature_value_hash": a["feature_value_hash"],
                "feature_value_json": a["feature_value_json"],
                "visual_context_entity_revision_id": (
                    a["visual_context_entity_revision_id"]
                ),
            }
        rebuilt["anchors"].append({
            "visual_facet_id": a["visual_facet_id"],
            "facet_key": a["facet_key"],
            "visual_anchor_id": a["visual_anchor_id"],
            "visual_anchor_revision_id": a["visual_anchor_revision_id"],
            "visual_anchor_snapshot_hash": a["visual_anchor_snapshot_hash"],
            "target": target,
            "items": items_by_anchor.get(a["position"], []),
        })

    rebuilt_hash = canonical_hash(rebuilt)
    stored_hash = canonical_hash(stored_pack)
    if rebuilt_hash != stored_hash:
        raise internal_invariant(
            f"ShotRevision {revision_id} captured M8 provenance disagrees "
            f"with its stored visual_reference_pack ({rebuilt_hash} != "
            f"{stored_hash})."
        )
    return rebuilt, rebuilt_hash


async def reconstruct_authority(
    conn: AsyncConnection, revision_id: str, facet_requirements: dict
) -> CapturedVisualAuthority:
    """Historical adapter: validated pack + the requirement map from the
    SAME coherent read that captured the revision. Historical
    reconstruction never reads CURRENT requirement policy (§10.2)."""
    pack, pack_hash = await reconstruct_pack(conn, revision_id)
    return build_captured_authority(pack, facet_requirements)
