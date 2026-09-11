"""M14B-6 — observation UI projections (frozen R2 §§31/41; proof cells
M14-UI:01/02).

UI:01 — the execution-readiness projection exposes the typed refusal
trace property → preservation → authority/source → source contract →
verdict with a deterministic explanation, for every §41 negative
posture; no negative degrades to prompt text.

UI:02 — the historical inspector separates the captured observation/
artifact (read from stored bytes + immutable bound rows) from the
current environment (a separately labeled contract observation that
never alters any captured value).
"""

from __future__ import annotations

import json

import pytest

_CHAIN_FIELDS = (
    "property", "preservation", "enforcement", "authority",
    "source_contract", "verdict", "explanation")
_AUTHORITY_FIELDS = ("domain", "source_kind", "source_id", "source_hash")


def _maker(client):
    from tests.conftest import make_tracked_maker

    return make_tracked_maker(client._transport.app.state.engine)


async def _readiness(client, shot_id: str) -> dict:
    from soloring.observation.readiness import observation_readiness

    settings = client._transport.app.state.settings
    async with _maker(client)() as session:
        return await observation_readiness(session, settings, shot_id)


def _assert_trace(row: dict) -> None:
    assert all(field in row for field in _CHAIN_FIELDS), (
        "every requirement row carries the full typed chain")
    assert all(field in row["authority"] for field in _AUTHORITY_FIELDS)
    assert row["explanation"], "the explanation is never empty"
    for token in (row["property"], row["preservation"],
                  row["source_contract"]):
        assert token in row["explanation"], (
            "the explanation is derived from the typed trace, never "
            "free prompt text")


# ---- M14-UI:01 refusal traces ----------------------------------------------

