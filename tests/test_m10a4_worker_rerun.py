"""M10A-4 DB-backed tests — worker historical transport, Exact Rerun derived
copy + query spy, and the chained 0011→0010→0009 downgrade proof."""
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from soloring.assets.blob_store import BlobStore
from soloring.spatial import error_codes as ec
from soloring.spatial.package3 import parse_manifest_v3
from soloring.spatial.spec3 import (
    build_spatial_realization_block,
    compose_workflow_spec_v3,
)
from soloring.spatial.worker_inputs import (
    current_m10_table_names,
    load_verified_derived_inputs,
)

BASE_DIR = Path(__file__).resolve().parents[1]
HEX = "ab" * 32


async def _mkblob(store: BlobStore, content: bytes) -> str:
    import tempfile
    h = hashlib.sha256(content).hexdigest()
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(content)
    assert await store.place(h, Path(f.name))
    return h


def _spec_json(blob_hash: str, continuity: str) -> str:
    from soloring.domain.canonical import canonical_json_str
    from soloring.spatial.derived import parse_derived_spec
    spec = {
        "schema_version": 1,
        "artifact_kind": "boxdepth_control_video",
        "artifact_schema_version": 1,
        "source": {"spatial_continuity_schema_version": 1,
                   "spatial_continuity_hash": continuity},
        "derivation": {"algorithm_id": "soloring.boxdepth.rasterizer",
                       "algorithm_version": "1.0.0",
                       "parameters": {"scope": "world", "entity_id": None,
                                      "placement_source_kind": None,
                                      "placement_source_id": None,
                                      "proxy_geometry": None,
                                      "sampling": {"frames": 17},
                                      "projection": {"width": 832}}},
        "output_contract": {"media_type": "application/x-npy",
                            "encoding": "npy-1.0", "width": 832,
                            "height": 480, "frame_count": 17,
                            "time_base_num": 1, "time_base_den": 17},
    }
    # canonical bytes come from the frozen parser/model dump, never a
    # hand-rolled second serializer
    return canonical_json_str(
        parse_derived_spec(spec).model_dump(mode="json", exclude_none=False))


