"""M10F-B — adversarial whole-M10 gate, part 1 (R5 §§8.3, 8.5.2, 8.6, 9).

Exact error-map negatives for the 14 durable codes no predecessor test
asserts (F-034/F-035), the reserved-vocabulary no-raiser structural scan,
the divergent same-spec/runtime D0 registration race at the real
post-`BEGIN IMMEDIATE` parking seam (§8.5.2, both meaningful commit
orders), the no-authority-transfer write spy over the exact frozen
47-table inventory with a `shot_revisions` positive control plus
owner-model inventory parity (§8.6), and the Exact-Rerun current-read
isolation spy with a deliberate positive control (§9).

§8.4 cells 12/22/23/24 and the class-19 worker/package race live in
`tests/test_m10f_adversarial_worker.py` (they need the hermetic worker
harness).
"""

from __future__ import annotations

import asyncio
import contextvars
import hashlib
import uuid

import pytest
from sqlalchemy import text

from soloring.errors import SoloRingError
from soloring.settings import BASE_DIR

from tests.test_m10b_world_authority import (
    _add_frames,
    _make_world_with_state,
    factory_session,
)

KINDS = frozenset({"test.depth"})
MEDIA = frozenset({"image/png"})
ALGS = frozenset({("soloring.boxdepth.rasterizer", "1.0.0")})


# ---------------------------------------------------------------------------
# §8.3 — exact error-map negatives (14 previously unasserted codes)
# ---------------------------------------------------------------------------


async def test_error_world_state_invalid_nonuuid_location_revision(factory):
    from soloring.spatial import worlds as world_svc

    _, eid, rid, world, _state = await _make_world_with_state(factory)
    with pytest.raises(SoloRingError) as e:
        await world_svc.create_state(
            factory_session(factory), world["id"],
            location_entity_revision_id="not-a-uuid")
    assert e.value.code == "SPATIAL_WORLD_STATE_INVALID"


async def test_error_frame_invalid_transform_shape(factory):
    from soloring.spatial import worlds as world_svc

    pid, eid, rid, world, state = await _make_world_with_state(factory)
    f = await world_svc.create_frame(
        factory_session(factory), world["id"], key="f", name="F",
        parent_spatial_frame_id=None, bound_entity_id=None)
    with pytest.raises(SoloRingError) as e:
        await world_svc.put_state_frame(
            factory_session(factory), state["id"], f["id"],
            translation_mm=[0, 0],  # not a 3-vector
            rotation_udeg=[0, 0, 0],
            half_extents_mm=None, bound_entity_revision_id=None)
    assert e.value.code == "SPATIAL_FRAME_INVALID"


async def test_error_frame_cycle_planted_parent_graph(factory):
    """STRUCTURAL: a cyclic parent graph is planted directly, then the
    production cycle walk (frame patch seam) rejects it."""
    from soloring.spatial import worlds as world_svc

    pid, eid, rid, world, state = await _make_world_with_state(factory)
    f1, f2 = await _add_frames(factory, world["id"], state["id"], n=2)
    async with factory() as s:
        await s.execute(text(
            "UPDATE spatial_frames SET parent_spatial_frame_id = :p "
            "WHERE id = :c"), {"p": f2, "c": f1})
        await s.execute(text(
            "UPDATE spatial_frames SET parent_spatial_frame_id = :p "
            "WHERE id = :c"), {"p": f1, "c": f2})
        await s.commit()
    with pytest.raises(SoloRingError) as e:
        await world_svc.patch_frame(
            factory_session(factory), f1, name="renamed")
    assert e.value.code == "SPATIAL_FRAME_CYCLE"


async def test_error_axis_invalid_frame_is_state_axis_endpoint(factory):
    from soloring.spatial import worlds as world_svc

    pid, eid, rid, world, state = await _make_world_with_state(factory)
    fa, fb = await _add_frames(factory, world["id"], state["id"], n=2)
    axis = await world_svc.create_axis(
        factory_session(factory), world["id"], key="ax", name="AX")
    await world_svc.put_state_axis(
        factory_session(factory), state["id"], axis["id"],
        a_frame_id=fa, b_frame_id=fb)
    with pytest.raises(SoloRingError) as e:
        await world_svc.delete_state_frame(
            factory_session(factory), state["id"], fa)
    assert e.value.code == "SPATIAL_AXIS_INVALID"


