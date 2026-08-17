"""Output import authority (v0.1 §81-§84) — idempotent by output identity.

Staged executor output is UNTRUSTED material until this module verifies and
persists it. Import converts staged bytes into immutable content-addressed
Blobs plus provenance Assets and Takes with deterministic output keys.

M3C hardening:
  * manifest conformance — the staged set must EXACTLY match the manifest's
    expected outputs (missing / extra / cardinality violations rejected);
  * staging containment — staged paths must live inside the given attempt
    staging directory (no traversal, no symlink escape), checked with real
    path RELATIVE-TO semantics (audit F6: a string-prefix test admits
    same-prefix sibling directories);
  * boundary checkpoints — every durable boundary is a named checkpoint so
    crash-matrix tests can inject death at each point and prove convergence;
  * concurrent convergence — duplicate Take creation races resolve through
    the unique constraint (never a bare check-then-insert).

Audit-remediation hardening:
  * OWNERSHIP-FENCED PUBLICATION (F1) — when a worker_id is supplied, the
    lease + Generation ownership are verified INSIDE the same BEGIN
    IMMEDIATE transaction that mints Take/Asset state. A worker that lost
    authority cannot publish: worker-originated durable mutations are
    fenced exactly like every other lifecycle write.
  * BOUNDED-MEMORY HASHING (F7) — staged outputs are hashed in bounded
    chunks; only the media-detection prefix is retained, so importing a
    multi-gigabyte output never allocates the file size in RAM.

Idempotency: re-importing the same (generation_id, output_key) creates
nothing — Take uniqueness plus constraint-based convergence guarantee no
duplicates on retry/reconnect/replay (§82, F26).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from soloring.assets.blob_store import BlobStore
from soloring.db.models import Generation
from soloring.domain.ids import new_uuid
from soloring.errors import ErrorCode, SoloRingError

log = logging.getLogger("soloring.generation.import")

_HEAD_BYTES = 16
_HASH_CHUNK = 1 << 20  # 1 MiB — hashing and media detection are chunked (F7)

# Durable boundaries, in execution order (M3C crash matrix):
#   stage_present -> hashed -> blob_placed -> blob_row -> take_inserted
#   -> asset_inserted -> committed
BOUNDARIES = (
    "stage_present",
    "hashed",
    "blob_placed",
    "blob_row",
    "take_inserted",
    "asset_inserted",
    "committed",
)


class _Checkpoint:
    """Named durable boundary. Tests monkeypatch `fire` to inject crashes."""

    async def fire(self, name: str) -> None:
        return None


checkpoint = _Checkpoint()


class ImportFailure(SoloRingError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.OUTPUT_INVALID, message, status_code=500)


class PublicationNotFenced(SoloRingError):
    """The publishing worker no longer holds authority (audit F1)."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            ErrorCode.GENERATION_OWNERSHIP_LOST,
            f"publication refused: {detail}",
            status_code=500,
        )


def expected_output_keys(outputs) -> list[str]:
    keys: list[str] = []
    for out in outputs:
        for index in range(out.expected_count):
            keys.append(f"{out.name}:{index}")
    return keys


def _validate_staged_set(
    staged: list, outputs, staging_directory: Path
) -> None:
    """Hostile-input validation before ANY durable effect (M3C §6, M4 §6)."""
    staged_dir = staging_directory.resolve()

    expected = expected_output_keys(outputs)
    got = [out.output_key for out in staged]
    if sorted(got) != sorted(expected):
        missing = sorted(set(expected) - set(got))
        extra = sorted(set(got) - set(expected))
        raise ImportFailure(
            f"Staged outputs do not match the captured contract: "
            f"missing={missing} unexpected={extra} expected={expected}"
        )
    by_name = {o.name: o for o in outputs}
    for out in staged:
        resolved = out.path.resolve()
        # Real containment (audit F6): a resolved path must be INSIDE the
        # staging directory — a same-prefix sibling
        # (/staging/G/attempt_evil/…) passes a naive startswith check.
        try:
            resolved.relative_to(staged_dir)
        except ValueError:
            raise ImportFailure(
                f"Staged output {out.output_key} path escapes the attempt "
                "staging directory."
            )
        name = out.output_key.rsplit(":", 1)[0]
        decl = by_name.get(name)
        if decl is not None and out.kind != decl.kind:
            raise ImportFailure(
                f"Staged output {out.output_key} declares kind {out.kind!r}; "
                f"captured contract requires {decl.kind!r}."
            )


