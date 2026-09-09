# SoloRing Next-Security Proof Map

Frozen R2 (`4c3d1846bba75b1395dd504c3d01e03542ad120dba93c40e7ed88b4012fd3d31`): the machine-checkable 20-cell security ledger.
Validated by `python scripts/next_security_validate_proof_map.py` (Backend CI, before tests).

## NSEC-BASE

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `NSEC-BASE:01` | STRUCTURAL | `scripts/next_security_validate_boundary.py` | Dual-mode implementation boundary: exact 3adead5 diff (strict security allowlist) when the predecessor is reachable; after squash integration, published-M13 diff + union allowlist + checked-in predecessor evidence (docs/security/nsec-predecessor-evidence.json) — no ephemeral-branch dependency. |
| `NSEC-BASE:02` | STRUCTURAL | `scripts/next_security_validate_boundary.py` | M13 immutable; migration head remains 0014; no server/alembic change. |
| `NSEC-BASE:03` | TEST | `tests/test_post_m13_next_security.py::test_nsec_base_03_predecessor_lock_next` | Predecessor lock (exact 3adead5) resolves next 14.2.35 — the replaced vulnerable identity. |
| `NSEC-BASE:04` | TEST | `tests/test_post_m13_next_security.py::test_nsec_base_04_predecessor_audit_evidence` | SEC0 evidence records the predecessor live audit reproducing both target Critical GHSAs (23 advisories, 9.5.0 - 15.5.23). |

## NSEC-PKG

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `NSEC-PKG:01` | STRUCTURAL | `scripts/next_security_validate.py` | package.json exact-pins next 15.5.25 (no caret). |
| `NSEC-PKG:02` | STRUCTURAL | `scripts/next_security_validate.py` | Lockfile resolves exact next 15.5.25. |
| `NSEC-PKG:03` | STRUCTURAL | `scripts/next_security_validate.py` | react/react-dom 19.2.8 + @types 19.2.18/19.2.7 resolve exact in both files. |
| `NSEC-PKG:04` | TEST | `tests/test_post_m13_next_security.py::test_nsec_pkg_04_lock_peer_graph_static_proof` | Lockfile peer graph statically satisfied (offline complement of the recorded npm ls; no force/legacy-peer-deps). |
| `NSEC-PKG:05` | TEST | `tests/test_post_m13_next_security.py::test_nsec_pkg_05_postcss_override_retained` | postcss override RETAINED exactly (frozen §7.4) with a safe resolved version. |

## NSEC-APP

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `NSEC-APP:01` | STRUCTURAL | `scripts/next_security_validate.py` | Every dynamic App Router page types params as a Promise (structural guard, frozen §8.4). |
| `NSEC-APP:02` | STRUCTURAL | `scripts/next_security_validate.py` | No unhandled Next-15 async-request API remains (next/headers, cookies(), headers(), draftMode(), searchParams, middleware, route handlers, edge). |
| `NSEC-APP:03` | STRUCTURAL | `scripts/next_security_validate.py` | The server-side fetch contract keeps explicit `cache: "no-store"`. |
| `NSEC-APP:04` | DISPOSITION | `docs/security/post-m13-next-security-Windows-production-proof.md` | Production `/api` rewrite preserves exact proxy semantics (probe: stub status/body through `next start`); build-time rewrite-origin fact recorded. |

## NSEC-SEC

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `NSEC-SEC:01` | TEST | `tests/test_post_m13_next_security.py::test_nsec_sec_01_02_locked_next_outside_target_advisory_ranges` | GHSA-p293-qw3h-jr36 inapplicable: locked next 15.5.25 outside every affected range (offline half) + absent from live audit (validator, CI). |
| `NSEC-SEC:02` | TEST | `tests/test_post_m13_next_security.py::test_nsec_sec_01_02_locked_next_outside_target_advisory_ranges` | GHSA-2xp9-vwfh-vxw4 inapplicable: same two-sided proof. |
| `NSEC-SEC:03` | STRUCTURAL | `scripts/next_security_validate.py` | Next exception REMOVED (baseline exceptions EMPTY) and live runtime audit zero high/critical. |
| `NSEC-SEC:04` | TEST | `tests/test_post_m13_next_security.py::test_nsec_sec_04_validator_negative_matrix` | 18-case negative matrix rejects pin/override/exception/GHSA/severity/structure regressions; accepts only the exact frozen shape. |

## NSEC-CLOSE

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `NSEC-CLOSE:01` | DISPOSITION | `docs/security/post-m13-next-security-closure-record.md` | Linux CI leg: PENDING PR CI — the workflow source carries every gate (nine validators, pins-only gate, typegen→tsc, build, both audit validators); zero Actions runs exist pre-PR by design; completes when an authorized PR's CI runs green. |
| `NSEC-CLOSE:02` | DISPOSITION | `docs/security/post-m13-next-security-Windows-production-proof.md` | Windows production-mode smoke on the exact final correction head (F1-corrected §12 sequence incl. `next typegen`); protocol per review F4 — identity and mechanical results in the re-review handoff, no post-proof commits. |
| `NSEC-CLOSE:03` | DISPOSITION | `docs/security/post-m13-next-security-closure-record.md` | Complete frozen Hygiene H7 re-closure green; residue absent; head 0014; clean tree; no M14 mutation. |
