"""M10F-E — two-lane live GPU smoke (R6 §15.1 / F-108).

Lane 1 (corrected lower-v1 projected execution):
    certified schema-3 package + empty M8/M10 → logical v1 → projected
    spatial-free graph → real Wan execution → exactly one video:0
    imported → Exact Rerun identical durable identities + zero D0.

Lane 2 (unchanged spatial-v3 execution):
    schema-5 source → real three-stream D0 → real spatial Wan execution
    → corrected PD-1C contract imports exactly one video:0 → Exact Rerun
    identical durable identities + zero D0 rematerialization.

Usage:
    .venv/Scripts/python.exe scripts/m10f_two_lane_smoke.py
(launches its own attested executor on 127.0.0.1:8199 + live server on
127.0.0.1:8200; the production port-8188 deployment is never touched)
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

SMOKE_ROOT = REPO / "data" / "m10f-two-lane-smoke"
DATA_DIR = SMOKE_ROOT / "data"
PKG_DIR = SMOKE_ROOT / "pkg3"
EVIDENCE = SMOKE_ROOT / "evidence"
SERVER_PORT = 8200
COMFY = "http://127.0.0.1:8199"
SERVER = f"http://127.0.0.1:{SERVER_PORT}"

SETPIECE_T = [-3000, 1650, 0]
STAGED_T = [-3600, 1500, -400]
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

COMFY_DIR = Path(r"C:/AI/ComfyUI")
COMFY_EXE = COMFY_DIR / "venv" / "Scripts" / "python.exe"
COMFY_PYDEPS = Path(r"C:/AI/M10R3-evidence/executor/pydeps")
WRAP_DIR = COMFY_DIR / "custom_nodes" / "ComfyUI-WanVideoWrapper"
PIN_WRAPPER = "088128b224242e110d3906c6750e9a3a348a659b"


def http(method, url, body=None):
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


def comfy_get(url, timeout=60):
    if not url.startswith("http"):
        url = COMFY + url
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def step(n, msg):
    print(f"[{time.strftime('%H:%M:%S')}] step {n}: {msg}", flush=True)


def fetch_db(sql, params=None):
    import sqlite3

    con = sqlite3.connect(DATA_DIR / "soloring.db")
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(sql, params or {}).fetchall()]
    con.close()
    return rows


def wait_http(url, timeout):
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


def _stop(proc):
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.send_signal(signal.CTRL_BREAK_EVENT)
        proc.wait(timeout=15)
    except Exception:
        proc.terminate()


def _launch_attested_executor():
    import subprocess as _sp

    def _rev(path):
        out = _sp.run(["git", "-C", str(path), "rev-parse", "HEAD"],
                      capture_output=True, text=True, timeout=30)
        if out.returncode != 0:
            raise SystemExit(f"cannot read git rev of {path}")
        return out.stdout.strip()

    comfy_commit = _rev(COMFY_DIR)
    wrapper_commit = _rev(WRAP_DIR)
    wrapper_tree = _sp.run(
        ["git", "-C", str(WRAP_DIR), "rev-parse", "HEAD^{tree}"],
        capture_output=True, text=True, timeout=30).stdout.strip()
    wrapper_status = _sp.run(
        ["git", "-C", str(WRAP_DIR), "status", "--short"],
        capture_output=True, text=True, timeout=30).stdout.strip()
    if wrapper_commit != PIN_WRAPPER:
        raise SystemExit(
            f"wrapper commit {wrapper_commit} != pinned {PIN_WRAPPER}")
    if wrapper_status:
        raise SystemExit(f"wrapper working tree dirty: {wrapper_status}")

    (SMOKE_ROOT / "comfy-user").mkdir(parents=True, exist_ok=True)
    _sp.run(["powershell", "-NoProfile", "-Command",
             "Get-NetTCPConnection -LocalPort 8199 -State Listen "
             "-ErrorAction SilentlyContinue | Select-Object "
             "-ExpandProperty OwningProcess | ForEach-Object { "
             "Stop-Process -Id $_ -Force }"],
            capture_output=True, timeout=30)
    log = open(SMOKE_ROOT / "comfy-boot.log", "wb")
    proc = _sp.Popen(
        [str(COMFY_EXE), "main.py", "--listen", "127.0.0.1", "--port",
         "8199", "--disable-all-custom-nodes",
         "--whitelist-custom-nodes", "ComfyUI-WanVideoWrapper",
         "--models-directory", str(
             Path(r"C:/AI/M10R3-evidence/executor/comfy/models")),
         "--user-directory", str(SMOKE_ROOT / "comfy-user"),
         "--output-directory", "output"],
        cwd=COMFY_DIR,
        env={**os.environ, "PYTHONPATH": str(COMFY_PYDEPS)},
        creationflags=_sp.CREATE_NEW_PROCESS_GROUP,
        stdout=log, stderr=_sp.STDOUT)
    if not wait_http(f"{COMFY}/system_stats", 180):
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
        gguf_commit=wrapper_commit,
        launched_at=time.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        pid=pid,
        process_start_fingerprint=capture_process_start_fingerprint(pid),
        executor_origin="http://127.0.0.1:8199",
        custom_node_whitelist=("ComfyUI-WanVideoWrapper",))
    att_dir = DATA_DIR / "comfy-fingerprint"
    att_dir.mkdir(parents=True, exist_ok=True)
    (att_dir / "deployment_attestation.json").write_text(
        json.dumps(doc, indent=2))
    return {"comfyui_commit": comfy_commit,
            "wanvideo_wrapper_commit": wrapper_commit,
            "wanvideo_wrapper_tree": wrapper_tree,
            "wanvideo_wrapper_status": "clean" if not wrapper_status
            else wrapper_status,
            "pid": pid}


def install_package():
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


async def seed_lane1_shot() -> dict:
    """A shot with NO spatial plan and NO M8 anchors → empty M10/M8 →
    the corrected schema-3 package falls back to logical v1."""
    os.environ.update(ENV)
    from sqlalchemy import text

    from soloring.db.engine import create_soloring_engine
    from soloring.settings import Settings

    engine = create_soloring_engine(Settings())
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory = async_sessionmaker(bind=engine, expire_on_commit=False,
                                 class_=AsyncSession)
    import uuid

    pid = str(uuid.uuid4())
    async with factory() as s:
        async with s.begin():
            await s.execute(text(
                "INSERT INTO projects (id, name, created_at, updated_at) "
                "VALUES (:p, 'M10F Lane1', 't', 't')"), {"p": pid})
            seq, scene, shot = (str(uuid.uuid4()) for _ in range(3))
            await s.execute(text(
                "INSERT INTO sequences (id, project_id, position, title) "
                "VALUES (:q, :p, 1, 'S')"), {"q": seq, "p": pid})
            await s.execute(text(
                "INSERT INTO scenes (id, sequence_id, position, title) "
                "VALUES (:c, :q, 0, 'C')"), {"c": scene, "q": seq})
            await s.execute(text(
                "INSERT INTO shots (id, project_id, shot_number, subject, "
                "duration_ms, scene_id, scene_position, created_at, "
                "updated_at) VALUES (:s, :p, 1, 'm10f lane1 lower-v1', "
                "5000, :c, 0, 't', 't')"),
                {"s": shot, "p": pid, "c": scene})
    await engine.dispose()
    return {"project": pid, "shot": shot}


async def seed_lane2_shot() -> dict:
    """A schema-5 spatial shot (one staged entity = 2 streams, within
    capacity) with a spatial plan and approved world."""
    os.environ.update(ENV)
    from sqlalchemy import text

    from soloring.db.engine import create_soloring_engine
    from soloring.settings import Settings

    engine = create_soloring_engine(Settings())
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory = async_sessionmaker(bind=engine, expire_on_commit=False,
                                 class_=AsyncSession)
    from soloring.spatial import (
        plans as plan_svc,
        revisions as wrev_svc,
        tracks as track_svc,
        transitions as trans_svc,
        worlds as world_svc,
    )

    import uuid

    pid = str(uuid.uuid4())
    async with factory() as s:
        async with s.begin():
            await s.execute(text(
                "INSERT INTO projects (id, name, created_at, updated_at) "
                "VALUES (:p, 'M10F Lane2', 't', 't')"), {"p": pid})

    async def _entity(kind, name):
        eid, rid = str(uuid.uuid4()), str(uuid.uuid4())
        async with factory() as s:
            async with s.begin():
                await s.execute(text(
                    "INSERT INTO creative_entities (id, project_id, kind, "
                    "name, created_at, updated_at) VALUES (:e, :p, :k, "
                    ":n, 't','t')"),
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
                "updated_at) VALUES (:s, :p, 1, 'm10f lane2 spatial', "
                "5000, :c, 0, 't', 't')"),
                {"s": shot, "p": pid, "c": scene})
            for i, eid in enumerate((loc, c1, c2)):
                await s.execute(text(
                    "INSERT INTO shot_entity_dependencies (shot_id, "
                    "entity_id, role, position) VALUES (:s, :e, 'cast', "
                    ":i)"), {"s": shot, "e": eid, "i": i})

    blocking = []
    for eid, t in ((c1, STAGED_T), (c2, [-2400, 1750, -800])):
        track = await track_svc.create_track(
            factory(), world["id"], entity_id=eid,
            requirement="optional")
        await trans_svc.create_transition(
            factory(), track["id"], anchor_type="sequence",
            anchor_id=seq, boundary="start", operation="set",
            translation_mm=t, rotation_udeg=[0, 0, 0])
        blocking.append({
            "spatial_track_id": track["id"],
            "screen_direction": "left_to_right",
            "keyframes": [{"time_ms": 0, "transform": {
                "translation_mm": t, "rotation_udeg": [0, 0, 0]}}],
        })
    await plan_svc.put_spatial_plan(
        factory(), shot, expected_plan_hash=None, plan_raw={
            "schema_version": 1, "spatial_world_id": world["id"],
            "camera": CAM, "blocking": blocking,
            "axis_constraint": None})
    await engine.dispose()
    return {"project": pid, "shot": shot}


def _wait_terminal(generation_id, timeout):
    deadline = time.monotonic() + timeout
    r = {}
    while time.monotonic() < deadline:
        r = fetch_db(
            "SELECT status, executor_job_id, error_code, error_message "
            "FROM generations WHERE id = :g", {"g": generation_id})[0]
        if r["status"] in ("succeeded", "failed", "interrupted",
                           "cancelled"):
            return r
        time.sleep(3.0)
    raise SystemExit(f"generation {generation_id} no terminal: {r}")


def _verify_video_zero_imported(gid):
    rows = fetch_db(
        "SELECT t.output_key, a.blob_hash FROM takes t JOIN assets a ON "
        "a.take_id = t.id WHERE t.generation_id = :g", {"g": gid})
    assert len(rows) == 1, f"expected exactly 1 imported output: {rows}"
    assert rows[0]["output_key"] == "video:0", rows
    blob = fetch_db("SELECT hash, size_bytes FROM blobs WHERE hash = :h",
                    {"h": rows[0]["blob_hash"]})
    assert blob and blob[0]["size_bytes"] > 0
    return {"output_key": rows[0]["output_key"],
            "blob_hash": rows[0]["blob_hash"],
            "blob_size": blob[0]["size_bytes"]}


async def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    report = {"started": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "comfy": COMFY, "server": SERVER}
    server = worker = None
    try:
        step(0, "launching the certified pinned executor (attested)")
        pins = _launch_attested_executor()
        report["executor_pins"] = pins
        print(f"        comfy {pins['comfyui_commit'][:12]}… wrapper "
              f"{pins['wanvideo_wrapper_commit'][:12]}… tree "
              f"{pins['wanvideo_wrapper_tree'][:12]}… pid {pins['pid']}")

        step(1, "installing the corrected frozen schema-3 package")
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

        step(3, "seeding lane 1 (non-spatial) + lane 2 (spatial) shots")
        lane1 = await seed_lane1_shot()
        report["lane1_seed"] = lane1
        lane2 = await seed_lane2_shot()
        report["lane2_seed"] = lane2

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

        step(5, "starting the real worker (one instance for both lanes)")
        worker = subprocess.Popen(
            [sys.executable, "-m", "soloring.worker"],
            cwd=REPO, env={**os.environ, **ENV},
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            stdout=open(SMOKE_ROOT / "worker.log", "wb"),
            stderr=subprocess.STDOUT)

        # ============ LANE 2: unchanged spatial-v3 execution ============
        step(6, "LANE 2: POST /shots/{id}/generations (spatial v3)")
        s2, g2 = http("POST",
                      f"{SERVER}/shots/{lane2['shot']}/generations")
        if s2 != 202:
            raise SystemExit(f"lane2 POST failed: {s2} {g2}")
        gid2 = g2["id"]
        report["lane2_generation_id"] = gid2
        row2 = fetch_db(
            "SELECT workflow_spec_json, workflow_spec_hash, status, "
            "manifest_hash FROM generations WHERE id = :g",
            {"g": gid2})[0]
        spec2 = json.loads(row2["workflow_spec_json"])
        assert spec2["schema_version"] == 3
        assert spec2["spatial_realization"]["derived_artifacts"]
        assert spec2["outputs"] == [{
            "name": "video", "kind": "video", "expected_count": 1,
            "accepted_media_types": None}]
        sib2 = fetch_db(
            "SELECT input_key, position, blob_hash FROM "
            "generation_derived_spatial_inputs WHERE generation_id = :g "
            "ORDER BY position", {"g": gid2})
        assert len(sib2) == 3, sib2  # world + 2 entities
        report["lane2_spec_hash"] = row2["workflow_spec_hash"]
        report["lane2_siblings"] = sib2
        print(f"        lane2 generation {gid2} spec v3 "
              f"siblings={len(sib2)}")

        step(7, "LANE 2: waiting for terminal (GPU, spatial execution)")
        t2 = _wait_terminal(gid2, 1800)
        report["lane2_terminal"] = t2
        if t2["status"] != "succeeded":
            raise SystemExit(f"lane2 {t2['status']}: {t2['error_message']}")

        step(8, "LANE 2: verifying spatial execution + video:0 import")
        history2 = json.loads(
            comfy_get(f"/history/{t2['executor_job_id']}", 30))
        rec2 = history2.get(t2["executor_job_id"])
        assert rec2
        graph2 = None
        for item in rec2.get("prompt", []):
            if isinstance(item, dict) and "101" in item:
                graph2 = item
                break
        assert graph2, "lane2 spatial graph not found"
        assert "101" in graph2 and "111" in graph2, (
            "lane2: spatial ControlNet nodes absent")
        report["lane2_controlnet_nodes_present"] = True
        report["lane2_import"] = _verify_video_zero_imported(gid2)
        print(f"        lane2 imported video:0 blob="
              f"{report['lane2_import']['blob_hash'][:16]}… "
              f"({report['lane2_import']['blob_size']} bytes)")

        step(8.5, "restarting executor before lane 2 rerun (VRAM)")
        pins2r = _launch_attested_executor()
        report["executor_pins_lane2_rerun"] = pins2r
        step(9, "LANE 2: Exact Rerun")
        s2r, r2 = http("POST", f"{SERVER}/generations/{gid2}/rerun")
        if s2r != 202:
            raise SystemExit(f"lane2 rerun POST failed: {s2r} {r2}")
        rid2 = r2["id"]
        report["lane2_rerun_id"] = rid2
        t2r = _wait_terminal(rid2, 1800)
        report["lane2_rerun_terminal"] = t2r
        if t2r["status"] != "succeeded":
            raise SystemExit(
                f"lane2 rerun {t2r['status']}: {t2r['error_message']}")
        row2r = fetch_db(
            "SELECT workflow_spec_json, workflow_spec_hash FROM "
            "generations WHERE id = :g", {"g": rid2})[0]
        assert row2r["workflow_spec_json"] == row2["workflow_spec_json"]
        assert row2r["workflow_spec_hash"] == row2["workflow_spec_hash"]
        sib2r = fetch_db(
            "SELECT input_key, position, blob_hash FROM "
            "generation_derived_spatial_inputs WHERE generation_id = :g "
            "ORDER BY position", {"g": rid2})
        assert sib2r == sib2, "lane2 rerun siblings differ"
        arts2 = fetch_db("SELECT COUNT(*) AS n FROM "
                         "derived_spatial_artifacts")
        assert arts2[0]["n"] == 3, (
            f"lane2 artifact count changed ({arts2[0]['n']}) — "
            "rematerialization suspected")
        report["lane2_rerun_reused_identities"] = True
        report["lane2_rerun_zero_remateralization"] = True

        # ============ executor restart between lanes ==================
        # the 3-ControlNet spatial execution + rerun leaves the 12 GB
        # RTX 3080 Ti VRAM in a state that crashes subsequent model
        # loads (torch access violation in module.to); a fresh executor
        # between lanes is the honest isolation.
        step(9.5, "restarting the executor between lanes (VRAM reset)")
        pins2 = _launch_attested_executor()
        report["executor_pins_lane1"] = pins2
        print(f"        comfy {pins2['comfyui_commit'][:12]}… wrapper "
              f"{pins2['wanvideo_wrapper_commit'][:12]}… pid "
              f"{pins2['pid']}")

        # ============ LANE 1: corrected lower-v1 projected execution ====
        step(10, "LANE 1: POST /shots/{id}/generations (lower-v1)")
        s1, g1 = http("POST",
                      f"{SERVER}/shots/{lane1['shot']}/generations")
        if s1 != 202:
            raise SystemExit(f"lane1 POST failed: {s1} {g1}")
        gid1 = g1["id"]
        report["lane1_generation_id"] = gid1
        row1 = fetch_db(
            "SELECT workflow_spec_json, workflow_spec_hash, status, "
            "manifest_hash FROM generations WHERE id = :g",
            {"g": gid1})[0]
        spec1 = json.loads(row1["workflow_spec_json"])
        assert spec1["schema_version"] == 1, spec1["schema_version"]
        assert "model" not in spec1 and "realization" not in spec1
        assert "spatial_realization" not in spec1
        assert spec1["outputs"] == [{
            "name": "video", "kind": "video", "expected_count": 1,
            "accepted_media_types": None}]
        assert spec1["prompt"]  # non-empty compiled prompt
        report["lane1_spec_hash"] = row1["workflow_spec_hash"]
        print(f"        lane1 generation {gid1} spec v1 prompt=…"
              f"{spec1['prompt'][-20:]}")


        step(11, "LANE 1: waiting for terminal (GPU, projected graph)")
        t1 = _wait_terminal(gid1, 1800)
        report["lane1_terminal"] = t1
        if t1["status"] != "succeeded":
            raise SystemExit(f"lane1 {t1['status']}: {t1['error_message']}")

        step(12, "LANE 1: verifying prompt + graph + video:0 import")
        history = json.loads(
            comfy_get(f"/history/{t1['executor_job_id']}", 30))
        rec = history.get(t1["executor_job_id"])
        assert rec, "lane1 prompt history vanished"
        graph = None
        for item in rec.get("prompt", []):
            if isinstance(item, dict) and "60" in item:
                graph = item
                break
        assert graph, "lane1 prompt graph not found"
        # projected graph: no ControlNet nodes
        for spatial in ("100", "101", "110", "111", "120", "121"):
            assert spatial not in graph, (
                f"lane1: spatial node {spatial} in projected graph")
        # non-empty prompt at 3/positive_prompt
        pp = graph["3"]["inputs"]["positive_prompt"]
        assert pp == spec1["prompt"], (
            f"lane1 prompt mismatch: {pp!r} != {spec1['prompt']!r}")
        assert pp, "lane1 prompt empty"
        # model link rewired to node 1
        assert graph["60"]["inputs"]["model"] == ["1", 0]
        report["lane1_prompt_bound"] = True
        report["lane1_projected_nodes"] = sorted(
            k for k in graph if k != "extra_data")
        report["lane1_import"] = _verify_video_zero_imported(gid1)
        print(f"        lane1 imported video:0 blob="
              f"{report['lane1_import']['blob_hash'][:16]}… "
              f"({report['lane1_import']['blob_size']} bytes)")

        step(13, "LANE 1: Exact Rerun")
        s1r, r1 = http("POST", f"{SERVER}/generations/{gid1}/rerun")
        if s1r != 202:
            raise SystemExit(f"lane1 rerun POST failed: {s1r} {r1}")
        rid1 = r1["id"]
        report["lane1_rerun_id"] = rid1
        t1r = _wait_terminal(rid1, 1800)
        report["lane1_rerun_terminal"] = t1r
        if t1r["status"] != "succeeded":
            raise SystemExit(
                f"lane1 rerun {t1r['status']}: {t1r['error_message']}")
        row1r = fetch_db(
            "SELECT workflow_spec_json, workflow_spec_hash FROM "
            "generations WHERE id = :g", {"g": rid1})[0]
        assert row1r["workflow_spec_json"] == row1["workflow_spec_json"]
        assert row1r["workflow_spec_hash"] == row1["workflow_spec_hash"]
        dsa1 = fetch_db(
            "SELECT COUNT(*) AS n FROM generation_derived_spatial_inputs "
            "WHERE generation_id = :g", {"g": rid1})
        assert dsa1[0]["n"] == 0, "lane1: D0 siblings on rerun!"
        report["lane1_rerun_reused_identities"] = True
        report["lane1_rerun_zero_d0"] = True

        step(14, "recording runtime identities")
        stats = json.loads(comfy_get("/system_stats", 30))
        report["executor_system"] = stats.get("system", {})
        report["soloring_head"] = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"],
            capture_output=True, text=True).stdout.strip()
        report["soloring_tree"] = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "HEAD^{tree}"],
            capture_output=True, text=True).stdout.strip()

        report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        report["result"] = "PASS"
        (EVIDENCE / "two-lane-report.json").write_text(
            json.dumps(report, indent=2))
        print("\nTWO-LANE LIVE SMOKE: PASS")
        return 0
    finally:
        _stop(worker)
        _stop(server)
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-NetTCPConnection -LocalPort 8199 -State Listen "
             "-ErrorAction SilentlyContinue | Select-Object "
             "-ExpandProperty OwningProcess | ForEach-Object { "
             "Stop-Process -Id $_ -Force }"],
            capture_output=True, timeout=30)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
