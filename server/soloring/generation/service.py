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
    """M10D §63.1 fence, now narrowed to its M10E fail-closed residue
    (M10E R3 §4.4/§7.1): schema-5 authority can execute ONLY through a
    captured schema-3 comfy package. When no package release was captured
    at Stage 0 (non-comfy executors), spatial execution remains
    unsupported and NOTHING is queued or persisted. The real schema-3
    realization path lives below in create_generation_request."""
    import json as _json

    from soloring.errors import ErrorCode, SoloRingError

    snapshot = _json.loads(revision.snapshot_json)
    if snapshot.get("schema_version") == 5:
        raise SoloRingError(
            ErrorCode.SPATIAL_REALIZATION_UNSUPPORTED,
            "This ShotRevision captures spatial continuity authority "
            "(schema 5); spatial realization requires a schema-3 spatial "
            "workflow package, and no package release was captured for "
            "this executor.",
            status_code=409,
            details={"shot_revision_id": revision.id,
                     "snapshot_hash": revision.snapshot_hash})

async def _realize_spatial_inputs(
    session: AsyncSession,
    settings,
    *,
    shot_id: str,
    shot_revision_id: str,
    pack: dict,
    manifest_v3: dict,
    realization_profile_hash: str,
):
    """M10E §7.1 steps 5-6 production finalizer (Generation-orchestration
    owned; the pure compiler owns derivation, the frozen primitives own
    publication/registration/binding).

    captured pack → canonical re-verification → pure D0 composition →
    content-addressed Blob publication → immutable DerivedSpatialArtifact
    registration (global convergence) → exact manifest input coordinates →
    final real-ID spatial_realization block + DerivedInputBinding siblings.

    Reads ONLY the captured pack and the Shot/ShotRevision identity rows —
    never current M10 authority. Pre-published owner-free
    Blob/provenance may outlive a later Generation rollback (§12.4)."""
    import hashlib as _hashlib

    from soloring.assets.blob_store import BlobStore as _BlobStore
    from soloring.db.timeutil import DB_NOW_SQL as _NOW
    from soloring.errors import ErrorCode as _EC
    from soloring.spatial import production_pins as _pins
    from soloring.spatial.derived import (
        prepare_derived_artifact as _prepare,
        register_derived_artifact as _register,
    )
    from soloring.spatial.derived_inputs import DerivedInputBinding
    from soloring.spatial.package3 import resolve_derived_binding
    from soloring.spatial.realize import (
        StagingCapacityExceeded,
        compose_spatial_realization,
    )
    from soloring.spatial.schemas import (
        parse_continuity_pack as _parse_pack,
    )
    from soloring.spatial.spec3 import build_spatial_realization_block
    from sqlalchemy import text as _text

    # §10.2: canonical verification through the frozen M10D grammar —
    # never normalize or "repair" captured bytes.
    _parse_pack(pack)

    # §13: the registration Project is derived from the same Shot context
    # that supplied the captured pack; the stored M10D continuity hash
    # must agree with the captured canonical bytes.
    row = (await session.execute(
        _text("SELECT s.project_id, srsw.spatial_continuity_hash "
              "FROM shots s JOIN shot_revisions sr ON sr.shot_id = s.id "
              "LEFT JOIN shot_revision_spatial_worlds srsw "
              "  ON srsw.shot_revision_id = sr.id "
              "WHERE s.id = :sid AND sr.id = :rid"),
        {"sid": shot_id, "rid": shot_revision_id})).mappings().one_or_none()
    if row is None or row["project_id"] is None:
        raise internal_invariant(
            "Spatial realization could not resolve the Shot-owning "
            "Project for registration.")
    project_id = row["project_id"]

    try:
        out = compose_spatial_realization(
            pack, realization_profile_hash=realization_profile_hash)
    except StagingCapacityExceeded as exc:
        # M10E R3 §4.5: the ONLY conversion seam — the typed capacity
        # condition becomes the durable SPATIAL_REALIZATION_UNSUPPORTED;
        # bare/unrelated ValueError is never converted.
        raise SoloRingError(
            _EC.SPATIAL_REALIZATION_UNSUPPORTED,
            f"Captured staging exceeds the frozen 3-stream control "
            f"capacity: {exc}",
            status_code=409,
            details={"shot_id": shot_id},
        ) from exc

    continuity_hash = canonical_hash(pack)
    if row["spatial_continuity_hash"] is not None and \
            row["spatial_continuity_hash"] != continuity_hash:
        raise internal_invariant(
            "Captured spatial continuity hash disagrees with the "
            "ShotRevision's stored M10D provenance.")

    store = _BlobStore(settings)
    artifacts: list[str] = []
    final_entries: list[dict] = []
    bindings: list[DerivedInputBinding] = []

    # §12.3 publication first, in its OWN committed BEGIN IMMEDIATE unit:
    # the service session stays read-only until the final Generation write
    # (WAL single-writer — a held session write transaction would block
    # the registration primitive's own BEGIN IMMEDIATE below).
    import contextlib as _cl

    async with session.bind.connect() as _pub:
        try:
            await _pub.exec_driver_sql("BEGIN IMMEDIATE")
            for spec, frames, digest in zip(
                    out.specs, out.frames, out.artifact_digests):
                content = b"".join(frames)
                if _hashlib.sha256(content).hexdigest() != digest:
                    raise internal_invariant(
                        "Materialized D0 bytes disagree with the artifact "
                        "digest.")
                tmp = store.tmp_path()
                tmp.write_bytes(content)
                await store.place(digest, tmp)
                await _pub.execute(
                    _text(f"INSERT OR IGNORE INTO blobs (hash, path, "
                          f"size_bytes, created_at) VALUES (:h, :p, :s, "
                          f"{_NOW})"),
                    {"h": digest, "p": str(store.path_for_hash(digest)),
                     "s": len(content)})
            await _pub.exec_driver_sql("COMMIT")
        except Exception:
            with _cl.suppress(Exception):
                await _pub.exec_driver_sql("ROLLBACK")
            raise

    for position, (spec, spec_hash, digest) in enumerate(zip(
            out.specs, out.spec_hashes, out.artifact_digests)):
        # §12.4/§13: immutable registration BEFORE the Generation write
        # unit; global convergence inside BEGIN IMMEDIATE.
        prepared = _prepare(
            spec, out.runtime_fingerprint, digest,
            allowed_artifact_kinds=frozenset({"boxdepth_control_video"}),
            allowed_media_types=frozenset({"image/png"}),
            allowed_algorithms=frozenset({
                (_pins.BOXDEPTH_ALGORITHM_ID,
                 _pins.BOXDEPTH_ALGORITHM_VERSION)}))
        artifact_id = await _register(session, store, project_id, prepared)
        artifacts.append(artifact_id)

        # §14.2: exact captured-manifest coordinates; no heuristics.
        role = ("spatial.world_depth" if position == 0
                else "spatial.entity_depth")
        input_key, _node, _field = resolve_derived_binding(
            manifest_v3, role, position)
        final_entries.append({
            "input_key": input_key,
            "position": position,
            "artifact_role": role,
            "derived_spatial_artifact_id": artifact_id,
            "spec_hash": spec_hash,
            "runtime_fingerprint_hash": out.runtime_fingerprint_hash,
            "blob_hash": digest,
        })
        bindings.append(DerivedInputBinding(
            input_key=input_key, position=position, artifact_role=role,
            derived_spatial_artifact_id=artifact_id, blob_hash=digest))

    # §11.2/§16.2: the FINAL block is rebuilt from real registered
    # identities — the pure compiler's provisional pending:* block is
    # never persisted.
    block = build_spatial_realization_block(
        spatial_continuity_hash=continuity_hash,
        realization_profile_hash=realization_profile_hash,
        derived_artifacts=final_entries,
        advisory_omissions=list(
            out.spatial_realization_block["advisory_omissions"]),
    )
    return block, tuple(bindings)


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

    # M10E §7.1: the captured snapshot decides the spatial plane. Schema 5
    # carries a canonical non-empty SpatialContinuityPack that ONLY the
    # schema-3 realization path below may consume; with no captured
    # package release (non-comfy executors) the M10D-era fail-closed
    # posture is preserved — nothing queues, nothing persists.
    snapshot = json.loads(revision.snapshot_json)
    spatial_pack = (
        snapshot.get("spatial_continuity")
        if snapshot.get("schema_version") == 5 else None
    )
    if spatial_pack is not None and release is None:
        assert_pre_m10e_spatial_execution_fence(revision)

    if release is not None:
        # §11.1 step 3 — NOW the captured package semantics are parsed
        # and cross-validated (after M7/M8, before M9 compilation).
        # EVERYTHING downstream derives from the EXACT captured bytes
        # and their captured hashes (audit F9): a second mutable
        # installed read could straddle an installation switch and
        # persist a Generation whose recorded artifacts were never
        # captured. Schema-2 releases additionally bind profile +
        # ExecutionModelFingerprint (§6.2); schema-3 releases additionally
        # carry the M10 spatial package documents (M10E §8).
        package = validate_package(release)
        if package.is_schema3:
            from soloring.workflows.manifest import build_template_v3

            template = build_template_v3(
                package.manifest_v3,
                package.release.manifest_hash,
                package.release.workflow_template_hash,
            )
        elif package.is_schema2:
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
    # The snapshot was loaded above (M10E §7.1 spatial-plane decision).
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
    if executor == "comfy" and not (
            getattr(template, "is_schema2", False)
            or getattr(template, "is_schema3", False)):
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
    if getattr(template, "is_schema2", False) or getattr(
            template, "is_schema3", False):
        release = package.release
        if not authority_nonempty:
            # §11.2/§16.3: empty effective M8 authority → exact spec v1
            # legacy path; profile/fingerprint are not Generation
            # dependencies. (A schema-3 package still composes spec v3
            # below — the M10 spatial plane is independent of M8.)
            pass
        else:
            from soloring.realization.authority import (
                reconstruct_authority,
            )
            from soloring.realization.compiler import compile_realization

            if getattr(template, "is_schema3", False):
                # M10E §9.2: the inherited M9 portion of the schema-3
                # documents is re-parsed through the FROZEN M9 parsers —
                # the exact same compiler seam as schema 2, never a fork.
                # The derived spatial inputs are EXCLUDED from the M9
                # manifest view (the same exclusion rule as
                # build_template_v3 and the schema-3 translator): they are
                # never realization-channel inputs.
                from soloring.realization.profile import (
                    parse_profile as _parse_profile_m9,
                )
                from soloring.workflows.manifest import (
                    parse_manifest_v2 as _parse_manifest_v2,
                )

                _spatial_keys = frozenset(
                    package.manifest_v3["spatial_bindings"])
                m9_profile = _parse_profile_m9(
                    {k: v for k, v in package.profile_v2.items()
                     if k != "spatial"} | {"schema_version": 1})
                m9_manifest = _parse_manifest_v2(
                    {**{k: v for k, v in package.manifest_v3.items()
                        if k != "spatial_bindings"},
                     "inputs": {k: v for k, v in
                                package.manifest_v3["inputs"].items()
                                if k not in _spatial_keys},
                     "schema_version": "2"})
            else:
                m9_profile = package.profile
                m9_manifest = package.manifest_v2

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
                profile=m9_profile,
                manifest=m9_manifest,
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
            if getattr(template, "is_schema3", False):
                model = package.profile_v2["model"]["id"]
                model_version = package.profile_v2["model"]["version"]
            else:
                model = package.profile.model.id
                model_version = package.profile.model.version

    # ---- M10E §7.1 steps 5-6: derived spatial realization (schema 5) ----
    derived_bindings: tuple = ()
    spatial_block: dict | None = None
    if spatial_pack is not None:
        if not getattr(template, "is_schema3", False):
            # Fail-closed M10 capability posture (§4.4): captured spatial
            # authority exists but the selected package is not a schema-3
            # spatial package — no hard spatial component may be silently
            # dropped. This fires AFTER package semantic validation and the
            # inherited M9 blockers, per the frozen §20.1 precedence.
            raise SoloRingError(
                ErrorCode.SPATIAL_REALIZATION_UNSUPPORTED,
                "The captured spatial continuity authority requires a "
                "schema-3 spatial workflow package; the selected package "
                "does not provide spatial realization.",
                status_code=409,
                details={"shot_revision_id": revision.id},
            )
        spatial_block, derived_bindings = await _realize_spatial_inputs(
            session, settings,
            shot_id=shot_id, shot_revision_id=revision.id,
            pack=spatial_pack,
            manifest_v3=package.manifest_v3,
            realization_profile_hash=package.release.realization_profile_hash,
        )
    elif getattr(template, "is_schema3", False):
        # A schema-3 package is a spatial package: with no captured M10
        # authority there is no executable spatial realization, and no
        # empty spec v3 exists (spec3 §2.1).
        raise SoloRingError(
            ErrorCode.SPATIAL_REALIZATION_UNSUPPORTED,
            "The selected schema-3 spatial package requires captured "
            "spatial continuity authority; this ShotRevision captures "
            "none.",
            status_code=409,
        )

    # M10-only v3 retains the real captured model identity even when the
    # M9 realization is absent (spec3 §2.1; no fake M9 block is invented).
    if getattr(template, "is_schema3", False) and model is None:
        model = package.profile_v2["model"]["id"]
        model_version = package.profile_v2["model"]["version"]

    # §19: source classes stay disjoint by input_key; combined
    # cardinality is assembly-layer validation only. M10E §15.2 extends
    # the disjointness to the derived spatial family — an ordinary/M9 key
    # colliding with a derived key is a composition-binding failure.
    legacy_keys = {i.input_key for i in legacy_inputs}
    realization_keys = {i.input_key for i in realization_inputs}
    derived_keys = {b.input_key for b in derived_bindings}
    overlap = legacy_keys & realization_keys
    if overlap:
        raise internal_invariant(
            f"Legacy and realization inputs collide on {sorted(overlap)}."
        )
    cross_family = (legacy_keys | realization_keys) & derived_keys
    if cross_family:
        raise SoloRingError(
            ErrorCode.SPATIAL_REALIZATION_BINDING_INVALID,
            f"Ordinary/realization input keys collide with derived "
            f"spatial input keys on {sorted(cross_family)}.",
            status_code=422,
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
    if getattr(template, "is_schema3", False):
        # M10E §16: spec v3 is composed exactly once, only after every
        # real immutable derived identity exists (spatial_block was built
        # from registered artifact UUIDs — never the provisional
        # pending:* block from the pure compiler).
        from soloring.spatial.spec3 import (
            compose_workflow_spec_v3,
            validate_spec_v3,
        )

        spec = compose_workflow_spec_v3(
            spec,
            model={
                "id": model,
                "version": model_version,
                "execution_model_fingerprint_hash": (
                    package.release.execution_model_fingerprint_hash
                ),
            },
            realization=realization_spec,
            spatial_realization=spatial_block,
        )
        validate_spec_v3(spec)
    elif realization_spec is not None:
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
    if getattr(template, "is_schema3", False) and "pending:" in spec_json:
        # E-041 defense at the composition seam itself.
        raise internal_invariant(
            "Provisional derived-artifact identity reached schema-3 "
            "WorkflowSpec composition."
        )

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
    return await repo.create_generation(
        session, draft, inputs, derived_inputs=derived_bindings)


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
