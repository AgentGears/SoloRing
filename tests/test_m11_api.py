"""M11 API proofs (frozen R3 plan §20.9)."""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import text

from soloring.domain.ids import new_uuid

NOW = "2026-01-01T00:00:00.000Z"


async def _seed(client, data=b"api-bytes") -> tuple[str, str, str]:
    """project_id, asset_id, blob_hash with real physical bytes."""
    settings = client._transport.app.state.settings
    bh = hashlib.sha256(data).hexdigest()
    p = settings.blob_dir / "sha256" / bh[0:2] / bh[2:4] / bh
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    engine = client._transport.app.state.engine
    pid, aid = new_uuid(), new_uuid()
    async with engine.connect() as conn:
        await conn.execute(
            text("INSERT INTO projects (id, name, created_at, updated_at) "
                 "VALUES (:id, 'P', :n, :n)"), {"id": pid, "n": NOW})
        await conn.execute(
            text("INSERT INTO blobs (hash, path, size_bytes, detected_media_type, created_at) "
                 "VALUES (:h, :p, :s, 'image/png', :n)"),
            {"h": bh, "p": f"sha256/{bh[:2]}/{bh[2:4]}/{bh}", "s": len(data), "n": NOW})
        await conn.execute(
            text("INSERT INTO assets (id, project_id, blob_hash, kind, created_at) "
                 "VALUES (:a, :p, :h, 'reference', :n)"),
            {"a": aid, "p": pid, "h": bh, "n": NOW})
        await conn.commit()
    return pid, aid, bh


async def test_production_object_and_revision_happy_path(client):
    """M11-API:01 — complete backend product path."""
    pid, aid, bh = await _seed(client)
    r = await client.post(f"/projects/{pid}/production-objects",
                          json={"name": "Reception Desk", "description": None})
    assert r.status_code == 201, r.text
    obj = r.json()
    assert obj["name"] == "Reception Desk"

    r = await client.post(
        f"/production-objects/{obj['id']}/publication-readiness",
        json={"asset_id": aid})
    assert r.status_code == 200, r.text
    ready = r.json()
    assert ready["ready"] is True and ready["issues"] == []
    assert ready["closure"]["blob_hash"] == bh
    assert ready["proposed_snapshot_hash"]

    r = await client.post(f"/production-objects/{obj['id']}/revisions",
                          json={"asset_id": aid})
    assert r.status_code == 201, r.text
    rev = r.json()
    assert rev["created"] is True  # frozen §11.3: explicit convergence flag
    assert rev["revision_number"] == 1
    assert rev["closure"]["blob_hash"] == bh
    assert rev["blob_url"].startswith(f"/blobs/{bh[:2]}/{bh[2:4]}/")
    assert rev["physical_integrity"] == "not_full_hash_verified_in_this_view"
    assert [s["asset_id"] for s in rev["sources"]] == [aid]

    r = await client.get(f"/production-revisions/{rev['revision_id']}")
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["snapshot_hash"] == rev["snapshot_hash"]

    r = await client.get(f"/production-objects/{obj['id']}/revisions")
    assert r.status_code == 200
    assert [x["revision_number"] for x in r.json()] == [1]

    # Frozen §11.1: object DETAIL carries revision summaries, sorted ASC.
    r = await client.get(f"/production-objects/{obj['id']}")
    assert r.status_code == 200, r.text
    obj_detail = r.json()
    assert obj_detail["id"] == obj["id"]
    assert obj_detail["name"] == "Reception Desk"
    assert [x["revision_number"] for x in obj_detail["revisions"]] == [1]
    assert obj_detail["revisions"][0]["revision_id"] == rev["revision_id"]


async def test_publish_status_201_new_200_converged(client):
    """M11-API:02 — API convergence is explicit."""
    pid, aid, _ = await _seed(client)
    r = await client.post(f"/projects/{pid}/production-objects",
                          json={"name": "Desk"})
    oid = r.json()["id"]
    r1 = await client.post(f"/production-objects/{oid}/revisions",
                           json={"asset_id": aid})
    r2 = await client.post(f"/production-objects/{oid}/revisions",
                           json={"asset_id": aid})
    assert r1.status_code == 201 and r2.status_code == 200
    assert r1.json()["created"] is True
    assert r2.json()["created"] is False  # converged: explicit
    assert r1.json()["revision_id"] == r2.json()["revision_id"]

    # Not-ready publish → 409 with the complete readiness result.
    other_pid = new_uuid()
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        await conn.execute(
            text("INSERT INTO projects (id, name, created_at, updated_at) "
                 "VALUES (:id, 'Q', :n, :n)"), {"id": other_pid, "n": NOW})
        await conn.commit()
    r3 = await client.post(f"/projects/{other_pid}/production-objects",
                           json={"name": "Other"})
    other_oid = r3.json()["id"]
    r4 = await client.post(f"/production-objects/{other_oid}/revisions",
                           json={"asset_id": aid})
    assert r4.status_code == 409
    assert r4.json()["error_code"] == "PRODUCTION_REVISION_NOT_READY"
    codes = [i["code"] for i in r4.json()["details"]["readiness"]["issues"]]
    assert codes == ["SOURCE_PROJECT_MISMATCH"]


