"""M5B-4 worker A — the process that must DIE.

Claims the one queued comfy Generation under its own lease, drives it
(submit → observe), and keeps running until abruptly terminated by the
parent (taskkill). No graceful shutdown path is registered on purpose.
"""

from __future__ import annotations

import asyncio
import sys

from soloring.db.engine import create_soloring_engine
from soloring.executors.comfy.client import ComfyClient
from soloring.settings import Settings
from soloring.worker import ownership
from soloring.worker.comfy_pipeline import drive_comfy_generation


async def main() -> None:
    data_dir = sys.argv[1]
    worker_id = sys.argv[2]
    base_url = sys.argv[3] if len(sys.argv) > 3 else "http://127.0.0.1:8188"

    settings = Settings(data_dir=data_dir)
    settings.executor = "comfy"
    settings.comfy_base_url = base_url
    engine = create_soloring_engine(settings)

    assert await ownership.acquire_worker_lease(
        engine, worker_id, settings.worker_lease_ttl_seconds
    ) in (ownership.LeaseAcquisitionResult.ACQUIRED_NEW,
          ownership.LeaseAcquisitionResult.REFRESHED_SELF)
    claim = await ownership.claim_next_generation(engine, worker_id)
    assert claim is not None, "worker A: nothing to claim"
    gid, attempt = claim
    print(f"[A] claimed {gid} attempt {attempt}", flush=True)

    client = ComfyClient(base_url, worker_id, timeout=600.0)
    try:
        result = await drive_comfy_generation(
            engine, settings, worker_id, gid, attempt, client,
            poll_interval=1.0,
        )
        print(f"[A] drive finished: {result}", flush=True)
    finally:
        await client.aclose()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