def _fp_json() -> str:
    from soloring.domain.canonical import canonical_json_str
    from soloring.spatial.derived import parse_runtime_fingerprint
    fp = {
        "schema_version": 1,
        "materializer": {"algorithm_id": "soloring.boxdepth.rasterizer",
                         "algorithm_version": "1.0.0",
                         "implementation_sha256": "c" * 64},
        "runtime": {"python": "3.12", "numpy": "2.5",
                    "pillow_png_encoder": "12.3.0", "encoder_identity":{"pillow_release":"10.0.0","pillow_native_module":"_imaging.cp312-win_amd64.pyd","pillow_native_module_sha256":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd","python_implementation":"cpython","python_abi_tag":"","platform":"win-amd64","zlib_compile_version":"1.3.1","zlib_runtime_version":"1.3.1"},
                    "platform_contract": "win-cpu"},
        "external_components": [],
    }
    return canonical_json_str(
        parse_runtime_fingerprint(fp).model_dump(mode="json",
                                                 exclude_none=False))


async def _seed_spatial_generation(factory, engine, settings, continuity="9" * 64):
    """Minimal populations: project/shot/shot-revision(schema5 rows) +
    generation + blob + provenance + sibling derived inputs. Returns ids."""
    import uuid
    store = BlobStore(settings)
    blob = await _mkblob(store, b"derived-bytes-v1")
    pid, loc, locrev, ent, entrev = (str(uuid.uuid4()) for _ in range(5))
    shot_id, srev, gen, art = (str(uuid.uuid4()) for _ in range(4))
    state_id, world_id, wrev = (str(uuid.uuid4()) for _ in range(3))
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO projects (id, name, created_at, updated_at) "
                "VALUES (:p, 'P', 't', 't')"), {"p": pid})
            await session.execute(text(
                "INSERT INTO creative_entities (id, project_id, kind, name, "
                "created_at, updated_at) VALUES "
                "(:e, :p, 'location', 'L', 't', 't')"), {"e": loc, "p": pid})
            await session.execute(text(
                "INSERT INTO creative_entities (id, project_id, kind, name, "
                "created_at, updated_at) VALUES "
                "(:e, :p, 'character', 'C', 't', 't')"), {"e": ent, "p": pid})
            for eid, rid in ((loc, locrev), (ent, entrev)):
                await session.execute(text(
                    "INSERT INTO entity_revisions (id, entity_id, "
                    "revision_number, schema_version, spec_hash, "
                    "created_at) VALUES "
                    "(:r, :e, 1, 1, :h, 't')"),
                {"r": rid, "e": eid, "h": HEX})
            await session.execute(text(
                "INSERT INTO spatial_worlds (id, project_id, "
                "location_entity_id, key, name, requirement, created_at, "
                "updated_at) VALUES (:w, :p, :loc, 'lobby', 'L', 'required', "
                "'t', 't')"),
                {"w": world_id, "p": pid, "loc": loc})
            await session.execute(text(
                "INSERT INTO spatial_world_states (id, spatial_world_id, "
                "location_entity_revision_id, created_at, updated_at) VALUES "
                "(:s, :w, :lr, 't', 't')"),
                {"s": state_id, "w": world_id, "lr": locrev})
            snap = "{}"
            await session.execute(text(
                "INSERT INTO spatial_world_revisions (id, "
                "spatial_world_state_id, revision_number, snapshot_json, "
                "snapshot_hash, created_at) VALUES (:r, :s, 1, :j, :h, 't')"),
                {"r": wrev, "s": state_id, "j": snap,
                 "h": hashlib.sha256(snap.encode()).hexdigest()})
            await session.execute(text(
                "INSERT INTO shots (id, project_id, shot_number, subject, "
                "created_at, updated_at) VALUES (:sh, :p, 1, 'S', 't', 't')"),
                {"sh": shot_id, "p": pid})
            await session.execute(text(
                "INSERT INTO shot_revisions (id, shot_id, revision_number, "
                "snapshot_json, snapshot_hash, created_at) VALUES "
                "(:r, :sh, 1, :snap, :h, 't')"),
                {"r": srev, "sh": shot_id, "snap": "{\"schema_version\":5}",
                 "h": HEX})
            await session.execute(text(
                "INSERT INTO shot_revision_spatial_worlds ("
                "shot_revision_id, spatial_continuity_hash, spatial_world_id,"
                " spatial_world_state_id, spatial_world_revision_id, "
                "spatial_world_revision_hash, location_entity_id, "
                "location_entity_revision_id, requirement) VALUES "
                "(:r, :c, :w, :s, :wr, :wh, :loc, :lr, 'required')"),
                {"r": srev, "c": continuity, "w": world_id, "s": state_id,
                 "wr": wrev, "wh": HEX, "loc": loc, "lr": locrev})
            await session.execute(text(
                "INSERT INTO blobs (hash, path, size_bytes, created_at) "
                "VALUES (:h, :path, 16, 't')"),
                {"h": blob, "path": str(store.path_for_hash(blob))})
            await session.execute(text(
                "INSERT INTO derived_spatial_artifacts (id, project_id, "
                "spec_schema_version, spec_json, spec_hash, "
                "spatial_continuity_schema_version, spatial_continuity_hash, "
                "artifact_kind, artifact_schema_version, algorithm_id, "
                "algorithm_version, runtime_fingerprint_json, "
                "runtime_fingerprint_hash, determinism_class, blob_hash, "
                "media_type, created_at) VALUES "
                "(:id, :p, 1, :sj, :sh, 1, :c, 'boxdepth_control_video', 1, "
                "'soloring.boxdepth.rasterizer', '1.0.0', :fj, :fh, 'D0', "
                ":bh, 'application/x-npy', 't')"),
                {"id": art, "p": pid, "sj": _spec_json(blob, continuity),
                 "sh": hashlib.sha256(
                     _spec_json(blob, continuity).encode()).hexdigest(),
                 "c": continuity, "fj": _fp_json(),
                 "fh": hashlib.sha256(_fp_json().encode()).hexdigest(),
                 "bh": blob})
            await session.execute(text(
                "INSERT INTO generations (id, shot_id, shot_revision_id, "
                "status, operation, executor, workflow_id, workflow_version, "
                "workflow_template_hash, manifest_hash, compiled_prompt, "
                "prompt_compiler_version, parameters_json, "
                "workflow_spec_json, workflow_spec_hash, created_at, "
                "updated_at, generation_number) VALUES "
                "(:g, :sh, :r, 'succeeded', 'generate', 'comfy', 'wf', 1, "
                ":th, :mh, 'p', 'v1', '{}', :sj, :sh2, 't', 't', 1)"),
                {"g": gen, "sh": shot_id, "r": srev, "th": HEX, "mh": HEX,
                 "sj": json.dumps({"schema_version": 3}),
                 "sh2": hashlib.sha256(
                     json.dumps({"schema_version": 3}).encode()).hexdigest()})
            await session.execute(text(
                "INSERT INTO generation_derived_spatial_inputs ("
                "generation_id, input_key, position, artifact_role, "
                "derived_spatial_artifact_id, blob_hash) VALUES "
                "(:g, 'world_depth', 0, 'spatial.world_depth', :a, :bh)"),
                {"g": gen, "a": art, "bh": blob})
    return {"generation_id": gen, "blob": blob, "continuity": continuity,
            "artifact": art, "shot_id": shot_id, "project": pid,
            "spec_hash": hashlib.sha256(
                _spec_json(blob, continuity).encode()).hexdigest(),
            "runtime_hash": hashlib.sha256(
                _fp_json().encode()).hexdigest()}


