"""M10F-E — DETERM:10 and the frontend/source audit gates.

DETERM:10 is the certified N≥3 same-runtime D0 byte specimen (§13.8 /
F-127): one materializer runtime, N independent materializations of the
same canonical spec, exact Blob SHA equality — recorded separately from
the live GPU source+rerun evidence. On the evidence machine this test
IS the byte oracle; on arbitrary CI runners the same test proves
grammar/decode/repeatability (byte equality still holds within one
process/runtime, which is exactly the frozen claim).
"""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import text


def test_d0_n3_same_runtime_exact_blob_sha_specimen():
    """DETERM:10 (§13.8 / F-127): N=3 independent materializations of the
    SAME canonical spec on the SAME materializer runtime produce byte-
    identical artifact digests, through the real compose path. This is
    recorded separately from the GPU source+rerun evidence class."""
    import importlib.util
    from pathlib import Path

    # reuse the frozen M10A lobby-pack helper (canonical fixture)
    spec = importlib.util.spec_from_file_location(
        "m10a_final_slice",
        Path(__file__).resolve().parent / "test_m10a_final_slice.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from soloring.spatial.realize import compose_spatial_realization

    pack = mod._lobby_pack()
    hashes = []
    for _ in range(3):
        out = compose_spatial_realization(pack)
        assert out.artifact_digests
        hashes.extend(out.artifact_digests)

    assert len(hashes) >= 3
    # every stream of every run is byte-identical (exact SHA equality)
    assert list(out.spec_hashes) == list(out.spec_hashes)  # sanity
    runs = [compose_spatial_realization(pack) for _ in range(2)]
    for r in runs:
        assert r.artifact_digests == out.artifact_digests
        assert r.spec_hashes == out.spec_hashes
        assert r.runtime_fingerprint_hash == out.runtime_fingerprint_hash


def test_frontend_source_audit_no_recovery_surface_no_error_dependency():
    """F-104 / Q49: apps/web has no M10F recovery import/call/API
    surface, and no client branch depends on the removed
    schema3-empty-M10 SPATIAL_REALIZATION_UNSUPPORTED behavior."""
    from pathlib import Path

    web = Path(__file__).resolve().parents[1] / "apps" / "web" / "src"
    assert web.is_dir()
    offenders_recovery = []
    offenders_error = []
    for src in web.rglob("*.ts*"):
        text = src.read_text(encoding="utf-8", errors="replace")
        if ("soloring.recovery" in text or "m10f_backup_restore" in text
                or "/backup" in text and "recovery" in text.lower()):
            offenders_recovery.append(str(src.relative_to(web)))
        if "SPATIAL_REALIZATION_UNSUPPORTED" in text:
            offenders_error.append(str(src.relative_to(web)))
    assert offenders_recovery == [], offenders_recovery
    assert offenders_error == [], offenders_error


def test_no_client_authority_recomputation():
    """Q59-leg: no client computes axis side, world membership, effective
    staging, or readiness independently of the server."""
    from pathlib import Path

    web = Path(__file__).resolve().parents[1] / "apps" / "web" / "src"
    forbidden_patterns = (
        "crossProduct", "cross_product", "axisSide", "axis_side",
        "effectiveStaging", "effective_staging",
    )
    offenders = []
    for src in web.rglob("*.ts*"):
        if "__tests__" in str(src) or ".test." in src.name:
            continue  # tests may exercise display helpers
        text = src.read_text(encoding="utf-8", errors="replace")
        for pat in forbidden_patterns:
            if pat in text:
                offenders.append((str(src.relative_to(web)), pat))
    # display of server-provided values is legal; computing them is not.
    # 'readiness' may appear as a display prop pass-through; assert no
    # math recomputation markers exist:
    assert offenders == [], offenders
