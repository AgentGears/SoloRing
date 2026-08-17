"""M5B-7 hold fix — exact-fingerprint capability binding regressions.

The audit reproduction: a characterization record from commit A plus a
RUNNING executor that still reports the same version but is a different
commit B must FAIL CLOSED to SOFT_ONLY. Version equality alone is not a
fingerprint; the local launcher attestation carries the revision the
deployment actually runs.
"""

from __future__ import annotations

import json

import httpx
import pytest

from soloring.executors.comfy.capability_record import (
    CapabilityRecordInvalid,
    build_capability_record,
    build_deployment_attestation,
    load_capability_record,
    load_deployment_attestation,
)
from soloring.settings import Settings
from soloring.worker.comfy_pipeline import resolve_capability

COMFY_COMMIT = "b" * 40
GGUF_COMMIT = "d" * 40


def _stage(tmp_path, *, record=None, attestation=None):
    fp = tmp_path / "comfy-fingerprint"
    fp.mkdir(parents=True, exist_ok=True)
    if record is not None:
        (fp / "capability_m5b5.json").write_text(json.dumps(record, indent=2))
    if attestation is not None:
        (fp / "deployment_attestation.json").write_text(
            json.dumps(attestation, indent=2))
    return fp


def _record(commit=COMFY_COMMIT, gguf=GGUF_COMMIT):
    return build_capability_record(
        comfyui_commit=commit, comfyui_version="0.33.0", gguf_commit=gguf)


def _attestation(commit=COMFY_COMMIT, gguf=GGUF_COMMIT):
    return build_deployment_attestation(
        comfyui_commit=commit, gguf_commit=gguf, launched_at="2026-08-17T00:00:00",
        pid=4242, process_start_fingerprint="2026-08-17T00:00:00",
        executor_origin="http://127.0.0.1:8188")


def _settings(tmp_path):
    return Settings(data_dir=tmp_path, comfy_cancellation_mode="targeted")


def _client(version="0.33.0"):
    def handler(request):
        return httpx.Response(200, json={
            "system": {"comfyui_version": version, "build": "t"}})

    return httpx.Client(transport=httpx.MockTransport(handler))  # noqa


def _comfy_client(version="0.33.0", base="http://127.0.0.1:8188"):
    from soloring.executors.comfy.client import ComfyClient

    return ComfyClient(base, "w",
                       transport=httpx.MockTransport(
                           lambda r: httpx.Response(200, json={
                               "system": {"comfyui_version": version,
                                          "build": "t"}})))


async def test_exact_fingerprint_engages_targeted(tmp_path, monkeypatch):
    import soloring.worker.comfy_pipeline as pipeline_mod

    monkeypatch.setattr(
        "soloring.executors.comfy.capability_record.verify_live_process",
        lambda att, port=8188: True)
    _stage(tmp_path, record=_record(), attestation=_attestation())
    cap = await resolve_capability(_settings(tmp_path), _comfy_client())
    assert cap.mode.value == "targeted"
    assert cap.retry_safety == "safe"
    assert cap.targeting_key == "prompt_id"


async def test_client_none_fails_closed(tmp_path):
    """No unsafe bypass: targeted resolution REQUIRES the live probe."""
    _stage(tmp_path, record=_record(), attestation=_attestation())
    cap = await resolve_capability(_settings(tmp_path), None)
    assert cap.mode.value == "soft_only"


async def test_stale_attestation_wrong_pid_fails_closed(tmp_path, monkeypatch):
    """THE stale-attestation case: record==attestation commits, version
    matches, but the process serving the port is NOT the attested one
    (manual same-version replacement)."""
    import soloring.executors.comfy.capability_record as cr

    monkeypatch.setattr(cr, "verify_live_process",
                        lambda att, port=8188: False)
    _stage(tmp_path, record=_record(), attestation=_attestation())
    cap = await resolve_capability(_settings(tmp_path), _comfy_client())
    assert cap.mode.value == "soft_only"


async def test_same_version_different_commit_fails_closed(tmp_path):
    """THE audit reproduction: version matches, revision does not."""
    _stage(tmp_path,
           record=_record(commit="a" * 40),          # characterized A
           attestation=_attestation(commit=COMFY_COMMIT))  # running B
    cap = await resolve_capability(_settings(tmp_path), _comfy_client())
    assert cap.mode.value == "soft_only"


