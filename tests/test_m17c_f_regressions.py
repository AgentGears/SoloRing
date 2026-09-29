"""M17C-B F corrective regressions (F-01/F-02, frozen under the PR
#26 protocol cycle of 2026-09-29; product base b4c31e6).

Public-restore error-envelope closure only — no PF-02/M17C-B semantic
change:

- F-01: the workflow-artifact METADATA probe (`Path.is_file()`
  immediately before the already-normalized content read) is guarded —
  PermissionError before generic OSError, both translated to
  RecoveryCorruption with artifact kind/hash/path context; ordinary
  absence keeps the established missing-artifact semantics.
- F-02: the initial backup-manifest.json ACQUISITION boundary
  (`read_bytes`) extends beyond missing — PermissionError and
  representative OSError become RecoveryCorruption with manifest
  identity/path context; parse_backup_manifest_v1 keeps its own
  UTF-8/JSON/canonical-grammar contract unchanged.

The regressions use a REAL manifest-listed workflow artifact
(synthesized into an otherwise-lawful backup: exact artifact path
layout, canonical manifest re-serialization, grammar-satisfying
sorted entries) and patch ONLY the target seam (the artifact's
`is_file`; the manifest's `read_bytes`), proving the probe/acquisition
layer fires — not the content-hash wrapper.
"""

from __future__ import annotations

import hashlib
import pathlib
import sqlite3

import pytest
from sqlalchemy import text

from soloring.recovery.backup import RecoveryCorruption
from tests.test_m17c_shot_mapping import (
    _bound_world,
    _seg_body,
)


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
    root = await _backup_0021(client, tmp_path, "f01")
    return world, root


