"""Comfy capability report + readiness evaluation (M5A-2; M5 plan §16, §66).

The report is versioned, evidence-backed, and tri-state per feature
(supported / unsupported / unknown) — never booleans. Version is diagnostic;
capability conclusions come from recorded evidence, not version arithmetic
(M5A-2 invariant 7). Cancellation capability keeps the structured mode/target
shape so later slices can classify TARGETED / SAFE_SINGLE_FLIGHT / SOFT_ONLY /
UNSUPPORTED without redesigning the report.

Pure evaluation: build_* functions are deterministic functions of their
evidence inputs. observed_at is supplied by the caller (outside the pure
normalizers), and canonical report bytes are fixture-pinned.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class FeatureState(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class ReadinessStatus(str, Enum):
    READY = "ready"
    INCOMPATIBLE = "incompatible"
    UNAVAILABLE = "unavailable"


class CancellationMode(str, Enum):
    """Structured running-cancellation classification (M5 §47-§50)."""

    TARGETED = "targeted"
    SAFE_SINGLE_FLIGHT = "safe_single_flight"
    SOFT_ONLY = "soft_only"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


CAPABILITY_PROFILE_VERSION = 1

FEATURE_KEYS = (
    "prompt_submission",
    "queue_observation",
    "targeted_history",
    "marker_roundtrip",
    "websocket_progress",
    "input_upload",
    "output_view",
    "pending_cancel",
    "running_cancel",
)


@dataclass(frozen=True)
class Evidence:
    """How a capability conclusion was reached (M5A-2 invariant 6)."""

    feature: str
    conclusion: FeatureState
    method: str  # e.g. "endpoint_probe", "marker_canary", "endpoint_rejected", "unprobed"
    detail: str = ""


@dataclass(frozen=True)
class CancellationCapability:
    mode: CancellationMode = CancellationMode.UNKNOWN
    targeting_key: str | None = None  # e.g. "prompt_id" when targeted
    uniqueness_guarantee: str | None = None
    # M5A-8 §3: repeating the operation against the SAME prompt after an
    # ambiguous response cannot affect another prompt. hard cancel is
    # automatic only when targeted AND retry_safety == "safe".
    retry_safety: str = "unknown"  # "safe" | "unsafe" | "unknown"


@dataclass(frozen=True)
class ComfyCapabilityReport:
    capability_profile_version: int = CAPABILITY_PROFILE_VERSION
    observed_at: str | None = None  # caller-supplied; not a normalizer concern
    executor_version: str | None = None
    wire_dialects: tuple[str, ...] = ()
    features: dict = field(default_factory=dict)
    cancellation: CancellationCapability = field(
        default_factory=CancellationCapability
    )
    evidence: tuple[Evidence, ...] = ()

    def feature(self, key: str) -> FeatureState:
        return self.features.get(key, FeatureState.UNKNOWN)


def unprobed_report(executor_version: str | None = None) -> ComfyCapabilityReport:
    """Every capability unknown: nothing has been actively probed yet."""
    return ComfyCapabilityReport(
        executor_version=executor_version,
        features={k: FeatureState.UNKNOWN for k in FEATURE_KEYS},
        evidence=tuple(
            Evidence(k, FeatureState.UNKNOWN, "unprobed") for k in FEATURE_KEYS
        ),
    )


REQUIRED_FEATURES_DEFAULT = (
    "prompt_submission",
    "queue_observation",
    "targeted_history",
    "marker_roundtrip",
    "input_upload",
    "output_view",
)


def evaluate_readiness(
    report: ComfyCapabilityReport,
    reachable: bool,
    required_features: tuple[str, ...] = REQUIRED_FEATURES_DEFAULT,
) -> ReadinessStatus:
    """READY iff every required feature is supported on a reachable service.

    INCOMPATIBLE: reachable enough to evaluate, but a mandatory capability is
    conclusively unsupported. UNAVAILABLE: cannot be meaningfully evaluated
    (including reachable-but-mandatory-capability-still-unknown: the caller
    should probe more before accepting work).
    """
    if not reachable:
        return ReadinessStatus.UNAVAILABLE
    states = [report.feature(k) for k in required_features]
    # A conclusive UNSUPPORTED outranks unprobed UNKNOWNs: the service was
    # reachable enough to reject the capability — that is INCOMPATIBLE, not
    # an outage (M5A-2 invariant 4).
    if any(st is FeatureState.UNSUPPORTED for st in states):
        return ReadinessStatus.INCOMPATIBLE
    if any(st is not FeatureState.SUPPORTED for st in states):
        return ReadinessStatus.UNAVAILABLE
    return ReadinessStatus.READY


def report_payload(report: ComfyCapabilityReport) -> dict:
    """JSON-safe canonical structure for fixture-pinning."""
    return {
        "capability_profile_version": report.capability_profile_version,
        "observed_at": report.observed_at,
        "executor_version": report.executor_version,
        "wire_dialects": list(report.wire_dialects),
        "features": {k: report.feature(k).value for k in FEATURE_KEYS},
        "cancellation": {
            "mode": report.cancellation.mode.value,
            "targeting_key": report.cancellation.targeting_key,
            "uniqueness_guarantee": report.cancellation.uniqueness_guarantee,
            "retry_safety": report.cancellation.retry_safety,
        },
        "evidence": [
            {
                "feature": e.feature,
                "conclusion": e.conclusion.value,
                "method": e.method,
                "detail": e.detail,
            }
            for e in sorted(report.evidence, key=lambda e: (e.feature, e.method))
        ],
    }
