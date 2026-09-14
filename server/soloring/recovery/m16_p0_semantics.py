"""M16-P0 compatibility adapter for published M14/M15 recovery semantics.

M15 published two deliberately distinct canonical projections for an update
operation:

* ``operation_json`` stores the audit projection with
  ``assessment.assessment_report_hash``;
* ``operation_hash`` is derived by ``compatibility.canonical.operation_root``
  whose assessment member is named ``report_hash``.

The semantic successor verifier re-derives the hash root from normalized rows.
This adapter teaches its canonical-JSON comparison about the published audit
projection without weakening either check: stored JSON must still be canonical
and row-exact, and the stored hash must still equal the canonical hash root.
"""

from __future__ import annotations

from soloring.domain.canonical import canonical_json_str as _canonical_json_str
from soloring.recovery import semantic_successors as _semantic
from soloring.recovery import successor_semantics as _successor


def _published_m15_json(value) -> str:
    """Serialize the published M15 audit projection when given its hash root.

    All non-operation values use the ordinary canonical serializer unchanged.
    The shape test is deliberately exact so assessment/report/use JSON checks
    elsewhere in the verifier cannot be reinterpreted by this adapter.
    """
    if (
        isinstance(value, dict)
        and set(value) == {"assessment", "items"}
        and isinstance(value.get("assessment"), dict)
        and set(value["assessment"]) == {"assessment_id", "report_hash"}
        and isinstance(value.get("items"), list)
    ):
        value = {
            "assessment": {
                "assessment_id": value["assessment"]["assessment_id"],
                "assessment_report_hash": value["assessment"]["report_hash"],
            },
            "items": value["items"],
        }
    return _canonical_json_str(value)


# Source-true M16-P0 repair: the verifier itself remains the one normalized-row
# implementation; only its canonical JSON rendering of the published M15
# operation audit root is adapted.  Install once at package import so concurrent
# backup/restore calls cannot race a temporary monkey-patch.
_semantic.canonical_json_str = _published_m15_json
_successor.verify_m15_compatibility_state = _semantic.verify_m15_compatibility_state

install_successor_semantics = _successor.install_successor_semantics
verify_m15_compatibility_state = _semantic.verify_m15_compatibility_state

__all__ = ["install_successor_semantics", "verify_m15_compatibility_state"]
