"""Characterization-record + deployment-attestation contract (v1, M5B-7 hold fix).

ONE shared, versioned contract (record v1 / attestation v4) for binding
the promoted targeted-cancellation
capability to the EXACT characterized executor:

    capability record  (what M5B-5 proved, on which fingerprint)
    deployment attestation (what revision the local launcher ACTUALLY runs)
    runtime check: record.commit == attestation.commit == live version probe
                   → TARGETED; anything else → fail closed to SOFT_ONLY

The record is emitted by scripts/m5b5_live_cancellation.py through this
module (never hand-edited); the v4 attestation is written by
scripts/launch_comfy.py ONLY after clean-tree checks, a whitelisted
launch, readiness, and lineage proof. Pure
file/JSON handling — no DB (package boundary holds).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

RECORD_SCHEMA_VERSION = 1
ATTESTATION_SCHEMA_VERSION = 4

RECORD_FILENAME = "capability_m5b5.json"
ATTESTATION_FILENAME = "deployment_attestation.json"

_HEX = set("0123456789abcdef")


_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def normalize_origin(base_url: str) -> str | None:
    """http://Host:Port → http://lower(host):port (default 80). None if
    unparseable. The attested identity is the ORIGIN, not just a port."""
    from urllib.parse import urlparse

    try:
        parsed = urlparse(base_url if "://" in base_url
                          else f"http://{base_url}")
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if not host:
        return None
    port = parsed.port or 80
    return f"http://{host}:{port}"


def is_loopback_origin(base_url: str) -> bool:
    origin = normalize_origin(base_url)
    if origin is None:
        return False
    host = origin.rsplit(":", 1)[0].removeprefix("http://")
    return host in _LOOPBACK_HOSTS


def _is_commit(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 40
            and set(value) <= _HEX)


class CapabilityRecordInvalid(Exception):
    """The record/attestation does not satisfy the versioned contract."""


@dataclass(frozen=True)
class CapabilityRecord:
    """The validated v1 characterization record (cancellation conclusions)."""

    comfyui_commit: str
    comfyui_version: str
    gguf_commit: str
    endpoint: str
    targeting_key: str
    uniqueness_guarantee: str
    retry_safety: str

    def matches_attestation(self, attestation: "DeploymentAttestation") -> bool:
        """The fingerprint-binding core: the characterized ComfyUI and
        ComfyUI-GGUF revisions must be EXACTLY what the launcher attests the
        running deployment is. Same version with a different commit is drift
        and must fail closed."""
        return (self.comfyui_commit == attestation.comfyui_commit
                and self.gguf_commit == attestation.gguf_commit)


# The EXACT characterized running-cancel contract (final-verification
# patch F1): these five values are what M5B-5 proved on the pinned
# deployment. A record that characterizes anything else characterizes an
# UNPROVEN contract and must be invalid — not merely non-empty.
REQUIRED_ENDPOINT = "POST /api/jobs/{prompt_id}/cancel"
REQUIRED_TARGETING_KEY = "prompt_id"
REQUIRED_UNIQUENESS = "proven"
REQUIRED_MODE = "TARGETED"
REQUIRED_RETRY_SAFETY = "safe"


@dataclass(frozen=True)
class DeploymentAttestation:
    """The validated v4 local deployment attestation.

    v4 binds the attestation to the SERVING PROCESS and its EXACT
    executable extension set, not merely the
    checkout at launch time: the launcher verifies clean source trees,
    starts the server, proves THAT process owns :8188, and only then
    atomically publishes pid + process_start_fingerprint. The runtime
    re-verifies the live process identity before trusting the attestation
    (a stale attestation cannot survive a manual replacement).
    """

    comfyui_commit: str
    gguf_commit: str
    executor_origin: str  # normalized http://host:port the launcher serves
    pid: int
    process_start_fingerprint: str  # CreationDate string from the OS
    custom_node_policy: tuple  # the EXACT enforced extension set (v4)
    launched_at: str

    def origin_matches(self, client_base: str) -> bool:
        """The attested executor must be THE executor the client targets
        (final-verification patch 3): normalized origin equality, not just
        the same port number on some other host."""
        return (normalize_origin(client_base) == self.executor_origin)


def _read_json(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CapabilityRecordInvalid(f"unreadable {path.name}: {exc}") from exc
    if not isinstance(raw, dict):
        raise CapabilityRecordInvalid(f"{path.name}: not an object")
    return raw


def load_capability_record(data_dir: Path) -> CapabilityRecord:
    """Strictly validate the v1 record; raise on ANY deviation."""
    doc = _read_json(Path(data_dir) / "comfy-fingerprint" / RECORD_FILENAME)
    if doc.get("schema_version") != RECORD_SCHEMA_VERSION:
        raise CapabilityRecordInvalid(
            f"record schema_version must be {RECORD_SCHEMA_VERSION}")
    fp = doc.get("executor_fingerprint")
    rc = doc.get("running_cancel")
    if not isinstance(fp, dict) or not isinstance(rc, dict):
        raise CapabilityRecordInvalid("record missing fingerprint/running_cancel")
    if not _is_commit(fp.get("comfyui_commit")) or not _is_commit(
            fp.get("gguf_commit")):
        raise CapabilityRecordInvalid("record commits must be 40-hex")
    for field in ("comfyui_version",):
        if not isinstance(fp.get(field), str) or not fp[field]:
            raise CapabilityRecordInvalid(f"record fingerprint.{field} missing")
    for field, want in (
        ("mode", REQUIRED_MODE),
        ("endpoint", REQUIRED_ENDPOINT),
        ("targeting_key", REQUIRED_TARGETING_KEY),
        ("uniqueness_guarantee", REQUIRED_UNIQUENESS),
        ("retry_safety", REQUIRED_RETRY_SAFETY),
    ):
        if rc.get(field) != want:
            raise CapabilityRecordInvalid(
                f"record running_cancel.{field} must be exactly {want!r} "
                f"(the characterized contract); got {rc.get(field)!r}")
    return CapabilityRecord(
        comfyui_commit=fp["comfyui_commit"],
        comfyui_version=fp["comfyui_version"],
        gguf_commit=fp["gguf_commit"],
        endpoint=rc["endpoint"],
        targeting_key=rc["targeting_key"],
        uniqueness_guarantee=rc["uniqueness_guarantee"],
        retry_safety=rc["retry_safety"],
    )


def load_deployment_attestation(
    data_dir: Path,
    *,
    expected_whitelist: tuple[str, ...] = ("ComfyUI-GGUF",),
) -> DeploymentAttestation:
    """Strictly validate the v4 launcher attestation.

    ``expected_whitelist`` is the caller's REQUIRED custom-node identity:
    the frozen M5 default (ComfyUI-GGUF) for the predecessor/schema-2
    path; the M10E schema-3 path derives it from the CAPTURED runtime
    requirement, so a correct commit attached to the WRONG whitelisted
    node is rejected exactly like a wrong commit."""
    doc = _read_json(Path(data_dir) / "comfy-fingerprint"
                     / ATTESTATION_FILENAME)
    if doc.get("schema_version") != ATTESTATION_SCHEMA_VERSION:
        raise CapabilityRecordInvalid(
            f"attestation schema_version must be {ATTESTATION_SCHEMA_VERSION}")
    att = doc.get("attestation")
    if not isinstance(att, dict):
        raise CapabilityRecordInvalid("attestation object missing")
    if not _is_commit(att.get("comfyui_commit")) or not _is_commit(
            att.get("gguf_commit")):
        raise CapabilityRecordInvalid("attestation commits must be 40-hex")
    origin = att.get("executor_origin")
    if not is_loopback_origin(origin or ""):
        raise CapabilityRecordInvalid(
            "attestation executor_origin missing or not loopback "
            "(v0.1 is a local-only dedicated deployment)")
    # v4: the executable extension set must be MECHANICALLY enforced —
    # all custom nodes disabled except the pinned whitelist. Imported
    # custom-node code is ordinary Python; an attestation without this
    # policy does not fingerprint what the process actually executes.
    # The SHAPE is strict (disable_all + exactly ONE whitelisted custom
    # node, whose commit is pinned in the attestation's custom-node
    # commit slot) AND the NAME must equal the caller's expected
    # deployment identity.
    policy = att.get("custom_node_policy")
    whitelist = (policy or {}).get("whitelist")
    if (not isinstance(policy, dict)
            or set(policy) != {"disable_all", "whitelist"}
            or policy.get("disable_all") is not True
            or not isinstance(whitelist, list)
            or len(whitelist) != 1
            or not isinstance(whitelist[0], str)
            or not whitelist[0]):
        raise CapabilityRecordInvalid(
            "attestation custom_node_policy must be exactly "
            '{"disable_all": true, "whitelist": [<one custom node>]}; '
            f"got {policy!r}")
    if tuple(whitelist) != tuple(expected_whitelist):
        raise CapabilityRecordInvalid(
            f"attested custom-node identity {whitelist!r} does not match "
            f"the required deployment whitelist "
            f"{list(expected_whitelist)!r} — the attestation does not "
            "describe the expected executable extension set")
    pid = att.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        raise CapabilityRecordInvalid("attestation pid missing/invalid")
    fingerprint = att.get("process_start_fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint:
        raise CapabilityRecordInvalid(
            "attestation process_start_fingerprint missing")
    launched = att.get("launched_at")
    if not isinstance(launched, str) or not launched:
        raise CapabilityRecordInvalid("attestation launched_at missing")
    return DeploymentAttestation(
        comfyui_commit=att["comfyui_commit"],
        gguf_commit=att["gguf_commit"],
        executor_origin=normalize_origin(att["executor_origin"]),
        custom_node_policy=tuple(policy["whitelist"]),
        pid=pid,
        process_start_fingerprint=fingerprint,
        launched_at=launched,
    )


def build_capability_record(
    *, comfyui_commit: str, comfyui_version: str, gguf_commit: str,
    frontend: str | None = None, torch: str | None = None,
    observed_at: str | None = None,
    runtime_policy: dict | None = None,
    extra_conclusions: dict | None = None,
) -> dict:
    """Emit the v1 record document (M5B-5 script + M5B-7 gate use this)."""
    doc = {
        "schema_version": RECORD_SCHEMA_VERSION,
        "executor_fingerprint": {
            "comfyui_commit": comfyui_commit,
            "comfyui_version": comfyui_version,
            "gguf_commit": gguf_commit,
        },
        "running_cancel": {
            "mode": "TARGETED",
            "endpoint": "POST /api/jobs/{prompt_id}/cancel",
            "targeting_key": "prompt_id",
            "uniqueness_guarantee": "proven",
            "retry_safety": "safe",
        },
    }
    fp = doc["executor_fingerprint"]
    if frontend:
        fp["frontend"] = frontend
    if torch:
        fp["torch"] = torch
    if observed_at:
        doc["observed_at"] = observed_at
    if runtime_policy:
        doc["runtime_policy"] = runtime_policy
    if extra_conclusions:
        doc["conclusions"] = extra_conclusions
    # The emitted document must itself satisfy the strict loader.
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "comfy-fingerprint"
        p.mkdir()
        (p / RECORD_FILENAME).write_text(json.dumps(doc, indent=2),
                                         encoding="utf-8")
        load_capability_record(Path(td))
    return doc


def build_deployment_attestation(
    *, comfyui_commit: str, gguf_commit: str, launched_at: str,
    pid: int, process_start_fingerprint: str, executor_origin: str,
    custom_node_whitelist: tuple[str, ...] = ("ComfyUI-GGUF",),
) -> dict:
    """Emit the v4 attestation document (scripts/launch_comfy.py — only
    after proving the launched process serves the whitelisted executor).
    ``custom_node_whitelist`` names the ONE custom node the launcher
    actually whitelisted (predecessor default: ComfyUI-GGUF; the M10E
    Wan deployment supplies ComfyUI-WanVideoWrapper) — the attestation
    must describe the executable extension set of the attested process."""
    doc = {
        "schema_version": ATTESTATION_SCHEMA_VERSION,
        "attestation": {
            "comfyui_commit": comfyui_commit,
            "gguf_commit": gguf_commit,
            "executor_origin": normalize_origin(executor_origin),
            "custom_node_policy": {"disable_all": True,
                                   "whitelist": list(custom_node_whitelist)},
            "pid": pid,
            "process_start_fingerprint": process_start_fingerprint,
            "launched_at": launched_at,
        },
    }
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "comfy-fingerprint"
        p.mkdir()
        (p / ATTESTATION_FILENAME).write_text(json.dumps(doc, indent=2),
                                              encoding="utf-8")
        load_deployment_attestation(
            Path(td), expected_whitelist=custom_node_whitelist)
    return doc


def verify_live_process(attestation: DeploymentAttestation,
                        port: int = 8188) -> bool:
    """True iff the attested process is STILL the one serving `port`.

    The stale-attestation defense (final-verification patch F2): compares
    the OS pid and its creation-time fingerprint against the listener on
    the executor port. A manual same-version replacement (different pid,
    or same pid recycled after reboot with a different CreationDate)
    invalidates the attestation. Windows CIM is the source; POSIX would
    use /proc/<pid> starttime.
    """
    import subprocess

    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-NetTCPConnection -LocalPort %d -State Listen "
         "-ErrorAction SilentlyContinue | "
         "Select-Object -First 1 -ExpandProperty OwningProcess" % port],
        capture_output=True, text=True, timeout=15)
    pid_str = out.stdout.strip()
    if not pid_str.isdigit() or int(pid_str) != attestation.pid:
        return False
    out2 = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-CimInstance Win32_Process -Filter "
         '"ProcessId=%d").CreationDate' % attestation.pid],
        capture_output=True, text=True, timeout=15)
    return out2.stdout.strip() == attestation.process_start_fingerprint


def capture_process_start_fingerprint(pid: int) -> str:
    """The launcher-side counterpart of the creation-time fingerprint."""
    import subprocess

    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-CimInstance Win32_Process -Filter "
         '"ProcessId=%d").CreationDate' % pid],
        capture_output=True, text=True, timeout=15)
    fp = out.stdout.strip()
    if not fp:
        raise CapabilityRecordInvalid(
            f"cannot capture start fingerprint for pid {pid}")
    return fp
