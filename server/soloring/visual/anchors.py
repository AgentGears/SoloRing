"""VisualAnchor curation: working set, revisions, approval (§§19–36).

M8B extends the M8A detail seam. Every mutation is one fenced BEGIN
IMMEDIATE unit; revision capture is the frozen two-phase contract (§31):
coherent read -> freeze in memory -> canonicalize/hash outside the write
txn -> fenced write with fail-closed reuse integrity (§31.3–31.4).
"""

from __future__ import annotations

import contextlib
import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from soloring.continuity.entities import _translate_op_error
from soloring.domain.ids import is_uuid, new_uuid
from soloring.errors import ErrorCode, SoloRingError, internal_invariant
from soloring.visual.canonical import (
    AnchorBinding,
    WorkingItem,
    build_revision_snapshot,
    revision_snapshot_bytes,
)

ROLES = ("primary", "supporting", "detail", "context")

MAX_REVISION_ATTEMPTS = 5


def _anchor_not_found(anchor_id: str) -> SoloRingError:
    return SoloRingError(
        ErrorCode.VISUAL_ANCHOR_NOT_FOUND,
        f"VisualAnchor {anchor_id} not found.",
        status_code=404,
    )


def _item_invalid(message: str) -> SoloRingError:
    return SoloRingError(
        ErrorCode.VISUAL_ANCHOR_ITEM_INVALID, message, status_code=422
    )


