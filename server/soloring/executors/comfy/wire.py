"""Comfy wire normalizers (M5A-2; M5 plan §14-§15).

The ONLY module permitted to interpret raw Comfy response shapes. Everything
above this file sees the closed normalized models from models.py.

Purity: normalizers are deterministic functions of their raw payload — no DB,
filesystem, settings mutation, network, or clock. Determinism is fixture-
pinned: same raw payload → byte-identical canonical serialization (via the
SoloRing canonical serializer), and key-order permutations normalize
identically.

Dialect policy: recognized dialects are explicit; detection FAILS CLOSED when
a payload could plausibly match multiple dialects with different
interpretations. Malformed-in-recognized-dialect raises ComfyResponseError
(COMFY_RESPONSE_INVALID), which is distinct from a capability conclusion.
"""

from __future__ import annotations

import json
from typing import Any

from soloring.executors.comfy.models import (
    DIAGNOSTIC_MAX,
    ComfyResponseError,
    JobState,
    NormalizedComfyJob,
    NormalizedHistoryRecord,
    NormalizedOutputReference,
    NormalizedProgress,
    NormalizedSystemInfo,
    NormalizedUploadReference,
    NormalizedWsEvent,
    SoloringMarker,
)

# Bounded identity validation (M5 §34): prompt ids must be short, printable,
# control-free strings. Not assumed to be UUIDs.
PROMPT_ID_MAX = 128
_CONTROL = {chr(c) for c in range(32)} | {chr(127)}

# Known Comfy history status_str values (dialect A: upstream history).
_HISTORY_STATUS_MAP = {
    # Old dialect (<= ~0.3.27) used "completed"; live 0.33.0 uses "success"
    # (M5B-1 fingerprint fixture data/comfy-fingerprint). Both are accepted:
    # normalizers name dialects, orchestration never sees raw strings.
    "completed": JobState.SUCCEEDED,
    "success": JobState.SUCCEEDED,
    "error": JobState.FAILED,
    "cancelled": JobState.CANCELLED,
    "interrupted": JobState.CANCELLED,
}


# Hard sanity bound for IDENTITY-BEARING remote values (re-audit R6):
# preserved EXACTLY or rejected — never silently rewritten, since downstream
# validators and graph bindings treat them as authoritative.
IDENTITY_MAX = 1024


def _identity_value(value: str, what: str) -> str:
    if len(value) > IDENTITY_MAX:
        raise ComfyResponseError(
            f"{what}: exceeds identity bound ({len(value)} > {IDENTITY_MAX})"
        )
    return value


def _diagnostic(value: object) -> str:
    """Bound an unknown remote token: printable, truncated, never whole."""
    text = repr(value)
    text = "".join(ch if ch not in _CONTROL else "?" for ch in text)
    return text[:DIAGNOSTIC_MAX]


def _require_prompt_id(value: object, what: str) -> str:
    if not isinstance(value, str) or not value:
        raise ComfyResponseError(f"{what}: missing prompt_id")
    if len(value) > PROMPT_ID_MAX:
        raise ComfyResponseError(f"{what}: overlong prompt_id")
    if any(ch in _CONTROL for ch in value):
        raise ComfyResponseError(f"{what}: control characters in prompt_id")
    return value


def _marker_from_extra_data(extra: object) -> SoloringMarker | None:
    """Narrow extra_data to exactly the SoloRing submission marker."""
    if not isinstance(extra, dict):
        return None
    soloring = extra.get("soloring")
    if not isinstance(soloring, dict):
        return None
    generation_id = soloring.get("generation_id")
    attempt_id = soloring.get("attempt_id")
    if isinstance(generation_id, str) and isinstance(attempt_id, str):
        return SoloringMarker(generation_id=generation_id, attempt_id=attempt_id)
    return None


def _as_dict(raw: object, what: str) -> dict:
    if not isinstance(raw, dict):
        raise ComfyResponseError(f"{what}: expected object, got {type(raw).__name__}")
    return raw


# --- system info -----------------------------------------------------------------


