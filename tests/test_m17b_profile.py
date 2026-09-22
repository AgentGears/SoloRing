"""M17B profile/payload matrix (frozen proof-map owners B*, C*, D*)."""

from __future__ import annotations

import hashlib

import pytest

from soloring.performance.profile import build_canonical_payload
from tests.m17b_seed import (HEAD_YAW, JAW, SMILE, TORSO, candidate_body,
                             channel, kf)


def _build(body: dict):
    return build_canonical_payload(
        {"schema_version": 1,
         "performance_profile_id":
             body["performance_profile_id"],
         "channels": body["channels"]},
        performance_kind=body["performance_kind"],
        performance_profile_id="performance-profile/1",
        start_num=body["temporal_start"]["num"],
        start_den=body["temporal_start"]["den"],
        end_num=body["temporal_end"]["num"],
        end_den=body["temporal_end"]["den"])


def _err(body: dict):
    try:
        _build(body)
    except Exception as exc:  # noqa: BLE001
        return exc
    return None


def _face_body(channels, kind):
    return candidate_body(channels, kind=kind)


def test_b01_unknown_profile_rejects():
    e = _err(candidate_body([channel(SMILE, [kf(0, 1, 0)])],
                            profile="performance-profile/2"))
    assert getattr(e, "args", [None])[0] and "profile" in str(e)


def test_b02_body_with_face_channel_rejects():
    e = _err(candidate_body([channel(SMILE, [kf(0, 1, 0)])],
                            kind="BODY"))
    assert "face" in str(e)


def test_b03_facial_with_body_channel_rejects():
    e = _err(candidate_body([channel(HEAD_YAW, [kf(0, 1, 0)])],
                            kind="FACIAL"))
    assert "body" in str(e)


def test_b04_body_facial_missing_body_rejects():
    e = _err(candidate_body([channel(SMILE, [kf(0, 1, 0)])],
                            kind="BODY_FACIAL"))
    assert "body" in str(e)


def test_b05_body_facial_missing_face_rejects():
    e = _err(candidate_body([channel(HEAD_YAW, [kf(0, 1, 0)])],
                            kind="BODY_FACIAL"))
    assert "face" in str(e)


def test_b06_generic_facial_with_fewer_than_four_articulation_channels_passes():
    body = candidate_body([channel(SMILE, [kf(0, 1, 0)]),
                           channel(JAW, [kf(0, 1, 100)])],
                          kind="FACIAL")
    b, _ = _build(body)
    assert b


def test_b07_root_world_channel_rejects():
    root = ("profile-1/body.root.translation_x", "body", "pose",
            "root_translation_x", "bounded_scalar_ppm")
    e = _err(candidate_body([channel(HEAD_YAW, [kf(0, 1, 0)]),
                             channel(root, [kf(0, 1, 0)])], kind="BODY"))
    assert "unknown" in str(e).lower() or "not in" in str(e)


def test_b08_exact_profile_descriptors_pass():
    body = candidate_body([channel(SMILE, [kf(0, 1, 0)])])
    b, chs = _build(body)
    assert chs[0]["channel_key"] == SMILE[0]


def test_b09_descriptor_mismatch_rejects():
    bad = list(SMILE)
    bad[1] = "body"
    e = _err(candidate_body([channel(tuple(bad), [kf(0, 1, 0)])]))
    assert "domain" in str(e)


def test_c01_reducible_positive_denominator_canonicalizes():
    body = candidate_body(
        [channel(SMILE, [kf(0, 4, 0)])],
        start=(0, 4), end=(9000, 2))
    b, chs = _build(body)
    assert chs[0]["keyframes"][0]["time_ms"] == {"num": 0, "den": 1}


def test_c02_zero_canonicalizes_to_0_1():
    body = candidate_body(
        [channel(SMILE, [kf(0, 99, 0)])], start=(0, 50), end=(9000, 2))
    b, chs = _build(body)
    assert chs[0]["keyframes"][0]["time_ms"] == {"num": 0, "den": 1}


def test_c03_denominator_zero_rejects():
    e = _err(candidate_body([channel(SMILE, [kf(0, 0, 0)])]))
    assert "denominator" in str(e)


def test_c04_negative_denominator_rejects():
    e = _err(candidate_body(
        [channel(SMILE, [kf(0, -2, 0)])]))
    assert "denominator" in str(e) or "positive" in str(e)


