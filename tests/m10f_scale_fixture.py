"""M10F-D canonical representative scale fixture (R6 §11.1).

One deterministic legal Project with ~2,500 Shots and the full M10 target
family in one database. Every identity is derived (uuid5 of a canonical
logical name under the frozen root namespace); random-looking scalars use
the frozen PRNG seed 0x534F4C4F52494E47 and never define identity;
wall-clock timestamps and SQLite rowids are excluded by the fixture-owned
inventory grammar.

Designated target-family semantics are built through production services;
bulk narrative volume (non-target shots) uses direct SQL with explicit
legality assertions (FK check + counts). Generation history spans
workflow-spec v1/v2/v3 targets, including a schema-5/schema-3 target with
real D0 provenance.
"""

from __future__ import annotations

import hashlib
import json
import random
import uuid
from pathlib import Path

from sqlalchemy import text

ROOT_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL, "https://soloring.local/m10f/scale-fixture/v1")
PRNG_SEED = 0x534F4C4F52494E47

# Deterministic cameras derive from the frozen resolver CAM with
# identity-stable perturbations (constants, not PRNG).
from tests.test_m10d_resolver import CAM as _FROZEN_CAM  # noqa: E402


def _camera(variant: int) -> dict:
    cam = json.loads(json.dumps(_FROZEN_CAM))
    if variant % 2:  # reverse-angle variant: mirrored Z position
        t = cam["keyframes"][0]["transform"]["translation_mm"]
        cam["keyframes"][0]["transform"]["translation_mm"] = [
            t[0], t[1], -t[2]]
    return cam


class deterministic_uuid4:
    """§11.1: no uuid4 may define fixture identity. Services mint ids via
    uuid.uuid4 at runtime; patching the uuid module makes EVERY minted id
    a deterministic uuid5 of a canonical auto-name, regardless of how the
    importing module bound `new_uuid`/`uuid4` at import time."""

    _counter = 0

    def __enter__(self):
        import uuid as _uuid

        self._real = _uuid.uuid4
        fixture = self

        def _deterministic():
            fixture._counter += 1
            return uuid.uuid5(
                ROOT_NAMESPACE, f"auto:{fixture._counter}")

        _uuid.uuid4 = _deterministic
        # modules that bound uuid4 directly at import time
        import soloring.generation.repository as _repo

        self._repo_uuid4 = _repo.uuid4
        _repo.uuid4 = _deterministic
        return self

    def __exit__(self, *exc):
        import uuid as _uuid

        _uuid.uuid4 = self._real
        import soloring.generation.repository as _repo

        _repo.uuid4 = self._repo_uuid4
        return False


def det_id(logical_name: str) -> str:
    """uuid5 identity under the frozen fixture namespace."""
    return str(uuid.uuid5(ROOT_NAMESPACE, logical_name))


def _rng() -> random.Random:
    return random.Random(PRNG_SEED)


# ---------------------------------------------------------------------------
# Identity-bearing inventory grammar (§11.1 digest)
# ---------------------------------------------------------------------------

