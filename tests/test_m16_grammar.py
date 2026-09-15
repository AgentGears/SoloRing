"""M16 strict grammar proofs (frozen R6 M16:GRAMMAR:01-10)."""

from __future__ import annotations

import sqlite3

import pytest

from soloring.continuity.intra_shot_canonical import (
    SAFE_INT_MAX,
    event_value,
    require_interior_time,
    require_plain_int,
    state_storage,
    target_value,
)
from soloring.domain.canonical import canonical_hash
from soloring.errors import SoloRingError

TARGET = {"kind": "entity_feature", "id": "11111111-1111-4111-8111-111111111111"}
ABSENT = {"present": False}


def _present(value="fresh"):
    return {"present": True, "value": value, "value_hash": canonical_hash(value)}


def _event(**changes):
    kw = dict(time_ms=1, ordinal=0, target=TARGET, before=ABSENT,
              after=_present(), persistence_mode="transient")
    kw.update(changes)
    return event_value(**kw)


def test_grammar_01():
    """time_ms rejects bool, float and numeric string."""
    for value in (True, 1.0, "1"):
        with pytest.raises(SoloRingError):
            _event(time_ms=value)


def test_grammar_02():
    """ordinal rejects bool, float and numeric string."""
    for value in (False, 0.0, "0"):
        with pytest.raises(SoloRingError):
            _event(ordinal=value)


def test_grammar_03():
    """Every M16 integer helper rejects values above the JS-safe maximum."""
    with pytest.raises(SoloRingError):
        require_plain_int(SAFE_INT_MAX + 1, field="ordinal")
    with pytest.raises(SoloRingError):
        _event(time_ms=SAFE_INT_MAX + 1)


def test_grammar_04():
    """time zero is not a genuine intra-Shot event coordinate."""
    with pytest.raises(SoloRingError):
        _event(time_ms=0)


def test_grammar_05():
    """time equal to duration is rejected by the frozen interior law."""
    with pytest.raises(SoloRingError):
        require_interior_time(1000, 1000)


def test_grammar_06():
    """time greater than duration is rejected by the frozen interior law."""
    with pytest.raises(SoloRingError):
        require_interior_time(1001, 1000)


def test_grammar_07():
    """negative ordinal is rejected."""
    with pytest.raises(SoloRingError):
        _event(ordinal=-1)


def test_grammar_08():
    """Target grammar is closed; database XOR shape is independently frozen."""
    with pytest.raises(SoloRingError):
        target_value("feature", TARGET["id"])
    from soloring.continuity.intra_shot_models import ShotIntraShotEvent

    check = next(
        c for c in ShotIntraShotEvent.__table__.constraints
        if getattr(c, "name", None) == "ck_sise_target_xor"
    )
    sql = str(check.sqltext)
    assert "entity_feature_id IS NOT NULL" in sql
    assert "entity_relation_id IS NOT NULL" in sql
    assert "production_instance_feature_id IS NOT NULL" in sql


def test_grammar_09():
    """Feature states require the exact closed shape and canonical value hash."""
    meta = {"value_type": "enum", "enum_values_json": '["fresh","healing"]'}
    with pytest.raises(SoloRingError):
        state_storage("entity_feature", {"present": False, "value": "fresh"}, meta)
    with pytest.raises(SoloRingError):
        state_storage(
            "entity_feature",
            {"present": True, "value": "fresh", "value_hash": "0" * 64},
            meta,
        )
    value, raw, digest = state_storage("entity_feature", _present(), meta)
    assert value == _present()
    assert digest == canonical_hash(value)
    assert raw.startswith('{"present":true')


def test_grammar_10():
    """before == after is rejected as a no-op."""
    with pytest.raises(SoloRingError):
        _event(before=ABSENT, after=ABSENT)
