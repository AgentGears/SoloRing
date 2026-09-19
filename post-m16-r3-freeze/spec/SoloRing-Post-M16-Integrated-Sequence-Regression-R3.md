# SoloRing Post-M16 Integrated Sequence Regression

## Frozen Specification + Execution Results R3

**Status:** R3 freeze candidate (successor to frozen R2; specification only; execution not authorized by this document)
**Purpose:** certify the integrated M11–M16 production-world chain on the exact R3 correction baseline (the unchanged product baseline of §0.2) derived from published M16 before G8 Performance / Dialogue Co-Design
**Authorization boundary:** freezing this specification does not authorize product-source correction, M17 planning/implementation, repository publication, merge, tag, release, or boundary-allowlist mutation.

---

# 0. Executive decision

The post-M16 regression is an **implementation-level integrated sequence certification**, not another architecture pressure test and not an M17 implementation plan.

It answers:

> **Does the R3 correction baseline (published M16 plus exactly the approved recovery correction — the same product baseline R2 pinned), exercised as one accumulating film-production history, preserve the implemented M11–M16 contracts across reusable production, occurrence identity, world state, spatial binding, execution, Production Revision evolution, intra-Shot persistent consequences, recovery, and historical reproduction?**

Required program order:

```text
M16
  ↓
post-M16 integrated sequence rerun
  ↓
G8 Performance / Dialogue Co-Design
  ↓
M17A / M17B / M17C
```

A regression PASS satisfies only the post-M16 integrated-rerun prerequisite.

It does not close G8 and does not authorize M17.

---

# 0.1 Lineage (immutable: R1 → R2)

R3 is the successor specification to frozen R2, which was itself the
identity-corrected successor to frozen R1. Both stay frozen forever.
R1 records the failure on the published M16 baseline:

```text
published M16 baseline
    -> FAILED integrated recovery at R1 Run1

exact approved recovery correction
    |

R2 correction baseline
    -> new certification target
```

R1 frozen identities:

```text
R1 Part I: 65827 B / 93c72e2ade77434ea07f5ac4aaa99f14f526ed0eb40b7f445024d3526969d5ff
R1 freeze archive: 200050 B / 7feaf0139e513b130a6ad7c4aea73c0e437e83bc649fb4a88cd323abfb994272
R1 Run1 evidence: 102212 B / ed5b9926c5323a750846c10a175174dcf601c6d31c5a7a46546099634dc79d44
R1 Run1 disposition: product defect confirmed (failing cell
PM16:RECOVERY:01); Run1 NON-CERTIFYING because contemporaneous §6.4
guard transcripts were absent
```

No R1 result may be promoted into an R2 PASS result. R2 never
rewrites the history into "M16 passed": the published M16 baseline
failed integrated recovery at R1 Run1; R2 certifies the correction
baseline defined in §0.2.


R2 frozen identities:

```text
R2 Part I: 70102 B / 5ad51e1dbe5bbe68753d1112c14a4eb66e4f526325331bbb2df63eea61682dad
R2 freeze archive: 209232 B / e7800cb227403f82e62f7983a4b11d0c6c5bb9b4346ec9d0c860e46694be1a4c
R2 precursor whole-file: 71593 B / 84535e34060ad38fc1a0d1e916ab26fbe730cf3aa6863fb04ae8be7194cdf1e3
R2 closed whole-file: 73134 B / d6c5285e2e00f8eb6bc65a367d4923845c216a094e1ce7dcbd53e8e2ecd8b163
(exact bytes preserved as lineage/SoloRing-Post-M16-Integrated-Sequence-Regression-R2-CLOSED.md)
```

R2 Tier-A Run1 was CERTIFYING (both frozen §6.4 guards PASS) and
closed FAIL:

```text
Run1 evidence archive: 396506 B / 829f0b0666e29a1750066c661235f4fef476e827cfde41197744bc7339a1ff89
Run1 manifest: 19178 B / 3d55aa59f13e736751ca230e6aa387d5e3c7f37116d176df530ec0091bdfa460 (103 entries)
R2 disposition: FAIL — 59 REQUIRED PASS / 5 REQUIRED NOT_EXECUTED / 3 OPTIONAL NOT_EXECUTED
failure surface: frozen CORE-3 fixture incompatible with whole-history recovery
product defect: no — fixture/harness incompatibility encountered while
entering PM16:RECOVERY:01 (RECOVERY:01 itself remains NOT_EXECUTED
and the thrown exception is recorded as HARNESS: FAIL in the evidence
ledger; neither is rewritten)
```

R2 Run1 root cause (ruled 2026-09-19): the frozen R2 §13.2.1 fixture
inserted a Generation whose minimal WorkflowSpec lacked `inputs` and
whose manifest/template identities were 64 zeros, so the certified
recovery liveness enumeration — correctly and fail-closed — refused
the accumulated history. A recovery exemption for fixture rows is
REJECTED: the fixture must become a valid historical citizen of the
same database recovery certifies. R3 therefore amends ONLY the
fixture contract (§13.2.1), the §6.4 guard mechanism, evidence-root
naming (§20), and harness robustness (§7.3); the product baseline is
unchanged from R2 (§0.2).

No R2 result may be promoted into an R3 PASS result. R3 never
rewrites history: the published M16 baseline failed integrated
recovery at R1 Run1 (a real product defect, corrected at the §0.2
baseline); the R2 specification then failed at its own certifying
Run1 for the frozen fixture/recovery incompatibility above, with no
product defect. R3 certifies the SAME correction baseline defined in
§0.2.

---

# 0.2 R3 certifying baseline (the approved recovery correction — unchanged from R2)

```text
CERTIFYING_COMMIT = 8199e46da6b8592f606725059601b402ab2874b0
CERTIFYING_TREE   = 941d14cda84d0186431a80c0f9cbdc3fa978296b
PARENT_COMMIT     = 488031a2b7d0070d23425bbe04b86d9f9f16e0bd
PARENT_TREE       = a2a3c3e480d20b10e472812505e4370a865a8d6d
```

These constants are IDENTICAL to frozen R2's baseline: R3 is a successor
specification revision on the SAME product commits (§8); no new product
commit exists or is required.

Mechanical requirements before freeze (recorded in correction/correction-head-identity.txt, byte-identical to R2's):

```text
parent(CERTIFYING_COMMIT) == PARENT_COMMIT
delta names == exactly:
    server/soloring/recovery/backup.py
    tests/test_m15_recovery.py
backup.py blob sha256 == 6df5f96a82b06c6af1eb3be07dc39bc890cea6d49f2c2e72e74f231007e537c4
test_m15_recovery.py blob sha256 == 41fd58ba50a96531a67ffa0b7bbe51e680b6de465223d26e5b5bf0d677c5ed6d
```

Raw commit object (correction/correction-commit-object.txt, 1,415 B
/ SHA-256 2c6c7d32ba5f51a0d7730241715cc60380690f78ae2d8f68f6e5196189c534de): the exact author/committer/message bytes, so the commit
object — and hence the commit id 8199e46… — is reconstructable
exactly from the pinned parent and tree.

Exact patch (git diff 488031a2..8199e46, stored as
correction/correction.patch):
4,554 B / aa566c793d91a3a12c0e828b08ca4f35a36c0ee1b68a4c2e0380ddf7de1f1bb5

Correction scope (correction/correction-delta.txt): removal of the
three vestigial `_verify_m13_pi_state` loop locals plus the focused
multi-transition recovery regression. No schema, migration, M16
authority, compatibility, capture, executor, API, or Shot semantics
changed.

---

# 1. Frozen-specification discipline

This artifact has two mechanically separated regions:

```text
PART I — FROZEN REGRESSION SPECIFICATION

<all identities, cases, coverage classifications,
failure rules, commands, and evidence grammar>

======== END OF FROZEN SPECIFICATION ========

PART II — EXECUTION RESULTS
```

Before any certifying execution:

1. Part I is complete.
2. Every pressure-test case has a coverage classification.
3. Every oracle identity has been byte-verified.
4. Every system-under-test identity has been resolved to a full exact value.
5. The exact Part-I bytes are hashed.
6. The Part-I SHA-256 and byte count are recorded before execution.

Nothing above `END OF FROZEN SPECIFICATION` may change once certification begins.

If the specification is defective or incomplete:

```text
STOP
→ record specification defect
→ create successor revision
→ freeze successor bytes
→ restart certification from the beginning
```

No result-driven amendment of R3 is permitted.

Lifecycle:

```text
DRAFT_SPEC
    ↓
SPEC_FROZEN_NOT_EXECUTED
    ↓
EXECUTION_IN_PROGRESS
    ↓
PASS
or
FAIL
or
EVIDENCE_SET_INCOMPLETE
```

## 1.1 Canonical Part-I byte location

The canonical R3 file is the exact file in the freeze set at this
exact archive-root-relative path ("freeze-set root" means the root
of the presented freeze archive / the `FREEZESET.sha256` tree):

```text
spec/SoloRing-Post-M16-Integrated-Sequence-Regression-R3.md
```

The Part-I identity is defined as:

```text
file:
    exact file above

hashed byte range:
    byte 0
    through and including the FINAL occurrence in this file of:
    ======== END OF FROZEN SPECIFICATION ========

record:
    part_i_byte_count
    part_i_sha256
    whole_preexecution_file_sha256
```

No separately reconstructed or copied Part-I text is authoritative.

The byte range is taken directly from the exact freeze-set file.

Appending Part II after execution is permitted only if the Part-I prefix bytes remain byte-identical.

After all Part-I content is final, the final two §26 prerequisites are marked complete, the Part-I byte count and SHA-256 are computed as the final freeze action, and those values are written only into Part II §A; no computed hash value is inserted into Part I.

Part I ends after the single LF immediately following the final marker; that LF is included in `part_i_byte_count` and `part_i_sha256`.

---

# 2. Oracle hierarchy

## 2.1 Certified six-artifact normative set

R3 inherits the frozen R2's oracle hierarchy verbatim (R2 inherited R1's, which pinned exactly the M16 R7 normative foundation).

