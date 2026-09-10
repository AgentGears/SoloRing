"""M14 `soloring.structural_mesh.v1` — strict retained-mesh grammar
(frozen R2 §12) with the B1 resource-cap stages (§35.1).

The retained Blob bytes must ALREADY be canonical SoloRing JSON that
validates under the closed schema-1 grammar: closed field sets, the
frozen shared-subset coordinate contract, plain JS-safe integer
vertices, distinct in-range triangle indices, exact integer cross-
product degeneracy rejection, two-sided winding-free semantics. Stage B
element caps apply after strict grammar classification and before any
geometry expansion. The Stage A byte cap is enforced by the retained
loader from the immutable closure size plus the physical byte length
BEFORE JSON decode.
"""

from __future__ import annotations

import json

from soloring.domain.canonical import canonical_json_bytes
from soloring.errors import ErrorCode, SoloRingError, validation_error
from soloring.spatial.math import JS_SAFE_MAX, JS_SAFE_MIN

MAX_RETAINED_MESH_BYTES_PER_REVISION = 100_000_000
MAX_VERTICES_PER_REVISION = 3_000_000
MAX_TRIANGLES_PER_REVISION = 500_000
MAX_TOTAL_TRIANGLES_PER_OBSERVATION = 500_000

MESH_KIND = "soloring.structural_mesh"
REPRESENTATION_CONTRACT = "soloring.structural_mesh.v1"

COORDINATE_SYSTEM = {
    "handedness": "right",
    "right_axis": "+x",
    "up_axis": "+y",
    "depth_positive_axis": "+z",
    "forward_axis": "-z",
    "linear_unit": "millimeter",
    "vector_convention": "column",
}

_ROOT_KEYS = {"schema_version", "kind", "coordinate_system",
              "vertices_mm", "triangles"}


def _invalid(message: str):
    return validation_error(
        f"structural_mesh.v1: {message}")


def _limit_exceeded(message: str):
    return SoloRingError(
        ErrorCode.STRUCTURAL_MESH_LIMIT_EXCEEDED, message,
        status_code=409)


def _plain_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_grammar(doc) -> None:
    if not isinstance(doc, dict):
        raise _invalid("root must be an object")
    extra = sorted(set(doc) - _ROOT_KEYS)
    if extra:
        raise _invalid(f"root has unknown fields {extra}")
    missing = sorted(_ROOT_KEYS - set(doc))
    if missing:
        raise _invalid(f"root is missing fields {missing}")
    if doc["schema_version"] != 1 or _plain_int(doc["schema_version"
                                                   ]) is False:
        raise _invalid("schema_version must be the plain integer 1")
    if doc["kind"] != MESH_KIND:
        raise _invalid(f"kind must be exactly {MESH_KIND!r}")
    if doc["coordinate_system"] != COORDINATE_SYSTEM:
        raise _invalid(
            "coordinate_system must equal the frozen shared subset of "
            "the M13 realization-local contract exactly")

    vertices = doc["vertices_mm"]
    if not isinstance(vertices, list) or not vertices:
        raise _invalid("vertices_mm must be a non-empty array")
    for vertex in vertices:
        if (not isinstance(vertex, list) or len(vertex) != 3
                or any(not _plain_int(v) for v in vertex)):
            raise _invalid(
                "every vertex must be exactly three plain integers")
        if any(not (JS_SAFE_MIN <= v <= JS_SAFE_MAX) for v in vertex):
            raise _invalid("vertex component outside the JS-safe range")

    triangles = doc["triangles"]
    if not isinstance(triangles, list) or not triangles:
        raise _invalid("triangles must be a non-empty array")
    for triangle in triangles:
        if (not isinstance(triangle, list) or len(triangle) != 3
                or any(not _plain_int(i) for i in triangle)):
            raise _invalid(
                "every triangle must be exactly three plain integer "
                "indices")
        if len(set(triangle)) != 3:
            raise _invalid("triangle indices must be distinct")
        if any(not (0 <= i < len(vertices)) for i in triangle):
            raise _invalid("triangle index out of range")
        a, b, c = (vertices[i] for i in triangle)
        u = [b[k] - a[k] for k in range(3)]
        v = [c[k] - a[k] for k in range(3)]
        cross = [u[1] * v[2] - u[2] * v[1],
                 u[2] * v[0] - u[0] * v[2],
                 u[0] * v[1] - u[1] * v[0]]
        if cross == [0, 0, 0]:
            raise _invalid(
                "zero-area triangle rejected by exact integer cross "
                "product")


def parse_structural_mesh_v1(raw: bytes) -> dict:
    """Strict parse: canonical bytes, closed grammar, Stage B caps.

    Raises SoloRingError on any violation; returns the parsed document.
    """
    if not isinstance(raw, (bytes, bytearray)):
        raise _invalid("retained mesh bytes required")
    raw = bytes(raw)
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise _invalid(f"not valid UTF-8 JSON: {exc}") from exc
    if canonical_json_bytes(doc) != raw:
        raise _invalid(
            "source bytes must already equal canonical serialization")
    _validate_grammar(doc)

    if len(doc["vertices_mm"]) > MAX_VERTICES_PER_REVISION:
        raise _limit_exceeded(
            f"mesh has {len(doc['vertices_mm'])} vertices; "
            f"MAX_VERTICES_PER_REVISION is {MAX_VERTICES_PER_REVISION}")
    if len(doc["triangles"]) > MAX_TRIANGLES_PER_REVISION:
        raise _limit_exceeded(
            f"mesh has {len(doc['triangles'])} triangles; "
            f"MAX_TRIANGLES_PER_REVISION is {MAX_TRIANGLES_PER_REVISION}")
    return doc


def is_structural_mesh_grammar(raw: bytes) -> bool:
    """Representation classification (frozen §28.1 step 4).

    True iff the bytes are canonical JSON satisfying the closed schema-1
    grammar. Cap limits are deliberately NOT part of classification: an
    over-cap mesh is a recognized representation hitting a typed
    resource-limit refusal, never an unsupported representation.
    """
    try:
        if not isinstance(raw, (bytes, bytearray)):
            return False
        doc = json.loads(bytes(raw).decode("utf-8"))
        if canonical_json_bytes(doc) != bytes(raw):
            return False
        _validate_grammar(doc)
        return True
    except SoloRingError:
        return False
    except (ValueError, UnicodeDecodeError):
        return False


def structural_mesh_bytes(doc: dict) -> bytes:
    return canonical_json_bytes(doc)
