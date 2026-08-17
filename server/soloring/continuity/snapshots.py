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


def build_capturable_snapshot(
    shot, refs, resolved: list[ResolvedDependency]
) -> tuple[dict, dict | None]:
    """(snapshot value, continuity spec or None) from ONE captured value.

    Empty dependency set returns the exact v1 form and no continuity spec
    (M6-F14: there is no empty schema-v2 alternative).
    """
    deps = sort_resolved(resolved)
    if not deps:
        return build_snapshot(shot, refs), None
    v1 = build_snapshot(shot, refs)
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


def effective_working_snapshot_hash(
    shot, refs, resolved: list[ResolvedDependency]
) -> str:
    """The Shot's effective working hash INCLUDING current approvals (M6-F15).

    Entity approval changes change this hash without any Shot-row mutation
    whenever the Shot holds dependencies."""
    snapshot, _ = build_capturable_snapshot(shot, refs, resolved)
    return canonical_hash(snapshot)


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
