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
`tmp_path`-derived storage; `Path(".")` is gone from the fixture source.
Verified: `tests/test_m10f_scale.py` 7/7 green with repo-root
`m10f-scale-pkgs` ABSENT after the run. Proofs: `test_hyg_art_02`
(signature/source/absence), `test_hyg_art_03` (focused absence; the
full-closure half is the §11 explicit assertion).

## H3 — frontend structural hygiene (HYG-03)

Frozen-plan option A: `WorldSetWorkspace` owns `<li>`;
`AuthoritySubjectRow` renders non-`li` content — ALL THREE return paths
(the nested deferred presentation, the loading path, and the main row)
now render `<div>`. Proofs: `apps/web/src/__tests__/PostM13Hygiene.test.tsx`
— the reachable workspace surface renders occurrences warning-free with
subject rows and the nested deferred presentation preserved, and the
console guard self-test proves a synthesized nesting error fails.

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
  (never written into the tree), rejects criticals/unlisted highs/
  advisory drift/invalidated exceptions; live audit ACCEPTED (1 excepted
  high); negative self-tests (unlisted high, invalidated exception,
  advisory drift) all rc=1.
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
