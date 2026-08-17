"""Canonical JSON serialization tests (plan §12, §50.6)."""

from __future__ import annotations

import hashlib

from soloring.domain.canonical import (
    canonical_hash,
    canonical_json_bytes,
    canonical_json_str,
)


def test_exact_byte_fixture() -> None:
    # plan §12.1 — this snapshot must produce exactly these UTF-8 bytes.
    snapshot = {
        "schema_version": 1,
        "intent": {"subject": "test", "action": None},
        "references": [],
    }
    expected = (
        b'{"intent":{"action":null,"subject":"test"},'
        b'"references":[],"schema_version":1}'
    )
    assert canonical_json_bytes(snapshot) == expected


def test_dict_insertion_order_irrelevant() -> None:
    a = canonical_json_bytes({"b": 1, "a": 2})
    b = canonical_json_bytes({"a": 2, "b": 1})
    assert a == b == b'{"a":2,"b":1}'


def test_empty_string_vs_null_distinct() -> None:
    assert canonical_json_bytes({"x": ""}) == b'{"x":""}'
    assert canonical_json_bytes({"x": None}) == b'{"x":null}'


def test_unicode_preserved_no_ascii_escape() -> None:
    s = "café—日本语"
    out = canonical_json_bytes({"s": s})
    assert out == ('{"s":"%s"}' % s).encode("utf-8")
    assert b"\\u" not in out  # ensure_ascii=False


def test_combining_characters_preserved_exact() -> None:
    # No NFC/NFD normalization (plan §12.2); precomposed vs decomposed differ.
    nfc = "é"  # U+00E9
    nfd = "e\u0301"  # e + combining acute
    assert canonical_json_bytes({"s": nfc}) != canonical_json_bytes({"s": nfd})
    assert canonical_hash({"s": nfc}) != canonical_hash({"s": nfd})


def test_embedded_quotes_and_newlines() -> None:
    v = 'he said "hi"\nnext line'
    assert canonical_json_bytes({"v": v}) == b'{"v":"he said \\"hi\\"\\nnext line"}'


def test_very_long_subject_deterministic() -> None:
    s = "a" * 100_000
    assert canonical_hash({"s": s}) == hashlib.sha256(
        canonical_json_bytes({"s": s})
    ).hexdigest()


def test_hash_and_str_match_bytes() -> None:
    snap = {"schema_version": 1, "intent": {"subject": "x"}, "references": []}
    assert canonical_hash(snap) == hashlib.sha256(canonical_json_bytes(snap)).hexdigest()
    assert canonical_json_str(snap) == canonical_json_bytes(snap).decode("utf-8")


def test_reference_ordering_is_canonical() -> None:
    # References sort by (role, position, asset_id) before serialization (§13).
    refs = [
        {"asset_id": "b", "blob_hash": "bb" * 32, "role": "reference", "position": 0},
        {"asset_id": "a", "blob_hash": "aa" * 32, "role": "character", "position": 0},
        {"asset_id": "a", "blob_hash": "aa" * 32, "role": "reference", "position": 1},
    ]
    key = lambda r: (r["role"], r["position"], r["asset_id"])  # noqa: E731

    snap_a = {"schema_version": 1, "intent": {"subject": "x"}, "references": sorted(refs, key=key)}
    snap_b = {"schema_version": 1, "intent": {"subject": "x"}, "references": sorted(reversed(refs), key=key)}
    assert canonical_hash(snap_a) == canonical_hash(snap_b)
