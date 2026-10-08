"""FPR33-01(d) — the REAL comfy capture-path create proof: the
schema-8 world creates a NATIVE comfy schema-5 Generation through
the genuine capture_current_release + validate_package chain (no
WORKFLOW_DIR monkeypatch, no post-creation executor mutation)."""

from __future__ import annotations

import json

import pytest

from tests.test_m17cd_create_path import (
    _facial_world, _row, _capture_closed,
)


@pytest.mark.asyncio
async def test_real_comfy_capture_path_creates_native_v5(
        client, factory, tmp_path):
    settings = client._transport.app.state.settings
    from pathlib import Path

    settings.executor = "comfy"
    settings.workflow_package_dir = Path(
        "workflows/performance_liveportrait_v1")
    try:
        world = await _facial_world(client, factory)
        r = await client.post(f"/shots/{world['shot']}/generations")
        assert r.status_code == 202, r.text
        generation = r.json()
        assert generation["executor"] == "comfy"
        assert generation["manifest_hash"] == (
            "24df9c9777406ce6cc30cab19dd85592d44036814abb56c66e"
            "52d99bbe745147")
        spec = json.loads((await _row(client, (
            "SELECT workflow_spec_json FROM generations "
            "WHERE id = :g"),
            {"g": generation["id"]}))["workflow_spec_json"])
        assert spec["schema_version"] == 5
    finally:
        settings.executor = "fake"
        settings.workflow_package_dir = None
