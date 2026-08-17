"""Continuity-domain enums (M6 plan §16, §45, §49)."""

from __future__ import annotations

from enum import Enum


class EntityKind(str, Enum):
    """The M6 story-world entity kinds (database CHECK mirrors the values)."""

    CHARACTER = "character"
    LOCATION = "location"
    PROP = "prop"
    COSTUME = "costume"
    VEHICLE = "vehicle"


ENTITY_KINDS: tuple[str, ...] = tuple(k.value for k in EntityKind)

# Which typed revision-spec table stores payloads for a kind.
SPEC_TABLE_BY_KIND: dict[str, str] = {
    EntityKind.CHARACTER.value: "character_revision_specs",
    EntityKind.LOCATION.value: "location_revision_specs",
    EntityKind.PROP.value: "prop_revision_specs",
    EntityKind.COSTUME.value: "costume_revision_specs",
    EntityKind.VEHICLE.value: "vehicle_revision_specs",
}