async def _hash_and_detect(path: Path) -> tuple[str, int, str | None]:
    """Bounded-memory hash + media sniff (audit F7): chunked reads, only the
    16-byte media prefix retained — importing a multi-gigabyte staged output
    never allocates the file size in RAM."""
    hasher = hashlib.sha256()

    def _read() -> tuple[str, int, bytes]:
        size = 0
        prefix = b""
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(_HASH_CHUNK)
                if not chunk:
                    break
                if size == 0:
                    prefix = chunk[:_HEAD_BYTES]
                hasher.update(chunk)
                size += len(chunk)
        return hasher.hexdigest(), size, prefix

    digest, size, prefix = await asyncio.to_thread(_read)
    if size == 0:
        raise ImportFailure(f"Staged output {path.name} is empty.")
    from soloring.assets.media import detect_media_type

    return digest, size, detect_media_type(prefix)


async def import_staged_outputs(
    session_factory: async_sessionmaker[AsyncSession],
    blob_store: BlobStore,
    generation: Generation,
    staged: list,
    expected_outputs=None,
    staging_directory: Path | None = None,
    worker_id: str | None = None,
    attempt_id: str | None = None,
) -> list[str]:
    """Import all staged outputs; returns the output_keys now durable.

    TWO-PHASE (re-audit R4): phase one preflights the ENTIRE staged set —
    hash, media detection, captured-contract media compatibility, and
    physical Blob placement (orphan-tolerant) — before ANY Take/Asset is
    minted. A later output's invalidity can therefore never leave a partial
    provenance graph from an earlier output. Phase two publishes under the
    ownership fence, one convergent transaction per output.

    `worker_id` + `attempt_id` (audits F1/R7): REQUIRED together for
    worker-originated publication. The fence verifies, inside the same
    BEGIN IMMEDIATE transaction that inserts Take/Asset state: the singleton
    lease, the Generation owner, the CURRENT execution attempt, and the
    `importing` lifecycle state. Omitting them is legal only for non-worker
    direct use (tests).
    """
    if worker_id is not None and attempt_id is None:
        raise ImportFailure("worker publication requires the attempt_id")

    if expected_outputs is not None and staging_directory is not None:
        _validate_staged_set(staged, expected_outputs, staging_directory)

    engine = session_factory.kw.get("bind")
    compat = {o.name: o for o in expected_outputs} if expected_outputs else {}

    # --- phase 1: preflight the complete set (no provenance writes) --------
    preflight: list[dict] = []
    for out in staged:
        await checkpoint.fire("stage_present")
        blob_hash, size, detected = await _hash_and_detect(out.path)
        await checkpoint.fire("hashed")
        decl = compat.get(out.output_key.rsplit(":", 1)[0])
        if (
            decl is not None
            and decl.accepted_media_types is not None
            and detected not in decl.accepted_media_types
        ):
            raise ImportFailure(
                f"Output {out.output_key}: detected media {detected!r} is not "
                "compatible with the captured contract "
                f"{list(decl.accepted_media_types)}."
            )
        relative_path = blob_store.relative_path_for_hash(blob_hash)
        await blob_store.place(blob_hash, out.path)
        await checkpoint.fire("blob_placed")
        preflight.append({
            "output_key": out.output_key, "blob_hash": blob_hash,
            "size": size, "detected": detected,
            "relative_path": relative_path,
        })

    # --- phase 2: fenced publication, one convergent unit per output -------
    imported_keys: list[str] = []
    for item in preflight:
        out_key = item["output_key"]
        blob_hash = item["blob_hash"]
        relative_path = item["relative_path"]
        async with engine.connect() as conn:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                if worker_id is not None:
                    await _verify_publication_fenced(
                        conn, worker_id, generation.id, attempt_id
                    )

                await conn.execute(
                    text(
                        "INSERT OR IGNORE INTO blobs "
                        "(hash, path, size_bytes, detected_media_type) "
                        "VALUES (:h, :p, :s, :m)"
                    ),
                    {"h": blob_hash, "p": relative_path, "s": item["size"],
                     "m": item["detected"]},
                )
                await checkpoint.fire("blob_row")

                take_id = new_uuid()
                inserted = (await conn.execute(
                    text(
                        "INSERT INTO takes (id, shot_id, generation_id, "
                        "output_key) VALUES (:id, :sid, :gid, :ok) "
                        "ON CONFLICT (generation_id, output_key) DO NOTHING"
                    ),
                    {"id": take_id, "sid": generation.shot_id,
                     "gid": generation.id, "ok": out_key},
                )).rowcount

                if inserted == 0:
                    # Concurrent importer won the (generation, output_key)
                    # race: converge on the winner instead of failing (M3C §5).
                    await conn.commit()
                    imported_keys.append(out_key)
                    continue

                await checkpoint.fire("take_inserted")

                project_id = (await conn.execute(
                    text("SELECT project_id FROM shots WHERE id = :sid"),
                    {"sid": generation.shot_id},
                )).scalar_one()
                await conn.execute(
                    text(
                        "INSERT INTO assets (id, project_id, take_id, "
                        "blob_hash, kind) VALUES "
                        "(:id, :pid, :tid, :bh, 'output')"
                    ),
                    {"id": new_uuid(), "pid": project_id, "tid": take_id,
                     "bh": blob_hash},
                )
                await checkpoint.fire("asset_inserted")
                log.info(
                    "IMPORT: generation %s output %s -> take %s blob %s",
                    generation.id, out_key, take_id, blob_hash,
                )
                imported_keys.append(out_key)
                await conn.commit()
                await checkpoint.fire("committed")
            except Exception:
                import contextlib

                with contextlib.suppress(Exception):
                    await conn.rollback()
                raise

    return imported_keys