| Artifact                                       | Exact SHA-256                                                      |
| ---------------------------------------------- | ------------------------------------------------------------------ |
| Architecture Pattern Register v2.5             | `1da9fe2b957a19015d275b076732bc1c42c7f0cf789dc4b05647fcf0914a69a0` |
| Product & Production Architecture v1.6         | `d93125ceed1e24dcbc86e88e5dfb42b02d7352bec5240ef9d75a5423c1a24077` |
| Capability & Ownership Map v1.6                | `e6411f8725f706f11168585490e5fd9525a63e85a5756552964745eec6e51d88` |
| Gap & Dependency Graph v1.6                    | `b3ec6ee1b2bddeec9ba18ce393da87e041592bb42fa9a478980c28666031457c` |
| Implementation Roadmap v1.4                    | `1e478a5b6ca49e7e56594a2e241938fa3c96a1fdc3bb39b49f2e033d3c64ed40` |
| Full-Sequence Product Pressure Test v1.6 rerun | `215ee3e5037690d82ccec15925999f7d1cea2b2bb890138995c90d82724971e9` |

No v1.7 architecture artifact or Roadmap v1.5 is a normative R3 oracle.

They may exist as later planning material but do not silently replace the set against which M16 was frozen.

## 2.2 Original scenario versus accepted interpretation

The pressure-test hierarchy is:

```text
original Full-Sequence Product Pressure Test v1.0
        =
immutable scenario source

v1.6 certified rerun
        =
accepted interpretation of that unchanged scenario
against the M16 normative architecture foundation

older v1.1/local rerun material
        =
historical/non-authoritative context for R3
```

If an older untracked rerun conflicts with the certified v1.6 rerun, the old rerun does not control R3.

If the original v1.0 scenario bytes and the certified v1.6 artifact reveal a genuine contradiction about what the unchanged scenario requires:

```text
STOP
→ specification cannot freeze until reconciled explicitly
```

No silent interpretation is allowed.

## 2.3 Mandatory v1.0 provenance/reconciliation review

Before freeze, the candidate original file currently known as the untracked pressure-test v1 document must be established as the actual original scenario source.

The review records:

```text
candidate path
provenance basis
creation/history evidence available
byte count
line count
SHA-256
reviewer disposition:
    VERIFIED_ORIGINAL
    or
    PROVENANCE_UNRESOLVED
```

`PROVENANCE_UNRESOLVED` blocks freeze.

After provenance is established, a human review compares the actual v1.0 scenario against the certified v1.6 rerun sufficiently to establish:

```text
v1.6 preserves the unchanged scenario
or
a material contradiction exists
```

This is not replaced by hash comparison.

The review output itself becomes frozen evidence.

---

# 3. Oracle-byte availability prerequisite

Hash strings alone are insufficient.

Before R3 freezes, the exact oracle bytes used by the regression must be collected into one immutable evidence input set:

```text
<freeze-set root>/                      (archive root)
  spec/
    SoloRing-Post-M16-Integrated-Sequence-Regression-R3.md

  oracles/
    Architecture-Pattern-Register-v2.5
    Product-and-Production-Architecture-v1.6
    Capability-and-Ownership-Map-v1.6
    Gap-and-Dependency-Graph-v1.6
    Implementation-Roadmap-v1.4
    Full-Sequence-Pressure-Test-Rerun-v1.6
    Full-Sequence-Pressure-Test-v1.0

  lineage/
    r1-frozen-identity.txt
    r1-run1-failure-identity.txt
    r2-frozen-identity.txt
    r2-run1-failure-identity.txt
    SoloRing-Post-M16-Integrated-Sequence-Regression-R2-CLOSED.md

  correction/
    correction-head-identity.txt
    correction-commit-object.txt
    correction.patch
    correction-delta.txt
    correction-validation.txt

  reviews/
    v1.0-provenance-review.txt
    v1.0-v1.6-reconciliation-review.txt
```

For each oracle record:

```text
logical role
source/retrieval location
byte length
line count where applicable
SHA-256
```

The six normative artifacts must hash exactly to §2.1.

The original v1.0 scenario must additionally be pinned by its exact reviewed hash before freeze.

Untracked workspace placement is not accepted as durable provenance by itself.

Either:

```text
A. commit/archive the exact oracle bytes in an immutable location
```

or:

```text
B. place exact copies in the R3 freeze input set,
   record originating retrieval provenance,
   and hash the copied bytes
```

If any required byte set cannot be obtained:

```text
EVIDENCE_SET_INCOMPLETE
```

Do not substitute a nearby revision.

---

# 4. Dual system identity

R3 carries THREE identities that must never be collapsed: the certified M16 implementation (the R1 closure object), the published M16 baseline (R1's failed certifying target), and the R3 correction baseline (§0.2, the certifying target — commit/tree identical to R2's).

## 4.1 Certified implementation identity

Record before freeze using full exact values:

```text
certified implementation commit:
    9e703806304063110a07458c3d3e0b0124c6ab14   # verified 2026-09-19, mechanically verified via git rev-parse/diff-list

certified implementation tree:
    ca52da2629502ac813538854bd812f2886a99c7b   # verified 2026-09-19, mechanically verified via git rev-parse/diff-list
```

This is the implementation identity that received the M16 closure certification.

## 4.2 Published system-under-test identity

Record before freeze using full exact values:

```text
published main commit:
    488031a2b7d0070d23425bbe04b86d9f9f16e0bd   # origin/main == M16^{commit}, verified 2026-09-19, mechanically verified via git rev-parse/diff-list

published main tree:
    a2a3c3e480d20b10e472812505e4370a865a8d6d   # verified 2026-09-19, mechanically verified via git rev-parse/diff-list

pre-M16 main parent:
    30ea135f3b2339491e9b36eaee2d0d8bc4ab8585   # parent(488031a2), verified 2026-09-19, mechanically verified via git rev-parse/diff-list

M16 branch publication tip:
    44936bfc2a3ac565621198bd84ea0370cbb753d9   # branch m16 head, verified 2026-09-19, mechanically verified via git rev-parse/diff-list

M16 branch first publication commit:
    e235b655dff382af5d695c50b10622c3fea8a97f   # verified 2026-09-19, mechanically verified via git rev-parse/diff-list

annotated tag:
    M16

tag object:
    4a890260448021419168ea51da6321d5b1e3867c   # verified 2026-09-19, mechanically verified via git rev-parse/diff-list

peeled tag commit:
    488031a2b7d0070d23425bbe04b86d9f9f16e0bd   # == published main commit, verified 2026-09-19, mechanically verified via git rev-parse/diff-list
```

The R1 certifying regression executed against the published M16 identity and FAILED (§0.1). The R2 certifying regression then executed against the same baseline and closed FAIL on the frozen fixture/recovery incompatibility (§0.1). The R3 certifying regression executes against the **R3 correction baseline** of §0.2; the §4.3 proof below is retained as lineage proving how that baseline's parent was constructed.

## 4.3 Squash-aware publication equivalence proof (historical lineage)

M16 publication was a squash merge.

The certified implementation branch and published `main` are therefore not joined by direct commit ancestry.

R3 must prove both history legs and their tree-equivalence join.

Exactly:

```text
1. parent(published_main) == pre_M16_main

2. rev-list(
       certified_implementation_commit
       ..
       branch_publication_tip
   )
   ==
   [
       branch_publication_commit_1,
       branch_publication_tip
   ]

3. tree(published_main)
   ==
   tree(branch_publication_tip)
   ==
   exact published tree

4. diff(
       certified_implementation_commit
       ..
       branch_publication_tip
   )
   ==
   exactly:
       README.md
       +
       the three approved validator allowlist files
```

The frozen full-identity form mechanically establishes (verified 2026-09-19, mechanically verified via git rev-parse/diff-list):

```text
parent(488031a2b7d0070d23425bbe04b86d9f9f16e0bd)
    == 30ea135f3b2339491e9b36eaee2d0d8bc4ab8585

rev-list 9e703806304063110a07458c3d3e0b0124c6ab14..44936bfc2a3ac565621198bd84ea0370cbb753d9
    == [e235b655dff382af5d695c50b10622c3fea8a97f,
       44936bfc2a3ac565621198bd84ea0370cbb753d9]

tree(488031a2b7d0070d23425bbe04b86d9f9f16e0bd)
    == tree(44936bfc2a3ac565621198bd84ea0370cbb753d9)
    == a2a3c3e480d20b10e472812505e4370a865a8d6d

diff --name-only 9e703806304063110a07458c3d3e0b0124c6ab14..44936bfc2a3ac565621198bd84ea0370cbb753d9
    == exactly:
       README.md
       scripts/m14_validate_boundary.py
       scripts/m16_validate_boundary.py
       scripts/next_security_validate_boundary.py
```

No production-domain, migration, schema, API, worker, executor, materializer, test-semantic, or workflow change may appear in the publication delta.

No claim that `488031a…` descends from `9e703806…` is permitted.

If any branch leg, parent, tree join, or four-file delta differs:

```text
FAIL — SYSTEM_IDENTITY_DRIFT
```

The exact commands and complete outputs become evidence.

---

# 5. Tier-B execution identity

Tier B is optional corroboration, not a prerequisite for Tier-A certification.

If Tier B runs, its preflight additionally pins the complete live MaterializerContract identity:

```text
963e3a035c202d4a906e6a9b86cc416895987f6a652aa0b19d94ee7538e6925c
```

(verified 2026-09-19, mechanically verified via git rev-parse/diff-list as the live computed contract hash; the prior pin 9e5526b1… reconstructs exactly from this document by the single-field LF materializer-implementation substitution.)

The full value must be resolved mechanically before Tier-B execution.

All other materially determinative executor/runtime/model/workflow identities required by the certified execution contract must likewise be captured.

A missing or mismatched Tier-B runtime identity means:

```text
Tier B = EVIDENCE_SET_INCOMPLETE or FAIL
```

according to the existing execution contract.

It does not invalidate a separately complete Tier-A PASS unless Part I explicitly made Tier B mandatory.

---

# 6. Identity guard protocol

Every certifying execution tier is bracketed by an identity guard.

A run without both successful guards is a run, but not certifying evidence about the claimed tree.

## 6.1 Pre-run guard

Immediately before executing the tier, assert and record:

