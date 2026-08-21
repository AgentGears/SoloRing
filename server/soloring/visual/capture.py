"""Schema-4 ShotRevision visual child persistence + reuse validation
(frozen plan §§56–57).

Rows are immutable projections written from the SAME frozen in-memory
visual pack that produced the canonical schema-4 bytes — never a second
authority. Reuse validation compares the stored projection exactly.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from soloring.errors import internal_invariant


def _expected_anchor_rows(pack: dict) -> set[tuple]:
    """Semantic projection of the canonical pack anchors (§57), in the
    pack's own canonical order — position-authoritative."""
    out = set()
    for pos, anchor in enumerate(pack.get("anchors", [])):
        target = anchor["target"]
        out.add((
            pos,
            anchor["visual_facet_id"],
            anchor["facet_key"],
            anchor["visual_anchor_id"],
            anchor["visual_anchor_revision_id"],
            anchor["visual_anchor_snapshot_hash"],
            target["kind"],
            target.get("entity_id"),
            target.get("entity_revision_id"),
            target.get("feature_id"),
            target.get("feature_value_hash"),
            target.get("feature_value_json"),
            target.get("visual_context_entity_revision_id"),
        ))
    return out


def _expected_item_rows(pack: dict) -> set[tuple]:
    out = set()
    for apos, anchor in enumerate(pack.get("anchors", [])):
        for it in anchor.get("items", []):
            out.add((
                apos,
                it["position"],
                it["asset_id"],
                it["blob_hash"],
                it["role"],
                it["view_key"],
            ))
    return out


async def persist_visual_children(
    conn: AsyncConnection, revision_id: str, pack: dict
) -> None:
    """Insert shot_revision_visual_anchors + _items from the frozen pack.

    Positions derive from the pack's canonical anchor order (§50) — the
    caller passes the already-sorted canonical pack."""
    for pos, anchor in enumerate(pack.get("anchors", [])):
        target = anchor["target"]
        await conn.execute(
            text(
                "INSERT INTO shot_revision_visual_anchors "
                "(shot_revision_id, position, visual_facet_id, facet_key, "
                " visual_anchor_id, visual_anchor_revision_id, "
                " visual_anchor_snapshot_hash, target_kind, entity_id, "
                " entity_revision_id, feature_id, feature_value_hash, "
                " feature_value_json, "
                " visual_context_entity_revision_id) VALUES "
                "(:rid, :pos, :fid, :fkey, :aid, :rev, :revh, :kind, "
                ":eid, :erid, :featid, :vh, :vj, :ctx)"
            ),
            {
                "rid": revision_id, "pos": pos,
                "fid": anchor["visual_facet_id"],
                "fkey": anchor["facet_key"],
                "aid": anchor["visual_anchor_id"],
                "rev": anchor["visual_anchor_revision_id"],
                "revh": anchor["visual_anchor_snapshot_hash"],
                "kind": target["kind"],
                "eid": target.get("entity_id"),
                "erid": target.get("entity_revision_id"),
                "featid": target.get("feature_id"),
                "vh": target.get("feature_value_hash"),
                "vj": target.get("feature_value_json"),
                "ctx": target.get("visual_context_entity_revision_id"),
            },
        )
        for it in anchor.get("items", []):
            await conn.execute(
                text(
                    "INSERT INTO shot_revision_visual_anchor_items "
                    "(shot_revision_id, anchor_position, item_position, "
                    " asset_id, blob_hash, role, view_key) VALUES "
                    "(:rid, :apos, :ipos, :asset, :bh, :role, :vk)"
                ),
                {
                    "rid": revision_id, "apos": pos,
                    "ipos": it["position"], "asset": it["asset_id"],
                    "bh": it["blob_hash"], "role": it["role"],
                    "vk": it["view_key"],
                },
            )


async def validate_visual_reuse(
    conn: AsyncConnection, revision_id: str, pack: dict | None
) -> None:
    """§57 reuse extension: stored visual rows must exactly project the
    recomputed pack (or both be empty). Any mismatch is
    INTERNAL_INVARIANT_VIOLATION — no repair, no recapture."""
    expected_anchors = _expected_anchor_rows(pack) if pack else set()
    expected_items = _expected_item_rows(pack) if pack else set()

    anchor_rows = (
        await conn.execute(
            text(
                "SELECT position, visual_facet_id, facet_key, "
                "visual_anchor_id, visual_anchor_revision_id, "
                "visual_anchor_snapshot_hash, target_kind, entity_id, "
                "entity_revision_id, feature_id, feature_value_hash, "
                "feature_value_json, visual_context_entity_revision_id "
                "FROM shot_revision_visual_anchors "
                "WHERE shot_revision_id = :rid"
            ),
            {"rid": revision_id},
        )
    ).all()
    stored_anchors = set(anchor_rows)
    if stored_anchors != expected_anchors:
        raise internal_invariant(
            f"ShotRevision {revision_id} reuse: stored visual anchor "
            "projection disagrees with the recomputed visual pack."
        )

    item_rows = (
        await conn.execute(
            text(
                "SELECT anchor_position, item_position, asset_id, "
                "blob_hash, role, view_key FROM "
                "shot_revision_visual_anchor_items "
                "WHERE shot_revision_id = :rid"
            ),
            {"rid": revision_id},
        )
    ).all()
    if set(item_rows) != expected_items:
        raise internal_invariant(
            f"ShotRevision {revision_id} reuse: stored visual item "
            "projection disagrees with the recomputed visual pack."
        )
