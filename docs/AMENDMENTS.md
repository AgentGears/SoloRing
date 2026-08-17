# SoloRing v0.1 Amendments

Deliberate, recorded deviations from the v0.1 master plan. Each was reviewed
and accepted; none emerged accidentally from implementation.

## 1. TAKE_REJECTED — approving a rejected Take (v0.1 §92, amended in M3B)

v0.1 §92 specified that approval clears `rejected_at` (approve-after-reject
silently revives). Amended: **approving a rejected Take is a 409 conflict**
(`TAKE_REJECTED`) — rejection and approval must not silently reverse each
other. An explicit un-reject operation may be added later if the workflow
needs it. Rejecting the *currently approved* Take remains the plan's explicit
transactional unapprove+reject (v0.1 §93).

## 2. Soft Cancel — unsafe running cancellation (v0.1 §73, amended in M5)

v0.1 §73 specified that running cancellation without a safely targeted
interrupt returns `409 GENERATION_NOT_CANCELLABLE`. Amended (M5 plan §51 as
reviewed): when safe hard running cancellation is unavailable,

```text
cancellation request is ACCEPTED
→ cancel_requested_at persisted
→ remote work may continue under observation
→ at remote terminal state: outputs are NOT fetched/imported/published
→ any non-importing staging is discarded
→ Generation → cancelled
```

No Take, output Asset, or canon mutation is created; the remote terminal
outcome is diagnostic only. The amendment does **not** change:

```text
importing → 409 GENERATION_NOT_CANCELLABLE
```

because durable publication has already begun. Lease loss during Soft Cancel
behaves like any recoverable active job: no destructive cancellation; the
successor adopts and continues the same safe policy.

Rationale: user intent is honored without ever issuing an unsafe global
interrupt; a bare global `/interrupt` is never treated as targeted
cancellation (v0.1 §73's safety condition, restated as M5-F19).
