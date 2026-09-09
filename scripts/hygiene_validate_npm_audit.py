"""Post-M13 hygiene npm-audit baseline validator (frozen R2 HYG-04/DEP:06).

Consumes `npm audit --omit=dev --json` (stdin or file), the checked-in
exception baseline, and the package lockfile, and fails on:
  * any runtime critical;
  * any runtime high not exactly covered by the baseline;
  * any baseline entry whose package/advisory identity no longer matches
    the live audit (advisory set, vulnerable range, severity);
  * installed-version drift: the lockfile's installed version of an
    excepted package differs from the baseline's exact pin
    (installed_version), or the package is missing from the lockfile;
  * fix identity drift: the live fixAvailable package name differs from
    the recorded fix name, or the offered fix's major segment differs
    from the recorded fix major (patch/minor drift of the offered fix is
    upstream-normal and accepted);
  * a baseline exception whose offered remediation has become
    non-major (isSemVerMajor == false) — the exception is invalidated;
  * a baseline entry that no longer appears in the live audit;
  * malformed audit output.

Exit codes: 0 accepted; 1 rejected; 2 usage error.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BASELINE_PATH = REPO / "docs" / "hygiene" / "npm-audit-runtime-exceptions.json"
LOCKFILE_PATH = REPO / "apps" / "web" / "package-lock.json"


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


def _major_of(version) -> str:
    return str(version or "").split(".")[0]


def installed_versions(lockfile: Path, packages: list[str]) -> dict[str, str]:
    """Installed version per package from the npm lockfile (v3 `packages`
    first, legacy `dependencies` fallback). Missing packages are absent
    from the result — the caller reports that as drift."""
    try:
        data = json.loads(lockfile.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    pkgs = data.get("packages") or {}
    deps = data.get("dependencies") or {}
    out: dict[str, str] = {}
    for name in packages:
        entry = pkgs.get(f"node_modules/{name}")
        if isinstance(entry, dict) and entry.get("version"):
            out[name] = str(entry["version"])
        else:
            legacy = deps.get(name)
            if isinstance(legacy, dict) and legacy.get("version"):
                out[name] = str(legacy["version"])
    return out


def validate(audit: dict, baseline: dict,
             installed: dict[str, str]) -> list[str]:
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
        entry = accepted.get(name)
        if entry is None:
            if severity == "high":
                errors.append(f"unlisted runtime high in {name}")
            continue
        # Excepted package: EVERY material identity is compared, whatever
        # the live severity — a silent severity downgrade must not let a
        # stale exception ride through unexamined.
        if severity != entry.get("severity"):
            errors.append(
                f"{name}: severity drifted (live {severity!r} vs baseline "
                f"{entry.get('severity')!r})")
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
        base_fix = entry.get("fix_available") or {}
        if isinstance(fix, dict):
            if fix.get("isSemVerMajor") is False:
                errors.append(
                    f"{name}: a COMPATIBLE (non-major) fix is now "
                    "available — the UPSTREAM_BLOCKED exception is "
                    "invalidated")
            if fix.get("name") != base_fix.get("name"):
                errors.append(
                    f"{name}: fix identity drifted (live fix package "
                    f"{fix.get('name')!r} vs baseline "
                    f"{base_fix.get('name')!r})")
            elif _major_of(fix.get("version")) != _major_of(
                    base_fix.get("version")):
                errors.append(
                    f"{name}: offered fix major drifted (live "
                    f"{fix.get('version')!r} vs baseline "
                    f"{base_fix.get('version')!r})")
        pinned = entry.get("installed_version")
        if pinned is not None:
            have = installed.get(name)
            if have is None:
                errors.append(
                    f"{name}: excepted package missing from the lockfile —"
                    " cannot verify the installed_version pin "
                    f"{pinned!r}")
            elif have != pinned:
                errors.append(
                    f"{name}: installed version drifted (lockfile "
                    f"{have!r} vs baseline pin {pinned!r})")

    for name, entry in accepted.items():
        if name not in vulns:
            errors.append(
                f"baseline exception {name} no longer appears in the "
                "audit — remove the stale exception")

    return errors


def main() -> int:
    args = sys.argv[1:]
    source = None
    baseline_path = BASELINE_PATH
    lockfile_path = LOCKFILE_PATH
    i = 0
    while i < len(args):
        if args[i] == "--baseline":
            i += 1
            if i >= len(args):
                return 2
            baseline_path = Path(args[i])
        elif args[i] == "--lockfile":
            i += 1
            if i >= len(args):
                return 2
            lockfile_path = Path(args[i])
        else:
            source = args[i]
        i += 1

    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return fail([f"cannot read baseline {baseline_path}: {exc}"])
    packages = [e["package"] for e in baseline.get("exceptions", [])]
    installed = installed_versions(lockfile_path, packages)

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

    errors = validate(audit, baseline, installed)
    if errors:
        return fail(errors)

    highs = sorted(n for n, v in audit["vulnerabilities"].items()
                   if v.get("severity") == "high")
    pinned = {e["package"]: e.get("installed_version")
              for e in baseline.get("exceptions", [])}
    print(f"npm audit baseline accepted: {len(highs)} excepted runtime "
          f"high(s) {highs}, zero unlisted findings; installed pins "
          f"verified against {lockfile_path.name}: {pinned}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
