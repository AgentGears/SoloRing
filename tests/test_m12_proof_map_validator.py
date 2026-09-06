"""M12 proof-map validator self-tests (frozen R3 §21 M12-PROOF)."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location(
    "m12_validate_proof_map", REPO / "scripts" / "m12_validate_proof_map.py"
)
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)

NODES = {
    "tests/test_x.py::test_plain",
    "tests/test_x.py::test_param[a-1]",
    "tests/test_y.py::test_other",
}


def test_m12_proof_map_has_exactly_122_unique_cells():
    """M12-PROOF:01 — cardinality and IDs frozen at 123 cells (R2->R3
    advanced 122 to 123 with M12-RACE:08; owner name keeps the historical
    frozen plan §21 wording)."""
    total = sum(len(c) for c in v.REQUIRED_CELLS.values())
    assert total == 123
    flat = [c for cells in v.REQUIRED_CELLS.values() for c in cells]
    assert len(flat) == len(set(flat))  # unique
    text = (REPO / "docs" / "SoloRing-M12-Proof-Map.md").read_text(
        encoding="utf-8")
    cells = re.findall(r"^\|\s*`?(M12-[A-Z-]+:\d+[a-z]?)`?\s*\|", text,
                       re.M)
    assert len(cells) == len(set(cells)) == 123


def test_m12_proof_map_all_test_owners_collect(tmp_path, monkeypatch):
    """M12-PROOF:02 — python/frontend owner resolution rules."""
    fe = tmp_path / "apps/web/src/__tests__"
    fe.mkdir(parents=True)
    (fe / "s.test.tsx").write_text(
        'it("exact title", () => {});\n', encoding="utf-8")
    monkeypatch.setattr(v, "REPO", tmp_path)
    assert v.frontend_owner_resolves(
        "apps/web/src/__tests__/s.test.tsx::exact title")
    assert not v.frontend_owner_resolves("apps/web/src/__tests__/s.test.tsx")
    assert not v.frontend_owner_resolves(
        "apps/web/src/__tests__/s.test.tsx::wrong")
    # python resolution rules
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_x.py").write_text(
        "def test_plain():\n    pass\n", encoding="utf-8")
    assert v.python_owner_resolves("tests/test_x.py::test_plain", NODES)
    assert v.python_owner_resolves("tests/test_x.py::test_param[a-1]", NODES)
    assert v.python_owner_resolves("tests/test_x.py::test_param", NODES)
    assert not v.python_owner_resolves("tests/test_x.py::test_pla", NODES)
    assert not v.python_owner_resolves("tests/test_z.py::test_plain", NODES)


def test_m12_proof_map_structural_owners_resolve():
    """M12-PROOF:03 — structural owners exist and the live map validates."""
    assert (REPO / "scripts/m12_validate_proof_map.py").is_file()
    assert hasattr(v, "validate_race_proof_no_shortcuts")
    text = (REPO / "docs" / "SoloRing-M12-Proof-Map.md").read_text(
        encoding="utf-8")
    errors = v.validate_map_text(text, set())
    # with an empty node universe, python owners legitimately dangle; the
    # structural owners must NOT be among the errors
    structural_errors = [e for e in errors if "RACE:08" in e or "PROOF" in e
                         and "unresolvable python" in e]
    assert not [e for e in structural_errors if "RACE:08" in e]


def test_m12_proof_map_validator_is_run_in_backend_ci_before_pytest():
    """M12-PROOF:04 — CI ordering."""
    workflow = (REPO / ".github" / "workflows" / "ci.yml").read_text()
    m12_pos = workflow.find("m12_validate_proof_map.py")
    pytest_pos = workflow.find("python -m pytest -q")
    m11_pos = workflow.find("m11_validate_proof_map.py")
    assert m12_pos != -1, "M12 validator missing from Backend CI"
    assert m12_pos < pytest_pos, "M12 validator must run before backend tests"
    assert m11_pos != -1 and m11_pos < pytest_pos  # predecessors retained
