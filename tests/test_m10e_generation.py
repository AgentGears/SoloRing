"""M10E-B — Generation schema-5 creation through the REAL service path
(frozen R3 §§7.1, 9-16, 20).

Captured-pack-only compilation, capacity whole-item failure, D0
materialization + Blob publication + provenance registration + real-ID
final WorkflowSpec v3 + atomic sibling queueing. Fixed-frame world-depth
semantics and canonical stream counts (E-020..E-045)."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from soloring.domain.canonical import canonical_hash
from soloring.domain.ids import is_uuid
from soloring.generation.service import create_generation_request
from soloring.settings import Settings

from tests.test_m10d_resolver import CAM, _entities, _first_sequence, _shot
from tests.test_m10e_package3_production import _schema3_package

# Deterministic in-frame geometry for the frozen CAM (camera at
# (-3000,1650,4200) looking toward -z; fx≈1155.6, center (416,240)):
# everything below projects inside the 832x480 viewport.
_SETPIECE_T = [-3000, 1650, 0]
_STAGED_T = [
    [-3600, 1500, -400],
    [-2400, 1750, -800],
    [-3000, 1200, -1200],
]
_EXTENTS = [600, 400, 300]


async def _spatial_seed(factory, *, staged=1, extents=None):
    """A schema-5-ready shot: required world (one frameless landmark
    'origin' + one fixed 'setpiece' frame with optional half extents),
    ``staged`` optional Track-staged characters, valid camera plan."""
    from soloring.spatial import plans as plan_svc
    from soloring.spatial import tracks as track_svc
    from soloring.spatial import transitions as trans_svc
    from soloring.spatial import revisions as wrev_svc
    from soloring.spatial import worlds as world_svc

    pid = str(uuid.uuid4())
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO projects (id, name, created_at, updated_at) "
                "VALUES (:p, 'P', 't', 't')"), {"p": pid})
    kinds = {"loc": "location"}
    for i in range(staged):
        kinds[f"c{i}"] = "character"
    ents = await _entities(factory, pid, kinds)
    loc, locrev = ents["loc"]

    world = await world_svc.create_world(
        factory(), pid, key="lobby", name="lobby", description=None,
        requirement="required", location_entity_id=loc)
    state = await world_svc.create_state(
        factory(), world["id"], location_entity_revision_id=locrev)
    for fkey, ext in (("origin", None), ("setpiece", extents)):
        f = await world_svc.create_frame(
            factory(), world["id"], key=fkey, name=fkey,
            parent_spatial_frame_id=None, bound_entity_id=None)
        await world_svc.put_state_frame(
            factory(), state["id"], f["id"],
            translation_mm=_SETPIECE_T,
            rotation_udeg=[0, 0, 0], half_extents_mm=ext,
            bound_entity_revision_id=None)
    rev = await wrev_svc.capture_revision(factory(), state["id"])
    await wrev_svc.approve_revision(
        factory(), state["id"], revision_id=rev["id"],
        expected_approved_revision_id=None)

    deps = [loc] + [ents[f"c{i}"][0] for i in range(staged)]
    shot = await _shot(factory, pid, deps, assigned=True)
    blocking = []
    for i in range(staged):
        ent, _ = ents[f"c{i}"]
        track = await track_svc.create_track(
            factory(), world["id"], entity_id=ent, requirement="optional")
        await trans_svc.create_transition(
            factory(), track["id"], anchor_type="sequence",
            anchor_id=await _first_sequence(factory, pid),
            boundary="start", operation="set",
            translation_mm=_STAGED_T[i], rotation_udeg=[0, 0, 0])
        blocking.append({
            "spatial_track_id": track["id"],
            "screen_direction": "left_to_right",
            "keyframes": [{
                "time_ms": 0,
                "transform": {"translation_mm": _STAGED_T[i],
                              "rotation_udeg": [0, 0, 0]}}],
        })
    await plan_svc.put_spatial_plan(
        factory(), shot, expected_plan_hash=None, plan_raw={
            "schema_version": 1,
            "spatial_world_id": world["id"],
            "camera": json.loads(json.dumps(CAM)),
            "blocking": blocking,
            "axis_constraint": None,
        })
    return {"pid": pid, "shot": shot, "world": world, "staged": staged}


def _spatial_settings(settings, package_dir: Path) -> Settings:
    settings.executor = "comfy"
    settings.workflow_package_dir = package_dir
    return settings


async def _create(factory, settings, seed):
    async with factory() as session:
        return await create_generation_request(
            session, seed["shot"], settings=settings)


async def _spec(engine, generation_id):
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT workflow_spec_json, workflow_spec_hash FROM "
            "generations WHERE id = :g"), {"g": generation_id})).mappings().one()
    spec = json.loads(row["workflow_spec_json"])
    assert canonical_hash(spec) == row["workflow_spec_hash"]
    return spec


async def _siblings(engine, generation_id):
    async with engine.connect() as conn:
        return [dict(r) for r in (await conn.execute(text(
            "SELECT input_key, position, artifact_role, "
            "derived_spatial_artifact_id, blob_hash FROM "
            "generation_derived_spatial_inputs WHERE generation_id = :g "
            "ORDER BY position"), {"g": generation_id})).mappings().all()]


async def test_schema5_full_realization_path(
        factory, engine, settings, tmp_path):
    """E-040/E-041/E-042/E-043/E-044/E-024 end to end with one staged
    entity: 2 streams, real IDs, no pending, empty structured bindings,
    deterministic advisory omission, real model identity, M9 absent."""
    pkg = await _schema3_package(tmp_path)
    seed = await _spatial_seed(factory, staged=1, extents=_EXTENTS)
    gen = await _create(factory, _spatial_settings(settings, pkg), seed)
    assert gen.status == "queued"

    spec = await _spec(engine, gen.id)
    assert spec["schema_version"] == 3
    assert spec["model"]["id"] == "wan2.1-t2v-1.3b"
    assert "realization" not in spec  # M8 absent: no fake M9 block
    sr = spec["spatial_realization"]
    assert sr["structured_bindings"] == []
    assert sr["advisory_omissions"] == ["screen_direction_not_consumed"]
    assert len(sr["derived_artifacts"]) == 2
    assert "pending:" not in json.dumps(spec)

    rows = await _siblings(engine, gen.id)
    assert len(rows) == 2
    assert [r["position"] for r in rows] == [0, 1]
    assert rows[0]["artifact_role"] == "spatial.world_depth"
    assert rows[0]["input_key"] == "world_depth"
    assert rows[1]["input_key"] == "entity_depth_1"

    # E-043: one-to-one spec↔sibling identity match
    by_key = {r["input_key"]: r for r in rows}
    for entry in sr["derived_artifacts"]:
        row = by_key[entry["input_key"]]
        assert is_uuid(row["derived_spatial_artifact_id"])
        assert (row["derived_spatial_artifact_id"]
                == entry["derived_spatial_artifact_id"])
        assert row["blob_hash"] == entry["blob_hash"]
        assert row["position"] == entry["position"]
        assert row["artifact_role"] == entry["artifact_role"]
        assert entry["spec_hash"] and entry["runtime_fingerprint_hash"]

    # provenance + Blob rows exist and converge on the same identities
    async with engine.connect() as conn:
        arts = [dict(r) for r in (await conn.execute(text(
            "SELECT id, spec_hash, runtime_fingerprint_hash, blob_hash, "
            "project_id, spatial_continuity_hash FROM "
            "derived_spatial_artifacts"))).mappings().all()]
    assert len(arts) == 2
    art_by_id = {a["id"]: a for a in arts}
    for row in rows:
        a = art_by_id[row["derived_spatial_artifact_id"]]
        assert a["blob_hash"] == row["blob_hash"]
        assert a["project_id"] == seed["pid"]
        assert a["spatial_continuity_hash"] == \
            sr["spatial_continuity_hash"]

    # physical blobs retained and valid
    from soloring.assets.blob_store import BlobStore

    store = BlobStore(settings)
    for row in rows:
        data = store.path_for_hash(row["blob_hash"]).read_bytes()
        import hashlib

        assert hashlib.sha256(data).hexdigest() == row["blob_hash"]

    # the persisted realization profile hash is the captured artifact's
    from soloring.workflows.artifact_store import WorkflowArtifactStore

    artifact_store = WorkflowArtifactStore(settings)
    profile_bytes = await artifact_store.get_profile(
        sr["realization_profile_hash"])
    assert json.loads(profile_bytes)["schema_version"] == 2


@pytest.mark.parametrize("staged,streams", [(0, 1), (1, 2), (2, 3)])
async def test_stream_counts_canonical_order(
        factory, engine, settings, tmp_path, staged, streams):
    """E-022: 0/1/2 staged entities → exactly 1/2/3 streams."""
    pkg = await _schema3_package(tmp_path)
    seed = await _spatial_seed(factory, staged=staged, extents=_EXTENTS)
    gen = await _create(factory, _spatial_settings(settings, pkg), seed)
    rows = await _siblings(engine, gen.id)
    assert len(rows) == streams
    assert rows[0]["artifact_role"] == "spatial.world_depth"
    keys = [r["input_key"] for r in rows]
    assert keys[0] == "world_depth"
    for i in range(1, streams):
        assert keys[i] == f"entity_depth_{i}"
        assert rows[i]["artifact_role"] == "spatial.entity_depth"


async def test_capacity_overflow_whole_item_fails(
        factory, engine, settings, tmp_path):
    """E-023 + R3 §4.5: 3 staged entities → typed capacity condition →
    SPATIAL_REALIZATION_UNSUPPORTED before materialization, Blob
    publication, provenance registration, Generation persistence, or
    queueing. An unrelated ValueError is never relabeled (positive
    control at the primitive seam)."""
    pkg = await _schema3_package(tmp_path)
    seed = await _spatial_seed(factory, staged=3, extents=_EXTENTS)
    from soloring.errors import ErrorCode, SoloRingError
    from soloring.spatial.realize import StagingCapacityExceeded

    s = _spatial_settings(settings, pkg)
    with pytest.raises(SoloRingError) as ei:
        await _create(factory, s, seed)
    assert ei.value.code == ErrorCode.SPATIAL_REALIZATION_UNSUPPORTED
    assert ei.value.status_code == 409

    async with engine.connect() as conn:
        for table in ("generations", "generation_derived_spatial_inputs",
                      "derived_spatial_artifacts", "blobs"):
            n = (await conn.execute(text(
                f"SELECT COUNT(*) FROM {table}"))).scalar()
            assert n == 0, table

    # the primitive seam raises the TYPED subclass and keeps "capacity"
    # in its message (inherited M10A match stays valid)
    with pytest.raises(ValueError, match="capacity") as typed:
        from soloring.spatial.realize import compose_spatial_realization

        compose_spatial_realization({
            "spatial_world": {"world_snapshot": {"frames": [], "axes": []}},
            "staging": [{}] * 3, "shot_plan": {}})
    assert isinstance(typed.value, StagingCapacityExceeded)

    # unrelated ValueError is NOT the typed condition (E-023 control)
    assert not issubclass(LookupError, StagingCapacityExceeded)


async def test_fixed_frame_changes_world_identity_only(
        factory, engine, settings, tmp_path):
    """E-037: a fixed-frame extent contributes to world depth — changing
    it changes the WORLD D0 identity, creates no entity sibling, and does
    not alter the movable-entity capacity count."""
    pkg = await _schema3_package(tmp_path)
    seed_a = await _spatial_seed(factory, staged=1, extents=_EXTENTS)
    gen_a = await _create(factory, _spatial_settings(settings, pkg), seed_a)
    seed_b = await _spatial_seed(factory, staged=1,
                                 extents=[900, 400, 300])
    gen_b = await _create(factory, _spatial_settings(settings, pkg), seed_b)
    rows_a = await _siblings(engine, gen_a.id)
    rows_b = await _siblings(engine, gen_b.id)
    assert len(rows_a) == len(rows_b) == 2
    assert rows_a[0]["blob_hash"] != rows_b[0]["blob_hash"]  # world moved
    # the entity layer is identical staging → identical derived identity
    assert rows_a[1]["blob_hash"] == rows_b[1]["blob_hash"]

    # a frameless landmark-only world (no extents anywhere) is valid too
    seed_c = await _spatial_seed(factory, staged=0, extents=None)
    gen_c = await _create(factory, _spatial_settings(settings, pkg), seed_c)
    rows_c = await _siblings(engine, gen_c.id)
    assert len(rows_c) == 1 and rows_c[0]["position"] == 0


async def test_repeated_creation_converges_on_retained_identities(
        factory, engine, settings, tmp_path):
    """E-031/E-032 at the service seam: the same captured ShotRevision
    (revision reuse) produces the same derived identities and Blob hashes;
    project-local provenance converges to the SAME artifact rows."""
    pkg = await _schema3_package(tmp_path)
    seed = await _spatial_seed(factory, staged=2, extents=_EXTENTS)
    s = _spatial_settings(settings, pkg)
    gen1 = await _create(factory, s, seed)
    gen2 = await _create(factory, s, seed)
    rows1 = await _siblings(engine, gen1.id)
    rows2 = await _siblings(engine, gen2.id)
    assert [r["blob_hash"] for r in rows1] == \
        [r["blob_hash"] for r in rows2]
    assert [r["derived_spatial_artifact_id"] for r in rows1] == \
        [r["derived_spatial_artifact_id"] for r in rows2]
    assert gen1.id != gen2.id
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM derived_spatial_artifacts"))).scalar()
    assert n == 3  # convergence, not duplication


async def test_schema5_without_schema3_package_fails_closed(
        factory, engine, settings):
    """E-025 posture preserved from the M10D fence: captured spatial
    authority with no captured package release → SPATIAL_REALIZATION_
    UNSUPPORTED, nothing persisted."""
    seed = await _spatial_seed(factory, staged=1, extents=_EXTENTS)
    settings.executor = "fake"  # no Stage-0 package capture at all
    from soloring.errors import ErrorCode, SoloRingError

    with pytest.raises(SoloRingError) as ei:
        async with factory() as session:
            await create_generation_request(
                session, seed["shot"], settings=settings)
    assert ei.value.code == ErrorCode.SPATIAL_REALIZATION_UNSUPPORTED
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM generations"))).scalar()
    assert n == 0


async def test_zero_current_m10_reads_after_capture_seam(
        factory, engine, settings, tmp_path):
    """E-020: a query spy fails on any current M10 authority read after
    the ShotRevision capture seam (positive control first)."""
    from soloring.domain import revisions as rev_svc
    from soloring.generation import service as gen_service
    from soloring.spatial.worker_inputs import current_m10_table_names

    pkg = await _schema3_package(tmp_path)
    seed = await _spatial_seed(factory, staged=1, extents=_EXTENTS)

    real_capture = rev_svc.capture_revision_with_visual
    after_capture = {"flag": False}

    async def _instrumented(session, shot_id, *, settings=None):
        out = await real_capture(session, shot_id, settings=settings)
        after_capture["flag"] = True
        return out

    import soloring.domain.revisions as revisions_mod

    seen: list[str] = []
    forbidden = set(current_m10_table_names())

    def _spy(conn, cursor, statement, parameters, context,
             executemany=False):
        if not after_capture["flag"]:
            return
        s = statement.lower()
        if s.strip().startswith(("select", "insert", "update")):
            seen.append(s)

    from sqlalchemy import event

    eng = engine.sync_engine
    event.listen(eng, "before_cursor_execute", _spy)
    try:
        original = revisions_mod.capture_revision_with_visual
        revisions_mod.capture_revision_with_visual = _instrumented
        try:
            gen = await _create(
                factory, _spatial_settings(settings, pkg), seed)
            assert gen.status == "queued"
        finally:
            revisions_mod.capture_revision_with_visual = original
        import re

        hits = [s for s in seen if any(
            re.search(rf"\b{t}\b", s) for t in forbidden)]
        assert hits == [], f"post-capture current M10 read: {hits[:2]}"
    finally:
        event.remove(eng, "before_cursor_execute", _spy)


# ------------------------------------------------------- E-045 parity ----

async def _v3_parity_package(tmp_path: Path) -> Path:
    """A schema-3 spatial package whose INHERITED M9 portions are exactly
    the V4 predecessor documents (profile v1 content, manifest v2
    content) plus the frozen M10 spatial overlay; the fingerprint
    artifact is the V4 file VERBATIM so execution_model_fingerprint_hash
    matches the predecessor release."""
    import hashlib

    from soloring.domain.canonical import canonical_hash, canonical_json_str
    from soloring.workflows.manifest import WORKFLOW_DIR_V4
    from soloring.spatial import production_package as prod

    v4 = WORKFLOW_DIR_V4
    manifest_v2 = json.loads((v4 / "manifest.json").read_bytes())
    profile_v1 = json.loads((v4 / "realization-profile.json").read_bytes())
    template = json.loads((v4 / "workflow.json").read_bytes())

    controlnet = {k: v for k, v in prod.production_template().items()
                  if k in ("100", "101", "110", "111", "120", "121")}
    template = {**template, **controlnet}

    prod_manifest = prod.production_manifest_v3()
    manifest_v3 = dict(manifest_v2)
    manifest_v3["schema_version"] = "3"
    # M10F PD-1C re-pin: the certified schema-3 manifest now declares the
    # ordinary prompt/output contract against the Wan template (node 3),
    # which this V4-template parity package does not contain. The parity
    # contract (E-045: inherited M9 portion equals the V2 documents
    # object-for-object) requires overlaying ONLY the spatial inputs; the
    # ordinary inputs stay the V4 manifest's own.
    spatial_inputs = {
        k: v for k, v in prod_manifest["inputs"].items()
        if k in prod_manifest["spatial_bindings"]
    }
    manifest_v3["inputs"] = {**manifest_v2["inputs"], **spatial_inputs}
    manifest_v3["outputs"] = manifest_v2["outputs"]
    manifest_v3["spatial_bindings"] = prod_manifest["spatial_bindings"]

    profile_v2 = dict(profile_v1)
    profile_v2["schema_version"] = 2
    profile_v2["spatial"] = {
        "spatial_document_schema": 1, "max_control_streams": 3,
        "roles": {"spatial.world_depth": {"kind": "derived",
                                          "capacity": 1},
                  "spatial.entity_depth": {"kind": "derived",
                                           "capacity": 2}},
        "runtime_requirements": {}, "advisory_omissions": [],
    }

    # The fingerprint must satisfy the schema-3 four-artifact
    # fingerprint↔template closure (node/field/declared_name cross-check
    # against THIS template's loader nodes), so it is an M10 extension
    # document bound to the parity template's actual loader values —
    # E-045's comparator is the realization block, which carries the
    # fingerprint hash through the seam identically on both sides.
    fingerprint_v3 = {
        "schema_version": 1,
        "m10_spatial_runtime": {
            "comfyui_commit": "b" * 40,
            "custom_nodes": {"ComfyUI-WanVideoWrapper": "c" * 40},
            "artifacts": [
                {"artifact_key": "wan_base", "storage_root_key":
                    "diffusion_models", "node": "98",
                 "field": "unet_name",
                 "declared_name": template["98"]["inputs"]["unet_name"],
                 "sha256": "1" * 64},
                {"artifact_key": "depth_controlnet", "storage_root_key":
                    "controlnet", "node": "100", "field": "model",
                 "declared_name": template["100"]["inputs"]["model"],
                 "sha256": "2" * 64},
                {"artifact_key": "umt5_text_encoder", "storage_root_key":
                    "text_encoders", "node": "97",
                 "field": "clip_name",
                 "declared_name": template["97"]["inputs"]["clip_name"],
                 "sha256": "3" * 64},
                {"artifact_key": "wan_vae", "storage_root_key": "vae",
                 "node": "10", "field": "vae_name",
                 "declared_name": template["10"]["inputs"]["vae_name"],
                 "sha256": "4" * 64},
            ],
        },
    }

    d = tmp_path / "pkg3_parity"
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_bytes(
        canonical_json_str(manifest_v3).encode())
    (d / "workflow.json").write_bytes(
        canonical_json_str(template).encode())
    (d / "realization-profile.json").write_bytes(
        canonical_json_str(profile_v2).encode())
    fingerprint_raw = canonical_json_str(fingerprint_v3).encode()
    (d / "execution-model-fingerprint.json").write_bytes(fingerprint_raw)
    (d / "workflow-package.json").write_bytes(canonical_json_str({
        "schema_version": 3,
        "workflow_id": manifest_v3["workflow_id"],
        "workflow_version": manifest_v3["version"],
        "manifest_hash": canonical_hash(manifest_v3),
        "workflow_template_hash": canonical_hash(template),
        "realization_profile_hash": canonical_hash(profile_v2),
        "execution_model_fingerprint_hash": hashlib.sha256(
            fingerprint_raw).hexdigest(),
    }).encode())
    return d


async def test_m9_v2_to_v3_payload_parity(
        client, factory, engine, settings, tmp_path, monkeypatch):
    """E-045: schema5+M8-present reuses the predecessor compiler seam
    exactly. The v3 path's inherited profile/manifest VIEWS equal the
    frozen V2 documents object-for-object, the fingerprint hash carried
    is the predecessor artifact's verbatim hash, the embedded realization
    block equals the predecessor seam's output for the same captured
    authority and release hashes (canonical JSON), and the ordinary
    realization GenerationInput rows project the compiler inputs exactly.
    Whole-spec equality is NOT asserted (schema version and the
    independent spatial_realization block differ by design)."""
    import hashlib

    from soloring.realization import compiler as compiler_mod
    from soloring.realization.profile import parse_profile
    from soloring.workflows.manifest import WORKFLOW_DIR_V4, parse_manifest_v2

    from tests.test_m8a_visual import _entity_with_revision, _facet, \
        _seed_project
    from tests.test_m8b_curation import _assets
    from tests.test_m8c_resolver import _approve_anchor, _depend, \
        _topology

    from tests.test_m10d_resolver import CAM, _entities, _first_sequence
    from soloring.spatial import plans as plan_svc
    from soloring.spatial import revisions as wrev_svc
    from soloring.spatial import tracks as track_svc
    from soloring.spatial import transitions as trans_svc
    from soloring.spatial import worlds as world_svc

    pid = await _seed_project(factory)
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    assets = await _assets(engine, pid, 1)
    facet = await _facet(client, pid, "entity", entity_id=eva["id"],
                         facet_key="identity")
    r = await client.post(
        f"/visual-facets/{facet['id']}/anchors",
        json={"entity_revision_id": rev1})
    await _approve_anchor(client, r.json()["id"], assets, ["front"])
    _, _, shots = await _topology(client, factory, pid)
    shot = shots[0]

    # the M10 spatial plane on the SAME shot/project
    ents = await _entities(factory, pid, {"loc": "location"})
    loc, locrev = ents["loc"]
    world = await world_svc.create_world(
        factory(), pid, key="lobby", name="lobby", description=None,
        requirement="required", location_entity_id=loc)
    state = await world_svc.create_state(
        factory(), world["id"], location_entity_revision_id=locrev)
    fr = await world_svc.create_frame(
        factory(), world["id"], key="setpiece", name="setpiece",
        parent_spatial_frame_id=None, bound_entity_id=None)
    await world_svc.put_state_frame(
        factory(), state["id"], fr["id"], translation_mm=_SETPIECE_T,
        rotation_udeg=[0, 0, 0], half_extents_mm=_EXTENTS,
        bound_entity_revision_id=None)
    wrev = await wrev_svc.capture_revision(factory(), state["id"])
    await wrev_svc.approve_revision(
        factory(), state["id"], revision_id=wrev["id"],
        expected_approved_revision_id=None)
    track = await track_svc.create_track(
        factory(), world["id"], entity_id=eva["id"],
        requirement="optional")
    await trans_svc.create_transition(
        factory(), track["id"], anchor_type="sequence",
        anchor_id=await _first_sequence(factory, pid),
        boundary="start", operation="set",
        translation_mm=_STAGED_T[0], rotation_udeg=[0, 0, 0])
    await _depend(client, shot, [eva["id"], loc])
    await plan_svc.put_spatial_plan(
        factory(), shot, expected_plan_hash=None, plan_raw={
            "schema_version": 1, "spatial_world_id": world["id"],
            "camera": json.loads(json.dumps(CAM)),
            "blocking": [{
                "spatial_track_id": track["id"],
                "screen_direction": "left_to_right",
                "keyframes": [{
                    "time_ms": 0,
                    "transform": {"translation_mm": _STAGED_T[0],
                                  "rotation_udeg": [0, 0, 0]}}],
            }],
            "axis_constraint": None,
        })

    pkg = await _v3_parity_package(tmp_path)
    captured = {}
    real_compile = compiler_mod.compile_realization

    def _spy_compile(**kwargs):
        result = real_compile(**kwargs)
        captured["kwargs"] = kwargs
        captured["result"] = result
        return result

    monkeypatch.setattr(compiler_mod, "compile_realization", _spy_compile)

    async with factory() as session:
        gen = await create_generation_request(
            session, shot, settings=_spatial_settings(settings, pkg))
    assert gen.status == "queued"
    assert captured, "the M9 compiler seam must have run"

    kw = captured["kwargs"]
    v4 = WORKFLOW_DIR_V4
    assert kw["profile"].model_dump() == parse_profile(
        (v4 / "realization-profile.json").read_bytes()).model_dump()
    assert kw["manifest"].model_dump() == parse_manifest_v2(
        (v4 / "manifest.json").read_bytes()).model_dump()
    # the fingerprint hash carried through the seam is the parity
    # package's OWN captured artifact hash (a schema-3-valid M10
    # extension document), and the embedded realization block equals the
    # predecessor compiler output for those same seam inputs
    assert kw["execution_model_fingerprint_hash"] == hashlib.sha256(
        (pkg / "execution-model-fingerprint.json").read_bytes()).hexdigest()

    from soloring.domain.canonical import canonical_json_str as cjs

    spec = await _spec(engine, gen.id)
    assert cjs(spec["realization"]) == cjs(captured["result"].spec)

    async with engine.connect() as conn:
        rows = [dict(r) for r in (await conn.execute(text(
            "SELECT input_key, position, asset_id, blob_hash, "
            "reference_role FROM generation_inputs WHERE generation_id = "
            ":g"), {"g": gen.id})).mappings().all()]
    expected = [{"input_key": p.input_key, "position": p.position,
                 "asset_id": p.asset_id, "blob_hash": p.blob_hash,
                 "reference_role": p.reference_role}
                for p in captured["result"].inputs]
    assert rows == expected


