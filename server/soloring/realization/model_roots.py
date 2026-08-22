"""Live Comfy model-root adapter (frozen plan §6.4, §6.4.1).

Closed mapping storage_root_key → Settings field; safe resolution;
streaming SHA-256 with NO persistent metadata cache. Live execution
compatibility only — the adapter never defines historical identity.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from soloring.errors import ErrorCode, SoloRingError
from soloring.settings import Settings

ROOT_KEYS = ("unet", "vae", "clip", "clip_vision")


class ModelIncompatible(SoloRingError):
    def __init__(self, message: str) -> None:
        super().__init__(
            ErrorCode.EXECUTION_MODEL_INCOMPATIBLE, message, status_code=503
        )


def root_for_key(settings: Settings, root_key: str) -> Path:
    """The configured ABSOLUTE root for a root key (§6.4 rules 1/3/5)."""
    if root_key not in ROOT_KEYS:
        raise ModelIncompatible(
            f"storage_root_key {root_key!r} is outside the frozen adapter "
            f"vocabulary {ROOT_KEYS}."
        )
    value: Path | None = {
        "unet": settings.comfy_model_root_unet,
        "vae": settings.comfy_model_root_vae,
        "clip": settings.comfy_model_root_clip,
        "clip_vision": settings.comfy_model_root_clip_vision,
    }[root_key]
    if value is None:
        raise ModelIncompatible(
            f"Model root for storage_root_key {root_key!r} is not "
            "configured (SOLORING_COMFY_MODEL_ROOT_*); refusing to skip "
            "live byte verification."
        )
    if not value.is_absolute():
        raise ModelIncompatible(
            f"Configured model root for {root_key!r} is not absolute: "
            f"{value}."
        )
    return value


def resolve_model_file(settings: Settings, root_key: str, declared_name: str) -> Path:
    """Resolve exactly root/declared_name with containment after
    resolution (§6.4 rule 4). No directory search, no fallbacks."""
    from soloring.realization.fingerprint import validate_declared_name

    validate_declared_name(declared_name)
    root = root_for_key(settings, root_key)
    try:
        resolved_root = root.resolve()
        candidate = (root / declared_name).resolve()
    except OSError as exc:
        raise ModelIncompatible(
            f"Configured model root for {root_key!r} cannot be resolved: "
            f"{exc}"
        ) from exc
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise ModelIncompatible(
            f"Resolved model path {candidate} escapes the configured root "
            f"{resolved_root}."
        )
    return candidate


def hash_file_streaming(path: Path, chunk_bytes: int = 8 << 20) -> str:
    """Streaming SHA-256 (§6.4.1): always content-hashed; callers may
    dedupe per submission attempt only — there is deliberately no
    persistent metadata-keyed cache. Unreadable bytes are live-environment
    incompatibilities (r2-gate B1), never raw OSError."""
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(chunk_bytes)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError as exc:
        raise ModelIncompatible(
            f"Required model file {path.name} cannot be read for "
            f"verification: {exc}"
        ) from exc
    return digest.hexdigest()


def verify_live_model_bytes(
    settings: Settings,
    entries: list[tuple[str, str, str]],
) -> dict[str, str]:
    """Resolve + hash every (root_key, declared_name, expected_sha256)
    entry; returns resolved path by entry key. Fails
    EXECUTION_MODEL_INCOMPATIBLE before any submission when a required
    root is unavailable, the file is missing, or the bytes differ.

    Duplicate bindings resolving to the same live file share ONE hash
    computation within this single attempt (§6.4.1)."""
    hashed: dict[Path, str] = {}
    resolved: dict[str, str] = {}
    for entry_key, root_key, declared_name, expected in entries:
        path = resolve_model_file(settings, root_key, declared_name)
        if not path.is_file():
            raise ModelIncompatible(
                f"Required model file {declared_name!r} under root "
                f"{root_key!r} is missing at {path}."
            )
        if not path.is_file():
            raise ModelIncompatible(
                f"Required model file {declared_name!r} under root "
                f"{root_key!r} is missing at {path}."
            )
        if path not in hashed:
            hashed[path] = hash_file_streaming(path)
        actual = hashed[path]
        if actual != expected:
            raise ModelIncompatible(
                f"Live model file {declared_name!r} (root {root_key!r}) "
                f"hashes to {actual}, but the captured fingerprint "
                f"requires {expected}."
            )
        resolved[entry_key] = str(path)
    return resolved
