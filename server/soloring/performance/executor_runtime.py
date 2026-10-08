"""M17C-D FPR33-01(c) — the performance executor's EXPLICIT runtime
identity law. This is a SEPARATE attestation lane, not a widening of
the predecessor ComfyUI-GGUF contract: a performance deployment
attests exactly ONE custom node — the in-tree
``soloring_performance_nodes`` package — whose CONTENT HASH is
recorded by the launcher and re-verified here against the pinned
in-tree implementation. The predecessor lane (whitelist exactly
``("ComfyUI-GGUF",)`` with its commit) is untouched.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

PERFORMANCE_NODE_PACKAGE = "soloring_performance_nodes"


def performance_nodes_content_hash(package_dir: Path | None = None
                                   ) -> str:
    """The deterministic content hash of the pinned in-tree node
    package — every file's bytes in sorted-path order. This IS the
    implementation identity the attestation fingerprints (a named
    class in workflow JSON is not a contract; the bytes are)."""
    root = package_dir or (
        Path(__file__).resolve().parent.parent / "executor_nodes" /
        PERFORMANCE_NODE_PACKAGE)
    digest = hashlib.sha256()
    paths = sorted(p for p in root.rglob("*") if p.is_file())
    if not paths:
        raise RuntimeError(
            f"the performance node package at {root} is empty")
    for path in paths:
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(b"\x00")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def check_performance_runtime(attestation) -> None:
    """The explicit performance-lane law: the attested deployment's
    custom-node policy is EXACTLY the one performance package, and
    its recorded content hash equals the pinned in-tree
    implementation's. Failure is typed ModelIncompatible (the same
    class the predecessor law raises)."""
    from soloring.realization.model_roots import ModelIncompatible

    required = performance_nodes_content_hash()
    policy = tuple(
        getattr(attestation, "custom_node_policy", ()) or ())
    if PERFORMANCE_NODE_PACKAGE not in policy:
        raise ModelIncompatible(
            f"the performance deployment must attest the "
            f"{PERFORMANCE_NODE_PACKAGE!r} custom node; got {policy!r}")
    actual = getattr(attestation, "performance_nodes_hash", None)
    if actual != required:
        raise ModelIncompatible(
            f"the attested performance node package hash {actual!r} "
            f"!= the pinned in-tree implementation {required!r}")
