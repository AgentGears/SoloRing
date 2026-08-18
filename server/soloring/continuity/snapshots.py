"""Continuity canonical specification and capturable snapshot forms (M6 §50–§52).

The continuity specification contains SEMANTIC REVISION IDENTITY only
(plan §50): entity ids/kinds, pinned revision ids/numbers/hashes, role,
position, source. Entity names, approval pointers, Asset ids, realization,
executor, and timestamps never enter it.

Snapshot form selection (M6-F14 / §52) is a total rule:

    zero resolved dependencies  -> EXACT existing v1 snapshot form,
                                   continuity columns NULL
    one or more                 -> schema v2 with a continuity block

The v1 path reuses ``domain.snapshots.build_snapshot`` verbatim so legacy
bytes and hashes stay identical.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.domain.snapshots import build_snapshot
from soloring.errors import internal_invariant

CONTINUITY_SCHEMA_VERSION = 1
CONTINUITY_SPEC_SCHEMA_VERSION_2 = 2


@dataclass(frozen=True)
class ResolvedDependency:
    """One capture-time-resolved working dependency (semantic identity)."""

    entity_id: str
    entity_kind: str
    entity_revision_id: str
    entity_revision_number: int
    entity_revision_hash: str
    role: str
    position: int
    source: str


_CONTINUITY_ORDER = ("role", "position", "entity_id", "entity_revision_id")


def sort_resolved(
    resolved: list[ResolvedDependency],
) -> list[ResolvedDependency]:
    """Deterministic §51 ordering before canonicalization; database row
    iteration order can never affect a continuity hash."""
    return sorted(resolved, key=lambda d: tuple(getattr(d, f) for f in _CONTINUITY_ORDER))


def build_continuity_spec(resolved: list[ResolvedDependency]) -> dict:
    return {
        "schema_version": CONTINUITY_SCHEMA_VERSION,
        "dependencies": [
            {
                "entity_id": d.entity_id,
                "entity_kind": d.entity_kind,
                "entity_revision_id": d.entity_revision_id,
                "entity_revision_number": d.entity_revision_number,
                "entity_revision_hash": d.entity_revision_hash,
                "role": d.role,
                "position": d.position,
                "source": d.source,
            }
            for d in sort_resolved(resolved)
        ],
    }


# M7C §5.3: canonical feature-state order — (entity_id, feature_kind,
# feature_id). Deliberately DIFFERENT from the resolver's API display order
# (entity_id, feature_key); the canonical builder re-sorts.
_FEATURE_ORDER = ("entity_id", "feature_kind", "feature_id")


def _feature_like(state) -> bool:
    return (
        hasattr(state, "entity_id")
        and hasattr(state, "feature_kind")
        and hasattr(state, "feature_id")
        and hasattr(state, "feature_key")
        and hasattr(state, "value_type")
        and hasattr(state, "value_json")
        and hasattr(state, "value_hash")
        and hasattr(state, "source_anchor_type")
    )


def sort_feature_states(states):
    """Canonical §5.3 ordering before canonicalization; display order and
    database row order can never affect canonical bytes."""
    return sorted(
        states, key=lambda st: tuple(getattr(st, f) for f in _FEATURE_ORDER)
    )


def feature_state_spec_entry(state) -> dict:
    """One feature_states entry in the frozen spec-v2 grammar (§5.1–§5.2).

    ``value`` is the parsed canonical scalar; ``value_hash`` is the
    resolver-verified SHA-256 of the scalar's canonical bytes — both
    carried through from the captured state, never recomputed here."""
    import json as _json

    return {
        "entity_id": state.entity_id,
        "feature_id": state.feature_id,
        "feature_key": state.feature_key,
        "feature_kind": state.feature_kind,
        "value_type": state.value_type,
        "unit": state.unit,
        "value": _json.loads(state.value_json),
        "value_hash": state.value_hash,
        "source_anchor": {
            "anchor_type": state.source_anchor_type,
            "anchor_id": state.source_anchor_id,
            "boundary": state.source_boundary,
        },
    }


def build_continuity_spec_v2(resolved, feature_states) -> dict:
    """Continuity-spec schema 2 (M7C §5): M6 dependencies + feature
    states + the dormant frozen relations array."""
    return {
        "schema_version": CONTINUITY_SPEC_SCHEMA_VERSION_2,
        "dependencies": build_continuity_spec(resolved)["dependencies"],
        "feature_states": [
            feature_state_spec_entry(st)
            for st in sort_feature_states(feature_states)
        ],
        "relations": [],
    }


def build_capturable_snapshot(
    shot, refs, resolved: list[ResolvedDependency], feature_states=()
) -> tuple[dict, dict | None]:
    """(snapshot value, continuity spec or None) from ONE captured value.

    THE single canonical builder (M7C §10.3 structural singularity) for
    both the working-hash path and capture persistence:

        zero dependencies            → exact schema 1, no spec
        deps + zero effective states → exact schema 2 + spec 1
        one or more effective states → schema 3 + spec 2

    There is no empty schema-3 representation (M6-F14 extended): states
    that all clear keep the exact schema-2 form.
    """
    deps = sort_resolved(resolved)
    states = sort_feature_states(feature_states)
    if not deps:
        return build_snapshot(shot, refs), None
    v1 = build_snapshot(shot, refs)
    if not states:
        spec = build_continuity_spec(deps)
        return (
            {
                "schema_version": 2,
                "intent": v1["intent"],
                "references": v1["references"],
                "continuity": spec,
            },
            spec,
        )
    spec = build_continuity_spec_v2(deps, states)
    return (
        {
            "schema_version": 3,
            "intent": v1["intent"],
            "references": v1["references"],
            "continuity": spec,
        },
        spec,
    )


def effective_working_snapshot_hash(
    shot, refs, resolved: list[ResolvedDependency], feature_states=()
) -> str:
    """The Shot's effective working hash (M6-F15 + M7C §10.4).

    Includes current approvals AND current effective Feature states: either
    mutating changes this hash without any Shot-row mutation. Delegates to
    THE builder — never a second hash implementation."""
    snapshot, _ = build_capturable_snapshot(shot, refs, resolved, feature_states)
    return canonical_hash(snapshot)


def historical_value_hash(value_json: str) -> str:
    """Captured-row-only re-canonicalization (M7C §12 + freeze note).

    Parses the stored canonical value bytes, re-serializes canonically, and
    returns the SHA-256 — with NO consultation of the live Feature schema
    (today's enum membership is not historical truth; the captured
    value_type/scalar/hash are the authority)."""
    import hashlib
    import json as _json

    scalar = _json.loads(value_json)
    return hashlib.sha256(canonical_json_str(scalar).encode("utf-8")).hexdigest()


_RESOLUTION_SQL = """
SELECT sed.entity_id, sed.role, sed.position,
       ce.kind AS entity_kind,
       er.id AS entity_revision_id,
       er.revision_number AS entity_revision_number,
       er.spec_hash AS entity_revision_hash
