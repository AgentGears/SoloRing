"""M5B-1 probe harness — double-tested before live use.

The probe itself is proven against a MockTransport Comfy speaking the
dialects wire.py already normalizes: the six mandatory capabilities derive
SUPPORTED from recorded evidence, the report evaluates READY, sanitized
fixtures are captured, and failure dialects degrade to UNKNOWN (never
SUPPORTED-by-assumption).
"""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from soloring.executors.comfy.capabilities import (
    FeatureState,
    ReadinessStatus,
    evaluate_readiness,
)
from soloring.executors.comfy.client import ComfyClient
from soloring.executors.comfy.probe import PROBE_PNG, run_probe
from soloring.executors.comfy.wire import classify_queue_dialect


class ProbeDouble:
    """Upstream-dialect Comfy for the probe: upload→LoadImage→SaveImage
    canary lifecycle with marker-preserving history and /view."""

    base_url = "http://comfy.test"

    def __init__(self):
        self.posts = 0
        self.pid = "probe-prompt-1"
        self.saved = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/system_stats":
            return httpx.Response(200, json={
                "system": {"comfyui_version": "0.3.99", "build": "probe"},
                "devices": [],
            })
        if path == "/upload/image":
            return httpx.Response(200, json={
                "name": "soloring_probe.png", "subfolder": "soloring_probe",
                "type": "input",
            })
        if path == "/prompt":
            self.posts += 1
            body = json.loads(request.content.decode())
            marker = body.get("extra_data", {}).get("soloring", {})
            self.saved["marker"] = marker
            return httpx.Response(200, json={"prompt_id": self.pid})
        if path == "/queue":
            return httpx.Response(200, json={
                "queue_running": [], "queue_pending": [],
            })
        if path.startswith("/history"):
            if path.endswith(self.pid) or path == "/history":
                return httpx.Response(200, json={self.pid: {
                    "prompt": [0, self.pid, {},
                               {"soloring": self.saved.get("marker", {})},
                               []],
                    "outputs": {"2": {"images": [
                        {"filename": "soloring_probe_00001_.png",
                         "subfolder": "", "type": "output"},
                    ]}},
                    "status": {"status_str": "completed", "messages": []},
                }})
            return httpx.Response(200, json={})
        if path == "/view":
            return httpx.Response(200, content=b"RIFF-probe-output-bytes")
        if path == "/interrupt":
            return httpx.Response(200, json={"accepted": False})
        return httpx.Response(404)


def _client(double) -> ComfyClient:
    return ComfyClient(double.base_url, "probe-test", timeout=10.0,
                       transport=httpx.MockTransport(double.handler))


async def test_probe_full_evidence_ready():
    double = ProbeDouble()
    client = _client(double)
    try:
        result = await run_probe(client, double.base_url, ws_probe=False,
                                 observed_at="2026-08-16T00:00:00Z")
    finally:
        await client.aclose()

    report = result.report
    assert report.executor_version == "0.3.99"
    assert result.marker_prompt_id == double.pid
    assert result.view_bytes_sha is not None

    mandatory = ("prompt_submission", "queue_observation",
                 "targeted_history", "marker_roundtrip", "input_upload",
                 "output_view")
    for feature in mandatory:
        assert report.feature(feature) is FeatureState.SUPPORTED, feature
    assert report.feature("websocket_progress") is FeatureState.UNKNOWN
    assert report.cancellation.mode.value == "unknown"  # M5B-5 defers this

    assert evaluate_readiness(report, reachable=True) is (
        ReadinessStatus.READY
    )
    # Exactly one canary POST; sanitized fixtures captured.
    assert double.posts == 1
    for name in ("system_stats_raw", "queue_raw", "history_raw",
                 "upload_response", "marker_history_record",
                 "interrupt_unknown_target"):
        assert name in result.fixtures, name
    # The marker canary really carried our identity through history.
    marker = result.fixtures["marker_history_record"]["marker"]
    assert marker == ("soloring-probe-generation", "soloring-probe-attempt")


async def test_probe_degrades_to_unknown_not_supported():
    class BrokenDouble(ProbeDouble):
        def handler(self, request):
            path = request.url.path
            if path == "/queue":
                return httpx.Response(200, json={"unexpected": 1})
            if path == "/upload/image":
                return httpx.Response(500)
            return super().handler(request)

    double = BrokenDouble()
    client = _client(double)
    try:
        result = await run_probe(client, double.base_url, ws_probe=False)
    finally:
        await client.aclose()

    report = result.report
    assert report.feature("queue_observation") is FeatureState.UNKNOWN
    assert report.feature("input_upload") is FeatureState.UNKNOWN
    assert report.feature("prompt_submission") is FeatureState.UNKNOWN
    readiness = evaluate_readiness(report, reachable=True)
    assert readiness is ReadinessStatus.UNAVAILABLE  # unknown, not incompatible
    assert any("upload" in n or "queue" in n for n in result.notes)


async def test_probe_unreachable():
    async def unreachable(request):
        raise httpx.ConnectError("down")

    client = ComfyClient("http://comfy.test", "probe-test", timeout=2.0,
                         transport=httpx.MockTransport(unreachable))
    result = await run_probe(client, "http://comfy.test", ws_probe=False)
    await client.aclose()
    assert evaluate_readiness(
        result.report, reachable=False,
    ) is ReadinessStatus.UNAVAILABLE
    assert result.fixtures == {}


def test_queue_dialect_classifier():
    assert classify_queue_dialect(
        {"queue_running": [], "queue_pending": []},
    ) == "queue_keyed_lists"
    assert classify_queue_dialect({"running": [], "pending": []}) == (
        "queue_flat_lists"
    )
    assert classify_queue_dialect({"weird": 1}) is None
    assert classify_queue_dialect("not-a-dict") is None


def test_probe_png_is_a_valid_tiny_png():
    assert PROBE_PNG[:8] == b"\x89PNG\r\n\x1a\n"
    assert PROBE_PNG.endswith(b"IEND\xaeB`\x82")
    assert len(PROBE_PNG) < 128