async def _load_anchor_row(conn: AsyncConnection, anchor_id: str) -> dict:
    row = (
        await conn.execute(
            text(
                "SELECT va.id, va.visual_facet_id, va.entity_revision_id, "
                "va.feature_value_hash, va.feature_value_json, "
                "va.visual_context_entity_revision_id, "
                "va.approved_revision_id, va.deleted_at, "
                "vf.project_id, vf.target_kind, vf.facet_key, "
                "vf.entity_id, vf.feature_id "
                "FROM visual_anchors va "
                "JOIN visual_facets vf ON vf.id = va.visual_facet_id "
                "WHERE va.id = :aid"
            ),
            {"aid": anchor_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise _anchor_not_found(anchor_id)
    return dict(row)


async def _load_working_items(conn: AsyncConnection, anchor_id: str):
    rows = (
        await conn.execute(
            text(
                "SELECT vai.asset_id, a.blob_hash, vai.role, vai.view_key, "
                "vai.position FROM visual_anchor_items vai "
                "JOIN assets a ON a.id = vai.asset_id "
                "WHERE vai.visual_anchor_id = :aid ORDER BY vai.position"
            ),
            {"aid": anchor_id},
        )
    ).mappings().all()
    return [
        WorkingItem(
            asset_id=r["asset_id"], blob_hash=r["blob_hash"],
            role=r["role"], view_key=r["view_key"], position=r["position"],
        )
        for r in rows
    ]


def _binding_of(anchor: dict) -> AnchorBinding:
    return AnchorBinding(
        visual_facet_id=anchor["visual_facet_id"],
        facet_key=anchor["facet_key"],
        target_kind=anchor["target_kind"],
        entity_id=anchor["entity_id"],
        feature_id=anchor["feature_id"],
        entity_revision_id=anchor["entity_revision_id"],
        feature_value_hash=anchor["feature_value_hash"],
        feature_value_json=anchor["feature_value_json"],
        visual_context_entity_revision_id=(
            anchor["visual_context_entity_revision_id"]
        ),
    )


def _normalize_view_key(raw: object) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise _item_invalid("view_key must be a string.")
    trimmed = raw.strip()
    if not trimmed:
        return None
    if len(trimmed) > 64:
        raise _item_invalid("view_key must be at most 64 characters.")
    return trimmed


async def put_working_set(session: AsyncSession, anchor_id: str, payload) -> None:
    """Atomic full-set replacement (§23). Server assigns contiguous
    positions 0..N-1 in submitted order; validates roles, one primary,
    same-Project Assets, duplicate rejection."""
    if not is_uuid(anchor_id):
        raise _anchor_not_found(anchor_id)

    seen_assets: set[str] = set()
    primary_count = 0
    prepared: list[dict] = []
    for item in payload.items:
        if item.role not in ROLES:
            raise _item_invalid(
                f"role must be one of {ROLES} (got {item.role!r})."
            )
        if not is_uuid(item.asset_id):
            raise SoloRingError(
                ErrorCode.ASSET_NOT_FOUND,
                f"Asset {item.asset_id} not found.",
                status_code=404,
            )
        if item.asset_id in seen_assets:
            raise _item_invalid(
                f"Asset {item.asset_id} appears more than once."
            )
        seen_assets.add(item.asset_id)
        if item.role == "primary":
            primary_count += 1
        prepared.append({
            "asset_id": item.asset_id,
            "role": item.role,
            "view_key": _normalize_view_key(item.view_key),
        })
    if primary_count > 1:
        raise SoloRingError(
            ErrorCode.VISUAL_ANCHOR_MULTIPLE_PRIMARY,
            "Working set contains more than one primary item.",
            status_code=422,
        )

    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            anchor = await _load_anchor_row(conn, anchor_id)
            if anchor["deleted_at"] is not None:
                raise _anchor_not_found(anchor_id)
            # Every Asset must exist and belong to the same Project (§23.2).
            for p in prepared:
                row = (
                    await conn.execute(
                        text(
                            "SELECT project_id FROM assets "
                            "WHERE id = :aid"
                        ),
                        {"aid": p["asset_id"]},
                    )
                ).first()
                if row is None:
                    raise SoloRingError(
                        ErrorCode.ASSET_NOT_FOUND,
                        f"Asset {p['asset_id']} not found.",
                        status_code=404,
                    )
                if row.project_id != anchor["project_id"]:
                    raise SoloRingError(
                        ErrorCode.VISUAL_ANCHOR_ASSET_PROJECT_MISMATCH,
                        f"Asset {p['asset_id']} belongs to another "
                        "Project.",
                        status_code=409,
                    )
            await conn.execute(
                text(
                    "DELETE FROM visual_anchor_items "
                    "WHERE visual_anchor_id = :aid"
                ),
                {"aid": anchor_id},
            )
            for position, p in enumerate(prepared):
                await conn.execute(
                    text(
                        "INSERT INTO visual_anchor_items "
                        "(visual_anchor_id, asset_id, role, view_key, "
                        " position, created_at) VALUES (:aid, :asset, "
                        ":role, :vk, :pos, "
                        "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
                    ),
                    {
                        "aid": anchor_id, "asset": p["asset_id"],
                        "role": p["role"], "vk": p["view_key"],
                        "pos": position,
                    },
                )
            await conn.execute(
                text(
                    "UPDATE visual_anchors SET updated_at = "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :aid"
                ),
                {"aid": anchor_id},
            )
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _translate_op_error(exc, "working set replacement") from exc


def _capturable(items: list[WorkingItem]) -> bool:
    return len(items) > 0 and sum(
        1 for it in items if it.role == "primary"
    ) == 1


async def _working_provenance_valid(
    conn: AsyncConnection, items: list[WorkingItem]
) -> bool:
    """§33: invalid Asset/Blob provenance makes the working state
    non-capturable. ONE batched Blob-identity query + physical-byte stats
    for the distinct hashes — the detail projection reports the state
    honestly as NULL rather than hashing dead references."""
    from soloring.assets.blob_store import BlobStore
    from soloring.settings import get_settings

    hashes = sorted({it.blob_hash for it in items})
    registered: set[str] = set()
    if hashes:
        ph = ", ".join(f":h{i}" for i in range(len(hashes)))
        rows = (
            await conn.execute(
                text(f"SELECT hash FROM blobs WHERE hash IN ({ph})"),
                {f"h{i}": h for i, h in enumerate(hashes)},
            )
        ).all()
        registered = {r[0] for r in rows}
    store = BlobStore(get_settings())
    for h in hashes:
        if h not in registered:
            return False
        if not store.path_for_hash(h).is_file():
            return False
    return True


async def _read_capture_state(conn: AsyncConnection, anchor_id: str):
    """§31.1 read phase: anchor + items + provenance, fully validated."""
    anchor = await _load_anchor_row(conn, anchor_id)
    if anchor["deleted_at"] is not None:
        raise _anchor_not_found(anchor_id)
    items = await _load_working_items(conn, anchor_id)
    # Provenance: every referenced Blob row + physical file must exist
    # (§31.1) — registered identity with missing bytes is corruption.
    from soloring.assets.blob_store import BlobStore
    from soloring.settings import get_settings

    store = BlobStore(get_settings())
    for it in items:
        blob = (
            await conn.execute(
                text("SELECT hash FROM blobs WHERE hash = :h"),
                {"h": it.blob_hash},
            )
        ).first()
        if blob is None:
            raise internal_invariant(
                f"Asset {it.asset_id} references unregistered Blob "
                f"{it.blob_hash}."
            )
        if not store.path_for_hash(it.blob_hash).is_file():
            raise internal_invariant(
                f"Blob {it.blob_hash} physical bytes are missing — "
                "registered identity with missing bytes is corruption."
            )
    return anchor, items


def _expected_item_rows(items: list[WorkingItem]) -> set[tuple]:
    return {
        (it.position, it.asset_id, it.blob_hash, it.role, it.view_key)
        for it in sorted(items, key=lambda i: (i.position, i.asset_id))
    }


async def capture_revision(session: AsyncSession, anchor_id: str) -> str:
    """Two-phase revision capture (§31): coherent read -> freeze ->
    canonicalize outside the write txn -> fenced write with fail-closed
    reuse validation."""
    if not is_uuid(anchor_id):
        raise _anchor_not_found(anchor_id)

    # Read phase on one explicit coherent read transaction.
    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN")
        try:
            anchor, items = await _read_capture_state(conn, anchor_id)
            await conn.commit()
        except Exception:
            with contextlib.suppress(Exception):
                await conn.rollback()
            raise

    if not _capturable(items):
        if not items:
            raise _item_invalid(
                "Revision capture requires at least one working item."
            )
        raise SoloRingError(
            ErrorCode.VISUAL_ANCHOR_PRIMARY_REQUIRED,
            "Revision capture requires exactly one primary item.",
            status_code=409,
        )

    # Canonicalize/hash phase — outside any write transaction (§31.2).
    snapshot = build_revision_snapshot(_binding_of(anchor), items)
    snapshot_json, snapshot_hash = revision_snapshot_bytes(snapshot)

    # Write phase.
    from soloring.generation.repository import busy_error, is_busy_error

    for _ in range(MAX_REVISION_ATTEMPTS):
        revision_id = new_uuid()
        async with session.bind.connect() as conn:
            try:
                await conn.exec_driver_sql("BEGIN IMMEDIATE")
                existing = (
                    await conn.execute(
                        text(
                            "SELECT id, snapshot_json FROM "
                            "visual_anchor_revisions "
                            "WHERE visual_anchor_id = :aid "
                            "AND snapshot_hash = :h"
                        ),
                        {"aid": anchor_id, "h": snapshot_hash},
                    )
                ).first()
                if existing is not None:
                    # Reuse integrity (§31.3): stored bytes must equal the
                    # recomputed canonical bytes AND the normalized item
                    # rows must exactly project them.
                    if existing.snapshot_json != snapshot_json:
                        raise internal_invariant(
                            f"VisualAnchorRevision {existing.id} reuse: "
                            "stored snapshot_json disagrees with the "
                            "recomputed canonical bytes."
                        )
                    item_rows = (
                        await conn.execute(
                            text(
                                "SELECT position, asset_id, blob_hash, "
                                "role, view_key FROM "
                                "visual_anchor_revision_items "
                                "WHERE visual_anchor_revision_id = :rid"
                            ),
                            {"rid": existing.id},
                        )
                    ).all()
                    stored = set(item_rows)
                    if stored != _expected_item_rows(items):
                        raise internal_invariant(
                            f"VisualAnchorRevision {existing.id} reuse: "
                            "normalized item rows disagree with the "
                            "recomputed snapshot projection."
                        )
                    await conn.exec_driver_sql("COMMIT")
                    return existing.id

                number = (
                    await conn.execute(
                        text(
                            "SELECT COALESCE(MAX(revision_number), 0) + 1 "
                            "FROM visual_anchor_revisions "
                            "WHERE visual_anchor_id = :aid"
                        ),
                        {"aid": anchor_id},
                    )
                ).scalar()
                await conn.execute(
                    text(
                        "INSERT INTO visual_anchor_revisions "
                        "(id, visual_anchor_id, revision_number, "
                        " snapshot_json, snapshot_hash, created_at) "
                        "VALUES (:id, :aid, :num, :sj, :sh, "
                        "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
                    ),
                    {
                        "id": revision_id, "aid": anchor_id,
                        "num": number, "sj": snapshot_json,
                        "sh": snapshot_hash,
                    },
                )
                for it in sorted(
                    items, key=lambda i: (i.position, i.asset_id)
                ):
                    await conn.execute(
                        text(
                            "INSERT INTO visual_anchor_revision_items "
                            "(visual_anchor_revision_id, position, "
                            " asset_id, blob_hash, role, view_key) "
                            "VALUES (:rid, :pos, :asset, :bh, :role, :vk)"
                        ),
                        {
                            "rid": revision_id, "pos": it.position,
                            "asset": it.asset_id, "bh": it.blob_hash,
                            "role": it.role, "vk": it.view_key,
                        },
                    )
                await conn.exec_driver_sql("COMMIT")
                return revision_id
            except Exception as exc:
                with contextlib.suppress(Exception):
                    await conn.exec_driver_sql("ROLLBACK")
                from sqlalchemy.exc import IntegrityError, OperationalError

                if isinstance(exc, IntegrityError):
                    continue
                if isinstance(exc, OperationalError) and is_busy_error(exc):
                    raise busy_error() from exc
                if isinstance(exc, SoloRingError):
                    raise
                raise _translate_op_error(
                    exc, "visual anchor revision capture"
                ) from exc

    raise internal_invariant(
        "Visual anchor revision capture exhausted retries."
    )


async def _verify_revision_integrity(
    conn: AsyncConnection, revision_id: str, anchor: dict
) -> dict:
    """§34 integrity gate: canonical(snapshot_json) hashes to
    snapshot_hash AND normalized item rows exactly project the snapshot."""
    rev = (
        await conn.execute(
            text(
                "SELECT id, visual_anchor_id, snapshot_json, "
                "snapshot_hash FROM visual_anchor_revisions "
                "WHERE id = :rid"
            ),
            {"rid": revision_id},
        )
    ).mappings().one_or_none()
    if rev is None:
        raise SoloRingError(
            ErrorCode.VISUAL_ANCHOR_REVISION_NOT_FOUND,
            f"VisualAnchorRevision {revision_id} not found.",
            status_code=404,
        )
    if rev["visual_anchor_id"] != anchor["id"]:
        raise internal_invariant(
            f"VisualAnchorRevision {revision_id} does not belong to "
            f"VisualAnchor {anchor['id']}."
        )
    try:
        import hashlib

        from soloring.domain.canonical import canonical_json_bytes

        parsed = json.loads(rev["snapshot_json"])
        digest = hashlib.sha256(
            canonical_json_bytes(parsed)
        ).hexdigest()
    except (ValueError, TypeError) as exc:
        raise internal_invariant(
            f"VisualAnchorRevision {revision_id} snapshot_json is "
            f"malformed: {exc}"
        ) from exc
    if digest != rev["snapshot_hash"]:
        raise internal_invariant(
            f"VisualAnchorRevision {revision_id} snapshot bytes disagree "
            "with its stored snapshot_hash."
        )
    item_rows = (
        await conn.execute(
            text(
                "SELECT position, asset_id, blob_hash, role, view_key "
                "FROM visual_anchor_revision_items "
                "WHERE visual_anchor_revision_id = :rid"
            ),
            {"rid": revision_id},
        )
    ).all()
    projected = {
        (it["position"], it["asset_id"], it["blob_hash"], it["role"],
         it["view_key"])
        for it in parsed.get("items", [])
    }
    if {(r[0], r[1], r[2], r[3], r[4]) for r in item_rows} != projected:
        raise internal_invariant(
            f"VisualAnchorRevision {revision_id} normalized item rows "
            "disagree with its canonical snapshot."
        )
    primary = sum(
        1 for it in parsed.get("items", []) if it.get("role") == "primary"
    )
    if len(parsed.get("items", [])) == 0 or primary != 1:
        raise internal_invariant(
            f"VisualAnchorRevision {revision_id} violates the one-primary "
            "capture invariant."
        )
    return dict(rev)


async def approve_revision(
    session: AsyncSession, revision_id: str, expected: str | None
) -> None:
    """§34: explicit approval with expected pointer, idempotent re-approval."""
    if not is_uuid(revision_id):
        raise SoloRingError(
            ErrorCode.VISUAL_ANCHOR_REVISION_NOT_FOUND,
            f"VisualAnchorRevision {revision_id} not found.",
            status_code=404,
        )
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            anchor_id = (
                await conn.execute(
                    text(
                        "SELECT visual_anchor_id FROM "
                        "visual_anchor_revisions WHERE id = :rid"
                    ),
                    {"rid": revision_id},
                )
            ).scalar_one_or_none()
            if anchor_id is None:
                raise SoloRingError(
                    ErrorCode.VISUAL_ANCHOR_REVISION_NOT_FOUND,
                    f"VisualAnchorRevision {revision_id} not found.",
                    status_code=404,
                )
            anchor = await _load_anchor_row(conn, anchor_id)
            if anchor["deleted_at"] is not None:
                raise _anchor_not_found(anchor_id)
            await _verify_revision_integrity(conn, revision_id, anchor)
            if anchor["approved_revision_id"] == revision_id:
                await conn.exec_driver_sql("COMMIT")  # idempotent 200
                return
            if (anchor["approved_revision_id"] or None) != (
                expected or None
            ):
                raise SoloRingError(
                    ErrorCode.VISUAL_ANCHOR_APPROVAL_CONFLICT,
                    "expected_approved_revision_id no longer matches the "
                    "stored approval pointer.",
                    status_code=409,
                )
            await conn.execute(
                text(
                    "UPDATE visual_anchors SET approved_revision_id = :rid,"
                    " updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                    "WHERE id = :aid"
                ),
                {"rid": revision_id, "aid": anchor_id},
            )
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _translate_op_error(exc, "revision approval") from exc


async def unapprove_anchor(
    session: AsyncSession, anchor_id: str, expected: str | None
) -> None:
    """§35: explicit unapproval, idempotent when already NULL."""
    if not is_uuid(anchor_id):
        raise _anchor_not_found(anchor_id)
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            anchor = await _load_anchor_row(conn, anchor_id)
            if anchor["deleted_at"] is not None:
                raise _anchor_not_found(anchor_id)
            current = anchor["approved_revision_id"]
            if current is None:
                await conn.exec_driver_sql("COMMIT")  # idempotent 200
                return
            if (current or None) != (expected or None):
                raise SoloRingError(
                    ErrorCode.VISUAL_ANCHOR_APPROVAL_CONFLICT,
                    "expected_approved_revision_id no longer matches the "
                    "stored approval pointer.",
                    status_code=409,
                )
            await conn.execute(
                text(
                    "UPDATE visual_anchors SET approved_revision_id = NULL, "
                    "updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                    "WHERE id = :aid"
                ),
                {"aid": anchor_id},
            )
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _translate_op_error(exc, "anchor unapproval") from exc


async def list_revisions(
    session: AsyncSession, anchor_id: str
) -> list[dict]:
    if not is_uuid(anchor_id):
        raise _anchor_not_found(anchor_id)
    async with session.bind.connect() as conn:
        await _load_anchor_row(conn, anchor_id)
        rows = (
            await conn.execute(
                text(
                    "SELECT id, visual_anchor_id, revision_number, "
                    "snapshot_hash, created_at FROM "
                    "visual_anchor_revisions WHERE visual_anchor_id = :aid "
                    "ORDER BY revision_number"
                ),
                {"aid": anchor_id},
            )
        ).mappings().all()
        return [dict(r) for r in rows]


async def get_revision(session: AsyncSession, revision_id: str) -> dict:
    if not is_uuid(revision_id):
        raise SoloRingError(
            ErrorCode.VISUAL_ANCHOR_REVISION_NOT_FOUND,
            f"VisualAnchorRevision {revision_id} not found.",
            status_code=404,
        )
    async with session.bind.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT id, visual_anchor_id, revision_number, "
                    "snapshot_json, snapshot_hash, created_at FROM "
                    "visual_anchor_revisions WHERE id = :rid"
                ),
                {"rid": revision_id},
            )
        ).mappings().one_or_none()
    if row is None:
        raise SoloRingError(
            ErrorCode.VISUAL_ANCHOR_REVISION_NOT_FOUND,
            f"VisualAnchorRevision {revision_id} not found.",
            status_code=404,
        )
    return dict(row)


