from __future__ import annotations

import sqlite3

import pytest

from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.production_world.resolver import production_world_hash
from soloring.recovery.backup import (
    RecoveryCorruption,
    _sqlite_readonly_uri,
    _verify_m13_selection_and_history,
)


def test_sqlite_readonly_uri_escapes_reserved_path_characters(tmp_path):
    root = tmp_path / "data#%20 space"
    root.mkdir()
    db_path = root / "soloring.db"
    con = sqlite3.connect(str(db_path))
    try:
        con.execute("CREATE TABLE marker (value TEXT NOT NULL)")
        con.execute("INSERT INTO marker (value) VALUES ('ok')")
        con.commit()
    finally:
        con.close()

    uri = _sqlite_readonly_uri(db_path)
    assert "%23" in uri
    assert "%2520" in uri
    assert "%20" in uri

    con = sqlite3.connect(uri, uri=True)
    try:
        assert con.execute("SELECT value FROM marker").fetchone()[0] == "ok"
        with pytest.raises(sqlite3.OperationalError):
            con.execute("CREATE TABLE forbidden (id INTEGER)")
    finally:
        con.close()


def _captured_history_db() -> tuple[sqlite3.Connection, dict]:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(
        """
        CREATE TABLE shot_production_world_selections (
            shot_id TEXT NOT NULL,
            binding_id TEXT NOT NULL
        );
        CREATE TABLE shot_revisions (
            id TEXT PRIMARY KEY,
            snapshot_json TEXT NOT NULL,
            snapshot_hash TEXT NOT NULL
        );
        CREATE TABLE shot_revision_production_worlds (
            shot_revision_id TEXT PRIMARY KEY,
            production_world_hash TEXT NOT NULL,
            binding_id TEXT NOT NULL,
            binding_hash TEXT NOT NULL,
            composition_revision_id TEXT NOT NULL,
            composition_revision_hash TEXT NOT NULL,
            spatial_world_revision_id TEXT NOT NULL,
            spatial_world_revision_hash TEXT NOT NULL
        );
        CREATE TABLE shot_revision_production_instance_feature_states (
            shot_revision_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            occurrence_id TEXT NOT NULL,
            feature_id TEXT NOT NULL,
            value_json TEXT NOT NULL,
            value_hash TEXT NOT NULL
        );
        CREATE TABLE shot_revision_production_instance_spatial_states (
            shot_revision_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            composition_id TEXT NOT NULL,
            occurrence_id TEXT NOT NULL,
            production_instance_track_id TEXT NOT NULL,
            requirement TEXT NOT NULL,
            x_mm INTEGER NOT NULL,
            y_mm INTEGER NOT NULL,
            z_mm INTEGER NOT NULL,
            yaw_udeg INTEGER NOT NULL,
            pitch_udeg INTEGER NOT NULL,
            roll_udeg INTEGER NOT NULL,
            source_transition_id TEXT NOT NULL,
            source_anchor_type TEXT NOT NULL,
            source_anchor_id TEXT NOT NULL,
            source_boundary TEXT NOT NULL
        );
        """
    )
    pack = {
        "schema_version": 1,
        "binding": {
            "binding_id": "binding-1",
            "binding_hash": "b" * 64,
            "value": {
                "schema_version": 1,
                "composition_revision": {
                    "revision_id": "composition-revision-1",
                    "snapshot_hash": "c" * 64,
                },
                "spatial_world_revision": {
                    "revision_id": "world-revision-1",
                    "snapshot_hash": "d" * 64,
                },
                "subjects": [],
                "entries": [],
            },
        },
        "instance_feature_states": [],
        "instance_spatial_states": [
            {
                "composition_id": "composition-1",
                "occurrence_id": "occurrence-1",
                "production_instance_track_id": "track-1",
                "requirement": "required",
                "transform": {
                    "translation_mm": [101, 202, 303],
                    "rotation_udeg": [404, 505, 606],
                },
                "source_transition": {
                    "transition_id": "transition-1",
                    "anchor_type": "shot",
                    "anchor_id": "anchor-1",
                    "boundary": "start",
                },
            }
        ],
    }
    snapshot = {"schema_version": 6, "production_world": pack}
    snapshot_json = canonical_json_str(snapshot)
    con.execute(
        "INSERT INTO shot_revisions (id, snapshot_json, snapshot_hash) "
        "VALUES (?, ?, ?)",
        ("shot-revision-1", snapshot_json, canonical_hash(snapshot)),
    )
    binding = pack["binding"]
    value = binding["value"]
    con.execute(
        "INSERT INTO shot_revision_production_worlds ("
        "shot_revision_id, production_world_hash, binding_id, binding_hash, "
        "composition_revision_id, composition_revision_hash, "
        "spatial_world_revision_id, spatial_world_revision_hash) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "shot-revision-1",
            production_world_hash(pack),
            binding["binding_id"],
            binding["binding_hash"],
            value["composition_revision"]["revision_id"],
            value["composition_revision"]["snapshot_hash"],
            value["spatial_world_revision"]["revision_id"],
            value["spatial_world_revision"]["snapshot_hash"],
        ),
    )
    state = pack["instance_spatial_states"][0]
    con.execute(
        "INSERT INTO shot_revision_production_instance_spatial_states ("
        "shot_revision_id, position, composition_id, occurrence_id, "
        "production_instance_track_id, requirement, x_mm, y_mm, z_mm, "
        "yaw_udeg, pitch_udeg, roll_udeg, source_transition_id, "
        "source_anchor_type, source_anchor_id, source_boundary) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "shot-revision-1",
            0,
            state["composition_id"],
            state["occurrence_id"],
            state["production_instance_track_id"],
            state["requirement"],
            *state["transform"]["translation_mm"],
            *state["transform"]["rotation_udeg"],
            state["source_transition"]["transition_id"],
            state["source_transition"]["anchor_type"],
            state["source_transition"]["anchor_id"],
            state["source_transition"]["boundary"],
        ),
    )
    return con, pack