def _manifest_doc():
    return parse_manifest_v3({
        "schema_version": "3", "version": 1, "workflow_id": "wf",
        "inputs": {"world_depth": {}}, "parameters": {}, "outputs": {},
        "spatial_bindings": {
            "world_depth": {"artifact_role": "spatial.world_depth",
                            "node": "7", "field": "control_images",
                            "format": "soloring.spatial.v1"}}})


def _spec(continuity, ids=None):
    """Build a schema-3 spec whose derived entries carry the REAL seeded
    identities when ``ids`` is supplied (the M10E worker cross-checks
    spec ↔ sibling ↔ provenance; synthetic placeholders no longer pass)."""
    artifact = (ids or {}).get("artifact", "x")
    blob = (ids or {}).get("blob", HEX)
    spec_hash = (ids or {}).get("spec_hash", HEX)
    runtime_hash = (ids or {}).get("runtime_hash", HEX)
    return compose_workflow_spec_v3(
        {"prompt": "p"},
        model={"id": "m", "version": "1", "execution_model_fingerprint_hash": HEX},
        realization=None,
        spatial_realization=build_spatial_realization_block(
            spatial_continuity_hash=continuity,
            realization_profile_hash=HEX,
            derived_artifacts=[{
                "input_key": "world_depth", "position": 0,
                "artifact_role": "spatial.world_depth",
                "derived_spatial_artifact_id": artifact,
                "spec_hash": spec_hash, "runtime_fingerprint_hash": runtime_hash,
                "blob_hash": blob}]))


# ---------------------------------------------------------------- worker ---

async def test_worker_transport_valid(factory, engine, settings):
    ids = await _seed_spatial_generation(factory, engine, settings)
    async with factory() as session:
        got = await load_verified_derived_inputs(
            session, BlobStore(settings), generation_id=ids["generation_id"],
            workflow_spec=_spec(ids["continuity"], ids),
            manifest_v3=_manifest_doc())
    assert len(got) == 1
    assert got[0].node == "7" and got[0].field == "control_images"
    assert got[0].input_key == "world_depth"


async def test_worker_missing_blob_fails(factory, engine, settings):
    ids = await _seed_spatial_generation(factory, engine, settings)
    BlobStore(settings).path_for_hash(ids["blob"]).unlink()
    async with factory() as session:
        from soloring.errors import SoloRingError
        with pytest.raises(SoloRingError) as ei:
            await load_verified_derived_inputs(
                session, BlobStore(settings),
                generation_id=ids["generation_id"],
                workflow_spec=_spec(ids["continuity"], ids),
                manifest_v3=_manifest_doc())
    assert ei.value.code == ec.DERIVED_SPATIAL_BLOB_MISSING


async def test_worker_corrupt_blob_fails(factory, engine, settings):
    ids = await _seed_spatial_generation(factory, engine, settings)
    BlobStore(settings).path_for_hash(ids["blob"]).write_bytes(b"tampered!")
    async with factory() as session:
        from soloring.errors import SoloRingError
        with pytest.raises(SoloRingError) as ei:
            await load_verified_derived_inputs(
                session, BlobStore(settings),
                generation_id=ids["generation_id"],
                workflow_spec=_spec(ids["continuity"], ids),
                manifest_v3=_manifest_doc())
    assert ei.value.code == ec.DERIVED_SPATIAL_BLOB_CORRUPT