def normalize_system_response(raw: object) -> NormalizedSystemInfo:
    body = _as_dict(raw, "system_stats")
    system = body.get("system")
    if system is None:
        # Dialect variant: version at top level.
        version = body.get("comfyui_version") if isinstance(
            body.get("comfyui_version"), str
        ) else None
        if version is None:
            raise ComfyResponseError("system_stats: no version information")
        return NormalizedSystemInfo(version=version[:DIAGNOSTIC_MAX])
    system = _as_dict(system, "system_stats.system")
    version = system.get("comfyui_version")
    build = system.get("build")
    return NormalizedSystemInfo(
        version=version[:DIAGNOSTIC_MAX] if isinstance(version, str) else None,
        build=build[:DIAGNOSTIC_MAX] if isinstance(build, str) else None,
    )


# --- queue -------------------------------------------------------------------------


def _queue_entries(raw_queue: object, key: str) -> list:
    entries = raw_queue.get(key)
    if entries is None:
        raise ComfyResponseError(f"queue: missing {key}")
    if not isinstance(entries, list):
        raise ComfyResponseError(f"queue: {key} is not a list")
    return entries


def _job_from_list_dialect(entry: object, position_kind: str) -> NormalizedComfyJob:
    """Dialect A (upstream): queue entries are tuples
    [number, prompt_id, prompt_graph, extra_data, outputs_to_execute]."""
    if not isinstance(entry, (list, tuple)) or len(entry) < 4:
        raise ComfyResponseError(
            f"queue {position_kind}: malformed entry ({_diagnostic(entry)})"
        )
    prompt_id = _require_prompt_id(entry[1], f"queue {position_kind}")
    marker = _marker_from_extra_data(entry[3])
    return NormalizedComfyJob(
        prompt_id=prompt_id,
        state=JobState.RUNNING if position_kind == "running" else JobState.PENDING,
        marker=marker,
    )


def _job_from_object_dialect(entry: object, position_kind: str) -> NormalizedComfyJob:
    """Dialect B (object entries): {"prompt_id":..., "extra_data":...}."""
    obj = _as_dict(entry, f"queue {position_kind}")
    prompt_id = _require_prompt_id(obj.get("prompt_id"), f"queue {position_kind}")
    marker = _marker_from_extra_data(obj.get("extra_data"))
    return NormalizedComfyJob(
        prompt_id=prompt_id,
        state=JobState.RUNNING if position_kind == "running" else JobState.PENDING,
        marker=marker,
    )


def _entry_is_object_dialect(entry: object) -> bool:
    return isinstance(entry, dict)


def classify_queue_dialect(raw: object) -> str | None:
    """Name the observed raw /queue shape (probe/diagnostics only).

    The classifier — not a parser: it never produces normalized jobs, it
    only names which dialect ``normalize_queue_response`` will accept, so
    raw-dialect knowledge stays confined to this module (M5B-1 boundary).
    """
    if not isinstance(raw, dict) or not raw:
        return None
    if "queue_running" in raw or "queue_pending" in raw:
        return "queue_keyed_lists"
    first = next(iter(raw.values()), None)
    if isinstance(first, list):
        return "queue_flat_lists"
    return None


def normalize_queue_response(raw: object) -> tuple[NormalizedComfyJob, ...]:
    """Normalize /queue into running-then-pending job tuples (deterministic)."""
    body = _as_dict(raw, "queue")
    running = _queue_entries(body, "queue_running")
    pending = _queue_entries(body, "queue_pending")

    jobs: list[NormalizedComfyJob] = []
    for position_kind, entries in (("running", running), ("pending", pending)):
        for entry in entries:
            if _entry_is_object_dialect(entry):
                jobs.append(_job_from_object_dialect(entry, position_kind))
            else:
                jobs.append(_job_from_list_dialect(entry, position_kind))
    return tuple(jobs)


# --- history -----------------------------------------------------------------------


def _history_status(status: object) -> JobState:
    status = _as_dict(status, "history status")
    status_str = status.get("status_str")
    if not isinstance(status_str, str):
        return JobState.UNKNOWN
    mapped = _HISTORY_STATUS_MAP.get(status_str)
    return mapped if mapped is not None else JobState.UNKNOWN


