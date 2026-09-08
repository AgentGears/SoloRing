"""Identity-operation impact resolution, preview, and fenced apply (§8).

The occurrence-consumer registry has two layers: mechanically discovered
relational FK consumers (PRAGMA-driven, exhaustive) and an explicitly
registered non-FK durable-consumer registry (empty in M12). Apply follows
the frozen 15-step FK-safe order under one BEGIN IMMEDIATE.
"""

from __future__ import annotations

import json as _json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.composition.canonical import (
    WorkingSpec,
    build_impact_value,
    build_operation_value,
    build_request_value,
    impact_fingerprint,
    operation_hash,
    operation_json,
    request_fingerprint,
)
from soloring.composition.service import (
    EditConflict,
    _require_composition,
    _require_scope,
    _spec_row_params,
    _terminated_ids,
    _working_spec,
)
from soloring.db.timeutil import DB_NOW_SQL
from soloring.domain.ids import new_uuid
from soloring.errors import ErrorCode, SoloRingError, internal_invariant, validation_error
from soloring.spatial.math import Transform as _Transform

# Frozen §8.1 — the mechanically discovered FK consumer set at 0013, with
# impact classification. A structural test re-derives this from PRAGMA and
# fails closed on any unregistered FK.
# Frozen M13 R3 §22.1 — the five direct M13 occurrence-FK families join the
# enumeration at 0014: subject adoption is durable identity metadata that
# never blocks by itself; active PI features/tracks are live current
# blockers once their authoring surfaces exist (M13B); the two historical
# ShotRevision projections never block. Live-blocker resolution itself
# activates with those surfaces — no M13 rows can exist before them.
FK_CONSUMERS: dict[tuple[str, str], str] = {
    ("composition_working_occurrences", "occurrence_id"): "working/internal",
    ("composition_working_occurrences", "composition_id"): "working/internal",
    ("composition_revision_occurrences", "occurrence_id"): "historical/non-blocking",
    ("composition_revision_occurrences", "composition_id"): "historical/non-blocking",
    ("composition_identity_operation_sources", "occurrence_id"): "lineage/internal",
    ("composition_identity_operation_sources", "composition_id"): "lineage/internal",
    ("composition_identity_operation_targets", "occurrence_id"): "lineage/internal",
    ("composition_identity_operation_targets", "composition_id"): "lineage/internal",
    ("composition_occurrence_authority_subjects", "occurrence_id"): "adoption/non-blocking",
    ("composition_occurrence_authority_subjects", "composition_id"): "adoption/non-blocking",
    ("production_instance_features", "occurrence_id"): "instance-state/live-blocker",
    ("production_instance_features", "composition_id"): "instance-state/live-blocker",
    ("production_instance_spatial_tracks", "occurrence_id"): "instance-spatial/live-blocker",
    ("production_instance_spatial_tracks", "composition_id"): "instance-spatial/live-blocker",
    ("shot_revision_production_instance_feature_states", "occurrence_id"): "historical/non-blocking",
    ("shot_revision_production_instance_feature_states", "composition_id"): "historical/non-blocking",
    ("shot_revision_production_instance_spatial_states", "occurrence_id"): "historical/non-blocking",
    ("shot_revision_production_instance_spatial_states", "composition_id"): "historical/non-blocking",
}

# Explicit non-FK durable-consumer registry (frozen §2.5; activated by
# M13 R3 §22.2): the Shot selection is the ONE registered indirect
# current consumer — it reaches occurrences only through
# binding → binding subject/entry → occurrence.
NON_FK_DURABLE_CONSUMERS: dict[str, str] = {
    "shot_production_world_selections": "current-selection/indirect",
}

# Frozen §2.4 cardinality contract.
CARDINALITY = {
    "mint": (0, 0, 1),            # sources min/max, targets
    "remove": (1, 1, 0),
    "replace_as_new": (1, 1, 1),
    "split": (1, 1, None),        # 2+
    "merge": (2, None, 1),
    "fork": (1, 1, 1),
}
_TERMINATES = {"mint": False, "remove": True, "replace_as_new": True,
               "split": True, "merge": True, "fork": False}


