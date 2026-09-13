"""Single shared pure placement-consumer classifier (frozen R5 §6.5.1).

This module is the ONLY product-code owner of the placement-consumer
decision law: the choice among CLEAN_A6 / UNIQUE_A4 / UNRESOLVED and
the emission of every placement-classification issue from the closed
M13 §12 vocabulary. Both callers call ``classify_placement_consumer_
from_facts``:

  * the published M13 ``derive_candidate`` path shapes already-loaded
    published facts and calls this function per subject occurrence;
  * the M15 working-state assessment loader shapes working-occurrence
    facts over the same grammar and calls the same function.

The function is PURE: no SQL, no database access, no row
loading, no clock or chance, no incidental-identity tie-breaks, no
mutation. Authority-subject *resolution* (entity existence, project
membership, active-claim uniqueness) and occurrence-universe loading
remain caller-side fact computation; once facts are shaped, every
placement decision below belongs to this function only.

Decision order mirrors the pinned M14 published path exactly for the
single-context case; the multi-context (working-state) generalization
is fail-closed: more than one applicable world context is UNRESOLVED,
never an A6 fallback or a tie-break.
"""

from __future__ import annotations

CLEAN_A6 = "CLEAN_A6"
UNIQUE_A4 = "UNIQUE_A4"
UNRESOLVED = "UNRESOLVED"

# Frozen M13 §12 placement-classification issue codes this classifier
# can return (BINDING_PROJECT_MISMATCH is context-level here; the
# pair-level early return in derive_candidate precedes classification).
_TARGET_CONFLICT = "BINDING_SPATIAL_TARGET_CONFLICT"
_TRANSFORM_CONFLICT = "BINDING_COMPOSITION_TRANSFORM_CONFLICT"
_SUBJECT_INVALID = "BINDING_SUBJECT_INVALID"
_INTERPRETATION_REQUIRED = "BINDING_SPATIAL_INTERPRETATION_REQUIRED"
_PROJECT_MISMATCH = "BINDING_PROJECT_MISMATCH"

# Working-state-only refusal reasons (never emitted by the published
# single-world path, whose caller supplies exactly one approved world).
_MULTI_WORLD = "multi_world_context"
_NO_APPROVED = "no_unique_approved_world_revision"


def classify_placement_consumer_from_facts(facts: dict) -> dict:
    """Classify one occurrence's placement consumer from loaded facts.

    ``facts`` grammar (all values caller-loaded; see module docstring):

      occurrence_id           str
      subject                 None | {"kind", "id", "valid": bool,
                              "invalid_detail": dict | None}
      world_contexts          list of {"world_id", "project_id",
                              "approved_revision":
                                  None | {"id", "snapshot_hash"},
                              "targets": list of {"kind", "id"}}
      transform_is_identity   bool
      revision                {"id", "project_id", "closed": bool,
                              "interpretation_hash": str | None}

    ``closed`` means the production-revisions row is present (the
    pinned M14 rule); an absent retained closure suppresses the
    interpretation fact instead.

    Returns exactly one of:

      {"outcome": "CLEAN_A6"}
      {"outcome": "UNIQUE_A4", "placement_contract": {...},
       "entry_facts": {...}}
      {"outcome": "UNRESOLVED", "reason": str, "detail": dict}
    """
    occurrence_id = facts["occurrence_id"]
    subject = facts.get("subject")
    if subject is None:
        # no authority subject -> no A4 consumer in the predecessor rule
        return {"outcome": CLEAN_A6}
    if not subject.get("valid", True):
        return {"outcome": UNRESOLVED, "reason": _SUBJECT_INVALID,
                "detail": dict(subject.get("invalid_detail") or {})}

    contexts = facts.get("world_contexts") or []
    if not contexts:
        return {"outcome": CLEAN_A6}
    if len(contexts) > 1:
        return {"outcome": UNRESOLVED, "reason": _MULTI_WORLD,
                "detail": {
                    "occurrence_id": occurrence_id,
                    "worlds": sorted(c["world_id"] for c in contexts)}}

    context = contexts[0]
    approved = context.get("approved_revision")
    if approved is None:
        return {"outcome": UNRESOLVED, "reason": _NO_APPROVED,
                "detail": {"occurrence_id": occurrence_id,
                           "world_id": context["world_id"]}}

    revision = facts["revision"]
    if context.get("project_id") != revision.get("project_id"):
        return {"outcome": UNRESOLVED, "reason": _PROJECT_MISMATCH,
                "detail": {"occurrence_id": occurrence_id,
                           "world_id": context["world_id"]}}

    targets = context.get("targets") or []
    if len(targets) > 1:
        return {"outcome": UNRESOLVED, "reason": _TARGET_CONFLICT,
                "detail": {"occurrence_id": occurrence_id,
                           "targets": list(targets)}}
    if not targets:
        return {"outcome": CLEAN_A6}

    # exactly one A4 target: the predecessor prerequisite order
    if not facts.get("transform_is_identity", False):
        return {"outcome": UNRESOLVED, "reason": _TRANSFORM_CONFLICT,
                "detail": {"occurrence_id": occurrence_id}}
    if not revision.get("closed", False):
        # pinned-M14 semantics: fires only when the production-revisions
        # row itself is absent (a missing closure instead suppresses the
        # interpretation fact below)
        return {"outcome": UNRESOLVED, "reason": _SUBJECT_INVALID,
                "detail": {"occurrence_id": occurrence_id,
                           "reason": "production_revision_not_closed"}}
    interpretation_hash = revision.get("interpretation_hash")
    if interpretation_hash is None:
        return {"outcome": UNRESOLVED, "reason": _INTERPRETATION_REQUIRED,
                "detail": {"occurrence_id": occurrence_id,
                           "production_revision_id": revision["id"]}}

    return {
        "outcome": UNIQUE_A4,
        "placement_contract": {
            "owner": "A4_SPATIAL",
            "spatial_world_id": context["world_id"],
            "spatial_world_revision_id": approved["id"],
            "spatial_world_revision_hash": approved["snapshot_hash"],
            "target_kind": targets[0]["kind"],
            "target_id": targets[0]["id"],
        },
        "entry_facts": {
            "occurrence_id": occurrence_id,
            "production_revision_id": revision["id"],
            "authority_subject": {"kind": subject["kind"],
                                  "id": subject["id"]},
            "spatial_interpretation_hash": interpretation_hash,
        },
    }
