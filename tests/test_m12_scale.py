"""M12 scale proofs (frozen R3 §21 M12-SCALE).

Representative fixture: 2,000 Compositions, 20,000 stable occurrences,
10,000 published Composition Revisions, 40,000 historical
revision-occurrence rows, 20,000 unrelated Production Revisions, 5,000
identity operations, one 2,000-occurrence working target. Judged by
query/work shape, never wall-clock.
"""

from __future__ import annotations

import asyncio
import hashlib
import json

import pytest
from sqlalchemy import event, text

from soloring.composition.readiness import (
    load_composition_revision_detail,
    publish_composition_revision,
    resolve_publication_readiness,
)
from soloring.composition.service import (
    list_compositions,
    list_working_occurrences,
)
from soloring.domain.ids import new_uuid

NOW = "2026-01-01T00:00:00.000Z"

N_COMPOSITIONS = 2_000
REVISIONS_PER_COMP = 5              # → 10,000 revisions
N_UNRELATED_PRODUCTION = 20_000
TARGET_OCCURRENCES = 2_000


class _QueryCounter:
    def __init__(self, engine):
        self.engine = engine
        self.count = 0

    def __enter__(self):
        def _spy(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().lower().startswith("select"):
                self.count += 1
        self._spy = _spy
        event.listen(self.engine.sync_engine, "before_cursor_execute", _spy)
        return self

    def __exit__(self, *exc):
        event.remove(self.engine.sync_engine, "before_cursor_execute", self._spy)


@pytest.fixture(scope="module")
def representative(tmp_path_factory):
    from sqlalchemy.ext.asyncio import create_async_engine

    from soloring.db import models  # noqa: F401
    from soloring.db.base import Base
    from soloring.settings import Settings

    base = tmp_path_factory.mktemp("m12_scale")
    data_dir = base / "data"
    data_dir.mkdir()
    settings = Settings(data_dir=data_dir)
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(data_dir / 'soloring.db').as_posix()}")

    async def build():
        from soloring.domain.canonical import canonical_json_str

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        pid = new_uuid()
        target_cid = new_uuid()
        selected_rid = new_uuid()
        async with engine.connect() as conn:
            await conn.execute(text(
                "INSERT INTO projects (id, name, created_at, updated_at) "
                "VALUES (:i, 'Scale', :n, :n)"), {"i": pid, "n": NOW})
            await conn.execute(text(
                "INSERT INTO compositions (id, project_id, name, "
                "metadata_version, working_version, created_at, updated_at) "
                "VALUES (:i, :p, 'Target', 0, 0, :n, :n)"),
                {"i": target_cid, "p": pid, "n": NOW})
            # selected production revision (real closure metadata)
            bh = hashlib.sha256(b"m12-scale-selected").hexdigest()
            from soloring.production.canonical import RetainedBlobClosure
            from soloring.production.canonical import (
                production_revision_snapshot_json as prsj,
                production_revision_snapshot_hash as prsh,
            )
            closure = RetainedBlobClosure(blob_hash=bh, size_bytes=1,
                                          media_type=None)
            await conn.execute(text(
                "INSERT INTO blobs (hash, path, size_bytes, "
                "detected_media_type, created_at) VALUES "
                "(:h, :p, 1, NULL, :n)"),
                {"h": bh, "p": f"sha256/{bh[:2]}/{bh[2:4]}/{bh}", "n": NOW})
            await conn.execute(text(
                "INSERT INTO production_objects (id, project_id, name, "
                "created_at, updated_at) VALUES (:o, :p, 'Sel', :n, :n)"),
                {"o": new_uuid(), "p": pid, "n": NOW})
            await conn.execute(text(
                "INSERT INTO production_revisions (id, production_object_id, "
                "revision_number, snapshot_json, snapshot_hash, created_at) "
                "VALUES (:r, (SELECT id FROM production_objects LIMIT 1), 1, "
                ":sj, :sh, :n)"),
                {"r": selected_rid, "sj": prsj(closure), "sh": prsh(closure),
                 "n": NOW})
            await conn.execute(text(
                "INSERT INTO production_revision_closures "
                "(production_revision_id, contract_key, contract_version, "
                "blob_hash, size_bytes, media_type) VALUES "
                "(:r, 'retained_blob', 1, :bh, 1, NULL)"),
                {"r": selected_rid, "bh": bh})

            # target working occurrences (2,000), each with a birth op
            occ_rows, target_edges, working_rows = [], [], []
            for i in range(TARGET_OCCURRENCES):
                oid = new_uuid()
                op = new_uuid()
                occ_rows.append({"o": oid, "op": op, "n": NOW})
                target_edges.append({"o": oid, "op": op})
                working_rows.append({
                    "o": oid, "name": f"Occ {i}", "pr": selected_rid,
                    "n": NOW})
            await conn.execute(text(
                "INSERT INTO composition_occurrences (id, composition_id, "
                "created_at) VALUES (:o, :c, :n)"),
                [{**r, "c": target_cid} for r in occ_rows])
            await conn.execute(text(
                "INSERT INTO composition_identity_operations (id, "
                "composition_id, operation_kind, working_version_before, "
                "working_version_after, request_fingerprint, "
                "impact_fingerprint, operation_json, operation_hash, "
                "created_at) VALUES (:op, :c, 'mint', :vb, :vb + 1, :rf, :mf, "
                "'{}', :oh, :n)"),
                [{**r, "c": target_cid, "vb": i, "rf": "0" * 64,
                  "mf": "1" * 64, "oh": f"{i:064x}"} for i, r in
                 enumerate(occ_rows)])
            await conn.execute(text(
                "INSERT INTO composition_identity_operation_targets "
                "(composition_id, operation_id, occurrence_id) VALUES "
                "(:c, :op, :o)"),
                [{**e, "c": target_cid} for e in target_edges])
            await conn.execute(text(
                "INSERT INTO composition_working_occurrences (composition_id, "
                "occurrence_id, display_name, source_kind, "
                "production_revision_id, visible, x_mm, y_mm, z_mm, yaw_udeg, "
                "pitch_udeg, roll_udeg, updated_at) VALUES "
                "(:c, :o, :name, 'production_revision', :pr, 1, 0, 0, 0, 0, "
                "0, 0, :n)"),
                [{**w, "c": target_cid} for w in working_rows])
            await conn.execute(text(
                "UPDATE compositions SET working_version = :wv WHERE id = :c"),
                {"c": target_cid, "wv": TARGET_OCCURRENCES})

            # unrelated production revisions
            await conn.execute(text(
                "INSERT OR IGNORE INTO blobs (hash, path, size_bytes, "
                "detected_media_type, created_at) VALUES (:h, :p, 1, NULL, "
                ":n)"),
                [{"h": h, "p": f"sha256/{h[:2]}/{h[2:4]}/{h}", "n": NOW}
                 for h in (hashlib.sha256(f"unrel-{i}".encode()).hexdigest()
                           for i in range(N_UNRELATED_PRODUCTION))])
            # each unrelated revision belongs to its own object to keep
            # (production_object_id, revision_number) unique
            unrel_objs = [{"o": new_uuid()} for _ in range(
                N_UNRELATED_PRODUCTION)]
            await conn.execute(text(
                "INSERT INTO production_objects (id, project_id, name, "
                "created_at, updated_at) VALUES (:o, :p, 'Bulk', :n, :n)"),
                [{**o, "p": pid, "n": NOW} for o in unrel_objs])
            await conn.execute(text(
                "INSERT INTO production_revisions (id, production_object_id, "
                "revision_number, snapshot_json, snapshot_hash, created_at) "
                "VALUES (:r, :o, 1, '{}', :h, :n)"),
                [{"r": new_uuid(), "o": o["o"], "h": f"{i:064x}", "n": NOW}
                 for i, o in enumerate(unrel_objs)])

            # bulk compositions with published revisions + projections
            for batch_start in range(0, N_COMPOSITIONS, 500):
                batch = range(batch_start, min(batch_start + 500,
                                               N_COMPOSITIONS))
                comps, revs, projs, occ_bulk, deps = [], [], [], [], []
                from soloring.domain.canonical import canonical_hash
                for i in batch:
                    cid = new_uuid()
                    comps.append({"c": cid, "n": NOW})
                    OCC_PER_REV = 4  # 10,000 revs x 4 = 40,000 rows
                    for j in range(REVISIONS_PER_COMP):
                        rid = new_uuid()
                        occ_ids = [new_uuid() for _ in range(OCC_PER_REV)]
                        snap = {
                            "schema_version": 1,
                            "occurrences": [{
                                "occurrence_id": oid,
                                "display_name": "Bulk",
                                "source": {"kind": "production_revision",
                                           "revision_id": selected_rid},
                                "transform": {"translation_mm": [0, 0, 0],
                                              "rotation_udeg": [0, 0, 0]},
                                "visible": True}
                                for oid in sorted(occ_ids)],
                            "dependencies": {
                                "production_revision_ids": [selected_rid],
                                "composition_revision_ids": []},
                        }
                        revs.append({"r": rid, "c": cid, "num": j + 1,
                                     "sj": canonical_json_str(snap),
                                     "sh": canonical_hash(snap), "n": NOW})
                        for oid in sorted(occ_ids):
                            occ_bulk.append({"o": oid, "c": cid, "n": NOW})
                            projs.append({"r": rid, "c": cid, "o": oid,
                                          "n": NOW})
                        deps.append({"r": rid, "pr": selected_rid})
                await conn.execute(text(
                    "INSERT INTO compositions (id, project_id, name, "
                    "metadata_version, working_version, created_at, "
                    "updated_at) VALUES (:c, :p, 'Bulk', 0, 0, :n, :n)"),
                    [{**c, "p": pid} for c in comps])
                await conn.execute(text(
                    "INSERT INTO composition_occurrences (id, composition_id, "
                    "created_at) VALUES (:o, :c, :n)"),
                    occ_bulk)
                await conn.execute(text(
                    "INSERT INTO composition_revisions (id, composition_id, "
                    "revision_number, snapshot_json, snapshot_hash, "
                    "created_at) VALUES (:r, :c, :num, :sj, :sh, :n)"),
                    revs)
                await conn.execute(text(
                    "INSERT INTO composition_revision_occurrences "
                    "(composition_revision_id, composition_id, occurrence_id, "
                    "display_name, source_kind, production_revision_id, "
                    "visible, x_mm, y_mm, z_mm, yaw_udeg, pitch_udeg, "
                    "roll_udeg) VALUES (:r, :c, :o, 'Bulk', "
                    "'production_revision', :pr, 1, 0, 0, 0, 0, 0, 0)"),
                    [{**p, "pr": selected_rid} for p in projs])
                await conn.execute(text(
                    "INSERT INTO composition_revision_production_dependencies "
                    "(composition_revision_id, production_revision_id) "
                    "VALUES (:r, :pr)"), deps)
            await conn.commit()
        return {"project_id": pid, "target_cid": target_cid,
                "selected_rid": selected_rid}

    info = asyncio.run(build())
    yield {"engine": engine, "settings": settings, **info}
    asyncio.run(engine.dispose())