def _check_cardinality(kind: str, n_sources: int, n_targets: int) -> None:
    smin, smax, texp = CARDINALITY[kind]
    if n_sources < smin or (smax is not None and n_sources > smax):
        raise validation_error(
            f"{kind} requires "
            f"{'exactly ' + str(smax) if smax == smin else str(smin) + '+'}"
            f" source occurrence(s)")
    if texp is None:
        if n_targets < 2:
            raise validation_error(f"{kind} requires 2 or more targets")
    elif n_targets != texp:
        raise validation_error(f"{kind} requires exactly {texp} target(s)")


async def _dispositions(conn, composition_id: str, source_ids: list[str]):
    rows = (
        await conn.execute(
            text(
                "SELECT o.id AS occurrence_id, "
                "CASE WHEN t.occurrence_id IS NULL THEN 0 ELSE 1 END AS terminated, "
                "CASE WHEN w.occurrence_id IS NULL THEN 0 ELSE 1 END AS in_working "
                "FROM composition_occurrences o "
                "LEFT JOIN (SELECT s.occurrence_id FROM "
                "composition_identity_operation_sources s "
                "JOIN composition_identity_operations op ON op.id = s.operation_id "
                "WHERE op.composition_id = :cid AND s.terminates_identity = 1) t "
                "ON t.occurrence_id = o.id "
                "LEFT JOIN composition_working_occurrences w "
                "ON w.occurrence_id = o.id "
                "AND w.composition_id = o.composition_id "
                "WHERE o.composition_id = :cid AND o.id IN ("
                + ",".join(f":i{n}" for n in range(len(source_ids))) + ")"
            ),
            {"cid": composition_id,
             **{f"i{n}": i for n, i in enumerate(source_ids)}},
        )
    ).fetchall()
    by_id = {r.occurrence_id: r for r in rows}
    out = []
    for sid in source_ids:
        if sid not in by_id:
            raise validation_error(
                f"source occurrence {sid!r} does not exist in this Composition")
        r = by_id[sid]
        active = not r.terminated
        out.append({
            "occurrence_id": sid,
            "active": active,
            "in_working_state": bool(r.in_working),
        })
    return out


async def _historical_counts(conn, source_ids: list[str]) -> dict[str, int]:
    """Advisory only — never part of the impact fingerprint (§6.2)."""
    if not source_ids:
        return {}
    rows = (
        await conn.execute(
            text(
                "SELECT occurrence_id, COUNT(*) FROM "
                "composition_revision_occurrences WHERE occurrence_id IN ("
                + ",".join(f":i{n}" for n in range(len(source_ids))) + ")"
                " GROUP BY occurrence_id"
            ),
            {f"i{n}": i for n, i in enumerate(source_ids)},
        )
    ).fetchall()
    return {r[0]: r[1] for r in rows}


async def _resolve_live_blockers(conn, source_ids: list[str]) -> list[dict]:
    """Registered external live blockers (frozen M13 R3 §22.3).

    Active ProductionInstanceFeature and ProductionInstanceSpatialTrack
    rows are unconditionally live current blockers for their occurrence.
    Subject adoption is durable identity metadata and never blocks by
    itself; historical ShotRevision rows never block. Blocker elements
    use the frozen canonical JSON shapes, sorted by
    (occurrence_id, consumer, id). The M13 current-selection blocker is
    the registered non-FK durable consumer (§22.2) and resolves through
    the binding subject graph.
    """
    if not source_ids:
        return []
    ph = ",".join(f":i{n}" for n in range(len(source_ids)))
    params = {f"i{n}": i for n, i in enumerate(source_ids)}
    blockers: list[dict] = []
    feature_rows = (
        await conn.execute(
            text(
                "SELECT id, occurrence_id FROM production_instance_features "
                f"WHERE deleted_at IS NULL AND occurrence_id IN ({ph})"
            ),
            params,
        )
    ).fetchall()
    for r in feature_rows:
        blockers.append({"consumer": "production_instance_feature",
                         "id": r.id, "occurrence_id": r.occurrence_id})
    track_rows = (
        await conn.execute(
            text(
                "SELECT id, occurrence_id FROM "
                "production_instance_spatial_tracks "
                f"WHERE deleted_at IS NULL AND occurrence_id IN ({ph})"
            ),
            params,
        )
    ).fetchall()
    for r in track_rows:
        blockers.append({"consumer": "production_instance_spatial_track",
                         "id": r.id, "occurrence_id": r.occurrence_id})
    sel_rows = (
        await conn.execute(
            text(
                "SELECT s.shot_id, s.binding_id, bs.occurrence_id FROM "
                "shot_production_world_selections s "
                "JOIN composition_spatial_binding_subjects bs "
                "ON bs.binding_id = s.binding_id "
                f"WHERE bs.occurrence_id IN ({ph})"
            ),
            params,
        )
    ).fetchall()
    for r in sel_rows:
        blockers.append({"consumer": "shot_production_world_selection",
                         "shot_id": r.shot_id, "binding_id": r.binding_id,
                         "occurrence_id": r.occurrence_id})
    blockers.sort(key=lambda b: (
        b["occurrence_id"], b["consumer"], b.get("id", b.get("shot_id"))))
    return blockers


