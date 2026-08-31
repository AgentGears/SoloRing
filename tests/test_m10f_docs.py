"""M10F-E — operator documentation content gate (R6 §14.1 / F-100).

Pins the load-bearing claims of docs/M10_SPATIAL_CONTINUITY_OPERATIONS.md
so they cannot silently drift from source. Cosmetic prose is free; the
pinned claims are not.
"""

from __future__ import annotations

import re
from pathlib import Path

DOC = (Path(__file__).resolve().parents[1] / "docs"
       / "M10_SPATIAL_CONTINUITY_OPERATIONS.md")


def _doc() -> str:
    return DOC.read_text(encoding="utf-8")


def test_docs_exist_and_cover_required_topics():
    text = _doc()
    for topic in (
        "coordinate", "camera", "frame", "required", "transition",
        "ShotSpatialPlan", "current edits after a capture", "schemas 1–4",
        "M9 absence never fabricates", "backup", "Blob", "Exact Rerun", "garbage",
        "feature-film", "orphan", "blobs.path",
    ):
        assert topic.lower() in text.lower(), topic


def test_docs_coordinate_units_are_exact():
    text = _doc()
    assert "millimeters" in text
    assert "microdegrees" in text
    assert "−Z" in text or "-Z" in text
    assert "focal_length_um" in text
    assert "sensor_width_um" in text
    assert "+180" in text and "−180" in text or "-180" in text


def test_docs_lower_schema_compatibility_rule_is_exact():
    text = _doc()
    assert "schema-3" in text
    assert "logical v1" in text and "logical v2" in text
    assert "empty v3" in text
    assert "prompt → node 3/positive_prompt" in text
    assert "video → node 80/images" in text
    assert "video:0" in text
    assert "lower-logical execution view" in text
    assert "never backfill" in text or "nothing backfills" in text


def test_docs_recovery_posture_and_completeness_is_exact():
    text = _doc()
    assert "database_url" in text
    assert "<data_dir>/soloring.db" in text
    assert "<data_dir>/blobs" in text
    assert "<data_dir>/workflow-artifacts" in text
    assert "six-path" in text
    # database-only backup is incomplete once physical history exists
    assert "database-only backup is incomplete" in text
    # exit codes
    assert "0 success, 2 unsupported posture, 1 other failure" in text
    # orphan staging semantics
    assert ".soloring-restore-" in text
    assert "never authoritative" in text
    # restored rerun zero rematerialization
    assert "zero D0 rematerialization" in text


def test_docs_no_gc_posture_is_exact():
    text = _doc()
    assert "No garbage collection" in text
    assert "DERIVED_SPATIAL_BLOB_MISSING" in text
    assert "no production delete path" in text.replace(
        "no\nproduction delete path", "no production delete path")


def test_docs_authority_direction_and_claim_limits_are_exact():
    text = _doc()
    assert "never becomes" in text or "never transfer" in text
    assert "does **not** promise" in text
    assert "request/provenance continuity authority" in text
    assert "not** promise that a generative model" in text or \
        "identical pixels" in text
    # executability vs identity separation
    assert "executability and durable" in text
    assert "separate concerns" in text


def test_docs_pd2_blob_path_metadata_rule_is_present():
    text = _doc()
    assert "hash-derived" in text
    assert "metadata" in text
    assert "never followed" in text


def test_docs_match_source_error_codes():
    """Every error code named in the docs exists in the frozen vocabulary."""
    from soloring.errors import ErrorCode
    from soloring.spatial import error_codes as ec

    known = {v for k, v in vars(ErrorCode).items()
             if isinstance(v, str)} | set(
        v for k, v in vars(ec).items()
        if isinstance(v, str) and v.startswith("DERIVED_"))
    named = set(re.findall(r"\b(?:SPATIAL|DERIVED_SPATIAL)_[A-Z_]+\b",
                           _doc()))
    assert named <= known, named - known
    assert named  # the docs must name at least the blockers they triage
