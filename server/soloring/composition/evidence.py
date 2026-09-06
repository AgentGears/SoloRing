"""One shared schema-1 identity-operation evidence validator (§12.2/§16.6).

Both the async historical verifier (impacts.verify_identity_history) and
the synchronous recovery verifier consume this exact contract so their
checklists can never diverge. Raises ValueError with a stable message on
any violation.
"""

from __future__ import annotations

from soloring.composition.canonical import (
    WorkingSpec,
    build_request_value,
    request_fingerprint,
)
from soloring.composition.impacts import CARDINALITY, _TERMINATES
from soloring.spatial.math import (
    JS_SAFE_MAX,
    JS_SAFE_MIN,
    Transform,
    UDEG_MIN,
)

_SOURCE_KINDS = ("production_revision", "composition_revision")


def _check(cond: bool, message: str) -> None:
    if not cond:
        raise ValueError(message)


def validate_target_working_spec(value: object) -> WorkingSpec:
    """Exact frozen target-spec grammar (shared with recovery)."""
    _check(isinstance(value, dict), "target spec must be an object")
    _check(set(value) == {"display_name", "source", "visible", "transform"},
           "target spec keys must be exactly "
           "{display_name, source, visible, transform}")
    src = value["source"]
    _check(isinstance(src, dict) and set(src) == {"kind", "revision_id"},
           "target spec source keys must be exactly {kind, revision_id}")
    _check(src["kind"] in _SOURCE_KINDS, "target spec source kind invalid")
    name = value["display_name"]
    _check(isinstance(name, str) and 1 <= len(name.strip()) <= 500
           and name == name.strip(),
           "target spec display_name grammar invalid")
    _check(isinstance(value["visible"], bool),
           "target spec visible must be a boolean")
    tr = value["transform"]
    _check(isinstance(tr, dict) and set(tr) == {
        "translation_mm", "rotation_udeg"},
        "target spec transform keys invalid")
    for key in ("translation_mm", "rotation_udeg"):
        vec = tr[key]
        _check(isinstance(vec, list) and len(vec) == 3,
               f"target spec {key} must have exactly 3 values")
        for v in vec:
            _check(isinstance(v, int) and not isinstance(v, bool),
                   f"target spec {key} must contain integers")
            _check(JS_SAFE_MIN <= v <= JS_SAFE_MAX,
                   f"target spec {key} outside JS-safe domain")
    for v in tr["rotation_udeg"]:
        _check(UDEG_MIN <= v < UDEG_MIN + 360_000_000,
               "target spec rotation not canonically normalized")
    return WorkingSpec(
        display_name=name, source_kind=src["kind"],
        revision_id=src["revision_id"], visible=value["visible"],
        transform=Transform(tuple(tr["translation_mm"]),
                             tuple(tr["rotation_udeg"])),
    )


def validate_operation_evidence(
    parsed: dict,
    *,
    row_composition_id: str,
    row_kind: str,
    row_before: int,
    row_after: int,
    row_request_fingerprint: str,
    row_impact_fingerprint: str,
    normalized_sources: list,   # [(occurrence_id, terminates_identity)]
    normalized_targets: list,   # [occurrence_id]
) -> None:
    """The complete frozen §12.2 semantic checklist over one operation.

    Callers pass the canonical parsed operation JSON and the normalized
    row projections; everything else is derived and cross-checked here.
    """
    # top-level grammar
    _check(isinstance(parsed, dict), "operation evidence must be an object")
    _check(set(parsed) == {
        "schema_version", "composition_id", "kind",
        "working_version_before", "working_version_after",
        "request_fingerprint", "impact_fingerprint", "sources", "targets",
    }, "operation evidence keys invalid")
    _check(parsed["schema_version"] == 1, "operation schema_version != 1")
    # row-field equivalence
    _check(parsed["composition_id"] == row_composition_id,
           "operation JSON composition_id differs from row")
    _check(parsed["kind"] == row_kind,
           "operation JSON kind differs from operation_kind")
    _check(parsed["working_version_before"] == row_before,
           "operation JSON working_version_before differs from row")
    _check(parsed["working_version_after"] == row_after,
           "operation JSON working_version_after differs from row")
    _check(parsed["request_fingerprint"] == row_request_fingerprint,
           "operation JSON request_fingerprint differs from row")
    _check(parsed["impact_fingerprint"] == row_impact_fingerprint,
           "operation JSON impact_fingerprint differs from row")
    # normalized edge equivalence (ids AND termination flags)
    json_sources = parsed["sources"]
    json_targets = parsed["targets"]
    _check(isinstance(json_sources, list), "sources must be a list")
    _check(isinstance(json_targets, list), "targets must be a list")
    _check([s["occurrence_id"] for s in json_sources]
           == [s[0] for s in normalized_sources],
           "source edges differ from operation evidence")
    _check([t["occurrence_id"] for t in json_targets] == normalized_targets,
           "target edges differ from operation evidence")
    for js, (_, rs_term) in zip(json_sources, normalized_sources):
        _check(bool(js.get("terminates_identity")) == bool(rs_term),
               "normalized terminates_identity differs from evidence")
    # source AND target cardinality per frozen §2.4
    kind = row_kind
    smin, smax, texp = CARDINALITY[kind]
    n_sources = len(normalized_sources)
    _check(n_sources >= smin and (smax is None or n_sources <= smax),
           f"{kind} source cardinality invalid")
    n_targets = len(normalized_targets)
    if texp is None:
        _check(n_targets >= 2, f"{kind} requires 2 or more targets")
    else:
        _check(n_targets == texp, f"{kind} target cardinality invalid")
    # termination-by-kind agreement
    expected_term = _TERMINATES[kind]
    for _, rs_term in normalized_sources:
        _check(bool(rs_term) == expected_term,
               "termination behavior disagrees with operation kind")
    # embedded target-spec grammar + request fingerprint rederivation
    parsed_specs = []
    for t in json_targets:
        _check("working_spec" in t, "target evidence missing spec")
        parsed_specs.append(validate_target_working_spec(t["working_spec"]))
    rederived = build_request_value(
        composition_id=row_composition_id, kind=kind,
        source_occurrence_ids=[s[0] for s in normalized_sources],
        target_specs=parsed_specs)
    _check(request_fingerprint(rederived) == row_request_fingerprint,
           "embedded target specs do not re-derive the stored request "
           "fingerprint")
