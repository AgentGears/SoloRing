"""M12 boundary proofs (frozen R3 §21 M12-BOUNDARY / M12-SCOPE)."""

from __future__ import annotations

import subprocess
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from soloring.composition import impacts as impacts_mod

BASE_DIR = Path(__file__).resolve().parents[1]


def _cfg() -> Config:
    cfg = Config(str(BASE_DIR / "server" / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "server" / "alembic"))
    return cfg


def _upgrade(tmp_path, monkeypatch, target="head"):
    import soloring.settings as settings_mod

    monkeypatch.setenv("SOLORING_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(settings_mod, "_settings", None)
    command.upgrade(_cfg(), target)


def _m12_source() -> str:
    files = [
        BASE_DIR / "server/soloring/composition/canonical.py",
        BASE_DIR / "server/soloring/composition/models.py",
        BASE_DIR / "server/soloring/composition/service.py",
        BASE_DIR / "server/soloring/composition/readiness.py",
        BASE_DIR / "server/soloring/composition/impacts.py",
    ]
    src = "\n".join(f.read_text(encoding="utf-8") for f in files)
    # M13 R3 §22.1/§22.3: the impacts FK-consumer registry enumerates the
    # new M13 occurrence-FK families BY TABLE NAME, and the live-blocker
    # resolver READS those tables to resolve termination blockers — a
    # classification inventory and read-only resolution, never a
    # spatial-authority write. Strip both before the token scan.
    import re as _re

    src = _re.sub(r"FK_CONSUMERS: dict.*?\n\}\n", "", src, count=1,
                  flags=_re.S)
    src = _re.sub(
        r"async def _resolve_live_blockers.*?(?=\n(?:async )?def )",
        "", src, count=1, flags=_re.S)
    return src


def test_m12_has_no_writes_to_production_revision_authority():
    """M12-BOUNDARY:01 — Composition paths never write M11 authority."""
    src = _m12_source()
    for pattern in ("UPDATE production_revisions", "INSERT INTO production_revisions",
                    "DELETE FROM production_revisions",
                    "UPDATE production_objects", "INSERT INTO production_objects",
                    "UPDATE production_revision_closures",
                    "UPDATE production_revision_source_assets"):
        assert pattern not in src, pattern


def test_m12_has_no_writes_to_spatial_continuity_authority():
    """M12-BOUNDARY:02 — no M10 spatial authority writes."""
    src = _m12_source()
    for pattern in ("spatial_world", "spatial_track", "spatial_frame",
                    "SpatialWorld", "SpatialTrack", "SpatialFrame"):
        assert pattern not in src.replace(
            "soloring.spatial.math", "").replace("spatial/math", ""), pattern


def test_m12_has_no_writes_to_continuity_or_shot_capture():
    """M12-BOUNDARY:03 — no M13 state/Shot-capture pre-implementation."""
    src = _m12_source()
    for pattern in ("INSERT INTO shots", "shot_revisions",
                    "INSERT INTO shot_references", "world_state"):
        assert pattern not in src, pattern


def test_m12_has_no_generation_executor_or_render_source_delta():
    """M12-BOUNDARY:04 — no execution milestone content."""
    out = subprocess.run(
        ["git", "diff", "--name-only", "5e8a71969b197b7c40a6daa120fda5b0334c1d33..HEAD"],
        cwd=BASE_DIR, capture_output=True, text=True, check=True,
    ).stdout
    changed = {line for line in out.splitlines() if line.strip()}
    forbidden = ("executor", "worker", "comfy", "render", "generation/",
                 "workflows/", "realization")
    offenders = sorted(
        p for p in changed
        if any(m in p.lower() for m in forbidden)
        and not p.startswith(("tests/", "scripts/", ".github/"))
        # spatial/math.py is the pinned value-grammar reuse seam, not a write
        and p != "server/soloring/spatial/math.py"
    )
    assert offenders == [], offenders


def test_m12_occurrence_fk_consumer_inventory_is_exhaustive(tmp_path, monkeypatch):
    """M12-BOUNDARY:05 — every FK to composition_occurrences is registered."""
    _upgrade(tmp_path, monkeypatch, "head")
    con = sqlite3.connect(tmp_path / "soloring.db")
    try:
        found = set()
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'")]
        for table in tables:
            quoted = table.replace('"', '""')
            for row in con.execute(f'PRAGMA foreign_key_list("{quoted}")'):
                parent, from_col = row[2], row[3]
                if parent == "composition_occurrences":
                    found.add((table, from_col))
    finally:
        con.close()
    assert found == set(impacts_mod.FK_CONSUMERS), sorted(found)


def test_m12_normative_external_name_scan_is_clean():
    """M12-BOUNDARY:06 — no external research/product names in M12 sources."""
    import re

    candidates = list((BASE_DIR / "server/soloring/composition").glob("*.py"))
    candidates += [
        BASE_DIR / "server/soloring/api/compositions.py",
        BASE_DIR / "server/soloring/api/schemas/compositions.py",
        BASE_DIR / "server/alembic/versions/0013_m12_composition_occurrences.py",
        BASE_DIR / "apps/web/src/components/WorldSetWorkspace.tsx",
        BASE_DIR / "apps/web/src/app/projects/[id]/world/page.tsx",
    ]
    forbidden = re.compile(
        r"comfy|midjourney|stable diffusion|blender|unity|unreal|adobe|"
        r"chatgpt|claude|openai|anthropic|github copilot", re.I)
    for f in candidates:
        assert not forbidden.search(f.read_text(encoding="utf-8")), f.name


def test_no_unregistered_non_fk_durable_occurrence_consumer_contract():
    """M12-BOUNDARY:07 — the non-FK registry stays closed. Empty and
    frozen in M12; M13 R3 §22.2 activates the ONE frozen indirect
    consumer (the Shot selection through binding→subject/entry→
    occurrence). Nothing beyond the frozen registry may exist."""
    assert impacts_mod.NON_FK_DURABLE_CONSUMERS == {
        "shot_production_world_selections": "current-selection/indirect",
    }
    # The impact fingerprint carries the consumer_contract_version so any
    # future registry extension changes impact identity mechanically.
    from soloring.composition.canonical import CONSUMER_CONTRACT_VERSION

    assert CONSUMER_CONTRACT_VERSION == 1


def test_no_arbitrary_property_override_storage(tmp_path, monkeypatch):
    """M12-SCOPE:06 — closed typed mutation vocabulary, no property bag."""
    _upgrade(tmp_path, monkeypatch, "head")
    con = sqlite3.connect(tmp_path / "soloring.db")
    try:
        cols = {r[1] for r in con.execute(
            "PRAGMA table_info(composition_working_occurrences)")}
    finally:
        con.close()
    assert not any("property" in c or "override" in c or "json" in c.lower()
                   for c in cols)
    src = _m12_source()
    assert "property_path" not in src
