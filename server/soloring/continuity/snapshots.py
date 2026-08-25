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


def build_continuity_spec_v2(resolved, feature_states, relation_states=()) -> dict:
    """Continuity-spec schema 2 (M7C §5 + M7D §8): M6 dependencies +
    feature states + relation states. The grammar does not change — M7D
    only POPULATES the relations field that M7C froze and emitted empty."""
    return {
        "schema_version": CONTINUITY_SPEC_SCHEMA_VERSION_2,
        "dependencies": build_continuity_spec(resolved)["dependencies"],
        "feature_states": [
            feature_state_spec_entry(st)
            for st in sort_feature_states(feature_states)
        ],
        "relations": [
            relation_state_spec_entry(rs)
            for rs in sort_relation_states(relation_states)
        ],
    }


# M7D §8.2: canonical relation-state order — (subject_entity_id,
# predicate_key, object_entity_id, relation_id); relation_id is the final
# tiebreaker only. The resolver's API display order drops the tiebreak;
# the canonical builder re-sorts (same discipline as feature states).
_RELATION_ORDER = (
    "subject_entity_id", "predicate_key", "object_entity_id", "relation_id",
)


def _relation_like(state) -> bool:
    return (
        hasattr(state, "subject_entity_id")
        and hasattr(state, "relation_id")
        and hasattr(state, "predicate_id")
        and hasattr(state, "predicate_key")
        and hasattr(state, "object_entity_id")
        and hasattr(state, "source_anchor_type")
        and hasattr(state, "source_anchor_id")
        and hasattr(state, "source_boundary")
    )


def sort_relation_states(states):
    """Canonical §8.2 ordering before canonicalization; display order and
    database row order can never affect canonical bytes."""
    return sorted(
        states, key=lambda st: tuple(getattr(st, f) for f in _RELATION_ORDER)
    )


def relation_state_spec_entry(state) -> dict:
    """One relations entry in the frozen spec-v2 grammar (§8.2).

    Insertion order is the canonical serialization order.
    ``source_transition_id`` is deliberately ABSENT — audit provenance is
    not semantic identity (APR-022): recreated equivalent transitions
    converge; the captured bytes carry the anchor triple only."""
    return {
        "subject_entity_id": state.subject_entity_id,
        "relation_id": state.relation_id,
        "predicate_id": state.predicate_id,
        "predicate_key": state.predicate_key,
        "object_entity_id": state.object_entity_id,
        "source_anchor": {
            "anchor_type": state.source_anchor_type,
            "anchor_id": state.source_anchor_id,
            "boundary": state.source_boundary,
        },
    }


def build_capturable_snapshot(
    shot, refs, resolved: list[ResolvedDependency], feature_states=(),
    relation_states=(), visual_pack=None, spatial_pack=None,
) -> tuple[dict, dict | None]:
    """(snapshot value, continuity spec or None) from ONE captured value.

    THE single canonical builder (M7C §10.3 structural singularity) for
    both the working-hash path and capture persistence:

        zero dependencies            → exact schema 1, no spec
        deps + zero effective states
          (features AND relations)   → exact schema 2 + spec 1
        one or more effective Feature states
        OR relation states           → schema 3 + spec 2
        any non-empty approved visual
        pack                          → schema 4 over the exact lower base

    There is no empty schema-3/4 representation (M6-F14 extended by M7D
    §8.3 and M8 §54–55): states that all clear keep the exact lower
    schema; the zero-deps/non-empty-visual cell is unreachable by
    construction. An endpoint-incomplete or visually-unready Shot never
    reaches this builder at all (the read unit raises first)."""
    deps = sort_resolved(resolved)
    states = sort_feature_states(feature_states)
    relations = sort_relation_states(relation_states)
    if not deps:
        # M8 §54: the zero-deps/non-empty-visual cell is UNREACHABLE by
        # construction; a pack here is an internal invariant, never a
        # representable schema.
        if visual_pack or spatial_pack:
            from soloring.errors import internal_invariant

            raise internal_invariant(
                "Visual/spatial authority pack supplied for a "
                "zero-dependency shot — the schema lattice declares "
                "this cell unreachable."
            )
        return build_snapshot(shot, refs), None
    v1 = build_snapshot(shot, refs)
    if not states and not relations:
        spec = build_continuity_spec(deps)
        base = {"schema_version": 4 if visual_pack else 2,
                "intent": v1["intent"],
                "references": v1["references"],
                "continuity": spec}
        if visual_pack:
            base["visual_reference_pack"] = visual_pack
    else:
        spec = build_continuity_spec_v2(deps, states, relations)
        base = {"schema_version": 4 if visual_pack else 3,
                "intent": v1["intent"],
                "references": v1["references"],
                "continuity": spec}
        if visual_pack:
            base["visual_reference_pack"] = visual_pack
    if spatial_pack is not None:
        # M10D §48-49: any non-empty M10 pack wraps the exact lower
        # semantic base as schema 5 (M8 present or absent). No empty
        # schema 5 exists — the resolver never yields an empty pack.
        base = {"schema_version": 5, **base, "spatial_continuity":
                spatial_pack}
    return base, spec


