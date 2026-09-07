"""Shared M13 test seeding helpers.

Builds the predecessor world (project, closed M11 Production Revision,
Creative Entity, Composition) through direct SQL plus the M12 API, so
M13 tests exercise the real predecessor seams.
"""

from __future__ import annotations

import hashlib

from sqlalchemy import text

from soloring.domain.ids import new_uuid

NOW = "2026-01-01T00:00:00.000Z"
SCOPE = "composition_working_state"


async def seed_base(client, *, tag: bytes = b"m13-seed") -> dict:
    """project + closed production revision (+source asset)."""
    settings = client._transport.app.state.settings
    bh = hashlib.sha256(tag).hexdigest()
    p = settings.blob_dir / "sha256" / bh[:2] / bh[2:4] / bh
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(tag)
    engine = client._transport.app.state.engine
    pid, prid, pobj, aid = new_uuid(), new_uuid(), new_uuid(), new_uuid()
    from soloring.production.canonical import (
        RetainedBlobClosure,
        production_revision_snapshot_json as sj,
        production_revision_snapshot_hash as sh,
    )
    closure = RetainedBlobClosure(
        blob_hash=bh, size_bytes=len(tag), media_type=None)
    async with engine.connect() as conn:
        await conn.execute(text(
            "INSERT INTO projects (id, name, created_at, updated_at) "
            "VALUES (:i, 'P', :n, :n)"), {"i": pid, "n": NOW})
        await conn.execute(text(
            "INSERT INTO blobs (hash, path, size_bytes, detected_media_type, "
            "created_at) VALUES (:h, :p, :s, NULL, :n)"),
            {"h": bh, "p": f"sha256/{bh[:2]}/{bh[2:4]}/{bh}",
             "s": len(tag), "n": NOW})
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
            "(:r, 'retained_blob', 1, :bh, :s, NULL)"),
            {"r": prid, "bh": bh, "s": len(tag)})
        await conn.execute(text(
            "INSERT INTO production_revision_source_assets "
            "(production_revision_id, asset_id, created_at) VALUES "
            "(:r, :a, :n)"), {"r": prid, "a": aid, "n": NOW})
        await conn.commit()
    return {"project_id": pid, "production_revision_id": prid,
            "production_object_id": pobj, "blob_hash": bh}


async def seed_second_revision(client, base: dict, *, number: int = 2) -> str:
    """A further closed revision of the same Production Object.

    Uses a distinct retained blob so the (production_object_id,
    snapshot_hash) uniqueness of M11 holds for genuinely different content.
    """
    settings = client._transport.app.state.settings
    tag = f"m13-rev-{number}".encode()
    bh = hashlib.sha256(tag).hexdigest()
    p = settings.blob_dir / "sha256" / bh[:2] / bh[2:4] / bh
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(tag)
    engine = client._transport.app.state.engine
    prid = new_uuid()
    from soloring.production.canonical import (
        RetainedBlobClosure,
        production_revision_snapshot_json as sj,
        production_revision_snapshot_hash as sh,
    )
    closure = RetainedBlobClosure(
        blob_hash=bh, size_bytes=len(tag), media_type=None)
    async with engine.connect() as conn:
        await conn.execute(text(
            "INSERT INTO blobs (hash, path, size_bytes, detected_media_type, "
            "created_at) VALUES (:h, :p, :s, NULL, :n)"),
            {"h": bh, "p": f"sha256/{bh[:2]}/{bh[2:4]}/{bh}",
             "s": len(tag), "n": NOW})
        await conn.execute(text(
            "INSERT INTO production_revisions (id, production_object_id, "
            "revision_number, snapshot_json, snapshot_hash, created_at) "
            "VALUES (:r, :o, :num, :sj, :sh, :n)"),
            {"r": prid, "o": base["production_object_id"], "num": number,
             "sj": sj(closure), "sh": sh(closure), "n": NOW})
        await conn.execute(text(
            "INSERT INTO production_revision_closures "
            "(production_revision_id, contract_key, contract_version, "
            "blob_hash, size_bytes, media_type) VALUES "
            "(:r, 'retained_blob', 1, :bh, :s, NULL)"),
            {"r": prid, "bh": bh, "s": len(tag)})
        await conn.commit()
    return prid