async def test_revision_detail_never_exposes_local_path(client):
    """M11-API:03 — storage paths remain internal."""
    pid, aid, bh = await _seed(client)
    r = await client.post(f"/projects/{pid}/production-objects", json={"name": "D"})
    oid = r.json()["id"]
    rev = (await client.post(f"/production-objects/{oid}/revisions",
                             json={"asset_id": aid})).json()
    blob = rev["blob_url"]
    assert blob == f"/blobs/{bh[:2]}/{bh[2:4]}/{bh}"
    detail_text = str(rev)
    settings = client._transport.app.state.settings
    assert str(settings.blob_dir) not in detail_text
    assert "sha256/" not in detail_text.replace(blob, "")
    r = await client.get(f"/production-revisions/{rev['revision_id']}")
    assert str(settings.blob_dir) not in r.text


async def test_revision_list_is_summary_only_and_sorted_by_revision_number(client):
    """M11-API:04 — bounded, summary-only, deterministic."""
    pid, aid, _ = await _seed(client, data=b"list-a")
    aid2, _, _ = None, None, None
    # second distinct blob
    data2 = b"list-b"
    settings = client._transport.app.state.settings
    bh2 = hashlib.sha256(data2).hexdigest()
    p2 = settings.blob_dir / "sha256" / bh2[0:2] / bh2[2:4] / bh2
    p2.parent.mkdir(parents=True, exist_ok=True)
    p2.write_bytes(data2)
    engine = client._transport.app.state.engine
    aid2 = new_uuid()
    async with engine.connect() as conn:
        await conn.execute(
            text("INSERT INTO blobs (hash, path, size_bytes, detected_media_type, created_at) "
                 "VALUES (:h, :p, :s, NULL, :n)"),
            {"h": bh2, "p": f"sha256/{bh2[:2]}/{bh2[2:4]}/{bh2}",
             "s": len(data2), "n": NOW})
        await conn.execute(
            text("INSERT INTO assets (id, project_id, blob_hash, kind, created_at) "
                 "VALUES (:a, :p, :h, 'reference', :n)"),
            {"a": aid2, "p": pid, "h": bh2, "n": NOW})
        await conn.commit()

    r = await client.post(f"/projects/{pid}/production-objects", json={"name": "D"})
    oid = r.json()["id"]
    for a in (aid2, aid):  # publish 2 then 1: numbers must still sort ASC
        rr = await client.post(f"/production-objects/{oid}/revisions",
                               json={"asset_id": a})
        assert rr.status_code == 201
    listing = (await client.get(f"/production-objects/{oid}/revisions")).json()
    assert [x["revision_number"] for x in listing] == [1, 2]
    for summary in listing:
        assert set(summary) == {"revision_id", "revision_number",
                                "snapshot_hash", "created_at"}


async def test_revision_detail_uses_metadata_verification_not_full_physical_hash(
    client, monkeypatch
):
    """M11-API:05 — browse does not turn into media re-hashing."""
    from soloring.assets.blob_store import BlobStore

    pid, aid, _ = await _seed(client, data=b"nohash" * 100)
    r = await client.post(f"/projects/{pid}/production-objects", json={"name": "D"})
    oid = r.json()["id"]
    rev = (await client.post(f"/production-objects/{oid}/revisions",
                             json={"asset_id": aid})).json()

    calls: list[str] = []
    orig = BlobStore.verify_physical_bytes

    async def _spied(self, blob_hash, expected_size):
        calls.append(blob_hash)
        return await orig(self, blob_hash, expected_size)

    monkeypatch.setattr(BlobStore, "verify_physical_bytes", _spied)
    r = await client.get(f"/production-revisions/{rev['revision_id']}")
    assert r.status_code == 200
    assert r.json()["physical_integrity"] == "not_full_hash_verified_in_this_view"
    assert calls == []