# table -> identity-bearing columns (timestamps/rowids excluded by design)
INVENTORY_GRAMMAR: dict[str, tuple[str, ...]] = {
    "projects": ("id", "name"),
    "sequences": ("id", "project_id", "position", "title"),
    "scenes": ("id", "sequence_id", "position", "title"),
    "shots": ("id", "project_id", "scene_id", "position", "subject"),
    "shot_references": ("id", "shot_id", "asset_id", "role"),
    "shot_entity_dependencies": ("shot_id", "entity_id"),
    "creative_entities": ("id", "project_id", "kind", "name"),
    "entity_revisions": ("id", "entity_id", "revision_number"),
    "entity_approved_revisions": ("entity_id", "entity_revision_id"),
    "continuity_features": ("id", "project_id", "facet_key"),
    "visual_facets": ("id", "project_id", "facet_key", "entity_id"),
    "visual_anchors": ("id", "visual_facet_id", "entity_revision_id"),
    "visual_anchor_revisions": ("id", "visual_anchor_id",
                                "revision_number", "snapshot_hash"),
    "spatial_worlds": ("id", "project_id", "key", "requirement",
                       "location_entity_id"),
    "spatial_world_states": ("id", "spatial_world_id",
                             "location_entity_revision_id",
                             "approved_revision_id"),
    "spatial_frames": ("id", "spatial_world_id", "key",
                       "parent_spatial_frame_id", "bound_entity_id"),
    "spatial_world_revisions": ("id", "spatial_world_state_id",
                                "revision_number", "snapshot_hash"),
    "spatial_axes": ("id", "spatial_world_id", "key"),
    "spatial_tracks": ("id", "spatial_world_id", "entity_id",
                       "requirement"),
    "spatial_transitions": ("id", "spatial_track_id", "anchor_type",
                            "anchor_id", "boundary", "operation",
                            "translation_mm", "rotation_udeg"),
    "shot_spatial_plans": ("shot_id", "plan_hash"),
    "shot_revisions": ("id", "shot_id", "revision_number",
                       "snapshot_hash"),
    "generations": ("id", "shot_id", "manifest_hash",
                    "workflow_template_hash", "workflow_spec_hash"),
    "generation_inputs": ("generation_id", "input_key", "position",
                          "blob_hash"),
    "derived_spatial_artifacts": ("id", "project_id", "spec_hash",
                                  "runtime_fingerprint_hash", "blob_hash"),
    "generation_derived_spatial_inputs": ("generation_id", "input_key",
                                          "position", "blob_hash"),
}


def canonical_inventory(engine) -> dict:
    """The fixture-owned semantic inventory: identity-bearing row tuples
    per table, lexically ordered tables, logical-identity-sorted tuples."""
    from soloring.domain.canonical import canonical_hash

    tables: dict[str, list] = {}
    import sqlite3

    con = sqlite3.connect(str(engine.url.database)
                          if not str(engine.url).startswith("sqlite+")
                          else str(engine.url).split("///")[-1])
    try:
        con.row_factory = sqlite3.Row
        for table in sorted(INVENTORY_GRAMMAR):
            cols = INVENTORY_GRAMMAR[table]
            quoted = ", ".join(f'"{c}"' for c in cols)
            rows = [tuple(r) for r in con.execute(
                f"SELECT {quoted} FROM {table}")]
            rows.sort(key=lambda t: json.dumps(
                [str(x) for x in t], sort_keys=True))
            tables[table] = rows
    finally:
        con.close()
    return {
        "digest": canonical_hash({"schema_version": 1, "tables": tables}),
        "counts": {t: len(rows) for t, rows in tables.items()},
        "tables": tables,
    }


# ---------------------------------------------------------------------------
# Fixture builder
# ---------------------------------------------------------------------------


