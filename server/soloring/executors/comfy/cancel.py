"""Comfy cancellation remote semantics (M5A-8; M5 plan §47-§53).

Remote-only layer (DB/ownership-free): pending deletion targets the EXACT
persisted prompt_id; hard running cancellation is gated on the capability
profile including retry safety; the global /interrupt is UNREACHABLE here —
M5A-8 fails closed on SAFE_SINGLE_FLIGHT (no mechanical interlock exists in
v0.1), so callers degrade to Soft Cancel, which issues no remote request at
all.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from soloring.executors.comfy.capabilities import CancellationCapability
from soloring.executors.comfy.client import ComfyClient, ComfyAPIError


class CancelOutcome(str, Enum):
    ACCEPTED = "accepted"        # remote accepted the targeted operation
    TOO_LATE = "too_late"        # prompt already terminal/absent remotely
    AMBIGUOUS = "ambiguous"      # request may have reached the executor


@dataclass(frozen=True)
class CancellationDecision:
    """What the caller should do (worker layer owns durable state)."""

    action: str  # "delete_pending" | "hard_cancel" | "soft_cancel"
    reason: str


def decide_cancellation(
    prompt_state: str, capability: CancellationCapability
) -> CancellationDecision:
    """Choose the cancellation path for a KNOWN prompt in a KNOWN remote
    state. Observations feed this; they never become the target identity.
    """
    if prompt_state == "pending":
        # Prompt-specific queue deletion is genuinely targeted (delete(P)).
        return CancellationDecision("delete_pending", "pending prompt")
    if prompt_state == "running":
        retry_safe = getattr(capability, "retry_safety", None) == "safe"
        if (
            capability.mode.value == "targeted"
            and retry_safe
        ):
            return CancellationDecision(
                "hard_cancel", "targeted + retry-safe capability"
            )
        return CancellationDecision(
            "soft_cancel",
            f"running cancellation not provably safe (mode="
            f"{capability.mode.value}, retry_safety="
            f"{getattr(capability, 'retry_safety', 'unknown')})",
        )
    # unknown/absent remote state: no destructive request is justified.
    return CancellationDecision(
        "soft_cancel", f"remote state {prompt_state!r} not targetable"
    )


async def cancel_pending(client: ComfyClient, prompt_id: str) -> CancelOutcome:
    """Prompt-specific queue deletion. Only ever receives the persisted id."""
    try:
        await client.cancel_pending(prompt_id)
    except ComfyAPIError as exc:
        # Ambiguous transport: possibly sent — NEVER re-target a different
        # prompt; the caller re-observes and may re-issue against exactly P.
        if "transport" in str(exc):
            return CancelOutcome.AMBIGUOUS
        # Conclusive rejection (e.g. 404): P is not deletable because it is
        # gone or already active — TOO_LATE drives re-observation.
        return CancelOutcome.TOO_LATE
    return CancelOutcome.ACCEPTED


async def cancel_running(
    client: ComfyClient, prompt_id: str
) -> CancelOutcome:
    """Hard targeted cancellation. Only invoked by callers that have already
    verified targeted+retry-safe capability; the target is always the
    persisted prompt_id.

    Uses the pinned deployment's ATOMIC per-job endpoint (M5B-5:
    /api/jobs/{id}/cancel — server-side interrupt_if_running holds the
    queue mutex and the per-prompt interrupt-flag reset makes a fall-through
    onto a successor job impossible). The plain /interrupt route is
    check-then-act and is intentionally NOT used by the product path; no
    code path can reach a global interrupt from Generation cancellation.
    """
    result = await client.cancel_job(prompt_id)
    if result is True:
        return CancelOutcome.ACCEPTED
    if result is False:
        return CancelOutcome.TOO_LATE
    return CancelOutcome.AMBIGUOUS
