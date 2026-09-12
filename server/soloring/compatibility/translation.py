"""M15 deterministic translator v1 — realization-local frame bridge
(frozen R4 §7).

A pure, inspectable coordinate-frame bridge over two immutable
ProductionRevisionSpatialInterpretation values. It is compatibility
translation evidence only: it never mutates A2/A4/A5 authority, any
binding, or any Shot, and it never materializes a compensating A6
transform.
"""

from __future__ import annotations

from soloring.domain.canonical import canonical_hash

TRANSLATOR_ID = "soloring.compatibility.realization_local_frame_bridge"
TRANSLATOR_VERSION = 1

_I64_MIN = -(2 ** 63)
_I64_MAX = 2 ** 63 - 1


class UnsupportedTranslation(Exception):
    """The exact pair is outside the frozen v1 subset; never wrapped."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _identity_rotation(interp: dict) -> bool:
    rotation = interp["realization_local_to_subject_local"]["rotation_udeg"]
    return rotation == [0, 0, 0]


def _translation(interp: dict) -> list[int]:
    return interp["realization_local_to_subject_local"]["translation_mm"]


def frame_bridge_supported(source: dict, target: dict) -> str | None:
    """Return the unsupported reason, or None when the exact pair sits
    inside the frozen v1 subset (schema-1, identity rotations, integral
    millimetres, representable delta)."""
    if source.get("schema_version") != 1 or target.get(
            "schema_version") != 1:
        return "schema_not_1"
    for interp in (source, target):
        rotation = interp["realization_local_to_subject_local"][
            "rotation_udeg"]
        translation = interp["realization_local_to_subject_local"][
            "translation_mm"]
        if any(not isinstance(v, int) or isinstance(v, bool)
               for v in rotation + translation):
            return "non_integral_interpretation"
    if not _identity_rotation(source) or not _identity_rotation(target):
        return "rotation_non_identity"
    delta = [s - t for s, t in zip(_translation(source),
                                   _translation(target))]
    if any(v < _I64_MIN or v > _I64_MAX for v in delta):
        return "translation_overflow"
    return None


def frame_bridge_translate(
        *, source: dict, target: dict,
        source_interpretation_hash: str,
        target_interpretation_hash: str) -> dict:
    """Canonical translator parameters + output (§7.2).

    Raises UnsupportedTranslation outside the exact v1 subset; the
    evaluator maps that to REVIEW_REQUIRED per §6.5.3."""
    reason = frame_bridge_supported(source, target)
    if reason is not None:
        raise UnsupportedTranslation(reason)
    delta = [s - t for s, t in zip(_translation(source),
                                  _translation(target))]
    parameters = {
        "schema_version": 1,
        "translator": {"id": TRANSLATOR_ID, "version": TRANSLATOR_VERSION},
        "source_interpretation_hash": source_interpretation_hash,
        "target_interpretation_hash": target_interpretation_hash,
        "source_local_to_target_local": {
            "translation_mm": delta,
            "rotation_udeg": [0, 0, 0],
        },
    }
    return {
        "translator_id": TRANSLATOR_ID,
        "translator_version": TRANSLATOR_VERSION,
        "parameters": parameters,
        "parameters_hash": canonical_hash(parameters),
        "output_hash": canonical_hash(parameters),
    }
