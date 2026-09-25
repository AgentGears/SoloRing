"""M17C PF-03 test fixtures built only from published M17A/M17B APIs."""

from __future__ import annotations

from soloring.performance.profile import CHANNELS
from tests.m17a_seed import place_blob, wave_bytes
from tests.m17b_seed import make_entity, make_project

ARTICULATION = (
    "profile-1/face.articulation.jaw_open",
    "profile-1/face.articulation.lip_round",
    "profile-1/face.articulation.lip_press",
    "profile-1/face.articulation.mouth_width",
)
SMILE = "profile-1/face.expression.smile"
HEAD_YAW = "profile-1/body.pose.head_yaw_udeg"


def kf(num: int, den: int, value: int, *, kind: str = "AUTHORED",
       alignment: str | None = None) -> dict:
    return {
        "time_ms": {"num": num, "den": den},
        "value": value,
        "provenance": {
            "kind": kind,
            "source_alignment_id": alignment,
        },
    }


def channel(key: str, keyframes: list[dict]) -> dict:
    domain, role, semantic, grammar, _lo, _hi = CHANNELS[key]
    return {
        "channel_key": key,
        "domain": domain,
        "role": role,
        "semantic_key": semantic,
        "value_grammar": grammar,
        "keyframes": keyframes,
    }


def dialogue_bound_body(
    vp_id: str,
    *,
    kind: str = "FACIAL",
    start: tuple[int, int] = (-250, 1),
    end: tuple[int, int] = (1500, 1),
    source_start: int = 48000,
    source_end: int = 96000,
    rate: int = 48000,
    origin: tuple[int, int] = (0, 1),
    omit: str | None = None,
    articulation_time: dict[str, tuple[int, int]] | None = None,
    alignment_by_channel: dict[str, str] | None = None,
    pre_post_expression: bool = False,
) -> dict:
    articulation_time = articulation_time or {}
    alignment_by_channel = alignment_by_channel or {}
    channels = []
    for key in ARTICULATION:
        if key == omit:
            continue
        t = articulation_time.get(key, (0, 1))
        aid = alignment_by_channel.get(key)
        channels.append(channel(
            key,
            [kf(t[0], t[1], 250000,
                kind="DERIVED" if aid else "AUTHORED",
                alignment=aid)],
        ))
    if pre_post_expression:
        channels.append(channel(SMILE, [
            kf(-250, 1, 100000),
            kf(1200, 1, 500000),
        ]))
    if kind == "BODY_FACIAL":
        channels.append(channel(HEAD_YAW, [kf(0, 1, 0)]))
    return {
        "performance_kind": kind,
        "performance_profile_id": "performance-profile/1",
        "temporal_domain": {
            "start": {"num": start[0], "den": start[1]},
            "end": {"num": end[0], "den": end[1]},
        },
        "channels": channels,
        "source_provenance": {
            "schema_version": 1,
            "source_kind": "authored",
            "producer_id": "m17c-test",
            "producer_version": "1",
            "source_identity": None,
            "parameters_sha256": None,
        },
        "vocal_binding": {
            "vocal_performance_revision_id": vp_id,
            "source_start_sample": source_start,
            "source_end_sample_exclusive": source_end,
            "sample_rate_hz": rate,
            "performance_origin_ms": {"num": origin[0], "den": origin[1]},
        },
    }


async def make_vp(
    client,
    *,
    pid: str | None = None,
    eid: str | None = None,
    tag: bytes = b"m17c-vp",
    frames: int = 144000,
) -> dict:
    if pid is None:
        pid = await make_project(client, name=f"M17C {tag!r}")
    if eid is None:
        eid = await make_entity(client, pid)
    line = (await client.post(
        f"/projects/{pid}/dialogue-lines", json={})).json()
    dlr = (await client.post(
        f"/dialogue-lines/{line['id']}/revisions",
        json={
            "speaker_subject_id": eid,
            "language": "en",
            "wording": "M17C exact timing fixture.",
        },
    )).json()
    # The deterministic WAVE shape is sufficient; tag only makes fixture
    # callers semantically distinct, not byte-distinct. A different frame count
    # may be supplied when distinct retained audio bytes are required.
    audio = wave_bytes(48000, frames)
    blob_hash = await place_blob(client, audio)
    vc = (await client.post(
        f"/dialogue-line-revisions/{dlr['id']}/vocal-candidates",
        json={
            "retained_audio_blob_hash": blob_hash,
            "source_provenance": {
                "schema_version": 1,
                "source_kind": "recorded",
            },
        },
    )).json()
    vp = (await client.post(
        f"/vocal-candidates/{vc['id']}/adopt",
        json={"adopted_by": "director"},
    )).json()
    return {
        "project_id": pid,
        "subject_id": eid,
        "line_id": line["id"],
        "dialogue_line_revision_id": dlr["id"],
        "vocal_candidate_id": vc["id"],
        "vp": vp,
        "blob_hash": blob_hash,
    }


async def make_alignment(client, vp_id: str, blob_hash: str, *,
                         suffix: str = "a") -> dict:
    response = await client.post(
        f"/vocal-performance-revisions/{vp_id}/alignments",
        json={
            "analyzer_id": "m17c-test-aligner",
            "analyzer_version": "1",
            "model_identity": f"model-{suffix}",
            "runtime_identity": "runtime-1",
            "parameters_sha256": "a" * 64,
            "alignment_document": {
                "schema_version": 1,
                "words": [{
                    "start_sample": 48000,
                    "end_sample_exclusive": 60000,
                    "label": "M17C",
                }],
                "phonemes": [],
                "viseme_classes": [],
            },
            "derivation_run": {
                "schema_version": 1,
                "run_timestamp_utc": "2026-09-25T12:00:00.000000Z",
                "host_context": "m17c-test",
                "input_digest": {
                    "vocal_performance_revision_id": vp_id,
                    "retained_audio_blob_sha256": blob_hash,
                },
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()
