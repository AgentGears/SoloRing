"""Effective Feature-state resolver (M7B plan §5–§6).

ONE resolver, operating on the caller's AsyncConnection so every consumer
(capture read unit, readiness projection, continuity-state endpoint)
derives from ONE consistent SQLite snapshot.

Resolution (inclusive eligibility — plan §5 / M7A.5 gate):

    current M6 semantic dependencies
    → unique dependent Entity identities
    → active Features of those Entities
    → active FeatureTransitions of those Features
    → canonical Project ordering (narrative.order — the only authority)
    → target Shot/start rank
    → eligible transitions (transition rank <= target rank)
    → highest-ranked eligible transition per Feature wins
    → set → effective state; clear → absent

Only entities already present as M6 semantic dependencies participate.
Unrelated-Entity Features are irrelevant even with transitions in the
same Scene.

Every winning `set` is re-canonicalized against the immutable Feature
schema and compared byte/hash-exactly with the persisted values;
disagreement is INTERNAL_INVARIANT_VIOLATION (stored corruption), never
silently trusted (plan §5 stored-value verification).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from soloring.continuity.values import canonicalize_value
from soloring.errors import ErrorCode, SoloRingError, internal_invariant
from soloring.narrative.order import (
    ANCHOR_SHOT,
    BOUNDARY_START,
    load_narrative_ordering,
)


@dataclass(frozen=True)
class EffectiveFeatureState:
    entity_id: str
    feature_id: str
    feature_key: str
    feature_kind: str
    value_type: str
    unit: str | None
    value_json: str
    value_hash: str
    source_transition_id: str
    source_anchor_type: str
    source_anchor_id: str
    source_boundary: str


@dataclass(frozen=True)
class ResolutionOutcome:
    """Result of resolving one target Shot."""

    shot_id: str
    assigned: bool
    # Relevant temporal data exists (>=1 active transition on a Feature of
    # a dependent Entity) — the §6 context condition.
    relevant_temporal_data: bool
    # Effective `set` states, sorted by (entity_id, feature_key).
    states: tuple[EffectiveFeatureState, ...]


@dataclass(frozen=True)
class EffectiveRelationState:
    """One effective (winner-active, both-endpoints-dependent) relation."""

    relation_id: str
    subject_entity_id: str
    predicate_id: str
    predicate_key: str
    object_entity_id: str
    source_transition_id: str
    source_anchor_type: str
    source_anchor_id: str
    source_boundary: str


@dataclass(frozen=True)
class RelationResolutionOutcome:
    """Result of resolving one target Shot's relation state (M7D §7).

    ``endpoint_requirements`` carries one §12.4 issue element per
    exactly-one-endpoint winner — ALL of them, deterministically ordered by
    (subject_entity_id, predicate_key, object_entity_id, relation_id)."""

    shot_id: str
    assigned: bool
    relevant_relation_data: bool
    relation_states: tuple[EffectiveRelationState, ...]
    endpoint_requirements: tuple[dict, ...]


def _shot_not_found(shot_id: str) -> SoloRingError:
    return SoloRingError(
        ErrorCode.SHOT_NOT_FOUND, f"Shot {shot_id} not found.", status_code=404
    )


def narrative_context_required(shot_id: str) -> SoloRingError:
    return SoloRingError(
        ErrorCode.NARRATIVE_CONTEXT_REQUIRED,
        f"Shot {shot_id} has relevant narrative Feature state but no "
        "resolvable narrative position (unassigned).",
        status_code=409,
        details={"shot_id": shot_id},
    )


async def resolve_effective_feature_state(
    conn: AsyncConnection, shot_id: str
) -> ResolutionOutcome:
    """Resolve the target Shot's effective Feature state on the caller's
    consistent read snapshot."""
    shot = (
        await conn.execute(
            text(
                "SELECT project_id, deleted_at, scene_id FROM shots "
                "WHERE id = :sid"
            ),
            {"sid": shot_id},
        )
    ).first()
    if shot is None or shot.deleted_at is not None:
        raise _shot_not_found(shot_id)
    assigned = shot.scene_id is not None

    # Dependent Entity identities come from the M6 dependency set
    # (duplicate roles must not duplicate state — deduplicate here).
    dep_rows = (
        await conn.execute(
            text(
                "SELECT DISTINCT entity_id FROM shot_entity_dependencies "
                "WHERE shot_id = :sid"
            ),
            {"sid": shot_id},
        )
    ).scalars().all()
    if not dep_rows:
        return ResolutionOutcome(
            shot_id=shot_id, assigned=assigned,
            relevant_temporal_data=False, states=(),
        )
    dep_ids = tuple(dep_rows)

    # Bulk load: active Features of dependent Entities + their active
    # transitions (set-oriented: two queries, independent of counts).
    placeholders = ", ".join(f":e{i}" for i in range(len(dep_ids)))
    dep_params = {f"e{i}": e for i, e in enumerate(dep_ids)}

    features = (
        await conn.execute(
            text(
                "SELECT f.id, f.entity_id, f.key, f.kind, f.value_type, "
                "f.unit, f.enum_values_json FROM continuity_features f "
                f"WHERE f.deleted_at IS NULL AND f.entity_id IN ({placeholders})"
            ),
            dep_params,
        )
    ).mappings().all()
    if not features:
        return ResolutionOutcome(
            shot_id=shot_id, assigned=assigned,
            relevant_temporal_data=False, states=(),
        )
    feature_ids = [f["id"] for f in features]
    f_placeholders = ", ".join(f":f{i}" for i in range(len(feature_ids)))
    f_params = {f"f{i}": fid for i, fid in enumerate(feature_ids)}

    transitions = (
        await conn.execute(
            text(
                "SELECT id, feature_id, anchor_type, anchor_id, boundary, "
                "operation, value_json, value_hash FROM "
                "continuity_feature_transitions "
                f"WHERE deleted_at IS NULL AND feature_id IN ({f_placeholders})"
            ),
            f_params,
        )
    ).mappings().all()
    if not transitions:
        return ResolutionOutcome(
            shot_id=shot_id, assigned=assigned,
            relevant_temporal_data=False, states=(),
        )
    # Relevant temporal data exists at all (§6): readiness conditioning
    # uses this even when the effective result is empty or the Shot is
    # unassigned.
    relevant = True

    if not assigned:
        # No narrative position: the outcome carries the condition; strict
        # consumers raise NARRATIVE_CONTEXT_REQUIRED themselves.
        return ResolutionOutcome(
            shot_id=shot_id, assigned=False,
            relevant_temporal_data=relevant, states=(),
        )

    ordering = await load_narrative_ordering(conn, shot.project_id)
    try:
        target_rank = ordering.shot_start_rank(shot_id)
    except SoloRingError:
        raise internal_invariant(
            f"Assigned active shot {shot_id} missing from its Project's "
            "canonical ordering during Feature-state resolution."
        )

    # Rank every transition through the ordering; a transition anchored
    # outside the canonical stream is stored corruption.
    by_feature: dict[str, list] = {}
    for t in transitions:
        try:
            rank = ordering.rank_of(t["anchor_type"], t["anchor_id"], t["boundary"])
        except SoloRingError:
            raise internal_invariant(
                f"Active feature transition {t['id']} anchored at "
                f"({t['anchor_type']}, {t['anchor_id']}, {t['boundary']}) "
                "is not present in the canonical ordering."
            )
        if rank <= target_rank:
            by_feature.setdefault(t["feature_id"], []).append((rank, t))

    feature_by_id = {f["id"]: dict(f) for f in features}
    winners: list[EffectiveFeatureState] = []
    for fid, eligible in by_feature.items():
        best_rank = max(r for r, _ in eligible)
        best = [t for r, t in eligible if r == best_rank]
        if len(best) != 1:
            raise internal_invariant(
                f"Ambiguous effective transition for feature {fid}: "
                f"{len(best)} transitions share the winning rank — "
                "no ID/timestamp/UUID tie-breaking is permitted."
            )
        t = best[0]
        if t["operation"] == "clear":
            if t["value_json"] is not None or t["value_hash"] is not None:
                raise internal_invariant(
                    f"Stored clear transition {t['id']} carries non-NULL "
                    "value columns."
                )
            continue  # canonical absence (§5 clear semantics)
        if t["operation"] != "set":
            raise internal_invariant(
                f"Stored transition {t['id']} has operation "
                f"{t['operation']!r} outside the set|clear domain."
            )
        feature = feature_by_id[fid]
        # Stored-value verification: re-canonicalize and require exact
        # byte/hash equality with what is persisted. ANY decoding failure
        # here is database corruption — normalized to the invariant error,
        # never leaked as client validation or an unstructured exception.
        try:
            enum_values = None
            if feature["value_type"] == "enum":
                enum_values = json.loads(feature["enum_values_json"])
            stored_value = json.loads(t["value_json"])
            v_json, v_hash = canonicalize_value(
                feature["value_type"], stored_value, enum_values=enum_values
            )
        except Exception as exc:
            raise internal_invariant(
                f"Stored transition {t['id']} value cannot be decoded "
                "against its Feature schema — persisted corruption."
            ) from exc
        if v_json != t["value_json"] or v_hash != t["value_hash"]:
            raise internal_invariant(
                f"Stored transition {t['id']} value disagrees with its "
                "Feature schema under re-canonicalization."
            )
        winners.append(
            EffectiveFeatureState(
                entity_id=feature["entity_id"],
                feature_id=fid,
                feature_key=feature["key"],
                feature_kind=feature["kind"],
                value_type=feature["value_type"],
                unit=feature["unit"],
                value_json=t["value_json"],
                value_hash=t["value_hash"],
                source_transition_id=t["id"],
                source_anchor_type=t["anchor_type"],
                source_anchor_id=t["anchor_id"],
                source_boundary=t["boundary"],
            )
        )

    winners.sort(key=lambda s: (s.entity_id, s.feature_key))
    return ResolutionOutcome(
        shot_id=shot_id, assigned=True,
        relevant_temporal_data=relevant, states=tuple(winners),
    )


def readiness_projection(outcome: ResolutionOutcome,
                         relation_outcome: RelationResolutionOutcome | None = None) -> dict:
    """The §7.1 readiness matrix as a plain projection — ONE projection
    consuming BOTH outcomes. After M7D there are exactly TWO semantic
    not-ready conditions: NARRATIVE_CONTEXT_REQUIRED (unassigned + relevant
    temporal data of either kind; precedence: endpoint classification
    needs a narrative position) and CONTINUITY_RELATION_ENDPOINT_REQUIRED
    (assigned + ≥1 active relation with exactly one dependency endpoint).

    continuity_state_ready means: the full current M7 state is resolvable
    AND safe for current-state capture/generation. Not-ready rows carry
    NULL working hash/differs at the consumers and block capture — an
    incomplete current state is never canonical absence (M7D §5.3).
    """
    relevant = outcome.relevant_temporal_data or (
        relation_outcome is not None
        and relation_outcome.relevant_relation_data
    )
    if not outcome.assigned and relevant:
        return {
            "continuity_state_ready": False,
            "readiness_issues": [{
                "error_code": ErrorCode.NARRATIVE_CONTEXT_REQUIRED,
                "shot_id": outcome.shot_id,
            }],
            "effective_states": (),
            "relation_states": (),
        }
    if relation_outcome is not None and relation_outcome.endpoint_requirements:
        return {
            "continuity_state_ready": False,
            "readiness_issues": list(relation_outcome.endpoint_requirements),
            "effective_states": (),
            "relation_states": (),
        }
    # M7C §10.2 extended by M7D §7.1: effective states of both kinds are
    # resolvable AND capture-safe — the only not-ready conditions are the
    # two rows above.
    return {
        "continuity_state_ready": True,
        "readiness_issues": [],
        "effective_states": outcome.states,
        "relation_states": (
            () if relation_outcome is None
            else relation_outcome.relation_states
        ),
    }


def relation_endpoint_required(shot_id: str, issues: list[dict]) -> SoloRingError:
    """The strict 409 carrying the FULL ordered issue set (§12.3) — never
    an arbitrary first missing endpoint."""
    return SoloRingError(
        ErrorCode.CONTINUITY_RELATION_ENDPOINT_REQUIRED,
        f"Shot {shot_id} has active relation(s) with exactly one semantic-"
        "dependency endpoint — continuity is incomplete until the missing "
        "endpoint is added or the relation is deactivated.",
        status_code=409,
        details={"shot_id": shot_id, "issues": issues},
    )


async def resolve_effective_relation_state(
    conn: AsyncConnection, shot_id: str
) -> RelationResolutionOutcome:
    """Resolve the target Shot's effective relation state on the caller's
    consistent read snapshot (M7D §7 — the ONE relation resolver).

    Candidate relations TOUCH the dependency subgraph (subject OR object in
    the deduplicated dependency set); endpoint completeness is classified
    AFTER temporal winner resolution:

        winner inactive / absent        → canonical absence
        winner active + both endpoints  → effective relation
        winner active + exactly one     → endpoint requirement (§12.4 issue)
        winner active + neither         → irrelevant (unreachable after
                                          OR-selection; explicit total
                                          classification, never skipped)

    Stored corruption — transitions anchored outside the canonical
    ordering, ambiguous winners, or guard-chain violations (inactive
    predicate/endpoints under an active relation) — is
    INTERNAL_INVARIANT_VIOLATION, never a silent skip (APR-017).
    """
    shot = (
        await conn.execute(
            text(
                "SELECT project_id, deleted_at, scene_id FROM shots "
                "WHERE id = :sid"
            ),
            {"sid": shot_id},
        )
    ).first()
    if shot is None or shot.deleted_at is not None:
        raise _shot_not_found(shot_id)
    assigned = shot.scene_id is not None

    dep_rows = (
        await conn.execute(
            text(
                "SELECT DISTINCT entity_id FROM shot_entity_dependencies "
                "WHERE shot_id = :sid"
            ),
            {"sid": shot_id},
        )
    ).scalars().all()
    if not dep_rows:
        return RelationResolutionOutcome(
            shot_id=shot_id, assigned=assigned,
            relevant_relation_data=False, relation_states=(),
            endpoint_requirements=(),
        )
    dep_ids = frozenset(dep_rows)

    placeholders = ", ".join(f":e{i}" for i in range(len(dep_rows)))
    dep_params = {f"e{i}": e for i, e in enumerate(dep_rows)}
    relations = (
        await conn.execute(
            text(
                "SELECT r.id, r.subject_entity_id, r.object_entity_id, "
                "r.predicate_id, p.key AS predicate_key, "
                "p.deleted_at AS predicate_deleted, "
                "ss.deleted_at AS subject_deleted, "
                "os.deleted_at AS object_deleted "
                "FROM continuity_relations r "
                "JOIN continuity_predicates p ON p.id = r.predicate_id "
                "JOIN creative_entities ss ON ss.id = r.subject_entity_id "
                "JOIN creative_entities os ON os.id = r.object_entity_id "
                "WHERE r.project_id = :pid AND r.deleted_at IS NULL "
                f"AND (r.subject_entity_id IN ({placeholders}) "
                f"OR r.object_entity_id IN ({placeholders}))"
            ),
            {"pid": shot.project_id, **dep_params},
        )
    ).mappings().all()
    if not relations:
        return RelationResolutionOutcome(
            shot_id=shot_id, assigned=assigned,
            relevant_relation_data=False, relation_states=(),
            endpoint_requirements=(),
        )

    # The §13 guard chain keeps active relations fully active; anything
    # else is stored corruption, fail closed.
    for r in relations:
        if (
            r["predicate_deleted"] is not None
            or r["subject_deleted"] is not None
            or r["object_deleted"] is not None
        ):
            raise internal_invariant(
                f"Active relation {r['id']} has a tombstoned predicate or "
                "endpoint — the M7D guard chain was violated."
            )

    relation_ids = [r["id"] for r in relations]
    r_placeholders = ", ".join(f":r{i}" for i in range(len(relation_ids)))
    r_params = {f"r{i}": rid for i, rid in enumerate(relation_ids)}
    transitions = (
        await conn.execute(
            text(
                "SELECT id, relation_id, anchor_type, anchor_id, boundary, "
                "state FROM continuity_relation_transitions "
                f"WHERE deleted_at IS NULL AND relation_id IN ({r_placeholders})"
            ),
            r_params,
        )
    ).mappings().all()
    if not transitions:
        return RelationResolutionOutcome(
            shot_id=shot_id, assigned=assigned,
            relevant_relation_data=False, relation_states=(),
            endpoint_requirements=(),
        )
    relevant = True

    if not assigned:
        # No narrative position: the outcome carries the condition; strict
        # consumers raise NARRATIVE_CONTEXT_REQUIRED themselves. Endpoint
        # classification requires a target position (§7 unassigned note).
        return RelationResolutionOutcome(
            shot_id=shot_id, assigned=False,
            relevant_relation_data=relevant, relation_states=(),
            endpoint_requirements=(),
        )

    ordering = await load_narrative_ordering(conn, shot.project_id)
    try:
        target_rank = ordering.shot_start_rank(shot_id)
    except SoloRingError:
        raise internal_invariant(
            f"Assigned active shot {shot_id} missing from its Project's "
            "canonical ordering during relation-state resolution."
        )

    by_relation: dict[str, list] = {}
    for t in transitions:
        try:
            rank = ordering.rank_of(t["anchor_type"], t["anchor_id"], t["boundary"])
        except SoloRingError:
            raise internal_invariant(
                f"Active relation transition {t['id']} anchored at "
                f"({t['anchor_type']}, {t['anchor_id']}, {t['boundary']}) "
                "is not present in the canonical ordering."
            )
        if rank <= target_rank:
            by_relation.setdefault(t["relation_id"], []).append((rank, t))

    relation_by_id = {r["id"]: dict(r) for r in relations}
    winners: list[EffectiveRelationState] = []
    requirements: list[dict] = []
    for rid, eligible in by_relation.items():
        best_rank = max(r for r, _ in eligible)
        best = [t for r, t in eligible if r == best_rank]
        if len(best) != 1:
            raise internal_invariant(
                f"Ambiguous effective transition for relation {rid}: "
                f"{len(best)} transitions share the winning rank — "
                "no ID/timestamp/UUID tie-breaking is permitted."
            )
        t = best[0]
        if t["state"] not in ("active", "inactive"):
            raise internal_invariant(
                f"Stored relation transition {t['id']} has state "
                f"{t['state']!r} outside the active|inactive domain."
            )
        if t["state"] == "inactive":
            continue  # canonical absence
        rel = relation_by_id[rid]
        subject_in = rel["subject_entity_id"] in dep_ids
        object_in = rel["object_entity_id"] in dep_ids
        if subject_in and object_in:
            winners.append(
                EffectiveRelationState(
                    relation_id=rid,
                    subject_entity_id=rel["subject_entity_id"],
                    predicate_id=rel["predicate_id"],
                    predicate_key=rel["predicate_key"],
                    object_entity_id=rel["object_entity_id"],
                    source_transition_id=t["id"],
                    source_anchor_type=t["anchor_type"],
                    source_anchor_id=t["anchor_id"],
                    source_boundary=t["boundary"],
                )
            )
        elif subject_in or object_in:
            # Exactly one endpoint present: continuity is INCOMPLETE —
            # an explicit §12.4 issue, never silent non-participation.
            requirements.append({
                "error_code": ErrorCode.CONTINUITY_RELATION_ENDPOINT_REQUIRED,
                "relation_id": rid,
                "subject_entity_id": rel["subject_entity_id"],
                "predicate_id": rel["predicate_id"],
                "predicate_key": rel["predicate_key"],
                "object_entity_id": rel["object_entity_id"],
                "present_entity_id": (
                    rel["subject_entity_id"] if subject_in
                    else rel["object_entity_id"]
                ),
                "missing_entity_id": (
                    rel["object_entity_id"] if subject_in
                    else rel["subject_entity_id"]
                ),
            })
        # Neither endpoint present: unreachable after OR-selection; the
        # classification is total and the relation is simply not listed.

    order_key = lambda st: (  # noqa: E731 - canonical §8.2 order
        st.subject_entity_id, st.predicate_key, st.object_entity_id,
        st.relation_id,
    )
    winners.sort(key=order_key)
    requirements.sort(
        key=lambda i: (
            i["subject_entity_id"], i["predicate_key"],
            i["object_entity_id"], i["relation_id"],
        )
    )
    return RelationResolutionOutcome(
        shot_id=shot_id, assigned=True,
        relevant_relation_data=relevant,
        relation_states=tuple(winners),
        endpoint_requirements=tuple(requirements),
    )
