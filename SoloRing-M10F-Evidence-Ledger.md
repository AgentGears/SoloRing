# SoloRing M10F Evidence Ledger (R6 §15)

Closure-only traceability of material claims to their evidence class.
The ledger is a record, never a second evidence authority: classes are
never promoted into one another, and no pytest metadata infers class.

Columns: claim_id | evidence_class | producer | exact command/test/run |
head/tree | artifact/hash | result

```text
claim_id               | class                  | producer | run                                                    | head/tree at run | artifact/hash | result
-----------------------|------------------------|----------|--------------------------------------------------------|------------------|---------------|--------
EVD-001 baseline       | SUPPLIED / LOCAL       | implementer | python -m pytest -q (pre-implementation)            | e1e9b357 / 9fe4308 | full log     | 1454/1454 PASS
EVD-002 baseline-focus | SUPPLIED / LOCAL       | implementer | focused M10 suites                                   | e1e9b357 / 9fe4308 | full log     | 152/152 PASS
EVD-003 baseline-front | SUPPLIED / LOCAL       | implementer | npm test + tsc --noEmit + npm run build              | e1e9b357 / 9fe4308 | build log    | 92/92 + PASS + PASS
EVD-004 baseline-comp  | SUPPLIED / LOCAL       | implementer | python -m compileall server scripts                  | e1e9b357 / 9fe4308 | -            | PASS
EVD-005 recovery       | SUPPLIED / LOCAL       | implementer | tests/test_m10f_backup_restore.py (41 tests)          | 4b8ea055 / 3e9d02b1 | local run log | PASS (all hermetic; CI-runnable but not run in a CI system for this record)
EVD-006 adversarial    | SUPPLIED / LOCAL       | implementer | tests/test_m10f_adversarial*.py (24 tests)            | 4b8ea055 / 3e9d02b1 | local run log | PASS (all hermetic; CI-runnable but not run in a CI system for this record)
EVD-007 compatibility  | SUPPLIED / LOCAL       | implementer | tests/test_m10f_compatibility.py (17 tests)           | 4b8ea055 / 3e9d02b1 | local run log | PASS (all hermetic; CI-runnable but not run in a CI system for this record)
EVD-008 scale          | SUPPLIED / LOCAL       | implementer | tests/test_m10f_scale.py (7 tests)                    | 4b8ea055 / 3e9d02b1 | local run log | PASS (all hermetic; CI-runnable but not run in a CI system for this record)
EVD-009 docs           | SUPPLIED / LOCAL       | implementer | tests/test_m10f_docs.py (8 tests)                     | 4b8ea055 / 3e9d02b1 | local run log | PASS
EVD-010 proof-map      | SUPPLIED / LOCAL       | implementer | python scripts/m10f_validate_proof_map.py            | 4b8ea055 / 3e9d02b1 | 8409db4a…  | VALID (all domains complete)
EVD-011 full-suite-x2  | SUPPLIED / LOCAL       | implementer | python -m pytest -q ×2 consecutive                   | 4b8ea055 / 3e9d02b1 | both logs  | 1553/1553 × 2 PASS
EVD-011b full-suite-final | SUPPLIED / LOCAL    | implementer | python -m pytest -q                                  | 4b8ea055 / 3e9d02b1 | full log   | 1553/1553 PASS (closing head)
EVD-012 gpu-v1-lane    | LIVE GPU / EXECUTOR    | operator  | m10f_two_lane_smoke.py lane 1                         | 4b8ea055 / 3e9d02b1 | two-lane-report.json | PASS @ closing head — projected {1..80}, prompt@3/positive_prompt, video:0 (13.2 MB), rerun identical, zero D0
EVD-013 gpu-v3-lane    | LIVE GPU / EXECUTOR    | operator  | m10f_two_lane_smoke.py lane 2                         | 4b8ea055 / 3e9d02b1 | two-lane-report.json | PASS @ closing head — 3-stream ControlNet, video:0 (9.4 MB), rerun identical, zero remat
EVD-014 d0-png-oracle  | LIVE GPU / EXECUTOR    | operator  | DETERM:10 N≥3 same-runtime specimen                  | 4b8ea055 / 3e9d02b1 | test_m10f_source_gate.py | PASS — 3× exact digest equality
EVD-015 archive        | SUPPLIED / LOCAL       | implementer | git archive HEAD → zip + scripts/m10f_archive_fidelity.py | e39f0d4f / 0dc69a71 | 63e1922a… | PASS — 429/429 files exact, zero content mismatches, CRLF-conversion accounted (F-114)
```

