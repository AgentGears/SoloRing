"""BlobStore (plan §17, §24, §45).

Path derivation is synchronous (no I/O). Physical placement is atomic via
``os.replace`` on the same filesystem (validated at startup by the engine).
The database stores RELATIVE paths; the physical path for serving is always
derived from the validated hash, never from stored or client-supplied paths.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from pathlib import Path

from soloring.settings import Settings

log = logging.getLogger("soloring.assets.blobs")

# Plan §45:  data/blobs/sha256/aa/bb/<full-hash>
BLOB_TREE = "sha256"


class BlobStore:
    """Derives Blob paths from content hashes; owns atomic placement."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.blob_dir = settings.blob_dir
        self.tmp_dir = settings.tmp_dir

    @staticmethod
    def validate_hash(blob_hash: str) -> bool:
        """True iff `blob_hash` is exactly 64 lowercase hex chars (plan §46)."""
        return len(blob_hash) == 64 and set(blob_hash) <= set("0123456789abcdef")

    def relative_path_for_hash(self, blob_hash: str) -> str:
        """The PERSISTED path form: sha256/aa/bb/<full-hash> (plan §17.2)."""
        if not self.validate_hash(blob_hash):
            raise ValueError(f"invalid blob hash: {blob_hash!r}")
        return f"{BLOB_TREE}/{blob_hash[0:2]}/{blob_hash[2:4]}/{blob_hash}"

    def path_for_hash(self, blob_hash: str) -> Path:
        """Physical Blob path: <blob_dir>/sha256/<h[0:2]>/<h[2:4]>/<hash> (§45)."""
        if not self.validate_hash(blob_hash):
            raise ValueError(f"invalid blob hash: {blob_hash!r}")
        return (
            self.blob_dir
            / BLOB_TREE
            / blob_hash[0:2]
            / blob_hash[2:4]
            / blob_hash
        )

    def tmp_path(self) -> Path:
        """A fresh, traversal-safe temp path under data/tmp for an upload (§43).

        The name is entirely server-generated (uuid hex) — no caller-supplied
        component is ever embedded in the path, so it cannot escape data/tmp.
        """
        import uuid

        return self.tmp_dir / f"{uuid.uuid4().hex}.tmp"

    @staticmethod
    def hash_bytes(data: bytes) -> str:
        """SHA-256 of bytes (plan §24, §43)."""
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def _hash_file(path: Path) -> str | None:
        """Hash an existing file's bytes in bounded chunks (re-audit R8);
        None when missing/locked. with-open closes the handle immediately: a
        concurrent os.replace on Windows fails while a read handle is open
        (WinError 32/5), so the read must not outlive the call. A multi-GB
        pre-existing Blob must never be allocated whole in memory just to be
        verified.
        """
        hasher = hashlib.sha256()
        try:
            with open(path, "rb") as fh:
                while True:
                    chunk = fh.read(1 << 20)
                    if not chunk:
                        break
                    hasher.update(chunk)
            return hasher.hexdigest()
        except FileNotFoundError:
            return None
        except PermissionError:
            return None  # locked by a concurrent placer; caller retries

    async def place(self, blob_hash: str, temp_path: Path) -> bool:
        """Atomically place a verified temp file at the Blob's final path (§24).

        The caller must possess INDEPENDENTLY VERIFIED bytes for exactly
        `blob_hash`. An existing destination is trusted only after hashing
        it: a corrupt pre-existing file at a content-addressed path is
        REPAIRED from the verified temp bytes (audit F3) — the path is the
        identity, so bad bytes at that path are a storage-integrity defect
        to fix, never a state to register as valid. Returns True when we
        placed/repaired the file, False when an identical verified file
        already existed.
        """
        final = self.path_for_hash(blob_hash)

        def _place() -> bool:
            final.parent.mkdir(parents=True, exist_ok=True)
            existing_hash = BlobStore._hash_file(final)
            if existing_hash == blob_hash:
                temp_path.unlink(missing_ok=True)
                return False  # converge on the identical, verified winner
            if existing_hash is not None:
                log.error(
                    "BLOB REPAIR: corrupt bytes at content-addressed path %s "
                    "(hashes to %s…); restoring from verified upload bytes",
                    final.name, existing_hash[:12],
                )
            if _replace_with_retry(temp_path, final, blob_hash):
                return True
            raise PermissionError(
                f"could not place blob {blob_hash} after retries"
            )

        def _replace_with_retry(tmp: Path, dst: Path, want: str) -> bool:
            for attempt in range(5):
                try:
                    os.replace(tmp, dst)
                    return True
                except PermissionError:
                    now = BlobStore._hash_file(dst)
                    if now == want:
                        return True  # concurrent verified winner converged
                    time.sleep(0.02 * (attempt + 1))
            return False

        return await asyncio.to_thread(_place)
