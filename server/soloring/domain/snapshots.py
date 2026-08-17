"""ShotRevision snapshot builder (plan §13, §15).

A pure function that assembles the canonical snapshot value from a Shot's
normalized stored fields and its ordered references. Used by the working-state
hash (M1B, plan §15) and by revision capture (M1C). The exact stored bytes are
the exact hashed bytes via domain.canonical.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

from soloring.domain.canonical import canonical_hash

SCHEMA_VERSION = 1


class _ShotLike(Protocol):
    subject: str
    action: str | None
    environment: str | None
    framing: str | None
    camera_motion: str | None
    lens: str | None
    mood: str | None
    duration_ms: int | None


@dataclass(frozen=True)
class ReferenceRef:
    """A reference's identity as it appears in a snapshot."""

    asset_id: str
    blob_hash: str
    role: str
    position: int


class _ReferenceLike(Protocol):
    asset_id: str
    blob_hash: str
    role: str
    position: int


def build_snapshot(shot: _ShotLike, references: Iterable[_ReferenceLike | ReferenceRef] = ()) -> dict:
    """Build the canonical snapshot value (plan §13).

    All optional intent fields are present (as stored, i.e. already normalized
    to None for empty). References are sorted by (role, position, asset_id).
    """
    refs = sorted(
        (
            {"asset_id": r.asset_id, "blob_hash": r.blob_hash, "role": r.role, "position": r.position}
            for r in references
        ),
        key=lambda x: (x["role"], x["position"], x["asset_id"]),
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "intent": {
            "subject": shot.subject,
            "action": shot.action,
            "environment": shot.environment,
            "framing": shot.framing,
            "camera_motion": shot.camera_motion,
            "lens": shot.lens,
            "mood": shot.mood,
            "duration_ms": shot.duration_ms,
        },
        "references": refs,
    }


def working_snapshot_hash(
    shot: _ShotLike, references: Iterable[_ReferenceLike | ReferenceRef] = ()
) -> str:
    """SHA-256 of the canonical snapshot of the Shot's current working state."""
    return canonical_hash(build_snapshot(shot, references))
