"""Canonical Composition builders (frozen M12 R3 §§5–6).

One snapshot/dependency builder serves readiness, publication, winner
validation, historical verification, and recovery. Request/impact/operation
v1 fingerprints are built here from normalized values only; no second
interpretation of Composition state is permitted anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass

from soloring.domain.canonical import canonical_hash, canonical_json_bytes, canonical_json_str
from soloring.spatial.math import Transform

SCHEMA_VERSION = 1
IDENTITY_SCHEMA_VERSION = 1
CONSUMER_CONTRACT_VERSION = 1

OPERATION_KINDS = ("mint", "remove", "replace_as_new", "split", "merge", "fork")
SOURCE_KINDS = ("production_revision", "composition_revision")


@dataclass(frozen=True)
class WorkingSpec:
    """One normalized occurrence configuration (frozen working-spec grammar)."""

    display_name: str
    source_kind: str
    revision_id: str
    visible: bool
    transform: Transform

    def canonical_value(self) -> dict:
        return {
            "display_name": self.display_name,
            "source": {"kind": self.source_kind, "revision_id": self.revision_id},
            "transform": self.transform.canonical_value(),
            "visible": self.visible,
        }


def build_snapshot_value(
    occurrences: list[WorkingSpec], occurrence_ids: list[str],
    production_dependency_ids: list[str],
    composition_dependency_ids: list[str],
) -> dict:
    """Exact schema-1 Composition Revision value (frozen §5.1).

    ``occurrences`` and ``occurrence_ids`` are parallel arrays; the builder
    itself sorts by occurrence_id so caller ordering can never influence
    identity (frozen §5.3 permutation-invariance).
    """
    pairs = sorted(zip(occurrence_ids, occurrences), key=lambda p: p[0])
    return {
        "schema_version": SCHEMA_VERSION,
        "occurrences": [
            {"occurrence_id": oid, **spec.canonical_value()}
            for oid, spec in pairs
        ],
        "dependencies": {
            "production_revision_ids": sorted(set(production_dependency_ids)),
            "composition_revision_ids": sorted(set(composition_dependency_ids)),
        },
    }


def snapshot_bytes(value: dict) -> bytes:
    return canonical_json_bytes(value)


def snapshot_hash(value: dict) -> str:
    return canonical_hash(value)


# --- identity-operation request / impact / operation (frozen §6) -----------

def build_request_value(
    *, composition_id: str, kind: str,
    source_occurrence_ids: list[str],
    target_specs: list[WorkingSpec],
) -> dict:
    return {
        "schema_version": IDENTITY_SCHEMA_VERSION,
        "composition_id": composition_id,
        "kind": kind,
        "source_occurrence_ids": sorted(set(source_occurrence_ids)),
        "target_working_specs": [
            spec.canonical_value()
            for spec in sorted(
                target_specs,
                key=lambda s: canonical_json_bytes(s.canonical_value()),
            )
        ],
    }


def request_fingerprint(request_value: dict) -> str:
    return canonical_hash(request_value)


def build_impact_value(
    *, composition_id: str, working_version: int,
    source_occurrence_ids: list[str],
    source_dispositions: list[dict],
    live_blocking_references: list[dict],
) -> dict:
    return {
        "schema_version": IDENTITY_SCHEMA_VERSION,
        "consumer_contract_version": CONSUMER_CONTRACT_VERSION,
        "composition_id": composition_id,
        "working_version": working_version,
        "source_occurrence_ids": sorted(set(source_occurrence_ids)),
        "source_dispositions": sorted(
            source_dispositions, key=lambda d: d["occurrence_id"]
        ),
        "live_blocking_references": sorted(
            live_blocking_references,
            # M13 R3 §22.3 order: (occurrence_id, consumer, id-or-shot_id).
            # The list was structurally empty throughout M12, so this key
            # never ran before M13 and no existing fingerprint changes.
            key=lambda r: (r["occurrence_id"], r["consumer"],
                           r.get("id", r.get("shot_id"))),
        ),
    }


def impact_fingerprint(impact_value: dict) -> str:
    return canonical_hash(impact_value)


def build_operation_value(
    *, composition_id: str, kind: str,
    working_version_before: int, working_version_after: int,
    request_fp: str, impact_fp: str,
    sources: list[dict], targets: list[dict],
) -> dict:
    return {
        "schema_version": IDENTITY_SCHEMA_VERSION,
        "composition_id": composition_id,
        "kind": kind,
        "working_version_before": working_version_before,
        "working_version_after": working_version_after,
        "request_fingerprint": request_fp,
        "impact_fingerprint": impact_fp,
        "sources": sorted(sources, key=lambda s: s["occurrence_id"]),
        "targets": sorted(targets, key=lambda t: t["occurrence_id"]),
    }


def operation_bytes(value: dict) -> bytes:
    return canonical_json_bytes(value)


def operation_hash(value: dict) -> str:
    return canonical_hash(value)


def operation_json(value: dict) -> str:
    return canonical_json_str(value)
