"""Audit remediation — M4/M5A regressions (source-audit F8, F9, F10, F12, F15).

F8:  load_workflow parses and hashes ONE byte buffer per file — an
     installation switch between parse and hash cannot pair version-A
     semantics with version-B's SHA-256.
F9:  a comfy Generation is persisted from the EXACT captured package bytes
     and hashes — never a second mutable installed read.
F10: manifest↔template binding validation runs at CAPTURE (bad pairs never
     queue a Generation) and after historical retrieval.
F12: the pipeline branches on DURABLE SUBMISSION STATE before any prework —
     an adopted confirmed prompt observes to terminal without uploads or
     translation; a submission_possible permit redisCOVERS only.
F15: one corrupt queued row cannot starve the queue.
"""

from __future__ import annotations

import hashlib
import json

import httpx
import pytest
from sqlalchemy import text

from soloring.api.schemas.projects import ProjectCreate
from soloring.api.schemas.references import ReferenceInput
from soloring.api.schemas.shots import ShotCreate
from soloring.assets.blob_store import BlobStore
from soloring.domain import projects, references, shots
from soloring.errors import ErrorCode
from soloring.executors.comfy.bindings import BindingInvalid
from soloring.executors.comfy.client import ComfyClient
from soloring.settings import BASE_DIR
from soloring.workflows import manifest as manifest_module
from soloring.workflows.manifest import load_workflow, parse_manifest
from soloring.worker import ownership

REPO_WF = BASE_DIR / "workflows" / "hunyuan_i2v_v1"
MANIFEST_BYTES = (REPO_WF / "manifest.json").read_bytes()
TEMPLATE_BYTES = (REPO_WF / "workflow.json").read_bytes()


def _installed_copy(tmp_path):
    wf = tmp_path / "wf"
    wf.mkdir()
    (wf / "manifest.json").write_bytes(MANIFEST_BYTES)
    (wf / "workflow.json").write_bytes(TEMPLATE_BYTES)
    (wf / "workflow-package.json").write_text(json.dumps({
        "schema_version": 1,
        "workflow_id": "hunyuan",
        "workflow_version": 1,
        "manifest_hash": hashlib.sha256(MANIFEST_BYTES).hexdigest(),
        "workflow_template_hash": hashlib.sha256(TEMPLATE_BYTES).hexdigest(),
    }))
    return wf


def _swap_manifest_default(wf, default: int) -> None:
    doc = json.loads(MANIFEST_BYTES.decode())
    doc["parameters"]["steps"]["default"] = default
    raw = json.dumps(doc, indent=2).encode()
    (wf / "manifest.json").write_bytes(raw)
    pkg = json.loads((wf / "workflow-package.json").read_text())
    pkg["manifest_hash"] = hashlib.sha256(raw).hexdigest()
    (wf / "workflow-package.json").write_text(json.dumps(pkg))


# --- F8 ------------------------------------------------------------------------


def test_load_workflow_semantics_and_hash_come_from_one_buffer(
    tmp_path, monkeypatch,
):
    wf = _installed_copy(tmp_path)
    monkeypatch.setattr(manifest_module, "WORKFLOW_DIR", wf)

    # The installation switches the manifest AFTER parse consumed the
    # buffer but before a (hypothetical) second hash read (audit F8
    # reproduction). Under the fix there IS no second read: the recorded
    # hash is the hash of exactly what was parsed.
    import soloring.workflows.manifest as mm

    real_parse = mm.parse_manifest

    def swapping_parse(raw):
        doc = real_parse(raw)
        _swap_manifest_default(wf, 99)  # valid new release lands mid-call
        return doc

    monkeypatch.setattr(mm, "parse_manifest", swapping_parse)

    template = load_workflow()
    steps = {p.name: p for p in template.parameters}["steps"]
    assert steps.default == 30  # version-A semantics…
    assert template.manifest_hash == hashlib.sha256(
        MANIFEST_BYTES
    ).hexdigest()  # …paired with version-A's hash


