"""Comfy input materialization (M5A-4; M5 plan §25-§31, as amended).

Boundary: SoloRing Blob identity → validated, attempt-isolated remote Comfy
input reference. Nothing here touches the DB, worker ownership, submission
state, /prompt, or /view. Materialization is ordered BEFORE submission
authority is ever consumed, so an upload failure can never create submission
ambiguity (remote orphan inputs are acceptable; duplicate executions are not).

Ownership split (M5A-4 closure amendment):

    ComfyInputMaterializer
        verifies immutable Blob identity (streamed, bounded memory)
        chooses attempt namespace + requested name
    ComfyUploader
        streams the VERIFIED, SAME content-addressed file through the
        transport — the seam receives a source_path, never whole-file bytes

The uploader opens the same Blob path read-only; the materializer re-verifies
identity AFTER transport (stat size + hash) so a source that changed or
vanished between verification and upload is detected rather than silently
shipping different bytes under a verified name.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from soloring.errors import ErrorCode, SoloRingError

# Comfy subfolder length bound (transport contract safety margin).
NAMESPACE_MAX = 96
_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]")
_CONTROL = {chr(c) for c in range(32)} | {chr(127)}
FILENAME_MAX = 190  # namespace-independent safety bound for returned names

_EXT_BY_TYPE = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
}

CHUNK = 1 << 20  # 1 MiB — verification + transport chunk size


class InputMaterializationError(SoloRingError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.COMFY_INPUT_UPLOAD_FAILED, message,
                         status_code=500)


class InputReferenceInvalid(SoloRingError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.COMFY_INPUT_REFERENCE_INVALID, message,
                         status_code=500)


@dataclass(frozen=True)
class CapturedInput:
    """One captured GenerationInput binding (logical identity)."""

    input_key: str
    position: int
    asset_id: str
    blob_hash: str


@dataclass(frozen=True)
class MaterializedComfyInput:
    """One logical input binding resolved to a remote reference.

    Provenance mapping (input_key/position/asset/blob) is retained so
    translation never loses the captured identity; `remote_name`/`subfolder`
    are the authoritative executor-local reference.
    """

    input_key: str
    position: int
    asset_id: str
    blob_hash: str
    remote_name: str
    subfolder: str


@dataclass(frozen=True)
class MaterializationOutcome:
    """Explicit retry semantics (M5 plan §30)."""

    materialized: tuple[MaterializedComfyInput, ...]
    retry_convergent: bool  # proven idempotent/convergent, or explicitly not


class ComfyUploader(Protocol):
    """Streaming transport seam (M5A-4 closure amendment).

    Receives the VERIFIED content-addressed source path plus the requested
    remote identity — never whole-file bytes. Implementations stream the file
    through the transport (multipart/chunked) and return the normalized
    server-assigned reference.
    """

    async def upload(
        self,
        *,
        source_path: Path,
        filename: str,
        subfolder: str,
    ) -> tuple[str, str]:
        ...


class ComfyInputMaterializer(Protocol):
    async def materialize(
        self,
        *,
        generation_id: str,
        attempt_id: str,
        inputs: Sequence[CapturedInput],
    ) -> MaterializationOutcome:
        ...


def attempt_namespace(generation_id: str, attempt_id: str) -> str:
    """Deterministic, safe, bounded isolation namespace (M5 §27)."""
    raw = f"soloring_gen_{generation_id}_att_{attempt_id}"
    safe = _UNSAFE.sub("", raw)
    if len(safe) > NAMESPACE_MAX:
        safe = safe[:NAMESPACE_MAX]
    if not safe:
        raise InputReferenceInvalid("empty attempt namespace")
    return safe


def requested_filename(blob_hash: str, detected_media_type: str | None) -> str:
    """Requested remote name derives from Blob identity only (M5 §27)."""
    ext = _EXT_BY_TYPE.get(detected_media_type or "", ".bin")
    return f"{blob_hash}{ext}"


def validate_returned_reference(
    name: str, subfolder: str, expected_namespace: str
) -> None:
    """Hostile validation of the normalized upload response (M5 §29)."""
    if not name or len(name) > FILENAME_MAX:
        raise InputReferenceInvalid(f"unsafe returned filename: {name!r}")
    if any(ch in _CONTROL for ch in name):
        raise InputReferenceInvalid("control characters in returned filename")
    if "/" in name or "\\" in name or name in (".", ".."):
        raise InputReferenceInvalid(f"returned filename is not basename-only: {name!r}")
    if subfolder != expected_namespace:
        raise InputReferenceInvalid(
            f"returned subfolder {subfolder!r} escapes the attempt namespace "
            f"{expected_namespace!r}"
        )


def _sniff_type(head: bytes) -> str | None:
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return None


def _hash_stream(path: Path) -> tuple[str, bytes]:
    """Bounded-memory chunked hashing; returns (hash, head-bytes)."""
    hasher = hashlib.sha256()
    head_chunk = b""
    with open(path, "rb") as fh:
        first = fh.read(CHUNK)
        head_chunk = first[:16]
        hasher.update(first)
        while True:
            chunk = fh.read(CHUNK)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest(), head_chunk


class HttpInputMaterializer:
    """Streams immutable Blob bytes into Comfy via the streaming uploader seam.

    Blob identity is verified (streamed, bounded memory) before transport;
    the uploader receives the same verified path; identity is re-verified
    after transport so any change between the two passes is detected.
    """

    def __init__(
        self,
        uploader: ComfyUploader,
        blob_path_for_hash,  # Callable[[str], Path] — the Blob store is authority
        retry_convergent: bool = False,
    ) -> None:
        self._uploader = uploader
        self._blob_path_for_hash = blob_path_for_hash
        self.retry_convergent = retry_convergent

    async def materialize(
        self,
        *,
        generation_id: str,
        attempt_id: str,
        inputs: Sequence[CapturedInput],
    ) -> MaterializationOutcome:
        namespace = attempt_namespace(generation_id, attempt_id)

        resolved: dict[str, tuple[str, str]] = {}
        upload_lock = asyncio.Lock()

        async def upload_blob(blob_hash: str) -> tuple[str, str]:
            if blob_hash in resolved:
                return resolved[blob_hash]
            async with upload_lock:
                if blob_hash in resolved:
                    return resolved[blob_hash]
                path = self._blob_path_for_hash(blob_hash)
                name, subfolder = await self._upload_verified(
                    path, blob_hash, namespace
                )
                resolved[blob_hash] = (name, subfolder)
                return resolved[blob_hash]

        unique_hashes = list(dict.fromkeys(i.blob_hash for i in inputs))
        await asyncio.gather(*(upload_blob(h) for h in unique_hashes))

        ordered = sorted(inputs, key=lambda i: (i.input_key, i.position))
        materialized = tuple(
            MaterializedComfyInput(
                input_key=i.input_key,
                position=i.position,
                asset_id=i.asset_id,
                blob_hash=i.blob_hash,
                remote_name=resolved[i.blob_hash][0],
                subfolder=resolved[i.blob_hash][1],
            )
            for i in ordered
        )
        return MaterializationOutcome(
            materialized=materialized,
            retry_convergent=self.retry_convergent,
        )

    async def _upload_verified(
        self, path: Path, blob_hash: str, namespace: str
    ) -> tuple[str, str]:
        """Verify identity (bounded memory) → streaming transport →
        re-verify identity → validate the returned reference."""
        content_hash, head = await asyncio.to_thread(_hash_stream, path)
        if content_hash != blob_hash:
            raise InputReferenceInvalid(
                f"Blob bytes at {path.name} no longer hash to the captured "
                "identity"
            )
        ext = _EXT_BY_TYPE.get(_sniff_type(head), ".bin")
        requested = f"{blob_hash}{ext}"

        attempts = 2 if self.retry_convergent else 1
        last_error: Exception | None = None
        for _ in range(attempts):
            try:
                name, subfolder = await self._uploader.upload(
                    source_path=path, filename=requested, subfolder=namespace
                )
                # The source must still be the verified identity AFTER
                # transport: detect a vanished/changed Blob, never ship
                # different bytes under a verified name silently.
                post_hash, _ = await asyncio.to_thread(_hash_stream, path)
                if post_hash != blob_hash:
                    raise InputReferenceInvalid(
                        f"Blob {blob_hash[:12]}… changed between verification "
                        "and transport"
                    )
                validate_returned_reference(name, subfolder, namespace)
                return name, subfolder
            except SoloRingError:
                raise  # validation failures are never retried
            except Exception as exc:  # transport failure
                last_error = exc
        raise InputMaterializationError(
            f"upload failed for {blob_hash[:12]}… "
            f"(retry_convergent={self.retry_convergent}): {last_error}"
        )
