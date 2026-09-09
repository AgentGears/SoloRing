"""Post-M13 Next.js Critical security remediation proofs (frozen R2
ledger NSEC BASE/PKG/SEC cells; offline and deterministic — live-audit
proofs run in CI via scripts/next_security_validate.py)."""

from __future__ import annotations

import json
import re
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
    """NSEC-BASE:03 (squash-survival form): the checked-in predecessor
    evidence records the exact vulnerable identity this slice replaces —
    predecessor commit 3adead5, its lock blob content hash, and
    next 14.2.35. The repository integrates by SQUASH merge only, so the
    intermediate hygiene commit is not part of published main history;
    the machine-readable evidence is the durable proof. When the
    predecessor happens to be reachable in the current clone, the live
    object is cross-verified against the same values."""
    ev = json.loads((REPO / "docs" / "security" /
                     "nsec-predecessor-evidence.json").read_text(
                         encoding="utf-8"))
    assert ev["predecessor_commit"] == \
        "3adead55ca052808260bc4939403bd1fdcc29e13"
    assert ev["predecessor_tree"] == \
        "d9e0c9b5cbfaeec902d70b97eed858193f76696a"
    assert ev["predecessor_lock_blob"] == \
        "946639773277989cbc05aca7b28e5a524d764f72"
    assert ev["predecessor_lock_next"] == "14.2.35"
    audit = ev["predecessor_live_audit"]
    assert audit["severity"] == "critical" and \
        audit["advisory_count"] == 23
    assert sorted(audit["target_ghsas_present"]) == sorted(TARGET_GHSAS)
    # opportunistic live cross-verification (pre-squash clones only —
    # must NOT be required in squash-shaped published history)
    reach = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet",
         f"{ev['predecessor_commit']}^{{commit}}"],
        cwd=REPO, capture_output=True, text=True)
    if reach.returncode == 0:
        blob = subprocess.run(
            ["git", "rev-parse",
             f"{ev['predecessor_commit']}:apps/web/package-lock.json"],
            cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.strip()
        assert blob == ev["predecessor_lock_blob"]
        lock = json.loads(subprocess.run(
            ["git", "cat-file", "-p", blob],
            cwd=REPO, capture_output=True, text=True, check=True).stdout)
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


def _semver_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in str(version).split("."):
        m = re.match(r"\d+", piece)
        if not m:
            break
        parts.append(int(m.group(0)))
    return tuple(parts)


def test_nsec_pkg_05_postcss_override_retained():
    """NSEC-PKG:05 (frozen §7.4 RETAIN): the override stays exactly
    '>=8.5.23 <9' and the lock resolves postcss inside the safe range
    (numeric semver comparison — never lexicographic)."""
    pkg = json.loads((WEB / "package.json").read_text(encoding="utf-8"))
    assert pkg["overrides"]["postcss"] == ">=8.5.23 <9"
    postcss = _lock_version(_lock(), "postcss")
    assert postcss is not None
    v = _semver_tuple(postcss)
    assert v >= (8, 5, 23) and v < (9,), postcss


@pytest.mark.parametrize("postcss,want_rc", [
    ("8.5.22", 1),   # vulnerable line
    ("8.5.3", 1),    # lexicographic hole: '8.5.3' > '8.5.23' as string
    ("8.5.23", 0),   # inclusive floor
    ("8.5.28", 0),   # resolved version (safe)
    ("8.10.0", 0),   # minor above 23 — safe, only reachable numerically
    ("9.0.0", 1),    # outside the override's <9 bound
])
def test_nsec_pkg_05_postcss_semver_matrix(tmp_path, postcss, want_rc):
    """NSEC-PKG:05 regression (review F2): the security validator's
    postcss safety check compares numerically — synthesized lockfiles
    carry each boundary version and the validator's --pins-only gate
    must accept/reject per the frozen >=8.5.23 <9 override range."""
    root = _matrix_tree(tmp_path, lock_over={"postcss": postcss})
    r = _run_pins_only(root)
    assert r.returncode == want_rc, (
        f"postcss {postcss}: expected rc={want_rc}, got "
        f"{r.returncode}\n{(r.stdout + r.stderr)[-500:]}")


def _run_pins_only(root):
    import sys
    exe = str(REPO / ".venv" / "Scripts" / "python.exe")
    if not Path(exe).exists():
        exe = sys.executable
    return subprocess.run(
        [exe, str(REPO / "scripts" / "next_security_validate.py"),
         "--root", str(root), "--pins-only"],
        capture_output=True, text=True, timeout=120)


def _load_script_module(name: str):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        name, REPO / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_nsec_boundary_exact_path_enforcement():
    """NSEC review F3: boundary allowlists match EXACT paths — only
    directory entries (trailing '/') may prefix-match. Near-prefix
    siblings of allowlisted files must be rejected by BOTH boundary
    validators."""
    sec = _load_script_module("next_security_validate_boundary")
    hyg = _load_script_module("hygiene_validate_boundary")
    for mod in (sec, hyg):
        pa = mod.path_allowed
        # exact entries: only exact equality
        assert pa("scripts/next_security_validate.py",
                  mod.ALLOWLIST) is True
        assert pa("scripts/next_security_validate.py.bak",
                  mod.ALLOWLIST) is False
        assert pa("scripts/next_security_validate.py-anything",
                  mod.ALLOWLIST) is False
        assert pa("apps/web/package.json", mod.ALLOWLIST) is True
        assert pa("apps/web/package.json.bak", mod.ALLOWLIST) is False
        assert pa(".github/workflows/ci.yml", mod.ALLOWLIST) is True
        assert pa(".github/workflows/ci.yml.orig", mod.ALLOWLIST) is False
        # directory entries: prefix
        assert pa("docs/security/anything.md", mod.ALLOWLIST) is True
        # unlisted root-level file with a listed directory name inside
        assert pa("docsX/hygiene/file.md", mod.ALLOWLIST) is False


def test_nsec_boundary_squash_survival(tmp_path, monkeypatch):
    """Merge-review blocker (squash-history durability): the repository
    integrates by SQUASH merge only, so the intermediate hygiene commit
    3adead5 is not permanently reachable from published main. Prove the
    security boundary survives that world:

      1. mode selection flips to published M13 exactly when the
         predecessor is unreachable;
      2. in published mode the FULL validator is green over the true
         post-squash surface (diff published M13..HEAD, union
         allowlist, checked-in predecessor evidence required);
      3. the checked-in evidence is mandatory in published mode — its
         absence is rejected.
    """
    sec = _load_script_module("next_security_validate_boundary")

    # 1. selection: predecessor mode in this clone (it is reachable)
    assert sec.select_base(REPO) == ("predecessor", sec.PREDECESSOR)
    # ... and published mode when the predecessor is unreachable
    def _unreachable(sha, repo):
        if sha == sec.PREDECESSOR:
            return False
        return sec._commit_reachable(sha, repo)
    monkeypatch.setattr(sec, "_commit_reachable", _unreachable)
    assert sec.select_base(REPO) == ("published", sec.PUBLISHED_M13)

    # 2. full published-mode validation over the true post-squash
    #    surface (the diff vs published M13 is exactly what a squash
    #    commit on main would carry)
    assert sec.main(REPO) == 0

    # 3. evidence is load-bearing in published mode: without the
    #    checked-in file the validator must reject
    ev = REPO / "docs" / "security" / "nsec-predecessor-evidence.json"
    saved = ev.read_text(encoding="utf-8")
    ev.unlink()
    try:
        assert sec.main(REPO) == 1
    finally:
        ev.write_text(saved, encoding="utf-8")
    # and corrupted identity values are rejected too
    bad = json.loads(saved)
    bad["predecessor_lock_blob"] = "0" * 40
    ev.write_text(json.dumps(bad), encoding="utf-8")
    try:
        assert sec.main(REPO) == 1
    finally:
        ev.write_text(saved, encoding="utf-8")


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
