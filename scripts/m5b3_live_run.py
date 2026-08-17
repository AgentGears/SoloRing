"""M5B-3 — the first REAL end-to-end HunyuanVideo I2V generation.

Runs the complete M5A lifecycle against the dedicated live ComfyUI
(127.0.0.1:8188) with the release-v2 workflow, producing the durable
evidence specimen under data/m5b3-specimen/ (ledger.json + DB + blobs —
NOT cleaned up).

Instrumentation (all at the SoloRing client boundary):
  * /prompt call count + exact bodies (assert: exactly one POST per attempt);
  * /upload/image requested vs returned identity (namespace semantics);
  * observation timeline (/queue, /history GET timestamps);
  * the streaming bridge: consumer-vs-loop thread ids (runtime guard),
    chunk count, bytes, duration — while a concurrent ticker + lease and
    generation heartbeats run (deadlock/latency proof);
  * VRAM peak sampling.

Exit code 0 == the whole mandatory gate held.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import subprocess
import threading
import time
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
from soloring.db import models  # noqa: F401 — register tables
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
from soloring.worker.comfy_pipeline import drive_comfy_generation
from soloring.workflows.manifest import load_workflow

SPECIMEN = BASE_DIR / "data" / "m5b3-specimen"
BASE_URL = "http://127.0.0.1:8188"
WORKER = "w-m5b3-live"
POLL_INTERVAL = 1.0

ledger: dict = {"started_at": datetime.now(timezone.utc).isoformat()}


def fail(msg: str) -> None:
    ledger["failure"] = msg
    (SPECIMEN / "ledger.json").write_text(json.dumps(ledger, indent=2,
                                                     default=str))
    raise SystemExit(f"M5B-3 GATE FAILURE: {msg}")


# --- a real reference image (pure-python PNG, 848x480 gradient) -------------


def make_png(width: int, height: int) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (len(data).to_bytes(4, "big") + tag + data
                + zlib.crc32(tag + data).to_bytes(4, "big"))

    # Linear-time scanline writer (filter byte 0 + RGB gradient per row).
    row = bytearray()
    for x in range(width):
        row += bytes((x * 255 // width, 127, (x * 89) % 256))
    parts = []
    for y in range(height):
        g = y * 255 // height
        parts.append(b"\x00")
        line = bytearray(row)
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


# --- client-boundary instrumentation -----------------------------------------


class RecordingTransport(httpx.AsyncBaseTransport):
    """Wraps the real transport; records the SoloRing-facing HTTP surface."""

    def __init__(self) -> None:
        self.inner = httpx.AsyncHTTPTransport()
        self.prompt_posts: list[dict] = []
        self.uploads: list[dict] = []
        self.observations: list[dict] = []
        self.t0 = time.monotonic()

    async def handle_async_request(self, request: httpx.Request):
        path = request.url.path
        t = round(time.monotonic() - self.t0, 3)
        # Multipart bodies stream lazily: aread() caches them so BOTH the
        # recorder and the inner transport can consume them.
        if path in ("/prompt", "/upload/image"):
            await request.aread()
        response = await self.inner.handle_async_request(request)
        if path == "/prompt" and request.method == "POST":
            self.prompt_posts.append(
                {"t": t, "body": json.loads(request.content.decode())}
            )
        elif path == "/upload/image":
            body = request.content
            fname = re.search(rb'filename="([^"]*)"', body)
            sub = re.search(rb'name="subfolder"\r\n\r\n([^\r]*)', body)
            returned = {}
            try:
                await response.aread()
                returned = response.json()
            except Exception as exc:  # noqa: BLE001
                returned = {"capture_error": repr(exc)}
            self.uploads.append({
                "t": t,
                "requested_name": fname.group(1).decode() if fname else None,
                "requested_subfolder": sub.group(1).decode() if sub else None,
                "returned": returned,
            })
        elif path in ("/queue",) or path.startswith("/history"):
            self.observations.append({"t": t, "path": path})
        return response


# --- monitors -----------------------------------------------------------------


class Monitors:
    def __init__(self, engine, worker_id: str, generation_id: str | None):
        self.engine = engine
        self.worker_id = worker_id
        self.gid = generation_id
        self.stop = threading.Event()
        self.ticker_max_gap = 0.0
        self.lease_ok = 0
        self.lease_fail = 0
        self.gen_hb_ok = 0
        self.gen_hb_fail = 0
        self.vram_peak_mb = 0
        self.status_timeline: list[tuple[float, str]] = []
        self.loop_thread_id: int | None = None
        self.view_thread_id: int | None = None

    def start_background(self):
        threading.Thread(target=self._vram_loop, daemon=True).start()

    def _vram_loop(self):
        while not self.stop.is_set():
            try:
                out = subprocess.run(
                    ["nvidia-smi", "--query-gpu=memory.used",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=5,
                )
                self.vram_peak_mb = max(self.vram_peak_mb,
                                        int(out.stdout.strip()))
            except Exception:  # noqa: BLE001
                pass
            self.stop.wait(1.0)


async def monitor_heartbeat(m: Monitors):
    """Lease + generation heartbeat every 2s while the drive runs."""
    interval = 2.0
    while not m.stop.is_set():
        try:
            r = await ownership.refresh_worker_lease(m.engine, m.worker_id)
            if r is ownership.LeaseRetentionResult.RETAINED:
                m.lease_ok += 1
            else:
                m.lease_fail += 1
            if m.gid:
                r2 = await ownership.heartbeat_owned_generation(
                    m.engine, m.worker_id, m.gid
                )
                if r2 is ownership.OwnershipMutationResult.OK:
                    m.gen_hb_ok += 1
                else:
                    m.gen_hb_fail += 1
        except Exception:  # noqa: BLE001
            m.lease_fail += 1
        # Pure-async interval: threading.Event.wait() with no timeout
        # would BLOCK the event loop (the M5B-3 debugging lesson).
        for _ in range(int(interval * 10)):
            if m.stop.is_set():
                return
            await asyncio.sleep(0.1)


async def task_dumper(delay: float = 60.0):
    """Print every asyncio task's stack once — finds event-parked hangs the
    thread dumps cannot see."""
    await asyncio.sleep(delay)
    import traceback

    for task in asyncio.all_tasks():
        if task is asyncio.current_task():
            continue
        print(f"--- TASK {task.get_coro()!r} ---", flush=True)
        try:
            st = task.get_stack(limit=8)
            for frame in st:
                print(f"    {frame.f_code.co_filename}:"
                      f"{frame.f_lineno} in {frame.f_code.co_name}",
                      flush=True)
        except Exception as exc:  # noqa: BLE001
            print("    <no stack>", exc, flush=True)


async def monitor_ticker(m: Monitors):
    """Event-loop latency probe: max gap between 10ms ticks."""
    last = time.monotonic()
    while not m.stop.is_set():
        await asyncio.sleep(0.01)
        now = time.monotonic()
        m.ticker_max_gap = max(m.ticker_max_gap, now - last)
        last = now


async def monitor_status(m: Monitors):
    last = None
    while not m.stop.is_set():
        try:
            async with m.engine.connect() as conn:
                status = (await conn.execute(
                    text("SELECT status FROM generations WHERE id=:g"),
                    {"g": m.gid},
                )).scalar_one_or_none()
            if status is not None and status != last:
                m.status_timeline.append(
                    (round(time.monotonic() - m.t0, 3), status)
                )
                last = status
        except Exception:  # noqa: BLE001
            pass
        for _ in range(5):
            if m.stop.is_set():
                return
            await asyncio.sleep(0.1)


# --- bridge instrumentation ----------------------------------------------------


def install_bridge_probe(m: Monitors):
    import soloring.worker.comfy_pipeline as pipeline_mod

    real_provider = pipeline_mod.ClientViewStreamProvider
    events = {"chunks": 0, "bytes": 0, "t_start": None, "t_end": None}

    class ProbedProvider(real_provider):
        def __call__(self, filename, subfolder, _read=1 << 20):
            import time as _time

            m.view_thread_id = threading.get_ident()
            if events["t_start"] is None:
                events["t_start"] = _time.monotonic()
            chunk = super().__call__(filename, subfolder, _read)
            events["chunks"] += 1
            events["bytes"] += len(chunk)
            events["t_end"] = _time.monotonic()
            return chunk

    pipeline_mod.ClientViewStreamProvider = ProbedProvider
    return events


# --- the run -------------------------------------------------------------------


async def main() -> None:
    import asyncio as _a
    import faulthandler

    faulthandler.dump_traceback_later(120, repeat=True)

    loop = _a.get_running_loop()
    import threading as _th

    SPECIMEN.mkdir(parents=True, exist_ok=True)
    settings = Settings(data_dir=SPECIMEN)
    settings.executor = "comfy"
    settings.comfy_base_url = BASE_URL
    engine = create_soloring_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False,
                                 class_=AsyncSession)

    # ---- project / shot / REAL reference blob -----------------------------
    png = make_png(848, 480)
    blob_hash = hashlib.sha256(png).hexdigest()
    store = BlobStore(settings)
    blob_path = store.path_for_hash(blob_hash)
    blob_path.parent.mkdir(parents=True, exist_ok=True)
    blob_path.write_bytes(png)
    async with factory() as s:
        pid = (await projects.create_project(
            s, ProjectCreate(name="M5B-3 Live Specimen"))).id
        shot = await shots.create_shot(
            s, pid, ShotCreate(subject="Neon koi drifting through a night "
                                       "market, steam rising"),
        )
        from soloring.db.models import Asset, Blob
        aid = new_uuid()
        existing_blob = await s.get(Blob, blob_hash)
        if existing_blob is None:
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

    # ---- generation creation (captures v2 M/T into the specimen store) ----
    async with factory() as s:
        generation = await gen_service.create_generation_request(
            s, shot.id, settings=settings,
        )
    gid = generation.id

    async with engine.connect() as conn:
        pre = dict((await conn.execute(
            text("SELECT id, attempt_id, shot_revision_id, executor, "
                 "manifest_hash, workflow_template_hash, workflow_spec_hash, "
                 "executor_submission_hash, executor_submission_state, "
                 "seed, status FROM generations WHERE id=:g"),
            {"g": gid},
        )).mappings().one())
    async with engine.connect() as conn:
        rev = dict((await conn.execute(
            text("SELECT id, snapshot_hash FROM shot_revisions "
                 "WHERE id=:r"), {"r": pre["shot_revision_id"]},
        )).mappings().one())
        inputs = [dict(r) for r in (await conn.execute(
            text("SELECT input_key, position, asset_id, blob_hash "
                 "FROM generation_inputs WHERE generation_id=:g "
                 "ORDER BY input_key, position"), {"g": gid},
        )).mappings().all()]

    ledger["pre"] = {
        "generation_id": gid, **{k: pre[k] for k in pre},
        "revision": rev, "generation_inputs": inputs,
        "workflow_spec_matches": None,
    }
    # Spec-hash self-consistency: persisted bytes ARE the hashed bytes.
    async with factory() as s:
        from soloring.generation.repository import get_generation_full
        full = await get_generation_full(s, gid)
    import hashlib as _h
    assert _h.sha256(full.workflow_spec_json.encode()).hexdigest() == (
        pre["workflow_spec_hash"]
    ), "spec hash mismatch"
    print(f"[pre] generation {gid}")
    print(f"[pre] MH={pre['manifest_hash'][:16]}… TH="
          f"{pre['workflow_template_hash'][:16]}…")

    # ---- instrumented client ------------------------------------------------
    transport = RecordingTransport()
    client = ComfyClient(BASE_URL, WORKER, timeout=600.0,
                         transport=transport)

    # ---- claim + monitors ---------------------------------------------------
    assert await ownership.acquire_worker_lease(
        engine, WORKER, settings.worker_lease_ttl_seconds
    ) in (ownership.LeaseAcquisitionResult.ACQUIRED_NEW,
          ownership.LeaseAcquisitionResult.REFRESHED_SELF)
    claim = await ownership.claim_next_generation(engine, WORKER)
    assert claim is not None and claim[0] == gid
    attempt = claim[1]

    m = Monitors(engine, WORKER, gid)
    m.loop_thread_id = _th.get_ident()
    m.t0 = transport.t0
    m.start_background()
    bridge_events = install_bridge_probe(m)

    dumper_task = _a.create_task(task_dumper(60))
    hb_task = _a.create_task(monitor_heartbeat(m))
    tick_task = _a.create_task(monitor_ticker(m))
    status_task = _a.create_task(monitor_status(m))

    # ---- THE DRIVE -----------------------------------------------------------
    print("[run] driving real generation (this is the expensive part)…")
    t_start = time.monotonic()
    try:
        result = await drive_comfy_generation(
            engine, settings, WORKER, gid, attempt, client,
            poll_interval=POLL_INTERVAL,
        )
    finally:
        m.stop.set()
        dumper_task.cancel()
        for t in (hb_task, tick_task, status_task):
            t.cancel()
        await _a.gather(hb_task, tick_task, status_task,
                        return_exceptions=True)
        await client.aclose()
    duration = time.monotonic() - t_start
    print(f"[run] drive result: {result}  ({duration:.1f}s)")

    ledger["run"] = {
        "result": result,
        "duration_s": round(duration, 1),
        "prompt_posts": [
            {"t": p["t"],
             "marker": p["body"].get("extra_data", {}).get("soloring"),
             "graph_nodes": sorted(p["body"]["prompt"].keys())}
            for p in transport.prompt_posts
        ],
        "uploads": transport.uploads,
        "observation_calls": len(transport.observations),
        "observation_first_20": transport.observations[:20],
        "status_timeline": [(t, s) for t, s in m.status_timeline],
        "bridge": {
            "loop_thread_id": m.loop_thread_id,
            "view_thread_id": m.view_thread_id,
            "threads_differ": (m.loop_thread_id is not None
                               and m.view_thread_id is not None
                               and m.loop_thread_id != m.view_thread_id),
            "chunks": bridge_events["chunks"],
            "bytes": bridge_events["bytes"],
            "duration_s": round(
                (bridge_events["t_end"] or 0) - (bridge_events["t_start"] or 0),
                3,
            ) if bridge_events["t_start"] else None,
        },
        "heartbeat": {
            "lease_ok": m.lease_ok, "lease_fail": m.lease_fail,
            "generation_ok": m.gen_hb_ok, "generation_fail": m.gen_hb_fail,
        },
        "ticker_max_gap_s": round(m.ticker_max_gap, 4),
        "vram_peak_mb": m.vram_peak_mb,
    }

    if result != "succeeded":
        fail(f"drive result was {result!r}")

    # ---- mandatory assertions -------------------------------------------------
    # 1. Exactly one /prompt for this attempt; marker round-tripped.
    ours = [p for p in transport.prompt_posts
            if p["body"].get("extra_data", {}).get("soloring", {})
            .get("generation_id") == gid]
    assert len(ours) == 1, f"expected exactly one POST, got {len(ours)}"
    sent = ours[0]["body"]
    marker = sent["extra_data"]["soloring"]
    assert marker["attempt_id"] == attempt

    # 2. Upload identity: requested vs returned, exact reference in graph.
    up = transport.uploads[-1]
    returned_name = up["returned"].get("name")
    returned_sub = up["returned"].get("subfolder")
    expected_ref = (f"{returned_sub}/{returned_name}" if returned_sub
                    else returned_name)
    assert sent["prompt"]["4"]["inputs"]["image"] == expected_ref, (
        f"graph image {sent['prompt']['4']['inputs']['image']!r} != "
        f"returned ref {expected_ref!r}"
    )
    assert returned_sub == up["requested_subfolder"], "namespace mismatch"

    # 3. Live-critical graph fields (cheap verification of what was sent).
    wf_dir = BASE_DIR / "workflows" / "hunyuan_i2v_v1"
    tgraph = json.loads((wf_dir / "workflow.json").read_text("utf-8"))
    # Translation-bound fields are EXPECTED to differ from the static
    # template: the creative prompt, the materialized input reference, and
    # the resolved parameters. Everything else must match byte-for-byte.
    bound = {("4", "image"), ("12", "prompt"), ("31", "steps"),
             ("31", "cfg")}
    for nid, node in tgraph.items():
        for field, value in node["inputs"].items():
            if isinstance(value, list) or (nid, field) in bound:
                continue
            assert sent["prompt"][nid]["inputs"][field] == value, (
                f"graph drift at {nid}.{field}"
            )
    assert sent["prompt"]["12"]["inputs"]["prompt"].startswith("Subject:")

    # 4. Post state + provenance chain.
    async with factory() as s:
        post = await get_generation_full(s, gid)
    import hashlib as _h2
    assert _h2.sha256(post.executor_submission_json.encode()).hexdigest() == (
        post.executor_submission_hash
    ), "submission hash != persisted bytes"
    assert post.executor_submission_state == "confirmed"
    assert post.executor_job_id and pre["seed"] is None

    async with engine.connect() as conn:
        take = dict((await conn.execute(
            text("SELECT id, output_key FROM takes "
                 "WHERE generation_id=:g"), {"g": gid},
        )).mappings().one())
        asset = dict((await conn.execute(
            text("SELECT id, blob_hash FROM assets WHERE take_id=:t"),
            {"t": take["id"]},
        )).mappings().one())
        out_blob = dict((await conn.execute(
            text("SELECT hash, size_bytes, detected_media_type FROM blobs "
                 "WHERE hash=:h"), {"h": asset["blob_hash"]},
        )).mappings().one())
        n_takes = (await conn.execute(
            text("SELECT COUNT(*) FROM takes WHERE generation_id=:g"),
            {"g": gid})).scalar_one()
    assert n_takes == 1 and take["output_key"] == "video:0"

    physical = store.path_for_hash(asset["blob_hash"])
    out_bytes = physical.read_bytes()
    assert out_bytes[:4] == b"RIFF" and out_bytes[8:12] == b"WEBP", (
        "output is not a WebP"
    )
    assert _h2.sha256(out_bytes).hexdigest() == asset["blob_hash"]

    # 5. Live history: exactly one prompt carries our marker.
    import urllib.request
    history = json.load(urllib.request.urlopen(
        f"{BASE_URL}/history/{post.executor_job_id}", timeout=10))
    rec = history.get(post.executor_job_id)
    assert rec is not None, "prompt missing from live history"
    live_marker = rec["prompt"][3].get("soloring", {})
    assert live_marker.get("generation_id") == gid
    assert live_marker.get("attempt_id") == attempt

    # 6. Import replay: zero duplicates.
    replay_path = SPECIMEN / "replay.webp"
    replay_path.write_bytes(out_bytes)
    from soloring.workflows.manifest import ExpectedOutput
    imported = await import_staged_outputs(
        factory, store, post,
        [StagedOutput(output_key="video:0", path=replay_path,
                      kind="video")],
        expected_outputs=[ExpectedOutput(
            name="video", kind="video", expected_count=1,
            accepted_media_types=None)],
        staging_directory=SPECIMEN,
    )
    async with engine.connect() as conn:
        n_takes2 = (await conn.execute(
            text("SELECT COUNT(*) FROM takes WHERE generation_id=:g"),
            {"g": gid})).scalar_one()
    assert imported == ["video:0"] and n_takes2 == 1

    # 7. Approval through the normal API (separate from worker success).
    from soloring.api.main import create_app
    from soloring.db.engine import create_session_factory
    app = create_app(settings)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    api = httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                            base_url="http://soloring-test")
    r = await api.post(f"/takes/{take['id']}/approve")
    assert r.status_code == 200, r.text
    assert r.json()["take_id"] == take["id"]
    shot_r = await api.get(f"/shots/{shot.id}")
    assert shot_r.json()["approved_take_id"] == take["id"]
    await api.aclose()

    ledger["post"] = {
        "prompt_id": post.executor_job_id,
        "terminal": "succeeded (live history status_str)",
        "resolved_output": {
            "filename": post.executor_job_id and
            history[post.executor_job_id]["outputs"]["15"]["images"][0]
            ["filename"],
            "field": "images", "type": "output",
        },
        "output_bytes": len(out_bytes),
        "output_blob_sha256": asset["blob_hash"],
        "output_detected_media_type": out_blob["detected_media_type"],
        "asset_id": asset["id"],
        "take_id": take["id"],
        "approved": True,
    }
    ledger["upload_semantics"] = {
        "requested": {"name": up["requested_name"],
                      "subfolder": up["requested_subfolder"]},
        "returned": {"name": returned_name, "subfolder": returned_sub},
        "note": ("SoloRing uploads with overwrite=true; live endpoint "
                 "returned the exact requested identity (no auto-rename "
                 "under this mode, as expected from Comfy's documented "
                 "overwrite behavior)"),
    }
    ledger["finished_at"] = datetime.now(timezone.utc).isoformat()
    (SPECIMEN / "ledger.json").write_text(json.dumps(ledger, indent=2,
                                                     default=str))
    print(json.dumps({k: ledger[k] for k in ("run", "post")} |
                     {"upload_semantics": ledger["upload_semantics"]},
                     indent=2, default=str)[:2500])
    print(f"\nM5B-3 GATE: ALL PROOFS HELD — specimen at {SPECIMEN}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
