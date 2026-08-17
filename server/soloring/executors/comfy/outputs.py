"""Comfy output discovery + retrieval (M5A-9; M5 plan §55-§60).

Three output identities stay explicit (M5A-9 §1):

    logical output        captured M4 contract (name/kind/count/media/keys)
    remote Comfy output   historical manifest binding + normalized history ref
    durable SoloRing      captured deterministic output_key (video:0)

Discovery (``resolve_comfy_outputs``) is PURE: no DB, network, filesystem,
installed workflow, staging, or import. "Extra output" means excess files
UNDER A DECLARED binding — unrelated nodes producing files are ignored, so
realistic graphs with diagnostics/previews stay valid.

Retrieval validates /view references lexically (type=output exact), streams
in bounded chunks to a unique temp, enforces the ACTUAL byte count against
the configured max, retries from byte zero, and atomically finalizes into
deterministic output_key-named staging targets.

Comfy code ends at validated ``StagedOutput`` production; the existing
M3C-hardened importer remains the publication authority.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from soloring.errors import ErrorCode, SoloRingError
from soloring.executors.base import StagedOutput
from soloring.executors.comfy.models import NormalizedHistoryRecord
from soloring.workflows.manifest import ManifestDocument

_CONTROL = {chr(c) for c in range(32)} | {chr(127)}
FILENAME_MAX = 190
SUBFOLDER_MAX = 256

DEFAULT_MAX_OUTPUT_BYTES = 8 * 1024 * 1024 * 1024  # 8 GiB
CHUNK = 1 << 20  # 1 MiB


class OutputInvalid(SoloRingError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.OUTPUT_INVALID, message, status_code=500)


class OutputFetchFailed(SoloRingError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.COMFY_OUTPUT_FETCH_FAILED, message,
                         status_code=500)


@dataclass(frozen=True)
class CapturedOutputContract:
    """The M4-captured logical output contract entries."""

    name: str
    kind: str
    expected_count: int
    accepted_media_types: tuple[str, ...] | None

    @property
    def output_keys(self) -> list[str]:
        return [f"{self.name}:{i}" for i in range(self.expected_count)]


@dataclass(frozen=True)
class ResolvedComfyOutput:
    output_key: str
    logical_name: str
    expected_kind: str
    accepted_media_types: tuple[str, ...] | None
    filename: str
    subfolder: str
    type: str = "output"


def resolve_comfy_outputs(
    *,
    captured_outputs: list[CapturedOutputContract],
    manifest: ManifestDocument,
    history: NormalizedHistoryRecord,
) -> list[ResolvedComfyOutput]:
    """Pure discovery: contract + historical bindings + normalized history →
    the exact expected remote references.

    Unrelated history outputs are ignored; cardinality is enforced per
    DECLARED binding; multi-output indexing is deterministic (normalized
    reference order); captured-contract/manifest consistency is required.
    """
    resolved: list[ResolvedComfyOutput] = []
    by_node_field: dict[tuple[str, str], list] = {}
    for ref in history.outputs:
        by_node_field.setdefault((ref.node, ref.output_field), []).append(ref)

    captured_names = {c.name for c in captured_outputs}
    for name, decl in manifest.outputs.items():
        if name not in captured_names:
            raise OutputInvalid(
                f"historical manifest maps output {name!r} but the captured "
                "contract declares no such output (binding/spec inconsistency)"
            )

    for contract in captured_outputs:
        decl = manifest.outputs.get(contract.name)
        if decl is None:
            raise OutputInvalid(
                f"captured output {contract.name!r} has no historical "
                "manifest binding"
            )
        if not decl.node:
            raise OutputInvalid(
                f"output {contract.name!r}: manifest declares no node binding"
            )
        refs = by_node_field.get((decl.node, decl.field or ""), [])
        if len(refs) != contract.expected_count:
            raise OutputInvalid(
                f"output {contract.name!r}: declared cardinality "
                f"{contract.expected_count}, history has {len(refs)} files "
                f"on node {decl.node!r}/{decl.field!r}"
            )
        ordered = sorted(
            refs, key=lambda r: (r.filename, r.subfolder)
        )  # M5A-2-normalized deterministic ordering
        for index, ref in enumerate(ordered):
            resolved.append(
                ResolvedComfyOutput(
                    output_key=f"{contract.name}:{index}",
                    logical_name=contract.name,
                    expected_kind=contract.kind,
                    accepted_media_types=contract.accepted_media_types,
                    filename=ref.filename,
                    subfolder=ref.subfolder,
                    type="output",
                )
            )

    expected_total = sum(c.expected_count for c in captured_outputs)
    if len(resolved) != expected_total:
        raise OutputInvalid("resolved output set is incomplete")
    resolved.sort(key=lambda r: r.output_key)
    return resolved


# --- lexical /view reference validation (M5A-9 §6-§7) -------------------------


def validate_output_reference(ref: ResolvedComfyOutput) -> None:
    """Structural validation BEFORE any /view request. Lexical only — SoloRing
    never resolves the path against a local Comfy output root."""
    if ref.type != "output":
        raise OutputInvalid(
            f"output {ref.output_key}: remote type {ref.type!r} != 'output'"
        )
    validate_filename(ref.filename)
    validate_subfolder(ref.subfolder)


def validate_filename(filename: str) -> None:
    if not filename or len(filename) > FILENAME_MAX:
        raise OutputInvalid(f"unsafe output filename: {filename!r}")
    if any(ch in _CONTROL for ch in filename):
        raise OutputInvalid("control characters in output filename")
    if "/" in filename or "\\" in filename or filename in (".", ".."):
        raise OutputInvalid(
            f"output filename is not a bounded basename: {filename!r}"
        )
    # Absolute detection for the exotic windows form "C:..." is covered by the
    # drive-letter check; leading "/" by the separator check above.
    if re.match(r"^[A-Za-z]:", filename):
        raise OutputInvalid(f"absolute output filename: {filename!r}")


def validate_subfolder(subfolder: str) -> None:
    if subfolder == "":
        return
    if len(subfolder) > SUBFOLDER_MAX:
        raise OutputInvalid("oversized output subfolder")
    if any(ch in _CONTROL for ch in subfolder):
        raise OutputInvalid("control characters in output subfolder")
    if subfolder.startswith("/") or subfolder.startswith("\\"):
        raise OutputInvalid("absolute output subfolder")
    if re.match(r"^[A-Za-z]:", subfolder):
        raise OutputInvalid("drive-letter output subfolder")
    if "\\" in subfolder:
        raise OutputInvalid("backslash in output subfolder")
    parts = subfolder.split("/")
    for part in parts:
        if part in (".", ".."):
            raise OutputInvalid(f"traversal component in output subfolder: {subfolder!r}")
        if part == "":
            raise OutputInvalid(
                f"empty interior path component in output subfolder: {subfolder!r}"
            )


# --- streamed retrieval (M5A-9 §8-§11) ------------------------------------------


def stage_target(staging_dir: Path, output_key: str) -> Path:
    """Deterministic staging target named by output_key, never the Comfy
    filename (§8): video:0 → video-0.staged."""
    safe = output_key.replace(":", "-")
    return staging_dir / f"{safe}.staged"


def stage_transfer_temp(staging_dir: Path, output_key: str) -> Path:
    """Unique per-transfer temp (§11: never a shared fixed .tmp)."""
    safe = output_key.replace(":", "-")
    staging_dir.mkdir(parents=True, exist_ok=True)
    return staging_dir / f"{safe}.download-{uuid.uuid4().hex[:8]}.tmp"


def _hash_path_chunked(path: Path) -> str:
    """Chunked SHA-256 of a staged file (bounded memory)."""
    hasher = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(CHUNK)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _publish_no_clobber(temp: Path, target: Path,
                        temp_identity: str) -> str:
    """Genuinely atomic no-clobber publication (third re-gate).

    ``os.link`` is the interlock: it either lands the COMPLETE verified
    bytes at the target atomically (winner) or fails with FileExistsError
    (loser) — unlike exists()-then-replace, there is no window in which
    two finalizers can both observe absence and overwrite each other.
    The hard-linked target appears only ever complete, so a loser's
    identity verification reads finalized bytes by construction.

    Loser path: verify the winner's target identity — identical bytes
    converge (temp discarded by the caller), different bytes are an
    integrity conflict.
    """
    try:
        os.link(temp, target)
        return "placed"
    except FileExistsError:
        if _hash_path_chunked(target) == temp_identity:
            return "converged"
        return "conflict"
    except OSError as exc:
        # FAIL-CLOSED (final M5A re-gate): an overwrite-capable fallback
        # (replace-then-verify) reintroduces the TOCTOU clobber — the final
        # writer observes its own bytes and cannot detect the divergence it
        # caused. If the staging filesystem cannot provide atomic no-clobber
        # publication, publication fails loudly instead.
        raise OutputFetchFailed(
            f"staging filesystem does not support atomic no-clobber "
            f"publication for {target.name} ({exc})"
        ) from exc


async def fetch_output_to_staging(
    view_fetch,  # async callable(filename, subfolder) -> bytes (validated type=output)
    resolved: ResolvedComfyOutput,
    staging_dir: Path,
    *,
    max_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    attempts: int = 2,
) -> Path:
    """Bounded streamed download → deterministic stage target.

    Each attempt starts from byte zero with a fresh unique temp; the
    finalized target appears only after one complete, size-valid transfer
    (§10). Zero-byte and over-max outputs are invalid.

    Finalization is CONVERGENT-BY-IDENTITY (re-audit R5, hardened in the
    third re-gate): the transfer is hashed while streaming and publication
    is a genuinely atomic no-clobber (``os.link`` interlock) — identical
    bytes converge (temp discarded), DIFFERENT bytes are an integrity
    conflict (never a silent last-writer-wins overwrite). There is no
    exists()-then-replace window in which two finalizers can both observe
    absence and clobber each other.
    """
    validate_output_reference(resolved)
    target = stage_target(staging_dir, resolved.output_key)

    last_error: Exception | None = None
    for _ in range(attempts):
        temp = stage_transfer_temp(staging_dir, resolved.output_key)
        try:
            hasher = hashlib.sha256()
            total = 0

            def _consume() -> int:
                nonlocal total
                total = 0
                with open(temp, "wb") as fh:
                    while True:
                        chunk = view_fetch(resolved.filename,
                                            resolved.subfolder,
                                            _read=_CHUNK_READ)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > max_bytes:
                            raise OutputInvalid(
                                f"output {resolved.output_key} exceeds "
                                f"max bytes ({max_bytes})"
                            )
                        hasher.update(chunk)
                        fh.write(chunk)
                return total

            # view_fetch is a sync-chunk provider in the transport adapter;
            # see ComfyClient.stream_view for the real HTTP form.
            await asyncio.to_thread(_consume)
            if total == 0:
                raise OutputInvalid(
                    f"output {resolved.output_key} is zero bytes"
                )
            temp_identity = hasher.hexdigest()

            outcome = await asyncio.to_thread(
                _publish_no_clobber, temp, target, temp_identity,
            )
            temp.unlink(missing_ok=True)  # placed = the link IS the content
            if outcome == "converged":
                return target
            if outcome == "conflict":
                raise OutputInvalid(
                    f"staged target {resolved.output_key} already holds "
                    "different verified bytes — concurrent divergent "
                    "transfers are an integrity conflict, never a silent "
                    "overwrite (re-audit R5)"
                )
            return target
        except SoloRingError:
            temp.unlink(missing_ok=True)
            raise  # semantic invalidity is never retried
        except Exception as exc:  # transport failure: retry from zero
            temp.unlink(missing_ok=True)
            last_error = exc
    raise OutputFetchFailed(
        f"/view transfer failed for {resolved.output_key} after "
        f"{attempts} attempts: {last_error}"
    )


_CHUNK_READ = CHUNK  # module-level constant for the sync provider protocol
