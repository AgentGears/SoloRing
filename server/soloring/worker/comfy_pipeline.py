"""Full Comfy execution pipeline (M5A-10 aggregate).

Composes M5A-2..9 into ONE lifecycle the worker dispatches for a persisted
``executor == "comfy"`` Generation:

    retrieve historical artifacts by CAPTURED hash (never installed files)
    → materialize inputs (attempt namespace, streamed, verified)
    → translate (pure; historical manifest + template + captured spec)
    → durable submission protocol (artifact → possible → ONE POST or rediscover)
    → observe to terminal (targeted history authority, cancellation-first)
    → resolve outputs (captured contract + historical bindings)
    → /view streamed to deterministic output_key staging
    → existing M3C-hardened importer (publication authority)
    → succeeded

Layering (M5 amendment §3): this module is worker orchestration above the
executor adapter — it owns lifecycle/fenced writes and composes the DB-free
Comfy package plus the M5A-1/6/8 durable protocols. Soft Cancel short-circuits
BEFORE any /view call: zero publication. The FakeExecutor path
(worker/execution.py) never enters this module.

No DB session spans a network call: every fenced transition owns its own
transaction (ownership.py), reads use short-lived connections.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from soloring.assets.blob_store import BlobStore
from soloring.errors import ErrorCode, SoloRingError
from soloring.executors.base import StagedOutput
from soloring.executors.comfy.capabilities import (
    CancellationCapability,
    CancellationMode,
)
from soloring.executors.comfy.bindings import validate_manifest_template_bindings
from soloring.executors.comfy.client import ComfyAPIError, ComfyClient
from soloring.executors.comfy.input_materializer import (
    CapturedInput,
    ComfyInputMaterializer,
    HttpInputMaterializer,
)
from soloring.executors.comfy.observe import (
    DisappearanceTracker,
    PromptObservation,
    observe_prompt,
)
from soloring.executors.comfy.outputs import (
    DEFAULT_MAX_OUTPUT_BYTES,
    CapturedOutputContract,
    fetch_output_to_staging,
    resolve_comfy_outputs,
)
from soloring.executors.comfy.translate import build_comfy_prompt
from soloring.generation.importer import import_staged_outputs
from soloring.generation.repository import get_generation_full, list_generation_inputs
from soloring.settings import Settings
from soloring.worker.comfy_cancellation import reconcile_cancellation
from soloring.worker.comfy_submission import run_comfy_submission
from soloring.worker.execution import spec_outputs
from soloring.worker.ownership import (
    OwnershipMutationResult,
    read_cancellation_intent,
    transition_owned_generation,
    update_owned_generation_progress,
)
from soloring.workflows.artifact_store import WorkflowArtifactStore
from soloring.workflows.manifest import parse_manifest

log = logging.getLogger("soloring.worker.comfy_pipeline")

# Pre-M5B-7 default (50 ms) caused a ~32 req/s busy loop on recovery paths;
# production cadence comes from Settings.comfy_observation_poll_seconds.
POLL_INTERVAL = 0.05  # explicit per-call override for tests only

# Conservative default capability: running-cancellation is not provably safe
# on an uncharacterized deployment, so decide_cancellation degrades to Soft
# Cancel (M5A-8 §3). M5B may upgrade this from live evidence.
SOFT_ONLY_CAPABILITY = CancellationCapability(
    mode=CancellationMode.SOFT_ONLY, retry_safety="unknown",
)

_TERMINAL = ("succeeded", "failed", "cancelled")


async def resolve_capability(
    settings: Settings, client: ComfyClient | None = None,
) -> CancellationCapability:
    """The deployment's running-cancellation capability (M5B-5/M5B-7).

    soft_only is the conservative default. targeted engages ONLY when the
    versioned characterization record, the launcher's deployment
    attestation, and the live executor AGREE on the exact fingerprint:

      * record contract v1 valid (shared capability_record module);
      * local attestation exists and its comfyui_commit + gguf_commit are
        EXACTLY the characterized ones — same version with a different
        commit is drift and fails closed;
      * the live /system_stats version equals the characterized version.

    Any miss — missing/incomplete record, missing/stale attestation,
    commit drift, version drift, unreachable probe — logs loudly and
    fails closed to SOFT_ONLY. SAFE_SINGLE_FLIGHT remains unreachable by
    design (no mechanical global interlock in v0.1).
    """
    if settings.comfy_cancellation_mode != "targeted":
        return SOFT_ONLY_CAPABILITY
    from pathlib import Path as _Path

    from soloring.executors.comfy.capability_record import (
        CapabilityRecordInvalid,
        load_capability_record,
        load_deployment_attestation,
    )

    def _closed(reason: str) -> CancellationCapability:
        log.error("CAPABILITY FAIL-CLOSED: %s — using SOFT_ONLY", reason)
        return SOFT_ONLY_CAPABILITY

    try:
        record = load_capability_record(_Path(settings.data_dir))
    except CapabilityRecordInvalid as exc:
        return _closed(f"characterization record: {exc}")
    try:
        attestation = load_deployment_attestation(_Path(settings.data_dir))
    except CapabilityRecordInvalid as exc:
        return _closed(f"deployment attestation: {exc}")
    if not record.matches_attestation(attestation):
        return _closed(
            "executor revision drift: characterized "
            f"comfy={record.comfyui_commit[:12]}/"
            f"gguf={record.gguf_commit[:12]} != attested "
            f"comfy={attestation.comfyui_commit[:12]}/"
            f"gguf={attestation.gguf_commit[:12]}"
        )
    if client is None:
        # No unsafe bypass (final-verification patch F3): the live checks
        # are mandatory for targeted resolution.
        return _closed("no live client supplied for the capability probe")
    from soloring.executors.comfy import wire as _wire

    try:
        raw = await client.system_stats()
        live_version = _wire.normalize_system_response(raw).version
    except Exception as exc:  # noqa: BLE001
        return _closed(f"live version probe failed: {exc}")
    if live_version != record.comfyui_version:
        return _closed(
            f"executor version drift: live {live_version!r} != "
            f"characterized {record.comfyui_version!r}"
        )
    # The attested executor must be THE executor this client targets
    # (final-verification patch 3): origin equality — not merely the same
    # port on some other host — plus v0.1's local-only loopback policy.
    from soloring.executors.comfy.capability_record import (
        is_loopback_origin,
        normalize_origin,
    )

    client_origin = normalize_origin(client._base)
    if not is_loopback_origin(client._base):
        return _closed(
            f"client origin {client_origin!r} is not loopback — v0.1 "
            "targeted cancellation is local-only"
        )
    if client_origin != attestation.executor_origin:
        return _closed(
            f"client origin {client_origin!r} != attested executor origin "
            f"{attestation.executor_origin!r}"
        )
    port = int(attestation.executor_origin.rsplit(":", 1)[1])
    from soloring.executors.comfy.capability_record import verify_live_process

    import asyncio as _aio

    if not await _aio.to_thread(verify_live_process, attestation, port):
        return _closed(
            "attested process no longer serves the executor port "
            f"(pid {attestation.pid}) — stale attestation"
        )
    return CancellationCapability(
        mode=CancellationMode.TARGETED,
        targeting_key=record.targeting_key,
        uniqueness_guarantee=record.uniqueness_guarantee,
        retry_safety=record.retry_safety,
    )


def _load_verified_schema3_workflow_spec(generation) -> dict:
    """One production seam for the stored schema-3 WorkflowSpec (E-080
    cells 18/19/20): parse the stored BYTES (malformed JSON fails
    closed), verify the canonical hash, and verify the stored bytes ARE
    canonical — a reordered/pretty-printed document is historical
    corruption, not an accepted equivalence."""
    import json as _json

    from soloring.domain.canonical import (
        canonical_hash as _spec_hash,
        canonical_json_str as _spec_canonical,
    )
    from soloring.errors import internal_invariant

    try:
        spec = _json.loads(generation.workflow_spec_json)
    except ValueError as exc:
        raise internal_invariant(
            f"Stored schema-3 workflow spec bytes are not valid JSON: "
            f"{exc}") from exc
    if _spec_hash(spec) != generation.workflow_spec_hash:
        raise internal_invariant(
            "Stored schema-3 workflow spec bytes disagree with the "
            "persisted workflow_spec_hash."
        )
    if _spec_canonical(spec) != generation.workflow_spec_json:
        raise internal_invariant(
            "Stored schema-3 workflow spec bytes are not canonical."
        )
    return spec


def _verify_schema3_stored_spec_canonical(spec: dict,
                                           stored_json: str) -> None:
    """E-106 B3a / corruption cell 20: the stored schema-3 WorkflowSpec
    BYTES must be canonical — semantic hash equality alone would accept a
    reordered/pretty-printed document as history."""
    from soloring.domain.canonical import canonical_json_str

    if canonical_json_str(spec) != stored_json:
        raise SoloRingError(
            ErrorCode.INTERNAL_INVARIANT_VIOLATION,
            "Stored schema-3 workflow spec bytes are not canonical.",
            status_code=500,
        )


def verify_schema3_runtime_environment(fingerprint_doc: dict,
                                       settings) -> None:
    """R3 §18 / E-106 B2: validate the CAPTURED schema-3
    ExecutionModelFingerprint against the ACTUAL execution environment:
    the live v4 deployment attestation proves the serving-process
    identity (pid + process-start fingerprint on the configured origin)
    and carries the launched ComfyUI commit + the whitelisted custom-node
    commit; the M10 fingerprint's artifact list is live-verified by
    streaming SHA-256 against the configured model roots. Failure is
    EXECUTION_MODEL_INCOMPATIBLE before any upload or submission. This
    NEVER compares against application constants — only captured identity
    vs live process/bytes."""
    from soloring.realization.model_roots import verify_live_model_bytes
    from soloring.realization.runtime import (
        load_live_attestation,
        verify_attested_process_live,
    )

    rr = fingerprint_doc.get("m10_spatial_runtime") or {}
    # The required custom-node IDENTITY is derived from the CAPTURED
    # runtime requirement — both the whitelisted NAME and the COMMIT must
    # match the attested deployment (a correct commit attached to the
    # wrong node is a wrong executable extension set).
    required_nodes = rr.get("custom_nodes") or {}
    if len(required_nodes) != 1:
        raise SoloRingError(
            ErrorCode.EXECUTION_MODEL_INCOMPATIBLE,
            f"The captured fingerprint requires {len(required_nodes)} "
            "custom nodes; the v4 single-node deployment attestation "
            "cannot close that requirement set.",
            status_code=503,
        )
    required_name, required_commit = next(iter(required_nodes.items()))
    attestation = load_live_attestation(
        settings, expected_whitelist=(required_name,))
    if attestation.comfyui_commit != rr.get("comfyui_commit"):
        raise SoloRingError(
            ErrorCode.EXECUTION_MODEL_INCOMPATIBLE,
            f"Live executor ComfyUI commit {attestation.comfyui_commit} "
            f"disagrees with the captured fingerprint "
            f"{rr.get('comfyui_commit')}.",
            status_code=503,
        )
    if attestation.gguf_commit != required_commit:
        raise SoloRingError(
            ErrorCode.EXECUTION_MODEL_INCOMPATIBLE,
            f"Live executor custom-node {required_name!r} commit "
            f"{attestation.gguf_commit} disagrees with the captured pin "
            f"{required_commit}.",
            status_code=503,
        )
    verify_attested_process_live(attestation, settings)
    artifacts = rr.get("artifacts") or []
    if artifacts:
        verify_live_model_bytes(settings, [
            (a["artifact_key"], a["storage_root_key"], a["declared_name"],
             a["sha256"])
            for a in artifacts
        ])


async def drive_comfy_generation(
    engine: AsyncEngine,
    settings: Settings,
    worker_id: str,
    generation_id: str,
    attempt_id: str,
    client: ComfyClient,
    *,
    materializer: ComfyInputMaterializer | None = None,
    capability: CancellationCapability | None = None,
    submission_grace_seconds: float = 5.0,
    disappearance_grace_seconds: float = 5.0,
    outage_grace_seconds: float = 30.0,
    poll_interval: float | None = None,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
) -> str:
    """Drive one claimed/adopted comfy Generation to a terminal status.

    Recovery-aware end to end: the submission protocol resolves durable state
    first, so a successor that adopts mid-flight REDISCOVERS (never re-POSTs)
    and idempotently re-confirms the persisted prompt identity.

    ``outage_grace_seconds`` (M5B-6): a TRANSIENT read outage shorter than
    the window never terminates the drive — the executor being unreachable
    is an availability problem, not evidence about the prompt, and the job
    keeps running remotely. Only once the outage exceeds the window does
    the drive classify interruption (EXECUTOR_UNAVAILABLE). Conclusive
    absence from a REACHABLE executor remains governed by the separate
    disappearance grace.
    """
    if poll_interval is None:
        poll_interval = settings.comfy_observation_poll_seconds
    if capability is None:
        capability = await resolve_capability(settings, client)
    try:
        return await _drive(
            engine, settings, worker_id, generation_id, attempt_id, client,
            materializer=materializer, capability=capability,
            submission_grace_seconds=submission_grace_seconds,
            disappearance_grace_seconds=disappearance_grace_seconds,
            outage_grace_seconds=outage_grace_seconds,
            poll_interval=poll_interval, max_output_bytes=max_output_bytes,
        )
    except SoloRingError as exc:
        # Stable error envelope through the worker boundary: domain failures
        # land as a fenced terminal transition carrying their durable code.
        r = await transition_owned_generation(
            engine, worker_id, generation_id, "failed",
            error_code=exc.code, error_message=str(exc),
        )
        if r is OwnershipMutationResult.OK:
            return "failed"
        raise  # authority lost: the successor owns the decision
    except ComfyAPIError as exc:
        # Executor-side outage mid-flight is interruption-class, not creative
        # failure: nothing about the request was proven invalid.
        r = await transition_owned_generation(
            engine, worker_id, generation_id, "interrupted",
            error_code=ErrorCode.EXECUTOR_UNAVAILABLE, error_message=str(exc),
        )
        if r is OwnershipMutationResult.OK:
            return "interrupted"
        raise
    except Exception as exc:  # noqa: BLE001 — envelope discipline for the rest
        log.exception("comfy pipeline invariant failure for %s", generation_id)
        r = await transition_owned_generation(
            engine, worker_id, generation_id, "failed",
            error_code=ErrorCode.INTERNAL_INVARIANT_VIOLATION,
            error_message=str(exc)[:500],
        )
        if r is OwnershipMutationResult.OK:
            return "failed"
        raise


async def _drive(
    engine: AsyncEngine,
    settings: Settings,
    worker_id: str,
    generation_id: str,
    attempt_id: str,
    client: ComfyClient,
    *,
    materializer: ComfyInputMaterializer | None,
    capability: CancellationCapability,
    submission_grace_seconds: float,
    disappearance_grace_seconds: float,
    outage_grace_seconds: float,
    poll_interval: float,
    max_output_bytes: int,
) -> str:
    factory = async_sessionmaker(bind=engine, expire_on_commit=False,
                                 class_=AsyncSession)
    blob_store = BlobStore(settings)
    artifact_store = WorkflowArtifactStore(settings)

    async with factory() as session:
        generation = await get_generation_full(session, generation_id)

    if generation.executor != "comfy":  # dispatch bug, never creative state
        raise SoloRingError(
            ErrorCode.INTERNAL_INVARIANT_VIOLATION,
            f"comfy pipeline invoked for executor={generation.executor!r}",
            status_code=500,
        )

    spec = json.loads(generation.workflow_spec_json)
    outputs = spec_outputs(spec)

    # 0) DURABLE SUBMISSION STATE FIRST (audit F12): a successor must never
    # do submission prework (artifact reads, blob verification, remote
    # uploads, translation) before learning whether the durable protocol
    # even allows a submission from this frame. Recovery that cannot
    # re-upload must still be able to observe a confirmed prompt to
    # terminal; only not_started may consume the permit.
    state = await _current_submission_state(engine, generation_id, worker_id)
    if state is None:
        raise SoloRingError(
            ErrorCode.GENERATION_OWNERSHIP_LOST,
            f"generation not owned by {worker_id}",
            status_code=500,
        )

    prompt_id: str | None = None

    if state == "uncertain":
        # Permanently ineligible for automatic resubmission. Terminalize if
        # the crash happened before the terminal write landed.
        status = await _current_status(engine, generation_id)
        if status in _TERMINAL:
            return status
        _require_ok(
            await transition_owned_generation(
                engine, worker_id, generation_id, "interrupted",
                error_code=ErrorCode.EXECUTOR_SUBMISSION_UNCERTAIN,
                error_message=(
                    "submission ambiguity unresolved after bounded "
                    "rediscovery; attempt permanently ineligible for "
                    "automatic resubmission"
                ),
            ),
            generation_id,
        )
        return "interrupted"

    elif state == "confirmed":
        # Adopt the persisted prompt identity; observe to terminal. No
        # prework: the remote already has the prompt.
        prompt_id = generation.executor_job_id
        if not prompt_id:
            raise SoloRingError(
                ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                "confirmed submission state without an executor_job_id",
                status_code=500,
            )

    else:  # not_started (fresh claim) | submission_possible (permit consumed)
        if state == "not_started":
            # 1) Historical artifacts by CAPTURED hash — never installed
            # files.
            manifest_bytes = await artifact_store.get_manifest(
                generation.manifest_hash
            )
            template_bytes = await artifact_store.get_template(
                generation.workflow_template_hash
            )
            template_graph = json.loads(template_bytes.decode("utf-8"))
            schema3_derived = None
            schema2_pending = None
            schema3_lower = None
            # M10F PD-1B (R6 §10.2.1): historical dispatch is keyed by the
            # pair (retained manifest schema, logical WorkflowSpec schema)
            # — never by the logical schema alone. A logical v1/v2
            # Generation may retain a schema-3 package.
            retained_manifest_schema = None
            try:
                retained_manifest_schema = json.loads(
                    manifest_bytes.decode("utf-8")).get("schema_version")
            except ValueError:
                retained_manifest_schema = None
            if (retained_manifest_schema == "3"
                    and spec.get("schema_version") in (1, 2)):
                from soloring.spatial.package3 import (
                    check_runtime_closure,
                    parse_manifest_v3,
                    parse_profile_v2,
                    project_lower_logical_execution_view,
                )

                manifest_v3_doc = parse_manifest_v3(
                    manifest_bytes.decode("utf-8"))
                lower = project_lower_logical_execution_view(
                    manifest_v3_doc, template_graph,
                    generation.manifest_hash,
                    generation.workflow_template_hash,
                    logical_schema_version=spec["schema_version"],
                )
                if spec["schema_version"] == 2:
                    # §10.2.1.3: full retained-package structural checks…
                    profile = parse_profile_v2(
                        (await artifact_store.get_profile(
                            spec["realization"]["profile"]["hash"]
                        )).decode("utf-8"))
                    fingerprint_doc = json.loads(
                        (await artifact_store.get_fingerprint(
                            spec["model"][
                                "execution_model_fingerprint_hash"]
                        )).decode("utf-8"))
                    unproven = check_runtime_closure(
                        profile["spatial"], fingerprint=fingerprint_doc,
                        template=template_graph)
                    if unproven:
                        raise internal_invariant(
                            "Schema-3 profile runtime requirements not "
                            "closed by captured fingerprint/template: "
                            f"{unproven}")
                    # …but live execution availability follows the
                    # PROJECTED graph: only fingerprint artifacts whose
                    # captured (node, field) loader binding survives the
                    # projection are live-verified (the removed depth
                    # ControlNet is not an execution-time requirement).
                    surviving = [
                        a for a in (
                            fingerprint_doc.get("m10_spatial_runtime")
                            or {}).get("artifacts", [])
                        if a.get("node") in lower.template
                    ]
                    verify_schema3_runtime_environment(
                        {**fingerprint_doc,
                         "m10_spatial_runtime": {
                             **(fingerprint_doc.get("m10_spatial_runtime")
                                or {}),
                             "artifacts": surviving,
                         }}, settings)
                manifest = lower.manifest
                template_graph = json.loads(json.dumps(lower.template))
                schema3_lower = lower
            elif spec.get("schema_version") == 3:
                # M10 frozen r3 §2.2/§48: schema-3 historical execution
                # reads captured state ONLY. The v3 manifest/profile/
                # fingerprint artifacts are retrieved by CAPTURED hash,
                # runtime closure is proven against them, and derived
                # spatial inputs are verified + uploaded from the exact
                # retained physical Blob bytes. Zero current-M10 reads.
                from soloring.domain.canonical import (
                    canonical_hash as _spec_hash,
                )
                from soloring.errors import internal_invariant
                from soloring.spatial.package3 import (
                    check_runtime_closure,
                    parse_manifest_v3,
                    parse_profile_v2,
                )
                from soloring.spatial.worker_inputs import (
                    execute_schema3_derived_inputs,
                )

                # E-080 cells 18/19/20 through ONE production seam: parse
                # stored bytes, verify canonical hash, verify stored bytes
                # ARE canonical.
                spec = _load_verified_schema3_workflow_spec(generation)
                manifest = parse_manifest_v3(
                    manifest_bytes.decode("utf-8")
                )
                profile = parse_profile_v2(
                    (
                        await artifact_store.get_profile(
                            spec["spatial_realization"][
                                "realization_profile_hash"
                            ]
                        )
                    ).decode("utf-8")
                )
                fingerprint_doc = json.loads(
                    (
                        await artifact_store.get_fingerprint(
                            spec["model"][
                                "execution_model_fingerprint_hash"
                            ]
                        )
                    ).decode("utf-8")
                )
                unproven = check_runtime_closure(
                    profile["spatial"], fingerprint=fingerprint_doc,
                    template=template_graph)
                if unproven:
                    raise internal_invariant(
                        "Schema-3 profile runtime requirements not closed "
                        f"by captured fingerprint/template: {unproven}"
                    )
                # R3 §18 / E-106 B2: the CAPTURED ExecutionModelFingerprint
                # must be validated against the ACTUAL execution
                # environment before any upload/submission — live
                # deployment attestation (serving-process identity +
                # ComfyUI/WanVideoWrapper commits) plus live model-byte
                # verification. Never a comparison against application
                # constants.
                verify_schema3_runtime_environment(
                    fingerprint_doc, settings)
                async with factory() as session:
                    schema3_derived = await execute_schema3_derived_inputs(
                        session, blob_store,
                        generation_id=generation_id,
                        attempt_id=attempt_id,
                        workflow_spec=spec,
                        manifest_v3=manifest,
                        client=ClientUploader(client),
                    )
            elif spec.get("schema_version") == 2:
                from soloring.domain.canonical import (
                    canonical_hash as _spec_hash,
                )
                from soloring.errors import internal_invariant

                if _spec_hash(spec) != generation.workflow_spec_hash:
                    raise internal_invariant(
                        "Stored schema-2 workflow spec bytes disagree with "
                        "the persisted workflow_spec_hash."
                    )
                # M9 §26/§51: schema-2 historical validation — the v2
                # manifest, captured profile, and ExecutionModelFingerprint
                # are retrieved by CAPTURED hash and cross-validated; the
                # live attestation + live model bytes are verified on
                # EVERY submission attempt (§6.4.1). Current installed
                # package/profile/M8 state is never consulted.
                from soloring.executors.comfy.bindings import (
                    validate_manifest_template_bindings_v2,
                )
                from soloring.realization.fingerprint import (
                    cross_validate_fingerprint_template,
                    parse_fingerprint,
                )
                from soloring.realization.profile import parse_profile
                from soloring.realization.runtime import (
                    check_runtime_compatibility,
                    load_live_attestation,
                    validate_schema2_historical_state,
                )
                from soloring.realization.model_roots import (
                    verify_live_model_bytes,
                )
                from soloring.workflows.manifest import parse_manifest_v2

                manifest = parse_manifest_v2(
                    manifest_bytes.decode("utf-8")
                )
                validate_manifest_template_bindings_v2(
                    manifest, template_graph
                )
                profile = parse_profile(
                    (
                        await artifact_store.get_profile(
                            spec["realization"]["profile"]["hash"]
                        )
                    ).decode("utf-8")
                )
                fingerprint = parse_fingerprint(
                    (
                        await artifact_store.get_fingerprint(
                            spec["model"][
                                "execution_model_fingerprint_hash"
                            ]
                        )
                    ).decode("utf-8")
                )
                cross_validate_fingerprint_template(
                    fingerprint, template_graph
                )
                from soloring.realization.runtime import (
                    verify_attested_process_live,
                )

                _attestation = load_live_attestation(settings)
                check_runtime_compatibility(fingerprint, _attestation)
                verify_attested_process_live(_attestation, settings)
                verify_live_model_bytes(
                    settings,
                    [
                        (
                            a.artifact_key,
                            a.storage_root_key,
                            a.declared_name,
                            a.sha256,
                        )
                        for a in fingerprint.artifacts
                    ],
                )
                schema2_pending = {
                    "profile": profile,
                    "fingerprint": fingerprint,
                }
            else:
                manifest = parse_manifest(manifest_bytes.decode("utf-8"))
                schema2_pending = None
                # Corruption/parser-drift defense (audit F10): the
                # historical pair is re-validated before translation
                # consumes it.
                validate_manifest_template_bindings(manifest, template_graph)

            # 2) Materialize captured inputs (attempt namespace; streamed;
            # verified).
            async with factory() as session:
                input_rows = await list_generation_inputs(
                    session, generation_id
                )
            if schema2_pending is not None:
                from soloring.realization.runtime import (
                    validate_schema2_historical_state as _validate,
                )

                _validate(
                    spec=spec,
                    generation_model=generation.model,
                    generation_model_version=generation.model_version,
                    profile=schema2_pending["profile"],
                    fingerprint=schema2_pending["fingerprint"],
                    input_rows=input_rows,
                )
            captured = [
                CapturedInput(
                    input_key=i.input_key, position=i.position,
                    asset_id=i.asset_id, blob_hash=i.blob_hash,
                )
                for i in input_rows
            ]
            if materializer is None:
                materializer = HttpInputMaterializer(
                    ClientUploader(client), blob_store.path_for_hash,
                    retry_convergent=False,
                )
            outcome = await materializer.materialize(
                generation_id=generation_id, attempt_id=attempt_id,
                inputs=captured,
            )

            # 3) Pure translation from the captured triple. For schema 3
            # the verified/uploaded derived references (schema3_derived)
            # are part of the pure translation input — bound at the exact
            # captured manifest-v3 node/field (M10E §17.2: the M10A
            # baseline computed them but never fed them into translation).
            payload = build_comfy_prompt(
                workflow_spec=spec, manifest=manifest,
                template=template_graph,
                materialized=outcome.materialized,
                generation_id=generation_id, attempt_id=attempt_id,
                client_id=worker_id,
                schema3_derived=schema3_derived,
            )
            payload_document = payload.to_document()
        else:
            # submission_possible: the permit was durably consumed by a
            # crashed predecessor — this frame is REDISCOVER_ONLY and needs
            # NO payload (the artifact is already persisted).
            payload_document = None

        # 4-6) Durable submission protocol: artifact → possible → ONE POST
        # or bounded rediscovery. Returns "" when the attempt resolved
        # uncertain.
        prompt_id = await run_comfy_submission(
            engine, settings, worker_id, generation_id, attempt_id,
            payload_document, client,
            grace_seconds=submission_grace_seconds,
        )
        if prompt_id == "":
            _require_ok(
                await transition_owned_generation(
                    engine, worker_id, generation_id, "interrupted",
                    error_code=ErrorCode.EXECUTOR_SUBMISSION_UNCERTAIN,
                    error_message=(
                        "submission ambiguity unresolved after bounded "
                        "rediscovery; attempt permanently ineligible for "
                        "automatic resubmission"
                    ),
                ),
                generation_id,
            )
            return "interrupted"

    assert prompt_id

    # 7) Lifecycle: preparing → submitted only on a FRESH claim; an adopted
    # row is already mid-flight and keeps its timestamps.
    if await _current_status(engine, generation_id) == "preparing":
        _require_ok(
            await transition_owned_generation(
                engine, worker_id, generation_id, "submitted", started=True,
            ),
            generation_id,
        )

    # 8) Observe to terminal — cancellation intent checked BEFORE each
    # observation so a persisted request is reconciled promptly (§72-§73).
    tracker = DisappearanceTracker(grace_seconds=disappearance_grace_seconds)
    terminal: PromptObservation | None = None
    last_signature = None
    outage_deadline: float | None = None  # M5B-6 transient-outage window
    while terminal is None:
        if await read_cancellation_intent(engine, generation_id):
            outcome_r = await reconcile_cancellation(
                engine, worker_id, generation_id, attempt_id, prompt_id,
                client, capability, tracker,
            )
            if outcome_r == "cancelled":
                return "cancelled"
            if outcome_r == "interrupted":
                return "interrupted"
            if outcome_r in _TERMINAL:
                # Remote terminal won the race (§11): normal semantics.
                terminal = PromptObservation(state=outcome_r)
                break
            # soft_cancel_selected | ambiguous → observe on; the next pass
            # re-reconciles with the SAME persisted prompt_id.
        else:
            try:
                obs = await observe_prompt(
                    client, prompt_id=prompt_id, generation_id=generation_id,
                    attempt_id=attempt_id, disappearance=tracker,
                )
                outage_deadline = None  # reachable: the window resets
            except ComfyAPIError:
                # Transient read outage (M5B-6): unreachability is an
                # availability fact, never prompt evidence. The disappearance
                # tracker is NOT advanced (no absence was observed), and the
                # drive keeps retrying until the outage window expires.
                now = time.monotonic()
                if outage_deadline is None:
                    outage_deadline = now + outage_grace_seconds
                elif now >= outage_deadline:
                    _require_ok(
                        await transition_owned_generation(
                            engine, worker_id, generation_id, "interrupted",
                            error_code=ErrorCode.EXECUTOR_UNAVAILABLE,
                            error_message=(
                                f"executor unreachable for over "
                                f"{outage_grace_seconds}s during observation"
                            ),
                        ),
                        generation_id,
                    )
                    return "interrupted"
                log.warning(
                    "comfy observation unreachable (outage window %.0fs "
                    "left) for %s",
                    outage_deadline - now, generation_id,
                )
                await asyncio.sleep(poll_interval)
                continue
            if obs.state in _TERMINAL:
                terminal = obs
                break
            if obs.state == "lost":
                _require_ok(
                    await transition_owned_generation(
                        engine, worker_id, generation_id, "interrupted",
                        error_code=ErrorCode.EXECUTOR_JOB_LOST,
                        error_message=obs.detail or "COMFY_JOB_LOST",
                    ),
                    generation_id,
                )
                return "interrupted"
            if obs.progress is not None and obs.progress.current is not None:
                signature = (
                    obs.progress.current, obs.progress.total, obs.progress.node,
                )
                if signature != last_signature:
                    r = await update_owned_generation_progress(
                        engine, worker_id, generation_id,
                        obs.progress.current, obs.progress.total,
                        obs.progress.node,
                    )
                    if r in (OwnershipMutationResult.LEASE_LOST,
                             OwnershipMutationResult.GENERATION_OWNERSHIP_LOST):
                        # Fenced mutation reports authority is gone
                        # (re-audit composition): stop this local drive
                        # immediately; never keep polling — and never
                        # cancel remote work — after deauthorization.
                        log.error(
                            "drive halted after progress write (%s) for %s",
                            r, generation_id,
                        )
                        raise SoloRingError(
                            ErrorCode.GENERATION_OWNERSHIP_LOST,
                            f"authority lost mid-drive ({r})",
                            status_code=500,
                        )
                    r = await transition_owned_generation(
                        engine, worker_id, generation_id, "running",
                    )
                    if r in (OwnershipMutationResult.LEASE_LOST,
                             OwnershipMutationResult.GENERATION_OWNERSHIP_LOST):
                        log.error(
                            "drive halted after running transition (%s) "
                            "for %s", r, generation_id,
                        )
                        raise SoloRingError(
                            ErrorCode.GENERATION_OWNERSHIP_LOST,
                            f"authority lost mid-drive ({r})",
                            status_code=500,
                        )
                    last_signature = signature
        await asyncio.sleep(poll_interval)

    assert terminal is not None
    if terminal.state == "failed":
        _require_ok(
            await transition_owned_generation(
                engine, worker_id, generation_id, "failed",
                error_code="EXECUTOR_FAILED",
                error_message=terminal.error or "executor reported failure",
            ),
            generation_id,
        )
        return "failed"
    if terminal.state == "cancelled":
        _require_ok(
            await transition_owned_generation(
                engine, worker_id, generation_id, "cancelled",
            ),
            generation_id,
        )
        return "cancelled"

    # 9) Output resolution against the CAPTURED contract + historical
    # bindings; streamed /view into deterministic output_key staging.
    # (The manifest is (re)loaded by hash here so the ADOPTED path — which
    # skipped all prework — resolves outputs from historical truth too.)
    history = await client.history(prompt_id)
    record = history.get(prompt_id)
    if record is None:
        _require_ok(
            await transition_owned_generation(
                engine, worker_id, generation_id, "interrupted",
                error_code=ErrorCode.EXECUTOR_JOB_LOST,
                error_message="terminal history vanished before output fetch",
            ),
            generation_id,
        )
        return "interrupted"

    # Output resolution is schema-aware (M10E: the captured manifest bytes
    # are v3 for schema-3 generations, and v2 manifests carry the
    # discriminated `source` object the schema-1 model rejects — the v1
    # parse here was a latent shared-path defect for both). One manifest
    # authority, schema-dispatched parse; resolve_comfy_outputs consumes
    # only the outputs declarations, identical across schemas.
    retained_manifest_schema = None
    try:
        retained_manifest_schema = json.loads(
            (await artifact_store.get_manifest(generation.manifest_hash))
            .decode("utf-8")).get("schema_version")
    except ValueError:
        retained_manifest_schema = None
    if (retained_manifest_schema == "3"
            and spec.get("schema_version") in (1, 2)):
        # M10F PD-1B: one canonical lower-logical view owns output
        # interpretation for retained schema-3 packages on logical v1/v2.
        from soloring.spatial.package3 import (
            parse_manifest_v3,
            project_lower_logical_execution_view,
        )

        manifest_v3_doc = parse_manifest_v3(
            (await artifact_store.get_manifest(generation.manifest_hash))
            .decode("utf-8")
        )
        template_graph = json.loads(
            (await artifact_store.get_template(
                generation.workflow_template_hash)).decode("utf-8"))
        manifest = project_lower_logical_execution_view(
            manifest_v3_doc, template_graph,
            generation.manifest_hash, generation.workflow_template_hash,
            logical_schema_version=spec["schema_version"],
        ).manifest
    elif spec.get("schema_version") == 3:
        from soloring.spatial.package3 import parse_manifest_v3
        from soloring.workflows.manifest import parse_manifest_v2

        manifest_v3_doc = parse_manifest_v3(
            (await artifact_store.get_manifest(generation.manifest_hash))
            .decode("utf-8")
        )
        inherited = {k: v for k, v in manifest_v3_doc.items()
                     if k != "spatial_bindings"}
        inherited["schema_version"] = "2"
        manifest = parse_manifest_v2(inherited)
    elif spec.get("schema_version") == 2:
        from soloring.workflows.manifest import parse_manifest_v2

        manifest = parse_manifest_v2(
            (await artifact_store.get_manifest(generation.manifest_hash))
            .decode("utf-8")
        )
    else:
        manifest = parse_manifest(
            (await artifact_store.get_manifest(generation.manifest_hash))
            .decode("utf-8")
        )
    contracts = [
        CapturedOutputContract(
            name=o.name, kind=o.kind, expected_count=o.expected_count,
            accepted_media_types=o.accepted_media_types,
        )
        for o in outputs
    ]
    resolved = resolve_comfy_outputs(
        captured_outputs=contracts, manifest=manifest, history=record,
    )

    staging_dir = Path(settings.staging_dir) / generation_id / attempt_id
    _require_ok(
        await transition_owned_generation(
            engine, worker_id, generation_id, "importing",
        ),
        generation_id,
    )
    provider = ClientViewStreamProvider(client)
    staged: list[StagedOutput] = []
    for ref in resolved:
        target = await fetch_output_to_staging(
            provider, ref, staging_dir, max_bytes=max_output_bytes,
        )
        staged.append(StagedOutput(
            output_key=ref.output_key, path=target, kind=ref.expected_kind,
        ))

    imported = await import_staged_outputs(
        factory, blob_store, generation, staged,
        expected_outputs=outputs, staging_directory=staging_dir,
        worker_id=worker_id, attempt_id=attempt_id,
    )

    _require_ok(
        await transition_owned_generation(
            engine, worker_id, generation_id, "succeeded",
        ),
        generation_id,
    )
    with contextlib.suppress(OSError):
        for out in staged:
            out.path.unlink(missing_ok=True)
        staging_dir.rmdir()
    log.info("COMFY PIPELINE complete: gen=%s prompt=%s outputs=%s",
             generation_id, prompt_id, imported)
    return "succeeded"


# --- adapters -----------------------------------------------------------------


class ClientUploader:
    """ComfyUploader seam over the client's streaming /upload/image."""

    def __init__(self, client: ComfyClient) -> None:
        self._client = client

    async def upload(
        self, *, source_path: Path, filename: str, subfolder: str,
    ) -> tuple[str, str]:
        ref = await self._client.upload_input(
            source_path=source_path, filename=filename, subfolder=subfolder,
        )
        return ref.name, ref.subfolder

    async def upload_bytes(
        self, *, data: bytes, filename: str, subfolder: str,
    ) -> tuple[str, str]:
        """Upload in-memory bytes through the same executor input
        namespace (M10E: per-frame D0 uploads — the bytes are exact
        slices of the verified retained Blob, never re-encoded). The
        temp path is uniquely keyed (uuid): concurrent attempts sharing
        a convergent derived Blob must never race one pathname."""
        import tempfile
        import uuid

        tmp = Path(tempfile.gettempdir()) / (
            f"soloring-up-{uuid.uuid4().hex}-{filename}")
        tmp.write_bytes(data)
        try:
            return await self.upload(
                source_path=tmp, filename=filename, subfolder=subfolder)
        finally:
            tmp.unlink(missing_ok=True)


