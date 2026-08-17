"""Generation repository tests (plan §37, §40, §41, §50.12, §50.14)."""

from __future__ import annotations

import asyncio
import re
import sqlite3

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.api.schemas.projects import ProjectCreate
from soloring.api.schemas.references import ReferenceInput
from soloring.api.schemas.shots import ShotCreate
from soloring.db.models import Generation, Take
from soloring.domain import projects, references, revisions, shots
from soloring.domain.ids import new_uuid
from soloring.errors import ErrorCode, SoloRingError
from soloring.generation import repository as repo
from soloring.generation.drafts import GenerationDraft
from soloring.generation.enums import GenerationOperation
from soloring.generation.input_mapping import (
    GenerationInputRule,
    resolve_generation_inputs,
)
from tests.conftest import seed_reference_asset

HEX64 = "ab" * 32
_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def _draft(shot_id: str, revision_id: str, **overrides) -> GenerationDraft:
    base = dict(
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
        compiled_prompt="prompt",
        negative_prompt=None,
        prompt_compiler_version="1",
        seed=42,
        parameters_json='{"steps":30,"cfg":7.0}',
        workflow_spec_json='{"schema_version":1}',
        workflow_spec_hash=HEX64,
    )
    base.update(overrides)
    return GenerationDraft(**base)


async def _seed_shot(factory, engine, with_refs: int = 0) -> tuple[str, str, list[dict]]:
    """Project + Shot + revision (+ optional seeded reference assets)."""
    async with factory() as s:
        pid = (await projects.create_project(s, ProjectCreate(name="P"))).id
        shot = await shots.create_shot(s, pid, ShotCreate(subject="subj"))
    refs = []
    for i in range(with_refs):
        refs.append(await seed_reference_asset(engine, pid))
    pairs = [(aid, "reference") for aid, _ in refs]
    if pairs:
        async with factory() as s:
            await references.replace_references(
                s, shot.id, [ReferenceInput(asset_id=a, role=r) for a, r in pairs]
            )
    async with factory() as s:
        rev = await revisions.capture_revision(s, shot.id)
    return shot.id, rev.id, refs


def _resolved(refs: list[tuple[str, str]]) -> list:
    snap_refs = [
        {"asset_id": aid, "blob_hash": bh, "role": "reference", "position": i}
        for i, (aid, bh) in enumerate(refs)
    ]
    return resolve_generation_inputs(
        {"schema_version": 1, "intent": {"subject": "x"}, "references": snap_refs},
        [GenerationInputRule("reference_image", "reference")],
    )


async def test_first_generation_number_is_one(factory, engine) -> None:
    sid, rid, _ = await _seed_shot(factory, engine)
    async with factory() as s:
        gen = await repo.create_generation(s, _draft(sid, rid), [])
    assert gen.generation_number == 1
    assert gen.status == "queued"
    assert gen.operation == "generate"


async def test_numbers_never_reused(factory, engine) -> None:
    sid, rid, _ = await _seed_shot(factory, engine)
    async with factory() as s:
        g1 = await repo.create_generation(s, _draft(sid, rid), [])
    async with factory() as s:
        g2 = await repo.create_generation(s, _draft(sid, rid), [])
    assert (g1.generation_number, g2.generation_number) == (1, 2)


async def test_concurrent_generation_numbers_unique(factory, engine) -> None:
    sid, rid, _ = await _seed_shot(factory, engine)
    n = 8

    async def one() -> int:
        async with factory() as s:
            gen = await repo.create_generation(s, _draft(sid, rid), [])
            return gen.generation_number

    nums = sorted(await asyncio.gather(*(one() for _ in range(n))))
    assert nums == list(range(1, n + 1))


async def test_missing_shot_rejected(factory) -> None:
    async with factory() as s:
        with pytest.raises(SoloRingError) as ei:
            await repo.create_generation(s, _draft(new_uuid(), new_uuid()), [])
    assert ei.value.code == ErrorCode.SHOT_NOT_FOUND


async def test_deleted_shot_rejected_atomically(factory, engine) -> None:
    sid, rid, _ = await _seed_shot(factory, engine)
    async with factory() as s:
        await shots.delete_shot(s, sid)
    async with factory() as s:
        with pytest.raises(SoloRingError) as ei:
            await repo.create_generation(s, _draft(sid, rid), [])
    assert ei.value.code == ErrorCode.SHOT_NOT_FOUND
    async with factory() as s:
        count = len((await s.execute(text("SELECT 1 FROM generations"))).all())
    assert count == 0  # nothing persisted


