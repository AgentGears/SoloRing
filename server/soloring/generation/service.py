"""Generation creation service (v0.1 §41) — capture, never read-later.

Everything the execution layer will ever consume is captured AT CREATION:
the immutable ShotRevision (snapshot of the complete creative state), the
resolved GenerationInputs, the compiled prompt + compiler version, workflow
identity/hashes, resolved parameters, and the canonical logical workflow
specification. The worker never reconstructs execution input from mutable
current Shot state.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.db.models import Generation, GenerationInput
from soloring.domain import revisions as revision_svc
from soloring.domain import shots as shot_svc
from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.domain.prompt import PROMPT_COMPILER_VERSION, compile_prompt
from soloring.domain.shot_intent import ShotIntent
from soloring.errors import (
    ErrorCode,
    SoloRingError,
    internal_invariant,
    not_found,
)
from soloring.generation import repository as repo
from soloring.generation.drafts import GenerationDraft
from soloring.generation.enums import GenerationOperation
from soloring.generation.input_mapping import (
    GenerationInputRule,
    resolve_generation_inputs,
)
from soloring.workflows.manifest import (
    WorkflowTemplate,
    build_template_v2,
    check_cardinality,
    load_workflow,
)

LOGICAL_WORKFLOW_SCHEMA_VERSION = 1
LOGICAL_WORKFLOW_SCHEMA_VERSION_2 = 2


def build_workflow_spec(
    template: WorkflowTemplate,
    inputs,
    compiled_prompt: str,
    parameters: dict,
) -> dict:
    """Versioned logical workflow specification (v0.1 §38, M4).

    Contains no transient executor state: no absolute paths, no staging, no
    executor filenames. Inputs are keyed by workflow input key. The OUTPUT
    CONTRACT is embedded (M4 §11): the worker and importer derive expected
    outputs from THIS captured spec, never from whichever manifest happens to
    be installed at execution time.
    """
    spec_inputs: dict[str, dict] = {}
    for resolved in inputs:
        entry = spec_inputs.setdefault(resolved.input_key, {"bindings": []})
        entry["bindings"].append(
            {
                "asset_id": resolved.asset_id,
                "blob_hash": resolved.blob_hash,
                "reference_role": resolved.reference_role,
                "position": resolved.position,
            }
        )
    return {
        "schema_version": LOGICAL_WORKFLOW_SCHEMA_VERSION,
        "workflow_id": template.workflow_id,
        "workflow_version": template.workflow_version,
        "manifest_hash": template.manifest_hash,
        "inputs": spec_inputs,
        "prompt": compiled_prompt,
        "parameters": parameters,
        "outputs": [
            {
                "name": o.name,
                "kind": o.kind,
                "expected_count": o.expected_count,
                "accepted_media_types": (
                    list(o.accepted_media_types)
                    if o.accepted_media_types is not None
                    else None
                ),
            }
            for o in template.outputs
        ],
    }



def assert_pre_m10e_spatial_execution_fence(revision) -> None:
    """M10D §63.1: one named temporary integration seam. Schema-5 (any
    non-empty captured SpatialContinuityPack) blocks Generation creation
    with SPATIAL_REALIZATION_UNSUPPORTED and NOTHING is queued or
    persisted. M10E must explicitly subsume this branch with real
    spatial capability handling while preserving the fail-closed default
    for unsupported hard M10 authority."""
    import json as _json

    from soloring.errors import ErrorCode, SoloRingError

    snapshot = _json.loads(revision.snapshot_json)
    if snapshot.get("schema_version") == 5:
        raise SoloRingError(
            ErrorCode.SPATIAL_REALIZATION_UNSUPPORTED,
            "This ShotRevision captures spatial continuity authority "
            "(schema 5); spatial realization is not yet supported — "
            "Generation creation is blocked until spatial-capable "
            "packages exist.",
            status_code=409,
            details={"shot_revision_id": revision.id,
                     "snapshot_hash": revision.snapshot_hash})

async def create_generation_request(
    session: AsyncSession, shot_id: str, *, settings: "Settings | None" = None
) -> Generation:
    """POST /shots/{id}/generations flow (v0.1 §41; M5 §5 executor selection).

    The executor is selected HERE, from Settings, and persisted on the row —
    the worker later dispatches from the persisted value, so a config change
    can never reinterpret a queued historical Generation. For comfy
    Generations the manifest+template pair is captured into the historical
    artifact store BEFORE any database transaction opens (capture is pure
    file I/O verified against the workflow-package.json descriptor).
    """
    from soloring.settings import Settings as _Settings, get_settings

    settings = settings or get_settings()
    executor = settings.executor

    if executor == "comfy":
        # CAPTURE RELEASE BYTES FIRST (M9 frozen plan §22): the four-
        # artifact descriptor-coherent release — no DB session work has
        # happened yet, so no transaction is open during file I/O.
        from soloring.realization.packages import (
            capture_current_release,
            validate_package,
        )
        from soloring.workflows.artifact_store import WorkflowArtifactStore

        # §11.1 Stage 0 (r1-gate B1): RAW BYTE capture only — coherent
        # descriptor-bound buffers placed content-addressed. Semantic
        # package validation runs AFTER the M7/M8 predecessor gates
        # below, per the frozen ordering.
        release = await capture_current_release(settings)
        await WorkflowArtifactStore(settings).place_release(release)
        package = None
        template = None
    else:
        release = None
        package = None
        template = load_workflow()

    # Validate the Shot, then use the PRIMITIVE shot_id everywhere below.
    # capture_revision() owns rollback semantics (collision retry rolls the
    # session back, expiring previously loaded ORM instances); dereferencing
    # a pre-helper ORM object after that is a MissingGreenlet/DetachedInstance
    # failure under concurrency (third re-gate P3-5).
    await shot_svc.get_shot(session, shot_id)

    # Resolve ordered references + capture/reuse the immutable revision.
    # M7/M8 blockers raise HERE — strictly BEFORE any semantic package
    # validation (frozen §11.1 ordering; r1-gate B1).
    refs = await shot_svc.snapshot_references(session, shot_id)
    revision, visual_result = await (
        revision_svc.capture_revision_with_visual(
            session, shot_id, settings=settings
        )
    )

    # M10D §63 — pre-M10E schema-5 fail-closed fence: spatially captured
    # authority cannot be executed until M10E installs real spatial
    # realization. Runs immediately after coherent capture/reuse and
    # BEFORE package semantic validation, input mapping, workflow-spec
    # assembly, or any Generation persistence. Existing Stage-0 raw
    # release capture above is not reclassified as package acceptance.
    assert_pre_m10e_spatial_execution_fence(revision)

    if release is not None:
        # §11.1 step 3 — NOW the captured package semantics are parsed
        # and cross-validated (after M7/M8, before M9 compilation).
        # EVERYTHING downstream derives from the EXACT captured bytes
        # and their captured hashes (audit F9): a second mutable
        # installed read could straddle an installation switch and
        # persist a Generation whose recorded artifacts were never
        # captured. Schema-2 releases additionally bind profile +
        # ExecutionModelFingerprint (§6.2).
        package = validate_package(release)
        if package.is_schema2:
            template = build_template_v2(
                package.manifest_v2,
                package.release.manifest_hash,
                package.release.workflow_template_hash,
            )
        else:
            from soloring.workflows.manifest import (
                build_template,
                parse_manifest,
            )
            from soloring.executors.comfy.bindings import (
                validate_manifest_template_bindings,
            )

            manifest_doc = parse_manifest(
                package.release.manifest_bytes.decode("utf-8")
            )
            # Bad executor bindings never queue a Generation (audit F10).
            validate_manifest_template_bindings(
                manifest_doc, package.template_graph
            )
            template = build_template(
                manifest_doc, package.release.manifest_hash,
                package.release.workflow_template_hash,
            )

    # Deterministic input mapping from the CAPTURED revision snapshot
    # (`template` already holds the captured-bytes workflow for comfy).
    snapshot = json.loads(revision.snapshot_json)
    rules = [
        GenerationInputRule(input_key=i.input_key, source_role=i.source_role)
        for i in template.reference_inputs
        if i.source_role is not None
    ]
    legacy_inputs = resolve_generation_inputs(snapshot, rules)

    # ---- M9 §22: compile + assemble (comfy schema-2 releases only) ----
    realization_spec = None
    realization_inputs = []
    model = None
    model_version = None
    profile_overrides: dict = {}
    authority_nonempty = bool(
        (snapshot.get("visual_reference_pack") or {}).get("anchors")
    )
    if executor == "comfy" and not getattr(template, "is_schema2", False):
        # §11.3: non-empty captured M8 authority may never be silently
        # ignored — a schema-1 package is insufficient.
        if authority_nonempty:
            raise SoloRingError(
                ErrorCode.REALIZATION_PROFILE_REQUIRED,
                "The captured M8 visual authority is non-empty but the "
                "selected workflow package is schema 1 (no M9 realization "
                "contract).",
                status_code=409,
            )
    if getattr(template, "is_schema2", False):
        release = package.release
        if not authority_nonempty:
            # §11.2/§16.3: empty effective M8 authority → exact spec v1
            # legacy path; profile/fingerprint are not Generation
            # dependencies.
            pass
        else:
            from soloring.realization.authority import (
                reconstruct_authority,
            )
            from soloring.realization.compiler import compile_realization

            requirement_map = {
                st.visual_facet_id: st.requirement
                for st in (visual_result.facet_statuses or ())
            }
            async with session.bind.connect() as conn:
                await conn.exec_driver_sql("BEGIN")
                try:
                    authority = await reconstruct_authority(
                        conn, revision.id, requirement_map
                    )
                    await conn.commit()
                except Exception:
                    import contextlib as _cl

                    with _cl.suppress(Exception):
                        await conn.rollback()
                    raise
            result = compile_realization(
                captured_visual_authority=authority,
                profile=package.profile,
                manifest=package.manifest_v2,
                profile_hash=release.realization_profile_hash,
                execution_model_fingerprint_hash=(
                    release.execution_model_fingerprint_hash
                ),
            )
            if not result.ready:
                first = result.issues[0]
                raise SoloRingError(
                    first["error_code"], first["message"], status_code=409
                )
            realization_spec = result.spec
            profile_overrides = dict(result.parameter_overrides)
            from soloring.generation.input_mapping import (
                ResolvedGenerationInput,
            )

            realization_inputs = [
                ResolvedGenerationInput(
                    input_key=p.input_key,
                    position=p.position,
                    asset_id=p.asset_id,
                    blob_hash=p.blob_hash,
                    reference_role=p.reference_role,
                )
                for p in result.inputs
            ]
            model = package.profile.model.id
            model_version = package.profile.model.version

    # §19: source classes stay disjoint by input_key; combined
    # cardinality is assembly-layer validation only.
    legacy_keys = {i.input_key for i in legacy_inputs}
    realization_keys = {i.input_key for i in realization_inputs}
    overlap = legacy_keys & realization_keys
    if overlap:
        raise internal_invariant(
            f"Legacy and realization inputs collide on {sorted(overlap)}."
        )
    inputs = legacy_inputs + realization_inputs

    # Cardinality validation (v0.1 §36: no reference silently ignored).
    counts: dict[str, int] = {}
    for resolved in inputs:
        counts[resolved.input_key] = counts.get(resolved.input_key, 0) + 1
    check_cardinality(template, counts)

    # Prompt compilation from the CAPTURED revision intent.
    intent = ShotIntent(**snapshot["intent"])
    compiled_prompt = compile_prompt(intent)

    from soloring.workflows.manifest import resolve_parameters

    parameters = resolve_parameters(template)  # strict, resolved at capture
    # §9: profile overrides are FINAL for the keys they own.
    for name, value in profile_overrides.items():
        parameters[name] = value
    if realization_spec is not None:
        for name, value in realization_spec["parameter_overrides"].items():
            if parameters.get(name) != value:
                raise internal_invariant(
                    "RealizationSpec parameter overrides disagree with "
                    "final captured parameters."
                )
    spec = build_workflow_spec(template, inputs, compiled_prompt, parameters)
    if realization_spec is not None:
        # §16.2: schema 2 preserves all schema-1 fields and adds model +
        # realization; no empty schema-2 is ever emitted (§16.1).
        spec["schema_version"] = LOGICAL_WORKFLOW_SCHEMA_VERSION_2
        spec["model"] = {
            "id": model,
            "version": model_version,
            "execution_model_fingerprint_hash": (
                package.release.execution_model_fingerprint_hash
            ),
        }
        spec["realization"] = realization_spec
    spec_json = canonical_json_str(spec)
    spec_hash = canonical_hash(spec)

    draft = GenerationDraft(
        shot_id=shot_id,
        shot_revision_id=revision.id,
        operation=GenerationOperation.GENERATE,
        executor=executor,
        workflow_id=template.workflow_id,
        workflow_version=template.workflow_version,
        workflow_template_hash=template.workflow_template_hash,
        manifest_hash=template.manifest_hash,
        model=model,
        model_version=model_version,
        compiled_prompt=compiled_prompt,
        negative_prompt=None,
        prompt_compiler_version=PROMPT_COMPILER_VERSION,
        seed=None,
        parameters_json=canonical_json_str(parameters),
        workflow_spec_json=spec_json,
        workflow_spec_hash=spec_hash,
    )
    return await repo.create_generation(session, draft, inputs)


async def list_generations(session: AsyncSession, shot_id: str) -> list[Generation]:
    await shot_svc.get_shot(session, shot_id)
    res = await session.execute(
        select(Generation)
        .where(Generation.shot_id == shot_id)
        .order_by(Generation.generation_number)
    )
    return list(res.scalars().all())


async def get_generation_or_404(
    session: AsyncSession, generation_id: str
) -> Generation:
    from soloring.domain.ids import is_uuid

    if not is_uuid(generation_id):
        raise not_found(
            ErrorCode.GENERATION_NOT_FOUND,
            f"Generation {generation_id} not found.",
        )
    generation = await session.get(Generation, generation_id)
    if generation is None:
        raise not_found(
            ErrorCode.GENERATION_NOT_FOUND,
            f"Generation {generation_id} not found.",
        )
    return generation


async def load_execution_inputs(
    session: AsyncSession, generation_id: str
) -> list[GenerationInput]:
    return await repo.list_generation_inputs(session, generation_id)


__all__ = [
    "create_generation_request",
    "list_generations",
    "get_generation_or_404",
    "load_execution_inputs",
    "build_workflow_spec",
]