def _normalize_request(conn_holder, composition_id: str, request: dict):
    """Validate + normalize a raw operation request (shared preview/apply)."""
    if not isinstance(request, dict):
        raise validation_error("operation request must be an object")
    if set(request) != {"kind", "source_occurrence_ids", "target_working_specs"}:
        raise validation_error(
            "operation request must be exactly "
            "{kind, source_occurrence_ids, target_working_specs}")
    kind = request["kind"]
    if kind not in CARDINALITY:
        raise validation_error(f"unknown operation kind {kind!r}")
    source_ids = request["source_occurrence_ids"]
    if (not isinstance(source_ids, list)
            or not all(isinstance(i, str) for i in source_ids)):
        raise validation_error("source_occurrence_ids must be a list of ids")
    if len(set(source_ids)) != len(source_ids):
        raise validation_error("source_occurrence_ids must be unique")
    specs = request["target_working_specs"]
    if not isinstance(specs, list):
        raise validation_error("target_working_specs must be a list")
    return kind, source_ids, specs


def _check_targets(kind: str, n_targets: int) -> None:
    texp = CARDINALITY[kind][2]
    if texp is None:
        if n_targets < 2:
            raise validation_error(f"{kind} requires 2 or more targets")
    elif n_targets != texp:
        raise validation_error(f"{kind} requires exactly {texp} target(s)")


async def _specs_through_validator(
    conn, *, project_id, parent_composition_id, raw_specs, kind,
) -> list[WorkingSpec]:
    specs = []
    for raw in raw_specs:
        specs.append(await _working_spec(
            conn, project_id=project_id,
            parent_composition_id=parent_composition_id, spec=raw))
    _check_targets(kind, len(specs))  # target cardinality only here
    return specs


async def preview_identity_operation(
    session: AsyncSession, composition_id: str, *, request: dict
) -> dict:
    """Frozen §8.3: normalize, fingerprint, resolve dispositions — mint nothing."""
    async with session.bind.connect() as conn:
        comp = await _require_composition(conn, composition_id)
        kind, source_ids, raw_specs = _normalize_request(
            None, composition_id, request)
        _check_cardinality(
            kind, len(source_ids), len(raw_specs))
        specs = await _specs_through_validator(
            conn, project_id=comp["project_id"],
            parent_composition_id=composition_id, raw_specs=raw_specs, kind=kind)
        dispositions = await _dispositions(conn, composition_id, source_ids)
        blockers = await _resolve_live_blockers(conn, source_ids)
        counts = await _historical_counts(conn, source_ids)
        request_value = build_request_value(
            composition_id=composition_id, kind=kind,
            source_occurrence_ids=source_ids, target_specs=specs)
        impact_value = build_impact_value(
            composition_id=composition_id,
            working_version=comp["working_version"],
            source_occurrence_ids=source_ids,
            source_dispositions=dispositions,
            live_blocking_references=blockers)
    # Frozen M13 R3 §22.4: any live M13 blocker makes a TERMINATING
    # operation's preview allowed=false with the full exact blocker set;
    # fork does not terminate and is never blocked by live state.
    blocked = bool(blockers) and _TERMINATES[kind]
    return {
        "allowed": not blocked,
        "working_version": comp["working_version"],
        "normalized_request": request_value,
        "request_fingerprint": request_fingerprint(request_value),
        "impact_fingerprint": impact_fingerprint(impact_value),
        "source_occurrence_summaries": dispositions,
        "historical_reference_counts": counts,  # advisory only
        "live_blocking_references": blockers,
    }


