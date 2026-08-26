"""Worker-side historical derived-spatial input transport (frozen r3 §48).

Loads the captured sibling derived-input rows for a Generation and verifies
them entirely from HISTORICAL state: captured rows, derived provenance,
canonical spec/runtime bytes, Blob DB identity, and physical Blob bytes.
Never reads current M10 authority. Fails closed on missing/corrupt bytes;
never rematerializes. The verified Blob is handed to the normal executor
input path through an execution-local adapter that does not widen the
published M5 CapturedInput seam (§2.4).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.assets.blob_store import BlobStore
from soloring.errors import ErrorCode, SoloRingError
from soloring.spatial import error_codes as ec
from soloring.spatial.blob_integrity import blob_integrity_status
from soloring.spatial.derived import validate_derived_provenance_row
from soloring.spatial.package3 import resolve_derived_binding

_CURRENT_M10_TABLES = (
    "spatial_worlds", "spatial_world_states", "spatial_frames",
    "spatial_world_state_frames", "spatial_axes", "spatial_world_state_axes",
    "spatial_tracks", "spatial_transitions", "shot_spatial_plans",
)


@dataclass
class VerifiedDerivedInput:
    """One verified historical derived input bound to an exact node/field."""

    input_key: str
    position: int
    artifact_role: str
    node: str
    field: str
    blob_hash: str
    local_path: str
    execution_reference: str | None = None
    # M10E §5.2 (frozen soloring.spatial.v1 consumption semantics): the
    # retained multi-frame D0 Blob is uploaded as its exact PNG frame
    # files (the CERTIFIED §114 executor consumption shape — the
    # WanVideoControlnet control_images input is an IMAGE tensor, so the
    # frames must enter through LoadImage nodes, never a bare filename
    # string at the tensor field). frame_references carries the uploaded
    # per-frame executor references, in frame order.
    frame_references: tuple[str, ...] = ()


def _split_png_frames(data: bytes) -> list[bytes] | None:
    """Deterministically split a retained D0 Blob into its exact PNG frame
    files. Returns None unless the content is a concatenation of complete
    PNG streams covering ALL bytes (the frozen D0 grammar); arbitrary
    non-PNG content stays a single opaque upload (legacy transport)."""
    frames: list[bytes] = []
    i, n = 0, len(data)
    sig = b"\x89PNG\r\n\x1a\n"
    while i < n:
        if data[i:i + 8] != sig:
            return None
        j = i + 8
        while True:
            if j + 8 > n:
                return None
            length = int.from_bytes(data[j:j + 4], "big")
            ctype = data[j + 4:j + 8]
            j += 8 + length + 4  # header + data + CRC
            if j > n:
                return None
            if ctype == b"IEND":
                break
        frames.append(data[i:j])
        i = j
    return frames if frames else None


def current_m10_table_names() -> tuple[str, ...]:
    """Forbidden current-authority table names for the read spy."""
    return _CURRENT_M10_TABLES


async def execute_schema3_derived_inputs(
    session: AsyncSession,
    store: BlobStore,
    *,
    generation_id: str,
    workflow_spec: dict,
    manifest_v3: dict,
    client,
) -> list[VerifiedDerivedInput]:
    """Full worker schema-3 derived-input path: verify (this module) then
    upload the EXACT retained historical Blob bytes to the executor's
    attempt-scoped input namespace, recording the executor-local
    reference for the manifest's exact node/field translation.

    ``client`` is the worker's ClientUploader (upload(source_path=…,
    filename=…, subfolder=…)); the bytes uploaded are read from the
    verified physical Blob path. A retained D0 Blob that parses as
    concatenated PNG frames is uploaded frame-per-file (the certified
    consumption shape); any other content is uploaded whole."""
    from pathlib import Path as _Path

    from soloring.executors.comfy.translate import comfy_input_reference

    verified = await load_verified_derived_inputs(
        session, store, generation_id=generation_id,
        workflow_spec=workflow_spec, manifest_v3=manifest_v3)
    for v in verified:
        subfolder = f"soloring-der-{generation_id[:8]}"
        data = _Path(v.local_path).read_bytes()
        frames = _split_png_frames(data)
        if frames and len(frames) > 1:
            refs = []
            for i, frame in enumerate(frames):
                filename = f"{v.input_key}_{v.blob_hash[:16]}_{i:03d}.png"
                name, sub = await client.upload_bytes(
                    data=frame, filename=filename, subfolder=subfolder)
                refs.append(comfy_input_reference(name, sub))
            v.frame_references = tuple(refs)
        else:
            ext = ".png" if frames else ".bin"
            filename = f"{v.input_key}_{v.blob_hash[:16]}{ext}"
            name, sub = await client.upload(
                source_path=_Path(v.local_path), filename=filename,
                subfolder=subfolder)
            v.execution_reference = comfy_input_reference(name, sub)
    return verified


def _fail(code: str, message: str, status: int = 500) -> SoloRingError:
    return SoloRingError(code, message, status_code=status)


async def load_verified_derived_inputs(
    session: AsyncSession,
    store: BlobStore,
    *,
    generation_id: str,
    workflow_spec: dict,
    manifest_v3: dict,
) -> list[VerifiedDerivedInput]:
    """Load + verify the derived sibling rows for one historical Generation.

    workflow_spec is the CAPTURED spec (schema 3); manifest_v3 the CAPTURED
    schema-3 manifest document. Every row must cross-check against the
    captured spatial_continuity_hash and the exact manifest binding.
    """
    captured_hash = (workflow_spec.get("spatial_realization") or {}).get(
        "spatial_continuity_hash")
    if not captured_hash:
        raise _fail(ec.DERIVED_SPATIAL_PROVENANCE_MISMATCH,
                    "Captured workflow-spec has no spatial_continuity_hash.")

    rows = (await session.execute(text(
        "SELECT gdsi.input_key, gdsi.position, gdsi.artifact_role, "
        "       gdsi.derived_spatial_artifact_id, gdsi.blob_hash "
        "FROM generation_derived_spatial_inputs gdsi "
        "WHERE gdsi.generation_id = :gid ORDER BY gdsi.position"),
        {"gid": generation_id})).mappings().all()

    srsw = (await session.execute(text(
        "SELECT srsw.spatial_continuity_hash "
        "FROM generations g "
        "JOIN shot_revision_spatial_worlds srsw "
        "  ON srsw.shot_revision_id = g.shot_revision_id "
        "WHERE g.id = :gid"), {"gid": generation_id})).first()
    if srsw is None or srsw[0] != captured_hash:
        raise _fail(ec.DERIVED_SPATIAL_PROVENANCE_MISMATCH,
                    "Captured spatial authority hash disagrees with the "
                    "Generation's ShotRevision spatial history.")

    verified: list[VerifiedDerivedInput] = []
    for row in rows:
        art = (await session.execute(text(
            "SELECT project_id, spec_schema_version, spec_json, spec_hash, "
            "spatial_continuity_schema_version, spatial_continuity_hash, "
            "artifact_kind, artifact_schema_version, algorithm_id, "
            "algorithm_version, runtime_fingerprint_json, "
            "runtime_fingerprint_hash, determinism_class, blob_hash, "
            "media_type "
            "FROM derived_spatial_artifacts WHERE id = :aid"),
            {"aid": row["derived_spatial_artifact_id"]})).mappings().one_or_none()
        if art is None:
            raise _fail(ec.DERIVED_SPATIAL_PROVENANCE_MISMATCH,
                        f"Derived provenance row missing for {row['input_key']}.")
        # ONE complete provenance validator (canonical spec + runtime bytes
        # and hashes, algorithm projection, D0, Blob identity) — the worker
        # reuses it rather than carrying a weaker second interpretation
        # (closure review blocker 4).
        try:
            validate_derived_provenance_row(art)
        except SoloRingError as exc:
            raise _fail(ec.DERIVED_SPATIAL_PROVENANCE_MISMATCH,
                        f"Historical derived provenance fails canonical "
                        f"validation: {exc.message}") from exc
        if art["spatial_continuity_hash"] != captured_hash:
            raise _fail(ec.DERIVED_SPATIAL_PROVENANCE_MISMATCH,
                        "Derived provenance source hash disagrees with the "
                        "captured spatial authority.")
        if art["blob_hash"] != row["blob_hash"]:
            raise _fail(ec.DERIVED_SPATIAL_PROVENANCE_MISMATCH,
                        "Derived input Blob identity disagrees with provenance.")

        # exact manifest binding (no graph heuristics)
        input_key, node, field = resolve_derived_binding(
            manifest_v3, row["artifact_role"], row["position"])
        if input_key != row["input_key"]:
            raise _fail(ec.DERIVED_SPATIAL_BINDING_INVALID,
                        f"Captured input_key {row['input_key']!r} disagrees "
                        f"with the manifest binding {input_key!r}.")

        # Blob DB identity + physical bytes
        blob_row = (await session.execute(
            text("SELECT hash FROM blobs WHERE hash = :h"),
            {"h": row["blob_hash"]})).first()
        if blob_row is None:
            raise _fail(ec.DERIVED_SPATIAL_BLOB_MISSING,
                        f"Historical derived Blob {row['blob_hash']} has no "
                        "Blob row.")
        status = await blob_integrity_status(store, row["blob_hash"])
        if status == "missing":
            raise _fail(ec.DERIVED_SPATIAL_BLOB_MISSING,
                        f"Physical derived Blob bytes missing for "
                        f"{row['input_key']}.")
        if status != "valid":
            raise _fail(ec.DERIVED_SPATIAL_BLOB_CORRUPT,
                        f"Physical derived Blob bytes corrupt for "
                        f"{row['input_key']}.")

        verified.append(VerifiedDerivedInput(
            input_key=row["input_key"], position=row["position"],
            artifact_role=row["artifact_role"], node=node, field=field,
            blob_hash=row["blob_hash"],
            local_path=str(store.path_for_hash(row["blob_hash"])),
        ))
    return verified


__all__ = [
    "VerifiedDerivedInput", "load_verified_derived_inputs",
    "execute_schema3_derived_inputs", "current_m10_table_names",
]
