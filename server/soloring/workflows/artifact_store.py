"""WorkflowArtifactStore (M5A-3; M5 plan §18-§21 as amended).

Two independently content-addressed historical artifacts:

    data/workflow-artifacts/
    ├── manifests/sha256/aa/bb/<manifest-hash>.json
    └── templates/sha256/aa/bb/<template-hash>.json

Each store preserves the EXACT bytes covered by its existing hash contract
(M4): raw file bytes → SHA-256. Nothing is parsed and reserialized before
placement.

Policies (explicitly chosen, tested):
  * Capture-time corrupt destination: REPAIR from independently verified
    bytes, with a high-severity integrity log (mirrors the M1D Blob-repair
    philosophy: capture possesses verified bytes for exactly that hash).
  * Historical retrieval: MISSING on absent bytes, INTEGRITY on hash
    mismatch — NEVER a fallback to the installed mutable workflow.

Coherent-pair capture (M5A-3 closure): the installed workflow directory
carries a workflow-package.json COMMIT DESCRIPTOR naming the manifest and
template content hashes of exactly one release. Capture reads the descriptor,
reads both sources, verifies them against the descriptor's declared hashes,
validates the pair, then re-reads the descriptor and requires it unchanged.
During a non-atomic installation update (M1/T2 or M2/T1 intermediates),
capture therefore either resolves one COMPLETE release or fails — it can
never certify a hybrid, even a structurally compatible one, because coherence
derives from the declared hash pair, not from file stability across reads.

This module is storage/validation only: no DB, no sessions, no worker
imports, no database transaction is ever open during its file I/O.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from soloring.errors import ErrorCode, SoloRingError
from soloring.settings import Settings

log = logging.getLogger("soloring.workflows.artifacts")

_HEX = set("0123456789abcdef")


class ArtifactMissing(SoloRingError):
    def __init__(self, kind: str, content_hash: str) -> None:
        super().__init__(
            {
                "manifests": ErrorCode.WORKFLOW_MANIFEST_MISSING,
                "templates": ErrorCode.COMFY_TEMPLATE_MISSING,
            }[kind],
            f"Historical workflow {kind} {content_hash} is missing from the "
            "artifact store.",
            status_code=500,
        )


class ArtifactIntegrity(SoloRingError):
    def __init__(self, kind: str, content_hash: str) -> None:
        super().__init__(
            {
                "manifests": ErrorCode.WORKFLOW_MANIFEST_INTEGRITY,
                "templates": ErrorCode.COMFY_TEMPLATE_INTEGRITY,
            }[kind],
            f"Historical workflow {kind} {content_hash} failed integrity "
            "verification.",
            status_code=500,
        )


class IncoherentCapture(SoloRingError):
    """The installed workflow package is not a coherent release (M5A-3)."""

    def __init__(self, what: str) -> None:
        super().__init__(
            ErrorCode.WORKFLOW_VALIDATION_FAILED,
            f"Installed workflow package incoherent ({what}); refusing to "
            "capture a hybrid manifest/template pair.",
            status_code=503,
        )


@dataclass(frozen=True)
class CapturedWorkflowArtifacts:
    manifest_hash: str
    manifest_bytes: bytes
    workflow_template_hash: str
    template_bytes: bytes


def _validate_hash(content_hash: str, kind: str) -> str:
    if len(content_hash) != 64 or not set(content_hash) <= _HEX:
        raise SoloRingError(
            ErrorCode.WORKFLOW_VALIDATION_FAILED,
            f"Invalid {kind} artifact hash: {content_hash!r}",
            status_code=500,
        )
    return content_hash


class WorkflowArtifactStore:
    def __init__(self, settings: Settings) -> None:
        self._root = Path(settings.data_dir) / "workflow-artifacts"

    def _path(self, kind: str, content_hash: str) -> Path:
        _validate_hash(content_hash, kind)
        return (
            self._root / kind / "sha256" / content_hash[0:2] / content_hash[2:4]
            / f"{content_hash}.json"
        )

    # --- capture -----------------------------------------------------------

    async def capture_package(
        self, package_path: Path, manifest_path: Path, template_path: Path
    ) -> CapturedWorkflowArtifacts:
        """Coherent capture of one COMPLETE installed release (M5A-3 closure).

        workflow-package.json is the pair-level commit marker: it names the
        manifest and template content hashes of exactly one release. Capture
        resolves the artifacts the DESCRIPTOR declares — a non-atomic update
        that has written only one of M2/T2 leaves the descriptor still
        naming M1/T1, so the stale member fails verification against the
        declared identity and capture rejects the hybrid.
        """
        import json as _json

        def _read_descriptor() -> dict:
            try:
                raw = package_path.read_bytes()
            except FileNotFoundError as exc:
                raise IncoherentCapture(
                    "workflow-package.json is missing"
                ) from exc
            try:
                doc = _json.loads(raw)
            except ValueError as exc:
                raise IncoherentCapture(
                    "workflow-package.json is malformed"
                ) from exc
            if (
                not isinstance(doc, dict)
                or doc.get("schema_version") != 1
                or not isinstance(doc.get("manifest_hash"), str)
                or not isinstance(doc.get("workflow_template_hash"), str)
            ):
                raise IncoherentCapture(
                    "workflow-package.json lacks required fields"
                )
            return doc

        d1 = await asyncio.to_thread(_read_descriptor)
        declared_mh = _validate_hash(d1["manifest_hash"], "manifest")
        declared_th = _validate_hash(d1["workflow_template_hash"], "template")

        manifest_bytes = await asyncio.to_thread(manifest_path.read_bytes)
        template_bytes = await asyncio.to_thread(template_path.read_bytes)
        actual_mh = hashlib.sha256(manifest_bytes).hexdigest()
        actual_th = hashlib.sha256(template_bytes).hexdigest()

        if actual_mh != declared_mh or actual_th != declared_th:
            raise IncoherentCapture(
                "installed manifest/template do not match the release "
                "declared by the package descriptor"
            )

        # Descriptor must not have moved while we read the pair (the update
        # protocol swaps it LAST; catching a swap here means we straddled a
        # release switch).
        d2 = await asyncio.to_thread(_read_descriptor)
        if d1 != d2:
            raise IncoherentCapture(
                "package descriptor changed during capture"
            )

        return CapturedWorkflowArtifacts(
            manifest_hash=declared_mh,
            manifest_bytes=manifest_bytes,
            workflow_template_hash=declared_th,
            template_bytes=template_bytes,
        )

    async def capture_pair(
        self, manifest_path: Path, template_path: Path
    ) -> CapturedWorkflowArtifacts:
        """Legacy stability-guarded capture (M5A-3 original). Prefer
        capture_package(): only the descriptor proves pair coherence."""
        first_manifest = await asyncio.to_thread(manifest_path.read_bytes)
        first_template = await asyncio.to_thread(template_path.read_bytes)
        mh1 = hashlib.sha256(first_manifest).hexdigest()
        th1 = hashlib.sha256(first_template).hexdigest()

        second_manifest = await asyncio.to_thread(manifest_path.read_bytes)
        second_template = await asyncio.to_thread(template_path.read_bytes)
        mh2 = hashlib.sha256(second_manifest).hexdigest()
        th2 = hashlib.sha256(second_template).hexdigest()

        if mh1 != mh2:
            raise IncoherentCapture("manifest source changed mid-capture")
        if th1 != th2:
            raise IncoherentCapture("template source changed mid-capture")

        return CapturedWorkflowArtifacts(
            manifest_hash=mh1,
            manifest_bytes=first_manifest,
            workflow_template_hash=th1,
            template_bytes=first_template,
        )

    async def place(self, kind: str, content_hash: str, content: bytes) -> None:
        """Content-addressed placement with race convergence + corrupt-target
        REPAIR policy (explicitly chosen over fail-strict for capture).

        The caller must possess independently verified bytes for exactly
        `content_hash` (capture re-hashes its inputs). A corrupt existing
        destination is repaired atomically with a high-severity log; a correct
        existing destination converges normally.
        """
        actual = hashlib.sha256(content).hexdigest()
        if actual != content_hash:
            raise SoloRingError(
                ErrorCode.WORKFLOW_VALIDATION_FAILED,
                f"Capture bytes do not hash to the claimed {kind} identity.",
                status_code=500,
            )
        await asyncio.to_thread(self._place_sync, kind, content_hash, content)

    def _place_sync(self, kind: str, content_hash: str, content: bytes) -> None:
        import time

        def _read_existing() -> bytes | None:
            # with-open closes the handle immediately: concurrent os.replace
            # on Windows fails while a read handle is open (WinError 32/5).
            # Transient locks during a concurrent SAME-HASH placement are
            # retryable: return None so the caller retries rather than fails.
            try:
                with open(final, "rb") as fh:
                    return fh.read()
            except FileNotFoundError:
                return None
            except PermissionError:
                return None  # locked by a concurrent placer; retry

        def _replace_with_retry() -> bool:
            for attempt in range(5):
                try:
                    os.replace(tmp, final)
                    return True
                except PermissionError:
                    existing = _read_existing()
                    if existing is not None and hashlib.sha256(existing).hexdigest() == content_hash:
                        return True  # concurrent winner converged; done
                    time.sleep(0.02 * (attempt + 1))
            return False

        final = self._path(kind, content_hash)
        final.parent.mkdir(parents=True, exist_ok=True)
        existing = _read_existing()
        if existing is not None and hashlib.sha256(existing).hexdigest() == content_hash:
            return  # converge on the identical winner
        if existing is not None:
            log.error(
                "WORKFLOW ARTIFACT REPAIR: %s %s target failed integrity; "
                "restoring from verified capture bytes",
                kind, content_hash,
            )
        import uuid

        tmp = final.with_suffix(f".tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}")
        tmp.write_bytes(content)
        try:
            if not _replace_with_retry():
                raise PermissionError(
                    f"could not place {kind} {content_hash} after retries"
                )
        finally:
            tmp.unlink(missing_ok=True)

    async def place_captured(self, captured: CapturedWorkflowArtifacts) -> None:
        await self.place("manifests", captured.manifest_hash, captured.manifest_bytes)
        await self.place("templates", captured.workflow_template_hash, captured.template_bytes)

    # --- historical retrieval ------------------------------------------------

    async def get_manifest(self, manifest_hash: str) -> bytes:
        return await self._get_verified("manifests", manifest_hash)

    async def get_template(self, workflow_template_hash: str) -> bytes:
        return await self._get_verified("templates", workflow_template_hash)

    async def _get_verified(self, kind: str, content_hash: str) -> bytes:
        _validate_hash(content_hash, kind)
        path = self._path(kind, content_hash)

        def _read() -> bytes | None:
            try:
                with open(path, "rb") as fh:
                    return fh.read()
            except FileNotFoundError:
                return None

        content = await asyncio.to_thread(_read)
        if content is None:
            raise ArtifactMissing(kind, content_hash)
        if hashlib.sha256(content).hexdigest() != content_hash:
            # NEVER fall back to the installed mutable workflow (M5A-3).
            raise ArtifactIntegrity(kind, content_hash)
        return content
