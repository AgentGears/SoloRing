"""M12 API proofs (frozen R3 §21 M12-API)."""

from __future__ import annotations

import hashlib
import json

import pytest
from sqlalchemy import text

from soloring.domain.ids import new_uuid

NOW = "2026-01-01T00:00:00.000Z"
SCOPE = "composition_working_state"


async def _seed(client) -> tuple[str, str]:
    """project_id, production_revision_id with real M11 closure."""
    settings = client._transport.app.state.settings
    bh = hashlib.sha256(b"m12-api").hexdigest()
    p = settings.blob_dir / "sha256" / bh[:2] / bh[2:4] / bh
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"m12-api")
    engine = client._transport.app.state.engine
    pid, prid, pobj, aid = new_uuid(), new_uuid(), new_uuid(), new_uuid()
    from soloring.production.canonical import RetainedBlobClosure
    from soloring.production.canonical import (
        production_revision_snapshot_json as sj,
        production_revision_snapshot_hash as sh,
    )
    closure = RetainedBlobClosure(blob_hash=bh, size_bytes=6, media_type=None)
    async with engine.connect() as conn:
        await conn.execute(text(
            "INSERT INTO projects (id, name, created_at, updated_at) "
            "VALUES (:i, 'P', :n, :n)"), {"i": pid, "n": NOW})
        await conn.execute(text(
            "INSERT INTO blobs (hash, path, size_bytes, detected_media_type, "
            "created_at) VALUES (:h, :p, 6, NULL, :n)"),
            {"h": bh, "p": f"sha256/{bh[:2]}/{bh[2:4]}/{bh}", "n": NOW})
        await conn.execute(text(
            "INSERT INTO assets (id, project_id, blob_hash, kind, created_at) "
            "VALUES (:a, :p, :h, 'reference', :n)"),
            {"a": aid, "p": pid, "h": bh, "n": NOW})
        await conn.execute(text(
            "INSERT INTO production_objects (id, project_id, name, created_at, "
            "updated_at) VALUES (:o, :p, 'Obj', :n, :n)"),
            {"o": pobj, "p": pid, "n": NOW})
        await conn.execute(text(
            "INSERT INTO production_revisions (id, production_object_id, "
            "revision_number, snapshot_json, snapshot_hash, created_at) "
            "VALUES (:r, :o, 1, :sj, :sh, :n)"),
            {"r": prid, "o": pobj, "sj": sj(closure), "sh": sh(closure),
             "n": NOW})
        await conn.execute(text(
            "INSERT INTO production_revision_closures "
            "(production_revision_id, contract_key, contract_version, "
            "blob_hash, size_bytes, media_type) VALUES "
            "(:r, 'retained_blob', 1, :bh, 6, NULL)"), {"r": prid, "bh": bh})
        await conn.execute(text(
            "INSERT INTO production_revision_source_assets "
            "(production_revision_id, asset_id, created_at) VALUES "
            "(:r, :a, :n)"), {"r": prid, "a": aid, "n": NOW})
        await conn.commit()
    return pid, prid


def _mint_body(prid, version, name="Chair 7") -> dict:
    return {
        "scope": SCOPE,
        "expected_working_version": version,
        "display_name": name,
        "source": {"kind": "production_revision", "revision_id": prid},
        "visible": True,
        "transform": {"translation_mm": [0, 0, 0], "rotation_udeg": [0, 0, 0]},
    }


async def test_api_create_list_detail_composition(client):
    """M12-API:01."""
    pid, _ = await _seed(client)
    r = await client.post(f"/projects/{pid}/compositions",
                          json={"name": "Lobby", "description": None})
    assert r.status_code == 201, r.text
    comp = r.json()
    assert comp["metadata_version"] == 0 and comp["working_version"] == 0
    assert comp["working_occurrence_count"] == 0
    r = await client.get(f"/projects/{pid}/compositions")
    assert [c["id"] for c in r.json()] == [comp["id"]]
    r = await client.get(f"/compositions/{comp['id']}")
    assert r.status_code == 200 and r.json()["name"] == "Lobby"


async def test_api_mint_and_patch_occurrence_returns_stable_id_and_version(
    client
):
    """M12-API:02 + scope cells M12-SCOPE:01/02/03 at HTTP level."""
    pid, prid = await _seed(client)
    cid = (await client.post(f"/projects/{pid}/compositions",
                             json={"name": "Lobby"})).json()["id"]
    r = await client.post(f"/compositions/{cid}/occurrences",
                          json=_mint_body(prid, 0))
    assert r.status_code == 201, r.text
    m = r.json()
    occ, version = m["occurrence_id"], m["working_version"]
    assert version == 1

    r = await client.patch(
        f"/compositions/{cid}/occurrences/{occ}",
        json={"scope": SCOPE, "expected_working_version": 1,
              "display_name": "Renamed"})
    assert r.status_code == 200, r.text
    assert r.json()["working_version"] == 2

    # bad scope rejected at HTTP level
    for bad_scope in ("shot_local", "unknown", None):
        body = _mint_body(prid, 2)
        body["scope"] = bad_scope
        r = await client.post(f"/compositions/{cid}/occurrences", json=body)
        assert r.status_code == 422, r.text


