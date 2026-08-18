"""Working state vs approved canon tests (M2 plan §3.2, §6.2).

Covers: no-canon/match/differ paths; all six broken-provenance variants
(including two that require simulating external corruption with FKs off,
since RESTRICT makes them unreachable through the ORM); the structural
single-transaction assertion; and the deterministic read-snapshot interleave.
"""

from __future__ import annotations

import logging
import sqlite3 as sq

import pytest

from soloring.api.schemas.projects import ProjectCreate
from soloring.api.schemas.shots import ShotCreate, ShotPatch
from soloring.db.models import Generation, Shot, Take
from soloring.domain import canon, projects, revisions, shots
from soloring.domain.ids import new_uuid
from soloring.errors import ErrorCode, SoloRingError
from soloring.generation import repository as repo
from soloring.generation.drafts import GenerationDraft
from soloring.generation.enums import GenerationOperation
from tests.conftest import create_project, create_shot

HEX64 = "ab" * 32


def _draft(shot_id: str, revision_id: str) -> GenerationDraft:
    return GenerationDraft(
        shot_id=shot_id,
        shot_revision_id=revision_id,
        operation=GenerationOperation.GENERATE,
        executor="fake",
        workflow_id="hunyuan_i2v",
        workflow_version=1,
        workflow_template_hash=HEX64,
        manifest_hash=HEX64,
        model=None,
        model_version=None,
        compiled_prompt="p",
        negative_prompt=None,
        prompt_compiler_version="1",
        seed=42,
        parameters_json="{}",
        workflow_spec_json="{}",
        workflow_spec_hash=HEX64,
    )


async def _seed_shot(factory, subject="x") -> str:
    async with factory() as s:
        pid = (await projects.create_project(s, ProjectCreate(name="P"))).id
        return (await shots.create_shot(s, pid, ShotCreate(subject=subject))).id


async def _capture(factory, shot_id: str) -> str:
    async with factory() as s:
        return (await revisions.capture_revision(s, shot_id)).id


async def _add_generation(factory, shot_id: str, revision_id: str) -> str:
    async with factory() as s:
        gen = await repo.create_generation(s, _draft(shot_id, revision_id), [])
        return gen.id


async def _add_take(factory, shot_id: str, generation_id: str) -> str:
    take_id = new_uuid()
    async with factory() as s:
        s.add(Take(id=take_id, shot_id=shot_id, generation_id=generation_id,
                   output_key="video:0"))
        await s.commit()
    return take_id


async def _approve(factory, shot_id: str, take_id: str | None) -> None:
    async with factory() as s:
        shot = await s.get(Shot, shot_id)
        shot.approved_take_id = take_id
        await s.commit()


def _plant_with_fks_off(engine, sql: str, params: dict) -> None:
    """Simulate external ledger corruption unreachable through the ORM.

    FK RESTRICT makes dangling generation/revision references impossible via
    normal writes; corruption tests plant them with foreign_keys=OFF on a raw
    connection to the same database file.
    """
    db_path = engine.sync_engine.url.database
    con = sq.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute(sql, params)
        con.commit()
    finally:
        con.close()


_GEN_SQL = """
INSERT INTO generations (
    id, shot_id, shot_revision_id, generation_number, status, operation,
    executor, workflow_id, workflow_version, workflow_template_hash,
    manifest_hash, compiled_prompt, prompt_compiler_version, seed,
    parameters_json, workflow_spec_json, workflow_spec_hash,
    created_at, updated_at, queued_at
) VALUES (
    :id, :shot_id, :revision_id, :number, 'queued', 'generate',
    'fake', 'wf', 1, :h64, :h64, 'p', '1', 42,
    '{}', '{}', :h64,
    '2026-01-01T00:00:00.000Z', '2026-01-01T00:00:00.000Z', '2026-01-01T00:00:00.000Z'
)
"""

_TAKE_SQL = """
INSERT INTO takes (id, shot_id, generation_id, output_key, created_at)
VALUES (:id, :shot_id, :generation_id, 'video:0', '2026-01-01T00:00:00.000Z')
"""


# --- happy paths -------------------------------------------------------------


async def test_no_approved_take_false_and_null(client, factory) -> None:
    p = await create_project(client, name="P")
    s = await create_shot(client, p["id"], subject="x")
    body = (await client.get(f"/shots/{s['id']}")).json()
    assert body["approved_take_id"] is None
    assert body["working_state_differs_from_approved"] is False


async def test_approved_matching_revision_false(client, factory) -> None:
    sid = await _seed_shot(factory)
    rid = await _capture(factory, sid)  # revision of the CURRENT working state
    gid = await _add_generation(factory, sid, rid)
    tid = await _add_take(factory, sid, gid)
    await _approve(factory, sid, tid)

    body = (await client.get(f"/shots/{sid}")).json()
    assert body["approved_take_id"] == tid
    assert body["working_state_differs_from_approved"] is False


