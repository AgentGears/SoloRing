"""Kind-specific revision payload schemas and canonical revision identity (M6 §20–§21).

Each entity kind has its OWN versioned Pydantic model even where the v1
shape matches (plan §20), so Character and Location design semantics can
diverge in v2 without a generic metadata swamp. Unknown fields are
forbidden (the house Pydantic v2 lesson: silently-ignored kwargs are not
rejection).

Canonical revision identity (plan §21) — the hash input is:

    {"schema_version": 1, "entity_kind": <kind>, "spec": <normalized spec>}

and deliberately excludes entity UUID, entity name, revision_number,
approval state, and created_at. Names are display metadata: renaming an
entity never reinterprets its revisions (M6 §18).
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from soloring.domain.canonical import canonical_json_bytes
from soloring.domain.normalize import normalize_optional_creative

REVISION_ENVELOPE_SCHEMA_VERSION = 1


class _RevisionSpecV1(BaseModel):
    """Shared v1 shape: deliberately shallow (M6 is temporal architecture)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    description: str | None = None
    notes: str | None = None

    @field_validator("description", "notes")
    @classmethod
    def _normalize(cls, value: str | None) -> str | None:
        trimmed = normalize_optional_creative(value)
        return trimmed


class CharacterRevisionSpecV1(_RevisionSpecV1):
    pass


class LocationRevisionSpecV1(_RevisionSpecV1):
    pass


class PropRevisionSpecV1(_RevisionSpecV1):
    pass


class CostumeRevisionSpecV1(_RevisionSpecV1):
    pass


class VehicleRevisionSpecV1(_RevisionSpecV1):
    pass


SPEC_MODEL_BY_KIND: dict[str, type[BaseModel]] = {
    "character": CharacterRevisionSpecV1,
    "location": LocationRevisionSpecV1,
    "prop": PropRevisionSpecV1,
    "costume": CostumeRevisionSpecV1,
    "vehicle": VehicleRevisionSpecV1,
}


def validate_spec_payload(entity_kind: str, payload: object) -> dict:
    """Validate + normalize a revision payload through the kind's model.

    Returns the normalized spec dict (the exact value that is persisted and
    hashed). Raises ValueError on any shape/schema violation so the caller
    maps it to the stable validation error.
    """
    model = SPEC_MODEL_BY_KIND.get(entity_kind)
    if model is None:
        raise ValueError(f"Unknown entity kind {entity_kind!r}.")
    try:
        validated = model.model_validate(payload)
    except Exception as exc:  # pydantic ValidationError details stay internal
        raise ValueError(f"Invalid {entity_kind} revision payload: {exc}") from exc
    return validated.model_dump()


def canonical_revision_value(entity_kind: str, spec: dict) -> dict:
    """The canonical hash input for an EntityRevision (plan §21)."""
    return {
        "schema_version": REVISION_ENVELOPE_SCHEMA_VERSION,
        "entity_kind": entity_kind,
        "spec": spec,
    }


def revision_spec_hash(entity_kind: str, spec: dict) -> tuple[bytes, str]:
    """(canonical envelope bytes, sha256 hex) — exact hashed bytes returned so
    callers persist exactly what was hashed."""
    envelope = canonical_json_bytes(canonical_revision_value(entity_kind, spec))
    return envelope, hashlib.sha256(envelope).hexdigest()
