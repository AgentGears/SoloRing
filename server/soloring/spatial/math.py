"""M10 schema-1 exact coordinate/transform/camera mathematics (frozen plan §6).

Pure integer-domain authority math. The matrix formula R = Ry·Rx·Rz defines
meaning; prose order is explanatory only. Production identity/hashing never
uses floating matrix bytes — floats appear only inside test-side golden
verification (§6.7) and downstream execution derivation, never in canonical
authority bytes.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

UDEG_MIN = -180_000_000
UDEG_MAX = +180_000_000
JS_SAFE_MAX = 9_007_199_254_740_991  # 2**53 - 1
JS_SAFE_MIN = -JS_SAFE_MAX


def normalize_udeg(value: int) -> int:
    """Normalize one rotation component into [-180000000, +180000000).

    Exactly +180000000 canonicalizes to -180000000 (§6.4). The normalized
    integer tuple is authoritative; no physical-equivalence reduction across
    distinct accepted tuples is performed.
    """
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("rotation component must be an int")
    span = 360_000_000
    n = ((value - UDEG_MIN) % span) + UDEG_MIN
    return n


def validate_int(value: int, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{what} must be an int")
    if not (JS_SAFE_MIN <= value <= JS_SAFE_MAX):
        raise ValueError(f"{what} outside JavaScript-safe integer domain")
    return value


@dataclass(frozen=True)
class Transform:
    """§6.4 canonical integer transform: translation_mm + rotation_udeg."""

    translation_mm: tuple[int, int, int]
    rotation_udeg: tuple[int, int, int]

    def __post_init__(self) -> None:
        for axis, v in enumerate(self.translation_mm):
            validate_int(v, f"translation_mm[{axis}]")
        comps = [normalize_udeg(v) for v in self.rotation_udeg]
        object.__setattr__(self, "rotation_udeg", tuple(comps))

    def canonical_value(self) -> dict:
        return {
            "translation_mm": list(self.translation_mm),
            "rotation_udeg": list(self.rotation_udeg),
        }


def _ry(a: float) -> list[list[float]]:
    return [[math.cos(a), 0.0, math.sin(a)],
            [0.0, 1.0, 0.0],
            [-math.sin(a), 0.0, math.cos(a)]]


def _rx(a: float) -> list[list[float]]:
    return [[1.0, 0.0, 0.0],
            [0.0, math.cos(a), -math.sin(a)],
            [0.0, math.sin(a), math.cos(a)]]


def _rz(a: float) -> list[list[float]]:
    return [[math.cos(a), -math.sin(a), 0.0],
            [math.sin(a), math.cos(a), 0.0],
            [0.0, 0.0, 1.0]]


def _mat_mul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)]
            for i in range(3)]


def rotation_matrix(rotation_udeg: tuple[int, int, int]) -> list[list[float]]:
    """R = Ry(yaw) · Rx(pitch) · Rz(roll); active, local→world (§6.2).

    Floating-point is used only to materialize the reference matrices; the
    authoritative identity remains the normalized integer tuple.
    """
    yaw, pitch, roll = (math.radians(v / 1_000_000) for v in rotation_udeg)
    return _mat_mul(_ry(yaw), _mat_mul(_rx(pitch), _rz(roll)))


def apply_rotation(rotation_udeg: tuple[int, int, int],
                   p_local: tuple[float, float, float]) -> tuple[float, float, float]:
    r = rotation_matrix(rotation_udeg)
    return tuple(sum(r[i][k] * p_local[k] for k in range(3)) for i in range(3))  # type: ignore[return-value]


def transform_point(t: Transform,
                    p_local: tuple[float, float, float]) -> tuple[float, float, float]:
    """p_world = R · p_local + t (§6.2)."""
    r = apply_rotation(t.rotation_udeg, p_local)
    return (r[0] + t.translation_mm[0],
            r[1] + t.translation_mm[1],
            r[2] + t.translation_mm[2])


@dataclass(frozen=True)
class CameraOptics:
    """§6.3 ideal pinhole: strictly positive integer micrometers."""

    focal_length_um: int
    sensor_width_um: int
    sensor_height_um: int

    def __post_init__(self) -> None:
        for name in ("focal_length_um", "sensor_width_um", "sensor_height_um"):
            v = getattr(self, name)
            if not isinstance(v, int) or isinstance(v, bool) or v <= 0:
                raise ValueError(f"{name} must be a positive int")
            validate_int(v, name)


def project_camera_point(optics: CameraOptics,
                         p_cam: tuple[float, float, float]) -> tuple[float, float]:
    """Project a camera-local point under the §6.3 pinhole convention.

    Defined only for z < 0 (camera forward is -Z). Returns sensor-plane
    (sensor_x_um, sensor_y_um); principal point is the sensor center and
    this function returns offsets from it, matching the frozen equation:

        sensor_x_um = focal_length_um * x / (-z)
        sensor_y_um = focal_length_um * y / (-z)

    z >= 0 is not projectable and raises.
    """
    x, y, z = p_cam
    if z >= 0:
        raise ValueError("point not projectable: camera-local z must be < 0")
    return (optics.focal_length_um * x / (-z),
            optics.focal_length_um * y / (-z))


def extent_world_corner(t: Transform, half_extents_mm: tuple[int, int, int],
                        corner_signs: tuple[int, int, int]) -> tuple[float, float, float]:
    """Transform one frame-local extent corner to world (§6.5 + §6.7-10).

    Extents are frame-local half dimensions centered at the frame origin;
    corner_signs selects (+/-1) per local axis.
    """
    local = tuple(s * h for s, h in zip(corner_signs, half_extents_mm))
    return transform_point(t, local)  # type: ignore[return-value]


def axis_side_cross(a: tuple[int, int, int], b: tuple[int, int, int],
                    c: tuple[int, int, int]) -> int:
    """§11.1 ground-plane side predicate in exact integer arithmetic.

    cross = (Bx-Ax)*(Cz-Az) - (Bz-Az)*(Cx-Ax)
    Must run on Python ints (arbitrary precision) — never float/SQLite/JS.
    """
    cross = (b[0] - a[0]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[0] - a[0])
    return cross
