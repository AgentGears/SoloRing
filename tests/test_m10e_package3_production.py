"""M10E-A — schema-3 package production integration (frozen R3 §8).

The ONE package authority (soloring.realization.packages) accepts descriptor
schema 3, captures all five artifacts coherently (D1/read/D2), delegates
M10 parsing to the frozen package3 authority, proves runtime closure by
exact captured fingerprint identity (production m10_spatial_runtime shape),
and validates every declared binding against the captured template graph.
Schema-1/2 gates are unchanged (E-014; full behavior via the M9A suite).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from soloring.domain.canonical import canonical_json_str
from soloring.realization.packages import (
    PackageIntegrity,
    capture_current_release,
    validate_package,
)
from soloring.spatial import production_package as prod
from soloring.spatial.package3 import Package3Invalid


def _write(path: Path, doc: dict) -> bytes:
    raw = canonical_json_str(doc).encode()
    path.write_bytes(raw)
    return raw


def _write_raw(path: Path, raw: bytes) -> None:
    path.write_bytes(raw)


async def _schema3_package(tmp_path: Path, *, mutate=None):
    """Install the frozen production schema-3 release into a temp package
    directory. Files carry CANONICAL bytes so sha256(file) equals the
    descriptor's canonical-hash pins. ``mutate`` replaces documents BEFORE
    writing; the descriptor is then re-pinned to the mutated members, so a
    mutated package remains CAPTURE-coherent and fails at SEMANTIC
    validation (the §21 posture) rather than at hash capture."""
    from soloring.domain.canonical import canonical_hash

    d = tmp_path / "pkg3"
    d.mkdir(parents=True, exist_ok=True)
    docs = {
        "manifest.json": prod.production_manifest_v3(),
        "workflow.json": prod.production_template(),
        "realization-profile.json": prod.production_profile_v2(),
        "execution-model-fingerprint.json":
            prod.production_fingerprint_document(),
    }
    descriptor = None
    if mutate is not None:
        docs = mutate(docs)
        descriptor = docs.pop("__descriptor__", None)
    if descriptor is None:
        descriptor = {
            "schema_version": 3,
            "workflow_id": docs["manifest.json"]["workflow_id"],
            "workflow_version": 1,
            "manifest_hash": canonical_hash(docs["manifest.json"]),
            "workflow_template_hash": canonical_hash(docs["workflow.json"]),
            "realization_profile_hash": canonical_hash(
                docs["realization-profile.json"]),
            "execution_model_fingerprint_hash": canonical_hash(
                docs["execution-model-fingerprint.json"]),
        }
    for name, doc in docs.items():
        _write(d / name, doc)
    _write(d / "workflow-package.json", descriptor)
    return d


def _settings_for(settings, package_dir: Path):
    settings.workflow_package_dir = package_dir
    return settings


async def test_capture_schema3_release_five_artifacts(
        settings, tmp_path):
    d = await _schema3_package(tmp_path)
    release = await capture_current_release(_settings_for(settings, d))
    assert release.schema_version == 3
    assert release.workflow_id == "wan21_spatial_v1"
    # every captured buffer hashes to its descriptor-declared identity
    assert hashlib.sha256(release.manifest_bytes).hexdigest() == \
        release.manifest_hash
    assert hashlib.sha256(release.template_bytes).hexdigest() == \
        release.workflow_template_hash
    assert hashlib.sha256(release.profile_bytes).hexdigest() == \
        release.realization_profile_hash
    assert hashlib.sha256(release.fingerprint_bytes).hexdigest() == \
        release.execution_model_fingerprint_hash
    ident = release.release_identity()
    assert ident["schema_version"] == 3
    assert ident["realization_profile_hash"] == \
        release.realization_profile_hash


async def test_validate_schema3_production_package(settings, tmp_path):
    """The frozen production documents pass the ONE production authority:
    delegated M10 parsing + runtime closure proven by the WRAPPED
    m10_spatial_runtime fingerprint identity (baseline defect fixed in
    M10E: _closed_by_fingerprint previously missed the wrapper)."""
    d = await _schema3_package(tmp_path)
    release = await capture_current_release(_settings_for(settings, d))
    package = validate_package(release)
    assert package.is_schema3
    assert package.manifest_v3["schema_version"] == "3"
    assert package.profile_v2["spatial"]["max_control_streams"] == 3
    # E-012: closure proven, not asserted
    from soloring.spatial.package3 import check_runtime_closure

    assert check_runtime_closure(
        package.profile_v2["spatial"], fingerprint=package.fingerprint_v3,
        template=package.template_graph) == []


async def test_descriptor_hash_disagreement_fails(settings, tmp_path):
    """Post-install member tamper: the descriptor still pins the original
    manifest identity, so D1/declared-hash capture is incoherent."""
    d = await _schema3_package(tmp_path)
    manifest = json.loads(canonical_json_str(
        prod.production_manifest_v3()))
    manifest["version"] = 2
    _write_raw(d / "manifest.json",
               canonical_json_str(manifest).encode())
    with pytest.raises(PackageIntegrity) as ei:
        await capture_current_release(_settings_for(settings, d))
    assert "manifest" in ei.value.message


async def test_descriptor_malformed_fails(settings, tmp_path):
    d = await _schema3_package(tmp_path)
    (d / "workflow-package.json").write_bytes(b"{not json")
    with pytest.raises(PackageIntegrity):
        await capture_current_release(_settings_for(settings, d))


async def test_descriptor_schema4_rejected(settings, tmp_path):
    """The descriptor gate stays closed beyond 1/2/3 (E-014 posture):
    schema 4 trips either the closed field set or the version range."""
    d = await _schema3_package(
        tmp_path, mutate=lambda docs: docs | {
            "__descriptor__": prod.production_descriptor_v3()
            | {"schema_version": 4}})
    with pytest.raises(PackageIntegrity, match="unknown fields|1, 2 or 3"):
        await capture_current_release(_settings_for(settings, d))


async def test_manifest_v3_malformed_is_binding_invalid(
        settings, tmp_path):
    def _mutate(docs):
        docs["manifest.json"] = {
            "schema_version": "3", "version": 1,
            "workflow_id": "wan21_spatial_v1",
            "inputs": {}, "parameters": {}, "outputs": {},
            "spatial_bindings": {}}
        return docs

    d = await _schema3_package(tmp_path, mutate=_mutate)
    release = await capture_current_release(_settings_for(settings, d))
    with pytest.raises(Package3Invalid):
        validate_package(release)


async def test_profile_capacity_mutated_fails(settings, tmp_path):
    def _mutate(docs):
        profile = json.loads(canonical_json_str(
            docs["realization-profile.json"]))
        profile["spatial"]["max_control_streams"] = 4
        docs["realization-profile.json"] = profile
        return docs

    d = await _schema3_package(tmp_path, mutate=_mutate)
    # descriptor still pins the ORIGINAL profile hash
    release = await capture_current_release(_settings_for(settings, d))
    with pytest.raises(Package3Invalid):
        validate_package(release)


async def test_runtime_requirement_unclosed_fails(settings, tmp_path):
    """E-013: dropping the comfyui commit from the fingerprint leaves the
    requirement unproven → semantic validation fails before queueing."""
    def _mutate(docs):
        fp = json.loads(canonical_json_str(
            docs["execution-model-fingerprint.json"]))
        del fp["m10_spatial_runtime"]["comfyui_commit"]
        docs["execution-model-fingerprint.json"] = fp
        return docs

    d = await _schema3_package(tmp_path, mutate=_mutate)
    release = await capture_current_release(_settings_for(settings, d))
    with pytest.raises(Package3Invalid, match="comfyui"):
        validate_package(release)


async def test_binding_node_missing_from_template_fails(
        settings, tmp_path):
    def _mutate(docs):
        manifest = json.loads(canonical_json_str(docs["manifest.json"]))
        manifest["spatial_bindings"]["world_depth"]["node"] = "999"
        docs["manifest.json"] = manifest
        return docs

    d = await _schema3_package(tmp_path, mutate=_mutate)
    release = await capture_current_release(_settings_for(settings, d))
    with pytest.raises(Package3Invalid, match="999"):
        validate_package(release)


async def test_binding_field_missing_from_template_node_fails(
        settings, tmp_path):
    def _mutate(docs):
        manifest = json.loads(canonical_json_str(docs["manifest.json"]))
        manifest["spatial_bindings"]["entity_depth_1"]["field"] = (
            "not_a_field")
        docs["manifest.json"] = manifest
        return docs

    d = await _schema3_package(tmp_path, mutate=_mutate)
    release = await capture_current_release(_settings_for(settings, d))
    with pytest.raises(Package3Invalid, match="not_a_field"):
        validate_package(release)


async def test_descriptor_changed_during_capture_fails(
        settings, tmp_path, monkeypatch):
    """§22.1 D1/read/D2: a descriptor swap mid-capture is incoherent."""
    d = await _schema3_package(tmp_path)
    import soloring.realization.packages as pkgs

    real_read = pkgs._read_descriptor
    calls = {"n": 0}

    def _flipping(path: Path) -> dict:
        doc = real_read(path)
        calls["n"] += 1
        if calls["n"] == 2:
            doc = dict(doc)
            doc["workflow_version"] = doc["workflow_version"] + 1
        return doc

    monkeypatch.setattr(pkgs, "_read_descriptor", _flipping)
    with pytest.raises(PackageIntegrity, match="changed during capture"):
        await capture_current_release(_settings_for(settings, d))


async def test_workflow_identity_disagreement_fails(settings, tmp_path):
    def _mutate(docs):
        profile = json.loads(canonical_json_str(
            docs["realization-profile.json"]))
        profile["workflow_id"] = "other_wf"
        docs["realization-profile.json"] = profile
        return docs

    d = await _schema3_package(tmp_path, mutate=_mutate)
    release = await capture_current_release(_settings_for(settings, d))
    from soloring.errors import ErrorCode, SoloRingError

    with pytest.raises(SoloRingError) as ei:
        validate_package(release)
    assert ei.value.code == ErrorCode.REALIZATION_INPUT_BINDING_INVALID
