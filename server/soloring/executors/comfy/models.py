"""Normalized Comfy models (M5A-2; M5 plan §13, §15).

Closed, bounded, executor-internal values. Remote payloads never become an
arbitrary-data tunnel: unknown remote values collapse to bounded
representations (state="unknown" + a truncated diagnostic token), and
extra_data propagation is narrowed to exactly the SoloRing submission marker
fields. These models are the ONLY Comfy vocabulary allowed above wire.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# Bounded diagnostics: unknown remote tokens are truncated to this length and
# stripped of control characters, never embedded whole (M5 §15).
DIAGNOSTIC_MAX = 120


class JobState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    LOST = "lost"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SoloringMarker:
    """The narrow slice of extra_data the adapter ever recovers (M5 §32)."""

    generation_id: str
    attempt_id: str

    def as_pair(self) -> tuple[str, str]:
        return self.generation_id, self.attempt_id


@dataclass(frozen=True)
class NormalizedProgress:
    current: int | None = None
    total: int | None = None
    node: str | None = None


@dataclass(frozen=True)
class NormalizedComfyJob:
    """A queue-visible job (M5 plan §13)."""

    prompt_id: str
    state: JobState
    marker: SoloringMarker | None = None
    progress: NormalizedProgress = field(default_factory=NormalizedProgress)
    error: str | None = None


@dataclass(frozen=True)
class NormalizedOutputReference:
    """One remote output file as declared by history (M5 §55-§57).

    Node/binding identity is retained so output mapping can be exact;
    filename/subfolder/type remain remote tokens pending validation at the
    /view boundary (M5A-9).
    """

    node: str
    output_field: str
    filename: str
    subfolder: str
    type: str


@dataclass(frozen=True)
class NormalizedHistoryRecord:
    """A terminal (or recorded) history entry for one prompt."""

    prompt_id: str
    terminal_state: JobState
    outputs: tuple[NormalizedOutputReference, ...] = ()
    error: str | None = None
    marker: SoloringMarker | None = None


@dataclass(frozen=True)
class NormalizedWsEvent:
    """Observational progress event (M5 §40-§41). Never lifecycle authority."""

    kind: str  # execution_start | executing | progress | execution_success | execution_error | unknown
    prompt_id: str | None = None
    progress: NormalizedProgress = field(default_factory=NormalizedProgress)
    diagnostic: str | None = None


@dataclass(frozen=True)
class NormalizedSystemInfo:
    """Version/build + advertised surface, normalized (M5 §16).

    Version is DIAGNOSTIC only — capability conclusions come from evidence,
    never from version arithmetic (M5A-2 invariant 7).
    """

    version: str | None = None
    build: str | None = None
    diagnostic: str | None = None


@dataclass(frozen=True)
class NormalizedUploadReference:
    """The authoritative remote input identity returned by upload (M5 §28)."""

    name: str
    subfolder: str


class ComfyResponseError(Exception):
    """Recognized dialect + malformed payload (distinct from INCOMPATIBLE).

    Mapped to the stable error code COMFY_RESPONSE_INVALID at API/report
    boundaries; never confused with a missing capability or an outage.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
