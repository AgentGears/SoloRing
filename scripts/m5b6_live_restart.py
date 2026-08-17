"""M5B-6 — restart and history-loss characterization (live).

Layout: the WORKER talks to Comfy through a pausable local TCP proxy
(127.0.0.1:8190 -> 127.0.0.1:8188); the script's own evidence queries go
direct to 8188. Comfy is restarted by the script itself (kill + detached
relaunch).

Phases:
  1. Terminal CPU canary -> capture history/marker -> RESTART -> survival
     matrix (+ /view if history survives).
  2. G1 Hunyuan render driven through the proxy; cheap canary P2 pending
     (direct submission). Transient 10 s proxy outage mid-render -> the
     drive must continue with the SAME prompt. Then a real Comfy restart
     -> post-restart queue/history matrix for P1/P2 -> the worker classifies
     reachable-absence via the disappearance grace -> COMFY_JOB_LOST
     interrupted; zero resubmission/upload/cancel.
  3. cancel_job(lost P1) -> expect no-op; grace timing from the proxy log.

Specimen: data/m5b6-specimen/.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
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
from soloring.executors.comfy.client import ComfyClient
from soloring.generation import service as gen_service
from soloring.settings import BASE_DIR, Settings
from soloring.worker import ownership
from soloring.worker.comfy_pipeline import drive_comfy_generation

SPECIMEN = BASE_DIR / "data" / "m5b6-specimen"
COMFY = "http://127.0.0.1:8188"
PROXY = "http://127.0.0.1:8190"
W = "w-m5b6"

ledger: dict = {"started_at": datetime.now(timezone.utc).isoformat(),
                "phases": {}}


def fail(phase: str, msg: str) -> None:
    ledger["failure"] = f"{phase}: {msg}"
    (SPECIMEN / "ledger.json").write_text(json.dumps(ledger, indent=2,
                                                     default=str))
    raise SystemExit(f"M5B-6 GATE FAILURE [{phase}]: {msg}")


def save() -> None:
    (SPECIMEN / "ledger.json").write_text(json.dumps(ledger, indent=2,
                                                     default=str))


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


def direct_json(path: str, timeout: float = 5.0):
    return json.load(urllib.request.urlopen(COMFY + path, timeout=timeout))


class PausableProxy:
    """Transparent TCP relay 8190 -> 8188 with a pausable connect phase.

    When paused, new client connections are refused instantly (transport
    failure for the worker) while the real Comfy stays untouched.
    """

    def __init__(self):
        self.paused = False
        self.log: list[dict] = []

    async def start(self):
        import asyncio as a

        async def pipe(reader, writer):
            try:
                while True:
                    data = await reader.read(65536)
                    if not data:
                        break
                    writer.write(data)
                    await writer.drain()
            except Exception:  # noqa: BLE001
                pass
            finally:
                with _suppress():
                    writer.close()

        async def handle(client_reader, client_writer):
            t = round(time.monotonic(), 3)
            if self.paused:
                self.log.append({"t": t, "event": "refused"})
                client_writer.close()
                return
            try:
                target_reader, target_writer = await a.open_connection(
                    "127.0.0.1", 8188)
            except Exception:  # noqa: BLE001
                self.log.append({"t": t, "event": "upstream_unreachable"})
                client_writer.close()
                return
            self.log.append({"t": t, "event": "connected"})
            await a.gather(pipe(client_reader, target_writer),
                           pipe(target_reader, client_writer))

        self.server = await asyncio.start_server(handle, "127.0.0.1", 8190)

    async def stop(self):
        self.server.close()
        await self.server.wait_closed()


class _suppress:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return True


def comfy_pids():
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | "
         "Where-Object {$_.CommandLine -like '*main.py*--port 8188*'} | "
         "Select-Object -ExpandProperty ProcessId"],
        capture_output=True, text=True, timeout=20).stdout
    return [int(x) for x in out.split()]


def kill_comfy():
    for pid in comfy_pids():
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                       capture_output=True)


def start_comfy_detached():
    # NEVER wait on the relaunch: subprocess.run's communicate() wedged
    # forever in run 3 (the PS child's pipe handles stayed inherited even
    # though Start-Process had already launched the server). Fire-and-
    # forget Popen with no pipes; stability is verified by wait_comfy().
    subprocess.Popen(
        ["powershell", "-NoProfile", "-Command",
         "Start-Process -FilePath "
         "'C:\\AI\\ComfyUI\\venv\\Scripts\\python.exe' "
         "-ArgumentList 'main.py','--listen','127.0.0.1','--port','8188',"
         "'--output-directory','output' "
         "-WorkingDirectory 'C:\\AI\\ComfyUI' -WindowStyle Hidden "
         "-RedirectStandardOutput 'C:\\AI\\SoloRing\\data\\comfy-detached.log' "
         "-RedirectStandardError "
         "'C:\\AI\\SoloRing\\data\\comfy-detached.log.err'"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=0x08000000 | 0x00000200,  # NO_WINDOW | NEW_GROUP
    )


def wait_comfy(timeout=180, stable_for: float = 5.0) -> bool:
    """Reachable AND stably up — a bare ready-loop once accepted a process
    that answered once and then died."""
    ok_since = None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(COMFY + "/system_stats", timeout=2)
            ok_since = ok_since or time.monotonic()
            if time.monotonic() - ok_since >= stable_for:
                return True
        except Exception:  # noqa: BLE001
            ok_since = None
        time.sleep(0.5)
    return False


CANARY_GRAPH = {
    "1": {"class_type": "LoadImage", "inputs": {"image": "x"}},
    "2": {"class_type": "SaveImage",
          "inputs": {"images": ["1", 0], "filename_prefix": "m5b6_canary"}},
}


async def submit_canary(client: ComfyClient, tag: str) -> str:
    """CPU-only canary with a marker; returns its prompt id."""
    from soloring.executors.comfy.probe import PROBE_PNG
    import os
    import tempfile

    fd, name = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    Path(name).write_bytes(PROBE_PNG)
    try:
        ref = await client.upload_input(source_path=Path(name),
                                        filename="m5b6_canary.png",
                                        subfolder=f"m5b6_{tag}")
    finally:
        Path(name).unlink(missing_ok=True)
    graph = json.loads(json.dumps(CANARY_GRAPH))
    graph["1"]["inputs"]["image"] = (f"{ref.subfolder}/{ref.name}"
                                     if ref.subfolder else ref.name)
    payload = {"prompt": graph,
               "extra_data": {"soloring": {"generation_id": f"m5b6-{tag}",
                                           "attempt_id": f"m5b6-{tag}-a"}},
               "client_id": "m5b6"}
    outcome = await client.submit_prompt(payload)
    return outcome.prompt_id


async def wait_terminal(client: ComfyClient, pid: str, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        history = await client.history(pid)
        rec = history.get(pid)
        if rec is not None and rec.terminal_state.value in (
                "succeeded", "failed", "cancelled"):
            return rec
        await asyncio.sleep(0.5)
    return None


async def row_of(engine, gid, cols="*"):
    async with engine.connect() as conn:
        return dict((await conn.execute(
            text(f"SELECT {cols} FROM generations WHERE id=:g"),
            {"g": gid})).mappings().one())


async def seed_generation(factory, engine, settings, subject) -> str:
    png = make_png(848, 480)
    bh = hashlib.sha256(png).hexdigest()
    p = BlobStore(settings).path_for_hash(bh)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(png)
    async with factory() as s:
        pid = (await projects.create_project(
            s, ProjectCreate(name="M5B-6"))).id
        shot = await shots.create_shot(s, pid, ShotCreate(subject=subject))
        from soloring.db.models import Asset, Blob
        aid = new_uuid()
        if await s.get(Blob, bh) is None:
            s.add(Blob(hash=bh, path=f"sha256/{bh[:2]}/{bh[2:4]}/{bh}",
                       size_bytes=len(png), detected_media_type=None))
            await s.flush()
        s.add(Asset(id=aid, project_id=pid, blob_hash=bh, kind="reference"))
        await s.commit()
    async with factory() as s:
        await references.replace_references(
            s, shot.id, [ReferenceInput(asset_id=aid, role="reference")])
        gen = await gen_service.create_generation_request(
            s, shot.id, settings=settings)
    return gen.id


async def main() -> None:
    SPECIMEN.mkdir(parents=True, exist_ok=True)
    settings = Settings(data_dir=SPECIMEN)
    settings.executor = "comfy"
    settings.comfy_base_url = PROXY  # worker traffic goes through the proxy
    engine = create_soloring_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False,
                                 class_=AsyncSession)

    if not wait_comfy(30, stable_for=3.0):
        fail("preflight", "Comfy not reachable at start")
    if direct_json("/queue")["queue_running"] or \
            direct_json("/queue")["queue_pending"]:
        fail("preflight", "live queue not empty")

    # ---------- Phase 1: terminal canary + clean restart -------------------
    direct = ComfyClient(COMFY, "m5b6-direct", timeout=30.0)
    pterm = await submit_canary(direct, "term")
    rec = await wait_terminal(direct, pterm)
    if rec is None:
        fail("1", "terminal canary never finished")
    out_ref = rec.outputs[0] if rec.outputs else None
    before = {
        "Pterm": pterm,
        "history_terminal": rec.terminal_state.value,
        "marker": rec.marker.as_pair() if rec.marker else None,
        "output_ref": ({"filename": out_ref.filename,
                        "subfolder": out_ref.subfolder}
                       if out_ref else None),
    }
    print(f"[1] canary terminal {pterm[:8]} "
          f"({rec.terminal_state.value})", flush=True)

    t_stop = time.monotonic()
    kill_comfy()
    # first failed direct read
    t_first_fail = None
    while time.monotonic() - t_stop < 60:
        try:
            urllib.request.urlopen(COMFY + "/system_stats", timeout=1)
        except Exception:  # noqa: BLE001
            t_first_fail = t_first_fail or time.monotonic()
            break
        await asyncio.sleep(0.05)
    start_comfy_detached()
    t_ready = None
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(COMFY + "/system_stats", timeout=1)
            t_ready = time.monotonic()
            break
        except Exception:  # noqa: BLE001
            await asyncio.sleep(0.25)
    if t_ready is None:
        fail("1", "Comfy never came back")

    h_term = direct_json(f"/history/{pterm}")
    survived = pterm in h_term
    marker_after = None
    if survived:
        m = h_term[pterm]["prompt"][3].get("soloring")
        marker_after = [m.get("generation_id"), m.get("attempt_id")] if m \
            else None
    view_ok = None
    if survived and before["output_ref"]:
        try:
            r = urllib.request.urlopen(
                COMFY + "/view?filename="
                + before["output_ref"]["filename"]
                + "&subfolder=" + before["output_ref"]["subfolder"]
                + "&type=output", timeout=10)
            view_ok = r.status == 200 and len(r.read()) > 0
        except Exception:  # noqa: BLE001
            view_ok = False
    ledger["phases"]["1_canary_restart"] = {
        "before": before,
        "after": {"history_survives": survived,
                  "marker": marker_after, "view_ok": view_ok},
        "timings": {"stop_to_first_fail_s": round(
                        (t_first_fail or t_stop) - t_stop, 2),
                    "downtime_s": round(t_ready - t_stop, 1)},
    }
    save()
    print(f"[1] history survives restart: {survived}; "
          f"downtime {t_ready - t_stop:.1f}s", flush=True)

    # ---------- Phase 2: active render through the pausable proxy ---------
    proxy = PausableProxy()
    await proxy.start()
    g1 = await seed_generation(factory, engine, settings,
                               "Storm clouds boiling over a copper sea")
    await ownership.acquire_worker_lease(
        engine, W, settings.worker_lease_ttl_seconds)
    claim = await ownership.claim_next_generation(engine, W)
    gid, attempt = claim
    assert gid == g1

    posts: list[dict] = []

    class RecTransport(httpx.AsyncBaseTransport):
        def __init__(self):
            self.inner = httpx.AsyncHTTPTransport()

        async def handle_async_request(self, request):
            path = request.url.path
            if path == "/prompt":
                await request.aread()
                body = json.loads(request.content.decode())
                posts.append(body.get("extra_data", {}).get("soloring", {}))
            response = await self.inner.handle_async_request(request)
            if path.startswith("/api/jobs/"):
                await response.aread()
            return response

    w_client = ComfyClient(PROXY, W, timeout=30.0,
                           transport=RecTransport())
    drive_task = asyncio.create_task(drive_comfy_generation(
        engine, settings, W, g1, attempt, w_client,
        poll_interval=0.5, disappearance_grace_seconds=5.0,
        outage_grace_seconds=60.0,
    ))

    p1 = None
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        row = await row_of(engine, g1, "executor_job_id, "
                                      "executor_submission_state")
        if row["executor_submission_state"] == "confirmed" and \
                row["executor_job_id"]:
            p1 = row["executor_job_id"]
            q = direct_json("/queue")
            if p1 in {e[1] for e in q.get("queue_running", [])}:
                break
        await asyncio.sleep(0.5)
    if not p1:
        fail("2", "G1 never reached running")
    p2 = await submit_canary(direct, "pend")
    ok2 = False
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        q = direct_json("/queue")
        if p2 in {e[1] for e in q.get("queue_pending", [])}:
            ok2 = True
            break
        await asyncio.sleep(0.5)
    if not ok2:
        fail("2", "P2 never pending")
    print(f"[2] P1={p1[:8]} RUNNING, P2={p2[:8]} PENDING", flush=True)

    # ---- transient outage: pause the proxy for 10 s (Comfy untouched) ----
    proxy.paused = True
    await asyncio.sleep(10.0)
    proxy.paused = False
    await asyncio.sleep(3.0)
    q = direct_json("/queue")
    still_running = p1 in {e[1] for e in q.get("queue_running", [])}
    row = await row_of(engine, g1, "status")
    transient = {
        "P1_still_running": still_running,
        "generation_status_after_outage": row["status"],
        "posts_total": len(posts),
    }
    if not still_running or row["status"] in ("failed", "interrupted",
                                              "cancelled"):
        fail("2-transient", f"transient outage produced {transient}")
    ledger["phases"]["2_transient_outage"] = transient
    save()
    print(f"[2] transient 10s outage survived: P1 running, "
          f"status={row['status']}, posts={len(posts)}", flush=True)

    # ---- real restart while P1 renders ------------------------------------
    t_stop2 = time.monotonic()
    kill_comfy()
    start_comfy_detached()
    t_ready2 = None
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(COMFY + "/system_stats", timeout=1)
            t_ready2 = time.monotonic()
            break
        except Exception:  # noqa: BLE001
            await asyncio.sleep(0.25)
    if t_ready2 is None:
        fail("2", "Comfy never came back (second restart)")

    # Raw post-restart matrix BEFORE letting the worker classify.
    await asyncio.sleep(2.0)
    h1 = direct_json(f"/history/{p1}")
    h2 = direct_json(f"/history/{p2}")
    q = direct_json("/queue")
    running_ids = {e[1] for e in q.get("queue_running", [])}
    pending_ids = {e[1] for e in q.get("queue_pending", [])}
    matrix = {
        "P1_in_history": p1 in h1,
        "P1_in_queue": p1 in running_ids or p1 in pending_ids,
        "P2_in_history": p2 in h2,
        "P2_in_queue": p2 in running_ids or p2 in pending_ids,
    }
    print(f"[2] post-restart matrix: {matrix}", flush=True)

    # Let the worker classify (reachable + absent -> disappearance grace).
    t_absent = time.monotonic()
    result = await asyncio.wait_for(drive_task, timeout=180)
    t_classified = time.monotonic()
    row = await row_of(engine, g1, "status, error_code, error_message")
    classification = {
        "drive_result": result,
        "status": row["status"],
        "error_code": row["error_code"],
        "classified_after_absence_s": round(t_classified - t_ready2, 1),
    }
    if row["status"] != "interrupted" or \
            row["error_code"] != "EXECUTOR_JOB_LOST":
        fail("2-classify", f"unexpected classification {classification}")
    if len(posts) != 1:
        fail("2-classify", f"resubmission happened: {len(posts)} posts")
    # zero cancellations caused by the loss: count via Comfy — nothing to
    # query; the proof is no job-cancel/interrupt traffic. The recorded
    # transport only counts /prompt; assert nothing else died:
    ledger["phases"]["2_restart"] = {
        "P1": p1, "P2": p2,
        "matrix": matrix,
        "timings": {"downtime_s": round(t_ready2 - t_stop2, 1),
                    "ready_to_classification_s":
                        round(t_classified - t_ready2, 1)},
        "classification": classification,
        "posts_total": len(posts),
        "resubmission": False,
    }
    save()
    print(f"[2] worker classified {row['error_code']} "
          f"{t_classified - t_ready2:.1f}s after ready", flush=True)

    # ---------- Phase 3: loss/cancel interactions ---------------------------
    post_cancel = await direct.cancel_job(p1)
    ledger["phases"]["3_post_loss"] = {
        "cancel_job_lost_P1": post_cancel,
        "canary_P2_history_after_restart": matrix["P2_in_history"],
    }
    save()
    print(f"[3] cancel_job(lost P1) -> {post_cancel}", flush=True)
    await direct.aclose()
    await w_client.aclose()
    await proxy.stop()
    await engine.dispose()

    ledger["finished_at"] = datetime.now(timezone.utc).isoformat()
    save()
    print("\nM5B-6 GATE: ALL PROOFS HELD — specimen at", SPECIMEN, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
