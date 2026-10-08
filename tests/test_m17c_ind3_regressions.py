"""M17C-B IND3 corrective regressions (IND3-01, frozen under the PR
#26 protocol cycle of 2026-09-29; product base b2c50ff).

IND3-01: the manifest/restore-tree layer's OWN content read
(``_verify_manifest_files`` -> ``_verify_bytes`` -> ``_stream_hash``
-> built-in ``open``) is normalized — a successful ``Path.is_file()``
probe followed by an open/read ``FileNotFoundError`` /
``PermissionError`` / representative ``OSError`` surfaces as the
backup module's stable ``RecoveryCorruption`` with Blob/manifest-read
specific context, never a raw OS exception. The regression patches the
ACTUAL built-in ``open`` seam selectively for the target staged Blob
filename (``_stream_hash`` uses built-in ``open``, NOT
``Path.read_bytes``), proving the MANIFEST layer fires FIRST — the
semantic M17B ``_blob_bytes`` reader (which normalizes
``Path.read_bytes``) is never reached. One representative adjacent
regression proves the same wrapper on the backup DB content read (the
adjacent-audit callsite in the same public restore path).
"""

from __future__ import annotations

import builtins
import pathlib
import sqlite3

import pytest
from sqlalchemy import text

from tests.test_m17c_shot_mapping import (
    _bound_world,
    _seg_body,
)

_TABLE = "shot_performance_segment_mappings"


def _engine(client):
    return client._transport.app.state.engine


async def _one(client, stmt, params=None):
    async with _engine(client).connect() as conn:
        return dict((await conn.execute(
            text(stmt), params or {})).mappings().one())


async def _backup_0021(client, tmp_path, tag):
    from tests.test_m17c_sr26_regressions import _backup_m17c
    return await _backup_m17c(client, tmp_path, tag)


async def _restore_refuses(backup_root, tmp_path, tag):
    from tests.test_m17c_sr2_regressions import (
        _restore_refuses as sr2_refuses)
    return await sr2_refuses(backup_root, tmp_path, tag)


async def _world_with_backup(client, tmp_path):
    world = await _bound_world(client)
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 1000, 0, vp=0))
    assert r.status_code == 200, r.text
    root = await _backup_0021(client, tmp_path, "ind3")
    blob_hash = (await _one(
        client,
        "SELECT canonical_channel_payload_blob_hash AS h FROM "
        "performance_candidates WHERE id = :c",
        {"c": world["candidate"]["id"]}))["h"]
    staged = root / "blobs" / "sha256" / blob_hash[:2] \
        / blob_hash[2:4] / blob_hash
    assert staged.is_file()
    return world, root, blob_hash


def _patch_open_for_name(monkeypatch, target_name, error):
    """Patch the ACTUAL built-in ``open`` seam (what ``_stream_hash``
    uses) selectively: only opens whose final path component equals
    ``target_name`` raise; every other open is the real built-in."""
    real_open = builtins.open

    def selective_open(file, mode="r", *args, **kwargs):
        try:
            name = pathlib.Path(file).name
        except TypeError:
            name = None
        if name == target_name:
            raise error
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", selective_open)
    return real_open


@pytest.mark.asyncio
@pytest.mark.parametrize("error,fragment", [
    # A: probe succeeds, the manifest content open gets FileNotFound
    (FileNotFoundError("gone"),
     "disappeared during manifest content verification"),
    # B: probe succeeds, the manifest content open gets Permission
    (PermissionError("denied"),
     "permission denied) during the manifest content read"),
    # C: probe succeeds, the manifest content open gets OSError(EIO)
    (OSError(5, "Input/output error"),
     "through a storage error"),
])
async def test_ind301_manifest_blob_content_read_normalized(
        client, tmp_path, monkeypatch, error, fragment):
    """The MANIFEST layer's own content read fires FIRST (the
    semantic M17B reader is never reached — its message family is
    explicitly NOT the one asserted) and refuses through the stable
    RecoveryCorruption hierarchy with a Blob/manifest-read specific
    diagnostic; never a raw OS exception."""
    _, root, blob_hash = await _world_with_backup(client, tmp_path)
    real_open = _patch_open_for_name(monkeypatch, blob_hash, error)
    exc = await _restore_refuses(root, tmp_path, "ind3")
    monkeypatch.setattr(builtins, "open", real_open)
    # the manifest-layer branch, not the semantic M17B family
    assert type(exc).__name__ == "RecoveryCorruption", repr(exc)
    assert "M17B payload blob" not in str(exc), exc
    assert blob_hash in str(exc), exc
    assert fragment in str(exc), (fragment, exc)
    assert not isinstance(exc, OSError), exc


@pytest.mark.asyncio
async def test_ind301_adjacent_backup_db_content_read_normalized(
        client, tmp_path, monkeypatch):
    """Adjacent-audit representative: the backup DB content read sits
    in the same public restore path with the same leak shape and now
    shares the wrapper — a permission failure on the DB content open
    refuses as RecoveryCorruption with DB context, never a raw
    PermissionError. (The sqlite3 machinery opens the DB through its
    own C layer, so patching builtins.open selectively for
    ``soloring.db`` hits exactly the manifest hash read.)"""
    _, root, _ = await _world_with_backup(client, tmp_path)
    real_open = _patch_open_for_name(
        monkeypatch, "soloring.db", PermissionError("denied"))
    exc = await _restore_refuses(root, tmp_path, "ind3-db")
    monkeypatch.setattr(builtins, "open", real_open)
    assert type(exc).__name__ == "RecoveryCorruption", repr(exc)
    assert "permission denied" in str(exc), exc
    assert "manifest content read" in str(exc), exc
    assert not isinstance(exc, OSError), exc


@pytest.mark.asyncio
async def test_ind301_hash_mismatch_still_passes_through(client, tmp_path):
    """A successful content read with the WRONG bytes keeps the
    existing hash-mismatch RecoveryCorruption (the wrapper adds no
    behavior when the read succeeds)."""
    from tests.test_m17c_sr26_regressions import _rehash_manifest
    _, root, blob_hash = await _world_with_backup(client, tmp_path)
    staged = root / "blobs" / "sha256" / blob_hash[:2] \
        / blob_hash[2:4] / blob_hash
    data = bytearray(staged.read_bytes())
    data[0] ^= 0xFF
    staged.write_bytes(bytes(data))
    _rehash_manifest(root)
    exc = await _restore_refuses(root, tmp_path, "ind3-hash")
    assert type(exc).__name__ == "RecoveryCorruption", repr(exc)
    assert "frozen identity" in str(exc), exc
