"""M5A-2 — Wire and capability layer (M5 plan §14-§16, §64-§66).

Adversarial matrix for normalization determinism, dialect handling, malformed
payloads, prompt-id validation, WS events, system info, capability tri-states,
canonical report stability, queue/history dedupe compatibility, marker-conflict
visibility, and the structural isolation rule (raw parsing confined to
wire.py).
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from soloring.domain.canonical import canonical_json_bytes
from soloring.errors import ErrorCode
from soloring.executors.comfy.capabilities import (
    CancellationCapability,
    CancellationMode,
    ComfyCapabilityReport,
    Evidence,
    FeatureState,
    ReadinessStatus,
    evaluate_readiness,
    report_payload,
    unprobed_report,
)
from soloring.executors.comfy.models import (
    ComfyResponseError,
    JobState,
    NormalizedComfyJob,
    SoloringMarker,
)
from soloring.executors.comfy.wire import (
    normalize_history_response,
    normalize_queue_response,
    normalize_submit_response,
    normalize_system_response,
    normalize_upload_response,
    normalize_ws_event,
    normalized_payload,
)
from soloring.settings import BASE_DIR

MARKER = {"soloring": {"generation_id": "g" * 36, "attempt_id": "a" * 36}}


def _queue_dialect_a(prompt_id="p-1", extra=None, running=True):
    return {
        "queue_running": [[0, prompt_id, {}, extra if extra is not None else MARKER, []]]
        if running
        else [],
        "queue_pending": [] if running else [[1, prompt_id, {}, extra if extra is not None else MARKER, []]],
    }


def _queue_dialect_b(prompt_id="p-1", extra=None, running=True):
    entry = {"prompt_id": prompt_id, "extra_data": extra if extra is not None else MARKER}
    return {
        "queue_running": [entry] if running else [],
        "queue_pending": [] if running else [entry],
    }


def _history_entry(status="completed", outputs=None, extra=None):
    return {
        "prompt": [0, "p-1", {}, extra if extra is not None else MARKER, []],
        "outputs": outputs or {},
        "status": {"status_str": status, "messages": []},
    }


# --- determinism + permutations -------------------------------------------------


def test_normalize_twice_canonical_equality():
    raw = _queue_dialect_a()
    a = normalized_payload(normalize_queue_response(raw))
    b = normalized_payload(normalize_queue_response(raw))
    assert canonical_json_bytes(a) == canonical_json_bytes(b)


def test_key_order_permutations_same_normalized_result():
    a = normalize_queue_response(_queue_dialect_a())
    # Same payload with reversed top-level key order.
    raw_b = dict(reversed(list(_queue_dialect_b().items())))
    b = normalize_queue_response(raw_b)
    # Both dialects produce the SAME semantic model for the same job.
    assert [(j.prompt_id, j.state, j.marker) for j in a] == [
        (j.prompt_id, j.state, j.marker) for j in b
    ]


def test_dialect_a_and_b_same_semantic_model():
    ja = normalize_queue_response(_queue_dialect_a("shared-p"))
    jb = normalize_queue_response(_queue_dialect_b("shared-p"))
    assert len(ja) == len(jb) == 1
    assert ja[0].prompt_id == jb[0].prompt_id == "shared-p"
    assert ja[0].state is jb[0].state is JobState.RUNNING
    assert ja[0].marker == jb[0].marker == SoloringMarker("g" * 36, "a" * 36)


def test_history_key_permutation_deterministic():
    raw = {"p-1": _history_entry()}
    shuffled = {"other": _history_entry(), "p-1": _history_entry()}
    shuffled_only = {"p-1": shuffled["p-1"]}
    a = normalized_payload(normalize_history_response(raw))
    b = normalized_payload(normalize_history_response(shuffled_only))
    assert canonical_json_bytes(a) == canonical_json_bytes(b)


# --- malformed matrix -------------------------------------------------------------


def test_unsupported_queue_dialect_fails_closed():
    # Entries that are neither tuples nor objects with prompt_id.
    with pytest.raises(ComfyResponseError):
        normalize_queue_response({"queue_running": [42], "queue_pending": []})


def test_missing_prompt_id_rejected():
    with pytest.raises(ComfyResponseError):
        normalize_queue_response({"queue_running": [[0]], "queue_pending": []})


def test_overlong_prompt_id_rejected():
    with pytest.raises(ComfyResponseError):
        normalize_queue_response(_queue_dialect_a("x" * 200))


def test_control_characters_in_prompt_id_rejected():
    with pytest.raises(ComfyResponseError):
        normalize_queue_response(_queue_dialect_a("p\x00-1"))


def test_missing_queue_keys_rejected():
    with pytest.raises(ComfyResponseError):
        normalize_queue_response({"queue_running": []})


def test_unknown_state_enum_maps_to_unknown_bounded():
    rec = normalize_history_response(
        {"p-1": _history_entry(status="weird_new_state")}
    )["p-1"]
    assert rec.terminal_state is JobState.UNKNOWN


def test_oversized_diagnostic_bounded():
    marker = {"soloring": {"generation_id": "g" * 5000, "attempt_id": "a" * 36}}
    job = normalize_queue_response(_queue_dialect_a("p-1", extra=marker))[0]
    assert len(job.marker.generation_id) == 5000  # marker itself is trusted
    # Diagnostics, by contrast, are bounded:
    from soloring.executors.comfy.wire import _diagnostic

    assert len(_diagnostic({"x": "y" * 10000})) <= 120 + len(repr({"x": ""}))


def test_non_object_root_rejected():
    with pytest.raises(ComfyResponseError):
        normalize_queue_response([1, 2, 3])
    with pytest.raises(ComfyResponseError):
        normalize_history_response("nope")


# --- history ----------------------------------------------------------------------


def test_history_valid_terminal_success():
    outputs = {
        "15": {"gifs": [{"filename": "v-0.png", "subfolder": "s", "type": "output"}]}
    }
    rec = normalize_history_response({"p-1": _history_entry(outputs=outputs)})["p-1"]
    assert rec.terminal_state is JobState.SUCCEEDED
    assert len(rec.outputs) == 1
    out = rec.outputs[0]
    assert (out.node, out.output_field, out.filename, out.subfolder, out.type) == (
        "15", "gifs", "v-0.png", "s", "output"
    )
    assert rec.marker == SoloringMarker("g" * 36, "a" * 36)


def test_history_executor_error():
    rec = normalize_history_response(
        {"p-1": _history_entry(
            status="error",
        )}
    )["p-1"]
    # status with messages empty → error None but state FAILED
    assert rec.terminal_state is JobState.FAILED


def test_history_unrelated_nonfile_data_tolerated():
    # Audit F14: live nodes attach scalars/text/metadata alongside real
    # output files. Unrelated non-file data must not reject the history
    # before the resolver can ignore it; strictness for DECLARED bindings
    # is enforced by resolve_comfy_outputs' binding-level cardinality.
    outputs = {
        "15": {"gifs": [
            {"filename": "v-0.webp", "subfolder": "", "type": "output"},
            {"subfolder": "", "type": "output"},   # dict without filename
            "bare-string-metadata",                # non-dict list item
        ]},
        "7": {"status": "completed"},              # scalar field
        "8": {"text": ["a caption", {"detail": 1}]},
    }
    rec = normalize_history_response(
        {"p-1": _history_entry(outputs=outputs)}
    )["p-1"]
    assert [(r.node, r.filename) for r in rec.outputs] == [("15", "v-0.webp")]


def test_history_invalid_filename_in_file_structure_rejected():
    # A dict that IS a file reference (has a filename key) but carries an
    # invalid one stays strictly rejected.
    bad = {"15": {"gifs": [{"filename": "", "subfolder": "",
                            "type": "output"}]}}
    with pytest.raises(ComfyResponseError):
        normalize_history_response({"p-1": _history_entry(outputs=bad)})


def test_history_success_dialect_from_live_0_33():
    # M5B-1 fixed-loop regression: live ComfyUI 0.33.0 reports terminal
    # success as status_str "success" (fixture captured from the dedicated
    # instance); older deployments said "completed". Both must normalize to
    # SUCCEEDED — a dialect rename can never strand an observed prompt as
    # UNKNOWN.
    for status_str in ("success", "completed"):
        rec = normalize_history_response({"p": {
            "prompt": [0, "p", {}, {}, []],
            "outputs": {},
            "status": {"status_str": status_str, "messages": []},
        }})["p"]
        assert rec.terminal_state.value == "succeeded", status_str


def test_history_output_ordering_deterministic():
    outputs = {
        "9": {"images": [{"filename": "b.png", "subfolder": "", "type": "output"}]},
        "15": {
            "gifs": [
                {"filename": "z.png", "subfolder": "", "type": "output"},
                {"filename": "a.png", "subfolder": "", "type": "output"},
            ]
        },
    }
    rec = normalize_history_response({"p-1": _history_entry(outputs=outputs)})["p-1"]
    names = [(o.node, o.filename) for o in rec.outputs]
    assert names == [("15", "a.png"), ("15", "z.png"), ("9", "b.png")]


# --- queue/history dedupe compatibility + marker conflicts -------------------------


def test_queue_and_history_same_prompt_dedupe_compatible():
    """One prompt visible in BOTH queue and history normalizes to records
    sharing prompt_id + marker — M5A-6 can dedupe by prompt_id without
    knowing the source dialect."""
    jobs = normalize_queue_response(_queue_dialect_a("same-p"))
    history = normalize_history_response({"same-p": _history_entry()})
    assert jobs[0].prompt_id == history["same-p"].prompt_id
    assert jobs[0].marker.as_pair() == history["same-p"].marker.as_pair()


def test_marker_conflict_remains_visible_not_merged():
    """queue P marker M1 vs history P marker M2: both records keep their own
    markers — inconsistency stays inspectable for M5A-6's invariant check."""
    m1 = {"soloring": {"generation_id": "g1", "attempt_id": "a1"}}
    m2 = {"soloring": {"generation_id": "g2", "attempt_id": "a2"}}
    jobs = normalize_queue_response(_queue_dialect_a("p", extra=m1))
    history = normalize_history_response({"p": _history_entry(extra=m2)})
    assert jobs[0].marker.as_pair() == ("g1", "a1")
    assert history["p"].marker.as_pair() == ("g2", "a2")
    assert jobs[0].marker != history["p"].marker


