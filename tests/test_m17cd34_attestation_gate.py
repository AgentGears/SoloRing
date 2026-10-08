"""M17C-D FPR34-02 — the EFFECTIVE schema-5 worker-boundary
attestation gate, adversarially (non-live): a valid retained
performance package driven through the REAL ``_drive`` preparation
must REFUSE BEFORE SUBMISSION — before any performance input is
uploaded, before any prompt is POSTed — when the deployment
attestation is GGUF-only (the predecessor lane without the
performance node), missing entirely, carrying the wrong pinned
implementation hash, or bound to the wrong serving process. No
unverified fallback: every refusal lands on the generation row as
EXECUTION_MODEL_INCOMPATIBLE."""

from __future__ import annotations

import json

import pytest

from tests.test_m17cd33_retained3 import (
    _drive_to_payload, _schema3_v5_generation,
)


def _base_attestation(pkg_fingerprint_path) -> dict:
    """The LAWFUL composed performance-lane attestation for THIS
    package's captured runtime requirement (the same document the
    positive retained-3 drives use)."""
    from soloring.performance.executor_runtime import (
        performance_nodes_content_hash,
    )

    fp = json.loads(
        pkg_fingerprint_path.read_text(encoding="utf-8"))
    rr = fp.get("m10_spatial_runtime") or fp["runtime_requirements"]
    composed = sorted(
        set(rr.get("custom_nodes") or ())
        | {"soloring_performance_nodes"})
    return {
        "schema_version": 4,
        "attestation": {
            "comfyui_commit": rr["comfyui_commit"],
            "gguf_commit": next(iter(rr["custom_nodes"].values())),
            "executor_origin": "http://127.0.0.1:8188",
            "custom_node_policy": {"disable_all": True,
                                   "whitelist": composed},
            "performance_nodes_hash":
                performance_nodes_content_hash(),
            "pid": 4242,
            "process_start_fingerprint": "fixture",
            "launched_at": "2026-01-01T00:00:00Z",
        },
    }


def _package_node(pkg_fingerprint_path) -> str:
    fp = json.loads(
        pkg_fingerprint_path.read_text(encoding="utf-8"))
    rr = fp.get("m10_spatial_runtime") or fp["runtime_requirements"]
    return next(iter(rr["custom_nodes"]))


async def _refused_before_submission(client, factory, tmp_path,
                                     monkeypatch, *, v2: bool,
                                     attestation_doc=None,
                                     write_attestation=True,
                                     message_substring: str):
    world, generation_id, spec, pkg = await _schema3_v5_generation(
        client, factory, tmp_path, v2=v2)
    fingerprint = pkg / "execution-model-fingerprint.json"
    stub, outcome, error_row = await _drive_to_payload(
        client, generation_id, fingerprint, monkeypatch,
        attestation_doc=attestation_doc,
        write_attestation=write_attestation)
    # the refusal is BEFORE SUBMISSION — no prompt document was ever
    # handed to the executor client...
    assert stub.payload is None
    # ...and BEFORE any performance input was uploaded (the gate
    # precedes the performance-input materialization)
    assert stub.uploads == [], stub.uploads
    # the refusal is the typed terminal state on the generation row
    assert error_row is not None
    assert error_row["error_code"] == "EXECUTION_MODEL_INCOMPATIBLE", \
        dict(error_row)
    assert message_substring in error_row["error_message"], \
        dict(error_row)
    return error_row


@pytest.mark.asyncio
async def test_gate_refuses_gguf_only_attestation_v1(
        client, factory, tmp_path, monkeypatch):
    """A perfectly valid PREDECESSOR-lane deployment (exactly the
    package's own captured node whitelisted, the lanes' disjoint
    shape with no performance field) is NOT a performance
    deployment: the schema-5 gate refuses it."""
    world, generation_id, spec, pkg = await _schema3_v5_generation(
        client, factory, tmp_path, v2=False)
    fingerprint = pkg / "execution-model-fingerprint.json"
    doc = _base_attestation(fingerprint)
    # reduce to the predecessor lane: ONLY the package's own
    # captured node, and NO performance_nodes_hash (a predecessor
    # attestation carrying it is invalid — disjoint lanes)
    doc["attestation"]["custom_node_policy"]["whitelist"] = [
        _package_node(fingerprint)]
    doc["attestation"].pop("performance_nodes_hash")
    stub, outcome, error_row = await _drive_to_payload(
        client, generation_id, fingerprint, monkeypatch,
        attestation_doc=doc)
    assert stub.payload is None
    assert stub.uploads == [], stub.uploads
    assert error_row["error_code"] == "EXECUTION_MODEL_INCOMPATIBLE"
    assert "lacks the required performance deployment nodes" \
        in error_row["error_message"], dict(error_row)


