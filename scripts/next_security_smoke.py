"""Post-M13 Next.js security production smoke (frozen R2 §10/§12).

Launches a disposable loopback stub backend + `next start -p 3000`
(SOLORING_API_ORIGIN pointed at the stub) against the ALREADY-BUILT
production bundle in apps/web/.next, then mechanically proves:

  * `/` renders (server component against the controlled fixture);
  * a dynamic App Router route renders through the fixture;
  * `/api/security-probe` proxies EXACTLY the stub status/body —
    the frozen `/api/:path* -> SOLORING_API_ORIGIN/:path*` rewrite
    contract in production mode;
  * an ordinary `/_next/static/...` asset serves;
  * behavioral no-store: two page requests produce TWO backend reads
    (no server-side fetch caching between them).

Exit codes: 0 all probes green; 1 any failure; 2 harness error.
No exploit payload is used; evidence is patched identity + normal
production behavior (frozen §12).
"""

from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WEB = REPO / "apps" / "web"
STUB_PORT = 8788
APP_PORT = 3000  # frozen: `next start -p 3000`
PROBE_BODY = "nsec-security-probe-ok-7f3a"

PROJECT = {
    "id": "p1", "project_id": "p1", "name": "NSEC Smoke Project",
    "description": None, "metadata_version": 0, "working_version": 1,
    "created_at": "2026-09-09T00:00:00Z", "updated_at":
    "2026-09-09T00:00:00Z",
}
stub_hits: list[str] = []


class Stub(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def _send(self, status: int, body: bytes, ctype: str):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        stub_hits.append(self.path)
        if self.path == "/security-probe":
            self._send(200, PROBE_BODY.encode(), "text/plain")
        elif self.path == "/projects":
            self._send(200, json.dumps([PROJECT]).encode(),
                       "application/json")
        elif self.path == "/projects/p1":
            self._send(200, json.dumps(PROJECT).encode(),
                       "application/json")
        else:
            # every other backend collection endpoint is a JSON list
            self._send(200, b"[]", "application/json")


def _port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _get(url: str, timeout: float = 15.0):
    req = urllib.request.Request(url, headers={"User-Agent":
                                               "nsec-smoke/1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace"), \
                r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), \
            e.headers.get("Content-Type", "")


def main() -> int:
    if _port_open(APP_PORT):
        print(f"SMOKE FAIL: port {APP_PORT} already occupied "
              "(frozen start port) — free it and rerun", file=sys.stderr)
        return 2

    server = ThreadingHTTPServer(("127.0.0.1", STUB_PORT), Stub)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    env = dict(__import__("os").environ)
    env["SOLORING_API_ORIGIN"] = f"http://127.0.0.1:{STUB_PORT}"
    env["NODE_ENV"] = "production"
    node = subprocess.run(["where", "node"], capture_output=True,
                          text=True).stdout.splitlines()[0].strip()
    next_bin = WEB / "node_modules" / "next" / "dist" / "bin" / "next"

    # The /api rewrite destination is resolved at BUILD time into
    # routes-manifest.json (Next 15), so the frozen §12 sequence builds
    # and starts under the SAME SOLORING_API_ORIGIN. Runtime env still
    # governs the server-component reads (api.server.ts apiOrigin()).
    print("building production bundle under stub origin ...")
    build = subprocess.run(
        [node, str(next_bin), "build"], cwd=str(WEB), env=env,
        capture_output=True, text=True)
    if build.returncode != 0:
        print("SMOKE FAIL: next build failed under stub origin:\n"
              + build.stdout[-2000:] + build.stderr[-2000:],
              file=sys.stderr)
        return 1

    import tempfile
    next_log = Path(tempfile.gettempdir()) / "nsec-smoke-next.log"
    log_f = open(next_log, "wb")
    proc = subprocess.Popen(
        [node, str(next_bin), "start", "-p", str(APP_PORT)],
        cwd=str(WEB), env=env, stdout=log_f, stderr=log_f)
    try:
        base = f"http://127.0.0.1:{APP_PORT}"
        for _ in range(120):  # wait for production server
            if _port_open(APP_PORT):
                break
            if proc.poll() is not None:
                print("SMOKE FAIL: next start exited early",
                      file=sys.stderr)
                return 1
            time.sleep(0.5)
        else:
            print("SMOKE FAIL: next start never listened",
                  file=sys.stderr)
            return 1
        time.sleep(1.0)

        results: list[tuple[str, bool, str]] = []

        # 1. `/` renders against the fixture (server component reads)
        st, body, _ = _get(f"{base}/")
        ok = st == 200 and "Projects" in body \
            and PROJECT["name"] in body
        results.append((f"/ -> {st}, fixture name rendered", ok,
                        body[:120]))

        # 2. dynamic App Router route through the controlled fixture
        st, body, _ = _get(f"{base}/projects/p1")
        ok = st == 200 and PROJECT["name"] in body
        results.append((f"/projects/p1 (dynamic route) -> {st}, "
                        "fixture rendered", ok, body[:120]))

        # 3. `/api/security-probe` proxies EXACT stub status/body
        st, body, ctype = _get(f"{base}/api/security-probe")
        ok = st == 200 and body == PROBE_BODY
        results.append((f"/api/security-probe -> {st}, body == stub "
                        "body, ctype {ctype}".format(ctype=ctype), ok,
                        body[:120]))

        # 4. an ordinary /_next/static asset serves
        st, body, _ = _get(f"{base}/")
        m = re.search(r"src=\"([^\"]*_next/static/[^\"]+)\"", body)
        if not m:
            results.append(("/_next/static asset discovery", False,
                            "no static script src on /"))
        else:
            ast, abody, actype = _get(f"{base}{m.group(1)}")
            ok = ast == 200 and len(abody) > 0 and "javascript" in \
                (actype or "")
            results.append((f"static asset -> {ast}, "
                            f"{len(abody)} bytes, {actype}", ok, ""))

        # 5. behavioral no-store: second `/` read hits the backend again
        before = len([h for h in stub_hits if h == "/projects"])
        _st, _b, _ = _get(f"{base}/")
        after = len([h for h in stub_hits if h == "/projects"])
        ok = _st == 200 and after > before
        results.append((f"no-store: backend /projects reads "
                        f"{before} -> {after} across two page requests",
                        ok, ""))

        print("stub hits:", stub_hits)
        bad = [r for r in results if not r[1]]
        for name, ok, ctx in results:
            print(f"  {'PASS' if ok else 'FAIL'}  {name}")
            if not ok and ctx:
                print(f"       body[:120]: {ctx!r}")
        if bad:
            print(f"SMOKE FAIL: {len(bad)} probe(s) failed",
                  file=sys.stderr)
            return 1
        print("Next security production smoke: ALL PROBES GREEN "
              "(production start, dynamic route, /api proxy exact, "
              "static asset, behavioral no-store).")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        server.shutdown()
        log_f.close()
        print(f"(next start log: {next_log})")


if __name__ == "__main__":
    sys.exit(main())