def _history_outputs(node_outputs: object, prompt_id: str) -> tuple[NormalizedOutputReference, ...]:
    node_outputs = _as_dict(node_outputs, "history outputs")
    refs: list[NormalizedOutputReference] = []
    for node, fields in node_outputs.items():
        fields = _as_dict(fields, f"history outputs[{node}]")
        for output_field, files in fields.items():
            # Tolerant of UNRELATED non-file data (audit F14): live nodes
            # attach scalars/text/metadata alongside real output files, and
            # the M5A-9 resolver ignores undeclared nodes anyway. Anything
            # that IS a file-reference structure stays strictly validated.
            if not isinstance(files, list):
                continue
            for f in files:
                if not isinstance(f, dict):
                    continue  # unrelated payload, not a file reference
                filename = f.get("filename")
                if filename is None:
                    continue  # dict without a filename: non-file data
                if not isinstance(filename, str) or not filename:
                    raise ComfyResponseError(
                        f"history output for {prompt_id}: invalid filename"
                    )
                refs.append(
                    NormalizedOutputReference(
                        node=_identity_value(
                            str(node), "history output node"),
                        output_field=_identity_value(
                            str(output_field), "history output field"),
                        filename=filename,
                        subfolder=f.get("subfolder") or "",
                        type=f.get("type") or "",
                    )
                )
    # Deterministic ordering: node, field, filename.
    refs.sort(key=lambda r: (r.node, r.output_field, r.filename))
    return tuple(refs)


def normalize_history_response(raw: object) -> dict[str, NormalizedHistoryRecord]:
    """Normalize /history or /history/{prompt_id} keyed by prompt_id.

    A single prompt visible in both queue and history normalizes to
    representations sharing prompt_id + marker, so M5A-6 can deduplicate by
    prompt_id without knowing the source dialect. Conflicting markers for one
    prompt_id are PRESERVED (both records keep their own marker) — merging is
    the caller's invariant decision, never the normalizer's.
    """
    body = _as_dict(raw, "history")
    records: dict[str, NormalizedHistoryRecord] = {}
    for prompt_id, entry in body.items():
        prompt_id = _require_prompt_id(prompt_id, "history key")
        entry = _as_dict(entry, f"history[{prompt_id}]")

        # Upstream history nests [number, prompt_id, graph, extra_data, ...]
        # under "prompt"; extra_data may also appear at the top level in some
        # dialects.
        marker = _marker_from_extra_data(entry.get("extra_data"))
        prompt_tuple = entry.get("prompt")
        if isinstance(prompt_tuple, (list, tuple)) and len(prompt_tuple) >= 4:
            marker = marker or _marker_from_extra_data(prompt_tuple[3])

        outputs = _history_outputs(entry.get("outputs") or {}, prompt_id)
        status = _history_status(entry.get("status") or {})

        error = None
        if status is JobState.FAILED:
            messages = (entry.get("status") or {}).get("messages")
            if isinstance(messages, list) and messages:
                error = _diagnostic(messages[-1])

        records[prompt_id] = NormalizedHistoryRecord(
            prompt_id=prompt_id,
            terminal_state=status,
            outputs=outputs,
            error=error,
            marker=marker,
        )
    return records


# --- upload -------------------------------------------------------------------------


def normalize_upload_response(raw: object) -> NormalizedUploadReference:
    body = _as_dict(raw, "upload")
    name = body.get("name")
    if not isinstance(name, str) or not name:
        raise ComfyResponseError("upload: missing name")
    subfolder = body.get("subfolder")
    return NormalizedUploadReference(
        name=_identity_value(name, "upload name"),
        subfolder=(
            _identity_value(subfolder, "upload subfolder")
            if isinstance(subfolder, str) else ""
        ),
    )


# --- submit --------------------------------------------------------------------------


