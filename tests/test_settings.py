"""Settings tests: timing invariant (audit #5) and data_dir root (audit #6)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from soloring.settings import TIMING_SAFETY_MULTIPLE, Settings


def test_defaults_satisfy_timing_invariant() -> None:
    s = Settings()
    assert s.worker_lease_ttl_seconds >= TIMING_SAFETY_MULTIPLE * s.worker_lease_refresh_interval_seconds
    assert (
        s.generation_heartbeat_stale_seconds
        >= TIMING_SAFETY_MULTIPLE * s.generation_heartbeat_interval_seconds
    )


def test_rejects_lease_ttl_below_safety_multiple_of_refresh() -> None:
    # refresh=10, TTL=2 -> 2 < 3*10; guarantees false staleness (audit #5).
    with pytest.raises(ValidationError):
        Settings(worker_lease_ttl_seconds=2, worker_lease_refresh_interval_seconds=10)


def test_rejects_generation_stale_below_safety_multiple_of_heartbeat() -> None:
    with pytest.raises(ValidationError):
        Settings(
            generation_heartbeat_stale_seconds=5,
            generation_heartbeat_interval_seconds=10,
        )


def test_data_dir_is_authoritative_root(tmp_path: Path) -> None:
    """blob/staging/tmp derive from data_dir when not set explicitly (audit #6)."""
    root = tmp_path / "store"
    s = Settings(data_dir=root)
    assert s.blob_dir == root / "blobs"
    assert s.staging_dir == root / "staging"
    assert s.tmp_dir == root / "tmp"
    assert s.db_path == root / "soloring.db"


def test_explicit_storage_overrides_are_honored(tmp_path: Path) -> None:
    root = tmp_path / "store"
    custom = tmp_path / "elsewhere" / "blobs"
    s = Settings(data_dir=root, blob_dir=custom)
    assert s.blob_dir == custom
    # the others still derive from data_dir
    assert s.staging_dir == root / "staging"
    assert s.tmp_dir == root / "tmp"


def test_worker_id_is_not_a_setting() -> None:
    assert "worker_id" not in Settings.model_fields
