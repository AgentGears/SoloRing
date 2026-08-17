"""M5B-5 — live cancellation characterization.

Phases (each asserts incrementally; specimen at data/m5b5-specimen/):
  B  pending collateral: G1 running + G2 pending; cancel G2 through the
     product path -> P2 removed, P1 untouched, deletes only P2.
  D  targeted matrix: with the TARGETED capability (M5B-5-proven atomic
     /api/jobs/{id}/cancel), cancel G1 mid-render -> successor G3/P4
     unaffected; repeat cancel(P1) -> no-op; unknown -> no-op.
  C  soft-cancel + worker death: G5 running under worker A (subprocess);
     user cancel -> soft selected durable -> A killed -> B adopts -> P5
     finishes remotely -> ZERO publication -> cancelled.
  E  terminal-before-cancel: G6 remotely terminal BEFORE the cancel request
     lands -> normal terminal wins -> published despite the cancel.
  F  endpoint envelope fixtures + capability conclusion JSON.

Exit 0 == the mandatory matrix held.
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
from soloring.worker.comfy_pipeline import drive_comfy_generation
from soloring.worker.comfy_submission import run_comfy_submission
from soloring.worker.recovery import reconcile_stale_generations

SPECIMEN = BASE_DIR / "data" / "m5b5-specimen"
BASE_URL = "http://127.0.0.1:8188"
W = "w-m5b5-main"
A_ID = "w-m5b5-A"
B_ID = "w-m5b5-B"

ledger: dict = {"started_at": datetime.now(timezone.utc).isoformat(),
                "phases": {}}


def fail(phase: str, msg: str) -> None:
    ledger["failure"] = f"{phase}: {msg}"
    (SPECIMEN / "ledger.json").write_text(json.dumps(ledger, indent=2,
                                                     default=str))
    raise SystemExit(f"M5B-5 GATE FAILURE [{phase}]: {msg}")


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
            + chunk(b"IHDR", width.to_bytes(4, "big") + height.to_bytes(4, "big")
                    + bytes((8, 2, 0, 0, 0)))
            + chunk(b"IDAT", zlib.compress(raw, 6))
            + chunk(b"IEND", b""))


def get_json(path: str):
    return json.load(urllib.request.urlopen(BASE_URL + path, timeout=10))


class RecTransport(httpx.AsyncBaseTransport):
    """Full client-boundary recorder for one worker's Comfy traffic."""

    def __init__(self, tag: str):
        self.tag = tag
        self.inner = httpx.AsyncHTTPTransport()
        self.prompt_posts: list[dict] = []
        self.upload_count = 0
        self.queue_deletes: list[str] = []
        self.job_cancels: list[dict] = []
        self.interrupts: list[dict] = []
        self.view_calls = 0
        self.global_history = 0

    async def handle_async_request(self, request: httpx.Request):
        path = request.url.path
        if path == "/prompt":
            await request.aread()
        response = await self.inner.handle_async_request(request)
        if path == "/prompt":
            body = json.loads(request.content.decode())
            self.prompt_posts.append({
                "marker": body.get("extra_data", {}).get("soloring", {}),
            })
        elif path == "/upload/image":
            self.upload_count += 1
        elif path == "/queue" and request.method == "POST":
            ids = json.loads(request.content.decode()).get("delete", [])
            self.queue_deletes.extend(ids)
        elif path.startswith("/api/jobs/") and path.endswith("/cancel"):
            pid = path[len("/api/jobs/"):-len("/cancel")]
            await response.aread()
            self.job_cancels.append(
                {"prompt_id": pid, "response": response.json()})
        elif path == "/interrupt":
            await request.aread()
            self.interrupts.append({"body": request.content.decode()[:200]})
        elif path == "/view":
            self.view_calls += 1
        elif path == "/history":
            self.global_history += 1
        return response


def client_for(tag: str) -> tuple[ComfyClient, RecTransport]:
    t = RecTransport(tag)
    return ComfyClient(BASE_URL, tag, timeout=600.0,
                       transport=t), t


