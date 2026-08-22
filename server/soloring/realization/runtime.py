"""M9 runtime compatibility (frozen plan §26, §76).

Pure comparison of a captured ExecutionModelFingerprint's runtime
requirements against the live deployment capability record, plus the
worker-side schema-2 historical validation helpers. Live-executor
compatibility only — never historical identity.
"""

from __future__ import annotations

from soloring.errors import ErrorCode, SoloRingError
from soloring.realization.fingerprint import (
    ExecutionModelFingerprintDocument,
)
from soloring.realization.model_roots import ModelIncompatible


def check_runtime_compatibility(
    fingerprint: ExecutionModelFingerprintDocument, attestation
) -> None:
    """§26.2: the live deployment attestation (v4) must satisfy the
    frozen stable runtime requirements — exact ComfyUI commit, exact
    required custom-node commits (the characterized deployment binds
    ComfyUI-GGUF via gguf_commit), exact custom-node policy. Any
    difference is EXECUTION_MODEL_INCOMPATIBLE before submission."""
    rr = fingerprint.runtime_requirements

    def _fail(what: str):
        raise ModelIncompatible(
            f"Live deployment does not satisfy the captured "
            f"ExecutionModelFingerprint: {what}"
        )

    if getattr(attestation, "comfyui_commit", None) != rr.comfyui_commit:
        _fail(
            f"ComfyUI commit {getattr(attestation, 'comfyui_commit', None)!r}"
            f" != required {rr.comfyui_commit!r}"
        )
    for name, required_commit in rr.custom_nodes.items():
        if name != "ComfyUI-GGUF":
            _fail(
                f"required custom node {name!r} has no characterized "
                "attestation binding"
            )
        actual = getattr(attestation, "gguf_commit", None)
        if actual != required_commit:
            _fail(
                f"custom node {name!r} commit {actual!r} != required "
                f"{required_commit!r}"
            )
    live_whitelist = tuple(getattr(attestation, "custom_node_policy", ()) or ())
    if list(live_whitelist) != list(rr.custom_node_policy.whitelist):
        _fail("custom-node whitelist differs from the captured requirement")


def verify_attested_process_live(attestation, settings) -> None:
    """§26.2 (B4): the attested process must STILL be the process serving
    the configured executor origin — the M5B stale-attestation defense
    (pid + process-start fingerprint vs the port listener). Failure is
    EXECUTION_MODEL_INCOMPATIBLE: the attested runtime is not the live
    one."""
    from urllib.parse import urlparse

    from soloring.executors.comfy.capability_record import verify_live_process

    base = getattr(settings, "comfy_base_url", None) or ""
    port = urlparse(base).port or (443 if "https" in base else 80)
    if not verify_live_process(attestation, port=port):
        raise ModelIncompatible(
            "The attested deployment process is not the live process "
            f"serving {base or 'the configured executor origin'}; stale "
            "attestation."
        )


def load_live_attestation(settings):
    """Load the live v4 deployment attestation; for schema-2 execution an
    unavailable/invalid attestation is EXECUTION_MODEL_INCOMPATIBLE."""
    from soloring.executors.comfy.capability_record import (
        CapabilityRecordInvalid,
        load_deployment_attestation,
    )

    try:
        return load_deployment_attestation(settings.data_dir)
    except (CapabilityRecordInvalid, FileNotFoundError) as exc:
        raise ModelIncompatible(
            f"No valid live deployment attestation is available: {exc}"
        ) from exc


def validate_schema2_historical_state(
    *,
    spec: dict,
    generation_model: str | None,
    generation_model_version: str | None,
    profile,
    fingerprint: ExecutionModelFingerprintDocument,
    input_rows: list,
) -> None:
    """§18.2/§32 worker-side historical cross-validation: spec model
    identity == Generation columns == profile model; realization input
    rows project the captured RealizationSpec exactly (contiguous,
    ordered, no extras). Violations are corruption, not compatibility."""

    def _corrupt(message: str) -> SoloRingError:
        return SoloRingError(
            ErrorCode.INTERNAL_INVARIANT_VIOLATION, message, status_code=500
        )

    model = spec.get("model") or {}
    realization = spec.get("realization") or {}
    if model.get("id") != generation_model or model.get(
        "version"
    ) != generation_model_version:
        raise _corrupt(
            "Generation model columns disagree with the schema-2 spec."
        )
    if profile.model.id != model.get("id") or profile.model.version != model.get(
        "version"
    ):
        raise _corrupt(
            "Historical profile model identity disagrees with the spec."
        )
    if fingerprint.model_id != profile.model.id or (
        fingerprint.model_version != profile.model.version
    ):
        raise _corrupt(
            "Historical fingerprint model identity disagrees with the "
            "profile."
        )
    if realization.get("profile", {}).get("hash") is None or model.get(
        "execution_model_fingerprint_hash"
    ) is None:
        raise _corrupt("Schema-2 spec lacks captured profile/model identity.")

    expected: dict[str, list[tuple[int, str, str, str]]] = {}
    for channel in realization.get("channels", []):
        for b in channel["bindings"]:
            expected.setdefault(channel["input_key"], []).append(
                (
                    b["binding_position"],
                    b["item"]["asset_id"],
                    b["item"]["blob_hash"],
                    b["item"]["role"],
                )
            )
    for key in expected:
        expected[key].sort()

    # §19: legacy shot_reference rows on OTHER input keys legally coexist
    # with realization rows; only the realization projection is compared.
    realization_keys = set(expected)
    actual: dict[str, list[tuple[int, str, str, str]]] = {}
    for row in input_rows:
        if row.input_key not in realization_keys:
            continue
        actual.setdefault(row.input_key, []).append(
            (row.position, row.asset_id, row.blob_hash, row.reference_role)
        )
    for key in actual:
        actual[key].sort()

    if expected != actual:
        raise _corrupt(
            "Persisted realization-backed GenerationInputs disagree with "
            "the captured RealizationSpec."
        )
    for key, rows in expected.items():
        positions = sorted(p for p, *_ in rows)
        if positions != list(range(len(rows))):
            raise _corrupt(
                f"Realization input positions for {key!r} are not "
                "zero-based contiguous."
            )
