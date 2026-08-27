"""M10E §29 — pinned live execution smoke (E-090..E-095 live layer).

Drives the REAL public path: HTTP POST /shots/{id}/generations against a
live uvicorn server over a fresh migrated DB, then the real worker
(``python -m soloring.worker``) against the certified pinned executor
(ComfyUI b963f4ad + ComfyUI-WanVideoWrapper 088128b2, port 8199), at
three-stream capacity (world + 2 entity depth chains), then an Exact
Rerun through POST /generations/{id}/rerun with the same worker.

Proves: fence subsumed (creation succeeds), exactly three derived
identities atomically queued, persisted spec v3 real-ID/no-pending, the
uploaded control frames concatenate to the EXACT retained Blob bytes and
bind at the certified nodes/fields through the frozen frame-chain
expansion, executor output retained as downstream evidence only, and
rerun reuses the exact same identities with zero rematerialization.

Usage:
    .venv/Scripts/python.exe scripts/m10e_live_smoke.py
(assumes the certified executor is already serving on 127.0.0.1:8199)
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "server"))

SMOKE_ROOT = REPO / "data" / "m10e-smoke"
DATA_DIR = SMOKE_ROOT / "data"
PKG_DIR = SMOKE_ROOT / "pkg3"
EVIDENCE = SMOKE_ROOT / "evidence"
SERVER_PORT = 8200
COMFY = "http://127.0.0.1:8199"
SERVER = f"http://127.0.0.1:{SERVER_PORT}"

SETPIECE_T = [-3000, 1650, 0]
STAGED_T = [[-3600, 1500, -400], [-2400, 1750, -800]]
EXTENTS = [600, 400, 300]
CAM = {"projection": "perspective", "focal_length_um": 50000,
       "sensor_width_um": 36000, "sensor_height_um": 20250,
       "keyframes": [{"time_ms": 0, "transform": {
           "translation_mm": [-3000, 1650, 4200],
           "rotation_udeg": [0, 0, 0]}}]}

ENV = {
    "SOLORING_DATA_DIR": str(DATA_DIR),
    "SOLORING_EXECUTOR": "comfy",
    "SOLORING_COMFY_BASE_URL": COMFY,
    "SOLORING_WORKFLOW_PACKAGE_DIR": str(PKG_DIR),
    # live model-byte verification roots (B2): the certified executor's
    # ComfyUI model directories
    "SOLORING_COMFY_MODEL_ROOT_DIFFUSION_MODELS": str(
        Path(r"C:/AI/M10R3-evidence/executor/comfy/models/"
             "diffusion_models")),
    "SOLORING_COMFY_MODEL_ROOT_CONTROLNET": str(
        Path(r"C:/AI/M10R3-evidence/executor/comfy/models/controlnet")),
    "SOLORING_COMFY_MODEL_ROOT_TEXT_ENCODERS": str(
        Path(r"C:/AI/M10R3-evidence/executor/comfy/models/text_encoders")),
    "SOLORING_COMFY_MODEL_ROOT_VAE": str(
        Path(r"C:/AI/M10R3-evidence/executor/comfy/models/vae")),
}

COMFY_DIR = Path(r"C:/AI/M10R3-evidence/executor/comfy")
COMFY_EXE = Path(r"C:/AI/ComfyUI/venv/Scripts/python.exe")
COMFY_PYDEPS = Path(r"C:/AI/M10R3-evidence/executor/pydeps")


def http(method: str, url: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"null")
        except Exception:
            return e.code, None


def comfy_get(url: str, timeout: float = 60) -> bytes:
    if not url.startswith("http"):
        url = COMFY + url
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def step(n: int, msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] step {n}: {msg}", flush=True)


def fetch_db(sql: str, params: dict | None = None):
    import sqlite3

    con = sqlite3.connect(DATA_DIR / "soloring.db")
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(sql, params or {}).fetchall()]
    con.close()
    return rows


async def seed_authority() -> dict:
    """Seed the schema-5 shot through the SERVICE layer (the same services
    the HTTP routes call); the GENERATION itself goes through real HTTP."""
    os.environ.update(ENV)
    from sqlalchemy import text

    from soloring.db.engine import create_soloring_engine
    from soloring.settings import Settings

    engine = create_soloring_engine(Settings())
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory = async_sessionmaker(bind=engine, expire_on_commit=False,
                                 class_=AsyncSession)
    from soloring.spatial import plans as plan_svc
    from soloring.spatial import revisions as wrev_svc
    from soloring.spatial import tracks as track_svc
    from soloring.spatial import transitions as trans_svc
    from soloring.spatial import worlds as world_svc

    import uuid

    pid = str(uuid.uuid4())
    async with factory() as s:
        async with s.begin():
            await s.execute(text(
                "INSERT INTO projects (id, name, created_at, updated_at) "
                "VALUES (:p, 'M10E Smoke', 't', 't')"), {"p": pid})

    async def _entity(kind: str, name: str):
        eid, rid = str(uuid.uuid4()), str(uuid.uuid4())
        async with factory() as s:
            async with s.begin():
                await s.execute(text(
                    "INSERT INTO creative_entities (id, project_id, kind, "
                    "name, created_at, updated_at) VALUES (:e, :p, :k, :n, "
                    "'t', 't')"),
                    {"e": eid, "p": pid, "k": kind, "n": name})
                await s.execute(text(
                    "INSERT INTO entity_revisions (id, entity_id, "
                    "revision_number, schema_version, spec_hash, "
                    "created_at) VALUES (:r, :e, 1, 1, :h, 't')"),
                    {"r": rid, "e": eid, "h": hashlib.sha256(
                        name.encode()).hexdigest()})
                await s.execute(text(
                    "INSERT INTO entity_approved_revisions (entity_id, "
                    "revision_id, approved_at) VALUES (:e, :r, 't')"),
                    {"e": eid, "r": rid})
        return eid, rid

    loc, locrev = await _entity("location", "lobby-loc")
    c1, _ = await _entity("character", "Hero")
    c2, _ = await _entity("character", "DeskClerk")

    world = await world_svc.create_world(
        factory(), pid, key="lobby", name="lobby", description=None,
        requirement="required", location_entity_id=loc)
    state = await world_svc.create_state(
        factory(), world["id"], location_entity_revision_id=locrev)
    for fkey, ext in (("origin", None), ("setpiece", EXTENTS)):
        f = await world_svc.create_frame(
            factory(), world["id"], key=fkey, name=fkey,
            parent_spatial_frame_id=None, bound_entity_id=None)
        await world_svc.put_state_frame(
            factory(), state["id"], f["id"], translation_mm=SETPIECE_T,
            rotation_udeg=[0, 0, 0], half_extents_mm=ext,
            bound_entity_revision_id=None)
    wrev = await wrev_svc.capture_revision(factory(), state["id"])
    await wrev_svc.approve_revision(
        factory(), state["id"], revision_id=wrev["id"],
        expected_approved_revision_id=None)

    shot = str(uuid.uuid4())
    seq, scene = str(uuid.uuid4()), str(uuid.uuid4())
    async with factory() as s:
        async with s.begin():
            await s.execute(text(
                "INSERT INTO sequences (id, project_id, position, title) "
                "VALUES (:q, :p, 1, 'S')"), {"q": seq, "p": pid})
            await s.execute(text(
                "INSERT INTO scenes (id, sequence_id, position, title) "
                "VALUES (:c, :q, 0, 'C')"), {"c": scene, "q": seq})
            await s.execute(text(
                "INSERT INTO shots (id, project_id, shot_number, subject, "
                "duration_ms, scene_id, scene_position, created_at, "
                "updated_at) VALUES (:s, :p, 1, 'm10e live smoke', 5000, "
                ":c, 0, 't', 't')"),
                {"s": shot, "p": pid, "c": scene})
            for i, eid in enumerate((loc, c1, c2)):
                await s.execute(text(
                    "INSERT INTO shot_entity_dependencies (shot_id, "
                    "entity_id, role, position) VALUES (:s, :e, 'cast', "
                    ":i)"), {"s": shot, "e": eid, "i": i})

    blocking = []
    for eid, t in ((c1, STAGED_T[0]), (c2, STAGED_T[1])):
        track = await track_svc.create_track(
            factory(), world["id"], entity_id=eid, requirement="optional")
        await trans_svc.create_transition(
            factory(), track["id"], anchor_type="sequence", anchor_id=seq,
            boundary="start", operation="set", translation_mm=t,
            rotation_udeg=[0, 0, 0])
        blocking.append({
            "spatial_track_id": track["id"],
            "screen_direction": "left_to_right",
            "keyframes": [{"time_ms": 0, "transform": {
                "translation_mm": t, "rotation_udeg": [0, 0, 0]}}],
        })
    await plan_svc.put_spatial_plan(
        factory(), shot, expected_plan_hash=None, plan_raw={
            "schema_version": 1, "spatial_world_id": world["id"],
            "camera": CAM, "blocking": blocking, "axis_constraint": None})
    await engine.dispose()
    return {"project": pid, "shot": shot}


def install_package() -> None:
    from soloring.domain.canonical import canonical_hash, canonical_json_str
    from soloring.spatial import production_package as prod

    PKG_DIR.mkdir(parents=True, exist_ok=True)
    docs = {
        "manifest.json": prod.production_manifest_v3(),
        "workflow.json": prod.production_template(),
        "realization-profile.json": prod.production_profile_v2(),
        "execution-model-fingerprint.json":
            prod.production_fingerprint_document(),
    }
    for name, doc in docs.items():
        (PKG_DIR / name).write_bytes(canonical_json_str(doc).encode())
    (PKG_DIR / "workflow-package.json").write_bytes(canonical_json_str({
        "schema_version": 3,
        "workflow_id": docs["manifest.json"]["workflow_id"],
        "workflow_version": 1,
        "manifest_hash": canonical_hash(docs["manifest.json"]),
        "workflow_template_hash": canonical_hash(docs["workflow.json"]),
        "realization_profile_hash": canonical_hash(
            docs["realization-profile.json"]),
        "execution_model_fingerprint_hash": canonical_hash(
            docs["execution-model-fingerprint.json"]),
    }).encode())


def wait_http(url: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                if r.status < 500:
                    return True
        except Exception:
            pass
        time.sleep(1.0)
    return False


def _stop(proc) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.send_signal(signal.CTRL_BREAK_EVENT)
        proc.wait(timeout=15)
    except Exception:
        proc.terminate()


def _prompt_graph(record: dict) -> dict:
    for item in record.get("prompt", []):
        if isinstance(item, dict) and "101" in item and "60" in item:
            return item
    raise SystemExit("history record carries no recognizable prompt graph")


def _download_input(ref: str) -> bytes:
    sub, name = ref.split("/", 1)
    url = (f"{COMFY}/view?filename={urllib.parse.quote(name)}"
           f"&subfolder={urllib.parse.quote(sub)}&type=input")
    return comfy_get(url, timeout=120)


def _launch_attested_executor() -> dict:
    """Launch the certified pinned executor and write the v4 deployment
    attestation into the smoke data dir (B2): the worker's live runtime
    closure then proves serving-process identity + ComfyUI/WanVideoWrapper
    commits + live model bytes against the CAPTURED fingerprint."""
    import subprocess as _sp

    def _rev(path: Path) -> str:
        out = _sp.run(["git", "-C", str(path), "rev-parse", "HEAD"],
                      capture_output=True, text=True, timeout=30)
        if out.returncode != 0:
            raise SystemExit(f"cannot read git rev of {path}")
        return out.stdout.strip()

    comfy_commit = _rev(COMFY_DIR)
    wrapper_commit = _rev(COMFY_DIR / "custom_nodes"
                          / "ComfyUI-WanVideoWrapper")
    # stop anything already on 8199
    _sp.run(["powershell", "-NoProfile", "-Command",
             "Get-NetTCPConnection -LocalPort 8199 -State Listen "
             "-ErrorAction SilentlyContinue | Select-Object -ExpandProperty "
             "OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force }"],
            capture_output=True, timeout=30)
    log = open(SMOKE_ROOT / "comfy-boot.log", "wb")
    proc = _sp.Popen(
        [str(COMFY_EXE), "main.py", "--listen", "127.0.0.1", "--port",
         "8199", "--disable-all-custom-nodes",
         "--whitelist-custom-nodes", "ComfyUI-WanVideoWrapper",
         "--output-directory", "output"],
        cwd=COMFY_DIR,
        env={**os.environ, "PYTHONPATH": str(COMFY_PYDEPS)},
        creationflags=_sp.CREATE_NEW_PROCESS_GROUP,
        stdout=log, stderr=_sp.STDOUT)
    if not wait_http(f"{COMFY}/system_stats", 120):
        raise SystemExit("certified executor did not become ready")
    out = _sp.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-NetTCPConnection -LocalPort 8199 -State Listen | "
         "Select-Object -First 1 -ExpandProperty OwningProcess"],
        capture_output=True, text=True, timeout=30)
    pid = int(out.stdout.strip())
    from soloring.executors.comfy.capability_record import (
        build_deployment_attestation,
        capture_process_start_fingerprint,
    )

    doc = build_deployment_attestation(
        comfyui_commit=comfy_commit,
        gguf_commit=wrapper_commit,  # the single whitelisted custom node
        launched_at=time.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        pid=pid,
        process_start_fingerprint=capture_process_start_fingerprint(pid),
        executor_origin="http://127.0.0.1:8199")
    att_dir = DATA_DIR / "comfy-fingerprint"
    att_dir.mkdir(parents=True, exist_ok=True)
    (att_dir / "deployment_attestation.json").write_text(
        json.dumps(doc, indent=2))
    return {"comfyui_commit": comfy_commit,
            "wanvideo_wrapper_commit": wrapper_commit, "pid": pid}


async def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    report: dict = {"started": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "comfy": COMFY, "server": SERVER}
    server = worker = None
    try:
        step(0, "launching the certified pinned executor (attested)")
        pins = _launch_attested_executor()
        report["executor_pins"] = pins
        print(f"        comfy {pins['comfyui_commit'][:12]}… wrapper "
              f"{pins['wanvideo_wrapper_commit'][:12]}… pid "
              f"{pins['pid']}")

        step(1, "installing the frozen schema-3 production package")
        install_package()

        step(2, "migrating a fresh live DB")
        for sub in ("blobs", "staging", "tmp"):
            (DATA_DIR / sub).mkdir(parents=True, exist_ok=True)
        migrated = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=REPO / "server", env={**os.environ, **ENV},
            capture_output=True, text=True)
        if migrated.returncode != 0:
            raise SystemExit(f"alembic failed: {migrated.stderr[-2000:]}")

        step(3, "seeding schema-5 authority through the service layer")
        seed = await seed_authority()
        report["seed"] = seed

        step(4, f"starting the live server on :{SERVER_PORT}")
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "soloring.api.main:app",
             "--port", str(SERVER_PORT)],
            cwd=REPO, env={**os.environ, **ENV},
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            stdout=open(SMOKE_ROOT / "server.log", "wb"),
            stderr=subprocess.STDOUT)
        if not wait_http(f"{SERVER}/projects", 60):
            raise SystemExit("server did not become ready")

        step(5, "POST /shots/{id}/generations (the public path)")
        status, gen = http("POST",
                           f"{SERVER}/shots/{seed['shot']}/generations")
        if status != 202:
            raise SystemExit(f"generation POST failed: {status} {gen}")
        gid = gen["id"]
        report["generation_id"] = gid
        print(f"        generation {gid} status={gen['status']}")

        step(6, "verifying queued derived identities (pre-worker)")
        sib = fetch_db(
            "SELECT input_key, position, artifact_role, "
            "derived_spatial_artifact_id, blob_hash FROM "
            "generation_derived_spatial_inputs WHERE generation_id = :g "
            "ORDER BY position", {"g": gid})
        assert len(sib) == 3, f"expected 3 siblings, got {len(sib)}"
        arts = fetch_db("SELECT id FROM derived_spatial_artifacts")
        assert len(arts) == 3
        row = fetch_db(
            "SELECT workflow_spec_json, workflow_spec_hash, status FROM "
            "generations WHERE id = :g", {"g": gid})[0]
        spec = json.loads(row["workflow_spec_json"])
        assert row["status"] == "queued"
        assert spec["schema_version"] == 3
        assert "pending:" not in row["workflow_spec_json"]
        assert spec["spatial_realization"]["structured_bindings"] == []
        from soloring.domain.canonical import canonical_hash

        assert canonical_hash(spec) == row["workflow_spec_hash"]
        report["spec_hash"] = row["workflow_spec_hash"]
        report["siblings"] = sib
        report["advisory_omissions"] = \
            spec["spatial_realization"]["advisory_omissions"]
        blob_bytes = {}
        from soloring.assets.blob_store import BlobStore
        from soloring.settings import Settings
        store = BlobStore(Settings())
        for r in sib:
            blob_bytes[r["blob_hash"]] = store.path_for_hash(
                r["blob_hash"]).read_bytes()

        step(7, "starting the real worker")
        worker = subprocess.Popen(
            [sys.executable, "-m", "soloring.worker"],
            cwd=REPO, env={**os.environ, **ENV},
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            stdout=open(SMOKE_ROOT / "worker.log", "wb"),
            stderr=subprocess.STDOUT)

        def _wait_terminal(generation_id: str, timeout: float) -> dict:
            deadline = time.monotonic() + timeout
            r = {}
            while time.monotonic() < deadline:
                r = fetch_db(
                    "SELECT status, executor_job_id, error_code, "
                    "error_message FROM generations WHERE id = :g",
                    {"g": generation_id})[0]
                if r["status"] in ("succeeded", "failed", "interrupted",
                                   "cancelled"):
                    return r
                time.sleep(3.0)
            raise SystemExit(
                f"generation {generation_id} did not reach terminal: {r}")

        step(8, "waiting for source execution to go terminal (GPU)")
        term = _wait_terminal(gid, 1800)
        report["source_terminal"] = term
        if term["status"] != "succeeded":
            raise SystemExit(f"source execution {term['status']}: "
                             f"{term['error_message']}")
        prompt_id = term["executor_job_id"]

        step(9, "verifying the certified control bindings + uploaded bytes")
        history = json.loads(comfy_get(f"/history/{prompt_id}", 30))
        record = history.get(prompt_id)
        assert record is not None, "prompt history vanished"
        graph = _prompt_graph(record)
        frame_sets = {}
        for node, key in (("101", "world_depth"), ("111", "entity_depth_1"),
                          ("121", "entity_depth_2")):
            link = graph[node]["inputs"]["control_images"]
            assert isinstance(link, list), (
                f"node {node} control_images is not a chain link: {link!r}")
            head = link[0]
            frames = []
            cursor = head
            while True:
                nd = graph[cursor]
                if nd["class_type"] == "LoadImage":
                    frames.append(nd["inputs"]["image"])
                    break
                frames.append(graph[nd["inputs"]["image2"][0]]
                              ["inputs"]["image"])
                cursor = nd["inputs"]["image1"][0]
            frames.reverse()
            frame_sets[key] = frames
            print(f"        node {node} <- {len(frames)}-frame chain "
                  f"({frames[0]} … {frames[-1]})")
        for key, frames in frame_sets.items():
            joined = b"".join(_download_input(ref) for ref in frames)
            assert joined in blob_bytes.values(), (
                f"{key}: uploaded frame concatenation is not the exact "
                "retained D0 Blob")
        report["uploaded_controls_match_retained"] = True
        report["control_frame_counts"] = {k: len(v)
                                          for k, v in frame_sets.items()}

        outputs = []
        for node_id, out in record.get("outputs", {}).items():
            for key, imgs in (out or {}).items():
                for img in imgs if isinstance(imgs, list) else [imgs]:
                    if isinstance(img, dict) and "filename" in img:
                        outputs.append({"node": node_id, **img})
        report["executor_outputs"] = outputs
        for i, o in enumerate(outputs):
            url = (f"{COMFY}/view?filename="
                   f"{urllib.parse.quote(o['filename'])}"
                   f"&subfolder={urllib.parse.quote(o.get('subfolder', ''))}"
                   f"&type=output")
            try:
                data = comfy_get(url, timeout=300)
                dest = EVIDENCE / f"out_{i}_{o['filename']}"
                dest.write_bytes(data)
                o["sha256"] = hashlib.sha256(data).hexdigest()
                o["saved"] = str(dest)
                print(f"        output {o['filename']} sha256="
                      f"{o['sha256'][:16]}…")
            except Exception as exc:
                o["fetch_error"] = str(exc)

        step(10, "Exact Rerun through the public path")
        status, rer = http("POST", f"{SERVER}/generations/{gid}/rerun")
        if status != 202:
            raise SystemExit(f"rerun POST failed: {status} {rer}")
        rid = rer["id"]
        report["rerun_id"] = rid
        term2 = _wait_terminal(rid, 1800)
        report["rerun_terminal"] = term2
        if term2["status"] != "succeeded":
            raise SystemExit(f"rerun execution {term2['status']}: "
                             f"{term2['error_message']}")

        step(11, "verifying rerun identity reuse + zero rematerialization")
        sib2 = fetch_db(
            "SELECT input_key, position, artifact_role, "
            "derived_spatial_artifact_id, blob_hash FROM "
            "generation_derived_spatial_inputs WHERE generation_id = :g "
            "ORDER BY position", {"g": rid})
        assert sib2 == sib, "rerun derived payload differs from source"
        row2 = fetch_db(
            "SELECT workflow_spec_json, workflow_spec_hash FROM "
            "generations WHERE id = :g", {"g": rid})[0]
        assert row2["workflow_spec_json"] == row["workflow_spec_json"]
        assert row2["workflow_spec_hash"] == row["workflow_spec_hash"]
        arts2 = fetch_db("SELECT id FROM derived_spatial_artifacts")
        assert len(arts2) == 3, (
            f"artifact count changed during rerun ({len(arts2)}) — "
            "rematerialization suspected")
        report["rerun_reused_identities"] = True

        step(12, "recording executor/runtime identities")
        stats = json.loads(comfy_get("/system_stats", 30))
        report["executor_system"] = stats.get("system", {})
        report["live_runtime_closure"] = (
            "product-enforced: v4 attestation (serving pid + commits) + "
            "live model-byte SHA-256 vs the CAPTURED fingerprint; "
            "verified by the worker before upload")
        report["output_pixels_are_authority"] = False  # downstream only

        report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        report["result"] = "PASS"
        (EVIDENCE / "smoke-report.json").write_text(json.dumps(
            report, indent=2))
        print("LIVE SMOKE: PASS")
        return 0
    finally:
        _stop(worker)
        _stop(server)
        import subprocess as _sp

        _sp.run(["powershell", "-NoProfile", "-Command",
                 "Get-NetTCPConnection -LocalPort 8199 -State Listen "
                 "-ErrorAction SilentlyContinue | Select-Object "
                 "-ExpandProperty OwningProcess | ForEach-Object { "
                 "Stop-Process -Id $_ -Force }"],
                capture_output=True, timeout=30)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
