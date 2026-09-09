# SoloRing Post-M13 Hygiene Proof Map

Frozen R2 (`034f0fd391edeecf39df773f8b5c62675cc486360666920b9b560b1d57d2b5dc`): the machine-checkable 30-cell hygiene ledger.
Validated by `python scripts/hygiene_validate_proof_map.py` (Backend CI, before tests).

## HYG-BASE

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `HYG-BASE:01` | STRUCTURAL | `scripts/hygiene_validate_boundary.py` | Diff base is exact M13 384a46d; no commit/tag move. |
| `HYG-BASE:02` | TEST | `tests/test_post_m13_hygiene.py::test_hyg_base_02_migration_head_unchanged` | Migration head remains 0014; no 0015 file exists. |
| `HYG-BASE:03` | STRUCTURAL | `scripts/hygiene_validate_boundary.py` | Inherited M13 boundary + hygiene boundary both pass (CI runs both). |
| `HYG-BASE:04` | STRUCTURAL | `scripts/hygiene_validate_boundary.py` | No authority/storage/execution semantics changed; allowlist-scoped diff; no new tables. |
| `HYG-BASE:05` | DISPOSITION | `docs/hygiene/post-m13-hygiene-H0-inventory.md` §7 | Local/CI delta fully characterized: 10 nodes, all external-runtime availability, zero unknown. |

## HYG-BE

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `HYG-BE:01` | DISPOSITION | `docs/hygiene/post-m13-hygiene-H0-inventory.md` §2 | Resource-warning family reproduced at predecessor (218 warnings, root-cause grouped). |
| `HYG-BE:02` | TEST | `tests/test_post_m13_hygiene.py::test_hyg_be_02_no_warnings_in_corrected_helpers` | Corrected helpers run warning-free (absence proof). |
| `HYG-BE:03` | TEST | `tests/test_post_m13_hygiene.py::test_hyg_be_03_rollback_cleanup_path` | Rollback cleanup path stays correct under the tracking factory. |
| `HYG-BE:04` | DISPOSITION | `docs/hygiene/post-m13-hygiene-H0-inventory.md` §2 | Unawaited coroutine reproduced at predecessor (RuntimeWarning from test_m13_races.py:631). |
| `HYG-BE:05` | TEST | `tests/test_m13_races.py::test_m13_race_15` | The R15 race (which exercises the corrected `_first_transition_id` in its change leg) still proves one whole BEFORE/AFTER staging; the helper returns the exact live id (companion assertion in `test_hyg_be_05_race_helper_preserves_live_proof`). |
| `HYG-BE:06` | TEST | `tests/test_post_m13_hygiene.py::test_hyg_be_01_02_leak_gate_is_fatal` | The session-finish warning gate is fatal: a subprocess run with one deliberate leak exits 1 with HYGIENE VIOLATION. |

## HYG-FE

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `HYG-FE:01` | DISPOSITION | `docs/hygiene/post-m13-hygiene-H0-inventory.md` §3 | Invalid nesting reproduced at predecessor with component stack (li → AuthoritySubjectRow → li). |
| `HYG-FE:02` | TEST | `apps/web/src/__tests__/PostM13Hygiene.test.tsx::Post-M13 hygiene: reachable DOM surface > World/Set workspace renders occurrences with valid nesting and no SoloRing validateDOMNesting output (HYG-FE:01/02/04)` | Reachable surface renders warning-free after fix. |
| `HYG-FE:03` | TEST | `apps/web/src/__tests__/PostM13Hygiene.test.tsx::Post-M13 hygiene: reachable DOM surface > World/Set workspace renders occurrences with valid nesting and no SoloRing validateDOMNesting output (HYG-FE:01/02/04)` | Occurrence display, subject rows, and nested deferred presentation preserved. |
| `HYG-FE:04` | TEST | `apps/web/src/__tests__/PostM13Hygiene.test.tsx::Post-M13 hygiene: reachable DOM surface > the console guard itself is live: a synthesized validateDOMNesting error fails the assertion (guard self-test)` | The guard self-test proves the capture helper records a synthesized validateDOMNesting error; the reachable-surface assertions (FE:02/03) then fail the suite on any captured SoloRing-attributed nesting output. |