def normalize_cancel_job_response(raw: object) -> bool:
    """Normalize POST /api/jobs/{id}/cancel (M5B-5).

    The pinned deployment's contract (source: server.py cancel_job_by_id):
    200 + {"cancelled": bool} — True iff a running/pending job with that id
    was actually cancelled; finished/unknown ids are idempotent no-ops
    (False). Anything else is malformed, never guessed.
    """
    body = _as_dict(raw, "cancel-job")
    cancelled = body.get("cancelled")
    if not isinstance(cancelled, bool):
        raise ComfyResponseError("cancel-job: missing boolean 'cancelled'")
    return cancelled


def normalize_submit_response(raw: object) -> str:
    body = _as_dict(raw, "submit")
    return _require_prompt_id(body.get("prompt_id"), "submit")


# --- websocket ------------------------------------------------------------------------


def normalize_ws_event(raw: object) -> NormalizedWsEvent:
    """Normalize a WS JSON message into an observational event.

    Comfy WS events arrive as JSON arrays like ["executing", {"prompt_id":...},
    node_id]; system progress arrives as ["progress", {value, max}, node_id].
    """
    if not isinstance(raw, (list, tuple)) or not raw:
        # Some dialects emit objects: {"type": ..., "data": ...}.
        if isinstance(raw, dict):
            kind = raw.get("type")
            data = raw.get("data")
            if isinstance(kind, str):
                return _ws_event_from_parts(
                    kind, data if isinstance(data, dict) else {}, raw
                )
        raise ComfyResponseError("ws: unrecognized message shape")
    kind = raw[0]
    if not isinstance(kind, str):
        raise ComfyResponseError("ws: non-string event kind")
    payload = raw[1] if len(raw) > 1 else {}
    node = raw[2] if len(raw) > 2 else None
    event = _ws_event_from_parts(
        kind, payload if isinstance(payload, dict) else {}, raw,
        node=node if isinstance(node, (str, int)) else None,
    )
    return event


def _ws_event_from_parts(
    kind: str, data: dict, raw: object, node: object = None
) -> NormalizedWsEvent:
    prompt_id = data.get("prompt_id")
    known = {
        "execution_start", "executing", "progress",
        "execution_success", "execution_error",
    }
    if kind == "progress":
        value = data.get("value")
        maximum = data.get("max")
        return NormalizedWsEvent(
            kind="progress",
            prompt_id=prompt_id if isinstance(prompt_id, str) else None,
            progress=NormalizedProgress(
                current=value if isinstance(value, int) else None,
                total=maximum if isinstance(maximum, int) else None,
                node=str(node) if node is not None else None,
            ),
        )
    if kind in known:
        return NormalizedWsEvent(
            kind=kind,
            prompt_id=prompt_id if isinstance(prompt_id, str) else None,
            progress=NormalizedProgress(node=str(node) if node is not None else None),
        )
    # Unknown remote event kind: bounded, collapses to "unknown".
    return NormalizedWsEvent(kind="unknown", diagnostic=_diagnostic(raw))


# --- canonical normalization bytes (test evidence) -----------------------------------


def normalized_payload(value: object) -> object:
    """Convert a normalized model into a JSON-safe canonical structure for
    fixture-pinning (deterministic; sorted keys come from the serializer)."""
    if isinstance(value, (NormalizedComfyJob, NormalizedHistoryRecord,
                          NormalizedWsEvent, NormalizedSystemInfo,
                          NormalizedUploadReference, NormalizedProgress,
                          SoloringMarker, NormalizedOutputReference)):
        out = {}
        for f in value.__dataclass_fields__:
            v = getattr(value, f)
            out[f] = normalized_payload(v)
        return out
    if isinstance(value, tuple):
        return [normalized_payload(v) for v in value]
    if isinstance(value, dict):
        return {k: normalized_payload(v) for k, v in value.items()}
    if isinstance(value, JobState):
        return value.value
    return value


__all__ = [
    "normalize_queue_response",
    "normalize_history_response",
    "normalize_system_response",
    "normalize_upload_response",
    "normalize_submit_response",
    "normalize_ws_event",
    "normalized_payload",
]
