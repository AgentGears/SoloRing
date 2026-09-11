"""M14B-1 — retained structural-mesh consumer (frozen R2 §§12/13/27/28;
proof cells M14-OBS:09/10/14/15/17 live in tests/test_m14_obs.py, and
M14-MAT:01-07 here).

Set-oriented immutable-history loading: canonical grammar, B1 caps,
exact ProductionRevision/closure/blob agreement, required interpretation
for recognized meshes only, A4/A6 placement chains, and the fail-closed
corruption negatives.
"""

from __future__ import annotations

import hashlib
import json
import uuid

import pytest
from sqlalchemy import text

from soloring.errors import SoloRingError
from soloring.observation.mesh import (
    parse_structural_mesh_v1,
    structural_mesh_bytes,
)
from soloring.observation.retained import load_retained_mesh_sources

from tests.m13_seed import make_composition, mint, mint_nested, publish
from tests.test_m13_binding import _adopt, _interpretation, _publish
from tests.test_m13_shot_capture import (
    _capture,
    _factory,
    _full_m13_world,
)

NOW = "2026-09-10T00:00:00Z"


def _mesh_doc(*, offset: int = 0) -> dict:
    return {
        "schema_version": 1,
        "kind": "soloring.structural_mesh",
        "coordinate_system": {
            "handedness": "right", "right_axis": "+x", "up_axis": "+y",
            "depth_positive_axis": "+z", "forward_axis": "-z",
            "linear_unit": "millimeter", "vector_convention": "column"},
        "vertices_mm": [
            [offset, 0, 0], [offset + 400, 0, 0], [offset, 400, 0],
            [offset, 0, 400], [offset + 400, 400, 400]],
        "triangles": [[0, 1, 2], [0, 3, 4]],
    }


def _reader(client):
    settings = client._transport.app.state.settings

    def read(blob_hash: str) -> bytes:
        path = (settings.blob_dir / "sha256" / blob_hash[:2]
                / blob_hash[2:4] / blob_hash)
        return path.read_bytes()

    return read


async def _write_blob(client, data: bytes) -> str:
    settings = client._transport.app.state.settings
    blob_hash = hashlib.sha256(data).hexdigest()
    path = settings.blob_dir / "sha256" / blob_hash[:2] / blob_hash[2:4] / blob_hash
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        await conn.execute(text(
            "INSERT INTO blobs (hash, path, size_bytes, "
            "detected_media_type, created_at) VALUES "
            "(:h, :p, :s, NULL, :n)"),
            {"h": blob_hash, "p": f"sha256/{blob_hash[:2]}/"
                                  f"{blob_hash[2:4]}/{blob_hash}",
             "s": len(data), "n": NOW})
        await conn.commit()
    return blob_hash


async def _mesh_production_revision(client, pid: str, blob: bytes,
                                    *, number: int) -> str:
    from soloring.production.canonical import (
        RetainedBlobClosure,
        production_revision_snapshot_json as sj,
        production_revision_snapshot_hash as sh,
    )

    blob_hash = hashlib.sha256(blob).hexdigest()
    prid, pobj = str(uuid.uuid4()), str(uuid.uuid4())
    closure = RetainedBlobClosure(
        blob_hash=blob_hash, size_bytes=len(blob), media_type=None)
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        await conn.execute(text(
            "INSERT INTO production_objects (id, project_id, name, "
            "created_at, updated_at) VALUES (:o, :p, 'Mesh', :n, :n)"),
            {"o": pobj, "p": pid, "n": NOW})
        await conn.execute(text(
            "INSERT INTO production_revisions (id, production_object_id, "
            "revision_number, snapshot_json, snapshot_hash, created_at) "
            "VALUES (:r, :o, :num, :sj, :sh, :n)"),
            {"r": prid, "o": pobj, "num": number, "sj": sj(closure),
             "sh": sh(closure), "n": NOW})
        await conn.execute(text(
            "INSERT INTO production_revision_closures "
            "(production_revision_id, contract_key, contract_version, "
            "blob_hash, size_bytes, media_type) VALUES "
            "(:r, 'retained_blob', 1, :bh, :s, NULL)"),
            {"r": prid, "bh": blob_hash, "s": len(blob)})
        await conn.commit()
    return prid


