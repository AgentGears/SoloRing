# Post-M13 Hygiene Gate — H0 Inventory and Dispositions

Frozen R2 (`034f0fd391edeecf39df773f8b5c62675cc486360666920b9b560b1d57d2b5dc`) — H0 evidence record. Baseline: `M13 @ 384a46d3a5c68d7d81784befc338aa8621b93fbd`, tree `a360a58bde22f9e692680232af56d5613d273702`, annotated tag `M13` (object `d8b0c6f52253a139cce3fc2f4ca712f856b6737a`), migration head `0014_m13_authority_complete_world`.

## 1. Baseline identity

```text
commit  384a46d3a5c68d7d81784befc338aa8621b93fbd
tree    a360a58bde22f9e692680232af56d5613d273702
tag     M13 → tag object d8b0c6f52253a139cce3fc2f4ca712f856b6737a
head    0014_m13_authority_complete_world
```

## 2. Backend warning inventory (HYG-01/HYG-02)

Full backend run with warnings visible (`-rw`): `1946 passed, 7 skipped,
218 warnings`. Families:

1. **SQLAlchemy GC'd non-checked-in connection (SAWarning)** — ~216 of
   the 218. Root causes (grouped):
   - **race-helper defect (HYG-02 shared root)**: the dead first query in
     `tests/test_m13_races.py::_first_transition_id` (`(await
     engine.connect()).execute(...)`) — one leaked connection + one
     unawaited coroutine. Reproduced in isolation: `RuntimeWarning:
     coroutine 'AsyncConnection.execute' was never awaited` raised from
     `tests/test_m13_races.py:631` under `-W always::RuntimeWarning`.
     A second identical dead construct was found during H0 in
     `tests/test_m13_corrections.py` (the `if False else None`
     leftover) — same class, same fix.
   - **test-fixture lifetime defect (dominant family)**: bare `factory()`
     sessions — 368 call sites — were never closed; their pooled
     connections were GC-terminated. Fix: the `factory` fixture returns a
     real `async_sessionmaker` subclass that registers every created
     session and closes them all at teardown (first attempt used a plain
     function wrapper and broke production consumers that read
     `session_factory.kw` — corrected to the subclass).
   - **attribution noise**: the remaining warnings fire at GC time
     inside `__del__` (frames like `sys:1`, `copy.py:61`), where
     `filterwarnings=error` cannot propagate — the permanent guard is a
     `pytest_warning_recorded` + `pytest_sessionfinish` gate in
     `tests/conftest.py` that fails the session on ANY occurrence of
     the SAWarning text or `was never awaited`. Gate self-test: a
     deliberate leaked connection produces `HYGIENE VIOLATION` and
     exit code 1 (rc verified).
2. **Unawaited coroutine (RuntimeWarning)** — covered by the same gate.
3. **Third-party/other** — residual pytest informational warnings; not
   SoloRing-owned; not made fatal (frozen plan: targeted only).

## 3. Frontend DOM inventory (HYG-03)

Scratch reproduction (created, run, deleted — tree stayed clean):
selecting a composition in `WorldSetWorkspace` and rendering occurrences
produces exactly one `validateDOMNesting` warning with the component
stack `li → AuthoritySubjectRow → li → ul → WorldSetWorkspace`. Fix
(frozen plan option A): the workspace owns `<li>`; all three
`AuthoritySubjectRow` return paths now render non-`li` content (`<div>`).

## 4. Artifact residue inventory (HYG-08)

