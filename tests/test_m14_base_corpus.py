"""M14A-3/B-6 — predecessor regression corpora (frozen R2 §38 E1-E2;
proof cells M14-BASE:04/05/06).

Schema 1/2/3 execution meaning is unchanged by the M14A-3 integration:
the schema-5 spatial path still composes exactly schema 3 through the
same frozen seam, byte-for-byte. The ShotRevision lattice 1..6 stays
green as one historical corpus, and the predecessor proof/boundary/
security validators remain green across the whole M14 surface.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text

from tests.test_m10e_generation import _create, _spatial_seed, _spatial_settings
from tests.test_m10e_package3_production import _schema3_package


async def test_m14_base_04(factory, engine, settings, tmp_path):
    """M14-BASE:04 WorkflowSpec schema-1/2/3 regression corpus green.

    The M10E schema-5 spatial path through the integrated service still
    produces exactly schema 3 — the M14A-3 branch is unreachable for
    schema ≤ 5."""
    pkg = await _schema3_package(tmp_path)
    seed = await _spatial_seed(factory, staged=1, extents=[600, 400, 300])
    generation = await _create(
        factory, _spatial_settings(settings, pkg), seed)

    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT workflow_spec_json, workflow_spec_hash FROM "
            "generations WHERE id = :g"),
            {"g": generation.id})).mappings().one()
    spec = json.loads(row["workflow_spec_json"])

    assert spec["schema_version"] == 3, (
        "schema-5 captures compose exactly schema 3 — unchanged by M14A-3")
    assert "world_observation" not in spec
    assert "spatial_realization" in spec

    from soloring.domain.canonical import canonical_hash

    assert canonical_hash(spec) == row["workflow_spec_hash"]

    from soloring.spatial.spec3 import validate_spec_v3

    validate_spec_v3(spec)


# ---- M14-BASE:05 ShotRevision schema-1..6 historical corpus ----------------

async def test_m14_base_05(client, factory, engine):
    """M14-BASE:05 ShotRevision schema-1..6 historical corpus green.

    One coherent corpus of six immutable ShotRevisions — one per schema
    level of the historical lattice. Every stored revision verifies its
    canonical bytes against its stored hash and remains legible through
    the historical read. M14 changed no capture semantics for schema
    ≤ 5 and extended the lattice additively with schema 6."""
    from soloring.domain.canonical import canonical_hash, canonical_json_str
    from soloring.domain import revisions as revision_svc
    from soloring.api.schemas.shots import ShotCreate
    from soloring.domain import shots as shot_svc

    from tests.test_m8a_visual import (
        _entity_with_revision,
        _feature,
        _seed_project,
    )
    from tests.test_m8c_resolver import _depend, _topology

    async def _capture(shot_id: str):
        async with factory() as s:
            return await revision_svc.capture_revision(s, shot_id)

    def _verify(revision, expected_schema: int) -> None:
        snapshot = json.loads(revision.snapshot_json)
        assert snapshot["schema_version"] == expected_schema
        assert revision.snapshot_json == canonical_json_str(snapshot), (
            f"schema-{expected_schema} snapshot must be the canonical "
            "encoding")
        assert revision.snapshot_hash == canonical_hash(snapshot)
        return snapshot

    corpus: dict[int, tuple] = {}

    # schema 1 — zero dependencies: the exact v1 form
    pid = await _seed_project(factory)
    async with factory() as s:
        bare = (await shot_svc.create_shot(
            s, pid, ShotCreate(subject="bare"))).id
    rev1 = await _capture(bare)
    snap1 = _verify(rev1, 1)
    assert rev1.continuity_spec_json is None
    corpus[1] = (bare, rev1, snap1)

    # schema 2 — dependencies, no effective states, no visual pack
    eva, _rev = await _entity_with_revision(client, factory, pid)
    _seq, scene2, shots2 = await _topology(client, factory, pid)
    await _depend(client, shots2[0], [eva["id"]])
    rev2 = await _capture(shots2[0])
    snap2 = _verify(rev2, 2)
    assert snap2["continuity"]["schema_version"] == 1
    corpus[2] = (shots2[0], rev2, snap2)

    # schema 3 — dependencies + effective feature states, no visual pack
    feat = await _feature(client, eva["id"])
    r = await client.post(
        f"/continuity-features/{feat['id']}/transitions",
        json={"anchor_type": "scene", "anchor_id": scene2,
              "boundary": "start", "operation": "set", "value": "fresh"})
    assert r.status_code == 201, r.text
    rev3 = await _capture(shots2[0])
    snap3 = _verify(rev3, 3)
    assert snap3["continuity"]["schema_version"] == 2
    assert snap3["continuity"]["feature_states"]
    corpus[3] = (shots2[0], rev3, snap3)

    # schema 4 — visual-reference pack over the schema-2 base
    from tests.test_m8b_curation import _assets
    from tests.test_m8c_resolver import _approve_anchor

    assets = await _assets(engine, pid, 1)
    r = await client.post(
        "/projects/{p}/visual-facets".format(p=pid),
        json={"target_kind": "entity", "facet_key": "face",
              "requirement": "required", "entity_id": eva["id"]})
    assert r.status_code == 201, r.text
    face_anchor = (await client.post(
        "/visual-facets/{f}/anchors".format(f=r.json()["id"]),
        json={"entity_revision_id": corpus[2][2] and _rev})).json()["id"]
    await _approve_anchor(client, face_anchor, assets, ["front"])
    rev4 = await _capture(shots2[0])
    snap4 = _verify(rev4, 4)
    assert snap4["visual_reference_pack"]["anchors"]
    corpus[4] = (shots2[0], rev4, snap4)

    # schema 5 — the M10 spatial plane over the same base (new world)
    from tests.test_m13_shot_capture import _capture as _m13_capture
    from tests.test_m13_shot_capture import _full_m13_world

    b5 = await _full_m13_world(client, tag=b"m14-base05-s5")
    rev5, _ = await _m13_capture(client, b5["shot"])
    snap5 = _verify(rev5, 5)
    assert snap5["spatial_continuity"]["schema_version"] == 1
    assert "production_world" not in snap5
    corpus[5] = (b5["shot"], rev5, snap5)

    # schema 6 — the M13 production world over the exact schema-5 base
    from tests.test_m13_shot_capture import _select_binding

    await _select_binding(client, b5)
    rev6, _ = await _m13_capture(client, b5["shot"])
    snap6 = _verify(rev6, 6)
    assert snap6["production_world"]["schema_version"] == 1
    corpus[6] = (b5["shot"], rev6, snap6)

    # the historical read stays green for every level of the corpus
    for schema_level, (shot_id, revision, _snap) in sorted(
            corpus.items()):
        r = await client.get(f"/shots/{shot_id}/revisions")
        assert r.status_code == 200, r.text
        ids = [row["id"] for row in r.json()]
        assert revision.id in ids, (
            f"schema-{schema_level} revision missing from the "
            "historical read")


# ---- M14-BASE:06 predecessor validators stay green -------------------------

_PREDECESSOR_VALIDATORS = (
    "m10f_validate_proof_map.py",
    "m11_validate_proof_map.py",
    "m12_validate_proof_map.py",
    "m13_validate_proof_map.py",
    "m13_validate_boundary.py",
    "hygiene_validate_proof_map.py",
    "hygiene_validate_boundary.py",
    "next_security_validate_proof_map.py",
    "next_security_validate_boundary.py",
)


def test_m14_base_06() -> None:
    """M14-BASE:06 predecessor proof/boundary/security validators green.

    The nine predecessor validators CI wires ahead of the M14 four —
    proof maps (M10F/M11/M12/M13/hygiene/next-security) and boundary
    gates (M13/hygiene/next-security) — each exit 0 against the current
    tree: the M14 surface never regressed a frozen predecessor gate."""
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    for name in _PREDECESSOR_VALIDATORS:
        result = subprocess.run(
            [sys.executable, str(scripts / name)],
            capture_output=True, text=True, cwd=str(scripts.parent),
        )
        assert result.returncode == 0, (
            f"predecessor validator {name} failed:\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")