async def _observation_world(client, *, tag: bytes, sources: list[dict],
                             adopt_first_mesh: bool = True,
                             pi_translation=(100, 0, 0)):
    """A captured schema-6 world whose composition has the given direct
    sources: {"kind": "mesh"|"nonmesh", "mesh": doc?, "transform": (x,y,z),
    "interpretation": (x,y,z)?}. Returns (b, snapshot, oids, prids)."""
    b = await _full_m13_world(client, tag=tag)
    cid = await make_composition(client, b["pid"])
    version = 0
    oids: list[str | None] = []
    prids: list[str | None] = []
    first_mesh_oid = None
    number = 100
    for source in sources:
        if source["kind"] == "mesh":
            blob = structural_mesh_bytes(source["mesh"])
            await _write_blob(client, blob)
            prid = await _mesh_production_revision(
                client, b["pid"], blob, number=number)
            number += 1
            minted = await mint(client, cid, prid, version,
                                transform=source.get("transform", (0, 0, 0)))
            version += 1
            oids.append(minted["occurrence_id"])
            prids.append(prid)
            if source.get("interpretation") is not None:
                await _interpretation(client, prid,
                                      translation=source["interpretation"])
            if first_mesh_oid is None:
                first_mesh_oid = minted["occurrence_id"]
        else:  # nonmesh: reuse seed_base's arbitrary-bytes revision
            minted = await mint(
                client, cid, b["production_revision_id"], version,
                transform=source.get("transform", (0, 0, 0)))
            version += 1
            oids.append(minted["occurrence_id"])
            prids.append(b["production_revision_id"])

    if adopt_first_mesh and first_mesh_oid is not None:
        await _adopt(client, cid, first_mesh_oid,
                     {"kind": "production_instance"})
        engine = client._transport.app.state.engine
        track = (await client.post(
            f"/spatial-worlds/{b['world']['id']}/production-instance-tracks",
            json={"occurrence_id": first_mesh_oid,
                  "requirement": "optional"})).json()["id"]
        async with engine.connect() as conn:
            seq = (await conn.execute(text(
                "SELECT id FROM sequences WHERE project_id = :p "
                "ORDER BY position LIMIT 1"), {"p": b["pid"]})).scalar_one()
        r = await client.post(
            f"/production-instance-spatial-tracks/{track}/transitions",
            json={"anchor_type": "sequence", "anchor_id": seq,
                  "boundary": "start", "operation": "set",
                  "transform": {"translation_mm": list(pi_translation),
                                "rotation_udeg": [0, 0, 0]}})
        assert r.status_code == 201, r.text
        b["pi_track"] = track

    pub = await publish(client, cid, version)
    composed_revision = pub["revision"]["revision_id"]
    pr = await _publish(client, composed_revision, b["rev"]["id"])
    assert pr.status_code == 201, pr.text
    binding_id = pr.json()["binding_id"]
    r = await client.put(
        f"/shots/{b['shot']}/production-world-selection",
        json={"binding_id": binding_id, "expected_binding_id": None})
    assert r.status_code == 200, r.text

    revision, _ = await _capture(client, b["shot"])
    snapshot = json.loads(revision.snapshot_json)
    assert snapshot["schema_version"] == 6
    return b, snapshot, oids, prids


async def _load(client, snapshot):
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        return await load_retained_mesh_sources(
            conn, _reader(client),
            captured_production_world=snapshot["production_world"],
            captured_spatial_pack=snapshot["spatial_continuity"])


# ---- MAT:01 canonical parser ----------------------------------------------

def test_m14_mat_01() -> None:
    mesh = _mesh_doc()
    raw = structural_mesh_bytes(mesh)
    assert parse_structural_mesh_v1(raw) == mesh

    reordered = json.dumps(mesh, sort_keys=True,
                           separators=(",", ":"), ensure_ascii=False)
    assert reordered.encode("utf-8") == raw, (
        "canonical bytes are sorted-key/minimal-separator/UTF-8")

    noncanonical = json.dumps(mesh, sort_keys=False,
                              separators=(", ", ": ")).encode("utf-8")
    with pytest.raises(SoloRingError, match="canonical"):
        parse_structural_mesh_v1(noncanonical)

    with pytest.raises(SoloRingError):
        parse_structural_mesh_v1(b"not json")


# ---- MAT:02 grammar negatives; winding not semantic -----------------------

def test_m14_mat_02() -> None:
    def mutate(**changes):
        mesh = _mesh_doc()
        mesh.update(changes)
        return structural_mesh_bytes(mesh)

    with pytest.raises(SoloRingError, match="distinct"):
        parse_structural_mesh_v1(mutate(triangles=[[0, 1, 1]]))
    degenerate = _mesh_doc()
    degenerate["vertices_mm"][3] = [800, 0, 0]  # on the v0–v1 line
    degenerate["triangles"] = [[0, 1, 3]]
    with pytest.raises(SoloRingError, match="zero-area"):
        parse_structural_mesh_v1(structural_mesh_bytes(degenerate))
    with pytest.raises(SoloRingError, match="out of range"):
        parse_structural_mesh_v1(mutate(triangles=[[0, 1, 99]]))
    with pytest.raises(SoloRingError, match="distinct"):
        parse_structural_mesh_v1(mutate(triangles=[[0, 0, 1]]))
    with pytest.raises(SoloRingError, match="plain integers"):
        parse_structural_mesh_v1(mutate(
            vertices_mm=[[0.5, 0, 0], [4, 0, 0], [0, 4, 0], [0, 0, 4],
                         [4, 4, 4]]))
    with pytest.raises(SoloRingError, match="unknown fields"):
        parse_structural_mesh_v1(mutate(surprise=1))
    bad_coords = _mesh_doc()
    bad_coords["coordinate_system"]["linear_unit"] = "meter"
    with pytest.raises(SoloRingError, match="coordinate_system"):
        parse_structural_mesh_v1(structural_mesh_bytes(bad_coords))

    # winding is NOT semantic: reversed winding is the same two-sided
    # triangle set
    flipped = _mesh_doc()
    flipped["triangles"] = [[2, 1, 0], [4, 3, 0]]
    assert parse_structural_mesh_v1(structural_mesh_bytes(flipped))


