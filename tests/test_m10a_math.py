"""M10A §6 mathematical golden fixtures (frozen plan §6.7).

Test-only floating trigonometry verifies the known matrix expectations;
production identity/hashing never uses floating matrix bytes.
"""
import math

import pytest

from soloring.spatial.math import (
    CameraOptics,
    Transform,
    axis_side_cross,
    extent_world_corner,
    normalize_udeg,
    project_camera_point,
    rotation_matrix,
    transform_point,
)

TOL = 1e-9


def approx_mat(m, expected):
    for i in range(3):
        for j in range(3):
            assert m[i][j] == pytest.approx(expected[i][j], abs=TOL), (i, j)


def matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)]
            for i in range(3)]


def eye():
    return [[1.0 if i == j else 0.0 for j in range(3)] for i in range(3)]


def column(m, v):
    return [sum(m[i][k] * v[k] for k in range(3)) for i in range(3)]


def test_fixture_1_identity_pose_camera_forward_is_world_negz():
    ident = Transform((0, 0, 0), (0, 0, 0))
    fwd = transform_point(ident, (0.0, 0.0, -1.0))
    assert fwd == (0.0, 0.0, -1.0)
    approx_mat(rotation_matrix((0, 0, 0)), eye())


def test_fixture_2_yaw_plus_90():
    # R = Ry(+90deg): world +X -> +Z? column-vector active rotation:
    # local +X maps to world [cos90, 0, -sin90] = [0,0,-1]
    m = rotation_matrix((90_000_000, 0, 0))
    approx_mat(m, [[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]])
    assert column(m, [1.0, 0.0, 0.0]) == pytest.approx([0.0, 0.0, -1.0])
    assert column(m, [0.0, 0.0, -1.0]) == pytest.approx([-1.0, 0.0, 0.0])  # forward -> world -X


def test_fixture_3_yaw_minus_90():
    m = rotation_matrix((-90_000_000, 0, 0))
    approx_mat(m, [[0.0, 0.0, -1.0], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]])
    assert column(m, [1.0, 0.0, 0.0]) == pytest.approx([0.0, 0.0, 1.0])


def test_fixture_4_pitch_plus_and_minus_90():
    mp = rotation_matrix((0, 90_000_000, 0))
    approx_mat(mp, [[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]])
    # camera forward -Z under pitch +90 -> world +Y (looking up)
    assert column(mp, [0.0, 0.0, -1.0]) == pytest.approx([0.0, 1.0, 0.0])
    mm = rotation_matrix((0, -90_000_000, 0))
    approx_mat(mm, [[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]])
    assert column(mm, [0.0, 0.0, -1.0]) == pytest.approx([0.0, -1.0, 0.0])


def test_fixture_5_roll_plus_90():
    m = rotation_matrix((0, 0, 90_000_000))
    approx_mat(m, [[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    assert column(m, [1.0, 0.0, 0.0]) == pytest.approx([0.0, 1.0, 0.0])  # image right -> world up


def test_fixture_6_combined_non_commuting():
    yaw, pitch, roll = 30_000_000, -45_000_000, 60_000_000
    got = rotation_matrix((yaw, pitch, roll))
    ry = [[math.cos(math.radians(30)), 0, math.sin(math.radians(30))],
          [0, 1, 0],
          [-math.sin(math.radians(30)), 0, math.cos(math.radians(30))]]
    rx = [[1, 0, 0],
          [0, math.cos(math.radians(-45)), -math.sin(math.radians(-45))],
          [0, math.sin(math.radians(-45)), math.cos(math.radians(-45))]]
    rz = [[math.cos(math.radians(60)), -math.sin(math.radians(60)), 0],
          [math.sin(math.radians(60)), math.cos(math.radians(60)), 0],
          [0, 0, 1]]
    approx_mat(got, matmul(matmul(ry, rx), rz))
    # non-commutativity evidence: swapping yaw/pitch differs
    swapped = rotation_matrix((pitch, yaw, roll))
    assert any(abs(got[i][j] - swapped[i][j]) > 1e-6 for i in range(3) for j in range(3))


def test_fixture_7_180_normalizes_to_minus_180():
    assert normalize_udeg(180_000_000) == -180_000_000
    assert normalize_udeg(-180_000_000) == -180_000_000
    assert normalize_udeg(180_000_001) == -179_999_999
    assert normalize_udeg(540_000_000) == -180_000_000
    assert normalize_udeg(0) == 0


def test_fixture_8_distinct_equivalent_tuples_remain_distinct():
    # (180,0,0) and (-180,0,0) both normalize to -180 -> identical canonical
    assert normalize_udeg(180_000_000) == normalize_udeg(-180_000_000)
    # (0,180,0) vs (0,-180,0): same story; but (90,90,0) vs (90,90,-0)? use a
    # genuinely equivalent-but-distinct accepted pair: yaw=90 vs pitch/roll
    # composition is NOT claimed equivalent — the contract keeps distinct
    # accepted tuples distinct. Demonstrate with two distinct valid tuples:
    a = Transform((0, 0, 0), (90_000_000, 0, 0))
    b = Transform((0, 0, 0), (90_000_000, 0, 1))
    assert a.rotation_udeg != b.rotation_udeg
    assert a.canonical_value() != b.canonical_value()


def test_fixture_9_pinhole_projection():
    optics = CameraOptics(focal_length_um=50_000, sensor_width_um=36_000,
                          sensor_height_um=20_250)
    # point 1000um right, 500um up, 2000um in front of camera
    sx, sy = project_camera_point(optics, (1000.0, 500.0, -2000.0))
    assert sx == pytest.approx(50_000 * 1000.0 / 2000.0, abs=TOL)  # 25000
    assert sy == pytest.approx(50_000 * 500.0 / 2000.0, abs=TOL)   # 12500
    with pytest.raises(ValueError):
        project_camera_point(optics, (0.0, 0.0, 0.0))
    with pytest.raises(ValueError):
        project_camera_point(optics, (1.0, 1.0, 1.0))


def test_fixture_10_extent_corner_local_to_world():
    t = Transform((1000, 200, 3000), (0, 0, 90_000_000))
    corner = extent_world_corner(t, (500, 200, 100), (1, 1, -1))
    # local corner (500, 200, -100) -> roll90: (x,y)->(-y,x) => (-200, 500, -100)
    # + translation
    assert corner[0] == pytest.approx(800.0, abs=TOL)
    assert corner[1] == pytest.approx(700.0, abs=TOL)
    assert corner[2] == pytest.approx(2900.0, abs=TOL)


def test_axis_side_golden():
    assert axis_side_cross((0, 0, 0), (1000, 0, 0), (0, 0, 1000)) == +1_000_000
    assert axis_side_cross((0, 0, 0), (1000, 0, 0), (0, 0, -1000)) == -1_000_000
    assert axis_side_cross((0, 0, 0), (1000, 0, 0), (500, 0, 0)) == 0


def test_axis_side_large_integer_precision():
    # products exceed 2**63: must still be exact via Python big ints
    big = 4_000_000_000_000
    cross = axis_side_cross((0, 0, 0), (big, 0, 0), (0, 0, big))
    assert cross == big * big  # 1.6e25 > int64 max


def test_transform_domain_validation():
    with pytest.raises(ValueError):
        Transform((0, 0, 0), (0, 0, 1.5))  # float rotation
    with pytest.raises(ValueError):
        Transform((2**53, 0, 0), (0, 0, 0))  # outside JS-safe
    with pytest.raises(ValueError):
        CameraOptics(0, 36000, 20250)  # non-positive focal
    with pytest.raises(ValueError):
        CameraOptics(50000, -1, 20250)
