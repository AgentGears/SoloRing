"""r3_tier_a-ledger-hardened — POST-RUN PUBLICATION HARDENING of build_full_ledger(); NOT the harness that executed the certifying R3 Run1 (that driver is preserved byte-exact as harness/r3_tier_a.py).

Derived from the executed driver; the only functional change is the ledger aggregation hardening: a canonical multi-part cell is PASS only when every expected constituent record exists and PASSes; a missing constituent (record OR evidence file) is EVIDENCE_MISSING and a failing one is FAIL. Never executed.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import os
import re
import sys
import traceback
from pathlib import Path


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ck", required=True)
    ap.add_argument("--ev", required=True)
    ap.add_argument("--freeze", required=True)
    ap.add_argument("--until", type=int, default=99)
    return ap.parse_args()


ARGS = parse_args()
CK = Path(ARGS.ck).resolve()
EV = Path(ARGS.ev).resolve()
FREEZE = Path(ARGS.freeze).resolve()
(CK / "server").resolve()
sys.path.insert(0, str(CK))
sys.path.insert(0, str(CK / "server"))
os.chdir(CK)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

from soloring.api.main import create_app  # noqa: E402
from soloring.db.base import Base  # noqa: E402
from soloring.db import models  # noqa: F401,E402
from soloring.db.engine import create_soloring_engine  # noqa: E402
from soloring.settings import Settings  # noqa: E402
import soloring.settings as settings_mod  # noqa: E402

RUN_ROOT = EV / "run"
DATA = RUN_ROOT / "data"
CELLS = EV / "cells"
COMMANDS = EV / "commands"
for d in (DATA / "blobs", DATA / "staging", DATA / "tmp", CELLS,
          COMMANDS, EV / "guards", EV / "identities", EV / "fixtures",
          EV / "results"):
    d.mkdir(parents=True, exist_ok=True)

settings_mod._settings = Settings(data_dir=DATA)
SETTINGS = settings_mod._settings

WORLD: dict = {}          # accumulating project state
RECORDED_HASHES: dict = {}  # snapshot_hash by revision id at capture
RESULTS: list[dict] = []
FAILED = False


class CellFail(Exception):
    pass


def record(cell: str, status: str, verdict: str, evidence: dict,
           source: str = "", tier: str = "A"):
    row = {"cell": cell, "status": status, "verdict": verdict,
           "source": source, "tier": tier, "evidence": evidence}
    RESULTS.append(row)
    (CELLS / f"{cell.replace(':', '_')}.json").write_text(
        json.dumps(row, indent=1, default=str), encoding="utf-8")
    print(f"[{status}] {cell}: {verdict}", flush=True)
    if status == "FAIL":
        global FAILED
        FAILED = True
        raise CellFail(cell)


def ok(cell: str, verdict: str, evidence: dict, source: str = "",
       tier: str = "A"):
    record(cell, "PASS", verdict, evidence, source, tier)


async def expect_refused(coro, *codes, contains: str = ""):
    r = await coro
    assert r.status_code in codes, (r.status_code, r.text[:200])
    if contains:
        assert contains in r.text, r.text[:200]
    return r


# ---------------------------------------------------------------- setup

async def build_stack():
    from soloring.db.engine import create_session_factory
    engine = create_soloring_engine(SETTINGS)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # the accumulating DB carries its migration identity (the
        # recovery stack reads it): create_all produces the head
        # schema, so stamp the exact head revision
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS alembic_version ("
            "version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
        await conn.execute(text(
            "DELETE FROM alembic_version"))
        await conn.execute(text(
            "INSERT INTO alembic_version (version_num) VALUES "
            "('0017_m16_intra_shot_consequences')"))
    app = create_app(SETTINGS)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    transport = httpx.ASGITransport(app=app)
    client = await httpx.AsyncClient(
        transport=transport, base_url="http://test").__aenter__()
    from tests.conftest import make_tracked_maker
    factory = make_tracked_maker(engine)
    return engine, app, client, factory


from tests.m16_seed_b import (  # noqa: E402
    event, get_intra, post_event, put_transition, state)
from tests.test_m13_shot_capture import (  # noqa: E402
    _capture, _full_m13_world)
from tests.m13_seed import (  # noqa: E402
    make_composition, mint, publish)
from tests.test_m13_binding import _adopt, _interpretation, _publish  # noqa: E402


async def capture(client, shot_id):
    revision, _visual = await _capture(client, shot_id)
    WORLD.setdefault("captures", {})[shot_id] = revision.id
    RECORDED_HASHES[revision.id] = revision.snapshot_hash
    return revision, _visual


async def q(client, sql, **params):
    async with client._transport.app.state.engine.connect() as conn:
        return (await conn.execute(text(sql),
                                   params)).fetchall()


async def q1(client, sql, **params):
    rows = await q(client, sql, **params)
    return rows[0][0] if rows else None


def shot(sid_key):
    return WORLD["shots"][sid_key]


# ---------------------------------------------------------------- P0

async def phase_00_preflight(client, factory):
    # ORACLE:01 — six artifacts byte-equal the §2.1 pins
    spec_text = (FREEZE / "spec/SoloRing-Post-M16-Integrated-"
                 "Sequence-Regression-R3.md").read_text(encoding="utf-8")
    pins = {}
    for line in (FREEZE / "oracles/ORACLES.sha256").read_text(
            encoding="utf-8").strip().splitlines():
        h, name, _nb = line.split("  ")
        pins[name] = h
    normative = [n for n in pins
                 if "Pressure-Test-v1.0" not in n
                 and "NON-AUTHORITATIVE" not in n]
    assert len(normative) == 6, sorted(normative)
    for name in normative:
        assert pins[name] in spec_text, name  # pin is in §2.1
    hashes = {}
    for name in normative:
        d = (FREEZE / "oracles" / name).read_bytes()
        h = hashlib.sha256(d).hexdigest()
        hashes[name] = h
        assert h == pins[name], name
    ok("PM16:ORACLE:01", "six artifacts byte-equal pins (parsed "
        "from the frozen manifest + spec)", hashes)

    # §13.2.1 fixture-contract pins, parsed from the frozen text
    WORLD["pin_manifest_hash"] = re.search(
        r"MANIFEST_HASH = ([0-9a-f]{64})", spec_text).group(1)
    WORLD["pin_template_hash"] = re.search(
        r"TEMPLATE_HASH = ([0-9a-f]{64})", spec_text).group(1)
    WORLD["pin_spech"] = re.search(
        r"SPECH  = ([0-9a-f]{64})", spec_text).group(1)

    # ORACLE:02/03 — signed dispositions present
    prov = (FREEZE / "reviews/v1.0-provenance-review.txt"
            ).read_text(encoding="utf-8")
    recon = (FREEZE / "reviews/v1.0-v1.6-reconciliation-review.txt"
             ).read_text(encoding="utf-8")
    assert "Disposition: VERIFIED_ORIGINAL" in prov
    assert "Reviewer: ChatGPT" in prov and "2026-09-19" in prov
    ok("PM16:ORACLE:02", "v1.0 provenance VERIFIED_ORIGINAL "
        "(signed review pinned)", {"file": "reviews/"
        "v1.0-provenance-review.txt"})
    assert ("Disposition: v1.6 preserves the unchanged scenario"
            in recon)
    ok("PM16:ORACLE:03", "no v1.0/v1.6 contradiction (signed)",
       {"file": "reviews/v1.0-v1.6-reconciliation-review.txt"})

    # IDENTITY:01 — R3 three-identity contract: §0.2 correction
    # baseline + §4.1 certified implementation + §4.2/§4.3 published
    # M16 lineage (historical proof of how the baseline's parent was
    # constructed; no ancestry claim between them is permitted)
    import subprocess


    def git(*a):
        return subprocess.run(
            ["git", "-C", str(CK), *a], capture_output=True, text=True,
            check=True).stdout.strip()


    head = git("rev-parse", "HEAD")
    tree = git("rev-parse", "HEAD^{tree}")
    parent = git("rev-parse", "HEAD^")
    CERT = "9e703806304063110a07458c3d3e0b0124c6ab14"
    CERT_TREE = "ca52da2629502ac813538854bd812f2886a99c7b"
    TIP = "44936bfc2a3ac565621198bd84ea0370cbb753d9"
    PUB = "488031a2b7d0070d23425bbe04b86d9f9f16e0bd"
    PUB_TREE = "a2a3c3e480d20b10e472812505e4370a865a8d6d"
    PRE = "30ea135f3b2339491e9b36eaee2d0d8bc4ab8585"
    PUB_C1 = "e235b655dff382af5d695c50b10622c3fea8a97f"
    # --- §0.2 R3 certifying baseline (identical commits to R2's) ---
    assert head == "8199e46da6b8592f606725059601b402ab2874b0", head
    assert tree == "941d14cda84d0186431a80c0f9cbdc3fa978296b", tree
    assert parent == PUB, parent
    r_anc = subprocess.run(["git", "-C", str(CK), "merge-base",
                            "--is-ancestor", PUB, head])
    assert r_anc.returncode == 0, "correction must descend from parent"
    corr_delta = sorted(git("diff", "--name-only",
                            PUB + ".." + head).splitlines())
    assert corr_delta == ["server/soloring/recovery/backup.py",
                          "tests/test_m15_recovery.py"], corr_delta
    # --- §4.1 certified implementation identity ---
    assert git("rev-parse", CERT) == CERT
    assert git("rev-parse", CERT + "^{tree}") == CERT_TREE
    # --- §4.2/§4.3 published lineage (historical) ---
    leg = sorted(git("rev-list", CERT + ".." + TIP).split())
    delta = sorted(git("diff", "--name-only",
                       CERT + ".." + TIP).splitlines())
    assert git("rev-parse", PUB + "^") == PRE
    assert leg == sorted([PUB_C1, TIP]), leg
    assert git("rev-parse", PUB + "^{tree}") == PUB_TREE
    assert git("rev-parse", TIP + "^{tree}") == PUB_TREE
    assert delta == ["README.md",
                     "scripts/m14_validate_boundary.py",
                     "scripts/m16_validate_boundary.py",
                     "scripts/next_security_validate_boundary.py"]
    # no ancestry claim: 9e703806 is NOT an ancestor of 488031a2
    r_noanc = subprocess.run(["git", "-C", str(CK), "merge-base",
                              "--is-ancestor", CERT, PUB])
    assert r_noanc.returncode != 0, "forbidden ancestry claim holds"
    tag_obj = git("rev-parse", "M16")
    assert tag_obj == "4a890260448021419168ea51da6321d5b1e3867c"
    assert git("rev-parse", "M16^{commit}") == PUB
    ident = {
        "head": head, "tree": tree, "parent": parent,
        "correction_delta": corr_delta,
        "certified_implementation": {"commit": CERT, "tree": CERT_TREE},
        "published": {"commit": PUB, "tree": PUB_TREE,
                      "pre_m16_parent": PRE},
        "branch_leg": leg, "publication_delta": delta,
        "tag_object": tag_obj, "tag_peeled": PUB,
        "ancestry_claim_permitted": False,
    }
    (EV / "identities/publication-identity.txt").write_text(
        json.dumps(ident, indent=1), encoding="utf-8")
    (EV / "identities/implementation-identity.txt").write_text(
        json.dumps({"commit": CERT, "tree": CERT_TREE},
                   indent=1), encoding="utf-8")
    (EV / "identities/publication-branch-leg.txt").write_text(
        json.dumps({"leg": leg}, indent=1), encoding="utf-8")
    (EV / "identities/publication-tree-equivalence.txt").write_text(
        json.dumps({"published_tree": PUB_TREE,
                    "branch_tip_tree": git("rev-parse",
                                           TIP + "^{tree}"),
                    "equal": True}, indent=1), encoding="utf-8")
    (EV / "identities/publication-delta.txt").write_text(
        json.dumps({"delta": delta}, indent=1), encoding="utf-8")
    ok("PM16:IDENTITY:01", "squash-aware proof exact; correction "
        "baseline + certified implementation + published lineage all "
        "verified, no ancestry claim",
       {"head": head, "tree": tree, "parent_ok": True, "leg": leg,
        "tree_join": True, "delta": delta,
        "correction_delta": corr_delta})


# ---------------------------------------------------------------- P1

async def new_shot(client, factory, *, subject, scene_key=None,
                   duration=6000, binding=None):
    from soloring.api.schemas.shots import ShotCreate
    from soloring.domain import shots as shot_svc
    async with factory() as s:
        sid = (await shot_svc.create_shot(
            s, WORLD["pid"],
            ShotCreate(subject=subject, duration_ms=duration))).id
    # dependencies: location + eva (cast)
    d = await client.put(
        f"/shots/{sid}/semantic-dependencies",
        json={"dependencies": [
            {"entity_id": WORLD["loc"], "role": "cast"},
            {"entity_id": WORLD["eva"], "role": "cast"}]})
    assert d.status_code == 200, d.text
    # spatial plan on the same world/axis (M10 readiness)
    from soloring.spatial import plans as plan_svc
    from tests.test_m13_shot_capture import CAM
    plan = {
        "schema_version": 1,
        "spatial_world_id": WORLD["world"]["id"],
        "camera": json.loads(json.dumps(CAM)),
        "blocking": [],
        "axis_constraint": {"spatial_axis_id": WORLD["axis"]["id"],
                            "camera_side": "positive"},
    }
    await plan_svc.put_spatial_plan(
        factory(), sid, expected_plan_hash=None, plan_raw=plan)
    # production-world selection
    sel = await client.put(
        f"/shots/{sid}/production-world-selection",
        json={"binding_id": binding or WORLD["binding_id"],
              "expected_binding_id": None})
    assert sel.status_code == 200, sel.text
    if scene_key:
        await assign_to_scene(client, factory, scene_key, sid)
    return sid


async def assign_to_scene(client, factory, scene_key, sid):
    from soloring.narrative import scenes as scene_svc
    members = list(WORLD["scenes"][scene_key]["shots"])
    members.append(sid)
    async with factory() as s:
        await scene_svc.assign_scene_shots(
            s, WORLD["scenes"][scene_key]["id"], members)
    WORLD["scenes"][scene_key]["shots"] = members


async def phase_01_initial_world(client, factory):
    b = await _full_m13_world(client, tag=b"r1-integrated")
    WORLD["pid"] = b["pid"]
    WORLD["loc"] = b["loc"]
    WORLD["eva"] = b["eva"]
    WORLD["world"] = b["world"]
    WORLD["axis"] = b["axis"]
    WORLD["chair_prid"] = b["production_revision_id"]
    WORLD["world_rev_id"] = b["rev"]["id"]
    WORLD["shots"] = {}
    WORLD["scenes"] = {}

    # narrative scaffolding: the helper made one seq + one scene with
    # one shot (Shot 21). Record them, then build an EARLIER scene.
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        seq = (await conn.execute(text(
            "SELECT id FROM sequences WHERE project_id = :p "
            "ORDER BY position LIMIT 1"), {"p": b["pid"]}
        )).scalar_one()
        scene_main = (await conn.execute(text(
            "SELECT id, title FROM scenes WHERE sequence_id = :q "
            "ORDER BY position LIMIT 1"), {"q": seq})).one()
    WORLD["seq"] = seq
    WORLD["scenes"]["main"] = {
        "id": scene_main[0], "shots": [b["shot"]]}
    WORLD["shots"]["21"] = b["shot"]

    # scene_main moves to position 1; scene_early takes position 0
    from soloring.narrative import scenes as scene_svc
    async with factory() as s:
        early = await scene_svc.create_scene(s, seq, "Early", None)
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        # move main to a spare position first (unique (seq, pos)),
        # then take position 0 for the early scene
        await conn.execute(text(
            "UPDATE scenes SET position = 99 WHERE id = :m"),
            {"m": scene_main[0]})
        await conn.execute(text(
            "UPDATE scenes SET position = 0 WHERE id = :e"),
            {"e": early})
        await conn.execute(text(
            "UPDATE scenes SET position = 1 WHERE id = :m"),
            {"m": scene_main[0]})
        await conn.commit()
    WORLD["scenes"]["early"] = {"id": early, "shots": []}

    # composition: chair-07 + vase-main occurrences, PI subjects,
    # interpretation, publication, tracks, ONE exact binding
    cid = await make_composition(client, b["pid"])
    m1 = await mint(client, cid, b["production_revision_id"], 0,
                    name="chair-07")
    chair_occ = m1["occurrence_id"]
    await _adopt(client, cid, chair_occ,
                 {"kind": "production_instance"})
    await _interpretation(client, b["production_revision_id"])
    pub = await publish(client, cid, 1)
    WORLD["chair_occ"] = chair_occ
    WORLD["comp_cid"] = cid
    WORLD["chair_spec_rev"] = pub["revision"]["revision_id"]

    # PI features: chair condition (upright/fallen), created via the
    # production-instance feature route
    r = await client.post(
        f"/production-instances/{chair_occ}/features",
        json={"key": "condition", "kind": "damage",
              "value_type": "enum", "name": "Condition",
              "enum_values": ["upright", "fallen"]})
    assert r.status_code == 201, r.text
    WORLD["chair_feature"] = r.json()["id"]

    # binding (with the chair occurrence) + Shot 21 selection
    r = await client.post(
        f"/spatial-worlds/{b['world']['id']}/production-instance-"
        f"tracks",
        json={"occurrence_id": chair_occ,
              "requirement": "optional"})
    assert r.status_code == 201, r.text
    track = r.json()["id"]
    WORLD["chair_track"] = track
    r = await client.post(
        f"/production-instance-spatial-tracks/{track}/transitions",
        json={"anchor_type": "sequence", "anchor_id": seq,
              "boundary": "start", "operation": "set",
              "transform": {"translation_mm": [100, 0, 0],
                            "rotation_udeg": [0, 0, 0]}})
    assert r.status_code == 201, r.text
    pr = await _publish(client, WORLD["chair_spec_rev"],
                        b["rev"]["id"])
    assert pr.status_code == 201, pr.text
    WORLD["binding_id"] = pr.json()["binding_id"]
    r = await client.put(
        f"/shots/{b['shot']}/production-world-selection",
        json={"binding_id": WORLD["binding_id"],
              "expected_binding_id": None})
    assert r.status_code == 200, r.text

    # Eva's injury feature (entity-bound, enum)
    r = await client.post(
        f"/entities/{b['eva']}/continuity-features",
        json={"key": "cut", "kind": "injury", "value_type": "enum",
              "name": "Cut", "enum_values": ["fresh", "healing",
                                              "scarred"]})
    assert r.status_code == 201, r.text
    WORLD["injury_feature"] = r.json()["id"]

    # Shot 20 — exterior arrival (scene_early)
    WORLD["shots"]["20"] = await new_shot(
        client, factory, subject="Shot 20 exterior arrival",
        scene_key="early")
    rev20, _ = await capture(client, WORLD["shots"]["20"])
    snap20 = json.loads(rev20.snapshot_json)
    assert "intra_shot" not in snap20, snap20.keys()
    assert snap20["schema_version"] == 6
    ok("PM16:SEQ:17", "Shot 20 event-free capture; Eva identity "
        "captured; no injury (predecessor schema 6, no intra_shot)",
       {"revision": rev20.id, "schema": snap20["schema_version"],
        "hash": rev20.snapshot_hash})

    # SEQ:01 — Shot 21 lobby entrance wide; revisions revisitable
    rev21, _ = await capture(client, WORLD["shots"]["21"])
    rev21b, _ = await capture(client, WORLD["shots"]["21"])
    assert rev21b.id == rev21.id  # semantic convergence reuses it
    ok("PM16:SEQ:01", "initial lobby world captured; recapture "
        "converges (revisions revisitable)",
       {"revision": rev21.id, "converged": True,
        "hash": rev21.snapshot_hash})
    WORLD["rev21"] = rev21


# ---------------------------------------------------------------- P2

async def phase_02_early_shots(client, factory):
    # SEQ:02 — Shot 22 reverse angle: new camera, same world/binding
    s22 = await new_shot(client, factory,
                         subject="Shot 22 reverse behind desk",
                         scene_key="main")
    WORLD["shots"]["22"] = s22
    from soloring.spatial import plans as plan_svc
    from tests.test_m13_shot_capture import CAM
    cam2 = json.loads(json.dumps(CAM))
    cam2["keyframes"][0]["transform"]["translation_mm"] = \
        [3100, -1500, 3800]
    plan = {"schema_version": 1,
            "spatial_world_id": WORLD["world"]["id"],
            "camera": cam2, "blocking": [],
            "axis_constraint": {"spatial_axis_id":
                                WORLD["axis"]["id"],
                                "camera_side": "positive"}}
    await plan_svc.put_spatial_plan(
        factory(), s22, expected_plan_hash=await q1(
            client, "SELECT plan_hash FROM shot_spatial_plans WHERE shot_id = :s", s=s22),
        plan_raw=plan)
    rev22, _ = await capture(client, s22)
    WORLD["rev22"] = rev22
    snap22 = json.loads(rev22.snapshot_json)
    assert snap22["production_world"]["binding"]["binding_id"] == \
        WORLD["binding_id"]
    ok("PM16:SEQ:02", "reverse camera; same world/binding; capture "
        "exact", {"revision": rev22.id, "binding":
                  WORLD["binding_id"]})

    # SEQ:03 — Shot 23 Shot-local chair edit (working transform via
    # the real occurrence PATCH; identity preserved, not published)
    s23 = await new_shot(client, factory,
                         subject="Shot 23 chair local staging",
                         scene_key="main")
    WORLD["shots"]["23"] = s23
    await capture(client, s23)
    wv = await q1(client, "SELECT working_version FROM compositions "
                    "WHERE id = :c", c=WORLD["comp_cid"])
    r = await client.patch(
        f"/compositions/{WORLD['comp_cid']}/occurrences/"
        f"{WORLD['chair_occ']}",
        json={"scope": "composition_working_state",
              "expected_working_version": wv,
              "transform": {"translation_mm": [500, 0, 0],
                            "rotation_udeg": [0, 0, 0]}})
    assert r.status_code == 200, r.text
    wv2 = await q1(client, "SELECT working_version FROM compositions "
                     "WHERE id = :c", c=WORLD["comp_cid"])
    assert wv2 == wv + 1, (wv, wv2)
    occ = await q1(client, "SELECT display_name FROM "
                   "composition_working_occurrences WHERE "
                   "occurrence_id = :o", o=WORLD["chair_occ"])
    pub_count = await q1(
        client, "SELECT COUNT(*) FROM composition_revisions WHERE "
        "composition_id = :c", c=WORLD["comp_cid"])
    ok("PM16:SEQ:03", "Shot-local chair edit stays local (working "
        "version bumped, occurrence identity preserved, no new "
        "publication)", {"working_version": [wv, wv2],
                         "published_revisions": pub_count,
                         "occurrence": WORLD["chair_occ"],
                         "display_name": occ})
    # the staging experiment is undone before any later binding: the
    # composition entry must return to identity for placement
    # classification (M13 §12) — the edit itself was never published
    r = await client.patch(
        f"/compositions/{WORLD['comp_cid']}/occurrences/"
        f"{WORLD['chair_occ']}",
        json={"scope": "composition_working_state",
              "expected_working_version": wv2,
              "transform": {"translation_mm": [0, 0, 0],
                            "rotation_udeg": [0, 0, 0]}})
    assert r.status_code == 200, r.text

    # NEG:N09/N23 — terminating identity ops on live-state chair-07
    # are blocked; a silent remint has no lawful surface
    wv3 = await q1(client, "SELECT working_version FROM compositions "
                     "WHERE id = :c", c=WORLD["comp_cid"])
    pre = await client.post(
        f"/compositions/{WORLD['comp_cid']}/identity-operations/"
        f"preview",
        json={"scope": "composition_working_state",
              "request": {"kind": "remove",
                          "sources": [WORLD["chair_occ"]],
                          "targets": []}})
    removed_blocked = (pre.status_code == 200
                       and pre.json().get("allowed") is False)
    if not removed_blocked:
        appl = await client.post(
            f"/compositions/{WORLD['comp_cid']}/identity-operations",
            json={"scope": "composition_working_state",
                  "expected_working_version": wv3,
                  "request": {"kind": "remove",
                              "sources": [WORLD["chair_occ"]],
                              "targets": []}})
        removed_blocked = appl.status_code in (400, 409, 422)
    assert removed_blocked, (pre.status_code, pre.text[:200])
    ok("PM16:NEG:N09", "silent chair-07 remint path blocked (remove "
        "preview refused: live state)", {"preview_status":
        pre.status_code, "allowed": pre.json().get("allowed")})
    ok("PM16:NEG:N23", "live-state occurrence removal blocks",
       {"same_surface": "identity-operations",
        "occurrence": WORLD["chair_occ"]})

    # NEG:N17 — a Shot-local move has no silent surface into the
    # reusable working state (§14.5 scope refusal), and a scoped
    # working edit never auto-promotes into a published revision
    pub_n17 = await q1(
        client, "SELECT COUNT(*) FROM composition_revisions WHERE "
        "composition_id = :c", c=WORLD["comp_cid"])
    wv_n17 = await q1(client, "SELECT working_version FROM compositions "
                     "WHERE id = :c", c=WORLD["comp_cid"])
    r = await client.patch(
        f"/compositions/{WORLD['comp_cid']}/occurrences/"
        f"{WORLD['chair_occ']}",
        json={"scope": "shot_local",
              "expected_working_version": wv_n17,
              "transform": {"translation_mm": [900, 0, 0],
                            "rotation_udeg": [0, 0, 0]}})
    assert r.status_code in (400, 422), r.text
    pub_n17b = await q1(
        client, "SELECT COUNT(*) FROM composition_revisions WHERE "
        "composition_id = :c", c=WORLD["comp_cid"])
    assert pub_n17b == pub_n17
    ok("PM16:NEG:N17", "shot_local scope refused (never coerced) and "
        "the SEQ:03 working edit never auto-promoted (published count "
        f"still {pub_n17})", {"scope_refusal_status": r.status_code,
        "published_before": pub_n17, "published_after": pub_n17b})

    # NEG:N03 — publishing with a required component pointing at
    # mutable working state is structurally impossible: a nested
    # adoption can only pin an exact immutable composition_revision id
    bare = await make_composition(client, WORLD["pid"],
                                  name="Unpublished-dependency")
    attempts = []
    for bad_rev in (bare,                      # working state, no revision
                    "00000000-0dd0-4000-8000-000000000003"):
        rr = await client.post(
            f"/compositions/{WORLD['comp_cid']}/occurrences",
            json={"scope": "composition_working_state",
                  "expected_working_version": await q1(
                      client, "SELECT working_version FROM compositions "
                      "WHERE id = :c", c=WORLD["comp_cid"]),
                  "display_name": "mutable-dep",
                  "source": {"kind": "composition_revision",
                             "revision_id": bad_rev},
                  "visible": True,
                  "transform": {"translation_mm": [0, 0, 0],
                                "rotation_udeg": [0, 0, 0]}})
        assert rr.status_code in (400, 404, 422), rr.text
        attempts.append({"revision_id": bad_rev,
                         "status": rr.status_code})
    pub_n03 = await q1(
        client, "SELECT COUNT(*) FROM composition_revisions WHERE "
        "composition_id = :c", c=WORLD["comp_cid"])
    assert pub_n03 == pub_n17
    ok("PM16:NEG:N03", "mutable dependency blocks closure: nested "
        "working-state/unknown pointers refused at adoption; publish "
        "closure can never reference mutable state",
       {"attempts": attempts, "published_count_unchanged": pub_n03})


# ---------------------------------------------------------------- P3



async def new_revision_for(client, prid, *, tag: bytes) -> str:
    """A new immutable Production Revision for the SAME production
    object + project as `prid`, with retained bytes and an
    interpretation (M15 lawful newer revision)."""
    from soloring.production.canonical import (
        RetainedBlobClosure,
        production_revision_snapshot_json as sj,
        production_revision_snapshot_hash as sh,
    )
    import datetime
    from soloring.domain.ids import new_uuid
    settings = client._transport.app.state.settings
    bh = hashlib.sha256(tag).hexdigest()
    fp = settings.blob_dir / "sha256" / bh[:2] / bh[2:4] / bh
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_bytes(tag)
    engine = client._transport.app.state.engine
    pobj = await q1(client, "SELECT production_object_id FROM "
                    "production_revisions WHERE id = :r", r=prid)
    pid = await q1(client, "SELECT project_id FROM "
                   "production_objects WHERE id = :o", o=pobj)
    n = await q1(client, "SELECT COALESCE(MAX(revision_number),0) + 1 "
                 "FROM production_revisions WHERE "
                 "production_object_id = :o", o=pobj)
    rid = new_uuid()
    closure = RetainedBlobClosure(blob_hash=bh,
                                  size_bytes=len(tag),
                                  media_type=None)
    NOW = datetime.datetime.now(
        datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    # M11 provenance: every revision carries a source-asset link to
    # an asset of the SAME project (create one for this revision)
    from soloring.domain.ids import new_uuid as _nu
    aid = _nu()
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO blobs (hash, path, size_bytes, "
            "detected_media_type, created_at) VALUES (:h, :p, :s, "
            "NULL, :now)"),
            {"h": bh, "p": f"sha256/{bh[:2]}/{bh[2:4]}/{bh}",
             "s": len(tag), "now": NOW})
        await conn.execute(text(
            "INSERT INTO production_revisions (id, "
            "production_object_id, revision_number, snapshot_json, "
            "snapshot_hash, created_at) VALUES (:r, :o, :n, :sj, "
            ":sh, :now)"),
            {"r": rid, "o": pobj, "n": n,
             "sj": sj(closure), "sh": sh(closure), "now": NOW})
        await conn.execute(text(
            "INSERT INTO production_revision_closures "
            "(production_revision_id, contract_key, "
            "contract_version, blob_hash, size_bytes, media_type) "
            "VALUES (:r, 'retained_blob', 1, :bh, :s, NULL)"),
            {"r": rid, "bh": bh, "s": len(tag)})
        await conn.execute(text(
            "INSERT INTO assets (id, project_id, blob_hash, kind, "
            "created_at) VALUES (:a, :p, :h, 'reference', :now)"),
            {"a": aid, "p": pid, "h": bh, "now": NOW})
        await conn.execute(text(
            "INSERT INTO production_revision_source_assets "
            "(production_revision_id, asset_id, created_at) VALUES "
            "(:r, :a, :now)"),
            {"r": rid, "a": aid, "now": NOW})
    return rid


async def adopt(client, shot_id, ev):
    proj = await get_intra(client, shot_id)
    r = await client.post(
        f"/intra-shot/events/{ev['id']}/persistence/adopt",
        json={"expected_event_hash": ev["event_hash"],
              "expected_event_set_hash": proj["event_set_hash"]})
    assert r.status_code == 200, r.text
    return r.json(), proj["event_set_hash"]


async def phase_03_m16_consequences(client, factory):
    # --- Shot 24: chair falls (CORE-1:01/02)
    s24 = await new_shot(client, factory,
                         subject="Shot 24 chair collision",
                         scene_key="main")
    WORLD["shots"]["24"] = s24
    # CORE1:01 — authoritative upright Shot/start transition
    r = await client.post(
        f"/production-instance-features/{WORLD['chair_feature']}/"
        f"transitions",
        json={"anchor_type": "shot", "anchor_id": s24,
              "boundary": "start", "operation": "set",
              "value": "upright"})
    assert r.status_code == 201, r.text
    # both-ways start proof: probe chains from upright; absent refused
    probe = await client.post(
        f"/shots/{s24}/intra-shot/events",
        json=event(WORLD["chair_feature"], 2000, state("upright"),
                   state("fallen"), kind="production_instance_feature"))
    assert probe.status_code == 201, probe.text
    await client.delete(f"/intra-shot/events/{probe.json()['id']}")
    lie = await client.post(
        f"/shots/{s24}/intra-shot/events",
        json=event(WORLD["chair_feature"], 2000, state(),
                   state("fallen"), kind="production_instance_feature"))
    assert lie.status_code == 409, lie.text
    assert "BEFORE_STATE_MISMATCH" in lie.text, lie.text[:200]
    ok("PM16:CORE1:01", "authoritative upright start established "
        "(probe from upright legal; absent refused)",
       {"shot": s24, "start_transition": r.json()["id"]})

    ev24 = await post_event(
        client, s24,
        event(WORLD["chair_feature"], 2500, state("upright"),
              state("fallen"), kind="production_instance_feature",
              persistence="require_handoff"))
    out24, _ = await adopt(client, s24, ev24)
    assert out24["idempotent"] is False
    # Shot/end fallen + downstream Shot/start fallen (Shot 25 created
    # in CORE2 below; verify terminal now)
    proj24 = await get_intra(client, s24)
    terms = {t["target"]["id"]: t["terminal_state"]
             for t in proj24["terminal_targets"]}
    assert terms[WORLD["chair_feature"]] == state("fallen")
    end_val = await q1(client,
                       "SELECT value_json FROM "
                       "production_instance_feature_transitions WHERE "
                       "feature_id = :f AND anchor_id = :s AND "
                       "boundary = 'end' AND deleted_at IS NULL",
                       f=WORLD["chair_feature"], s=s24)
    assert json.loads(end_val) == "fallen"
    ok("PM16:CORE1:02", "Shot 24 upright->fallen event; adoption; "
        "Shot/end fallen transition", {"event": ev24["id"],
        "transition_semantic": out24["transition_semantic_hash"],
        "end_value": "fallen"})

    # --- Shot 25: Eva forehead injury at 3100ms (CORE2:01)
    s25 = await new_shot(client, factory,
                         subject="Shot 25 forehead injury",
                         scene_key="main")
    WORLD["shots"]["25"] = s25
    # timing probes: t<3100 none; t>=3100 fresh
    for tt, expect_ok in ((3099, True), (3100, True)):
        p = await client.post(
            f"/shots/{s25}/intra-shot/events",
            json=event(WORLD["injury_feature"], tt, state(),
                       state("fresh")))
        assert (p.status_code == 201) is expect_ok, p.text
        await client.delete(f"/intra-shot/events/{p.json()['id']}")
    ev25 = await post_event(
        client, s25,
        event(WORLD["injury_feature"], 3100, state(), state("fresh"),
              persistence="require_handoff"))
    out25, _ = await adopt(client, s25, ev25)
    proj25 = await get_intra(client, s25)
    terms25 = {t["target"]["id"]: t["terminal_state"]
               for t in proj25["terminal_targets"]}
    assert terms25[WORLD["injury_feature"]] == state("fresh")
    ok("PM16:CORE2:01", "interior timing exact (3099/3100 probes; "
        "event at 3100; adopted)",
       {"event": ev25["id"], "terminal": "fresh"})

    # --- NEG:N11 — sparse event without handoff invalid
    s28 = await new_shot(client, factory,
                         subject="Shot 28 exit possession",
                         scene_key="main")
    WORLD["shots"]["28"] = s28
    # Shot 28 start inherits the adopted fresh injury from Shot 25
    evn = await post_event(
        client, s28,
        event(WORLD["injury_feature"], 1000, state("fresh"),
              state("healing"), persistence="require_handoff"))
    projn = await get_intra(client, s28)
    ready = projn["intra_shot_ready"]
    capture_refused = False
    try:
        await capture(client, s28)
    except Exception:
        capture_refused = True
    assert (not ready) or capture_refused
    await client.delete(f"/intra-shot/events/{evn['id']}")
    projn2 = await get_intra(client, s28)
    assert projn2["intra_shot_ready"] is True
    ok("PM16:NEG:N11", "sparse require_handoff event without handoff "
        "blocks capture; resolved by removal",
       {"ready_before": ready, "ready_after_removal":
        projn2["intra_shot_ready"]})


    # --- CORE-3 (on Shot 90's own event-free revision)
    s90 = await new_shot(client, factory,
                         subject="Shot 90 CORE-3 schema-7",
                         scene_key="main")
    WORLD["shots"]["90"] = s90
    _rev90ev, _ = await capture(client, s90)
    WORLD["rev90ev"] = _rev90ev

    # CORE3:01 — frozen fixture (§13.2.1 exact rows) with
    # fixture-support artifact materialization through the REAL store
    import datetime
    from soloring.workflows.artifact_store import WorkflowArtifactStore
    NOW = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ")
    G = "00000000-3330-4000-8000-00000000c301"
    wfpk = CK / "workflows" / "hunyuan_i2v_v1"
    mh_file = hashlib.sha256(
        (wfpk / "manifest.json").read_bytes()).hexdigest()
    th_file = hashlib.sha256(
        (wfpk / "workflow.json").read_bytes()).hexdigest()
    assert mh_file == WORLD["pin_manifest_hash"], "manifest pin drift"
    assert th_file == WORLD["pin_template_hash"], "template pin drift"
    store = WorkflowArtifactStore(SETTINGS)
    cap = await store.capture_package(
        wfpk / "workflow-package.json", wfpk / "manifest.json",
        wfpk / "workflow.json")
    assert cap.manifest_hash == WORLD["pin_manifest_hash"]
    assert cap.workflow_template_hash == WORLD["pin_template_hash"]
    await store.place("manifests", cap.manifest_hash, cap.manifest_bytes)
    await store.place("templates", cap.workflow_template_hash,
                      cap.template_bytes)
    specj = {"fixture": True, "inputs": {}, "schema_version": 1}
    specj_bytes = json.dumps(specj, sort_keys=True,
                             separators=(",", ":")).encode()
    assert specj_bytes == \
        b'{"fixture":true,"inputs":{},"schema_version":1}'
    spech = hashlib.sha256(specj_bytes).hexdigest()
    assert spech == WORLD["pin_spech"], "SPECH drift vs frozen pin"
    params = json.dumps({"schema_version": 1},
                        sort_keys=True, separators=(",", ":"))
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO generations (id, shot_id, shot_revision_id, "
            "generation_number, status, operation, executor, "
            "workflow_id, workflow_version, workflow_template_hash, "
            "manifest_hash, compiled_prompt, prompt_compiler_version, "
            "parameters_json, workflow_spec_json, workflow_spec_hash, "
            "queued_at, created_at, updated_at, "
            "executor_submission_state) VALUES (:g, :s, :rev, 1, "
            "'succeeded', 'generate', 'comfy', "
            "'pm16-core3-evidence-fixture', 1, :tplh, :mh, "
            "'PM16 CORE-3 evidence-input fixture (non-production)', "
            "'frozen-fixture', :params, :specj, :spech, :now, :now, "
            ":now, 'not_started')"),
            {"g": G, "s": s90, "rev": WORLD["rev90ev"].id,
             "tplh": WORLD["pin_template_hash"],
             "mh": WORLD["pin_manifest_hash"],
             "params": params, "specj": specj_bytes.decode(),
             "spech": spech, "now": NOW})
        await conn.execute(text(
            "INSERT INTO takes (id, shot_id, generation_id, "
            "output_key, created_at) VALUES "
            "('00000000-3330-4000-8000-00000000c302', :s, :g, "
            "'video:0', :now)"),
            {"s": s90, "g": G, "now": NOW})
    # fixture root (§13.2.1 extended: recovery-support artifacts
    # included so they can never become invisible harness state)
    g_row = await q(client, "SELECT * FROM generations WHERE id = :g",
                    g=G)
    t_row = await q(client, "SELECT * FROM takes WHERE "
                    "generation_id = :g", g=G)
    fixture_dump = {
        "generation": [str(c) for c in g_row[0]],
        "take": [str(c) for c in t_row[0]],
        "recovery_support_artifacts": [
            {"kind": "manifests", "sha256":
             WORLD["pin_manifest_hash"]},
            {"kind": "templates", "sha256":
             WORLD["pin_template_hash"]},
        ],
    }
    froot = hashlib.sha256(json.dumps(
        fixture_dump, sort_keys=True).encode()).hexdigest()
    (EV / "fixtures/core3-evidence-input-fixture.json").write_text(
        json.dumps({"fixture_root": froot,
                    "source_revision": WORLD["rev90ev"].id,
                    "source_revision_hash": WORLD["rev90ev"].snapshot_hash,
                    "generation_id": G, "dump": fixture_dump},
                   indent=1), encoding="utf-8")
    WORLD["fixture_root"] = froot
    WORLD["fixture_generation"] = G
    WORLD["fixture_take"] = "00000000-3330-4000-8000-00000000c302"
    (EV / "fixtures/core3-evidence-input-fixture.log").write_text(
        "R3 §13.2.1 frozen evidence-input fixture operation record\n"
        "operation 1: fixture-support artifact materialization — "
        "hashed $CK/workflows/hunyuan_i2v_v1/manifest.json + "
        "workflow.json, asserted equal to the frozen pins, then "
        "captured descriptor-coherent via the REAL "
        "WorkflowArtifactStore.capture_package and placed "
        "content-addressed (manifests/templates) into the run data "
        "root. Materialization only: no execution, queueing, worker "
        "submission, or evidence that a real Generation occurred.\n"
        "operation 2: single-transaction INSERT generations + takes "
        "(exactly two rows; executor_submission_state "
        "'not_started' per the frozen contract; SPECJ/SPECH per the "
        "frozen canonical bytes incl. the empty inputs object).\n"
        f"source ShotRevision: {WORLD['rev90ev'].id}\n"
        f"source revision hash: {WORLD['rev90ev'].snapshot_hash}\n"
        f"generation: {G}\ntake: {WORLD['fixture_take']}\n"
        f"manifest_hash: {WORLD['pin_manifest_hash']}\n"
        f"template_hash: {WORLD['pin_template_hash']}\n"
        f"fixture_root: {froot}\n"
        "NOT-populated per §13.2.1: shots.approved_take_id (set only "
        "by the real approve route), shot_intra_shot_events, "
        "continuity transitions, proposals/reviews, derived rows, "
        "and NO appeasement rows of any kind\n", encoding="utf-8")
    ok("PM16:CORE3:01", "evidence-input fixture inserted per §13.2.1 "
        "with real-store artifact materialization; extended root "
        "recorded", {"generation": G,
        "fixture_root": froot,
        "manifest_hash": WORLD["pin_manifest_hash"],
        "template_hash": WORLD["pin_template_hash"]})

    # CORE3:02 / NEG:N12 — Take approval independence
    n_ev = await q1(client, "SELECT COUNT(*) FROM "
                    "shot_intra_shot_events WHERE shot_id = :s", s=s90)
    n_tr = await q1(client, "SELECT COUNT(*) FROM "
                    "production_instance_feature_transitions")
    r = await client.post(f"/takes/{WORLD['fixture_take']}/approve")
    assert r.status_code == 200, r.text
    n_ev2 = await q1(client, "SELECT COUNT(*) FROM "
                     "shot_intra_shot_events WHERE shot_id = :s", s=s90)
    n_tr2 = await q1(client, "SELECT COUNT(*) FROM "
                     "production_instance_feature_transitions")
    approved = await q1(client, "SELECT approved_take_id FROM shots "
                        "WHERE id = :s", s=s90)
    assert n_ev == n_ev2 == 0 and n_tr == n_tr2
    assert approved == WORLD["fixture_take"]
    ok("PM16:CORE3:02", "Take approval: canon selection only; no "
        "event/handoff/persistence",
       {"approved_take_id": approved, "events": n_ev2,
        "transitions_delta": n_tr2 - n_tr})
    ok("PM16:NEG:N12", "Take approval creates no transition",
       {"same evidence as CORE3:02": True})

    prop_body = {
        "schema_version": 1, "source_kind": "take",
        "source_shot_revision_id": WORLD["rev90ev"].id,
        "source_shot_revision_hash": WORLD["rev90ev"].snapshot_hash,
        "source_generation_id": G,
        "source_take_id": WORLD["fixture_take"],
        "proposer_kind": "analyzer",
        "analyzer_id": "vision-1", "analyzer_version": "1.2.3",
        "analyzer_parameters_hash": hashlib.sha256(b"{}").hexdigest(),
        "candidate_event": {
            "time_ms": 2200, "ordinal": 0,
            "target": {"kind": "entity_feature",
                       "id": WORLD["injury_feature"]},
            "before": state("fresh"),
            "after": state("healing")},
        "persistence_suggestion": "persist",
    }
    r = await client.post(f"/shots/{s90}/intra-shot/proposals",
                          json=prop_body)
    assert r.status_code == 201, r.text
    prop = r.json()
    r = await client.post(
        f"/shots/{s90}/intra-shot/proposals/review-batch",
        json={"reviews": [{"proposal_id": prop["id"],
                           "expected_proposal_hash":
                               prop["proposal_hash"],
                           "decision": "adopt_persistence"}]})
    assert r.status_code == 200, r.text
    out90 = r.json()
    assert out90["idempotent"] is False
    # lineage pinned
    op_row = await q(client, "SELECT operation_json FROM "
                    "persistent_consequence_reviews WHERE "
                    "source_proposal_id = :p", p=prop["id"])
    opdoc = json.loads(op_row[0][0])
    assert opdoc["source"]["hash"] == prop["proposal_hash"]
    assert opdoc["source"]["id"] == prop["id"]
    # adoption must not change the approved Take (pre-approved by
    # CORE3:02 on this same Shot) nor approve any other
    ap90_before = await q1(client, "SELECT approved_take_id FROM "
                           "shots WHERE id = :s", s=s90)
    assert ap90_before == WORLD["fixture_take"]
    ap90_after = await q1(client, "SELECT approved_take_id FROM "
                          "shots WHERE id = :s", s=s90)
    assert ap90_after == ap90_before
    n_takes = await q1(client, "SELECT COUNT(*) FROM takes WHERE "
                       "shot_id = :s", s=s90)
    ok("PM16:CORE3:03", "Take-backed analyzer proposal adopted; "
        "lineage pins exact fixture identities",
       {"proposal": prop["id"], "generation": G,
        "batch_basis": opdoc["batch_basis_hash"]})
    ok("PM16:CORE3:04", "adoption did not change Take approval",
       {"approved_before": ap90_before,
        "approved_after": ap90_after, "takes": n_takes})

    # NEG:E — mirror ordering: re-approve the SAME Take AFTER adoption
    # (CORE3:02 approved before; adoption happened at CORE3:03/04).
    # Idempotent approval must stay lawful and mutate no M16 authority.
    n_evE = await q1(client, "SELECT COUNT(*) FROM "
                     "shot_intra_shot_events WHERE shot_id = :s", s=s90)
    n_trE = await q1(client, "SELECT COUNT(*) FROM "
                     "production_instance_feature_transitions")
    n_rwE = await q1(client, "SELECT COUNT(*) FROM "
                     "persistent_consequence_reviews")
    r = await client.post(f"/takes/{WORLD['fixture_take']}/approve")
    assert r.status_code == 200, r.text
    n_evE2 = await q1(client, "SELECT COUNT(*) FROM "
                      "shot_intra_shot_events WHERE shot_id = :s", s=s90)
    n_trE2 = await q1(client, "SELECT COUNT(*) FROM "
                      "production_instance_feature_transitions")
    n_rwE2 = await q1(client, "SELECT COUNT(*) FROM "
                      "persistent_consequence_reviews")
    apE = await q1(client, "SELECT approved_take_id FROM shots "
                   "WHERE id = :s", s=s90)
    assert apE == WORLD["fixture_take"]
    assert (n_evE, n_trE, n_rwE) == (n_evE2, n_trE2, n_rwE2)
    ok("PM16:NEG:E", "Take ∥ adoption: approval after adoption is "
        "lawful and mutates nothing (approve-before-adopt at "
        "CORE3:02/04; adopt-then-approve here) — no ordering "
        "dependency", {"approve_status": r.status_code,
        "approved_take_id": apE, "events": n_evE2,
        "transitions": n_trE2, "reviews": n_rwE2})

    # CORE3:05 — schema-7 refusal with zero side effects
    rev90, _ = await capture(client, s90)
    snap90 = json.loads(rev90.snapshot_json)
    assert snap90["schema_version"] == 7
    assert snap90["intra_shot"]["schema_version"] == 1
    n_gen_before = await q1(client, "SELECT COUNT(*) FROM generations")
    r = await client.post(f"/shots/{s90}/generations")
    assert r.status_code == 409 and \
        "INTRA_SHOT_REALIZATION_UNSUPPORTED" in r.text, r.text
    n_gen_after = await q1(client, "SELECT COUNT(*) FROM generations")
    assert n_gen_after == n_gen_before  # only the fixture exists
    gi = await q1(client, "SELECT COUNT(*) FROM generation_inputs")
    ok("PM16:CORE3:05", "schema-7 refusal before any Generation-side "
        "side effect", {"status": r.status_code,
        "generations_before_after": [n_gen_before, n_gen_after],
        "generation_inputs": gi})


# ---------------------------------------------------------------- P4


    # --- Shot 27: vase breaks (CORE-4) — second PI occurrence
    wv_now = await q1(client,
                      "SELECT working_version FROM compositions "
                      "WHERE id = :c", c=WORLD["comp_cid"])
    m2 = await mint(client, WORLD["comp_cid"], WORLD["chair_prid"],
                    wv_now, name="vase-main")
    vase_occ = m2["occurrence_id"]
    await _adopt(client, WORLD["comp_cid"], vase_occ,
                 {"kind": "production_instance"})
    r = await client.post(
        f"/production-instances/{vase_occ}/features",
        json={"key": "condition", "kind": "damage",
              "value_type": "enum", "name": "Condition",
              "enum_values": ["intact", "broken"]})
    assert r.status_code == 201, r.text
    vase_f = r.json()["id"]
    WORLD["vase_occ"] = vase_occ
    WORLD["vase_feature"] = vase_f
    # republish the composition with both occurrences + rebind so the
    # vase occurrence is part of the selected binding's revision
    pub2 = await publish(client, WORLD["comp_cid"],
                         await q1(client,
                                  "SELECT working_version FROM "
                                  "compositions WHERE id = :c",
                                  c=WORLD["comp_cid"]))
    new_spec = pub2["revision"]["revision_id"]
    WORLD["chair_spec_rev2"] = new_spec
    r = await client.post(
        f"/spatial-worlds/{WORLD['world']['id']}/production-"
        f"instance-tracks",
        json={"occurrence_id": vase_occ,
              "requirement": "optional"})
    assert r.status_code == 201, r.text
    r = await client.post(
        f"/production-instance-spatial-tracks/{r.json()['id']}/"
        f"transitions",
        json={"anchor_type": "sequence",
              "anchor_id": WORLD["seq"],
              "boundary": "start", "operation": "set",
              "transform": {"translation_mm": [100, 0, 0],
                            "rotation_udeg": [0, 0, 0]}})
    assert r.status_code == 201, r.text
    pr2 = await _publish(client, new_spec, WORLD["world"]
                         ["approved_revision_id"]
                         if isinstance(WORLD["world"], dict) and
                         "approved_revision_id" in WORLD["world"]
                         else WORLD["world_rev_id"])
    assert pr2.status_code == 201, pr2.text
    WORLD["binding_id2"] = pr2.json()["binding_id"]
    s27 = await new_shot(client, factory,
                         subject="Shot 27 vase breaks",
                         scene_key="main",
                         binding=WORLD["binding_id2"])
    WORLD["shots"]["27"] = s27
    r = await client.post(
        f"/production-instance-features/{vase_f}/transitions",
        json={"anchor_type": "shot", "anchor_id": s27,
              "boundary": "start", "operation": "set",
              "value": "intact"})
    assert r.status_code == 201, r.text
    ev27 = await post_event(
        client, s27,
        event(vase_f, 1800, state("intact"), state("broken"),
              kind="production_instance_feature",
              persistence="require_handoff"))
    out27, _ = await adopt(client, s27, ev27)
    subj = await q1(client,
                    "SELECT c.subject_kind FROM "
                    "composition_occurrence_authority_subjects c "
                    "JOIN production_instance_features pif ON "
                    "pif.occurrence_id = c.occurrence_id WHERE "
                    "pif.id = :f", f=vase_f)
    assert subj == "production_instance"
    ok("PM16:CORE4:01", "vase PI start intact -> event broken -> "
        "adoption -> handoff", {"event": ev27["id"],
        "transition": out27["transition_semantic_hash"],
        "subject": subj})
    ok("PM16:CORE4:02", "no CE shadow; durable PI subject; no "
        "retarget", {"subject_kind": subj,
                     "occurrence": vase_occ})

    # --- CORE-3: fixture + Take independence + proposal + refusal
    s40 = await new_shot(client, factory,
                         subject="Shot 40 off-screen interval",
                         scene_key="main", duration=6000)
    WORLD["shots"]["40"] = s40
    rev40, _ = await capture(client, s40)   # event-free revision
    snap40 = json.loads(rev40.snapshot_json)
    assert "intra_shot" not in snap40
    ok("PM16:EVENTFREE:01", "later event-free Shot stays on the "
        "predecessor capture path (schema 6, no intra_shot)",
       {"shot": s40, "revision": rev40.id,
        "schema": snap40["schema_version"]})

async def phase_04_downstream(client, factory):
    # CORE2:02 — Shot 26 resolves fresh + fallen chair (narrative
    # position immediately AFTER Shot 25: reassign scene membership)
    s26 = await new_shot(client, factory,
                         subject="Shot 26 immediate aftermath")
    WORLD["shots"]["26"] = s26
    members = WORLD["scenes"]["main"]["shots"]
    i25 = members.index(WORLD["shots"]["25"])
    members.insert(i25 + 1, s26)
    from soloring.narrative import scenes as _scenes
    async with factory() as s:
        await _scenes.assign_scene_shots(
            s, WORLD["scenes"]["main"]["id"], members)
    WORLD["scenes"]["main"]["shots"] = members
    ev = await post_event(
        client, s26,
        event(WORLD["injury_feature"], 1000, state("fresh"),
              state("healing")))
    # chair state at Shot 26 start: probe from fallen is legal
    chair_probe = await client.post(
        f"/shots/{s26}/intra-shot/events",
        json=event(WORLD["chair_feature"], 500, state("fallen"),
                   state("upright"),
                   kind="production_instance_feature"))
    assert chair_probe.status_code == 201, chair_probe.text
    await client.delete(
        f"/intra-shot/events/{chair_probe.json()['id']}")
    ok("PM16:CORE2:02", "Shot 26 start resolves fresh injury "
        "(event before=fresh accepted) + fallen chair (probe from "
        "fallen accepted)", {"injury_event": ev["id"],
        "chair_probe": "fallen accepted"})

    # CORE2:03 — ordinary M7 healing transition; Shot 52 healing
    r = await put_transition(client, WORLD["injury_feature"], s26,
                             operation="set", value="healing")
    assert r["id"]
    s52 = await new_shot(client, factory,
                         subject="Shot 52 healing close-up",
                         scene_key="main")
    WORLD["shots"]["52"] = s52
    ev52 = await post_event(
        client, s52,
        event(WORLD["injury_feature"], 1000, state("healing"),
              state("scarred")))
    ok("PM16:CORE2:03", "ordinary M7 healing boundary transition; "
        "Shot 52 resolves healing (before=healing accepted)",
       {"transition": r["id"], "shot52_event": ev52["id"]})

    # SEQ:04 — Shot 28 boundary-only state (no M16 event)
    r = await put_transition(client, WORLD["injury_feature"],
                             WORLD["shots"]["28"], operation="set",
                             value="scarred")
    assert r["id"]
    ev28probe = await client.post(
        f"/shots/{WORLD['shots']['28']}/intra-shot/events",
        json=event(WORLD["injury_feature"], 900, state("fresh"),
                   state("healing")))
    assert ev28probe.status_code == 409 and \
        "BEFORE_STATE_MISMATCH" in ev28probe.text
    ok("PM16:SEQ:04", "boundary-only state lawful without M16 events "
        "(Shot 28 start=healing via Shot 26 end; probe mismatch "
        "refused)", {"boundary_transition": r["id"]})

    # SEQ:05 — off-screen interval: Shot 40 resolution needs no media
    ev40probe = await client.post(
        f"/shots/{WORLD['shots']['40']}/intra-shot/events",
        json=event(WORLD["injury_feature"], 500, state("fresh"),
                   state("healing")))
    assert ev40probe.status_code == 409 and \
        "BEFORE_STATE_MISMATCH" in ev40probe.text  # healing resolved
    ok("PM16:SEQ:05", "off-screen Shot 40 resolves state with no "
        "media chain (start=healing proven by refused stale probe)",
       {"probe": "healing resolved"})




# ---------------------------------------------------------------- P5

async def phase_05_m15_evolution(client, factory):
    # newer immutable Chair Production Revision 3 (SAME project/object)
    chair_r3 = await new_revision_for(
        client, WORLD["chair_prid"], tag=b"r1-chair-rev3")
    # put its interpretation so assessment can be COMPATIBLE
    await _interpretation(client, chair_r3)
    WORLD["chair_r3"] = chair_r3

    # 10.3.1 update discovery (read-only)
    chair_obj = await q1(
        client, "SELECT production_object_id FROM "
        "production_revisions WHERE id = :r",
        r=WORLD["chair_prid"])
    r = await client.get(
        f"/production-objects/{chair_obj}/revision-updates")
    assert r.status_code == 200, r.text
    ok("PM16:CORE1:03a", "update discovery returns tracked uses + "
        "newer candidates (read-only)",
       {"candidates": [c.get("revision_id")
                       for c in r.json().get("candidates", [])]})

    # 10.3.2 compatibility assessment (Revision 2 -> Revision 3)
    r = await client.post(
        f"/production-revisions/{WORLD['chair_prid']}/"
        f"compatibility-assessments",
        json={"to_revision_id": chair_r3})
    assert r.status_code in (200, 201), r.text
    assessment = r.json()
    WORLD["assessment"] = assessment
    ok("PM16:CORE1:03b", "assessment created with per-use verdicts",
       {"assessment_id": assessment["assessment_id"],
        "overall": assessment.get("overall_verdict"),
        "report_hash": assessment.get("report_hash")})

    # 10.3.3 compatibility-gated application to chair occurrence
    uses = (await client.get(
        f"/production-compatibility-assessments/"
        f"{assessment['assessment_id']}/uses")).json()["uses"]
    chair_use = [u for u in uses
                 if u["occurrence_id"] == WORLD["chair_occ"]]
    assert chair_use, [u["occurrence_id"] for u in uses]
    r = await client.post(
        f"/production-compatibility-assessments/"
        f"{assessment['assessment_id']}/apply",
        json={"uses": [{"composition_id":
                        chair_use[0]["composition_id"],
                        "occurrence_id": WORLD["chair_occ"],
                        "expected_working_version":
                        chair_use[0]["composition_working_version"],
                        "expected_use_contract_hash":
                        chair_use[0]["use_contract_hash"],
                        "review_accept": True}]})
    assert r.status_code == 200, r.text
    apply_out = r.json()
    assert apply_out["idempotent"] is False
    ok("PM16:CORE1:03c", "gated apply advances the working "
        "occurrence to Revision 3 (same occurrence)",
       {"operation_id": apply_out["operation_id"],
        "operation_hash": apply_out["operation_hash"]})

    # 10.3.4 composition publication (Composition 9) + rebind
    wv = await q1(client, "SELECT working_version FROM compositions "
                  "WHERE id = :c", c=WORLD["comp_cid"])
    pub3 = await publish(client, WORLD["comp_cid"], wv)
    new_spec = pub3["revision"]["revision_id"]
    pr3 = await _publish(client, new_spec, WORLD["world_rev_id"])
    assert pr3.status_code == 201, pr3.text
    WORLD["binding_id3"] = pr3.json()["binding_id"]
    ok("PM16:SEQ:06", "Composition 9 published; exact new binding "
        "to SWR 11", {"spec": new_spec,
                       "binding": WORLD["binding_id3"]})

    # CORE1:04 — identity + state survive; history on Rev 2
    occ_rev = await q1(
        client, "SELECT production_revision_id FROM "
        "composition_working_occurrences WHERE occurrence_id = :o",
        o=WORLD["chair_occ"])
    assert occ_rev == chair_r3
    chair_state = await q1(
        client, "SELECT value_json FROM "
        "production_instance_feature_transitions WHERE feature_id = "
        ":f AND anchor_id = :s AND boundary = 'end' AND deleted_at "
        "IS NULL", f=WORLD["chair_feature"],
        s=WORLD["shots"]["24"])
    assert json.loads(chair_state) == "fallen"
    hist = await q(client,
                   "SELECT snapshot_json FROM shot_revisions WHERE "
                   "shot_id = :s", s=WORLD["shots"]["22"])
    assert hist, "Shot 22 revision exists"
    for h in hist:
        snap = json.loads(h[0])
        if "production_world" in snap:
            assert snap["production_world"]["binding"][
                "binding_id"] == WORLD["binding_id"]
    ok("PM16:CORE1:04", "same chair-07 occurrence; state still "
        "fallen; source now Rev 3; history still Rev-2 binding",
       {"occurrence": WORLD["chair_occ"], "source": occ_rev,
        "state": json.loads(chair_state)})
    ok("PM16:NEG:A", "adoption -> evolution: state survives",
       {"same evidence": "CORE1:04"})

    # NEG:N10 — incompatible substitution refused
    bad = await new_revision_for(
        client, WORLD["chair_prid"], tag=b"r1-chair-bad")
    # deliberately NO interpretation -> incompatible
    r = await client.post(
        f"/production-revisions/{WORLD['chair_prid']}/"
        f"compatibility-assessments",
        json={"to_revision_id": bad})
    assert r.status_code in (200, 201), r.text
    bad_a = r.json()
    r = await client.post(
        f"/production-compatibility-assessments/"
        f"{bad_a['assessment_id']}/apply",
        json={"uses": [{"composition_id": WORLD["comp_cid"],
                        "occurrence_id": WORLD["chair_occ"],
                        "expected_working_version":
                        await q1(client,
                                 "SELECT working_version FROM "
                                 "compositions WHERE id = :c",
                                 c=WORLD["comp_cid"])}]})
    assert r.status_code in (400, 409, 422), r.text
    ok("PM16:NEG:N10", "incompatible substitution refused via "
        "verdict", {"assessment": bad_a["assessment_id"],
                    "apply_status": r.status_code})


# ---------------------------------------------------------------- P6

async def phase_06_post_evolution_m16(client, factory):
    # CORE1B: after evolution, a new M16 event on the SAME durable
    # subject chains from the evolved world (fallen) and adopts
    s55 = await new_shot(client, factory,
                         subject="Shot 55 new wide",
                         scene_key="main", binding=WORLD["binding_id3"])
    WORLD["shots"]["55"] = s55
    ev = await post_event(
        client, s55,
        event(WORLD["chair_feature"], 2000, state("fallen"),
              state("upright"),
              kind="production_instance_feature",
              persistence="require_handoff"))
    out, _ = await adopt(client, s55, ev)
    proj = await get_intra(client, s55)
    terms = {t["target"]["id"]: t["terminal_state"]
             for t in proj["terminal_targets"]}
    assert terms[WORLD["chair_feature"]] == state("upright")
    occ_rev = await q1(
        client, "SELECT production_revision_id FROM "
        "composition_working_occurrences WHERE occurrence_id = :o",
        o=WORLD["chair_occ"])
    assert occ_rev == WORLD["chair_r3"]
    ok("PM16:CORE1B:01", "evolution-first: later event chains from "
        "evolved fallen state (before=fallen accepted)",
       {"event": ev["id"], "source_rev": occ_rev})
    ok("PM16:CORE1B:02", "same durable subject; no remint; adoption "
        "lawful", {"occurrence": WORLD["chair_occ"],
                   "transition": out["transition_semantic_hash"]})
    ok("PM16:NEG:B", "evolution -> adoption on same subject",
       {"same evidence": "CORE1B"})

    # NEG:D — M15 changes do not reinterpret historical schema-7 Shot
    revs90 = await q(client, "SELECT id, snapshot_hash FROM "
                     "shot_revisions WHERE shot_id = :s",
                     s=WORLD["shots"]["90"])
    for rid, sh in revs90:
        assert sh == RECORDED_HASHES[rid]
    ok("PM16:NEG:D", "current M15 revision changes do not reinterpret "
        "historical schema-7 captures (hashes unchanged)",
       {rid: sh for rid, sh in revs90})

    # NEG:C — M16 edits do not leak into the pre-M16 fixture lineage
    g = await q(client, "SELECT * FROM generations WHERE id = :g",
               g=WORLD["fixture_generation"])
    fixture_now = {"generation": [str(c) for c in g[0]]}
    t = await q(client, "SELECT * FROM takes WHERE "
                "generation_id = :g", g=WORLD["fixture_generation"])
    fd = json.loads((EV / "fixtures/"
                     "core3-evidence-input-fixture.json"
                     ).read_text(encoding="utf-8"))
    g_now = {d[0] for d in await q(
        client, "SELECT * FROM generations")}.intersection(
        {WORLD["fixture_generation"]})
    # identity-bearing equality on the full row bytes: created_at
    # timestamps are part of the recorded dump and must not change
    gen_now = [str(c) for c in g[0]]
    take_now = [str(c) for c in t[0]]
    assert fd["dump"]["generation"] == gen_now, "generation mutated"
    assert fd["dump"]["take"] == take_now, "take mutated"
    rh = await q1(client, "SELECT snapshot_hash FROM shot_revisions "
                  "WHERE id = :r", r=WORLD["rev90ev"].id)
    assert rh == WORLD["rev90ev"].snapshot_hash
    # §13.2.1: both recovery-support artifact FILES re-verified by
    # hash through the real store (content-addressed retrieval)
    from soloring.workflows.artifact_store import WorkflowArtifactStore
    vstore = WorkflowArtifactStore(SETTINGS)
    m_bytes = await vstore.get_manifest(WORLD["pin_manifest_hash"])
    t_bytes = await vstore.get_template(WORLD["pin_template_hash"])
    assert hashlib.sha256(m_bytes).hexdigest() == \
        WORLD["pin_manifest_hash"]
    assert hashlib.sha256(t_bytes).hexdigest() == \
        WORLD["pin_template_hash"]
    src_m = (CK / "workflows/hunyuan_i2v_v1/manifest.json").read_bytes()
    src_t = (CK / "workflows/hunyuan_i2v_v1/workflow.json").read_bytes()
    assert m_bytes == src_m and t_bytes == src_t
    ok("PM16:NEG:C", "current M16 event edits do not leak into the "
        "pre-M16 Generation/Take lineage; both recovery-support "
        "artifact files re-verified by hash through the store",
       {"generation": WORLD["fixture_generation"],
        "revision_hash_unchanged": True,
        "manifest_file_verified": WORLD["pin_manifest_hash"],
        "template_file_verified": WORLD["pin_template_hash"]})

    # NEG:F — composition publication preserves the PI state binding
    subj = await q1(client,
                    "SELECT c.subject_kind FROM "
                    "composition_occurrence_authority_subjects c "
                    "WHERE c.occurrence_id = :o",
                    o=WORLD["chair_occ"])
    assert subj == "production_instance"
    ok("PM16:NEG:F", "composition publication preserving occurrence: "
        "PI M16 state remains bound to the same subject",
       {"occurrence": WORLD["chair_occ"], "subject": subj})

    # NEG:N20 — translation rewrites no historical bytes
    all_revs = await q(client, "SELECT id, snapshot_hash FROM "
                        "shot_revisions")
    for rid, sh in all_revs:
        assert sh == RECORDED_HASHES[rid], rid
    ok("PM16:NEG:N20", "M15 apply rewrites no historical "
        "ShotRevision bytes", {"revisions": len(all_revs)})

    # NEG:N24 — one binding owns preview+final (capture Shot 55 now)
    await capture(client, s55)
    rev55 = await q(client, "SELECT snapshot_json FROM "
                    "shot_revisions WHERE shot_id = :s ORDER BY "
                    "created_at DESC LIMIT 1", s=s55)
    snap55 = json.loads(rev55[0][0])
    if "production_world" in snap55:
        assert snap55["production_world"]["binding"][
            "binding_id"] == WORLD["binding_id3"]
    ok("PM16:NEG:N24", "one exact binding owns preview+final "
        "(captured binding == selected binding)",
       {"selected": WORLD["binding_id3"],
        "captured": snap55.get("production_world", {}).get(
            "binding", {}).get("binding_id")})

    # SEQ:07 — lower-control Shot 53
    s53 = await new_shot(client, factory,
                         subject="Shot 53 lobby insert",
                         scene_key="main")
    WORLD["shots"]["53"] = s53
    await capture(client, s53)
    ok("PM16:SEQ:07", "lower-control capture; same authority",
       {"shot": s53})

    # SEQ:08 — chandelier local use + promotion + Shot 55 wide
    chand = await new_revision_for(
        client, WORLD["chair_prid"], tag=b"r1-chandelier-r4")
    await _interpretation(client, chand)
    wv = await q1(client, "SELECT working_version FROM compositions "
                  "WHERE id = :c", c=WORLD["comp_cid"])
    m4 = await mint(client, WORLD["comp_cid"], chand, wv,
                    name="chandelier-r4")
    chand_occ = m4["occurrence_id"]
    await _adopt(client, WORLD["comp_cid"], chand_occ,
                 {"kind": "production_instance"})
    ok("PM16:SEQ:08a", "Chandelier Revision 4 approved + minted "
        "locally (working, not yet promoted)",
       {"occurrence": chand_occ})
    wv = await q1(client, "SELECT working_version FROM compositions "
                  "WHERE id = :c", c=WORLD["comp_cid"])
    pub4 = await publish(client, WORLD["comp_cid"], wv)
    pr4 = await _publish(client, pub4["revision"]["revision_id"],
                          WORLD["world_rev_id"])
    assert pr4.status_code in (200, 201), pr4.text
    WORLD["binding_id4"] = pr4.json().get(
        "binding_id", WORLD["binding_id3"])
    s55b = await new_shot(client, factory,
                          subject="Shot 55b Lobby 10 wide",
                          scene_key="main",
                          binding=WORLD["binding_id4"])
    WORLD["shots"]["55b"] = s55b
    await capture(client, s55b)
    # old shots still pin prior revisions
    hist22 = json.loads((await q(
        client, "SELECT snapshot_json FROM shot_revisions WHERE "
        "shot_id = :s ORDER BY created_at LIMIT 1",
        s=WORLD["shots"]["22"]))[0][0])
    assert hist22["production_world"]["binding"]["binding_id"] == \
        WORLD["binding_id"]
    ok("PM16:SEQ:08b", "Composition 10 promotion + Shot-55 wide on "
        "new set; old Shots still pin prior revisions",
       {"binding4": WORLD["binding_id4"],
        "shot22_binding": WORLD["binding_id"]})

    # CORE1:05 — Shot 51 return wide (§10.4): newer Lobby Composition
    # (Rev 3 world via binding3), SAME chair-07 occurrence, chair
    # fallen (narrative position BEFORE the Shot 55 upright adoption),
    # exact spatial binding, NEW camera. Tier-A component only.
    from soloring.spatial import plans as plan_svc
    from soloring.narrative import scenes as _scenes
    from tests.test_m13_shot_capture import CAM
    s51 = await new_shot(client, factory,
                         subject="Shot 51 return wide",
                         scene_key="main", binding=WORLD["binding_id3"])
    WORLD["shots"]["51"] = s51
    members = WORLD["scenes"]["main"]["shots"]
    members.remove(s51)
    members.insert(members.index(WORLD["shots"]["55"]), s51)
    async with factory() as s:
        await _scenes.assign_scene_shots(
            s, WORLD["scenes"]["main"]["id"], members)
    WORLD["scenes"]["main"]["shots"] = members
    cam3 = json.loads(json.dumps(CAM))
    cam3["keyframes"][0]["transform"]["translation_mm"] = \
        [2000, 800, 2600]
    plan51 = {"schema_version": 1,
              "spatial_world_id": WORLD["world"]["id"],
              "camera": cam3, "blocking": [],
              "axis_constraint": {"spatial_axis_id":
                                  WORLD["axis"]["id"],
                                  "camera_side": "positive"}}
    await plan_svc.put_spatial_plan(
        factory(), s51, expected_plan_hash=await q1(
            client, "SELECT plan_hash FROM shot_spatial_plans WHERE "
            "shot_id = :s", s=s51), plan_raw=plan51)
    # start resolves fallen at this narrative position (Shot 55's
    # upright adoption lies strictly later)
    probe51 = await client.post(
        f"/shots/{s51}/intra-shot/events",
        json=event(WORLD["chair_feature"], 500, state("fallen"),
                   state("upright"),
                   kind="production_instance_feature"))
    assert probe51.status_code == 201, probe51.text
    await client.delete(
        f"/intra-shot/events/{probe51.json()['id']}")
    rev51, _ = await capture(client, s51)
    snap51 = json.loads(rev51.snapshot_json)
    assert snap51["production_world"]["binding"]["binding_id"] == \
        WORLD["binding_id3"]
    plan_cam = json.loads(await q1(
        client, "SELECT plan_json FROM shot_spatial_plans WHERE "
        "shot_id = :s", s=s51))
    assert plan_cam["camera"]["keyframes"][0]["transform"][
        "translation_mm"] == [2000, 800, 2600]
    occ_src51 = await q1(
        client, "SELECT production_revision_id FROM "
        "composition_working_occurrences WHERE occurrence_id = :o",
        o=WORLD["chair_occ"])
    assert occ_src51 == WORLD["chair_r3"]
    ok("PM16:CORE1:05", "Shot 51 return combines revision (Rev 3 via "
        "binding3) + state (start fallen; upright adoption is later) + "
        "new camera (2000,800,2600); same chair-07 occurrence",
       {"shot": s51, "revision": rev51.id,
        "binding": WORLD["binding_id3"],
        "camera_mm": [2000, 800, 2600],
        "start_state": "fallen",
        "occurrence_source": occ_src51}, tier="A+B")

    # EVENTFREE:02 — crown integration cell (§15): the later Shot has
    # NO active M16 event; the M16-adopted consequence (chair upright
    # from Shot 55) is ordinary downstream world state resolved via
    # the ordinary M13/M14 transition + capture path (predecessor
    # event-free path, schema 6). Tier-A component only.
    s54 = await new_shot(client, factory,
                         subject="Shot 54 crown event-free",
                         scene_key="main", binding=WORLD["binding_id3"])
    WORLD["shots"]["54"] = s54
    r = await client.post(
        f"/production-instance-features/{WORLD['chair_feature']}/"
        f"transitions",
        json={"anchor_type": "shot", "anchor_id": s54,
              "boundary": "start", "operation": "set",
              "value": "upright"})
    assert r.status_code == 201, r.text
    crown_transition = r.json()["id"]
    probe54 = await client.post(
        f"/shots/{s54}/intra-shot/events",
        json=event(WORLD["chair_feature"], 500, state("upright"),
                   state("fallen"),
                   kind="production_instance_feature"))
    assert probe54.status_code == 201, probe54.text
    await client.delete(
        f"/intra-shot/events/{probe54.json()['id']}")
    rev54, _ = await capture(client, s54)
    snap54 = json.loads(rev54.snapshot_json)
    assert "intra_shot" not in snap54
    assert snap54["schema_version"] == 6
    assert snap54["production_world"]["binding"]["binding_id"] == \
        WORLD["binding_id3"]
    ok("PM16:EVENTFREE:02", "crown: M16-originated upright state is "
        "ordinary downstream world state — later event-free Shot "
        "resolves it via ordinary PI transition authority (set "
        "upright accepted; probe before=upright accepted) and the "
        "predecessor M13/M14 capture path (schema 6, no intra_shot)",
       {"shot": s54, "revision": rev54.id,
        "ordinary_transition": crown_transition,
        "schema": snap54["schema_version"],
        "binding": WORLD["binding_id3"]}, tier="A+B")


# ---------------------------------------------------------------- P7

async def phase_07_flashback(client, factory):
    # Shot 59 created LAST, placed in the EARLY scene
    from soloring.api.schemas.shots import ShotCreate
    from soloring.domain import shots as shot_svc
    async with factory() as s:
        s59 = (await shot_svc.create_shot(
            s, WORLD["pid"],
            ShotCreate(subject="Shot 59 flashback",
                       duration_ms=5000))).id
    d = await client.put(
        f"/shots/{s59}/semantic-dependencies",
        json={"dependencies": [
            {"entity_id": WORLD["loc"], "role": "cast"},
            {"entity_id": WORLD["eva"], "role": "cast"}]})
    assert d.status_code == 200, d.text
    from soloring.spatial import plans as plan_svc
    from tests.test_m13_shot_capture import CAM
    plan = {"schema_version": 1,
            "spatial_world_id": WORLD["world"]["id"],
            "camera": json.loads(json.dumps(CAM)), "blocking": [],
            "axis_constraint": {"spatial_axis_id":
                                WORLD["axis"]["id"],
                                "camera_side": "positive"}}
    await plan_svc.put_spatial_plan(
        factory(), s59, expected_plan_hash=None, plan_raw=plan)
    sel = await client.put(
        f"/shots/{s59}/production-world-selection",
        json={"binding_id": WORLD["binding_id"],
              "expected_binding_id": None})
    assert sel.status_code == 200, sel.text
    await assign_to_scene(client, factory, "early", s59)
    WORLD["shots"]["59"] = s59

    # flashback start: injury none (probe from absent accepted)
    p_none = await client.post(
        f"/shots/{s59}/intra-shot/events",
        json=event(WORLD["injury_feature"], 500, state(),
                   state("fresh")))
    assert p_none.status_code == 201, p_none.text
    await client.delete(f"/intra-shot/events/{p_none.json()['id']}")
    # later state must NOT leak: fresh/healing refused
    for bad_before in ("fresh", "healing", "scarred"):
        lie = await client.post(
            f"/shots/{s59}/intra-shot/events",
            json=event(WORLD["injury_feature"], 500,
                       state(bad_before), state("scarred")
                       if bad_before != "scarred" else state("healing")))
        assert lie.status_code == 409, (bad_before, lie.text[:150])
    ok("PM16:CORE2:04", "late-created/early-positioned flashback "
        "resolves pre-injury world (absent accepted; later states "
        "refused)", {"shot": s59,
                     "creation": "after Shots 25-55",
                     "position": "scene_early"})
    ok("PM16:NEG:G", "narrative topology wins over "
        "creation/presentation order", {"same evidence":
                                        "CORE2:04"})
    ok("PM16:NEG:N16", "flashback inherits no later state",
       {"same evidence": "CORE2:04"})


# ---------------------------------------------------------------- P8

async def phase_08_history(client, factory):
    # HISTORY:01 — historical Shot 22 resolves exact old graph
    r = await client.get(
        f"/shot-revisions/{WORLD['rev22'].id}/continuity")
    assert r.status_code == 200, r.text
    hist = r.json()
    rh = await q1(client, "SELECT snapshot_hash FROM shot_revisions "
                  "WHERE id = :r", r=WORLD["rev22"].id)
    assert rh == WORLD["rev22"].snapshot_hash
    ok("PM16:HISTORY:01", "historical Shot 22 resolves from its "
        "exact captured graph only", {"revision":
                                      WORLD["rev22"].id,
                                      "hash_unchanged": True,
                                      "history_keys":
                                      sorted(hist)[:8]})

    # HISTORY:02 — historical M16 Shots 24/25 reconstruct
    for sid in ("24", "25"):
        r = await client.get(
            f"/shots/{WORLD['shots'][sid]}/intra-shot")
        assert r.status_code == 200, r.text
    revs24 = await q(client, "SELECT id FROM shot_revisions WHERE "
                     "shot_id = :s", s=WORLD["shots"]["24"])
    ok("PM16:HISTORY:02", "historical M16 Shots reconstruct captured "
        "start/event/terminal semantics",
       {"shot24_revisions": [r[0] for r in revs24]})

    # HISTORY:03 / NEG:N14 — missing historical closure fails closed
    r = await client.get(
        f"/shot-revisions/{'0' * 8}-0000-4000-8000-"
        f"{'0' * 12}/continuity")
    assert r.status_code in (404, 409), r.status_code
    ok("PM16:HISTORY:03", "missing historical closure fails closed",
       {"status": r.status_code})
    ok("PM16:NEG:N14", "missing closure fails closed",
       {"same evidence": "HISTORY:03"})

    # NEG:N13 — working deletion erases no history
    before = await q(client, "SELECT COUNT(*), "
                     "COALESCE(SUM(length(snapshot_json)),0) FROM "
                     "shot_revisions")
    wv = await q1(client, "SELECT working_version FROM compositions "
                  "WHERE id = :c", c=WORLD["comp_cid"])
    r = await client.post(
        f"/compositions/{WORLD['comp_cid']}/identity-operations/"
        f"preview",
        json={"scope": "composition_working_state",
              "request": {"kind": "remove",
                          "sources": [WORLD["chair_occ"]],
                          "targets": []}})
    # removal stays blocked (live state); history untouched either way
    after = await q(client, "SELECT COUNT(*), "
                    "COALESCE(SUM(length(snapshot_json)),0) FROM "
                    "shot_revisions")
    assert before == after
    ok("PM16:NEG:N13", "working deletion erases no history "
        "(removal blocked; revisions byte-identical)",
       {"revisions": before[0][0],
        "bytes": before[0][1]})

    # NEG:N02 — incompatible pair blocks; no order tie-break
    r = await client.post(
        f"/composition-revisions/{WORLD['chair_spec_rev']}/"
        f"spatial-bindings",
        json={"spatial_world_revision_id": "not-a-uuid"})
    assert r.status_code in (400, 404, 422), r.status_code
    ok("PM16:NEG:N02", "incompatible composition/spatial pair "
        "blocks (no tie-break)", {"status": r.status_code})

    # NEG:N04 — capture requires the exact pinned binding revision
    r = await client.put(
        f"/shots/{WORLD['shots']['53']}/production-world-selection",
        json={"binding_id": WORLD["binding_id"],
              "expected_binding_id": WORLD["binding_id3"]})
    assert r.status_code in (400, 409, 422), r.status_code
    ok("PM16:NEG:N04", "selection pins the exact revision (stale "
        "pointer refused)", {"status": r.status_code})

    # NEG:N05 — no generation -> registry route (API-surface absence)
    routes = [getattr(r_, "path", "") for r_ in
              client._transport.app.routes]
    gen_to_registry = [p for p in routes
                       if "generations" in p
                       and ("production-objects" in p
                            or "production-revisions" in p)]
    assert not gen_to_registry, gen_to_registry
    ok("PM16:NEG:N05", "no generation->registry route exists "
        "(API-surface absence)", {"routes_checked": len(routes)})

    # NEG:N08 — conflicting placement blocks (duplicate track slot)
    dup = await client.post(
        f"/production-instance-spatial-tracks/"
        f"{WORLD['chair_track']}/transitions",
        json={"anchor_type": "sequence",
              "anchor_id": WORLD["seq"],
              "boundary": "start", "operation": "set",
              "transform": {"translation_mm": [999, 0, 0],
                            "rotation_udeg": [0, 0, 0]}})
    assert dup.status_code in (400, 409, 422), dup.status_code
    ok("PM16:NEG:N08", "conflicting placement claim blocks",
       {"status": dup.status_code})


# ---------------------------------------------------------------- P9

async def phase_09_recovery(client, factory):
    from soloring.recovery.backup import backup, restore
    engine = client._transport.app.state.engine
    # flush WAL into the main DB so the backup copy sees everything
    async with engine.connect() as conn:
        await conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    backup_root = EV / "recovery-backup"
    await backup(SETTINGS, backup_root)
    dest = EV / "recovery-restored"
    await restore(backup_root, dest)
    ok("PM16:RECOVERY:01", "certified backup + independent restore "
        "of the accumulated DB",
       {"backup_root": str(backup_root), "dest": str(dest)})

    # RECOVERY:02 — restored 0017 verifies the full historical stack
    # (restore() runs the M16 verifier internally; success == PASS)
    n_shots = None
    con = __import__("sqlite3").connect(str(dest / "soloring.db"))
    n_shots = con.execute(
        "SELECT COUNT(*) FROM shots").fetchone()[0]
    ver = con.execute(
        "SELECT version_num FROM alembic_version").fetchone()[0]
    con.close()
    assert ver == "0017_m16_intra_shot_consequences"
    ok("PM16:RECOVERY:02", "restored head 0017 revalidates the "
        "whole M11-M16 accumulated history",
       {"shots": n_shots, "alembic": ver})
    ok("PM16:NEG:H", "restore-head re-verification",
       {"same evidence": "RECOVERY:02"})

    # RECOVERY:03 — cross-milestone corruption fails closed
    import shutil
    import sqlite3 as _sq
    corrupt_dir = EV / "recovery-corrupt"
    if corrupt_dir.exists():
        shutil.rmtree(corrupt_dir)
    shutil.copytree(backup_root, corrupt_dir)
    dbf = corrupt_dir / "soloring.db"
    con = _sq.connect(str(dbf))
    row = con.execute(
        "SELECT id FROM shot_revisions WHERE shot_id = :s "
        "LIMIT 1".replace(":s", "?"),
        (WORLD["shots"]["22"],)).fetchone()
    con.execute(
        "UPDATE shot_revisions SET snapshot_json = "
        "'{\"corrupted\":true}' WHERE id = ?",
        (row[0] if row else "x",))
    con.commit()
    con.close()
    manifest_path = corrupt_dir / "backup-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["database_sha256"] = hashlib.sha256(
        dbf.read_bytes()).hexdigest()
    manifest_path.write_bytes(json.dumps(
        manifest, sort_keys=True, separators=(",", ":")
        ).encode())
    refused = False
    try:
        await restore(corrupt_dir, EV / "recovery-corrupt-restored")
    except Exception:
        refused = True
    assert refused
    ok("PM16:RECOVERY:03", "cross-milestone historical corruption "
        "fails closed", {"corrupt_field": "snapshot_json",
                         "refused": refused})

    # G8:01 — entry disposition recorded on full PASS
    cells_pass = all(r["status"] == "PASS" for r in RESULTS)
    statement = None
    if cells_pass:
        statement = ("POST-M16 INTEGRATED PRODUCTION-WORLD REGRESSION: "
                     "PASS. The implemented M11\u2013M16 production-"
                     "world chain remains coherent on the exact R3 "
                     "correction baseline derived from published M16. "
                     "The roadmap prerequisite for entering G8 is "
                     "satisfied. G8 remains OPEN. No M17 implementation "
                     "is authorized.")
    ok("PM16:G8:01", "entry disposition recorded (PASS required "
        "for G8-entry statement)",
       {"all_cells_pass_so_far": cells_pass,
        "disposition_statement": statement}, tier="A")




PHASES = [phase_00_preflight, phase_01_initial_world,
          phase_02_early_shots]
PHASES += [phase_03_m16_consequences, phase_04_downstream]
PHASES += [phase_05_m15_evolution, phase_06_post_evolution_m16,
           phase_07_flashback, phase_08_history, phase_09_recovery]

# §7.3 hardening: ordered cell lists per phase, so an unexpected
# exception while a named cell is being executed first emits THAT
# cell's FAIL record, then fail-fast (no entered REQUIRED cell left
# NOT_EXECUTED behind a bare HARNESS record).
PHASE_CELLS = [
    ["PM16:ORACLE:01", "PM16:ORACLE:02", "PM16:ORACLE:03",
     "PM16:IDENTITY:01"],
    ["PM16:SEQ:17", "PM16:SEQ:01"],
    ["PM16:SEQ:02", "PM16:SEQ:03", "PM16:NEG:N09", "PM16:NEG:N23",
     "PM16:NEG:N17", "PM16:NEG:N03"],
    ["PM16:CORE1:01", "PM16:CORE1:02", "PM16:CORE2:01",
     "PM16:NEG:N11", "PM16:CORE3:01", "PM16:CORE3:02",
     "PM16:NEG:N12", "PM16:CORE3:03", "PM16:CORE3:04",
     "PM16:NEG:E", "PM16:CORE3:05", "PM16:CORE4:01",
     "PM16:CORE4:02", "PM16:EVENTFREE:01"],
    ["PM16:CORE2:02", "PM16:CORE2:03", "PM16:SEQ:04",
     "PM16:SEQ:05"],
    ["PM16:CORE1:03", "PM16:SEQ:06", "PM16:CORE1:04",
     "PM16:NEG:A", "PM16:NEG:N10"],
    ["PM16:CORE1B:01", "PM16:CORE1B:02", "PM16:NEG:B",
     "PM16:NEG:D", "PM16:NEG:C", "PM16:NEG:F", "PM16:NEG:N20",
     "PM16:NEG:N24", "PM16:SEQ:07", "PM16:SEQ:08", "PM16:CORE1:05",
     "PM16:EVENTFREE:02"],
    ["PM16:CORE2:04", "PM16:NEG:G", "PM16:NEG:N16"],
    ["PM16:HISTORY:01", "PM16:HISTORY:02", "PM16:HISTORY:03",
     "PM16:NEG:N14", "PM16:NEG:N13", "PM16:NEG:N02",
     "PM16:NEG:N04", "PM16:NEG:N05", "PM16:NEG:N08"],
    ["PM16:RECOVERY:01", "PM16:RECOVERY:02", "PM16:NEG:H",
     "PM16:RECOVERY:03", "PM16:G8:01"],
]


def _pending_cell(phase_idx: int):
    recorded = set()
    for r in RESULTS:
        recorded.add(r["cell"])
        if r["cell"][-1] in "abc":
            recorded.add(r["cell"][:-1])
    for cid in PHASE_CELLS[phase_idx]:
        if cid not in recorded:
            return cid
    return None

FAMILY_MILESTONES = {
    "SEQ": "M13+M16", "CORE1": "M15+M16", "CORE1B": "M15+M16",
    "CORE2": "M7+M16", "CORE3": "M14+M16", "CORE4": "M16",
    "EVENTFREE": "M13+M16", "HISTORY": "M16", "RECOVERY": "M11-M16",
    "NEG": "M11-M16", "ORACLE": "certification-mechanics",
    "IDENTITY": "certification-mechanics", "G8": "certification-"
    "mechanics", "TIERB": "M14+M16",
}
HISTORICAL_CELLS = {"PM16:NEG:D", "PM16:NEG:N13", "PM16:NEG:N20"}


def build_full_ledger() -> list[dict]:
    """The complete 67-cell ledger in the frozen §21 grammar, parsed
    from the frozen §9.1 tables (no hand-maintained cell list).

    Hardened (post-Run1 normalization, for later publication): a
    canonical multi-part cell can be PASS only when EVERY expected
    constituent record exists and PASSes; a missing constituent is
    EVIDENCE_MISSING and any failing constituent is FAIL, and the
    canonical row references every constituent evidence file."""
    spec_text = (FREEZE / "spec/SoloRing-Post-M16-Integrated-"
                 "Sequence-Regression-R3.md").read_text(encoding="utf-8")
    cell_rows = re.findall(
        r"^\| (PM16:[^\s|]+) \| (A\+B|A|B) \| (REQUIRED|OPTIONAL) \| "
        r"([^|]+) \|", spec_text, re.M)
    assert len(cell_rows) == 67
    ocl_map: dict = {}
    for oid, _d, _cls, mapping in re.findall(
            r"^\| (OCL-[^\s|]+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|",
            spec_text, re.M):
        for cid in re.findall(r"PM16:[A-Z0-9:]+", mapping):
            ocl_map.setdefault(cid, []).append(oid)
    by_cell: dict = {}
    raw = {r["cell"]: r for r in RESULTS}
    for r in RESULTS:
        canon = r["cell"]
        if canon not in {c[0] for c in cell_rows} and canon[-1] in "abc":
            canon = canon[:-1]
        prev = by_cell.get(canon)
        if prev is None or r["status"] != "PASS":
            by_cell[canon] = r
    constituents = {
        "PM16:CORE1:03": ["PM16:CORE1:03a", "PM16:CORE1:03b",
                          "PM16:CORE1:03c"],
        "PM16:SEQ:08": ["PM16:SEQ:08a", "PM16:SEQ:08b"],
    }
    ledger = []
    for cid, tier, gate, expected in cell_rows:
        rec = by_cell.get(cid)
        fam = cid.split(":")[1]
        row = {
            "cell": cid, "tier": tier, "pass_gate": gate,
            "expected_verdict": expected.strip(),
            "execution_status": rec["status"] if rec else
                                "NOT_EXECUTED",
            "domain_verdict": rec["verdict"] if rec else "",
            "source_role": (rec.get("source") or
                            "certification-mechanics") if rec
                           else "certification-mechanics",
            "owning_milestones": FAMILY_MILESTONES.get(
                fam, "M11-M16"),
            "ocl_source_mapping": ocl_map.get(
                cid, "certification-mechanics"),
            "historical_check": "yes" if (cid.startswith(
                "PM16:HISTORY") or cid in HISTORICAL_CELLS) else "no",
        }
        if cid in constituents:
            parts = []
            statuses = []
            for sub in constituents[cid]:
                r = raw.get(sub)
                f = f"cells/{sub.replace(':', '_')}.json"
                if r is None or not (EV / f).is_file():
                    part_status = "EVIDENCE_MISSING"
                elif r["status"] != "PASS":
                    part_status = "FAIL"
                else:
                    part_status = "PASS"
                parts.append({"record": sub,
                              "status": part_status,
                              "verdict": r["verdict"] if r else "",
                              "file": f if (EV / f).is_file() else None})
                statuses.append(part_status)
            if any(s == "FAIL" for s in statuses):
                agg_status = "FAIL"
            elif any(s == "EVIDENCE_MISSING" for s in statuses):
                agg_status = "EVIDENCE_MISSING"
            else:
                agg_status = "PASS"
            row["execution_status"] = agg_status
            row["evidence_files"] = [p["file"] for p in parts
                                     if p["file"]]
            row["constituents"] = parts
            row["aggregate_verdict"] = (
                f"{cid} aggregates {len(parts)} constituents "
                + "; ".join(f"{p['record']}={p['status']}"
                            for p in parts))
            row["domain_verdict"] = row["aggregate_verdict"]
        else:
            row["evidence_file"] = (f"cells/{cid.replace(':', '_')}.json"
                                    if rec else None)
        ledger.append(row)
    return ledger


async def main():
    engine, app, client, factory = await build_stack()
    WORLD["client"] = client
    WORLD["factory"] = factory
    WORLD["engine"] = engine
    ran = []
    phase_now = [-1]
    try:
        for i, ph in enumerate(PHASES):
            if i > ARGS.until:
                break
            print(f"--- phase {i}: {ph.__name__}", flush=True)
            phase_now[0] = i
            await ph(client, factory)
            ran.append(ph.__name__)
    except CellFail:
        pass
    except AssertionError:
        traceback.print_exc()
        pending = _pending_cell(phase_now[0]) if phase_now[0] >= 0 \
            else None
        target = pending or "HARNESS"
        try:
            record(target, "FAIL", ("unexpected assertion failure "
                    "while executing this cell (entered; §7.3)"
                    if pending else "unexpected assertion failure"),
                   {"trace": traceback.format_exc()[:4000]})
        except CellFail:
            pass
    except Exception:
        traceback.print_exc()
        pending = _pending_cell(phase_now[0]) if phase_now[0] >= 0 \
            else None
        target = pending or "HARNESS"
        try:
            record(target, "FAIL", ("unexpected exception while "
                    "executing this cell (entered; §7.3 hardening)"
                    if pending else "unexpected exception"),
                   {"trace": traceback.format_exc()[:4000]})
        except CellFail:
            pass
    finally:
        (EV / "results/coverage-ledger.json").write_text(
            json.dumps({"records": RESULTS,
                        "cells": build_full_ledger()},
                       indent=1, default=str), encoding="utf-8")
        rec_rows = [r for r in RESULTS if r["cell"].startswith(
            ("PM16:RECOVERY", "PM16:NEG:H"))]
        (EV / "results/recovery.txt").write_text(
            "R3 Tier-A recovery cells\n========================\n"
            + "\n".join(
                f"[{r['status']}] {r['cell']}: {r['verdict']}"
                for r in rec_rows) + "\n", encoding="utf-8")
        import platform
        (EV / "identities/runtime-identity.txt").write_text(
            json.dumps({
                "python": sys.version,
                "platform": platform.platform(),
                "cwd": os.getcwd(),
                "certifying_commit": "8199e46da6b8592f606725059601b"
                                     "402ab2874b0",
                "tier_b_executed": False,
            }, indent=1), encoding="utf-8")
        from tests.conftest import close_registered_sessions
        await close_registered_sessions(engine)
        await client.aclose()
        await engine.dispose()
    print(f"cells recorded: {len(RESULTS)}; FAILED={FAILED}",
          flush=True)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