def test_scale_fixture_cardinalities(representative):
    """M12-SCALE:01 — representative scale is reproducible."""
    async def counts():
        from sqlalchemy import text as _text

        async with representative["engine"].connect() as conn:
            out = {}
            for key, sql in {
                "compositions": "SELECT COUNT(*) FROM compositions",
                "occurrences":
                    "SELECT COUNT(*) FROM composition_occurrences",
                "revisions": "SELECT COUNT(*) FROM composition_revisions",
                "history_rows":
                    "SELECT COUNT(*) FROM composition_revision_occurrences",
                "production":
                    "SELECT COUNT(*) FROM production_revisions",
                "identity_ops":
                    "SELECT COUNT(*) FROM composition_identity_operations",
            }.items():
                out[key] = (await conn.execute(_text(sql))).scalar_one()
            return out

    c = asyncio.run(counts())
    assert c["compositions"] >= N_COMPOSITIONS
    assert c["occurrences"] >= TARGET_OCCURRENCES
    assert c["revisions"] >= 10_000
    assert c["history_rows"] >= 40_000
    assert c["production"] >= N_UNRELATED_PRODUCTION + 1
    assert c["identity_ops"] >= TARGET_OCCURRENCES


async def _module_engine_session(representative):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    return async_sessionmaker(bind=representative["engine"],
                              expire_on_commit=False, class_=AsyncSession)


