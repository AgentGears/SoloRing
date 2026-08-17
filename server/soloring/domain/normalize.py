"""Text normalization primitives (plan §7).

Canonical snapshot identity depends on stored strings, so normalization is part
of the persistence contract. Reference roles are the exception: persisted
exactly as supplied (case-sensitive, untrimmed), only structurally validated.
"""

from __future__ import annotations

# Structural bounds (plan §7.1, §7.3, §7.5).
PROJECT_NAME_MAX = 500
SHOT_SUBJECT_MAX = 20_000
ROLE_MAX = 64
ORIGINAL_FILENAME_MAX = 512


def normalize_optional_creative(value: str | None) -> str | None:
    """Optional creative Shot string (plan §7.4).

    NULL / "" / whitespace-only -> None ; otherwise trimmed. Gives one canonical
    persistent representation so ``action=""`` and ``action=None`` converge.
    """
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def normalize_required_text(value: str | None) -> str:
    """Required text (project name, shot subject): trim (plan §7.1, §7.3).

    Caller rejects an empty result. Never returns None.
    """
    return (value or "").strip()


def normalize_project_name(value: str | None) -> str:
    return normalize_required_text(value)


def normalize_project_description(value: str | None) -> str | None:
    """Project description: trim; empty-after-trim -> None (plan §7.2)."""
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def is_valid_role(role: object) -> bool:
    """Reference role validation (plan §7.5, §11.4).

    Roles are exact/case-sensitive/untrimmed but must be non-empty,
    non-whitespace-only, and <= 64 chars.
    """
    if not isinstance(role, str):
        return False
    if not (1 <= len(role) <= ROLE_MAX):
        return False
    return len(role.strip()) > 0


def basename_filename(filename: str | None) -> str | None:
    """Take the basename of an uploaded filename and bound its length (plan §19).

    Provenance metadata only; never used as a filesystem path.
    """
    if filename is None:
        return None
    # basename regardless of separator style
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    if not name:
        return None
    return name[:ORIGINAL_FILENAME_MAX]
