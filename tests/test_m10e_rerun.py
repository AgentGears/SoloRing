"""M10E-E — Exact Rerun of real schema-3 Generations (frozen R3 §19).

Durable WorkflowSpec bytes verbatim, exact derived payload projection
(only generation_id rebinding), zero current-M10 reads, zero compiler/
materializer/registration calls, historical-mutation isolation, and
fail-closed corruption behavior (E-070..E-077)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import text

from tests.test_m10e_generation import (
    _EXTENTS,
    _create,
    _schema3_package,
    _siblings,
    _spatial_seed,
    _spatial_settings,
    _spec,
)


async def _terminal_generation(factory, engine, settings, tmp_path,
                               *, staged=2):
    pkg = await _schema3_package(tmp_path)
    seed = await _spatial_seed(factory, staged=staged, extents=_EXTENTS)
    gen = await _create(factory, _spatial_settings(settings, pkg), seed)
    async with engine.connect() as conn:
        await conn.execute(text(
            "UPDATE generations SET status='succeeded', completed_at='t' "
            "WHERE id = :g"), {"g": gen.id})
        await conn.commit()
    return gen, seed, pkg


async def test_rerun_copies_spec_bytes_and_derived_projection(
        factory, engine, settings, tmp_path):
    """E-070/E-071: WorkflowSpec JSON/hash verbatim; each sibling's
    identity-bearing tuple copied exactly; only the parent changes."""
    from soloring.generation import rerun

    gen, _, _ = await _terminal_generation(
        factory, engine, settings, tmp_path)
    new = await rerun.create_rerun(
        _session(factory), gen.id)
    src_rows = await _siblings(engine, gen.id)
    new_rows = await _siblings(engine, new.id)
    assert [r["input_key"] for r in src_rows] == \
        [r["input_key"] for r in new_rows]
    for s, n in zip(src_rows, new_rows):
        assert s == n  # full projection equality
    async with engine.connect() as conn:
        src = (await conn.execute(text(
            "SELECT workflow_spec_json, workflow_spec_hash FROM "
            "generations WHERE id = :g"), {"g": gen.id})).mappings().one()
        dst = (await conn.execute(text(
            "SELECT workflow_spec_json, workflow_spec_hash FROM "
            "generations WHERE id = :g"), {"g": new.id})).mappings().one()
    assert dst["workflow_spec_json"] == src["workflow_spec_json"]
    assert dst["workflow_spec_hash"] == src["workflow_spec_hash"]


def _session(factory):
    return factory()


async def test_rerun_zero_current_m10_reads_and_zero_rematerialization(
        factory, engine, settings, tmp_path, monkeypatch):
    """E-072/E-073: spies with positive controls — no current-M10 reads,
    no compose/materialize/register calls during rerun."""
    from sqlalchemy import event

    from soloring.generation import rerun
    from soloring.spatial import boxdepth, realize
    from soloring.spatial import derived as derived_mod
    from soloring.spatial.worker_inputs import current_m10_table_names

    gen, _, _ = await _terminal_generation(
        factory, engine, settings, tmp_path)

    called = {"compose": 0, "materialize": 0, "register": 0}

    async def _no_compose(*a, **k):
        called["compose"] += 1
        raise AssertionError("rerun must not compile spatial authority")

    def _no_materialize(*a, **k):
        called["materialize"] += 1
        raise AssertionError("rerun must not rematerialize D0")

    async def _no_register(*a, **k):
        called["register"] += 1
        raise AssertionError("rerun must not register derived artifacts")

    monkeypatch.setattr(realize, "compose_spatial_realization", _no_compose)
    monkeypatch.setattr(boxdepth, "materialize", _no_materialize)
    monkeypatch.setattr(derived_mod, "register_derived_artifact",
                        _no_register)

    seen: list[str] = []
    forbidden = set(current_m10_table_names())

    def _spy(conn, cursor, statement, parameters, context,
             executemany=False):
        s = statement.lower()
        if s.strip().startswith(("select", "insert", "update")):
            seen.append(s)

    eng = engine.sync_engine
    event.listen(eng, "before_cursor_execute", _spy)
    try:
        new = await rerun.create_rerun(_session(factory), gen.id)
        import re

        hits = [s for s in seen if any(
            re.search(rf"\b{t}\b", s) for t in forbidden)]
        assert hits == [], f"rerun read current M10: {hits[:2]}"
        assert called == {"compose": 0, "materialize": 0, "register": 0}
        assert (await _siblings(engine, new.id))
    finally:
        event.remove(eng, "before_cursor_execute", _spy)


async def test_current_authority_mutation_cannot_change_rerun_identity(
        factory, engine, settings, tmp_path):
    """E-074/§22.5: after the source Generation is terminal, aggressive
    current M10 mutation leaves the rerun's durable identity identical."""
    from soloring.generation import rerun

    gen, seed, _ = await _terminal_generation(
        factory, engine, settings, tmp_path)
    src_rows = await _siblings(engine, gen.id)
    src_spec = await _spec(engine, gen.id)

    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        # wipe/rewrite every current M10 authority surface
        await conn.execute(text(
            "DELETE FROM shot_spatial_plans WHERE shot_id = :s"),
            {"s": seed["shot"]})
        await conn.execute(text(
            "UPDATE spatial_world_revisions SET snapshot_json = '{}', "
            "snapshot_hash = :h WHERE id LIKE '%'"),
            {"h": "0" * 64})
        await conn.execute(text(
            "UPDATE spatial_tracks SET deleted_at = 't', "
            "requirement = 'optional'"))
        await conn.execute(text(
            "UPDATE spatial_worlds SET requirement = 'optional', "
            "deleted_at = 't'"))
        await conn.exec_driver_sql("COMMIT")

    new = await rerun.create_rerun(_session(factory), gen.id)
    assert await _spec(engine, new.id) == src_spec
    assert await _siblings(engine, new.id) == src_rows


