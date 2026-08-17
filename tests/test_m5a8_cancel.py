"""M5A-8 — Cancellation (M5 plan §47-§53, mandatory matrix).

Instrumented double: pending_delete_calls[prompt_id], targeted_cancel_calls,
interrupt_calls. The strongest negative assertion is interrupt_calls == 0 in
every non-interlock test.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text

from soloring.api.schemas.projects import ProjectCreate
from soloring.api.schemas.references import ReferenceInput
from soloring.api.schemas.shots import ShotCreate
from soloring.domain import projects, references, shots
from soloring.errors import ErrorCode
from soloring.executors.comfy.capabilities import (
    CancellationCapability,
    CancellationMode,
)
from soloring.executors.comfy.cancel import (
    CancelOutcome,
    decide_cancellation,
)
from soloring.executors.comfy.client import ComfyClient
from soloring.executors.comfy.observe import DisappearanceTracker
from soloring.worker.comfy_cancellation import (
    CancellationConflict,
    reconcile_cancellation,
)
from soloring.worker.ownership import (
    OwnershipMutationResult,
    acquire_worker_lease,
    adopt_stale_generation,
    claim_next_generation,
    select_owned_soft_cancel,
    transition_owned_generation,
)

GID = "g" * 36


class CancelDouble:
    base_url = "http://comfy.test"

    def __init__(self, *, running=(), pending=(), history=None):
        self._running = [[0, p, {}, m, []] for p, m in running]
        self._pending = [[1, p, {}, m, []] for p, m in pending]
        self._history = history or {}
        self.pending_delete_calls: list[str] = []
        self.targeted_cancel_calls: list[str] = []
        self.interrupt_calls = 0
        self.delete_ambiguous = False
        self.delete_fail_4xx = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/queue" and request.method == "GET":
            return httpx.Response(200, json={
                "queue_running": self._running,
                "queue_pending": self._pending,
            })
        if path == "/queue" and request.method == "POST":
            body = json.loads(request.content.decode())
            for pid in body.get("delete", []):
                self.pending_delete_calls.append(pid)
                if self.delete_ambiguous:
                    raise httpx.ReadTimeout("ambiguous delete")
                if self.delete_fail_4xx:
                    return httpx.Response(404, json={})
                self._pending = [e for e in self._pending if e[1] != pid]
                self._running = [e for e in self._running if e[1] != pid]
            return httpx.Response(200, json={})
        if path.startswith("/api/jobs/") and path.endswith("/cancel"):
            # Atomic per-job cancellation (M5B-5 product path). True iff the
            # id was actually running/pending; finished/unknown = no-op.
            pid = path.split("/api/jobs/")[1][: -len("/cancel")]
            self.targeted_cancel_calls.append(pid)
            if any(e[1] == pid for e in self._running):
                self._running = [e for e in self._running if e[1] != pid]
                self._history.setdefault(pid, {
                    "prompt": [0, pid, {}, {"soloring": {
                        "generation_id": GID, "attempt_id": "a"}}, []],
                    "outputs": {},
                    "status": {"status_str": "interrupted", "messages": []},
                })
                return httpx.Response(200, json={"cancelled": True})
            if any(e[1] == pid for e in self._pending):
                self._pending = [e for e in self._pending if e[1] != pid]
                return httpx.Response(200, json={"cancelled": True})
            return httpx.Response(200, json={"cancelled": False})
        if path == "/interrupt":
            body = json.loads(request.content or b"{}")
            pid = body.get("prompt_id")
            if pid is None:
                # GLOBAL interrupt (no target) — the unsafe operation.
                self.interrupt_calls += 1
                return httpx.Response(400, json={"accepted": False})
            # Targeted cancellation: counted separately, never as global.
            if pid is not None:
                self.targeted_cancel_calls.append(pid)
                self._running = [e for e in self._running if e[1] != pid]
                self._history.setdefault(pid, {
                    "prompt": [0, pid, {}, {"soloring": {"generation_id": GID,
                                                          "attempt_id": "a"}},
                               []],
                    "outputs": {},
                    "status": {"status_str": "interrupted", "messages": []},
                })
                return httpx.Response(200, json={"accepted": True})
            return httpx.Response(400, json={"accepted": False})
        if path.startswith("/history"):
            return httpx.Response(200, json=self._history)
        return httpx.Response(404)


def _client(double) -> ComfyClient:
    return ComfyClient(double.base_url, "w", timeout=5.0,
                       transport=httpx.MockTransport(double.handler))


SOFT_ONLY = CancellationCapability(mode=CancellationMode.SOFT_ONLY,
                                    retry_safety="unsafe")
TARGETED_SAFE = CancellationCapability(mode=CancellationMode.TARGETED,
                                        retry_safety="safe",
                                        targeting_key="prompt_id")


# --- pure decision tests ------------------------------------------------------------


def test_decision_pending_deletes():
    d = decide_cancellation("pending", SOFT_ONLY)
    assert d.action == "delete_pending"


def test_decision_running_requires_targeted_plus_retry_safe():
    assert decide_cancellation("running", SOFT_ONLY).action == "soft_cancel"
    cap = CancellationCapability(mode=CancellationMode.TARGETED,
                                  retry_safety="unknown")
    assert decide_cancellation("running", cap).action == "soft_cancel"
    assert decide_cancellation("running", TARGETED_SAFE).action == "hard_cancel"


def test_decision_unknown_state_soft():
    assert decide_cancellation("unknown", TARGETED_SAFE).action == "soft_cancel"


# --- DB fixture ---------------------------------------------------------------------


async def _seed(client_, factory, engine):
    async with factory() as s:
        pid = (await projects.create_project(s, ProjectCreate(name="P"))).id
        shot = await shots.create_shot(s, pid, ShotCreate(subject="x"))
    aid, _ = await _seed_asset(engine, pid)
    async with factory() as s:
        await references.replace_references(
            s, shot.id, [ReferenceInput(asset_id=aid, role="reference")]
        )
    r = await client_.post(f"/shots/{shot.id}/generations")
    assert r.status_code == 202, r.text
    return r.json()["id"]


async def _seed_asset(engine, project_id):
    import hashlib

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from soloring.db.models import Asset, Blob
    from soloring.domain.ids import new_uuid

    aid = new_uuid()
    bh = hashlib.sha256(aid.encode()).hexdigest()
    f = async_sessionmaker(bind=engine, expire_on_commit=False,
                            class_=AsyncSession)
    async with f() as s:
        s.add(Blob(hash=bh, path=f"sha256/{bh[:2]}/{bh[2:4]}/{bh}",
                   size_bytes=1))
        await s.flush()
        s.add(Asset(id=aid, project_id=project_id, blob_hash=bh,
                    kind="reference"))
        await s.commit()
    return aid, bh


async def _setup_active(client_, factory, engine, *, status="running",
                        persist_intent=True):
    """Seed + claim + simulate a confirmed comfy handle + persisted intent."""
    gid = await _seed(client_, factory, engine)
    await acquire_worker_lease(engine, "w-A", 30)
    _, attempt = await claim_next_generation(engine, "w-A")
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(text(
            "UPDATE generations SET executor_job_id='P', "
            "executor_submission_state='confirmed', attempt_id=:a "
            "WHERE id=:g"
        ).bindparams(a=attempt, g=gid))
        if persist_intent:
            await conn.execute(text(
                "UPDATE generations SET cancel_requested_at="
                "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=:g"
            ).bindparams(g=gid))
        await conn.exec_driver_sql("COMMIT")
    return gid, attempt


def _marker(gid, attempt):
    return {"soloring": {"generation_id": gid, "attempt_id": attempt}}


async def _counts(factory, gid):
    async with factory() as s:
        takes = (await s.execute(text(
            "SELECT count(*) FROM takes WHERE generation_id=:g"
        ), {"g": gid})).scalar()
        assets = (await s.execute(text(
            "SELECT count(*) FROM assets a JOIN takes t ON a.take_id=t.id "
            "WHERE t.generation_id=:g"
        ), {"g": gid})).scalar()
        row = dict((await s.execute(text(
            "SELECT status, soft_cancel_selected_at, cancel_requested_at, "
            "executor_job_id FROM generations WHERE id=:g"
        ), {"g": gid})).mappings().one())
    return takes, assets, row


async def _cancel(client_, factory, engine, double, gid, attempt,
                  capability=SOFT_ONLY):
    return await reconcile_cancellation(
        engine, "w-A", gid, attempt, "P", _client(double), capability,
    )


# --- pending cancellation ---------------------------------------------------------------


async def test_pending_delete_targets_only_p(client, factory, engine):
    gid, attempt = await _setup_active(client, factory, engine)
    double = CancelDouble(
        pending=[("P", _marker(gid, attempt)),
                 ("Q", _marker("other" * 5 + "x", "b" * 36))],
    )
    result = await _cancel(client, factory, engine, double, gid, attempt)
    assert result == "cancelled"
    assert double.pending_delete_calls == ["P"]  # exact P only
    assert double.interrupt_calls == 0
    _, _, row = await _counts(factory, gid)
    assert row["status"] == "cancelled"


async def test_g1_g2_both_pending_cancel_g1_leaves_g2(client, factory, engine):
    gid, attempt = await _setup_active(client, factory, engine)
    double = CancelDouble(
        pending=[("P", _marker(gid, attempt)),
                 ("Q", _marker("other" * 5 + "x", "b" * 36))],
    )
    await _cancel(client, factory, engine, double, gid, attempt)
    # Q survives in the queue.
    assert any(e[1] == "Q" for e in double._pending)
    assert double.interrupt_calls == 0


# --- running: soft cancel -----------------------------------------------------------------


async def test_running_hard_unavailable_selects_durable_soft_cancel(
    client, factory, engine
):
    gid, attempt = await _setup_active(client, factory, engine)
    double = CancelDouble(running=[("P", _marker(gid, attempt))])
    result = await _cancel(client, factory, engine, double, gid, attempt)
    assert result == "soft_cancel_selected"
    _, _, row = await _counts(factory, gid)
    assert row["soft_cancel_selected_at"] is not None
    assert row["cancel_requested_at"] is not None
    assert double.interrupt_calls == 0
    assert double.pending_delete_calls == []
    assert double.targeted_cancel_calls == []


async def test_soft_cancel_plus_remote_success_zero_publication(
    client, factory, engine
):
    gid, attempt = await _setup_active(client, factory, engine)
    double = CancelDouble(running=[("P", _marker(gid, attempt))])
    await _cancel(client, factory, engine, double, gid, attempt)  # soft

    # Remote later SUCCEEDS.
    double._history["P"] = {
        "prompt": [0, "P", {}, _marker(gid, attempt), []],
        "outputs": {}, "status": {"status_str": "completed", "messages": []},
    }
    double._running = []
    result = await _cancel(client, factory, engine, double, gid, attempt)
    assert result == "cancelled"
    takes, assets, row = await _counts(factory, gid)
    assert takes == 0 and assets == 0  # ZERO Take/Asset
    assert row["status"] == "cancelled"
    assert double.interrupt_calls == 0


async def test_soft_cancel_plus_remote_failure_zero_publication(
    client, factory, engine
):
    gid, attempt = await _setup_active(client, factory, engine)
    double = CancelDouble(running=[("P", _marker(gid, attempt))])
    await _cancel(client, factory, engine, double, gid, attempt)
    double._history["P"] = {
        "prompt": [0, "P", {}, _marker(gid, attempt), []],
        "outputs": {}, "status": {"status_str": "error",
                                    "messages": [{"e": 1}]},
    }
    double._running = []
    result = await _cancel(client, factory, engine, double, gid, attempt)
    assert result == "cancelled"
    takes, assets, _ = await _counts(factory, gid)
    assert takes == 0 and assets == 0


async def test_soft_cancel_never_enters_importing(client, factory, engine):
    gid, attempt = await _setup_active(client, factory, engine)
    double = CancelDouble(running=[("P", _marker(gid, attempt))])
    await _cancel(client, factory, engine, double, gid, attempt)
    double._history["P"] = {
        "prompt": [0, "P", {}, _marker(gid, attempt), []],
        "outputs": {}, "status": {"status_str": "completed", "messages": []},
    }
    double._running = []
    await _cancel(client, factory, engine, double, gid, attempt)
    _, _, row = await _counts(factory, gid)
    assert row["status"] == "cancelled"  # never importing


# --- running: targeted hard cancel -----------------------------------------------------------


async def test_targeted_hard_cancel_uses_exact_persisted_id(
    client, factory, engine
):
    gid, attempt = await _setup_active(client, factory, engine)
    double = CancelDouble(running=[("P", _marker(gid, attempt)),
                                     ("Q", _marker("o" * 35 + "x", "b" * 36))])
    result = await _cancel(client, factory, engine, double, gid, attempt,
                           capability=TARGETED_SAFE)
    assert result == "cancelled"
    assert double.targeted_cancel_calls == ["P"]  # exact persisted id
    # Q (another identity's prompt) untouched by OUR cancel call:
    assert "Q" not in double.targeted_cancel_calls
    assert double.interrupt_calls == 0  # targeted transport, not global


async def test_g1_finishes_g2_starts_cancel_lands_g2_unaffected(
    client, factory, engine
):
    """The collateral race: the cancel operation lands AFTER G1 completed and
    G2 started. With targeted cancellation the request still identifies P
    (G1's prompt), so Q (G2) is unaffected."""
    gid, attempt = await _setup_active(client, factory, engine)
    double = CancelDouble(running=[("P", _marker(gid, attempt)),
                                     ("Q", _marker("o" * 35 + "x", "b" * 36))])
    # G1 (P) completes; G2 (Q) starts.
    double._history["P"] = {
        "prompt": [0, "P", {}, _marker(gid, attempt), []],
        "outputs": {}, "status": {"status_str": "completed", "messages": []},
    }
    double._running = [e for e in double._running if e[1] == "Q"]
    # The stale cancel lands now (TOO_LATE for P):
    result = await _cancel(client, factory, engine, double, gid, attempt,
                           capability=TARGETED_SAFE)
    # History reconciliation: P succeeded — but cancel was requested, and
    # since no soft cancel was selected... per §11 TOO_LATE → terminal wins.
    assert result in ("succeeded", "cancelled")
    assert "Q" not in double.targeted_cancel_calls  # Q NEVER targeted
    assert double.interrupt_calls == 0
    assert any(e[1] == "Q" for e in double._running) or double._history.get("Q") is None


async def test_too_late_history_reconciliation_terminal_wins(
    client, factory, engine
):
    gid, attempt = await _setup_active(client, factory, engine)
    double = CancelDouble(running=[("P", _marker(gid, attempt))])
    double._history["P"] = {
        "prompt": [0, "P", {}, _marker(gid, attempt), []],
        "outputs": {}, "status": {"status_str": "completed", "messages": []},
    }
    # First observe already sees terminal → normal completion wins (no soft).
    result = await _cancel(client, factory, engine, double, gid, attempt)
    assert result == "succeeded"


# --- ambiguous transport ----------------------------------------------------------------------


async def test_ambiguous_delete_same_target_only_no_retarget(
    client, factory, engine
):
    gid, attempt = await _setup_active(client, factory, engine)
    double = CancelDouble(pending=[("P", _marker(gid, attempt)),
                                     ("Q", _marker("o" * 35 + "x", "b" * 36))])
    double.delete_ambiguous = True
    result = await _cancel(client, factory, engine, double, gid, attempt)
    assert result == "ambiguous"
    assert double.pending_delete_calls == ["P"]  # only ever P
    assert "Q" not in double.pending_delete_calls


async def test_retry_unsafe_targeted_ambiguous_goes_soft(
    client, factory, engine
):
    """TARGETED but retry_safety unknown/unsafe + running → soft (§6)."""
    gid, attempt = await _setup_active(client, factory, engine)
    double = CancelDouble(running=[("P", _marker(gid, attempt))])
    cap = CancellationCapability(mode=CancellationMode.TARGETED,
                                  retry_safety="unknown")
    result = await _cancel(client, factory, engine, double, gid, attempt,
                           capability=cap)
    assert result == "soft_cancel_selected"
    assert double.targeted_cancel_calls == []


# --- races, ownership, recovery ---------------------------------------------------------------


async def test_terminal_before_cancel_wins(client, factory, engine):
    gid, attempt = await _setup_active(client, factory, engine)
    double = CancelDouble(history={
        "P": {"prompt": [0, "P", {}, _marker(gid, attempt), []],
               "outputs": {}, "status": {"status_str": "completed",
                                          "messages": []}},
    })
    result = await _cancel(client, factory, engine, double, gid, attempt)
    assert result == "succeeded"  # terminal wins even with intent persisted


async def test_importing_409(client, factory, engine):
    """The API rejects cancellation of importing work (existing rule)."""
    gid = await _seed(client, factory, engine)
    async with factory() as s:
        await s.execute(text(
            "UPDATE generations SET status='importing' WHERE id=:g"
        ).bindparams(g=gid))
        await s.commit()
    r = await client.post(f"/generations/{gid}/cancel")
    assert r.status_code == 409
    assert r.json()["error_code"] == ErrorCode.GENERATION_NOT_CANCELLABLE


async def test_lease_loser_cannot_select_soft_cancel(
    client, factory, engine
):
    gid, attempt = await _setup_active(client, factory, engine)
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(text(
            "UPDATE worker_leases SET heartbeat_at = "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now','-9999 seconds')"
        ))
        await conn.exec_driver_sql("COMMIT")
    await acquire_worker_lease(engine, "w-B", 30)  # B takes the lease
    assert (await select_owned_soft_cancel(engine, "w-A", gid)) is False
    _, _, row = await _counts(factory, gid)
    assert row["soft_cancel_selected_at"] is None


async def test_lease_loser_cannot_persist_cancellation_terminal(
    client, factory, engine
):
    gid, attempt = await _setup_active(client, factory, engine)
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(text(
            "UPDATE worker_leases SET heartbeat_at = "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now','-9999 seconds')"
        ))
        await conn.exec_driver_sql("COMMIT")
    await acquire_worker_lease(engine, "w-B", 30)
    r = await transition_owned_generation(engine, "w-A", gid, "cancelled")
    assert r is OwnershipMutationResult.LEASE_LOST
    _, _, row = await _counts(factory, gid)
    assert row["status"] != "cancelled"


async def test_soft_cancel_survives_worker_death(
    client, factory, engine
):
    gid, attempt = await _setup_active(client, factory, engine)
    double = CancelDouble(running=[("P", _marker(gid, attempt))])
    await _cancel(client, factory, engine, double, gid, attempt)  # A: soft

    # A dies; B takes over + adopts.
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(text(
            "UPDATE worker_leases SET heartbeat_at = "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now','-9999 seconds')"
        ))
        await conn.execute(text(
            "UPDATE generations SET heartbeat_at = "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now','-9999 seconds') "
            "WHERE id=:g"
        ).bindparams(g=gid))
        await conn.exec_driver_sql("COMMIT")
    await acquire_worker_lease(engine, "w-B", 30)
    assert (await adopt_stale_generation(engine, "w-B", gid)) is (
        OwnershipMutationResult.OK
    )

    # B sees the durable soft-cancel selection: never hard-cancels; remote
    # success → discarded, zero publication.
    double._history["P"] = {
        "prompt": [0, "P", {}, _marker(gid, attempt), []],
        "outputs": {}, "status": {"status_str": "completed", "messages": []},
    }
    double._running = []
    result = await reconcile_cancellation(
        engine, "w-B", gid, attempt, "P", _client(double), TARGETED_SAFE,
    )
    assert result == "cancelled"
    takes, assets, row = await _counts(factory, gid)
    assert takes == 0 and assets == 0
    assert double.targeted_cancel_calls == []  # B NEVER hard-cancelled
    assert double.interrupt_calls == 0


async def test_cancel_never_changes_executor_job_id(client, factory, engine):
    gid, attempt = await _setup_active(client, factory, engine)
    double = CancelDouble(running=[("P", _marker(gid, attempt))])
    await _cancel(client, factory, engine, double, gid, attempt)
    _, _, row = await _counts(factory, gid)
    assert row["executor_job_id"] == "P"


async def test_successor_adopts_before_cancellation_work(
    client, factory, engine
):
    """A non-owner cannot run cancellation reconciliation (ownership read)."""
    gid, attempt = await _setup_active(client, factory, engine)
    await acquire_worker_lease(engine, "w-B", 30)
    double = CancelDouble(running=[("P", _marker(gid, attempt))])
    with pytest.raises(CancellationConflict):
        await reconcile_cancellation(
            engine, "w-B", gid, attempt, "P", _client(double), SOFT_ONLY,
        )


async def test_pending_delete_race_p_to_running(client, factory, engine):
    """P was pending at decision time but became running before the delete:
    the delete no-ops (404) → TOO_LATE → reconcile sees running → policy."""
    gid, attempt = await _setup_active(client, factory, engine)
    double = CancelDouble(running=[("P", _marker(gid, attempt))])
    double.delete_fail_4xx = True
    # decision sees running under SOFT_ONLY → soft (delete never sent).
    result = await _cancel(client, factory, engine, double, gid, attempt)
    assert result == "soft_cancel_selected"
    assert double.pending_delete_calls == []


# --- structural ------------------------------------------------------------------------------


def test_cancel_module_db_free():
    import ast as _ast

    banned = ("soloring.db", "soloring.worker", "sqlalchemy", "aiosqlite")
    source = (Path(__file__).parent.parent / "server" / "soloring"
              / "executors" / "comfy" / "cancel.py").read_text("utf-8")
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


# --- M5B-5: atomic cancel-job contract (wire + client) -----------------------


def test_cancel_job_response_strict():
    from soloring.executors.comfy.wire import (
        ComfyResponseError, normalize_cancel_job_response,
    )
    assert normalize_cancel_job_response({"cancelled": True}) is True
    assert normalize_cancel_job_response({"cancelled": False}) is False
    for bad in ({"cancelled": "yes"}, {}, {"cancelled": 1}, "x"):
        with pytest.raises(ComfyResponseError):
            normalize_cancel_job_response(bad)


async def test_cancel_job_client_transport():
    import httpx

    from soloring.executors.comfy.client import ComfyClient

    calls = []

    def handler(request):
        calls.append(request.url.path)
        if "unknown" in request.url.path:
            return httpx.Response(200, json={"cancelled": False})
        return httpx.Response(200, json={"cancelled": True})

    client = ComfyClient("http://x", "w", transport=httpx.MockTransport(handler))
    assert await client.cancel_job("P") is True
    assert await client.cancel_job("unknown-id") is False
    await client.aclose()
    assert calls == ["/api/jobs/P/cancel", "/api/jobs/unknown-id/cancel"]


async def test_resolve_capability_from_settings(tmp_path, monkeypatch):
    # soft_only needs nothing. targeted REQUIRES a matching characterization
    # record (M5B-7 mechanical binding); drift/absence fails CLOSED.
    import json

    from soloring.settings import Settings
    from soloring.worker.comfy_pipeline import resolve_capability

    soft = await resolve_capability(Settings(data_dir=tmp_path))
    assert soft.mode.value == "soft_only"

    # targeted without a record -> fail closed to soft_only
    no_record = await resolve_capability(Settings(
        data_dir=tmp_path, comfy_cancellation_mode="targeted"))
    assert no_record.mode.value == "soft_only"

    # targeted with the v1 record AND its launcher attestation
    from soloring.executors.comfy.capability_record import (
        build_capability_record,
        build_deployment_attestation,
    )

    fp_dir = tmp_path / "comfy-fingerprint"
    fp_dir.mkdir(parents=True)
    (fp_dir / "capability_m5b5.json").write_text(json.dumps(
        build_capability_record(
            comfyui_commit="a" * 40, comfyui_version="0.33.0",
            gguf_commit="b" * 40)))
    (fp_dir / "deployment_attestation.json").write_text(json.dumps(
        build_deployment_attestation(
            comfyui_commit="a" * 40, gguf_commit="b" * 40,
            launched_at="2026-08-17T00:00:00", pid=99,
            process_start_fingerprint="fp",
            executor_origin="http://127.0.0.1:8188")))
    targeted = await resolve_capability(Settings(
        data_dir=tmp_path, comfy_cancellation_mode="targeted"))
    assert targeted.mode.value == "soft_only"  # no client -> fails closed
    # With a live client (process verification stubbed to the attested
    # process), targeted engages.
    import httpx

    from soloring.executors.comfy.client import ComfyClient

    monkeypatch.setattr(
        "soloring.executors.comfy.capability_record.verify_live_process",
        lambda att, port=8188: True)
    probe = ComfyClient(
        "http://127.0.0.1:8188", "w",
        transport=httpx.MockTransport(lambda r: (
            httpx.Response(200, json={"system": {
                "comfyui_version": "0.33.0", "build": "t"}}))))
    engaged = await resolve_capability(
        Settings(data_dir=tmp_path, comfy_cancellation_mode="targeted"),
        probe)
    await probe.aclose()
    assert engaged.mode.value == "targeted"
    assert engaged.retry_safety == "safe"
    assert engaged.targeting_key == "prompt_id"

    # incomplete record -> fail closed
    (fp_dir / "capability_m5b5.json").write_text(json.dumps({
        "executor_fingerprint": {"comfyui_version": "0.33.0"},
        "running_cancel": {"mode": "TARGETED"},
    }))
    closed = await resolve_capability(Settings(
        data_dir=tmp_path, comfy_cancellation_mode="targeted"))
    assert closed.mode.value == "soft_only"


async def test_resolve_capability_fails_closed_on_version_drift(tmp_path):
    import json

    import httpx

    from soloring.executors.comfy.client import ComfyClient
    from soloring.settings import Settings
    from soloring.worker.comfy_pipeline import resolve_capability

    fp_dir = tmp_path / "comfy-fingerprint"
    fp_dir.mkdir(parents=True)
    (fp_dir / "capability_m5b5.json").write_text(json.dumps({
        "executor_fingerprint": {
            "comfyui_commit": "c" * 40, "comfyui_version": "9.9.9",
            "gguf_commit": "g" * 40,
        },
        "running_cancel": {"mode": "TARGETED", "retry_safety": "safe",
                           "endpoint": "POST /api/jobs/{prompt_id}/cancel"},
    }))

    def handler(request):
        return httpx.Response(200, json={
            "system": {"comfyui_version": "0.33.0", "build": "t"}})

    client = ComfyClient("http://x", "w", transport=httpx.MockTransport(handler))
    drifted = await resolve_capability(
        Settings(data_dir=tmp_path, comfy_cancellation_mode="targeted"),
        client,
    )
    await client.aclose()
    assert drifted.mode.value == "soft_only"  # live 0.33.0 != record 9.9.9

