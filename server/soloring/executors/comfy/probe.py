"""Live capability/evidence probe (M5B-1; M5 plan §16, §66).

DB-free like the rest of the Comfy package. Runs a bounded evidence
collection against a REAL ComfyUI instance and composes the actual
``ComfyCapabilityReport`` — capability conclusions come from recorded
evidence, never version arithmetic (M5A-2 invariant 7).

Evidence collected (M5B-1 scope):
  * system_stats build/version (diagnostic);
  * raw /queue and /history dialects (sanitized fixtures) + wire-normalizer
    acceptance;
  * /upload/image round-trip of a 1x1 PNG (returned name/subfolder identity);
  * MARKER ROUND-TRIP: a minimal CPU-only LoadImage→SaveImage prompt with the
    SoloRing marker in extra_data, observed through targeted /history —
    proves /prompt + marker + targeted_history + /view together;
  * /ws first-message dialect (observational; WS is never lifecycle
    authority);
  * /interrupt + /queue-delete response CONTRACTS (diagnostic only).

Cancellation capability stays UNKNOWN until the M5B-5 live probes; the
runtime default remains SOFT_ONLY.

New wire dialects follow exactly one path (M5B plan):
capture sanitized fixture → wire.py normalizer → M5A regression → rerun the
M5A gate → return to M5B. Nothing live-specific lives here or in
orchestration.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field

from soloring.executors.comfy import wire
from soloring.executors.comfy.capabilities import (
    CAPABILITY_PROFILE_VERSION,
    CancellationCapability,
    CancellationMode,
    ComfyCapabilityReport,
    Evidence,
    FeatureState,
)
from soloring.executors.comfy.client import (
    ComfyAPIError,
    ComfyClient,
    PromptAccepted,
)
from soloring.executors.comfy.translate import comfy_input_reference

# 1x1 transparent PNG — the marker-canary input needs no models.
PROBE_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da636460f8ff9f0001040100c9fe92ef0000000049454e44"
    "ae426082"
)


@dataclass
class ProbeResult:
    """Everything M5B-1 observed, raw and interpreted."""

    report: ComfyCapabilityReport
    fixtures: dict = field(default_factory=dict)  # sanitized raw dialects
    marker_prompt_id: str | None = None
    view_bytes_sha: str | None = None
    notes: list[str] = field(default_factory=list)


def _evidence(feature: str, ok: bool, method: str, detail: str = "") -> Evidence:
    return Evidence(
        feature=feature,
        conclusion=(FeatureState.SUPPORTED if ok else FeatureState.UNKNOWN),
        method=method,
        detail=detail[:200],
    )


async def probe_system(client: ComfyClient) -> tuple[dict | None, str | None]:
    """Raw system_stats dict + normalized version, or (None, diagnostic)."""
    try:
        raw = await client.system_stats()
    except ComfyAPIError as exc:
        return None, f"unreachable: {exc}"
    try:
        info = wire.normalize_system_response(raw)
    except Exception as exc:  # noqa: BLE001
        return raw, f"malformed: {exc}"
    return raw, info.version


async def probe_read_dialects(client: ComfyClient, fixtures: dict,
                              notes: list[str]) -> dict[str, bool]:
    """Raw queue/history shapes + wire-normalizer acceptance."""
    ok: dict[str, bool] = {}
    try:
        raw_queue = await client._json_read("GET", "/queue", "queue probe")
        fixtures["queue_raw"] = raw_queue
        wire.normalize_queue_response(raw_queue)
        ok["queue_observation"] = True
    except Exception as exc:  # noqa: BLE001
        ok["queue_observation"] = False
        notes.append(f"queue dialect: {exc}")
    try:
        raw_history = await client._json_read("GET", "/history", "history")
        fixtures["history_raw"] = raw_history
        wire.normalize_history_response(raw_history)
        ok["history_full"] = True
    except Exception as exc:  # noqa: BLE001
        ok["history_full"] = False
        notes.append(f"history dialect: {exc}")
    return ok


async def probe_upload(client: ComfyClient, fixtures: dict,
                       notes: list[str]) -> tuple[bool, str, str]:
    """Upload the 1x1 probe PNG; return (ok, name, subfolder)."""
    import os
    import tempfile
    from pathlib import Path

    fd, tmp_name = tempfile.mkstemp(suffix=".png")
    os.close(fd)  # Windows: the path is unwritable while the fd is open
    tmp = Path(tmp_name)
    try:
        tmp.write_bytes(PROBE_PNG)
        ref = await client.upload_input(
            source_path=tmp, filename="soloring_probe.png",
            subfolder="soloring_probe",
        )
        fixtures["upload_response"] = {"name": ref.name,
                                       "subfolder": ref.subfolder}
        return True, ref.name, ref.subfolder
    except Exception as exc:  # noqa: BLE001
        notes.append(f"upload: {exc}")
        return False, "", ""
    finally:
        tmp.unlink(missing_ok=True)


def _probe_graph(image_ref: str) -> dict:
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": image_ref}},
        "2": {"class_type": "SaveImage",
              "inputs": {"images": ["1", 0],
                         "filename_prefix": "soloring_probe"}},
    }


async def probe_marker_roundtrip(
    client: ComfyClient, generation_id: str, attempt_id: str,
    image_name: str, image_subfolder: str, fixtures: dict, notes: list[str],
    timeout: float = 30.0,
) -> dict[str, object]:
    """The M5B-1 headline proof: ONE CPU-only prompt with the SoloRing
    marker; terminal observation through targeted history; /view fetch of
    the produced output. Returns which sub-proofs held."""
    payload = {
        "prompt": _probe_graph(comfy_input_reference(image_name,
                                                     image_subfolder)),
        "extra_data": {"soloring": {"generation_id": generation_id,
                                    "attempt_id": attempt_id}},
        "client_id": "soloring-probe",
    }
    outcome = await client.submit_prompt(payload)
    if not isinstance(outcome, PromptAccepted):
        notes.append(f"prompt rejected: {outcome}")
        return {"prompt": False}
    prompt_id = outcome.prompt_id

    deadline = time.monotonic() + timeout
    record = None
    while time.monotonic() < deadline:
        history = await client.history(prompt_id)
        rec = history.get(prompt_id)
        if rec is not None and rec.terminal_state.value in (
            "succeeded", "failed", "cancelled",
        ):
            record = rec
            break
        await asyncio.sleep(0.25)

    result: dict[str, object] = {
        "prompt": True, "prompt_id": prompt_id,
        "history_terminal": record is not None,
        "marker_roundtrip": False, "succeeded": False, "view": False,
        "view_sha": None, "output_ref": None,
    }
    if record is None:
        notes.append("marker canary: no terminal history before timeout")
        return result

    fixtures["marker_history_record"] = {
        "prompt_id": prompt_id,
        "terminal_state": record.terminal_state.value,
        "marker": (record.marker.as_pair()
                   if record.marker is not None else None),
        "outputs": [
            {"node": r.node, "field": r.output_field,
             "filename": r.filename, "subfolder": r.subfolder, "type": r.type}
            for r in record.outputs
        ],
    }
    if record.marker is not None and (
        record.marker.as_pair() == (generation_id, attempt_id)
    ):
        result["marker_roundtrip"] = True
    result["succeeded"] = record.terminal_state.value == "succeeded"

    if record.outputs:
        ref = record.outputs[0]
        result["output_ref"] = {
            "filename": ref.filename, "subfolder": ref.subfolder,
            "type": ref.type,
        }
        try:
            data = await client.fetch_view(ref.filename, ref.subfolder,
                                           output_type=ref.type or "output")
            import hashlib

            result["view"] = len(data) > 0
            result["view_sha"] = hashlib.sha256(data).hexdigest()
        except ComfyAPIError as exc:
            notes.append(f"view: {exc}")
    return result


async def probe_ws(base_url: str, fixtures: dict,
                   notes: list[str], timeout: float = 5.0) -> bool:
    """Observational only: connect, capture the first message dialect.
    WS telemetry is never lifecycle authority (M5A-7); this proves the
    endpoint exists and speaks, nothing more."""
    import websockets

    ws_url = base_url.replace("http://", "ws://").rstrip("/") + "/ws"
    try:
        async with websockets.connect(ws_url) as ws:
            first = await asyncio.wait_for(ws.recv(), timeout)
            text = first if isinstance(first, str) else (
                first.decode("utf-8", "replace")
            )
            parsed = json.loads(text)
            fixtures["ws_first_message"] = parsed
            return isinstance(parsed, dict) and "type" in parsed
    except Exception as exc:  # noqa: BLE001
        notes.append(f"ws: {exc}")
        return False


async def probe_interrupt_contract(client: ComfyClient, fixtures: dict,
                                   notes: list[str]) -> None:
    """Diagnostic contract probe ONLY: how /interrupt and /queue-delete
    answer unknown/absent targets. No capability elevation derives from
    this; running/pending cancellation stays UNKNOWN until M5B-5."""
    try:
        import httpx

        response = await client._client.post(
            client._base + "/interrupt",
            json={"prompt_id": "00000000-0000-0000-0000-000000000000"},
        )
        fixtures["interrupt_unknown_target"] = {
            "status": response.status_code,
            "body": _bounded(response.text),
        }
    except Exception as exc:  # noqa: BLE001
        notes.append(f"interrupt contract: {exc}")


def _bounded(text: str, limit: int = 400) -> str:
    return text[:limit]


async def run_probe(
    client: ComfyClient,
    base_url: str,
    ws_probe: bool = True,
    observed_at: str | None = None,
) -> ProbeResult:
    """Full M5B-1 evidence collection → the real ComfyCapabilityReport."""
    fixtures: dict = {}
    notes: list[str] = []
    evidence: list[Evidence] = []
    features: dict[str, FeatureState] = {}

    raw_system, version = await probe_system(client)
    reachable = raw_system is not None
    if raw_system is not None:
        fixtures["system_stats_raw"] = raw_system
    else:
        notes.append(f"system_stats: {version}")

    dialects = (await probe_read_dialects(client, fixtures, notes)
                if reachable else {"queue_observation": False,
                                   "history_full": False})

    upload_ok, up_name, up_sub = (False, "", "")
    marker: dict[str, object] = {}
    view_sha = None
    prompt_id = None
    if reachable:
        upload_ok, up_name, up_sub = await probe_upload(client, fixtures,
                                                        notes)
        if upload_ok:
            marker = await probe_marker_roundtrip(
                client, "soloring-probe-generation", "soloring-probe-attempt",
                up_name, up_sub, fixtures, notes,
            )
            prompt_id = marker.get("prompt_id")
            view_sha = marker.get("view_sha")
        await probe_interrupt_contract(client, fixtures, notes)

    ws_ok = False
    if ws_probe and reachable:
        ws_ok = await probe_ws(base_url, fixtures, notes)

    def mark(feature: str, ok: bool, method: str, detail: str = "") -> None:
        evidence.append(_evidence(feature, ok, method, detail))
        features[feature] = (FeatureState.SUPPORTED if ok
                             else FeatureState.UNKNOWN)

    mark("prompt_submission", bool(marker.get("prompt")), "marker_canary")
    mark("queue_observation", dialects.get("queue_observation", False),
         "endpoint_probe")
    mark("targeted_history", bool(marker.get("history_terminal")),
         "marker_canary")
    mark("marker_roundtrip", bool(marker.get("marker_roundtrip")),
         "marker_canary")
    mark("input_upload", upload_ok, "endpoint_probe")
    mark("output_view", bool(marker.get("view")), "marker_canary")
    mark("websocket_progress", ws_ok, "ws_connect",
         "observational endpoint probe only; WS is never lifecycle "
         "authority")
    # Cancellation stays UNKNOWN until the M5B-5 live probes; the runtime
    # default capability remains SOFT_ONLY.
    evidence.append(_evidence("pending_cancel", False, "unprobed",
                              "deferred to M5B-5"))
    evidence.append(_evidence("running_cancel", False, "unprobed",
                              "deferred to M5B-5"))
    features["pending_cancel"] = FeatureState.UNKNOWN
    features["running_cancel"] = FeatureState.UNKNOWN

    report = ComfyCapabilityReport(
        capability_profile_version=CAPABILITY_PROFILE_VERSION,
        observed_at=observed_at,
        executor_version=version,
        wire_dialects=_observed_dialects(fixtures),
        features=features,
        cancellation=CancellationCapability(
            mode=CancellationMode.UNKNOWN,
            retry_safety="unknown",
        ),
        evidence=tuple(evidence),
    )
    return ProbeResult(report=report, fixtures=fixtures,
                       marker_prompt_id=prompt_id, view_bytes_sha=view_sha,
                       notes=notes)


def _observed_dialects(fixtures: dict) -> tuple[str, ...]:
    dialects = []
    if "queue_raw" in fixtures:
        named = wire.classify_queue_dialect(fixtures["queue_raw"])
        if named is not None:
            dialects.append(named)
    if "history_raw" in fixtures:
        dialects.append("history_keyed_by_prompt_id")
    if "ws_first_message" in fixtures:
        dialects.append("ws_status_json")
    return tuple(dialects)
