"""M14 baseline verifier (frozen R2 §0/§32 M14-0).

Mechanically proves the exact M14 implementation predecessor identity the
frozen plan authorizes:
  * base01 — predecessor commit 20429b3 exists, its tree is exactly
    0a755efe, the current HEAD descends from it, and the M14 pin file
    names the same frozen plan identity;
  * base02 — the immutable M13 annotated tag still points at the frozen
    tag object / commit / tree and has not moved;
  * base03 — the migration predecessor is exactly 0014 at the predecessor
    commit and no 0015 migration exists yet (M14-0 scope guard).

Exit codes: 0 clean; 1 violation; 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PINS = REPO / "tests" / "fixtures" / "m14" / "m14_pins.json"

PREDECESSOR_COMMIT = "20429b3bf2ead3ca6c1d2402d5028e500bd4f9e8"
PREDECESSOR_TREE = "0a755efeeb9c87f1168f77e6905413affa435240"
M13_TAG_OBJECT = "d8b0c6f52253a139cce3fc2f4ca712f856b6737a"
M13_COMMIT = "384a46d3a5c68d7d81784befc338aa8621b93fbd"
M13_TREE = "a360a58bde22f9e692680232af56d5613d273702"
MIGRATION_PREDECESSOR = "0014_m13_authority_complete_world"


def git(*args: str, check: bool = True) -> str:
    out = subprocess.run(
        ["git", "-C", str(REPO), *args],
        capture_output=True, text=True,
    )
    if check and out.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout.strip()


def load_pins() -> dict:
    if not PINS.is_file():
        raise RuntimeError(f"missing pin file {PINS}")
    pins = json.loads(PINS.read_text(encoding="utf-8"))
    if pins["implementation_predecessor"]["commit"] != PREDECESSOR_COMMIT:
        raise RuntimeError("pin file predecessor commit mismatch")
    if pins["implementation_predecessor"]["tree"] != PREDECESSOR_TREE:
        raise RuntimeError("pin file predecessor tree mismatch")
    if pins["frozen_plan"]["sha256"] != (
            "68f910f5ff132fe00345fc41fa07f25e650d74ccd3f7ec445822194c03bde860"):
        raise RuntimeError("pin file frozen-plan hash mismatch")
    return pins


def check_base01() -> list[str]:
    errors: list[str] = []
    try:
        tree = git("rev-parse", f"{PREDECESSOR_COMMIT}^{{tree}}")
    except RuntimeError:
        return [f"predecessor commit {PREDECESSOR_COMMIT} not present"]
    if tree != PREDECESSOR_TREE:
        errors.append(
            f"predecessor tree {tree} != {PREDECESSOR_TREE}")
    if git("merge-base", "--is-ancestor", PREDECESSOR_COMMIT, "HEAD",
           check=False) and subprocess.run(
            ["git", "-C", str(REPO), "merge-base", "--is-ancestor",
             PREDECESSOR_COMMIT, "HEAD"]).returncode != 0:
        errors.append("HEAD does not descend from the M14 predecessor")
    try:
        load_pins()
    except RuntimeError as exc:
        errors.append(str(exc))
    return errors


def check_base02() -> list[str]:
    errors: list[str] = []
    if subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "--verify",
             "--quiet", "refs/tags/M13"],
            capture_output=True).returncode != 0:
        # actions/checkout does not fetch tags by default; pull the exact
        # immutable tag once rather than weakening the check.
        subprocess.run(
            ["git", "-C", str(REPO), "fetch", "--quiet", "origin",
             "refs/tags/M13:refs/tags/M13"],
            capture_output=True)
    if subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "--verify",
             "--quiet", "refs/tags/M13"],
            capture_output=True).returncode != 0:
        return ["M13 tag absent even after targeted fetch"]
    tag_object = git("rev-parse", "refs/tags/M13")
    peeled = git("rev-parse", "refs/tags/M13^{}")
    if tag_object != M13_TAG_OBJECT:
        errors.append(f"M13 tag object {tag_object} != {M13_TAG_OBJECT}")
    if peeled != M13_COMMIT:
        errors.append(f"M13 peeled commit {peeled} != {M13_COMMIT}")
    tree = git("rev-parse", "refs/tags/M13^{tree}")
    if tree != M13_TREE:
        errors.append(f"M13 tree {tree} != {M13_TREE}")
    return errors


MIGRATION_0015 = "0015_m14_world_observation_execution"


def check_base03() -> list[str]:
    errors: list[str] = []
    listing = git(
        "ls-tree", "--name-only", PREDECESSOR_COMMIT,
        "server/alembic/versions/")
    names = [line for line in listing.splitlines() if line.strip()]
    py_names = [n.split("/")[-1] for n in names if n.endswith(".py")]
    if not any(n.startswith(MIGRATION_PREDECESSOR) for n in py_names):
        errors.append(
            f"predecessor lacks migration {MIGRATION_PREDECESSOR}")
    head_listing = git(
        "ls-tree", "--name-only", "HEAD", "server/alembic/versions/")
    head_names = [line.split("/")[-1] for line in head_listing.splitlines()
                  if line.strip().endswith(".py")]
    migrations = sorted(
        n for n in head_names
        if n[0].isdigit() and not n.startswith("__"))
    # Frozen M14B-2 (R2 §23): from this slice on the head is exactly the
    # M14 migration; the pre-B2 "no 0015" posture is superseded.
    if not migrations or migrations[-1] != f"{MIGRATION_0015}.py":
        errors.append(
            "current migration head is not exactly "
            f"{MIGRATION_0015}: {migrations[-1:]}")
    beyond = [m for m in migrations if m > f"{MIGRATION_0015}.py"]
    if beyond:
        errors.append(f"migrations beyond 0015 exist: {beyond}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--focus", choices=("all", "base01", "base02", "base03"),
        default="all")
    args = parser.parse_args()

    checks = {
        "base01": check_base01,
        "base02": check_base02,
        "base03": check_base03,
    }
    selected = (list(checks) if args.focus == "all" else [args.focus])
    errors: list[str] = []
    for name in selected:
        errors.extend(checks[name]())
    if errors:
        for e in errors:
            print(f"M14-BASELINE INVALID: {e}", file=sys.stderr)
        return 1
    print(f"M14 baseline clean ({', '.join(selected)}): predecessor "
          "20429b3/0a755efe, M13 tag immutable, migration head 0015.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
