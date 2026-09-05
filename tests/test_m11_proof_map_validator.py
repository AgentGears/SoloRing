"""M11 proof-map validator self-tests (frozen R3 plan §20.12).

The proof system is itself source-gated: a validator that cannot detect
its own failure modes is not accepted evidence.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location(
    "m11_validate_proof_map", REPO / "scripts" / "m11_validate_proof_map.py"
)
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)

# A synthetic collected-node universe for the self-tests (no pytest run).
NODES = {
    "tests/test_x.py::test_plain",
    "tests/test_x.py::test_param[a-1]",
    "tests/test_x.py::test_param[b-2]",
    "tests/test_y.py::test_other",
}


def test_parameterized_python_owner_resolution(tmp_path, monkeypatch):
    """M11-PROOF:01 — parameterized backend owners resolve exactly under
    the frozen grammar; bare-function and bracket forms both resolve;
    textual prefixes and unknown names do not."""
    fe = tmp_path / "tests"
    fe.mkdir()
    (fe / "test_x.py").write_text("def test_plain():\n    pass\n", encoding="utf-8")
    monkeypatch.setattr(v, "REPO", tmp_path)
    assert v.python_owner_resolves("tests/test_x.py::test_plain", NODES)
    assert v.python_owner_resolves("tests/test_x.py::test_param[a-1]", NODES)
    # A bare function owner resolves when at least one parameterized node
    # exists on that function boundary.
    assert v.python_owner_resolves("tests/test_x.py::test_param", NODES)
    # Textual prefix matching is forbidden: this owner is NOT a function
    # boundary of any collected node.
    assert not v.python_owner_resolves("tests/test_x.py::test_pla", NODES)
    assert not v.python_owner_resolves("tests/test_x.py::test_missing", NODES)
    assert not v.python_owner_resolves("tests/test_missing.py::test_plain", NODES)
    assert not v.python_owner_resolves("no-double-colon", NODES)


def test_frontend_exact_title_owner_resolution(tmp_path, monkeypatch):
    """M11-PROOF:02 — frontend resolution requires file + exact test title,
    not a bare filename."""
    fe = tmp_path / "apps/web/src/__tests__"
    fe.mkdir(parents=True)
    (fe / "suite.test.tsx").write_text(
        'it("exact title here", () => {});\n', encoding="utf-8"
    )
    monkeypatch.setattr(v, "REPO", tmp_path)
    assert v.frontend_owner_resolves(
        "apps/web/src/__tests__/suite.test.tsx::exact title here"
    )
    # Bare filenames are invalid proof owners.
    assert not v.frontend_owner_resolves("apps/web/src/__tests__/suite.test.tsx")
    # Wrong title does not resolve.
    assert not v.frontend_owner_resolves(
        "apps/web/src/__tests__/suite.test.tsx::wrong title"
    )
    # Missing file does not resolve.
    assert not v.frontend_owner_resolves(
        "apps/web/src/__tests__/absent.test.tsx::exact title here"
    )


def test_missing_duplicate_unknown_and_dangling_evidence_fail_closed(tmp_path):
    """M11-PROOF:03 — required-cell removal, duplicates, unknown IDs, and
    dangling owners all fail validation."""
    real = (REPO / "docs" / "SoloRing-M11-Proof-Map.md").read_text(encoding="utf-8")
    empty_nodes: set[str] = set()

    # 1. removing one required cell fails completeness.
    def _remove_cell(text: str, cell: str) -> str:
        return "\n".join(
            l for l in text.splitlines() if not l.startswith(f"| `{cell}`")
        )

    missing_one = _remove_cell(real, "M11-RECOVERY:13")
    errs = v.validate_map_text(missing_one, empty_nodes)
    assert any("missing required cells" in e and "M11-RECOVERY:13" in e for e in errs)

    # 2. a duplicate cell fails.
    dup = real.replace(
        "| `M11-ID:01` |",
        "| `M11-ID:01` |",  # unchanged first occurrence
        1,
    )
    line = [l for l in real.splitlines() if l.startswith("| `M11-ID:01`")][0]
    dup = real.replace(line, line + "\n" + line, 1)
    errs = v.validate_map_text(dup, empty_nodes)
    assert any("duplicate cell M11-ID:01" in e for e in errs)

    # 3. an unknown cell fails even with a resolvable-looking owner.
    unknown = real + "\n| `M11-FAKE:99` | TEST | `tests/test_x.py::test_x` | x |\n"
    errs = v.validate_map_text(unknown, empty_nodes)
    assert any("unknown cells" in e and "M11-FAKE:99" in e for e in errs)

    # 4. dangling owners fail even when the cell name is valid: with an
    # empty collected-node universe every python TEST/STRUCTURAL row dangles.
    errs = v.validate_map_text(real, empty_nodes)
    assert any("dangling/unresolvable python owner" in e for e in errs)

    # 5. unknown disposition fails.
    bad = real.replace("| `M11-ID:01` | TEST |", "| `M11-ID:01` | MAYBE |", 1)
    errs = v.validate_map_text(bad, empty_nodes)
    assert any("unknown disposition" in e for e in errs)

    # 6. duplicate closure command fails.
    cmds = "\n".join(
        [
            "| `CMD:proof-map` | `x` | y |",
            "| `CMD:proof-map` | `x` | y |",
        ]
    )
    assert any("duplicate closure command" in e for e in v.validate_cmds(cmds))