async def build_fixture(engine, factory, settings, *, n_bulk_shots=2460,
                        with_history: bool = True) -> dict:
    """Build the canonical representative Project. Returns identities.

    ``with_history=False`` skips Generation creation (used by cold-path
    measurements that need a pristine target Shot).
    """
    rng = _rng()
    pid = det_id("project")
    ids: dict[str, str] = {"project": pid}

    async with factory() as s:
        await s.execute(text(
            "INSERT INTO projects (id, name, created_at, updated_at) "
            "VALUES (:p, 'M10F Representative', 't', 't')"), {"p": pid})
        await s.commit()

    # --- narrative topology: 5 sequences x 10 scenes -------------------
    from tests.test_m10d_resolver import (
        CAM,
        _entities,
        _first_sequence,
        _shot,
    )

    scene_ids: list[str] = []
    async with factory() as s:
        for si in range(5):
            seq = det_id(f"seq:{si}")
            await s.execute(text(
                "INSERT INTO sequences (id, project_id, position, title, "
                "created_at, updated_at) VALUES (:i, :p, :pos, :t, 't','t')"
            ), {"i": seq, "p": pid, "pos": si, "t": f"Sequence {si}"})
            for ci in range(10):
                sc = det_id(f"scene:{si}:{ci}")
                await s.execute(text(
                    "INSERT INTO scenes (id, sequence_id, position, title, "
                    "created_at, updated_at) VALUES "
                    "(:i, :s, :pos, :t, 't','t')"),
                    {"i": sc, "s": seq, "pos": ci, "t": f"Scene {si}.{ci}"})
                scene_ids.append(sc)
        await s.commit()

    # --- entities -------------------------------------------------------
    kinds = {"loc": "location", "loc2": "location",
             "char:0": "character", "char:1": "character",
             "char:2": "character", "char:3": "character",
             "prop:0": "prop", "prop:1": "prop", "veh:0": "vehicle",
             "veh:1": "vehicle"}
    ents = await _entities(factory, pid, kinds)
    ids["loc"], ids["loc_rev"] = ents["loc"]
    for k in kinds:
        if k != "loc":
            ids[k] = ents[k][0]

    # --- the required world reused across the project -------------------
    from soloring.spatial import (
        plans as plan_svc,
        revisions as wrev_svc,
        tracks as track_svc,
        transitions as trans_svc,
        worlds as world_svc,
    )

    world = await world_svc.create_world(
        factory(), pid, key="lobby", name="lobby", description=None,
        requirement="required", location_entity_id=ids["loc"])
    ids["world"] = world["id"]

    state_a = await world_svc.create_state(
        factory(), world["id"], location_entity_revision_id=ids["loc_rev"])

    # 62 stable frame identities: 'origin' + 61 set pieces
    frame_ids: dict[str, str] = {}
    frame_ids["origin"] = (await world_svc.create_frame(
        factory(), world["id"], key="origin", name="origin",
        parent_spatial_frame_id=None, bound_entity_id=None))["id"]
    for fi in range(61):
        key = f"set-{fi}"
        frame_ids[key] = (await world_svc.create_frame(
            factory(), world["id"], key=key, name=key,
            parent_spatial_frame_id=frame_ids["origin"], bound_entity_id=None))["id"]

    def _t(i: int, z: int) -> list[int]:
        return [(-3600 + 90 * i) % 7200 - 3600, 1500 + 40 * i, z]

    # state A memberships: prop/veh-bound fixed frames + axes
    await world_svc.put_state_frame(
        factory(), state_a["id"], frame_ids["origin"],
        translation_mm=[-3000, 1650, 0], rotation_udeg=[0, 0, 0],
        half_extents_mm=None, bound_entity_revision_id=None)
    for fi in range(61):
        await world_svc.put_state_frame(
            factory(), state_a["id"], frame_ids[f"set-{fi}"],
            translation_mm=_t(fi, -200 - 30 * fi),
            rotation_udeg=[0, rng.randint(-3, 3), 0],
            half_extents_mm=[300, 200, 150] if fi % 2 else None,
            bound_entity_revision_id=None)
    # prop/vehicle-bound frames in state A
    f_prop = (await world_svc.create_frame(
        factory(), world["id"], key="prop-mount", name="prop-mount",
        parent_spatial_frame_id=None, bound_entity_id=ids["prop:0"]))["id"]
    await world_svc.put_state_frame(
        factory(), state_a["id"], f_prop, translation_mm=[-2500, 1400, -600],
        rotation_udeg=[0, 0, 0], half_extents_mm=[120, 80, 60],
        bound_entity_revision_id=ents["prop:0"][1])
    f_veh = (await world_svc.create_frame(
        factory(), world["id"], key="veh-mount", name="veh-mount",
        parent_spatial_frame_id=None, bound_entity_id=ids["veh:0"]))["id"]
    await world_svc.put_state_frame(
        factory(), state_a["id"], f_veh, translation_mm=[-2000, 1300, -800],
        rotation_udeg=[0, 0, 0], half_extents_mm=None,
        bound_entity_revision_id=ents["veh:0"][1])

    axis_ids = {}
    for ai in range(4):
        axis_ids[ai] = (await world_svc.create_axis(
            factory(), world["id"], key=f"axis-{ai}", name=f"Axis {ai}"))["id"]
    await world_svc.put_state_axis(
        factory(), state_a["id"], axis_ids[0],
        a_frame_id=frame_ids["origin"], b_frame_id=frame_ids["set-0"])
    await world_svc.put_state_axis(
        factory(), state_a["id"], axis_ids[1],
        a_frame_id=frame_ids["set-5"], b_frame_id=frame_ids["set-9"])
    await world_svc.put_state_axis(
        factory(), state_a["id"], axis_ids[2],
        a_frame_id=frame_ids["set-20"], b_frame_id=frame_ids["set-40"])
    await world_svc.put_state_axis(
        factory(), state_a["id"], axis_ids[3],
        a_frame_id=frame_ids["set-3"], b_frame_id=frame_ids["set-31"])

    rev_a = await wrev_svc.capture_revision(factory(), state_a["id"])
    await wrev_svc.approve_revision(
        factory(), state_a["id"], revision_id=rev_a["id"],
        expected_approved_revision_id=None)
    ids["state_a"], ids["world_rev_a"] = state_a["id"], rev_a["id"]

    # state B on a later location revision: same char movable by track
    loc2 = det_id("loc:entity:revision:2")
    async with factory() as s:
        await s.execute(text(
            "INSERT INTO entity_revisions (id, entity_id, revision_number, "
            "schema_version, spec_hash, created_at) VALUES "
            "(:i, :e, 2, 1, :h, 't')"),
            {"i": loc2, "e": ids["loc"], "h": "0" * 64})
        await s.commit()
    state_b = await world_svc.create_state(
        factory(), world["id"], location_entity_revision_id=loc2)
    await world_svc.put_state_frame(
        factory(), state_b["id"], frame_ids["origin"],
        translation_mm=[-3000, 1650, 0], rotation_udeg=[0, 0, 0],
        half_extents_mm=None, bound_entity_revision_id=None)
    for fi in range(0, 61, 2):  # state-specific membership/value changes
        await world_svc.put_state_frame(
            factory(), state_b["id"], frame_ids[f"set-{fi}"],
            translation_mm=_t(fi, -240 - 25 * fi),
            rotation_udeg=[0, rng.randint(-2, 2), 0],
            half_extents_mm=[320, 210, 140] if fi % 4 else None,
            bound_entity_revision_id=None)
    rev_b = await wrev_svc.capture_revision(factory(), state_b["id"])
    await wrev_svc.approve_revision(
        factory(), state_b["id"], revision_id=rev_b["id"],
        expected_approved_revision_id=None)
    ids["state_b"], ids["world_rev_b"] = state_b["id"], rev_b["id"]

    # --- tracks + transitions (required/optional, clears, re-entry) -----
    seq0 = det_id("seq:0")
    track_ids: dict[str, str] = {}
    # prop:0 / veh:0 carry FIXED frames (state A); their tracks would
    # collide with those placements, so the recurring prop/vehicle tracks
    # ride on prop:1 / veh:1 (§11.1 "another legal non-conflicting" form).
    track_specs = [
        ("char:0", "optional"), ("char:1", "required"), ("char:2", "optional"),
        ("char:3", "required"), ("prop:1", "optional"), ("veh:1", "required"),
    ]
    for name, requirement in track_specs:
        track_ids[name] = (await track_svc.create_track(
            factory(), world["id"], entity_id=ids[name],
            requirement=requirement))["id"]
    staging_t0: dict[str, list[int]] = {}
    for _i, name in enumerate(sorted(track_ids)):
        staging_t0[name] = _t((_i * 13) % 61, -900)
        await trans_svc.create_transition(
            factory(), track_ids[name], anchor_type="sequence",
            anchor_id=seq0, boundary="start", operation="set",
            translation_mm=staging_t0[name],
            rotation_udeg=[0, 0, 0])
    # a clear at scene 2 start + later re-entry at scene 5 start
    await trans_svc.create_transition(
        factory(), track_ids["char:3"], anchor_type="scene",
        anchor_id=det_id("scene:0:2"), boundary="start", operation="clear")
    await trans_svc.create_transition(
        factory(), track_ids["char:3"], anchor_type="scene",
        anchor_id=det_id("scene:0:5"), boundary="start", operation="set",
        translation_mm=_t(11, -1100), rotation_udeg=[0, 0, 0])

    # --- designated target shots + plans through services ---------------
    target_shots: list[str] = []
    plan_variants = ("static", "multi-keyframe", "multi-track", "axis-ok",
                     "axis-on", "axis-violation", "handoff-ok",
                     "handoff-late")
    deps_all = [ids["loc"]] + [ids[k] for k in
                               ("char:0", "char:1", "char:2", "char:3",
                                "prop:0", "prop:1", "veh:0")]
    for ti in range(40):
        shot = await _shot(factory, pid, deps_all, assigned=True)
        target_shots.append(shot)
        variant = plan_variants[ti % len(plan_variants)]
        blocking = []
        for bi, name in enumerate(("char:0", "char:1", "char:2")
                                  [: 3 if variant in
                                   ("multi-track", "static",
                                    "multi-keyframe") else 1]):
            keyframes = ([{"time_ms": 0, "transform": {
                "translation_mm": staging_t0[name],
                "rotation_udeg": [0, 0, 0]}}]
                if variant != "multi-keyframe" else [
                    {"time_ms": 0, "transform": {
                        "translation_mm": staging_t0[name],
                        "rotation_udeg": [0, 0, 0]}},
                    {"time_ms": 2000, "transform": {
                        "translation_mm": _t(bi * 7 + 3, -1300),
                        "rotation_udeg": [0, 15, 0]}},
                    {"time_ms": 4000, "transform": {
                        "translation_mm": _t(bi * 7 + 6, -1600),
                        "rotation_udeg": [0, 30, 0]}}])
            blocking.append({
                "spatial_track_id": track_ids[name],
                "screen_direction": "left_to_right" if bi % 2 else
                "right_to_left",
                "keyframes": keyframes,
            })
        axis_constraint = None
        if variant in ("axis-ok", "axis-on", "axis-violation"):
            axis_constraint = {
                "spatial_axis_id": axis_ids[
                    {"axis-ok": 0, "axis-on": 1, "axis-violation": 2}[
                        variant]],
                "camera_side": {"axis-ok": "positive", "axis-on":
                                "negative", "axis-violation": "negative"}[
                                    variant],
            }
        camera = _camera(ti)
        await plan_svc.put_spatial_plan(
            factory(), shot, expected_plan_hash=None, plan_raw={
                "schema_version": 1, "spatial_world_id": world["id"],
                "camera": camera, "blocking": blocking,
                "axis_constraint": axis_constraint,
            })
    ids["target_shots"] = target_shots
    ids["shot_a"], ids["shot_b"] = target_shots[0], target_shots[1]

    # dedicated COLD first-Generation target (§11.4): dependency closure
    # of loc + ONE staged character — exactly one applicable track, 2
    # control streams (world + entity), inside the frozen capacity.
    cold_shot = await _shot(
        factory, pid, [ids["loc"], ids["char:0"]], assigned=True)
    await plan_svc.put_spatial_plan(
        factory(), cold_shot, expected_plan_hash=None, plan_raw={
            "schema_version": 1, "spatial_world_id": world["id"],
            "camera": _camera(0), "blocking": [{
                "spatial_track_id": track_ids["char:0"],
                "screen_direction": "left_to_right",
                "keyframes": [{"time_ms": 0, "transform": {
                    "translation_mm": staging_t0["char:0"],
                    "rotation_udeg": [0, 0, 0]}}],
            }], "axis_constraint": None,
        })
    ids["cold_target"] = cold_shot

    # --- unrelated noise authority --------------------------------------
    noise_locs = {}
    async with factory() as s:
        for wi in range(3):
            eid, rid = det_id(f"entity:noise-loc:{wi}"), det_id(
                f"entity-rev:noise-loc:{wi}")
            await s.execute(text(
                "INSERT INTO creative_entities (id, project_id, kind, "
                "name, created_at, updated_at) VALUES (:e, :p, 'location', "
                ":n, 't','t')"), {"e": eid, "p": pid, "n": f"nloc {wi}"})
            await s.execute(text(
                "INSERT INTO entity_revisions (id, entity_id, "
                "revision_number, schema_version, spec_hash, created_at) "
                "VALUES (:r, :e, 1, 1, :h, 't')"),
                {"r": rid, "e": eid,
                 "h": hashlib.sha256(f"noise {wi}".encode()).hexdigest()})
            await s.execute(text(
                "INSERT INTO entity_approved_revisions (entity_id, "
                "revision_id, approved_at) VALUES (:e, :r, 't')"),
                {"e": eid, "r": rid})
            noise_locs[wi] = (eid, rid)
        await s.commit()
    for wi in range(3):
        noise_world = await world_svc.create_world(
            factory(), pid, key=f"noise-{wi}", name=f"noise {wi}",
            description=None, requirement="optional",
            location_entity_id=noise_locs[wi][0])
        noise_state = await world_svc.create_state(
            factory(), noise_world["id"],
            location_entity_revision_id=noise_locs[wi][1])
        nf = (await world_svc.create_frame(
            factory(), noise_world["id"], key="n", name="n",
            parent_spatial_frame_id=None, bound_entity_id=None))["id"]
        await world_svc.put_state_frame(
            factory(), noise_state["id"], nf, translation_mm=[0, 0, 0],
            rotation_udeg=[0, 0, 0], half_extents_mm=None,
            bound_entity_revision_id=None)
        await wrev_svc.capture_revision(factory(), noise_state["id"])
        nt = (await track_svc.create_track(
            factory(), noise_world["id"], entity_id=ids["char:3"],
            requirement="optional"))["id"]
        await trans_svc.create_transition(
            factory(), nt, anchor_type="sequence", anchor_id=seq0,
            boundary="end", operation="set", translation_mm=[9, 9, 9],
            rotation_udeg=[0, 0, 0])

    # --- bulk narrative volume (non-target; direct SQL + legality) ------
    rng2 = _rng()
    rows = []
    for bi in range(n_bulk_shots):
        rows.append({
            "i": det_id(f"bulk-shot:{bi}"), "p": pid,
            "sc": scene_ids[bi % len(scene_ids)],
            "pos": bi // len(scene_ids) + 100, "num": bi + 1000,
            "sub": f"Bulk shot {bi}"})
    insert = text(
        "INSERT INTO shots (id, project_id, scene_id, scene_position, "
        "shot_number, subject, created_at, updated_at) VALUES "
        "(:i, :p, :sc, :pos, :num, :sub, 't','t')")
    async with engine.begin() as conn:
        await conn.execute(insert, rows)
    ids["n_bulk"] = len(rows)

    # legality assertions for the bulk leg
    import sqlite3 as _sq

    db_path = str(engine.url).split("///")[-1]
    con = _sq.connect(db_path)
    try:
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        assert fk == [], f"bulk insert violated FKs: {fk[:3]}"
        n = con.execute("SELECT COUNT(*) FROM shots").fetchone()[0]
        assert n >= 2500, n
    finally:
        con.close()

    if not with_history:
        return ids

    # --- Generation history: v1 / v2 / v3 targets ------------------------
    await _build_generation_history(engine, factory, settings, ids,
                                    Path("."), pid)
    return ids