@pytest.mark.asyncio
async def test_gate_refuses_missing_attestation_v1(
        client, factory, tmp_path, monkeypatch):
    """No attestation file at all: no unverified fallback — the
    drive refuses rather than submitting unauthenticated."""
    await _refused_before_submission(
        client, factory, tmp_path, monkeypatch, v2=False,
        write_attestation=False,
        message_substring=(
            "No valid live deployment attestation is available"))


@pytest.mark.asyncio
async def test_gate_refuses_wrong_performance_hash_v1(
        client, factory, tmp_path, monkeypatch):
    """The composed lane with a WRONG pinned implementation hash:
    the exact content-hash law refuses at the gate."""
    world, generation_id, spec, pkg = await _schema3_v5_generation(
        client, factory, tmp_path, v2=False)
    doc = _base_attestation(
        pkg / "execution-model-fingerprint.json")
    doc["attestation"]["performance_nodes_hash"] = "0" * 64
    stub, outcome, error_row = await _drive_to_payload(
        client, generation_id,
        pkg / "execution-model-fingerprint.json", monkeypatch,
        attestation_doc=doc)
    assert stub.payload is None
    assert stub.uploads == [], stub.uploads
    assert error_row["error_code"] == "EXECUTION_MODEL_INCOMPATIBLE"
    assert "the pinned in-tree implementation" \
        in error_row["error_message"], dict(error_row)


@pytest.mark.asyncio
async def test_gate_refuses_wrong_process_attestation_v1(
        client, factory, tmp_path, monkeypatch):
    """A perfectly composed, correctly hashed attestation for a
    DIFFERENT serving process (another origin) refuses at the gate —
    the performance requirements bind to THE serving process, and
    the origin-equality law runs for real here (only the live-pid
    read is the battery's bypass)."""
    world, generation_id, spec, pkg = await _schema3_v5_generation(
        client, factory, tmp_path, v2=False)
    doc = _base_attestation(
        pkg / "execution-model-fingerprint.json")
    doc["attestation"]["executor_origin"] = "http://127.0.0.1:8288"
    stub, outcome, error_row = await _drive_to_payload(
        client, generation_id,
        pkg / "execution-model-fingerprint.json", monkeypatch,
        attestation_doc=doc)
    assert stub.payload is None
    assert stub.uploads == [], stub.uploads
    assert error_row["error_code"] == "EXECUTION_MODEL_INCOMPATIBLE"
    assert "is not the configured executor origin" \
        in error_row["error_message"], dict(error_row)


@pytest.mark.asyncio
async def test_gate_refuses_gguf_only_attestation_v2(
        client, factory, tmp_path, monkeypatch):
    """The same refusal on the OTHER lower form (v5-over-v2): the
    gate is common to both, and the v2 lane cannot bypass it."""
    world, generation_id, spec, pkg = await _schema3_v5_generation(
        client, factory, tmp_path, v2=True)
    assert "model" in spec and "realization" in spec  # v2 lower
    doc = _base_attestation(
        pkg / "execution-model-fingerprint.json")
    att = doc["attestation"]
    att["custom_node_policy"]["whitelist"] = [
        _package_node(pkg / "execution-model-fingerprint.json")]
    att.pop("performance_nodes_hash")
    stub, outcome, error_row = await _drive_to_payload(
        client, generation_id,
        pkg / "execution-model-fingerprint.json", monkeypatch,
        attestation_doc=doc)
    assert stub.payload is None
    assert stub.uploads == [], stub.uploads
    assert error_row["error_code"] == "EXECUTION_MODEL_INCOMPATIBLE"
    assert "lacks the required performance deployment nodes" \
        in error_row["error_message"], dict(error_row)


@pytest.mark.asyncio
async def test_gate_refuses_wrong_hash_v2(
        client, factory, tmp_path, monkeypatch):
    """The wrong-hash refusal on the v2 lower form too."""
    world, generation_id, spec, pkg = await _schema3_v5_generation(
        client, factory, tmp_path, v2=True)
    doc = _base_attestation(
        pkg / "execution-model-fingerprint.json")
    doc["attestation"]["performance_nodes_hash"] = "f" * 64
    stub, outcome, error_row = await _drive_to_payload(
        client, generation_id,
        pkg / "execution-model-fingerprint.json", monkeypatch,
        attestation_doc=doc)
    assert stub.payload is None
    assert stub.uploads == [], stub.uploads
    assert error_row["error_code"] == "EXECUTION_MODEL_INCOMPATIBLE"
    assert "the pinned in-tree implementation" \
        in error_row["error_message"], dict(error_row)
