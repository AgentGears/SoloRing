"""Composition publication readiness + fenced publish + verified readers.

One builder (composition.canonical.build_snapshot_value) serves readiness,
publication, winner validation, historical verification, and recovery.
Dependency closure is INDEPENDENTLY rederived from direct sources and each
direct nested revision's frozen normalized dependency rows (frozen §11).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.composition.canonical import (
    WorkingSpec,
    build_snapshot_value,
    snapshot_hash,
)
from soloring.composition.service import (
    EditConflict,
    _require_composition,
    _terminated_ids,
)
from soloring.domain.canonical import canonical_hash, canonical_json_bytes
from soloring.domain.ids import new_uuid
from soloring.db.timeutil import DB_NOW_SQL
from soloring.errors import ErrorCode, SoloRingError, internal_invariant, not_found
from soloring.spatial.math import Transform, JS_SAFE_MIN, JS_SAFE_MAX, UDEG_MIN

COMPOSITION_EMPTY = "COMPOSITION_EMPTY"

_SNAPSHOT_SCHEMA_VERSIONS = (1,)


def _row_to_spec(row) -> WorkingSpec:
    if row.source_kind == "production_revision":
        rid = row.production_revision_id
    else:
        rid = row.nested_composition_revision_id
    return WorkingSpec(
        display_name=row.display_name,
        source_kind=row.source_kind,
        revision_id=rid,
        visible=bool(row.visible),
        transform=Transform(
            translation_mm=(row.x_mm, row.y_mm, row.z_mm),
            rotation_udeg=(row.yaw_udeg, row.pitch_udeg, row.roll_udeg),
        ),
    )


async def _load_working(conn, composition_id: str):
    """Coherent load: working rows + lineage termination + source ownership."""
    rows = (
        await conn.execute(
            text(
                "SELECT w.* FROM composition_working_occurrences w "
                "WHERE w.composition_id = :cid ORDER BY w.occurrence_id"
            ),
            {"cid": composition_id},
        )
    ).fetchall()
    if not rows:
        return [], set(), {}
    ids = [r.occurrence_id for r in rows]
    terminated = await _terminated_ids(conn, composition_id, ids)
    prod_ids = [r.production_revision_id for r in rows
                if r.source_kind == "production_revision"]
    nested_ids = [r.nested_composition_revision_id for r in rows
                  if r.source_kind == "composition_revision"]
    ownership: dict[str, str] = {}
    if prod_ids:
        found = (
            await conn.execute(
                text(
                    "SELECT pr.id, po.project_id AS project_id "
                    "FROM production_revisions pr "
                    "JOIN production_objects po ON po.id = pr.production_object_id "
                    "WHERE pr.id IN ("
                    + ",".join(f":p{n}" for n in range(len(prod_ids))) + ")"
                ),
                {f"p{n}": i for n, i in enumerate(prod_ids)},
            )
        ).fetchall()
        for f in found:
            ownership[f.id] = f.project_id
    if nested_ids:
        found = (
            await conn.execute(
                text(
                    "SELECT cr.id, c.project_id AS project_id "
                    "FROM composition_revisions cr "
                    "JOIN compositions c ON c.id = cr.composition_id "
                    "WHERE cr.id IN ("
                    + ",".join(f":n{n}" for n in range(len(nested_ids))) + ")"
                ),
                {f"n{n}": i for n, i in enumerate(nested_ids)},
            )
        ).fetchall()
        for f in found:
            ownership[f.id] = f.project_id
    return rows, terminated, ownership


async def _derive_dependencies(conn, rows):
    """Independently rederived direct + flattened closure (frozen §11.2/11.3).

    Set-oriented: all direct nested revision IDs are gathered first and
    their frozen closure rows resolved in ONE bounded query per dependency
    family — never per-nested-revision round trips (frozen §18).
    """
    prod = set()
    nested_ids = set()
    for r in rows:
        if r.source_kind == "production_revision":
            prod.add(r.production_revision_id)
        else:
            nested_ids.add(r.nested_composition_revision_id)
    if nested_ids:
        ids = list(nested_ids)
        ph = ",".join(f":n{i}" for i in range(len(ids)))
        prod.update(r[0] for r in (await conn.execute(
            text(
                "SELECT d.production_revision_id FROM "
                "composition_revision_production_dependencies d "
                f"WHERE d.composition_revision_id IN ({ph})"
            ),
            {f"n{i}": v for i, v in enumerate(ids)},
        )).fetchall())
        nested_ids.update(r[0] for r in (await conn.execute(
            text(
                "SELECT d.nested_composition_revision_id FROM "
                "composition_revision_nested_dependencies d "
                f"WHERE d.composition_revision_id IN ({ph})"
            ),
            {f"n{i}": v for i, v in enumerate(ids)},
        )).fetchall())
    return sorted(prod), sorted(nested_ids)


async def _validate_working_composition_integrity(
    conn, composition_id: str, comp: dict, rows, terminated, ownership,
) -> None:
    """The one shared working-state integrity predicate (frozen §9.1).

    Active Project, Composition ownership, every source exists and belongs
    to the Project, direct AND transitive self-lineage forbidden,
    terminated-working forbidden, AND the persisted working-row grammar
    (name/source/transform exact integer domains, JS-safe bounds,
    already-canonical rotation) validates BEFORE any canonicalization —
    so a corrupt raw row (e.g. yaw = +180000000) can never be copied into
    immutable authority by publication. Readiness, publish freeze, and the
    fenced phase all call this.
    """
    if terminated:
        raise internal_invariant(
            "terminated occurrence remains in working state",
            details={"occurrence_ids": sorted(terminated)},
        )
    nested_ids = []
    for r in rows:
        # persisted grammar: exact XOR source columns
        if r.source_kind == "production_revision":
            if r.production_revision_id is None \
                    or r.nested_composition_revision_id is not None:
                raise internal_invariant(
                    "working row violates source XOR grammar",
                    details={"occurrence_id": r.occurrence_id})
        elif r.source_kind == "composition_revision":
            if r.production_revision_id is not None \
                    or r.nested_composition_revision_id is None:
                raise internal_invariant(
                    "working row violates source XOR grammar",
                    details={"occurrence_id": r.occurrence_id})
        else:
            raise internal_invariant(
                "working row has unknown source_kind",
                details={"occurrence_id": r.occurrence_id,
                         "source_kind": r.source_kind})
        # persisted grammar: normalized display name
        name = r.display_name
        if not isinstance(name, str) or not (
                1 <= len(name.strip()) <= 500 and name == name.strip()):
            raise internal_invariant(
                "working row display_name violates grammar",
                details={"occurrence_id": r.occurrence_id})
        # persisted grammar: JS-safe integers + CANONICAL rotation — the
        # raw stored values, before Transform re-normalizes them.
        for v in (r.x_mm, r.y_mm, r.z_mm,
                  r.yaw_udeg, r.pitch_udeg, r.roll_udeg):
            if not isinstance(v, int) or not (JS_SAFE_MIN <= v <= JS_SAFE_MAX):
                raise internal_invariant(
                    "working row transform outside JS-safe domain",
                    details={"occurrence_id": r.occurrence_id})
        for v in (r.yaw_udeg, r.pitch_udeg, r.roll_udeg):
            if not (UDEG_MIN <= v < UDEG_MIN + 360_000_000):
                raise internal_invariant(
                    "working row rotation not canonically normalized "
                    "(e.g. +180000000 stored raw)",
                    details={"occurrence_id": r.occurrence_id,
                             "value": v})
        if r.visible not in (0, 1):
            raise internal_invariant(
                "working row visible flag invalid",
                details={"occurrence_id": r.occurrence_id})
        rid = (r.production_revision_id
               if r.source_kind == "production_revision"
               else r.nested_composition_revision_id)
        if rid is None or ownership.get(rid) != comp["project_id"]:
            raise internal_invariant(
                "working source row violates project coherence",
                details={"occurrence_id": r.occurrence_id, "source": rid},
            )
        if r.source_kind == "composition_revision":
            nested_ids.append(rid)
    if nested_ids:
        ph = ",".join(f":n{i}" for i in range(len(nested_ids)))
        clash = (await conn.execute(
            text(
                "SELECT COUNT(*) FROM composition_revisions cr "
                f"WHERE cr.id IN ({ph}) AND cr.composition_id = :cid"
            ),
            {**{f"n{i}": v for i, v in enumerate(nested_ids)},
             "cid": composition_id},
        )).scalar_one()
        if clash:
            raise internal_invariant(
                "direct self-lineage nested source persisted",
                details={"composition_id": composition_id},
            )
        # Transitive self-lineage: any revision in a nested source's frozen
        # closure owned by THIS Composition (frozen §3.8/§11.5).
        tclash = (await conn.execute(
            text(
                "SELECT COUNT(*) FROM "
                "composition_revision_nested_dependencies d "
                "JOIN composition_revisions cr "
                "ON cr.id = d.nested_composition_revision_id "
                f"WHERE d.composition_revision_id IN ({ph}) "
                "AND cr.composition_id = :cid"
            ),
            {**{f"n{i}": v for i, v in enumerate(nested_ids)},
             "cid": composition_id},
        )).scalar_one()
        if tclash:
            raise internal_invariant(
                "transitive same-lineage embedding in working state",
                details={"composition_id": composition_id},
            )


async def resolve_publication_readiness(
    session: AsyncSession, composition_id: str
) -> dict:
    """Frozen §9: one coherent read; COMPOSITION_EMPTY is the only ordinary
    blocker; malformed persisted state is INTERNAL_INVARIANT_VIOLATION."""
    async with session.bind.connect() as conn:
        comp = await _require_composition(conn, composition_id)
        rows, terminated, ownership = await _load_working(conn, composition_id)
        if not rows:
            return {
                "ready": False,
                "working_version": comp["working_version"],
                "issues": [{"code": COMPOSITION_EMPTY,
                            "message": "empty working state cannot publish"}],
                "proposed_snapshot_hash": None,
            }
        await _validate_working_composition_integrity(
            conn, composition_id, comp, rows, terminated, ownership)
        prod_deps, nested_deps = await _derive_dependencies(conn, rows)
        specs = [_row_to_spec(r) for r in rows]
        value = build_snapshot_value(
            specs, [r.occurrence_id for r in rows], prod_deps, nested_deps,
        )
    return {
        "ready": True,
        "working_version": comp["working_version"],
        "issues": [],
        "proposed_snapshot_hash": snapshot_hash(value),
        "occurrence_count": len(rows),
        "direct_production_source_count": sum(
            1 for r in rows if r.source_kind == "production_revision"),
        "direct_nested_source_count": sum(
            1 for r in rows if r.source_kind == "composition_revision"),
        "flattened_production_dependency_count": len(prod_deps),
        "flattened_nested_dependency_count": len(nested_deps),
    }


async def publish_composition_revision(
    session: AsyncSession, composition_id: str, *, expected_working_version: int
) -> tuple[dict, bool]:
    """Frozen §10: coherent freeze → canonicalize outside fence → writer fence."""
    async with session.bind.connect() as conn:
        comp = await _require_composition(conn, composition_id)
        rows, terminated, ownership = await _load_working(conn, composition_id)
        if not rows:
            raise SoloRingError(
                ErrorCode.COMPOSITION_NOT_READY,
                "empty working state cannot publish",
                status_code=409,
                details={"issues": [{"code": COMPOSITION_EMPTY}]},
            )
        await _validate_working_composition_integrity(
            conn, composition_id, comp, rows, terminated, ownership)
        if comp["working_version"] != expected_working_version:
            raise EditConflict(
                "stale_working_version",
                "working state changed since read; refetch and retry",
            )
        prod_deps, nested_deps = await _derive_dependencies(conn, rows)
        specs = [_row_to_spec(r) for r in rows]
        value = build_snapshot_value(
            specs, [r.occurrence_id for r in rows], prod_deps, nested_deps,
        )
    sj = canonical_json_bytes(value).decode("utf-8")
    sh = snapshot_hash(value)

    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        # Fenced revalidation (frozen §10.2): active Project, Composition
        # existence, working_version — plus the full working-integrity
        # predicate so no invalid authority can be committed even when a
        # corrupt working row changed nothing observable to the freeze.
        fenced_comp = await _require_composition(conn, composition_id)
        fenced_rows, fenced_terminated, fenced_ownership = await _load_working(
            conn, composition_id)
        if not fenced_rows:
            raise SoloRingError(
                ErrorCode.COMPOSITION_NOT_READY,
                "working state became empty at the fence",
                status_code=409,
                details={"issues": [{"code": COMPOSITION_EMPTY}]},
            )
        await _validate_working_composition_integrity(
            conn, composition_id, fenced_comp, fenced_rows, fenced_terminated,
            fenced_ownership)
        cur = (
            await conn.execute(
                text("SELECT working_version FROM compositions WHERE id = :cid"),
                {"cid": composition_id},
            )
        ).first()
        if cur is None or cur.working_version != expected_working_version:
            raise EditConflict(
                "stale_working_version",
                "working state changed at the fence; no stale snapshot published",
            )
        # The fenced working state must equal the frozen snapshot content
        # (the integrity predicate above proves its legality; this proves
        # it is the SAME state we canonicalized outside the fence).
        if [r.occurrence_id for r in fenced_rows] != [
                r.occurrence_id for r in rows]:
            raise EditConflict(
                "fence_race",
                "working membership changed at the publish fence",
            )
        existing = (
            await conn.execute(
                text("SELECT id, snapshot_json, snapshot_hash, revision_number "
                     "FROM composition_revisions "
                     "WHERE composition_id = :cid AND snapshot_hash = :h"),
                {"cid": composition_id, "h": sh},
            )
        ).first()
        if existing is not None:
            await _validate_existing_winner(conn, existing, composition_id, sj, sh)
            await conn.exec_driver_sql("COMMIT")
            revision_id, number, created = (
                existing.id, existing.revision_number, False)
        else:
            number = (
                await conn.execute(
                    text("SELECT COALESCE(MAX(revision_number), 0) + 1 "
                         "FROM composition_revisions WHERE composition_id = :cid"),
                    {"cid": composition_id},
                )
            ).scalar_one()
            revision_id = new_uuid()
            await conn.execute(
                text(
                    "INSERT INTO composition_revisions (id, composition_id, "
                    f"revision_number, snapshot_json, snapshot_hash, created_at) "
                    f"VALUES (:id, :cid, :num, :sj, :sh, {DB_NOW_SQL})"
                ),
                {"id": revision_id, "cid": composition_id, "num": number,
                 "sj": sj, "sh": sh},
            )
            for row in rows:
                await conn.execute(
                    text(
                        "INSERT INTO composition_revision_occurrences "
                        "(composition_revision_id, composition_id, occurrence_id, "
                        "display_name, source_kind, production_revision_id, "
                        "nested_composition_revision_id, visible, x_mm, y_mm, z_mm, "
                        "yaw_udeg, pitch_udeg, roll_udeg) VALUES "
                        "(:rid, :cid, :oid, :name, :kind, :prid, :nrid, :vis, "
                        ":x, :y, :z, :yaw, :pitch, :roll)"
                    ),
                    {"rid": revision_id, "cid": composition_id,
                     "oid": row.occurrence_id, "name": row.display_name,
                     "kind": row.source_kind,
                     "prid": row.production_revision_id,
                     "nrid": row.nested_composition_revision_id,
                     "vis": row.visible, "x": row.x_mm, "y": row.y_mm,
                     "z": row.z_mm, "yaw": row.yaw_udeg,
                     "pitch": row.pitch_udeg, "roll": row.roll_udeg},
                )
            for dep in prod_deps:
                await conn.execute(
                    text("INSERT INTO composition_revision_production_dependencies "
                         "(composition_revision_id, production_revision_id) "
                         "VALUES (:rid, :dep)"),
                    {"rid": revision_id, "dep": dep})
            for dep in nested_deps:
                await conn.execute(
                    text("INSERT INTO composition_revision_nested_dependencies "
                         "(composition_revision_id, nested_composition_revision_id) "
                         "VALUES (:rid, :dep)"),
                    {"rid": revision_id, "dep": dep})
            await conn.exec_driver_sql("COMMIT")
            created = True

    detail = await load_composition_revision_detail(session, revision_id)
    return detail, created


async def _validate_existing_winner(conn, existing, composition_id, sj, sh) -> None:
    if existing.snapshot_json != sj or existing.snapshot_hash != sh:
        raise internal_invariant(
            "existing winner snapshot bytes/hash diverge from recomputed value",
            details={"revision_id": existing.id},
        )
    await _verify_revision_invariants(conn, existing.id, composition_id)


def _verify_transform_grammar(row) -> None:
    for v in (row.x_mm, row.y_mm, row.z_mm):
        if not isinstance(v, int) or not (JS_SAFE_MIN <= v <= JS_SAFE_MAX):
            raise internal_invariant(
                "stored translation outside JS-safe integer domain",
                details={"occurrence_id": row.occurrence_id},
            )
    for v in (row.yaw_udeg, row.pitch_udeg, row.roll_udeg):
        if not isinstance(v, int) or not (JS_SAFE_MIN <= v <= JS_SAFE_MAX):
            raise internal_invariant(
                "stored rotation outside JS-safe integer domain",
                details={"occurrence_id": row.occurrence_id},
            )
        if not (UDEG_MIN <= v < UDEG_MIN + 360_000_000):
            raise internal_invariant(
                "stored rotation not canonically normalized",
                details={"occurrence_id": row.occurrence_id},
            )


async def _verify_revision_invariants(conn, revision_id, composition_id) -> dict:
    """Full immutable-revision verification (frozen §§11.3/12.1)."""
    import json as _json

    rev = (
        await conn.execute(
            text("SELECT id, composition_id, snapshot_json, snapshot_hash "
                 "FROM composition_revisions WHERE id = :rid"),
            {"rid": revision_id},
        )
    ).first()
    if rev is None or rev.composition_id != composition_id:
        raise internal_invariant(
            "composition revision missing or lineage mismatch",
            details={"revision_id": revision_id},
        )
    try:
        parsed = _json.loads(rev.snapshot_json)
    except ValueError:
        raise internal_invariant(
            "snapshot_json is not parseable JSON",
            details={"revision_id": revision_id},
        )
    if parsed.get("schema_version") not in _SNAPSHOT_SCHEMA_VERSIONS:
        raise internal_invariant(
            "unknown snapshot schema version",
            details={"revision_id": revision_id},
        )
    if canonical_json_bytes(parsed) != rev.snapshot_json.encode("utf-8"):
        raise internal_invariant(
            "stored snapshot is not the canonical encoding",
            details={"revision_id": revision_id},
        )
    if canonical_hash(parsed) != rev.snapshot_hash:
        raise internal_invariant(
            "snapshot_hash mismatch",
            details={"revision_id": revision_id},
        )
    proj_rows = (
        await conn.execute(
            text("SELECT * FROM composition_revision_occurrences "
                 "WHERE composition_revision_id = :rid ORDER BY occurrence_id"),
            {"rid": revision_id},
        )
    ).fetchall()
    occurrences = parsed.get("occurrences", [])
    if len(proj_rows) != len(occurrences):
        raise internal_invariant(
            "projection row count differs from snapshot occurrences",
            details={"revision_id": revision_id},
        )
    for row, occ in zip(proj_rows, occurrences):
        if row.occurrence_id != occ["occurrence_id"]:
            raise internal_invariant(
                "projection order/identity differs from snapshot",
                details={"revision_id": revision_id},
            )
        spec = _row_to_spec(row)
        rebuilt = {"occurrence_id": row.occurrence_id, **spec.canonical_value()}
        if rebuilt != occ:
            raise internal_invariant(
                "normalized projection differs from canonical snapshot entry",
                details={"revision_id": revision_id,
                         "occurrence_id": row.occurrence_id},
            )
        _verify_transform_grammar(row)

    # Independently rederive the closure from direct immutable sources
    # (set-oriented: one bounded query per dependency family, frozen §18).
    direct_prod = {r.production_revision_id for r in proj_rows
                   if r.source_kind == "production_revision"}
    direct_nested = {r.nested_composition_revision_id for r in proj_rows
                     if r.source_kind == "composition_revision"}
    exp_prod, exp_nested = set(direct_prod), set(direct_nested)
    if direct_nested:
        ids = list(direct_nested)
        ph = ",".join(f":n{i}" for i in range(len(ids)))
        exp_prod.update(d[0] for d in (await conn.execute(
            text("SELECT production_revision_id FROM "
                 "composition_revision_production_dependencies "
                 f"WHERE composition_revision_id IN ({ph})"),
            {f"n{i}": v for i, v in enumerate(ids)},
        )).fetchall())
        exp_nested.update(d[0] for d in (await conn.execute(
            text("SELECT nested_composition_revision_id FROM "
                 "composition_revision_nested_dependencies "
                 f"WHERE composition_revision_id IN ({ph})"),
            {f"n{i}": v for i, v in enumerate(ids)},
        )).fetchall())
    deps_block = parsed.get("dependencies", {})
    if (sorted(exp_prod) != deps_block.get("production_revision_ids")
            or sorted(exp_nested) != deps_block.get("composition_revision_ids")):
        raise internal_invariant(
            "snapshot dependency arrays differ from independently rederived "
            "closure",
            details={"revision_id": revision_id},
        )
    stored_prod = {
        r[0] for r in (await conn.execute(
            text("SELECT production_revision_id FROM "
                 "composition_revision_production_dependencies "
                 "WHERE composition_revision_id = :rid"), {"rid": revision_id},
        )).fetchall()}
    stored_nested = {
        r[0] for r in (await conn.execute(
            text("SELECT nested_composition_revision_id FROM "
                 "composition_revision_nested_dependencies "
                 "WHERE composition_revision_id = :rid"), {"rid": revision_id},
        )).fetchall()}
    if stored_prod != exp_prod or stored_nested != exp_nested:
        raise internal_invariant(
            "normalized dependency rows differ from independently rederived "
            "closure",
            details={"revision_id": revision_id},
        )
    clash = (
        await conn.execute(
            text(
                "SELECT COUNT(*) FROM composition_revision_nested_dependencies d "
                "JOIN composition_revisions cr "
                "ON cr.id = d.nested_composition_revision_id "
                "WHERE d.composition_revision_id = :rid "
                "AND cr.composition_id = :cid"
            ),
            {"rid": revision_id, "cid": composition_id},
        )
    ).scalar_one()
    if clash:
        raise internal_invariant(
            "transitive same-lineage embedding in stored revision",
            details={"revision_id": revision_id},
        )
    return parsed


async def load_composition_revision_detail(
    session: AsyncSession, revision_id: str
) -> dict:
    """Verified historical reader — never consults current working state."""
    async with session.bind.connect() as conn:
        rev = (
            await conn.execute(
                text("SELECT id, composition_id, revision_number, snapshot_json, "
                     "snapshot_hash, created_at FROM composition_revisions "
                     "WHERE id = :rid"), {"rid": revision_id},
            )
        ).first()
        if rev is None:
            raise not_found(
                ErrorCode.COMPOSITION_REVISION_NOT_FOUND,
                f"composition revision {revision_id!r} not found",
            )
        await _verify_revision_invariants(conn, revision_id, rev.composition_id)
    return {
        "revision_id": rev.id,
        "composition_id": rev.composition_id,
        "revision_number": rev.revision_number,
        "snapshot_json": rev.snapshot_json,
        "snapshot_hash": rev.snapshot_hash,
        "created_at": rev.created_at,
    }