```text
HEAD == exact CERTIFYING_COMMIT (§0.2)

tree == exact CERTIFYING_TREE (§0.2)

tracked worktree clean

index clean

checkout contains the expected migration file set,
whose terminal Alembic revision is exactly:
    0017_m16_intra_shot_consequences

no later migration exists in the tested checkout

new run database upgrades successfully to exactly:
    0017_m16_intra_shot_consequences

no unexpected pre-existing repository residue
```

Run from a clean detached worktree created from the exact R3 CERTIFYING_COMMIT (§0.2).

Evidence output is written outside that checkout.

## 6.2 Post-run guard

Immediately after the tier, before interpreting results:

```text
HEAD unchanged

tree unchanged

tracked worktree unchanged

index unchanged

migration/code checkout identity unchanged

no unauthorized source mutation

no unexpected repository residue
```

If either identity guard fails:

```text
FAIL — RUN_NOT_BOUND_TO_EXPECTED_TREE
```

The test results cannot be reused after repairing the checkout.

The complete tier must restart.

## 6.3 Required guard evidence

Retain:

```text
identity-guard-tier-a-pre.log
identity-guard-tier-a-post.log

identity-guard-tier-b-pre.log
identity-guard-tier-b-post.log   # if Tier B runs
```

Each transcript records:

```text
commands
working directory
timestamps
exit statuses
expected identities
actual identities
```

---

## 6.4 Frozen guard command blocks (verbatim)

Run from the detached certification checkout; evidence written to
`$EV` (outside the checkout). Every command's non-zero exit is an
immediate certification failure for the bracketed tier.

**Pre-run guard (Tier A and, if run, Tier B):**

```bash
set -e
# identity
CERTIFYING_COMMIT=8199e46da6b8592f606725059601b402ab2874b0
CERTIFYING_TREE=941d14cda84d0186431a80c0f9cbdc3fa978296b
PARENT_COMMIT=488031a2b7d0070d23425bbe04b86d9f9f16e0bd
# identity: the R3 certifying baseline (§0.2, identical commits to R2's), bound by frozen
# constants — NOT phrases about any "published" commit
test "$(git -C "$CK" rev-parse HEAD)" = "$CERTIFYING_COMMIT"
test "$(git -C "$CK" rev-parse 'HEAD^{tree}')" = "$CERTIFYING_TREE"
test "$(git -C "$CK" rev-parse HEAD^)" = "$PARENT_COMMIT"
test "$(git -C "$CK" diff --name-only HEAD^..HEAD | sort | tr '\n' ' ')" \
  = "server/soloring/recovery/backup.py tests/test_m15_recovery.py "
# clean checkout
test -z "$(git -C "$CK" status --porcelain --untracked-files=no)"
# untracked non-ignored files are ALSO forbidden (ignored entries like
# __pycache__/ remain excluded by git ignore rules)
test -z "$(git -C "$CK" status --porcelain)"
test -z "$(git -C "$CK" diff-index --cached HEAD)"
# migration baseline: terminal revision is exactly 0017, none later
test "$(ls "$CK/server/alembic/versions" | grep -c '^0017_m16_intra_shot_consequences.py$')" = 1
test "$(ls "$CK/server/alembic/versions" | sed 's/_.*//' | sort -n | tail -1)" = "0017"
# fresh DB upgrades to exactly 0017 — through the SUPPORTED
# settings environment; no startup adapter of any kind is
# permitted for certification
TMPROOT="$(mktemp -d)"
TMPDB="$TMPROOT/guard.db"
cd "$CK/server" && SOLORING_DATABASE_URL="sqlite:///$TMPDB" \
SOLORING_DATA_DIR="$TMPROOT" PYTHONDONTWRITEBYTECODE=1 \
python -m alembic upgrade head
test "$(python -c "import sqlite3,sys;print(sqlite3.connect(sys.argv[1]).execute('SELECT version_num FROM alembic_version').fetchone()[0])" "$TMPDB")" = "0017_m16_intra_shot_consequences"
```

**Post-run guard:**

```bash
set -e
CERTIFYING_COMMIT=8199e46da6b8592f606725059601b402ab2874b0
CERTIFYING_TREE=941d14cda84d0186431a80c0f9cbdc3fa978296b
test "$(git -C "$CK" rev-parse HEAD)" = "$CERTIFYING_COMMIT"
test "$(git -C "$CK" rev-parse 'HEAD^{tree}')" = "$CERTIFYING_TREE"
test -z "$(git -C "$CK" status --porcelain --untracked-files=no)"
test -z "$(git -C "$CK" status --porcelain)"
test -z "$(git -C "$CK" diff-index --cached HEAD)"
test "$(ls "$CK/server/alembic/versions" | sed 's/_.*//' | sort -n | tail -1)" = "0017"
# no residue appeared inside the checkout during the run
test ! -e "$CK/m10f-scale-pkgs"
# general residue is already covered by the full --porcelain check above
```

Transcripts — guard scripts live OUTSIDE the certification
checkout, under `$EV/guards/` (a script materialized inside `$CK`
would violate the very untracked-empty assertion the guard asserts).
Each guard executes through this exact frozen wrapper, which writes
everything §6.3 requires — timestamps, working directory, complete
stdout+stderr xtrace, and the numeric exit status — into one
transcript:

```bash
{
  echo "guard_start_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "wrapper_pwd=$PWD"
  echo "CK=$CK"
  echo "EV=$EV"
  bash -x "$EV/guards/guard-pre.sh" 2>&1
  echo "guard_exit=$?"
  echo "guard_end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$EV/guards/identity-guard-tier-a-pre.log" 2>&1
grep -q "^guard_exit=0$" "$EV/guards/identity-guard-tier-a-pre.log"   || exit 2
```

(post guard and Tier-B variants substitute the script and log names
the same way; a missing or non-zero `guard_exit` line is the tier
failure.) `$CK` is the detached worktree path; `$EV` the evidence
package path (written OUTSIDE the checkout); both recorded in
`identities/`. The harness runs the suite with
`PYTHONDONTWRITEBYTECODE=1` so bytecode cache never dirties the
checkout. The runner pins TMPDIR to an interpreter-resolvable directory
outside the checkout so mktemp results are openable; that is environment
preparation, not a code adapter. Certification requires NO
sitecustomize/startup adapter: the guard's database mechanism is the
supported SOLORING_* settings environment above.

# 7. Regression implementation model

## 7.1 One accumulating Project

The central certification deliberately suspends ordinary test independence.

It uses one logical Project whose history accumulates:

```text
publish production
→ compose reusable world
→ bind spatial authority
→ capture early work
→ create/adopt consequences
→ resolve later world state
→ evolve reusable revisions
→ preserve occurrence + state
→ create further consequences after evolution
→ capture later work
→ resolve flashback
→ reproduce old history
→ backup / restore accumulated history
```

The normal sequence may not be replaced with independently seeded final-state fixtures.

The sole frozen exception is §13.2's narrowly scoped CORE-3 Generation/Take evidence-input fixture.

## 7.2 Pytest discipline

Preferred implementation:

```text
one certifying sequence driver
    +
one session-scoped engine/world fixture
    +
ordered phase helpers
    +
per-cell evidence recorder
```

For example:

```text
test_post_m16_integrated_sequence.py

test_integrated_sequence_certification(...)
    phase_01_initial_world()
    phase_02_early_shots()
    phase_03_m16_consequences()
    phase_04_downstream_state()
    phase_05_m15_evolution()
    phase_06_post_evolution_m16()
    phase_07_flashback()
    phase_08_history()
    phase_09_recovery()
```

Using one driver avoids accidental pytest collection-order dependence.

If multiple pytest test items are used instead, ordering must be mechanically enforced.

## 7.3 Fail-fast

The accumulating certification is fail-fast.

On first REQUIRED-cell failure:

```text
STOP sequence
→ retain evidence through failing cell
→ do not continue using partially invalid history
```

An unexpected exception raised while a named cell is being executed
must first emit that cell's FAIL record (traceback/evidence) and only
then trigger fail-fast; the runner may not leave an entered REQUIRED
cell as NOT_EXECUTED behind a bare HARNESS record. (Frozen R2's Run1
HARNESS-only record in §0.1 is history and is not rewritten.)

After any product-code correction:

```text
destroy run database/state
→ recreate clean exact-baseline checkout
→ rerun from cell 1
```

No checkpoint resume is certifying.

---

# 8. No product correction during certification

The harness may observe and record defects.

It may not correct product code during the certifying run.

If a failure requires product-source modification:

```text
record FAIL
→ close run
→ separately review/authorize correction
```

Permanently (generic rule): a frozen regression specification is bound to exactly one certifying commit/tree. If a product correction is required, the current run terminates FAIL and that specification cannot certify the corrected head. A successor specification revision must be frozen with the new exact baseline before certification restarts from cell 1.

---

# 9. Coverage inventory requirement

Before freeze, every v1.0/v1.6 case, negative, cross-sequence invariant, and applicable additive case must appear in the coverage ledger.

Allowed coverage classes are exactly:

```text
DIRECT
INHERITED_CERTIFIED
EXPECTED_FUTURE_GAP
OUT_OF_SCOPE
```

### DIRECT

R3 executes new integrated evidence on the accumulating Project.

### INHERITED_CERTIFIED

The exact R3 correction baseline already provides sufficient certifying local evidence and R3 pins that evidence instead of duplicating it.

### EXPECTED_FUTURE_GAP

The frozen pre-run specification identifies an intentionally unimplemented later capability.

### OUT_OF_SCOPE

The case belongs to an explicitly independent/deferred branch and Part I states why it is not required for the M11–M16 claim.

No pressure-test case may remain unclassified.

No unexpected failure may be relabelled `EXPECTED_FUTURE_GAP` after execution begins.

The coverage ledger is part of Part I and therefore frozen before any certifying run.

## 9.1 Coverage ledger and cell universe

Two mechanically distinct tables, both Part I:

- **Oracle Coverage Ledger** — one row per v1.0/v1.6 source case, IDs
  in the `OCL-*` namespace (NOT certifying cells), each with exactly
  one coverage class and a pointer to the cell(s)/evidence carrying
  it. Zero unclassified oracle cases.