async def apply_identity_operation(
    session: AsyncSession, composition_id: str, *,
    scope: object, expected_working_version: int,
    expected_request_fingerprint: str, expected_impact_fingerprint: str,
    request: dict,
) -> dict:
    """Frozen §8.4 — the 15-step FK-safe fenced apply."""
    _require_scope(scope)
    if not isinstance(expected_working_version, int) or isinstance(
        expected_working_version, bool
    ):
        raise validation_error("expected_working_version must be an integer")

    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        # 1. revalidate
        comp = await _require_composition(conn, composition_id)
        # 2. exact working_version
        if comp["working_version"] != expected_working_version:
            raise EditConflict("stale_working_version",
                               "working state changed; refetch and retry")
        # 3. normalize/validate
        kind, source_ids, raw_specs = _normalize_request(
            None, composition_id, request)
        _check_cardinality(kind, len(source_ids), len(raw_specs))
        specs = await _specs_through_validator(
            conn, project_id=comp["project_id"],
            parent_composition_id=composition_id, raw_specs=raw_specs, kind=kind)
        # 4. recompute request fingerprint
        request_value = build_request_value(
            composition_id=composition_id, kind=kind,
            source_occurrence_ids=source_ids, target_specs=specs)
        req_fp = request_fingerprint(request_value)
        if req_fp != expected_request_fingerprint:
            raise EditConflict("stale_request",
                               "request fingerprint mismatch under fence")
        # 5. recompute impact
        dispositions = await _dispositions(conn, composition_id, source_ids)
        terminated_now = await _terminated_ids(conn, composition_id, source_ids)
        for d in dispositions:
            if d["occurrence_id"] in terminated_now:
                raise EditConflict(
                    "stale_impact",
                    "source identity terminated since preview")
        blockers = await _resolve_live_blockers(conn, source_ids)
        impact_value = build_impact_value(
            composition_id=composition_id,
            working_version=comp["working_version"],
            source_occurrence_ids=source_ids,
            source_dispositions=dispositions,
            live_blocking_references=blockers)
        imp_fp = impact_fingerprint(impact_value)
        if imp_fp != expected_impact_fingerprint:
            raise EditConflict("stale_impact",
                               "impact fingerprint mismatch under fence")
        # 6. live M13 blockers refuse TERMINATING operations (frozen
        # M13 R3 §22.4); fork does not terminate and is never blocked
        # merely because the source owns live state.
        if blockers and _TERMINATES[kind]:
            raise EditConflict(
                "live_references",
                "terminating identity operation refused: live M13 "
                "authority references exist for a source occurrence",
                details={"live_blocking_references": blockers})
        # 7. temporal/liveness/cardinality rules
        for d in dispositions:
            if not d["active"] or not d["in_working_state"]:
                raise validation_error(
                    "source occurrence must be active and in working state")
        if kind == "fork":
            pass  # fork source stays active; same requirement applies now
        # 8. target UUIDs in memory
        target_ids = [new_uuid() for _ in specs]
        # 9. canonical immutable operation value
        terminates = _TERMINATES[kind]
        op_value = build_operation_value(
            composition_id=composition_id, kind=kind,
            working_version_before=comp["working_version"],
            working_version_after=comp["working_version"] + 1,
            request_fp=req_fp, impact_fp=imp_fp,
            sources=[{"occurrence_id": sid,
                      "terminates_identity": terminates}
                     for sid in source_ids],
            targets=[{"occurrence_id": tid,
                      "working_spec": spec.canonical_value()}
                     for tid, spec in zip(target_ids, specs)])
        # 10. insert operation
        op_id = new_uuid()
        await conn.execute(
            text(
                "INSERT INTO composition_identity_operations "
                "(id, composition_id, operation_kind, working_version_before, "
                "working_version_after, request_fingerprint, impact_fingerprint, "
                f"operation_json, operation_hash, created_at) VALUES "
                f"(:id, :cid, :kind, :before, :after, :req, :imp, :opjson, :ophash, "
                f"{DB_NOW_SQL})"
            ),
            {"id": op_id, "cid": composition_id, "kind": kind,
             "before": comp["working_version"],
             "after": comp["working_version"] + 1,
             "req": req_fp, "imp": imp_fp,
             "opjson": operation_json(op_value),
             "ophash": operation_hash(op_value)},
        )
        # 11. target occurrence rows exist before any edge references them
        for tid in target_ids:
            await conn.execute(
                text(
                    f"INSERT INTO composition_occurrences (id, composition_id, "
                    f"created_at) VALUES (:oid, :cid, {DB_NOW_SQL})"
                ),
                {"oid": tid, "cid": composition_id},
            )
        # 12. lineage edges
        for sid in source_ids:
            await conn.execute(
                text(
                    "INSERT INTO composition_identity_operation_sources "
                    "(composition_id, operation_id, occurrence_id, "
                    "terminates_identity) VALUES (:cid, :opid, :oid, :term)"
                ),
                {"cid": composition_id, "opid": op_id, "oid": sid,
                 "term": 1 if terminates else 0},
            )
        for tid in target_ids:
            await conn.execute(
                text(
                    "INSERT INTO composition_identity_operation_targets "
                    "(composition_id, operation_id, occurrence_id) "
                    "VALUES (:cid, :opid, :oid)"
                ),
                {"cid": composition_id, "opid": op_id, "oid": tid},
            )
        # 13. working membership mutation from exact operation target specs
        if terminates:
            for sid in source_ids:
                await conn.execute(
                    text("DELETE FROM composition_working_occurrences "
                         "WHERE composition_id = :cid AND occurrence_id = :oid"),
                    {"cid": composition_id, "oid": sid})
        for tid, spec in zip(target_ids, specs):
            await conn.execute(
                text(
                    "INSERT INTO composition_working_occurrences "
                    "(composition_id, occurrence_id, display_name, source_kind, "
                    "production_revision_id, nested_composition_revision_id, "
                    "visible, x_mm, y_mm, z_mm, yaw_udeg, pitch_udeg, roll_udeg, "
                    f"updated_at) VALUES (:cid, :oid, :name, :kind, :prid, :nrid, "
                    f":vis, :x, :y, :z, :yaw, :pitch, :roll, {DB_NOW_SQL})"
                ),
                _spec_row_params(composition_id, tid, spec),
            )
        # 14. increment working_version exactly once
        await conn.execute(
            text("UPDATE compositions SET working_version = working_version + 1 "
                 "WHERE id = :cid"), {"cid": composition_id})
        # 15. COMMIT
        await conn.exec_driver_sql("COMMIT")
    return {
        "operation_id": op_id,
        "kind": kind,
        "working_version": expected_working_version + 1,
        "target_occurrence_ids": target_ids,
    }