async def test_mismatched_revision_rejected(factory, engine) -> None:
    sid, rid, _ = await _seed_shot(factory, engine)
    sid2, rid2, _ = await _seed_shot(factory, engine)  # another shot/revision
    async with factory() as s:
        with pytest.raises(SoloRingError) as ei:
            await repo.create_generation(s, _draft(sid, rid2), [])
    assert ei.value.code == ErrorCode.VALIDATION_ERROR


async def test_generation_and_inputs_persist_atomically(factory, engine) -> None:
    sid, rid, refs = await _seed_shot(factory, engine, with_refs=2)
    inputs = _resolved(refs)
    async with factory() as s:
        gen = await repo.create_generation(s, _draft(sid, rid), inputs)
    async with factory() as s:
        stored = await repo.list_generation_inputs(s, gen.id)
    assert len(stored) == 2
    assert [(i.input_key, i.position) for i in stored] == [("reference_image", 0), ("reference_image", 1)]
    assert {i.asset_id for i in stored} == {a for a, _ in refs}


async def test_failed_validation_leaves_no_generation(factory, engine) -> None:
    sid, rid, _ = await _seed_shot(factory, engine)
    inputs = _resolved([("00000000-0000-0000-0000-000000000000", HEX64)])
    async with factory() as s:
        with pytest.raises(SoloRingError) as ei:
            await repo.create_generation(s, _draft(sid, rid), inputs)
    assert ei.value.code == ErrorCode.VALIDATION_ERROR
    async with factory() as s:
        assert (await s.execute(text("SELECT count(*) FROM generations"))).scalar() == 0
        assert (await s.execute(text("SELECT count(*) FROM generation_inputs"))).scalar() == 0


async def test_blob_hash_mismatch_rejected(factory, engine) -> None:
    sid, rid, refs = await _seed_shot(factory, engine, with_refs=1)
    aid, real_bh = refs[0]
    snap_refs = [{"asset_id": aid, "blob_hash": "f" * 64, "role": "reference", "position": 0}]
    inputs = resolve_generation_inputs(
        {"schema_version": 1, "intent": {"subject": "x"}, "references": snap_refs},
        [GenerationInputRule("reference_image", "reference")],
    )
    async with factory() as s:
        with pytest.raises(SoloRingError):
            await repo.create_generation(s, _draft(sid, rid), inputs)


async def test_persisted_inputs_immutable_after_reference_edits(factory, engine) -> None:
    """GenerationInputs never follow later ShotReference edits (§38)."""
    sid, rid, refs = await _seed_shot(factory, engine, with_refs=2)
    inputs = _resolved(refs)
    async with factory() as s:
        gen = await repo.create_generation(s, _draft(sid, rid), inputs)
    before = sorted((i.asset_id, i.position, i.blob_hash) for i in inputs)

    # Replace the shot's working references with a completely different set.
    new_aid, new_bh = await seed_reference_asset(engine, (await _pid(factory, sid)))
    async with factory() as s:
        await references.replace_references(
            s, sid, [ReferenceInput(asset_id=new_aid, role="style")]
        )

    async with factory() as s:
        stored = await repo.list_generation_inputs(s, gen.id)
    after = sorted((i.asset_id, i.position, i.blob_hash) for i in stored)
    assert after == before


async def _pid(factory, shot_id: str) -> str:
    async with factory() as s:
        shot = await shots.get_shot(s, shot_id)
        return shot.project_id


# --- collision fault policy (§37.1) ----------------------------------------


def _unique_violation() -> IntegrityError:
    return IntegrityError(
        "INSERT INTO generations",
        {},
        sqlite3.IntegrityError(
            "UNIQUE constraint failed: generations.shot_id, generations.generation_number"
        ),
    )


async def test_number_collision_retry_then_success(factory, engine, monkeypatch) -> None:
    sid, rid, _ = await _seed_shot(factory, engine)
    real = repo._execute_generation_insert
    state = {"n": 0}

    async def fake(session, params):
        state["n"] += 1
        if state["n"] == 1:
            raise _unique_violation()
        return await real(session, params)

    monkeypatch.setattr(repo, "_execute_generation_insert", fake)
    async with factory() as s:
        gen = await repo.create_generation(s, _draft(sid, rid), [])
    assert state["n"] == 2  # one collision + one success
    assert gen.generation_number == 1


async def test_number_collision_exhaustion_internal_error(factory, engine, monkeypatch) -> None:
    sid, rid, _ = await _seed_shot(factory, engine)

    async def always(session, params):
        raise _unique_violation()

    monkeypatch.setattr(repo, "_execute_generation_insert", always)
    async with factory() as s:
        with pytest.raises(SoloRingError) as ei:
            await repo.create_generation(s, _draft(sid, rid), [])
    assert ei.value.code == ErrorCode.INTERNAL_INVARIANT_VIOLATION
    assert ei.value.status_code == 500


