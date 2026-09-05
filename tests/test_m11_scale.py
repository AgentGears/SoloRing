"""M11 scale/query-shape proofs (frozen R3 plan §§20.11/22).

The representative fixture is evidence scale, not a product limit:
>=2,000 Production Objects, >=10,000 Production Revisions, >=10,000 source
links, >=20,000 unrelated Project Assets. Authority is query shape and
one-selected-Blob physical work — no wall-clock threshold is normative.
"""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import event, text

from soloring.assets.blob_store import BlobStore
from soloring.domain.ids import new_uuid
from soloring.production.canonical import (
    RetainedBlobClosure,
    production_revision_snapshot_hash,
    production_revision_snapshot_json,
)
from soloring.production.service import (
    create_production_object,
    list_production_objects,
    list_production_revisions,
)
from soloring.production.readiness import resolve_publication_readiness
from soloring.production.service import load_production_revision_metadata_verified

NOW = "2026-01-01T00:00:00.000Z"

N_OBJECTS = 2_000
REVISIONS_PER_OBJECT = 5          # → 10,000 revisions + 10,000 source links
N_UNRELATED_ASSETS = 20_000


@pytest.fixture
def blob_store(settings) -> BlobStore:
    return BlobStore(settings)


class _QueryCounter:
    """Counts SELECT statements issued through the engine."""

    def __init__(self, engine) -> None:
        self.engine = engine
        self.count = 0
        self.statements: list[str] = []

    def __enter__(self):
        self._listener = self._make_listener()
        event.listen(self.engine.sync_engine, "before_cursor_execute", self._listener)
        return self

    def _make_listener(self):
        def _spy(conn, cursor, statement, parameters, context, executemany):
            low = statement.lower()
            if low.lstrip().startswith("select") or low.lstrip().startswith("pragma table_info"):
                self.count += 1
                self.statements.append(statement)
        return _spy

    def __exit__(self, *exc):
        event.remove(self.engine.sync_engine, "before_cursor_execute", self._listener)


async def _seed_representative(engine, blob_store) -> dict:
    """Bulk-build the frozen representative fixture through direct SQL."""
    pid = new_uuid()
    selected_data = b"selected-blob"
    selected_bh = hashlib.sha256(selected_data).hexdigest()
    p = blob_store.path_for_hash(selected_bh)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(selected_data)

    async with engine.connect() as conn:
        await conn.execute(
            text("INSERT INTO projects (id, name, created_at, updated_at) "
                 "VALUES (:id, 'Scale', :n, :n)"), {"id": pid, "n": NOW})
        # selected candidate asset (real physical bytes)
        await conn.execute(
            text("INSERT INTO blobs (hash, path, size_bytes, detected_media_type, created_at) "
                 "VALUES (:h, :p, :s, 'image/png', :n)"),
            {"h": selected_bh, "p": f"sha256/{selected_bh[:2]}/{selected_bh[2:4]}/{selected_bh}",
             "s": len(selected_data), "n": NOW})
        selected_asset = new_uuid()
        await conn.execute(
            text("INSERT INTO assets (id, project_id, blob_hash, kind, created_at) "
                 "VALUES (:a, :p, :h, 'reference', :n)"),
            {"a": selected_asset, "p": pid, "h": selected_bh, "n": NOW})

        # unrelated project assets over synthetic blobs (no physical bytes:
        # they are never selected, and readiness must not touch them)
        unrelated = [
            (new_uuid(), pid, hashlib.sha256(f"unrelated-{i}".encode()).hexdigest())
            for i in range(N_UNRELATED_ASSETS)
        ]
        await conn.execute(
            text("INSERT OR IGNORE INTO blobs (hash, path, size_bytes, detected_media_type, created_at) "
                 "VALUES (:h, :p, 1, NULL, :n)"),
            [{"h": bh, "p": f"sha256/{bh[:2]}/{bh[2:4]}/{bh}", "n": NOW}
             for _, _, bh in unrelated],
        )
        await conn.execute(
            text("INSERT INTO assets (id, project_id, blob_hash, kind, created_at) "
                 "VALUES (:a, :p, :h, 'reference', :n)"),
            [{"a": a, "p": pid, "h": bh, "n": NOW} for a, _, bh in unrelated],
        )

        # production objects + revisions + closures + source links
        objs, revs, closures, links = [], [], [], []
        for i in range(N_OBJECTS):
            oid = new_uuid()
            objs.append({"id": oid, "project_id": pid,
                         "name": f"Object {i}", "desc": None})
            for j in range(REVISIONS_PER_OBJECT):
                closure = RetainedBlobClosure(
                    blob_hash=hashlib.sha256(f"obj{i}-rev{j}".encode()).hexdigest(),
                    size_bytes=3,
                    media_type=None,
                )
                rid = new_uuid()
                revs.append({
                    "id": rid, "oid": oid, "num": j + 1,
                    "sj": production_revision_snapshot_json(closure),
                    "sh": production_revision_snapshot_hash(closure),
                })
                closures.append({
                    "rid": rid, "bh": closure.blob_hash, "sz": 3, "mt": None,
                })
                links.append({"rid": rid, "a": selected_asset})
        await conn.execute(
            text("INSERT INTO production_objects (id, project_id, name, description, "
                 "created_at, updated_at) VALUES (:id, :project_id, :name, :desc, :n, :n)"),
            [{**o, "n": NOW} for o in objs],
        )
        await conn.execute(
            text("INSERT OR IGNORE INTO blobs (hash, path, size_bytes, detected_media_type, created_at) "
                 "VALUES (:h, :p, 3, NULL, :n)"),
            [{"h": c["bh"], "p": f"sha256/{c['bh'][:2]}/{c['bh'][2:4]}/{c['bh']}", "n": NOW}
             for c in closures],
        )
        await conn.execute(
            text("INSERT INTO production_revisions (id, production_object_id, revision_number, "
                 "snapshot_json, snapshot_hash, created_at) "
                 "VALUES (:id, :oid, :num, :sj, :sh, :n)"),
            [{**r, "n": NOW} for r in revs],
        )
        await conn.execute(
            text("INSERT INTO production_revision_closures (production_revision_id, "
                 "contract_key, contract_version, blob_hash, size_bytes, media_type) "
                 "VALUES (:rid, 'retained_blob', 1, :bh, :sz, :mt)"),
            closures,
        )
        await conn.execute(
            text("INSERT INTO production_revision_source_assets (production_revision_id, "
                 "asset_id, created_at) VALUES (:rid, :a, :n)"),
            [{**l, "n": NOW} for l in links],
        )
        await conn.commit()
    return {"project_id": pid, "object_id": objs[0]["id"],
            "selected_asset": selected_asset,
            "revision_id": revs[0]["id"]}


