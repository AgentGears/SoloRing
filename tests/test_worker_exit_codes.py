"""Worker exit-code semantics (plan §9).

Clean lease-loss / explicit stop / takeover -> exit 0.
Unexpected runtime failure -> exit non-zero.
A worker that loses authority never reports itself as crashed.
"""

from __future__ import annotations

import pytest

from soloring.worker import process
from soloring.worker.process import WorkerExitCode, run_entrypoint


def test_fatal_error_exits_nonzero(monkeypatch) -> None:
    async def _boom(**kwargs):  # noqa: ANN003
        raise RuntimeError("invariant violated")

    monkeypatch.setattr(process.runtime, "run_worker", _boom)
    code = run_entrypoint()
    assert code == WorkerExitCode.FATAL
    assert int(code) != 0


def test_clean_run_exits_zero(monkeypatch) -> None:
    async def _ok(**kwargs):  # noqa: ANN003
        return "clean_stop"

    monkeypatch.setattr(process.runtime, "run_worker", _ok)
    code = run_entrypoint()
    assert code == WorkerExitCode.CLEAN
    assert int(code) == 0


def test_keyboardinterrupt_exits_zero(monkeypatch) -> None:
    async def _interrupt(**kwargs):  # noqa: ANN003
        raise KeyboardInterrupt

    monkeypatch.setattr(process.runtime, "run_worker", _interrupt)
    code = run_entrypoint()
    assert code == WorkerExitCode.CLEAN


@pytest.mark.parametrize("exc", [RuntimeError("x"), ValueError("y"), OSError("z")])
def test_unexpected_exception_is_fatal(monkeypatch, exc) -> None:
    async def _raise(**kwargs):  # noqa: ANN003
        raise exc

    monkeypatch.setattr(process.runtime, "run_worker", _raise)
    assert run_entrypoint() == WorkerExitCode.FATAL