async def make_entity(client, project_id: str, *, kind: str = "prop",
                       name: str = "Chair E") -> str:
    engine = client._transport.app.state.engine
    eid = new_uuid()
    async with engine.connect() as conn:
        await conn.execute(text(
            "INSERT INTO creative_entities (id, project_id, kind, name, "
            "created_at, updated_at) VALUES (:e, :p, :k, :n, :t, :t)"),
            {"e": eid, "p": project_id, "k": kind, "n": name, "t": NOW})
        await conn.commit()
    return eid


async def make_composition(client, project_id: str, *,
                           name: str = "Lobby") -> str:
    r = await client.post(f"/projects/{project_id}/compositions",
                          json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _spec(prid: str, name: str = "Chair 7") -> dict:
    return {
        "display_name": name,
        "source": {"kind": "production_revision", "revision_id": prid},
        "visible": True,
        "transform": {"translation_mm": [0, 0, 0],
                      "rotation_udeg": [0, 0, 0]},
    }


async def mint(client, composition_id: str, prid: str, version: int, *,
               name: str = "Chair 7",
               transform: tuple = (0, 0, 0)) -> dict:
    spec = _spec(prid, name)
    if transform != (0, 0, 0):
        spec["transform"] = {"translation_mm": list(transform),
                             "rotation_udeg": [0, 0, 0]}
    r = await client.post(
        f"/compositions/{composition_id}/occurrences",
        json={"scope": SCOPE, "expected_working_version": version,
              **spec})
    assert r.status_code == 201, r.text
    return r.json()


async def mint_nested(client, composition_id: str, nested_revision_id: str,
                      version: int, *, name: str = "Nested") -> dict:
    spec = _spec(nested_revision_id, name)
    spec["source"] = {"kind": "composition_revision",
                      "revision_id": nested_revision_id}
    r = await client.post(
        f"/compositions/{composition_id}/occurrences",
        json={"scope": SCOPE, "expected_working_version": version, **spec})
    assert r.status_code == 201, r.text
    return r.json()


async def patch_source(client, composition_id: str, occurrence_id: str,
                       version: int, *, kind: str, revision_id: str) -> dict:
    r = await client.patch(
        f"/compositions/{composition_id}/occurrences/{occurrence_id}",
        json={"scope": SCOPE, "expected_working_version": version,
              "source": {"kind": kind, "revision_id": revision_id}})
    assert r.status_code == 200, r.text
    return r.json()


async def publish(client, composition_id: str,
                  expected_working_version: int) -> dict:
    r = await client.post(
        f"/compositions/{composition_id}/publish",
        json={"expected_working_version": expected_working_version})
    assert r.status_code in (200, 201), r.text
    return r.json()


async def identity_apply(client, composition_id: str, request: dict,
                         version: int) -> dict:
    """Preview + apply one identity operation, returning the apply body."""
    r = await client.post(
        f"/compositions/{composition_id}/identity-operations/preview",
        json={"scope": SCOPE, "request": request})
    assert r.status_code == 200, r.text
    pv = r.json()
    r = await client.post(
        f"/compositions/{composition_id}/identity-operations",
        json={"scope": SCOPE, "expected_working_version": version,
              "expected_request_fingerprint":
                  pv["request_fingerprint"],
              "expected_impact_fingerprint":
                  pv["impact_fingerprint"],
              "request": request})
    assert r.status_code == 200, r.text
    return r.json()


def _target_spec(prid: str, name: str) -> dict:
    return _spec(prid, name)


async def remove_occurrence(client, composition_id: str, occurrence_id: str,
                            version: int) -> dict:
    return await identity_apply(
        client, composition_id,
        {"kind": "remove", "source_occurrence_ids": [occurrence_id],
         "target_working_specs": []}, version)


async def fork_occurrence(client, composition_id: str, occurrence_id: str,
                          prid: str, version: int, *,
                          name: str = "Forked") -> dict:
    return await identity_apply(
        client, composition_id,
        {"kind": "fork", "source_occurrence_ids": [occurrence_id],
         "target_working_specs": [_target_spec(prid, name)]}, version)
