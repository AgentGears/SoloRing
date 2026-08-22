"""Workflow package schema 2 (frozen plan §§6, 23, 24, 66).

Four-artifact descriptor-bound release capture with the M5 descriptor-
last discipline extended to manifest+template+profile+fingerprint, plus
the full package cross-validation (profile structure, profile↔manifest
channel bijection, fingerprint↔template bindings, package cross-
identity). No DB, no sessions — file I/O and pure validation only.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from soloring.errors import ErrorCode, SoloRingError
from soloring.realization.fingerprint import (
    ExecutionModelFingerprintDocument,
    cross_validate_fingerprint_template,
    parse_fingerprint,
)
from soloring.realization.profile import (
    RealizationProfileDocument,
    parse_profile,
)
from soloring.workflows.manifest import (
    ManifestDocumentV2,
    parse_manifest,
    parse_manifest_v2,
)

_HEX = set("0123456789abcdef")


class PackageIntegrity(SoloRingError):
    """Stage-0: one coherent current release byte set cannot be
    established (§23 / §41: WORKFLOW_PACKAGE_INTEGRITY)."""

    def __init__(self, what: str) -> None:
        super().__init__(
            ErrorCode.WORKFLOW_PACKAGE_INTEGRITY,
            f"Workflow package capture incoherent ({what}); no candidate "
            "package snapshot exists.",
            status_code=503,
        )


@dataclass(frozen=True)
class CapturedPackageRelease:
    """One complete, descriptor-bound release byte snapshot."""

    schema_version: int
    workflow_id: str
    workflow_version: int
    manifest_hash: str
    manifest_bytes: bytes
    workflow_template_hash: str
    template_bytes: bytes
    realization_profile_hash: str | None = None
    profile_bytes: bytes | None = None
    execution_model_fingerprint_hash: str | None = None
    fingerprint_bytes: bytes | None = None

    def release_identity(self) -> dict:
        out = {
            "schema_version": self.schema_version,
            "workflow_id": self.workflow_id,
            "workflow_version": self.workflow_version,
            "manifest_hash": self.manifest_hash,
            "workflow_template_hash": self.workflow_template_hash,
        }
        if self.schema_version == 2:
            out["realization_profile_hash"] = self.realization_profile_hash
            out["execution_model_fingerprint_hash"] = (
                self.execution_model_fingerprint_hash
            )
        return out


def _validate_hash(value: object, what: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or not set(value) <= _HEX:
        raise PackageIntegrity(f"{what} hash is not lowercase 64-hex")
    return value


def _read_descriptor(package_path: Path) -> dict:
    try:
        raw = package_path.read_bytes()
    except FileNotFoundError as exc:
        raise PackageIntegrity("workflow-package.json is missing") from exc
    try:
        doc = json.loads(raw)
    except ValueError as exc:
        raise PackageIntegrity("workflow-package.json is malformed") from exc
    if not isinstance(doc, dict):
        raise PackageIntegrity("workflow-package.json is not an object")
    schema = doc.get("schema_version")
    if schema not in (1, 2):
        raise PackageIntegrity("descriptor schema_version must be 1 or 2")
    for field in ("workflow_id", "workflow_version", "manifest_hash",
                  "workflow_template_hash"):
        if field not in doc:
            raise PackageIntegrity(f"descriptor lacks {field}")
    if schema == 2 and (
        "realization_profile_hash" not in doc
        or "execution_model_fingerprint_hash" not in doc
    ):
        raise PackageIntegrity(
            "schema-2 descriptor lacks profile/fingerprint hashes"
        )
    if schema == 1 and (
        "realization_profile_hash" in doc
        or "execution_model_fingerprint_hash" in doc
    ):
        # Schema 1 cannot claim M9 semantics (§6.2).
        raise PackageIntegrity(
            "schema-1 descriptor declares M9 artifact hashes; schema 1 "
            "cannot claim M9 semantics"
        )
    return doc


async def capture_release(
    package_path: Path,
    manifest_path: Path,
    template_path: Path,
    profile_path: Path | None = None,
    fingerprint_path: Path | None = None,
) -> CapturedPackageRelease:
    """D1 → read each artifact ONCE → hash → require == D1 → D2 == D1.

    Hashing and parsing always use the SAME captured byte buffers
    (§23); a concurrent release switch yields complete BEFORE, complete
    AFTER, or incoherent — never a hybrid."""
    d1 = await asyncio.to_thread(_read_descriptor, package_path)

    async def _read(path: Path | None, what: str) -> bytes:
        if path is None:
            raise PackageIntegrity(f"{what} source path not supplied")
        try:
            return await asyncio.to_thread(path.read_bytes)
        except FileNotFoundError as exc:
            raise PackageIntegrity(f"{what} bytes are missing") from exc

    manifest_bytes = await _read(manifest_path, "manifest")
    template_bytes = await _read(template_path, "template")

    declared = {
        "manifest": _validate_hash(d1["manifest_hash"], "manifest"),
        "template": _validate_hash(
            d1["workflow_template_hash"], "template"
        ),
    }
    actual = {
        "manifest": hashlib.sha256(manifest_bytes).hexdigest(),
        "template": hashlib.sha256(template_bytes).hexdigest(),
    }

    profile_bytes = fingerprint_bytes = None
    if d1["schema_version"] == 2:
        if profile_path is None or fingerprint_path is None:
            raise PackageIntegrity(
                "schema-2 capture requires profile and fingerprint sources"
            )
        profile_bytes = await _read(
            profile_path, "realization-profile"
        )
        fingerprint_bytes = await _read(
            fingerprint_path, "execution-model-fingerprint"
        )
        declared["profile"] = _validate_hash(
            d1["realization_profile_hash"], "profile"
        )
        declared["fingerprint"] = _validate_hash(
            d1["execution_model_fingerprint_hash"], "fingerprint"
        )
        actual["profile"] = hashlib.sha256(profile_bytes).hexdigest()
        actual["fingerprint"] = hashlib.sha256(fingerprint_bytes).hexdigest()

    for kind in declared:
        if actual[kind] != declared[kind]:
            raise PackageIntegrity(
                f"captured {kind} bytes do not match the release declared "
                "by the descriptor"
            )

    d2 = await asyncio.to_thread(_read_descriptor, package_path)
    if d1 != d2:
        raise PackageIntegrity("descriptor changed during capture")

    return CapturedPackageRelease(
        schema_version=d1["schema_version"],
        workflow_id=d1["workflow_id"],
        workflow_version=d1["workflow_version"],
        manifest_hash=declared["manifest"],
        manifest_bytes=manifest_bytes,
        workflow_template_hash=declared["template"],
        template_bytes=template_bytes,
        realization_profile_hash=declared.get("profile"),
        profile_bytes=profile_bytes,
        execution_model_fingerprint_hash=declared.get("fingerprint"),
        fingerprint_bytes=fingerprint_bytes,
    )


@dataclass(frozen=True)
class ValidatedPackage:
    """Semantic view of a captured release after §24 validation."""

    release: CapturedPackageRelease
    manifest_v1: object | None
    manifest_v2: ManifestDocumentV2 | None
    profile: RealizationProfileDocument | None
    fingerprint: ExecutionModelFingerprintDocument | None
    template_graph: dict

    @property
    def is_schema2(self) -> bool:
        return self.release.schema_version == 2


def validate_package(release: CapturedPackageRelease) -> ValidatedPackage:
    """§24 semantic validation over the captured buffers: strict parses,
    profile↔manifest bijection, fingerprint↔template bindings, package
    cross-identity. Package validity is NOT M9 readiness."""
    from soloring.executors.comfy.bindings import (
        validate_manifest_template_bindings,
        validate_manifest_template_bindings_v2,
    )

    template_graph = json.loads(release.template_bytes.decode("utf-8"))
    manifest_v1 = manifest_v2 = None
    profile = fingerprint = None

    if release.schema_version == 1:
        manifest_v1 = parse_manifest(
            release.manifest_bytes.decode("utf-8")
        )
        validate_manifest_template_bindings(manifest_v1, template_graph)
    else:
        manifest_v2 = parse_manifest_v2(
            release.manifest_bytes.decode("utf-8")
        )
        profile = parse_profile(release.profile_bytes.decode("utf-8"))
        fingerprint = parse_fingerprint(
            release.fingerprint_bytes.decode("utf-8")
        )

        # Package cross-identity (§24): one workflow identity everywhere.
        for label, wf_id, wf_version in (
            ("manifest", manifest_v2.workflow_id, manifest_v2.version),
            ("profile", profile.workflow_id, profile.workflow_version),
            (
                "descriptor",
                release.workflow_id,
                release.workflow_version,
            ),
        ):
            if wf_id != release.workflow_id or wf_version != release.workflow_version:
                raise SoloRingError(
                    ErrorCode.REALIZATION_INPUT_BINDING_INVALID,
                    f"Package {label} workflow identity "
                    f"({wf_id} v{wf_version}) disagrees with the descriptor "
                    f"({release.workflow_id} "
                    f"v{release.workflow_version}).",
                    status_code=422,
                )

        # Profile model identity == fingerprint model identity (§7.2).
        if (
            profile.model.id != fingerprint.model_id
            or profile.model.version != fingerprint.model_version
        ):
            raise SoloRingError(
                ErrorCode.REALIZATION_INPUT_BINDING_INVALID,
                "RealizationProfile model identity disagrees with the "
                "ExecutionModelFingerprint model identity.",
                status_code=422,
            )

        # Fingerprint loader bindings exist in the captured template with
        # exact declared_name equality (§24 / §6.3).
        cross_validate_fingerprint_template(fingerprint, template_graph)

        # Profile ↔ manifest channel bijection (§7.5).
        _validate_profile_manifest_bijection(profile, manifest_v2)

        # Manifest-v2 structural node/field bindings against the template.
        validate_manifest_template_bindings_v2(manifest_v2, template_graph)

    return ValidatedPackage(
        release=release,
        manifest_v1=manifest_v1,
        manifest_v2=manifest_v2,
        profile=profile,
        fingerprint=fingerprint,
        template_graph=template_graph,
    )


def _validate_profile_manifest_bijection(
    profile: RealizationProfileDocument, manifest: ManifestDocumentV2
) -> None:
    from soloring.errors import ErrorCode

    def _invalid(message: str) -> SoloRingError:
        return SoloRingError(
            ErrorCode.REALIZATION_INPUT_BINDING_INVALID,
            message,
            status_code=422,
        )

    realization_inputs: dict[str, str] = {}  # input_key -> channel
    shot_reference_keys: set[str] = set()
    for input_key, decl in manifest.inputs.items():
        source = decl.source
        if source is None:
            continue
        if isinstance(source.kind, str):
            pass
        kind = getattr(source, "kind", None)
        if kind == "realization_channel":
            channel = source.channel
            if input_key in realization_inputs:
                raise _invalid(
                    f"Manifest input {input_key!r} claimed twice."
                )
            realization_inputs[input_key] = channel
        elif kind == "shot_reference":
            if input_key in shot_reference_keys:
                raise _invalid(
                    f"Manifest input {input_key!r} declared twice."
                )
            shot_reference_keys.add(input_key)

    profile_channels: dict[str, str] = {}  # channel -> input_key
    for channel_key, channel in profile.channels.items():
        if channel.input_key in profile_channels.values():
            raise _invalid(
                f"Two profile channels share input_key "
                f"{channel.input_key!r}."
            )
        profile_channels[channel_key] = channel.input_key

    for channel_key, input_key in profile_channels.items():
        if realization_inputs.get(input_key) != channel_key:
            raise _invalid(
                f"Profile channel {channel_key!r} has no matching manifest "
                f"realization_channel declaration for input "
                f"{input_key!r}."
            )
    for input_key, channel in realization_inputs.items():
        if profile_channels.get(channel) != input_key:
            raise _invalid(
                f"Manifest realization input {input_key!r} (channel "
                f"{channel!r}) has no matching profile channel."
            )

    # Profile parameter overrides must name real manifest parameters (§9.1).
    for name in profile.parameter_overrides:
        if name not in manifest.parameters:
            raise _invalid(
                f"Profile parameter override {name!r} is not a manifest "
                "parameter."
            )