async def test_unrelated_integrity_not_treated_as_collision(factory, engine, monkeypatch) -> None:
    """A non-numbering CHECK failure is not retried; it is an invariant."""
    sid, rid, _ = await _seed_shot(factory, engine)
    calls = {"n": 0}
    real = repo._execute_generation_insert

    async def counting(session, params):
        calls["n"] += 1
        return await real(session, params)

    monkeypatch.setattr(repo, "_execute_generation_insert", counting)
    # executor="bogus" passes draft validation but violates the DB CHECK,
    # producing a non-numbering IntegrityError at insert time.
    async with factory() as s:
        with pytest.raises(SoloRingError) as ei:
            await repo.create_generation(s, _draft(sid, rid, executor="bogus"), [])
    assert ei.value.code == ErrorCode.INTERNAL_INVARIANT_VIOLATION
    assert calls["n"] == 1  # number allocated once; failure was NOT retried


# --- Generation vs Shot-DELETE race (audit: serialization-first) ------------


async def test_delete_race_generation_authority_first(factory, engine, monkeypatch) -> None:
    """Generation acquires write authority -> DELETE must wait -> both succeed.

    Deterministic interleave: the atomic INSERT executes (write lock held),
    then we pause BEFORE commit while a concurrent Shot DELETE starts. The
    DELETE cannot pass the Generation transaction; after the Generation
    commits, the DELETE completes. No raw OperationalError/BUSY may leak.
    """
    sid, rid, _ = await _seed_shot(factory, engine)
    real = repo._execute_generation_insert
    inserted = asyncio.Event()
    gate = asyncio.Event()

    async def hold_before_commit(session, params):
        row = await real(session, params)
        inserted.set()
        await gate.wait()  # hold the open write transaction (pre-commit)
        return row

    monkeypatch.setattr(repo, "_execute_generation_insert", hold_before_commit)

    async def run_create():
        async with factory() as s:
            return await repo.create_generation(s, _draft(sid, rid), [])

    async def run_delete():
        async with factory() as s:
            await shots.delete_shot(s, sid)

    create_task = asyncio.create_task(run_create())
    await asyncio.wait_for(inserted.wait(), timeout=5)

    delete_task = asyncio.create_task(run_delete())
    await asyncio.sleep(0.3)
    assert not delete_task.done(), "DELETE must block on the Generation transaction"

    gate.set()
    gen = await asyncio.wait_for(create_task, timeout=6)
    await asyncio.wait_for(delete_task, timeout=6)

    # Generation committed (it held authority); the delete landed afterwards.
    assert gen.generation_number == 1
    from soloring.db.models import Shot as ShotModel

    async with factory() as s:
        shot_row = await s.get(ShotModel, sid)
        assert shot_row.deleted_at is not None
        stored = await repo.get_generation(s, gen.id)
        assert stored.id == gen.id


async def test_delete_race_delete_authority_first(factory, engine) -> None:
    """DELETE commits first -> Generation creation sees it -> SHOT_NOT_FOUND.

    Also proves no raw OperationalError/BUSY leaks in this ordering: the
    insert's WHERE EXISTS evaluates against the post-delete snapshot.
    """
    sid, rid, _ = await _seed_shot(factory, engine)
    async with factory() as s:
        await shots.delete_shot(s, sid)
    async with factory() as s:
        with pytest.raises(SoloRingError) as ei:
            await repo.create_generation(s, _draft(sid, rid), [])
    assert ei.value.code == ErrorCode.SHOT_NOT_FOUND
    async with factory() as s:
        n = (await s.execute(text("SELECT count(*) FROM generations"))).scalar()
        m = (await s.execute(text("SELECT count(*) FROM generation_inputs"))).scalar()
    assert (n, m) == (0, 0)


# --- BUSY / raw-OperationalError boundary normalization (§37.1) -------------


def _locked_error() -> OperationalError:
    return OperationalError(
        "INSERT INTO generations",
        {},
        sqlite3.OperationalError("database is locked"),
    )


async def test_returning_busy_translated_not_retried(factory, engine, monkeypatch) -> None:
    """OperationalError(BUSY) at the insert seam -> SQLITE_BUSY, no retry."""
    sid, rid, _ = await _seed_shot(factory, engine)
    calls = {"n": 0}

    async def busy(session, params):
        calls["n"] += 1
        raise _locked_error()

    monkeypatch.setattr(repo, "_execute_generation_insert", busy)
    async with factory() as s:
        with pytest.raises(SoloRingError) as ei:
            await repo.create_generation(s, _draft(sid, rid), [])
    assert ei.value.code == ErrorCode.SQLITE_BUSY
    assert ei.value.status_code == 503
    assert calls["n"] == 1  # BUSY is a different failure class: never retried