- **PM16 Cell Universe** — one row per actual certifying cell with
  stable `PM16:*` ID, tier, and pass gate. Mapping rule (asymmetric):
  every DIRECT OCL row maps to at least one REQUIRED A/A+B PM16 cell;
  PM16 may additionally contain decomposition, oracle, identity,
  recovery, evidence and disposition cells that do not correspond
  one-to-one with an oracle case.

### 9.1.1 Oracle Coverage Ledger

**(a) v1.0 §6 matrix — all 33 rows**

| OCL ID | Source case | Class | Carried by |
|---|---|---|---|
| OCL-v1:01 | Shot 20 exterior arrival | DIRECT | PM16:SEQ:17 |
| OCL-v1:02 | Shot 21 lobby entrance wide | DIRECT | PM16:SEQ:01 |
| OCL-v1:03 | Shot 22 reverse behind desk | DIRECT | PM16:SEQ:02 |
| OCL-v1:04 | Shot 23 chair local staging | DIRECT | PM16:SEQ:03 |
| OCL-v1:05 | Shot 24 chair collision | DIRECT | PM16:CORE1:02 |
| OCL-v1:06 | Shot 25 forehead injury | DIRECT | PM16:CORE2:01 |
| OCL-v1:07 | Shot 26 immediate aftermath | DIRECT | PM16:CORE2:02 |
| OCL-v1:08 | Shot 27 vase breaks | DIRECT | PM16:CORE4:01 |
| OCL-v1:09 | Shot 28 exit/possession | DIRECT | PM16:SEQ:04 |
| OCL-v1:10 | Shot 40 unrelated scene | DIRECT | PM16:SEQ:05 |
| OCL-v1:11 | Chair Production Revision 3 | DIRECT | PM16:CORE1:03 |
| OCL-v1:12 | Lobby Composition 9 published | DIRECT | PM16:SEQ:06 |
| OCL-v1:13 | Shot 51 return wide | DIRECT | PM16:CORE1:05 |
| OCL-v1:14 | Shot 52 healing close-up | DIRECT | PM16:CORE2:03 |
| OCL-v1:15 | Shot 53 lobby insert | DIRECT | PM16:SEQ:07 |
| OCL-v1:16 | Chandelier Revision 4 approved | DIRECT | PM16:SEQ:08 |
| OCL-v1:17 | Shot 54 Shot-local substitution | DIRECT | PM16:SEQ:08 |
| OCL-v1:18 | Lobby Composition 10 published | DIRECT | PM16:SEQ:08 |
| OCL-v1:19 | Shot 55 new wide with Lobby 10 | DIRECT | PM16:SEQ:08 |
| OCL-v1:20 | Shot 56 generated desk detail | OUT_OF_SCOPE | no generation→registry route (structural; N-05 rerun PASS) |
| OCL-v1:21 | Promote key-card holder | EXPECTED_FUTURE_GAP | candidate→reusable promotion future |
| OCL-v1:22 | Shot 57 lobby with promoted object | EXPECTED_FUTURE_GAP | depends on OCL-v1:21 |
| OCL-v1:23 | Shot 58 physical contact | EXPECTED_FUTURE_GAP | Performance/contact future (G8) |
| OCL-v1:24 | Shot 59 flashback | DIRECT | PM16:CORE2:04 |
| OCL-v1:25 | Candidate-world ingestion (op) | EXPECTED_FUTURE_GAP | ingestion future |
| OCL-v1:26 | Shot 61 imported camera trajectory | EXPECTED_FUTURE_GAP | with OCL-v1:25 |
| OCL-v1:27 | Shot 62 candidate performance | EXPECTED_FUTURE_GAP | G8 future |
| OCL-v1:28 | Shot 63 simulation proposes | EXPECTED_FUTURE_GAP | simulation future |
| OCL-v1:29 | Shot 64 validated lamp support | EXPECTED_FUTURE_GAP | simulation future |
| OCL-v1:30 | Shot 65 executor lacks control | INHERITED_CERTIFIED | M14-CAP:05 |
| OCL-v1:31 | Shot 66 compatible alternative executor | EXPECTED_FUTURE_GAP | second executor path future |
| OCL-v1:32 | Shot 67 historical rerun | DIRECT | PM16:HISTORY:01 |
| OCL-v1:33 | Historical representation missing | DIRECT | PM16:HISTORY:03 |

**(b) v1.6 rerun additions**

| OCL ID | Source case | Class | Carried by |
|---|---|---|---|
| OCL-r6:01 | 13A dialogue/lip-sync | EXPECTED_FUTURE_GAP | G8 future |
| OCL-r6:02 | 13B editorial/conform/finishing | EXPECTED_FUTURE_GAP | later program |
| OCL-r6:03 | 13C deterministic editorial materialization | EXPECTED_FUTURE_GAP | later program |
| OCL-r6:04 | §20 filmmaker UX | OUT_OF_SCOPE | M16 UI:01–06 separately certified |
| OCL-r6:05 | §19 residual capability gaps | EXPECTED_FUTURE_GAP | = the EXPECTED_FUTURE_GAP rows above |

**(c) v1.0 §20 negatives — all 24**

| OCL ID | Source | Class | Carried by |
|---|---|---|---|
| OCL-N:01 | N-01 | INHERITED_CERTIFIED | M11-PUB:16 (+ M11-PUB:14) |
| OCL-N:02 | N-02 | DIRECT | PM16:NEG:N02 |
| OCL-N:03 | N-03 | DIRECT | PM16:NEG:N03 |
| OCL-N:04 | N-04 | DIRECT | PM16:NEG:N04 |
| OCL-N:05 | N-05 | DIRECT | PM16:NEG:N05 |
| OCL-N:06 | N-06 | EXPECTED_FUTURE_GAP | candidate reconstruction future |
| OCL-N:07 | N-07 | EXPECTED_FUTURE_GAP | simulation future |
| OCL-N:08 | N-08 | DIRECT | PM16:NEG:N08 |
| OCL-N:09 | N-09 | DIRECT | PM16:NEG:N09 |
| OCL-N:10 | N-10 | DIRECT | PM16:NEG:N10 |
| OCL-N:11 | N-11 | DIRECT | PM16:NEG:N11 |
| OCL-N:12 | N-12 | DIRECT | PM16:NEG:N12 |
| OCL-N:13 | N-13 | DIRECT | PM16:NEG:N13 |
| OCL-N:14 | N-14 | DIRECT | PM16:NEG:N14 |
| OCL-N:15 | N-15 | INHERITED_CERTIFIED | M14-CAP:05 |
| OCL-N:16 | N-16 | DIRECT | PM16:NEG:N16 |
| OCL-N:17 | N-17 | DIRECT | PM16:NEG:N17 |
| OCL-N:18 | N-18 | OUT_OF_SCOPE | derivation-level provenance mechanics (v1.6 PASS) |
| OCL-N:19 | N-19 | OUT_OF_SCOPE | consumer-representation multiplicity (v1.6 PASS) |
| OCL-N:20 | N-20 | DIRECT | PM16:NEG:N20 |
| OCL-N:21 | N-21 | EXPECTED_FUTURE_GAP | candidate derivation future |
| OCL-N:22 | N-22 | INHERITED_CERTIFIED | M13-STATE:01 + M16:INSTANCE:06 |
| OCL-N:23 | N-23 | DIRECT | PM16:NEG:N23 |
| OCL-N:24 | N-24 | DIRECT | PM16:NEG:N24 |

**(d) v1.0 §21/§22 registers and v1.6 §22 appendix — split rows**

| OCL ID | Source | Class | Carried by |
|---|---|---|---|
| OCL-CR:1 | CR-1 authority subject | DIRECT | PM16:CORE4:01/02 (+ M13-STATE:01 inherited) |
| OCL-CR:2 | CR-2 exact binding | DIRECT | PM16:NEG:N02 / SEQ:06 |
| OCL-CR:3 | CR-3 within-Shot handoff | DIRECT | PM16:CORE1:02 + CORE2:01 |
| OCL-CR:4 | CR-4 identity across revisions | DIRECT | PM16:CORE1:04 (+ M12-ID:01/03 inherited) |
| OCL-CR:5 | CR-5 compatibility verdict | DIRECT | PM16:CORE1:03 |
| OCL-CL:1 | CL-1 narrative topology | DIRECT | PM16:NEG:G / CORE2:04 |
| OCL-CL:2 | CL-2 adoptable outputs | OUT_OF_SCOPE | derivation bundles future |
| OCL-CL:3 | CL-3 local substitution identity | DIRECT | PM16:SEQ:03 |
| OCL-CL:4 | CL-4 review separate from Take | DIRECT | PM16:CORE3:02/04 |
| OCL-CL:5 | CL-5 candidate confidence | EXPECTED_FUTURE_GAP | candidate program future |
| OCL-QT:1 | QT-1 realization profiles | OUT_OF_SCOPE | additive executor stress (v1.6 PASS) |
| OCL-QT:2 | QT-2 references/properties | OUT_OF_SCOPE | additive (v1.6 PASS) |
| OCL-QT:3 | QT-3 variant explosion | OUT_OF_SCOPE | additive (v1.6 PASS) |
| OCL-QT:4 | QT-4 recompile prompt | OUT_OF_SCOPE | additive (v1.6 PASS) |
| OCL-QT:5 | QT-5 raw attempt unselected | OUT_OF_SCOPE | additive (v1.6 PASS) |
| OCL-QT:6 | QT-6 controlled iteration | OUT_OF_SCOPE | additive (v1.6 PASS) |
| OCL-QT:7 | QT-7 Take trim/reorder | OUT_OF_SCOPE | additive (v1.6 PASS) |
| OCL-QT:8 | QT-8 preview/final meaning | OUT_OF_SCOPE | additive (v1.6 PASS) |

Coverage totals: 80 oracle rows (33 matrix + 5 rerun additions + 24
negatives + 5 CR + 5 CL + 8 QT), each exactly one class; 0 unclassified.

### 9.1.2 PM16 Cell Universe (certifying cells)

Pass gate: `REQUIRED` cells must PASS for the document PASS;
`OPTIONAL` cells may record NOT_EXECUTED without blocking a Tier-A /
document PASS. An `A+B` cell requires its Tier-A component only.