async def test_m14_ui_01(client, tmp_path) -> None:
    """M14-UI:01 refusal traces property → preservation → authority/
    source → contract → verdict through the readiness projection, for
    the §41 captured-world negatives."""
    from tests.test_m14_execution import (
        _observation_package,
        _schema6_world,
    )
    from tests.test_m14_materializer import _mesh_doc, _observation_world

    # ---- N4: non-mesh retained blob → occurrence.structure UNSUPPORTED
    b, _sel, _rev, _snapshot = await _schema6_world(
        client, tag=b"m14-ui01-n4", mesh=False)
    pkg = await _observation_package(tmp_path)
    settings = client._transport.app.state.settings
    from tests.test_m10e_generation import _spatial_settings

    _spatial_settings(settings, pkg)
    projection = await _readiness(client, b["shot"])
    assert projection["readiness"] == "refused"
    rows = {r["property"]: r for r in projection["requirements"]}
    n4 = rows["occurrence.structure"]
    assert n4["verdict"] == "UNSUPPORTED"
    assert n4["source_contract"] == "unrecognized.retained_blob"
    assert n4["preservation"] == "STRUCTURAL"
    _assert_trace(n4)
    positions = [r["position"] for r in projection["requirements"]]
    assert positions == list(range(len(positions))), (
        "requirement rows are ordered")

    # ---- N3: nested Composition occurrence → typed unsupported
    from tests.m13_seed import make_composition, mint, mint_nested, publish
    from tests.test_m13_binding import _publish
    from tests.test_m13_shot_capture import (
        _capture,
        _full_m13_world,
        _select_binding,
    )

    b3 = await _full_m13_world(client, tag=b"m14-ui01-n3")
    nested_cid = await make_composition(client, b3["pid"])
    await mint(client, nested_cid, b3["production_revision_id"], 0)
    nested_revision = (await publish(
        client, nested_cid, 1))["revision"]["revision_id"]
    cid = await make_composition(client, b3["pid"])
    await mint(client, cid, b3["production_revision_id"], 0)
    await mint_nested(client, cid, nested_revision, 1)
    composed_revision = (await publish(
        client, cid, 2))["revision"]["revision_id"]
    pr = await _publish(client, composed_revision, b3["rev"]["id"])
    r = await client.put(
        f"/shots/{b3['shot']}/production-world-selection",
        json={"binding_id": pr.json()["binding_id"],
              "expected_binding_id": None})
    assert r.status_code == 200, r.text
    await _capture(client, b3["shot"])

    projection = await _readiness(client, b3["shot"])
    assert projection["readiness"] == "refused"
    rows = {r["property"]: r for r in projection["requirements"]}
    n3 = [r for r in projection["requirements"]
          if r["source_contract"] == "nested_composition.v1"]
    assert len(n3) == 1
    assert n3[0]["verdict"] == "UNSUPPORTED"
    _assert_trace(n3[0])

    # ---- N2: captured PI feature state → continuity.instance_feature
    b2, _snap2, oids, _prids = await _observation_world(
        client, tag=b"m14-ui01-n2",
        sources=[{"kind": "mesh", "mesh": _mesh_doc(),
                  "transform": (0, 0, 0),
                  "interpretation": (0, 0, 0)}],
        adopt_first_mesh=True)
    engine = client._transport.app.state.engine
    from sqlalchemy import text

    async with engine.connect() as conn:
        seq = (await conn.execute(text(
            "SELECT id FROM sequences WHERE project_id = :p "
            "ORDER BY position LIMIT 1"),
            {"p": b2["pid"]})).scalar_one()
    r = await client.post(
        f"/production-instances/{oids[0]}/features",
        json={"key": "fallen", "kind": "status", "value_type": "text",
              "name": "Fallen"})
    assert r.status_code == 201, r.text
    r = await client.post(
        f"/production-instance-features/{r.json()['id']}/transitions",
        json={"anchor_type": "sequence", "anchor_id": seq,
              "boundary": "start", "operation": "set", "value": "down"})
    assert r.status_code == 201, r.text
    await _capture(client, b2["shot"])

    projection = await _readiness(client, b2["shot"])
    assert projection["readiness"] == "refused"
    rows = {r["property"]: r for r in projection["requirements"]}
    n2 = rows["continuity.instance_feature"]
    assert n2["verdict"] == "UNSUPPORTED"
    assert n2["preservation"] == "EXACT"
    assert n2["source_contract"] == "m13.production_instance_feature.v1"
    _assert_trace(n2)

    # ---- N1: captured visual-reference pack → visual.identity UNSUPPORTED
    from tests.test_m8a_visual import _facet
    from tests.test_m8b_curation import _assets
    from tests.test_m8c_resolver import _approve_anchor

    b1 = await _full_m13_world(client, tag=b"m14-ui01-n1")
    assets = await _assets(engine, b1["pid"], 1)
    async with engine.connect() as conn:
        evarev = (await conn.execute(text(
            "SELECT revision_id FROM entity_approved_revisions "
            "WHERE entity_id = :e"),
            {"e": b1["eva"]})).scalar_one()
    facet = await _facet(client, b1["pid"], "entity",
                         entity_id=b1["eva"], facet_key="face")
    anchor = (await client.post(
        f"/visual-facets/{facet['id']}/anchors",
        json={"entity_revision_id": evarev})).json()["id"]
    await _approve_anchor(client, anchor, assets, ["front"])
    await _select_binding(client, b1)
    revision1, _ = await _capture(client, b1["shot"])
    snapshot1 = json.loads(revision1.snapshot_json)
    assert snapshot1["schema_version"] == 6
    assert snapshot1.get("visual_reference_pack"), (
        "premise: the captured revision carries a visual pack")

    projection = await _readiness(client, b1["shot"])
    assert projection["readiness"] == "refused"
    rows = {r["property"]: r for r in projection["requirements"]}
    n1 = rows["visual.identity"]
    assert n1["verdict"] == "UNSUPPORTED"
    assert n1["preservation"] == "IDENTITY_APPEARANCE"
    assert n1["source_contract"] == "m8.visual_reference_pack.v1"
    _assert_trace(n1)

    # ---- the fifth negative: a property unknown to the test profile
    # → UNKNOWN, still refusing (never a silent pass)
    from tests.test_m10e_package3_production import _schema3_package
    from tests.test_m14_execution import _observation_profile

    def _install_stripped_profile(docs):
        docs["realization-profile.json"] = _observation_profile()
        block = docs["realization-profile.json"]["observation"]
        block["capabilities"] = [
            c for c in block["capabilities"]
            if c["property"] != "camera.projection"]
        block["unsupported_capabilities"] = [
            c for c in block.get("unsupported_capabilities", [])
            if c["property"] != "camera.projection"]
        return docs

    pkg_unknown = await _schema3_package(
        tmp_path, mutate=_install_stripped_profile)
    _spatial_settings(settings, pkg_unknown)
    projection = await _readiness(client, b["shot"])
    assert projection["readiness"] == "refused"
    rows = {r["property"]: r for r in projection["requirements"]}
    unknown = rows["camera.projection"]
    assert unknown["verdict"] == "UNKNOWN", (
        "a REQUIRED property absent from both profile lists is the only "
        "UNKNOWN — and it still refuses")
    _assert_trace(unknown)
    assert "no declaration" in unknown["explanation"]


