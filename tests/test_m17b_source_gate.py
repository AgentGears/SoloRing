"""M17B boundary-refusal source gate (frozen proof-map owners
H01–H11). Structural refusals proven against the live schema, the
route table, and the migration chain."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / "server"


def _db_tables() -> set[str]:
    import tempfile
    db = Path(tempfile.mkdtemp()) / "sg.db"
    env = {"SystemRoot": "C:\\Windows",
           "SOLORING_DATABASE_URL": f"sqlite:///{db.as_posix()}",
           "SOLORING_DATA_DIR": db.parent.as_posix(),
           "PYTHONDONTWRITEBYTECODE": "1"}
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                   cwd=SERVER, capture_output=True, env=env)
    con = sqlite3.connect(db)
    tabs = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    cols = {t: [r[1] for r in con.execute(
        f"PRAGMA table_info({t})")] for t in tabs}
    con.close()
    return tabs, cols


def _route_source() -> str:
    return (SERVER / "soloring" / "api" / "m17b_performance.py"
            ).read_text(encoding="utf-8")


def test_h01_no_vocalperformance_binding_on_base_performancerevision():
    _, cols = _db_tables()
    perf_cols = set(cols["performance_revisions"])
    assert not any("vocal" in c for c in perf_cols)
    assert "source_vocal_performance_revision_id" not in perf_cols


def test_h02_no_synchronization_basis_version():
    _, cols = _db_tables()
    for t in ("performance_revisions", "performance_candidates"):
        assert "synchronization_basis_version" not in cols[t]


def test_h03_no_dialogue_bound_required_articulation_enforcement(client):
    # generic FACIAL with two articulation channels (fewer than four)
    # is lawful — proven live in B06; here assert the gate has no
    # all-four enforcement hook in the profile grammar
    from soloring.performance.profile import CHANNELS
    arts = [k for k in CHANNELS
            if k.startswith("profile-1/face.articulation.")]
    assert len(arts) == 4  # the registry HAS four; no rule REQUIRES them
    src = (SERVER / "soloring" / "performance" / "profile.py"
           ).read_text(encoding="utf-8")
    assert "all four" not in src
    assert "len(articulation" not in src


def test_h04_no_shot_performance_binding():
    _, cols = _db_tables()
    for t in ("performance_revisions", "performance_candidates"):
        assert not any(c.startswith("shot") for c in cols[t])


def test_h05_no_shotrevision_schema_8():
    tabs, _ = _db_tables()
    assert not any(t.startswith("shot_revisions_schema_8")
                   for t in tabs)
    vers = sorted(p.name for p in
                  (SERVER / "alembic" / "versions").glob("*.py"))
    # M17C-A (successor-admitted): the one migration beyond 0019 is
    # 0020; schema-8 Shot capture remains a future M17C-C surface.
    assert vers[-1] == "0023_m17cc_capture_closure_preimage.py"
    assert not any("schema_8" in v for v in vers)


def test_h06_no_generation_workflowspec_performance_schema():
    """H06 (PUB-R2): STRUCTURAL inspection of the ACTUAL WorkflowSpec
    authority — schema 4 in soloring.observation.workflow_spec
    (ROOT_KEYS / WORLD_OBSERVATION_KEYS / exact-key parser) and its
    schema-3 delegate in soloring.spatial.spec3 — plus the generation
    service source, the frozen workflow-contract JSON trees, and the
    generations table. A change to the WorkflowSpec schema code that
    introduced a performance key would fail here."""
    import inspect
    import json as _json

    import soloring.observation.workflow_spec as ws4
    import soloring.spatial.spec3 as ws3
    from soloring.errors import SoloRingError

    for mod in (ws4, ws3):
        src = inspect.getsource(mod)
        assert "performance" not in src.lower(), \
            f"{mod.__name__} mentions performance vocabulary"
        for name, value in vars(mod).items():
            if name.startswith("__"):
                continue
            members = ()
            if isinstance(value, (set, frozenset)):
                members = value
            elif isinstance(value, dict):
                members = list(value)
            for m in members:
                if isinstance(m, str):
                    assert "performance" not in m.lower(), \
                        (mod.__name__, name, m)

    # schema-4 key vocabularies exist and the parser is exact-key
    # closed: a performance key (like ANY unknown key) is refused
    assert isinstance(ws4.ROOT_KEYS, frozenset)
    assert isinstance(ws4.WORLD_OBSERVATION_KEYS, frozenset)
    with pytest.raises(SoloRingError) as exc_info:
        ws4.parse_workflow_spec_v4(
            {"schema_version": 4, "performance": None})
    assert "performance" in str(exc_info.value)

    src = (SERVER / "soloring" / "generation" / "service.py"
           ).read_text(encoding="utf-8", errors="replace")
    # FPR-M17CC-01 → M17C-D evolution (frozen plan R2-FINAL): the
    # retired blanket refusal is superseded by the ADMISSION
    # STRUCTURE; the service's performance vocabulary now spans the
    # two M17C-D regions — the admission gates (events through the
    # wrap + the spatial-composition refusal + the kind gate) and
    # the translation/v5-wrap block. Every case-insensitive
    # occurrence of the vocabulary must lie INSIDE those regions.
    lowered = src.lower()
    gates_start = lowered.rfind(
        "\n", 0, lowered.find("# m17c-d admission gates"))
    assert gates_start >= 0, "the M17C-D admission gates not found"
    marker = lowered.find(
        "performance_spatial_composition_unsupported")
    assert marker >= 0, \
        "the M17C-D spatial-composition admission refusal not found"
    wrap_end = lowered.find(
        "performance_inputs=performance_inputs)")
    assert wrap_end > 0, "the M17C-D persistence pass-through not found"
    block_end = lowered.find("\n", wrap_end) + 1
    stray = [
        i for i in range(len(lowered))
        if lowered.startswith("performance", i)
        and not (gates_start <= i < block_end)
    ]
    assert not stray, \
        "generation service mentions performance semantics beyond " \
        f"the M17C-D admission/translation regions (offsets {stray})"

    def _assert_no_performance(node, where: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                assert "performance" not in str(k).lower(), \
                    f"workflow key {k!r} in {where}"
                _assert_no_performance(v, where)
        elif isinstance(node, list):
            for v in node:
                _assert_no_performance(v, where)

    workflows = sorted((REPO / "workflows").rglob("*.json"))
    assert workflows, "frozen workflow contracts not found"
    for wf in workflows:
        # M17C-D FPR32-M17CD-01: the PINNED performance executor
        # package (workflows/performance_liveportrait_v1) is the one
        # frozen workflow contract whose keys LAWFULLY name the
        # performance derived inputs — every predecessor workflow
        # stays performance-free
        if "performance_liveportrait_v1" in wf.parts:
            continue
        doc = _json.loads(wf.read_text(encoding="utf-8"))
        _assert_no_performance(doc, wf.name)

    _, cols = _db_tables()
    gen = cols.get("generations", [])
    assert not any("performance" in c for c in gen)


def test_h07_no_executor_integration():
    src = _route_source()
    assert "executor" not in src.lower().replace(
        "executor_qualification_assessed", "")
    perf = (SERVER / "soloring" / "performance"
            ).glob("*.py")
    for f in perf:
        # M17C-D (frozen plan R2-FINAL W4): worker_inputs.py IS the
        # schema-5 performance execution lane — the one performance
        # module deliberately consuming the executor TRANSPORT seam
        # (the derived-input upload + the marker namespace; it never
        # imports ComfyClient itself). Every other performance module
        # stays executor-free.
        if f.name in ("worker_inputs.py", "executor_runtime.py"):
            # M17C-D: worker_inputs.py IS the schema-5 execution
            # lane consuming the executor TRANSPORT seam (never
            # ComfyClient itself); executor_runtime.py is the
            # performance-lane ATTESTATION LAW (it names the
            # predecessor ComfyUI-GGUF contract it preserves —
            # documentation, never executor code)
            assert "ComfyClient" not in f.read_text(
                encoding="utf-8")
            continue
        t = f.read_text(encoding="utf-8")
        assert "ComfyClient" not in t
        assert "comfy" not in t.lower()


def test_h08_no_universal_rig_schema():
    _, cols = _db_tables()
    for t in ("performance_revisions", "performance_candidates",
              "performance_retarget_assessments",
              "performance_retarget_reviews"):
        assert not any("rig" in c.lower() or "skeleton" in c.lower()
                       or "deform" in c.lower()
                       for c in cols[t]), t


def test_h09_no_profile_2():
    from soloring.performance.profile import PROFILE_ID
    assert PROFILE_ID == "performance-profile/1"
    _, cols = _db_tables()
    assert not any("profile_2" in c or "profile2" in c
                   for c in cols["performance_revisions"])


def test_h10_no_m18_contact_authority():
    _, cols = _db_tables()
    for t in ("performance_revisions", "performance_candidates",
              "performance_retarget_assessments"):
        assert not any("contact" in c.lower()
                       for c in cols[t]), t


def test_h11_no_m19_qc_correction_authority_and_no_m17b_frontend_product_surface():
    _, cols = _db_tables()
    for t in ("performance_revisions", "performance_candidates"):
        assert not any("qc" in c.lower() or "correction" in c.lower()
                       for c in cols[t]), t
    # backend/API-only: no M17B-specific frontend component exists
    web = REPO / "apps" / "web"
    hits = [p for p in web.rglob("*m17b*")
            if p.is_file()] if web.is_dir() else []
    assert hits == []