def effective_working_snapshot_hash(
    shot, refs, resolved: list[ResolvedDependency], feature_states=(),
    relation_states=(), visual_pack=None, spatial_pack=None,
) -> str:
    """The Shot's effective working hash (M6-F15 + M7C §10.4 + M7D §10.2).

    Includes current approvals AND current effective Feature AND Relation
    states: mutating any of them changes this hash without any Shot-row
    mutation. Delegates to THE builder — never a second hash
    implementation."""
    snapshot, _ = build_capturable_snapshot(
        shot, refs, resolved, feature_states, relation_states, visual_pack,
        spatial_pack,
    )
    return canonical_hash(snapshot)


def historical_canonicalize_value(value_type: str, value_json: str):
    """Captured-row-only historical canonicalization (M7C §12 + freeze note).

    Enforces the frozen scalar grammar for the CAPTURED value_type using
    captured-row information only — never today's Feature schema (enum
    membership was not captured; the row's value_type/scalar/hash are the
    authority). Returns (canonical_value_json, sha256). Raises ValueError
    on any type violation; the caller normalizes that to the invariant
    error.

    Grammar (frozen §7 byte contracts, historical form):
      boolean  → JSON true/false (nothing else; 0/1 are not booleans)
      integer  → JSON int, not bool, within safe-integer bounds
      decimal  → canonical decimal STRING form (no exponent, trimmed zeros)
      text     → JSON string, 1–4096, non-whitespace, already trimmed
      enum     → a JSON string (enum-shaped); membership is NOT re-checked
    Objects and arrays are invalid for every type."""
    import hashlib
    import json as _json

    try:
        scalar = _json.loads(value_json)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"stored value_json is not valid JSON: {exc}")
    if isinstance(scalar, (dict, list)):
        raise ValueError("stored value is an object/array — no M7 value type permits it")

    if value_type == "boolean":
        if not isinstance(scalar, bool):
            raise ValueError("captured boolean is not JSON true/false")
    elif value_type == "integer":
        if isinstance(scalar, bool) or not isinstance(scalar, int):
            raise ValueError("captured integer is not a JSON integer")
        if not (-9007199254740991 <= scalar <= 9007199254740991):
            raise ValueError("captured integer is outside safe-integer bounds")
    elif value_type == "decimal":
        if not isinstance(scalar, str):
            raise ValueError("captured decimal is not a canonical string")
        import re as _re
        if _re.match(r"^-?(?:0|[1-9][0-9]*)(\.[0-9]+)?$", scalar) is None:
            raise ValueError(
                "captured decimal does not match the canonical grammar"
            )
        # Must already be canonical: trimmed zeros / no -0.
        from soloring.continuity.values import canonical_decimal_string
        if canonical_decimal_string(scalar) != scalar:
            raise ValueError("captured decimal is not in canonical form")
        # Frozen decimal bounds (M7 §7.4): reject rather than round —
        # recoverable from the captured scalar alone.
        from decimal import Decimal as _Dec
        _, _digits, _exp = _Dec(scalar).as_tuple()
        if len(_digits) > 38:
            raise ValueError(
                "captured decimal precision exceeds the frozen 38 digits"
            )
        if _exp < 0 and -_exp > 18:
            raise ValueError(
                "captured decimal scale exceeds the frozen 18 places"
            )
    elif value_type == "text":
        if not isinstance(scalar, str):
            raise ValueError("captured text is not a string")
        if not (1 <= len(scalar) <= 4096):
            raise ValueError("captured text length out of bounds")
        if scalar.strip() == "" or scalar != scalar.strip():
            raise ValueError("captured text is not already-trimmed non-whitespace")
    elif value_type == "enum":
        if not isinstance(scalar, str):
            raise ValueError("captured enum value is not a string")
        # Enum-SHAPE bounds every legally captured value must satisfy
        # (any legal enum member is 1–128 chars, trimmed, non-whitespace);
        # membership itself deliberately NOT re-checked — today's
        # enum_values_json is not historical truth (the freeze note).
        if not (1 <= len(scalar) <= 128):
            raise ValueError("captured enum value length out of bounds")
        if scalar.strip() == "" or scalar != scalar.strip():
            raise ValueError(
                "captured enum value is not trimmed non-whitespace"
            )
    else:
        raise ValueError(f"captured value_type {value_type!r} is outside the M7 domain")

    canonical = canonical_json_str(scalar)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return canonical, digest


def historical_value_hash(value_json: str) -> str:
    """Backward-compatible pure re-hash (no type grammar). Prefer
    historical_canonicalize_value, which enforces the captured type."""
    return historical_canonicalize_value(
        _infer_scalar_type(value_json), value_json
    )[1]


def _infer_scalar_type(value_json: str) -> str:
    """Best-effort type inference for the pure-hash helper (tests only)."""
    import json as _json

    scalar = _json.loads(value_json)
    if isinstance(scalar, bool):
        return "boolean"
    if isinstance(scalar, int):
        return "integer"
    return "text"


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