async def wait_queue_state(prompt_id: str, want: str, timeout: float = 300):
    """want in {'running','pending','absent','terminal'} via live HTTP."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        q = get_json("/queue")
        running = {e[1] for e in q.get("queue_running", [])}
        pending = {e[1] for e in q.get("queue_pending", [])}
        if want == "running" and prompt_id in running:
            return True
        if want == "pending" and prompt_id in pending:
            return True
        if want == "absent" and prompt_id not in running | pending:
            h = get_json(f"/history/{prompt_id}")
            return prompt_id not in h or bool(h)
        if want == "terminal":
            h = get_json(f"/history/{prompt_id}")
            if prompt_id in h:
                return True
        await asyncio.sleep(1.0)
    return False


async def row_of(engine, gid: str, cols: str = "*"):
    async with engine.connect() as conn:
        return dict((await conn.execute(
            text(f"SELECT {cols} FROM generations WHERE id=:g"),
            {"g": gid})).mappings().one())


async def wait_job_id(engine, gid: str, timeout: float = 240) -> str | None:
    """Block until the submission task has durably minted executor_job_id."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        jid = (await row_of(engine, gid, "executor_job_id"))["executor_job_id"]
        if jid:
            return jid
        await asyncio.sleep(0.5)
    return None


async def seed_generation(factory, engine, settings, api, subject: str) -> str:
    png = make_png(848, 480)
    bh = hashlib.sha256(png).hexdigest()
    store = BlobStore(settings)
    p = store.path_for_hash(bh)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(png)
    async with factory() as s:
        pid = (await projects.create_project(
            s, ProjectCreate(name="M5B-5"))).id
        shot = await shots.create_shot(s, pid, ShotCreate(subject=subject))
        from soloring.db.models import Asset, Blob
        aid = new_uuid()
        if await s.get(Blob, bh) is None:
            s.add(Blob(hash=bh,
                       path=f"sha256/{bh[:2]}/{bh[2:4]}/{bh}",
                       size_bytes=len(png), detected_media_type="image/png"))
            await s.flush()
        s.add(Asset(id=aid, project_id=pid, blob_hash=bh, kind="reference"))
        await s.commit()
    async with factory() as s:
        await references.replace_references(
            s, shot.id, [ReferenceInput(asset_id=aid, role="reference")],
        )
        gen = await gen_service.create_generation_request(
            s, shot.id, settings=settings,
        )
    return gen.id