async def get_anchor_detail(session: AsyncSession, anchor_id: str) -> dict:
    """§33 detail: anchor + ordered items + working/approved hashes +
    differs — all server-computed through the ONE builder."""
    if not is_uuid(anchor_id):
        raise _anchor_not_found(anchor_id)
    async with session.bind.connect() as conn:
        anchor = await _load_anchor_row(conn, anchor_id)
        if anchor["deleted_at"] is not None:
            raise _anchor_not_found(anchor_id)
        items = await _load_working_items(conn, anchor_id)
        working_hash = None
        if _capturable(items) and await _working_provenance_valid(
            conn, items
        ):
            snapshot = build_revision_snapshot(
                _binding_of(anchor), items
            )
            working_hash = revision_snapshot_bytes(snapshot)[1]
        approved_hash = None
        if anchor["approved_revision_id"] is not None:
            approved = (
                await conn.execute(
                    text(
                        "SELECT snapshot_hash FROM "
                        "visual_anchor_revisions WHERE id = :rid"
                    ),
                    {"rid": anchor["approved_revision_id"]},
                )
            ).scalar_one_or_none()
            if approved is None:
                raise internal_invariant(
                    f"VisualAnchor {anchor_id} approved_revision_id "
                    "points at a missing revision."
                )
            approved_hash = approved
    return {
        "id": anchor["id"],
        "visual_facet_id": anchor["visual_facet_id"],
        "entity_revision_id": anchor["entity_revision_id"],
        "feature_value_hash": anchor["feature_value_hash"],
        "feature_value_json": anchor["feature_value_json"],
        "visual_context_entity_revision_id": (
            anchor["visual_context_entity_revision_id"]
        ),
        "approved_revision_id": anchor["approved_revision_id"],
        "created_at": None,  # filled by the route from the base row
        "updated_at": None,
        "items": [
            {
                "asset_id": it.asset_id, "role": it.role,
                "view_key": it.view_key, "position": it.position,
            }
            for it in items
        ],
        "working_snapshot_hash": working_hash,
        "approved_snapshot_hash": approved_hash,
        "working_state_differs_from_approved": (
            None
            if (working_hash is None or approved_hash is None)
            else working_hash != approved_hash
        ),
    }