def test_c05_signed_64_overflow_rejects():
    e = _err(candidate_body(
        [channel(SMILE, [kf(2 ** 63, 1, 0)])]))
    assert "64" in str(e) or "overflow" in str(e).lower()


def test_c06_start_end_rejects():
    e = _err(candidate_body([channel(SMILE, [kf(0, 1, 0)])],
                            start=(5, 1), end=(5, 1)))
    assert "less than end" in str(e)


def test_c07_start_rejects():
    e = _err(candidate_body([channel(SMILE, [kf(0, 1, 0)])],
                            start=(5, 1), end=(4, 1)))
    assert "less than end" in str(e)


def test_c08_negative_start_is_lawful_when_end_is_greater():
    body = candidate_body([channel(SMILE, [kf(-1000, 1, 0)])],
                          start=(-2000, 1), end=(4500, 1))
    b, chs = _build(body)
    assert chs[0]["keyframes"][0]["time_ms"] == {"num": -1000, "den": 1}


def test_c09_keyframe_exactly_at_start_passes():
    body = candidate_body([channel(SMILE, [kf(250, 1, 0)])],
                          start=(250, 1), end=(4500, 1))
    b, _ = _build(body)
    assert b


def test_c10_keyframe_exactly_at_exclusive_end_rejects():
    e = _err(candidate_body([channel(SMILE, [kf(4500, 1, 0)])],
                            start=(0, 1), end=(4500, 1)))
    assert "outside" in str(e) or "domain" in str(e)


def test_c11_fractional_rational_keyframe_inside_domain_passes_and_remains_exact():
    body = candidate_body(
        [channel(SMILE, [kf(2250, 2, 0)])], start=(0, 1),
        end=(4500, 1))
    b, chs = _build(body)
    assert chs[0]["keyframes"][0]["time_ms"] == {"num": 1125, "den": 1}
    body2 = candidate_body(
        [channel(SMILE, [kf(1, 3, 0)])], start=(0, 1), end=(4500, 1))
    b2, chs2 = _build(body2)
    assert chs2[0]["keyframes"][0]["time_ms"] == {"num": 1, "den": 3}


def test_d01_empty_payload_rejects():
    e = _err(candidate_body([]))
    assert "at least one channel" in str(e)


def test_d02_duplicate_channel_rejects():
    e = _err(candidate_body([channel(SMILE, [kf(0, 1, 0)]),
                             channel(SMILE, [kf(100, 1, 0)])]))
    assert "more than once" in str(e)


def test_d03_duplicate_canonical_keyframe_timestamp_rejects():
    e = _err(candidate_body(
        [channel(SMILE, [kf(0, 1, 0), kf(0, 1, 500)])]))
    assert "duplicate" in str(e)


def test_d04_unsorted_input_canonicalizes_deterministically():
    a = candidate_body([channel(JAW, [kf(100, 1, 5)]),
                        channel(SMILE, [kf(0, 1, 0), kf(200, 1, 7)])])
    b1, _ = _build(a)
    b2, _ = _build(a)
    assert b1 == b2
    import json
    doc = json.loads(b1.decode("utf-8"))
    keys = [c["channel_key"] for c in doc["channels"]]
    assert keys == sorted(keys)


def test_d05_float_timestamp_value_rejects():
    k = kf(0, 1, 0)
    k["value"] = 0.5
    e = _err(candidate_body([channel(SMILE, [k])]))
    assert "integer" in str(e)
    k2 = kf(0, 1, 0)
    k2["time_ms"] = {"num": 0.5, "den": 1}
    e2 = _err(candidate_body([channel(SMILE, [k2])]))
    assert e2 is not None


def test_d06_python_bool_value_rejects():
    k = kf(0, 1, True)
    e = _err(candidate_body([channel(SMILE, [k])]))
    assert "bool" in str(e)


def test_d07_out_of_range_ppm_rejects():
    k = kf(0, 1, 1_000_001)
    e = _err(candidate_body([channel(SMILE, [k])]))
    assert "outside" in str(e)
    k2 = kf(0, 1, -1_000_001)
    e2 = _err(candidate_body([channel(SMILE, [k2])]))
    assert "outside" in str(e2)


def test_d08_out_of_range_microdegree_rejects():
    k = kf(0, 1, 30_000_001)
    e = _err(candidate_body([channel(HEAD_YAW, [k])], kind="BODY"))
    assert "outside" in str(e)