class ClientViewStreamProvider:
    """Sync chunk provider bridging the staging fetcher's worker thread to
    the event loop's /view byte stream.

    Satisfies the M5A-9 provider protocol: repeated calls advance a cursor,
    EOF returns b"", and the call after EOF (or after a transport failure)
    restarts from byte zero with a fresh single-request stream — the fetcher's
    retry-from-zero semantics map onto a real HTTP re-GET.

    DEADLOCK GUARD (M5B-3 runtime assertion): run_coroutine_threadsafe(...).
    result() DEADLOCKS if executed on the event-loop thread it targets. The
    provider records the loop's thread identity at construction and refuses
    immediately (rather than hanging) if a same-thread call is ever made.
    """

    def __init__(self, client: ComfyClient) -> None:
        import threading

        self._client = client
        self._loop = asyncio.get_running_loop()
        self._loop_thread_id = threading.get_ident()
        self._key: tuple | None = None
        self._agen = None

    def __call__(self, filename: str, subfolder: str, _read: int = 1 << 20):
        import threading

        if threading.get_ident() == self._loop_thread_id:
            raise RuntimeError(
                "view stream bridge invoked on its own event-loop thread — "
                "run_coroutine_threadsafe(...).result() would deadlock"
            )
        key = (filename, subfolder, _read)
        if self._agen is None or key != self._key:
            self._close_current()
            self._agen = self._client.stream_view(
                filename, subfolder, chunk_size=_read,
            )
            self._key = key
        try:
            chunk = asyncio.run_coroutine_threadsafe(
                self._agen.asend(None), self._loop,
            ).result()
        except StopAsyncIteration:
            self._agen = None  # next call restarts from byte zero
            return b""
        except Exception:
            self._agen = None  # broken stream; next attempt re-GETs
            raise
        if not chunk:
            self._agen = None
            return b""
        return chunk

    def _close_current(self) -> None:
        if self._agen is not None:
            agen, self._agen = self._agen, None
            with contextlib.suppress(Exception):
                asyncio.run_coroutine_threadsafe(
                    agen.aclose(), self._loop,
                ).result()


# --- helpers ------------------------------------------------------------------


async def _current_status(engine: AsyncEngine, generation_id: str) -> str | None:
    async with engine.connect() as conn:
        return (await conn.execute(
            text("SELECT status FROM generations WHERE id = :g"),
            {"g": generation_id},
        )).scalar_one_or_none()


async def _current_submission_state(
    engine: AsyncEngine, generation_id: str, worker_id: str
) -> str | None:
    """Durable submission state, or None on ownership loss (audit F12)."""
    async with engine.connect() as conn:
        row = (await conn.execute(
            text("SELECT worker_id, executor_submission_state "
                 "FROM generations WHERE id = :g"),
            {"g": generation_id},
        )).one_or_none()
    if row is None or row.worker_id != worker_id:
        return None
    return row.executor_submission_state


def _require_ok(r: OwnershipMutationResult, generation_id: str) -> None:
    if r is not OwnershipMutationResult.OK:
        raise SoloRingError(
            ErrorCode.GENERATION_OWNERSHIP_LOST,
            f"fenced transition rejected ({r}) for {generation_id}",
            status_code=500,
        )