| Cell | Tier | Pass gate | Expected verdict |
|---|---|---|---|
| PM16:ORACLE:01 | A | REQUIRED | six artifacts byte-equal pins |
| PM16:ORACLE:02 | A | REQUIRED | v1.0 provenance VERIFIED_ORIGINAL |
| PM16:ORACLE:03 | A | REQUIRED | no v1.0/v1.6 contradiction |
| PM16:IDENTITY:01 | A | REQUIRED | squash-aware proof exact |
| PM16:SEQ:01 | A | REQUIRED | initial lobby world; revisions revisitable |
| PM16:SEQ:02 | A+B | REQUIRED | reverse camera; same world/binding; capture exact |
| PM16:SEQ:03 | A | REQUIRED | Shot-local edit stays local |
| PM16:SEQ:04 | A | REQUIRED | boundary-only state lawful without M16 |
| PM16:SEQ:05 | A | REQUIRED | state resolves with no media chain |
| PM16:SEQ:06 | A | REQUIRED | Composition 9 publishes; exact SWR-11 binding |
| PM16:SEQ:07 | A | REQUIRED | lower-control capture; same authority |
| PM16:SEQ:08 | A | REQUIRED | Rev4 approval; local use; Composition 10; Shot-55 wide |
| PM16:SEQ:17 | A | REQUIRED | Eva identity captured; no injury |
| PM16:CORE1:01 | A | REQUIRED | authoritative upright start |
| PM16:CORE1:02 | A | REQUIRED | Shot 24 event/adoption/downstream |
| PM16:CORE1:03 | A | REQUIRED | §10.3 M15 chain via exact callables |
| PM16:CORE1:04 | A | REQUIRED | same occurrence; state survives; history on Rev 2 |
| PM16:CORE1:05 | A+B | REQUIRED | Shot 51 return combines revision+state+camera |
| PM16:CORE1B:01 | A | REQUIRED | evolution-first then event |
| PM16:CORE1B:02 | A | REQUIRED | same durable subject; no remint |
| PM16:CORE2:01 | A | REQUIRED | interior timing exact |
| PM16:CORE2:02 | A | REQUIRED | downstream fresh from authority |
| PM16:CORE2:03 | A | REQUIRED | ordinary M7 healing; Shot 52 |
| PM16:CORE2:04 | A | REQUIRED | flashback resolves pre-injury world |
| PM16:CORE3:01 | A | REQUIRED | fixture inserted per §13.2, logged |
| PM16:CORE3:02 | A | REQUIRED | Take approval: no event/handoff/persistence |
| PM16:CORE3:03 | A | REQUIRED | lineage pinned; adoption creates event+handoff |
| PM16:CORE3:04 | A | REQUIRED | adoption does not approve Take |
| PM16:CORE3:05 | A | REQUIRED | schema-7 refusal; zero side effects |
| PM16:CORE4:01 | A | REQUIRED | vase PI chain |
| PM16:CORE4:02 | A | REQUIRED | no shadow/retarget negatives |
| PM16:EVENTFREE:01 | A | REQUIRED | event-free later Shot on predecessor path |
| PM16:EVENTFREE:02 | A+B | REQUIRED | crown: M16-originated state via M13/M14 |
| PM16:HISTORY:01 | A | REQUIRED | Exact Rerun Shot 22 captured-graph-only |
| PM16:HISTORY:02 | A | REQUIRED | historical 24/25 reconstruct |
| PM16:HISTORY:03 | A | REQUIRED | missing closure fails closed |
| PM16:RECOVERY:01 | A | REQUIRED | backup + independent restore |
| PM16:RECOVERY:02 | A | REQUIRED | restored 0017 verifies full stack |
| PM16:RECOVERY:03 | A | REQUIRED | corruption fails closed |
| PM16:NEG:A | A | REQUIRED | adoption→evolution: state survives |
| PM16:NEG:B | A | REQUIRED | evolution→adoption |
| PM16:NEG:C | A | REQUIRED | no M16 leak into pre-M16 Generation |
| PM16:NEG:D | A | REQUIRED | M15 changes do not reinterpret history |
| PM16:NEG:E | A | REQUIRED | Take ∥ adoption: no ordering dependency |
| PM16:NEG:F | A | REQUIRED | publication preserves PI state binding |
| PM16:NEG:G | A | REQUIRED | narrative topology wins |
| PM16:NEG:H | A | REQUIRED | restore-head re-verification |
| PM16:NEG:N02 | A | REQUIRED | incompatible pair blocks |
| PM16:NEG:N03 | A | REQUIRED | mutable dependency blocks closure |
| PM16:NEG:N04 | A | REQUIRED | capture requires pinned revision |
| PM16:NEG:N05 | A | REQUIRED | no generation→registry route |
| PM16:NEG:N08 | A | REQUIRED | conflicting placement blocks |
| PM16:NEG:N09 | A | REQUIRED | silent remint refused |
| PM16:NEG:N10 | A | REQUIRED | incompatible substitution refused |
| PM16:NEG:N11 | A | REQUIRED | sparse event without handoff invalid |
| PM16:NEG:N12 | A | REQUIRED | Take creates no transition |
| PM16:NEG:N13 | A | REQUIRED | working deletion erases no history |
| PM16:NEG:N14 | A | REQUIRED | missing closure fails closed |
| PM16:NEG:N16 | A | REQUIRED | flashback inherits no later state |
| PM16:NEG:N17 | A | REQUIRED | local edit never auto-promotes |
| PM16:NEG:N20 | A | REQUIRED | translation rewrites no historical bytes |
| PM16:NEG:N23 | A | REQUIRED | live-state removal blocks |
| PM16:NEG:N24 | A | REQUIRED | one binding owns preview+final |
| PM16:IDENTITY:02 | B | OPTIONAL | live pin == frozen pin |
| PM16:TIERB:01 | B | OPTIONAL | one event-free Shot on certified path |
| PM16:TIERB:02 | B | OPTIONAL | runtime identities pinned |
| PM16:G8:01 | A | REQUIRED | entry disposition recorded on full PASS |

Cell totals: 67 cells (64 REQUIRED — 61 Tier-A and 3 A+B —
and 3 OPTIONAL B-only). Every DIRECT OCL row maps to at least
one REQUIRED cell; INHERITED_CERTIFIED appears only in OCL
rows, never as a cell.

### 9.1.3 Invariant rollups (NOT cells)

The five v1.6 §18 invariant families are verified as ledger roll-ups
over the cells above, not as separate certifying cells:
identity ← SEQ:01/02/17, CORE1:04, CORE4:01; temporal ← CORE2:01–04,
NEG:G, SEQ:03/04; authority ← CORE3:02–05, NEG:N05/N12, OCL EXPECTED_FUTURE_GAP
absences; historical ← HISTORY:01–03, RECOVERY:01–03, NEG:C/D/N20;
execution ← CORE3:05, EVENTFREE:01/02, OCL-v1:30/31 dispositions.

# 10. CORE-1 — M16 persistence through lawful M15 evolution

This is the highest-information integration chain.

## 10.1 Initial Production Instance state

Construct through lawful M11–M14 surfaces:

```text
Lobby Composition 8

Chair Production Revision 2

chair-07 durable occurrence

chair-07 recognized Production Instance authority subject

explicit authoritative PI-feature transition
establishing chair-07 = upright
at the applicable Shot/start boundary

exact Composition ↔ Spatial binding
```

There is no ambient/default `upright` fact.

The harness must author the initial `upright` state through the existing Production Instance feature-transition authority.

It may not seed an unstated default into the state resolver.

Capture the applicable early Shots only after that authoritative start-state path exists.

## 10.2 M16 consequence

At Shot 24:

```text
Shot/start:
    chair-07 = upright

intra-Shot event:
    upright → fallen

explicit persistent-consequence adoption

Shot/end:
    chair-07 = fallen

later Shot/start:
    chair-07 = fallen
```

Take approval remains independent.

## 10.3 Exact lawful M15 revision-evolution surface

The later Chair Revision 3 update may not use direct database mutation or an invented shortcut.

R3 must exercise the published M15 flow:

```text
newer immutable Chair Production Revision 3
        ↓
affected-current-work / update discovery
        ↓
explicit source→target compatibility assessment
        ↓
consumer-specific verdict
        ↓
compatibility-gated application
to selected current working occurrence
        ↓
same occurrence identity
        ↓
ordinary Composition publication
        ↓
updated Composition↔Spatial binding/readiness
where required
```

Source fit is complete (enumerated from the published M16 checkout 488031a, 2026-09-19, mechanically verified via git rev-parse/diff-list). The exact implemented chain:

### 10.3.0 Occurrence revision-tracking policy (preamble)

```text
module:     soloring/compatibility/impact.py
callables:  tracking_policy(conn, *, composition_id,
              occurrence_id)
            put_tracking_policy(conn, *, composition_id,
              occurrence_id, mode, expected_policy_version)
service:    compatibility/service.py::read_tracking /
            put_tracking_policy bridge under BEGIN IMMEDIATE
API:        GET/PUT /compositions/{composition_id}/occurrences/
            {occurrence_id}/revision-tracking
inputs:     composition_id, occurrence_id, mode,
            expected_policy_version (optimistic concurrency)
evidence:   policy version + mode
owns:       the occurrence's revision-tracking mode row only
does NOT:   touch working revisions, state, or assessments
```

### 10.3.1 Update discovery

```text
module:     soloring/compatibility/impact.py
callable:   update_discovery(conn, *, production_object_id)
service:    compatibility/service.py::revision_updates
API:        GET /production-objects/{production_object_id}/
            revision-updates
inputs:     production_object_id (one bounded query class over
            composition_working_occurrences x tracking policy)
evidence:   set-oriented tracked-use info + concrete newer
            candidate revisions; NO assessment identity
owns:       nothing — read-only
does NOT:   create an assessment, select a latest revision,
            or mutate any row (module docstring §16.2)
```

### 10.3.2 Compatibility assessment