async def test_approved_then_edit_true(client, factory) -> None:
    sid = await _seed_shot(factory)
    rid = await _capture(factory, sid)
    gid = await _add_generation(factory, sid, rid)
    tid = await _add_take(factory, sid, gid)
    await _approve(factory, sid, tid)

    async with factory() as s:
        await shots.patch_shot(s, sid, ShotPatch(subject="changed"))

    body = (await client.get(f"/shots/{sid}")).json()
    assert body["working_state_differs_from_approved"] is True


async def test_field_present_on_detail_only(client, factory) -> None:
    p = await create_project(client, name="P")
    s = await create_shot(client, p["id"], subject="x")
    detail = (await client.get(f"/shots/{s['id']}")).json()
    assert "working_state_differs_from_approved" in detail
    items = (await client.get(f"/projects/{p['id']}/shots")).json()
    assert items and "working_state_differs_from_approved" not in items[0]
    assert "working_snapshot_hash" not in items[0]


# --- broken provenance → invariant + log ------------------------------------


async def _assert_invariant(client, factory, caplog, sid: str) -> dict:
    with caplog.at_level(logging.ERROR, logger="soloring.domain.canon"):
        r = await client.get(f"/shots/{sid}")
    assert r.status_code == 500
    body = r.json()
    assert body["error_code"] == ErrorCode.INTERNAL_INVARIANT_VIOLATION
    assert "CANON INTEGRITY" in caplog.text
    assert sid in caplog.text
    return body["details"]


async def test_dangling_approved_take(client, factory, caplog) -> None:
    sid = await _seed_shot(factory)
    ghost = new_uuid()
    await _approve(factory, sid, ghost)
    details = await _assert_invariant(client, factory, caplog, sid)
    assert details["approved_take_id"] == ghost
    assert details["broken_link"] == "approved_take_missing"


async def test_take_of_other_shot(client, factory, caplog) -> None:
    sid1 = await _seed_shot(factory, "one")
    sid2 = await _seed_shot(factory, "two")
    rid2 = await _capture(factory, sid2)
    gid2 = await _add_generation(factory, sid2, rid2)
    tid2 = await _add_take(factory, sid2, gid2)
    await _approve(factory, sid1, tid2)  # shot1 approves shot2's take
    details = await _assert_invariant(client, factory, caplog, sid1)
    assert details["broken_link"] == "take_belongs_to_other_shot"
    assert details["take_id"] == tid2


async def test_generation_of_other_shot(client, factory, caplog) -> None:
    sid1 = await _seed_shot(factory, "one")
    sid2 = await _seed_shot(factory, "two")
    rid2 = await _capture(factory, sid2)
    gid2 = await _add_generation(factory, sid2, rid2)
    # Take on shot1 pointing at shot2's generation: FKs satisfied, ownership wrong.
    tid1 = await _add_take(factory, sid1, gid2)
    await _approve(factory, sid1, tid1)
    details = await _assert_invariant(client, factory, caplog, sid1)
    assert details["broken_link"] == "generation_belongs_to_other_shot"
    assert details["take_id"] == tid1
    assert details["generation_id"] == gid2


async def test_revision_of_other_shot(client, factory, caplog) -> None:
    sid1 = await _seed_shot(factory, "one")
    rid1 = await _capture(factory, sid1)
    sid2 = await _seed_shot(factory, "two")
    rid2 = await _capture(factory, sid2)  # belongs to shot2

    # Generation on shot1 pointing at shot2's revision: FK satisfied, wrong owner.
    gid = new_uuid()
    async with factory() as s:
        s.add(Generation(
            id=gid, shot_id=sid1, shot_revision_id=rid2, generation_number=1,
            status="queued", operation="generate", executor="fake",
            workflow_id="wf", workflow_version=1, workflow_template_hash=HEX64,
            manifest_hash=HEX64, compiled_prompt="p", prompt_compiler_version="1",
            parameters_json="{}", workflow_spec_json="{}", workflow_spec_hash=HEX64,
        ))
        await s.commit()
    tid = await _add_take(factory, sid1, gid)
    await _approve(factory, sid1, tid)
    details = await _assert_invariant(client, factory, caplog, sid1)
    assert details["broken_link"] == "revision_belongs_to_other_shot"
    assert details["take_id"] == tid
    assert details["generation_id"] == gid
    assert details["revision_id"] == rid2


async def test_missing_generation_planted_corruption(client, factory, engine, caplog) -> None:
    """Take exists but references a generation that does not.

    Unreachable through the ORM (FK RESTRICT); planted with FKs off to
    simulate external ledger corruption.
    """
    sid = await _seed_shot(factory)
    ghost_gen = new_uuid()
    tid = new_uuid()
    _plant_with_fks_off(engine, _TAKE_SQL, {"id": tid, "shot_id": sid,
                                            "generation_id": ghost_gen})
    await _approve(factory, sid, tid)
    details = await _assert_invariant(client, factory, caplog, sid)
    assert details["broken_link"] == "generation_missing"
    assert details["take_id"] == tid
    assert details["generation_id"] == ghost_gen


