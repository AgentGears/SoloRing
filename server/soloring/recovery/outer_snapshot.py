"""RR16-M17CC-01: the ONE shared recovery-side outer-ShotRevision
snapshot parser.

The successor recovery chain is total over malformed
``shot_revisions.snapshot_json`` values BEFORE any predecessor
verifier makes semantic use of a decoded snapshot: the M16 verifier
parses every ShotRevision (the global history enumeration, the
intra-shot companion sweep, and the proposal source-revision lookup)
BEFORE the M17C-C chain runs, and its former bare ``json.loads`` +
``.get()`` exposed raw ``JSONDecodeError`` / ``UnicodeDecodeError`` /
``AttributeError`` for malformed JSON, an invalid-UTF-8 BLOB, or a
valid non-object top level.

The law here is deliberately ONLY the parse/shape boundary:
``load_outer_snapshot`` accepts exactly the persisted text/bytes
forms the recovery contract supports, converts EVERY decode failure
into the typed recovery-corruption contract, and requires a JSON
OBJECT before any consumer calls ``.get()`` on the result. Semantic
interpretation — schema discrimination, canonical-bytes/hash
authentication, and every closure law — stays with the owning
verifier (M16 keeps predecessor-first semantics; the M17C-C
classification keeps its own guarded decode and its
authenticate-before-classification law unchanged).
"""

from __future__ import annotations

import json


def load_outer_snapshot(snapshot_json, what: str) -> dict:
    """Decode one persisted ``shot_revisions.snapshot_json`` value
    into a JSON object, or fail as typed recovery corruption.

    ``json.loads`` accepts both text and bytes (decoding bytes
    strictly as UTF-8), so the exhaustive malformed family —
    non-JSON text, an invalid-UTF-8 SQLite BLOB, or a decodable but
    non-object top level such as ``[]`` — terminates through
    :class:`RecoveryCorruption`, never a raw Python exception.
    """
    from soloring.recovery.backup import RecoveryCorruption

    try:
        snap = json.loads(snapshot_json)
    except (ValueError, TypeError) as exc:
        # ValueError covers JSONDecodeError and UnicodeDecodeError;
        # TypeError covers non-text/non-bytes storage classes
        raise RecoveryCorruption(
            f"{what} snapshot_json is not decodable persisted JSON: "
            f"{exc}") from exc
    if not isinstance(snap, dict):
        raise RecoveryCorruption(
            f"{what} snapshot is not a JSON object")
    return snap