```text
module:     soloring/compatibility/evaluator.py
callable:   assess_revision_update(session, *,
              from_revision_id, to_revision_id)   # §13.1
service:    compatibility/service.py::create_assessment
            (+ advisory_references response projection)
API:        POST /production-revisions/{from_revision_id}/
            compatibility-assessments  body {to_revision_id}
inputs:     verified from/to Production Revisions (same
            project); one BEGIN IMMEDIATE transaction
evidence:   immutable assessment (assessment_id, report_hash,
            scope_hash) + per-use children with verdicts
            {COMPATIBLE_AS_IS,
             COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION,
             REQUIRES_REVIEW, INCOMPATIBLE} and translator
            pins; NO_CURRENT_USES persists nothing; identical
            coordinates converge (200/201 by convergence)
owns:       append-only assessment + use evidence rows only
does NOT:   mutate composition_working_occurrences, working
            versions, occurrence state, or any M16 plane
```

### 10.3.3 Compatibility-gated application

```text
module:     soloring/compatibility/apply.py
callable:   apply_revision_update(session, *, assessment_id,
              selected_uses)   # §14.1–§14.3
service:    compatibility/service.py::apply_assessment
            (+ _restore_idempotent_translator_projection)
API:        POST /production-compatibility-assessments/
            {assessment_id}/apply  body {uses: [...]}
inputs:     assessment_id; selected uses (must belong to the
            assessment; per-composition consistent
            expected_working_version); fenced BEGIN IMMEDIATE;
            exact source/target snapshot-hash re-verification;
            idempotency probe before fresh-path state checks
evidence:   operation_id + operation_hash + ordered items with
            before/after spec hashes and translator pins;
            idempotent flag on exact retry
owns:       INSERT production_update_operations/items
            (immutable operation evidence);
            UPDATE composition_working_occurrences
            SET production_revision_id = target
            WHERE ... AND production_revision_id = source
            (guarded same-source update);
            UPDATE compositions SET working_version = +1
            (guarded stale_working_version check)
does NOT:   change occurrence_id (identity untouched),
            publish any Composition revision, touch any
            Shot/ShotRevision/Generation/Take row, or touch
            any M16 plane (events, proposals, reviews, PI or
            entity feature transitions) — the guarded UPDATE
            touches production_revision_id only, which is the
            structural reason adopted M16 state must survive
            evolution, and what CORE-1 proves behaviorally
```

### 10.3.4 Composition publication

```text
module:     soloring/composition/readiness.py
callable:   publish_composition_revision(session,
              composition_id, *, expected_working_version)
            # frozen §10: coherent freeze, canonicalize outside
            # the fence, writer-fence revalidation
API:        POST /compositions/{composition_id}/publish
inputs:     expected_working_version (== the version the §10.3.3
            apply incremented; stale → EditConflict)
evidence:   new immutable Composition Revision + snapshot hash
owns:       the composition revision + spec rows it freezes
does NOT:   mint new occurrence ids (working occurrences are
            carried as-is), or touch spatial binding
```

### 10.3.5 Binding publication + readiness selection

```text
module:     soloring/production_world/binding.py
callable:   publish_binding(session, *,
              composition_revision_id,
              spatial_world_revision_id)   # §11.3 compare-and-
            # freeze; 201 created / 200 converged
API:        POST /composition-revisions/{composition_revision_
            id}/spatial-bindings  body {spatial_world_revision_
            id}; then PUT /shots/{shot_id}/production-world-
            selection body {binding_id, expected_binding_id}
inputs:     exact composition revision + spatial world revision
evidence:   binding_id + binding_hash over the derived pair
owns:       the immutable binding row + shot selection pointer
does NOT:   mutate occurrences, production revisions, or state
```

No direct SQL substitute is allowed for CORE-1.

Result:

```text
chair-07 occurrence identity unchanged

chair-07 persistent state still fallen

source Production Revision now Chair Revision 3

historical captured Shots still use Revision 2
```

## 10.4 Return Shot

Shot 51 combines:

```text
newer Lobby Composition

same chair-07

Chair Revision 3

chair-07 fallen

exact spatial binding

new camera
```

This is the integrated return-after-upgrade proof.

---

# 11. CORE-1B — inverse evolution/adoption order

R3 proves the mirror ordering.

After lawful M15 evolution has already advanced an occurrence:

```text
M15 revision update first
        ↓
later Shot resolves evolved production occurrence
        ↓
new M16 event targets same durable authority subject
        ↓
event before-state comes from evolved current state
        ↓
explicit persistence adoption
        ↓
ordinary downstream state resolves adopted consequence
```

Required proof:

```text
revision evolution does not make occurrence unaddressable to M16

M16 does not mint a replacement occurrence

before-state chains from lawful evolved world

adoption targets same durable authority subject
```

Together:

```text
adoption → evolution

evolution → adoption
```

are both certified.

---

# 12. CORE-2 — forehead injury, healing, and flashback

## 12.1 Intra-Shot injury

Shot 25:

```text
t = 0:
    injury = none

t = 3100 ms:
    none → fresh_injury

t < 3100:
    none

t >= 3100:
    fresh_injury

Shot/end−:
    fresh_injury
```

Persistence is explicitly adopted.

The ordinary Shot/end feature transition becomes:

```text
fresh_injury
```

Shot 26 resolves:

```text
injury = fresh_injury
```

without inspecting Shot 25 pixels.

## 12.2 Healing uses ordinary M7 continuity

The later transition:

```text
fresh_injury → healing
```

is authored as an **ordinary M7 continuity-feature boundary/Shot-end transition**.

It is not represented as another M16 event.

This proves that M16 returns its adopted consequence into the ordinary temporal continuity model.

Shot 52 resolves:

```text
injury = healing
```

## 12.3 Flashback ordering stress

The flashback Shot is created **after Shots 25–52 and their later-state authority already exist**.

Only afterward is it placed at an earlier canonical narrative position.

Therefore:

```text
database / authoring creation order:
    late

canonical narrative position:
    before injury
```

It must resolve:

```text
injury = none

chair-07 = pre-fall state

vase = intact
where applicable
```

The regression fails if any of these determines continuity instead:

```text
row creation order
Shot number
presentation order
current/latest state
latest transition
```

---

# 13. CORE-3 — Take, proposal, adoption, and schema-7 refusal

## 13.1 Purpose

CORE-3 proves:

```text
Take approval
is independent from
M16 proposal/event/persistence authority

and

schema-7 authority
fails closed before Generation-side effects
```

These assertions do not depend on GPU image quality.

## 13.2 Frozen Tier-A evidence-input fixture exception

There is no lawful GPU-free production path that creates a real Generation row.

Therefore R3 freezes one narrowly scoped exception to §7.1.

For CORE-3 only, Tier A may directly insert the minimum exact Generation/Take lineage rows required to serve as **evidence inputs**.

Those rows are not treated as proof that Generation execution occurred.

Rules:

```text
scope:
    CORE-3 only

purpose:
    provide upstream immutable Generation/Take evidence lineage

method:
    exact labelled DB fixture insertion

allowed rows:
    only minimum Generation/Take lineage
    and unavoidable referential prerequisites

forbidden:
    event rows
    proposal review rows
    handoffs
    persistence transitions
    Take approval mutation
    schema-7 capture result
    expected result rows
```

Every fixture insert is logged in the evidence package with:

```text
SQL/domain fixture operation
inserted row identities
source ShotRevision identity/hash
Generation identity
Take identity
canonical values/hashes where applicable
```

The fixture is labelled:

```text
NON-PRODUCTION EVIDENCE-INPUT FIXTURE
NOT EXECUTION EVIDENCE
```

The fixture exists before every CORE-3 invariant being asserted.

Therefore it cannot satisfy the tested conclusion by construction.

No other central sequence phase acquires permission for direct row seeding from this exception.

After insertion, the frozen Generation/Take evidence-input rows become immutable accumulated Project history: later R3 cells may read and cite them, including historical-leakage tests, but no later cell may mutate, replace, or re-seed them.

### 13.2.1 Frozen fixture definition (exact rows and commands)

The fixture is derived from the published 0017 schema. Two rows are
inserted, in this order, through a single transaction:

**Row 1 — `generations`** (every NOT NULL column receives a value;
every nullable column not listed receives SQL NULL):

```sql
INSERT INTO generations (
    id, shot_id, shot_revision_id, generation_number, status,
    operation, executor, workflow_id, workflow_version,
    workflow_template_hash, manifest_hash, model, model_version,
    compiled_prompt, negative_prompt, prompt_compiler_version, seed,
    parameters_json, workflow_spec_json, workflow_spec_hash,
    queued_at, created_at, updated_at, executor_submission_state)
VALUES (
    :G, :shot, :rev, 1, 'succeeded', 'generate', 'comfy',
    'pm16-core3-evidence-fixture', 1,
    :TEMPLATE_HASH, :MANIFEST_HASH, NULL, NULL,
    'PM16 CORE-3 evidence-input fixture (non-production)',
    NULL, 'frozen-fixture', NULL,
    :PARAMS, :SPECJ, :SPECH,
    :NOW, :NOW, :NOW, 'not_started')
```

Deterministic values (exact literals or derivation rules):

```text
G             = 00000000-3330-4000-8000-00000000c301  (fixed UUID)
MANIFEST_HASH = 67e43719e8e2610ec5e582d37b7e9bb083dd1ae389c156d9765efcf76bf23236   (pinned: sha256 of
                $CK/workflows/hunyuan_i2v_v1/manifest.json)
TEMPLATE_HASH = c7ee0fb9a6c430623f086b0df242ffcd6aefe1b3a3f44eec0d2cd8197aed6b3f   (pinned: sha256 of
                $CK/workflows/hunyuan_i2v_v1/workflow.json)
PARAMS = {"schema_version":1}
SPECJ  = {"fixture":true,"inputs":{},"schema_version":1}
         (recovery-valid canonical bytes: the empty inputs object is
          the exact relationship to the fixture's intentionally empty
          generation_inputs set)
SPECH  = dc09d07f73fde694830eb46ea89f48dfa3ef0a9d58adad8fd0a902d34145b10c  (derived: sha256 of the exact canonical SPECJ bytes)
NOW    = strftime('%Y-%m-%dT%H:%M:%fZ','now')        (DB clock)
shot   = the CORE-3 Shot id (in-run value)
rev    = the real event-free ShotRevision id captured in §13.3
         (in-run value; the fixture NEVER fabricates a revision)
```

**Fixture-support artifact materialization (before Row 1).** The
harness hashes the exact certifying-tree source bytes

```text
$CK/workflows/hunyuan_i2v_v1/manifest.json
$CK/workflows/hunyuan_i2v_v1/workflow.json
```