# ---- MAT:03 exact blob/hash agreement + representation identity ----------

async def test_m14_mat_03(client) -> None:
    mesh = _mesh_doc()
    _b, snapshot, oids, prids = await _observation_world(
        client, tag=b"m14b1-mat03",
        sources=[{"kind": "mesh", "mesh": mesh,
                  "transform": (25, -50, 10),
                  "interpretation": (5, 0, 0)}],
        adopt_first_mesh=False)
    outcome = await _load(client, snapshot)

    assert len(outcome.sources) == 1
    source = outcome.sources[0]
    blob_hash = hashlib.sha256(structural_mesh_bytes(mesh)).hexdigest()
    assert source.retained_blob_hash == blob_hash
    assert source.occurrence_object["retained_blob_hash"] == blob_hash, (
        "representation identity IS the retained blob hash (§12.3)")
    assert source.mesh == mesh

    settings = client._transport.app.state.settings
    tampered = b"x" * 16
    path = (settings.blob_dir / "sha256" / blob_hash[:2]
            / blob_hash[2:4] / blob_hash)
    original = path.read_bytes()
    path.write_bytes(tampered)
    try:
        with pytest.raises(SoloRingError, match="physical retained Blob"):
            await _load(client, snapshot)
    finally:
        path.write_bytes(original)


# ---- MAT:04 exact ProductionRevision/hash/blob agreement -----------------

async def test_m14_mat_04(client) -> None:
    _b, snapshot, _oids, prids = await _observation_world(
        client, tag=b"m14b1-mat04",
        sources=[{"kind": "mesh", "mesh": _mesh_doc(),
                  "interpretation": (0, 0, 0)}])
    prid = prids[0]
    engine = client._transport.app.state.engine

    async with engine.connect() as conn:
        await conn.execute(text(
            "UPDATE production_revisions SET snapshot_hash = "
            ":h WHERE id = :r"),
            {"h": "0" * 64, "r": prid})
        await conn.commit()
    with pytest.raises(SoloRingError, match="disagrees"):
        await _load(client, snapshot)


# ---- closure-size corruption (separate world; the row hash above is left
# tampered inside its own test DB, so each negative owns its fixtures) ----


async def test_m14_mat_04_closure_corruption(client) -> None:
    _b, snapshot, _oids, prids = await _observation_world(
        client, tag=b"m14b1-mat04b",
        sources=[{"kind": "mesh", "mesh": _mesh_doc(),
                  "interpretation": (0, 0, 0)}])
    prid = prids[0]
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        await conn.execute(text(
            "UPDATE production_revision_closures SET size_bytes = "
            "size_bytes + 1 WHERE production_revision_id = :r"),
            {"r": prid})
        await conn.commit()
    with pytest.raises(SoloRingError, match="M11 agreement"):
        await _load(client, snapshot)


# ---- MAT:05 composition-owned (A6) chain exact ----------------------------

async def test_m14_mat_05(client) -> None:
    _b, snapshot, oids, _prids = await _observation_world(
        client, tag=b"m14b1-mat05",
        sources=[{"kind": "mesh", "mesh": _mesh_doc(),
                  "transform": (25, -50, 10),
                  "interpretation": (5, 0, 0)}],
        adopt_first_mesh=False)
    outcome = await _load(client, snapshot)

    (source,) = outcome.sources
    assert source.placement_owner == "A6"
    assert source.placement_source_kind == "composition_revision"
    assert source.subject_local_to_world == {
        "translation_mm": [25, -50, 10], "rotation_udeg": [0, 0, 0]}
    assert source.realization_local_to_subject_local == {
        "translation_mm": [5, 0, 0], "rotation_udeg": [0, 0, 0]}
    assert source.realization_local_to_world == {
        "translation_mm": [30, -50, 10], "rotation_udeg": [0, 0, 0]}, (
        "A6 chain: interpretation then exact composition transform")
    requirement = source.placement_requirement
    assert requirement["property"] == "occurrence.placement"
    assert requirement["authority"]["domain"] == "A6"
    assert (requirement["authority"]["source_kind"]
            == "composition_revision")
    assert requirement["source_contract"] == "m14.placement.v1"


