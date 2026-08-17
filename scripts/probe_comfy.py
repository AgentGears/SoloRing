"""M5B-1 probe CLI — live ComfyUI fingerprint + capability report.

Usage:
    .venv/Scripts/python.exe scripts/probe_comfy.py \
        [--base-url http://127.0.0.1:8188] \
        [--out-dir data/comfy-fingerprint]

Writes report.json (the real ComfyCapabilityReport + probe metadata) and
fixtures/*.json (sanitized raw dialects) under --out-dir. Exit code 0 when
the six mandatory capabilities are SUPPORTED (evaluate_readiness READY),
1 on UNAVAILABLE/INCOMPATIBLE, 2 on unreachable.

New wire dialects follow the fixed loop: sanitized fixture → wire.py
normalizer → M5A regression → rerun M5A gate → return to M5B.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

from soloring.executors.comfy.capabilities import ReadinessStatus, evaluate_readiness
from soloring.executors.comfy.client import ComfyClient
from soloring.executors.comfy.probe import run_probe
from soloring.settings import BASE_DIR


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=None,
                        help="ComfyUI base URL (default SOLORING_COMFY_BASE_URL"
                             " or http://127.0.0.1:8188)")
    parser.add_argument("--out-dir", default=None,
                        help="output directory (default data/comfy-fingerprint)")
    args = parser.parse_args()

    from soloring.settings import get_settings

    settings = get_settings()
    base_url = args.base_url or settings.comfy_base_url or "http://127.0.0.1:8188"
    out_dir = Path(args.out_dir or (BASE_DIR / "data" / "comfy-fingerprint"))
    out_dir.mkdir(parents=True, exist_ok=True)

    client = ComfyClient(base_url, "soloring-probe", timeout=15.0)
    try:
        result = await run_probe(
            client, base_url,
            observed_at=datetime.now(timezone.utc).isoformat(),
        )
    finally:
        await client.aclose()

    report = result.report
    from soloring.executors.comfy.capabilities import report_payload

    doc = {
        "observed_at": report.observed_at,
        "base_url": base_url,
        "executor_version": report.executor_version,
        "wire_dialects": list(report.wire_dialects),
        "features": report_payload(report)["features"],
        "cancellation": report_payload(report)["cancellation"],
        "evidence": report_payload(report)["evidence"],
        "marker_prompt_id": result.marker_prompt_id,
        "view_bytes_sha256": result.view_bytes_sha,
        "notes": result.notes,
    }
    (out_dir / "report.json").write_text(
        json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    fixtures_dir = out_dir / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    for name, fixture in result.fixtures.items():
        (fixtures_dir / f"{name}.json").write_text(
            json.dumps(fixture, indent=2, ensure_ascii=False,
                       default=str), encoding="utf-8",
        )

    readiness = evaluate_readiness(report, reachable=doc["executor_version"]
                                   is not None or bool(result.fixtures))
    print(json.dumps({
        "readiness": readiness.value,
        "executor_version": report.executor_version,
        "wire_dialects": list(report.wire_dialects),
        "features": doc["features"],
        "marker_prompt_id": result.marker_prompt_id,
        "notes": result.notes,
    }, indent=2))
    print(f"report + {len(result.fixtures)} fixtures -> {out_dir}")

    if readiness is ReadinessStatus.READY:
        return 0
    if readiness is ReadinessStatus.INCOMPATIBLE:
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
