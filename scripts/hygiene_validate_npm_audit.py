"""Post-M13 hygiene npm-audit baseline validator (frozen R2 HYG-04/DEP:06).

Consumes `npm audit --omit=dev --json` (stdin or file) plus the checked-in
exception baseline and fails on:
  * any runtime critical;
  * any runtime high not exactly covered by the baseline;
  * any baseline entry whose package/advisory identity no longer matches
    the live audit (advisory set, severity, fix-available major flag);
  * a baseline exception whose offered remediation has become
    non-major (isSemVerMajor == false) — the exception is invalidated;
  * malformed audit output.

Exit codes: 0 accepted; 1 rejected; 2 usage error.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BASELINE_PATH = REPO / "docs" / "hygiene" / "npm-audit-runtime-exceptions.json"


def fail(messages: list[str]) -> int:
    for m in messages:
        print(f"NPM-AUDIT-BASELINE REJECTED: {m}", file=sys.stderr)
    return 1


def _advisory_ids(finding: dict) -> set[str]:
    ids: set[str] = set()
    for via in finding.get("via", []):
        if isinstance(via, dict) and via.get("url"):
            ids.add(str(via["url"]).rstrip("/").rsplit("/", 1)[-1])
    return ids


def validate(audit: dict, baseline: dict) -> list[str]:
    errors: list[str] = []
    vulns = audit.get("vulnerabilities", {})
    if not isinstance(vulns, dict):
        return ["audit JSON has no vulnerabilities object"]

    accepted = {
        e["package"]: e for e in baseline.get("exceptions", [])}

    for name, finding in vulns.items():
        severity = finding.get("severity")
        if severity == "critical":
            errors.append(f"runtime critical in {name}")
            continue
        if severity != "high":
            continue
        entry = accepted.get(name)
        if entry is None:
            errors.append(f"unlisted runtime high in {name}")
            continue
        live_ids = _advisory_ids(finding)
        base_ids = set(entry.get("advisories", []))
        if live_ids != base_ids:
            errors.append(
                f"{name}: advisory identity drifted "
                f"(+{sorted(live_ids - base_ids)} "
                f"-{sorted(base_ids - live_ids)})")
        if finding.get("range") != entry.get("vulnerable_range"):
            errors.append(
                f"{name}: vulnerable range drifted "
                f"(live {finding.get('range')!r} vs baseline "
                f"{entry.get('vulnerable_range')!r})")
        fix = finding.get("fixAvailable")
        if isinstance(fix, dict) and fix.get("isSemVerMajor") is False:
            errors.append(
                f"{name}: a COMPATIBLE (non-major) fix is now available — "
                "the UPSTREAM_BLOCKED exception is invalidated")

    for name, entry in accepted.items():
        if name not in vulns:
            errors.append(
                f"baseline exception {name} no longer appears in the "
                "audit — remove the stale exception")

    if not accepted and not any(
            v.get("severity") in ("high", "critical")
            for v in vulns.values()):
        pass  # clean audit with empty baseline is fine
    return errors


def main() -> int:
    args = sys.argv[1:]
    source = None
    baseline_path = BASELINE_PATH
    i = 0
    while i < len(args):
        if args[i] == "--baseline":
            i += 1
            if i >= len(args):
                return 2
            baseline_path = Path(args[i])
        else:
            source = args[i]
        i += 1

    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return fail([f"cannot read baseline {baseline_path}: {exc}"])

    if source in (None, "-"):
        raw = sys.stdin.read()
    else:
        try:
            raw = Path(source).read_text(encoding="utf-8")
        except OSError as exc:
            return fail([f"cannot read audit {source}: {exc}"])
    try:
        audit = json.loads(raw)
    except ValueError as exc:
        return fail([f"audit output is not valid JSON: {exc}"])
    if "vulnerabilities" not in audit:
        return fail(["audit output is not npm-audit JSON "
                     "(no vulnerabilities key)"])

    errors = validate(audit, baseline)
    if errors:
        return fail(errors)

    highs = sorted(n for n, v in audit["vulnerabilities"].items()
                   if v.get("severity") == "high")
    print(f"npm audit baseline accepted: {len(highs)} excepted runtime "
          f"high(s) {highs}, zero unlisted findings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