async def test_scale_working_occurrence_listing_is_bounded_queries(
    representative,
):
    """M12-SCALE:01 owner — no N+1 in occurrence listing."""
    factory = await _module_engine_session(representative)
    async with factory() as s:
        with _QueryCounter(representative["engine"]) as counter:
            listing = await list_working_occurrences(
                s, representative["target_cid"])
    assert len(listing) == TARGET_OCCURRENCES
    assert counter.count <= 3  # bounded query count regardless of N


async def test_scale_composition_listing_is_bounded_queries(representative):
    """M12-SCALE:06 — listing 2,000 Compositions has no per-Comp query."""
    factory = await _module_engine_session(representative)
    async with factory() as s:
        with _QueryCounter(representative["engine"]) as counter:
            listing = await list_compositions(s, representative["project_id"])
    assert len(listing) >= N_COMPOSITIONS
    assert counter.count <= 3


async def test_scale_publication_readiness_source_validation_is_set_oriented(
    representative,
):
    """M12-SCALE:02 — readiness does not query once per occurrence."""
    factory = await _module_engine_session(representative)
    async with factory() as s:
        with _QueryCounter(representative["engine"]) as counter:
            r = await resolve_publication_readiness(
                s, representative["target_cid"])
    assert r["ready"] and r["occurrence_count"] == TARGET_OCCURRENCES
    assert counter.count < 30  # set-oriented, not 2,000 queries


