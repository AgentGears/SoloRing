"""M14A-3 — schema-4 historical storage + Exact Rerun (frozen R2 §§19/
26; proof cells M14-HIST:01-03).

A SUPPORTED schema-6 generation persists WorkflowSpec schema 4 with the
exact nested observation/negotiation bytes and hashes, and Exact Rerun
copies those bytes verbatim with no current-state compilation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import text

from soloring.domain.canonical import canonical_hash
from soloring.generation.rerun import create_rerun
from soloring.generation.service import create_generation_request

from tests.test_m14_execution import (
    _comfy,
    _factory,
    _observation_package,
    _schema6_world,
    _stored_spec,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "m14"


async def _supported_generation(client, tmp_path, *, tag):
    b, _sel, revision, _snapshot = await _schema6_world(client, tag=tag)
    pkg = await _observation_package(tmp_path)
    settings = _comfy(client, pkg)
    async with _factory(client)() as session:
        generation = await create_generation_request(
            session, b["shot"], settings=settings)
    return client, b, generation, pkg


async def _descriptor_profile_hash(pkg: Path) -> str:
    descriptor = json.loads(
        (pkg / "workflow-package.json").read_text(encoding="utf-8"))
    return descriptor["realization_profile_hash"]


def _test_m14_hist_body(client, tmp_path):
    return _supported_generation(client, tmp_path, tag=b"m14a3-hist")


async def test_m14_hist_01(client, tmp_path):
    """M14-HIST:01 schema-4 WorkflowSpec stores exact observation/hash."""
    client, b, generation, pkg = await _test_m14_hist_body(client, tmp_path)
    engine = client._transport.app.state.engine
    spec = await _stored_spec(engine, generation.id)

    import hashlib

    from soloring.domain.canonical import canonical_json_bytes
    from soloring.observation.spec import (
        parse_world_observation_spec,
        world_observation_spec_hash,
    )

    assert spec["schema_version"] == 4
    observation = spec["world_observation"]
    embedded = parse_world_observation_spec(observation["spec"])
    assert observation["spec"] == embedded
    assert observation["spec_hash"] == world_observation_spec_hash(embedded)
    assert observation["spec_hash"] == hashlib.sha256(
        canonical_json_bytes(embedded)).hexdigest()
    assert embedded["shot_revision"]["id"] == generation.shot_revision_id
    assert embedded["materializations"][0]["source_occurrence_ids"] == []


async def test_m14_hist_02(client, tmp_path):
    """M14-HIST:02 schema-4 stores exact negotiation/hash + capability-
    contract hash bound to the captured profile."""
    client, b, generation, pkg = await _test_m14_hist_body(client, tmp_path)
    engine = client._transport.app.state.engine
    spec = await _stored_spec(engine, generation.id)
    observation = spec["world_observation"]

    import hashlib

    from soloring.domain.canonical import canonical_json_bytes
    from soloring.observation.capability import (
        validate_negotiation_result,
    )

    negotiation = validate_negotiation_result(observation["negotiation"])
    assert negotiation["verdict"] == "SUPPORTED"
    assert observation["negotiation"] == negotiation
    assert observation["negotiation_hash"] == hashlib.sha256(
        canonical_json_bytes(negotiation)).hexdigest()

    profile = json.loads(
        (pkg / "realization-profile.json").read_text(encoding="utf-8"))
    assert observation["capability_contract_hash"] == canonical_hash(
        profile["observation"]), (
        "capability_contract_hash must be SHA-256 of the canonical "
        "captured observation block")
    assert observation["profile_hash"] == await _descriptor_profile_hash(pkg)


async def test_m14_hist_03(client, tmp_path):
    """M14-HIST:03 Exact Rerun copies exact schema-4 bytes/hash; no
    current-state compilation ever touches the observation."""
    client, b, generation, pkg = await _test_m14_hist_body(client, tmp_path)
    engine = client._transport.app.state.engine

    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT workflow_spec_json, workflow_spec_hash FROM "
            "generations WHERE id = :g"), {"g": generation.id})).mappings(
        ).one()
        await conn.execute(text(
            "UPDATE generations SET status = 'succeeded' WHERE id = :g"),
            {"g": generation.id})
        await conn.commit()

    async with _factory(client)() as session:
        rerun = await create_rerun(session, generation.id)

    assert rerun.id != generation.id
    async with engine.connect() as conn:
        rerun_row = (await conn.execute(text(
            "SELECT workflow_spec_json, workflow_spec_hash FROM "
            "generations WHERE id = :g"), {"g": rerun.id})).mappings().one()

    assert rerun_row["workflow_spec_json"] == row["workflow_spec_json"], (
        "Exact Rerun must copy the schema-4 bytes verbatim")
    assert rerun_row["workflow_spec_hash"] == row["workflow_spec_hash"]
    assert canonical_hash(json.loads(rerun_row["workflow_spec_json"])) == (
        rerun_row["workflow_spec_hash"])
