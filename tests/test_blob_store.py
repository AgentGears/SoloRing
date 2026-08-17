"""BlobStore skeleton tests (plan §24, §45) + path-safety (audit #4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from soloring.assets.blob_store import BlobStore
from soloring.settings import Settings


@pytest.fixture
def store(tmp_data_dir: Path) -> BlobStore:
    return BlobStore(Settings(data_dir=tmp_data_dir))


# --- hash validation & path derivation --------------------------------------


def test_validate_hash_accepts_64_lowercase_hex(store: BlobStore) -> None:
    assert store.validate_hash("a" * 64)
    assert store.validate_hash("0123456789abcdef" * 4)


@pytest.mark.parametrize(
    "bad",
    [
        "short",
        "A" * 64,          # uppercase rejected
        "g" * 64,          # non-hex
        "a" * 63,          # too short
        "a" * 65,          # too long
        "",
    ],
)
def test_validate_hash_rejects_invalid(store: BlobStore, bad: str) -> None:
    assert not store.validate_hash(bad)


def test_path_for_hash_layout(store: BlobStore) -> None:
    h = "abcdef0123456789" * 4  # 64 hex
    p = store.path_for_hash(h)
    # plan §45: <blob_dir>/sha256/<h[0:2]>/<h[2:4]>/<full-hash>
    assert p == store.blob_dir / "sha256" / h[0:2] / h[2:4] / h


def test_path_for_hash_rejects_invalid(store: BlobStore) -> None:
    with pytest.raises(ValueError):
        store.path_for_hash("../escape")


# --- temp path traversal safety (audit #4) ----------------------------------
# tmp_path takes NO caller input, so traversal is structurally impossible.
# These tests guard against any future regression that re-introduces input.


def test_tmp_path_is_under_tmp_dir(store: BlobStore) -> None:
    p = store.tmp_path()
    # resolved path must be contained within tmp_dir
    assert p.resolve().is_relative_to(store.tmp_dir.resolve())
    assert p.parent == store.tmp_dir
    assert p.suffix == ".tmp"


def test_tmp_path_names_are_server_generated(store: BlobStore) -> None:
    names = {store.tmp_path().name for _ in range(20)}
    assert len(names) == 20  # unique, random
    for n in names:
        assert n.endswith(".tmp")
        assert ".." not in n and "/" not in n and "\\" not in n


def test_tmp_path_has_no_traversal_surface(store: BlobStore) -> None:
    # There is no parameter to abuse; signature is tmp_path().
    import inspect

    sig = inspect.signature(store.tmp_path)
    assert list(sig.parameters) == [], "tmp_path must accept no caller input"