async def test_worker_provenance_mismatch_fails(factory, engine, settings):
    ids = await _seed_spatial_generation(factory, engine, settings)
    async with factory() as session:
        await session.execute(text(
            "UPDATE derived_spatial_artifacts SET spatial_continuity_hash = :nh "
            "WHERE id = :a"), {"nh": "ef" * 32, "a": ids["artifact"]})
        await session.commit()
    async with factory() as session:
        from soloring.errors import SoloRingError
        with pytest.raises(SoloRingError) as ei:
            await load_verified_derived_inputs(
                session, BlobStore(settings),
                generation_id=ids["generation_id"],
                workflow_spec=_spec(ids["continuity"], ids),
                manifest_v3=_manifest_doc())
    assert ei.value.code == ec.DERIVED_SPATIAL_PROVENANCE_MISMATCH


async def test_worker_wrong_binding_fails(factory, engine, settings):
    ids = await _seed_spatial_generation(factory, engine, settings)
    bad = parse_manifest_v3({
        "schema_version": "3", "version": 1, "workflow_id": "wf",
        "inputs": {"other_key": {}}, "parameters": {}, "outputs": {},
        "spatial_bindings": {
            "other_key": {"artifact_role": "spatial.world_depth",
                          "node": "7", "field": "control_images",
                          "format": "soloring.spatial.v1"}}})
    async with factory() as session:
        from soloring.errors import SoloRingError
        with pytest.raises(SoloRingError) as ei:
            await load_verified_derived_inputs(
                session, BlobStore(settings),
                generation_id=ids["generation_id"],
                workflow_spec=_spec(ids["continuity"], ids), manifest_v3=bad)
    assert ei.value.code == ec.DERIVED_SPATIAL_BINDING_INVALID


# ------------------------------------------------------------------ rerun ---

async def test_rerun_copies_derived_rows_verbatim(factory, engine, settings):
    from soloring.generation import rerun
    ids = await _seed_spatial_generation(factory, engine, settings)
    async with factory() as session:
        await session.execute(text(
            "UPDATE generations SET status='succeeded', "
            "completed_at='t' WHERE id=:g"), {"g": ids["generation_id"]})
        await session.commit()
    new_id = await rerun._create_rerun_fenced(engine, ids["generation_id"])
    async with factory() as session:
        rows = (await session.execute(text(
            "SELECT input_key, position, artifact_role, "
            "derived_spatial_artifact_id, blob_hash FROM "
            "generation_derived_spatial_inputs WHERE generation_id=:g "
            "ORDER BY position"), {"g": new_id})).mappings().all()
        src = (await session.execute(text(
            "SELECT input_key, position, artifact_role, "
            "derived_spatial_artifact_id, blob_hash FROM "
            "generation_derived_spatial_inputs WHERE generation_id=:g "
            "ORDER BY position"), {"g": ids["generation_id"]})).mappings().all()
    assert [dict(r) for r in rows] == [dict(r) for r in src]


async def test_rerun_zero_current_m10_reads(factory, engine, settings):
    """Query spy: rerun reads no current M10 authority table."""
    from soloring.generation import rerun
    ids = await _seed_spatial_generation(factory, engine, settings)
    async with factory() as session:
        await session.execute(text(
            "UPDATE generations SET status='succeeded', completed_at='t' "
            "WHERE id=:g"), {"g": ids["generation_id"]})
        await session.commit()

    seen: list[str] = []
    from sqlalchemy import event
    forbidden = set(current_m10_table_names())

    def _spy(conn, cursor, statement, parameters, context, executemany=False):
        stmt = statement.lower()
        for table in forbidden:
            if table in stmt and ("select" in stmt or "insert" in stmt
                                  or "update" in stmt):
                seen.append(table)

    # positive control: the spy detects a forbidden current-table read
    sync_spy_called: list[str] = []
    eng = engine.sync_engine
    event.listen(eng, "before_cursor_execute", _spy)
    try:
        async with factory() as session:
            await session.execute(text("SELECT 1 FROM spatial_worlds"))
        assert seen, "spy positive control failed"
        seen.clear()
        await rerun._create_rerun_fenced(engine, ids["generation_id"])
        hits = [t for t in seen if t in forbidden]
        assert hits == [], f"rerun read current M10 tables: {hits}"
    finally:
        event.remove(eng, "before_cursor_execute", _spy)
        sync_spy_called.clear()