async def test_rerun_execution_fails_closed_on_corrupt_history(
        factory, engine, settings, tmp_path):
    """E-075: corrupt physical derived bytes fail the rerun's worker
    verification closed — never rematerialize."""
    from soloring.assets.blob_store import BlobStore
    from soloring.errors import SoloRingError
    from soloring.generation import rerun
    from soloring.spatial import error_codes as ec
    from soloring.spatial.package3 import parse_manifest_v3
    from soloring.spatial import production_package as prod
    from soloring.spatial.worker_inputs import load_verified_derived_inputs

    gen, _, _ = await _terminal_generation(
        factory, engine, settings, tmp_path, staged=1)
    new = await rerun.create_rerun(_session(factory), gen.id)
    rows = await _siblings(engine, new.id)
    BlobStore(settings).path_for_hash(rows[0]["blob_hash"]).write_bytes(
        b"tampered")

    spec = await _spec(engine, new.id)
    async with factory() as session:
        with pytest.raises(SoloRingError) as ei:
            await load_verified_derived_inputs(
                session, BlobStore(settings), generation_id=new.id,
                workflow_spec=spec,
                manifest_v3=parse_manifest_v3(prod.production_manifest_v3()))
    assert ei.value.code == ec.DERIVED_SPATIAL_BLOB_CORRUPT


async def test_rerun_reuses_retained_blob_identities(
        factory, engine, settings, tmp_path):
    """§29: the rerun worker reuses the exact same derived artifact IDs /
    blob hashes as the source attempt."""
    from soloring.assets.blob_store import BlobStore
    from soloring.generation import rerun
    from soloring.spatial.package3 import parse_manifest_v3
    from soloring.spatial import production_package as prod
    from soloring.spatial.worker_inputs import load_verified_derived_inputs

    class _Up:
        async def upload(self, *, source_path: Path, filename: str,
                         subfolder: str):
            return filename, subfolder

    gen, _, _ = await _terminal_generation(
        factory, engine, settings, tmp_path, staged=2)
    new = await rerun.create_rerun(_session(factory), gen.id)
    spec = await _spec(engine, new.id)
    async with factory() as session:
        verified = await load_verified_derived_inputs(
            session, BlobStore(settings), generation_id=new.id,
            workflow_spec=spec,
            manifest_v3=parse_manifest_v3(prod.production_manifest_v3()))
    assert [v.blob_hash for v in verified] == \
        [r["blob_hash"] for r in await _siblings(engine, gen.id)]