async def test_error_world_revision_not_found(factory):
    from soloring.spatial import revisions as wrev_svc

    pid, eid, rid, world, state = await _make_world_with_state(factory)
    with pytest.raises(SoloRingError) as e:
        await wrev_svc.approve_revision(
            factory_session(factory), state["id"],
            revision_id=str(uuid.uuid4()),
            expected_approved_revision_id=None)
    assert e.value.code == "SPATIAL_WORLD_REVISION_NOT_FOUND"


async def test_error_world_approval_conflict_stale_expected(factory):
    from soloring.spatial import revisions as wrev_svc

    pid, eid, rid, world, state = await _make_world_with_state(factory)
    rev = await wrev_svc.capture_revision(factory_session(factory),
                                          state["id"])
    with pytest.raises(SoloRingError) as e:
        await wrev_svc.approve_revision(
            factory_session(factory), state["id"], revision_id=rev["id"],
            expected_approved_revision_id=str(uuid.uuid4()))
    assert e.value.code == "SPATIAL_WORLD_APPROVAL_CONFLICT"


async def test_error_track_invalid_cross_project_world(factory, engine):
    from soloring.spatial.staging import resolve_effective_staging
    from tests.test_m10d_resolver import _entities, _shot

    pid = str(uuid.uuid4())
    async with factory() as s:
        await s.execute(text(
            "INSERT INTO projects (id, name, created_at, updated_at) "
            "VALUES (:p, 'P', 't', 't')"), {"p": pid})
        await s.commit()
    ents = await _entities(factory, pid, {"loc": "location"})
    shot = await _shot(factory, pid, [ents["loc"][0]], assigned=True)

    # world from the helper's own (different) project
    _, eid, lrev, world, _state = await _make_world_with_state(factory)
    async with engine.connect() as conn:
        world_project = (await conn.execute(text(
            "SELECT project_id FROM spatial_worlds WHERE id = :w"),
            {"w": world["id"]})).scalar()
    assert world_project != pid

    with pytest.raises(SoloRingError) as e:
        async with engine.connect() as conn:
            await resolve_effective_staging(
                conn, shot_id=shot, spatial_world_id=world["id"],
                resolved_entity_revisions={})
    assert e.value.code == "SPATIAL_TRACK_INVALID"


async def test_error_shot_plan_conflict_stale_expected_hash(factory):
    import json

    from tests.test_m10d_resolver import CAM
    from tests.test_m10e_generation import _spatial_seed
    from soloring.spatial import plans as plan_svc

    seed = await _spatial_seed(factory, staged=0)
    with pytest.raises(SoloRingError) as e:
        await plan_svc.put_spatial_plan(
            factory_session(factory), seed["shot"],
            expected_plan_hash="0" * 64,
            plan_raw={
                "schema_version": 1,
                "spatial_world_id": seed["world"]["id"],
                "camera": json.loads(json.dumps(CAM)),
                "blocking": [],
                "axis_constraint": None,
            })
    assert e.value.code == "SPATIAL_SHOT_PLAN_CONFLICT"


# --- derived family (prepare/parse seams) ------------------------------------


def _spec():
    from tests.test_m10a_derived import _spec as m10a_spec

    return m10a_spec()


def _runtime():
    from tests.test_m10a_derived import _runtime as m10a_runtime

    return m10a_runtime()


def test_derived_error_kind_unsupported():
    from soloring.spatial.derived import prepare_derived_artifact

    spec = _spec()
    spec["artifact_kind"] = "unsupported.kind"
    with pytest.raises(SoloRingError) as e:
        prepare_derived_artifact(
            spec, _runtime(), "c" * 64, allowed_artifact_kinds=KINDS,
            allowed_media_types=MEDIA, allowed_algorithms=ALGS)
    assert e.value.code == "DERIVED_SPATIAL_KIND_UNSUPPORTED"

    spec2 = _spec()
    spec2["derivation"]["algorithm_id"] = "other.algorithm"
    with pytest.raises(SoloRingError) as e:
        prepare_derived_artifact(
            spec2, _runtime(), "c" * 64, allowed_artifact_kinds=KINDS,
            allowed_media_types=MEDIA, allowed_algorithms=ALGS)
    assert e.value.code == "DERIVED_SPATIAL_KIND_UNSUPPORTED"


