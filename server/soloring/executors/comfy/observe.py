"""Comfy observation (M5A-7; M5 plan §40-§46).

Authority rule:

    WebSocket says what MAY be happening now.
    Targeted /history/{prompt_id} says what DURABLY happened.
    /queue fills the active-job gap.

`observe_prompt` merges those with explicit precedence: terminal history wins
over stale queue/WS; queue presence yields pending/running; both absent enters
a MONOTONIC disappearance grace (read failures and WS activity never extend
it) ending in COMFY_JOB_LOST — or COMFY_HISTORY_LOST only when the caller
supplies positive evidence of an executor history reset (conservative default
per the M5A-7 review until M5B characterizes the live deployment).

Marker discipline: a marker PRESENT-but-contradictory for our prompt is an
invariant failure; a marker ABSENT (dialect omission) leaves the handle
usable.

This module is DB/ownership-free (worker orchestration applies observations
through its own fenced writes).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from soloring.executors.comfy.client import ComfyAPIError, ComfyClient
from soloring.executors.comfy.models import (
    JobState,
    NormalizedProgress,
    SoloringMarker,
)


class ObservationConflict(RuntimeError):
    """Persisted identity contradicted by executor evidence."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True)
class PromptObservation:
    state: str  # pending | running | succeeded | failed | cancelled | lost
    progress: NormalizedProgress | None = None
    error: str | None = None
    detail: str | None = None  # bounded diagnostic (e.g. loss classification)


def _check_marker(
    marker: SoloringMarker | None,
    generation_id: str,
    attempt_id: str,
) -> None:
    """Absent marker: allowed (dialect omission). Contradictory: failure."""
    if marker is None:
        return
    if marker.as_pair() != (generation_id, attempt_id):
        raise ObservationConflict(
            f"prompt carries marker for a different SoloRing identity "
            f"({marker.generation_id[:8]}…/{marker.attempt_id[:8]}…)"
        )


async def observe_prompt(
    client: ComfyClient,
    *,
    prompt_id: str,
    generation_id: str,
    attempt_id: str,
    disappearance: "DisappearanceTracker | None" = None,
) -> PromptObservation:
    """One authoritative observation of a KNOWN prompt handle.

    Precedence: targeted history (terminal) > queue (active) > disappearance
    grace (bounded absence) > COMFY_JOB_LOST.
    """
    # --- targeted history first: terminal authority --------------------------
    history = await client.history(prompt_id)
    record = history.get(prompt_id)
    if record is not None:
        _check_marker(record.marker, generation_id, attempt_id)
        if record.terminal_state in (
            JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED,
        ):
            if disappearance is not None:
                disappearance.clear()
            return PromptObservation(
                state=record.terminal_state.value,
                error=record.error,
            )
        # Non-terminal history entry (still recording): fall through to queue.

    # --- queue: the active-job gap --------------------------------------------
    jobs = await client.queue()
    for job in jobs:
        if job.prompt_id == prompt_id:
            _check_marker(job.marker, generation_id, attempt_id)
            if disappearance is not None:
                disappearance.clear()
            state = (
                "running" if job.state is JobState.RUNNING else "pending"
            )
            return PromptObservation(state=state, progress=job.progress)

    # --- absent from both authoritative surfaces -------------------------------
    if disappearance is None:
        return PromptObservation(state="lost", detail="COMFY_JOB_LOST")

    if disappearance.register_absence():
        detail = (
            "COMFY_HISTORY_LOST"
            if disappearance.history_reset_evidence
            else "COMFY_JOB_LOST"
        )
        return PromptObservation(state="lost", detail=detail)
    return PromptObservation(
        state="unknown", detail="disappearance grace running",
    )


class DisappearanceTracker:
    """Monotonic bounded-absence tracker (M5A-7 §grace).

    The deadline starts on the FIRST observed absence and never restarts —
    HTTP read failures and WS activity do not extend it; authoritative
    presence clears it.
    """

    def __init__(self, grace_seconds: float,
                 history_reset_evidence: bool = False) -> None:
        self.grace_seconds = grace_seconds
        self.history_reset_evidence = history_reset_evidence
        self._deadline: float | None = None

    def clear(self) -> None:
        self._deadline = None

    def register_absence(self) -> bool:
        """Record one absent poll; True when grace has expired."""
        if self._deadline is None:
            self._deadline = time.monotonic() + self.grace_seconds
            return False
        return time.monotonic() >= self._deadline

    @property
    def pending(self) -> bool:
        return self._deadline is not None


# --- WebSocket adapter (observational telemetry only) ---------------------------


class WsObservationAdapter:
    """Normalizes WS messages into observational telemetry.

    Terminal WS events are NOT lifecycle authority: they return a
    `reconcile=True` trigger so the caller performs immediate targeted-HTTP
    reconciliation. Duplicated/reordered frames cannot alter correctness
    because nothing durable is derived here.
    """

    def __init__(self) -> None:
        self.connected = True

    def on_message(self, raw: object):
        """→ (event, reconcile_now). Never a terminal decision."""
        from soloring.executors.comfy.wire import normalize_ws_event

        event = normalize_ws_event(raw)
        reconcile = event.kind in ("execution_success", "execution_error")
        return event, reconcile

    def on_disconnect(self) -> None:
        """Record disconnect; HTTP observation continues (§41)."""
        self.connected = False

    def on_reconnect(self) -> None:
        """Reconnect is telemetry-only: no lifecycle reset."""
        self.connected = True