async def test_rerun_transport_references_are_nondurable(
        factory, engine, settings, tmp_path):
    """E-077: rerun-local upload filenames/subfolders/executor references
    legitimately DIFFER between the source execution and its rerun — they
    are execution-attempt-local transport state, never historical
    identity. Exactness is asserted ONLY over retained Blob bytes/hashes,
    the durable WorkflowSpec bytes, and the five-field derived payload
    projection."""
    import hashlib

    from soloring.assets.blob_store import BlobStore
    from soloring.generation import rerun
    from soloring.spatial.package3 import parse_manifest_v3
    from soloring.spatial import production_package as prod
    from soloring.spatial.worker_inputs import execute_schema3_derived_inputs

    class _Recording:
        def __init__(self) -> None:
            self.uploads: list[tuple[str, str, bytes]] = []

        async def upload(self, *, source_path: Path, filename: str,
                         subfolder: str):
            data = source_path.read_bytes()
            self.uploads.append((filename, subfolder, data))
            return filename, subfolder

        async def upload_bytes(self, *, data: bytes, filename: str,
                               subfolder: str):
            self.uploads.append((filename, subfolder, data))
            return filename, subfolder

    gen, _, _ = await _terminal_generation(
        factory, engine, settings, tmp_path, staged=2)
    new = await rerun.create_rerun(_session(factory), gen.id)

    async with engine.connect() as conn:
        src_row = (await conn.execute(text(
            "SELECT workflow_spec_json, workflow_spec_hash FROM "
            "generations WHERE id = :g"),
            {"g": gen.id})).mappings().one()
        new_row = (await conn.execute(text(
            "SELECT workflow_spec_json, workflow_spec_hash FROM "
            "generations WHERE id = :g"),
            {"g": new.id})).mappings().one()

    # durable identity: EXACT for both spec bytes and the derived payload
    assert new_row["workflow_spec_json"] == src_row["workflow_spec_json"]
    assert new_row["workflow_spec_hash"] == src_row["workflow_spec_hash"]
    assert await _siblings(engine, new.id) == await _siblings(engine, gen.id)

    src_up, new_up = _Recording(), _Recording()
    manifest_v3 = parse_manifest_v3(prod.production_manifest_v3())
    for generation_id, uploader in ((gen.id, src_up), (new.id, new_up)):
        async with factory() as session:
            verified = await execute_schema3_derived_inputs(
                session, BlobStore(settings), generation_id=generation_id,
                attempt_id="11111111-1111-4111-8111-111111111115",
                workflow_spec=json.loads(src_row["workflow_spec_json"]),
                manifest_v3=manifest_v3, client=uploader)
        assert [v.blob_hash for v in verified] == \
            [r["blob_hash"] for r in await _siblings(engine, gen.id)]

    # transport identity: DIFFERENT by construction (attempt-scoped
    # namespaces), while the uploaded BYTES are the exact retained Blobs
    src_names = {(f, s) for f, s, _ in src_up.uploads}
    new_names = {(f, s) for f, s, _ in new_up.uploads}
    assert src_names and new_names
    assert not (src_names & new_names), (
        "rerun transport references should be attempt-scoped, not "
        "shared historical identity")
    # per-stream frame uploads concatenate to the EXACT retained Blob
    # bytes (frame splitting never re-encodes)
    blob_bytes = {r["blob_hash"]: BlobStore(settings).path_for_hash(
        r["blob_hash"]).read_bytes() for r in await _siblings(engine, gen.id)}
    for uploads in (src_up.uploads, new_up.uploads):
        by_stream: dict[str, list[bytes]] = {}
        for filename, _, data in uploads:
            stream = filename.rsplit("_", 1)[0]  # input_key + blob prefix
            by_stream.setdefault(stream, []).append(data)
        assert len(by_stream) == 3
        for key, parts in by_stream.items():
            joined = b"".join(parts)
            assert joined in blob_bytes.values(), (
                f"stream {key} uploads are not the exact retained bytes")


async def test_same_generation_attempts_get_isolated_transport(
        factory, engine, settings, tmp_path):
    """E-106 B4 / R4 §2.4: TWO EXECUTION ATTEMPTS OF THE SAME GENERATION
    receive disjoint attempt-scoped upload namespaces while every durable
    identity stays identical — attempt locality is not merely
    generation locality."""
    from soloring.assets.blob_store import BlobStore
    from soloring.spatial.package3 import parse_manifest_v3
    from soloring.spatial import production_package as prod
    from soloring.spatial.worker_inputs import execute_schema3_derived_inputs

    class _Rec:
        def __init__(self) -> None:
            self.uploads: list[tuple[str, str, bytes]] = []

        async def upload(self, *, source_path, filename, subfolder):
            data = source_path.read_bytes()
            self.uploads.append((filename, subfolder, data))
            return filename, subfolder

        async def upload_bytes(self, *, data, filename, subfolder):
            self.uploads.append((filename, subfolder, data))
            return filename, subfolder

    gen, _, _ = await _terminal_generation(
        factory, engine, settings, tmp_path, staged=2)
    sib = await _siblings(engine, gen.id)
    spec = await _spec(engine, gen.id)
    manifest_v3 = parse_manifest_v3(prod.production_manifest_v3())

    attempt_a = "aaaaaaaa-0000-4000-8000-00000000000a"
    attempt_b = "bbbbbbbb-0000-4000-8000-00000000000b"
    ups = {}
    for label, attempt in (("a", attempt_a), ("b", attempt_b)):
        recorder = _Rec()
        async with factory() as session:
            verified = await execute_schema3_derived_inputs(
                session, BlobStore(settings), generation_id=gen.id,
                attempt_id=attempt, workflow_spec=spec,
                manifest_v3=manifest_v3, client=recorder)
        ups[label] = recorder.uploads
        assert [v.blob_hash for v in verified] == \
            [r["blob_hash"] for r in sib]

    subs_a = {sub for _, sub, _ in ups["a"]}
    subs_b = {sub for _, sub, _ in ups["b"]}
    assert subs_a and subs_b
    assert not (subs_a & subs_b), (
        "attempts of the SAME generation must not share a transport "
        "namespace")
    assert all(sub.startswith(f"soloring_gen_{gen.id}_att_")
               for sub in subs_a | subs_b)
    # identical durable inputs: same frame sets, byte-for-byte
    assert sorted(f for f, _, _ in ups["a"]) == \
        sorted(f for f, _, _ in ups["b"])
    assert sorted(d for _, _, d in ups["a"]) == \
        sorted(d for _, _, d in ups["b"])


