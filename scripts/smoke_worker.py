"""End-to-end smoke test of the real `python -m soloring.worker` entrypoint.

Applies the migration to a fresh temp DB, starts the real worker process,
confirms it acquires the singleton lease, then stops it. Not part of the unit
suite (it shells out); run manually:

    .venv/Scripts/python.exe scripts/smoke_worker.py
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from alembic import command
from alembic.config import Config

REPO = Path(__file__).resolve().parent.parent


def main() -> int:
    data_dir = Path(tempfile.mkdtemp(prefix="soloring_smoke_"))
    # Apply in-process so command.upgrade (via env.py -> get_settings()) sees it.
    os.environ["SOLORING_DATA_DIR"] = str(data_dir)
    env = {**os.environ}

    # 1. Apply migration.
    cfg = Config(str(REPO / "server" / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO / "server" / "alembic"))
    # env.py reads Settings (which honors SOLORING_DATA_DIR) for the URL.
    import soloring.settings as smod

    smod._settings = None  # rebuild from env
    command.upgrade(cfg, "head")
    print("[smoke] migration applied ->", data_dir)

    # 2. Start the real worker process.
    proc = subprocess.Popen(
        [sys.executable, "-m", "soloring.worker"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        time.sleep(1.5)

        # 3. Inspect the lease row directly.
        db = data_dir / "soloring.db"
        con = sqlite3.connect(str(db))
        try:
            row = con.execute(
                "SELECT worker_id, heartbeat_at FROM worker_leases WHERE name='generation-worker'"
            ).fetchone()
        finally:
            con.close()

        out_tail = ""
        # drain whatever output is available without blocking
        try:
            outs, _ = proc.communicate(timeout=0.1)
            out_tail = outs
        except subprocess.TimeoutExpired:
            pass

        print("[smoke] worker_leases row:", row)
        ok = row is not None and len(row[0]) == 36 and "-" in row[0]
        print("[smoke] lease acquired with fresh uuid4:", ok)
        if out_tail:
            print("[smoke] stdout snippet:\n" + "\n".join(out_tail.splitlines()[:6]))
        return 0 if ok else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
