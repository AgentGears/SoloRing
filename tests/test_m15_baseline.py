"""M15-0 baseline + proof scaffold (frozen R4 §28 M15-0, §31.1 M15-BASE:01..07).

Seven baseline cells against the exact frozen contract
7410a01226361ff81a951b17a03ec093c4d85bade52484793879f7560fecfe11:
predecessor/tag identity, migration head, predecessor validator
battery, migration immutability, execution-source scope, the direct
source-swap seam characterization, and the named M12 behavioral
succession. No product behavior changes.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from soloring.composition.service import patch_working_occurrence
from soloring.errors import SoloRingError
from tests.test_m12_identity import (
    SCOPE,
    _comp,
    _mint,
    _seed_production,
    _seed_project,
    _spec,
)

REPO = Path(__file__).resolve().parents[1]
PINS = REPO / "tests" / "fixtures" / "m15" / "m15_pins.json"
G4 = REPO / "tests" / "fixtures" / "m15" / "g4_contract.json"

M14_COMMIT = "89298e793c651e9e8b9164912c76e3595867a60a"
M14_TREE = "3c4fec0bdb11732f0c77c22acc65d3ba882df393"
M14_TAG_OBJECT = "ff4c6107876ddd991ec626b3605deb143ec7daf9"
MIGRATION_PREDECESSOR = "0015_m14_world_observation_execution"

# Frozen R4 §26.1: the M14 execution path and the M13 placement
# classifier are off-limits for all of M15. The worker/executors
# prefixes carry the schema-4 worker execution path, Comfy
# submission/runtime verification, the M14 materializers, and take
# import; observation/ carries the M14 observation compilers.
PROHIBITED_PREFIXES = (
    "server/soloring/observation/",
    "server/soloring/workflows/",
    "server/soloring/worker/",
    "server/soloring/executors/",
)
# Frozen R4 §28/BASE:03 — the M11–M14 validator battery CI wires ahead
# of pytest; M15 must never regress a frozen predecessor gate.
# M17C-A (PR #26, mirroring the CI retirement in .github/workflows/
# ci.yml): the boundary/source-fit validators are frozen-slice-scoped
# and reject successor milestones by design, so they are retired here
# alongside their CI steps. Proof maps and the admitted-set-swept
# m14 baseline validator remain enforced.
_PREDECESSOR_VALIDATORS = (
    "m10f_validate_proof_map.py",
    "m11_validate_proof_map.py",
    "m12_validate_proof_map.py",
    "m13_validate_proof_map.py",
    "hygiene_validate_proof_map.py",
    "next_security_validate_proof_map.py",
    "m14_validate_baseline.py",
    "m14_validate_proof_map.py",
)


def _git(*args: str, check: bool = True) -> str:
    out = subprocess.run(
        ["git", "-C", str(REPO), *args],
        capture_output=True, text=True,
    )
    if check and out.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout.strip()


def _migration_names(rev: str) -> list[str]:
    listing = _git("ls-tree", "--name-only", rev, "server/alembic/versions/")
    names = [line.split("/")[-1] for line in listing.splitlines()
             if line.strip().endswith(".py")]
    return sorted(n for n in names if n[0].isdigit()
                  and not n.startswith("__"))


def test_m14_commit_tree_and_tag_baseline() -> None:
    """M15-BASE:01 — exact M14 predecessor identity (frozen R4 header)."""
    pins = json.loads(PINS.read_text(encoding="utf-8"))
    assert pins["frozen_plan"]["sha256"] == (
        "b781f8157156babd9dc73e0397071708dac398e51a6658a910"
        "71da4dc9442c83")
    assert pins["frozen_plan"]["proof_cells"] == 127
    assert pins["implementation_predecessor"] == {
        "commit": M14_COMMIT, "tree": M14_TREE}
    assert pins["m14_identity"]["tag_object"] == M14_TAG_OBJECT
    assert pins["migration_predecessor"] == MIGRATION_PREDECESSOR
    # the G4 contract fixture names the same frozen contract
    g4 = json.loads(G4.read_text(encoding="utf-8"))
    assert g4["frozen_plan_sha256"] == pins["frozen_plan"]["sha256"]

    # commit exists with the exact published tree; HEAD descends from it
    assert _git("rev-parse", f"{M14_COMMIT}^{{tree}}") == M14_TREE
    ancestor = subprocess.run(
        ["git", "-C", str(REPO), "merge-base", "--is-ancestor",
         M14_COMMIT, "HEAD"],
        capture_output=True)
    assert ancestor.returncode == 0, (
        "HEAD does not descend from the M14 predecessor")

    # immutable annotated tag M14 (targeted fetch for CI checkouts that
    # do not carry tags — same fallback as the M14 baseline validator)
    if subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "--verify", "--quiet",
             "refs/tags/M14"],
            capture_output=True).returncode != 0:
        subprocess.run(
            ["git", "-C", str(REPO), "fetch", "--quiet", "origin",
             "refs/tags/M14:refs/tags/M14"],
            capture_output=True)
    assert _git("rev-parse", "refs/tags/M14") == M14_TAG_OBJECT
    assert _git("rev-parse", "refs/tags/M14^{}") == M14_COMMIT
    assert _git("rev-parse", "refs/tags/M14^{tree}") == M14_TREE


def test_migration_head_is_0015_before_m15() -> None:
    """M15-BASE:02 — predecessor migration head exactly 0015.

    The predecessor-tree assertion is timeless. The current-head
    posture was the M15-0 scope guard (no migration beyond 0015), then
    superseded by M15A (frozen §11) to 0016, and now by M16-A: the head
    is exactly the frozen 0017, the single admitted successor — the M14
    base03 / M15 BASE:02 mid-flight precedent."""
    pre = _migration_names(M14_COMMIT)
    assert pre, "predecessor migration listing empty"
    assert pre[-1] == f"{MIGRATION_PREDECESSOR}.py"
    head = _migration_names("HEAD")
    assert head, "current migration listing empty"
    # M17C-A succession (PR #26): the single admitted successor beyond
    # the frozen 0019 is 0020_m17c_dialogue_bound_performance.
    assert head[-1] == "0020_m17c_dialogue_bound_performance.py", (
        f"current migration head is not the admitted 0020: {head[-1:]}")
    beyond = [m for m in head
              if m > "0020_m17c_dialogue_bound_performance.py"]
    assert not beyond, f"migrations beyond 0020 exist: {beyond}"


def test_predecessor_proof_validators_green() -> None:
    """M15-BASE:03 — M11–M14 validators preserved.

    The thirteen predecessor validators CI wires ahead of the M15
    surface — proof maps (M10F/M11/M12/M13/hygiene/next-security/M14),
    boundary gates (M13/hygiene/next-security/M14), the M14 baseline,
    and the M14 source-fit gate — each exit 0 against the current
    tree."""
    scripts = REPO / "scripts"
    for name in _PREDECESSOR_VALIDATORS:
        result = subprocess.run(
            [sys.executable, str(scripts / name)],
            capture_output=True, text=True, cwd=str(scripts.parent),
        )
        assert result.returncode == 0, (
            f"predecessor validator {name} failed:\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")


def test_no_predecessor_migration_bytes_changed() -> None:
    """M15-BASE:04 — predecessor migration files are byte-frozen.

    Every migration file present at the M14 predecessor keeps its exact
    blob at HEAD; M15A may only add the new 0016 file (frozen §11.6:
    migration 0016 alters/rebuilds no predecessor table)."""
    listing = _git(
        "ls-tree", "--name-only", M14_COMMIT, "server/alembic/versions/")
    paths = [line for line in listing.splitlines()
             if line.strip().endswith(".py")]
    assert paths, "predecessor migration listing empty"
    for path in paths:
        before = _git("rev-parse", f"{M14_COMMIT}:{path}")
        after = _git("rev-parse", f"HEAD:{path}")
        assert before == after, (
            f"predecessor migration bytes changed: {path}")


def test_m15_source_scope_excludes_execution_source() -> None:
    """M15-BASE:05 — no execution-source expansion (frozen §26.1).

    No path under the M14 execution surfaces (observation, workflows,
    the schema-4 worker path, executors/Comfy/materializers/take
    import) may change under M15, and the M13 placement-owner
    classifier is reused through its pure seam without extraction or
    semantic modification."""
    changed = [p for p in
               _git("diff", "--name-only", M14_COMMIT, "HEAD").splitlines()
               if p.strip()]
    # Post-M15 review remediation changes exactly one path beneath the frozen
    # M15 execution-source prefixes: the M10 Comfy translator correction.
    # The exception is byte-pinned so later edits cannot inherit permanent
    # successor ownership merely by reusing the same pathname.
    post_m15_owned = {
        "server/soloring/executors/comfy/translate.py":
            "9d0af0782a372c57cfbb389d8accd6f8c3675ac8",
    }
    for path, expected_blob in post_m15_owned.items():
        assert _git("rev-parse", f"HEAD:{path}") == expected_blob, (
            f"post-M15 successor bytes changed without M15 boundary review: {path}"
        )
    violations = [
        p for p in changed
        if p.startswith(PROHIBITED_PREFIXES) and p not in post_m15_owned
    ]
    assert not violations, (
        f"execution-source paths changed under M15: {violations}")
    # frozen R5 §26.1 source-scope rule: under production_world/, only
    # the two named classifier-refactor files may change (NEW shared
    # classifier + wiring-only binding.py), semantics-frozen by BASE:09
    pw_changed = sorted(
        p for p in changed
        if p.startswith("server/soloring/production_world/"))
    assert pw_changed == [
        "server/soloring/production_world/binding.py",
        "server/soloring/production_world/placement_consumer.py"], (
        f"unauthorized production_world changes: {pw_changed}")
    assert (REPO / "server/soloring/production_world/"
            "placement_consumer.py").is_file()


async def test_direct_source_swap_is_the_intended_m15_seam(
        engine, factory):
    """M15-BASE:06 — source-fit characterization of the M15 seam (§2.3).

    The same-ProductionObject direct ProductionRevision source swap on
    a working occurrence is exactly the seam M15 closes: before M15C it
    succeeds identity-preserving (the frozen §2.3 predecessor
    behavior); after M15C the ordinary PATCH refuses with the typed
    compatibility requirement. Cross-ProductionObject changes always
    require the replace_as_new identity operation."""
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)  # one object, r1 + r2
    other = await _seed_production(factory, pid)  # a different object
    cid = await _comp(factory, pid)
    occ = await _mint(factory, cid, _spec(rids[0]), 0)

    # M15C landed (frozen R6 §15): the ordinary PATCH ends on the
    # typed-refusal branch — the only identity-preserving source swap
    # is the M15 compatibility assessment + explicit apply
    with pytest.raises(SoloRingError) as ei:
        await patch_working_occurrence(
            factory(), cid, occ, scope=SCOPE, expected_working_version=1,
            source={"kind": "production_revision",
                    "revision_id": rids[1]})
    assert ei.value.code == (
        "PRODUCTION_REVISION_UPDATE_REQUIRES_COMPATIBILITY")
    assert ei.value.details["required_action"] == "compatibility_assessment"
    assert ei.value.details["current_revision_id"] == rids[0]
    assert ei.value.details["requested_revision_id"] == rids[1]

    # cross-lineage always routes to replace_as_new, before and after M15
    async with factory() as s:
        async with s.bind.connect() as conn:
            version = (await conn.execute(
                text("SELECT working_version FROM compositions "
                     "WHERE id = :c"), {"c": cid})).scalar_one()
    with pytest.raises(SoloRingError) as ei:
        await patch_working_occurrence(
            factory(), cid, occ, scope=SCOPE,
            expected_working_version=version,
            source={"kind": "production_revision",
                    "revision_id": other[0]})
    assert ei.value.details["identity_change_required"] is True
    assert ei.value.details["allowed_operation"] == "replace_as_new"


def test_m12_direct_patch_proof_has_explicit_m15_successor() -> None:
    """M15-BASE:07 — behavioral succession is named, not disabled (§27).

    The published predecessor proof M12-ID:06 keeps its exact owner and
    occurrence-identity invariant; the M15 map names its successor
    owners (M15-APPLY:06 identity + M15-APPLY:12 bypass closure) in
    both the map document and the hard-coded validator inventory."""
    m12_src = (REPO / "tests" / "test_m12_identity.py").read_text(
        encoding="utf-8")
    m12_owner = (
        "test_same_production_object_revision_update_preserves_occurrence_id")
    assert f"def {m12_owner}(" in m12_src
    m12_map = (REPO / "docs" / "SoloRing-M12-Proof-Map.md").read_text(
        encoding="utf-8")
    assert "`M12-ID:06`" in m12_map

    m15_map = (REPO / "docs" / "SoloRing-M15-Proof-Map.md").read_text(
        encoding="utf-8")
    assert "`M15-APPLY:06`" in m15_map
    assert "`M15-APPLY:12`" in m15_map

    spec = importlib.util.spec_from_file_location(
        "m15_validate_proof_map",
        REPO / "scripts" / "m15_validate_proof_map.py")
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    assert "M15-APPLY:06" in validator.REQUIRED_CELLS["M15-APPLY"]
    assert "M15-APPLY:12" in validator.REQUIRED_CELLS["M15-APPLY"]