requires exact equality to MANIFEST_HASH / TEMPLATE_HASH above, and
places the descriptor-coherent pair through the REAL
WorkflowArtifactStore (capture_package on the installed
workflow-package.json descriptor, then content-addressed place of
manifests/templates) into the run data root. This is fixture-support
materialization ONLY — no execution, queueing, worker submission, or
evidence that a real Generation occurred; recovery must find the same
content-addressed artifacts any real schema-1 Generation would own.

The DB fixture remains EXACTLY two inserted rows. No GenerationInput,
queue, worker, observation, spatial, event, transition, proposal,
review, or result rows may be added merely to appease recovery.

**Row 2 — `takes`:**

```sql
INSERT INTO takes (id, shot_id, generation_id, output_key, created_at)
VALUES (
    '00000000-3330-4000-8000-00000000c302', :shot, :G, 'video:0',
    :NOW)
```

**What the fixture provably does NOT populate** (each is a tested
CORE-3 outcome or a forbidden row per §13.2):

```text
shots.approved_take_id     — set only by the real POST /takes/{id}/approve
shot_intra_shot_events     — no rows
continuity_*_transitions   — no rows
shot_intra_shot_event_proposals / persistent_consequence_reviews
                           — no rows (proposals are created via the
                             real §11.1 ingestion against this lineage)
derived observation/spatial/queue/worker rows — none
```

The fixture exists before every CORE-3 assertion; no assertion tests
the presence/absence of `generations`/`takes` rows themselves.

**Fixture-root identity.** Immediately after insertion, the harness
computes and records:

```text
fixture_root = sha256(
    canonical_json_bytes({
        "generation": {all inserted column values of Row 1,
                       with NOW fields replaced by the recorded
                       timestamps},
        "take":       {all inserted column values of Row 2},
        "recovery_support_artifacts": [
            {"kind": "manifests", "sha256": MANIFEST_HASH},
            {"kind": "templates", "sha256": TEMPLATE_HASH},
        ],
    }))
```

The value is written to
`evidence/fixtures/core3-evidence-input-fixture.json` together with
the full row dumps and the source ShotRevision id/snapshot_hash.
PM16:HISTORY and PM16:NEG:C cells re-read these rows, re-derive the
same root, AND re-verify both artifact FILES by hash through the
store root to prove immutability of the whole fixture across the
sequence.

## 13.3 Tier-A Take/proposal sequence

Begin from an event-free captured ShotRevision.

Insert the exact frozen Generation/Take evidence-input lineage under §13.2.

Then:

```text
approve Take
        ↓
assert:
    approved_take_id changes lawfully
    no M16 event created
    no handoff created
    no persistence adopted
```

Create or ingest a valid Take/analyzer-backed M16 proposal tied to the exact fixture lineage.

Then:

```text
review proposal
→ adopt event/persistence
→ create exact event + agreeing handoff
```

Assert:

```text
persistence adoption did not approve Take

Take approval did not create event/handoff

proposal lineage still pins exact
ShotRevision / Generation / Take input identities
```

## 13.4 Schema-7 refusal

Capture a new event-bearing schema-7 ShotRevision.

Attempt Generation creation through the real Generation service.

Expected result:

```text
INTRA_SHOT_REALIZATION_UNSUPPORTED
```

and prove zero side effects:

```text
no Generation row

no GenerationInput

no derived observation publication

no derived spatial publication

no workflow package publication

no queueing

no worker submission

no stripped/lowered schema

no prompt-only event approximation
```

This refusal is a **PASS condition**.

The direct evidence-input fixture from §13.2 is excluded from the zero-side-effect accounting because it predates the tested schema-7 Generation attempt and has a separately frozen identity.

---

# 14. CORE-4 — Production Instance consequence

The regression includes a stateful Production Instance target independently of Eva's CreativeEntity case.

Use `vase-main`, `chair-07`, or the exact frozen pressure-test occurrence selected during coverage enumeration.

Prove:

```text
stable Production Instance occurrence
        ↓
recognized durable authority subject
        ↓
explicit authoritative Shot/start state
        ↓
M16 event
        ↓
terminal state
        ↓
explicit Shot/end handoff
        ↓
later ordinary state resolution
```

Negative assertions:

```text
no duplicate CreativeEntity shadow authority

no display-name retarget

no hierarchy-path retarget

no representation/file-path retarget

no proximity fallback
```

---

# 15. Crown integration cell — event-originated state executes normally later

This is a separate named acceptance cell.

It proves:

```text
M16 intra-Shot event
        ↓
explicit persistence adoption
        ↓
ordinary existing continuity transition authority
        ↓
later event-free Shot
        ↓
M13 production-world resolution
        ↓
M14 observation/capture path
        ↓
ordinary supported execution semantics
```

The later Shot itself contains no active M16 event.

Therefore it remains on the predecessor event-free capture/execution path rather than schema 7.

This proves the central integration property:

> An M16-originated persistent consequence becomes ordinary downstream world state rather than being trapped behind event-aware execution support that does not yet exist.

---

# 16. Tier-A / Tier-B execution annotation

Every coverage cell declares:

```text
tier = A
tier = B
tier = A+B
```

## 16.1 Tier A — mandatory

Tier A proves the full authority/history sequence without requiring stochastic GPU output.

It covers:

```text
domain/API operations

SQLite authority

capture

compatibility

event fold/adoption

Take/proposal independence

history

schema-7 refusal

recovery

negative integration cases
```

A Tier-A PASS is the required post-M16 integrated-regression disposition.

## 16.2 Tier B — optional live corroboration

Tier B executes one or more **event-free downstream Shots** through the certified M14 executor path.

Recommended:

```text
Shot 51

or

Shot 52
```

Tier B must not attempt to render active schema-7 event timing.

## 16.3 Shot 22 annotation

Any old shorthand saying Shot 22 was `captured/executed` is split:

```text
Tier A:
    capture and historical execution contract only

Tier B:
    live execution only if explicitly selected
```

No Tier-A PASS cell silently requires GPU availability.

---

# 17. Required cross-milestone adversarial matrix

In addition to inherited local milestone evidence, R3 directly executes:

```text
A. M16 adoption
   → M15 revision evolution
   → state survives

B. M15 revision evolution
   → later M16 event
   → adoption succeeds against same durable subject

C. current M16 event/handoff changes
   → old pre-M16 Generation / ShotRevision
   → no current-state leakage

D. current M15 revision changes
   → historical schema-7 Shot
   → immutable captured semantics preserved

E. Take approval ∥ persistence adoption
   → no hidden ordering dependency
   → neither performs the other's authority mutation

F. Composition publication preserving occurrence
   → Production Instance M16 state remains bound
      to same durable subject

G. flashback authored late / positioned early
   → canonical narrative topology wins

H. restore head 0017
   → M13 + M14 + M15 + M16 historical semantics verified
```

These remain REQUIRED R3 cells even if their constituent local invariants already have predecessor proof-map coverage; their oracle-case mapping lives in the OCL rows.

---

# 18. Inherited M16 proof-map relationship

R3 is not an extension of the frozen M16 164-cell universe.

The 164-cell map remains unchanged.

R3 may cite exact M16 cells as `INHERITED_CERTIFIED`, but creates its own namespace:

```text
PM16:ORACLE:*
PM16:IDENTITY:*
PM16:CORE1:*
PM16:CORE1B:*
PM16:CORE2:*
PM16:CORE3:*
PM16:CORE4:*
PM16:EVENTFREE:*
PM16:HISTORY:*
PM16:RECOVERY:*
PM16:NEG:*
PM16:TIERB:*
PM16:SEQ:*
PM16:G8:*
```


The complete R3 cell universe is frozen independently before execution.

No R3 cell is retrospectively added to `M16:*`.

---

# 19. Historical and recovery phase

The accumulated production history must survive a real backup/restore cycle.

After the sequence completes:

```text
accumulated M11–M16 Project
        ↓
certified backup
        ↓
independent restored database
        ↓
historical verification
```

On the restored database prove:

```text
current final world state coherent

historical Shot 22 resolves exact old graph

historical M16 Shot 24/25 reconstructs
captured start/event/terminal/handoff semantics

current M15 revision evolution
does not reinterpret old captures

current M16 working events/proposals/reviews
do not reinterpret old captures

historical reproduction uses captured graph only
```

Then create a disposable corruption copy and mutate at least one cross-milestone historical semantic field.

Required result:

```text
restore / historical certification fails closed
```

Synthetic milestone recovery fixtures do not substitute for this accumulated-history proof.

---

# 20. Evidence package

Required layout:

```text
post-m16-integrated-r3-evidence/
  oracles/

  guards/
    identity-guard-tier-a-pre.log
    identity-guard-tier-a-post.log
    identity-guard-tier-b-pre.log
    identity-guard-tier-b-post.log

  commands/
    <per-command logs>

  fixtures/
    core3-evidence-input-fixture.log
    core3-evidence-input-fixture.json

  cells/
    <per-cell evidence records>

  results/
    pytest-tier-a.txt
    tier-b.txt
    recovery.txt
    coverage-ledger.json

  identities/
    implementation-identity.txt
    publication-identity.txt
    publication-branch-leg.txt
    publication-tree-equivalence.txt
    publication-delta.txt
    runtime-identity.txt

  MANIFEST.json
```

Tier-B-only files are omitted when Tier B does not run.

The Tier-A runner prepares results/ before launch, captures the driver
stdout/stderr transcript contemporaneously, and captures the true
driver exit through the pipeline. Post-run transcript reconstruction
is prohibited.

Every command record contains:

```text
command
working directory
start timestamp
end timestamp
exit status
stdout/stderr artifact identity
```

## 20.1 Manifest discipline

`MANIFEST.json` enumerates every evidence payload file and contains:

```text
relative path
byte count
SHA-256
semantic role
producer command/cell where applicable
```

No README, log, result file, guard transcript, fixture declaration, oracle copy, or auxiliary artifact may sit outside the manifest because it is merely descriptive.

The manifest cannot recursively hash itself.

Therefore:

```text
MANIFEST hashes every other evidence-package file.

The final results record pins the exact SHA-256
and byte count of MANIFEST.json itself.
```

