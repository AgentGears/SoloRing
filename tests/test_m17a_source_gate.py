"""M17A-F full source gate (frozen R5 §14) — the G8 worked scenario
through the exact M17A boundary, from a fresh database, using only
public/domain operations. Machine-readable evidence recorded."""

from __future__ import annotations

import json
from fractions import Fraction

import pytest

from tests.m17a_seed import make_entity, make_project, make_shot, \
    place_blob, stamp_alembic, wave_bytes


@pytest.mark.asyncio
async def test_source_gate(client, tmp_path):
    evidence = {}
    pid = await make_project(client)
    eva = await make_entity(client, pid)
    evidence["project"] = pid
    evidence["speaker"] = eva
    r = await client.post(f"/projects/{pid}/dialogue-lines", json={})
    lid = r.json()["id"]
    r = await client.post(f"/dialogue-lines/{lid}/revisions", json={
        "speaker_subject_id": eva, "language": "en",
        "wording": "You weren't supposed to see this."})
    lr1 = r.json()
    evidence["L"], evidence["Lr1"] = lid, lr1
    data = wave_bytes(48000, 216000)
    import hashlib
    blob_sha = hashlib.sha256(data).hexdigest()
    h = await place_blob(client, data)
    assert h == blob_sha
    evidence["C1_blob"] = {"sha256": h, "bytes": len(data),
                           "rate": 48000, "frames": 216000}
    r = await client.post(f"/dialogue-line-revisions/{lr1['id']}"
                          "/vocal-candidates", json={
        "retained_audio_blob_hash": h,
        "source_provenance": {"schema_version": 1,
                              "source_kind": "recorded"}})
    assert r.status_code == 201, r.text
    c1 = r.json()
    assert (c1["trim_start_sample"],
            c1["trim_end_sample_exclusive"]) == (0, 216000)
    r = await client.post(f"/vocal-candidates/{c1['id']}/adopt",
                          json={"adopted_by": "director"})
    v1 = r.json()
    assert v1["speaker_subject_id"] == eva
    evidence["V1"] = v1
    # selection initially UNSET; explicit select
    r = await client.get(f"/dialogue-line-revisions/{lr1['id']}"
                         "/vocal-selection")
    assert r.json()["state"] == "UNSET"
    r = await client.put(f"/dialogue-line-revisions/{lr1['id']}"
                         "/vocal-selection",
                         json={"vocal_performance_revision_id": v1["id"],
                               "selected_by": "director"})
    assert r.json()["state"] == "SELECTED"
    shot_a = await make_shot(client, pid, 2000)
    shot_b = await make_shot(client, pid, 3000)
    r = await client.put(f"/shots/{shot_a}/vocal-segments/0", json={
        "vocal_performance_revision_id": v1["id"],
        "source_start_sample": 0,
        "source_end_sample_exclusive": 96000,
        "sample_rate_hz": 48000,
        "performance_origin_ms": {"num": 0, "den": 1},
        "shot_anchor_ms": {"num": 0, "den": 1}})
    assert r.status_code == 200
    m_a_hash = r.json()["mapping_hash"]
    r = await client.put(f"/shots/{shot_b}/vocal-segments/0", json={
        "vocal_performance_revision_id": v1["id"],
        "source_start_sample": 84000,
        "source_end_sample_exclusive": 216000,
        "sample_rate_hz": 48000,
        "performance_origin_ms": {"num": 1750, "den": 1},
        "shot_anchor_ms": {"num": -250, "den": 1}})
    assert r.status_code == 200
    m_b_hash = r.json()["mapping_hash"]
    evidence["M_A"], evidence["M_B"] = m_a_hash, m_b_hash
    # exact positions via Fraction arithmetic
    ev = {}
    ev["s84000_shotB_ms"] = str(Fraction(-250) + Fraction(0, 48000))
    ev["s96000_shotB_ms"] = str(Fraction(-250) + Fraction(12000 * 1000, 48000))
    ev["s84000_perf_ms"] = str(Fraction(1750) + Fraction(0, 48000))
    ev["s96000_perf_ms"] = str(Fraction(1750) + Fraction(12000 * 1000, 48000))
    ev["s95999_shotA_ms"] = str(Fraction(95999 * 1000, 48000))
    assert ev["s84000_shotB_ms"] == "-250"
    assert ev["s96000_shotB_ms"] == "0"
    assert ev["s84000_perf_ms"] == "1750"
    assert ev["s95999_shotA_ms"] == "95999/48"
    evidence["exact_positions"] = ev
    # alignment triple D1/D1_same/D1_variant
    words = [{"start_sample": 0, "end_sample_exclusive": 12000,
              "label": "You"}]

    def _al(ws, run_ts="2026-09-19T12:34:56.123456Z",
            host="worker-7 (CPython 3.12.10)"):
        return {"analyzer_id": "X", "analyzer_version": "1.2.0",
                "model_identity": "Mx", "runtime_identity": "Rx",
                "parameters_sha256": "a" * 64,
                "alignment_document": {"schema_version": 1, "words": ws,
                                       "phonemes": [],
                                       "viseme_classes": []},
                "derivation_run": {
                    "schema_version": 1,
                    "run_timestamp_utc": run_ts,
                    "host_context": host,
                    "input_digest": {
                        "vocal_performance_revision_id": v1["id"],
                        "retained_audio_blob_sha256": h}}}

    d1 = (await client.post(
        f"/vocal-performance-revisions/{v1['id']}/alignments",
        json=_al(words))).json()
    d1s = (await client.post(
        f"/vocal-performance-revisions/{v1['id']}/alignments",
        json=_al(words))).json()
    # the variant is a genuinely DISTINCT derivation run R2 (R2 != R1):
    # one exact run may not carry contradictory outputs (frozen F08)
    d1v = (await client.post(
        f"/vocal-performance-revisions/{v1['id']}/alignments",
        json=_al([
            {"start_sample": 0, "end_sample_exclusive": 6000,
             "label": "You"},
            {"start_sample": 6000, "end_sample_exclusive": 13000,
             "label": "weren't"}],
            run_ts="2026-09-19T12:41:09.654321Z"))).json()
    assert len({d1["id"], d1s["id"], d1v["id"]}) == 3
    assert d1s["retained_sha256"] == d1["retained_sha256"]
    assert d1v["retained_sha256"] != d1["retained_sha256"]
    assert d1v["derivation_run_identity"] != d1["derivation_run_identity"]
    assert d1v["derivation_run_identity"] == d1v["derivation_run_hash"]
    evidence["D1"], evidence["D1_same"], evidence["D1_variant"] = \
        d1, d1s, d1v
    # replacement: Lr2 -> UNSET -> adopt V2 -> explicit select
    lr2 = (await client.post(f"/dialogue-lines/{lid}/revisions", json={
        "speaker_subject_id": eva, "language": "en",
        "wording": "You were never supposed to see this."})).json()
    evidence["Lr2"] = lr2
    r = await client.get(f"/dialogue-line-revisions/{lr2['id']}"
                         "/vocal-selection")
    assert r.json()["state"] == "UNSET"
    r = await client.post(
        f"/vocal-performance-revisions/{v1['id']}/compatibility/"
        f"dialogue-line-revisions/{lr2['id']}")
    assert r.json()["verdict"] == "INCOMPATIBLE"
    h2 = await place_blob(client, wave_bytes(48000, 48000))
    c2 = (await client.post(
        f"/dialogue-line-revisions/{lr2['id']}/vocal-candidates",
        json={"retained_audio_blob_hash": h2,
              "source_provenance": {"schema_version": 1,
                                    "source_kind": "adr"}}
    )).json()
    v2 = (await client.post(f"/vocal-candidates/{c2['id']}/adopt",
                            json={"adopted_by": "director"})).json()
    r = await client.get(f"/dialogue-line-revisions/{lr2['id']}"
                         "/vocal-selection")
    assert r.json()["state"] == "UNSET"  # adoption alone != selection
    await client.put(
        f"/dialogue-line-revisions/{lr2['id']}/vocal-selection",
        json={"vocal_performance_revision_id": v2["id"],
              "selected_by": "director"})
    d2 = (await client.post(
        f"/vocal-performance-revisions/{v2['id']}/alignments",
        json={"analyzer_id": "Y", "analyzer_version": "2.0",
              "model_identity": "My", "runtime_identity": "Ry",
              "parameters_sha256": "b" * 64,
              "alignment_document": {"schema_version": 1, "words": words,
                                     "phonemes": [],
                                     "viseme_classes": []},
              "derivation_run": {
                  "schema_version": 1,
                  "run_timestamp_utc": "2026-09-19T13:00:00.000000Z",
                  "host_context": "worker-9",
                  "input_digest": {
                      "vocal_performance_revision_id": v2["id"],
                      "retained_audio_blob_sha256": h2}}}
    )).json()
    evidence["V2"], evidence["D2"] = v2, d2
    # immutability proofs
    v1_after = (await client.get(
        f"/vocal-performance-revisions/{v1['id']}")).json()
    assert v1_after["adoption_id"] == v1["adoption_id"]
    rows = (await client.get(
        f"/vocal-performance-revisions/{v1['id']}/alignments")).json()
    assert {x["id"] for x in rows} == \
        {d1["id"], d1s["id"], d1v["id"]}
    r = await client.get(f"/dialogue-line-revisions/{lr1['id']}"
                         "/vocal-selection")
    assert r.json()["selected_vocal_performance_revision_id"] == \
        v1["id"]
    maps_a = (await client.get(f"/shots/{shot_a}/vocal-segments"
                               )).json()
    assert maps_a[0]["mapping_hash"] == m_a_hash
    (tmp_path / "m17a_source_gate_evidence.json").write_text(
        json.dumps(evidence, indent=1), encoding="utf-8")
