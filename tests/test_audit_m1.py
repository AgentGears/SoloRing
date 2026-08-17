"""Audit remediation — M1 regressions (source-audit findings F2, F3).

F2: ShotRevision capture must derive Shot state and references from ONE
    SQLite read snapshot; an interleaved writer must never be combinable
    into a hybrid revision (subject=A + new refs) that never existed.
F3: a corrupt pre-existing file at a content-addressed Blob path must be
    detected (by hashing) and repaired from the independently verified
    upload bytes — never registered as valid by path-existence alone.
"""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import text

from soloring.api.schemas.projects import ProjectCreate
from soloring.api.schemas.references import ReferenceInput
from soloring.api.schemas.shots import ShotCreate, ShotPatch
from soloring.assets.blob_store import BlobStore
from soloring.domain import projects, references, revisions, shots
from soloring.domain import shots as shots_svc


async def _seed_blob_content(engine, settings, content: bytes,
                             project_id: str | None = None,
                             ) -> tuple[str, str]:
    """Physical blob bytes + Blob/Asset rows; returns (asset_id, blob_hash)."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from soloring.db.models import Asset, Blob
    from soloring.domain.ids import new_uuid

    bh = hashlib.sha256(content).hexdigest()
    path = BlobStore(settings).path_for_hash(bh)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    aid = new_uuid()
    f = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with f() as s:
        pid = project_id or (await s.execute(
            text("SELECT id FROM projects LIMIT 1")
        )).scalar_one()
        s.add(Blob(hash=bh, path=f"sha256/{bh[:2]}/{bh[2:4]}/{bh}",
                   size_bytes=len(content), detected_media_type=None))
        await s.flush()
        s.add(Asset(id=aid, project_id=pid, blob_hash=bh, kind="reference"))
        await s.commit()
    return aid, bh


async def _seed(factory, engine, settings):
    async with factory() as s:
        pid = (await projects.create_project(s, ProjectCreate(name="P"))).id
        shot = await shots.create_shot(s, pid, ShotCreate(subject="A"))
    aid, bh = await _seed_blob_content(
        engine, settings, b"reference-one", pid,
    )
    async with factory() as s:
        await references.replace_references(
            s, shot.id, [ReferenceInput(asset_id=aid, role="reference")],
        )
    return shot.id, pid, aid, bh


# --- F2: consistent capture snapshot ------------------------------------------------


async def test_capture_revision_never_combines_two_db_states(
    factory, engine, settings, monkeypatch,
):
    shot_id, pid, aid, bh = await _seed(factory, engine, settings)
    old_ref = bh

    # Interleave a writer BETWEEN the shot read and the references read:
    # subject flips A→B and the reference set is replaced atomically after.
    # With the fixed single-snapshot capture, the read that already saw
    # subject A must also see the OLD references — the captured revision is
    # one database state, never a hybrid (audit F2 reproduction).
    import soloring.domain.revisions as revisions_mod

    real_refs = revisions_mod._reference_refs

    async def interleaving_refs(executor, sid):
        async with factory() as s:
            await shots_svc.patch_shot(s, sid, ShotPatch(subject="B"))
        other_aid, _ = await _seed_blob_content(
            engine, settings, b"reference-two",
        )
        async with factory() as s:
            await references.replace_references(
                s, sid,
                [ReferenceInput(asset_id=other_aid, role="reference")],
            )
        return await real_refs(executor, sid)

    monkeypatch.setattr(revisions_mod, "_reference_refs", interleaving_refs)

    async with factory() as s:
        rev = await revisions.capture_revision(s, shot_id)

    snap = json.loads(rev.snapshot_json)
    # Deterministic under the fix: the snapshot opened before the write, so
    # the whole OLD state is captured. (The invariant under test is: subject
    # and references always come from the same state — no A+new or B+old.)
    assert snap["intent"]["subject"] == "A"
    assert [r["blob_hash"] for r in snap["references"]] == [old_ref]


# --- F3: corrupt pre-existing blob repaired ------------------------------------------


async def test_corrupt_preexisting_blob_repaired_from_verified_upload(
    settings, tmp_path,
):
    store = BlobStore(settings)
    good = b"\x89PNG\r\n\x1a\n" + b"good-bytes" * 8
    bh = hashlib.sha256(good).hexdigest()

    # Pre-existing CORRUPT bytes at the content-addressed path, no DB row
    # (audit F3 reproduction).
    final = store.path_for_hash(bh)
    final.parent.mkdir(parents=True, exist_ok=True)
    final.write_bytes(b"corrupt-preexisting-bytes")

    tmp = tmp_path / "upload.tmp"
    tmp.write_bytes(good)
    placed = await store.place(bh, tmp)

    assert placed is True  # we repaired
    assert not tmp.exists()
    assert final.read_bytes() == good
    assert hashlib.sha256(final.read_bytes()).hexdigest() == bh


async def test_verified_preexisting_blob_converges(settings, tmp_path):
    store = BlobStore(settings)
    good = b"already-correct"
    bh = hashlib.sha256(good).hexdigest()
    final = store.path_for_hash(bh)
    final.parent.mkdir(parents=True, exist_ok=True)
    final.write_bytes(good)

    tmp = tmp_path / "upload.tmp"
    tmp.write_bytes(good)
    assert await store.place(bh, tmp) is False  # converged, temp discarded
    assert final.read_bytes() == good