async def test_gguf_node_drift_fails_closed(tmp_path):
    _stage(tmp_path,
           record=_record(gguf="e" * 40),
           attestation=_attestation(gguf="f" * 40))
    cap = await resolve_capability(_settings(tmp_path), _comfy_client())
    assert cap.mode.value == "soft_only"


async def test_missing_attestation_fails_closed(tmp_path):
    _stage(tmp_path, record=_record())  # no attestation at all
    cap = await resolve_capability(_settings(tmp_path), _comfy_client())
    assert cap.mode.value == "soft_only"


async def test_missing_record_fails_closed(tmp_path):
    _stage(tmp_path, attestation=_attestation())
    cap = await resolve_capability(_settings(tmp_path), _comfy_client())
    assert cap.mode.value == "soft_only"


async def test_live_version_drift_fails_closed(tmp_path):
    _stage(tmp_path, record=_record(), attestation=_attestation())
    cap = await resolve_capability(_settings(tmp_path),
                                   _comfy_client(version="9.9.9"))
    assert cap.mode.value == "soft_only"


async def test_unreachable_probe_fails_closed(tmp_path):
    _stage(tmp_path, record=_record(), attestation=_attestation())
    cap = await resolve_capability(_settings(tmp_path),
                                   _unreachable_client())
    assert cap.mode.value == "soft_only"


def _unreachable_client():
    from soloring.executors.comfy.client import ComfyClient

    async def boom(request):
        raise httpx.ConnectError("down")

    return ComfyClient("http://x", "w", transport=httpx.MockTransport(boom))


def test_record_contract_strictness():
    # The m5b5-emitted shape round-trips; tampered shapes reject.
    doc = _record()
    assert doc["running_cancel"]["mode"] == "TARGETED"
    assert doc["running_cancel"]["retry_safety"] == "safe"
    for tamper in (
        lambda d: d.update(schema_version=2),
        lambda d: d["executor_fingerprint"].update(comfyui_commit="short"),
        lambda d: d["running_cancel"].update(retry_safety="PROVEN live: …"),
        lambda d: d["running_cancel"].update(mode="SOFT_ONLY"),
        lambda d: d.pop("running_cancel"),
        # Exact-value contract (final verification): characterizing an
        # UNPROVEN contract must invalidate the record.
        lambda d: d["running_cancel"].update(endpoint="POST /interrupt"),
        lambda d: d["running_cancel"].update(targeting_key="whatever"),
        lambda d: d["running_cancel"].update(uniqueness_guarantee="unproven"),
    ):
        import copy
        import tempfile
        from pathlib import Path

        bad = copy.deepcopy(doc)
        tamper(bad)
        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "comfy-fingerprint"
            fp.mkdir()
            (fp / "capability_m5b5.json").write_text(json.dumps(bad))
            with pytest.raises(CapabilityRecordInvalid):
                load_capability_record(Path(td))


def test_attestation_contract_strictness():
    doc = _attestation()
    assert doc["schema_version"] == 4
    assert doc["attestation"]["pid"] == 4242
    assert doc["attestation"]["process_start_fingerprint"]
    assert doc["attestation"]["executor_origin"] == "http://127.0.0.1:8188"
    assert doc["attestation"]["custom_node_policy"] == {
        "disable_all": True, "whitelist": ["ComfyUI-GGUF"]}
    import copy
    import tempfile
    from pathlib import Path

    bad = copy.deepcopy(doc)
    bad["attestation"]["comfyui_commit"] = "nothex"
    with tempfile.TemporaryDirectory() as td:
        fp = Path(td) / "comfy-fingerprint"
        fp.mkdir()
        (fp / "deployment_attestation.json").write_text(json.dumps(bad))
        with pytest.raises(CapabilityRecordInvalid):
            load_deployment_attestation(Path(td))


# --- final-verification patch 3: executor-instance binding -------------------


