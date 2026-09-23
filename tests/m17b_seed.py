"""M17B test helpers: project/entity scaffolding, direct-SQL
production-object/revision seeding (the established m13_seed pattern),
and a candidate-body builder mirroring the frozen payload grammar."""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import text

NOW = "2026-01-01T00:00:00.000Z"


async def make_project(client, name: str = "M17B Test") -> str:
    r = await client.post("/projects", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def make_entity(client, pid: str, name: str = "Eva") -> str:
    r = await client.post(f"/projects/{pid}/entities",
                          json={"kind": "character", "name": name})
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    r = await client.post(f"/entities/{eid}/revisions",
                          json={"spec": {"description": name}})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    r = await client.put(f"/entities/{eid}/approved-revision",
                         json={"revision_id": rid,
                               "expected_approved_revision_id": None})
    assert r.status_code == 200, r.text
    return eid


async def seed_production_object(client, pid: str, label: str,
                                 tag: bytes) -> str:
    """One production object under the project (direct SQL, the
    m13_seed pattern)."""
    from soloring.domain.ids import new_uuid
    engine = client._transport.app.state.engine
    pobj = new_uuid()
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO production_objects (id, project_id, name, "
            "created_at, updated_at) VALUES (:o, :p, :l, :n, :n)"),
            {"o": pobj, "p": pid, "l": label, "n": NOW})
    return pobj


async def seed_production_revision(client, pobj: str, tag: bytes,
                                   number: int) -> dict:
    """One closed production revision with a retained-blob closure."""
    from soloring.domain.ids import new_uuid
    from soloring.production.canonical import (
        RetainedBlobClosure,
        production_revision_snapshot_json as sj,
        production_revision_snapshot_hash as sh,
    )
    settings = client._transport.app.state.settings
    bh = hashlib.sha256(tag).hexdigest()
    p = settings.blob_dir / "sha256" / bh[:2] / bh[2:4] / bh
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(tag)
    closure = RetainedBlobClosure(
        blob_hash=bh, size_bytes=len(tag), media_type=None)
    engine = client._transport.app.state.engine
    prid, aid = new_uuid(), new_uuid()
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT OR IGNORE INTO blobs (hash, path, size_bytes, "
            "detected_media_type, created_at) VALUES (:h, :p, :s, NULL, "
            ":n)"),
            {"h": bh, "p": f"sha256/{bh[:2]}/{bh[2:4]}/{bh}",
             "s": len(tag), "n": NOW})
        await conn.execute(text(
            "INSERT INTO production_revisions (id, "
            "production_object_id, revision_number, snapshot_json, "
            "snapshot_hash, created_at) VALUES (:r, :o, :n2, :sj, :sh, "
            ":n)"),
            {"r": prid, "o": pobj, "n2": number, "sj": sj(closure),
             "sh": sh(closure), "n": NOW})
        await conn.execute(text(
            "INSERT INTO production_revision_closures "
            "(production_revision_id, contract_key, "
            "contract_version, blob_hash, size_bytes, media_type) "
            "VALUES (:r, 'retained_blob', 1, :bh, :s, NULL)"),
            {"r": prid, "bh": bh, "s": len(tag)})
        await conn.execute(text(
            "INSERT INTO assets (id, project_id, blob_hash, kind, "
            "created_at) SELECT :a, po.project_id, :h, 'reference', "
            ":n FROM production_objects po WHERE po.id = :o"),
            {"a": aid, "h": bh, "n": NOW, "o": pobj})
        await conn.execute(text(
            "INSERT INTO production_revision_source_assets "
            "(production_revision_id, asset_id, created_at) VALUES "
            "(:r, :a2, :n)"),
            {"r": prid, "a2": aid, "n": NOW})
    return {"production_revision_id": prid,
            "production_object_id": pobj, "snapshot_hash":
                sh(closure)}


def channel(meta: tuple, keyframes: list[dict]) -> dict:
    key, domain, role, semantic, grammar = meta
    return {"channel_key": key, "domain": domain, "role": role,
            "semantic_key": semantic, "value_grammar": grammar,
            "keyframes": keyframes}


def kf(num: int, den: int, value: int, kind: str = "AUTHORED",
       alignment: str | None = None) -> dict:
    return {"time_ms": {"num": num, "den": den}, "value": value,
            "provenance": {"kind": kind,
                           "source_alignment_id": alignment}}


SMILE = ("profile-1/face.expression.smile", "face", "expression",
         "smile", "bounded_scalar_ppm")
JAW = ("profile-1/face.articulation.jaw_open", "face", "articulation",
       "jaw_open", "bounded_scalar_ppm")
HEAD_YAW = ("profile-1/body.pose.head_yaw_udeg", "body", "pose",
            "head_yaw", "bounded_scalar_microdeg")
TORSO = ("profile-1/body.pose.torso_lean_udeg", "body", "pose",
         "torso_lean", "bounded_scalar_microdeg")


def candidate_body(channels: list[dict], start=(0, 1), end=(4500, 1),
                   kind: str | None = None,
                   source_kind: str = "authored",
                   producer: str = "fixture-producer",
                   source_identity=None, parameters_sha256=None,
                   profile: str = "performance-profile/1", **over
                   ) -> dict:
    if kind is None:
        domains = {c["domain"] for c in channels}
        kind = ("FACIAL" if domains == {"face"}
                else "BODY" if domains == {"body"} else "BODY_FACIAL")
    body = {"performance_kind": kind,
            "performance_profile_id": profile,
            "temporal_domain": {
                "start": {"num": start[0], "den": start[1]},
                "end": {"num": end[0], "den": end[1]}},
            "channels": channels,
            "source_provenance": {
                "schema_version": 1, "source_kind": source_kind,
                "producer_id": producer, "producer_version": "1",
                "source_identity": source_identity,
                "parameters_sha256": parameters_sha256}}
    body.update(over)
    return body


async def create_candidate(client, subject_id: str, body: dict) -> dict:
    r = await client.post(
        f"/creative-entities/{subject_id}/performance-candidates",
        json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def adopt(client, candidate_id: str,
                adopted_by: str = "director") -> dict:
    r = await client.post(f"/performance-candidates/{candidate_id}/"
                          "adopt", json={"adopted_by": adopted_by})
    assert r.status_code == 200, r.text
    return r.json()


async def stamp_alembic(client, head: str =
                        "0019_m17b_performance_revisions") -> None:
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS alembic_version ("
            "version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
        await conn.execute(text("DELETE FROM alembic_version"))
        await conn.execute(text(
            "INSERT INTO alembic_version (version_num) VALUES (:h)"),
            {"h": head})
