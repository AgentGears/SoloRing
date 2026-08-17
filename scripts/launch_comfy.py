"""Pinned ComfyUI launcher (M5B-7 hold fix; v4 whitelist policy).

The canonical way to start the dedicated executor — ALL custom nodes
disabled except the pinned ComfyUI-GGUF whitelist. Reads the LIVE git
revisions of the ComfyUI checkout and the ComfyUI-GGUF custom node, writes
the v4 deployment attestation (consumed by resolve_capability) — only
after clean-tree checks, the whitelisted launch, readiness, and lineage
proof — then starts
the server detached. Starting Comfy any other way leaves no attestation —
and targeted cancellation then fails closed, exactly as designed.

Usage:
    .venv/Scripts/python.exe scripts/launch_comfy.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

COMFY_DIR = Path(r"C:\AI\ComfyUI")
GGUF_DIR = COMFY_DIR / "custom_nodes" / "ComfyUI-GGUF"
COMFY_PORT = 8188


def git_rev(path: Path) -> str:
    out = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"],
                         capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise SystemExit(f"cannot read git revision of {path}: {out.stderr}")
    rev = out.stdout.strip()
    if len(rev) != 40:
        raise SystemExit(f"unexpected revision {rev!r} for {path}")
    return rev


def require_clean_tree(path: Path) -> None:
    """Commit equality != source equality: an uncommitted modification to
    the cancellation implementation would leave HEAD unchanged. The
    launcher refuses to attest a dirty tree (final-verification F2)."""
    status = subprocess.run(
        ["git", "-C", str(path), "status", "--porcelain"],
        capture_output=True, text=True, timeout=30)
    if status.returncode != 0:
        raise SystemExit(f"cannot read git status of {path}: {status.stderr}")
    # Untracked files count too (final verification): an untracked
    # executable source file can change runtime behavior with HEAD
    # unchanged. Only inert non-source suffixes are allowed.
    ALLOWED_UNTRACKED_SUFFIX = {".log", ".txt", ".png", ".json", ".csv"}
    dirty = []
    for ln in status.stdout.splitlines():
        entry = ln.strip()
        if not entry:
            continue
        path_part = entry[3:].strip().strip('"')
        if entry.startswith("??"):
            if not any(path_part.endswith(sfx)
                       for sfx in ALLOWED_UNTRACKED_SUFFIX):
                dirty.append(entry)
        else:
            dirty.append(entry)
    if dirty:
        raise SystemExit(
            f"{path} is not clean (uncommitted or untracked source; git "
            f"commit equality would NOT attest the running source): "
            f"{dirty[:3]}")


def kill_existing() -> None:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | "
         "Where-Object {$_.CommandLine -like '*main.py*--port 8188*'} | "
         "Select-Object -ExpandProperty ProcessId"],
        capture_output=True, text=True, timeout=30).stdout
    for pid in [int(x) for x in out.split()]:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                       capture_output=True)
        print(f"killed previous server pid {pid}")


def _is_same_process_tree(launched_pid: int, serving_pid: int) -> bool:
    """True iff serving_pid == launched_pid or is a verifiable descendant
    (walk ParentProcessId via CIM, bounded depth)."""
    if serving_pid == launched_pid:
        return True
    current = serving_pid
    for _ in range(8):  # bounded ancestry walk
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-CimInstance Win32_Process -Filter "
             f"'ProcessId={current}').ParentProcessId"],
            capture_output=True, text=True, timeout=15).stdout.strip()
        if not out.isdigit():
            return False
        parent = int(out)
        if parent == launched_pid:
            return True
        if parent <= 4:
            return False
        current = parent
    return False


def main() -> None:
    from soloring.executors.comfy.capability_record import (
        build_deployment_attestation,
        capture_process_start_fingerprint,
    )
    from soloring.settings import BASE_DIR

    # Commit equality != source equality: refuse to attest dirty trees.
    require_clean_tree(COMFY_DIR)
    require_clean_tree(GGUF_DIR)
    comfy_commit = git_rev(COMFY_DIR)
    gguf_commit = git_rev(GGUF_DIR)
    launched_at = datetime.now(timezone.utc).isoformat()

    kill_existing()
    exe = str(COMFY_DIR / "venv" / "Scripts" / "python.exe")
    log_out = str(BASE_DIR / "data" / "comfy-detached.log")
    log_err = str(BASE_DIR / "data" / "comfy-detached.log.err")
    pid_file = BASE_DIR / "data" / "comfy-launch-pid.txt"
    # Fire-and-forget with NO pipes (subprocess.run's communicate() wedges
    # when the PS child's handles are inherited — the M5B-6 lesson); the
    # launcher PID lands in a file and the serving PID is re-derived from
    # the port listener anyway.
    ps = (
        "Start-Process -FilePath "
        + repr(exe).replace("'", '"')
        + " -ArgumentList 'main.py','--listen','127.0.0.1','--port',"
        + f"'{COMFY_PORT}','--output-directory','output',"
        + "'--disable-all-custom-nodes',"
        + "'--whitelist-custom-nodes','ComfyUI-GGUF'"
        + " -PassThru"
        + f" -WorkingDirectory '{COMFY_DIR}' -WindowStyle Hidden"
        + f" -RedirectStandardOutput '{log_out}'"
        + f" -RedirectStandardError '{log_err}'"
        + f" | ForEach-Object {{ $_.Id }} | Out-File -Encoding ascii '{pid_file}'"
    )
    subprocess.Popen(["powershell", "-NoProfile", "-Command", ps],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     stdin=subprocess.DEVNULL,
                     creationflags=0x08000000 | 0x00000200)

    deadline = time.monotonic() + 180
    import urllib.request

    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{COMFY_PORT}/system_stats", timeout=2)
            break
        except Exception:  # noqa: BLE001
            time.sleep(1.0)
    else:
        raise SystemExit("server did not become ready")

    # Prove THE LAUNCHED PROCESS (or its verified descendant — the venv
    # shim spawns a child interpreter) owns the port. A pre-existing
    # foreign listener that dodged kill_existing() must NOT be attested
    # with our commits (final-verification patch 3).
    launched_pid = None
    deadline_pid = time.monotonic() + 15
    while time.monotonic() < deadline_pid:
        try:
            launched_pid = int(pid_file.read_text().strip())
            break
        except (OSError, ValueError):
            time.sleep(0.5)
    if launched_pid is None:
        raise SystemExit("could not read the launched pid file")

    owner = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-NetTCPConnection -LocalPort %d -State Listen | "
         "Select-Object -First 1 -ExpandProperty OwningProcess" % COMFY_PORT],
        capture_output=True, text=True, timeout=15).stdout.strip()
    if not owner.isdigit():
        raise SystemExit(f"no listener found on :{COMFY_PORT}")
    serving_pid = int(owner)
    if not _is_same_process_tree(launched_pid, serving_pid):
        raise SystemExit(
            f"listener pid {serving_pid} is NOT the launched process "
            f"{launched_pid} or its descendant — refusing to attest (a "
            f"foreign server may own :{COMFY_PORT})")
    fingerprint = capture_process_start_fingerprint(serving_pid)

    attestation = build_deployment_attestation(
        comfyui_commit=comfy_commit, gguf_commit=gguf_commit,
        launched_at=launched_at, pid=serving_pid,
        process_start_fingerprint=fingerprint,
        executor_origin=f"http://127.0.0.1:{COMFY_PORT}",
    )
    fp_dir = BASE_DIR / "data" / "comfy-fingerprint"
    fp_dir.mkdir(parents=True, exist_ok=True)
    tmp = fp_dir / "deployment_attestation.json.tmp"
    tmp.write_text(json.dumps(attestation, indent=2), encoding="utf-8")
    tmp.replace(fp_dir / "deployment_attestation.json")  # atomic publish
    print(f"server READY pid {serving_pid} on :{COMFY_PORT}; "
          f"attestation published: comfy={comfy_commit[:12]} "
          f"gguf={gguf_commit[:12]}")


if __name__ == "__main__":
    sys.exit(main())