def _add_real_artifact(root) -> tuple[str, str, pathlib.Path]:
    """Synthesize ONE real manifest-listed workflow artifact into an
    otherwise-lawful backup: canonical bytes on disk at the exact
    artifact path, a grammar-satisfying (sorted) manifest entry, and a
    canonical manifest rewrite with the recomputed database hash."""
    from soloring.domain.canonical import canonical_json_bytes
    body = b'{"kind": "f01-real-artifact"}'
    sha = hashlib.sha256(body).hexdigest()
    kind = "manifests"
    path = (root / "workflow-artifacts" / kind / "sha256" / sha[:2]
            / sha[2:4] / f"{sha}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    manifest_path = root / "backup-manifest.json"
    import json
    doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = doc["workflow_artifacts"] + [
        {"kind": kind, "sha256": sha}]
    doc["workflow_artifacts"] = sorted(
        entries, key=lambda e: (e["kind"], e["sha256"]))
    doc["database_sha256"] = hashlib.sha256(
        (root / "soloring.db").read_bytes()).hexdigest()
    manifest_path.write_bytes(canonical_json_bytes(doc))
    return kind, sha, path


# ---------------------------------------------------------------------------
# F-01 — workflow-artifact metadata probe
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("error,fragment", [
    (PermissionError("denied"),
     "permission denied) during the storage probe"),
    (OSError(5, "Input/output error"),
     "could not be probed through a storage error"),
])
async def test_f01_artifact_probe_normalized(
        client, tmp_path, monkeypatch, error, fragment):
    """The artifact's is_file() probe fails after everything earlier in
    the restore sequence succeeds — the PROBE layer fires with the
    COMPLETE identity contract (kind + sha + concrete path + probe
    family), NOT the content-hash wrapper (its 'manifest content read'
    family is explicitly not matched), and the raw OS exception cannot
    satisfy the contract. Exact-PATH injection is viable because
    ``_verify_backup_tree(backup_root, False)`` probes the ORIGINAL
    backup root before any staging — the probe receives exactly the
    ``path`` this test constructed."""
    _, root = await _world_with_backup(client, tmp_path)
    kind, sha, path = _add_real_artifact(root)
    # the injected failure replaces a GENUINELY successful metadata
    # probe, not a masked absent fixture
    assert path.is_file()
    real_is_file = pathlib.Path.is_file

    def selective_is_file(self):
        if self == path:
            raise error
        return real_is_file(self)

    monkeypatch.setattr(pathlib.Path, "is_file", selective_is_file)
    exc = await _restore_refuses(root, tmp_path, "f01")
    monkeypatch.setattr(pathlib.Path, "is_file", real_is_file)
    assert isinstance(exc, RecoveryCorruption), repr(exc)
    assert not isinstance(exc, OSError), exc
    assert kind in str(exc), exc
    assert sha in str(exc), exc
    assert str(path) in str(exc), exc
    assert fragment in str(exc), (fragment, exc)
    # the content-hash wrapper is NOT the first firing layer
    assert "manifest content read" not in str(exc), exc
    assert "disappeared during manifest content" not in str(exc), exc


@pytest.mark.asyncio
async def test_f01_artifact_ordinary_absence_unchanged(client, tmp_path):
    """A plain missing artifact file keeps the established
    missing-artifact corruption semantics."""
    _, root = await _world_with_backup(client, tmp_path)
    kind, sha, path = _add_real_artifact(root)
    path.unlink()
    from tests.test_m17c_sr26_regressions import _rehash_manifest
    _rehash_manifest(root)
    exc = await _restore_refuses(root, tmp_path, "f01-missing")
    assert isinstance(exc, RecoveryCorruption), repr(exc)
    assert "is missing" in str(exc), exc
    assert sha in str(exc), exc


@pytest.mark.asyncio
async def test_f01_artifact_hash_mismatch_unchanged(client, tmp_path):
    """Successful probe + wrong bytes keeps the content-hash wrapper's
    pass-through mismatch behavior."""
    _, root = await _world_with_backup(client, tmp_path)
    kind, sha, path = _add_real_artifact(root)
    data = bytearray(path.read_bytes())
    data[0] ^= 0xFF
    path.write_bytes(bytes(data))
    from tests.test_m17c_sr26_regressions import _rehash_manifest
    _rehash_manifest(root)
    exc = await _restore_refuses(root, tmp_path, "f01-hash")
    assert isinstance(exc, RecoveryCorruption), repr(exc)
    assert "frozen identity" in str(exc), exc


# ---------------------------------------------------------------------------
# F-02 — initial backup-manifest.json acquisition
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("error,fragment", [
    (PermissionError("denied"),
     "permission denied) during manifest acquisition"),
    (OSError(5, "Input/output error"),
     "through a storage error"),
])
async def test_f02_manifest_acquisition_normalized(
        client, tmp_path, monkeypatch, error, fragment):
    """Only the target backup-manifest.json read_bytes fails: the
    acquisition boundary fires with the CONCRETE manifest location in
    the diagnostic before any parse/probe stage; the raw OS exception
    cannot satisfy the contract. Exact-PATH selection is viable because
    the acquisition reads the ORIGINAL backup root's manifest before
    any staging."""
    _, root = await _world_with_backup(client, tmp_path)
    manifest_path = root / "backup-manifest.json"
    real_read_bytes = pathlib.Path.read_bytes

    def selective_read_bytes(self):
        if self == manifest_path:
            raise error
        return real_read_bytes(self)

    monkeypatch.setattr(pathlib.Path, "read_bytes", selective_read_bytes)
    exc = await _restore_refuses(root, tmp_path, "f02")
    monkeypatch.setattr(pathlib.Path, "read_bytes", real_read_bytes)
    assert isinstance(exc, RecoveryCorruption), repr(exc)
    assert not isinstance(exc, OSError), exc
    assert str(manifest_path) in str(exc), exc
    assert fragment in str(exc), (fragment, exc)


@pytest.mark.asyncio
async def test_f02_missing_manifest_unchanged(client, tmp_path):
    """The frozen missing-manifest behavior is preserved under the
    EXACT production subtype (RecoveryCorruption from the authoritative
    module) with the frozen diagnostic and no destination created."""
    _, root = await _world_with_backup(client, tmp_path)
    (root / "backup-manifest.json").unlink()
    from soloring.recovery import restore as rb_restore
    with pytest.raises(RecoveryCorruption,
                       match="no backup-manifest.json"):
        await rb_restore(root, tmp_path / "dest")
    assert not (tmp_path / "dest").exists()


@pytest.mark.asyncio
async def test_f02_malformed_manifest_still_parse_contract(
        client, tmp_path):
    """Malformed manifest bytes remain parse_backup_manifest_v1's
    contract (BackupManifestInvalid, not generic recovery corruption
    from the acquisition boundary)."""
    _, root = await _world_with_backup(client, tmp_path)
    (root / "backup-manifest.json").write_bytes(b"{nope")
    from soloring.recovery import restore as rb_restore
    from soloring.recovery.backup import BackupManifestInvalid
    with pytest.raises(BackupManifestInvalid):
        await rb_restore(root, tmp_path / "dest")
    assert not (tmp_path / "dest").exists()
