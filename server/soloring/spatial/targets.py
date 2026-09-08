"""M10-owned CreativeEntity A4 target classification (frozen M13 R3 §10.1).

ONE primitive classifying the exact CreativeEntity target set for an exact
SpatialWorldRevision, using the same M10 authority semantics as current
spatial resolution: fixed frames come from the verified revision snapshot;
SpatialTrack authority comes from the applicable active tracks in the
world (a Track is a competing placement authority even when its current
temporal state is absent — the resolver's P0-1 rule). M13 binding
derivation consumes this primitive instead of inventing a second
eligibility algorithm.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from soloring.errors import ErrorCode, SoloRingError
from soloring.spatial.revisions import load_verified_world_revision


async def load_world_revision_with_world(
    conn: AsyncConnection, *, spatial_world_revision_id: str,
) -> dict:
    """Verified W plus its owning world identity and Project.

    Raises 404 (not corruption) when the revision does not exist; a row
    that exists but fails the verified reader raises the invariant error.
    """
    row = (
        await conn.execute(
            text(
                "SELECT r.id, r.spatial_world_state_id, w.id AS world_id, "
                "w.project_id FROM spatial_world_revisions r "
                "JOIN spatial_world_states st "
                "ON st.id = r.spatial_world_state_id "
                "JOIN spatial_worlds w ON w.id = st.spatial_world_id "
                "WHERE r.id = :rid"),
            {"rid": spatial_world_revision_id},
        )
    ).first()
    if row is None:
        raise SoloRingError(
            ErrorCode.SPATIAL_WORLD_REVISION_NOT_FOUND,
            f"SpatialWorldRevision {spatial_world_revision_id!r} not found.",
            status_code=404)
    verified = await load_verified_world_revision(
        conn, spatial_world_state_id=row.spatial_world_state_id,
        spatial_world_revision_id=row.id)
    return {"verified": verified, "world_id": row.world_id,
            "project_id": row.project_id}


async def classify_entity_a4_targets(
    conn: AsyncConnection, *, world: dict, entity_ids: list[str],
) -> dict[str, list[dict]]:
    """Exact M10 target classification for (W, entity) — §10.1.

    ``world`` is the value returned by ``load_world_revision_with_world``.
    Returns entity_id -> ordered list of
    ``{"kind": "entity_fixed_frame"|"entity_track", "id": ...}``
    candidates. The caller applies the frozen 0/1/>1 classification; this
    primitive only reports the exact candidate set, mirroring the
    resolver's fixed-frame ∪ applicable-track semantics.
    """
    wanted = set(entity_ids)
    out: dict[str, list[dict]] = {e: [] for e in entity_ids}
    if not wanted:
        return out
    # fixed frames: the verified revision snapshot (immutable authority)
    for fr in world["verified"]["snapshot"]["frames"]:
        eid = fr["bound_entity_id"]
        if eid in wanted:
            out[eid].append({"kind": "entity_fixed_frame",
                             "id": fr["spatial_frame_id"]})
    # SpatialTrack authority: applicable active tracks in the world —
    # independent of temporal staging outcome (resolver P0-1)
    ph = ", ".join(f":e{i}" for i in range(len(wanted)))
    params = {f"e{i}": e for i, e in enumerate(sorted(wanted))}
    rows = (
        await conn.execute(
            text(
                f"SELECT id, entity_id FROM spatial_tracks "
                f"WHERE spatial_world_id = :w AND deleted_at IS NULL "
                f"AND entity_id IN ({ph})"),
                {"w": world["world_id"], **params},
        )
    ).fetchall()
    for r in rows:
        out[r.entity_id].append({"kind": "entity_track", "id": r.id})
    for eid in out:
        out[eid].sort(key=lambda t: (t["kind"], t["id"]))
    return out