async def verify_identity_history(
    session: AsyncSession, composition_id: str
) -> list[dict]:
    """Frozen §12.2 — the complete lineage temporal/liveness verifier."""
    async with session.bind.connect() as conn:
        comp = await _require_composition(conn, composition_id)
        ops = (
            await conn.execute(
                text("SELECT * FROM composition_identity_operations "
                     "WHERE composition_id = :cid ORDER BY working_version_before"),
                {"cid": composition_id},
            )
        ).fetchall()
        before_seen: set[int] = set()
        birth: dict[str, int] = {}
        terminated_at: dict[str, int] = {}
        out = []
        for op in ops:
            if op.working_version_before in before_seen:
                raise internal_invariant(
                    "duplicate identity-operation version interval",
                    details={"operation_id": op.id})
            before_seen.add(op.working_version_before)
            if op.working_version_after != op.working_version_before + 1:
                raise internal_invariant(
                    "operation version step != +1",
                    details={"operation_id": op.id})
            if op.working_version_after > comp["working_version"]:
                raise internal_invariant(
                    "operation after exceeds current working_version",
                    details={"operation_id": op.id})
            try:
                parsed = _json.loads(op.operation_json)
            except ValueError:
                raise internal_invariant(
                    "operation_json not parseable",
                    details={"operation_id": op.id})
            from soloring.domain.canonical import canonical_hash, canonical_json_bytes

            if canonical_json_bytes(parsed) != op.operation_json.encode("utf-8"):
                raise internal_invariant(
                    "operation_json not canonical",
                    details={"operation_id": op.id})
            if canonical_hash(parsed) != op.operation_hash:
                raise internal_invariant(
                    "operation_hash mismatch",
                    details={"operation_id": op.id})
            # THE one shared evidence checklist (§12.2) — consumed
            # identically by recovery so the two verifiers cannot diverge.
            sources = (
                await conn.execute(
                    text("SELECT occurrence_id, terminates_identity FROM "
                         "composition_identity_operation_sources "
                         "WHERE operation_id = :oid ORDER BY occurrence_id"),
                    {"oid": op.id},
                )
            ).fetchall()
            targets = (
                await conn.execute(
                    text("SELECT occurrence_id FROM "
                         "composition_identity_operation_targets "
                         "WHERE operation_id = :oid ORDER BY occurrence_id"),
                    {"oid": op.id},
                )
            ).fetchall()
            from soloring.composition.evidence import validate_operation_evidence

            try:
                validate_operation_evidence(
                    parsed,
                    row_composition_id=composition_id,
                    row_kind=op.operation_kind,
                    row_before=op.working_version_before,
                    row_after=op.working_version_after,
                    row_request_fingerprint=op.request_fingerprint,
                    row_impact_fingerprint=op.impact_fingerprint,
                    normalized_sources=[
                        (s.occurrence_id, s.terminates_identity)
                        for s in sources],
                    normalized_targets=[t.occurrence_id for t in targets],
                )
            except ValueError as exc:
                raise internal_invariant(
                    str(exc), details={"operation_id": op.id}) from exc
            for s in sources:
                if s.occurrence_id in terminated_at:
                    raise internal_invariant(
                        "post-termination source use",
                        details={"operation_id": op.id,
                                 "occurrence_id": s.occurrence_id})
                if s.occurrence_id not in birth:
                    raise internal_invariant(
                        "source used before birth",
                        details={"operation_id": op.id,
                                 "occurrence_id": s.occurrence_id})
                if s.terminates_identity:
                    if s.occurrence_id in terminated_at:
                        raise internal_invariant(
                            "double termination",
                            details={"occurrence_id": s.occurrence_id})
                    terminated_at[s.occurrence_id] = op.working_version_before
            for t in targets:
                if t.occurrence_id in birth:
                    raise internal_invariant(
                        "double birth",
                        details={"occurrence_id": t.occurrence_id})
                birth[t.occurrence_id] = op.working_version_before
            out.append({
                "operation_id": op.id, "kind": op.operation_kind,
                "working_version_before": op.working_version_before,
                "working_version_after": op.working_version_after,
                "created_at": op.created_at,  # (created_at,id) cursor key
                "sources": [dict(s._mapping) for s in sources],
                "targets": [t.occurrence_id for t in targets],
            })
        # every occurrence has exactly one birth
        all_occ = (
            await conn.execute(
                text("SELECT id FROM composition_occurrences "
                     "WHERE composition_id = :cid"), {"cid": composition_id},
            )
        ).fetchall()
        for o in all_occ:
            if o.id not in birth:
                raise internal_invariant(
                    "occurrence without birth operation",
                    details={"occurrence_id": o.id})
        # no terminated occurrence in working state
        working = (
            await conn.execute(
                text("SELECT occurrence_id FROM composition_working_occurrences "
                     "WHERE composition_id = :cid"), {"cid": composition_id},
            )
        ).fetchall()
        for w in working:
            if w.occurrence_id in terminated_at:
                raise internal_invariant(
                    "terminated occurrence remains in working state",
                    details={"occurrence_id": w.occurrence_id})
        # active-occurrence ↔ working-membership equality (§12.3): a live
        # nonterminated occurrence must BE in working membership.
        active = {o.id for o in all_occ if o.id not in terminated_at}
        if active != {w.occurrence_id for w in working}:
            raise internal_invariant(
                "active occurrence set differs from working membership",
                details={"composition_id": composition_id})
    return out
