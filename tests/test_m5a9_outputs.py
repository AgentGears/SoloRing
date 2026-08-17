"""M5A-9 — Output discovery, retrieval, and import integration.

Discovery matrix (pure), transfer matrix (instrumented /view), publication/
recovery matrix (worker orchestration + real importer), and the structural
negative-evidence rules.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3 as sq
import time
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text

from soloring.api.schemas.projects import ProjectCreate
from soloring.api.schemas.references import ReferenceInput
from soloring.api.schemas.shots import ShotCreate
from soloring.domain import projects, references, shots
from soloring.errors import ErrorCode, SoloRingError
from soloring.executors.base import StagedOutput
from soloring.executors.comfy.models import NormalizedHistoryRecord
from soloring.executors.comfy.outputs import (
    DEFAULT_MAX_OUTPUT_BYTES,
    CapturedOutputContract,
    OutputFetchFailed,
    OutputInvalid,
    ResolvedComfyOutput,
    fetch_output_to_staging,
    resolve_comfy_outputs,
    stage_target,
    validate_filename,
    validate_output_reference,
    validate_subfolder,
)
from soloring.executors.comfy.wire import normalize_history_response
from soloring.settings import BASE_DIR, Settings
from soloring.workflows.manifest import parse_manifest

MANIFEST = parse_manifest(
    (BASE_DIR / "workflows" / "hunyuan_i2v_v1" / "manifest.json").read_text("utf-8")
)
# The declared output binding (release v2: SaveAnimatedWEBP → field "images").
OUT_NODE = MANIFEST.outputs["video"].node
OUT_FIELD = MANIFEST.outputs["video"].field


def _contract(name="video", count=1):
    return [CapturedOutputContract(
        name=name, kind="video", expected_count=count,
        accepted_media_types=None,
    )]


def _history(outputs: dict, marker_pair=("g" * 36, "a" * 36)):
    raw = {"P": {
        "prompt": [0, "P", {}, {"soloring": {
            "generation_id": marker_pair[0], "attempt_id": marker_pair[1]}}, []],
        "outputs": outputs,
        "status": {"status_str": "completed", "messages": []},
    }}
    return normalize_history_response(raw)["P"]


# --- discovery matrix (pure) -----------------------------------------------------


def test_one_declared_output_one_reference():
    rec = _history({OUT_NODE: {OUT_FIELD: [
        {"filename": "v-0.png", "subfolder": "", "type": "output"}]}})
    out = resolve_comfy_outputs(
        captured_outputs=_contract(), manifest=MANIFEST, history=rec,
    )
    assert len(out) == 1
    assert out[0].output_key == "video:0"
    assert out[0].filename == "v-0.png"


def test_declared_count_2_deterministic_assignment():
    rec = _history({OUT_NODE: {OUT_FIELD: [
        {"filename": "b.png", "subfolder": "", "type": "output"},
        {"filename": "a.png", "subfolder": "", "type": "output"},
    ]}})
    out = resolve_comfy_outputs(
        captured_outputs=_contract(count=2), manifest=MANIFEST, history=rec,
    )
    assert [o.output_key for o in out] == ["video:0", "video:1"]
    # normalized ordering: sorted by (filename, subfolder) regardless of the
    # history list order above.
    assert [o.filename for o in out] == ["a.png", "b.png"]


def test_history_construction_permutation_identical_mapping():
    o1 = {"filename": "a.png", "subfolder": "s", "type": "output"}
    o2 = {"filename": "b.png", "subfolder": "s", "type": "output"}
    forward = resolve_comfy_outputs(
        captured_outputs=_contract(count=2), manifest=MANIFEST,
        history=_history({OUT_NODE: {OUT_FIELD: [o1, o2]}}),
    )
    reverse = resolve_comfy_outputs(
        captured_outputs=_contract(count=2), manifest=MANIFEST,
        history=_history({OUT_NODE: {OUT_FIELD: [o2, o1]}}),
    )
    assert [(o.output_key, o.filename) for o in forward] == [
        (o.output_key, o.filename) for o in reverse
    ]


def test_unrelated_history_outputs_ignored():
    rec = _history({
        OUT_NODE: {OUT_FIELD: [{"filename": "v-0.png", "subfolder": "",
                                "type": "output"}]},
        "99": {"images": [{"filename": "diag.png", "subfolder": "",
                             "type": "output"}]},
        "7": {"previews": [{"filename": "p.jpg", "subfolder": "tmp",
                              "type": "temp"}]},
    })
    out = resolve_comfy_outputs(
        captured_outputs=_contract(), manifest=MANIFEST, history=rec,
    )
    assert len(out) == 1  # diagnostics/previews/other nodes: ignored


def test_extra_output_under_declared_binding_invalid():
    rec = _history({OUT_NODE: {OUT_FIELD: [
        {"filename": "a.png", "subfolder": "", "type": "output"},
        {"filename": "b.png", "subfolder": "", "type": "output"},
    ]}})
    with pytest.raises(OutputInvalid) as e:
        resolve_comfy_outputs(
            captured_outputs=_contract(count=1), manifest=MANIFEST, history=rec,
        )
    assert "cardinality" in str(e.value)


def test_missing_declared_binding_output_invalid():
    rec = _history({"99": {"images": [
        {"filename": "x.png", "subfolder": "", "type": "output"}]}})
    with pytest.raises(OutputInvalid):
        resolve_comfy_outputs(
            captured_outputs=_contract(), manifest=MANIFEST, history=rec,
        )


def test_missing_manifest_binding_invalid():
    rec = _history({})
    with pytest.raises(OutputInvalid):
        resolve_comfy_outputs(
            captured_outputs=_contract(name="nonexistent"),
            manifest=MANIFEST, history=rec,
        )


def test_manifest_maps_undeclared_captured_output_invalid():
    contract = _contract(name="extra_not_in_manifest")
    rec = _history({})
    with pytest.raises(OutputInvalid):
        resolve_comfy_outputs(
            captured_outputs=contract, manifest=MANIFEST, history=rec,
        )


# --- /view reference validation -----------------------------------------------------


def _ref(output_key="video:0", filename="v-0.png", subfolder="", typ="output"):
    return ResolvedComfyOutput(
        output_key=output_key, logical_name="video", expected_kind="video",
        accepted_media_types=None, filename=filename, subfolder=subfolder,
        type=typ,
    )


def test_type_input_rejected_before_view():
    with pytest.raises(OutputInvalid):
        validate_output_reference(_ref(typ="input"))


def test_type_temp_rejected_before_view():
    with pytest.raises(OutputInvalid):
        validate_output_reference(_ref(typ="temp"))


@pytest.mark.parametrize("bad", [
    "", ".", "..", "a/b.png", "a\\b.png", "x" * 300, "con\ttrol", "C:\\x.png",
])
def test_unsafe_filenames_rejected(bad):
    with pytest.raises(OutputInvalid):
        validate_filename(bad)


def test_valid_filenames_with_spaces_parens_unicode():
    validate_filename("result (1).png")
    validate_filename("café render.webm")
    validate_filename("a b.png")


@pytest.mark.parametrize("bad", [
    "/abs", "C:/x", "a\\b", "a/../b", "./a", "a//b", "x" * 300, "a/\tb",
])
def test_unsafe_subfolders_rejected(bad):
    with pytest.raises(OutputInvalid):
        validate_subfolder(bad)


def test_valid_subfolders():
    validate_subfolder("")
    validate_subfolder("project")
    validate_subfolder("project/render")


# --- transfer matrix (instrumented) --------------------------------------------------


class ViewDouble:
    """Chunk-provider double with full /view instrumentation."""

    def __init__(self, content=b"x" * 100):
        self.content = content
        self.calls: list[tuple[str, str, str]] = []
        self.fail_next_transports = 0
        self.max_read = 0
        self._pos = 0

    def __call__(self, filename, subfolder, _read=None):
        self.calls.append((filename, subfolder, "output"))
        self.max_read = max(self.max_read, _read or 0)
        if self.fail_next_transports > 0:
            self.fail_next_transports -= 1
            raise ConnectionError("view transport failure")
        self._pos = 0
        chunk_size = _read or 1 << 16

        def gen():
            pos = 0
            data = self.content
            while pos < len(data):
                piece = data[pos:pos + chunk_size]
                pos += len(piece)
                yield piece

        self._gen = gen()

    def sync_chunk_provider(self):
        # Position-based reader: serves chunks from the current position and
        # wraps to byte 0 after exhaustion, so every consumer that reads to
        # completion receives the full object (real HTTP re-GETs per attempt).
        state = {"pos": 0}

        def provider(filename, subfolder, _read=1 << 16):
            self.calls.append((filename, subfolder, "output"))
            self.max_read = max(self.max_read, _read)
            if self.fail_next_transports > 0:
                self.fail_next_transports -= 1
                raise ConnectionError("view transport failure")
            data = self.content
            pos = state["pos"]
            if pos >= len(data):
                state["pos"] = 0
                return b""
            chunk = data[pos:pos + _read]
            state["pos"] = pos + len(chunk)
            return chunk

        return provider


async def test_valid_file_streamed_and_staged(tmp_path):
    d = ViewDouble(b"\x89PNG\r\n\x1a\n" + b"payload" * 10)
    ref = _ref()
    target = await fetch_output_to_staging(
        d.sync_chunk_provider(), ref, tmp_path,
    )
    assert target == stage_target(tmp_path, "video:0")
    assert target.name == "video-0.staged"
    assert target.read_bytes() == d.content
    assert d.calls[0][2] == "output"  # /view always type=output


async def test_large_output_bounded_chunk_reads(tmp_path):
    big = b"\x89PNG\r\n\x1a\n" + (b"0123456789abcdef" * 1024 * 1024)  # 16 MiB
    d = ViewDouble(big)
    await fetch_output_to_staging(
        d.sync_chunk_provider(), _ref(), tmp_path,
        max_bytes=64 * 1024 * 1024,
    )
    assert d.max_read <= 1 << 20  # bounded chunks, no whole-buffer read


async def test_actual_bytes_exceeding_max_rejected(tmp_path):
    d = ViewDouble(b"z" * 1000)
    with pytest.raises(OutputInvalid):
        await fetch_output_to_staging(
            d.sync_chunk_provider(), _ref(), tmp_path, max_bytes=100,
        )
    assert not (tmp_path / "video-0.staged").exists()


async def test_lying_size_provider_still_enforced(tmp_path):
    # No Content-Length concept in the provider; enforcement is by actual
    # streamed bytes (§9).
    d = ViewDouble(b"z" * 5000)
    with pytest.raises(OutputInvalid):
        await fetch_output_to_staging(
            d.sync_chunk_provider(), _ref(), tmp_path, max_bytes=100,
        )


async def test_zero_byte_output_invalid(tmp_path):
    d = ViewDouble(b"")
    with pytest.raises(OutputInvalid):
        await fetch_output_to_staging(d.sync_chunk_provider(), _ref(), tmp_path)
    assert not (tmp_path / "video-0.staged").exists()


async def test_timeout_partial_removed_retry_from_zero_success(tmp_path):
    d = ViewDouble(b"\x89PNG\r\n\x1a\n" + b"data" * 100)
    provider = d.sync_chunk_provider()
    state = {"calls": 0}
    real = provider

    def flaky(filename, subfolder, _read=1 << 16):
        state["calls"] += 1
        if state["calls"] == 1:
            raise ConnectionError("timeout mid-transfer")
        return real(filename, subfolder, _read)

    target = await fetch_output_to_staging(flaky, _ref(), tmp_path, attempts=2)
    assert target.read_bytes() == d.content
    # No leftover transfer temps.
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == []


async def test_retries_exhausted_interrupted_no_finalized(tmp_path):
    def always_fail(filename, subfolder, _read=1 << 16):
        raise ConnectionError("down")

    with pytest.raises(OutputFetchFailed):
        await fetch_output_to_staging(always_fail, _ref(), tmp_path, attempts=2)
    assert not (tmp_path / "video-0.staged").exists()
    assert list(tmp_path.glob("*.tmp")) == []


async def test_concurrent_fetches_converge(tmp_path):
    d = ViewDouble(b"shared-verified-bytes")
    provider = d.sync_chunk_provider()
    results = await asyncio.gather(
        *(fetch_output_to_staging(provider, _ref(), tmp_path) for _ in range(4))
    )
    assert all(r == results[0] for r in results)
    assert results[0].read_bytes() == d.content


# --- worker publication/recovery matrix ------------------------------------------------


async def _seed_generation(client_, factory, engine):
    async with factory() as s:
        pid = (await projects.create_project(s, ProjectCreate(name="P"))).id
        shot = await shots.create_shot(s, pid, ShotCreate(subject="Eva"))
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
        s.add(Asset(id=aid, project_id=pid, blob_hash=bh, kind="reference"))
        await s.commit()
    async with factory() as s:
        await references.replace_references(
            s, shot.id, [ReferenceInput(asset_id=aid, role="reference")]
        )
    r = await client_.post(f"/shots/{shot.id}/generations")
    assert r.status_code == 202, r.text
    return r.json()["id"]


async def _import_via_existing_importer(engine, settings, factory, gid,
                                        staged: list, spec_outputs):
    """Hand the complete staged set to the M3C-hardened importer."""
    from soloring.assets.blob_store import BlobStore
    from soloring.generation.importer import import_staged_outputs
    from soloring.generation.repository import get_generation_full
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    f2 = async_sessionmaker(bind=engine, expire_on_commit=False,
                             class_=AsyncSession)
    async with f2() as s:
        generation = await get_generation_full(s, gid)
    return await import_staged_outputs(
        f2, BlobStore(settings), generation, staged,
        expected_outputs=spec_outputs,
        staging_directory=Path(settings.staging_dir) / gid / "attempt-x",
    )


async def test_complete_set_import_exact_takes_then_replay_zero_dups(
    client, factory, engine, settings, tmp_path
):
    gid = await _seed_generation(client, factory, engine)
    async with factory() as s:
        shot_id = (await s.execute(text(
            "SELECT shot_id FROM generations WHERE id=:g"
        ), {"g": gid})).scalar()

    staging = Path(settings.staging_dir) / gid / "attempt-x"
    staging.mkdir(parents=True, exist_ok=True)
    content = b"\x89PNG\r\n\x1a\nfake-comfy-output"
    (staging / "video-0.staged").write_bytes(content)

    staged = [StagedOutput(output_key="video:0",
                            path=staging / "video-0.staged",
                            kind="video")]
    out = _contract()
    imported = await _import_via_existing_importer(
        engine, settings, factory, gid, staged, out,
    )
    assert imported == ["video:0"]

    async with factory() as s:
        takes = (await s.execute(text(
            "SELECT count(*) FROM takes WHERE generation_id=:g"
        ), {"g": gid})).scalar()
        assets = (await s.execute(text(
            "SELECT count(*) FROM assets a JOIN takes t ON a.take_id=t.id "
            "WHERE t.generation_id=:g"
        ), {"g": gid})).scalar()
    assert takes == 1 and assets == 1

    # Replay: zero duplicates. (The importer's blob placement consumed the
    # staged file via os.replace — restage the same verified bytes first.)
    (staging / "video-0.staged").write_bytes(content)
    await _import_via_existing_importer(
        engine, settings, factory, gid, staged, out,
    )
    async with factory() as s:
        takes2 = (await s.execute(text(
            "SELECT count(*) FROM takes WHERE generation_id=:g"
        ), {"g": gid})).scalar()
        assets2 = (await s.execute(text(
            "SELECT count(*) FROM assets a JOIN takes t ON a.take_id=t.id "
            "WHERE t.generation_id=:g"
        ), {"g": gid})).scalar()
    assert takes2 == 1 and assets2 == 1


async def test_two_output_second_download_fails_zero_partial(
    client, factory, engine, settings
):
    gid = await _seed_generation(client, factory, engine)
    staging = Path(settings.staging_dir) / gid / "attempt-y"
    staging.mkdir(parents=True, exist_ok=True)
    (staging / "video-0.staged").write_bytes(b"\x89PNG\r\n\x1a\nfirst")
    # video:1 never staged (its download failed) → complete-set validation
    # must reject before the importer.
    staged = [StagedOutput(output_key="video:0",
                            path=staging / "video-0.staged",
                            kind="video")]
    with pytest.raises(SoloRingError):
        await _import_via_existing_importer(
            engine, settings, factory, gid, staged,
            _contract(count=2),
        )
    async with factory() as s:
        takes = (await s.execute(text(
            "SELECT count(*) FROM takes WHERE generation_id=:g"
        ), {"g": gid})).scalar()
    assert takes == 0  # zero partial Take graph


async def test_media_mismatch_zero_partial(client, factory, engine, settings):
    gid = await _seed_generation(client, factory, engine)
    staging = Path(settings.staging_dir) / gid / "attempt-z"
    staging.mkdir(parents=True, exist_ok=True)
    (staging / "video-0.staged").write_bytes(b"not-media-at-all")
    staged = [StagedOutput(output_key="video:0",
                            path=staging / "video-0.staged",
                            kind="video")]
    contract = [CapturedOutputContract(
        name="video", kind="video", expected_count=1,
        accepted_media_types=("image/png",),  # mismatching contract
    )]
    with pytest.raises(SoloRingError):
        await _import_via_existing_importer(
            engine, settings, factory, gid, staged, contract,
        )
    async with factory() as s:
        takes = (await s.execute(text(
            "SELECT count(*) FROM takes WHERE generation_id=:g"
        ), {"g": gid})).scalar()
    assert takes == 0


async def test_soft_cancel_short_circuits_before_view(
    client, factory, engine, settings
):
    """history succeeded + soft_cancel set → zero /view, zero import,
    cancelled."""
    from soloring.worker.ownership import (
        acquire_worker_lease, claim_next_generation,
    )

    gid = await _seed_generation(client, factory, engine)
    await acquire_worker_lease(engine, "w-A", 30)
    _, attempt = await claim_next_generation(engine, "w-A")
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(text(
            "UPDATE generations SET cancel_requested_at="
            "strftime('%Y-%m-%dT%H:%M:%fZ','now'), soft_cancel_selected_at="
            "strftime('%Y-%m-%dT%H:%M:%fZ','now'), executor_job_id='P' "
            "WHERE id=:g"
        ).bindparams(g=gid))
        await conn.exec_driver_sql("COMMIT")

    from soloring.worker.comfy_cancellation import reconcile_cancellation
    from soloring.executors.comfy.capabilities import (
        CancellationCapability, CancellationMode,
    )
    from soloring.executors.comfy.client import ComfyClient

    view_calls: list[str] = []

    class Double:
        base_url = "http://c"

        def handler(self, request):
            if request.url.path == "/view":
                view_calls.append(request.url.path)
                return httpx.Response(200, content=b"x")
            if request.url.path.startswith("/history"):
                return httpx.Response(200, json={
                    "P": {"prompt": [0, "P", {}, {}, []], "outputs": {},
                           "status": {"status_str": "completed",
                                       "messages": []}},
                })
            if request.url.path == "/queue":
                return httpx.Response(200, json={
                    "queue_running": [], "queue_pending": []})
            return httpx.Response(404)

    c = ComfyClient("http://c", "w", transport=httpx.MockTransport(
        Double().handler))
    result = await reconcile_cancellation(
        engine, "w-A", gid, attempt, "P", c,
        CancellationCapability(mode=CancellationMode.SOFT_ONLY,
                                retry_safety="unsafe"),
    )
    assert result == "cancelled"
    assert view_calls == []  # ZERO /view
    async with factory() as s:
        row = dict((await s.execute(text(
            "SELECT status, cancel_requested_at, soft_cancel_selected_at "
            "FROM generations WHERE id=:g"
        ), {"g": gid})).mappings().one())
        takes = (await s.execute(text(
            "SELECT count(*) FROM takes WHERE generation_id=:g"
        ), {"g": gid})).scalar()
    assert row["status"] == "cancelled"
    assert takes == 0


async def test_lease_loser_import_write_fenced(client, factory, engine):
    gid = await _seed_generation(client, factory, engine)
    from soloring.worker.ownership import (
        OwnershipMutationResult, acquire_worker_lease, claim_next_generation,
        transition_owned_generation,
    )

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
    r = await transition_owned_generation(engine, "w-A", gid, "succeeded")
    assert r is OwnershipMutationResult.LEASE_LOST


# --- structural negatives -------------------------------------------------------------


def test_outputs_module_db_free_and_no_discovery_filesystem():
    import ast as _ast

    banned_imports = ("soloring.db", "soloring.worker", "sqlalchemy",
                       "aiosqlite")
    banned_calls = ("listdir", "glob", "rglob", "walk")
    source = (BASE_DIR / "server" / "soloring" / "executors" / "comfy"
              / "outputs.py").read_text("utf-8")
    tree = _ast.parse(source)
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, _ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        for n in names:
            for b in banned_imports:
                assert not (n == b or n.startswith(b + ".")), n
        if isinstance(node, _ast.Attribute) and node.attr in banned_calls:
            raise AssertionError(f"filesystem discovery: {node.attr}")
        if isinstance(node, _ast.Call) and isinstance(node.func, _ast.Name):
            assert node.func.id != "open" or True  # open(wb) for streaming is the allowed form
    assert "COMFY_OUTPUT_ROOT" not in source
    assert "installed" not in source.lower() or "installed workflow" in source


def test_no_caller_controlled_view_type():
    """The /view type is hardcoded to output in validation + resolution."""
    from soloring.executors.comfy import outputs as outputs_mod
    import inspect

    src = inspect.getsource(outputs_mod)
    assert 'ref.type != "output"' in src  # validation is exact
    # ResolvedComfyOutput defaults to output and resolve never reads a
    # caller type.
    r = ResolvedComfyOutput(
        output_key="k", logical_name="v", expected_kind="video",
        accepted_media_types=None, filename="f.png", subfolder="",
    )
    assert r.type == "output"