# --- F9 / F10 -------------------------------------------------------------------


async def _seed_comfy(client, factory, engine, settings, monkeypatch, wf):
    import soloring.api.generations as generations_api

    settings.executor = "comfy"
    # M9: legacy comfy-contract tests pin the published v1 package (the
    # current release advanced to schema-2 hunyuan_i2v_v4; §56 override).
    from soloring.workflows.manifest import WORKFLOW_DIR as _V1

    settings.workflow_package_dir = _V1
    monkeypatch.setattr(generations_api, "get_settings", lambda: settings)
    async with factory() as s:
        pid = (await projects.create_project(s, ProjectCreate(name="P"))).id
        shot = await shots.create_shot(s, pid, ShotCreate(subject="Eva"))
    content = b"\x89PNG\r\n\x1a\n" + b"ref" * 8
    bh = hashlib.sha256(content).hexdigest()
    path = BlobStore(settings).path_for_hash(bh)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from soloring.db.models import Asset, Blob
    from soloring.domain.ids import new_uuid

    aid = new_uuid()
    f = async_sessionmaker(bind=engine, expire_on_commit=False,
                           class_=AsyncSession)
    async with f() as s:
        s.add(Blob(hash=bh, path=f"sha256/{bh[:2]}/{bh[2:4]}/{bh}",
                   size_bytes=len(content), detected_media_type="image/png"))
        await s.flush()
        s.add(Asset(id=aid, project_id=pid, blob_hash=bh, kind="reference"))
        await s.commit()
    async with f() as s:
        await references.replace_references(
            s, shot.id, [ReferenceInput(asset_id=aid, role="reference")],
        )
    r = await client.post(f"/shots/{shot.id}/generations")
    return r, shot.id


async def test_comfy_creation_persists_the_captured_release_only(
    client, factory, engine, settings, monkeypatch, tmp_path,
):
    wf = _installed_copy(tmp_path)
    monkeypatch.setattr(manifest_module, "WORKFLOW_DIR", wf)

    # The installation switches to a NEW valid release immediately after
    # capture places the old pair (audit F9 reproduction window).
    from soloring.workflows.artifact_store import WorkflowArtifactStore

    real_place = WorkflowArtifactStore.place_captured

    async def switching_place(self, captured):
        await real_place(self, captured)
        _swap_manifest_default(wf, 77)

    monkeypatch.setattr(WorkflowArtifactStore, "place_captured",
                        switching_place)

    r, _ = await _seed_comfy(client, factory, engine, settings, monkeypatch,
                             wf)
    assert r.status_code == 202, r.text
    gid = r.json()["id"]

    async with engine.connect() as conn:
        row = (await conn.execute(
            text("SELECT manifest_hash, workflow_template_hash "
                 "FROM generations WHERE id=:g"), {"g": gid},
        )).mappings().one()
    # The CAPTURED pair, not the post-switch installed state.
    assert row["manifest_hash"] == hashlib.sha256(MANIFEST_BYTES).hexdigest()
    assert row["workflow_template_hash"] == hashlib.sha256(
        TEMPLATE_BYTES
    ).hexdigest()
    # And the recorded artifacts are retrievable (they were really placed).
    store = WorkflowArtifactStore(settings)
    assert await store.get_manifest(row["manifest_hash"]) == MANIFEST_BYTES


async def test_bad_binding_package_rejected_at_capture(
    client, factory, engine, settings, monkeypatch, tmp_path,
):
    wf = _installed_copy(tmp_path)
    # Coherent package whose manifest binds a node the template lacks.
    doc = json.loads(MANIFEST_BYTES.decode())
    doc["inputs"]["reference_image"]["node"] = "4242"
    raw = json.dumps(doc, indent=2).encode()
    (wf / "manifest.json").write_bytes(raw)
    pkg = json.loads((wf / "workflow-package.json").read_text())
    pkg["manifest_hash"] = hashlib.sha256(raw).hexdigest()
    (wf / "workflow-package.json").write_text(json.dumps(pkg))
    monkeypatch.setattr(manifest_module, "WORKFLOW_DIR", wf)

    r, _ = await _seed_comfy(client, factory, engine, settings, monkeypatch,
                             wf)
    assert r.status_code == 422, r.text
    assert r.json()["error_code"] == ErrorCode.COMFY_TEMPLATE_BINDING_INVALID
    async with engine.connect() as conn:
        n = (await conn.execute(
            text("SELECT COUNT(*) FROM generations")
        )).scalar_one()
    assert n == 0  # nothing queued from an invalid pair


