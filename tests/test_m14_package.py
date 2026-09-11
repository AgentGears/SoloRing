"""M14B-4 — wan21_spatial_v1 v2 production release (frozen R2 §§15/17/
18; proof cells PKG:01-08).

A NEW immutable release (descriptor schema 4 / profile schema 3 /
workflow version 2), not a reinterpretation of v1. Manifest semantics
inherited (schema 3 format, workflow version advanced per the package
cross-identity law); template + fingerprint byte-identical to the
certified v1 members.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from sqlalchemy import text

from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.errors import SoloRingError
from soloring.observation.capability import (
    capability_contract_hash,
    negotiate,
    validate_observation_block,
)
from soloring.observation.materializer import (
    build_materializer_contract,
    materializer_contract_hash,
)
from soloring.realization.packages import capture_release, validate_package
from soloring.spatial.production_package import (
    production_descriptor_v3,
    production_descriptor_v4,
    production_fingerprint_document,
    production_manifest_v3,
    production_manifest_v3_v2,
    production_observation_block,
    production_profile_v2,
    production_profile_v3,
    production_template,
)

NOW = "2026-09-11T00:00:00Z"


def _write_package(directory: Path, *, descriptor, manifest, template,
                   profile, fingerprint) -> Path:
    directory.mkdir(parents=True, exist_ok=True)

    def write(name, doc):
        (directory / name).write_bytes(
            canonical_json_str(doc).encode("utf-8"))

    write("workflow-package.json", descriptor)
    write("manifest.json", manifest)
    write("workflow.json", template)
    write("realization-profile.json", profile)
    write("execution-model-fingerprint.json", fingerprint)
    return directory


def _v1_package(directory: Path) -> Path:
    return _write_package(
        directory,
        descriptor=production_descriptor_v3(),
        manifest=production_manifest_v3(),
        template=production_template(),
        profile=production_profile_v2(),
        fingerprint=production_fingerprint_document())


def _v2_package(directory: Path) -> Path:
    return _write_package(
        directory,
        descriptor=production_descriptor_v4(),
        manifest=production_manifest_v3_v2(),
        template=production_template(),
        profile=production_profile_v3(),
        fingerprint=production_fingerprint_document())


async def _capture(directory: Path):
    return await capture_release(
        directory / "workflow-package.json",
        directory / "manifest.json",
        directory / "workflow.json",
        directory / "realization-profile.json",
        directory / "execution-model-fingerprint.json")


# ---- PKG:01 descriptor-4 coherent four-artifact capture ---------------------

async def test_m14_pkg_01(tmp_path):
    release = await _capture(_v2_package(tmp_path / "v2"))
    assert release.schema_version == 4
    assert release.workflow_version == 2
    package = validate_package(release)
    assert package.is_schema3, (
        "descriptor 4 is the same manifest-v3 spatial family")
    descriptor = production_descriptor_v4()
    assert release.manifest_hash == descriptor["manifest_hash"]
    assert release.workflow_template_hash == (
        descriptor["workflow_template_hash"])
    assert release.realization_profile_hash == (
        descriptor["realization_profile_hash"])
    assert release.execution_model_fingerprint_hash == (
        descriptor["execution_model_fingerprint_hash"])

    # tampered member hash → capture refuses (coherent four-hash binding)
    broken = _v2_package(tmp_path / "broken")
    doc = json.loads((broken / "manifest.json").read_text(encoding="utf-8"))
    doc["inputs"]["prompt"]["node"] = "999"
    (broken / "manifest.json").write_bytes(
        canonical_json_str(doc).encode("utf-8"))
    with pytest.raises(Exception, match="do not match"):
        await _capture(broken)


# ---- PKG:02 workflow identity agreement -------------------------------------

async def test_m14_pkg_02(tmp_path):
    release = await _capture(_v2_package(tmp_path))
    package = validate_package(release)
    assert package.manifest_v3["workflow_id"] == "wan21_spatial_v1"
    assert package.manifest_v3["version"] == 2
    assert package.profile_v2["workflow_version"] == 2
    assert package.profile_v2["schema_version"] == 3

    # an incoherent descriptor (v2 declared, v1 manifest) fails the
    # package cross-identity law
    mixed = _write_package(
        tmp_path / "mixed",
        descriptor=production_descriptor_v4(),
        manifest=production_manifest_v3(),  # v1 manifest under v2 desc
        template=production_template(),
        profile=production_profile_v3(),
        fingerprint=production_fingerprint_document())
    with pytest.raises(Exception, match="incoherent"):
        await _capture(mixed)


# ---- PKG:03 capability contract hash bound to profile bytes ------------------

async def test_m14_pkg_03(tmp_path):
    release = await _capture(_v2_package(tmp_path))
    package = validate_package(release)
    block = package.profile_v2["observation"]
    validate_observation_block(block)
    assert capability_contract_hash(package.profile_v2) == (
        canonical_hash(block)), (
        "the capability contract hash is SHA-256 over the canonical "
        "captured observation block bytes")
    contract = build_materializer_contract()
    assert block["materializers"][0]["contract_hash"] == (
        materializer_contract_hash(contract)), (
        "the release's materializer contract identity IS the REAL "
        "implementation/runtime contract — mechanically derived, never "
        "hand-pinned")
    for capability in block["capabilities"]:
        assert capability["materializer_id"] == (
            block["materializers"][0]["id"])
        assert capability["materializer_version"] == (
            block["materializers"][0]["version"])


# ---- PKG:04 runtime fingerprint/template closure remains exact --------------

async def test_m14_pkg_04(tmp_path):
    release_v1 = await _capture(_v1_package(tmp_path / "v1"))
    release_v2 = await _capture(_v2_package(tmp_path / "v2"))
    assert release_v1.template_bytes == release_v2.template_bytes, (
        "the v2 release inherits the EXACT certified template bytes")
    assert release_v1.fingerprint_bytes == release_v2.fingerprint_bytes, (
        "the v2 release inherits the EXACT captured fingerprint family")
    validate_package(release_v1)
    validate_package(release_v2)


# ---- PKG:05 v1 immutable/executable -----------------------------------------

async def test_m14_pkg_05(tmp_path):
    """v1 stays byte- and meaning-immutable: the v1 builders still
    produce the certified release, it validates, and the v2 builders
    never touch the v1 documents."""
    v1_dir = _v1_package(tmp_path / "v1")
    release = await _capture(v1_dir)
    package = validate_package(release)
    assert package.release.schema_version == 3
    assert package.release.workflow_version == 1
    assert "observation" not in package.profile_v2

    # the v1 members are byte-identical under v2 construction EXCEPT the
    # manifest (workflow version) and the profile (schema 3 + block):
    assert production_manifest_v3_v2() != production_manifest_v3()
    v1_manifest = production_manifest_v3()
    v2_manifest = production_manifest_v3_v2()
    assert {k: v for k, v in v2_manifest.items() if k != "version"} == {
        k: v for k, v in v1_manifest.items() if k != "version"}, (
        "the v2 manifest changes ONLY the workflow version")
    v1_profile = production_profile_v2()
    v3_profile = production_profile_v3()
    assert {k: v for k, v in v3_profile.items()
            if k not in ("schema_version", "workflow_version",
                         "observation")} == {
        k: v for k, v in v1_profile.items()
        if k not in ("schema_version", "workflow_version")}, (
        "the schema-3 profile inherits the exact schema-2 fields")


# ---- PKG:06 v2 package validates end-to-end ---------------------------------

async def test_m14_pkg_06(tmp_path):
    release = await _capture(_v2_package(tmp_path))
    package = validate_package(release)
    assert package.release.schema_version == 4
    block = package.profile_v2["observation"]
    tuples = {(c["property"], c["preservation"], c["source_contract"])
              for c in block["capabilities"]}
    assert tuples == {
        ("camera.projection", "STRUCTURAL", "m10.camera_projection.v1"),
        ("world.structure", "STRUCTURAL", "m10.world_depth.v1"),
        ("occurrence.structure", "STRUCTURAL",
         "soloring.structural_mesh.v1"),
        ("occurrence.placement", "STRUCTURAL", "m14.placement.v1")}, (
        "the initial profile advertises EXACTLY the four structural "
        "tuples B3 mechanically proves")


# ---- the hard non-capabilities (report requirement) --------------------------

async def test_v2_hard_refusals(tmp_path):
    """visual.identity and continuity.instance_feature REQUIRED under
    this profile negotiate UNSUPPORTED — Wan's inference ability never
    manufactures a capability absent from the captured profile."""
    from tests.test_m14_capabilities import (
        _requirement as _cap_requirement,
        _spec as _cap_spec,
    )

    release = await _capture(_v2_package(tmp_path))
    package = validate_package(release)
    block = package.profile_v2["observation"]

    # NOTE: §8.10's mechanical rule gives UNKNOWN for a property the
    # profile has NO declaration for at all (a §17 capability entry
    # cannot exist without a resolvable materializer, so absence is the
    # only representation the grammar allows). The frozen §15 matrix
    # labels these rows UNSUPPORTED at the product level; under EITHER
    # verdict the requirement refuses before Generation publication —
    # which is the load-bearing claim. Wan's inference ability never
    # manufactures a capability.
    visual = _cap_spec([
        _cap_requirement("visual.identity", "IDENTITY_APPEARANCE",
                         "REQUIRED", "m8.visual_reference_pack.v1",
                         domain="A3", source_kind="visual_reference_pack")])
    verdict = negotiate(visual, block)
    assert verdict["requirements"][0]["verdict"] == "UNSUPPORTED", (
        "Erratum E-1: the explicit unsupported declaration makes the "
        "frozen §15 N1 row exactly UNSUPPORTED")
    assert verdict["verdict"] == "UNSUPPORTED"
    assert verdict["requirements"][0]["capability"] is None

    feature = _cap_spec([
        _cap_requirement(
            "continuity.instance_feature", "EXACT", "REQUIRED",
            "m13.production_instance_feature.v1", domain="A2",
            source_kind="production_world_pack", subkey="wardrobe_color")])
    verdict = negotiate(feature, block)
    assert verdict["requirements"][0]["verdict"] == "UNSUPPORTED", (
        "Erratum E-1: the frozen §15 N2 row is exactly UNSUPPORTED")
    assert verdict["verdict"] == "UNSUPPORTED"
    assert verdict["requirements"][0]["capability"] is None

    # the DISTINCT UNKNOWN case: a property absent from BOTH lists
    absent = _cap_spec([
        _cap_requirement("occurrence.placement", "STRUCTURAL",
                         "REQUIRED", "m14.placement.v1")])
    import copy

    reduced = copy.deepcopy(block)
    reduced["capabilities"] = [c for c in reduced["capabilities"]
                               if c["property"] != "occurrence.placement"]
    verdict = negotiate(absent, reduced)
    assert verdict["requirements"][0]["verdict"] == "UNKNOWN"
    assert verdict["verdict"] == "UNKNOWN"

    # shot.intent stays PERMITTED_INFERENCE, never a structural claim
    intent = _cap_spec([
        _cap_requirement("shot.intent", "INFERABLE",
                         "PERMITTED_INFERENCE",
                         "lower_schema_3.prompt", domain="A1",
                         source_kind="shot_revision")])
    verdict = negotiate(intent, block)
    assert verdict["verdict"] == "SUPPORTED"
    assert verdict["requirements"][0]["verdict"] == "PERMITTED_INFERENCE"


async def test_descriptor4_requires_profile3(tmp_path):
    """Erratum E-2: a hash-coherent schema-4 descriptor over a
    schema-2 profile claims the version without the semantics it was
    introduced to identify — it now REJECTS."""
    from soloring.spatial.package3 import Package3Invalid

    mixed = _write_package(
        tmp_path / "d4-p2",
        descriptor=production_descriptor_v4()
        | {"realization_profile_hash": canonical_hash(
            production_profile_v2())},
        manifest=production_manifest_v3_v2(),
        template=production_template(),
        profile=production_profile_v2(),  # schema 2 under descriptor 4
        fingerprint=production_fingerprint_document())
    with pytest.raises(Package3Invalid, match="schema 4 requires"):
        validate_package(await _capture(mixed))


# ---- PKG:07 release-switch race cannot capture a hybrid ----------------------

async def test_m14_pkg_07(tmp_path):
    """A concurrent release switch during capture yields complete
    BEFORE, complete AFTER, or an integrity refusal — never a hybrid.
    The D1/D2 descriptor re-read catches the torn write."""
    directory = _v1_package(tmp_path / "pkg")
    v2_files = {
        name: (Path(_v2_package(tmp_path / "v2source")) / name).read_bytes()
        for name in ("workflow-package.json", "manifest.json",
                     "workflow.json", "realization-profile.json",
                     "execution-model-fingerprint.json")
    }

    switch = asyncio.Event()
    capture_task = asyncio.create_task(_capture(directory))

    async def switcher():
        await asyncio.sleep(0)  # interleave with the capture reads
        for name, payload in v2_files.items():
            (directory / name).write_bytes(payload)
        switch.set()

    from soloring.realization.packages import PackageIntegrity
    from soloring.workflows.artifact_store import IncoherentCapture

    try:
        await asyncio.gather(capture_task, switcher())
        result = capture_task.result()
        # whatever was captured validates coherently: v1 or v2, never
        # mixed
        package = validate_package(result)
        version = package.release.workflow_version
        assert version in (1, 2)
        if version == 1:
            assert "observation" not in package.profile_v2
        else:
            assert "observation" in package.profile_v2
    except (IncoherentCapture, PackageIntegrity):
        # the THIRD legal race outcome (frozen RACE-05): the capture
        # REFUSED the torn window instead of resolving to a complete
        # side — an integrity refusal, never a hybrid. The torn window
        # manifests differently across platforms (CI's Posix timing
        # reaches the manifest-vs-descriptor refusal; locally the
        # descriptor re-read catches it as IncoherentCapture).
        pass

    # a fully settled switch captures the complete v2 release
    for name, payload in v2_files.items():
        (directory / name).write_bytes(payload)
    after = validate_package(await _capture(directory))
    assert after.release.workflow_version == 2


# ---- PKG:08 recovery retains all four schema-4 package artifacts -------------

async def test_m14_pkg_08(tmp_path, monkeypatch):
    """The schema-4 WorkflowSpec artifact-liveness view uses the same
    four package artifact kinds — proven at the recovery grammar level:
    a schema-4 spec's lower_schema_3 identities resolve within the four
    kinds, and the observation block adds no fifth artifact demand."""
    from soloring.recovery.backup import _generation_artifact_requirements

    release = await _capture(_v2_package(tmp_path))
    package = validate_package(release)
    lower_spatial = {
        "schema_version": 3,
        "workflow_id": "wan21_spatial_v1",
        "workflow_version": 2,
        "manifest_hash": package.release.manifest_hash,
        "inputs": {},
        "prompt": "lobby",
        "parameters": {},
        "outputs": [],
        "model": {
            "id": "wan2.1-t2v-1.3b", "version": "fp16",
            "execution_model_fingerprint_hash": (
                package.release.execution_model_fingerprint_hash)},
        "spatial_realization": {
            "schema_version": 1,
            "spatial_continuity_hash": "a" * 64,
            "realization_profile_hash": (
                package.release.realization_profile_hash),
            "structured_bindings": [],
            "derived_artifacts": [],
            "advisory_omissions": [],
        },
    }
    spec = {
        "schema_version": 4,
        "lower_schema_3": lower_spatial,
        "world_observation": {
            "spec": {}, "spec_hash": "b" * 64,
            "profile_hash": package.release.realization_profile_hash,
            "capability_contract_hash": "c" * 64,
            "negotiation": {}, "negotiation_hash": "d" * 64,
        },
    }
    requirements = _generation_artifact_requirements(spec, "Generation x")
    kinds = {kind for kind, _ in requirements}
    assert kinds <= {"manifests", "templates", "realization_profiles",
                     "execution_model_fingerprints"}, (
        "schema 4 references exactly the same four workflow-package "
        "artifact kinds — no fifth observation artifact exists")
    assert ("realization_profiles",
            package.release.realization_profile_hash) in requirements
    assert ("execution_model_fingerprints",
            package.release.execution_model_fingerprint_hash
            ) in requirements
