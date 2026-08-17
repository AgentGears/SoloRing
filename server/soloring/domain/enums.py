"""Domain enums shared across packages (plan §14 of v0.1, M1 §32)."""

from __future__ import annotations

from enum import Enum


class AssetKind(str, Enum):
    """Provenance kind of an Asset (plan §18, §26).

    REFERENCE: client-uploaded reference (take_id IS NULL)
    OUTPUT:     generated output (take_id IS NOT NULL)
    """

    REFERENCE = "reference"
    OUTPUT = "output"
