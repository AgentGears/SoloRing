"""M2C live smoke: the reviewer's full hash-transition chain, through the
Next.js /api proxy (http://127.0.0.1:3000) against the real backend.

Chain: edit -> hash changes -> identical save -> hash stable -> upload ->
rediscovery -> attach -> hash changes -> second role legal -> same-role
reorder -> hash changes -> role change -> hash changes -> remove -> hash
changes -> cross-project attach rejected with envelope, refs+hash unchanged.
"""

from __future__ import annotations

import io
import json
import sys
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:3000/api"

PNG1 = b"\x89PNG\r\n\x1a\n" + b"reference-alpha-payload"
PNG2 = b"\x89PNG\r\n\x1a\n" + b"reference-beta-payload"


def req(method: str, path: str, body=None, headers=None, raw=None):
    url = BASE + path
    data = raw if raw is not None else (
        json.dumps(body).encode() if body is not None else None
    )
    r = urllib.request.Request(url, data=data, method=method)
    if body is not None and raw is None:
        r.add_header("content-type", "application/json")
    for k, v in (headers or {}).items():
        r.add_header(k, v)
    try:
        with urllib.request.urlopen(r) as resp:
            payload = resp.read()
            return resp.status, json.loads(payload) if payload else None
    except urllib.error.HTTPError as e:
        payload = e.read()
        return e.code, json.loads(payload) if payload else None


def multipart(name: bytes, data: bytes):
    boundary = "----soloringsmoke"
    body = io.BytesIO()
    body.write(f"--{boundary}\r\n".encode())
    body.write(
        b'Content-Disposition: form-data; name="file"; filename="'
        + name + b'"\r\n'
    )
    body.write(b"Content-Type: image/png\r\n\r\n")
    body.write(data + b"\r\n")
    body.write(f"--{boundary}--\r\n".encode())
    return body.getvalue(), {"content-type": f"multipart/form-data; boundary={boundary}"}


def hash_of(shot_id: str) -> str:
    _, shot = req("GET", f"/shots/{shot_id}")
    return shot["working_snapshot_hash"]


def refs_of(shot_id: str):
    _, refs = req("GET", f"/shots/{shot_id}/references")
    return refs


def put_refs(shot_id, desired):
    return req("PUT", f"/shots/{shot_id}/references", {"references": desired})


def check(label: str, ok: bool, extra: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + extra) if extra else ''}")
    if not ok:
        sys.exit(1)


