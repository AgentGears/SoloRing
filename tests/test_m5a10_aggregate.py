"""M5A-10 — aggregate adversarial and release gate.

The headline proof: real Project/Shot/Reference creation → executor=comfy
PERSISTED at creation → historical manifest/template captured → worker claims
+ attempt_id → materialize → translate → ONE POST → observe → /view →
import → Take — all against the deterministic HTTP double.

Plus: takeover after a lost submit response (one POST, one remote prompt, one
durable result), Soft Cancel zero-publication, installed-workflow mutation
(G1 keeps M1/T1 while G2 uses M2/T2), creative-state freeze through the Comfy
path, executor-selection dispatch regression, the stable error envelope
through the worker boundary, and aggregate AST boundary / state-space audits.
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text

from soloring.api.schemas.projects import ProjectCreate
from soloring.api.schemas.references import ReferenceInput
from soloring.api.schemas.shots import ShotCreate, ShotPatch
from soloring.domain import projects, references, shots
from soloring.domain.canonical import canonical_json_bytes, canonical_hash
from soloring.executors.comfy.client import ComfyClient
from soloring.executors.comfy.input_materializer import attempt_namespace
from soloring.settings import BASE_DIR, Settings
from soloring.workflows import manifest as manifest_module
from soloring.workflows.manifest import parse_manifest
from soloring.worker import ownership
from soloring.worker.execution import process_next_generation
from soloring.worker.recovery import reconcile_stale_generations

REPO_WORKFLOW_DIR = BASE_DIR / "workflows" / "hunyuan_i2v_v1"
MANIFEST_BYTES = (REPO_WORKFLOW_DIR / "manifest.json").read_bytes()
TEMPLATE_BYTES = (REPO_WORKFLOW_DIR / "workflow.json").read_bytes()
MANIFEST = parse_manifest(MANIFEST_BYTES.decode("utf-8"))
VIDEO_DECL = MANIFEST.outputs["video"]  # release v2: node "15", field "images"

PNG_REF = b"\x89PNG\r\n\x1a\n" + b"reference-payload-" * 8
OUT_BYTES = b"RIFF\x24\x00\x00\x00WEBPVP8L" + b"video-frame-" * 24


# --- the lifecycle HTTP double ---------------------------------------------------


@dataclass
class LifecycleDouble:
    """MockTransport Comfy with a poll-driven prompt lifecycle.

    Prompts advance pending → running → terminal as /queue is polled
    (advance_after_polls per phase). Terminal prompts appear in /history with
    one declared output file servable on /view. Full POST instrumentation:
    prompt bodies, uploads, view calls, interrupts, queue deletes.
    """

    base_url: str = "http://comfy.test"
    advance_after_polls: int = 3
    initial_state: str = "pending"     # state until the first advance boundary
    lose_submit_response: bool = False
    fail_prompt_400: bool = False
    marker_visibility_delay: int = 0
    prompt_posts: list = field(default_factory=list)     # (g, a, body)
    uploads: list = field(default_factory=list)          # (filename, subfolder)
    view_calls: list = field(default_factory=list)       # (filename, subfolder)
    interrupt_calls: int = 0
    queue_deletes: list = field(default_factory=list)
    files: dict = field(default_factory=dict)            # filename → bytes
    _prompts: dict = field(default_factory=dict)         # pid → record
    _next_pid: int = 0
    _poll_count: int = 0
    posted: asyncio.Event = field(default_factory=asyncio.Event)

    # -- state machine -------------------------------------------------------
    def _advance(self) -> None:
        self._poll_count += 1
        per_phase = max(self.advance_after_polls, 0)
        for rec in self._prompts.values():
            if rec["state"] == "terminal":
                continue
            if per_phase == 0 or self._poll_count >= 2 * per_phase:
                rec["state"] = "terminal"
                self._finalize(rec)
            elif self._poll_count >= per_phase:
                rec["state"] = "running"

    def _finalize(self, rec: dict) -> None:
        if rec["status_str"] != "completed":
            return
        refs = []
        for i in range(VIDEO_DECL.expected_count or 1):
            name = f"{rec['pid']}-video-{i}.webp"
            self.files[name] = OUT_BYTES
            refs.append({"filename": name, "subfolder": "", "type": "output"})
        rec["outputs"] = {VIDEO_DECL.node: {VIDEO_DECL.field: refs}}

    def _marker_visible(self) -> bool:
        return self._poll_count >= self.marker_visibility_delay

    # -- HTTP surface ----------------------------------------------------------
    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/system_stats":
            return httpx.Response(200, json={
                "system": {"comfyui_version": "0.3.14", "build": "t"}
            })
        if path == "/upload/image":
            return self._handle_upload(request)
        if path == "/prompt":
            return self._handle_prompt(request)
        if path == "/queue" and request.method == "GET":
            return self._handle_queue()
        if path == "/queue" and request.method == "POST":
            return self._handle_queue_delete(request)
        if path == "/interrupt":
            return self._handle_interrupt(request)
        if path.startswith("/history"):
            return self._handle_history()
        if path == "/view":
            return self._handle_view(request)
        return httpx.Response(404)

    def _handle_upload(self, request: httpx.Request) -> httpx.Response:
        body = request.content
        fname = re.search(rb'filename="([^"]*)"', body)
        subfolder = re.search(rb'name="subfolder"\r\n\r\n([^\r]*)', body)
        name = fname.group(1).decode() if fname else "unknown.bin"
        sub = subfolder.group(1).decode() if subfolder else ""
        self.uploads.append((name, sub))
        return httpx.Response(200, json={"name": name, "subfolder": sub,
                                         "type": "input"})

    def _handle_prompt(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        marker = body.get("extra_data", {}).get("soloring", {})
        g = marker.get("generation_id", "?")
        a = marker.get("attempt_id", "?")
        self.prompt_posts.append((g, a, body))
        self.posted.set()

        if self.fail_prompt_400:
            return httpx.Response(400, json={"error": {
                "type": "prompt_outputs_failed_validation",
            }, "node_errors": {}})
        self._next_pid += 1
        pid = f"prompt-{self._next_pid:04d}"
        self._prompts[pid] = {
            "pid": pid, "extra": body.get("extra_data", {}),
            "state": self.initial_state,
            "status_str": "completed", "outputs": {}, "error": None,
        }
        if self.lose_submit_response:
            raise httpx.ReadTimeout("response lost after acceptance")
        return httpx.Response(200, json={"prompt_id": pid})

    def _handle_queue(self) -> httpx.Response:
        self._advance()
        running, pending = [], []
        for pid, rec in self._prompts.items():
            if rec["state"] == "terminal":
                continue
            extra = rec["extra"] if self._marker_visible() else {"unrelated": True}
            entry = [0, pid, {}, extra, []]
            (running if rec["state"] == "running" else pending).append(entry)
        return httpx.Response(200, json={
            "queue_running": running, "queue_pending": pending,
        })

    def _handle_queue_delete(self, request: httpx.Request) -> httpx.Response:
        pids = json.loads(request.content.decode()).get("delete", [])
        self.queue_deletes.extend(pids)
        for pid in pids:
            rec = self._prompts.get(pid)
            if rec and rec["state"] != "terminal":
                rec["state"] = "terminal"
                rec["status_str"] = "cancelled"
        return httpx.Response(200, json={})

    def _handle_interrupt(self, request: httpx.Request) -> httpx.Response:
        self.interrupt_calls += 1
        try:
            body = json.loads(request.content.decode())
        except ValueError:
            body = {}
        pid = body.get("prompt_id")
        rec = self._prompts.get(pid)
        if rec and rec["state"] != "terminal":
            rec["state"] = "terminal"
            rec["status_str"] = "cancelled"
        return httpx.Response(200, json={"accepted": True})

    def _handle_history(self) -> httpx.Response:
        self._poll_count += 1
        out = {}
        for pid, rec in self._prompts.items():
            if rec["state"] != "terminal":
                continue
            extra = rec["extra"] if self._marker_visible() else {"unrelated": True}
            out[pid] = {
                "prompt": [0, pid, {}, extra, []],
                "outputs": rec["outputs"],
                "status": {"status_str": rec["status_str"],
                           "messages": []},
            }
            if rec["status_str"] == "error":
                out[pid]["status"]["messages"] = [
                    ["execution_error", {"exception_message": "boom"}]
                ]
        return httpx.Response(200, json=out)

    def _handle_view(self, request: httpx.Request) -> httpx.Response:
        params = request.url.params
        filename = params.get("filename", "")
        subfolder = params.get("subfolder", "")
        self.view_calls.append((filename, subfolder))
        if filename in self.files and params.get("type") == "output":
            return httpx.Response(200, content=self.files[filename])
        return httpx.Response(404)

    # -- assertions helpers ----------------------------------------------------
    def post_count(self, generation_id: str, attempt_id: str) -> int:
        return sum(1 for g, a, _ in self.prompt_posts
                   if g == generation_id and a == attempt_id)

    def body_for(self, generation_id: str) -> dict:
        for g, _, body in self.prompt_posts:
            if g == generation_id:
                return body
        raise AssertionError(f"no prompt posted for {generation_id}")


def _client(double: LifecycleDouble, client_id: str) -> ComfyClient:
    return ComfyClient(
        double.base_url, client_id, timeout=10.0,
        transport=httpx.MockTransport(double.handler),
    )


# --- seeding -----------------------------------------------------------------------


async def _seed_reference(engine, settings, project_id: str,
                          content: bytes = PNG_REF) -> tuple[str, str]:
    from soloring.assets.blob_store import BlobStore
    from soloring.db.models import Asset, Blob
    from soloring.domain.ids import new_uuid
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    bh = hashlib.sha256(content).hexdigest()
    path = BlobStore(settings).path_for_hash(bh)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    aid = new_uuid()
    f = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with f() as s:
        s.add(Blob(hash=bh, path=f"sha256/{bh[:2]}/{bh[2:4]}/{bh}",
                   size_bytes=len(content), detected_media_type="image/png"))
        await s.flush()
        s.add(Asset(id=aid, project_id=project_id, blob_hash=bh,
                    kind="reference"))
        await s.commit()
    return aid, bh


async def _seed_comfy_generation(client, monkeypatch, settings, factory,
                                 engine) -> dict:
    """Project + Shot + real reference Blob → comfy Generation via the API."""
    import soloring.api.generations as generations_api

    settings.executor = "comfy"
    monkeypatch.setattr(generations_api, "get_settings", lambda: settings)

    async with factory() as s:
        pid = (await projects.create_project(s, ProjectCreate(name="P"))).id
        shot = await shots.create_shot(s, pid, ShotCreate(subject="Eva"))
    aid, bh = await _seed_reference(engine, settings, pid)
    async with factory() as s:
        await references.replace_references(
            s, shot.id, [ReferenceInput(asset_id=aid, role="reference")]
        )
    r = await client.post(f"/shots/{shot.id}/generations")
    assert r.status_code == 202, r.text
    gid = r.json()["id"]

    async with factory() as s:
        rev_id = (await s.execute(
            text("SELECT id FROM shot_revisions WHERE shot_id=:sid "
                 "ORDER BY revision_number DESC LIMIT 1"),
            {"sid": shot.id},
        )).scalar_one()
    return {"generation_id": gid, "shot_id": shot.id, "project_id": pid,
            "asset_id": aid, "blob_hash": bh, "revision_id": rev_id}


async def _row(engine, gid: str) -> dict:
    async with engine.connect() as conn:
        return dict((await conn.execute(
            text("SELECT * FROM generations WHERE id=:g"), {"g": gid},
        )).mappings().one())


async def _one(engine, sql: str, params: dict):
    async with engine.connect() as conn:
        return (await conn.execute(text(sql), params)).scalar_one_or_none()


async def _wait_status(engine, gid: str, wanted: str, timeout: float = 5.0):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        row = await _row(engine, gid)
        if row["status"] == wanted:
            return row
        await asyncio.sleep(0.02)
    raise AssertionError(f"status never reached {wanted}: {row['status']}")


async def _run_once(engine, settings, worker_id: str, double) -> str | None:
    await ownership.acquire_worker_lease(
        engine, worker_id, settings.worker_lease_ttl_seconds
    )
    client = _client(double, worker_id)
    try:
        return await process_next_generation(
            engine, settings, worker_id, comfy_client=client,
        )
    finally:
        await client.aclose()


# --- headline: full lifecycle + provenance ------------------------------------------


async def test_headline_happy_path_full_provenance(
    client, monkeypatch, settings, factory, engine,
):
    seed = await _seed_comfy_generation(client, monkeypatch, settings,
                                        factory, engine)
    gid = seed["generation_id"]
    double = LifecycleDouble()

    assert await _run_once(engine, settings, "w-headline", double) == "succeeded"

    row = await _row(engine, gid)
    assert row["status"] == "succeeded"
    assert row["executor"] == "comfy"
    assert row["executor_submission_state"] == "confirmed"
    assert row["attempt_id"] is not None
    assert row["executor_job_id"].startswith("prompt-")
    assert row["started_at"] is not None and row["completed_at"] is not None
    assert row["error_code"] is None

    # Provenance: captured identities match the installed release bytes.
    assert row["manifest_hash"] == hashlib.sha256(MANIFEST_BYTES).hexdigest()
    assert row["workflow_template_hash"] == hashlib.sha256(
        TEMPLATE_BYTES
    ).hexdigest()
    spec = json.loads(row["workflow_spec_json"])
    assert row["workflow_spec_hash"] == canonical_hash(spec)
    assert row["shot_revision_id"] == seed["revision_id"]

    # Submission artifact: persisted bytes ARE the hashed canonical bytes,
    # and the marker carries the durable attempt identity.
    sub_json = row["executor_submission_json"]
    assert sub_json is not None
    assert hashlib.sha256(sub_json.encode("utf-8")).hexdigest() == (
        row["executor_submission_hash"]
    )
    assert canonical_json_bytes(json.loads(sub_json)) == sub_json.encode("utf-8")
    doc = json.loads(sub_json)
    assert doc["extra_data"]["soloring"] == {
        "generation_id": gid, "attempt_id": row["attempt_id"],
    }

    # Exactly ONE POST, with the captured creative content.
    assert len(double.prompt_posts) == 1
    assert double.post_count(gid, row["attempt_id"]) == 1
    body = double.body_for(gid)
    graph = body["prompt"]
    assert graph["12"]["inputs"]["prompt"] == spec["prompt"]
    assert graph["31"]["inputs"]["steps"] == spec["parameters"]["steps"]
    assert graph["31"]["inputs"]["cfg"] == spec["parameters"]["cfg"]
    # Input bound by logical identity to the materialized remote reference.
    assert len(double.uploads) == 1
    up_name, up_sub = double.uploads[0]
    assert up_name == f"{seed['blob_hash']}.png"
    assert up_sub == attempt_namespace(gid, row["attempt_id"])
    assert graph["4"]["inputs"]["image"] == f"{up_sub}/{up_name}"

    # Publication: one Take/Asset/Blob for output video:0.
    assert await _one(engine, "SELECT COUNT(*) FROM takes WHERE "
                              "generation_id=:g", {"g": gid}) == 1
    take = await _one(engine, "SELECT output_key FROM takes WHERE "
                              "generation_id=:g", {"g": gid})
    assert take == "video:0"
    assert await _one(engine, "SELECT COUNT(*) FROM assets a JOIN takes t "
                              "ON a.take_id=t.id WHERE t.generation_id=:g",
                      {"g": gid}) == 1
    assert len(double.view_calls) == 1
    assert double.interrupt_calls == 0

    # Staging cleaned; artifacts durable and byte-identical to the release.
    assert not (Path(settings.staging_dir) / gid / row["attempt_id"]).exists()
    from soloring.workflows.artifact_store import WorkflowArtifactStore
    store = WorkflowArtifactStore(settings)
    assert await store.get_manifest(row["manifest_hash"]) == MANIFEST_BYTES
    assert await store.get_template(
        row["workflow_template_hash"]) == TEMPLATE_BYTES


# --- takeover: A dies after response-lost → B adopts → ONE POST ---------------------


async def test_takeover_after_response_lost_single_post(
    client, monkeypatch, settings, factory, engine, age_heartbeat,
):
    seed = await _seed_comfy_generation(client, monkeypatch, settings,
                                        factory, engine)
    gid = seed["generation_id"]
    double = LifecycleDouble(lose_submit_response=True,
                             marker_visibility_delay=100)

    worker_a = "w-a"
    await ownership.acquire_worker_lease(
        engine, worker_a, settings.worker_lease_ttl_seconds
    )
    claim = await ownership.claim_next_generation(engine, worker_a)
    assert claim is not None
    _, attempt = claim

    from soloring.worker.comfy_pipeline import drive_comfy_generation
    client_a = _client(double, worker_a)
    task = asyncio.create_task(drive_comfy_generation(
        engine, settings, worker_a, gid, attempt, client_a,
    ))
    await asyncio.wait_for(double.posted.wait(), timeout=5)
    await asyncio.sleep(0.3)  # A is now inside bounded rediscovery
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await client_a.aclose()

    # A died mid-rediscovery: permit consumed, no confirm, still preparing.
    row = await _row(engine, gid)
    assert row["executor_submission_state"] == "submission_possible"
    assert row["executor_job_id"] is None
    assert row["status"] == "preparing"
    assert len(double.prompt_posts) == 1  # the remote accepted exactly one

    # The queue settles: markers become visible to the successor.
    double.marker_visibility_delay = 0

    # A's lease AND generation heartbeat go stale; B takes the authority.
    await age_heartbeat(engine)
    from soloring.db.timeutil import db_now_minus_sql
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(text(
            "UPDATE generations SET heartbeat_at = "
            + db_now_minus_sql(9999) + " WHERE id = :g"
        ), {"g": gid})
        await conn.exec_driver_sql("COMMIT")

    worker_b = "w-b"
    result = await ownership.acquire_worker_lease(
        engine, worker_b, settings.worker_lease_ttl_seconds
    )
    assert result is ownership.LeaseAcquisitionResult.TAKEN_OVER
    client_b = _client(double, worker_b)
    acted = await reconcile_stale_generations(
        engine, worker_b, settings, comfy_client=client_b,
    )
    await client_b.aclose()
    assert acted == 1

    row = await _row(engine, gid)
    assert row["status"] == "succeeded"
    assert row["executor_submission_state"] == "confirmed"
    assert row["worker_id"] == worker_b
    assert row["attempt_id"] == attempt  # adoption preserves the attempt

    # ONE POST total, ONE remote prompt, ONE durable result.
    assert len(double.prompt_posts) == 1
    assert len(double._prompts) == 1
    assert await _one(engine, "SELECT COUNT(*) FROM takes WHERE "
                              "generation_id=:g", {"g": gid}) == 1


# --- Soft Cancel: zero publication, zero /view, zero interrupt ----------------------


async def test_soft_cancel_zero_publication(
    client, monkeypatch, settings, factory, engine,
):
    seed = await _seed_comfy_generation(client, monkeypatch, settings,
                                        factory, engine)
    gid = seed["generation_id"]
    # Running from the start: with the conservative SOFT_ONLY capability the
    # reconciler must degrade to Soft Cancel, never a destructive request.
    double = LifecycleDouble(advance_after_polls=40, initial_state="running")

    worker = "w-soft"
    await ownership.acquire_worker_lease(
        engine, worker, settings.worker_lease_ttl_seconds
    )
    claim = await ownership.claim_next_generation(engine, worker)
    _, attempt = claim

    from soloring.worker.comfy_pipeline import drive_comfy_generation
    client_w = _client(double, worker)
    task = asyncio.create_task(drive_comfy_generation(
        engine, settings, worker, gid, attempt, client_w,
    ))
    try:
        await _wait_status(engine, gid, "submitted")
        r = await client.post(f"/generations/{gid}/cancel")
        assert r.status_code == 200, r.text
        assert r.json()["cancel_requested"] is True

        double.advance_after_polls = 0  # remote finishes now
        assert await asyncio.wait_for(task, timeout=10) == "cancelled"
    finally:
        await client_w.aclose()
        if not task.done():
            task.cancel()

    row = await _row(engine, gid)
    assert row["status"] == "cancelled"
    assert row["soft_cancel_selected_at"] is not None
    assert row["cancel_requested_at"] is not None
    prompt_id = row["executor_job_id"]
    assert prompt_id is not None and prompt_id.startswith("prompt-")
    row_after = await _row(engine, gid)
    assert row_after["executor_job_id"] == prompt_id

    # ZERO publication and ZERO destructive/remote-cancel surface activity.
    assert await _one(engine, "SELECT COUNT(*) FROM takes WHERE "
                              "generation_id=:g", {"g": gid}) == 0
    assert await _one(engine, "SELECT COUNT(*) FROM assets a JOIN takes t "
                              "ON a.take_id=t.id WHERE t.generation_id=:g",
                      {"g": gid}) == 0
    assert double.view_calls == []
    assert double.interrupt_calls == 0
    assert double.queue_deletes == []


# --- installed workflow mutation: G1 keeps M1/T1, G2 uses M2/T2 ---------------------


async def test_installed_workflow_mutation_end_to_end(
    client, monkeypatch, settings, factory, engine, tmp_path,
):
    wf = tmp_path / "wf"
    wf.mkdir()
    (wf / "manifest.json").write_bytes(MANIFEST_BYTES)
    (wf / "workflow.json").write_bytes(TEMPLATE_BYTES)
    (wf / "workflow-package.json").write_bytes(
        (REPO_WORKFLOW_DIR / "workflow-package.json").read_bytes()
    )
    monkeypatch.setattr(manifest_module, "WORKFLOW_DIR", wf)

    seed = await _seed_comfy_generation(client, monkeypatch, settings,
                                        factory, engine)
    g1 = seed["generation_id"]
    row1 = await _row(engine, g1)
    t1 = row1["workflow_template_hash"]

    # Install protocol: mutate the template, then swap the descriptor last.
    template2 = json.loads(TEMPLATE_BYTES.decode())
    template2["98"]["inputs"]["unet_name"] = "hunyuan-video-i2v-720p-Q5_K_M.gguf"
    t2_bytes = json.dumps(template2, indent=2).encode()
    (wf / "workflow.json").write_bytes(t2_bytes)
    (wf / "workflow-package.json").write_text(json.dumps({
        "schema_version": 1,
        "workflow_id": "hunyuan",
        "workflow_version": 1,
        "manifest_hash": hashlib.sha256(MANIFEST_BYTES).hexdigest(),
        "workflow_template_hash": hashlib.sha256(t2_bytes).hexdigest(),
    }))

    async with factory() as s:
        shot2 = await shots.create_shot(s, seed["project_id"],
                                        ShotCreate(subject="Ada"))
    async with factory() as s:
        await references.replace_references(
            s, shot2.id,
            [ReferenceInput(asset_id=seed["asset_id"], role="reference")],
        )
    r = await client.post(f"/shots/{shot2.id}/generations")
    assert r.status_code == 202, r.text
    g2 = r.json()["id"]
    row2 = await _row(engine, g2)
    assert row2["workflow_template_hash"] == hashlib.sha256(t2_bytes).hexdigest()
    assert row2["manifest_hash"] == row1["manifest_hash"]

    # G1 executes AFTER the mutation and still uses the captured T1.
    double = LifecycleDouble()
    assert await _run_once(engine, settings, "w-mut", double) == "succeeded"
    assert await _run_once(engine, settings, "w-mut", double) == "succeeded"
    assert double.body_for(g1)["prompt"]["98"]["inputs"]["unet_name"] == (
        "hunyuan-video-i2v-720p-Q4_K_M.gguf"
    )
    assert double.body_for(g2)["prompt"]["98"]["inputs"]["unet_name"] == (
        "hunyuan-video-i2v-720p-Q5_K_M.gguf"
    )
    for gid in (g1, g2):
        assert await _one(engine, "SELECT COUNT(*) FROM takes WHERE "
                                  "generation_id=:g", {"g": gid}) == 1


# --- creative state freezes at capture through the Comfy path ----------------------


async def test_creative_state_freeze_through_comfy(
    client, monkeypatch, settings, factory, engine,
):
    seed = await _seed_comfy_generation(client, monkeypatch, settings,
                                        factory, engine)
    gid = seed["generation_id"]
    row = await _row(engine, gid)
    spec_prompt = json.loads(row["workflow_spec_json"])["prompt"]

    # Mutate the live Shot AFTER capture: subject, creative fields, and a
    # completely different reference set.
    async with factory() as s:
        await shots.patch_shot(s, seed["shot_id"], ShotPatch(
            subject="Renamed", action="a different action",
        ))
    other_aid, other_bh = await _seed_reference(
        engine, settings, seed["project_id"],
        content=b"\x89PNG\r\n\x1a\n" + b"other-reference-*" * 8,
    )
    async with factory() as s:
        await references.replace_references(
            s, seed["shot_id"],
            [ReferenceInput(asset_id=other_aid, role="reference")],
        )

    double = LifecycleDouble()
    assert await _run_once(engine, settings, "w-freeze", double) == "succeeded"

    row = await _row(engine, gid)
    assert row["shot_revision_id"] == seed["revision_id"]
    body = double.body_for(gid)
    assert body["prompt"]["12"]["inputs"]["prompt"] == spec_prompt
    # Only the CAPTURED blob was ever uploaded; the new reference never
    # reached the executor.
    assert {u[0] for u in double.uploads} == {f"{seed['blob_hash']}.png"}
    assert other_bh not in {u[0].rsplit(".", 1)[0] for u in double.uploads}


# --- executor-selection dispatch regression -----------------------------------------

async def test_executor_selection_dispatch_regression(
    client, monkeypatch, settings, factory, engine,
):
    import soloring.api.generations as generations_api

    # G1 under comfy selection.
    seed = await _seed_comfy_generation(client, monkeypatch, settings,
                                        factory, engine)
    g1 = seed["generation_id"]

    # Config switch: only NEW creations change executor.
    settings.executor = "fake"
    monkeypatch.setattr(generations_api, "get_settings", lambda: settings)
    async with factory() as s:
        shot2 = await shots.create_shot(s, seed["project_id"],
                                        ShotCreate(subject="Fake path"))
    async with factory() as s:
        await references.replace_references(
            s, shot2.id,
            [ReferenceInput(asset_id=seed["asset_id"], role="reference")],
        )
    r = await client.post(f"/shots/{shot2.id}/generations")
    assert r.status_code == 202, r.text
    g2 = r.json()["id"]
    assert (await _row(engine, g1))["executor"] == "comfy"
    assert (await _row(engine, g2))["executor"] == "fake"

    # Each dispatched by ITS persisted executor, in one queue drain.
    double = LifecycleDouble()
    assert await _run_once(engine, settings, "w-dispatch", double) == "succeeded"
    assert await _run_once(engine, settings, "w-dispatch", double) == "succeeded"

    row1, row2 = await _row(engine, g1), await _row(engine, g2)
    assert row1["status"] == "succeeded" and row2["status"] == "succeeded"
    # Comfy row carries the full durable submission identity.
    assert row1["executor_submission_state"] == "confirmed"
    assert row1["executor_submission_hash"] is not None
    # Fake row NEVER acquires comfy submission state, artifact, or soft cancel.
    assert row2["executor_submission_state"] == "not_started"
    assert row2["executor_submission_json"] is None
    assert row2["executor_submission_hash"] is None
    assert row2["soft_cancel_selected_at"] is None
    # Exactly one comfy POST (G1); the fake executor never touched Comfy.
    assert len(double.prompt_posts) == 1
    assert len(double.uploads) == 1
    # Fake creation captures no workflow artifacts: the store still holds
    # exactly the pair G1's comfy creation put there.
    artifacts = list((Path(settings.data_dir) / "workflow-artifacts")
                     .rglob("*.json"))
    assert len(artifacts) == 2  # one manifest + one template, from G1 only


async def test_unknown_executor_rejected_at_load(monkeypatch):
    with pytest.raises(Exception):
        Settings(executor="bogus", data_dir=Path("./tmp-invalid"))


# --- stable error envelope through the worker boundary ------------------------------


async def test_error_envelope_contract_proven_rejection(
    client, monkeypatch, settings, factory, engine,
):
    seed = await _seed_comfy_generation(client, monkeypatch, settings,
                                        factory, engine)
    gid = seed["generation_id"]
    double = LifecycleDouble(fail_prompt_400=True)
    assert await _run_once(engine, settings, "w-env1", double) == "failed"
    row = await _row(engine, gid)
    assert row["status"] == "failed"
    assert row["error_code"] == "EXECUTOR_UNAVAILABLE"
    assert row["error_message"]


async def test_error_envelope_missing_historical_artifact(
    client, monkeypatch, settings, factory, engine,
):
    seed = await _seed_comfy_generation(client, monkeypatch, settings,
                                        factory, engine)
    gid = seed["generation_id"]
    row = await _row(engine, gid)

    # The historical manifest bytes vanish before execution.
    artifact = (Path(settings.data_dir) / "workflow-artifacts" / "manifests"
                / "sha256" / row["manifest_hash"][0:2]
                / row["manifest_hash"][2:4] / f"{row['manifest_hash']}.json")
    assert artifact.exists()
    artifact.unlink()

    double = LifecycleDouble()
    assert await _run_once(engine, settings, "w-env2", double) == "failed"
    row = await _row(engine, gid)
    assert row["status"] == "failed"
    assert row["error_code"] == "WORKFLOW_MANIFEST_MISSING"
    # No POST happened: retrieval precedes any executor interaction.
    assert double.prompt_posts == []


# --- aggregate AST boundary + state-space audits -----------------------------------

SERVER_SRC = BASE_DIR / "server" / "soloring"
COMFY_PKG = SERVER_SRC / "executors" / "comfy"


def _py_files(root: Path):
    return [p for p in root.rglob("*.py")]


def _imports_of(tree) -> set[str]:
    mods: set[str] = set()
    for node in ast_walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    return mods


def ast_walk(tree):
    import ast
    yield from ast.walk(tree)


def test_comfy_package_is_db_and_worker_free():
    forbidden_roots = ("soloring.db", "soloring.worker", "soloring.generation",
                       "soloring.domain", "soloring.assets", "sqlalchemy",
                       "sqlite3", "alembic")
    # Sole sanctioned exception: the pure canonical-bytes serializer shared
    # contract (imports nothing but json — creative state it is not).
    allowed = {"soloring.domain.canonical"}
    for path in _py_files(COMFY_PKG):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for mod in _imports_of(tree):
            if mod in allowed:
                continue
            assert not mod.startswith(forbidden_roots), (
                f"{path.name} imports {mod}: the Comfy adapter must stay "
                "DB/worker/creative-state free"
            )


def test_wire_dialect_keys_confined_to_wire():
    import ast
    dialect_keys = ("queue_running", "queue_pending", "status_str")
    for path in _py_files(COMFY_PKG):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast_walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value in dialect_keys:
                    assert path.name == "wire.py", (
                        f"{path.name} touches raw dialect key "
                        f"{node.value!r}; wire.py is the only parsing layer"
                    )


def test_submit_prompt_has_exactly_two_sanctioned_call_sites():
    hits = []
    for path in _py_files(SERVER_SRC):
        src = path.read_text(encoding="utf-8")
        if ".submit_prompt(" in src:
            hits.append(path)
    # 1) the durable one-shot-protocol module (lifecycle authority);
    # 2) the M5B-1 diagnostic marker canary, which deliberately bypasses
    #    the durable protocol (the probe is DB-free and posts exactly one
    #    labeled throwaway prompt — never a Generation lifecycle path).
    allowed = [
        SERVER_SRC / "worker" / "comfy_submission.py",
        SERVER_SRC / "executors" / "comfy" / "probe.py",
    ]
    assert hits == allowed, (
        f"/prompt must be invoked from exactly {allowed}: {hits}"
    )
    # And no generic retry layer wraps it (client construction is transport-
    # passthrough; M5A-6 covers the exactly-one-attempt contract).


def test_worker_lifecycle_transitions_never_regress():
    import ast
    allowed = {"submitted", "running", "importing", "succeeded", "failed",
               "interrupted", "cancelled"}
    forbidden = {"queued", "preparing", "not_started", "submission_possible",
                 "confirmed", "uncertain"}
    seen: set[str] = set()
    for path in _py_files(SERVER_SRC / "worker"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast_walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else (
                node.func.attr if isinstance(node.func, ast.Attribute) else ""
            )
            if name != "transition_owned_generation":
                continue
            if len(node.args) >= 4:
                target = node.args[3]
            else:
                target = node.keywords[0].value if (
                    node.keywords and node.keywords[0].arg == "to_status"
                ) else None
            assert isinstance(target, ast.Constant) and isinstance(
                target.value, str), f"non-literal transition in {path.name}"
            assert target.value not in forbidden, (
                f"{path.name} transitions to forbidden {target.value!r}"
            )
            seen.add(target.value)
    assert seen <= allowed
    assert seen  # the scan actually found call sites


def test_queued_status_writes_confined_to_requeue_and_insert():
    writers = []
    for path in _py_files(SERVER_SRC):
        src = path.read_text(encoding="utf-8")
        # WRITES of queued only; the cancel route's WHERE status='queued'
        # read filter is the sanctioned §69 immediate-cancel check.
        if "SET status = 'queued'" in src or "SET status='queued'" in src:
            writers.append(path)
    allowed = [
        SERVER_SRC / "worker" / "ownership.py",     # requeue (fenced, attempt-less only)
        SERVER_SRC / "generation" / "repository.py",  # creation INSERT
    ]
    for w in writers:
        assert w in allowed, f"unexpected queued-status writer: {w}"


def test_generation_status_mutation_confined_to_worker_and_cancel():
    # Lifecycle status mutations belong to the worker fence; the ONLY API-side
    # exception is the transactional immediate-cancel of not-yet-executing
    # work (v0.1 §69), which never touches active execution.
    for path in _py_files(SERVER_SRC):
        src = path.read_text(encoding="utf-8")
        if "UPDATE generations SET status" in src:
            assert path in (
                SERVER_SRC / "worker" / "ownership.py",
                SERVER_SRC / "worker" / "recovery.py",
                SERVER_SRC / "api" / "generations.py",
            ), f"unexpected status writer: {path}"
