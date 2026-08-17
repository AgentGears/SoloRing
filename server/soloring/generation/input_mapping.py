"""Deterministic GenerationInput mapping (plan §39).

A manifest-independent seam: given an immutable ShotRevision snapshot and an
explicit rule set, derive the identical ordered GenerationInput set every time.

The function is synchronous, pure, and inspects ONLY the snapshot value plus
the rules — never current Shot rows, ShotReferences, Asset/Blob rows, the
filesystem, or the network.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from soloring.domain.normalize import is_valid_role


@dataclass(frozen=True)
class GenerationInputRule:
    """One workflow-semantic input fed from one creative reference role."""

    input_key: str
    source_role: str


@dataclass(frozen=True)
class ResolvedGenerationInput:
    input_key: str
    asset_id: str
    blob_hash: str
    reference_role: str
    position: int


def _validate_rules(rules: Sequence[GenerationInputRule]) -> None:
    seen: set[str] = set()
    for rule in rules:
        if not isinstance(rule.input_key, str) or not rule.input_key.strip():
            raise ValueError(f"input_key {rule.input_key!r} must be non-empty.")
        if not is_valid_role(rule.source_role):
            raise ValueError(f"source_role {rule.source_role!r} is invalid.")
        if rule.input_key in seen:
            raise ValueError(f"duplicate input_key {rule.input_key!r}.")
        seen.add(rule.input_key)


def resolve_generation_inputs(
    revision_snapshot: dict,
    rules: Sequence[GenerationInputRule],
) -> list[ResolvedGenerationInput]:
    """Derive the deterministic ordered input bindings (plan §39.3).

    Rules normalize by input_key; matching references retain deterministic
    snapshot order (role, position, asset_id); positions are zero-based per
    input_key; final output is ordered by (input_key, position). A rule
    matching zero references emits zero bindings (cardinality is M4's concern).
    """
    _validate_rules(rules)

    refs = sorted(
        revision_snapshot.get("references", []),
        key=lambda r: (r["role"], r["position"], r["asset_id"]),
    )

    out: list[ResolvedGenerationInput] = []
    for rule in sorted(rules, key=lambda r: r.input_key):
        position = 0
        for ref in refs:
            if ref["role"] == rule.source_role:
                out.append(
                    ResolvedGenerationInput(
                        input_key=rule.input_key,
                        asset_id=ref["asset_id"],
                        blob_hash=ref["blob_hash"],
                        reference_role=ref["role"],
                        position=position,
                    )
                )
                position += 1

    out.sort(key=lambda r: (r.input_key, r.position))
    return out