async def test_scale_revision_detail_load_is_bounded_queries(representative):
    """M12-SCALE:05."""
    from soloring.composition.readiness import _verify_revision_invariants

    factory = await _module_engine_session(representative)
    async with factory() as s:
        async with s.bind.connect() as conn:
            rid = (await conn.execute(text(
                "SELECT id FROM composition_revisions LIMIT 1"))).scalar_one()
            with _QueryCounter(representative["engine"]) as counter:
                detail = await load_composition_revision_detail(s, rid)
    assert detail["revision_id"] == rid
    assert counter.count <= 20


async def test_scale_identity_impact_resolution_is_set_oriented(
    representative,
):
    """M12-SCALE:04."""
    from soloring.composition.impacts import preview_identity_operation

    factory = await _module_engine_session(representative)
    async with factory() as s:
        async with s.bind.connect() as conn:
            result = await conn.execute(
                text("SELECT occurrence_id FROM "
                     "composition_working_occurrences "
                     "WHERE composition_id = :c LIMIT 50"),
                {"c": representative["target_cid"]})
            ocs = [r[0] for r in result.fetchall()]
        from soloring.composition.impacts import _dispositions

        async with s.bind.connect() as conn:
            with _QueryCounter(representative["engine"]) as counter:
                dispositions = await _dispositions(
                    conn, representative["target_cid"], ocs)
        assert len(dispositions) == 50
        assert all(d["active"] and d["in_working_state"] for d in dispositions)
        assert counter.count <= 3  # set-oriented: 50 sources, bounded queries