async def test_returning_non_busy_operational_translated(factory, engine, monkeypatch) -> None:
    """A non-BUSY OperationalError -> internal invariant, never raw."""
    sid, rid, _ = await _seed_shot(factory, engine)
    calls = {"n": 0}

    async def broken(session, params):
        calls["n"] += 1
        raise OperationalError(
            "INSERT INTO generations",
            {},
            sqlite3.OperationalError("no such table: generations"),
        )

    monkeypatch.setattr(repo, "_execute_generation_insert", broken)
    async with factory() as s:
        with pytest.raises(SoloRingError) as ei:
            await repo.create_generation(s, _draft(sid, rid), [])
    assert ei.value.code == ErrorCode.INTERNAL_INVARIANT_VIOLATION
    assert calls["n"] == 1


async def test_fenced_begin_immediate_busy_translated(factory, engine, monkeypatch) -> None:
    """BEGIN IMMEDIATE lock timeout in the fallback -> SQLITE_BUSY, not raw."""
    import contextlib as _cl

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    monkeypatch.setattr(repo, "sqlite_supports_returning", lambda: False)
    sid, rid, _ = await _seed_shot(factory, engine)

    class _BusyConn:
        def __init__(self, real) -> None:
            self._real = real

        async def exec_driver_sql(self, stmt, *a, **k):
            if stmt.strip().upper().startswith("BEGIN"):
                raise _locked_error()
            return await self._real.exec_driver_sql(stmt, *a, **k)

        def __getattr__(self, name):
            return getattr(self._real, name)

    class _BusyEngine:
        def __init__(self, real) -> None:
            self._real = real

        def connect(self):
            @_cl.asynccontextmanager
            async def cm():
                async with self._real.connect() as c:
                    yield _BusyConn(c)

            return cm()

        def __getattr__(self, name):
            return getattr(self._real, name)

    busy_factory = async_sessionmaker(
        bind=_BusyEngine(engine), expire_on_commit=False, class_=AsyncSession
    )
    async with busy_factory() as s:
        with pytest.raises(SoloRingError) as ei:
            await repo.create_generation(s, _draft(sid, rid), [])
    assert ei.value.code == ErrorCode.SQLITE_BUSY
    assert ei.value.status_code == 503
    async with factory() as s:
        n = (await s.execute(text("SELECT count(*) FROM generations"))).scalar()
    assert n == 0  # nothing persisted


# --- discriminator unit tests (hardening) -----------------------------------


def _mk_op_error(message: str, code: int | None = None) -> OperationalError:
    inner = sqlite3.OperationalError(message)
    if code is not None:
        inner.sqlite_errorcode = code  # real sqlite3 sets this; tests can too
    return OperationalError("stmt", {}, inner)


def test_busy_discriminator_uses_numeric_codes() -> None:
    assert repo.is_busy_error(_mk_op_error("x", 5))            # SQLITE_BUSY
    assert repo.is_busy_error(_mk_op_error("x", 6))            # SQLITE_LOCKED
    assert repo.is_busy_error(_mk_op_error("x", 517))          # SQLITE_BUSY_SNAPSHOT (extended)
    assert repo.is_busy_error(_mk_op_error("x", 262))          # SQLITE_LOCKED_SHAREDCACHE (extended)
    assert not repo.is_busy_error(_mk_op_error("x", 1))        # SQLITE_ERROR


def test_busy_discriminator_string_fallback() -> None:
    assert repo.is_busy_error(_mk_op_error("database is locked"))
    assert repo.is_busy_error(_mk_op_error("database table is locked"))
    assert repo.is_busy_error(_mk_op_error("database schema is locked"))
    assert not repo.is_busy_error(_mk_op_error("no such table: generations"))


def test_number_discriminator_is_exact_signature() -> None:
    exact = IntegrityError(
        "stmt", {}, sqlite3.IntegrityError(
            "UNIQUE constraint failed: generations.shot_id, generations.generation_number"
        )
    )
    superset = IntegrityError(
        "stmt", {}, sqlite3.IntegrityError(
            "UNIQUE constraint failed: generations.shot_id, "
            "generations.generation_number, generations.other"
        )
    )
    assert repo._is_generation_number_uniqueness_error(exact)
    assert not repo._is_generation_number_uniqueness_error(superset)