@pytest.fixture(scope="module")
def representative(tmp_path_factory):
    import asyncio

    from sqlalchemy.ext.asyncio import create_async_engine

    from soloring.settings import Settings

    base = tmp_path_factory.mktemp("m11_scale")
    data_dir = base / "data"
    data_dir.mkdir()
    settings = Settings(data_dir=data_dir)
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(data_dir / 'soloring.db').as_posix()}")
    from soloring.db import models  # noqa: F401
    from soloring.db.base import Base

    async def build():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        return await _seed_representative(engine, BlobStore(settings))

    info = asyncio.run(build())
    yield {"engine": engine, "settings": settings, **info}
    asyncio.run(engine.dispose())


def test_representative_fixture_is_deterministic_and_meets_frozen_cardinalities(
    representative,
):
    """M11-SCALE:01 — representative scale is reproducible."""
    import asyncio

    async def counts():
        async with representative["engine"].connect() as conn:
            objs = (await conn.execute(
                text("SELECT COUNT(*) FROM production_objects"))).scalar_one()
            revs = (await conn.execute(
                text("SELECT COUNT(*) FROM production_revisions"))).scalar_one()
            links = (await conn.execute(
                text("SELECT COUNT(*) FROM production_revision_source_assets"))).scalar_one()
            assets = (await conn.execute(
                text("SELECT COUNT(*) FROM assets"))).scalar_one()
        return objs, revs, links, assets

    objs, revs, links, assets = asyncio.run(counts())
    assert objs == N_OBJECTS
    assert revs == N_OBJECTS * REVISIONS_PER_OBJECT == 10_000
    assert links == 10_000
    assert assets == N_UNRELATED_ASSETS + 1


async def _query_count(engine, fn) -> tuple[int, object]:
    with _QueryCounter(engine) as counter:
        result = await fn()
    return counter.count, result


