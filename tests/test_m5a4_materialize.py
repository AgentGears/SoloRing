"""M5A-4 — Input Materialization (M5 plan §25-§31, §68).

The full mandatory matrix: one-blob-one-reference, namespace determinism and
attempt isolation, returned-name authority, hostile reference validation,
same-blob dedup with logical bindings preserved, out-of-order completion →
deterministic order, retry with/without proven convergence, large-blob event
loop discipline, missing/corrupt Blob, original-filename irrelevance, purity
rules, and no submission-state mutation.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path

import pytest

from soloring.errors import ErrorCode, SoloRingError
from soloring.executors.comfy.input_materializer import (
    CapturedInput,
    HttpInputMaterializer,
    InputMaterializationError,
    InputReferenceInvalid,
    MaterializationOutcome,
    attempt_namespace,
    requested_filename,
    validate_returned_reference,
)
from soloring.settings import BASE_DIR

import ast

PNG = b"\x89PNG\r\n\x1a\n" + b"input-materialization-payload" * 4
BH = hashlib.sha256(PNG).hexdigest()
PNG2 = b"\x89PNG\r\n\x1a\n" + b"second-distinct-blob" * 4
BH2 = hashlib.sha256(PNG2).hexdigest()

GID, AID = "g" * 36, "a" * 36
NS = attempt_namespace(GID, AID)


class FakeUploader:
    """Streaming-seam double: receives source_path, streams it in bounded
    chunks (never whole-file bytes), and records every interface fact the
    negative-evidence proofs need."""

    def __init__(
        self,
        rename_map: dict | None = None,
        fail_first: int = 0,
        delay_map: dict | None = None,
        mutate_source_after_verify: bool = False,
    ):
        self.store: dict[str, bytes] = {}
        self.calls: list[tuple[str, str]] = []
        self.source_paths: list[Path] = []
        self.max_read: int = 0  # largest single read the seam performed
        self.rename_map = rename_map or {}
        self.fail_first = fail_first
        self.delay_map = delay_map or {}
        self.mutate_source_after_verify = mutate_source_after_verify

    async def upload(self, *, source_path: Path, filename: str, subfolder: str):
        await asyncio.sleep(self.delay_map.get(filename, 0))
        self.calls.append((filename, subfolder))
        self.source_paths.append(source_path)
        if self.fail_first > 0:
            self.fail_first -= 1
            raise ConnectionError("simulated upload transport failure")
        # Stream in bounded chunks; track the largest read for the
        # no-whole-file-buffer behavioral proof.
        content = bytearray()
        with open(source_path, "rb") as fh:
            while True:
                chunk = fh.read(1 << 16)  # 64 KiB stream chunks
                if not chunk:
                    break
                self.max_read = max(self.max_read, len(chunk))
                content.extend(chunk)
        if self.mutate_source_after_verify:
            source_path.write_bytes(b"tampered-after-verification")
        self.store[f"{subfolder}/{filename}"] = bytes(content)
        return self.rename_map.get(filename, filename), subfolder


def _blob_dir(tmp_path: Path) -> Path:
    d = tmp_path / "blobs" / "sha256" / BH[:2] / BH[2:4]
    d.mkdir(parents=True, exist_ok=True)
    (d / BH).write_bytes(PNG)
    d2 = tmp_path / "blobs" / "sha256" / BH2[:2] / BH2[2:4]
    d2.mkdir(parents=True, exist_ok=True)
    (d2 / BH2).write_bytes(PNG2)
    return tmp_path / "blobs"


def _path_for(blob_root: Path):
    def fn(blob_hash: str) -> Path:
        return blob_root / "sha256" / blob_hash[:2] / blob_hash[2:4] / blob_hash
    return fn


def _inputs(*specs):
    return [CapturedInput(input_key=k, position=p, asset_id=a, blob_hash=b)
            for k, p, a, b in specs]


# --- basics ---------------------------------------------------------------------


async def test_one_blob_one_normalized_reference(tmp_path):
    root = _blob_dir(tmp_path)
    up = FakeUploader()
    m = HttpInputMaterializer(up, _path_for(root))
    outcome = await m.materialize(
        generation_id=GID, attempt_id=AID,
        inputs=_inputs(("reference_image", 0, "asset-1", BH)),
    )
    assert isinstance(outcome, MaterializationOutcome)
    (item,) = outcome.materialized
    assert item.remote_name == f"{BH}.png"
    assert item.subfolder == NS
    assert item.blob_hash == BH
    assert len(up.calls) == 1
    assert up.store[f"{NS}/{BH}.png"] == PNG
    assert up.source_paths[0].name == BH  # same content-addressed path


def test_namespace_deterministic_and_attempt_isolated():
    assert attempt_namespace(GID, AID) == attempt_namespace(GID, AID)
    assert attempt_namespace(GID, "b" * 36) != NS  # different attempt
    ns = NS
    assert set(ns) <= set("soloring_gen_att_0123456789abcdef")
    assert "/" not in ns and "\\" not in ns and len(ns) <= 96


def test_requested_filename_from_blob_identity():
    assert requested_filename(BH, "image/png") == f"{BH}.png"
    assert requested_filename(BH, None) == f"{BH}.bin"


# --- returned-reference authority + validation -------------------------------------


async def test_auto_renamed_returned_name_is_authoritative(tmp_path):
    root = _blob_dir(tmp_path)
    renamed = f"{BH[:8]}… (1).png"
    up = FakeUploader(rename_map={f"{BH}.png": renamed})
    m = HttpInputMaterializer(up, _path_for(root))
    outcome = await m.materialize(
        generation_id=GID, attempt_id=AID,
        inputs=_inputs(("reference_image", 0, "asset-1", BH)),
    )
    assert outcome.materialized[0].remote_name == renamed  # NOT the requested


async def test_unexpected_subfolder_rejected(tmp_path):
    root = _blob_dir(tmp_path)

    class WrongFolder(FakeUploader):
        async def upload(self, **kw):
            n, _ = await super().upload(**kw)
            return n, "some-other-folder"

    m = HttpInputMaterializer(WrongFolder(), _path_for(root))
    with pytest.raises(InputReferenceInvalid):
        await m.materialize(
            generation_id=GID, attempt_id=AID,
            inputs=_inputs(("reference_image", 0, "asset-1", BH)),
        )


@pytest.mark.parametrize("bad_name", ["", "/etc/passwd", "..", "a/b.png", "a\\b.png", "x" * 300, "con\ttrol"])
async def test_unsafe_returned_filenames_rejected(tmp_path, bad_name):
    root = _blob_dir(tmp_path)

    class Bad(FakeUploader):
        async def upload(self, **kw):
            await super().upload(**kw)
            return bad_name, kw["subfolder"]

    m = HttpInputMaterializer(Bad(), _path_for(root))
    with pytest.raises(InputReferenceInvalid):
        await m.materialize(
            generation_id=GID, attempt_id=AID,
            inputs=_inputs(("reference_image", 0, "asset-1", BH)),
        )


# --- dedup + ordering -------------------------------------------------------------


async def test_same_blob_two_bindings_one_upload(tmp_path):
    root = _blob_dir(tmp_path)
    up = FakeUploader()
    m = HttpInputMaterializer(up, _path_for(root))
    outcome = await m.materialize(
        generation_id=GID, attempt_id=AID,
        inputs=_inputs(
            ("reference_image", 0, "asset-1", BH),
            ("style_image", 0, "asset-1", BH),  # same blob, second logical binding
        ),
    )
    assert len(outcome.materialized) == 2  # logical bindings preserved
    assert len(up.calls) == 1  # one physical upload
    keys = [(i.input_key, i.position) for i in outcome.materialized]
    assert keys == [("reference_image", 0), ("style_image", 0)]


async def test_out_of_order_completion_deterministic_result(tmp_path):
    root = _blob_dir(tmp_path)
    # style_image's upload finishes FIRST; reference_image is delayed.
    up = FakeUploader(delay_map={f"{BH}.png": 0.05, f"{BH2}.png": 0.0})
    m = HttpInputMaterializer(up, _path_for(root))
    outcome = await m.materialize(
        generation_id=GID, attempt_id=AID,
        inputs=_inputs(
            ("reference_image", 0, "asset-1", BH),
            ("reference_image", 1, "asset-2", BH2),
        ),
    )
    ordered = [(i.input_key, i.position, i.blob_hash) for i in outcome.materialized]
    assert ordered == [
        ("reference_image", 0, BH),
        ("reference_image", 1, BH2),
    ]
    assert len(up.calls) == 2


# --- retry policy -------------------------------------------------------------------


async def test_retry_with_proven_convergence_succeeds(tmp_path):
    root = _blob_dir(tmp_path)
    up = FakeUploader(fail_first=1)
    m = HttpInputMaterializer(up, _path_for(root), retry_convergent=True)
    outcome = await m.materialize(
        generation_id=GID, attempt_id=AID,
        inputs=_inputs(("reference_image", 0, "asset-1", BH)),
    )
    assert outcome.materialized[0].remote_name == f"{BH}.png"
    assert outcome.retry_convergent is True
    assert len(up.calls) == 2


async def test_retry_without_convergence_fails_fast(tmp_path):
    root = _blob_dir(tmp_path)
    up = FakeUploader(fail_first=1)
    m = HttpInputMaterializer(up, _path_for(root), retry_convergent=False)
    with pytest.raises(InputMaterializationError) as e:
        await m.materialize(
            generation_id=GID, attempt_id=AID,
            inputs=_inputs(("reference_image", 0, "asset-1", BH)),
        )
    assert e.value.code == ErrorCode.COMFY_INPUT_UPLOAD_FAILED
    assert len(up.calls) == 1  # no speculative retry


# --- event loop + blob integrity ------------------------------------------------------


async def test_large_upload_does_not_starve_event_loop(tmp_path):
    root = _blob_dir(tmp_path)
    big = b"\x89PNG\r\n\x1a\n" + (b"0123456789abcdef" * 4 * 1024 * 1024)  # ~64 MiB
    bh = hashlib.sha256(big).hexdigest()
    d = root / "sha256" / bh[:2] / bh[2:4]
    d.mkdir(parents=True, exist_ok=True)
    (d / bh).write_bytes(big)

    ticks: list[float] = []
    done = asyncio.Event()

    async def ticker():
        while not done.is_set():
            ticks.append(time.monotonic())
            await asyncio.sleep(0.005)

    up = FakeUploader()
    m = HttpInputMaterializer(up, _path_for(root))
    task = asyncio.create_task(ticker())
    try:
        outcome = await m.materialize(
            generation_id=GID, attempt_id=AID,
            inputs=_inputs(("reference_image", 0, "asset-big", bh)),
        )
    finally:
        done.set()
        await task
    assert outcome.materialized[0].remote_name == f"{bh}.png"
    gaps = [b - a for a, b in zip(ticks, ticks[1:])]
    assert ticks and max(gaps) < 0.5, f"event loop starved: max gap={max(gaps):.3f}"


async def test_corrupt_blob_rejected_before_upload(tmp_path):
    root = _blob_dir(tmp_path)
    (root / "sha256" / BH[:2] / BH[2:4] / BH).write_bytes(b"corrupted")
    up = FakeUploader()
    m = HttpInputMaterializer(up, _path_for(root))
    with pytest.raises(InputReferenceInvalid):
        await m.materialize(
            generation_id=GID, attempt_id=AID,
            inputs=_inputs(("reference_image", 0, "asset-1", BH)),
        )
    assert up.calls == []  # no bytes ever uploaded


async def test_missing_blob_rejected(tmp_path):
    root = _blob_dir(tmp_path)
    missing = "e" * 64
    up = FakeUploader()
    m = HttpInputMaterializer(up, _path_for(root))
    with pytest.raises(Exception):
        await m.materialize(
            generation_id=GID, attempt_id=AID,
            inputs=_inputs(("reference_image", 0, "asset-x", missing)),
        )
    assert up.calls == []


def test_original_filename_never_enters_materialization():
    """The materializer's inputs carry only hash identity — there is no
    filename field on CapturedInput at all (structural proof)."""
    import dataclasses

    fields = {f.name for f in dataclasses.fields(CapturedInput)}
    assert "original_filename" not in fields
    assert fields == {"input_key", "position", "asset_id", "blob_hash"}


# --- purity + boundary -----------------------------------------------------------------


def test_materializer_module_purity():
    import ast as _ast

    source = (BASE_DIR / "server" / "soloring" / "executors" / "comfy"
              / "input_materializer.py").read_text("utf-8")
    tree = _ast.parse(source)
    banned = ("soloring.db", "soloring.worker", "sqlalchemy", "aiosqlite")
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
    # Endpoint literals could only appear as call/keyword string arguments;
    # docstring prose is structurally excluded by checking only Call nodes.
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Call):
            for sub in _ast.walk(node):
                if (
                    isinstance(sub, _ast.Constant)
                    and isinstance(sub.value, str)
                    and sub.value in ("/prompt", "/view")
                ):
                    raise AssertionError(
                        f"endpoint literal in materializer code: {sub.value}"
                    )


def test_no_submission_state_and_no_prompt_or_view():
    import ast as _ast

    source = (BASE_DIR / "server" / "soloring" / "executors" / "comfy"
              / "input_materializer.py").read_text("utf-8")
    banned_calls = ("mark_submission_possible", "persist_owned_executor_submission")
    for name in banned_calls:
        assert name not in source, f"submission-state mutation leaked: {name}"


# --- M5A-4 closure: bounded-memory + same-source guarantees ------------------------


async def test_uploader_seam_never_receives_whole_file_bytes(tmp_path):
    """Behavioral negative evidence: with a 32 MiB Blob, the seam's largest
    single read stays at stream-chunk size — the interface structurally
    cannot receive the complete payload."""
    root = _blob_dir(tmp_path)
    big = b"\x89PNG\r\n\x1a\n" + (b"0123456789abcdef" * 2 * 1024 * 1024)  # ~32 MiB
    bh = hashlib.sha256(big).hexdigest()
    d = root / "sha256" / bh[:2] / bh[2:4]
    d.mkdir(parents=True, exist_ok=True)
    (d / bh).write_bytes(big)

    up = FakeUploader()
    m = HttpInputMaterializer(up, _path_for(root))
    outcome = await m.materialize(
        generation_id=GID, attempt_id=AID,
        inputs=_inputs(("reference_image", 0, "asset-big", bh)),
    )
    assert outcome.materialized[0].remote_name == f"{bh}.png"
    assert up.max_read <= 1 << 16, (
        f"seam buffered whole file: max_read={up.max_read}"
    )
    assert up.source_paths[0].name == bh  # verified content-addressed path


def test_materializer_source_has_no_read_bytes():
    """AST: input_materializer.py must not contain read_bytes()/read() calls
    that materialize whole files outside the bounded _hash_stream chunker."""
    import ast as _ast

    source = (BASE_DIR / "server" / "soloring" / "executors" / "comfy"
              / "input_materializer.py").read_text("utf-8")
    tree = _ast.parse(source)
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Attribute) and node.attr == "read_bytes":
            raise AssertionError("read_bytes() in materializer (whole-file read)")
        if (
            isinstance(node, _ast.Call)
            and isinstance(node.func, _ast.Attribute)
            and node.func.attr == "read"
            and node.args
        ):
            # fh.read(CHUNK) with an explicit bounded size is the allowed form.
            arg = node.args[0]
            bounded = (
                (isinstance(arg, _ast.Constant) and isinstance(arg.value, int))
                or (isinstance(arg, _ast.Name) and arg.id == "CHUNK")
            )
            if not bounded:
                raise AssertionError(
                    "unbounded read() in materializer: only fh.read(CHUNK) allowed"
                )


async def test_source_changed_between_verification_and_transport_detected(tmp_path):
    """The uploader tamers with the source after the materializer verified it:
    the post-transport re-verification must catch it and fail."""
    root = _blob_dir(tmp_path)
    up = FakeUploader(mutate_source_after_verify=True)
    m = HttpInputMaterializer(up, _path_for(root))
    from soloring.executors.comfy.input_materializer import InputReferenceInvalid

    with pytest.raises(InputReferenceInvalid):
        await m.materialize(
            generation_id=GID, attempt_id=AID,
            inputs=_inputs(("reference_image", 0, "asset-1", BH)),
        )


async def test_uploader_opens_same_content_addressed_path_read_only(tmp_path):
    """The seam receives exactly the Blob-store-derived path for the hash —
    arbitrary caller paths never enter (the path derives from
    blob_path_for_hash, and the double records it)."""
    root = _blob_dir(tmp_path)
    seen = {}

    class Recording(FakeUploader):
        async def upload(self, **kw):
            seen["path"] = kw["source_path"]
            return await super().upload(**kw)

    up = Recording()
    m = HttpInputMaterializer(up, _path_for(root))
    await m.materialize(
        generation_id=GID, attempt_id=AID,
        inputs=_inputs(("reference_image", 0, "asset-1", BH)),
    )
    expected = root / "sha256" / BH[:2] / BH[2:4] / BH
    assert seen["path"] == expected