def test_derived_error_runtime_unpinnable():
    from soloring.spatial.derived import parse_runtime_fingerprint

    with pytest.raises(SoloRingError) as e:
        parse_runtime_fingerprint({"schema_version": "bogus"})
    assert e.value.code == "DERIVED_SPATIAL_RUNTIME_UNPINNABLE"
    with pytest.raises(SoloRingError) as e:
        parse_runtime_fingerprint("not-json")
    assert e.value.code == "DERIVED_SPATIAL_RUNTIME_UNPINNABLE"


def test_derived_error_output_invalid():
    from soloring.spatial.derived import prepare_derived_artifact

    spec = _spec()
    spec["output_contract"]["media_type"] = "video/mp4"
    with pytest.raises(SoloRingError) as e:
        prepare_derived_artifact(
            spec, _runtime(), "c" * 64, allowed_artifact_kinds=KINDS,
            allowed_media_types=MEDIA, allowed_algorithms=ALGS)
    assert e.value.code == "DERIVED_SPATIAL_OUTPUT_INVALID"

    with pytest.raises(SoloRingError) as e:
        prepare_derived_artifact(
            _spec(), _runtime(), "NOT-CANONICAL",
            allowed_artifact_kinds=KINDS, allowed_media_types=MEDIA,
            allowed_algorithms=ALGS)
    assert e.value.code == "DERIVED_SPATIAL_OUTPUT_INVALID"


def test_reserved_derived_codes_have_no_raiser():
    """NOT-APPLICABLE-SOURCE-FIT substitute proof for
    DERIVED_SPATIAL_MATERIALIZATION_FAILED / _CAPTURE_CONFLICT /
    _HARD_COMPONENT_LOSS: reserved frozen vocabulary with no production
    raise site in the published tree. If a raiser appears, the proof map
    must be revised before M10F closure can claim these codes TEST."""
    server = BASE_DIR / "server" / "soloring"
    reserved = (
        "DERIVED_SPATIAL_MATERIALIZATION_FAILED",
        "DERIVED_SPATIAL_CAPTURE_CONFLICT",
        "DERIVED_SPATIAL_HARD_COMPONENT_LOSS",
    )
    for code in reserved:
        for py in server.rglob("*.py"):
            src = py.read_text(encoding="utf-8")
            if f'"{code}"' in src or f"'{code}'" in src:
                assert py.name in ("error_codes.py", "errors.py"), (
                    f"{code} gained a mention/raise site in {py}")
    ec = (server / "spatial" / "error_codes.py").read_text(encoding="utf-8")
    for code in reserved:
        assert code in ec  # vocabulary itself stays frozen


# ---------------------------------------------------------------------------
# §8.5.2 — divergent same-spec/runtime D0 registration
# ---------------------------------------------------------------------------