async def test_production_object_list_query_shape_is_bounded(
    engine, factory, representative
):
    """M11-SCALE:02 — object list query count does not grow with N."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    rep_engine = representative["engine"]
    rep_factory = async_sessionmaker(bind=rep_engine, expire_on_commit=False,
                                     class_=AsyncSession)
    pid = representative["project_id"]

    async with rep_factory() as s:
        big_count, big = await _query_count(
            rep_engine, lambda: list_production_objects(s, pid))
    assert len(big) == N_OBJECTS

    # small fixture: one object on the per-test engine
    pid2 = new_uuid()
    async with factory() as s:
        async with s.bind.connect() as conn:
            await conn.execute(
                text("INSERT INTO projects (id, name, created_at, updated_at) "
                     "VALUES (:id, 'Small', :n, :n)"), {"id": pid2, "n": NOW})
            await conn.commit()
    async with factory() as s:
        await create_production_object(s, pid2, name="Only")
    async with factory() as s:
        small_count, small = await _query_count(
            engine, lambda: list_production_objects(s, pid2))
    assert len(small) == 1
    assert big_count == small_count  # same bounded query class


async def test_revision_list_query_shape_is_bounded(
    engine, factory, representative
):
    """M11-SCALE:03 — revision list stays bounded (one query)."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    rep_factory = async_sessionmaker(bind=representative["engine"],
                                     expire_on_commit=False, class_=AsyncSession)
    oid = representative["object_id"]
    async with rep_factory() as s:
        count, listing = await _query_count(
            representative["engine"],
            lambda: list_production_revisions(s, oid))
    assert len(listing) == REVISIONS_PER_OBJECT
    assert count <= 2  # one bounded query (plus at most trivial metadata)


async def test_readiness_query_class_independent_of_total_project_assets(
    representative
):
    """M11-SCALE:04 — readiness does not scan unrelated Assets."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    rep_factory = async_sessionmaker(bind=representative["engine"],
                                     expire_on_commit=False, class_=AsyncSession)
    blob_store = BlobStore(representative["settings"])
    async with rep_factory() as s:
        with _QueryCounter(representative["engine"]) as counter:
            r = await resolve_publication_readiness(
                s, blob_store,
                production_object_id=representative["object_id"],
                source_asset_id=representative["selected_asset"])
    assert r.ready
    asset_touching = [
        q for q in counter.statements
        if "FROM assets" in q and "JOIN" not in q.upper()
    ]
    # No statement enumerates the asset table: the candidate is resolved by
    # identity, never by scanning Project Assets.
    for q in counter.statements:
        low = q.lower()
        if low.startswith("select") and "assets" in low:
            assert "where a.id =" in low or "where assets.id" in low, q[:120]
    assert counter.count < 10  # bounded query family, not 20k-cardinality


async def test_readiness_hashes_selected_blob_only(representative, monkeypatch):
    """M11-SCALE:05 — physical work is one selected Blob, not Project media."""
    calls: list[str] = []
    orig = BlobStore.verify_physical_bytes

    async def _spied(self, blob_hash, expected_size):
        calls.append(blob_hash)
        return await orig(self, blob_hash, expected_size)

    monkeypatch.setattr(BlobStore, "verify_physical_bytes", _spied)
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    rep_factory = async_sessionmaker(bind=representative["engine"],
                                     expire_on_commit=False, class_=AsyncSession)
    blob_store = BlobStore(representative["settings"])
    async with rep_factory() as s:
        r = await resolve_publication_readiness(
            s, blob_store,
            production_object_id=representative["object_id"],
            source_asset_id=representative["selected_asset"])
    assert r.ready
    assert len(calls) == 1  # exactly one physical hash: the selected Blob


async def test_metadata_detail_query_shape_is_bounded_and_performs_no_full_hash(
    representative, monkeypatch
):
    """M11-SCALE:06 — ordinary detail is bounded in SQL and physical work."""
    calls: list[str] = []
    orig = BlobStore.verify_physical_bytes

    async def _spied(self, blob_hash, expected_size):
        calls.append(blob_hash)
        return await orig(self, blob_hash, expected_size)

    monkeypatch.setattr(BlobStore, "verify_physical_bytes", _spied)
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    rep_factory = async_sessionmaker(bind=representative["engine"],
                                     expire_on_commit=False, class_=AsyncSession)
    async with rep_factory() as s:
        async with s.bind.connect() as conn:
            with _QueryCounter(representative["engine"]) as counter:
                meta = await load_production_revision_metadata_verified(
                    conn, revision_id=representative["revision_id"])
    assert meta["revision_id"] == representative["revision_id"]
    assert counter.count <= 10
    assert calls == []  # no full physical hash on ordinary detail
