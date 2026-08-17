"""M5B-4 — live worker-death adoption.

A real Generation (G4) is created, claimed and driven by worker A — a
SEPARATE PROCESS that is abruptly killed (taskkill) once the prompt id is
durable and the GPU job is demonstrably running. Worker B (a genuinely
fresh identity, in-process) then follows the REAL ownership path: lease
staleness → lease takeover → unconditional stale reconciliation → adoption
→ completion of the SAME attempt/prompt, with zero uploads, zero /prompt,
zero cancellations.

Specimen: data/m5b4-specimen/ (ledger + DB + blobs preserved).
Exit 0 == the mandatory gate held.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
import threading
import time
import urllib.request
import zlib
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from soloring.api.schemas.projects import ProjectCreate
from soloring.api.schemas.references import ReferenceInput
from soloring.api.schemas.shots import ShotCreate
from soloring.assets.blob_store import BlobStore
from soloring.db import models  # noqa: F401
from soloring.db.base import Base
from soloring.db.engine import create_soloring_engine
from soloring.domain import projects, references, shots
from soloring.domain.ids import new_uuid
from soloring.executors.base import StagedOutput
from soloring.executors.comfy.client import ComfyClient
from soloring.generation import service as gen_service
from soloring.generation.importer import import_staged_outputs
from soloring.settings import BASE_DIR, Settings
from soloring.worker import ownership
from soloring.worker.recovery import reconcile_stale_generations
from soloring.workflows.manifest import ExpectedOutput

SPECIMEN = BASE_DIR / "data" / "m5b4-specimen"
BASE_URL = "http://127.0.0.1:8188"
WORKER_A = "w-m5b4-A"
WORKER_B = "w-m5b4-B"

ledger: dict = {"started_at": datetime.now(timezone.utc).isoformat()}


def fail(msg: str) -> None:
    ledger["failure"] = msg
    (SPECIMEN / "ledger.json").write_text(json.dumps(ledger, indent=2,
                                                     default=str))
    raise SystemExit(f"M5B-4 GATE FAILURE: {msg}")


def make_png(width: int, height: int) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (len(data).to_bytes(4, "big") + tag + data
                + zlib.crc32(tag + data).to_bytes(4, "big"))

    row = bytearray()
    for x in range(width):
        row += bytes((x * 255 // width, 127, (x * 89) % 256))
    parts = []
    for y in range(height):
        parts.append(b"\x00")
        line = bytearray(row)
        g = y * 255 // height
        for x in range(width):
            line[x * 3 + 1] = g
        parts.append(bytes(line))
    raw = b"".join(parts)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", (width.to_bytes(4, "big")
                              + height.to_bytes(4, "big")
                              + bytes((8, 2, 0, 0, 0))))
            + chunk(b"IDAT", zlib.compress(raw, 6))
            + chunk(b"IEND", b""))


def http_get_json(path: str):
    return json.load(urllib.request.urlopen(BASE_URL + path, timeout=10))


class BTransport(httpx.AsyncBaseTransport):
    """Records worker B's ENTIRE client boundary: /prompt, uploads,
    cancellations, and global-vs-targeted history reads."""

    def __init__(self) -> None:
        self.inner = httpx.AsyncHTTPTransport()
        self.prompt_posts = 0
        self.uploads = 0
        self.queue_deletes = 0
        self.interrupts = 0
        self.global_history = 0
        self.targeted_history = 0
        self.queue_gets = 0
        self.view_calls = 0
        self.first_observation_t = None
        self.t0 = time.monotonic()

    async def handle_async_request(self, request: httpx.Request):
        path = request.url.path
        t = round(time.monotonic() - self.t0, 3)
        if path in ("/prompt", "/upload/image"):
            await request.aread()
        response = await self.inner.handle_async_request(request)
        if path == "/prompt" and request.method == "POST":
            self.prompt_posts += 1
        elif path == "/upload/image":
            self.uploads += 1
        elif path == "/queue" and request.method == "POST":
            self.queue_deletes += 1
        elif path == "/interrupt":
            self.interrupts += 1
        elif path == "/history":
            self.global_history += 1
        elif path.startswith("/history/"):
            self.targeted_history += 1
            if self.first_observation_t is None:
                self.first_observation_t = t
        elif path == "/queue":
            self.queue_gets += 1
            if self.first_observation_t is None:
                self.first_observation_t = t
        elif path == "/view":
            self.view_calls += 1
        return response


async def db_row(engine, sql, params):
    async with engine.connect() as conn:
        return dict((await conn.execute(text(sql), params)).mappings().one())


async def main() -> None:
    SPECIMEN.mkdir(parents=True, exist_ok=True)
    settings = Settings(data_dir=SPECIMEN)
    settings.executor = "comfy"
    settings.comfy_base_url = BASE_URL
    engine = create_soloring_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False,
                                 class_=AsyncSession)

    # ---- fresh real Generation -------------------------------------------
    png = make_png(848, 480)
    blob_hash = hashlib.sha256(png).hexdigest()
    store = BlobStore(settings)
    path = store.path_for_hash(blob_hash)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
    async with factory() as s:
        pid = (await projects.create_project(
            s, ProjectCreate(name="M5B-4 Adoption Specimen"))).id
        shot = await shots.create_shot(
            s, pid, ShotCreate(subject="Rain-slick alley, paper lanterns "
                                       "guttering in the wind"),
        )
        from soloring.db.models import Asset, Blob
        aid = new_uuid()
        if await s.get(Blob, blob_hash) is None:
            s.add(Blob(hash=blob_hash,
                       path=f"sha256/{blob_hash[:2]}/{blob_hash[2:4]}/{blob_hash}",
                       size_bytes=len(png), detected_media_type="image/png"))
            await s.flush()
        s.add(Asset(id=aid, project_id=pid, blob_hash=blob_hash,
                    kind="reference"))
        await s.commit()
    async with factory() as s:
        await references.replace_references(
            s, shot.id, [ReferenceInput(asset_id=aid, role="reference")],
        )
        generation = await gen_service.create_generation_request(
            s, shot.id, settings=settings,
        )
    gid = generation.id
    pre = await db_row(engine, "SELECT attempt_id, executor_submission_hash, "
                               "manifest_hash, workflow_template_hash, "
                               "workflow_spec_hash, executor_submission_json "
                               "FROM generations WHERE id=:g", {"g": gid})
    ledger["pre"] = {"generation_id": gid, "worker_a": WORKER_A,
                     "worker_b": WORKER_B, **pre}
    print(f"[setup] generation {gid} queued", flush=True)

    # ---- worker A (separate process) submits and observes -----------------
    a_proc = subprocess.Popen(
        [str(BASE_DIR / ".venv" / "Scripts" / "python.exe"), "-u",
         str(BASE_DIR / "scripts" / "m5b4_worker_a.py"),
         str(SPECIMEN), WORKER_A, BASE_URL],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    print("[A] process launched", flush=True)

    # Wait for: confirmed + prompt running on the GPU.
    deadline = time.monotonic() + 240
    prompt_id = None
    while time.monotonic() < deadline:
        row = await db_row(engine, "SELECT executor_submission_state, "
                                   "executor_job_id, status, worker_id "
                                   "FROM generations WHERE id=:g", {"g": gid})
        if (row["executor_submission_state"] == "confirmed"
                and row["executor_job_id"]):
            prompt_id = row["executor_job_id"]
            queue = http_get_json("/queue")
            running_ids = [e[1] for e in queue.get("queue_running", [])]
            pending_ids = [e[1] for e in queue.get("queue_pending", [])]
            if prompt_id in running_ids or prompt_id in pending_ids:
                break
        await asyncio.sleep(0.5)
    if prompt_id is None:
        a_proc.kill()
        fail("worker A never reached a confirmed running prompt")
    frame = await db_row(engine, "SELECT attempt_id, "
                                   "executor_submission_state, "
                                   "executor_submission_hash, "
                                   "executor_submission_json, "
                                   "executor_job_id, executor_handle_json, "
                                   "manifest_hash, workflow_template_hash, "
                                   "workflow_spec_hash, soft_cancel_selected_at "
                                   "FROM generations WHERE id=:g", {"g": gid})
    ledger["a_confirmed"] = {
        "prompt_id": prompt_id,
        "t": datetime.now(timezone.utc).isoformat(),
        "frame": frame,
    }
    print(f"[A] confirmed prompt {prompt_id} and demonstrably queued/running",
          flush=True)

    a_last = await db_row(engine, "SELECT heartbeat_at, claimed_at, "
                                  "worker_id FROM generations WHERE id=:g",
                          {"g": gid})
    lease_a = await db_row(engine, "SELECT worker_id, heartbeat_at FROM "
                                   "worker_leases WHERE "
                                   "name='generation-worker'", {})
    ledger["a_death_precise"] = {
        "generation_worker": a_last["worker_id"],
        "generation_heartbeat_at": a_last["heartbeat_at"],
        "lease_worker": lease_a["worker_id"],
        "lease_heartbeat_at": lease_a["heartbeat_at"],
    }

    # ---- ABRUPT DEATH (taskkill, no grace) ---------------------------------
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(a_proc.pid)],
                   capture_output=True)
    a_proc.wait(timeout=15)
    t_death = time.monotonic()
    print(f"[A] KILLED (pid {a_proc.pid}) while the GPU job runs", flush=True)
    ledger["a_killed"] = {"pid": a_proc.pid,
                          "t": datetime.now(timezone.utc).isoformat()}

    # Prove Comfy kept running P immediately after the death.
    await asyncio.sleep(2)
    queue = http_get_json("/queue")
    still = (prompt_id in [e[1] for e in queue.get("queue_running", [])]
             or prompt_id in [e[1] for e in queue.get("queue_pending", [])])
    ledger["comfy_after_death"] = {"prompt_still_active": still}

    # ---- B: the REAL ownership path — wait for natural staleness ----------
    ttl = settings.worker_lease_ttl_seconds
    print(f"[B] waiting for natural lease staleness (ttl={ttl}s)…", flush=True)
    deadline = time.monotonic() + ttl + 90
    taken = None
    while time.monotonic() < deadline:
        taken = await ownership.acquire_worker_lease(
            engine, WORKER_B, ttl
        )
        if taken is ownership.LeaseAcquisitionResult.TAKEN_OVER:
            break
        await asyncio.sleep(2)
    if taken is not ownership.LeaseAcquisitionResult.TAKEN_OVER:
        fail(f"B never took over the lease (last={taken})")
    t_takeover = time.monotonic()
    print(f"[B] lease TAKEN_OVER from dead A "
          f"(failover wait {t_takeover - t_death:.1f}s)", flush=True)

    b_transport = BTransport()
    b_client = ComfyClient(BASE_URL, WORKER_B, timeout=600.0,
                           transport=b_transport)
    acted = await reconcile_stale_generations(
        engine, WORKER_B, settings, comfy_client=b_client,
    )
    await b_client.aclose()
    t_done = time.monotonic()
    print(f"[B] reconciliation drove {acted} generation(s) to terminal",
          flush=True)

    ledger["b_run"] = {
        "takeover_after_death_s": round(t_takeover - t_death, 1),
        "first_observation_after_takeover_s": b_transport.first_observation_t,
        "total_s": round(t_done - t_takeover, 1),
        "prompt_posts": b_transport.prompt_posts,
        "uploads": b_transport.uploads,
        "queue_deletes": b_transport.queue_deletes,
        "interrupts": b_transport.interrupts,
        "global_history_scans": b_transport.global_history,
        "targeted_history_reads": b_transport.targeted_history,
        "queue_reads": b_transport.queue_gets,
        "view_calls": b_transport.view_calls,
    }

    # ---- adoption preserved the frame exactly ------------------------------
    post = await db_row(engine, "SELECT * FROM generations WHERE id=:g",
                        {"g": gid})
    assert post["attempt_id"] == frame["attempt_id"], "attempt changed!"
    assert frame["attempt_id"] is not None, "A never minted an attempt"
    assert post["executor_submission_state"] == "confirmed"
    assert post["executor_submission_hash"] == frame["executor_submission_hash"]
    assert post["executor_submission_json"] == frame["executor_submission_json"]
    assert post["executor_job_id"] == prompt_id == frame["executor_job_id"]
    assert post["executor_handle_json"] == frame["executor_handle_json"]
    assert post["manifest_hash"] == frame["manifest_hash"]
    assert post["workflow_template_hash"] == frame["workflow_template_hash"]
    assert post["workflow_spec_hash"] == frame["workflow_spec_hash"]
    assert post["soft_cancel_selected_at"] == (
        frame["soft_cancel_selected_at"]
    )
    assert post["status"] == "succeeded", f"status {post['status']}"
    assert post["worker_id"] == WORKER_B

    # B did NOTHING forbidden.
    assert b_transport.prompt_posts == 0, "B posted /prompt — CRITICAL"
    assert b_transport.uploads == 0, "B uploaded — F12 regression"
    assert b_transport.queue_deletes == 0
    assert b_transport.interrupts == 0
    assert b_transport.global_history == 0, "B scanned global history"

    # ---- exactly-once, from Comfy's own history ----------------------------
    history_all = http_get_json("/history")
    marker_prompts = []
    for pid_h, rec in history_all.items():
        marker = rec.get("prompt", [None, None, None, {}])[3].get("soloring")
        if marker and marker.get("generation_id") == gid:
            marker_prompts.append(pid_h)
    assert marker_prompts == [prompt_id], marker_prompts
    live_marker = history_all[prompt_id]["prompt"][3]["soloring"]
    assert live_marker["attempt_id"] == frame["attempt_id"]

    async with engine.connect() as conn:
        take = dict((await conn.execute(text(
            "SELECT id, output_key FROM takes WHERE generation_id=:g"),
            {"g": gid})).mappings().one())
        asset = dict((await conn.execute(text(
            "SELECT id, blob_hash FROM assets WHERE take_id=:t"),
            {"t": take["id"]})).mappings().one())
        n_takes = (await conn.execute(text(
            "SELECT COUNT(*) FROM takes WHERE generation_id=:g"),
            {"g": gid})).scalar_one()
        n_assets = (await conn.execute(text(
            "SELECT COUNT(*) FROM assets WHERE kind='output'"
        ))).scalar_one()
    assert n_takes == 1 and n_assets == 1

    out_path = store.path_for_hash(asset["blob_hash"])
    out_bytes = out_path.read_bytes()
    assert out_bytes[:4] == b"RIFF" and out_bytes[8:12] == b"WEBP"
    assert hashlib.sha256(out_bytes).hexdigest() == asset["blob_hash"]

    # ---- replay reconciliation import: zero duplicates ----------------------
    replay = SPECIMEN / "replay.webp"
    replay.write_bytes(out_bytes)
    from soloring.generation.repository import get_generation_full
    async with factory() as s:
        full = await get_generation_full(s, gid)
    imported = await import_staged_outputs(
        factory, store, full,
        [StagedOutput(output_key="video:0", path=replay, kind="video")],
        expected_outputs=[ExpectedOutput(
            name="video", kind="video", expected_count=1,
            accepted_media_types=None)],
        staging_directory=SPECIMEN,
    )
    async with engine.connect() as conn:
        n_takes2 = (await conn.execute(text(
            "SELECT COUNT(*) FROM takes WHERE generation_id=:g"),
            {"g": gid})).scalar_one()
        n_assets2 = (await conn.execute(text(
            "SELECT COUNT(*) FROM assets WHERE kind='output'"
        ))).scalar_one()
    assert imported == ["video:0"] and n_takes2 == 1 and n_assets2 == 1

    ledger["post"] = {
        "prompt_id": prompt_id,
        "take_id": take["id"], "asset_id": asset["id"],
        "output_blob_sha256": asset["blob_hash"],
        "output_bytes": len(out_bytes),
        "generation_status": post["status"],
        "marker_prompts_in_live_history": marker_prompts,
        "replay": {"imported": imported, "takes": n_takes2,
                   "assets": n_assets2},
    }
    ledger["finished_at"] = datetime.now(timezone.utc).isoformat()
    (SPECIMEN / "ledger.json").write_text(json.dumps(ledger, indent=2,
                                                     default=str))
    print(json.dumps(ledger["b_run"], indent=1))
    print(f"\nM5B-4 GATE: ALL PROOFS HELD — specimen at {SPECIMEN}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
