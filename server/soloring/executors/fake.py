"""FakeExecutor (v0.1 §77) — deterministic, script-driven, DURABLE.

The only executor behind Hard Gates A/B. Jobs live in a small file-backed
store (one JSON per job under data/tmp/fake-executor/), so ANY process or
instance can adopt and continue a job from its persisted handle — exactly how
a real executor adapter reconciles from durable handle identity (plan §66,
§88). A stale worker's job survives its process; the recovering authority
adopts the SAME job and never resubmits.

Output byte contract (deterministic, test-pinned):

    PNG_MAGIC + b"|soloring-fake-v1|" + <workflow_spec_hash>.encode()

The workflow_spec_hash embeds the compiled prompt, reference identities, and
parameters (v0.1 §38), so distinct captured states always produce distinct
bytes, and identical captured states produce identical bytes.
"""

from __future__ import annotations

import json
from pathlib import Path

from soloring.executors.base import (
    CancelResult,
    ExecutionHandle,
    ExecutionObservation,
    ExecutionProgress,
    ExecutionStatus,
    GenerationExecutionSpec,
    GenerationExecutor,
    StagedOutput,
)
from soloring.settings import get_settings

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
FAKE_MARKER = b"|soloring-fake-v1|"
TOTAL_STEPS = 3


def fake_output_bytes(workflow_spec_hash: str) -> bytes:
    """Deterministic output content derived from the captured spec hash."""
    return PNG_MAGIC + FAKE_MARKER + workflow_spec_hash.encode("ascii")


def _store_dir() -> Path:
    return get_settings().tmp_dir / "fake-executor"


def _job_path(job_id: str) -> Path:
    # job_id is internally generated ("fake-<n>-<uuid prefix>"); sanitize the
    # filename defensively anyway.
    safe = "".join(c for c in job_id if c.isalnum() or c in "-_")
    return _store_dir() / f"{safe}.json"


def _load_job(job_id: str) -> dict | None:
    path = _job_path(job_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_job(job_id: str, job: dict) -> None:
    """Atomic state-file publication: temp file + os.replace, so concurrent
    readers never observe a partial file (M3C review)."""
    import os

    path = _job_path(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(job), encoding="utf-8")
    os.replace(tmp, path)


class FakeExecutor(GenerationExecutor):
    """Durable scripted executor; jobs advance one step per inspect() call."""

    def __init__(self, inspect_advances: int = 1) -> None:
        self._advances = inspect_advances
        self.cancel_calls: list[str] = []
        self.submit_calls: list[str] = []      # every submit call
        self.new_executions: list[str] = []    # submissions that CREATED a job

    async def submit(self, spec: GenerationExecutionSpec) -> ExecutionHandle:
        """Idempotent submission: job identity is DERIVED from the durable
        (generation, attempt) fence identity. Re-submitting the same identity
        (e.g., after a crash between submit and handle persistence) REJOINS
        the existing job instead of executing again (M3C headline fix)."""
        job_id = f"fake-{spec.generation_id[:12]}-{spec.attempt_id[:12]}"
        existing = _load_job(job_id)
        if existing is None:
            _write_job(
                job_id,
                {
                    "generation_id": spec.generation_id,
                    "attempt_id": spec.attempt_id,
                    "workflow_spec_hash": spec.workflow_spec_hash,
                    "steps": 0,
                    "cancelled": False,
                },
            )
            self.new_executions.append(job_id)
        self.submit_calls.append(job_id)
        return ExecutionHandle(kind="fake", job_id=job_id)

    async def cancel(self, handle: ExecutionHandle) -> CancelResult:
        self.cancel_calls.append(handle.job_id)
        job = _load_job(handle.job_id)
        if job is None:
            return CancelResult.NOT_FOUND
        if job["steps"] >= TOTAL_STEPS:
            return CancelResult.TOO_LATE
        job["cancelled"] = True
        _write_job(handle.job_id, job)
        return CancelResult.CANCELLED

    async def inspect(self, handle: ExecutionHandle) -> ExecutionObservation:
        job = _load_job(handle.job_id)
        if job is None:
            # Durable handle points at a job the executor no longer knows:
            # the plan §88 reconciliation outcome is LOST → interrupted.
            return ExecutionObservation(status=ExecutionStatus.LOST)
        if job["cancelled"]:
            return ExecutionObservation(status=ExecutionStatus.CANCELLED)
        if job["steps"] < TOTAL_STEPS:
            return ExecutionObservation(
                status=ExecutionStatus.RUNNING,
                progress=ExecutionProgress(
                    current=job["steps"] + 1, total=TOTAL_STEPS, node="fake-sampler"
                ),
            )
        return ExecutionObservation(status=ExecutionStatus.SUCCEEDED)

    def advance(self, handle: ExecutionHandle) -> None:
        """Test/loop hook: move the scripted job forward one step."""
        job = _load_job(handle.job_id)
        if job is None or job["steps"] >= TOTAL_STEPS:
            return
        job["steps"] += self._advances
        _write_job(handle.job_id, job)

    async def fetch_outputs(
        self,
        handle: ExecutionHandle,
        outputs,
        staging_directory: Path,
    ) -> list[StagedOutput]:
        job = _load_job(handle.job_id)
        if job is None:
            raise RuntimeError(f"fake job {handle.job_id} vanished before fetch")
        content = fake_output_bytes(job["workflow_spec_hash"])
        staged: list[StagedOutput] = []
        staging_directory.mkdir(parents=True, exist_ok=True)
        for out in outputs:
            for index in range(out.expected_count):
                key = f"{out.name}:{index}"
                # Deterministic staged name (§80): <prefix>-<index>.tmp
                path = staging_directory / f"{out.name}-{index}.tmp"
                path.write_bytes(content)
                staged.append(StagedOutput(output_key=key, path=path, kind=out.kind))
        return staged


def handle_json(handle: ExecutionHandle) -> str:
    return json.dumps({"kind": handle.kind, "job_id": handle.job_id})


def handle_from_json(raw: str) -> ExecutionHandle:
    data = json.loads(raw)
    return ExecutionHandle(kind=data["kind"], job_id=data["job_id"])
