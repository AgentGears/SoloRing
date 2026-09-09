"""Post-M13 Next.js security validator (frozen R2 §11.3/§14 PKG+APP+SEC).

Proves the frozen security closure against the working tree and (in
full mode) a runtime `npm audit --omit=dev --json` document:

  PKG  package.json exact-pins the five approved targets;
  PKG  package-lock resolves the same five exact pins;
  PKG  postcss override RETAINED (>=8.5.23 <9) and the lockfile
       resolves a non-vulnerable postcss inside that range;
  PKG  Next major exactly 15;
  SEC  the hygiene audit baseline carries NO Next exception (frozen
       §11.1: removed, not rewritten) — the exceptions array is empty;
  SEC  neither target Critical GHSA appears anywhere in the audit;
  SEC  the audit contains zero high/critical findings;
  APP  every dynamic App Router page types `params` as a Promise;
  APP  no unhandled Next-15 async-request API remains (next/headers,
       cookies(), headers(), draftMode(), searchParams, middleware
       files, route handlers, experimental-edge);
  APP  the server-side fetch contract keeps `cache: "no-store"`.

`--pins-only` skips the audit-document checks (CI pre-test gate);
`--root PATH` points at a synthesized tree (negative self-tests).

Exit codes: 0 valid; 1 rejected; 2 usage error.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

TARGETS = {
    "next": "15.5.25",
    "react": "19.2.8",
    "react-dom": "19.2.8",
}
DEV_TARGETS = {
    "@types/react": "19.2.18",
    "@types/react-dom": "19.2.7",
}
TARGET_GHSAS = ("GHSA-p293-qw3h-jr36", "GHSA-2xp9-vwfh-vxw4")
POSTCSS_OVERRIDE = ">=8.5.23 <9"

FORBIDDEN_PATTERNS = [
    (r"next/headers", "next/headers"),
    (r"\bcookies\s*\(", "cookies()"),
    (r"\bheaders\s*\(", "headers()"),
    (r"\bdraftMode\s*\(", "draftMode()"),
    (r"\bsearchParams\b", "page searchParams"),
    (r"experimental-edge|edge-runtime", "edge runtime"),
]


def fail(errors: list[str]) -> int:
    for m in errors:
        print(f"NEXT-SECURITY INVALID: {m}", file=sys.stderr)
    return 1


def _semver(version: str) -> tuple[int, ...]:
    """Stable numeric semver prefix as a tuple (numeric comparison —
    lexicographic strings misorder 8.5.3 vs 8.5.23)."""
    parts: list[int] = []
    for piece in str(version).split("."):
        digits = re.match(r"\d+", piece)
        if not digits:
            break
        parts.append(int(digits.group(0)))
    return tuple(parts)


SAFE_POSTCSS_LO = _semver("8.5.23")   # inclusive lower bound (override)
SAFE_POSTCSS_HI = _semver("9")        # exclusive upper bound


def _lock_version(lock: dict, name: str):
    entry = (lock.get("packages") or {}).get(f"node_modules/{name}")
    if isinstance(entry, dict) and entry.get("version"):
        return str(entry["version"])
    legacy = (lock.get("dependencies") or {}).get(name)
    if isinstance(legacy, dict) and legacy.get("version"):
        return str(legacy["version"])
    return None


def validate_pins(root: Path, errors: list[str]) -> None:
    web = root / "apps" / "web"
    pkg = json.loads((web / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((web / "package-lock.json").read_text(
        encoding="utf-8"))

    for name, want in TARGETS.items():
        got = (pkg.get("dependencies") or {}).get(name)
        if got != want:
            errors.append(f"package.json {name} = {got!r}, "
                          f"frozen pin is {want!r}")
    for name, want in DEV_TARGETS.items():
        got = (pkg.get("devDependencies") or {}).get(name)
        if got != want:
            errors.append(f"package.json {name} = {got!r}, "
                          f"frozen pin is {want!r}")

    for name, want in {**TARGETS, **DEV_TARGETS}.items():
        got = _lock_version(lock, name)
        if got != want:
            errors.append(f"lockfile {name} = {got!r}, frozen pin is "
                          f"{want!r}")

    override = (pkg.get("overrides") or {}).get("postcss")
    if override != POSTCSS_OVERRIDE:
        errors.append(f"postcss override {override!r} != frozen RETAIN "
                      f"{POSTCSS_OVERRIDE!r}")
    postcss = _lock_version(lock, "postcss")
    if postcss is None:
        errors.append("postcss missing from the lockfile")
    else:
        v = _semver(postcss)
        if not (v >= SAFE_POSTCSS_LO and v < SAFE_POSTCSS_HI):
            errors.append(f"lockfile postcss {postcss!r} outside the "
                          "override range (vulnerable line)")

    major = str(TARGETS["next"]).split(".")[0]
    lock_major = str(_lock_version(lock, "next") or "").split(".")[0]
    if lock_major != major:
        errors.append(f"Next major is {lock_major!r}, frozen contract "
                      f"requires exactly {major!r}")

    baseline = json.loads((root / "docs" / "hygiene" /
                           "npm-audit-runtime-exceptions.json")
                          .read_text(encoding="utf-8"))
    exceptions = baseline.get("exceptions") or []
    if exceptions:
        errors.append(f"audit baseline carries {len(exceptions)} "
                      "exception(s); frozen §11.1 requires the array "
                      "EMPTY (Next exception removed, not rewritten)")
    if any(e.get("package") == "next" for e in exceptions):
        errors.append("a Next exception still exists in the baseline")


def validate_app_structure(root: Path, errors: list[str]) -> None:
    src = root / "apps" / "web" / "src"
    for page in sorted((src / "app").rglob("page.tsx")):
        text = page.read_text(encoding="utf-8")
        if re.search(r"params\s*:\s*\{\s*[A-Za-z_]", text):
            errors.append(f"{page.relative_to(root)}: synchronous "
                          "`params` type — Next 15 requires Promise")
    for f in sorted(src.rglob("*.ts")) + sorted(src.rglob("*.tsx")):
        text = f.read_text(encoding="utf-8")
        for pattern, what in FORBIDDEN_PATTERNS:
            if re.search(pattern, text):
                errors.append(f"{f.relative_to(root)}: forbidden "
                              f"async-request API ({what})")
    for name in ("middleware.ts", "middleware.js", "src/middleware.ts"):
        if (root / "apps" / "web" / name).exists():
            errors.append(f"middleware file present: {name}")
    for route in sorted((src / "app").rglob("route.ts")):
        errors.append(f"route handler present: "
                      f"{route.relative_to(root)}")
    shared = (src / "lib" / "api.shared.ts").read_text(encoding="utf-8")
    if 'cache: "no-store"' not in shared:
        errors.append("api.shared.ts lost the explicit "
                      '`cache: "no-store"` server-fetch contract')


def validate_audit(audit: dict, errors: list[str]) -> None:
    vulns = audit.get("vulnerabilities")
    if not isinstance(vulns, dict):
        errors.append("audit JSON has no vulnerabilities object")
        return
    for name, finding in vulns.items():
        severity = finding.get("severity")
        if severity in ("high", "critical"):
            errors.append(f"runtime {severity} present in {name} — "
                          "frozen exit requires zero high/critical")
        for via in finding.get("via", []):
            if isinstance(via, dict):
                ghsa = str(via.get("url", "")).rstrip("/").rsplit(
                    "/", 1)[-1]
                if ghsa in TARGET_GHSAS:
                    errors.append(f"target Critical advisory {ghsa} "
                                  f"present under {name}")


def main() -> int:
    args = sys.argv[1:]
    source = None
    pins_only = False
    root = REPO
    i = 0
    while i < len(args):
        if args[i] == "--pins-only":
            pins_only = True
        elif args[i] == "--root":
            i += 1
            if i >= len(args):
                return 2
            root = Path(args[i])
        else:
            source = args[i]
        i += 1

    errors: list[str] = []
    try:
        validate_pins(root, errors)
        validate_app_structure(root, errors)
    except (OSError, ValueError, KeyError) as exc:
        return fail([f"cannot validate tree at {root}: {exc}"])

    if not pins_only:
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
        validate_audit(audit, errors)

    if errors:
        return fail(errors)
    mode = "pins+tree" if pins_only else "pins+tree+audit"
    print(f"Next security validator green ({mode}): next "
          f"{TARGETS['next']} exact, five pins verified, override "
          "retained, baseline exceptions EMPTY, structure guards green"
          + ("" if pins_only
             else ", zero high/critical, both target GHSAs absent"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