## HYG-DEP

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `HYG-DEP:01` | AUDIT-EVIDENCE | `docs/hygiene/post-m13-hygiene-H0-inventory.md` §5 | Full npm audit inventory captured (2 highs at baseline). |
| `HYG-DEP:02` | AUDIT-EVIDENCE | `docs/hygiene/post-m13-hygiene-H0-inventory.md` §5 | Runtime-only audit inventory captured (same 2 highs). |
| `HYG-DEP:03` | DISPOSITION | `apps/web/package.json` | postcss compatibly remediated via overrides (8.5.28); next range recomputed (audit evidence in H0 inventory §5). |
| `HYG-DEP:04` | DISPOSITION | `docs/hygiene/npm-audit-runtime-exceptions.json` | Successor closure (frozen Next-security R2 @ 4c3d1846): the next exception is REMOVED — baseline exceptions array empty; runtime audit zero high/critical; both target Critical GHSAs absent (NSEC-SEC:03). |
| `HYG-DEP:05` | AUDIT-EVIDENCE | `docs/hygiene/post-m13-hygiene-H0-inventory.md` §5 | No force/major migration; pip-audit==2.10.1 classified 39 deps, 0 vulnerabilities. |
| `HYG-DEP:06` | TEST | `tests/test_post_m13_hygiene.py::test_hyg_dep_06_audit_validator_rejects_drift` | Validator negative matrix: rejects unlisted highs, advisory/range/severity drift, fix identity/major drift, invalidated exceptions, installed-version drift, missing lockfile entries, stale exceptions; accepts exact pins and offered-fix patch drift. |

## HYG-REQ

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `HYG-REQ:01` | SETTINGS-EVIDENCE | `docs/hygiene/post-m13-hygiene-H0-inventory.md` §6 | Classified settings-side: no rulesets; protection document lacks required-status/review blocks. |
| `HYG-REQ:02` | SETTINGS-EVIDENCE | `docs/hygiene/post-m13-hygiene-H0-inventory.md` §6 | Current/desired state documented; zero code-side occurrences. |
| `HYG-REQ:03` | DISPOSITION | `scripts/hygiene_validate_boundary.py` | No unauthorized settings mutation in the branch; no authority/execution change (allowlist-scoped diff from exact M13). |

## HYG-META

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `HYG-META:01` | STRUCTURAL | `scripts/hygiene_validate_proof_map.py` | README identifies M13 CLOSED + PUBLISHED with baseline identity. |
| `HYG-META:02` | STRUCTURAL | `scripts/hygiene_validate_proof_map.py` | Obsolete M6/v0.1 product definition removed/reframed. |
| `HYG-META:03` | STRUCTURAL | `scripts/hygiene_validate_proof_map.py` | pyproject description aligned; version 0.1.0 kept with explicit independence note. |

## HYG-ART

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `HYG-ART:01` | DISPOSITION | `docs/hygiene/post-m13-hygiene-H0-inventory.md` §4 | Repo-root residue reproduced at predecessor (present in working tree; Path(".") root cause identified). |
| `HYG-ART:02` | TEST | `tests/test_post_m13_hygiene.py::test_hyg_art_02_generated_packages_live_under_pytest_tmp` | A real representative history build runs: generated package files exist under pytest tmp; repo-root residue absent before/after; pkg_root_parent is mandatory (omission raises). |
| `HYG-ART:03` | TEST | `tests/test_post_m13_hygiene.py::test_hyg_art_03_no_repo_root_residue_after_focus` | Focused suite + full closure leave residue absent without manual deletion (full-closure half = §11 explicit assertion). |
