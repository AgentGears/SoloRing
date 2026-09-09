# Post-M13 Hygiene Gate — H1–H6 Implementation Record

Frozen R2 (`034f0fd391edeecf39df773f8b5c62675cc486360666920b9b560b1d57d2b5dc`). Baseline: `M13 @ 384a46d3a5c68d7d81784befc338aa8621b93fbd`, tree `a360a58bde22f9e692680232af56d5613d273702`, annotated tag `M13` (object `d8b0c6f52253a139cce3fc2f4ca712f856b6737a`), migration head `0014_m13_authority_complete_world` (unchanged).

## H1 — backend resource/test hygiene (HYG-01/02)

Fixes:

1. `tests/test_m13_races.py::_first_transition_id`: the dead first query
   (unawaited `AsyncConnection.execute` coroutine + unowned connection)
   is deleted; the helper is now exactly one awaited query under
   `async with engine.connect()`.
2. `tests/test_m13_corrections.py`: an identical leftover dead construct
   (an `if False else None` fragment with the same leak shape) removed.
3. The systemic family (216 of the 218 predecessor warnings): bare
   `factory()` sessions — 368 call sites — were never closed. Fix in
   `tests/conftest.py`: every session maker in the suite (the fixture
   factory AND the file-local `_factory` helpers in
   test_m13_binding/test_m13_shot_capture/test_m13_scale/test_m13_recovery)
   now goes through `make_tracked_maker`, a real `async_sessionmaker`
   subclass that registers created sessions; `close_registered_sessions`
   closes them all (rollback-then-close) BEFORE engine disposal in the
   `engine`, `client`, and `factory` fixtures. A first wrapper-function
   attempt broke production consumers reading `session_factory.kw` — the
   subclass preserves every sessionmaker attribute.
4. Permanent fatal guard in `tests/conftest.py`: `pytest_warning_recorded`
   registers any SAWarning carrying the non-checked-in-connection text or
   any `was never awaited` warning, and `pytest_sessionfinish` fails the
   session (exit 1, HYGIENE VIOLATION block). This lives in the
   recorder rather than `filterwarnings=error` because both families
   fire inside `__del__` where raised errors cannot propagate.

Proofs: `tests/test_post_m13_hygiene.py` — BE:02 (corrected helpers run
warning-free under `warnings.catch_warnings`), BE:03 (rollback path), BE:05
(race data lookup still returns the live id), BE:06/BE:01 (a subprocess
run with ONE deliberate leak exits 1 with the violation block; the leak
file is written inside tests/ so the real conftest loads, deleted in
finally).

Result: predecessor 218 warnings → 30 under the same full-suite run
(round-3 run: `1952 passed, 7 skipped, 30 warnings`); the remaining 30
are being driven to the classification contract (the run that produced
them is the H1 evidence; each residual warning family must be fixed or
classified before H7 closes — see H7 closure below for the final count).

## H2 — test artifact containment (HYG-08)

`build_fixture` gained `pkg_root_parent`; the caller passes pytest
`tmp_path`-derived storage; `Path(".")` is gone from the fixture
source. The parameter is MANDATORY when `with_history=True` — omission
raises at entry (an earlier draft fell back to an unscoped OS tempdir;
removed as not caller-scoped). Verified: `tests/test_m10f_scale.py`
7/7 green with repo-root `m10f-scale-pkgs` ABSENT after the run.
Proofs: `test_hyg_art_02` (a REAL representative history build runs:
v1/v2/v3 targets minted, generated package files exist under pytest
tmp, repo-root residue absent before/after, mandatory-parameter
omission raises) and `test_hyg_art_03` (focused absence; the
full-closure half is the §11 explicit assertion). CI additionally
asserts residue absence AFTER the backend suite (pre-suite check
kept), so a regression that recreates the directory during pytest
still fails the job.

## H3 — frontend structural hygiene (HYG-03)

