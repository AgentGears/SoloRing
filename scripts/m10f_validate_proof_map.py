"""M10F proof-map validator (R5 §16/§16.1).

Validates SoloRing-M10F-Proof-Map.md for:
  * closed disposition vocabulary (TEST / STRUCTURAL / INHERITED /
    NOT-APPLICABLE-SOURCE-FIT) — anything else is rejected;
  * numbered-domain completeness (frozen required key sets: 24 M10 spatial
    error codes, 12 derived error codes, 19 §61 race classes, 10 M10D §66
    composed families, 25 umbrella corruption cells, 31 recovery cells,
    10 determinism classes, the compatibility lattice, scale obligations,
    and the 3 canonical demonstrations);
  * pytest owner resolution against `pytest --collect-only -q` using the
    closed rule: a function owner matches a collected node exactly or on a
    function-boundary prefix (`name[`); an owner carrying `[param]` must
    equal one collected node exactly; textual prefixes are forbidden;
  * NOT-APPLICABLE-SOURCE-FIT entries must carry a rationale naming the
    absent mechanism plus a substitute executable/source owner that itself
    resolves;
  * duplicate obligation keys and dangling owners are rejected;
  * a closure-command appendix for non-pytest commands (compileall,
    frontend gate, archive fidelity, live GPU evidence) whose entries are
    never misrepresented as pytest owners.

Self-tests prove the parameterized-owner rules and that removing recovery
cell 31 from an otherwise valid map fails completeness.

Exit codes: 0 valid; 1 invalid; 2 usage error.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

DISPOSITIONS = ("TEST", "STRUCTURAL", "INHERITED",
                "NOT-APPLICABLE-SOURCE-FIT")

M10_ERROR_CODES = (
    "SPATIAL_WORLD_INVALID", "SPATIAL_WORLD_STATE_INVALID",
    "SPATIAL_WORLD_CAPTURE_CONFLICT", "SPATIAL_FRAME_INVALID",
    "SPATIAL_FRAME_CYCLE", "SPATIAL_AXIS_INVALID",
    "SPATIAL_WORLD_REVISION_NOT_FOUND", "SPATIAL_WORLD_APPROVAL_CONFLICT",
    "SPATIAL_TRACK_INVALID", "SPATIAL_ENTITY_INSTANCING_UNSUPPORTED",
    "SPATIAL_TRANSITION_INVALID", "SPATIAL_SHOT_PLAN_INVALID",
    "SPATIAL_SHOT_PLAN_CONFLICT", "SPATIAL_CONTEXT_AMBIGUOUS",
    "SPATIAL_SHOT_PLAN_REQUIRED", "SPATIAL_WORLD_STATE_REQUIRED",
    "SPATIAL_WORLD_APPROVAL_REQUIRED", "SPATIAL_TRACK_STATE_REQUIRED",
    "SPATIAL_ENTITY_PLACEMENT_CONFLICT", "SPATIAL_ENTITY_REVISION_MISMATCH",
    "SPATIAL_BLOCKING_STATE_MISMATCH", "SPATIAL_AXIS_CONSTRAINT_VIOLATION",
    "SPATIAL_REALIZATION_UNSUPPORTED", "SPATIAL_REALIZATION_BINDING_INVALID",
)
DERIVED_ERROR_CODES = (
    "DERIVED_SPATIAL_SPEC_INVALID", "DERIVED_SPATIAL_KIND_UNSUPPORTED",
    "DERIVED_SPATIAL_RUNTIME_UNPINNABLE", "DERIVED_SPATIAL_NONDETERMINISTIC",
    "DERIVED_SPATIAL_MATERIALIZATION_FAILED", "DERIVED_SPATIAL_OUTPUT_INVALID",
    "DERIVED_SPATIAL_PROVENANCE_MISMATCH", "DERIVED_SPATIAL_BLOB_MISSING",
    "DERIVED_SPATIAL_BLOB_CORRUPT", "DERIVED_SPATIAL_CAPTURE_CONFLICT",
    "DERIVED_SPATIAL_BINDING_INVALID", "DERIVED_SPATIAL_HARD_COMPONENT_LOSS",
)

REQUIRED_DOMAINS: dict[str, tuple[str, ...]] = {
    "ERROR": tuple(M10_ERROR_CODES) + tuple(DERIVED_ERROR_CODES),
    "RACE61": tuple(str(i) for i in range(1, 20)),
    "RACEM10D": tuple(f"66.{i}" for i in range(1, 11)),
    "CORRUPT": tuple(str(i) for i in range(1, 26)),
    "RECOVERY": tuple(str(i) for i in range(1, 32)),
    "DETERM": tuple(str(i) for i in range(1, 11)),
    "COMPAT": (
        "shotrev-1", "shotrev-2", "shotrev-3", "shotrev-4", "shotrev-5",
        "pkg1-empty-v1", "pkg2-empty-v1", "pkg2-m8-v2", "pkg12-m10-blocked",
        "pkg3-empty-v1-fallback", "pkg3-m8-v2-fallback", "pkg3-m10-only-v3",
        "pkg3-m8-m10-v3", "rerun-no-upgrade", "worker-retained-artifacts",
        "runtime-drift-executability-only",
    ),
    "SCALE": (
        "fixture-determinism", "resolution-bounded", "capture-bounded",
        "generation-cold-bounded", "no-fanout", "metrics-recorded",
    ),
    "DEMO": ("lobby-reverse-angle", "moving-character", "cross-domain"),
    "BACKUPALGO": (
        "posture-db-url", "posture-blob-dir", "posture-default",
        "manifest-grammar", "finalize-contract", "ordering-blob",
        "ordering-artifacts", "fk-completeness", "full-cycle",
        "source-write-coherence", "legacy-d0-path",
    ),
    "ISOLATION": (
        "authority-write-spy", "shot-revisions-positive-control",
        "inventory-parity", "worker-zero-current-m10",
        "rerun-zero-current-m10", "current-read-positive-control",
        "rerun-zero-rematerialization", "drift-identity-stability",
    ),
}

_ROW = re.compile(
    r"^\|\s*([A-Z0-9_]+:[A-Za-z0-9_.\-]+)\s*\|"
    r"\s*([A-Z\-]+)\s*\|"
    r"\s*([^|]*?)\s*\|"
    r"\s*([^|]*?)\s*\|\s*$"
)
_APPENDIX = re.compile(
    r"^\|\s*(CMD:[A-Za-z0-9_.\-]+)\s*\|"
    r"\s*([^|]+?)\s*\|"
    r"\s*([^|]+?)\s*\|\s*$"
)


def parse_map(text: str) -> tuple[dict[str, dict], list[tuple], list[str]]:
    entries: dict[str, dict] = {}
    appendix: list[tuple] = []
    problems: list[str] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if line.startswith("| CMD:"):
            m = _APPENDIX.match(line)
            if not m:
                problems.append(f"line {lineno}: malformed appendix row")
                continue
            key, command, owner = m.group(1), m.group(2), m.group(3)
            if key in entries or any(k == key for k, _, _ in appendix):
                problems.append(f"line {lineno}: duplicate appendix key {key}")
            appendix.append((key, command, owner))
            continue
        m = _ROW.match(line)
        if not m:
            if re.match(r"^\|\s*[A-Z0-9_]+:", line):
                problems.append(f"line {lineno}: malformed obligation row")
            continue
        key, disposition, owner, note = m.groups()
        if disposition not in DISPOSITIONS:
            problems.append(
                f"line {lineno}: unknown disposition {disposition!r} "
                f"for {key}")
            continue
        if key in entries:
            problems.append(f"line {lineno}: duplicate obligation key {key}")
        entries[key] = {
            "disposition": disposition,
            "owner": owner.strip(),
            "note": note.strip(),
            "line": lineno,
        }
    return entries, appendix, problems


def collect_nodes(python: str) -> list[str]:
    out = subprocess.run(
        [python, "-m", "pytest", "--collect-only", "-q"],
        cwd=str(REPO), capture_output=True, text=True, check=True,
    ).stdout
    nodes = []
    for line in out.splitlines():
        line = line.strip()
        if "::" in line and not line.startswith(("=", "！", "tests failed")):
            nodes.append(line)
    return nodes


def resolve_owner(owner: str, nodes: list[str]) -> list[str]:
    """Closed rule: exact node, exact-with-parameter, or function-boundary
    prefix (`name[`). Any other prefix match is ambiguous and forbidden."""
    if "[" in owner:
        return [n for n in nodes if n == owner]
    prefix = owner + "["
    return [n for n in nodes if n == owner or n.startswith(prefix)]


def validate(
    entries: dict[str, dict], appendix: list[tuple], nodes: list[str]
) -> list[str]:
    problems: list[str] = []

    for domain, required in REQUIRED_DOMAINS.items():
        for ident in required:
            key = f"{domain}:{ident}"
            if key not in entries:
                problems.append(f"completeness: missing {key}")

    for key, e in sorted(entries.items()):
        domain = key.split(":", 1)[0]
        if domain not in REQUIRED_DOMAINS:
            problems.append(f"{key}: unknown domain {domain!r}")
            continue
        ident = key.split(":", 1)[1]
        if ident not in REQUIRED_DOMAINS[domain]:
            problems.append(f"{key}: unknown {domain} obligation id {ident!r}")

        if e["disposition"] == "NOT-APPLICABLE-SOURCE-FIT":
            note = e["note"]
            substitute = e["owner"]
            if not note or "source" not in note.lower():
                problems.append(
                    f"{key}: N/A-SOURCE-FIT requires a rationale naming the "
                    "absent mechanism/source path")
            if not substitute:
                problems.append(
                    f"{key}: N/A-SOURCE-FIT requires a substitute owner")
            elif substitute.startswith("CMD:"):
                if not any(k == substitute for k, _, _ in appendix):
                    problems.append(
                        f"{key}: substitute {substitute} not in the "
                        "closure-command appendix")
            elif not resolve_owner(substitute, nodes):
                problems.append(
                    f"{key}: N/A-SOURCE-FIT substitute {substitute!r} does "
                    "not resolve")
            continue

        owner = e["owner"]
        if not owner:
            problems.append(f"{key}: {e['disposition']} requires an owner")
            continue
        if owner.startswith("CMD:"):
            problems.append(
                f"{key}: pytest-owned obligation may not point at the "
                "closure-command appendix ({owner})")
            continue
        matches = resolve_owner(owner, nodes)
        if not matches:
            problems.append(f"{key}: owner {owner!r} does not resolve")
        elif "[" not in owner and len(matches) == 0:
            problems.append(f"{key}: ambiguous owner {owner!r}")

    seen_cmd: set[str] = set()
    for key, command, owner in appendix:
        if key in seen_cmd:
            problems.append(f"{key}: duplicate appendix key")
        seen_cmd.add(key)
        if not command.strip() or not owner.strip():
            problems.append(f"{key}: appendix rows need command + owner")
    return problems


def summary(entries: dict, appendix: list, nodes: list) -> str:
    lines = [
        f"proof-map entries: {len(entries)}",
        f"closure-command appendix entries: {len(appendix)}",
        f"collected pytest nodes: {len(nodes)}",
    ]
    for domain in sorted(REQUIRED_DOMAINS):
        required = len(REQUIRED_DOMAINS[domain])
        present = sum(
            1 for ident in REQUIRED_DOMAINS[domain]
            if f"{domain}:{ident}" in entries)
        lines.append(f"domain {domain}: {present}/{required}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Self-tests (§16.1 items 9-10) — no pytest required
# ---------------------------------------------------------------------------

def self_test() -> list[str]:
    failures: list[str] = []
    nodes = [
        "tests/test_x.py::test_param[one]",
        "tests/test_x.py::test_param[two]",
        "tests/test_x.py::test_param[three]",
        "tests/test_x.py::test_plain",
    ]

    m = resolve_owner("tests/test_x.py::test_param", nodes)
    if len(m) != 3:
        failures.append(f"3-param function owner resolved {len(m)} nodes")
    if resolve_owner("tests/test_x.py::test_param[two]", nodes) != [
            "tests/test_x.py::test_param[two]"]:
        failures.append("exact parameter owner did not resolve one node")
    if resolve_owner("tests/test_x.py::test_param[nope]", nodes):
        failures.append("unknown parameter owner resolved")

    def synth_entries(with_cell31: bool = True):
        ents: dict[str, dict] = {}
        for domain, req in REQUIRED_DOMAINS.items():
            for ident in req:
                if domain == "RECOVERY" and ident == "31" and not with_cell31:
                    continue
                ents[f"{domain}:{ident}"] = {
                    "disposition": "TEST",
                    "owner": "tests/test_x.py::test_plain",
                    "note": "", "line": 0,
                }
        return ents

    problems_full = validate(synth_entries(True), [], nodes)
    completeness = [p for p in problems_full if "completeness" in p]
    if completeness:
        failures.append(f"synthetic complete map flagged: {completeness[:2]}")
    problems_missing = validate(synth_entries(False), [], nodes)
    if not any("RECOVERY:31" in p for p in problems_missing):
        failures.append("removing recovery cell 31 did not fail completeness")
    return failures


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="m10f_validate_proof_map")
    p.add_argument("map", nargs="?", type=Path,
                   default=REPO / "SoloRing-M10F-Proof-Map.md")
    p.add_argument("--python", default=sys.executable)
    p.add_argument("--collect", default=None, type=Path,
                   help="pre-collected pytest node list (one per line) "
                        "instead of running pytest")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args(argv)

    if args.self_test:
        failures = self_test()
        for f in failures:
            print(f"SELF-TEST FAIL: {f}", file=sys.stderr)
        print("self-test:", "PASS" if not failures else "FAIL")
        return 0 if not failures else 1

    if not args.map.is_file():
        print(f"map not found: {args.map}", file=sys.stderr)
        return 2
    entries, appendix, problems = parse_map(args.map.read_text(
        encoding="utf-8"))
    if args.collect is not None:
        nodes = [
            l.strip() for l in
            args.collect.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    else:
        nodes = collect_nodes(args.python)
    problems += validate(entries, appendix, nodes)
    print(summary(entries, appendix, nodes))
    if problems:
        print(f"\nINVALID ({len(problems)} problems):")
        for pr in problems:
            print(f"  - {pr}")
        return 1
    print("VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
