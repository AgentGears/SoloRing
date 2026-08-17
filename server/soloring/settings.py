"""Application settings (plan §3, §15, §17, §42).

IMPORTANT (plan §8): ``worker_id`` is NOT a setting. It is freshly generated as
``str(uuid.uuid4())`` exactly once at worker process startup and is never
configurable, never loaded from the environment, and never persisted. There is
deliberately no field here for it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# server/soloring/settings.py -> parents[2] is the repository root.
BASE_DIR: Path = Path(__file__).resolve().parents[2]

# Plan §17: "Thresholds must remain comfortably larger than normal refresh
# cadence." Enforced as a minimum multiple at config-load time so a stale
# threshold can never sit below the refresh cadence that feeds it.
TIMING_SAFETY_MULTIPLE = 3


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SOLORING_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        # NOTE: validate_assignment is deliberately left False. The timing
        # invariant is enforced when settings are LOADED from configuration.
        # Tests that need pathological timing (e.g. to force takeover) construct
        # valid defaults and then mutate fields directly.
    )

    # --- Storage layout (plan §4, §45) -------------------------------------
    # `data_dir` is the authoritative storage root. blob/staging/tmp default to
    # None and are derived from data_dir; each may still be overridden directly.
    data_dir: Path = Field(default=BASE_DIR / "data")
    blob_dir: Path | None = None
    staging_dir: Path | None = None
    tmp_dir: Path | None = None

    # Explicit override for the database URL. When empty, derived from data_dir.
    database_url: str | None = None

    # --- API ----------------------------------------------------------------
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # --- Upload limits (plan §42) ------------------------------------------
    upload_chunk_bytes: int = Field(default=1024 * 1024, ge=4096)  # 1 MiB
    max_upload_bytes: int = Field(default=2 * 1024 * 1024 * 1024, ge=1024)  # 2 GiB

    # --- Timing defaults (plan §17) ----------------------------------------
    worker_lease_ttl_seconds: int = Field(default=30, gt=0)
    worker_lease_refresh_interval_seconds: int = Field(default=5, gt=0)
    generation_heartbeat_interval_seconds: int = Field(default=5, gt=0)
    generation_heartbeat_stale_seconds: int = Field(default=30, gt=0)
    worker_poll_interval_seconds: int = Field(default=1, gt=0)
    sse_poll_interval_seconds: int = Field(default=2, gt=0)

    # --- Executor selection (M5 §5): applies only at NEW Generation creation.
    # The worker dispatches from the PERSISTED Generation.executor, so config
    # changes never reinterpret queued historical Generations. Closed set: a
    # typo in SOLORING_EXECUTOR must fail at load, never queue a Generation
    # the worker cannot dispatch (CHECK ck_generations_executor mirrors this).
    executor: Literal["fake", "comfy"] = "fake"

    # --- Comfy (executor adapter, M5B) ---------------------------------------
    comfy_base_url: str | None = None
    # Running-cancellation capability for the Comfy pipeline. "soft_only" is
    # the conservative default; "targeted" is backed ONLY by the M5B-5 live
    # proof on the pinned deployment (atomic /api/jobs/{id}/cancel +
    # retry-safety collateral matrix). Elevation is explicit configuration.
    comfy_cancellation_mode: Literal["soft_only", "targeted"] = "soft_only"
    # Observation cadence for live prompts (M5B-7): one explicit interval for
    # every path (claim, recovery, takeover) — the pre-M5B-7 default of 50 ms
    # produced ~32 HTTP reads/s per Generation (M5B-4 finding). Measured
    # default for the pinned deployment: see docs/EXECUTOR_PROFILE.md.
    comfy_observation_poll_seconds: float = Field(default=1.0, gt=0.0)

    @model_validator(mode="after")
    def _derive_storage_and_validate_timing(self) -> "Settings":
        # data_dir is the root; derive sub-dirs when not explicitly provided.
        if self.blob_dir is None:
            self.blob_dir = self.data_dir / "blobs"
        if self.staging_dir is None:
            self.staging_dir = self.data_dir / "staging"
        if self.tmp_dir is None:
            self.tmp_dir = self.data_dir / "tmp"

        # Plan §17: thresholds must stay comfortably larger than refresh cadence.
        if (
            self.worker_lease_refresh_interval_seconds * TIMING_SAFETY_MULTIPLE
            > self.worker_lease_ttl_seconds
        ):
            raise ValueError(
                "worker_lease_ttl_seconds must be at least "
                f"{TIMING_SAFETY_MULTIPLE}x worker_lease_refresh_interval_seconds "
                "(plan §17: thresholds must remain comfortably larger than refresh)"
            )
        if (
            self.generation_heartbeat_interval_seconds * TIMING_SAFETY_MULTIPLE
            > self.generation_heartbeat_stale_seconds
        ):
            raise ValueError(
                "generation_heartbeat_stale_seconds must be at least "
                f"{TIMING_SAFETY_MULTIPLE}x generation_heartbeat_interval_seconds "
                "(plan §17)"
            )
        return self

    @property
    def db_path(self) -> Path:
        return self.data_dir / "soloring.db"

    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        # aiosqlite expects a posix-style path in the URL.
        return f"sqlite+aiosqlite:///{self.db_path.as_posix()}"

    def ensure_storage_dirs(self) -> None:
        for d in (self.data_dir, self.blob_dir, self.staging_dir, self.tmp_dir):
            d.mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return a process-wide cached Settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