def main() -> None:
    _, proj = req("POST", "/projects", {"name": "M2C Chain"})
    pid = proj["id"]
    _, shot = req("POST", f"/projects/{pid}/shots", {"subject": "Eva enters"})
    sid = shot["id"]
    h0 = shot["working_snapshot_hash"]

    # 1) edit -> hash changes
    _, s1 = req("PATCH", f"/shots/{sid}", {"subject": "Eva strides into the lobby"})
    check("edit subject -> hash changed", s1["working_snapshot_hash"] != h0)
    h1 = s1["working_snapshot_hash"]
    check("updated_at advanced on save", s1["updated_at"] >= shot["updated_at"])

    # 2) identical save -> hash stable
    _, s2 = req("PATCH", f"/shots/{sid}", {"subject": "Eva strides into the lobby"})
    check("identical save -> hash stable", s2["working_snapshot_hash"] == h1)
    check(
        "optional blank -> null round-trip",
        req("PATCH", f"/shots/{sid}", {"action": "   "})[1]["action"] is None,
    )

    # 3) upload -> refresh -> rediscovery
    raw, hdrs = multipart(b"ref-a.png", PNG1)
    code, a1 = req("POST", f"/projects/{pid}/assets", raw=raw, headers=hdrs)
    check("upload through proxy", code == 201 and a1["detected_media_type"] == "image/png")
    _, listed = req("GET", f"/projects/{pid}/assets")
    check(
        "asset rediscovered from server list",
        [x["id"] for x in listed] == [a1["id"]] and listed[0]["blob_url"].startswith("/blobs/"),
    )

    # 4) attach -> hash changes
    code, _ = put_refs(sid, [{"asset_id": a1["id"], "role": "reference"}])
    h2 = hash_of(sid)
    check("attach -> hash changed", code == 200 and h2 != h1)

    # 5) second role on same asset legal -> hash changes
    code, resp = put_refs(
        sid,
        [{"asset_id": a1["id"], "role": "reference"}, {"asset_id": a1["id"], "role": "character"}],
    )
    h3 = hash_of(sid)
    check("second role legal + hash changed", code == 200 and h3 != h2)
    check(
        "duplicate (asset, role) identity enforced server-side",
        put_refs(
            sid,
            [
                {"asset_id": a1["id"], "role": "reference"},
                {"asset_id": a1["id"], "role": "reference"},
            ],
        )[0] == 400,
    )

    # 6) same-role reorder -> hash changes (need two assets in one role)
    raw, hdrs = multipart(b"ref-b.png", PNG2)
    _, a2 = req("POST", f"/projects/{pid}/assets", raw=raw, headers=hdrs)
    put_refs(
        sid,
        [
            {"asset_id": a1["id"], "role": "reference"},
            {"asset_id": a2["id"], "role": "reference"},
            {"asset_id": a1["id"], "role": "character"},
        ],
    )
    h4a = hash_of(sid)
    code, _ = put_refs(
        sid,
        [
            {"asset_id": a2["id"], "role": "reference"},
            {"asset_id": a1["id"], "role": "reference"},
            {"asset_id": a1["id"], "role": "character"},
        ],
    )
    h4b = hash_of(sid)
    check("same-role reorder -> hash changed", code == 200 and h4b != h4a)
    order = [(r["asset_id"], r["role"], r["position"]) for r in refs_of(sid)]
    check("server order canonical after reorder", order == [
        (a1["id"], "character", 0), (a1["id"], "reference", 0), (a2["id"], "reference", 1),
    ] or order == [
        (a1["id"], "character", 0), (a2["id"], "reference", 0), (a1["id"], "reference", 1),
    ])

    # 7) role change (MOVE a2: reference -> style) -> hash changes, both
    #    groups renormalized
    code, resp = put_refs(
        sid,
        [
            {"asset_id": a1["id"], "role": "reference"},
            {"asset_id": a2["id"], "role": "style"},
        ],
    )
    h5 = hash_of(sid)
    check("role change -> hash changed", code == 200 and h5 != h4b)
    pos = {(r["asset_id"], r["role"]): r["position"] for r in resp}
    check(
        "both role groups re-normalized",
        pos[(a1["id"], "reference")] == 0
        and pos[(a2["id"], "style")] == 0
        and (a2["id"], "reference") not in pos,
    )

    # 8) remove (drop a2/style) -> hash changes
    code, _ = put_refs(sid, [{"asset_id": a1["id"], "role": "reference"}])
    h6 = hash_of(sid)
    check("remove -> hash changed", code == 200 and h6 != h5)
    check("removed reference gone from canonical set", [
        (r["asset_id"], r["role"]) for r in refs_of(sid)
    ] == [(a1["id"], "reference")])

    # 9) cross-project asset rejected; refs + hash unchanged
    _, other = req("POST", "/projects", {"name": "Other"})
    raw, hdrs = multipart(b"x.png", PNG1)
    _, ax = req("POST", f"/projects/{other['id']}/assets", raw=raw, headers=hdrs)
    refs_before = refs_of(sid)
    h_before = hash_of(sid)
    code, err = put_refs(
        sid,
        [
            {"asset_id": a1["id"], "role": "reference"},
            {"asset_id": ax["id"], "role": "reference"},
        ],
    )
    check(
        "cross-project attach -> stable envelope",
        code == 400 and err["error_code"] == "REFERENCE_SET_INVALID"
        and set(err.keys()) == {"error_code", "message", "details"},
    )
    check(
        "after failed PUT: refs AND hash unchanged",
        refs_of(sid) == refs_before and hash_of(sid) == h_before,
    )

    # cleanup
    req("DELETE", f"/projects/{pid}")
    req("DELETE", f"/projects/{other['id']}")
    print("\nM2C chain: ALL PASS")


if __name__ == "__main__":
    main()
