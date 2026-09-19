"""R3 Tier-A evidence packager (frozen §20/§20.1).

Builds MANIFEST.json over every evidence payload (the manifest cannot
hash itself, and the final results record pins the manifest), then
writes results/run-record.json with the run disposition, and emits the
presentation ZIP. The frozen-spec identity fields are PARSED from the
frozen Part II §A (never hardcoded). Runs AFTER the post-guard;
evidence-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


ap = argparse.ArgumentParser()
ap.add_argument("--ev", required=True)
ap.add_argument("--freeze", required=True)
ap.add_argument("--driver-rc", type=int, required=True)
ap.add_argument("--pre-rc", type=int, required=True)
ap.add_argument("--post-rc", type=int, required=True)
A = ap.parse_args()
EV = Path(A.ev).resolve()
FREEZE = Path(A.freeze).resolve()

ROLES = {
    "guards": "identity-guard transcript",
    "cells": "cell evidence record",
    "commands": "command record",
    "fixtures": "CORE-3 evidence-input fixture record",
    "identities": "identity record",
    "results": "result record",
    "oracles": "oracle byte-copy",
    "harness": "certifying harness file",
    "guard-tmp": "pre-guard fresh-DB scratch (verbatim §6.4 command)",
    "run": "run database/state",
}

entries = []
for p in sorted(EV.rglob("*")):
    if not p.is_file():
        continue
    rel = p.relative_to(EV).as_posix()
    if rel in ("MANIFEST.json", "results/run-record.json"):
        continue
    if "__pycache__" in rel:
        continue
    b = p.read_bytes()
    top = rel.split("/")[0]
    entries.append({
        "path": rel, "bytes": len(b), "sha256": sha256(b),
        "role": ROLES.get(top, "auxiliary evidence"),
    })

manifest_b = (json.dumps(
    {"generated_utc": datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"),
     "entries": entries}, indent=1) + "\n").encode()
(EV / "MANIFEST.json").write_bytes(manifest_b)

# frozen-spec identity parsed mechanically from Part II §A
spec_path = next((FREEZE / "spec").glob(
    "SoloRing-Post-M16-Integrated-Sequence-Regression-R3.md"))
spec_text = spec_path.read_text(encoding="utf-8")
frozen_pi_bytes = int(re.search(
    r"part_i_byte_count: (\d+)", spec_text).group(1))
frozen_pi_sha = re.search(
    r"part_i_sha256: ([0-9a-f]{64})", spec_text).group(1)

ledger = json.loads(
    (EV / "results/coverage-ledger.json").read_text(encoding="utf-8"))
cells = ledger["cells"]
req = [c for c in cells if c["pass_gate"] == "REQUIRED"]
req_pass = [c for c in req if c["execution_status"] == "PASS"]
b_cells = [c for c in cells if c["pass_gate"] == "OPTIONAL"]


def guard_line(name: str) -> str:
    t = (EV / "guards" / name).read_text(encoding="utf-8")
    m = re.search(r"^guard_exit=(\d+)$", t, re.M)
    return m.group(1) if m else "MISSING"


pre_exit = guard_line("identity-guard-tier-a-pre.log")
post_exit = guard_line("identity-guard-tier-a-post.log")
guards_ok = pre_exit == "0" and post_exit == "0" and A.pre_rc == 0 \
    and A.post_rc == 0
required_ok = len(req_pass) == len(req) == 64
disposition = ("PASS" if (guards_ok and A.driver_rc == 0
                          and required_ok) else "FAIL")

run_record = {
    "run": "R3-TIER-A-RUN1",
    "specification": {
        "name": "SoloRing-Post-M16-Integrated-Sequence-Regression-R3",
        "frozen_part_i_bytes": frozen_pi_bytes,
        "frozen_part_i_sha256": frozen_pi_sha,
        "evidence_root": "post-m16-integrated-r3-evidence/ "
        "(frozen §20 layout; the R1-era inherited root name is not "
        "used by R3)",
    },
    "certifying_baseline": {
        "commit": "8199e46da6b8592f606725059601b402ab2874b0",
        "tree": "941d14cda84d0186431a80c0f9cbdc3fa978296b",
        "parent": "488031a2b7d0070d23425bbe04b86d9f9f16e0bd",
        "same_product_baseline_as_r2": True,
    },
    "guards": {"pre_exit": pre_exit, "post_exit": post_exit,
               "wrappers_verbatim": True,
               "startup_adapter_used": False,
               "transcripts": ["guards/identity-guard-tier-a-pre.log",
                               "guards/identity-guard-tier-a-post.log"]},
    "driver_exit": A.driver_rc,
    "cells": {"required_total": len(req), "required_pass":
              len(req_pass), "optional_not_executed":
              sum(1 for c in b_cells
                  if c["execution_status"] == "NOT_EXECUTED"),
              "total": len(cells)},
    "disposition": disposition,
    "harness": {
        "driver": "harness/r3_tier_a.py",
        "driver_sha256": sha256(
            (EV / "harness/r3_tier_a.py").read_bytes()),
    },
    "manifest": {"sha256": sha256(manifest_b),
                 "bytes": len(manifest_b),
                 "entry_count": len(entries)},
}
norm_path = EV / "results/normalization-record.json"
if norm_path.exists():
    run_record["normalization"] = json.loads(
        norm_path.read_text(encoding="utf-8"))
if disposition == "PASS":
    run_record["g8_disposition_statement"] = (
        "POST-M16 INTEGRATED PRODUCTION-WORLD REGRESSION: PASS. The "
        "implemented M11\u2013M16 production-world chain remains "
        "coherent on the exact R3 correction baseline (§0.2) derived "
        "from published M16. The roadmap prerequisite for entering G8 "
        "is satisfied. G8 remains OPEN. No M17 implementation is "
        "authorized.")
rr_b = (json.dumps(run_record, indent=1) + "\n").encode()
(EV / "results/run-record.json").write_bytes(rr_b)

ZIP = EV.parent / ("SoloRing-Post-M16-R3-TierA-Run1-NORMALIZED-"
                   "2026-09-19.zip")
with zipfile.ZipFile(ZIP, "w") as z:
    for rel in [e["path"] for e in entries] + \
            ["MANIFEST.json", "results/run-record.json"]:
        zi = zipfile.ZipInfo(rel, date_time=(2026, 9, 19, 0, 0, 0))
        zi.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(zi, (EV / rel).read_bytes())

print(f"entries={len(entries)} disposition={disposition} "
      f"required={len(req_pass)}/{len(req)} pre={pre_exit} "
      f"post={post_exit} driver={A.driver_rc}")
print(f"MANIFEST.json {len(manifest_b)} B / {sha256(manifest_b)}")
print(f"ZIP {ZIP.name} {ZIP.stat().st_size} B / "
      f"{sha256(ZIP.read_bytes())}")