# --- fenced BEGIN IMMEDIATE fallback (§37.2) --------------------------------


async def test_fenced_fallback_creates_generation(factory, engine, monkeypatch) -> None:
    monkeypatch.setattr(repo, "sqlite_supports_returning", lambda: False)
    sid, rid, refs = await _seed_shot(factory, engine, with_refs=1)
    inputs = _resolved(refs)
    async with factory() as s:
        gen = await repo.create_generation(s, _draft(sid, rid), inputs)
    assert gen.generation_number == 1
    async with factory() as s:
        stored = await repo.list_generation_inputs(s, gen.id)
    assert len(stored) == 1


async def test_fenced_fallback_rejects_deleted_shot(factory, engine, monkeypatch) -> None:
    monkeypatch.setattr(repo, "sqlite_supports_returning", lambda: False)
    sid, rid, _ = await _seed_shot(factory, engine)
    async with factory() as s:
        await shots.delete_shot(s, sid)
    async with factory() as s:
        with pytest.raises(SoloRingError) as ei:
            await repo.create_generation(s, _draft(sid, rid), [])
    assert ei.value.code == ErrorCode.SHOT_NOT_FOUND


async def test_fenced_fallback_bad_binding_rolls_back(factory, engine, monkeypatch) -> None:
    monkeypatch.setattr(repo, "sqlite_supports_returning", lambda: False)
    sid, rid, _ = await _seed_shot(factory, engine)
    inputs = _resolved([("00000000-0000-0000-0000-000000000000", HEX64)])
    async with factory() as s:
        with pytest.raises(SoloRingError) as ei:
            await repo.create_generation(s, _draft(sid, rid), inputs)
    assert ei.value.code == ErrorCode.VALIDATION_ERROR
    async with factory() as s:
        n = (await s.execute(text("SELECT count(*) FROM generations"))).scalar()
        m = (await s.execute(text("SELECT count(*) FROM generation_inputs"))).scalar()
    assert (n, m) == (0, 0)


# --- timestamps + reads (§50.11, §35) --------------------------------------


async def test_updated_at_generated_by_sqlite(factory, engine) -> None:
    sid, rid, _ = await _seed_shot(factory, engine)
    async with factory() as s:
        gen = await repo.create_generation(s, _draft(sid, rid), [])
    for field in ("created_at", "updated_at", "queued_at"):
        assert _TS.match(getattr(gen, field)), field


async def test_light_and_full_reads(factory, engine) -> None:
    from sqlalchemy import inspect as sa_inspect

    sid, rid, _ = await _seed_shot(factory, engine)
    async with factory() as s:
        gen = await repo.create_generation(s, _draft(sid, rid), [])

    # Lightweight read: the deferred large payload is NOT loaded.
    async with factory() as s:
        light = await repo.get_generation(s, gen.id)
        assert light.status == "queued"
        assert "workflow_spec_json" in sa_inspect(light).unloaded

    # Full provenance read: explicitly undeferred.
    async with factory() as s:
        full = await repo.get_generation_full(s, gen.id)
        assert full.workflow_spec_json == '{"schema_version":1}'
        assert "workflow_spec_json" not in sa_inspect(full).unloaded

    async with factory() as s:
        with pytest.raises(SoloRingError):
            await repo.get_generation(s, new_uuid())


# --- Takes (§50.14) ---------------------------------------------------------


async def test_take_output_identity_constraints(factory, engine) -> None:
    sid, rid, _ = await _seed_shot(factory, engine)
    async with factory() as s:
        g1 = await repo.create_generation(s, _draft(sid, rid), [])
    async with factory() as s:
        g2 = await repo.create_generation(s, _draft(sid, rid), [])

    async def add_take(session: AsyncSession, gen_id: str, key: str) -> None:
        session.add(
            Take(id=new_uuid(), shot_id=sid, generation_id=gen_id, output_key=key)
        )
        await session.commit()

    async with factory() as s:
        await add_take(s, g1.id, "video:0")

    # duplicate (generation_id, output_key) rejected
    async with factory() as s:
        session_take = Take(id=new_uuid(), shot_id=sid, generation_id=g1.id, output_key="video:0")
        s.add(session_take)
        with pytest.raises(IntegrityError):
            await s.commit()
        await s.rollback()

    # same output_key on a DIFFERENT generation is allowed
    async with factory() as s:
        await add_take(s, g2.id, "video:0")

    # empty output_key rejected by CHECK
    async with factory() as s:
        s.add(Take(id=new_uuid(), shot_id=sid, generation_id=g1.id, output_key=""))
        with pytest.raises(IntegrityError):
            await s.commit()
        await s.rollback()