FROM shot_entity_dependencies sed
JOIN creative_entities ce ON ce.id = sed.entity_id
LEFT JOIN entity_approved_revisions ar ON ar.entity_id = sed.entity_id
LEFT JOIN entity_revisions er ON er.id = ar.revision_id
WHERE sed.shot_id = :sid
"""


async def resolve_working_dependencies(
    conn: AsyncConnection, shot_id: str
) -> list[ResolvedDependency]:
    """Resolve every working dependency against current approvals.

    Runs INSIDE the caller's consistent read unit so all dependencies
    resolve from ONE snapshot (plan §41/§58: a coherent all-A or all-B
    revision set, never a mixture). Total-resolution is the §46 invariant
    chain (assignment requires approval; approval never retracts; deletion
    is blocked while referenced) — an unresolvable row is an internal
    invariant violation, never a silent skip.
    """
    rows = (await conn.execute(text(_RESOLUTION_SQL), {"sid": shot_id})).mappings().all()
    resolved: list[ResolvedDependency] = []
    for row in rows:
        if row["entity_revision_id"] is None:
            raise internal_invariant(
                f"Working dependency {row['entity_id']} of shot {shot_id} "
                "has no resolvable approved revision — the §46 invariant "
                "chain was violated."
            )
        resolved.append(
            ResolvedDependency(
                entity_id=row["entity_id"],
                entity_kind=row["entity_kind"],
                entity_revision_id=row["entity_revision_id"],
                entity_revision_number=row["entity_revision_number"],
                entity_revision_hash=row["entity_revision_hash"],
                role=row["role"],
                position=row["position"],
                source="shot_explicit",
            )
        )
    return resolved


def continuity_spec_bytes(spec: dict) -> tuple[str, str]:
    """(canonical spec json, sha256 hex) — exact persisted == exact hashed."""
    return canonical_json_str(spec), canonical_hash(spec)
