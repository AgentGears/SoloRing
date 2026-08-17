"""AST structural purity test for domain/prompt.py (M2 plan §3.1.6).

The compiler may depend only on the creative ShotIntent type and standard
library string logic — and v1 needs no stdlib imports at all. Rejects direct
imports of DB/FS/network/executor machinery (not a loose text grep).
"""

from __future__ import annotations

import ast
from pathlib import Path

from soloring.settings import BASE_DIR

BANNED_PREFIXES = {
    "sqlalchemy",
    "asyncio",
    "os",
    "pathlib",
    "subprocess",
    "socket",
    "http",
    "urllib",
    "requests",
    "httpx",
    "aiohttp",
    "soloring.db",
    "soloring.assets",
    "soloring.executors",
    "soloring.worker",
}

ALLOWED_IMPORTS = {"__future__", "soloring.domain.shot_intent"}


def _imported_modules() -> list[str]:
    source = (BASE_DIR / "server" / "soloring" / "domain" / "prompt.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.append(node.module or "")
    return modules


def _is_banned(module: str) -> bool:
    return any(
        module == prefix or module.startswith(prefix + ".")
        for prefix in BANNED_PREFIXES
    )


def test_compiler_imports_are_exactly_the_allowed_set() -> None:
    modules = _imported_modules()
    assert set(modules) <= ALLOWED_IMPORTS, (
        f"domain/prompt.py imports outside the allowed set: {sorted(set(modules) - ALLOWED_IMPORTS)}"
    )


def test_compiler_rejects_db_fs_network_executor_dependencies() -> None:
    for module in _imported_modules():
        assert not _is_banned(module), f"banned import in prompt.py: {module}"


def test_version_is_a_literal_assignment() -> None:
    source = (BASE_DIR / "server" / "soloring" / "domain" / "prompt.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    literals = [
        node.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(t.id == "PROMPT_COMPILER_VERSION" for t in node.targets)
        and isinstance(node.value, ast.Constant)
    ]
    assert literals == ["1"], "PROMPT_COMPILER_VERSION must be a literal '1'"