# ------------- E-106 round-2: transport namespace details (B4) -----------

async def test_same_prefix_attempt_ids_get_distinct_namespaces(
        factory, engine, settings, tmp_path):
    """Two attempt IDs sharing their FIRST EIGHT characters receive
    distinct transport namespaces (full-identity attempt_namespace,
    not a truncated prefix)."""
    from soloring.assets.blob_store import BlobStore
    from soloring.executors.comfy.input_materializer import attempt_namespace
    from soloring.spatial.package3 import parse_manifest_v3
    from soloring.spatial import production_package as prod
    from soloring.spatial.worker_inputs import execute_schema3_derived_inputs

    class _Rec:
        def __init__(self) -> None:
            self.subs: set[str] = set()

        async def upload(self, *, source_path, filename, subfolder):
            self.subs.add(subfolder)
            return filename, subfolder

        async def upload_bytes(self, *, data, filename, subfolder):
            self.subs.add(subfolder)
            return filename, subfolder

    gen, _, _ = await _terminal_generation(
        factory, engine, settings, tmp_path, staged=1)
    spec = await _spec(engine, gen.id)
    manifest_v3 = parse_manifest_v3(prod.production_manifest_v3())
    shared = "aaaaaaaa-bbbb-4bbb-8bbb-"
    attempts = [shared + "00000000000a", shared + "00000000000b"]
    assert attempts[0][:8] == attempts[1][:8]
    subs = set()
    for attempt in attempts:
        rec = _Rec()
        async with factory() as session:
            await execute_schema3_derived_inputs(
                session, BlobStore(settings), generation_id=gen.id,
                attempt_id=attempt, workflow_spec=spec,
                manifest_v3=manifest_v3, client=rec)
        subs |= rec.subs
    assert len(subs) == 2, "same-prefix attempts must not share a namespace"
    assert all(sub.startswith(f"soloring_gen_{gen.id}_att_")
               for sub in subs)
    # the full-identity primitive itself distinguishes them
    assert (attempt_namespace(gen.id, attempts[0])
            != attempt_namespace(gen.id, attempts[1]))


async def test_wrong_returned_subfolder_fails_closed(
        factory, engine, settings, tmp_path):
    """A hostile/incorrect upload response escaping the requested
    attempt namespace is rejected by the predecessor
    validate_returned_reference before it becomes a Comfy reference."""
    from soloring.assets.blob_store import BlobStore
    from soloring.errors import SoloRingError
    from soloring.spatial.package3 import parse_manifest_v3
    from soloring.spatial import production_package as prod
    from soloring.spatial.worker_inputs import execute_schema3_derived_inputs

    class _Hostile:
        async def upload(self, *, source_path, filename, subfolder):
            return filename, "elsewhere"  # escapes the namespace

        async def upload_bytes(self, *, data, filename, subfolder):
            return filename, "elsewhere"

    gen, _, _ = await _terminal_generation(
        factory, engine, settings, tmp_path, staged=1)
    spec = await _spec(engine, gen.id)
    async with factory() as session:
        with pytest.raises(SoloRingError) as ei:
            await execute_schema3_derived_inputs(
                session, BlobStore(settings), generation_id=gen.id,
                attempt_id="11111111-1111-4111-8111-111111111116",
                workflow_spec=spec,
                manifest_v3=parse_manifest_v3(
                    prod.production_manifest_v3()),
                client=_Hostile())
    from soloring.errors import ErrorCode as _EC

    assert ei.value.code == _EC.COMFY_INPUT_REFERENCE_INVALID
