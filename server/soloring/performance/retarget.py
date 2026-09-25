"""Shared M17C PF-03 synchronization constants and typed errors."""

from soloring.errors import ErrorCode, SoloRingError

PERFORMANCE_VOCAL_BINDING_NOT_FOUND = "PERFORMANCE_VOCAL_BINDING_NOT_FOUND"
PERFORMANCE_VOCAL_BINDING_INVALID = "PERFORMANCE_VOCAL_BINDING_INVALID"
PERFORMANCE_VOCAL_SUBJECT_MISMATCH = "PERFORMANCE_VOCAL_SUBJECT_MISMATCH"
PERFORMANCE_VOCAL_PROJECT_MISMATCH = "PERFORMANCE_VOCAL_PROJECT_MISMATCH"
PERFORMANCE_VOCAL_INTERVAL_INVALID = "PERFORMANCE_VOCAL_INTERVAL_INVALID"
PERFORMANCE_VOCAL_ALIGNMENT_MISMATCH = "PERFORMANCE_VOCAL_ALIGNMENT_MISMATCH"
PERFORMANCE_REQUIRED_ARTICULATION_MISSING = "PERFORMANCE_REQUIRED_ARTICULATION_MISSING"

REQUIRED_ARTICULATION = (
    "profile-1/face.articulation.jaw_open",
    "profile-1/face.articulation.lip_round",
    "profile-1/face.articulation.lip_press",
    "profile-1/face.articulation.mouth_width",
)

BINDING_FIELDS = (
    "vocal_performance_revision_id",
    "source_start_sample",
    "source_end_sample_exclusive",
    "sample_rate_hz",
    "performance_origin_num",
    "performance_origin_den",
    "synchronization_basis_version",
    "binding_schema_version",
    "binding_json",
    "binding_hash",
)

def invalid(code: str, message: str) -> SoloRingError:
    return SoloRingError(code, message, status_code=422)

def corrupt(message: str) -> SoloRingError:
    return SoloRingError(ErrorCode.INTERNAL_INVARIANT_VIOLATION, message, status_code=500)

def strict_int(value, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise invalid(PERFORMANCE_VOCAL_BINDING_INVALID,
                      f"{what} must be an exact integer (bool is not an integer)")
    return value