async def test_divergent_d0_registration_parked_interleaving(
        factory, engine, settings):
    """Leader's REAL `BEGIN IMMEDIATE` completes, then parks holding the
    write transaction; the follower signals arrival immediately before
    its own REAL `BEGIN IMMEDIATE` (which blocks on the writer lock) and,
    after the leader commits, must fail DERIVED_SPATIAL_NONDETERMINISTIC.
    No sleep, PRAGMA guess, or progress handler establishes order."""
    from sqlalchemy.ext.asyncio import AsyncConnection

    from soloring.assets.blob_store import BlobStore
    from soloring.spatial.derived import (
        prepare_derived_artifact,
        register_derived_artifact,
    )
    from tests.test_m10a_derived import _runtime, _spec

    store = BlobStore(settings)
    pid = str(uuid.uuid4())

    def _place(data: bytes) -> str:
        bh = hashlib.sha256(data).hexdigest()
        p = store.path_for_hash(bh)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return bh

    b1, b2 = _place(b"divergent-leader"), _place(b"divergent-follower")
    async with engine.begin() as c:
        await c.execute(text(
            "INSERT INTO projects (id, name, created_at, updated_at) "
            "VALUES (:i, 'P', 't', 't')"), {"i": pid})
        for bh, data in ((b1, b"divergent-leader"),
                         (b2, b"divergent-follower")):
            await c.execute(text(
                "INSERT OR IGNORE INTO blobs (hash, path, size_bytes) "
                "VALUES (:h, :p, :n)"),
                {"h": bh, "p": store.relative_path_for_hash(bh),
                 "n": len(data)})

    leader_prepared = prepare_derived_artifact(
        _spec(), _runtime(), b1, allowed_artifact_kinds=KINDS,
        allowed_media_types=MEDIA, allowed_algorithms=ALGS)
    follower_prepared = prepare_derived_artifact(
        _spec(), _runtime(), b2, allowed_artifact_kinds=KINDS,
        allowed_media_types=MEDIA, allowed_algorithms=ALGS)
    assert leader_prepared.spec_hash == follower_prepared.spec_hash
    assert leader_prepared.runtime_hash == follower_prepared.runtime_hash

    role_var = contextvars.ContextVar("m10f_divergent_role", default=None)
    leader_acquired = asyncio.Event()
    follower_at_seam = asyncio.Event()
    real_exec = AsyncConnection.exec_driver_sql

    async def traced_exec(self, statement, *a, **k):
        is_begin = (isinstance(statement, str)
                    and statement.strip().upper().startswith("BEGIN"))
        role = role_var.get()
        if is_begin and role == "leader":
            result = await real_exec(self, statement, *a, **k)
            leader_acquired.set()
            await asyncio.wait_for(follower_at_seam.wait(), 30)
            return result  # production code proceeds to SELECT/INSERT/COMMIT
        if is_begin and role == "follower":
            follower_at_seam.set()  # arrival signalled BEFORE the real begin
            return await real_exec(self, statement, *a, **k)
        return await real_exec(self, statement, *a, **k)

    AsyncConnection.exec_driver_sql = traced_exec
    follower_failure: list = []
    try:
        async def _leader():
            role_var.set("leader")
            async with factory() as s:
                await register_derived_artifact(
                    s, store, pid, leader_prepared)

        async def _follower():
            await leader_acquired.wait()
            role_var.set("follower")
            async with factory() as s:
                try:
                    await register_derived_artifact(
                        s, store, pid, follower_prepared)
                except SoloRingError as exc:
                    follower_failure.append(exc.code)

        leader_task = asyncio.create_task(_leader())
        follower_task = asyncio.create_task(_follower())
        await asyncio.wait_for(leader_task, 60)
        await asyncio.wait_for(follower_task, 60)
    finally:
        AsyncConnection.exec_driver_sql = real_exec

    assert follower_failure == ["DERIVED_SPATIAL_NONDETERMINISTIC"], (
        follower_failure)


async def test_divergent_d0_registration_leader_commits_first(
        factory, engine, settings):
    """The second meaningful order: leader already committed; the next
    divergent registration (fresh session, real seam) fails
    NONDETERMINISTIC. (The cross-project variant is frozen by M10A's
    test_global_d0_different_blob_fails.)"""
    from soloring.assets.blob_store import BlobStore
    from soloring.spatial.derived import (
        prepare_derived_artifact,
        register_derived_artifact,
    )
    from tests.test_m10a_derived import _runtime, _spec

    store = BlobStore(settings)
    pid = str(uuid.uuid4())

    def _place(data: bytes) -> str:
        bh = hashlib.sha256(data).hexdigest()
        p = store.path_for_hash(bh)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return bh

    b1 = _place(b"order-leader")
    async with engine.begin() as c:
        await c.execute(text(
            "INSERT INTO projects (id, name, created_at, updated_at) "
            "VALUES (:i, 'P', 't', 't')"), {"i": pid})
        await c.execute(text(
            "INSERT OR IGNORE INTO blobs (hash, path, size_bytes) "
            "VALUES (:h, :p, :n)"),
            {"h": b1, "p": store.relative_path_for_hash(b1), "n": 15})
    async with factory() as s:
        await register_derived_artifact(
            s, store, pid, prepare_derived_artifact(
                _spec(), _runtime(), b1, allowed_artifact_kinds=KINDS,
                allowed_media_types=MEDIA, allowed_algorithms=ALGS))

    b2 = _place(b"order-follower")
    async with engine.begin() as c:
        await c.execute(text(
            "INSERT OR IGNORE INTO blobs (hash, path, size_bytes) "
            "VALUES (:h, :p, :n)"),
            {"h": b2, "p": store.relative_path_for_hash(b2), "n": 16})
    async with factory() as s:
        with pytest.raises(SoloRingError) as e:
            await register_derived_artifact(
                s, store, pid, prepare_derived_artifact(
                    _spec(), _runtime(), b2, allowed_artifact_kinds=KINDS,
                    allowed_media_types=MEDIA, allowed_algorithms=ALGS))
    assert e.value.code == "DERIVED_SPATIAL_NONDETERMINISTIC"


