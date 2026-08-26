"""Production D0 box-depth materializer (certified §114 evidence-backed).

Faithful production port of the certified reference implementation
(soloring.boxdepth.rasterizer v1.0.0, reference sha256 7328c77c…, exercised
by the §114 GPU smoke). Pure Python + numpy CPU rasterization; float64
intermediates; D0 byte-determinism. The output grammar is the frozen
as-smoked §114.5 encoding:

    float32 linear-metric depth (mm)
        -> per-spec affine uint8 [d_min, d_max], background sentinel -> 255
        -> 17-frame PNG sequence, 832x480, L-mode, time base 1/17

Movable Entities use the frozen box-standin-v1 proxy policy (§115):
execution-only oriented boxes from captured derivation parameters; never
authority.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image

from soloring.spatial import production_pins as pins

BG_DEPTH_MM = 4294967295.0  # float32-domain sentinel from the reference

# 12 box triangles in fixed winding (corner enumeration of the reference).
BOX_FACES = [
    (0, 1, 3), (0, 3, 2), (4, 6, 7), (4, 7, 5), (0, 4, 5), (0, 5, 1),
    (2, 3, 7), (2, 7, 6), (0, 2, 6), (0, 6, 4), (1, 5, 7), (1, 7, 3),
]


def _euler_xyz_to_r(rot_deg):
    rx, ry, rz = (np.radians(np.asarray(rot_deg, dtype=np.float64)))
    Rx = np.array([[1, 0, 0], [0, np.cos(rx), -np.sin(rx)],
                    [0, np.sin(rx), np.cos(rx)]])
    Ry = np.array([[np.cos(ry), 0, np.sin(ry)], [0, 1, 0],
                    [-np.sin(ry), 0, np.cos(ry)]])
    Rz = np.array([[np.cos(rz), -np.sin(rz), 0], [np.sin(rz), np.cos(rz), 0],
                    [0, 0, 1]])
    return Rz @ Ry @ Rx


def _box_corners(center_mm, half_extents_mm, rot_deg):
    c = np.asarray(center_mm, dtype=np.float64)
    h = np.asarray(half_extents_mm, dtype=np.float64)
    R = _euler_xyz_to_r(rot_deg)
    out = []
    for dx in (-h[0], h[0]):
        for dy in (-h[1], h[1]):
            for dz in (-h[2], h[2]):
                out.append(c + R @ np.array([dx, dy, dz], dtype=np.float64))
    return np.array(out)


def _interp_keyframes(kfs, t):
    ks = sorted(kfs, key=lambda k: k["t"])
    if t <= ks[0]["t"]:
        return np.asarray(ks[0]["value"], dtype=np.float64)
    if t >= ks[-1]["t"]:
        return np.asarray(ks[-1]["value"], dtype=np.float64)
    for a, b in zip(ks, ks[1:]):
        if a["t"] <= t <= b["t"]:
            f = (t - a["t"]) / (b["t"] - a["t"])
            va = np.asarray(a["value"], dtype=np.float64)
            vb = np.asarray(b["value"], dtype=np.float64)
            return va + (vb - va) * f
    raise AssertionError("unreachable")


def _rasterize(tris_world, entity_ids, cam, W, H, near, far):
    w2c = np.asarray(cam["w2c_3x4"], dtype=np.float64)
    fx, fy, cx, cy = (float(cam[k]) for k in ("fx", "fy", "cx", "cy"))
    depth = np.full((H, W), BG_DEPTH_MM, dtype=np.float64)
    inst = np.zeros((H, W), dtype=np.uint16)
    tri_cam = tris_world @ w2c[:, :3].T + w2c[:, 3:4].T
    z = tri_cam[:, :, 2]
    with np.errstate(divide="ignore", invalid="ignore"):
        u = (tri_cam[:, :, 0] / -z) * fx + cx
        v = (tri_cam[:, :, 1] / -z) * fy + cy
    vis = (np.all((z < -near) & (z > -far), axis=1)
           & np.all(np.isfinite(u), axis=1) & np.all(np.isfinite(v), axis=1))
    for ti in range(len(tris_world)):
        if not vis[ti]:
            continue
        x0 = max(int(np.floor(u[ti].min())), 0)
        x1 = min(int(np.ceil(u[ti].max())), W - 1)
        y0 = max(int(np.floor(v[ti].min())), 0)
        y1 = min(int(np.ceil(v[ti].max())), H - 1)
        if x0 > x1 or y0 > y1:
            continue
        xs, ys = np.meshgrid(
            np.arange(x0, x1 + 1, dtype=np.float64),
            np.arange(y0, y1 + 1, dtype=np.float64))
        det = ((u[ti, 1] - u[ti, 0]) * (v[ti, 2] - v[ti, 0])
               - (u[ti, 2] - u[ti, 0]) * (v[ti, 1] - v[ti, 0]))
        if abs(det) < 1e-30:
            continue
        w0 = (((u[ti, 1] - u[ti, 0]) * (ys - v[ti, 0])
               - (v[ti, 1] - v[ti, 0]) * (xs - u[ti, 0])) / det)
        w1 = (((v[ti, 2] - v[ti, 0]) * (xs - u[ti, 0])
               - (u[ti, 2] - u[ti, 0]) * (ys - v[ti, 0])) / det)
        w2b = 1.0 - w0 - w1
        inside = (w0 >= 0) & (w1 >= 0) & (w2b >= 0)
        if not inside.any():
            continue
        zi = w0 * z[ti, 0] + w1 * z[ti, 1] + w2b * z[ti, 2]
        d = -zi
        region = depth[y0:y1 + 1, x0:x1 + 1]
        reg_inst = inst[y0:y1 + 1, x0:x1 + 1]
        closer = inside & (d < region)
        region[closer] = d[closer]
        reg_inst[closer] = entity_ids[ti]
    return depth, inst


def materialize_depth_mm(continuity_pack: dict) -> np.ndarray:
    """Captured SpatialContinuityPack -> [F, H, W] float32 metric depth.

    Pure with respect to SoloRing DB/network/current state: the pack is
    the complete authority input (frozen §57). World frames with extents
    contribute oriented occupancy; staged entities contribute proxy boxes
    under the box-standin-v1 policy; the camera comes from the captured
    plan with piecewise-linear-clamped keyframe interpolation (§47).
    """
    p = pins
    W, H, F = p.GRAMMAR_WIDTH, p.GRAMMAR_HEIGHT, p.GRAMMAR_FRAMES
    near, far = 1.0, 100000.0
    world = continuity_pack["spatial_world"]["world_snapshot"]
    frames = sorted(world["frames"],
                    key=lambda f: (f["frame_key"], f["spatial_frame_id"]))
    entities = sorted(continuity_pack["staging"],
                      key=lambda s: (s["entity_id"], s["spatial_track_id"]))
    out = []
    for f in range(F):
        t = f / (F - 1) if F > 1 else 0.0
        tris, eids = [], []
        for fr in frames:
            if fr.get("half_extents_mm") is None:
                continue  # frameless landmarks stay invisible (§107.1)
            corners = _box_corners(
                fr["transform"]["translation_mm"],
                fr["half_extents_mm"],
                [v / 1_000_000 for v in fr["transform"]["rotation_udeg"]])
            for tri in BOX_FACES:
                tris.append(corners[list(tri)])
                eids.append(0)
        for idx, st in enumerate(entities, start=1):
            pos = st["transform"]["translation_mm"]
            rot = [v / 1_000_000
                   for v in st["transform"]["rotation_udeg"]]
            half = st.get("proxy_half_extents_mm",
                          list(pins.PROXY_DEFAULT_ENTITY_HALF_EXTENTS_MM))
            corners = _box_corners(pos, half, rot)
            for tri in BOX_FACES:
                tris.append(corners[list(tri)])
                eids.append(idx)
        plan_kfs = continuity_pack["shot_plan"]["camera"]["keyframes"]
        pose = _interp_keyframes(
            [{"t": k["time_ms"],
              "value": k["transform"]["translation_mm"] + k["transform"][
                  "rotation_udeg"]} for k in plan_kfs],
            t * 4000.0)  # 17-frame span over 4s shot; §47 policy
        tvals = _interp_keyframes(
            [{"t": k["time_ms"],
              "value": k["transform"]["translation_mm"]} for k in plan_kfs],
            t * 4000.0)
        rvals = _interp_keyframes(
            [{"t": k["time_ms"],
              "value": [v / 1_000_000
                        for v in k["transform"]["rotation_udeg"]]}
             for k in plan_kfs], t * 4000.0)
        R = _euler_xyz_to_r(rvals)
        c2w = np.eye(4)
        c2w[:3, :3] = R
        c2w[:3, 3] = tvals
        w2c = np.linalg.inv(c2w)[:3, :]
        optics = continuity_pack["shot_plan"]["camera"]
        # pinhole: fx = fy = focal * width / sensor_width; principal center
        focal = optics["focal_length_um"]
        sensor_w = optics["sensor_width_um"]
        fx = fy = focal * W / sensor_w
        cam = {"w2c_3x4": w2c.tolist(), "fx": fx, "fy": fy,
               "cx": W / 2.0, "cy": H / 2.0}
        depth, _ = _rasterize(np.array(tris) if tris else np.zeros(
            (0, 3, 3)), eids, cam, W, H, near, far)
        out.append(depth)
    return np.stack(out).astype(np.float32)


def encode_control_pngs(depth_mm: np.ndarray) -> list[bytes]:
    """§114.5 frozen encoding: per-spec affine uint8, BG->255, PNG L-mode.

    A role whose view contains no valid geometry (e.g. an entity layer
    whose proxy box is entirely off-frame) encodes as all-background
    frames under the frozen [0, 255] affine — deterministic, no error.
    """
    valid = depth_mm[depth_mm < BG_DEPTH_MM]
    if valid.size:
        d_min = float(valid.min())
        d_max = float(valid.max())
    else:
        d_min, d_max = 0.0, 1.0
    frames = []
    for f in range(depth_mm.shape[0]):
        d = depth_mm[f]
        v = np.where(d >= BG_DEPTH_MM, float(pins.GRAMMAR_BACKGROUND),
                     np.clip((d - d_min) * 255.0 / max(d_max - d_min, 1e-9),
                             0, 255))
        buf = io.BytesIO()
        Image.fromarray(v.astype(np.uint8), mode=pins.GRAMMAR_MODE).save(
            buf, format="PNG")
        frames.append(buf.getvalue())
    return frames


def materialize(continuity_pack: dict) -> list[bytes]:
    """Complete D0 materialization: pack -> 17 PNG control frames."""
    return encode_control_pngs(materialize_depth_mm(continuity_pack))


def artifact_digest(frames: list[bytes]) -> str:
    h = hashlib.sha256()
    for frame in frames:
        h.update(frame)
    return h.hexdigest()


def write_frames(frames: list[bytes], directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, data in enumerate(frames):
        p = directory / ("%03d.png" % i)
        p.write_bytes(data)
        paths.append(p)
    return paths


__all__ = [
    "materialize", "materialize_depth_mm", "encode_control_pngs",
    "artifact_digest", "write_frames", "BOX_FACES", "BG_DEPTH_MM",
]
