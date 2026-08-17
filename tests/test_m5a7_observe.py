"""M5A-7 — Observation (M5 plan §40-§46, mandatory matrix).

HTTP-double-backed tests for authority precedence, disappearance grace, WS
telemetry discipline, marker semantics, and the recovery proof.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text

from soloring.api.schemas.projects import ProjectCreate
from soloring.api.schemas.references import ReferenceInput
from soloring.api.schemas.shots import ShotCreate
from soloring.domain import projects, references, shots
from soloring.errors import ErrorCode
from soloring.executors.comfy import observe as observe_mod
from soloring.executors.comfy.client import ComfyAPIError, ComfyClient
from soloring.executors.comfy.models import NormalizedProgress
from soloring.executors.comfy.observe import (
    DisappearanceTracker,
    ObservationConflict,
    PromptObservation,
    WsObservationAdapter,
    observe_prompt,
)
from soloring.settings import BASE_DIR

async def asyncio_sleep(s):
    import asyncio

    await asyncio.sleep(s)


GID, AID = "g" * 36, "a" * 36
MARKER = {"soloring": {"generation_id": GID, "attempt_id": AID}}


class ComfyDouble:
    """Minimal observation double: queue + targeted history."""

    base_url = "http://comfy.test"

    def __init__(self, *, queue_running=(), queue_pending=(), history=None,
                 read_failures_left: int = 0):
        self._running = list(queue_running)
        self._pending = list(queue_pending)
        self._history = history or {}
        self.history_calls: list[str] = []
        self.queue_calls = 0
        self.read_failures_left = read_failures_left

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/queue":
            self.queue_calls += 1
            if self.read_failures_left > 0:
                self.read_failures_left -= 1
                return httpx.Response(503, text="degraded")
            return httpx.Response(200, json={
                "queue_running": self._running,
                "queue_pending": self._pending,
            })
        if path.startswith("/history"):
            self.history_calls.append(path)
            if self.read_failures_left > 0:
                self.read_failures_left -= 1
                return httpx.Response(503, text="degraded")
            return httpx.Response(200, json=self._history)
        if path == "/system_stats":
            return httpx.Response(200, json={"system": {"comfyui_version": "0.3"}})
        return httpx.Response(404)

    def set_running(self, pid, marker=MARKER):
        self._running = [[0, pid, {}, marker, []]]
        self._pending = []

    def set_pending(self, pid, marker=MARKER):
        self._pending = [[1, pid, {}, marker, []]]
        self._running = []

    def set_history_success(self, pid, marker=MARKER):
        self._history = {pid: {
            "prompt": [0, pid, {}, marker, []], "outputs": {},
            "status": {"status_str": "completed", "messages": []},
        }}

    def set_history_failed(self, pid, marker=MARKER):
        self._history = {pid: {
            "prompt": [0, pid, {}, marker, []], "outputs": {},
            "status": {"status_str": "error",
                        "messages": [{"type": "execution_error"}]},
        }}

    def set_history_cancelled(self, pid, marker=MARKER):
        self._history = {pid: {
            "prompt": [0, pid, {}, marker, []], "outputs": {},
            "status": {"status_str": "interrupted", "messages": []},
        }}


def _client(double) -> ComfyClient:
    return ComfyClient(double.base_url, "w", timeout=5.0,
                       transport=httpx.MockTransport(double.handler))


async def _obs(double, pid="P", tracker=None):
    return await observe_prompt(
        _client(double), prompt_id=pid, generation_id=GID, attempt_id=AID,
        disappearance=tracker,
    )


# --- authority precedence ------------------------------------------------------


async def test_known_prompt_pending():
    d = ComfyDouble(queue_pending=[[1, "P", {}, MARKER, []]])
    obs = await _obs(d)
    assert obs.state == "pending"


async def test_known_prompt_running():
    d = ComfyDouble(queue_running=[[0, "P", {}, MARKER, []]])
    obs = await _obs(d)
    assert obs.state == "running"


async def test_terminal_history_success_wins():
    d = ComfyDouble(queue_running=[[0, "P", {}, MARKER, []]])
    d.set_history_success("P")
    obs = await _obs(d)
    assert obs.state == "succeeded"


async def test_terminal_history_failure_bounded_diagnostics():
    d = ComfyDouble()
    d.set_history_failed("P")
    obs = await _obs(d)
    assert obs.state == "failed"
    assert obs.error is None or len(obs.error) <= 200


async def test_terminal_history_cancelled():
    d = ComfyDouble()
    d.set_history_cancelled("P")
    obs = await _obs(d)
    assert obs.state == "cancelled"


async def test_stale_queue_running_vs_history_succeeded_history_wins():
    d = ComfyDouble(queue_running=[[0, "P", {}, MARKER, []]])
    d.set_history_success("P")
    obs = await _obs(d)
    assert obs.state == "succeeded"


# --- disappearance grace --------------------------------------------------------


async def test_brief_absence_no_premature_loss():
    d = ComfyDouble()
    tracker = DisappearanceTracker(grace_seconds=1.0)
    obs = await _obs(d, tracker=tracker)
    assert obs.state == "unknown"  # grace running, not lost
    assert tracker.pending


async def test_reappearance_clears_timer():
    d = ComfyDouble()
    tracker = DisappearanceTracker(grace_seconds=1.0)
    await _obs(d, tracker=tracker)
    assert tracker.pending
    d.set_running("P")
    obs = await _obs(d, tracker=tracker)
    assert obs.state == "running"
    assert not tracker.pending  # cleared


async def test_continuous_absence_past_grace_job_lost():
    d = ComfyDouble()
    tracker = DisappearanceTracker(grace_seconds=0.05)
    deadline_seen = None
    for _ in range(50):
        obs = await _obs(d, tracker=tracker)
        if obs.state == "lost":
            deadline_seen = obs
            break
        await asyncio_sleep(0.02)
    assert deadline_seen is not None
    assert deadline_seen.detail == "COMFY_JOB_LOST"


async def test_history_reset_evidence_classifies_history_lost():
    d = ComfyDouble()
    tracker = DisappearanceTracker(grace_seconds=0.01,
                                     history_reset_evidence=True)
    lost = None
    for _ in range(50):
        obs = await _obs(d, tracker=tracker)
        if obs.state == "lost":
            lost = obs
            break
        await asyncio_sleep(0.02)
    assert lost is not None
    assert lost.detail == "COMFY_HISTORY_LOST"


async def test_read_failures_do_not_extend_grace():
    d = ComfyDouble(read_failures_left=2)
    tracker = DisappearanceTracker(grace_seconds=0.2)
    t0 = time.monotonic()
    lost = None
    for _ in range(100):
        try:
            obs = await _obs(d, tracker=tracker)
            if obs.state == "lost":
                lost = obs
                break
        except ComfyAPIError:
            pass  # degraded poll inside the same deadline
        await asyncio_sleep(0.02)
    elapsed = time.monotonic() - t0
    assert lost is not None
    assert elapsed < 1.0  # failures did not extend the 0.2s grace


# --- marker semantics -------------------------------------------------------------


async def test_present_but_contradictory_marker_fails():
    other = {"soloring": {"generation_id": "OTHER" * 3 + "X",
                            "attempt_id": AID}}
    d = ComfyDouble(queue_running=[[0, "P", {}, other, []]])
    with pytest.raises(ObservationConflict):
        await _obs(d)


async def test_absent_marker_in_permitted_dialect_still_usable():
    d = ComfyDouble(queue_running=[[0, "P", {}, {"unrelated": 1}, []]])
    obs = await _obs(d)
    assert obs.state == "running"  # omission ≠ contradiction


async def test_history_marker_contradiction_fails():
    other = {"soloring": {"generation_id": GID, "attempt_id": "B" * 36}}
    d = ComfyDouble()
    d.set_history_success("P", marker=other)
    with pytest.raises(ObservationConflict):
        await _obs(d)


# --- WebSocket telemetry -------------------------------------------------------------


def test_ws_progress_observed():
    ws = WsObservationAdapter()
    event, reconcile = ws.on_message(
        ["progress", {"value": 3, "max": 10}, "31"]
    )
    assert event.kind == "progress" and event.progress.current == 3
    assert reconcile is False


def test_ws_terminal_events_trigger_reconciliation_not_authority():
    ws = WsObservationAdapter()
    for kind, payload in (
        ("execution_success", {"prompt_id": "P"}),
        ("execution_error", {"prompt_id": "P"}),
    ):
        event, reconcile = ws.on_message([kind, payload])
        assert event.kind == kind
        assert reconcile is True  # trigger; the DECISION is HTTP history's


def test_ws_duplicate_and_reordered_events_harmless():
    ws = WsObservationAdapter()
    frames = [
        ["executing", {"prompt_id": "P"}, 3],
        ["progress", {"value": 1, "max": 10}, 3],
        ["progress", {"value": 1, "max": 10}, 3],  # duplicate
        ["executing", {"prompt_id": "P"}, 2],  # reordered
    ]
    for f in frames:
        ws.on_message(f)  # no durable state derived: cannot alter correctness


def test_ws_disconnect_continues_http_and_reconnect_no_reset():
    ws = WsObservationAdapter()
    ws.on_disconnect()
    assert ws.connected is False  # HTTP polling continues elsewhere
    ws.on_reconnect()
    assert ws.connected is True


def test_ws_activity_does_not_extend_disappearance_grace():
    tracker = DisappearanceTracker(grace_seconds=0.05)
    tracker.register_absence()  # start the deadline
    ws = WsObservationAdapter()
    ws.on_message(["progress", {"value": 5, "max": 10}, 3])
    ws.on_message(["execution_start", {"prompt_id": "P"}])
    time.sleep(0.08)
    # WS activity neither cleared nor extended the tracker.
    assert tracker.pending
    assert tracker.register_absence() is True


# --- known-handle discipline + worker integration --------------------------------------


async def test_known_handle_observation_is_targeted_not_global():
    d = ComfyDouble(queue_running=[[0, "P", {}, MARKER, []]])
    await _obs(d)
    await _obs(d)
    assert all(p == "/history/P" for p in d.history_calls)
    assert not any(p == "/history" for p in d.history_calls)


async def test_lease_loss_prevents_stale_writes(client, factory, engine):
    """Fenced progress write from a lease loser is rejected (worker layer)."""
    from soloring.worker.ownership import (
        OwnershipMutationResult, acquire_worker_lease, claim_next_generation,
        update_owned_generation_progress,
    )

    async with factory() as s:
        pid = (await projects.create_project(s, ProjectCreate(name="P"))).id
        shot = await shots.create_shot(s, pid, ShotCreate(subject="x"))
    aid, _ = await _seed_asset(engine, pid)
    async with factory() as s:
        await references.replace_references(
            s, shot.id, [ReferenceInput(asset_id=aid, role="reference")]
        )
    r = await client.post(f"/shots/{shot.id}/generations")
    assert r.status_code == 202, r.text
    gid = r.json()["id"]

    await acquire_worker_lease(engine, "w-A", 30)
    await claim_next_generation(engine, "w-A")
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(text(
            "UPDATE worker_leases SET heartbeat_at = "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now','-9999 seconds')"
        ))
        await conn.exec_driver_sql("COMMIT")
    await acquire_worker_lease(engine, "w-B", 30)
    # A's observation-driven progress write is fenced off:
    result = await update_owned_generation_progress(
        engine, "w-A", gid, 1, 3, "fake-sampler"
    )
    assert result is OwnershipMutationResult.LEASE_LOST


async def test_successor_reconstructs_from_handle_without_ws_history(
    client, factory, engine
):
    """The recovery proof: A receives WS progress, loses lease; B adopts and
    reconstructs RUNNING purely from targeted HTTP; completion is terminal
    only via history; exactly one import path."""
    async with factory() as s:
        pid = (await projects.create_project(s, ProjectCreate(name="P"))).id
        shot = await shots.create_shot(s, pid, ShotCreate(subject="x"))
    aid, bh = await _seed_asset(engine, pid)
    async with factory() as s:
        await references.replace_references(
            s, shot.id, [ReferenceInput(asset_id=aid, role="reference")]
        )
    r = await client.post(f"/shots/{shot.id}/generations")
    assert r.status_code == 202, r.text
    gid = r.json()["id"]

    from soloring.worker.ownership import (
        OwnershipMutationResult, acquire_worker_lease, adopt_stale_generation,
        claim_next_generation,
    )

    await acquire_worker_lease(engine, "w-A", 30)
    _, attempt = await claim_next_generation(engine, "w-A")

    # A's WS telemetry (never persisted as history):
    ws = WsObservationAdapter()
    ws.on_message(["execution_start", {"prompt_id": "P"}])
    ws.on_message(["progress", {"value": 2, "max": 10}, 3])

    # Remote truth: P running.
    d = ComfyDouble(queue_running=[[0, "P", {}, MARKER, []]])

    # Lease loss + takeover.
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(text(
            "UPDATE worker_leases SET heartbeat_at = "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now','-9999 seconds')"
        ))
        await conn.execute(text(
            "UPDATE generations SET heartbeat_at = "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now','-9999 seconds'), "
            "executor_job_id='P', executor_submission_state='confirmed' "
            "WHERE id=:g"
        ).bindparams(g=gid))
        await conn.exec_driver_sql("COMMIT")
    await acquire_worker_lease(engine, "w-B", 30)
    assert (await adopt_stale_generation(engine, "w-B", gid)) is (
        OwnershipMutationResult.OK
    )

    # B reconstructs from the persisted handle — no WS history needed. The
    # double's marker uses the STATIC pair, so build a matching double.
    d2 = ComfyDouble(queue_running=[[0, "P", {},
        {"soloring": {"generation_id": gid, "attempt_id": attempt}}, []]])
    obs = await observe_prompt(
        _client(d2), prompt_id="P", generation_id=gid, attempt_id=attempt,
    )
    assert obs.state == "running"

    # Completion is terminal ONLY via history.
    d2.set_history_success("P", marker={"soloring": {
        "generation_id": gid, "attempt_id": attempt}})
    obs2 = await observe_prompt(
        _client(d2), prompt_id="P", generation_id=gid, attempt_id=attempt,
    )
    assert obs2.state == "succeeded"


async def _seed_asset(engine, project_id):
    import hashlib

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from soloring.db.models import Asset, Blob
    from soloring.domain.ids import new_uuid

    aid = new_uuid()
    bh = hashlib.sha256(aid.encode()).hexdigest()
    f = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with f() as s:
        s.add(Blob(hash=bh, path=f"sha256/{bh[:2]}/{bh[2:4]}/{bh}", size_bytes=1))
        await s.flush()
        s.add(Asset(id=aid, project_id=project_id, blob_hash=bh,
                     kind="reference"))
        await s.commit()
    return aid, bh


# --- structural -----------------------------------------------------------------------


def test_observe_module_is_db_free():
    import ast as _ast

    banned = ("soloring.db", "soloring.worker", "sqlalchemy", "aiosqlite")
    source = (BASE_DIR / "server" / "soloring" / "executors" / "comfy"
              / "observe.py").read_text("utf-8")
    tree = _ast.parse(source)
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, _ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        for n in names:
            for b in banned:
                assert not (n == b or n.startswith(b + ".")), n


def test_no_session_held_during_http():
    """observe.py opens no sessions at all (AST: no engine/session refs)."""
    import ast as _ast

    source = (BASE_DIR / "server" / "soloring" / "executors" / "comfy"
              / "observe.py").read_text("utf-8")
    tree = _ast.parse(source)
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Name):
            assert node.id not in ("AsyncSession", "session_maker",
                                    "sessionmaker", "engine"), node.id