async def _build_generation_history(engine, factory, settings, ids,
                                    tmp_root: Path, pid: str) -> None:
    """v1 (schema-1 package), v2 (parity schema-3 package + M8), and v3
    (schema-5 + certified package, real D0) targets through production."""
    import httpx

    from soloring.api.main import create_app
    from soloring.db.engine import create_session_factory

    app = create_app(settings)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    transport = httpx.ASGITransport(app=app)

    from soloring.api.schemas.references import ReferenceInput
    from soloring.domain import references as ref_svc
    from soloring.generation.service import create_generation_request
    from soloring.workflows.manifest import WORKFLOW_DIR as V1_DIR

    from tests.test_m10d_resolver import _entities as _r_entities, \
        _shot as _r_shot
    from tests.test_m8b_curation import _assets

    # auxiliary project for the non-spatial compatibility targets: the
    # main project carries a REQUIRED world, and M8-only / v1 shots must
    # not be spatially blocked. Same DATABASE, per §11.1.
    pid2 = det_id("project-aux")
    async with factory() as s:
        await s.execute(text(
            "INSERT INTO projects (id, name, created_at, updated_at) "
            "VALUES (:p, 'M10F Compatibility Aux', 't', 't')"), {"p": pid2})
        await s.commit()

    async with httpx.AsyncClient(transport=transport,
                                 base_url="http://test") as client:
        # --- v1 target: schema-1 package + legacy reference ---------------
        from soloring.settings import Settings as _S

        pkg_root = tmp_root / "m10f-scale-pkgs"
        pkg_root.mkdir(parents=True, exist_ok=True)
        legacy = await _assets(engine, pid2, 1)
        # repair fixture placeholder bytes to the true preimage
        import hashlib as _hl

        from soloring.assets.blob_store import BlobStore

        store = BlobStore(settings)
        async with engine.connect() as c:
            bh = (await c.execute(text(
                "SELECT blob_hash FROM assets WHERE id = :a"),
                {"a": legacy[0]})).scalar()
        p = store.path_for_hash(bh)
        if (_hl.sha256(p.read_bytes()).hexdigest() != bh
                or True):
            p.write_bytes(legacy[0].encode())
            async with factory() as s2:
                await s2.execute(text(
                    "UPDATE blobs SET size_bytes = :n WHERE hash = :h"),
                    {"n": len(legacy[0]), "h": bh})
                await s2.commit()
        # v1 target needs a PLAN-FREE shot: shot_a carries spatial
        # authority and would correctly block on a schema-1 package.
        from tests.test_m10d_resolver import _entities as _aux_entities

        aux_ents = await _aux_entities(factory, pid2, {"auxloc": "location"})
        shot_v1 = await _r_shot(
            factory, pid2, [aux_ents["auxloc"][0]], assigned=True)
        async with factory() as s:
            await ref_svc.replace_references(
                s, shot_v1,
                [ReferenceInput(asset_id=legacy[0], role="reference")])
        saved_pkg = settings.workflow_package_dir
        settings.executor = "comfy"
        settings.workflow_package_dir = V1_DIR
        async with factory() as session:
            await create_generation_request(
                session, shot_v1, settings=settings)
        ids["v1_target_shot"] = shot_v1

        # --- v2 + v3 targets ----------------------------------------------
        from tests.test_m10e_generation import (
            _EXTENTS,
            _create as _e_create,
            _spatial_seed as _e_seed,
            _v3_parity_package,
        )
        from tests.test_m10e_package3_production import _schema3_package
        from tests.test_m9c_generation import _m9_shot

        # v2: M8 authority + parity schema-3 package on a DEDICATED shot
        shot_v2, _a = await _m9_shot(client, factory, engine, settings, pid2)
        parity = await _v3_parity_package(pkg_root)
        settings.workflow_package_dir = parity
        async with factory() as session:
            await create_generation_request(session, shot_v2,
                                            settings=settings)
        ids["v2_target_shot"] = shot_v2

        # v3: dedicated spatial seed with the certified package (real D0)
        certified = await _schema3_package(pkg_root)
        settings.workflow_package_dir = certified
        seed = await _e_seed(factory, staged=1, extents=_EXTENTS)
        gen3 = await _e_create(factory, settings, seed)
        ids["v3_target_shot"] = seed["shot"]
        ids["v3_generation"] = gen3.id
        settings.workflow_package_dir = saved_pkg