def test_no_marker_normalizes_to_none():
    jobs = normalize_queue_response(_queue_dialect_a("p", extra={"unrelated": 1}))
    assert jobs[0].marker is None
    history = normalize_history_response(
        {"p": _history_entry(extra={"custom_node": {"x": 1}})}
    )
    assert history["p"].marker is None


# --- websocket -------------------------------------------------------------------------


def _ws(kind, payload=None, node=None):
    return [kind, payload or {}, node]


def test_ws_execution_start():
    ev = normalize_ws_event(_ws("execution_start", {"prompt_id": "p-1"}))
    assert ev.kind == "execution_start" and ev.prompt_id == "p-1"


def test_ws_executing():
    ev = normalize_ws_event(_ws("executing", {"prompt_id": "p-1"}, 12))
    assert ev.kind == "executing"
    assert ev.progress.node == "12"


def test_ws_progress():
    ev = normalize_ws_event(_ws("progress", {"value": 3, "max": 10}, "31"))
    assert ev.kind == "progress"
    assert ev.progress.current == 3 and ev.progress.total == 10


def test_ws_execution_success():
    ev = normalize_ws_event(_ws("execution_success", {"prompt_id": "p-1"}))
    assert ev.kind == "execution_success"


def test_ws_execution_error():
    ev = normalize_ws_event(_ws("execution_error", {"prompt_id": "p-1"}))
    assert ev.kind == "execution_error"