async def _verify_publication_fenced(
    conn, worker_id: str, generation_id: str, attempt_id: str | None = None
) -> None:
    """Full publication fence INSIDE the publication transaction (F1, R7).

    The caller holds BEGIN IMMEDIATE. Publication authority belongs to the
    worker + Generation + CURRENT execution attempt + importing lifecycle
    state, all verified in this one transaction: a stale worker, a recycled
    attempt, or a row that already left importing can never mint Take/Asset
    state.
    """
    from soloring.worker.ownership import LEASE_NAME

    lease = (await conn.execute(
        text("SELECT worker_id FROM worker_leases WHERE name = :n"),
        {"n": LEASE_NAME},
    )).one_or_none()
    if lease is None or lease.worker_id != worker_id:
        raise PublicationNotFenced("worker lease authority lost")
    row = (await conn.execute(
        text("SELECT worker_id, status, attempt_id FROM generations "
             "WHERE id = :g"),
        {"g": generation_id},
    )).one_or_none()
    if row is None:
        raise PublicationNotFenced("generation vanished")
    if row.worker_id != worker_id:
        raise PublicationNotFenced("generation ownership lost")
    if row.status in ("succeeded", "failed", "interrupted", "cancelled"):
        raise PublicationNotFenced(
            f"generation already terminal ({row.status})"
        )
    if attempt_id is not None and row.attempt_id != attempt_id:
        current = (row.attempt_id or "none")[:8]
        raise PublicationNotFenced(
            f"stale attempt {attempt_id[:8]}… (current {current}…)"
        )
    if row.status != "importing":
        raise PublicationNotFenced(
            f"generation not in importing state ({row.status})"
        )
