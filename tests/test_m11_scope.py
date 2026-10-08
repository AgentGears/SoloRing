"""M11 authority-boundary / forbidden-expansion proofs (frozen R3 §20.10).

M11 must not widen Asset semantics, smuggle Shot/Generation/Take capture
scope, introduce an M15 update lifecycle, a generalized representation
registry, or any executor/live-render source delta.
"""

from __future__ import annotations

import subprocess
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

BASE_DIR = Path(__file__).resolve().parents[1]


def _cfg() -> Config:
    cfg = Config(str(BASE_DIR / "server" / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "server" / "alembic"))
    return cfg


def _upgrade(tmp_path, monkeypatch, target):
    import soloring.settings as settings_mod

    monkeypatch.setenv("SOLORING_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(settings_mod, "_settings", None)
    command.upgrade(_cfg(), target)


def _table_cols(root: Path, table: str) -> list[str]:
    con = sqlite3.connect(root / "soloring.db")
    try:
        return [r[1] for r in con.execute(f'PRAGMA table_info("{table}")')]
    finally:
        con.close()


def _head_blob(path: str) -> str:
    return subprocess.run(
        ["git", "rev-parse", f"HEAD:{path}"], cwd=BASE_DIR,
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def test_asset_kind_constraint_unchanged(tmp_path, monkeypatch):
    """M11-BOUNDARY:01 — M11 does not widen Asset semantics."""
    _upgrade(tmp_path, monkeypatch, "head")
    con = sqlite3.connect(tmp_path / "soloring.db")
    try:
        checks = [
            r[0] for r in con.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' "
                "AND name='assets'")
        ]
        # Exact predecessor CHECKs, unchanged.
        assert "kind IN ('reference', 'output')" in checks[0]
        assert "(kind = 'reference' AND take_id IS NULL) " in checks[0]
        assert "production" not in checks[0]
    finally:
        con.close()


def test_no_shot_generation_take_schema_change(tmp_path, monkeypatch):
    """M11-BOUNDARY:02 — capture/execution authority tables untouched."""
    _upgrade(tmp_path, monkeypatch, "0011_m10_derived_spatial_execution")
    before = {
        t: _table_cols(tmp_path, t)
        for t in ("shots", "shot_revisions", "generations",
                  "generation_inputs", "takes")
    }
    _upgrade(tmp_path, monkeypatch, "head")
    after = {
        t: _table_cols(tmp_path, t)
        for t in ("shots", "shot_revisions", "generations",
                  "generation_inputs", "takes")
    }
    assert before == after


def test_no_production_current_revision_pointer(tmp_path, monkeypatch):
    """M11-BOUNDARY:03 — M15 update lifecycle absent."""
    _upgrade(tmp_path, monkeypatch, "head")
    cols = _table_cols(tmp_path, "production_objects")
    assert not any("revision" in c for c in cols)
    assert not any(c in ("current", "approved", "latest") for c in cols)


def test_no_generalized_representation_registry_table(tmp_path, monkeypatch):
    """M11-BOUNDARY:04 — RP-02 non-edge preserved."""
    _upgrade(tmp_path, monkeypatch, "head")
    con = sqlite3.connect(tmp_path / "soloring.db")
    try:
        prod_tables = sorted(
            r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name LIKE 'production_%'"))
    finally:
        con.close()
    # M13 R3 §4 adds the narrow frozen companions (spatial interpretation
    # + Production Instance state/staging) — explicitly not RP-02.
    # M15A adds the frozen compatibility-evidence tables (R4 §11) —
    # explicitly not RP-02.
    assert prod_tables == [
        "production_compatibility_assessments",
        "production_compatibility_uses",
        "production_instance_feature_transitions",
        "production_instance_features",
        "production_instance_spatial_tracks",
        "production_instance_spatial_transitions",
        "production_objects",
        "production_revision_closures",
        "production_revision_source_assets",
        "production_revision_spatial_interpretations",
        "production_revisions",
        "production_update_items",
        "production_update_operations",
    ]


def test_no_execution_source_delta_in_m11_owned_diff():
    """M11-BOUNDARY:05 — no executor/live-runtime source changed by M11."""
    out = subprocess.run(
        ["git", "diff", "--name-only", "6f5d9771e3e67fa4097b7b7babab238d1f57a57e..HEAD"],
        cwd=BASE_DIR, capture_output=True, text=True, check=True,
    ).stdout
    changed = {line for line in out.splitlines() if line.strip()}
    forbidden_markers = (
        "executor", "worker", "comfy", "realization", "render",
        "generation/", "workflows/",
    )
    # M14 implementation succession (frozen R2 @ 68f910f5, authorized
    # 2026-09-10): the authorized M14 execution-integration surface is
    # carved out of this M11 boundary exactly as the M12/M13/hygiene/
    # next-security gates were carved. The M14 boundary validator owns
    # these paths' classification.
    m14_owned = (
        "server/soloring/observation/",
        "server/soloring/generation/service.py",
        "server/soloring/realization/packages.py",
        "server/soloring/errors.py",
        "server/soloring/generation/repository.py",
        "server/soloring/spatial/boxdepth.py",
        "server/soloring/generation/rerun.py",
        "server/soloring/worker/comfy_pipeline.py",
        "server/soloring/workflows/artifact_store.py",
        "server/soloring/worker/execution.py",
        "server/soloring/api/generations.py",
        "server/soloring/api/realization.py",
    )
    # Post-M15 review remediation is byte-pinned, not path-authorized: any
    # later semantic edit to either source must update this reviewed pin.
    post_m15_owned = {
        # M17C-D FPR33-01(c): the performance executor lane
        # (the node package, the attestation record, the
        # runtime branch, the authority wrap read-through,
        # the lane law, the launcher lane), byte-pinned
        'scripts/launch_comfy.py': '8f2c1eef9371e4eeede418f7aeb400d7524ce154',
        'server/soloring/executor_nodes/soloring_performance_nodes/__init__.py': '4044507a3e72628265bd7ab01c15419c4f79cb6d',
        'server/soloring/executors/comfy/capability_record.py': '08c79332e0de4b8e6acb20865b4866bcc781c99d',
        'server/soloring/realization/authority.py': '3fcbac52417e4cf79f423a2dace1d834797e8e94',
        'server/soloring/realization/runtime.py': '2749ff589e3c4db1cd0ee2c24fd887e6459e88a1',
        'server/soloring/performance/executor_runtime.py': '38f97f5bdd2a4d42b3e94c25eb4ce5ebd17e497b',
        # M17C-D FPR32: the PINNED performance executor package
        # (the frozen LivePortrait contract), byte-pinned
        'workflows/performance_liveportrait_v1/manifest.json': 'aacfd334a26ca6786a5208b2975c2cc9f15a6049',
        'workflows/performance_liveportrait_v1/workflow.json': '9a34292d6a3c8fc0b32993f4e99fbaf9eb54e6b5',
        'workflows/performance_liveportrait_v1/workflow-package.json': 'd7d4bc075bb5f5d426bb3db928c1c4c10ce9c1b1',
        # M17C-D execution succession (frozen plan R2-FINAL,
        # authorized 2026-10-07): the D lane's sampler/spec/
        # translation/worker modules + the touched persistence
        # seams, byte-pinned to the committed implementation.
        'server/soloring/performance/execution_sampler.py':
            '2b12d5e9a5dd6d9c28e670f81f14da5c35c15c9d',
        'server/soloring/performance/execution_spec.py':
            'ffcdb7aa6204f324e4fd8fe230c3543c28ff510f',
        'server/soloring/performance/execution_translation.py':
            '31d83591f465f28351cc8c99affcff50628a9804',
        'server/soloring/performance/worker_inputs.py':
            '873167d3e5b97c590390898169b6ae3ea8ce0e4b',
        'server/soloring/worker/comfy_pipeline.py':
            'bdd46705f265de7750f8620dc8991809d6026536',
        'server/soloring/generation/repository.py':
            'e70056c340e790da1b83ac64c47483b70613c935',
        'server/soloring/recovery/backup.py':
            '7a17e5ab492507bec432f666219c083c6e39dd15',
        "server/soloring/executors/comfy/translate.py":
            "978639dac19562ee5b597947b1e9eeea673014f6",
        "server/soloring/spatial/worker_inputs.py":
            "c9d260e6ffcf325af42a79297a84c95fe9f3c77d",
    }
    for path, expected_blob in post_m15_owned.items():
        assert _head_blob(path) == expected_blob, (
            f"post-M15 successor bytes changed without M11 boundary review: {path}"
        )
    offenders = sorted(
        p for p in changed
        if any(m in p.lower() for m in forbidden_markers)
        # authorized M11 artifacts: test/validator/CI-proof-map seams
        # (§20.0; M11-PROOF:04 requires the ci.yml validator step) — the
        # claim under test is that no executor/live-render SOURCE changed
        and not p.startswith(("tests/", "scripts/", ".github/"))
        and not p.startswith(m14_owned)
        and p not in post_m15_owned
    )
    assert offenders == [], f"execution source touched by M11: {offenders}"


def test_backend_ci_runs_m11_proof_map_validator_before_backend_tests():
    """M11-PROOF:04 — CI executes the M11 validator before backend tests
    and preserves the predecessor proof-map validation."""
    workflow = (BASE_DIR / ".github" / "workflows" / "ci.yml").read_text()
    m11_pos = workflow.find("m11_validate_proof_map.py")
    m10f_pos = workflow.find("m10f_validate_proof_map.py")
    pytest_pos = workflow.find("python -m pytest -q")
    assert m11_pos != -1, "M11 validator missing from Backend CI"
    assert m10f_pos != -1, "predecessor M10F validation was removed"
    assert m11_pos < pytest_pos, "M11 validator must run before backend tests"