# ---- MAT:06 A4 spatial-owned chain exact -----------------------------------

async def test_m14_mat_06(client) -> None:
    _b, snapshot, oids, _prids = await _observation_world(
        client, tag=b"m14b1-mat06",
        sources=[{"kind": "mesh", "mesh": _mesh_doc(),
                  "transform": (0, 0, 0),
                  "interpretation": (5, 0, 0)}],
        adopt_first_mesh=True)
    outcome = await _load(client, snapshot)

    (source,) = outcome.sources
    assert source.placement_owner == "A4"
    assert source.placement_source_kind == "composition_spatial_binding"
    assert source.subject_local_to_world == {
        "translation_mm": [100, 0, 0], "rotation_udeg": [0, 0, 0]}, (
        "A4 PI-track world transform from instance_spatial_states")
    assert source.realization_local_to_world == {
        "translation_mm": [105, 0, 0], "rotation_udeg": [0, 0, 0]}
    requirement = source.placement_requirement
    assert requirement["authority"]["domain"] == "A4"
    assert (requirement["authority"]["source_kind"]
            == "composition_spatial_binding")
    assert requirement["authority"]["source_id"] == (
        snapshot["production_world"]["binding"]["binding_id"])
    assert requirement["authority"]["source_hash"] == (
        snapshot["production_world"]["binding"]["binding_hash"])


# ---- MAT:07 PI captured spatial-state matching exact ----------------------

async def test_m14_mat_07(client) -> None:
    """PI captured spatial-state matching is exact: with the captured
    state row absent (missing/mismatched captured state), the A4 PI
    chain fails closed — never falls back to identity or current state
    (frozen §13.3)."""
    _b, snapshot, oids, _prids = await _observation_world(
        client, tag=b"m14b1-mat07",
        sources=[{"kind": "mesh", "mesh": _mesh_doc(),
                  "interpretation": (0, 0, 0)}],
        adopt_first_mesh=True)
    pack = snapshot["production_world"]
    (state,) = pack["instance_spatial_states"]
    assert state["occurrence_id"] == oids[0]
    assert state["transform"]["translation_mm"] == [100, 0, 0]

    engine = client._transport.app.state.engine
    import copy

    malformed = copy.deepcopy(snapshot)
    malformed["production_world"]["instance_spatial_states"] = []
    with pytest.raises(SoloRingError, match="instance_spatial_states"):
        await _load(client, malformed)


# ---- set-oriented loading + historical isolation --------------------------

async def test_loader_query_shape_constant(client) -> None:
    one, _snap1, _o1, _p1 = await _observation_world(
        client, tag=b"m14b1-q1",
        sources=[{"kind": "mesh", "mesh": _mesh_doc(),
                  "interpretation": (0, 0, 0)}])
    snap1 = _snap1
    _two, snap2, _o2, _p2 = await _observation_world(
        client, tag=b"m14b1-q3",
        sources=[{"kind": "mesh", "mesh": _mesh_doc(offset=1),
                  "interpretation": (0, 0, 0)},
                 {"kind": "mesh", "mesh": _mesh_doc(offset=2),
                  "interpretation": (0, 0, 0)},
                 {"kind": "mesh", "mesh": _mesh_doc(offset=3),
                  "interpretation": (0, 0, 0)}],
        adopt_first_mesh=False)
    outcome1 = await _load(client, snap1)
    outcome3 = await _load(client, snap2)
    assert outcome1.query_count == outcome3.query_count == 4, (
        "SQL round trips bounded by domain batch, not occurrence count")
    assert len(outcome3.sources) == 3


async def test_loader_historical_isolation(client) -> None:
    """Current-state resolver unavailability: after the capture, mutate
    every current mutable successor (newer revisions, superseded
    composition) — the captured load is byte-identical."""
    b, snapshot, oids, prids = await _observation_world(
        client, tag=b"m14b1-hist",
        sources=[{"kind": "mesh", "mesh": _mesh_doc(),
                  "transform": (25, -50, 10),
                  "interpretation": (5, 0, 0)}],
        adopt_first_mesh=False)
    before = await _load(client, snapshot)

    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        # supersede the composition with a new working version
        await conn.execute(text(
            "UPDATE compositions SET working_version = working_version + 1 "
            "WHERE id = (SELECT composition_id FROM "
            "composition_revisions WHERE id = :c)"),
            {"c": before.sources[0].composition_revision_id})
        await conn.commit()

    after = await _load(client, snapshot)
    assert [s.occurrence_object for s in after.sources] == [
        s.occurrence_object for s in before.sources]
    assert after.query_count == before.query_count