async def main() -> None:
    import faulthandler

    faulthandler.dump_traceback_later(300, repeat=True)
    SPECIMEN.mkdir(parents=True, exist_ok=True)
    settings_t = Settings(data_dir=SPECIMEN)
    settings_t.executor = "comfy"
    settings_t.comfy_cancellation_mode = "targeted"
    settings_s = Settings(data_dir=SPECIMEN)
    settings_s.executor = "comfy"  # soft_only default

    engine = create_soloring_engine(settings_t)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False,
                                 class_=AsyncSession)

    app = create_app(settings_t)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    api = httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                            base_url="http://soloring-test")

    q0 = get_json("/queue")
    if q0.get("queue_running") or q0.get("queue_pending"):
        fail("preflight", "live queue not empty — drain unrelated prompts "
                          "before the gate run")
    g1 = await seed_generation(factory, engine, settings_t, api,
                               "Molten glass sculpture rotating over black")
    g2 = await seed_generation(factory, engine, settings_t, api,
                               "Paper crane drifting down a stairwell")
    g3 = await seed_generation(factory, engine, settings_t, api,
                               "Aurora over a frozen lake, slow pan")
    print(f"[setup] G1={g1[:8]} G2={g2[:8]} G3={g3[:8]}", flush=True)

    r_acquire = await ownership.acquire_worker_lease(
        engine, W, settings_t.worker_lease_ttl_seconds)
    assert r_acquire in (
        ownership.LeaseAcquisitionResult.ACQUIRED_NEW,
        ownership.LeaseAcquisitionResult.REFRESHED_SELF,
        ownership.LeaseAcquisitionResult.TAKEN_OVER,  # stale prior test run
    )
    w_client, w_rec = client_for(W)

    # ================= PHASE B: pending collateral =========================
    c1, a1 = await ownership.claim_next_generation(engine, W)
    c2, a2 = await ownership.claim_next_generation(engine, W)
    assert c1 == g1 and c2 == g2, (c1, c2)

    cap_t = None  # derive from settings_t (targeted)
    t_g1 = asyncio.create_task(drive_comfy_generation(
        engine, settings_t, W, g1, a1, w_client, poll_interval=1.0))
    # Deterministic ordering: G1's prompt must be RUNNING before G2 submits,
    # so P2 is guaranteed pending behind P1 (concurrent task starts race).
    p1 = await wait_job_id(engine, g1)
    if not p1:
        fail("B", "G1 never minted a prompt id")
    ok = await wait_queue_state(p1, "running", timeout=240)
    if not ok:
        fail("B", "P1 never reached running")
    t_g2 = asyncio.create_task(drive_comfy_generation(
        engine, settings_t, W, g2, a2, w_client, poll_interval=1.0))
    p2 = await wait_job_id(engine, g2)
    if not p2:
        fail("B", "G2 never minted a prompt id")
    ok2 = await wait_queue_state(p2, "pending", timeout=120)
    if not ok2:
        fail("B", f"P2 never pending (running={ok})")
    print(f"[B] P1={p1[:8]} RUNNING, P2={p2[:8]} PENDING", flush=True)

    r = await api.post(f"/generations/{g2}/cancel")
    assert r.status_code == 200 and r.json()["cancel_requested"] is True
    g2_result = await asyncio.wait_for(t_g2, timeout=120)
    if g2_result != "cancelled":
        fail("B", f"G2 result {g2_result!r}")
    q = get_json("/queue")
    running_ids = {e[1] for e in q.get("queue_running", [])}
    pending_ids = {e[1] for e in q.get("queue_pending", [])}
    assert p2 not in running_ids | pending_ids, "P2 not removed"
    assert p1 in running_ids, "P1 disturbed by the pending cancel!"
    assert w_rec.queue_deletes == [p2], w_rec.queue_deletes
    assert w_rec.job_cancels == [], w_rec.job_cancels
    assert w_rec.interrupts == []
    row2 = await row_of(engine, g2, "status, cancel_requested_at")
    assert row2["status"] == "cancelled" and row2["cancel_requested_at"]
    ledger["phases"]["B_pending_collateral"] = {
        "P1_running_untouched": p1 in running_ids,
        "P2_removed": True,
        "queue_deletes": w_rec.queue_deletes,
        "G2": "cancelled",
    }
    print("[B] PASSED: pending cancel named exactly P2; P1 untouched",
          flush=True)
    (SPECIMEN / "ledger.json").write_text(json.dumps(
        ledger, indent=2, default=str))

    # ============ PHASE D: targeted running-cancel + collateral ============
    c3, a3 = await ownership.claim_next_generation(engine, W)
    assert c3 == g3
    t_g3 = asyncio.create_task(drive_comfy_generation(
        engine, settings_t, W, g3, a3, w_client, poll_interval=1.0))
    p3 = p1  # G1's prompt is the running job to hard-cancel
    p4 = None
    p4 = await wait_job_id(engine, g3)
    if p4:
        ok4p = await wait_queue_state(p4, "pending", timeout=120)
        p4 = p4 if ok4p else None
    if not p4:
        fail("D", "G3 never reached pending")
    print(f"[D] P3(=P1)={p3[:8]} RUNNING, P4={p4[:8]} PENDING", flush=True)

    r = await api.post(f"/generations/{g1}/cancel")
    assert r.status_code == 200 and r.json()["cancel_requested"] is True
    g1_result = await asyncio.wait_for(t_g1, timeout=120)
    if g1_result != "cancelled":
        fail("D", f"G1 result {g1_result!r}")
    # The atomic interrupt lands at the next step boundary (~11 s for this
    # model); the history entry appears when the job actually stops.
    deadline = time.monotonic() + 60
    h3 = {}
    while time.monotonic() < deadline:
        h3 = get_json(f"/history/{p3}")
        if p3 in h3:
            break
        await asyncio.sleep(1.0)
    assert p3 in h3, "cancelled P3 never reached history"
    # P4 promoted to running and undisturbed:
    ok4 = await wait_queue_state(p4, "running", timeout=120)
    if not ok4:
        fail("D", "P4 never started after P3 cancel")

    # repeat cancel(P3) while P4 is CURRENT: must be a no-op, P4 unaffected
    repeat = await w_client.cancel_job(p3)
    assert repeat is False, f"repeat cancel(P3) returned {repeat}"
    unknown = await w_client.cancel_job("00000000-0000-0000-0000-000000000000")
    assert unknown is False
    q = get_json("/queue")
    running_ids = {e[1] for e in q.get("queue_running", [])}
    assert p4 in running_ids, "P4 fell off after repeat cancel(P3)!"

    g3_result = await asyncio.wait_for(t_g3, timeout=900)
    assert g3_result == "succeeded", g3_result
    takes3 = (await row_of_count(engine, g3))
    assert takes3 == 1
    jc = [c for c in w_rec.job_cancels]
    assert jc == [
        {"prompt_id": p3, "response": {"cancelled": True}},
        {"prompt_id": p3, "response": {"cancelled": False}},
        {"prompt_id": "00000000-0000-0000-0000-000000000000",
         "response": {"cancelled": False}},
    ], jc
    assert w_rec.interrupts == []
    ledger["phases"]["D_targeted"] = {
        "cancel_P3_response": {"cancelled": True},
        "P3_history_terminal": h3[p3]["status"]["status_str"],
        "P4_promoted_unaffected": True,
        "repeat_cancel_P3": False,
        "unknown_cancel": False,
        "job_cancel_calls": jc,
        "G1": "cancelled", "G3": "succeeded",
    }
    print("[D] PASSED: targeted cancel stopped exactly P3; P4 unaffected; "
          "repeat+unknown are no-ops", flush=True)

    # ============ PHASE C: soft cancel + worker death (G5) =================
    g5 = await seed_generation(factory, engine, settings_s, api,
                               "Candle flame blooming into a paper flower")
    # W's lease must go stale so A can take it naturally.
    print("[C] letting W's lease go stale for worker A…", flush=True)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        r_ = await ownership.acquire_worker_lease(
            engine, A_ID, settings_s.worker_lease_ttl_seconds)
        if r_ is ownership.LeaseAcquisitionResult.TAKEN_OVER:
            break
        await asyncio.sleep(2.0)
    else:
        fail("C", "A never took over the lease")

    a_proc = subprocess.Popen(
        [str(BASE_DIR / ".venv" / "Scripts" / "python.exe"), "-u",
         str(BASE_DIR / "scripts" / "m5b4_worker_a.py"),
         str(SPECIMEN), A_ID, BASE_URL],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    p5 = None
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        row = await row_of(engine, g5, "executor_submission_state, "
                                       "executor_job_id, status, worker_id")
        if row["executor_submission_state"] == "confirmed" and row["executor_job_id"]:
            p5 = row["executor_job_id"]
            if await wait_queue_state(p5, "running", timeout=5):
                break
        await asyncio.sleep(1.0)
    if not p5:
        a_proc.kill()
        fail("C", "A never got G5 running")
    print(f"[C] P5={p5[:8]} running under A", flush=True)

    r = await api.post(f"/generations/{g5}/cancel")
    assert r.status_code == 200 and r.json()["cancel_requested"] is True
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        row = await row_of(engine, g5, "soft_cancel_selected_at")
        if row["soft_cancel_selected_at"]:
            break
        await asyncio.sleep(0.5)
    else:
        fail("C", "soft cancel never selected durably")
    print("[C] soft_cancel_selected_at durable — killing A", flush=True)

    subprocess.run(["taskkill", "/F", "/T", "/PID", str(a_proc.pid)],
                   capture_output=True)
    a_proc.wait(timeout=15)
    t_death = time.monotonic()

    deadline = time.monotonic() + settings_s.worker_lease_ttl_seconds + 120
    taken = None
    while time.monotonic() < deadline:
        taken = await ownership.acquire_worker_lease(
            engine, B_ID, settings_s.worker_lease_ttl_seconds)
        if taken is ownership.LeaseAcquisitionResult.TAKEN_OVER:
            break
        await asyncio.sleep(2.0)
    if taken is not ownership.LeaseAcquisitionResult.TAKEN_OVER:
        fail("C", f"B never took over ({taken})")

    b_client, b_rec = client_for(B_ID)
    acted = await reconcile_stale_generations(
        engine, B_ID, settings_s, comfy_client=b_client,
    )
    await b_client.aclose()
    row5 = await row_of(engine, g5, "status, worker_id, "
                                    "soft_cancel_selected_at")
    if row5["status"] != "cancelled":
        fail("C", f"G5 status {row5['status']!r} (acted={acted})")
    takes5 = await row_of_count(engine, g5)
    if takes5 != 0:
        fail("C", f"soft-cancelled G5 published {takes5} takes")
    if (b_rec.view_calls or b_rec.job_cancels or b_rec.queue_deletes
            or b_rec.interrupts):
        fail("C", f"B destructive calls: view={b_rec.view_calls} "
                  f"jobs={b_rec.job_cancels} del={b_rec.queue_deletes} "
                  f"intr={b_rec.interrupts}")
    h5 = get_json(f"/history/{p5}")
    ledger["phases"]["C_soft_death"] = {
        "P5_remote_terminal": h5[p5]["status"]["status_str"],
        "G5_status": row5["status"],
        "B_zero_destructive_calls": True,
        "B_view_calls": b_rec.view_calls,
        "takes_for_G5": takes5,
        "failover_s": round(time.monotonic() - t_death, 1),
    }
    print("[C] PASSED: soft cancel survived worker death; remote completion "
          "published nothing", flush=True)

    # ============ PHASE E: terminal-before-cancel (G6) =====================
    g6 = await seed_generation(factory, engine, settings_s, api,
                               "Ink drop unfurling in water, macro")
    c6, a6 = await ownership.claim_next_generation(engine, B_ID)
    assert c6 == g6
    e_client, e_rec = client_for("w-m5b5-E")
    # Submit only (no observe loop); wait for REMOTE terminal ourselves.
    from soloring.executors.comfy.translate import build_comfy_prompt
    from soloring.workflows.artifact_store import WorkflowArtifactStore
    from soloring.workflows.manifest import parse_manifest
    artifact_store = WorkflowArtifactStore(settings_s)
    row6 = await row_of(engine, g6)
    manifest = parse_manifest(
        (await artifact_store.get_manifest(row6["manifest_hash"]))
        .decode("utf-8"))
    tgraph = json.loads(
        (await artifact_store.get_template(row6["workflow_template_hash"]))
        .decode("utf-8"))
    # Materialize + translate exactly as the pipeline's not_started branch
    # does, then submit ONLY — the observe loop is deliberately withheld so
    # the cancel can land after remote terminal but before worker handling.
    from soloring.executors.comfy.input_materializer import (
        CapturedInput, HttpInputMaterializer,
    )
    from soloring.worker.comfy_pipeline import ClientUploader
    async with factory() as s:
        from soloring.generation.repository import list_generation_inputs
        input_rows = await list_generation_inputs(s, g6)
    captured = [CapturedInput(input_key=i.input_key, position=i.position,
                              asset_id=i.asset_id, blob_hash=i.blob_hash)
                for i in input_rows]
    mat = HttpInputMaterializer(ClientUploader(e_client),
                                BlobStore(settings_s).path_for_hash,
                                retry_convergent=False)
    outcome = await mat.materialize(generation_id=g6, attempt_id=a6,
                                    inputs=captured)
    payload = build_comfy_prompt(
        workflow_spec=json.loads(row6["workflow_spec_json"]),
        manifest=manifest, template=tgraph,
        materialized=outcome.materialized,
        generation_id=g6, attempt_id=a6, client_id=B_ID,
    )
    p6 = await run_comfy_submission(
        engine, settings_s, B_ID, g6, a6, payload.to_document(), e_client,
    )
    assert p6, "G6 submission failed"
    print(f"[E] P6={p6[:8]} submitted; waiting for REMOTE terminal…",
          flush=True)
    (SPECIMEN / "ledger.json").write_text(json.dumps(
        ledger, indent=2, default=str))
    ok = await wait_queue_state(p6, "terminal", timeout=900)
    if not ok:
        fail("E", "P6 never reached terminal history")
    # Cancel request arrives AFTER remote terminal, BEFORE worker observes.
    r = await api.post(f"/generations/{g6}/cancel")
    assert r.status_code == 200 and r.json()["cancel_requested"] is True
    result6 = await drive_comfy_generation(
        engine, settings_s, B_ID, g6, a6, e_client, poll_interval=1.0,
    )
    await e_client.aclose()
    if result6 != "succeeded":
        fail("E", f"terminal-before-cancel resolved {result6!r}")
    takes6 = await row_of_count(engine, g6)
    assert takes6 == 1
    ledger["phases"]["E_terminal_before_cancel"] = {
        "P6_remote_terminal_first": True,
        "cancel_request_after_terminal": True,
        "G6_result": result6, "takes": takes6,
    }
    print("[E] PASSED: terminal-before-cancel — normal terminal won",
          flush=True)
    (SPECIMEN / "ledger.json").write_text(json.dumps(
        ledger, indent=2, default=str))

    # ============ PHASE F: envelope fixtures + conclusion ==================
    fixtures = {}
    req = urllib.request.Request(
        BASE_URL + "/queue", data=json.dumps(
            {"delete": ["00000000-0000-0000-0000-000000000000"]}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        fixtures["delete_nonexistent"] = {
            "status": resp.status, "body": resp.read().decode()[:120]}
    h3s = h3[p3]["status"]["status_str"]
    fixtures["cancelled_history_status_str"] = h3s
    from soloring.executors.comfy.wire import normalize_history_response
    norm = normalize_history_response(h3)
    fixtures["cancelled_normalizes_to"] = norm[p3].terminal_state.value

    # The runtime-consumable v1 record (shared contract module — never
    # hand-edited): binds the promoted targeted capability to THIS exact
    # deployment fingerprint.
    from soloring.executors.comfy.capability_record import (
        build_capability_record,
    )
    record_doc = build_capability_record(
        comfyui_commit="b963f4ad210a42841ab23dfc28a84143a0cce227",
        comfyui_version="0.33.0",
        gguf_commit="6ea2651e7df66d7585f6ffee804b20e92fb38b8a",
        frontend="1.49.6",
        torch="2.13.0+cu130",
        observed_at=datetime.now(timezone.utc).isoformat(),
        runtime_policy={
            "outage_grace_s": 30, "disappearance_grace_s": 5,
            "observation_poll_s": 1.0,
        },
        extra_conclusions={
            "pending_cancel": "SUPPORTED — exact-id queue deletion",
            "soft_cancel": "durable; survived worker death with zero "
                           "publication",
            "retry_safety_proof": "repeat cancel(P3) while P4 current was a "
                                  "no-op and P4 completed (phase D)",
            "unsafe_interrupt_route": "/interrupt is check-then-act and is "
                                      "NOT used by the product path",
        },
    )
    (SPECIMEN / "comfy-fingerprint").mkdir(parents=True, exist_ok=True)
    (SPECIMEN / "comfy-fingerprint" / "capability_m5b5.json").write_text(
        json.dumps(record_doc, indent=2), encoding="utf-8")

    conclusion = {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "pending_cancel": {
            "supported": True, "targeting": "prompt_id",
            "mechanism": "POST /queue {delete:[P]} — SoloRing product path",
            "collateral_proof": "P1 untouched while P2 removed (phase B)",
            "retry_characterization": "repeat delete of already-gone id is a "
                                      "200 no-op",
        },
        "running_cancel": {
            "mode": "TARGETED",
            "endpoint": "POST /api/jobs/{prompt_id}/cancel",
            "atomicity": "server-side interrupt_if_running under queue mutex; "
                         "per-prompt interrupt-flag reset prevents "
                         "successor leakage (source-verified)",
            "idempotence": "finished/unknown ids → 200 {cancelled:false}",
            "retry_safety": "PROVEN live: repeat cancel(P3) while P4 current "
                            "was a no-op and P4 completed (phase D)",
            "unsafe_interrupt_route": "/interrupt is check-then-act and is "
                                      "NOT used by the product path",
            "runtime_setting": "SOLORING_COMFY_CANCELLATION_MODE "
                               "(default soft_only; targeted proven on this "
                               "deployment)",
        },
        "soft_cancel": {
            "live_proof": "phase C: durable selection survived worker death; "
                          "remote completion published zero Take/Asset; "
                          "zero /view, deletes, interrupts",
        },
        "safe_single_flight": "disabled by design (no mechanical interlock)",
    }
    ledger["phases"]["F_conclusion"] = conclusion
    ledger["phases"]["F_envelopes"] = fixtures
    (SPECIMEN / "capability_m5b5.json").write_text(
        json.dumps(conclusion, indent=2))
    ledger["finished_at"] = datetime.now(timezone.utc).isoformat()
    (SPECIMEN / "ledger.json").write_text(json.dumps(ledger, indent=2,
                                                     default=str))
    await api.aclose()
    await w_client.aclose()
    await engine.dispose()
    print("\nM5B-5 GATE: ALL PROOFS HELD — specimen at", SPECIMEN, flush=True)


async def row_of_count(engine, gid: str) -> int:
    async with engine.connect() as conn:
        return (await conn.execute(text(
            "SELECT COUNT(*) FROM takes WHERE generation_id=:g"),
            {"g": gid})).scalar_one()


if __name__ == "__main__":
    asyncio.run(main())
