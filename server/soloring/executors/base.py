"""GenerationExecutor contract (v0.1 §76).

Executors are untrusted-output adapters: everything they produce is staged,
unverified material until the import authority (generation/importer.py)
validates and persists it. Handles are executor-agnostic persisted identity
(v0.1 §87).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from soloring.workflows.manifest import WorkflowTemplate


class ExecutionStatus(str, Enum):
    SUBMITTED = "submitted"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    LOST = "lost"


@dataclass(frozen=True)
class GenerationExecutionSpec:
    """Everything an executor may consume — all of it captured/immutable at
    Generation creation. Executors never read current Shot state."""

    generation_id: str
    attempt_id: str
    workflow_spec: dict
    workflow_spec_hash: str
    compiled_prompt: str
    executor: str
    template: "WorkflowTemplate | None" = None


@dataclass(frozen=True)
class ExecutionHandle:
    kind: str
    job_id: str


@dataclass(frozen=True)
class ExecutionProgress:
    current: int | None = None
    total: int | None = None
    node: str | None = None


@dataclass(frozen=True)
class ExecutionObservation:
    status: ExecutionStatus
    progress: ExecutionProgress = field(default_factory=ExecutionProgress)
    error_message: str | None = None


@dataclass(frozen=True)
class StagedOutput:
    output_key: str
    path: Path
    kind: str


class GenerationExecutor(ABC):
    """Executor adapter surface (v0.1 §76)."""

    @abstractmethod
    async def submit(self, spec: GenerationExecutionSpec) -> ExecutionHandle:
        ...

    @abstractmethod
    async def inspect(self, handle: ExecutionHandle) -> ExecutionObservation:
        ...

    @abstractmethod
    async def cancel(self, handle: ExecutionHandle) -> "CancelResult":
        ...

    @abstractmethod
    async def fetch_outputs(
        self,
        handle: ExecutionHandle,
        outputs,  # Sequence[ExpectedOutput] from the CAPTURED spec (M4)
        staging_directory: Path,
    ) -> list[StagedOutput]:
        ...


class CancelResult(str, Enum):
    """v0.1 §72-§74 cancellation outcomes (exercised in M3B)."""

    CANCELLED = "cancelled"
    TOO_LATE = "too_late"
    NOT_FOUND = "not_found"
