"""M17C-C §1.7 regressions: backup/restore + downgrade closure (frozen
R4 §10.7; scope R0 1.7).

The frozen rule: **valid M17C-C historical closure survives
backup/restore exactly; invalid downgrade cannot erase it.**

Laws proven:

- a REAL populated 0021 database upgrades to 0022 with every M17C-A/B
  predecessor surface byte-identical (row-content fingerprints over
  the authority/working tables + the blob set + the table inventory)
  and the three new tables existing EMPTY; recovery at 0022 stays
  green;
- a clean schema-8 capture round-trips: ShotRevision bytes/hash,
  companion parent, children (count/order/bytes/hashes/projection),
  immutable PR/VP/binding closure, retained payload Blob closure —
  identical before and after restore, with the §12 historical
  response IDENTICAL through the actual public reader on the
  restored tree and the full recovery verifier green;
- the MILESTONE EXIT CRITERION composite: 8-over-7 capture → mutate
  every forbidden current surface → historical read A → backup →
  restore fresh → recovery verifier green → historical read B →
  A == B exactly;
- fixture-valid generation_performance_inputs rows survive a REAL
  backup/restore (liveness walks the 14th Blob-FK path) with exact
  identities, bytes, tiebacks, and translation identity — durability
  without any M17C-D writer semantics;
- the Blob-FK inventory restores at exactly 14 paths at 0022 and
  exactly 13 on a 0021-retargeted restore;
- populated downgrade refuses at each of the three fences naming the
  blocking table (the segment fence proven with an isolated child),
  and the refusal is NON-DESTRUCTIVE: the head stays 0022, the rows
  survive byte-for-byte, no table is partially dropped, and recovery
  stays green on the still-valid state;
- the empty downgrade produces a database the predecessor head
  ACCEPTS (verifier green at 0021);
- backup/restore table inclusion is explicit, not incidental: the
  restored file's FK metadata yields the exact head-specific Blob-FK
  inventory, and the restore-time liveness enumeration certifies the
  14-path policy mechanically.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from tests.m17cc_capture_helper import capture as _capture
from tests.test_m17cc_persist import _lawful
from tests.test_m17c_shot_mapping import _bound_world, _seg_body

_HEAD = "0022_m17c_schema8_capture"
_HEAD_0021 = "0021_m17c_shot_performance_mappings"
_PARENTS = "shot_revision_performance_specs"
_CHILDREN = "shot_revision_performance_segments"
_GPI = "generation_performance_inputs"
_TRANSLATION_ID = "soloring-executor-translation-facial-liveportrait/1"

# the M17C-A/B predecessor surfaces the 0021→0022 upgrade must carry
# across byte-identically (row-content fingerprints)
_PREDECESSOR_TABLES = (
    ("performance_candidates", "id"),
    ("performance_revisions", "id"),
    ("vocal_candidates", "id"),
    ("vocal_performance_revisions", "id"),
    ("vocal_performance_selections", "dialogue_line_revision_id"),
    ("dialogue_alignments", "id"),
    ("performance_candidate_vocal_bindings",
     "performance_candidate_id"),
    ("performance_revision_vocal_bindings",
     "performance_revision_id"),
    ("performance_candidate_sync_classifications",
     "performance_candidate_id"),
    ("performance_revision_sync_classifications",
     "performance_revision_id"),
    ("shot_vocal_segment_mappings", "shot_id, position"),
    ("shot_performance_segment_mappings", "shot_id, position"),
    ("blobs", "hash"),
)


def _con(db):
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    return c


def _sql(db, stmt, params=()):
    con = _con(db)
    try:
        con.execute(stmt, params)
        con.commit()
    finally:
        con.close()


def _rows(db, table, order):
    con = _con(db)
    try:
        return [dict(r) for r in con.execute(
            f"SELECT * FROM {table} ORDER BY {order}")]
    finally:
        con.close()


def _fingerprint(tables, db) -> dict:
    """Row-content fingerprints: canonical JSON of every row of every
    predecessor surface, plus the table inventory."""
    out = {}
    for table, order in tables:
        out[table] = _rows(db, table, order)
    con = _con(db)
    try:
        # the three M17C-C tables legitimately APPEAR (empty) after
        # the upgrade — excluded so the fingerprint pins the
        # predecessor inventory
        out["__tables__"] = sorted(
            r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")
            if r[0] not in (_PARENTS, _CHILDREN, _GPI))
    finally:
        con.close()
    return out


def _verify(db, blobs, head=_HEAD):
    from soloring.recovery.m17c_verifier import verify_m17c_binding_state
    verify_m17c_binding_state(db, blobs, head=head)


async def _backup(client, tmp_path, tag):
    from tests.test_m17c_sr26_regressions import _backup_m17c
    return await _backup_m17c(client, tmp_path, f"m17cc-17-{tag}")


async def _restored_client(dest: Path):
    """The ACTUAL public reader over a restored tree: a second app
    bound to the restored database (no create_all — the restored file
    IS the schema), so history B provably reads the restored closure
    and nothing else."""
    import httpx
    from soloring.api.main import create_app
    from soloring.db.engine import create_session_factory, \
        create_soloring_engine
    from soloring.settings import Settings

    settings = Settings(
        data_dir=dest,
        database_url=f"sqlite+aiosqlite:///{(dest / 'soloring.db').as_posix()}")  # noqa: E501
    engine = create_soloring_engine(settings)
    app = create_app(settings)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport,
                             base_url="http://restored"), engine


async def _history_at(client, revision_id):
    r = await client.get(f"/shot-revisions/{revision_id}/continuity")
    assert r.status_code == 200, r.text
    return r.json()


async def _mutate_forbidden_surfaces(client, world):
    """The §12 forbidden current surfaces all move: a newer valid VP
    re-selected, a newer valid performance mapping added, then every
    current vocal/performance mapping deleted, the dependency
    selection cleared, and the Shot duration changed."""
    from tests.m17a_seed import place_blob, wave_bytes
    from tests.m17b_seed import (
        HEAD_YAW, candidate_body, channel as m17b_channel,
        kf as m17b_kf,
    )

    new_blob = await place_blob(client, wave_bytes(48000, 72000))
    new_vc = (await client.post(
        f"/dialogue-line-revisions/"
        f"{world['dialogue_line_revision_id']}/vocal-candidates",
        json={
            "retained_audio_blob_hash": new_blob,
            "source_provenance": {
                "schema_version": 1, "source_kind": "recorded"},
        })).json()
    new_vp = (await client.post(
        f"/vocal-candidates/{new_vc['id']}/adopt",
        json={"adopted_by": "director"})).json()
    r = await client.put(
        f"/dialogue-line-revisions/"
        f"{world['dialogue_line_revision_id']}/vocal-selection",
        json={"vocal_performance_revision_id": new_vp["id"],
              "selected_by": "d"})
    assert r.status_code == 200, r.text

    newer = (await client.post(
        f"/creative-entities/{world['subject_id']}/"
        "performance-candidates",
        json=candidate_body(
            [m17b_channel(HEAD_YAW, [m17b_kf(0, 2, 0)])]),
    )).json()
    newer_pr = (await client.post(
        f"/performance-candidates/{newer['id']}/adopt",
        json={"adopted_by": "s17"})).json()
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/9",
        json=_seg_body(newer_pr["id"], 1500, 2000, 0))
    assert r.status_code == 200, r.text

    engine = client._transport.app.state.engine
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.execute(text(
            "DELETE FROM shot_vocal_segment_mappings WHERE shot_id = :s"),
            {"s": world["shot"]})
        await conn.execute(text(
            "DELETE FROM shot_performance_segment_mappings "
            "WHERE shot_id = :s"), {"s": world["shot"]})
        await conn.execute(text(
            "UPDATE shots SET duration_ms = 7777 WHERE id = :s"),
            {"s": world["shot"]})
    r = await client.put(
        f"/shots/{world['shot']}/semantic-dependencies",
        json={"dependencies": []})
    assert r.status_code == 200, r.text
    return new_vp, newer_pr


@pytest.mark.asyncio
async def test_real_0021_upgrade_retains_predecessor_verbatim(
        client, tmp_path):
    """§1.7 gate 1: a GENUINE populated 0021 database upgrades to 0022
    with every M17C-A/B predecessor surface byte-identical and the
    three new tables EMPTY; recovery at 0022 stays green."""
    from soloring.domain.canonical import canonical_json_bytes
    import hashlib

    from tests.test_m17cc_migration import _run

    world = await _bound_world(client)
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 1000, 0, vp=0))
    assert r.status_code == 200, r.text

    root = await _backup(client, tmp_path, "up21")

    # reshape into a GENUINE 0021 database (the established pattern:
    # drop the three create_all-staged successor tables, stamp 0021,
    # rewrite the manifest canonically with the recomputed db hash)
    con = sqlite3.connect(root / "soloring.db")
    for t in (_PARENTS, _CHILDREN, _GPI):
        con.execute(f"DROP TABLE {t}")
    con.execute("UPDATE alembic_version SET version_num = ?",
                (_HEAD_0021,))
    con.commit()
    con.close()
    manifest_path = root / "backup-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["alembic_version"] = _HEAD_0021
    manifest["database_sha256"] = hashlib.sha256(
        (root / "soloring.db").read_bytes()).hexdigest()
    manifest_path.write_bytes(canonical_json_bytes(manifest))

    before = _fingerprint(_PREDECESSOR_TABLES, root / "soloring.db")

    up = _run(root / "soloring.db", "upgrade", "head")
    assert up.returncode == 0, (up.stderr or "")[-800:]

    con = _con(root / "soloring.db")
    try:
        assert con.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0] == _HEAD
        for t in (_PARENTS, _CHILDREN, _GPI):
            assert con.execute(
                f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0, t
    finally:
        con.close()

    after = _fingerprint(_PREDECESSOR_TABLES, root / "soloring.db")
    assert after == before
    _verify(root / "soloring.db", root / "blobs")


@pytest.mark.asyncio
async def test_schema8_roundtrip_preserves_complete_closure(
        client, tmp_path):
    """§1.7 gate 2: a schema-8 capture (dialogue + generic) round-trips
    with the complete closure byte-identical — snapshot bytes/hash,
    parent, children, immutable PR/VP/binding rows, retained payload
    Blob bytes — the §12 historical response IDENTICAL through the
    public reader on the restored tree, and the full recovery
    verifier green. The BEFORE fingerprints read the live DB FILE
    AFTER the backup (the backup checkpoints WAL, so the file is the
    exact state that was staged)."""
    from soloring.recovery.backup import restore as rb_restore

    world = await _bound_world(client)
    await _lawful(client, world, extra=True)
    revision, _visual = await _capture(client, world["shot"])

    root = await _backup(client, tmp_path, "rt")
    live = client_db_path(client)

    tables = [
        ("shot_revisions", "id"),
        (_PARENTS, "shot_revision_id"),
        (_CHILDREN, "shot_revision_id, position"),
        ("performance_revisions", "id"),
        ("vocal_performance_revisions", "id"),
        ("performance_revision_vocal_bindings",
         "performance_revision_id"),
        ("performance_revision_sync_classifications",
         "performance_revision_id"),
        ("blobs", "hash"),
    ]
    before = {t: _rows(live, t, o) for t, o in tables}

    history_a = await _history_at(client, revision.id)

    dest = tmp_path / "m17cc-17-rt-restored"
    await rb_restore(root, dest)
    after = {t: _rows(dest / "soloring.db", t, o) for t, o in tables}
    assert after == before

    # the §12 historical response through the ACTUAL public reader on
    # the restored tree is identical
    rclient, rengine = await _restored_client(dest)
    try:
        history_b = await _history_at(rclient, revision.id)
    finally:
        await rclient.aclose()
        await rengine.dispose()
    assert history_b == history_a

    _verify(dest / "soloring.db", dest / "blobs")


@pytest.mark.asyncio
async def test_exit_criterion_mutate_backup_restore_equality(
        client, tmp_path):
    """The FINAL M17C-C product proof (§1.7 gate 3 + gate 4): an
    8-over-7 capture, every forbidden current surface mutated,
    historical read A, backup, restore into a FRESH tree (the original
    never consulted again), the recovery verifier green, historical
    read B — A == B exactly, both planes intact."""
    from soloring.recovery.backup import restore as rb_restore
    from tests.m16_seed_b import (
        event, post_event, seed_feature_world, state,
    )
    from tests.m17c_seed import ARTICULATION, dialogue_bound_body, make_vp
    from tests.m17cc_capture_helper import _factory
    from tests.test_m17c_shot_mapping import _add_dependency

    base = await seed_feature_world(client, _factory(client))
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(client, sid, event(fid, 1000, state(),
                                        state("fresh")))
    vp_world = await make_vp(client, pid=base["project_id"],
                             eid=base["entity_id"])
    r = await client.put(
        f"/dialogue-line-revisions/"
        f"{vp_world['dialogue_line_revision_id']}/vocal-selection",
        json={"vocal_performance_revision_id": vp_world["vp"]["id"],
              "selected_by": "d"})
    assert r.status_code == 200, r.text
    r = await client.put(
        f"/shots/{sid}/vocal-segments/0",
        json={
            "vocal_performance_revision_id": vp_world["vp"]["id"],
            "source_start_sample": 48000,
            "source_end_sample_exclusive": 96000,
            "sample_rate_hz": 48000,
            "performance_origin_ms": {"num": 0, "den": 1},
            "shot_anchor_ms": {"num": 0, "den": 1},
        })
    assert r.status_code == 200, r.text
    candidate = (await client.post(
        f"/creative-entities/{base['entity_id']}/"
        "dialogue-bound-performance-candidates",
        json=dialogue_bound_body(
            vp_world["vp"]["id"],
            articulation_time={key: (600, 1) for key in ARTICULATION}),
    )).json()
    pr = (await client.post(
        f"/performance-candidates/{candidate['id']}/adopt",
        json={"adopted_by": "d"})).json()
    r = await client.put(
        f"/shots/{sid}/performance-segments/0",
        json=_seg_body(pr["id"], 0, 1000, 0, vp=0))
    assert r.status_code == 200, r.text

    revision, _visual = await _capture(client, sid)
    world = {"shot": sid, "subject_id": base["entity_id"],
             "dialogue_line_revision_id":
                 vp_world["dialogue_line_revision_id"],
             "project_id": base["project_id"]}

    await _mutate_forbidden_surfaces(client, world)
    history_a = await _history_at(client, revision.id)
    assert history_a["snapshot_schema_version"] == 8
    assert history_a["intra_shot"] is not None
    assert history_a["performance"] is not None

    root = await _backup(client, tmp_path, "exit")
    dest = tmp_path / "m17cc-17-exit-restored"
    await rb_restore(root, dest)
    _verify(dest / "soloring.db", dest / "blobs")

    rclient, rengine = await _restored_client(dest)
    try:
        history_b = await _history_at(rclient, revision.id)
    finally:
        await rclient.aclose()
        await rengine.dispose()
    assert history_b == history_a
    assert history_b["intra_shot"] is not None
    assert history_b["performance"]["segments"][0][
        "performance_revision_id"] == pr["id"]


@pytest.mark.asyncio
async def test_gpi_rows_survive_real_backup_restore(
        client, tmp_path):
    """§1.7 gate 5: fixture-valid derived-input rows inserted into the
    LIVE database (with real placed Blob bytes, so the 14-path
    liveness walk finds them) survive a REAL backup/restore with
    exact identities, bytes, tiebacks, and translation identity; the
    §13.6 recovery laws validate them on the restored tree. No
    production writer is introduced."""
    from sqlalchemy import text
    from soloring.recovery.backup import restore as rb_restore
    from tests.m17a_seed import place_blob

    world = await _bound_world(client)
    await _lawful(client, world, extra=True)
    revision, _visual = await _capture(client, world["shot"])
    engine = client._transport.app.state.engine

    blob = await place_blob(client, b"m17cc-17-derived-bytes")
    template_hash, manifest_hash = _write_generation_artifacts(client)
    gen_id = await _insert_live_generation(
        engine, world["shot"], revision.id, template_hash,
        manifest_hash)
    rows = await _live_gpi_rows(client, revision.id, gen_id, blob)
    async with engine.begin() as conn:
        for params in rows:
            await conn.execute(text(
                "INSERT INTO generation_performance_inputs ("
                "generation_id, input_key, position, artifact_role, "
                "shot_revision_segment_position, "
                "performance_revision_id, vocal_performance_revision_id,"
                " blob_hash, binding_hash, segment_hash, "
                "translation_identity, derived_input_hash, created_at) "
                "VALUES (:g, :k, :p, :r, :sp, :pr, :v, :b, :bh, :sh, "
                ":t, :d, :c)"), params)

    before_gpi = _rows(client_db_path(client), _GPI,
                       "generation_id, input_key, position")
    before_gen = _rows(client_db_path(client), "generations", "id")
    src_blob = blob_file(client._transport.app.state.settings.data_dir, blob)

    root = await _backup(client, tmp_path, "gpi")
    dest = tmp_path / "m17cc-17-gpi-restored"
    await rb_restore(root, dest)

    assert _rows(dest / "soloring.db", _GPI,
                 "generation_id, input_key, position") == before_gpi
    assert _rows(dest / "soloring.db", "generations",
                 "id") == before_gen
    assert (blob_file(dest, blob).read_bytes()
            == src_blob.read_bytes())
    _verify(dest / "soloring.db", dest / "blobs")


async def _insert_live_generation(engine, shot_id, revision_id,
                                  template_hash, manifest_hash):
    from soloring.domain.canonical import (
        canonical_hash as _ch, canonical_json_str as _cj,
    )
    from soloring.domain.ids import new_uuid
    from sqlalchemy import text

    gen_id = new_uuid()
    # schema-1 WorkflowSpec: no frozen artifact dependencies beyond
    # the manifest/template pair; the translation identity rides as a
    # materialized field (fixture construction)
    spec = {"schema_version": 1, "inputs": {},
            "performance_translation": _TRANSLATION_ID}
    now = "2026-09-30T00:00:00.000Z"
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO generations (id, shot_id, shot_revision_id, "
            "generation_number, status, operation, executor, "
            "workflow_id, workflow_version, workflow_template_hash, "
            "manifest_hash, compiled_prompt, prompt_compiler_version, "
            "parameters_json, workflow_spec_json, workflow_spec_hash, "
            "created_at, updated_at, queued_at, "
            "executor_submission_state) VALUES "
            "(:g, :s, :r, 1, 'queued', 'generate', 'fake', 'w', 1, "
            ":wth, :mh, 'p', '1', '{}', :wsj, :wsh, :c, :c, :c, "
            "'not_started')"),
            {"g": gen_id, "s": shot_id, "r": revision_id,
             "wth": template_hash, "mh": manifest_hash,
             "wsj": _cj(spec), "wsh": _ch(spec), "c": now})
    return gen_id


def _write_generation_artifacts(client):
    """The two content-addressed workflow-artifact files liveness
    requires for any generation row: write fixture bytes at the
    canonical hash-sharded paths and return their REAL hashes."""
    import hashlib

    artifacts = (client._transport.app.state.settings.data_dir
                 / "workflow-artifacts")

    def _p(kind: str, content: bytes) -> str:
        h = hashlib.sha256(content).hexdigest()
        p = artifacts / kind / "sha256" / h[:2] / h[2:4] / f"{h}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        return h

    template_hash = _p("templates", b"m17cc-17-fixture-template")
    manifest_hash = _p(
        "manifests", b'{"fixture": "m17cc-17-generation"}')
    return template_hash, manifest_hash


async def _live_gpi_rows(client, revision_id, gen_id, blob):
    """Two fixture siblings over the two captured segments, built from
    the real captured children (controls + vocal_audio)."""
    from sqlalchemy import text

    engine = client._transport.app.state.engine
    out = []
    async with engine.connect() as conn:
        children = (await conn.execute(text(
            f"SELECT position, performance_revision_id, "
            f"vocal_performance_revision_id, vocal_binding_hash, "
            f"segment_hash FROM {_CHILDREN} WHERE shot_revision_id = :r"
            " ORDER BY position"), {"r": revision_id})).mappings().all()
        gen_created = (await conn.execute(text(
            "SELECT created_at FROM generations WHERE id = :g"),
            {"g": gen_id})).scalar_one()
    for child in children:
        role = "performance.controls"
        key = f"performance:{child['position']}"
        if child["vocal_performance_revision_id"] is not None:
            role = "performance.vocal_audio"
            key += ":vocal"
        out.append({
            "g": gen_id, "k": key, "p": 0, "r": role,
            "sp": child["position"],
            "pr": child["performance_revision_id"],
            "v": child["vocal_performance_revision_id"],
            "b": blob, "bh": child["vocal_binding_hash"],
            "sh": child["segment_hash"],
            "t": _TRANSLATION_ID, "d": "9" * 64,
            "c": gen_created,
        })
    return out


def client_db_path(client):
    settings = client._transport.app.state.settings
    return settings.data_dir / "soloring.db"


def blob_file(root, blob_hash):
    return root / "blobs" / "sha256" / blob_hash[:2] / \
        blob_hash[2:4] / blob_hash


@pytest.mark.asyncio
async def test_blob_fk_inventory_restoration(client, tmp_path):
    """§1.7 gates 6+10: the restored 0022 database's FK metadata
    yields EXACTLY the 14-path head policy (generation_performance_
    inputs.blob_hash the sole M17C-C addition), and a 0021-retargeted
    restore keeps the predecessor 13-path policy with the verifier
    green — the table/inventory inclusion is certified mechanically
    by the restore-time liveness enumeration, not by file-copy luck."""
    import hashlib

    from soloring.domain.canonical import canonical_json_bytes
    from soloring.recovery.backup import (
        M17B_BLOB_FK_COLUMNS, _blob_fk_inventory,
        _blob_fk_policy_for_head, restore as rb_restore,
    )

    world = await _bound_world(client)
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 1000, 0, vp=0))
    assert r.status_code == 200, r.text
    root = await _backup(client, tmp_path, "inv")

    dest = tmp_path / "m17cc-17-inv-restored"
    await rb_restore(root, dest)
    con = _con(dest / "soloring.db")
    try:
        restored = _blob_fk_inventory(con)
    finally:
        con.close()
    policy_0022 = _blob_fk_policy_for_head(_HEAD)
    assert restored == set(policy_0022)
    assert ("generation_performance_inputs", "blob_hash") in restored
    assert len(restored) == 14
    assert ("generation_performance_inputs", "blob_hash") \
        not in set(M17B_BLOB_FK_COLUMNS)
    assert len(set(M17B_BLOB_FK_COLUMNS)) == 13

    # predecessor retarget: a genuine 0021 reshape restores at 13
    # paths with the verifier green
    con = sqlite3.connect(root / "soloring.db")
    for t in (_PARENTS, _CHILDREN, _GPI):
        con.execute(f"DROP TABLE {t}")
    con.execute("UPDATE alembic_version SET version_num = ?",
                (_HEAD_0021,))
    con.commit()
    con.close()
    manifest_path = root / "backup-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["alembic_version"] = _HEAD_0021
    manifest["database_sha256"] = hashlib.sha256(
        (root / "soloring.db").read_bytes()).hexdigest()
    manifest_path.write_bytes(canonical_json_bytes(manifest))

    dest21 = tmp_path / "m17cc-17-inv21-restored"
    await rb_restore(root, dest21)
    con = _con(dest21 / "soloring.db")
    try:
        assert _blob_fk_inventory(con) == set(M17B_BLOB_FK_COLUMNS)
    finally:
        con.close()
    _verify(dest21 / "soloring.db", dest21 / "blobs", head=_HEAD_0021)


@pytest.mark.asyncio
async def test_populated_downgrade_refusal_is_non_destructive(
        client, tmp_path):
    """§1.7 gate 9: on a VALID schema-8 staged state the 0022→0021
    downgrade refuses at the specs fence naming the table, the head
    stays 0022, every M17C-C row survives byte-for-byte, no table is
    partially dropped, and recovery stays green — the fence fires
    before any destructive DDL. (The three per-table fence-NAMING
    tests with isolated rows live in test_m17cc_migration.)"""
    from tests.test_m17cc_migration import _run

    world = await _bound_world(client)
    await _lawful(client, world, extra=True)
    revision, _visual = await _capture(client, world["shot"])
    root = await _backup(client, tmp_path, "dd")

    before_parent = _rows(root / "soloring.db", _PARENTS,
                          "shot_revision_id")
    before_children = _rows(root / "soloring.db", _CHILDREN,
                            "shot_revision_id, position")

    result = _run(root / "soloring.db", "downgrade", _HEAD_0021,
                  expect=1)
    combined = result.stdout + result.stderr
    assert "0022 downgrade refused" in combined
    assert _PARENTS in combined

    con = _con(root / "soloring.db")
    try:
        assert con.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0] == _HEAD
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()
    for t in (_PARENTS, _CHILDREN, _GPI):
        assert t in tables, t
    assert _rows(root / "soloring.db", _PARENTS,
                 "shot_revision_id") == before_parent
    assert _rows(root / "soloring.db", _CHILDREN,
                 "shot_revision_id, position") == before_children
    _verify(root / "soloring.db", root / "blobs")


def test_empty_downgrade_yields_predecessor_accepted(tmp_path):
    """§1.7 gate 8: with all three M17C-C tables empty the downgrade
    drops cleanly and the resulting database is ACCEPTED by the
    predecessor head (verifier green at 0021)."""
    from tests.test_m17cc_migration import _run

    db = tmp_path / "m17cc-17-empty.db"
    _run(db, "upgrade", "head")
    _run(db, "downgrade", _HEAD_0021)

    con = sqlite3.connect(db)
    try:
        assert con.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0] == _HEAD_0021
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()
    assert not ({_PARENTS, _CHILDREN, _GPI} & tables)
    _verify(db, tmp_path / "empty-blobs", head=_HEAD_0021)