### Two-lane GPU smoke evidence detail — CLOSING HEAD (2026-08-30T06:56:21 → 07:03:50)

```text
ComfyUI commit               b963f4ad210a42841ab23dfc28a84143a0cce227 (matches certified pin)
WanVideoWrapper commit       088128b224242e110d3906c6750e9a3a348a659b (matches frozen pin)
WanVideoWrapper tree         f3e0aea21b1483ab6339c1009403122b2509131f
WanVideoWrapper status       clean (verified via git status --short)
custom-node whitelist        ComfyUI-WanVideoWrapper (only)
executor ports               8199 (evidence deployment; 8188 untouched)
wrapper restoration          git clone from upstream + detached checkout at the
                             pinned commit; rev-parse HEAD == pin; clean tree

LANE 1 — corrected lower-v1 projected execution:
  logical spec               schema 1, non-empty prompt
  projected graph            {1,2,3,4,50,60,70,80} — zero spatial ControlNet nodes
  prompt transport           verified at 3/positive_prompt (live graph)
  Wan execution              succeeded (~97 seconds on RTX 3080 Ti)
  imported video:0           blob ab2eadb27113664c…, 13,245,920 bytes
  Exact Rerun                succeeded; spec bytes + hash identical
  zero D0                    confirmed (0 derived siblings on rerun)

LANE 2 — unchanged spatial-v3 execution:
  logical spec               schema 3, 3 derived siblings (world + 2 entity)
  spatial ControlNet         nodes 101/111/121 all present in the live graph
  Wan execution              succeeded (~121 seconds on RTX 3080 Ti)
  imported video:0           blob ab6da556d707323b…, 9,376,642 bytes
  Exact Rerun                succeeded; spec bytes + hash + sibling projection identical
  zero rematerialization     confirmed (artifact count unchanged at 3)

  NOTE: executor restarted before each GPU operation that followed a heavy
  spatial run (source→rerun and lane2→lane1) — the 3-ControlNet execution
  leaves the 12 GB RTX 3080 Ti VRAM in a state that crashes subsequent model
  loads (torch access violation in module.to). Both lanes pass individually
  on clean VRAM; the restart is an honest hardware-isolation measure.
```

## Correction ledger (§6 disclosures made during implementation)

```text
R6-SF1  Blob FK inventory is six paths (two immutable M8
        visual-provenance tables omitted by R5). Found by the recovery
        FK-completeness guard on its first real run; corrected in
        recovery/backup.py EXPECTED_BLOB_FK_COLUMNS and normatively in
        R6 §5.7. No authority/schema/migration change.
PD-2    M10E D0 publication persisted absolute blobs.path
        (service.py:235). Corrected to relative_path_for_hash; legacy
        absolute rows preserved as metadata, never dereferenced
        (F-146/F-147 regression green). Load-bearing file; fresh live
        evidence already mandated by PD-1.
REPIN-1 test_m10e_generation._v3_parity_package re-pin (test-only):
        overlays only spatial inputs after PD-1C declared prompt at
        node 3, which the V4-template hybrid cannot carry. Parity
        semantics preserved.
```

The independent reviewer records reproduced evidence separately; this
ledger never labels SUPPLIED results as INDEPENDENTLY REPRODUCED.
