"""The ONE current VisualReferenceResolver (frozen plan §§42–52).

Downstream of the frozen M7 semantic resolver/readiness gate — never a
peer resolver. Runs on the caller's connection inside the caller's
coherent read transaction (§44); batch-fetches by ID set (§64); verifies
approved-revision integrity (§48); emits the canonical VisualReferencePack
with the frozen anchor ordering (§50) and hash rules (§51).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.errors import ErrorCode, SoloRingError, internal_invariant

PACK_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ResolvedAnchor:
    """One effective (approved + provenance-valid) anchor entry."""

    visual_facet_id: str
    facet_key: str
    visual_anchor_id: str
    visual_anchor_revision_id: str
    visual_anchor_snapshot_hash: str
    target_kind: str
    entity_id: str | None
    entity_revision_id: str | None
    feature_id: str | None
    feature_value_hash: str | None
    feature_value_json: str | None
    visual_context_entity_revision_id: str | None
    items: tuple[tuple[str, str, str, str | None, int], ...]  # asset,blob,role,view,pos


@dataclass(frozen=True)
class FacetStatus:
    """Per-facet resolution outcome for the inspector (§72)."""

    visual_facet_id: str
    facet_key: str
    target_kind: str
    entity_id: str | None
    feature_id: str | None
    requirement: str  # effective policy after value override
    resolved: str  # 'approved' | 'missing' | 'unapproved' | 'not_applicable'
    visual_anchor_id: str | None = None
    approved_revision_id: str | None = None
    # §72 row payload: primary Asset, reference count, blocking issue,
    # and the CURRENT semantic/design state the facet binds to (the
    # resolved EntityRevision for entity facets; the effective value +
    # visual-context revision for feature facets).
    primary_asset_id: str | None = None
    item_count: int = 0
    issue: dict | None = None
    entity_revision_id: str | None = None
    feature_value_hash: str | None = None
    feature_value_json: str | None = None
    visual_context_entity_revision_id: str | None = None


@dataclass(frozen=True)
class VisualResolutionResult:
    shot_id: str
    visual_continuity_ready: bool
    issues: tuple[dict, ...] = ()
    facet_statuses: tuple[FacetStatus, ...] = ()
    pack: dict | None = None
    visual_reference_pack_hash: str | None = None


def _issue(code: ErrorCode, **details) -> dict:
    return {"error_code": code, **details}


async def _batch_fetch_facets(
    conn: AsyncConnection,
    entity_ids: list[str],
    feature_ids: list[str],
) -> list[dict]:
    """§64.3: one query per target kind, never per target."""
    rows: list[dict] = []
    if entity_ids:
        ph = ", ".join(f":e{i}" for i in range(len(entity_ids)))
        rows += [
            dict(r)
            for r in (
                await conn.execute(
                    text(
                        "SELECT id, project_id, target_kind, entity_id, "
                        "feature_id, facet_key, requirement FROM "
                        f"visual_facets WHERE target_kind = 'entity' "
                        f"AND deleted_at IS NULL AND entity_id IN ({ph})"
                    ),
                    {f"e{i}": e for i, e in enumerate(entity_ids)},
                )
            ).mappings().all()
        ]
    if feature_ids:
        ph = ", ".join(f":f{i}" for i in range(len(feature_ids)))
        rows += [
            dict(r)
            for r in (
                await conn.execute(
                    text(
                        "SELECT id, project_id, target_kind, entity_id, "
                        "feature_id, facet_key, requirement FROM "
                        f"visual_facets WHERE target_kind = 'feature' "
                        f"AND deleted_at IS NULL AND feature_id IN ({ph})"
                    ),
                    {f"f{i}": f for i, f in enumerate(feature_ids)},
                )
            ).mappings().all()
        ]
    return rows


async def _batch_fetch_policies(
    conn: AsyncConnection, facet_ids: list[str]
) -> dict[str, dict[str, str]]:
    """facet_id -> {feature_value_hash: policy}."""
    if not facet_ids:
        return {}
    ph = ", ".join(f":v{i}" for i in range(len(facet_ids)))
    rows = (
        await conn.execute(
            text(
                "SELECT visual_facet_id, feature_value_hash, policy FROM "
                f"visual_facet_value_policies WHERE visual_facet_id IN ({ph})"
            ),
            {f"v{i}": v for i, v in enumerate(facet_ids)},
        )
    ).mappings().all()
    out: dict[str, dict[str, str]] = {}
    for r in rows:
        out.setdefault(r["visual_facet_id"], {})[
            r["feature_value_hash"]
        ] = r["policy"]
    return out


async def _batch_fetch_anchors(
    conn: AsyncConnection,
    entity_bindings: list[tuple[str, str]],   # (facet_id, entity_revision_id)
    feature_bindings: list[tuple[str, str, str]],  # (facet, value_hash, ctx)
) -> list[dict]:
    rows: list[dict] = []
    if entity_bindings:
        conds = " OR ".join(
            f"(visual_facet_id = :ab{i}a AND entity_revision_id = :ab{i}b)"
            for i in range(len(entity_bindings))
        )
        params = {}
        for i, (fid, er) in enumerate(entity_bindings):
            params[f"ab{i}a"] = fid
            params[f"ab{i}b"] = er
        rows += [
            dict(r)
            for r in (
                await conn.execute(
                    text(
                        "SELECT id, visual_facet_id, entity_revision_id, "
                        "feature_value_hash, feature_value_json, "
                        "visual_context_entity_revision_id, "
                        "approved_revision_id FROM visual_anchors "
                        f"WHERE deleted_at IS NULL AND ({conds})"
                    ),
                    params,
                )
            ).mappings().all()
        ]
    if feature_bindings:
        conds = " OR ".join(
            f"(visual_facet_id = :fb{i}a AND feature_value_hash = :fb{i}b "
            f"AND visual_context_entity_revision_id = :fb{i}c)"
            for i in range(len(feature_bindings))
        )
        params = {}
        for i, (fid, vh, ctx) in enumerate(feature_bindings):
            params[f"fb{i}a"] = fid
            params[f"fb{i}b"] = vh
            params[f"fb{i}c"] = ctx
        rows += [
            dict(r)
            for r in (
                await conn.execute(
                    text(
                        "SELECT id, visual_facet_id, entity_revision_id, "
                        "feature_value_hash, feature_value_json, "
                        "visual_context_entity_revision_id, "
                        "approved_revision_id FROM visual_anchors "
                        f"WHERE deleted_at IS NULL AND ({conds})"
                    ),
                    params,
                )
            ).mappings().all()
        ]
    return rows


async def _batch_fetch_revisions(
    conn: AsyncConnection, revision_ids: list[str]
) -> dict[str, dict]:
    """§64.6: ONE query for every candidate approved revision."""
    if not revision_ids:
        return {}
    ph = ", ".join(f":rv{i}" for i in range(len(revision_ids)))
    rows = (
        await conn.execute(
            text(
                "SELECT id, visual_anchor_id, snapshot_json, snapshot_hash "
                f"FROM visual_anchor_revisions WHERE id IN ({ph})"
            ),
            {f"rv{i}": r for i, r in enumerate(revision_ids)},
        )
    ).mappings().all()
    return {r["id"]: dict(r) for r in rows}


async def _batch_fetch_assets(
    conn: AsyncConnection, asset_ids: list[str]
) -> dict[str, dict]:
    """§64.7: ONE query for every referenced Asset (id -> project/blob)."""
    if not asset_ids:
        return {}
    ph = ", ".join(f":a{i}" for i in range(len(asset_ids)))
    rows = (
        await conn.execute(
            text(
                "SELECT id, project_id, blob_hash FROM assets "
                f"WHERE id IN ({ph})"
            ),
            {f"a{i}": a for i, a in enumerate(asset_ids)},
        )
    ).mappings().all()
    return {r["id"]: dict(r) for r in rows}


async def _batch_fetch_blobs(
    conn: AsyncConnection, blob_hashes: list[str]
) -> set[str]:
    """§64.7: ONE query for every referenced Blob identity."""
    if not blob_hashes:
        return set()
    ph = ", ".join(f":b{i}" for i in range(len(blob_hashes)))
    rows = (
        await conn.execute(
            text(f"SELECT hash FROM blobs WHERE hash IN ({ph})"),
            {f"b{i}": b for i, b in enumerate(blob_hashes)},
        )
    ).all()
    return {r[0] for r in rows}


def _verify_approved_revision_inmemory(
    anchor: dict,
    facet: dict,
    rev: dict | None,
    item_rows: list[tuple],
    assets_by_id: dict[str, dict],
    registered_blobs: set[str],
    live_blob_files: set[str],
) -> list[tuple]:
    """§48 integrity gate, fully in-memory over the batch phases.

    Verifies: revision exists and belongs to this VisualAnchor; canonical
    snapshot bytes hash to the stored snapshot_hash; normalized immutable
    item rows exactly project the snapshot; and the referenced
    Asset/Blob provenance remains valid (Asset exists in the owning
    Project, Blob identity is registered, physical bytes exist).
    Corruption fails closed — no approved authority is silently omitted.
    Returns the ordered item tuples for the effective pack.

    ``item_rows`` are the asset-first ``(asset_id, blob_hash, role,
    view_key, position)`` tuples produced by ``_batch_revision_items``.
    """
    revision_id = anchor["approved_revision_id"]
    if rev is None or rev["visual_anchor_id"] != anchor["id"]:
        raise internal_invariant(
            f"approved_revision_id {revision_id} does not resolve to an "
            f"immutable revision of VisualAnchor {anchor['id']}."
        )
    try:
        parsed = json.loads(rev["snapshot_json"])
    except (ValueError, TypeError) as exc:
        raise internal_invariant(
            f"VisualAnchorRevision {revision_id} snapshot_json is "
            f"malformed: {exc}"
        ) from exc
    if (
        hashlib.sha256(
            canonical_json_str(parsed).encode("utf-8")
        ).hexdigest()
        != rev["snapshot_hash"]
    ):
        raise internal_invariant(
            f"VisualAnchorRevision {revision_id} canonical bytes disagree "
            "with its stored snapshot_hash."
        )
    projected = {
        (it["position"], it["asset_id"], it["blob_hash"], it["role"],
         it["view_key"])
        for it in parsed.get("items", [])
    }
    stored = {(pos, asset, blob, role, view)
              for asset, blob, role, view, pos in item_rows}
    if stored != projected:
        raise internal_invariant(
            f"VisualAnchorRevision {revision_id} normalized item rows "
            "disagree with its canonical snapshot."
        )
    primaries = [
        it for it in parsed.get("items", []) if it.get("role") == "primary"
    ]
    if not parsed.get("items") or len(primaries) != 1:
        raise internal_invariant(
            f"VisualAnchorRevision {revision_id} violates the one-primary "
            "capture invariant."
        )
    for it in parsed.get("items", []):
        asset = assets_by_id.get(it["asset_id"])
        if asset is None:
            raise internal_invariant(
                f"VisualAnchorRevision {revision_id} references Asset "
                f"{it['asset_id']}, which no longer exists."
            )
        if asset["project_id"] != facet["project_id"]:
            raise internal_invariant(
                f"VisualAnchorRevision {revision_id} references Asset "
                f"{it['asset_id']} outside the owning Project."
            )
        if asset["blob_hash"] != it["blob_hash"]:
            raise internal_invariant(
                f"VisualAnchorRevision {revision_id} item references Blob "
                f"{it['blob_hash']}, but Asset {it['asset_id']} now points "
                f"at Blob {asset['blob_hash']} — corrupted Asset→Blob "
                "provenance."
            )
        if it["blob_hash"] not in registered_blobs:
            raise internal_invariant(
                f"VisualAnchorRevision {revision_id} references unregistered "
                f"Blob {it['blob_hash']}."
            )
        if it["blob_hash"] not in live_blob_files:
            raise internal_invariant(
                f"Blob {it['blob_hash']} physical bytes are missing — "
                "registered identity with missing bytes is corruption "
                "(§40/§91)."
            )
    ordered = sorted(
        item_rows, key=lambda t: (t[4], t[0])
    )  # position, then asset_id for totality
    return ordered


async def _batch_revision_items(
    conn: AsyncConnection, revision_ids: list[str]
) -> dict[str, list[tuple]]:
    if not revision_ids:
        return {}
    ph = ", ".join(f":r{i}" for i in range(len(revision_ids)))
    rows = (
        await conn.execute(
            text(
                "SELECT visual_anchor_revision_id, position, asset_id, "
                f"blob_hash, role, view_key FROM "
                f"visual_anchor_revision_items "
                f"WHERE visual_anchor_revision_id IN ({ph}) "
                "ORDER BY position"
            ),
            {f"r{i}": r for i, r in enumerate(revision_ids)},
        )
    ).mappings().all()
    out: dict[str, list[tuple]] = {}
    for r in rows:
        out.setdefault(r["visual_anchor_revision_id"], []).append(
            (r["asset_id"], r["blob_hash"], r["role"], r["view_key"],
             r["position"])
        )
    return out


def _anchor_sort_key(a: ResolvedAnchor) -> tuple:
    """§50 ordering: target-kind rank, then semantic coordinates, then
    IDs only as mechanical totality."""
    if a.target_kind == "entity":
        return (
            0, a.entity_id or "", a.entity_revision_id or "",
            a.facet_key, a.visual_facet_id, a.visual_anchor_revision_id,
        )
    return (
        1, a.feature_id or "", a.feature_value_hash or "",
        a.visual_context_entity_revision_id or "", a.facet_key,
        a.visual_facet_id, a.visual_anchor_revision_id,
    )


def _pack_anchor_entry(a: ResolvedAnchor) -> dict:
    if a.target_kind == "entity":
        target = {
            "kind": "entity",
            "entity_id": a.entity_id,
            "entity_revision_id": a.entity_revision_id,
        }
    else:
        target = {
            "kind": "feature",
            "feature_id": a.feature_id,
            "feature_value_hash": a.feature_value_hash,
            "feature_value_json": a.feature_value_json,
            "visual_context_entity_revision_id": (
                a.visual_context_entity_revision_id
            ),
        }
    return {
        "visual_facet_id": a.visual_facet_id,
        "facet_key": a.facet_key,
        "visual_anchor_id": a.visual_anchor_id,
        "visual_anchor_revision_id": a.visual_anchor_revision_id,
        "visual_anchor_snapshot_hash": a.visual_anchor_snapshot_hash,
        "target": target,
        "items": [
            {
                "asset_id": asset, "blob_hash": blob, "role": role,
                "view_key": view, "position": pos,
            }
            for asset, blob, role, view, pos in a.items
        ],
    }


def build_reference_pack(anchors: list[ResolvedAnchor]) -> dict:
    """§49 canonical pack from the effective (approved) anchor set."""
    return {
        "schema_version": PACK_SCHEMA_VERSION,
        "anchors": [
            _pack_anchor_entry(a)
            for a in sorted(anchors, key=_anchor_sort_key)
        ],
    }


async def resolve_visual_reference_pack_async(
    shot_id: str,
    semantic_resolution,
    *,
    conn: AsyncConnection,
    blob_store=None,
) -> VisualResolutionResult:
    """§42 resolver. ``semantic_resolution`` is the already-pinned M7
    result: (resolved_deps, feature_states). The caller has already
    verified M7 readiness — this function NEVER resolves partial visual
    state from unresolved semantics (§52.1 is enforced by the caller).

    ``blob_store`` is the physical-bytes authority. HTTP entry points
    pass the RUNNING APP's store (built from request.app.state.settings
    — r2-gate B2); non-HTTP service callers may omit it, in which case
    the process-level Settings singleton applies.
    """
    resolved_deps = semantic_resolution[0]  # list[ResolvedDependency]
    feature_states = semantic_resolution[1]  # tuple[EffectiveFeatureState]

    # §45: entity facets bind through resolved EntityRevisions.
    entity_ids = sorted({d.entity_id for d in resolved_deps})
    entity_rev_by_entity = {d.entity_id: d.entity_revision_id
                            for d in resolved_deps}
    # §46: feature facets bind through effective values + owner context.
    feature_ids = sorted({s.feature_id for s in feature_states})
    feature_ctx = {s.feature_id: (s.entity_id, s.value_hash)
                   for s in feature_states}

    facets = await _batch_fetch_facets(conn, entity_ids, feature_ids)
    facet_ids = [f["id"] for f in facets]
    policies = await _batch_fetch_policies(conn, facet_ids)

    entity_bindings: list[tuple[str, str]] = []
    feature_bindings: list[tuple[str, str, str]] = []
    facet_targets: dict[str, dict] = {}
    effective_policy: dict[str, str] = {}
    statuses: list[FacetStatus] = []
    issues: list[dict] = []

    feature_value_owners = {
        s.feature_id: s.entity_id for s in feature_states
    }
    for f in facets:
        fid = f["id"]
        facet_targets[fid] = f
        if f["target_kind"] == "entity":
            er = entity_rev_by_entity.get(f["entity_id"])
            effective_policy[fid] = f["requirement"]
            entity_bindings.append((fid, er))
        else:
            owner, vhash = feature_ctx.get(f["feature_id"], (None, None))
            override = policies.get(fid, {}).get(vhash)
            effective_policy[fid] = override or f["requirement"]
            if vhash is not None:
                feature_bindings.append((
                    fid, vhash, entity_rev_by_entity.get(owner),
                ))

    anchors = await _batch_fetch_anchors(
        conn, entity_bindings, feature_bindings
    )
    anchor_by_facet: dict[str, dict] = {}
    for a in anchors:
        anchor_by_facet[a["visual_facet_id"]] = a

    # §64.6–64.7: batch-fetch EVERY applicable approved revision, its
    # immutable items, and the Asset/Blob provenance in bounded query
    # classes — never one query per anchor/revision/item.
    approved_anchor_rows = [
        a for a in anchors if a["approved_revision_id"] is not None
    ]
    approved_ids = [a["approved_revision_id"] for a in approved_anchor_rows]
    revisions_by_id = await _batch_fetch_revisions(conn, approved_ids)
    items_by_rev = await _batch_revision_items(conn, approved_ids)
    referenced_assets = sorted({
        it[0]
        for rows in items_by_rev.values()
        for it in rows
    })
    assets_by_id = await _batch_fetch_assets(conn, referenced_assets)
    referenced_blobs = sorted({
        it[1]
        for rows in items_by_rev.values()
        for it in rows
    })
    registered_blobs = await _batch_fetch_blobs(conn, referenced_blobs)
    if blob_store is None:
        from soloring.assets.blob_store import BlobStore
        from soloring.settings import get_settings

        blob_store = BlobStore(get_settings())
    live_blob_files = {
        h for h in referenced_blobs if blob_store.path_for_hash(h).is_file()
    }

    approved: list[ResolvedAnchor] = []
    feature_state_by_id = {s.feature_id: s for s in feature_states}
    for f in facets:
        fid = f["id"]
        policy = effective_policy[fid]
        # §72: the CURRENT semantic/design state this facet binds to.
        semantic: dict = {}
        if f["target_kind"] == "entity":
            semantic["entity_revision_id"] = entity_rev_by_entity.get(
                f["entity_id"]
            )
        else:
            fstate = feature_state_by_id.get(f["feature_id"])
            if fstate is not None:
                semantic["feature_value_hash"] = fstate.value_hash
                semantic["feature_value_json"] = fstate.value_json
                semantic["visual_context_entity_revision_id"] = (
                    entity_rev_by_entity.get(fstate.entity_id)
                )
        if f["target_kind"] == "feature":
            owner, vhash = feature_ctx.get(f["feature_id"], (None, None))
            if vhash is None:  # feature absent/cleared (§10)
                statuses.append(FacetStatus(
                    visual_facet_id=fid, facet_key=f["facet_key"],
                    target_kind="feature", entity_id=None,
                    feature_id=f["feature_id"],
                    requirement="not_applicable", resolved="not_applicable",
                    **semantic,
                ))
                continue
            if policy == "not_applicable":
                statuses.append(FacetStatus(
                    visual_facet_id=fid, facet_key=f["facet_key"],
                    target_kind="feature", entity_id=None,
                    feature_id=f["feature_id"],
                    requirement="not_applicable", resolved="not_applicable",
                    **semantic,
                ))
                continue

        a = anchor_by_facet.get(fid)
        if a is None:
            if policy == "required":
                issue = _issue(
                    ErrorCode.VISUAL_REALIZATION_REQUIRED,
                    visual_facet_id=fid, facet_key=f["facet_key"],
                )
                issues.append(issue)
                statuses.append(FacetStatus(
                    visual_facet_id=fid, facet_key=f["facet_key"],
                    target_kind=f["target_kind"], entity_id=f["entity_id"],
                    feature_id=f["feature_id"], requirement=policy,
                    resolved="missing", issue=issue, **semantic,
                ))
            else:
                statuses.append(FacetStatus(
                    visual_facet_id=fid, facet_key=f["facet_key"],
                    target_kind=f["target_kind"], entity_id=f["entity_id"],
                    feature_id=f["feature_id"], requirement=policy,
                    resolved="missing", **semantic,
                ))
            continue
        if a["approved_revision_id"] is None:
            if policy == "required":
                issue = _issue(
                    ErrorCode.VISUAL_ANCHOR_APPROVAL_REQUIRED,
                    visual_facet_id=fid, facet_key=f["facet_key"],
                    visual_anchor_id=a["id"],
                )
                issues.append(issue)
            else:
                issue = None
            statuses.append(FacetStatus(
                visual_facet_id=fid, facet_key=f["facet_key"],
                target_kind=f["target_kind"], entity_id=f["entity_id"],
                feature_id=f["feature_id"], requirement=policy,
                resolved="unapproved", visual_anchor_id=a["id"],
                issue=issue if policy == "required" else None, **semantic,
            ))
            continue

        # §48 integrity gate for every applicable approved revision —
        # verified in memory over the batch phases above.
        rev = revisions_by_id.get(a["approved_revision_id"])
        items = _verify_approved_revision_inmemory(
            a, f, rev, items_by_rev.get(a["approved_revision_id"], []),
            assets_by_id, registered_blobs, live_blob_files,
        )
        primary_asset = next(
            (it[0] for it in items if it[2] == "primary"), None
        )
        approved.append(ResolvedAnchor(
            visual_facet_id=fid,
            facet_key=f["facet_key"],
            visual_anchor_id=a["id"],
            visual_anchor_revision_id=a["approved_revision_id"],
            visual_anchor_snapshot_hash=rev["snapshot_hash"],
            target_kind=f["target_kind"],
            entity_id=f["entity_id"],
            entity_revision_id=a["entity_revision_id"],
            feature_id=f["feature_id"],
            feature_value_hash=a["feature_value_hash"],
            feature_value_json=a["feature_value_json"],
            visual_context_entity_revision_id=(
                a["visual_context_entity_revision_id"]
            ),
            items=tuple(items),
        ))
        statuses.append(FacetStatus(
            visual_facet_id=fid, facet_key=f["facet_key"],
            target_kind=f["target_kind"], entity_id=f["entity_id"],
            feature_id=f["feature_id"], requirement=policy,
            resolved="approved", visual_anchor_id=a["id"],
            approved_revision_id=a["approved_revision_id"],
            primary_asset_id=primary_asset, item_count=len(items),
            **semantic,
        ))

    ready = not issues
    pack = None
    pack_hash = None
    if ready and approved:
        pack = build_reference_pack(approved)
        pack_hash = canonical_hash(pack)

    return VisualResolutionResult(
        shot_id=shot_id,
        visual_continuity_ready=ready,
        issues=tuple(issues),
        facet_statuses=tuple(statuses),
        pack=pack,
        visual_reference_pack_hash=pack_hash,
    )
