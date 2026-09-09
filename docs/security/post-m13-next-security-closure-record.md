# Post-M13 Next.js Critical Security Remediation — Full Closure Record (SEC6)

Frozen R2 (`4c3d1846bba75b1395dd504c3d01e03542ad120dba93c40e7ed88b4012fd3d31`) §16. Base: `post-m13-hygiene @ 3adead55ca052808260bc4939403bd1fdcc29e13` (tree `d9e0c9b5`). Slice commits: SEC0 `cf75c16` → SEC1 `adc9fef` → SEC2 `259c164` → SEC3 `da8205b` → SEC4 `6bd48dc` → SEC5 `d3d3c05` → SEC6 (this slice). The final branch head/tree are reported in the push record and nominated per frozen §19.

## Frozen §16 closure matrix — results

```text
M10F proof map                      GREEN (175 entries, all domains)
M11 proof map                       GREEN (91 cells)
M12 proof map                       GREEN (123 cells)
M13 proof map                       GREEN (115 cells)
M13 boundary                        GREEN (no M14 semantics, no runtime-module changes)
hygiene proof map                   GREEN (30/30, all owners resolve, metadata green)
hygiene boundary                    GREEN (allowlist-scoped; successor slice recognized)
Next security proof map             GREEN (20/20, all owners resolve)
Next security boundary              GREEN (security-slice scoped; no server/alembic change;
                                      head 0014; Next major exactly 15; no M14 semantics)

backend pytest pass 1               1977 passed / 7 skipped, ZERO warnings, rc=0 (868s)
backend pytest pass 2               1977 passed / 7 skipped, ZERO warnings, rc=0 (857s)
frontend tests                      28 files / 124 tests, rc=0
TypeScript                          0 errors (after `npx next typegen` — F1)
production build                    GREEN (CI-style, SOLORING_API_ORIGIN=http://127.0.0.1:65534;
                                      six dynamic routes)
npm dependency graph                valid (npm ci 177 pkgs; npm ls zero invalid/unmet)
runtime npm audit                   ZERO findings at every severity
hygiene audit validator             GREEN (accepted against the EMPTY exception baseline)
Next security validator             GREEN (pins+tree+audit; both target GHSAs absent)
Windows production smoke            SEC5 run green at 6bd48dc; final-correction-head rerun
                                    (F1-corrected §12 sequence) reported in the re-review
                                    handoff — see the Windows proof doc protocol

repo-root m10f-scale-pkgs           ABSENT
migration head                      0014_m13_authority_complete_world
tracked tree                        CLEAN at the final head
M14 source mutation                 NONE (boundary-proven)
```

## Closure status after the source-review corrections (review of 9137c13)

Four blockers (F1–F4) were corrected additively; the corrected counts
and reruns supersede the matrix rows above where noted:

- **F1** — CI now runs `npx next typegen` immediately before
  `npx tsc --noEmit` (Next 15.5's documented CI sequence), and the
  Windows §12 sequence gains the same step. Empirical nuance recorded:
  on this toolchain (TypeScript 5.9.3) a clean-state `tsc` does NOT
  error on the unresolved `./.next/types/routes.d.ts` reference —
  `--listFilesOnly` proves the route types silently drop out of the
  program instead, making the typecheck silently weaker; the typegen
  step restores route-type validation and matches the documented
  sequence.
- **F2** — the postcss safety bound in the security validator and the
  PKG:05 proof now compares numeric semver tuples (lexicographic
  strings misorder 8.5.3 vs 8.5.23). Regression matrix
  (8.5.22/8.5.3/9.0.0 reject; 8.5.23/8.5.28/8.10.0 accept) is
  automated against the validator itself.
- **F3** — both boundary validators enforce exact-path allowlists
  (directory entries alone may prefix-match); near-prefix siblings of
  allowlisted files are rejected, with an automated negative proof
  over BOTH validators' real allowlists.
- **F4** — the mandatory Windows production proof is rerun on the
  exact final correction head (F1-corrected sequence) after the
  correction commit, with no source changes afterward; identity and
  mechanical results are reported in the re-review handoff per the
  review instruction (no post-proof commits).

**NSEC-CLOSE:01 (Linux CI leg) status: PENDING PR CI.** Zero GitHub
Actions runs exist for the branch head because no PR is authorized
yet — that is expected, not a defect. The workflow source carries
every gate (nine validators across both jobs, the pins-only pre-test
gate, typegen→tsc, build, and both audit validators on one audit
document); CLOSE:01 completes when an authorized PR's CI runs green.

Node-count arithmetic: 1977 = 1954 (hygiene closure count) + 23 (the
security proof tests: 5 offline proofs + the 18-case negative matrix).

## Exit statement (frozen §19)

The post-M13 implementation baseline runs a supported Next.js 15
Maintenance-LTS release (15.5.25, above the August 2026 Critical-RCE
patch floor of 15.5.24); the exact installed framework version is
mechanically pinned in package.json AND the lockfile; the two Critical
Next.js advisories (`GHSA-p293-qw3h-jr36`,
`GHSA-2xp9-vwfh-vxw4`) are absent from the live runtime audit; the
Windows production server and `/api` proxy operate correctly (SEC5
record); and the complete frozen Post-M13 Hygiene Gate re-closes
without changing M13 or introducing M14 semantics.

The exact resulting commit/tree (the branch head at push time) is
nominated as the clean post-M13 implementation-start baseline for
future M14, subject to source review — it is not M14 and does not
alter the M13 tag.

## Authorization boundary at closure

PR creation, merge, repository-settings mutation, and M14 work remain
NOT AUTHORIZED. This record nominates; it does not publish.