async def test_api_identity_preview_then_apply_requires_both_fingerprints(
    client
):
    """M12-API:03."""
    pid, prid = await _seed(client)
    cid = (await client.post(f"/projects/{pid}/compositions",
                             json={"name": "Lobby"})).json()["id"]
    occ = (await client.post(f"/compositions/{cid}/occurrences",
                             json=_mint_body(prid, 0))).json()["occurrence_id"]
    request = {
        "kind": "remove",
        "source_occurrence_ids": [occ],
        "target_working_specs": [],
    }
    p = (await client.post(
        f"/compositions/{cid}/identity-operations/preview",
        json=request)).json()
    assert p["allowed"] and p["request_fingerprint"] and p["impact_fingerprint"]

    r = await client.post(
        f"/compositions/{cid}/identity-operations",
        json={"scope": SCOPE, "expected_working_version": 1,
              "expected_request_fingerprint": p["request_fingerprint"],
              "expected_impact_fingerprint": p["impact_fingerprint"],
              "request": request})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["kind"] == "remove" and out["working_version"] == 2

    # wrong fingerprint replay → 409 with a closed reason
    r = await client.post(
        f"/compositions/{cid}/identity-operations",
        json={"scope": SCOPE, "expected_working_version": 2,
              "expected_request_fingerprint": "0" * 64,
              "expected_impact_fingerprint": p["impact_fingerprint"],
              "request": request})
    assert r.status_code == 409
    assert r.json()["details"]["reason"] == "stale_request"


async def test_api_publish_returns_201_created_and_200_converged(client):
    """M12-API:04."""
    pid, prid = await _seed(client)
    cid = (await client.post(f"/projects/{pid}/compositions",
                             json={"name": "Lobby"})).json()["id"]
    await client.post(f"/compositions/{cid}/occurrences",
                      json=_mint_body(prid, 0))
    r1 = await client.post(f"/compositions/{cid}/publish",
                           json={"expected_working_version": 1})
    assert r1.status_code == 201, r1.text
    assert r1.json()["created"] is True
    r2 = await client.post(f"/compositions/{cid}/publish",
                           json={"expected_working_version": 1})
    assert r2.status_code == 200 and r2.json()["created"] is False
    assert (r1.json()["revision"]["revision_id"]
            == r2.json()["revision"]["revision_id"])


async def test_api_revision_detail_exposes_exact_occurrence_and_dependency_identity(
    client
):
    """M12-API:05."""
    pid, prid = await _seed(client)
    cid = (await client.post(f"/projects/{pid}/compositions",
                             json={"name": "Lobby"})).json()["id"]
    occ = (await client.post(f"/compositions/{cid}/occurrences",
                             json=_mint_body(prid, 0))).json()["occurrence_id"]
    rev = (await client.post(f"/compositions/{cid}/publish",
                             json={"expected_working_version": 1})).json()["revision"]
    r = await client.get(f"/composition-revisions/{rev['revision_id']}")
    assert r.status_code == 200, r.text
    detail = r.json()
    parsed = json.loads(detail["snapshot_json"])
    assert parsed["occurrences"][0]["occurrence_id"] == occ
    assert parsed["dependencies"]["production_revision_ids"] == [prid]
    # current name change cannot alter history
    await client.patch(f"/compositions/{cid}/occurrences/{occ}",
                       json={"scope": SCOPE, "expected_working_version": 1,
                             "display_name": "Later"})
    r2 = await client.get(f"/composition-revisions/{rev['revision_id']}")
    assert r2.json()["snapshot_hash"] == detail["snapshot_hash"]


async def test_api_has_no_occurrence_delete_endpoint(client):
    """M12-API:06 / M12-SCOPE:05 — removal must use identity operations."""
    pid, prid = await _seed(client)
    cid = (await client.post(f"/projects/{pid}/compositions",
                             json={"name": "Lobby"})).json()["id"]
    occ = (await client.post(f"/compositions/{cid}/occurrences",
                             json=_mint_body(prid, 0))).json()["occurrence_id"]
    r = await client.delete(f"/compositions/{cid}/occurrences/{occ}")
    assert r.status_code == 405  # no DELETE route exists


async def test_api_list_endpoints_use_stable_cursor_pagination(client):
    """M12-API:07."""
    pid, prid = await _seed(client)
    cid = (await client.post(f"/projects/{pid}/compositions",
                             json={"name": "Lobby"})).json()["id"]
    for i in range(3):
        await client.post(
            f"/compositions/{cid}/occurrences",
            json=_mint_body(prid, i, name=f"Chair {i}"))
    r = await client.get(f"/compositions/{cid}/occurrences?limit=2")
    first_two = r.json()
    assert len(first_two) == 2
    cursor = first_two[-1]["occurrence_id"]
    r2 = await client.get(
        f"/compositions/{cid}/occurrences?limit=2&cursor={cursor}")
    assert len(r2.json()) == 1
    ids = [o["occurrence_id"] for o in first_two + r2.json()]
    assert ids == sorted(ids)  # stable occurrence-id order


async def test_metadata_patch_requires_metadata_version_and_does_not_advance_working_version(
    client
):
    """M12-API:08."""
    pid, prid = await _seed(client)
    cid = (await client.post(f"/projects/{pid}/compositions",
                             json={"name": "Lobby"})).json()["id"]
    await client.post(f"/compositions/{cid}/occurrences",
                      json=_mint_body(prid, 0))
    r = await client.patch(
        f"/compositions/{cid}",
        json={"expected_metadata_version": 0, "name": "Grand Lobby"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["metadata_version"] == 1 and body["working_version"] == 1
    # stale metadata version → 409
    r = await client.patch(
        f"/compositions/{cid}",
        json={"expected_metadata_version": 0, "name": "Stale"})
    assert r.status_code == 409
    assert r.json()["details"]["reason"] == "stale_metadata_version"