# --- F12 ------------------------------------------------------------------------


class _Double:
    """Minimal double: prompt exists (pending), terminalizes on demand."""

    base_url = "http://comfy.test"

    def __init__(self):
        self.prompt_posts = []
        self.uploads = []
        self._pid = "prompt-0001"
        self._terminal = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/upload/image":
            self.uploads.append(path)
            return httpx.Response(500)  # UNAVAILABLE: prework must fail
        if path == "/prompt":
            body = json.loads(request.content.decode())
            self.prompt_posts.append(body)
            return httpx.Response(200, json={"prompt_id": self._pid})
        if path == "/queue":
            if not self._terminal:
                marker = body_extra(self.prompt_posts[0])
                return httpx.Response(200, json={
                    "queue_running": [[0, self._pid, {}, marker, []]],
                    "queue_pending": [],
                })
            return httpx.Response(200, json={
                "queue_running": [], "queue_pending": [],
            })
        if path.startswith("/history"):
            if self._terminal:
                marker = body_extra(self.prompt_posts[0])
                return httpx.Response(200, json={self._pid: {
                    "prompt": [0, self._pid, {}, marker, []],
                    "outputs": {"15": {"images": [
                        {"filename": "out.webp", "subfolder": "",
                         "type": "output"}]}},
                    "status": {"status_str": "completed", "messages": []},
                }})
            return httpx.Response(200, json={})
        if path == "/view":
            return httpx.Response(200, content=b"RIFF-out-bytes")
        return httpx.Response(404)


def body_extra(posted):
    return posted.get("extra_data", {})


def _client(double, worker_id):
    return ComfyClient(double.base_url, worker_id, timeout=10.0,
                      transport=httpx.MockTransport(double.handler))


async def test_confirmed_adoption_skips_submission_prework(
    client, factory, engine, settings, monkeypatch, tmp_path,
):
    """State=confirmed: the successor observes/publishes with NO uploads,
    NO translation, NO second POST (audit F12)."""
    wf = _installed_copy(tmp_path)
    monkeypatch.setattr(manifest_module, "WORKFLOW_DIR", wf)
    r, shot_id = await _seed_comfy(client, factory, engine, settings,
                                   monkeypatch, wf)
    assert r.status_code == 202
    gid = r.json()["id"]

    worker_a = "w-a"
    await ownership.acquire_worker_lease(
        engine, worker_a, settings.worker_lease_ttl_seconds
    )
    claim = await ownership.claim_next_generation(engine, worker_a)
    _, attempt = claim

    # Predecessor A: full submission (ONE POST) — then "dies" before
    # observing. Durable state: confirmed with the persisted prompt id.
    double = _Double()
    client_a = _client(double, worker_a)
    from soloring.worker.comfy_submission import run_comfy_submission

    payload = {
        "prompt": {"4": {"class_type": "LoadImage",
                         "inputs": {"image": "x.png"}}},
        "extra_data": {"soloring": {"generation_id": gid,
                                    "attempt_id": attempt}},
        "client_id": worker_a,
    }
    prompt_id = await run_comfy_submission(
        engine, settings, worker_a, gid, attempt, payload, client_a,
    )
    assert prompt_id == "prompt-0001"
    await client_a.aclose()

    # Successor B adopts.
    from soloring.db.timeutil import db_now_minus_sql

    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(text(
            "UPDATE worker_leases SET heartbeat_at = "
            + db_now_minus_sql(9999) + " WHERE name = 'generation-worker'"
        ))
        await conn.execute(text(
            "UPDATE generations SET heartbeat_at = "
            + db_now_minus_sql(9999) + " WHERE id = :g"), {"g": gid})
        await conn.exec_driver_sql("COMMIT")
    worker_b = "w-b"
    await ownership.acquire_worker_lease(
        engine, worker_b, settings.worker_lease_ttl_seconds
    )
    assert await ownership.adopt_stale_generation(
        engine, worker_b, gid
    ) is ownership.OwnershipMutationResult.OK

    double._terminal = True
    client_b = _client(double, worker_b)
    from soloring.worker.comfy_pipeline import drive_comfy_generation

    result = await drive_comfy_generation(
        engine, settings, worker_b, gid, attempt, client_b,
        # A materializer that would FAIL any upload: proves no prework ran.
        materializer=_FailingMaterializer(),
    )
    await client_b.aclose()

    assert result == "succeeded"
    assert len(double.prompt_posts) == 1  # only A's POST
    assert double.uploads == []  # /upload/image never even requested
    async with engine.connect() as conn:
        takes = (await conn.execute(
            text("SELECT COUNT(*) FROM takes WHERE generation_id=:g"),
            {"g": gid},
        )).scalar_one()
    assert takes == 1