# ---------------------------------------------------------------------------
# §8.6 — no-authority-transfer write spy + inventory parity
# ---------------------------------------------------------------------------

FORBIDDEN_AUTHORITY_TABLES = frozenset({
    # narrative / Shot authoring context + immutable parent history
    "shots", "shot_references", "shot_revisions", "sequences", "scenes",
    # M7 semantic continuity authority/history
    "creative_entities", "entity_revisions", "character_revision_specs",
    "location_revision_specs", "prop_revision_specs",
    "costume_revision_specs", "vehicle_revision_specs",
    "entity_approved_revisions", "shot_entity_dependencies",
    "shot_revision_entity_dependencies", "continuity_features",
    "continuity_feature_transitions", "continuity_predicates",
    "continuity_relations", "continuity_relation_transitions",
    "shot_revision_feature_states", "shot_revision_relation_states",
    # M8 visual authority/history
    "visual_facets", "visual_facet_value_policies", "visual_anchors",
    "visual_anchor_items", "visual_anchor_revisions",
    "visual_anchor_revision_items", "shot_revision_visual_anchors",
    "shot_revision_visual_anchor_items",
    # M10 spatial authority/history
    "spatial_worlds", "spatial_world_states", "spatial_frames",
    "spatial_world_state_frames", "spatial_axes",
    "spatial_world_state_axes", "spatial_world_revisions",
    "spatial_world_revision_frames", "spatial_world_revision_axes",
    "spatial_tracks", "spatial_transitions", "shot_spatial_plans",
    "shot_revision_spatial_worlds", "shot_revision_spatial_track_states",
    "shot_revision_spatial_plans",
})


def _authority_write_spy(engine, violations: list):
    from sqlalchemy import event

    def before_cursor_execute(
            conn, cursor, statement, parameters, context, executemany):
        if not isinstance(statement, str):
            return
        head = statement.lstrip()[:80].upper()
        if not head.startswith(("INSERT", "UPDATE", "DELETE", "REPLACE")):
            return
        for table in FORBIDDEN_AUTHORITY_TABLES:
            t = table.upper()
            if (f"INTO {t} " in head or f"INTO {t}(" in head
                    or head.startswith(f"UPDATE {t} ")
                    or (head.startswith("DELETE")
                        and f"FROM {t} " in head)):
                violations.append((table, statement[:120]))
                return

    event.listen(engine.sync_engine, "before_cursor_execute",
                 before_cursor_execute)
    return lambda: event.remove(
        engine.sync_engine, "before_cursor_execute",
        before_cursor_execute)


async def test_no_authority_transfer_write_spy(factory, engine, settings,
                                               tmp_path):
    """§8.6 scope: the spy covers the D0 materialization/registration and
    Exact Rerun paths — NOT the legitimate first ShotRevision capture
    (that is production authoring). A converged SECOND create reuses the
    already-captured revision, so its realization/registration legs must
    write zero authority rows."""
    from tests.test_m10e_generation import _EXTENTS, _create, _spatial_seed
    from tests.test_m10e_package3_production import _schema3_package

    pkg = await _schema3_package(tmp_path)
    settings.executor = "comfy"
    settings.workflow_package_dir = pkg
    seed = await _spatial_seed(factory, staged=1, extents=_EXTENTS)
    gen = await _create(factory, settings, seed)  # legitimate capture
    assert gen.status == "queued"

    violations: list = []
    detach = _authority_write_spy(engine, violations)
    try:
        gen2 = await _create(factory, settings, seed)  # converged capture
        assert gen2.status == "queued"
        assert gen2.shot_revision_id == gen.shot_revision_id

        from soloring.generation import rerun

        async with engine.connect() as c:
            await c.execute(text(
                "UPDATE generations SET status='succeeded', completed_at='t' "
                "WHERE id = :g"), {"g": gen.id})
            await c.commit()
        async with factory() as s:
            await rerun.create_rerun(s, gen.id)
    finally:
        detach()
    assert violations == [], violations[:4]