# ------------------------------------------------------- downgrade chain ----

def _cfg() -> Config:
    cfg = Config(str(BASE_DIR / "server" / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "server" / "alembic"))
    return cfg


def _point_at(data_dir: Path, monkeypatch) -> Path:
    import soloring.settings as settings_mod
    monkeypatch.setenv("SOLORING_DATA_DIR", str(data_dir))
    monkeypatch.setattr(settings_mod, "_settings", None)
    return data_dir / "soloring.db"


def test_chained_downgrade_0011_0010_0009_empty(tmp_path, monkeypatch):
    db = _point_at(tmp_path, monkeypatch)
    command.upgrade(_cfg(), "head")
    command.downgrade(_cfg(), "0010_m10_spatial_cinematic_continuity")
    command.downgrade(_cfg(), "0009_m8_visual_identity")
    con = sqlite3.connect(db)
    ver = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    left = con.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND "
        "(name LIKE 'spatial_%' OR name LIKE 'shot_revision_spatial%' OR "
        "name LIKE 'shot_spatial%' OR name LIKE 'derived_spatial%' OR "
        "name LIKE 'generation_derived%')").fetchone()[0]
    con.close()
    assert ver == "0009_m8_visual_identity"
    assert left == 0


def test_chained_downgrade_populated_0011_refuses_before_ddl(
        tmp_path, monkeypatch):
    db = _point_at(tmp_path, monkeypatch)
    command.upgrade(_cfg(), "head")
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys=OFF")
    con.execute("INSERT INTO derived_spatial_artifacts (id, project_id, "
                "spec_schema_version, spec_json, spec_hash, "
                "spatial_continuity_schema_version, spatial_continuity_hash, "
                "artifact_kind, artifact_schema_version, algorithm_id, "
                "algorithm_version, runtime_fingerprint_json, "
                "runtime_fingerprint_hash, determinism_class, blob_hash, "
                "media_type, created_at) VALUES ('a','p',1,'{}','" + "x"*64 +
                "',1,'" + "y"*64 + "','k',1,'alg','1','{}','" + "z"*64 +
                "','D0','" + "b"*64 + "','m','t')")
    con.commit()
    con.close()
    with pytest.raises(RuntimeError, match="refused"):
        command.downgrade(_cfg(), "0010_m10_spatial_cinematic_continuity")
    con = sqlite3.connect(db)
    ver = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    n = con.execute("SELECT COUNT(*) FROM derived_spatial_artifacts"
                    ).fetchone()[0]
    con.close()
    assert ver == "0011_m10_derived_spatial_execution"  # nothing dropped
    assert n == 1


def test_chained_downgrade_v3_spec_refuses(tmp_path, monkeypatch):
    db = _point_at(tmp_path, monkeypatch)
    command.upgrade(_cfg(), "head")
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys=OFF")
    con.execute("INSERT INTO generations (id, shot_id, shot_revision_id, "
                "status, operation, executor, workflow_id, workflow_version, "
                "workflow_template_hash, manifest_hash, compiled_prompt, "
                "prompt_compiler_version, parameters_json, "
                "workflow_spec_json, workflow_spec_hash, created_at, "
                "updated_at, generation_number) VALUES "
                "('g','s','r','queued','generate','comfy','wf',1,'" + "h"*64 +
                "','" + "h"*64 + "','p','v','{}',?, '" + "h"*64 +
                "','t','t',1)",
                (json.dumps({"schema_version": 3}),))
    con.commit()
    con.close()
    with pytest.raises(RuntimeError, match="refused"):
        command.downgrade(_cfg(), "0010_m10_spatial_cinematic_continuity")


def test_chained_downgrade_after_0011_removed_empty_0010_succeeds(
        tmp_path, monkeypatch):
    db = _point_at(tmp_path, monkeypatch)
    command.upgrade(_cfg(), "head")
    command.downgrade(_cfg(), "0010_m10_spatial_cinematic_continuity")
    command.downgrade(_cfg(), "0009_m8_visual_identity")
    con = sqlite3.connect(db)
    ver = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    con.close()
    assert ver == "0009_m8_visual_identity"
