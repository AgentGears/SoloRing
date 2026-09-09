"""Post-M13 Next.js Critical security remediation proofs (frozen R2
ledger NSEC BASE/PKG/SEC cells; offline and deterministic — live-audit
proofs run in CI via scripts/next_security_validate.py)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
WEB = REPO / "apps" / "web"

TARGETS = {
    "next": "15.5.25",
    "react": "19.2.8",
    "react-dom": "19.2.8",
    "@types/react": "19.2.18",
    "@types/react-dom": "19.2.7",
}
TARGET_GHSAS = ("GHSA-p293-qw3h-jr36", "GHSA-2xp9-vwfh-vxw4")


def _lock() -> dict:
    return json.loads((WEB / "package-lock.json").read_text(
        encoding="utf-8"))


def _lock_version(lock: dict, name: str):
    entry = (lock.get("packages") or {}).get(f"node_modules/{name}")
    return str(entry["version"]) if entry and entry.get("version") \
        else None


# ---------------------------------------------------------------------------
# NSEC-BASE:03/04 — predecessor reproduction (offline, from git + SEC0 doc)
# ---------------------------------------------------------------------------


def test_nsec_base_03_predecessor_lock_next():
    """NSEC-BASE:03: the predecessor lock (exact 3adead5) resolves
    next 14.2.35 — the vulnerable identity this slice replaces."""
    out = subprocess.run(
        ["git", "show", "3adead55ca052808260bc4939403bd1fdcc29e13:"
         "apps/web/package-lock.json"],
        cwd=REPO, capture_output=True, text=True, check=True).stdout
    lock = json.loads(out)
    assert _lock_version(lock, "next") == "14.2.35"


def test_nsec_base_04_predecessor_audit_evidence():
    """NSEC-BASE:04: the SEC0 inventory records the predecessor live
    audit reproducing BOTH target Critical advisories on next 14.2.35
    (23 advisories, range 9.5.0 - 15.5.23)."""
    doc = (REPO / "docs" / "security" /
           "post-m13-next-security-SEC0-inventory.md").read_text(
               encoding="utf-8")
    for token in (*TARGET_GHSAS, "CRITICAL", "23 advisories",
                  "9.5.0 - 15.5.23", "14.2.35"):
        assert token in doc, token


# ---------------------------------------------------------------------------
# NSEC-PKG:04/05 — peer graph + postcss override (offline, from the lock)
# ---------------------------------------------------------------------------


def _satisfies(version: str, spec: str) -> bool:
    """Minimal semver satisfier for lockfile peer specs: '*'/'any',
    exact equality, '^X.Y.Z' (same major, >=), and prerelease-exact."""
    spec = spec.strip()
    if spec in ("*", "", "latest"):
        return True
    for alt in spec.split("||"):
        alt = alt.strip()
        if alt in ("*", ""):
            return True
        if alt.startswith("^"):
            base = alt[1:].split("-")[0]
            vb = version.split("-")[0]
            a, b = base.split("."), vb.split(".")
            if a and b and a[0] == b[0]:
                if [int(x) for x in b] >= [int(x) for x in a]:
                    return True
        elif alt == version:
            return True
    return False


def test_nsec_pkg_04_lock_peer_graph_static_proof():
    """NSEC-PKG:04: every peer requirement of the five target packages
    is satisfied by the locked graph — the offline complement of the
    recorded `npm ls` (no force/legacy-peer-deps anywhere)."""
    lock = _lock()
    pkgs = lock["packages"]
    checked = 0
    for name in TARGETS:
        entry = pkgs.get(f"node_modules/{name}", {})
        for peer, spec in (entry.get("peerDependencies") or {}).items():
            if peer not in pkgs.get(
                    "node_modules", {}) and \
                    f"node_modules/{peer}" not in pkgs:
                continue  # optional peer not installed (e.g. sass)
            have = _lock_version(lock, peer)
            assert have is not None, f"peer {peer} missing from lock"
            assert _satisfies(have, spec), (
                f"{name} peer {peer} {spec!r} unsatisfied by {have}")
            checked += 1
    assert checked >= 3, f"unexpectedly few peers checked ({checked})"


def test_nsec_pkg_05_postcss_override_retained():
    """NSEC-PKG:05 (frozen §7.4 RETAIN): the override stays exactly
    '>=8.5.23 <9' and the lock resolves postcss inside the safe range."""
    pkg = json.loads((WEB / "package.json").read_text(encoding="utf-8"))
    assert pkg["overrides"]["postcss"] == ">=8.5.23 <9"
    postcss = _lock_version(_lock(), "postcss")
    assert postcss is not None and "8.5.23" <= postcss < "9", postcss


# ---------------------------------------------------------------------------
# NSEC-SEC:01/02 — offline advisory-range membership for the locked next
# ---------------------------------------------------------------------------


def _in_range(version: str, lo: str | None, hi: str | None) -> bool:
    v = [int(x) for x in version.split(".")]

    def key(s):
        return [int(x) for x in s.split(".")]

    if lo is not None and v < key(lo):
        return False
    if hi is not None and v >= key(hi):
        return False
    return True


def test_nsec_sec_01_02_locked_next_outside_target_advisory_ranges():
    """NSEC-SEC:01/02 (offline half): the locked next 15.5.25 falls in
    NONE of the two target Critical advisories' affected ranges.
    Encoding note: each advisory's second segment is the 16.x line —
    the vendor's own "patched: 15.5.24" statement lower-bounds it at
    16.0 (the GitHub UI renders it as a bare `<16.3.3`; read literally
    that would also swallow the patched 15.5.24, contradicting the
    patched-versions fact). The live-audit half is enforced by the
    security validator in CI (GHSA absence + zero high/critical)."""
    next_v = _lock_version(_lock(), "next")
    assert next_v == "15.5.25", next_v
    p293 = [("13.4", "15.5.24"), ("16.0", "16.3.3")]
    x2p9 = [("10.0.0", "15.5.24"), ("16.0", "16.3.3")]
    for lo, hi in p293 + x2p9:
        assert not _in_range(next_v, lo, hi), (lo, hi)


# ---------------------------------------------------------------------------
# NSEC-SEC:04 — security-validator negative matrix (subprocess, rc-exact)
# ---------------------------------------------------------------------------


def _matrix_tree(tmp_path, *, pkg_over=None, lock_over=None,
                 baseline_exceptions=None, sync_page=False,
                 no_store=False, forbidden=False):
    pkg = {"dependencies": dict(TARGETS), "devDependencies": {
        "@types/react": TARGETS["@types/react"],
        "@types/react-dom": TARGETS["@types/react-dom"]},
        "overrides": {"postcss": ">=8.5.23 <9"}}
    override_value = (pkg_over or {}).pop("__override__", None)
    for k, v in (pkg_over or {}).items():
        if k in pkg["dependencies"]:
            pkg["dependencies"][k] = v
        else:
            pkg["devDependencies"][k] = v
    if override_value is not None:
        pkg["overrides"]["postcss"] = override_value
    lock_pkgs = {f"node_modules/{n}": {"version": v}
                 for n, v in TARGETS.items()}
    lock_pkgs["node_modules/postcss"] = {"version": "8.5.28"}
    for k, v in (lock_over or {}).items():
        lock_pkgs[f"node_modules/{k}"] = {"version": v}
    root = tmp_path / "tree"
    web = root / "apps" / "web"
    (web / "src" / "lib").mkdir(parents=True)
    (web / "src" / "app" / "x" / "[id]").mkdir(parents=True)
    (web / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
    (web / "package-lock.json").write_text(json.dumps(
        {"lockfileVersion": 3, "packages": lock_pkgs}), encoding="utf-8")
    shared = ('export async function f(u){return await fetch(u, {'
              'cache: "no-store"});}' if not no_store else
              "export async function f(u){return await fetch(u);}")
    (web / "src" / "lib" / "api.shared.ts").write_text(
        shared, encoding="utf-8")
    page = ("export default async function P({params}: {params: "
            "Promise<{id:string}>}){const {id}=await params;return id;}"
            if not sync_page else
            "export default function P({params}: {params: {id:string}}"
            "){return params.id;}")
    if forbidden:
        page += ('import {cookies} from "next/headers"; '
                 "const c = cookies();")
    (web / "src" / "app" / "x" / "[id]" / "page.tsx").write_text(
        page, encoding="utf-8")
    hyg = root / "docs" / "hygiene"
    hyg.mkdir(parents=True)
    (hyg / "npm-audit-runtime-exceptions.json").write_text(json.dumps(
        {"schema_version": 1, "policy": "x",
         "exceptions": baseline_exceptions or []}), encoding="utf-8")
    return root


def _audit(vulns=None):
    return {"vulnerabilities": vulns or {}}


def _finding(sev="high", url=None):
    via = ([{"url": f"https://github.com/advisories/{url}"}]
           if url else [])
    return {"severity": sev, "range": "*", "via": via,
            "fixAvailable": False}


@pytest.mark.parametrize("label,kwargs,audit,want_rc", [
    ("exact tree + clean audit (full)", {}, "clean", 0),
    ("exact tree pins-only", {}, None, 0),
    ("package.json next drift", {"pkg_over": {"next": "15.5.24"}},
     None, 1),
    ("lockfile next drift", {"lock_over": {"next": "15.5.24"}},
     None, 1),
    ("react drift", {"lock_over": {"react": "19.2.7"}}, None, 1),
    ("types drift", {"lock_over": {"@types/react": "19.2.17"}},
     None, 1),
    ("override changed", {"pkg_over": {"__override__": ">=8 <9"}},
     None, 1),
    ("vulnerable postcss resolution",
     {"lock_over": {"postcss": "8.4.31"}}, None, 1),
    ("next major 16", {"pkg_over": {"next": "16.3.4"},
                       "lock_over": {"next": "16.3.4"}}, None, 1),
    ("baseline carries next exception",
     {"baseline_exceptions": [{"package": "next"}]}, None, 1),
    ("baseline carries any exception",
     {"baseline_exceptions": [{"package": "other"}]}, None, 1),
    ("audit: target GHSA p293 under any package", {}, "p293", 1),
    ("audit: target GHSA 2xp9 under any package", {}, "2xp9", 1),
    ("audit: runtime high", {}, "high", 1),
    ("audit: runtime critical", {}, "critical", 1),
    ("synchronous params page", {"sync_page": True}, None, 1),
    ("no-store contract removed", {"no_store": True}, None, 1),
    ("forbidden async-request API", {"forbidden": True}, None, 1),
])
def test_nsec_sec_04_validator_negative_matrix(
        tmp_path, label, kwargs, audit, want_rc):
    """NSEC-SEC:04: the security validator accepts exactly the frozen
    closure shape and rejects every regression class: pin drift in
    package.json or lockfile, override drift, vulnerable postcss
    resolution, wrong Next major, any surviving exception, either
    target Critical GHSA, any runtime high/critical, synchronous
    params, lost no-store, forbidden async-request APIs."""
    import sys
    root = _matrix_tree(tmp_path, **kwargs)
    audit_path = None
    if audit is not None:
        if audit == "clean":
            doc = _audit()
        elif audit in ("p293", "2xp9"):
            doc = _audit({"some-pkg": _finding(
                "critical", TARGET_GHSAS[0 if audit == "p293" else 1])})
        else:
            doc = _audit({"some-pkg": _finding(audit)})
        audit_path = tmp_path / "audit.json"
        audit_path.write_text(json.dumps(doc), encoding="utf-8")
    exe = str(REPO / ".venv" / "Scripts" / "python.exe")
    if not Path(exe).exists():
        exe = sys.executable
    cmd = [exe, str(REPO / "scripts" / "next_security_validate.py"),
           "--root", str(root)]
    if audit is None:
        cmd.append("--pins-only")
    else:
        cmd.append(str(audit_path))
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    assert r.returncode == want_rc, (
        f"{label}: expected rc={want_rc}, got rc={r.returncode}\n"
        f"{(r.stdout + r.stderr)[-600:]}")