Part II records:

```text
manifest_sha256 = <exact>
manifest_bytes  = <exact>
entry_count     = <exact>
```

That produces one externally pinned manifest root.

---

# 21. Results grammar

Every R3 cell records:

| Field                | Required value                                                    |
| -------------------- | ----------------------------------------------------------------- |
| Cell ID              | stable `PM16:*` ID                                                |
| Source / certification role | exact oracle/invariant source, or `certification-mechanics` |
| Owning milestone(s)  | M11–M16                                                           |
| OCL source mapping   | OCL row ID(s) this cell carries (DIRECT rows only; cells without an oracle case state `certification-mechanics`) |
| Tier                 | A / B / A+B                                                       |
| Execution status     | PASS / FAIL / NOT_EXECUTED / EVIDENCE_MISSING                     |
| Domain verdict       | exact expected meaning                                            |
| Evidence             | exact command/test/hash/result                                    |
| Historical check     | yes/no + evidence                                                 |
| Notes                | diagnostic only                                                   |

Document disposition is exactly:

```text
PASS
FAIL
EVIDENCE_SET_INCOMPLETE
```

A note cannot override a failing status.

---

# 22. Stop rules

Certification stops immediately if:

1. an oracle byte differs from its pin;
2. v1.0 provenance is unresolved;
3. v1.0/v1.6 reconciliation exposes a material contradiction;
4. a required oracle cannot be retrieved;
5. the implementation/publication branch-leg or tree-equivalence proof differs from §4.3;
6. either identity guard fails;
7. migration file-set/head verification differs from `0017_m16_intra_shot_consequences`;
8. a REQUIRED cell fails;
9. an unclassified pressure-test case is discovered;
10. a result requires current/latest substitution;
11. stable occurrence identity must be reminted to make continuity work;
12. M15 evolution loses or retargets M16 state;
13. M16 adoption after M15 evolution cannot resolve the same durable subject;
14. Take approval changes persistence;
15. persistence review changes Take approval;
16. CORE-3 requires any direct DB fixture beyond the frozen evidence-input exception;
17. schema-7 authority is stripped, lowered, prompt-approximated, or partially executed;
18. historical reads depend on current Production Revision, event, transition, proposal, or world state;
19. recovery cannot certify the accumulated M11–M16 history;
20. a supposedly expected future gap was not classified before execution;
21. passing would require a product-code correction during the run.

---

# 23. Repository/publication disposition

The certifying Tier-A run occurs against the clean detached **R3 correction baseline** (§0.2 — commit/tree identical to R2's) — the published M16 baseline plus exactly the approved recovery correction.

The R3 specification, harness, and evidence may not change that system-under-test tree before certification.

After PASS:

```text
certifying evidence
    remains evidence about published M16

then, separately if authorized:

R3 specification + regression harness
    may be committed as an evidence/test-only change
```

Such a later commit is not the commit certified by R3.

Its publication requires separate review.

If boundary/source-fit allowlists must change to admit the new spec/test files, those changes belong to that later evidence-only publication step.

They may not be inserted into the M16 baseline before certification.

The post-M16 harness remains outside the frozen M16 164-cell map permanently.

---

# 24. G8 entry disposition

Only a complete R3 PASS may state:

> **POST-M16 INTEGRATED PRODUCTION-WORLD REGRESSION: PASS.
> The implemented M11–M16 production-world chain remains coherent on the exact R3 correction baseline (§0.2) derived from published M16. The roadmap prerequisite for entering G8 is satisfied. G8 remains OPEN. No M17 implementation is authorized.**

R3 carries forward, but does not answer:

```text
A1 Dialogue Line revision identity

A7 Vocal Performance revision
+ retained approved audio closure

exact audio / Performance / Shot temporal mapping

derived dialogue-alignment evidence contract

minimum body/facial Performance representation

vocal ↔ facial synchronization
+ compatibility semantics

Shot capture
+ historical closure
```

---

# 25. Maximum product claim after PASS

The maximum justified claim is:

> **SoloRing's R3 correction baseline (the published M16 baseline plus exactly the two-file recovery correction of §0.2 — the same product baseline R2 pinned) preserves the implemented M11–M16 production-world program as one coherent accumulated system. Reusable Production Revisions and surviving occurrence identities remain stable through explicit compatibility-gated evolution; persistent state survives lawful realization revision changes; later evolved occurrences remain valid targets for new intra-Shot consequences; intra-Shot changes preserve true Shot-start state and persist only through explicit adoption into existing continuity authority; adopted consequences become ordinary downstream world state consumable by event-free M13/M14 capture and execution; current production evolution cannot reinterpret captured history; and recovery and historical reproduction operate from retained immutable authority rather than current/latest state. Active schema-7 event realization remains deliberately unsupported and fails closed until a later reviewed Performance execution milestone provides that capability. This claim is made about the correction baseline; its exact two-file departure from published M16 is pinned in §0.2.**

That claim does not include:

```text
event-aware animation execution
body/facial Performance implementation
production lip sync
exact contact implementation
universal rigging
editorial authority
full Sound Post
future G8/M17 functionality
```

---

# 26. Freeze prerequisites

R3 is freezeable only when all are complete:

* [x] lineage/* and correction/* byte-verified against FREEZESET.sha256; embedded lineage/correction identities mechanically equal the §0.1/§0.2 pins (R1 + R2 lineage files); the closed R2 specification payload is exactly 73134 B / d6c5285e2e00f8eb6bc65a367d4923845c216a094e1ce7dcbd53e8e2ecd8b163, its Part-I prefix equals frozen R2 70102 B / 5ad51e1dbe5bbe68753d1112c14a4eb66e4f526325331bbb2df63eea61682dad, and its Part-II disposition matches the verified R2 Run1 ledger/guards (FAIL; 59 REQUIRED PASS / 5 REQUIRED NOT_EXECUTED / 3 OPTIONAL NOT_EXECUTED; pre+post guards PASS; RECOVERY:01 NOT_EXECUTED with the HARNESS:FAIL record);
* [x] correction ancestry + two-file delta + blob identities + patch SHA + commit-object bytes mechanically re-verified (identical commits to frozen R2's baseline);
* [x] CORE-3 fixture-contract artifacts byte-verified: the certifying-tree manifest.json/workflow.json hash exactly to the §13.2.1 pins and are descriptor-coherent through the real WorkflowArtifactStore;
* [x] exhaustive v1.0/v1.6 coverage ledger; zero unclassified cases;
* [x] exact six R7 normative artifacts collected and byte-verified;
* [x] original v1.0 scenario provenance established;
* [x] exact v1.0 SHA-256 recorded;
* [x] human v1.0↔v1.6 reconciliation review completed;
* [x] old v1.1/local reruns explicitly classified non-authoritative;
* [x] canonical freeze-set path for this exact R3 file recorded;
* [x] Part-I byte-boundary rule verified;
* [x] full certified-implementation commit/tree recorded;
* [x] full pre-M16-main identity recorded;
* [x] full M16 branch publication identities recorded;
* [x] full published-M16 commit/tree/tag identities recorded;
* [x] squash-aware branch-leg proof mechanically executable;
* [x] exact branch-tip ↔ squash tree equality mechanically executable;
* [x] exact four-file publication delta enumerated;
* [x] full Tier-B MaterializerContract pin recorded if Tier B is included;
* [x] complete `PM16:*` cell universe frozen;
* [x] every cell assigned tier and pass gate;
* [x] exact M15 update-discovery callable named;
* [x] exact M15 compatibility-assessment callable named;
* [x] exact M15 compatibility-gated application callable named;
* [x] exact subsequent Composition publication/binding path named;
* [x] explicit authoritative PI `upright` Shot/start transition mechanism frozen;
* [x] CORE-1B inverse ordering frozen;
* [x] CORE-2 ordinary M7 fresh→healing transition frozen;
* [x] CORE-2 late-created/early-positioned flashback mechanism frozen;
* [x] CORE-3 direct evidence-input fixture exception frozen exactly as §13.2;
* [x] CORE-3 exact permitted fixture rows and commands frozen;
* [x] Tier-A matrix contains no hidden GPU requirement;
* [x] accumulating-fixture/fail-fast/full-restart semantics frozen;
* [x] exact Alembic-head preflight frozen;
* [x] pre/post identity-guard commands frozen;
* [x] evidence-manifest schema frozen;
* [x] post-PASS repository disposition frozen;
* [x] Part-I byte count recorded;
* [x] Part-I SHA-256 recorded.

Only then:

```text
R3 SPECIFICATION FROZEN
```

======== END OF FROZEN SPECIFICATION ========

# PART II — EXECUTION RESULTS

**Status:** not executed.

The fields below remain unpopulated until R3 Part I has been frozen and execution has been separately authorized.

## A. Frozen specification identity

```text
part_i_byte_count: 76957
part_i_sha256: cd382d97abc40033c4b914446c6e75ba1ae98b83c0dfac31e74968809f150e88
whole_preexecution_file_sha256:
  932228beea01500bcecc5778688b51fd018592ce55a8929d2fb3d925948e27d2
  (defined: SHA-256 of the immediate PRECURSOR file — after the
   final two §26 boxes are ticked and while this §A remained blank;
   it hashes that precursor, NOT this final populated file)
```

## B. System-under-test identity

```text
parent_commit:
certifying_commit:
certifying_tree:
certifying_delta_proof:
certified_implementation_commit:
certified_implementation_tree:

pre_M16_main:
branch_publication_commit_1:
branch_publication_tip:

published_M16_commit:
published_M16_tree:
M16_tag_object:
M16_tag_peeled_commit:
```

## C. Oracle verification

```text
six_artifact_verification:
v1.0_provenance_verdict:
v1.0_sha256:
v1.0_v1.6_reconciliation_verdict:
```

## D. Tier A

```text
pre_guard:
execution:
post_guard:
disposition:
```

## E. Tier B

```text
status:
runtime_identity:
pre_guard:
execution:
post_guard:
disposition:
```

## F. Evidence root

```text
manifest_sha256:
manifest_bytes:
entry_count:
```

## G. Final disposition

```text
PASS
FAIL
or
EVIDENCE_SET_INCOMPLETE
```

## H. G8 entry

```text
NOT EVALUATED