Frozen-plan option A: `WorldSetWorkspace` owns `<li>`;
`AuthoritySubjectRow` renders non-`li` content — ALL THREE return paths
(the nested deferred presentation, the loading path, and the main row)
now render `<div>`. Proofs: `apps/web/src/__tests__/PostM13Hygiene.test.tsx`
— the reachable workspace surface renders occurrences warning-free with
subject rows and the nested deferred presentation preserved, and the
console guard self-test proves the capture helper RECORDS a synthesized
validateDOMNesting error. The failing half is carried by the
reachable-surface test itself: its zero-nesting-output assertion
(which consults the same captured console) is what fails the suite
when a real SoloRing-attributed nesting warning appears.

## H4 — dependency posture (HYG-04)

- postcss (transitive high): **compatibly remediated** —
  `apps/web/package.json` `overrides` pins `postcss >=8.5.23 <9`
  (resolved 8.5.28); fe tests (124) + tsc + build green after the
  change; `postcss` gone from the audit.
- next (direct high, 21 advisories): closed as
  **UPSTREAM_BLOCKED_RUNTIME_HIGH** against the checked-in baseline
  `docs/hygiene/npm-audit-runtime-exceptions.json` (ten predicates; the
  lockfile regen recomputed the vulnerable range to `9.5.0 - 15.5.20` —
  same 21 advisories — recorded in the baseline).
- Validator `scripts/hygiene_validate_npm_audit.py`: streams audit JSON
  and reads the package lockfile (never written into the tree). The
  baseline exact-pins the installed version (`next@14.2.35`); the
  validator rejects criticals, unlisted highs, advisory drift,
  range drift, severity drift, fix identity/major drift, installed
  version drift, missing lockfile entries, and stale exceptions
  (offered-fix patch/minor drift is upstream-normal and accepted); a
  compatible fix (`isSemVerMajor: false`) invalidates the exception.
  Live audit ACCEPTED at closure (1 excepted high, pins verified); the
  full rejection matrix is the automated proof
  `tests/test_post_m13_hygiene.py::test_hyg_dep_06_audit_validator_rejects_drift`.
- Python: pip-audit==2.10.1 in a temporary external venv audited the
  39-dependency snapshot — 0 vulnerabilities; venv/snapshot removed.

## H5 — required-status disposition (HYG-05)

Outcome **D (SETTINGS-SIDE)** — evidence and routing in the H0 inventory
§6: no rulesets; the readable branch-protection document lacks
required-status/review blocks; zero code-side occurrences. No settings
mutation performed; any change requires explicit owner authorization.

## H6 — product metadata (HYG-06)

README rewritten: post-M13 product description (feature-film-level
continuity architecture; persistent production-authority + historical
world; execution downstream; M14 future), M13 CLOSED + PUBLISHED with
the baseline identity, M6-era status/suite counts/layout removed, and
the package-semver-independence note. pyproject description replaced;
`version = "0.1.0"` deliberately kept per the frozen plan option 1.
Assertions are enforced by `scripts/hygiene_validate_proof_map.py`.

## Source-review corrections (review of 3ee6cc2, frozen R2 unchanged)

Independent source review of `3ee6cc2ed8699e0718cc650b3b0f5dd43db65e4d`
(tree `52878f8e`) against frozen R2 found three blockers and two
evidence/precision items; all five were corrected additively (no plan
revision — all are conformance/evidence corrections inside frozen R2):