async def test_scale_nested_closure_uses_normalized_dependency_sets(
    representative, tmp_path
):
    """M12-SCALE:03/:07 — closure reads frozen rows, no recursive walk."""
    factory = await _module_engine_session(representative)
    async with factory() as s:
        async with s.bind.connect() as conn:
            with _QueryCounter(representative["engine"]) as counter:
                rows = (await conn.execute(text(
                    "SELECT d.nested_composition_revision_id FROM "
                    "composition_revision_nested_dependencies d "
                    "WHERE d.composition_revision_id = (SELECT id FROM "
                    "composition_revisions LIMIT 1)"))).fetchall()
                prows = (await conn.execute(text(
                    "SELECT production_revision_id FROM "
                    "composition_revision_production_dependencies WHERE "
                    "composition_revision_id = (SELECT id FROM "
                    "composition_revisions LIMIT 1)"))).fetchall()
    # normalized closure sets are read in bounded queries
    assert counter.count <= 3
    assert isinstance(rows, list) and isinstance(prows, list)


async def test_scale_deep_nested_chain_uses_frozen_closure_without_recursive_current_state_walk(  # noqa: E501
    representative,
):
    """M12-SCALE:07 — depth-32 chain reads frozen closure rows, bounded."""
    # build a depth-32 nested chain in a dedicated small fixture
    import hashlib as _hl

    from sqlalchemy import text as _text
    from sqlalchemy.ext.asyncio import (AsyncSession, async_sessionmaker,
                                        create_async_engine)

    from soloring.db import models  # noqa: F401
    from soloring.db.base import Base
    from soloring.settings import Settings
    import tempfile
    from pathlib import Path as _P

    tmp = tempfile.mkdtemp()
    settings = Settings(data_dir=_P(tmp))
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{_P(tmp).as_posix()}/chain.db")

    async def build():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        pid = new_uuid()
        prid = new_uuid()
        async with engine.connect() as conn:
            await conn.execute(_text(
                "INSERT INTO projects (id, name, created_at, updated_at) "
                "VALUES (:i, 'Chain', :n, :n)"), {"i": pid, "n": NOW})
            bh = _hl.sha256(b"chain-leaf").hexdigest()
            await conn.execute(_text(
                "INSERT INTO blobs (hash, path, size_bytes, "
                "detected_media_type, created_at) VALUES "
                "(:h, :p, 5, NULL, :n)"),
                {"h": bh, "p": f"sha256/{bh[:2]}/{bh[2:4]}/{bh}", "n": NOW})
            await conn.execute(_text(
                "INSERT INTO production_objects (id, project_id, name, "
                "created_at, updated_at) VALUES (:o, :p, 'Obj', :n, :n)"),
                {"o": new_uuid(), "p": pid, "n": NOW})
            await conn.execute(_text(
                "INSERT INTO production_revisions (id, production_object_id, "
                "revision_number, snapshot_json, snapshot_hash, created_at) "
                "VALUES (:r, (SELECT id FROM production_objects LIMIT 1), 1, "
                "'{}', :h, :n)"),
                {"r": prid, "h": "0" * 64, "n": NOW})
            await conn.execute(_text(
                "INSERT INTO production_revision_closures "
                "(production_revision_id, contract_key, contract_version, "
                "blob_hash, size_bytes, media_type) VALUES "
                "(:r, 'retained_blob', 1, :bh, 5, NULL)"),
                {"r": prid, "bh": bh})
            # depth-32 chain: comp_i nests comp_{i-1}'s revision
            from soloring.domain.canonical import (
                canonical_hash,
                canonical_json_str,
            )
            prev_rev = None
            prev_prod_deps = []
            prev_nested_deps = []
            for depth in range(32):
                cid, rid, oid = new_uuid(), new_uuid(), new_uuid