class _FailingMaterializer:
    async def materialize(self, **kw):
        raise AssertionError(
            "adoption of a confirmed prompt must not materialize inputs "
            "(audit F12)"
        )


# --- F15 ------------------------------------------------------------------------


async def test_corrupt_queued_row_does_not_starve_the_queue(
    client, factory, engine, settings,
):
    settings.executor = "fake"
    async with factory() as s:
        pid = (await projects.create_project(s, ProjectCreate(name="P"))).id
        s1 = await shots.create_shot(s, pid, ShotCreate(subject="one"))
        s2 = await shots.create_shot(s, pid, ShotCreate(subject="two"))
        content = b"\x89PNG\r\n\x1a\n" + b"f15" * 8
    bh = hashlib.sha256(content).hexdigest()
    path = BlobStore(settings).path_for_hash(bh)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from soloring.db.models import Asset, Blob
    from soloring.domain.ids import new_uuid

    aid = new_uuid()
    f = async_sessionmaker(bind=engine, expire_on_commit=False,
                           class_=AsyncSession)
    async with f() as s:
        s.add(Blob(hash=bh, path=f"sha256/{bh[:2]}/{bh[2:4]}/{bh}",
                   size_bytes=len(content), detected_media_type="image/png"))
        await s.flush()
        s.add(Asset(id=aid, project_id=pid, blob_hash=bh, kind="reference"))
        await s.commit()
    for shot in (s1, s2):
        async with f() as s:
            await references.replace_references(
                s, shot.id,
                [ReferenceInput(asset_id=aid, role="reference")],
            )
    g1 = (await client.post(f"/shots/{s1.id}/generations")).json()["id"]
    g2 = (await client.post(f"/shots/{s2.id}/generations")).json()["id"]

    # Corrupt the OLDEST queued row with an illegal submission state.
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(text(
            "UPDATE generations SET executor_submission_state = 'uncertain' "
            "WHERE id = :g"), {"g": g1})
        await conn.exec_driver_sql("COMMIT")

    worker = "w-f15"
    await ownership.acquire_worker_lease(
        engine, worker, settings.worker_lease_ttl_seconds
    )
    claim = await ownership.claim_next_generation(engine, worker)
    assert claim is not None
    claimed_id, _ = claim
    assert claimed_id != g1  # the corrupt row was skipped…
    # …but the valid row behind it was claimed.
    async with engine.connect() as conn:
        row = (await conn.execute(
            text("SELECT status FROM generations WHERE id=:g"),
            {"g": claimed_id},
        )).scalar_one()
    assert row == "preparing"
