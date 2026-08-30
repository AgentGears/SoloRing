"""M10F-A operator recovery tool (R5 §7.1/§7.2).

Usage:
    python scripts/m10f_backup_restore.py backup  --data-dir <dir> --dest <path>
    python scripts/m10f_backup_restore.py restore --from <backup-root> --dest <path>

Exit codes:
    0  success
    2  unsupported storage posture (reported before any staging mutation)
    1  any other recovery failure (corruption, fault, bad destination, ...)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from soloring.recovery import (  # noqa: E402
    RecoveryError,
    RecoveryUnsupported,
    backup,
    restore,
)
from soloring.settings import Settings  # noqa: E402


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="m10f_backup_restore")
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("backup", help="create a full-instance local backup")
    b.add_argument("--data-dir", required=True, type=Path)
    b.add_argument("--dest", required=True, type=Path)

    r = sub.add_parser("restore", help="restore a backup into a fresh data root")
    r.add_argument("--from", dest="backup_root", required=True, type=Path)
    r.add_argument("--dest", required=True, type=Path)

    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "backup":
            settings = Settings(data_dir=args.data_dir)
            evidence = asyncio.run(backup(settings, args.dest))
        else:
            evidence = asyncio.run(restore(args.backup_root, args.dest))
    except RecoveryUnsupported as exc:
        print(f"UNSUPPORTED STORAGE POSTURE: {exc}", file=sys.stderr)
        return 2
    except RecoveryError as exc:
        print(f"RECOVERY FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
