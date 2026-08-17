"""ShotIntent tests (plan §9.1, §10)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from soloring.domain.shot_intent import ShotIntent


def test_defaults_optional_fields_none() -> None:
    si = ShotIntent(subject="Eva enters the lobby")
    assert si.subject == "Eva enters the lobby"
    for field in (
        "action", "environment", "framing", "camera_motion", "lens", "mood", "duration_ms",
    ):
        assert getattr(si, field) is None


def test_full_intent() -> None:
    si = ShotIntent(
        subject="Eva",
        action="enters",
        environment="lobby",
        framing="medium",
        camera_motion="push-in",
        lens="50mm",
        mood="unease",
        duration_ms=5000,
    )
    assert si.duration_ms == 5000
    assert si.lens == "50mm"


def test_subject_required() -> None:
    with pytest.raises(ValidationError):
        ShotIntent()  # type: ignore[call-arg]


def test_executor_parameters_not_accepted() -> None:
    # ShotIntent must never carry model/executor parameters (plan §10).
    with pytest.raises(ValidationError):
        ShotIntent(subject="x", steps=30)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        ShotIntent(subject="x", cfg=7.0)  # type: ignore[call-arg]
