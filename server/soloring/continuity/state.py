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


def capture_unavailable() -> SoloRingError:
    return SoloRingError(
        ErrorCode.NARRATIVE_STATE_CAPTURE_UNAVAILABLE,
        "The Shot has one or more effective Feature states; historical "
        "schema-v3 capture is not implemented until M7C, so mutable-state "
        "capture/generation is blocked.",
        status_code=409,
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


def readiness_projection(outcome: ResolutionOutcome) -> dict:
    """The §7 readiness matrix as a plain projection.

    continuity_state_ready means: the full current M7 state is resolvable
    AND safe for current-state capture/generation under the installed
    milestone. A correctly resolved NONEMPTY Feature state is not
    capture-safe until M7C (temporary M7B gate, plan §9).
    """
    if not outcome.assigned and outcome.relevant_temporal_data:
        return {
            "continuity_state_ready": False,
            "readiness_issues": [{
                "code": ErrorCode.NARRATIVE_CONTEXT_REQUIRED,
                "shot_id": outcome.shot_id,
            }],
            "effective_states": (),
        }
    if outcome.states:
        return {
            "continuity_state_ready": False,
            "readiness_issues": [{
                "code": ErrorCode.NARRATIVE_STATE_CAPTURE_UNAVAILABLE,
                "shot_id": outcome.shot_id,
                "effective_state_count": len(outcome.states),
            }],
            "effective_states": outcome.states,
        }
    return {
        "continuity_state_ready": True,
        "readiness_issues": [],
        "effective_states": (),
    }