def test_ws_unknown_event_bounded():
    ev = normalize_ws_event(_ws("brand_new_event", {"huge": "x" * 5000}))
    assert ev.kind == "unknown"
    assert len(ev.diagnostic or "") <= 200  # bounded via _diagnostic


def test_ws_object_dialect():
    ev = normalize_ws_event({"type": "executing", "data": {"prompt_id": "p-9"}})
    assert ev.kind == "executing" and ev.prompt_id == "p-9"


def test_ws_malformed_rejected():
    with pytest.raises(ComfyResponseError):
        normalize_ws_event("not-a-list")
    with pytest.raises(ComfyResponseError):
        normalize_ws_event([42, {}])


# --- system info --------------------------------------------------------------------------


def test_system_valid_nested():
    info = normalize_system_response(
        {"system": {"comfyui_version": "0.3.14", "build": "abc"}}
    )
    assert info.version == "0.3.14" and info.build == "abc"


def test_system_valid_top_level_dialect():
    info = normalize_system_response({"comfyui_version": "1.0.0"})
    assert info.version == "1.0.0"


def test_system_malformed():
    with pytest.raises(ComfyResponseError):
        normalize_system_response({"system": "not-an-object"})
    with pytest.raises(ComfyResponseError):
        normalize_system_response({})


# --- upload + submit -------------------------------------------------------------------------


def test_upload_normalization():
    ref = normalize_upload_response({"name": "hash (1).png", "subfolder": "sub"})
    assert ref.name == "hash (1).png" and ref.subfolder == "sub"
    with pytest.raises(ComfyResponseError):
        normalize_upload_response({"name": ""})


def test_submit_normalization():
    assert normalize_submit_response({"prompt_id": "abc"}) == "abc"
    with pytest.raises(ComfyResponseError):
        normalize_submit_response({})
    with pytest.raises(ComfyResponseError):
        normalize_submit_response({"prompt_id": "x" * 200})


# --- capability report -------------------------------------------------------------------------


def _report(features=None, evidence=()):
    return ComfyCapabilityReport(
        executor_version="0.3.14",
        wire_dialects=("queue_list_v1", "history_v1"),
        features=features or {},
        evidence=evidence,
        cancellation=CancellationCapability(
            mode=CancellationMode.SOFT_ONLY,
            targeting_key=None,
            uniqueness_guarantee=None,
        ),
    )