async def test_remote_same_version_client_fails_closed(tmp_path, monkeypatch):
    """THE split-brain reproduction: local attestation A valid and its
    process running, but the CLIENT points at a remote same-version B."""
    monkeypatch.setattr(
        "soloring.executors.comfy.capability_record.verify_live_process",
        lambda att, port=8188: True)  # local check would succeed...
    _stage(tmp_path, record=_record(), attestation=_attestation())
    cap = await resolve_capability(
        _settings(tmp_path), _comfy_client(base="http://10.55.66.77:8188"))
    assert cap.mode.value == "soft_only"  # ...but origin policy refuses


async def test_localhost_alias_origin_mismatch_fails_closed(tmp_path, monkeypatch):
    """Even a loopback alias differs from the attested origin string."""
    monkeypatch.setattr(
        "soloring.executors.comfy.capability_record.verify_live_process",
        lambda att, port=8188: True)
    _stage(tmp_path, record=_record(), attestation=_attestation())
    cap = await resolve_capability(
        _settings(tmp_path), _comfy_client(base="http://localhost:8188"))
    assert cap.mode.value == "soft_only"


def test_attestation_rejects_non_loopback_origin(tmp_path):
    import copy

    doc = _attestation()
    bad = copy.deepcopy(doc)
    bad["attestation"]["executor_origin"] = "http://10.55.66.77:8188"
    fp = tmp_path / "comfy-fingerprint"
    fp.mkdir(parents=True)
    (fp / "deployment_attestation.json").write_text(json.dumps(bad))
    from pathlib import Path

    from soloring.executors.comfy.capability_record import (
        CapabilityRecordInvalid,
        load_deployment_attestation,
    )

    with pytest.raises(CapabilityRecordInvalid):
        load_deployment_attestation(tmp_path)


# --- final verification patch 4: executable extension set ----------------------


async def test_v3_attestation_without_policy_rejected(tmp_path, monkeypatch):
    """An old v3 attestation (no custom_node_policy) is INVALID: it was
    produced without the whitelist guarantee and must resolve SOFT_ONLY."""
    monkeypatch.setattr(
        "soloring.executors.comfy.capability_record.verify_live_process",
        lambda att, port=8188: True)
    import copy

    v3 = _attestation()
    del v3["attestation"]["custom_node_policy"]
    v3["schema_version"] = 3
    _stage(tmp_path, record=_record(), attestation=v3)
    cap = await resolve_capability(_settings(tmp_path), _comfy_client())
    assert cap.mode.value == "soft_only"


def test_attestation_wrong_policy_rejected(tmp_path):
    import copy

    from soloring.executors.comfy.capability_record import (
        CapabilityRecordInvalid,
        load_deployment_attestation,
    )

    for tamper in (
        lambda a: a["attestation"].update(custom_node_policy={
            "disable_all": False, "whitelist": ["ComfyUI-GGUF"]}),
        lambda a: a["attestation"].update(custom_node_policy={
            "disable_all": True, "whitelist": ["ComfyUI-GGUF",
                                               "SomeOtherNode"]}),
        lambda a: a["attestation"].update(custom_node_policy={
            "disable_all": True, "whitelist": []}),
        lambda a: a["attestation"].pop("custom_node_policy"),
        # Structurally exact: an extra key is NOT the characterized policy.
        lambda a: a["attestation"]["custom_node_policy"].update(
            unexpected="accepted?"),
    ):
        bad = copy.deepcopy(_attestation())
        tamper(bad)
        fp = tmp_path / "comfy-fingerprint"
        fp.mkdir(parents=True, exist_ok=True)
        (fp / "deployment_attestation.json").write_text(json.dumps(bad))
        with pytest.raises(CapabilityRecordInvalid):
            load_deployment_attestation(tmp_path)


def test_canonical_launcher_pins_whitelist():
    """The launcher's server arguments MUST mechanically enforce the
    attested extension set: all custom nodes disabled, exactly
    ComfyUI-GGUF whitelisted."""
    src = open("scripts/launch_comfy.py", encoding="utf-8").read()
    assert "--disable-all-custom-nodes" in src.replace("',", " ").replace(
        "''", " ")
    assert "'--disable-all-custom-nodes'" in src
    assert "'--whitelist-custom-nodes','ComfyUI-GGUF'" in src
    # and nothing else is whitelisted
    import re

    wl = re.findall(r"'--whitelist-custom-nodes','([^']+)'", src)
    assert wl == ["ComfyUI-GGUF"], wl