async def test_missing_revision_planted_corruption(client, factory, engine, caplog) -> None:
    """Generation exists but references a ShotRevision that does not."""
    sid = await _seed_shot(factory)
    ghost_rev = new_uuid()
    gid = new_uuid()
    tid = new_uuid()
    _plant_with_fks_off(engine, _GEN_SQL, {"id": gid, "shot_id": sid,
                                           "revision_id": ghost_rev,
                                           "number": 1, "h64": HEX64})
    _plant_with_fks_off(engine, _TAKE_SQL, {"id": tid, "shot_id": sid,
                                            "generation_id": gid})
    await _approve(factory, sid, tid)
    details = await _assert_invariant(client, factory, caplog, sid)
    assert details["broken_link"] == "revision_missing"
    assert details["take_id"] == tid
    assert details["generation_id"] == gid
    assert details["revision_id"] == ghost_rev


# --- snapshot discipline (§6.2) ----------------------------------------------


async def test_read_unit_is_one_connection_one_transaction(factory, engine) -> None:
    """Structural: one checkout, one explicit BEGIN, one terminal commit, and
    no intermediate transaction boundary during the whole detail read."""
    import contextlib

    sid = await _seed_shot(factory)
    rid = await _capture(factory, sid)
    gid = await _add_generation(factory, sid, rid)
    tid = await _add_take(factory, sid, gid)
    await _approve(factory, sid, tid)

    boundaries: list[str] = []
    checkouts = {"n": 0}

    class _ConnProxy:
        def __init__(self, real) -> None:
            self._real = real

        async def exec_driver_sql(self, stmt, *a, **k):
            head = stmt.strip().split(None, 1)[0].upper()
            if head in {"BEGIN", "COMMIT", "ROLLBACK", "BEGIN IMMEDIATE"}:
                boundaries.append(head)
            return await self._real.exec_driver_sql(stmt, *a, **k)

        async def commit(self):
            boundaries.append("commit()")
            return await self._real.commit()

        async def rollback(self):
            boundaries.append("rollback()")
            return await self._real.rollback()

        def __getattr__(self, name):
            return getattr(self._real, name)

    class _EngineProxy:
        def __init__(self, real) -> None:
            self._real = real

        def connect(self):
            checkouts["n"] += 1

            @contextlib.asynccontextmanager
            async def cm():
                async with self._real.connect() as c:
                    yield _ConnProxy(c)

            return cm()

        def __getattr__(self, name):
            return getattr(self._real, name)

    proxy_engine = _EngineProxy(engine)
    shot, refs, differs, _resolved, _eff, _ready = await shots.read_shot_detail(proxy_engine, sid)

    assert differs is False  # chain intact, working == approved hash
    assert checkouts["n"] == 1, "detail read must use exactly one connection"
    # One explicit BEGIN, exactly one terminal commit, nothing in between.
    assert boundaries == ["BEGIN", "commit()"], boundaries


async def test_read_snapshot_interleave_single_snapshot(factory, engine, monkeypatch) -> None:
    """Deterministic interleave: a commit between the working-state read and
    the provenance traversal must NOT be visible to the in-flight read unit.

    Arrangement: approved revision hash currently equals the working hash, so
    the in-flight (old-snapshot) result must be False. The concurrent mutation
    rewrites the approved revision's snapshot_hash mid-unit; a mixed-snapshot
    implementation would return True.

    This test is also the reason the read unit uses an explicit driver BEGIN:
    AsyncSession + Python sqlite3 legacy mode holds no read snapshot for
    SELECT-only sequences, and an earlier implementation failed exactly here.
    """
    sid = await _seed_shot(factory)
    rid = await _capture(factory, sid)
    gid = await _add_generation(factory, sid, rid)
    tid = await _add_take(factory, sid, gid)
    await _approve(factory, sid, tid)

    async def mutate_during_checkpoint() -> None:
        async with factory() as other:
            from sqlalchemy import text as _text

            await other.execute(
                _text("UPDATE shot_revisions SET snapshot_hash = :h WHERE id = :r"),
                {"h": "f" * 64, "r": rid},
            )
            await other.commit()

    monkeypatch.setattr(canon, "_checkpoint", mutate_during_checkpoint)

    # In-flight read unit: working state read first, mutation commits at the
    # checkpoint, provenance traversal reads afterwards.
    _shot, _refs, differs, _resolved, _eff, _ready = await shots.read_shot_detail(engine, sid)
    assert differs is False, "comparison mixed read snapshots"

    # The mutation did land: a fresh read unit sees the new hash.
    async def _noop() -> None:
        pass

    monkeypatch.setattr(canon, "_checkpoint", _noop)
    _shot2, _refs2, differs2, _resolved2, _eff2, _ready2 = await shots.read_shot_detail(engine, sid)
    assert differs2 is True