async def test_no_authority_transfer_positive_control_trips_on_shot_revisions(
        factory, engine):
    """Deliberate positive control: a rollback-scoped write targeting
    `shot_revisions` (with a REAL parent Shot) MUST trip the spy."""
    from tests.test_m10d_resolver import _entities, _shot

    pid = str(uuid.uuid4())
    async with factory() as s:
        await s.execute(text(
            "INSERT INTO projects (id, name, created_at, updated_at) "
            "VALUES (:p, 'P', 't', 't')"), {"p": pid})
        await s.commit()
    ents = await _entities(factory, pid, {"loc": "location"})
    shot = await _shot(factory, pid, [ents["loc"][0]], assigned=True)

    violations: list = []
    detach = _authority_write_spy(engine, violations)
    try:
        async with engine.connect() as c:
            await c.exec_driver_sql("BEGIN IMMEDIATE")
            await c.execute(text(
                "INSERT INTO shot_revisions (id, shot_id, revision_number, "
                "snapshot_json, snapshot_hash, created_at) VALUES "
                "(:i, :s, 99, '{}', :h, 't')"),
                {"i": str(uuid.uuid4()), "s": shot, "h": "0" * 64})
            await c.exec_driver_sql("ROLLBACK")
    finally:
        detach()
    assert any(v[0] == "shot_revisions" for v in violations), violations


async def test_authority_write_inventory_matches_owner_models():
    """The explicit §8.6 set equals the owner-model-derived family,
    excluding only the two M10E execution-provenance tables."""
    from soloring.continuity import models as continuity_models
    from soloring.db.base import Base
    from soloring.domain import models as domain_models
    from soloring.narrative import models as narrative_models
    from soloring.spatial import models as spatial_models
    from soloring.visual import models as visual_models

    def tables_of(module, only_names=None):
        out = set()
        for name in dir(module):
            obj = getattr(module, name)
            if (isinstance(obj, type) and issubclass(obj, Base)
                    and obj is not Base
                    and getattr(obj, "__module__", "") == module.__name__
                    and (only_names is None or name in only_names)):
                out.add(obj.__tablename__)
        return out

    exclusions = {"derived_spatial_artifacts",
                  "generation_derived_spatial_inputs"}
    derived = tables_of(spatial_models, {
        "DerivedSpatialArtifact", "GenerationDerivedSpatialInput"})
    assert derived == exclusions

    expected = (
        tables_of(domain_models,
                  {"Shot", "ShotReference", "ShotRevision"})
        | tables_of(narrative_models)
        | tables_of(continuity_models)
        | tables_of(visual_models)
        | (tables_of(spatial_models) - exclusions)
    )
    assert expected == set(FORBIDDEN_AUTHORITY_TABLES), (
        sorted(expected ^ set(FORBIDDEN_AUTHORITY_TABLES)))


# ---------------------------------------------------------------------------
# §9 — historical read isolation (Exact Rerun zero current-M10 reads)
# ---------------------------------------------------------------------------


async def test_rerun_current_read_isolation_with_positive_control(
        factory, engine, settings, tmp_path):
    from sqlalchemy import event

    from soloring.generation import rerun
    from soloring.spatial.worker_inputs import current_m10_table_names

    from tests.test_m10e_generation import _EXTENTS, _create, _spatial_seed
    from tests.test_m10e_package3_production import _schema3_package

    pkg = await _schema3_package(tmp_path)
    settings.executor = "comfy"
    settings.workflow_package_dir = pkg
    seed = await _spatial_seed(factory, staged=1, extents=_EXTENTS)
    gen = await _create(factory, settings, seed)
    async with engine.connect() as c:
        await c.execute(text(
            "UPDATE generations SET status='succeeded', completed_at='t' "
            "WHERE id = :g"), {"g": gen.id})
        await c.commit()

    forbidden = tuple(current_m10_table_names())
    assert forbidden, "current M10 table list must not be empty"
    hits: list = []

    def spy(conn, cursor, statement, parameters, context, executemany):
        if not isinstance(statement, str):
            return
        upper = statement.upper()
        if not upper.lstrip().startswith("SELECT"):
            return
        for t in forbidden:
            if t.upper() in upper:
                hits.append((t, statement[:100]))
                return

    event.listen(engine.sync_engine, "before_cursor_execute", spy)
    try:
        async with factory() as s:
            new = await rerun.create_rerun(s, gen.id)
        assert new.id != gen.id
        assert hits == [], hits[:2]

        # deliberate positive control: a real current-authority read
        # through the same engine trips the spy
        async with engine.connect() as c:
            await c.execute(text(
                "SELECT id FROM spatial_worlds LIMIT 1"))
        assert hits, "spy failed to observe a current M10 read"
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", spy)
