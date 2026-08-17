"""Worker process entrypoint and exit semantics (plan §9, §57).

Exit codes distinguish clean deauthorization from fatal failure so process
supervisors can tell lease-loss (expected, exit 0) from a real crash (non-zero):

    clean lease-loss / explicit stop / takeover by another worker -> 0
    unexpected runtime exception / invariant violation            -> non-zero

A worker that loses authority never reports itself as crashed (plan §9).
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from enum import IntEnum

from soloring.settings import Settings, get_settings
from soloring.worker import runtime

log = logging.getLogger("soloring.worker.process")


class WorkerExitCode(IntEnum):
    CLEAN = 0
    FATAL = 70  # non-zero: unexpected failure (plan §9)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _install_stop_handlers(loop: asyncio.AbstractEventLoop, stop_event: asyncio.Event) -> None:
    """Install best-effort handlers so a normal stop drives an in-loop shutdown.

    Plan §9 requires explicit normal process termination to be a *clean* exit,
    distinguishable from a fatal crash. On POSIX, ``loop.add_signal_handler``
    catches SIGINT/SIGTERM. On Windows Proactor loops that API is unavailable,
    so we fall back to ``signal.signal``, which can intercept console Ctrl+C
    (SIGINT) and route it to ``stop_event`` via ``call_soon_threadsafe``.

    Forced kills (TerminateProcess / POSIX SIGKILL) cannot be caught on ANY
    platform; those are outside the scope of "normal" termination.
    """
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, RuntimeError):
            # Windows fallback: install via signal.signal.
            def _handler(signum, frame, loop=loop, ev=stop_event):  # noqa: ANN001
                loop.call_soon_threadsafe(ev.set)
            try:
                signal.signal(sig, _handler)
            except (OSError, ValueError):
                # Signal not installable in this context (e.g. non-main thread).
                pass


async def _amain(settings: Settings) -> None:
    """Install stop handlers for graceful shutdown, then run the worker."""
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    _install_stop_handlers(loop, stop_event)
    await runtime.run_worker(settings=settings, stop_event=stop_event)


def run_entrypoint() -> int:
    """Synchronous entry returning an exit code (testable without SystemExit)."""
    _configure_logging()
    settings = get_settings()
    try:
        asyncio.run(_amain(settings))
    except KeyboardInterrupt:
        log.info("interrupted (KeyboardInterrupt); clean shutdown")
        return WorkerExitCode.CLEAN
    except Exception:  # noqa: BLE001 — fatal path must always produce non-zero
        log.exception("fatal worker error")
        return WorkerExitCode.FATAL
    return WorkerExitCode.CLEAN


def main() -> None:
    sys.exit(run_entrypoint())