# ---- M14-UI:02 historical inspector separation ------------------------------

async def test_m14_ui_02(client, tmp_path, monkeypatch) -> None:
    """M14-UI:02 the historical inspector separates captured
    observation/artifact from the current environment: every captured
    value comes from the stored schema-4 bytes + bound artifact rows,
    and a CHANGED current materializer contract is only a labeled
    environment observation — the captured values are byte-identical
    before and after the divergence."""
    from soloring.observation.inspection import read_captured_observation
    from tests.test_m14_execution import (
        _comfy,
        _generate,
        _observation_package,
        _schema6_world,
    )

    b, _sel, _rev, _snapshot = await _schema6_world(
        client, tag=b"m14-ui02")
    pkg = await _observation_package(tmp_path)
    generation = await _generate(client, b["shot"], _comfy(client, pkg))

    async with _maker(client)() as session:
        before = await read_captured_observation(session, generation.id)

    captured = before["captured"]
    assert captured["policy_verdict"] == "SUPPORTED"
    assert captured["requirements"], "the captured verdict rows persist"
    for row in captured["requirements"]:
        assert all(field in row for field in _CHAIN_FIELDS[:-1])
    (occurrence,) = captured["production_occurrences"]
    assert occurrence["production_revision_id"]
    assert occurrence["production_revision_hash"]
    assert occurrence["retained_blob_hash"]
    artifact = captured["artifact"]
    assert artifact is not None
    assert artifact["materializer_id"] == "soloring.observation.mesh_depth"
    assert artifact["blob_hash"]
    assert artifact["source_retained_blob_hashes"] == [
        occurrence["retained_blob_hash"]]

    # the stored spec hash is the captured observation hash (not recomputed)
    engine = client._transport.app.state.engine
    from sqlalchemy import text

    async with engine.connect() as conn:
        stored = json.loads((await conn.execute(text(
            "SELECT workflow_spec_json FROM generations WHERE id = :g"),
            {"g": generation.id})).scalar_one())
    assert captured["observation_spec_hash"] == (
        stored["world_observation"]["spec_hash"])

    # current environment agreement is reported, never applied
    environment = before["current_environment"]
    assert environment["contract_matches_captured"] is True

    # ---- divergence: today's materializer contract changes; the
    # captured values must not move by one byte
    from soloring.observation import materializer as materializer_module

    real_contract = materializer_module.build_materializer_contract

    def _changed_contract(*, resource_limits=None):
        contract = real_contract(resource_limits=resource_limits)
        contract["runtime"]["numpy"] = "9.9.9-divergence-probe"
        return contract

    monkeypatch.setattr(materializer_module, "build_materializer_contract",
                        _changed_contract)
    async with _maker(client)() as session:
        after = await read_captured_observation(session, generation.id)
    assert after["captured"] == captured, (
        "a changed current materializer never rewrites any captured "
        "observation/artifact value")
    assert after["current_environment"][
        "contract_matches_captured"] is False, (
        "the divergence is surfaced as an environment observation")
    assert after["current_environment"][
        "materializer_contract_hash"] != (
        captured["artifact"]["materializer_contract_hash"])