1. **Exception exact-pinning (F1).** The baseline recorded only
   `installed_major: "14"`; it now exact-pins
   `installed_version: "14.2.35"` (the lockfile's installed next), and
   the validator reads `apps/web/package-lock.json` and rejects
   installed-version drift and an excepted package missing from the
   lockfile. It also compares live severity with the baseline
   (previously a silent severity downgrade skipped the excepted
   finding entirely) and verifies the material fix identity
   (fix package name + offered-fix major segment; patch/minor drift of
   the offered fix is upstream-normal and accepted).
2. **Proof-map owner contract (F2).** The validator now resolves the
   owner for ALL six dispositions (previously only TEST) and rejects
   multi-owner fields. The two double-owner cells were reduced to one
   canonical owner each (DEP:03 → `apps/web/package.json`;
   REQ:03 → the boundary validator). DEP:06 now points at a real
   automated negative matrix
   (`test_hyg_dep_06_audit_validator_rejects_drift`, 12 cases) instead
   of the validator script it was supposed to prove. BE:05 now points
   at the actual R15 race (`test_m13_race_15`), whose change leg
   exercises the corrected `_first_transition_id` with the parked
   BEFORE/AFTER assertions intact.
3. **HYG-08 permanent proof (F3).** `test_hyg_art_02` now RUNS a real
   representative history build (v1/v2/v3 targets minted) and asserts
   generated package files exist under pytest tmp with repo-root
   residue absent (previously signature/source inspection only).
   `pkg_root_parent` is mandatory when `with_history=True` (omission
   raises at entry; the unscoped OS-tempdir fallback was removed). CI
   gained a post-suite residue check after the backend suite (the
   pre-suite check is kept).
4. **H0 touched-file set (F4).** §9 now records the initial intended
   set AND the final reviewed 49-file diff set with the H1 expansion
   narrative (the original wording overstated pre-edit completeness).
5. **Evidence precision (F5).** The `_first_transition_id` defect
   location is pinned to `test_m13_races.py:659-662` at published M13
   (was misstated as 631); the H3 guard-self-test description now
   states exactly what the self-test proves (the capture helper
   records the warning) and where the failing assertion lives.

## Post-freeze upstream drift observation (2026-09-09, pending owner decision)

While re-running the H7 closure after the corrections above, the LIVE
`npm audit --omit=dev` data drifted past the frozen baseline (the
freeze-time acceptance on 2026-09-06 was against 21 advisories /
severity high / range `9.5.0 - 15.5.20`):

- two NEW advisories, both rated **critical**:
  `GHSA-p293-qw3h-jr36` (Next.js: Unauthenticated Remote Code
  Execution on windows-hosted servers) and `GHSA-2xp9-vwfh-vxw4`
  (Next.js: Unauthenticated Remote Code Execution in Image
  Optimization API);
- advisory count 21 → 23; vulnerable range → `9.5.0 - 15.5.23`;
- `fixAvailable` unchanged (`next@16.3.4`, `isSemVerMajor: true`);
  overall finding severity high → critical (max across advisories).

The validator REJECTS the live audit on three independent axes
(critical present; advisory identity drift +2; vulnerable range
drift) — exact behavior per the frozen policy, and direct evidence
that the F1 exact-pinning works. The baseline is deliberately NOT
updated in this correction round: the frozen exception class is
`UPSTREAM_BLOCKED_RUNTIME_HIGH` and the frozen validator design
rejects any runtime critical, so absorbing a critical rating is a
plan-level decision (exception amendment with an explicit
critical-risk acceptance — noting one new advisory specifically
targets Windows-hosted self-hosted servers, which matches this
deployment — versus remediation outside this gate). Disposition:
**pending owner decision**; CI's audit step will remain red against
live advisory data until decided.

## HYG-04 successor closure (frozen Next-security R2 @ 4c3d1846)

The pending owner decision above was resolved by a separately planned,
reviewed, and frozen security-stop remediation (not an exception
amendment): the unsupported, Critical-vulnerable `next@14.2.35`
runtime was replaced by the exact-pinned Next 15 Maintenance-LTS line
(`next@15.5.25`, above the 15.5.24 patch floor), with React 19
companions, the two frozen async-param page corrections, and a
mandatory Windows production-mode proof (GHSA-p293 has no known
workaround on Windows-hosted deployments). The Next exception is
REMOVED — the baseline `exceptions` array is empty — and the live
runtime audit carries zero findings at every severity, with both
target Critical GHSAs absent. Full evidence:
`docs/security/post-m13-next-security-implementation-record.md`,
`docs/security/post-m13-next-security-Windows-production-proof.md`,
and `scripts/next_security_validate.py`. The hygiene boundary
validator's allowlist recognizes the reviewed successor slice so this
gate stays GREEN across it.
