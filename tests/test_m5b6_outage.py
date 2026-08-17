"""M5B-6 — outage-tolerant observation regressions (product unit level).

Transient read failures shorter than the outage window must NEVER terminate
the drive (the executor being unreachable is not evidence about the prompt);
only an outage exceeding the window classifies EXECUTOR_UNAVAILABLE
interruption. Conclusive absence from a REACHABLE executor still follows the
disappearance grace (COMFY_JOB_LOST), independently of outages.
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
from soloring.executors.comfy.client import ComfyClient
from soloring.settings import BASE_DIR, Settings
from soloring.worker import ownership
from soloring.worker.comfy_pipeline import drive_comfy_generation

PNG = b"\x89PNG\r\n\x1a\n" + b"ref" * 8


class OutageDouble:
    """Speaks the release-v3 dialect; drops N consecutive reads on demand."""

    base_url = "http://comfy.test"

    def __init__(self):
        self.fail_reads = 0
        self.read_failures = 0
        self.posts = 0
        self.pid = "p-outage-1"
        self.terminal_after = 2  # polls before terminal success

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/upload/image":
            body = request.content
            import re as _re

            sub = _re.search(rb'name="subfolder"\r\n\r\n([^\r]*)', body)
            return httpx.Response(200, json={
                "name": "x.png",
                "subfolder": sub.group(1).decode() if sub else "",
            })
        if path == "/prompt":
            self.posts += 1
            return httpx.Response(200, json={"prompt_id": self.pid})
        if path in ("/queue",) or path.startswith("/history"):
            if self.fail_reads > 0:
                self.fail_reads -= 1
                self.read_failures += 1
                raise httpx.ConnectError("transient outage")
            if path.startswith("/history"):
                self.terminal_after -= 1
                if self.terminal_after <= 0:
                    marker = self.marker
                    return httpx.Response(200, json={self.pid: {
                        "prompt": [0, self.pid, {}, marker, []],
                        "outputs": {"15": {"images": [
                            {"filename": "out.webp", "subfolder": "",
                             "type": "output"}]}},
                        "status": {"status_str": "success",
                                   "messages": []},
                    }})
                return httpx.Response(200, json={})
            return httpx.Response(200, json={
                "queue_running": [], "queue_pending": []})
        if path == "/view":
            return httpx.Response(200, content=b"RIFF-outage-proof-bytes")
        return httpx.Response(404)

    marker: dict = {}


async def _seed(client, factory, engine, settings, monkeypatch) -> str:
    import soloring.api.generations as generations_api
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from soloring.db.models import Asset, Blob
    from soloring.domain.ids import new_uuid

    settings.executor = "comfy"
    saved = generations_api.get_settings
    generations_api.get_settings = lambda: settings
    try:
        async with factory() as s:
            pid = (await projects.create_project(
                s, ProjectCreate(name="P"))).id
            shot = await shots.create_shot(s, pid, ShotCreate(subject="x"))
        bh = hashlib.sha256(PNG).hexdigest()
        path = BlobStore(settings).path_for_hash(bh)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(PNG)
        aid = new_uuid()
        f = async_sessionmaker(bind=engine, expire_on_commit=False,
                               class_=AsyncSession)
        async with f() as s:
            s.add(Blob(hash=bh, path=f"sha256/{bh[:2]}/{bh[2:4]}/{bh}",
                       size_bytes=len(PNG), detected_media_type=None))
            await s.flush()
            s.add(Asset(id=aid, project_id=pid, blob_hash=bh,
                        kind="reference"))
            await s.commit()
        async with f() as s:
            await references.replace_references(
                s, shot.id, [ReferenceInput(asset_id=aid, role="reference")])
        r = await client.post(f"/shots/{shot.id}/generations")
        assert r.status_code == 202, r.text
        return r.json()["id"]
    finally:
        generations_api.get_settings = saved


async def _run(client, factory, engine, settings, monkeypatch,
               outage_grace, double):
    gid = await _seed(client, factory, engine, settings, monkeypatch)
    from soloring.workflows import manifest as mm
    monkeypatch.setattr(mm, "WORKFLOW_DIR",
                        BASE_DIR / "workflows" / "hunyuan_i2v_v1")
    w = "w-outage"
    await ownership.acquire_worker_lease(
        engine, w, settings.worker_lease_ttl_seconds)
    claim = await ownership.claim_next_generation(engine, w)
    _, attempt = claim
    double.marker = {"soloring": {"generation_id": gid,
                                  "attempt_id": attempt}}
    c = ComfyClient(double.base_url, w, timeout=10.0,
                    transport=httpx.MockTransport(double.handler))
    try:
        result = await drive_comfy_generation(
            engine, settings, w, gid, attempt, c,
            outage_grace_seconds=outage_grace, poll_interval=0.02,
            disappearance_grace_seconds=0.2,
        )
    finally:
        await c.aclose()
    return gid, result, double


async def test_transient_outage_shorter_than_window_continues(
    client, factory, engine, settings, monkeypatch,
):
    """~6 consecutive read failures with a 5s window: the drive MUST
    survive, re-observe the SAME prompt after recovery, and publish."""
    double = OutageDouble()
    double.fail_reads = 6  # client retries once per call -> 3 failed polls
    gid, result, double = await _run(
        client, factory, engine, settings, monkeypatch,
        outage_grace=5.0, double=double,
    )
    assert result == "succeeded"
    assert double.posts == 1  # never resubmitted
    async with engine.connect() as conn:
        takes = (await conn.execute(text(
            "SELECT COUNT(*) FROM takes WHERE generation_id=:g"),
            {"g": gid})).scalar_one()
    assert takes == 1


async def test_outage_longer_than_window_interrupts_unavailable(
    client, factory, engine, settings, monkeypatch,
):
    double = OutageDouble()
    double.fail_reads = 10_000  # effectively forever
    gid, result, double = await _run(
        client, factory, engine, settings, monkeypatch,
        outage_grace=0.3, double=double,
    )
    assert result == "interrupted"
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT error_code, status FROM generations WHERE id=:g"),
            {"g": gid})).mappings().one()
    assert row["status"] == "interrupted"
    assert row["error_code"] == "EXECUTOR_UNAVAILABLE"
    assert double.posts == 1  # the outage never reopens submission