def test_capability_tri_states():
    r = unprobed_report("0.3.14")
    for k in (
        "prompt_submission", "queue_observation", "targeted_history",
        "marker_roundtrip", "websocket_progress", "input_upload",
        "output_view", "pending_cancel", "running_cancel",
    ):
        assert r.feature(k) is FeatureState.UNKNOWN


def test_readiness_unreachable():
    assert evaluate_readiness(unprobed_report(), reachable=False) is (
        ReadinessStatus.UNAVAILABLE
    )


def test_readiness_unknown_mandatory_is_unavailable():
    r = unprobed_report()
    assert evaluate_readiness(r, reachable=True) is ReadinessStatus.UNAVAILABLE


def test_readiness_unsupported_mandatory_is_incompatible():
    r = _report(
        features={"marker_roundtrip": FeatureState.UNSUPPORTED},
        evidence=(Evidence("marker_roundtrip", FeatureState.UNSUPPORTED,
                           "endpoint_rejected", "extra_data dropped"),),
    )
    assert evaluate_readiness(r, reachable=True) is ReadinessStatus.INCOMPATIBLE


def test_readiness_all_supported_is_ready():
    features = {
        "prompt_submission": FeatureState.SUPPORTED,
        "queue_observation": FeatureState.SUPPORTED,
        "targeted_history": FeatureState.SUPPORTED,
        "marker_roundtrip": FeatureState.SUPPORTED,
        "input_upload": FeatureState.SUPPORTED,
        "output_view": FeatureState.SUPPORTED,
    }
    r = _report(features=features)
    assert evaluate_readiness(r, reachable=True) is ReadinessStatus.READY


def test_evidence_methods_distinguish_provenance():
    e1 = Evidence("marker_roundtrip", FeatureState.SUPPORTED, "marker_canary")
    e2 = Evidence("input_upload", FeatureState.UNSUPPORTED, "endpoint_rejected")
    e3 = Evidence("websocket_progress", FeatureState.UNKNOWN, "unprobed")
    r = _report(evidence=(e1, e2, e3))
    p = report_payload(r)
    methods = {(e["feature"], e["method"]) for e in p["evidence"]}
    assert ("marker_roundtrip", "marker_canary") in methods
    assert ("input_upload", "endpoint_rejected") in methods
    assert ("websocket_progress", "unprobed") in methods


def test_capability_report_canonical_bytes_stable():
    r = _report(
        features={"input_upload": FeatureState.SUPPORTED},
        evidence=(Evidence("input_upload", FeatureState.SUPPORTED, "endpoint_probe"),),
    )
    a = canonical_json_bytes(report_payload(r))
    b = canonical_json_bytes(report_payload(_report(
        features={"input_upload": FeatureState.SUPPORTED},
        evidence=(Evidence("input_upload", FeatureState.SUPPORTED, "endpoint_probe"),),
    )))
    assert a == b


def test_cancellation_mode_structured_not_boolean():
    p = report_payload(_report())
    assert p["cancellation"]["mode"] == "soft_only"
    assert set(p["cancellation"]) == {
        "mode", "targeting_key", "uniqueness_guarantee", "retry_safety",
    }


def test_version_diagnostic_not_authoritative():
    """A high version alone never implies capability (invariant 7): the
    report with version but all-unknown features is UNAVAILABLE, not READY."""
    r = unprobed_report(executor_version="99.0.0")
    assert r.executor_version == "99.0.0"
    assert evaluate_readiness(r, reachable=True) is ReadinessStatus.UNAVAILABLE


# --- structural isolation: raw parsing confined to wire.py -----------------------------


def test_no_raw_wire_parsing_outside_wire_py():
    """AST rule: comfy package modules other than wire.py must not index
    queue/history-style raw tuples or reference raw response keys."""
    comfy_dir = BASE_DIR / "server" / "soloring" / "executors" / "comfy"
    offenders = []
    for path in comfy_dir.glob("*.py"):
        if path.name == "wire.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            # Raw queue-tuple indexing (entry[1]/entry[3]-style) appears as
            # Subscript on a plain Name; flag constants >= 1 subscripts on
            # names matching entry-ish patterns.
            if (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Name)
                and node.value.id in ("entry", "raw", "payload", "prompt_tuple")
                and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, int)
                and node.slice.value >= 1
            ):
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == [], f"raw wire indexing outside wire.py: {offenders}"


def test_comfy_package_does_not_import_db_or_worker():
    """The Comfy adapter is database/ownership-free (M5 amendment §3): the
    worker orchestrates; the adapter only speaks remote semantics."""
    comfy_dir = BASE_DIR / "server" / "soloring" / "executors" / "comfy"
    banned = ("soloring.db", "soloring.worker", "sqlalchemy")
    for path in comfy_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for n in names:
                if any(n == b or n.startswith(b + ".") for b in banned):
                    raise AssertionError(
                        f"{path.name} imports {n!r} — Comfy adapter must stay "
                        "DB/ownership-free"
                    )
