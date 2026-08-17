"""Generation enums (plan §31–§32, §14 of v0.1).

Persisted enum values are mirrored by database CHECK constraints in migration
0002 and the ORM models.
"""

from __future__ import annotations

from enum import Enum


class GenerationOperation(str, Enum):
    GENERATE = "generate"
    RERUN = "rerun"


class GenerationStatus(str, Enum):
    QUEUED = "queued"
    PREPARING = "preparing"
    SUBMITTED = "submitted"
    RUNNING = "running"
    IMPORTING = "importing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"


class Executor(str, Enum):
    """v0.1-executor set (plan §32: an explicit v0.1 schema constraint)."""

    FAKE = "fake"
    COMFY = "comfy"
