"""M6C architecture-boundary scans (plan §80, §63 non-goals).

AST/source scans modeled after the M5 hardening approach: the executor and
worker trees must not know the Story World exists; Take approval must not
mutate canon; Asset paths must not auto-create Story World objects; and
EntityRevision payload schemas must stay free of realization bindings.
These supplement runtime tests; they do not replace them.
"""

from __future__ import annotations

import ast
from pathlib import Path

from soloring.settings import BASE_DIR

SERVER = BASE_DIR / "server" / "soloring"

# Names that would leak Story World state into execution infrastructure.
_CONTINUITY_TOKENS = (
    "CreativeEntity",
    "EntityRevision",
    "EntityApprovedRevision",
    "ShotEntityDependency",
    "ShotRevisionEntityDependency",
    "entity_approved_revisions",
    "shot_entity_dependencies",
    "shot_revision_entity_dependencies",
    "creative_entities",
    "soloring.continuity",
    "continuity.dependencies",
    "continuity.approvals",
    "continuity.entities",
)


def _python_files(*dirs: Path):
    for d in dirs:
        for path in sorted(d.rglob("*.py")):
            yield path


def _source_tokens(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    tokens: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            tokens.add(node.id)
        elif isinstance(node, ast.Attribute):
            tokens.add(node.attr)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            module = getattr(node, "module", None) or ""
            tokens.add(module)
            for alias in node.names:
                tokens.add(alias.name)
                tokens.add(alias.asname or alias.name)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            for token in _CONTINUITY_TOKENS:
                if token in node.value:
                    tokens.add(token)
    return tokens


def test_executors_and_worker_never_reference_story_world():
    offenders: list[str] = []
    for path in _python_files(SERVER / "executors", SERVER / "worker"):
        hit = _source_tokens(path) & set(_CONTINUITY_TOKENS)
        # The worker legitimately persists ShotRevisions whose table HAS the
        # continuity columns — but it must never resolve them; the columns
        # are written only by domain capture. Raw table-name leakage is what
        # these tokens detect, so any hit is reviewed.
        if hit:
            offenders.append(f"{path.relative_to(BASE_DIR)}: {sorted(hit)}")
    assert not offenders, offenders


def test_take_approval_never_mutates_canon():
    # Take approval lives in the takes API + generation service surfaces.
    paths = [
        SERVER / "api" / "takes.py",
        SERVER / "generation" / "service.py",
        SERVER / "generation" / "repository.py",
        SERVER / "generation" / "importer.py",
    ]
    for path in paths:
        if not path.exists():
            continue
        hit = _source_tokens(path) & set(_CONTINUITY_TOKENS)
        assert not hit, f"{path.name}: {sorted(hit)}"


def test_asset_paths_never_create_story_world_objects():
    for path in _python_files(SERVER / "assets", SERVER / "api"):
        if path.name not in {"assets.py", "blobs.py", "references.py",
                             "upload.py", "upload_discipline.py"} and "assets" not in str(path):
            continue
        tokens = _source_tokens(path)
        creating = tokens & {
            "CreativeEntity", "creative_entities", "soloring.continuity",
        }
        assert not creating, f"{path.name}: {sorted(creating)}"


def test_entity_revision_payloads_have_no_realization_bindings():
    """The M6 kind-specific spec schemas must structurally reject known
    realization fields (M6-F13) — pinned both by extra=forbid and by the
    absence of any such field in the models."""
    from soloring.continuity.canonical import SPEC_MODEL_BY_KIND
    from soloring.continuity.enums import ENTITY_KINDS

    forbidden_fragments = (
        "lora", "embedding", "controlnet", "checkpoint", "comfy",
        "executor", "node_id", "model_file", "workflow",
    )
    assert set(SPEC_MODEL_BY_KIND) == set(ENTITY_KINDS)
    for kind, model in SPEC_MODEL_BY_KIND.items():
        fields = set(model.model_fields)
        for fragment in forbidden_fragments:
            for field in fields:
                assert fragment not in field.lower(), (
                    f"{kind}.{field} looks like a realization binding"
                )
        # and a payload carrying such a key is rejected outright
        import pytest

        with pytest.raises(Exception):
            model.model_validate({"description": "x", "lora_id": "no"})
