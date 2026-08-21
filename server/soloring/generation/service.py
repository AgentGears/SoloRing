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
from soloring.errors import ErrorCode, not_found
from soloring.generation import repository as repo
from soloring.generation.drafts import GenerationDraft
from soloring.generation.enums import GenerationOperation
from soloring.generation.input_mapping import (
    GenerationInputRule,
    resolve_generation_inputs,
)
from soloring.workflows.manifest import WorkflowTemplate, check_cardinality, load_workflow

LOGICAL_WORKFLOW_SCHEMA_VERSION = 1


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
        # Coherent capture of the installed release FIRST — no DB session
        # work has happened yet, so no transaction is open during file I/O.
        from soloring.executors.comfy.bindings import (
            validate_manifest_template_bindings,
        )
        from soloring.workflows.artifact_store import WorkflowArtifactStore
        from soloring.workflows.manifest import (
            WORKFLOW_DIR,
            build_template,
            parse_manifest,
        )

        package = WORKFLOW_DIR / "workflow-package.json"
        artifact_store = WorkflowArtifactStore(settings)
        captured = await artifact_store.capture_package(
            package, WORKFLOW_DIR / "manifest.json",
            WORKFLOW_DIR / "workflow.json",
        )
        await artifact_store.place_captured(captured)

        # EVERYTHING downstream derives from the EXACT captured bytes and
        # their captured hashes (audit F9): a second mutable installed read
        # could straddle an installation switch and persist a Generation
        # whose recorded artifacts were never captured.
        manifest_doc = parse_manifest(captured.manifest_bytes.decode("utf-8"))
        template_graph = json.loads(captured.template_bytes.decode("utf-8"))
        # Bad executor bindings never queue a Generation (audit F10).
        validate_manifest_template_bindings(manifest_doc, template_graph)
        template = build_template(
            manifest_doc, captured.manifest_hash,
            captured.workflow_template_hash,
        )
    else:
        template = load_workflow()

    # Validate the Shot, then use the PRIMITIVE shot_id everywhere below.
    # capture_revision() owns rollback semantics (collision retry rolls the
    # session back, expiring previously loaded ORM instances); dereferencing
    # a pre-helper ORM object after that is a MissingGreenlet/DetachedInstance
    # failure under concurrency (third re-gate P3-5).
    await shot_svc.get_shot(session, shot_id)

    # Resolve ordered references + capture/reuse the immutable revision.
    refs = await shot_svc.snapshot_references(session, shot_id)
    revision = await revision_svc.capture_revision(
        session, shot_id, settings=settings
    )

    # Deterministic input mapping from the CAPTURED revision snapshot
    # (`template` already holds the captured-bytes workflow for comfy).
    snapshot = json.loads(revision.snapshot_json)
    rules = [
        GenerationInputRule(input_key=i.input_key, source_role=i.source_role)
        for i in template.reference_inputs
    ]
    inputs = resolve_generation_inputs(snapshot, rules)

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
    spec = build_workflow_spec(template, inputs, compiled_prompt, parameters)
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
        model=None,
        model_version=None,
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
