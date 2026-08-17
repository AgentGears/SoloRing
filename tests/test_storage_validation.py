"""Same-filesystem startup validation tests (plan §21)."""

from __future__ import annotations

import pytest


def test_same_filesystem_passes(settings) -> None:
    from soloring.db.engine import _validate_same_filesystem

    settings.ensure_storage_dirs()
    _validate_same_filesystem(settings)  # no raise


def test_cross_device_rejected(settings, monkeypatch) -> None:
    from soloring.db import engine as engine_mod

    class _Stat:
        def __init__(self, dev: int) -> None:
            self.st_dev = dev

    calls = {"n": 0}

    def fake_stat(p, *a, **k):  # noqa: ANN001, ANN202
        calls["n"] += 1
        return _Stat(1 if calls["n"] == 1 else 2)

    settings.ensure_storage_dirs()
    monkeypatch.setattr(engine_mod.os, "stat", fake_stat)
    with pytest.raises(RuntimeError, match="different filesystems"):
        engine_mod._validate_same_filesystem(settings)


def test_create_engine_validates_layout(settings) -> None:
    """create_soloring_engine runs the same-filesystem check at startup."""
    from sqlalchemy.ext.asyncio import AsyncEngine

    from soloring.db.engine import create_soloring_engine

    eng = create_soloring_engine(settings)  # same FS -> constructs fine
    assert isinstance(eng, AsyncEngine)
