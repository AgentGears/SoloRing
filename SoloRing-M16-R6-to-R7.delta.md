# SoloRing M16 — R6 -> R7 Normative Delta Record

**Date:** 2026-09-17
**Predecessor:** frozen R6 — SHA-256 `cef6a82b4101df1f61a814e54df5d9f8fcffea1a14335ee8ef1c479eeadf839d` (127,396 B / 2,791 L)
**Cause:** R6 contradiction confirmed by milestone ruling (PR #21 review `5237368385` follow-up). §12.1 requires the direct-review request to carry an expected current working snapshot hash; §9.2 defines `working_snapshot_hash` as NULL exactly while an M16 blocker (an unresolved `require_handoff` event) exists — which is the direct-adoption precondition; G5-5's resolution order places the working snapshot after the M16 resolver. No R6 clause defines the requested fence's meaning for the direct case. Ruling: option (b) — remove the field, do not substitute another value.

## Normative changes (the complete R7 delta)

1. **§7.5.1** — the event-source `review_basis_hash` grammar becomes exactly
   `{schema_version, source, decision, expected_event_set_hash, expected_handoff}`.
   `expected_working_snapshot_hash` is REMOVED, not replaced. For
   `decline_persistence`, `expected_handoff` is null. Direct event review is
   fenced by current M16 authority: the source event hash identifies the
   exact semantic event reviewed; the event-set hash commits the complete
   current M16 event set and duration; and under the same `BEGIN IMMEDIATE`
   the service re-resolves current predecessor Shot/start authority and
   performs the complete prospective fold before any A2 mutation, so a stale
   start-state dependency still fails without any working-snapshot hash.
2. **§12.1** — the request carries exactly the expected source event hash and
   the expected current event-set hash. No prior ShotRevision capture is
   required: the authored-authority flow `author event -> adopt persistence
   -> future capture` is lawful. The exact-retry probe is located by the
   review's immutable source coordinates (source event id + hash + decision,
   unique under the reviews uniqueness index).
3. **§12.4** — a later capture or unrelated whole-Shot change never
   manufactures a new direct-review basis: direct retries are located by
   immutable source coordinates and validated against committed-result drift
   only.
4. **Recovery (0017 verification)** — event-source review-basis verification
   recomputes the exact §7.5.1 R7 field set; a missing or extra field
   (including any `expected_working_snapshot_hash`) is corruption. The
   C-depth verifier is narrowly reopened for this event-source branch only.
5. **Proof map** — two new cells: `M16:ADOPT:21` (two-field direct adopt
   succeeds from `working_snapshot_hash == null`; the Shot then becomes
   M16-ready and obtains its ordinary authoritative working snapshot hash)
   and `M16:ADOPT:22` (direct review basis/operation grammar carries no
   working-snapshot field; exact §7.5.1 R7 roots). Because these two cells
   are normative, R7's frozen universe is **164 cells with ADOPT = 13**
   (R6 froze 162 with ADOPT = 11; every other family count is unchanged).
   The correction-round regressions ADOPT:12-20 are deliberately OUTSIDE the
   frozen universe — they are review evidence, not frozen cells.

## Explicitly unchanged

- Proposal-source §7.5.2 in full: proposal adoption still reads the real
  current working snapshot hash once and requires equality with the pinned
  source ShotRevision when creating authority. A proposal is historical
  evidence that must not silently rebase; a direct event is already current
  authoritative working state. The distinction is intentional.
- §9.2/§9.3 working-hash semantics, readiness gating, and the capture fence.
- No database migration: the changed field lives inside canonical
  operation/basis JSON, not a dedicated schema column.

## Rejected alternatives (recorded for audit)

- (a) fence = last captured ShotRevision hash: neither current nor
  guaranteed to exist; contradicts the lawful capture-after-adopt flow.
- (c) keep synthetic stand-ins (event-set hash / empty-basis hash) in a
  field named `expected_working_snapshot_hash`: preserves implementation
  behavior by corrupting the audit meaning of the field name.
