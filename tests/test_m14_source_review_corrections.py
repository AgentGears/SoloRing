"""M14 source-review correction slice (from eaa3097, 2026-09-11).

Covers the five findings of the first independent source review of the
20429b3..eaa3097 delta:

  P0-1  zero-retained-mesh schema-4 Generations still publish/bind the
        observation (end-to-end Generation + hermetic worker + the E4
        byte-identity against the M10-only twin);
  P0-2  the producing MaterializerContract must equal the negotiated/
        captured one at creation, and the worker rejects an artifact
        produced under a contract other than the stored spec's;
  P0-3  Production Instance placement resolves by the full frozen §13.3
        key (composition, occurrence, track) — wrong composition,
        wrong occurrence, and duplicate matches fail closed;
  P1-4  schema-4 validation is relational (requirement hashes/order,
        capability echo, policy echo, verdict consistency) and the
        worker cross-checks the retained profile/capability identities;
        the inspector verifies the persisted spec hash and the
        binding/artifact/provenance identities it presents;
  P1-5  the A4 no-conflicting-transform invariant is re-verified at load
        (frozen §13.2), and the §31 UX/API surface is real product
        surface (routes on the existing inspector seams, driven here
        through the HTTP boundary).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "m14"


def _engine_of(client):
    return client._transport.app.state.engine


async def _capture_latest(client, shot_id: str):
    from tests.test_m13_shot_capture import _capture

    revision, _visual = await _capture(client, shot_id)
    return revision


# ---- P0-1: zero-mesh schema-4 publishes, binds, and executes ----------------

async def _empty_composition_revision(client, b) -> str:
    """An immutable composition revision with ZERO occurrences, built by
    cloning a real published revision's canonical shape (the M13 API
    refuses to publish empty working states, so the valid empty
    revision is constructed at the immutable-history seam and bound
    through the REAL binding service)."""
    from tests.m13_seed import make_composition, mint, publish

    cid = await make_composition(client, b["pid"])
    await mint(client, cid, b["production_revision_id"], 0)
    real_revision = (await publish(client, cid, 1))["revision"][
        "revision_id"]

    engine = _engine_of(client)
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT composition_id, snapshot_json, snapshot_hash, "
            "revision_number FROM composition_revisions WHERE id = :r"),
            {"r": real_revision})).mappings().one()
        snapshot = json.loads(row["snapshot_json"])
        snapshot["occurrences"] = []
        snapshot["dependencies"] = {
            "composition_revision_ids": [],
            "production_revision_ids": []}
        from soloring.domain.canonical import (
            canonical_hash,
            canonical_json_str,
        )

        new_id = str(uuid.uuid4())
        await conn.execute(text(
            "INSERT INTO composition_revisions (id, composition_id, "
            "revision_number, snapshot_json, snapshot_hash, created_at) "
            "VALUES (:i, :c, :n, :sj, :sh, "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"),
            {"i": new_id, "c": row["composition_id"],
             "n": row["revision_number"] + 1,
             "sj": canonical_json_str(snapshot),
             "sh": canonical_hash(snapshot)})
        await conn.commit()
    return new_id


async def test_zero_mesh_schema4_publishes_binds_and_worker_executes(
        client, tmp_path, monkeypatch):
    """The §§14.2/19/25.1 law: a supported schema-4 observation with
    source_occurrence_ids=[] STILL materializes (the exact M10 path),
    publishes, and binds observation.world_depth — the Generation is
    never published without its binding — and the worker executes the
    historical closure to a Take."""
    from soloring.observation.materializer import (
        materialize_observation_world_depth,
    )
    from tests.test_m13_binding import _publish
    from tests.test_m13_shot_capture import _full_m13_world
    from tests.test_m14_execution import (
        _comfy,
        _generate,
        _observation_package,
        _world_depth_blob,
    )

    b = await _full_m13_world(client, tag=b"m14-sr-zeromesh")
    empty_revision = await _empty_composition_revision(client, b)
    pr = await _publish(client, empty_revision, b["rev"]["id"])
    assert pr.status_code == 201, pr.text
    r = await client.put(
        f"/shots/{b['shot']}/production-world-selection",
        json={"binding_id": pr.json()["binding_id"],
              "expected_binding_id": None})
    assert r.status_code == 200, r.text
    revision = await _capture_latest(client, b["shot"])
    snapshot = json.loads(revision.snapshot_json)
    assert snapshot["schema_version"] == 6

    pkg = await _observation_package(tmp_path)
    settings = _comfy(client, pkg)
    engine = _engine_of(client)

    generation = await _generate(client, b["shot"], settings)
    spec = json.loads((await _run_query(engine, (
        "SELECT workflow_spec_json FROM generations WHERE id = :g"),
        {"g": generation.id})).scalar_one())
    observation = spec["world_observation"]["spec"]
    assert observation["materializations"][0][
        "source_occurrence_ids"] == []

    # the binding EXISTS for the zero-mesh observation
    async with engine.connect() as conn:
        binding = (await conn.execute(text(
            "SELECT derived_observation_artifact_id, blob_hash FROM "
            "generation_derived_observation_inputs WHERE generation_id = "
            ":g"), {"g": generation.id})).mappings().one()
        artifact = (await conn.execute(text(
            "SELECT blob_hash, provenance_json FROM "
            "derived_observation_artifacts WHERE id = :a"),
            {"a": binding["derived_observation_artifact_id"]}
        )).mappings().one()
    assert binding["blob_hash"] == artifact["blob_hash"]
    assert json.loads(artifact["provenance_json"])[
        "source_retained_blob_hashes"] == []

    # E4/§14.2 byte identity: the zero-mesh observation artifact equals
    # the plain M10-only twin's world-depth bytes
    from tests.test_m14_execution import _twin_schema5_shot

    twin_shot = await _twin_schema5_shot(client, b)
    await _capture_latest(client, twin_shot)
    twin_generation = await _generate(client, twin_shot, settings)
    assert await _world_depth_blob(engine, twin_generation.id) == (
        binding["blob_hash"]), (
        "zero-mesh schema-4 bytes must equal the exact M10 twin bytes")

    # ---- the hermetic worker executes the zero-mesh historical closure
    # (runtime verification + capability probing are hermetic seams —
    # the B5 pattern; the submission/output/import path is fully driven)
    import soloring.worker.comfy_pipeline as cp
    from soloring.worker import ownership
    from tests.test_m10f_compatibility import _FakeExecutorClient

    async def _cap(*a, **k):
        return object()

    monkeypatch.setattr(cp, "resolve_capability", _cap)
    monkeypatch.setattr(
        cp, "verify_schema3_runtime_environment",
        lambda *a, **k: None)
    output = b"zero-mesh-take-output"
    fake = _FakeExecutorClient(
        output, output_node="80", output_field="images")
    worker = "w-m14-sr-zeromesh"
    await ownership.acquire_worker_lease(engine, worker, 300)
    claim = await ownership.claim_next_generation(engine, worker)
    assert claim is not None and claim[0] == generation.id
    status = await cp.drive_comfy_generation(
        engine, settings, worker, generation.id, claim[1], fake)
    assert status == "succeeded", (
        f"the zero-mesh historical closure must execute — got {status}")
    take = (await _run_query(engine, (
        "SELECT t.id FROM takes t WHERE t.generation_id = :g"),
        {"g": generation.id})).scalar_one()
    assert take
    world_uploads = [(f, s) for f, s in fake.uploads
                     if f.startswith("world_depth_")]
    assert len(world_uploads) == 17, (
        "the worker uploads the bound zero-mesh control frames")


async def _run_query(engine, sql, params):
    async with engine.connect() as conn:
        return await conn.execute(text(sql), params)


# ---- P0-2: contract equality at creation + artifact/spec at the worker ------

async def test_contract_mismatch_refuses_before_materialization(
        client, tmp_path):
    """A package whose observation block advertises a contract other
    than the live producing contract refuses BEFORE materialization or
    publication: the negotiation contract and the byte-producing
    contract may never diverge."""
    from soloring.errors import SoloRingError
    from tests.test_m10e_generation import _spatial_settings
    from tests.test_m10e_package3_production import _schema3_package
    from tests.test_m14_execution import (
        _generate,
        _observation_profile,
        _schema6_world,
    )

    b, _sel, _rev, _snapshot = await _schema6_world(
        client, tag=b"m14-sr-contract")  # mesh world: SUPPORTED posture
    settings_live = client._transport.app.state.settings

    # a profile advertising the PRISTINE fixture contract (dd351121…)
    # while the machine computes the live one
    from soloring.observation.materializer import (
        build_materializer_contract,
        materializer_contract_hash,
    )

    live = materializer_contract_hash(build_materializer_contract())
    pristine = json.loads(
        (FIXTURES / "m14-f06-realization-profile-observation-v1.json")
        .read_bytes().decode("utf-8"))
    advertised = pristine["materializers"][0]["contract_hash"]
    assert advertised != live, "premise: the two contracts differ"

    def _install_pristine(docs):
        profile = _observation_profile()
        for materializer in profile["observation"]["materializers"]:
            if materializer["id"] == "soloring.observation.mesh_depth":
                materializer["contract_hash"] = advertised
        docs["realization-profile.json"] = profile
        return docs

    pkg = await _schema3_package(tmp_path, mutate=_install_pristine)
    settings = _spatial_settings(settings_live, pkg)
    engine = _engine_of(client)

    with pytest.raises(SoloRingError) as excinfo:
        await _generate(client, b["shot"], settings)
    assert "INTERNAL_INVARIANT" in str(excinfo.value.code)
    assert (await _run_query(engine, (
        "SELECT COUNT(*) FROM generations WHERE shot_id = :s"),
        {"s": b["shot"]})).scalar_one() == 0
    assert (await _run_query(engine, (
        "SELECT COUNT(*) FROM derived_observation_artifacts"),
        {})).scalar_one() == 0, (
        "no artifact may be published under a diverged contract")


async def test_worker_rejects_artifact_contract_divergence(
        client, tmp_path, monkeypatch):
    """The worker refuses an artifact whose (self-consistently re-pinned)
    captured contract differs from the stored WorldObservationSpec's
    materializer contract — the historical counterpart of the
    creation-side equality gate."""
    from tests.test_m14_b5_worker_closure import _run, _seed

    b, generation, spec4, manifest_v3, settings, engine = await _seed(
        client, tmp_path, tag=b"m14-sr-artifact-contract")

    wrong = "f" * 64
    async with engine.connect() as conn:
        artifact_row = (await conn.execute(text(
            "SELECT a.id, a.provenance_json FROM "
            "generation_derived_observation_inputs i "
            "JOIN derived_observation_artifacts a "
            "ON a.id = i.derived_observation_artifact_id "
            "WHERE i.generation_id = :g"),
            {"g": generation.id})).mappings().one()
        provenance = json.loads(artifact_row["provenance_json"])
        provenance["materializer_contract_hash"] = wrong
        from soloring.domain.canonical import (
            canonical_hash,
            canonical_json_str,
        )

        await conn.execute(text(
            "UPDATE derived_observation_artifacts SET "
            "materializer_contract_hash = :c, provenance_json = :pj, "
            "provenance_hash = :ph WHERE id = :a"),
            {"c": wrong, "pj": canonical_json_str(provenance),
             "ph": canonical_hash(provenance),
             "a": artifact_row["id"]})
        await conn.commit()

    from soloring.errors import SoloRingError

    with pytest.raises(SoloRingError) as excinfo:
        await _run(client, generation, spec4, manifest_v3, settings,
                   attempt="33333333-3333-4333-8333-333333333331")
    assert "DERIVED_SPATIAL_PROVENANCE_MISMATCH" in str(
        excinfo.value.code)


# ---- P0-3: PI placement resolves by the full §13.3 triple -------------------

async def _adopted_world(client, *, tag: bytes):
    from tests.test_m14_materializer import _mesh_doc, _observation_world

    return await _observation_world(
        client, tag=tag,
        sources=[{"kind": "mesh", "mesh": _mesh_doc(),
                  "transform": (0, 0, 0), "interpretation": (0, 0, 0)}],
        adopt_first_mesh=True)


async def _load_with(client, snapshot):
    from soloring.observation.retained import load_retained_mesh_sources
    from tests.test_m14_materializer import _reader

    engine = _engine_of(client)
    async with engine.connect() as conn:
        return await load_retained_mesh_sources(
            conn, _reader(client),
            captured_production_world=snapshot["production_world"],
            captured_spatial_pack=snapshot["spatial_continuity"])


async def _rewrite_captured_pack(engine, revision_id: str, mutate):
    """Rewrite the stored schema-6 snapshot's production_world pack
    (re-pinning snapshot_hash AND the companion production_world_hash)
    and return the mutated pack."""
    from soloring.domain.canonical import (
        canonical_hash,
        canonical_json_str,
    )
    from soloring.production_world.resolver import production_world_hash

    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT snapshot_json, snapshot_hash FROM shot_revisions "
            "WHERE id = :r"), {"r": revision_id})).mappings().one()
        snapshot = json.loads(row["snapshot_json"])
        mutate(snapshot)
        await conn.execute(text(
            "UPDATE shot_revisions SET snapshot_json = :sj, "
            "snapshot_hash = :sh WHERE id = :r"),
            {"sj": canonical_json_str(snapshot),
             "sh": canonical_hash(snapshot), "r": revision_id})
        await conn.execute(text(
            "UPDATE shot_revision_production_worlds "
            "SET production_world_hash = :pwh WHERE shot_revision_id = :r"),
            {"pwh": production_world_hash(
                snapshot["production_world"]), "r": revision_id})
        await conn.commit()
        return snapshot


async def test_pi_placement_wrong_composition_fails_closed(client):
    from soloring.errors import SoloRingError

    _b, snapshot, _oids, _prids = await _adopted_world(
        client, tag=b"m14-sr-pi-comp")
    revision_id = await _latest_revision(client, _b["shot"])

    def _mutate(snap):
        for state in snap["production_world"][
                "instance_spatial_states"]:
            state["composition_id"] = str(uuid.uuid4())

    engine = _engine_of(client)
    mutated = await _rewrite_captured_pack(
        engine, revision_id, _mutate)
    with pytest.raises(SoloRingError) as excinfo:
        await _load_with(client, mutated)
    assert "exactly one state" in str(excinfo.value.message)


async def test_pi_placement_wrong_occurrence_fails_closed(client):
    from soloring.errors import SoloRingError

    _b, snapshot, _oids, _prids = await _adopted_world(
        client, tag=b"m14-sr-pi-occ")
    revision_id = await _latest_revision(client, _b["shot"])

    def _mutate(snap):
        for state in snap["production_world"][
                "instance_spatial_states"]:
            state["occurrence_id"] = str(uuid.uuid4())

    engine = _engine_of(client)
    mutated = await _rewrite_captured_pack(
        engine, revision_id, _mutate)
    with pytest.raises(SoloRingError) as excinfo:
        await _load_with(client, mutated)
    assert "exactly one state" in str(excinfo.value.message)


async def test_pi_placement_duplicate_exact_match_fails_closed(client):
    from soloring.errors import SoloRingError

    _b, snapshot, _oids, _prids = await _adopted_world(
        client, tag=b"m14-sr-pi-dup")
    revision_id = await _latest_revision(client, _b["shot"])

    def _mutate(snap):
        states = snap["production_world"]["instance_spatial_states"]
        states.append(json.loads(json.dumps(states[0])))

    engine = _engine_of(client)
    mutated = await _rewrite_captured_pack(
        engine, revision_id, _mutate)
    with pytest.raises(SoloRingError) as excinfo:
        await _load_with(client, mutated)
    assert "exactly one state" in str(excinfo.value.message)


async def _latest_revision(client, shot_id: str) -> str:
    engine = _engine_of(client)
    return (await _run_query(engine, (
        "SELECT id FROM shot_revisions WHERE shot_id = :s "
        "ORDER BY revision_number DESC LIMIT 1"),
        {"s": shot_id})).scalar_one()


# ---- P1-5a: A4 no-conflicting-transform re-verification ----------------------

async def test_a4_conflicting_composition_transform_fails_closed(client):
    """Frozen §13.2: a bound occurrence's captured Composition transform
    must be the identity. A historically consistent but non-identity
    transform (re-pinned through the composition hash and the binding
    value pin) fails closed at load."""
    from soloring.domain.canonical import (
        canonical_hash,
        canonical_json_str,
    )
    from soloring.errors import SoloRingError

    _b, snapshot, oids, _prids = await _adopted_world(
        client, tag=b"m14-sr-a4-conflict")
    revision_id = await _latest_revision(client, _b["shot"])
    engine = _engine_of(client)

    comp_pin = snapshot["production_world"]["binding"]["value"][
        "composition_revision"]

    async with engine.connect() as conn:
        comp = json.loads((await conn.execute(text(
            "SELECT snapshot_json FROM composition_revisions "
            "WHERE id = :c"), {"c": comp_pin["revision_id"]}
        )).scalar_one())
        for occurrence in comp["occurrences"]:
            if occurrence["occurrence_id"] == oids[0]:
                occurrence["transform"]["translation_mm"] = [123, 0, 0]
        comp_hash = canonical_hash(comp)
        await conn.execute(text(
            "UPDATE composition_revisions SET snapshot_json = :sj, "
            "snapshot_hash = :sh WHERE id = :c"),
            {"sj": canonical_json_str(comp), "sh": comp_hash,
             "c": comp_pin["revision_id"]})
        await conn.commit()

    def _mutate(snap):
        snap["production_world"]["binding"]["value"][
            "composition_revision"]["snapshot_hash"] = comp_hash

    mutated = await _rewrite_captured_pack(
        engine, revision_id, _mutate)
    with pytest.raises(SoloRingError) as excinfo:
        await _load_with(client, mutated)
    assert "non-identity Composition transform" in (
        str(excinfo.value.message))


# ---- P1-4: schema-4 relational validation ------------------------------------

def _valid_spec4_fixture() -> dict:
    return json.loads(
        (FIXTURES / "m14-f06-workflow-spec-v4.json")
        .read_bytes().decode("utf-8"))


def _resign(spec4: dict) -> dict:
    """Re-derive the nested hashes so the corrupted value stays
    self-hashed — the exact class a structural-only validator misses."""
    from soloring.domain.canonical import canonical_hash

    observation = spec4["world_observation"]
    observation["spec_hash"] = canonical_hash(observation["spec"])
    observation["negotiation_hash"] = canonical_hash(
        observation["negotiation"])
    return spec4


def test_relational_row_order_swap_rejects():
    from soloring.errors import SoloRingError

    from soloring.observation.workflow_spec import parse_workflow_spec_v4

    spec4 = _resign(_valid_spec4_fixture())
    rows = spec4["world_observation"]["negotiation"]["requirements"]
    if len(rows) >= 2:
        rows[0], rows[1] = rows[1], rows[0]
    spec4 = _resign(spec4)
    with pytest.raises(SoloRingError, match="hash-match"):
        parse_workflow_spec_v4(spec4)


def test_relational_capability_echo_mismatch_rejects():
    from soloring.errors import SoloRingError

    from soloring.observation.workflow_spec import parse_workflow_spec_v4

    spec4 = _resign(_valid_spec4_fixture())
    for row in spec4["world_observation"]["negotiation"]["requirements"]:
        if row["verdict"] == "SUPPORTED" and row["capability"]:
            row["capability"]["source_contract"] = "forged.contract.v1"
            break
    spec4 = _resign(spec4)
    with pytest.raises(SoloRingError, match="echoes a capability"):
        parse_workflow_spec_v4(spec4)


def test_relational_policy_echo_mismatch_rejects():
    from soloring.errors import SoloRingError

    from soloring.observation.workflow_spec import parse_workflow_spec_v4

    spec4 = _resign(_valid_spec4_fixture())
    spec4["world_observation"]["negotiation"]["policy"]["id"] = (
        "forged-policy")
    spec4 = _resign(spec4)
    with pytest.raises(SoloRingError, match="policy"):
        parse_workflow_spec_v4(spec4)


def test_relational_verdict_inconsistency_rejects():
    from soloring.errors import SoloRingError

    from soloring.observation.workflow_spec import parse_workflow_spec_v4

    spec4 = _resign(_valid_spec4_fixture())
    spec4["world_observation"]["negotiation"]["verdict"] = "UNSUPPORTED"
    spec4 = _resign(spec4)
    with pytest.raises(SoloRingError, match="inconsistent"):
        parse_workflow_spec_v4(spec4)


def test_relational_capability_on_refused_row_rejects():
    from soloring.errors import SoloRingError

    from soloring.observation.workflow_spec import parse_workflow_spec_v4

    spec4 = _resign(_valid_spec4_fixture())
    for row in spec4["world_observation"]["negotiation"]["requirements"]:
        if row["verdict"] in ("UNSUPPORTED", "UNKNOWN",
                              "PERMITTED_INFERENCE"):
            # structurally complete (the structural validator accepts
            # it) — the RELATIONAL rule is what must refuse it
            row["capability"] = {
                "property": "forged", "preservation": "STRUCTURAL",
                "source_contract": "forged",
                "materializer_id": "soloring.observation.mesh_depth",
                "materializer_version": 1,
                "output_role": "observation.world_depth"}
            break
    else:
        pytest.skip("fixture carries no refused row")
    spec4 = _resign(spec4)
    with pytest.raises(SoloRingError, match="cannot echo"):
        parse_workflow_spec_v4(spec4)


async def test_worker_rejects_profile_hash_divergence(
        client, tmp_path, monkeypatch):
    """A schema-4 Generation whose stored observation profile_hash was
    corrupted AND re-canonicalized (self-consistent bytes/hash) refuses
    in the worker before any submission: the retained profile must be
    the profile the observation negotiated under."""
    from soloring.domain.canonical import (
        canonical_hash,
        canonical_json_str,
    )
    from tests.test_m14_b5_worker_closure import _seed

    b, generation, spec4, manifest_v3, settings, engine = await _seed(
        client, tmp_path, tag=b"m14-sr-profile-hash")

    spec4["world_observation"]["profile_hash"] = "e" * 64
    async with engine.connect() as conn:
        await conn.execute(text(
            "UPDATE generations SET workflow_spec_json = :sj, "
            "workflow_spec_hash = :sh WHERE id = :g"),
            {"sj": canonical_json_str(spec4),
             "sh": canonical_hash(spec4), "g": generation.id})
        await conn.commit()

    from soloring.errors import ErrorCode
    from tests.test_m10f_compatibility import _FakeExecutorClient

    fake = _FakeExecutorClient(
        b"profile-divergence-sentinel", output_node="80",
        output_field="images")

    async def _explode_submit(*args, **kwargs):
        raise AssertionError(
            "submission reached for a profile-divergent Generation")

    fake.submit_prompt = _explode_submit
    import soloring.worker.comfy_pipeline as cp
    from soloring.worker import ownership

    engine = _engine_of(client)
    worker = "w-m14-sr-profile"
    await ownership.acquire_worker_lease(engine, worker, 300)
    claim = await ownership.claim_next_generation(engine, worker)
    assert claim is not None and claim[0] == generation.id

    async def _cap(*a, **k):
        return object()

    monkeypatch.setattr(cp, "resolve_capability", _cap)
    monkeypatch.setattr(
        cp, "verify_schema3_runtime_environment",
        lambda *a, **k: None)
    status = await cp.drive_comfy_generation(
        engine, settings, worker, generation.id, claim[1], fake)
    assert status == "failed"
    async with engine.connect() as conn:
        code = (await conn.execute(text(
            "SELECT error_code FROM generations WHERE id = :g"),
            {"g": generation.id})).scalar_one()
    assert code == "INTERNAL_INVARIANT_VIOLATION"


# ---- P1-4b: inspector hardening ----------------------------------------------

async def test_inspector_rejects_spec_hash_divergence(client, tmp_path):
    from soloring.domain.canonical import canonical_hash
    from soloring.errors import SoloRingError

    from soloring.observation.inspection import read_captured_observation
    from tests.test_m14_b5_worker_closure import _seed
    from tests.conftest import make_tracked_maker

    b, generation, spec4, manifest_v3, settings, engine = await _seed(
        client, tmp_path, tag=b"m14-sr-inspector")
    # corrupt the stored bytes WITHOUT re-pinning the persisted hash
    spec4["world_observation"]["spec_hash"] = "d" * 64
    async with engine.connect() as conn:
        await conn.execute(text(
            "UPDATE generations SET workflow_spec_json = :sj "
            "WHERE id = :g"),
            {"sj": json.dumps(spec4), "g": generation.id})
        await conn.commit()

    maker = make_tracked_maker(engine)
    async with maker() as session:
        with pytest.raises(SoloRingError):
            await read_captured_observation(session, generation.id)


# ---- P1-5b: the §31 UX/API surface (real product routes) ---------------------

async def test_observation_readiness_route(client, tmp_path):
    """GET /shots/{id}/observation-readiness is the §31 product surface:
    the full refusal chain, capture currency, policy identity — through
    the real HTTP boundary."""
    from tests.test_m10e_generation import _spatial_settings
    from tests.test_m14_execution import (
        _observation_package,
        _schema6_world,
    )

    b, _sel, _rev, _snapshot = await _schema6_world(
        client, tag=b"m14-sr-route-readiness", mesh=False)
    pkg = await _observation_package(tmp_path)
    _spatial_settings(client._transport.app.state.settings, pkg)

    r = await client.get(f"/shots/{b['shot']}/observation-readiness")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["readiness"] == "refused"
    assert body["capture"]["schema_version"] == 6
    rows = {row["property"]: row for row in body["requirements"]}
    refusal = rows["occurrence.structure"]
    for field in ("property", "preservation", "enforcement",
                  "source_contract", "verdict", "explanation"):
        assert refusal[field]
    assert refusal["verdict"] == "UNSUPPORTED"
    assert body["policy"]["verdict"] in ("SUPPORTED", "UNSUPPORTED")
    assert body["policy"]["profile_hash"]

    r = await client.get("/shots/not-a-uuid/observation-readiness")
    assert r.status_code == 404


async def test_generation_observation_route(client, tmp_path):
    """GET /generations/{id}/observation is the §31 historical inspector
    surface: captured observation/artifact with the current environment
    separately labeled — through the real HTTP boundary."""
    from tests.test_m14_b5_worker_closure import _seed

    b, generation, spec4, manifest_v3, settings, engine = await _seed(
        client, tmp_path, tag=b"m14-sr-route-inspector")

    r = await client.get(f"/generations/{generation.id}/observation")
    assert r.status_code == 200, r.text
    body = r.json()
    captured = body["captured"]
    assert captured["observation_spec_hash"] == (
        spec4["world_observation"]["spec_hash"])
    assert captured["artifact"]["blob_hash"]
    assert captured["requirements"]
    environment = body["current_environment"]
    assert environment["contract_matches_captured"] in (True, False)
    assert "environment observation only" in environment["note"]

    r = await client.get(
        f"/generations/{str(uuid.uuid4())}/observation")
    assert r.status_code == 404


# ---- R2-P0: capability/materializer identity (CAP:04 full tuple) ------------

def _golden_spec_and_block():
    spec = json.loads(
        (FIXTURES / "m14-f06-world-observation-spec-v1.json")
        .read_bytes().decode("utf-8"))
    block = json.loads(
        (FIXTURES / "m14-f06-realization-profile-observation-v1.json")
        .read_bytes().decode("utf-8"))
    return spec, block


def test_two_materializer_capability_identity_is_the_exact_tuple():
    """A block carrying mesh_depth v1 AND v2 with the capability pointing
    at v2 does NOT support a spec pinned to v1 — the materializer
    identity is part of the capability coordinate (frozen §17/CAP:04)."""
    import copy

    from soloring.observation import negotiate

    spec, block = _golden_spec_and_block()
    v2 = copy.deepcopy(block["materializers"][0])
    v2["version"] = 2
    v2["contract_hash"] = "a" * 64
    block["materializers"].append(v2)
    for capability in block["capabilities"]:
        if (capability["property"], capability["preservation"]) == (
                "occurrence.structure", "STRUCTURAL"):
            capability["materializer_version"] = 2

    result = negotiate(spec, block)
    rows = result["requirements"]
    structure = [row for requirement, row in zip(spec["requirements"], rows)
                 if requirement["property"] == "occurrence.structure"]
    (row,) = structure
    assert row["verdict"] == "UNSUPPORTED", (
        "a capability for a DIFFERENT materializer version never "
        "supports the spec's pinned v1 materialization")
    assert result["verdict"] == "UNSUPPORTED"

    # the control: the same block with the capability back at v1 supports
    spec2, block2 = _golden_spec_and_block()
    v2b = copy.deepcopy(block2["materializers"][0])
    v2b["version"] = 2
    v2b["contract_hash"] = "a" * 64
    block2["materializers"].append(v2b)
    result2 = negotiate(spec2, block2)
    assert result2["verdict"] == result2_verdict_expected()


def result2_verdict_expected():
    from soloring.observation import negotiate
    spec, block = _golden_spec_and_block()
    return negotiate(spec, block)["verdict"]


def test_schema4_materializer_echo_mismatch_rejects():
    """A self-hashed schema-4 value whose echoed capability carries a
    DIFFERENT materializer identity than the spec's pinned materialization
    rejects under relational validation."""
    from soloring.errors import SoloRingError

    from soloring.observation.workflow_spec import parse_workflow_spec_v4

    spec4 = _resign(_valid_spec4_fixture())
    for row in spec4["world_observation"]["negotiation"]["requirements"]:
        if row["verdict"] == "SUPPORTED" and row["capability"]:
            row["capability"]["materializer_version"] = 2
            break
    spec4 = _resign(spec4)
    with pytest.raises(SoloRingError, match="materializer identity"):
        parse_workflow_spec_v4(spec4)


async def test_service_resolves_exact_v1_not_highest_version(
        client, tmp_path):
    """A profile declaring ONLY mesh_depth v2 (with its capability at
    v2) refuses with the typed policy outcome: the schema-1 grammar
    cannot pin v2, so no contract identity is fabricatable. A profile
    with v1+v2 executes under v1 — the capability and the spec both
    pin v1."""
    from soloring.errors import ErrorCode, SoloRingError
    from tests.test_m10e_generation import _spatial_settings
    from tests.test_m10e_package3_production import _schema3_package
    from tests.test_m14_execution import (
        _generate,
        _observation_profile,
        _schema6_world,
    )

    b, _sel, _rev, _snapshot = await _schema6_world(
        client, tag=b"m14-sr2-v2only")
    settings_live = client._transport.app.state.settings
    engine = _engine_of(client)

    def _bump_all_versions(profile):
        for materializer in profile["observation"]["materializers"]:
            materializer["version"] = 2
        for capability in profile["observation"]["capabilities"]:
            capability["materializer_version"] = 2
        return profile

    pkg_v2_only = await _schema3_package(
        tmp_path, mutate=lambda docs:
        docs | {"realization-profile.json": _bump_all_versions(
            _observation_profile())})
    settings = _spatial_settings(settings_live, pkg_v2_only)

    with pytest.raises(SoloRingError) as excinfo:
        await _generate(client, b["shot"], settings)
    assert excinfo.value.code == ErrorCode.OBSERVATION_POLICY_UNSUPPORTED
    assert (await _run_query(engine, (
        "SELECT COUNT(*) FROM generations WHERE shot_id = :s"),
        {"s": b["shot"]})).scalar_one() == 0

    # v1 + v2 both declared, capability at v1 → executes under v1
    def _add_v2(docs):
        import copy

        profile = _observation_profile()
        v2 = copy.deepcopy(profile["observation"]["materializers"][0])
        v2["version"] = 2
        v2["contract_hash"] = "b" * 64
        profile["observation"]["materializers"].append(v2)
        docs["realization-profile.json"] = profile
        return docs

    pkg_both = await _schema3_package(tmp_path, mutate=_add_v2)
    settings_both = _spatial_settings(settings_live, pkg_both)
    generation = await _generate(client, b["shot"], settings_both)
    spec = json.loads((await _run_query(engine, (
        "SELECT workflow_spec_json FROM generations WHERE id = :g"),
        {"g": generation.id})).scalar_one())
    pinned = spec["world_observation"]["spec"]["materializations"][0][
        "materializer"]
    assert pinned["version"] == 1, (
        "the schema-1 grammar pins v1 — the service resolves that exact "
        "entry even when a higher version is declared")




# ---- R2-P1: CreativeEntity exact-target placement ---------------------------

async def _entity_subject_world(client, *, tag: bytes, mode: str):
    """A captured schema-6 world whose single mesh occurrence is bound
    to a CreativeEntity subject with the given A4 placement mode
    ('track' — staged via an entity spatial track; 'frame' — bound to a
    world frame)."""
    from soloring.spatial import revisions as wrev_svc
    from soloring.spatial import tracks as track_svc
    from soloring.spatial import transitions as trans_svc
    from soloring.spatial import worlds as world_svc
    from tests.conftest import make_tracked_maker
    from tests.m13_seed import make_composition, mint, publish
    from tests.test_m13_binding import _adopt, _interpretation, _publish
    from tests.test_m13_shot_capture import _capture, _full_m13_world
    from tests.test_m14_materializer import (
        _mesh_doc,
        _mesh_production_revision,
        _write_blob,
        structural_mesh_bytes,
    )

    b = await _full_m13_world(client, tag=tag)
    factory = make_tracked_maker(_engine_of(client))
    if mode == "frame":
        async with _engine_of(client).connect() as conn:
            eva_rev = (await conn.execute(text(
                "SELECT revision_id FROM entity_approved_revisions "
                "WHERE entity_id = :e"), {"e": b["eva"]})).scalar_one()
        fr = await world_svc.create_frame(
            factory(), b["world"]["id"], key="evaseat", name="evaseat",
            parent_spatial_frame_id=None, bound_entity_id=b["eva"])
        await world_svc.put_state_frame(
            factory(), b["state"]["id"], fr["id"],
            translation_mm=[900, 0, 300], rotation_udeg=[0, 0, 0],
            half_extents_mm=None,
            bound_entity_revision_id=eva_rev)
        new_rev = await wrev_svc.capture_revision(
            factory(), b["state"]["id"])
        await wrev_svc.approve_revision(
            factory(), b["state"]["id"], revision_id=new_rev["id"],
            expected_approved_revision_id=b["rev"]["id"])
        world_revision_id = new_rev["id"]
    else:
        async with _engine_of(client).connect() as conn:
            seq = (await conn.execute(text(
                "SELECT id FROM sequences WHERE project_id = :p "
                "ORDER BY position LIMIT 1"),
                {"p": b["pid"]})).scalar_one()
        track = await track_svc.create_track(
            factory(), b["world"]["id"], entity_id=b["eva"],
            requirement="required")
        await trans_svc.create_transition(
            factory(), track["id"], anchor_type="sequence",
            anchor_id=seq, boundary="start", operation="set",
            translation_mm=[-800, 0, 200], rotation_udeg=[0, 0, 0])
        world_revision_id = b["rev"]["id"]

    blob = structural_mesh_bytes(_mesh_doc())
    await _write_blob(client, blob)
    prid = await _mesh_production_revision(
        client, b["pid"], blob, number=600)
    cid = await make_composition(client, b["pid"])
    m = await mint(client, cid, prid, 0)
    oid = m["occurrence_id"]
    await _interpretation(client, prid)
    await _adopt(client, cid, oid,
                 {"kind": "creative_entity", "creative_entity_id": b["eva"]})
    composed = (await publish(client, cid, 1))["revision"]["revision_id"]
    pr = await _publish(client, composed, world_revision_id)
    assert pr.status_code == 201, pr.text
    r = await client.put(
        f"/shots/{b['shot']}/production-world-selection",
        json={"binding_id": pr.json()["binding_id"],
              "expected_binding_id": None})
    assert r.status_code == 200, r.text
    revision, _ = await _capture(client, b["shot"])
    snapshot = json.loads(revision.snapshot_json)
    assert snapshot["schema_version"] == 6
    return b, snapshot, revision


async def _rewrite_spatial_pack(engine, revision_id: str, mutate):
    """Rewrite the captured schema-6 snapshot's spatial plane (re-pinning
    snapshot_hash AND the companion spatial_continuity_hash)."""
    from soloring.domain.canonical import (
        canonical_hash,
        canonical_json_str,
    )

    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT snapshot_json FROM shot_revisions WHERE id = :r"),
            {"r": revision_id})).mappings().one()
        snapshot = json.loads(row["snapshot_json"])
        mutate(snapshot)
        spatial_hash = canonical_hash(snapshot["spatial_continuity"])
        await conn.execute(text(
            "UPDATE shot_revisions SET snapshot_json = :sj, "
            "snapshot_hash = :sh WHERE id = :r"),
            {"sj": canonical_json_str(snapshot),
             "sh": canonical_hash(snapshot), "r": revision_id})
        await conn.execute(text(
            "UPDATE shot_revision_spatial_worlds SET "
            "spatial_continuity_hash = :h WHERE shot_revision_id = :r"),
            {"h": spatial_hash, "r": revision_id})
        await conn.commit()
        return snapshot


async def test_entity_track_wrong_track_fails_closed(client):
    from soloring.errors import SoloRingError

    b, snapshot, revision = await _entity_subject_world(
        client, tag=b"m14-sr2-etrack-wrong", mode="track")

    def _mutate(snap):
        for staged in snap["spatial_continuity"]["staging"]:
            staged["spatial_track_id"] = str(uuid.uuid4())

    engine = _engine_of(client)
    mutated = await _rewrite_spatial_pack(engine, revision.id, _mutate)
    with pytest.raises(SoloRingError, match="exactly one"):
        await _load_with(client, mutated)


async def test_entity_track_duplicate_exact_target_fails_closed(client):
    from soloring.errors import SoloRingError

    b, snapshot, revision = await _entity_subject_world(
        client, tag=b"m14-sr2-etrack-dup", mode="track")

    def _mutate(snap):
        staging = snap["spatial_continuity"]["staging"]
        staging.append(json.loads(json.dumps(staging[0])))

    engine = _engine_of(client)
    mutated = await _rewrite_spatial_pack(engine, revision.id, _mutate)
    with pytest.raises(SoloRingError, match="exactly one"):
        await _load_with(client, mutated)


async def test_entity_fixed_frame_wrong_frame_fails_closed(client):
    from soloring.errors import SoloRingError

    b, snapshot, revision = await _entity_subject_world(
        client, tag=b"m14-sr2-eframe-wrong", mode="frame")

    def _mutate(snap):
        for frame in snap["spatial_continuity"]["spatial_world"][
                "world_snapshot"]["frames"]:
            if frame.get("bound_entity_id") == b["eva"]:
                frame["spatial_frame_id"] = str(uuid.uuid4())

    engine = _engine_of(client)
    mutated = await _rewrite_spatial_pack(engine, revision.id, _mutate)
    with pytest.raises(SoloRingError, match="exactly one"):
        await _load_with(client, mutated)


async def test_entity_fixed_frame_duplicate_exact_target_fails_closed(
        client):
    from soloring.errors import SoloRingError

    b, snapshot, revision = await _entity_subject_world(
        client, tag=b"m14-sr2-eframe-dup", mode="frame")

    def _mutate(snap):
        frames = snap["spatial_continuity"]["spatial_world"][
            "world_snapshot"]["frames"]
        match = next(f for f in frames
                     if f.get("bound_entity_id") == b["eva"])
        frames.append(json.loads(json.dumps(match)))

    engine = _engine_of(client)
    mutated = await _rewrite_spatial_pack(engine, revision.id, _mutate)
    with pytest.raises(SoloRingError, match="exactly one"):
        await _load_with(client, mutated)


# ---- R2-P1: the inspector fails closed on missing/duplicate binding ----------

async def test_inspector_http_missing_binding_fails_closed(
        client, tmp_path):
    from tests.test_m14_b5_worker_closure import _seed

    b, generation, spec4, manifest_v3, settings, engine = await _seed(
        client, tmp_path, tag=b"m14-sr2-insp-missing")
    async with engine.connect() as conn:
        await conn.execute(text(
            "DELETE FROM generation_derived_observation_inputs "
            "WHERE generation_id = :g"), {"g": generation.id})
        await conn.commit()

    r = await client.get(f"/generations/{generation.id}/observation")
    assert r.status_code == 500, (
        "a schema-4 Generation without its binding is historical "
        "corruption, not a successful empty inspection")
    assert "missing its mandatory derived-observation binding" in (
        r.json().get("message", ""))


async def test_inspector_http_duplicate_binding_fails_closed(
        client, tmp_path):
    from tests.test_m14_b5_worker_closure import _seed

    b, generation, spec4, manifest_v3, settings, engine = await _seed(
        client, tmp_path, tag=b"m14-sr2-insp-dup")
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT input_key, artifact_role, "
            "derived_observation_artifact_id, blob_hash FROM "
            "generation_derived_observation_inputs WHERE generation_id "
            "= :g"), {"g": generation.id})).mappings().one()
        await conn.execute(text(
            "INSERT INTO generation_derived_observation_inputs "
            "(generation_id, input_key, position, artifact_role, "
            "derived_observation_artifact_id, blob_hash) VALUES "
            "(:g, :k, 1, :r, :a, :h)"),
            {"g": generation.id, "k": row["input_key"] + "-x",
             "r": row["artifact_role"],
             "a": row["derived_observation_artifact_id"],
             "h": row["blob_hash"]})
        await conn.commit()

    r = await client.get(f"/generations/{generation.id}/observation")
    assert r.status_code == 500
    assert "binding rows" in r.json().get("message", "")


async def test_inspector_http_missing_artifact_row_fails_closed(
        client, tmp_path):
    from tests.test_m14_b5_worker_closure import _seed

    b, generation, spec4, manifest_v3, settings, engine = await _seed(
        client, tmp_path, tag=b"m14-sr2-insp-artifact")
    # physical-corruption simulation: delete the artifact row with the
    # FK enforcement disabled on this one connection (the immediate-FK
    # schema cannot otherwise produce binding-without-artifact)
    async with engine.connect() as conn:
        await conn.exec_driver_sql("PRAGMA foreign_keys = OFF")
        await conn.execute(text(
            "DELETE FROM derived_observation_artifacts WHERE id IN ("
            "SELECT derived_observation_artifact_id FROM "
            "generation_derived_observation_inputs WHERE generation_id "
            "= :g)"), {"g": generation.id})
        await conn.commit()

    r = await client.get(f"/generations/{generation.id}/observation")
    assert r.status_code == 500
    assert "artifact row is missing" in r.json().get("message", "")
