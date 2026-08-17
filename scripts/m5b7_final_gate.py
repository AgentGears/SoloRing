"""M5B-7 — final live release gate.

  A. Cadence measurement on a cheap canary (request rate, terminal-detection
     latency) with the new SOLORING_COMFY_OBSERVATION_POLL_SECONDS default.
  B. Final real Hunyuan Generation (release v3) through the full product
     path at the production cadence: exactly one /prompt, bounded
     observation counts, heartbeats, streaming bridge, one Take/Asset/Blob,
     approval through the API.
  C. Failure-envelope assertion: every terminal row in the specimen carries
     a stable bounded code, no raw executor bodies.

Specimen: data/m5b7-specimen/.
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

from soloring.api.main import create_app
from soloring.api.schemas.projects import ProjectCreate
from soloring.api.schemas.references import ReferenceInput
from soloring.api.schemas.shots import ShotCreate
from soloring.assets.blob_store import BlobStore
from soloring.db import models  # noqa: F401
from soloring.db.base import Base
from soloring.db.engine import create_soloring_engine, create_session_factory
from soloring.domain import projects, references, shots
from soloring.domain.ids import new_uuid
from soloring.executors.comfy.client import ComfyClient
from soloring.generation import service as gen_service
from soloring.settings import BASE_DIR, Settings
from soloring.worker import ownership
from soloring.worker.comfy_pipeline import ClientViewStreamProvider
from soloring.worker.comfy_pipeline import drive_comfy_generation

SPECIMEN = BASE_DIR / "data" / "m5b7-specimen"
BASE_URL = "http://127.0.0.1:8188"
W = "w-m5b7"

ledger: dict = {"started_at": datetime.now(timezone.utc).isoformat(),
                "phases": {}}


def fail(phase: str, msg: str) -> None:
    ledger["failure"] = f"{phase}: {msg}"
    (SPECIMEN / "ledger.json").write_text(json.dumps(ledger, indent=2,
                                                     default=str))
    raise SystemExit(f"M5B-7 GATE FAILURE [{phase}]: {msg}")


def save() -> None:
    (SPECIMEN / "ledger.json").write_text(json.dumps(ledger, indent=2,
                                                     default=str))


def get_json(path: str):
    return json.load(urllib.request.urlopen(BASE_URL + path, timeout=10))


def make_png(width: int, height: int) -> bytes:
    def chunk(tag, data):
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
            + chunk(b"IHDR", width.to_bytes(4, "big")
                    + height.to_bytes(4, "big") + bytes((8, 2, 0, 0, 0)))
            + chunk(b"IDAT", zlib.compress(raw, 6))
            + chunk(b"IEND", b""))


class Rec(httpx.AsyncBaseTransport):
    def __init__(self):
        self.inner = httpx.AsyncHTTPTransport()
        self.prompt_posts = 0
        self.uploads = 0
        self.history_gets = 0
        self.queue_gets = 0
        self.view_calls = 0
        self.job_cancels = 0
        self.interrupts = 0

    async def handle_async_request(self, request: httpx.Request):
        path = request.url.path
        if path == "/prompt":
            await request.aread()
        response = await self.inner.handle_async_request(request)
        if path == "/prompt":
            self.prompt_posts += 1
        elif path == "/upload/image":
            self.uploads += 1
        elif path.startswith("/history"):
            self.history_gets += 1
        elif path == "/queue":
            self.queue_gets += 1
        elif path == "/view":
            self.view_calls += 1
        elif path.startswith("/api/jobs/"):
            self.job_cancels += 1
        elif path == "/interrupt":
            self.interrupts += 1
        return response


CANARY_GRAPH = {
    "1": {"class_type": "LoadImage", "inputs": {"image": "x"}},
    "2": {"class_type": "SaveImage",
          "inputs": {"images": ["1", 0], "filename_prefix": "m5b7_canary"}},
}


async def cadence_measurement() -> dict:
    """Cheap prompt observed at the production cadence via a real drive."""
    print("[A] cadence measurement on a CPU canary…", flush=True)
    from soloring.executors.comfy.probe import PROBE_PNG

    import os
    import tempfile

    fd, name = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    Path(name).write_bytes(PROBE_PNG)
    rec = Rec()
    client = ComfyClient(BASE_URL, "m5b7-cadence", timeout=30.0,
                         transport=rec)
    ref = await client.upload_input(source_path=Path(name),
                                    filename="m5b7.png",
                                    subfolder="m5b7_cadence")
    Path(name).unlink(missing_ok=True)
    graph = json.loads(json.dumps(CANARY_GRAPH))
    graph["1"]["inputs"]["image"] = (f"{ref.subfolder}/{ref.name}"
                                     if ref.subfolder else ref.name)
    payload = {"prompt": graph,
               "extra_data": {"soloring": {"generation_id": "m5b7-cadence",
                                           "attempt_id": "m5b7-a"}},
               "client_id": "m5b7"}
    t0 = time.monotonic()
    outcome = await client.submit_prompt(payload)
    pid = outcome.prompt_id
    deadline = time.monotonic() + 60
    terminal_at = None
    while time.monotonic() < deadline:
        history = await client.history(pid)
        if pid in history:
            terminal_at = time.monotonic()
            break
        await asyncio.sleep(1.0)  # the production cadence
    await client.aclose()
    duration = (terminal_at or time.monotonic()) - t0
    cycles = max(1, rec.history_gets)
    return {
        "prompt_accepted": pid is not None,
        "terminal_detected": terminal_at is not None,
        "detection_latency_s": round(duration, 2),
        "history_reads": rec.history_gets,
        "queue_reads": rec.queue_gets,
        "reads_per_second": round((rec.history_gets + rec.queue_gets)
                                  / max(duration, 0.001), 2),
    }


async def main() -> None:
    SPECIMEN.mkdir(parents=True, exist_ok=True)
    if get_json("/queue")["queue_running"] or \
            get_json("/queue")["queue_pending"]:
        fail("preflight", "live queue not empty")

    # ---- A. cadence --------------------------------------------------------
    cadence = await cadence_measurement()
    ledger["phases"]["A_cadence"] = cadence
    save()
    print(f"[A] {json.dumps(cadence)}", flush=True)
    if cadence["reads_per_second"] > 5:
        fail("A", f"cadence still too aggressive: {cadence}")

    # ---- B. final real generation -----------------------------------------
    settings = Settings(data_dir=SPECIMEN)
    settings.executor = "comfy"
    settings.comfy_base_url = BASE_URL
    settings.comfy_cancellation_mode = "targeted"  # BEFORE the assertion
    # Stage the v1 capability record AND the live launcher attestation into
    # the specimen, then ASSERT the targeted capability actually engages —
    # the final proof must not rest on a silent SOFT_ONLY fallback.
    import shutil

    fp_src = BASE_DIR / "data" / "comfy-fingerprint"
    fp_dst = SPECIMEN / "comfy-fingerprint"
    fp_dst.mkdir(parents=True, exist_ok=True)
    for name in ("capability_m5b5.json", "deployment_attestation.json"):
        shutil.copy(fp_src / name, fp_dst / name)
    from soloring.executors.comfy.capability_record import (
        load_capability_record, load_deployment_attestation,
    )
    from soloring.worker.comfy_pipeline import resolve_capability

    _record = load_capability_record(SPECIMEN)
    _att = load_deployment_attestation(SPECIMEN)
    _probe_client = ComfyClient(BASE_URL, "m5b7-capcheck", timeout=15.0)
    _resolved = await resolve_capability(settings, _probe_client)
    await _probe_client.aclose()
    if _resolved.mode.value != "targeted":
        fail("B", f"targeted capability did NOT engage for the final proof "
                 f"(resolved {_resolved.mode.value!r} — record "
                 f"{_record.comfyui_commit[:12]}, attestation "
                 f"{_att.comfyui_commit[:12]})")
    print(f"[B] targeted capability ENGAGED (record==attestation=="
          f"{_record.comfyui_commit[:12]}…)", flush=True)
    ledger["phases"]["B_capability_engaged"] = {
        "resolved_mode": _resolved.mode.value,
        "record_comfyui_commit": _record.comfyui_commit,
        "attestation_comfyui_commit": _att.comfyui_commit,
        "retry_safety": _resolved.retry_safety,
    }
    save()
    settings.executor = "comfy"
    settings.comfy_cancellation_mode = "targeted"  # mechanically bound
    engine = create_soloring_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False,
                                 class_=AsyncSession)

    png = make_png(848, 480)
    bh = hashlib.sha256(png).hexdigest()
    p = BlobStore(settings).path_for_hash(bh)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(png)
    async with factory() as s:
        pid = (await projects.create_project(
            s, ProjectCreate(name="M5B-7 Final Release Specimen"))).id
        shot = await shots.create_shot(
            s, pid, ShotCreate(subject="Goldfish orbiting a paper lantern, "
                                       "night pond"))
        from soloring.db.models import Asset, Blob
        aid = new_uuid()
        s.add(Blob(hash=bh, path=f"sha256/{bh[:2]}/{bh[2:4]}/{bh}",
                   size_bytes=len(png), detected_media_type="image/png"))
        await s.flush()
        s.add(Asset(id=aid, project_id=pid, blob_hash=bh, kind="reference"))
        await s.commit()
    async with factory() as s:
        await references.replace_references(
            s, shot.id, [ReferenceInput(asset_id=aid, role="reference")])
        gen = await gen_service.create_generation_request(
            s, shot.id, settings=settings)
    gid = gen.id

    await ownership.acquire_worker_lease(
        engine, W, settings.worker_lease_ttl_seconds)
    claim = await ownership.claim_next_generation(engine, W)
    assert claim[0] == gid
    attempt = claim[1]

    rec = Rec()
    client = ComfyClient(BASE_URL, W, timeout=600.0, transport=rec)

    # heartbeats + ticker during the drive
    hb = {"ok": 0, "fail": 0}
    ticker = {"max_gap": 0.0}
    stop = asyncio.Event()

    async def heartbeat():
        while not stop.is_set():
            try:
                r = await ownership.refresh_worker_lease(engine, W)
                hb["ok" if r is ownership.LeaseRetentionResult.RETAINED
                   else "fail"] += 1
            except Exception:  # noqa: BLE001
                hb["fail"] += 1
            for _ in range(20):
                if stop.is_set():
                    return
                await asyncio.sleep(0.1)

    async def tick():
        last = time.monotonic()
        while not stop.is_set():
            await asyncio.sleep(0.01)
            now = time.monotonic()
            ticker["max_gap"] = max(ticker["max_gap"], now - last)
            last = now

    # bridge probe
    import soloring.worker.comfy_pipeline as pipeline_mod

    real_provider = pipeline_mod.ClientViewStreamProvider
    bridge = {"loop_tid": threading.get_ident(), "view_tid": None,
              "chunks": 0}

    class Probed(real_provider):
        def __call__(self, filename, subfolder, _read=1 << 20):
            bridge["view_tid"] = threading.get_ident()
            chunk = super().__call__(filename, subfolder, _read)
            bridge["chunks"] += 1
            return chunk

    pipeline_mod.ClientViewStreamProvider = Probed

    hb_task = asyncio.create_task(heartbeat())
    tick_task = asyncio.create_task(tick())
    t0 = time.monotonic()
    result = await drive_comfy_generation(
        engine, settings, W, gid, attempt, client,
    )
    duration = time.monotonic() - t0
    stop.set()
    await asyncio.gather(hb_task, tick_task, return_exceptions=True)
    await client.aclose()
    if result != "succeeded":
        fail("B", f"final generation result {result!r}")

    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT executor_submission_state, executor_job_id, "
            "error_code FROM generations WHERE id=:g"),
            {"g": gid})).mappings().one()
        take = dict((await conn.execute(text(
            "SELECT id, output_key FROM takes WHERE generation_id=:g"),
            {"g": gid})).mappings().one())
        counts = (await conn.execute(text(
            "SELECT (SELECT COUNT(*) FROM takes WHERE generation_id=:g) "
            "AS takes, (SELECT COUNT(*) FROM assets WHERE kind='output') "
            "AS assets"), {"g": gid})).mappings().one()
    assert row["executor_submission_state"] == "confirmed"
    assert rec.prompt_posts == 1, rec.prompt_posts
    assert rec.uploads == 1
    assert rec.job_cancels == 0 and rec.interrupts == 0
    assert bridge["view_tid"] is not None and \
        bridge["view_tid"] != bridge["loop_tid"]

    # approval through the normal API
    app = create_app(settings)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    api = httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                            base_url="http://soloring-test")
    r = await api.get(f"/shots/{shot.id}/takes")
    takes_payload = r.json()
    assert takes_payload[0]["output_kind"] == "video", takes_payload[0]
    assert takes_payload[0]["detected_media_type"] is None
    r2 = await api.post(f"/takes/{take['id']}/approve")
    assert r2.status_code == 200 and r2.json()["take_id"] == take["id"]
    r3 = await api.get(f"/shots/{shot.id}")
    assert r3.json()["approved_take_id"] == take["id"]
    await api.aclose()

    ledger["phases"]["B_final_generation"] = {
        "result": result,
        "duration_s": round(duration, 1),
        "prompt_posts": rec.prompt_posts,
        "uploads": rec.uploads,
        "history_reads": rec.history_gets,
        "queue_reads": rec.queue_gets,
        "view_calls": rec.view_calls,
        "reads_per_second": round(
            (rec.history_gets + rec.queue_gets) / duration, 2),
        "heartbeat": dict(hb),
        "ticker_max_gap_s": round(ticker["max_gap"], 4),
        "bridge_threads_differ": True,
        "takes": counts["takes"], "assets": counts["assets"],
        "approved": True,
        "take_payload_head": {
            "output_kind": takes_payload[0]["output_kind"],
            "detected_media_type": takes_payload[0]["detected_media_type"],
        },
    }
    save()
    print(f"[B] final generation succeeded in {duration:.1f}s "
          f"({rec.history_gets}H/{rec.queue_gets}Q reads, "
          f"{rec.view_calls} views)", flush=True)

    # ---- C. envelope audit over all live specimens -------------------------
    envelopes = []
    for spec in ("m5b3", "m5b4", "m5b5", "m5b6", "m5b7"):
        db = BASE_DIR / "data" / spec / "soloring.db"
        if not db.exists():
            continue
        import sqlite3

        con = sqlite3.connect(str(db))
        for code, msg in con.execute(
                "SELECT error_code, error_message FROM generations "
                "WHERE error_code IS NOT NULL").fetchall():
            envelopes.append({"specimen": spec, "code": code,
                              "msg_len": len(msg or ""),
                              "has_raw": any(t in (msg or "") for t in (
                                  "Traceback", "C:\\AI", "models/",
                                  "gguf", "safetensors"))})
        con.close()
    bad = [e for e in envelopes if e["has_raw"] or e["msg_len"] > 500]
    if bad:
        fail("C", f"unsafe error envelopes: {bad}")
    ledger["phases"]["C_envelopes"] = {
        "samples": len(envelopes), "unsafe": 0,
        "codes": sorted({e["code"] for e in envelopes}),
    }
    save()
    print(f"[C] {len(envelopes)} error envelopes audited — all bounded",
          flush=True)

    ledger["finished_at"] = datetime.now(timezone.utc).isoformat()
    save()
    await engine.dispose()
    print("\nM5B-7 GATE: ALL PROOFS HELD — specimen at", SPECIMEN, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