def test_m13_recovery_reverifies_shot_revision_hash():
    con, _pack = _captured_history_db()
    try:
        _verify_m13_selection_and_history(con)
        con.execute(
            "UPDATE shot_revisions SET snapshot_hash = ? WHERE id = ?",
            ("0" * 64, "shot-revision-1"),
        )
        with pytest.raises(RecoveryCorruption, match="snapshot_hash"):
            _verify_m13_selection_and_history(con)
    finally:
        con.close()


def test_m13_recovery_reverifies_canonical_shot_revision_bytes():
    con, _pack = _captured_history_db()
    try:
        row = con.execute(
            "SELECT snapshot_json FROM shot_revisions WHERE id = ?",
            ("shot-revision-1",),
        ).fetchone()
        con.execute(
            "UPDATE shot_revisions SET snapshot_json = ? WHERE id = ?",
            ("  " + row[0], "shot-revision-1"),
        )
        with pytest.raises(RecoveryCorruption, match="not canonical"):
            _verify_m13_selection_and_history(con)
    finally:
        con.close()


def test_m13_recovery_reverifies_production_world_hash():
    con, _pack = _captured_history_db()
    try:
        _verify_m13_selection_and_history(con)
        con.execute(
            "UPDATE shot_revision_production_worlds "
            "SET production_world_hash = ? WHERE shot_revision_id = ?",
            ("0" * 64, "shot-revision-1"),
        )
        with pytest.raises(RecoveryCorruption, match="production_world_hash"):
            _verify_m13_selection_and_history(con)
    finally:
        con.close()


@pytest.mark.parametrize(
    ("column", "bad_value"),
    [
        ("position", 1),
        ("composition_id", "wrong-composition"),
        ("occurrence_id", "wrong-occurrence"),
        ("production_instance_track_id", "wrong-track"),
        ("requirement", "optional"),
        ("x_mm", 111),
        ("y_mm", 222),
        ("z_mm", 333),
        ("yaw_udeg", 444),
        ("pitch_udeg", 555),
        ("roll_udeg", 666),
        ("source_transition_id", "wrong-transition"),
        ("source_anchor_type", "scene"),
        ("source_anchor_id", "wrong-anchor"),
        ("source_boundary", "end"),
    ],
)
def test_m13_recovery_verifies_every_captured_pi_spatial_projection(
    column, bad_value
):
    con, _pack = _captured_history_db()
    try:
        _verify_m13_selection_and_history(con)
        con.execute(
            f"UPDATE shot_revision_production_instance_spatial_states "
            f"SET {column} = ? WHERE shot_revision_id = ?",  # noqa: S608
            (bad_value, "shot-revision-1"),
        )
        with pytest.raises(RecoveryCorruption, match="PI spatial-state"):
            _verify_m13_selection_and_history(con)
    finally:
        con.close()