@pytest.mark.asyncio
async def test_d09_canonical_payload_bytes_rehash_exactly_and_duplicate_digest_fields_agree(client):
    from tests.m17b_seed import (adopt, create_candidate, make_entity,
                                 make_project)
    pid = await make_project(client)
    eid = await make_entity(client, pid)
    c = await create_candidate(client, eid, candidate_body(
        [channel(SMILE, [kf(0, 1, 0)])]))
    assert c["canonical_channel_payload_sha256"] == \
        c["canonical_channel_payload_blob_hash"]
    engine = client._transport.app.state.engine
    from sqlalchemy import text
    settings = client._transport.app.state.settings
    p = (settings.blob_dir / "sha256" /
         c["canonical_channel_payload_blob_hash"][:2] /
         c["canonical_channel_payload_blob_hash"][2:4] /
         c["canonical_channel_payload_blob_hash"])
    data = p.read_bytes()
    assert hashlib.sha256(data).hexdigest() == \
        c["canonical_channel_payload_blob_hash"]
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT canonical_channel_payload_blob_hash FROM "
            "performance_candidates WHERE id = :i"),
            {"i": c["id"]})).fetchone()
    assert row[0] == c["canonical_channel_payload_blob_hash"]


@pytest.mark.asyncio
async def test_d10_physical_blob_corruption_rejects(client,
                                                      tmp_path):
    from tests.m17b_seed import (create_candidate, make_entity,
                                 make_project, stamp_alembic)
    from soloring.recovery.backup import backup
    pid = await make_project(client)
    eid = await make_entity(client, pid)
    c = await create_candidate(client, eid, candidate_body(
        [channel(SMILE, [kf(0, 1, 0)])]))
    settings = client._transport.app.state.settings
    p = (settings.blob_dir / "sha256" /
         c["canonical_channel_payload_blob_hash"][:2] /
         c["canonical_channel_payload_blob_hash"][2:4] /
         c["canonical_channel_payload_blob_hash"])
    p.write_bytes(b"corrupted-retained-payload")
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        await conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    await stamp_alembic(client)
    with pytest.raises(Exception) as exc_info:
        await backup(settings, tmp_path / "bk")
    assert "rehash" in str(exc_info.value) or "blob" in str(
        exc_info.value).lower()


def test_d11_unknown_or_missing_payload_channel_object_keys_reject():
    bad = channel(SMILE, [kf(0, 1, 0)])
    bad["extra"] = 1
    e = _err(candidate_body([bad]))
    assert "closed" in str(e)
    bad2 = {k: v for k, v in channel(SMILE, [kf(0, 1, 0)]).items()
            if k != "role"}
    e2 = _err(candidate_body([bad2]))
    assert "closed" in str(e2)
    payload = {"schema_version": 1,
               "performance_profile_id": "performance-profile/1",
               "channels": [channel(SMILE, [kf(0, 1, 0)])],
               "extra": True}
    try:
        build_canonical_payload(
            payload, performance_kind="FACIAL",
            performance_profile_id="performance-profile/1",
            start_num=0, start_den=1, end_num=4500, end_den=1)
        raise AssertionError("should reject")
    except Exception as exc:  # noqa: BLE001
        assert "closed" in str(exc)


def test_d12_unknown_or_missing_keyframe_rational_keyframe_provenance_object_keys_reject():
    k = kf(0, 1, 0)
    k["extra"] = 1
    e = _err(candidate_body([channel(SMILE, [k])]))
    assert "closed" in str(e)
    k2 = kf(0, 1, 0)
    k2["time_ms"] = {"num": 0, "den": 1, "x": 1}
    e2 = _err(candidate_body([channel(SMILE, [k2])]))
    assert "closed" in str(e2)
    k3 = kf(0, 1, 0)
    k3["provenance"] = {"kind": "AUTHORED",
                        "source_alignment_id": None, "z": 1}
    e3 = _err(candidate_body([channel(SMILE, [k3])]))
    assert "closed" in str(e3)


def test_d13_every_declared_channel_requires_at_least_one_keyframe():
    e = _err(candidate_body([channel(SMILE, [])]))
    assert "at least one keyframe" in str(e)


def test_d14_minimal_canonical_payload_golden_reproduces_pinned_bytes_and_sha256():
    b, _ = _build(candidate_body([channel(SMILE, [kf(0, 1, 0)])]))
    assert len(b) == 342
    assert hashlib.sha256(b).hexdigest() == (
        "9bb7db9d172462d351c519f34557b3951f6aaf85feb1334c33557b01"
        "b662fd26")