Repo-root `m10f-scale-pkgs/` present at the baseline working tree
(leftover from prior closure runs — the defect's observable). Root cause:
`tests/m10f_scale_fixture.py` passed `Path(".")` into
`_build_generation_history`. Fix: `build_fixture` takes
`pkg_root_parent` (caller passes pytest `tmp_path`-derived storage);
falls back to OS temp when absent. Verified: `tests/test_m10f_scale.py`
7/7 green with repo-root residue ABSENT after the run.

## 5. Dependency audits (HYG-04)

### npm

`npm audit --json` and `--omit=dev --json` at the baseline: exactly two
findings, both high, both present in the runtime tree:

- `next` (direct, high, 21 GHSA advisories, vulnerable
  `9.3.4-canary.0 - 16.3.0-preview.10` at baseline audit data;
  fixAvailable `next@16.3.4`, `isSemVerMajor: true`) →
  **UPSTREAM_BLOCKED_RUNTIME_HIGH** (all ten predicates; exception
  baseline at `docs/hygiene/npm-audit-runtime-exceptions.json`). No
  Next major migration inside this gate.
- `postcss` (transitive via next, high, 4 GHSA advisories, `<=8.5.22`)
  → **compatibly remediated**: `package.json` `overrides` pins
  `postcss >=8.5.23 <9` (resolved 8.5.28); frontend tests (124), tsc,
  and production build all green after the override; `postcss` no longer
  appears in the audit. Note: the lockfile regen recomputed next's
  vulnerable range to `9.5.0 - 15.5.20` (same 21 advisories) — the
  exception baseline records the recomputed range.

Validator: `scripts/hygiene_validate_npm_audit.py` (streamed audit JSON;
never written into the tree). Verified: live audit accepted (1 excepted
high); negative self-tests reject an unlisted high, an invalidated
exception (`isSemVerMajor: false`), and advisory drift — all rc=1.

### Python

Pinned mechanism per frozen plan: `pip freeze` snapshot (40 entries) of
the project environment, audited by `pip-audit==2.10.1` installed in a
temporary venv outside the repository, `--format json`, venv and
snapshot removed afterwards. Result: **39 dependencies audited, 0
vulnerabilities** — accepted clean; no remediation required.

## 6. Required-status classification (HYG-05)

- Code-side search: zero occurrences of required-status/required_status
  enforcement concepts in `server/soloring` or `apps/web/src`.
- Settings-side evidence (owner-credential read-only queries):
  `GET /repos/AgentGears/SoloRing/rulesets` → `[]` (no rulesets);
  `GET /repos/AgentGears/SoloRing/branches/main/protection` → the
  endpoint responds (branch protection exists in some form) with
  `required_status_checks` **absent/empty** and
  `required_pull_request_reviews` **absent/empty** in the returned
  document.

Classification: **SETTINGS-SIDE (outcome D)**. Current state: no
rulesets; required-status-check enforcement not present in the readable
protection document. Desired state is an owner decision (e.g. requiring
the CI checks for main). **No settings mutation is performed or
authorized by this gate**; any change requires explicit owner
authorization.

## 7. Local vs CI test-selection delta (HYG-BASE:05)

Local (this machine, full run): `1946 passed, 7 skipped` = 1953 nodes.
CI (PR #15 run 34225983502): `1936 passed, 17 skipped` = 1953 nodes.
Same collection; the delta is 10 pass↔skip flips:

| node(s) | local | CI | classification |
|---|---|---|---|
| `tests/test_m12_migration.py::test_0013_populated_tables_refuse_downgrade_before_ddl[value-N]` ×7 (skip site line 224: "populated in M12B/M12C suites") | skipped | skipped | shared, no delta |
| `tests/test_m10e_live_contract.py::test_layer3_certified_byte_oracle[name]` ×8 (`_evidence_machine()` false on CI) | passed (evidence machine) | skipped | external-runtime availability |
| `tests/test_m10e_live_contract.py::test_layer3_gate_has_positive_control` ×1 (same guard) | passed | skipped | external-runtime availability |
| `tests/test_m10a_final_slice.py::test_reference_hash_matches_certified` ×1 (`C:\AI\M10A1-evidence` mount absent on CI) | passed | skipped | external-runtime availability |

8 + 1 + 1 = 10 — exactly the observed delta; every differing node is
classified `external-runtime availability` (certified evidence-machine /
evidence-tree guards that intentionally skip on non-certified runners).
Zero `unknown` nodes. The gate does not require identical counts
(frozen §3.8).

## 8. Metadata inventory (HYG-06)

- README: M6-era opening ("Local-first creative generation loop"), M6
  status line, M6-era suite counts (765/765), M6-era layout block.
- pyproject: `version = "0.1.0"` (kept), stale v0.1 description.
- No package-version policy exists → option 1 of the frozen plan:
  version unchanged, independence documented in README.

## 9. Intended touched-file set

```text
tests/conftest.py                                   tracking factory + warning gate
tests/test_m13_races.py                             dead query removed
tests/test_m13_corrections.py                       dead construct removed
tests/m10f_scale_fixture.py                         pkg_root_parent containment
tests/test_m10f_scale.py                            caller passes pytest tmp
tests/test_post_m13_hygiene.py                      focused backend regressions
apps/web/src/components/ProductionWorldPanel.tsx    de-<li> AuthoritySubjectRow
apps/web/src/__tests__/PostM13Hygiene.test.tsx      FE regressions + console guard
apps/web/package.json + package-lock.json            postcss override
README.md, pyproject.toml                            metadata
docs/hygiene/*                                      baseline + this inventory
docs/SoloRing-Post-M13-Hygiene-Proof-Map.md         30-cell ledger
scripts/hygiene_validate_{proof_map,boundary,npm_audit}.py
.github/workflows/ci.yml                            hygiene validators + guards
```
