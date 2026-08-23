"""M9A — package/profile/fingerprint contracts (frozen plan §§6–8, 23–24,
77).

Covers: strict schema-1 documents (recursive unknown-field rejection),
the closed fingerprint rules incl. safe relative declared_name, manifest
schema 2 source discrimination, four-artifact coherent capture with the
descriptor-last D1/D2 discipline, package cross-validation (identity,
bijection, fingerprint↔template), artifact-store extension, the §6.4
model-root adapter, and golden raw-byte fixtures for the authored
Hunyuan v4 release. CI is hermetic: live-deployment facts are verified
in the M9 live lane, not here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import text

from soloring.errors import SoloRingError
from soloring.realization.fingerprint import (
    cross_validate_fingerprint_template,
    parse_fingerprint,
    validate_declared_name,
)
from soloring.realization.model_roots import (
    ModelIncompatible,
    hash_file_streaming,
    resolve_model_file,
    verify_live_model_bytes,
)
from soloring.realization.packages import (
    PackageIntegrity,
    capture_release,
    validate_package,
)
from soloring.realization.profile import parse_profile
from soloring.settings import BASE_DIR, Settings
from soloring.workflows.artifact_store import WorkflowArtifactStore
from soloring.workflows.manifest import parse_manifest, parse_manifest_v2

V3_DIR = BASE_DIR / "workflows" / "hunyuan_i2v_v1"
V4_DIR = BASE_DIR / "workflows" / "hunyuan_i2v_v4"

# Golden raw-byte identities of the authored schema-2 release (M9A gate).
V4_PROFILE_HASH = "ebf35077d8da2fa7d6495e7d1b277fff93efdf0bff5948e46b7e3a5ea44c1641"
V4_FINGERPRINT_HASH = (
    "c23a99e1e560b02e40eae39099c164aefda451ea02654129bd929f640a2fb03b"
)
V4_MANIFEST_HASH = (
    "0cb9e00875347af274d146c96846bcd9a4d81150541ac78893f735178b0bdfe3"
)
# The template bytes are deliberately identical to the published v3
# release: content addressing converges on the same identity.
V3_TEMPLATE_HASH = (
    "c7ee0fb9a6c430623f086b0df242ffcd6aefe1b3a3f44eec0d2cd8197aed6b3f"
)


def _profile_doc() -> dict:
    return json.loads((V4_DIR / "realization-profile.json").read_text())


def _fingerprint_doc() -> dict:
    return json.loads((V4_DIR / "execution-model-fingerprint.json").read_text())


async def _capture_v4(tmp: Path | None = None) -> object:
    d = tmp or V4_DIR
    return await capture_release(
        d / "workflow-package.json",
        d / "manifest.json",
        d / "workflow.json",
        d / "realization-profile.json",
        d / "execution-model-fingerprint.json",
    )


async def _capture_v3() -> object:
    return await capture_release(
        V3_DIR / "workflow-package.json",
        V3_DIR / "manifest.json",
        V3_DIR / "workflow.json",
    )


# --- RealizationProfile schema 1 ---------------------------------------------------


def test_profile_golden_bytes_and_parse():
    doc = parse_profile((V4_DIR / "realization-profile.json").read_text())
    assert doc.schema_version == 1
    assert doc.profile_id == "hunyuan-i2v-single-reference"
    assert set(doc.channels) == {"hero_reference"}
    assert doc.channels["hero_reference"].allowed_roles == ["primary"]
    assert doc.rules[0].facet_key == "identity"
    import hashlib

    assert hashlib.sha256(
        (V4_DIR / "realization-profile.json").read_bytes()
    ).hexdigest() == V4_PROFILE_HASH


def test_profile_rejects_unknown_fields_recursively():
    doc = _profile_doc()
    doc["channels"]["hero_reference"]["surprise"] = 1
    with pytest.raises(SoloRingError) as ei:
        parse_profile(doc)
    assert ei.value.code == "REALIZATION_PROFILE_INVALID"


def test_profile_rejects_duplicate_selector():
    doc = _profile_doc()
    doc["rules"].append(
        {"target_kind": "entity", "facet_key": "identity",
         "channel": "hero_reference"}
    )
    with pytest.raises(SoloRingError) as ei:
        parse_profile(doc)
    assert "Duplicate profile selector" in ei.value.message


def test_profile_rejects_min_max_and_unreachable_channel():
    doc = _profile_doc()
    doc["channels"]["hero_reference"]["min_items"] = 2
    doc["channels"]["hero_reference"]["max_items"] = 1
    with pytest.raises(SoloRingError, match="exceeds"):
        parse_profile(doc)

    # min_items > 0 with no targeting rule is statically invalid (§7.6).
    doc = _profile_doc()
    doc["rules"] = []
    with pytest.raises(SoloRingError, match="no rule targets it"):
        parse_profile(doc)


def test_profile_rejects_unknown_role_and_bad_facet_key():
    doc = _profile_doc()
    doc["channels"]["hero_reference"]["allowed_roles"] = ["hero"]
    with pytest.raises(SoloRingError, match="unknown M8 role"):
        parse_profile(doc)

    doc = _profile_doc()
    doc["rules"][0]["facet_key"] = "Not-Lowercase"
    with pytest.raises(SoloRingError, match="grammar"):
        parse_profile(doc)


def test_profile_rejects_rule_to_unknown_channel():
    doc = _profile_doc()
    doc["rules"][0]["channel"] = "missing_channel"
    with pytest.raises(SoloRingError, match="unknown channel"):
        parse_profile(doc)


# --- ExecutionModelFingerprint schema 1 ---------------------------------------------


def test_fingerprint_golden_bytes_and_parse():
    doc = parse_fingerprint(
        (V4_DIR / "execution-model-fingerprint.json").read_text()
    )
    assert doc.model_id == "hunyuan-video-i2v"
    assert len(doc.artifacts) == 5  # ALL model-bearing loaders, not just UNet
    nodes = {(a.node, a.field) for a in doc.artifacts}
    assert nodes == {
        ("10", "vae_name"),
        ("97", "clip_name"),
        ("98", "unet_name"),
        ("99", "clip_name1"),
        ("99", "clip_name2"),
    }
    import hashlib

    assert hashlib.sha256(
        (V4_DIR / "execution-model-fingerprint.json").read_bytes()
    ).hexdigest() == V4_FINGERPRINT_HASH


def test_fingerprint_rejects_unknown_fields_and_duplicates():
    doc = _fingerprint_doc()
    doc["artifacts"][0]["extra"] = True
    with pytest.raises(SoloRingError) as ei:
        parse_fingerprint(doc)
    assert ei.value.code == "EXECUTION_MODEL_FINGERPRINT_INVALID"

    doc = _fingerprint_doc()
    doc["artifacts"][1]["artifact_key"] = doc["artifacts"][0]["artifact_key"]
    with pytest.raises(SoloRingError, match="Duplicate artifact_key"):
        parse_fingerprint(doc)

    doc = _fingerprint_doc()
    doc["artifacts"][1]["node"] = doc["artifacts"][0]["node"]
    doc["artifacts"][1]["field"] = doc["artifacts"][0]["field"]
    with pytest.raises(SoloRingError, match="Duplicate fingerprint loader"):
        parse_fingerprint(doc)


def test_fingerprint_rejects_bad_root_key_sha_and_commits():
    doc = _fingerprint_doc()
    doc["artifacts"][0]["storage_root_key"] = "checkpoints"
    with pytest.raises(SoloRingError, match="frozen adapter vocabulary"):
        parse_fingerprint(doc)

    doc = _fingerprint_doc()
    doc["artifacts"][0]["sha256"] = "XYZ"
    with pytest.raises(SoloRingError, match="lowercase 64-hex"):
        parse_fingerprint(doc)

    doc = _fingerprint_doc()
    doc["runtime_requirements"]["comfyui_commit"] = "not-a-commit"
    with pytest.raises(SoloRingError, match="40-hex"):
        parse_fingerprint(doc)

    doc = _fingerprint_doc()
    doc["runtime_requirements"]["custom_node_policy"]["disable_all"] = False
    with pytest.raises(SoloRingError, match="disable-all"):
        parse_fingerprint(doc)


def test_fingerprint_declared_name_safe_relative_contract():
    for bad in (
        "/abs/name.safetensors",
        "C:/models/name.gguf",
        "../escape.gguf",
        "a/../b.gguf",
        "a//b.gguf",
        "./here.gguf",
        "trailing/",
        "back\\slash.gguf",
        "",
    ):
        with pytest.raises(SoloRingError):
            validate_declared_name(bad)
    assert validate_declared_name("dir/name.gguf") == "dir/name.gguf"


def test_fingerprint_template_cross_validation():
    fp = parse_fingerprint(
        (V4_DIR / "execution-model-fingerprint.json").read_text()
    )
    template = json.loads((V4_DIR / "workflow.json").read_text())
    cross_validate_fingerprint_template(fp, template)  # positive control

    bad = _fingerprint_doc()
    bad["artifacts"][0]["node"] = "404"
    with pytest.raises(SoloRingError, match="does not exist"):
        cross_validate_fingerprint_template(
            parse_fingerprint(bad), template
        )

    bad = _fingerprint_doc()
    bad["artifacts"][0]["declared_name"] = "different.safetensors"
    with pytest.raises(SoloRingError, match="differs from template"):
        cross_validate_fingerprint_template(
            parse_fingerprint(bad), template
        )


# --- Manifest schema 2 ---------------------------------------------------------------


def test_manifest_v2_parses_and_rejects_source_role():
    doc = parse_manifest_v2((V4_DIR / "manifest.json").read_text())
    src = doc.inputs["reference_image"].source
    assert src.kind == "realization_channel"
    assert src.channel == "hero_reference"
    assert "source_role" not in (
        json.loads((V4_DIR / "manifest.json").read_text())
        ["inputs"]["reference_image"]
    )

    raw = json.loads((V4_DIR / "manifest.json").read_text())
    raw["inputs"]["reference_image"]["source_role"] = "reference"
    with pytest.raises(SoloRingError, match="no dual form"):
        parse_manifest_v2(raw)


def test_manifest_v2_rejects_invalid_shot_reference_role():
    raw = json.loads((V4_DIR / "manifest.json").read_text())
    raw["inputs"]["reference_image"]["source"] = {
        "kind": "shot_reference", "role": "   ",
    }
    with pytest.raises(SoloRingError, match="valid predecessor"):
        parse_manifest_v2(raw)


def test_manifest_schema1_remains_accepted_unchanged():
    doc = parse_manifest((V3_DIR / "manifest.json").read_text())
    assert doc.version == 3
    assert doc.inputs["reference_image"].source_role == "reference"


def test_schema2_legacy_binding_equivalence_fixture():
    """§8: re-authoring the v3 legacy input into schema-2 shot_reference
    form preserves the identical resolved binding semantics."""
    v1 = parse_manifest((V3_DIR / "manifest.json").read_text())
    raw = json.loads((V4_DIR / "manifest.json").read_text())
    raw["inputs"]["reference_image"]["source"] = {
        "kind": "shot_reference", "role": "reference",
    }
    v2 = parse_manifest_v2(raw)
    a, b = v1.inputs["reference_image"], v2.inputs["reference_image"]
    assert (a.node, a.field, a.kind, a.required, a.cardinality) == (
        b.node, b.field, b.kind, b.required, b.cardinality
    )
    assert a.source_role == v2.inputs["reference_image"].source.role


# --- Coherent four-artifact capture --------------------------------------------------


async def test_v4_release_captures_with_golden_hashes():
    release = await _capture_v4()
    assert release.schema_version == 2
    assert release.workflow_version == 4
    assert release.manifest_hash == V4_MANIFEST_HASH
    assert release.workflow_template_hash == V3_TEMPLATE_HASH
    assert release.realization_profile_hash == V4_PROFILE_HASH
    assert release.execution_model_fingerprint_hash == V4_FINGERPRINT_HASH


async def test_v3_schema1_release_captures_unchanged(tmp_path):
    release = await _capture_v3()
    assert release.schema_version == 1
    assert release.realization_profile_hash is None
    # Round-trips through the legacy discipline too.
    store = WorkflowArtifactStore(Settings(data_dir=tmp_path / "d"))
    await store.place_release(release)
    assert await store.get_manifest(release.manifest_hash) == (
        release.manifest_bytes
    )


async def test_capture_rejects_hash_mismatch_as_package_integrity(tmp_path):
    d = tmp_path / "pkg"
    d.mkdir()
    for name in (
        "workflow-package.json", "manifest.json", "workflow.json",
        "realization-profile.json", "execution-model-fingerprint.json",
    ):
        (d / name).write_bytes((V4_DIR / name).read_bytes())
    # Tamper the profile bytes (descriptor still declares the golden hash).
    (d / "realization-profile.json").write_text("{}")
    with pytest.raises(PackageIntegrity):
        await capture_release(
            d / "workflow-package.json", d / "manifest.json",
            d / "workflow.json", d / "realization-profile.json",
            d / "execution-model-fingerprint.json",
        )


async def test_capture_rejects_descriptor_change_during_capture(
    tmp_path, monkeypatch,
):
    import soloring.realization.packages as pkg

    d = tmp_path / "pkg"
    d.mkdir()
    for name in (
        "workflow-package.json", "manifest.json", "workflow.json",
        "realization-profile.json", "execution-model-fingerprint.json",
    ):
        (d / name).write_bytes((V4_DIR / name).read_bytes())

    real_read = pkg._read_descriptor
    calls = {"n": 0}

    def flip(path):
        doc = real_read(path)
        calls["n"] += 1
        if calls["n"] == 2:  # the D2 read observes a switched release
            doc = dict(doc)
            doc["workflow_version"] = 5
        return doc

    monkeypatch.setattr(pkg, "_read_descriptor", flip)
    with pytest.raises(PackageIntegrity, match="descriptor changed"):
        await capture_release(
            d / "workflow-package.json", d / "manifest.json",
            d / "workflow.json", d / "realization-profile.json",
            d / "execution-model-fingerprint.json",
        )


async def test_schema1_descriptor_cannot_claim_m9_artifacts(tmp_path):
    import hashlib

    d = tmp_path / "pkg"
    d.mkdir()
    for name in ("manifest.json", "workflow.json"):
        (d / name).write_bytes((V3_DIR / name).read_bytes())
    (d / "workflow-package.json").write_text(json.dumps({
        "schema_version": 1,
        "workflow_id": "hunyuan_i2v",
        "workflow_version": 3,
        "manifest_hash": hashlib.sha256(
            (d / "manifest.json").read_bytes()
        ).hexdigest(),
        "workflow_template_hash": hashlib.sha256(
            (d / "workflow.json").read_bytes()
        ).hexdigest(),
        "realization_profile_hash": "0" * 64,
    }))
    with pytest.raises(PackageIntegrity, match="cannot claim M9|field set is closed"):
        await capture_release(
            d / "workflow-package.json", d / "manifest.json",
            d / "workflow.json",
        )


# --- Package cross-validation ----------------------------------------------------


async def test_v4_package_validates_end_to_end():
    release = await _capture_v4()
    package = validate_package(release)
    assert package.is_schema2
    assert package.profile.profile_id == "hunyuan-i2v-single-reference"
    assert package.fingerprint.model_id == package.profile.model.id
    assert package.release.release_identity() == {
        "schema_version": 2,
        "workflow_id": "hunyuan_i2v",
        "workflow_version": 4,
        "manifest_hash": V4_MANIFEST_HASH,
        "workflow_template_hash": V3_TEMPLATE_HASH,
        "realization_profile_hash": V4_PROFILE_HASH,
        "execution_model_fingerprint_hash": V4_FINGERPRINT_HASH,
    }


async def test_package_rejects_identity_disagreement(tmp_path):
    d = tmp_path / "pkg"
    d.mkdir()
    for name in (
        "manifest.json", "workflow.json", "realization-profile.json",
        "execution-model-fingerprint.json",
    ):
        (d / name).write_bytes((V4_DIR / name).read_bytes())
    profile = json.loads((V4_DIR / "realization-profile.json").read_text())
    profile["workflow_version"] = 99
    (d / "realization-profile.json").write_text(json.dumps(profile))
    import hashlib

    descriptor = {
        "schema_version": 2,
        "workflow_id": "hunyuan_i2v",
        "workflow_version": 4,
        "manifest_hash": hashlib.sha256(
            (d / "manifest.json").read_bytes()
        ).hexdigest(),
        "workflow_template_hash": hashlib.sha256(
            (d / "workflow.json").read_bytes()
        ).hexdigest(),
        "realization_profile_hash": hashlib.sha256(
            (d / "realization-profile.json").read_bytes()
        ).hexdigest(),
        "execution_model_fingerprint_hash": hashlib.sha256(
            (d / "execution-model-fingerprint.json").read_bytes()
        ).hexdigest(),
    }
    (d / "workflow-package.json").write_text(json.dumps(descriptor))
    release = await capture_release(
        d / "workflow-package.json", d / "manifest.json", d / "workflow.json",
        d / "realization-profile.json",
        d / "execution-model-fingerprint.json",
    )
    with pytest.raises(SoloRingError) as ei:
        validate_package(release)
    assert ei.value.code == "REALIZATION_INPUT_BINDING_INVALID"


async def test_package_rejects_model_identity_mismatch():
    release = await _capture_v4()
    from dataclasses import replace

    fp = _fingerprint_doc()
    fp["model_version"] = "different"
    tampered = replace(
        release,
        fingerprint_bytes=json.dumps(fp).encode(),
    )
    with pytest.raises(SoloRingError, match="model identity"):
        validate_package(tampered)


async def test_package_rejects_bijection_breaks(tmp_path):
    # Manifest realization input without a matching profile channel.
    d = tmp_path / "pkg"
    d.mkdir()
    for name in (
        "workflow.json", "realization-profile.json",
        "execution-model-fingerprint.json",
    ):
        (d / name).write_bytes((V4_DIR / name).read_bytes())
    manifest = json.loads((V4_DIR / "manifest.json").read_text())
    manifest["inputs"]["reference_image"]["source"]["channel"] = "ghost"
    (d / "manifest.json").write_text(json.dumps(manifest))
    import hashlib

    descriptor = {
        "schema_version": 2,
        "workflow_id": "hunyuan_i2v",
        "workflow_version": 4,
        "manifest_hash": hashlib.sha256(
            (d / "manifest.json").read_bytes()
        ).hexdigest(),
        "workflow_template_hash": hashlib.sha256(
            (d / "workflow.json").read_bytes()
        ).hexdigest(),
        "realization_profile_hash": V4_PROFILE_HASH,
        "execution_model_fingerprint_hash": V4_FINGERPRINT_HASH,
    }
    (d / "workflow-package.json").write_text(json.dumps(descriptor))
    release = await capture_release(
        d / "workflow-package.json", d / "manifest.json", d / "workflow.json",
        d / "realization-profile.json",
        d / "execution-model-fingerprint.json",
    )
    with pytest.raises(SoloRingError, match="no matching"):
        validate_package(release)


# --- Artifact store extension ------------------------------------------------------


async def test_store_places_and_verifies_profile_fingerprint(tmp_path):
    settings = Settings(data_dir=tmp_path / "d")
    store = WorkflowArtifactStore(settings)
    release = await _capture_v4()
    await store.place_release(release)
    assert await store.get_profile(V4_PROFILE_HASH) == (
        release.profile_bytes
    )
    assert await store.get_fingerprint(V4_FINGERPRINT_HASH) == (
        release.fingerprint_bytes
    )
    # Missing historical fingerprint bytes are corruption, not 404-flavored.
    store._path(
        "execution_model_fingerprints", V4_FINGERPRINT_HASH
    ).unlink()
    with pytest.raises(SoloRingError) as ei:
        await store.get_fingerprint(V4_FINGERPRINT_HASH)
    assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"


# --- §6.4 model-root adapter --------------------------------------------------------


def _root_settings(tmp_path: Path, with_files: dict[str, bytes]) -> Settings:
    unet = tmp_path / "unet"
    unet.mkdir()
    for name, content in with_files.items():
        (unet / name).write_bytes(content)
    return Settings(
        data_dir=tmp_path / "data",
        comfy_model_root_unet=unet,
        comfy_model_root_vae=tmp_path / "vae",
        comfy_model_root_clip=tmp_path / "clip",
        comfy_model_root_clip_vision=tmp_path / "vision",
    )


def test_model_root_unset_and_relative_fail_closed(tmp_path):
    settings = Settings(data_dir=tmp_path / "d")  # no roots configured
    with pytest.raises(ModelIncompatible, match="not configured"):
        resolve_model_file(settings, "unet", "model.gguf")
    rel = Settings(
        data_dir=tmp_path / "d",
        comfy_model_root_unet=Path("relative/root"),
    )
    with pytest.raises(ModelIncompatible, match="not absolute"):
        resolve_model_file(rel, "unet", "model.gguf")


def test_model_root_traversal_and_containment(tmp_path):
    settings = _root_settings(tmp_path, {"model.gguf": b"x"})
    with pytest.raises(SoloRingError):
        resolve_model_file(settings, "unet", "../escape.gguf")
    path = resolve_model_file(settings, "unet", "model.gguf")
    assert path.is_file()


def test_verify_live_model_bytes_positive_and_drift(tmp_path):
    import hashlib

    good = b"hunyuan-bytes-v1"
    settings = _root_settings(tmp_path, {"model.gguf": good})
    expected = hashlib.sha256(good).hexdigest()
    resolved = verify_live_model_bytes(
        settings,
        [("video_unet", "unet", "model.gguf", expected)],
    )
    assert resolved["video_unet"].endswith("model.gguf")

    # Same filename, different bytes → EXECUTION_MODEL_INCOMPATIBLE.
    (tmp_path / "unet" / "model.gguf").write_bytes(b"hunyuan-bytes-v2")
    with pytest.raises(ModelIncompatible, match="hashes to"):
        verify_live_model_bytes(
            settings,
            [("video_unet", "unet", "model.gguf", expected)],
        )


def test_verify_dedupes_same_file_within_attempt(tmp_path):
    import hashlib

    settings = _root_settings(tmp_path, {"a.gguf": b"same", "b.gguf": b"same"})
    expected = hashlib.sha256(b"same").hexdigest()
    resolved = verify_live_model_bytes(
        settings,
        [
            ("k1", "unet", "a.gguf", expected),
            ("k2", "unet", "b.gguf", expected),
        ],
    )
    assert set(resolved) == {"k1", "k2"}


def test_settings_expose_model_roots_via_env_prefix(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "SOLORING_COMFY_MODEL_ROOT_UNET", str(tmp_path / "models-unet")
    )
    settings = Settings(data_dir=tmp_path / "d")
    assert settings.comfy_model_root_unet == tmp_path / "models-unet"


# --- Source-fit ledger --------------------------------------------------------------


async def test_no_migration_added_and_reference_role_still_present():
    versions = sorted(
        p.name for p in
        (BASE_DIR / "server" / "alembic" / "versions").glob("0*.py")
    )
    assert versions[-1] == "0011_m10_derived_spatial_execution.py"
    # M10A added 0010/0011 (frozen r3 §7/§102); M9 itself added none beyond
    # updating predecessor head pins.
    # generation_inputs.reference_role remains the published fact.
    from tests.conftest import seed_reference_asset  # noqa: F401 (presence)

    assert "reference_role" in (BASE_DIR / "server" / "alembic" / "versions"
                                / "0002_temporal_domain_storage.py").read_text()
