"""Canonical Project-local narrative ordering (M7A.5, plan §12–§15).

THE single authoritative ordering implementation. It owns the only
Project-topology → boundary-stream → boundary-rank → target Shot/start
position derivation in the codebase; Feature/Relation resolvers (M7B+) and
any other consumer must use this module, never re-implement ordering
(plan §14: "no secondary ordering implementation exists in ... resolvers").

Frozen contract:

* One Project-local flattened boundary stream per active Project (§12.1,
  contract patch §8 — strictly the TARGET Project's; no ordering
  relationship exists between Projects):

      for Sequence ordered by position:
          Sequence/start
          for Scene in Sequence ordered by position:
              Scene/start
              for assigned ACTIVE Shot ordered by scene_position:
                  Shot/start
                  Shot/end
              Scene/end
          Sequence/end

* Boundary precedence (§13): container start < first child start; child
  ends < container end; container end < next container start. A monotonically
  increasing in-memory rank is assigned in emission order — ties cannot
  exist by construction, and NO database iteration order, timestamp,
  creation order, or UUID is ever consulted as a semantic tie-breaker.

* Ordering input is ONLY the persisted position columns (Sequences.position,
  Scenes.position, Shots.scene_position) of ACTIVE rows. Soft-deleted nodes
  and unassigned Shots never appear. Nodes belonging to OTHER Projects are
  simply not this stream's business (Project-locality), even if their own
  topology were internally corrupt.

* Stored topology corruption reachable from THIS Project — an active Scene
  under a missing/tombstoned Sequence of this Project, an assigned active
  Shot under a missing/tombstoned Scene/Sequence of this Project, or a
  position collision among active siblings — is an internal invariant
  failure: raised explicitly, never silently skipped and never repaired by
  ordering on identity (§13/§15).

Ranks are ephemeral: meaningful only inside one topology snapshot loaded by
one caller read. Nothing persists them.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from soloring.errors import internal_invariant

ANCHOR_SEQUENCE = "sequence"
ANCHOR_SCENE = "scene"
ANCHOR_SHOT = "shot"

BOUNDARY_START = "start"
BOUNDARY_END = "end"


@dataclass(frozen=True)
class Boundary:
    """One flattened narrative boundary.

    ``(anchor_type, anchor_id, boundary)`` is the stable boundary identity:
    it survives any reorder — only the ephemeral ``rank`` moves.
    """

    anchor_type: str
    anchor_id: str
    boundary: str
    rank: int

    @property
    def identity(self) -> tuple[str, str, str]:
        return (self.anchor_type, self.anchor_id, self.boundary)


@dataclass(frozen=True)
class NarrativeOrdering:
    """The authoritative ordering of one Project's active topology."""

    project_id: str
    boundaries: tuple[Boundary, ...]

    def rank_of(self, anchor_type: str, anchor_id: str, boundary: str) -> int:
        """The ephemeral monotonic rank of one boundary."""
        for b in self.boundaries:
            if (
                b.anchor_type == anchor_type
                and b.anchor_id == anchor_id
                and b.boundary == boundary
            ):
                return b.rank
        raise internal_invariant(
            f"Boundary ({anchor_type}, {anchor_id}, {boundary}) does not "
            "exist in this Project's narrative ordering."
        )

    def boundary_identities(self) -> tuple[tuple[str, str, str], ...]:
        return tuple(b.identity for b in self.boundaries)

    def shot_start_rank(self, shot_id: str) -> int:
        return self.rank_of(ANCHOR_SHOT, shot_id, BOUNDARY_START)

    def shot_end_rank(self, shot_id: str) -> int:
        return self.rank_of(ANCHOR_SHOT, shot_id, BOUNDARY_END)

    def shot_ids_in_order(self) -> tuple[str, ...]:
        """Active assigned Shots in narrative order (by their /start rank)."""
        return tuple(
            b.anchor_id
            for b in self.boundaries
            if b.anchor_type == ANCHOR_SHOT and b.boundary == BOUNDARY_START
        )


def _corrupt(detail: str):
    return internal_invariant(
        f"Stored narrative topology is corrupt: {detail} "
        "(explicit failure — no silent skip, no identity-based repair)."
    )


async def load_narrative_ordering(
    conn: AsyncConnection, project_id: str
) -> NarrativeOrdering:
    """Build the target Project's boundary stream from ONE caller-held read.

    All queries run on the caller's connection so the ordering derives from
    the same SQLite read snapshot the caller uses (capture/read units keep
    their one-consistent-read discipline). Rows are ordered ONLY by the
    persisted position columns; ranks are assigned by position sort, so
    fetch order is never semantic.
    """
    sequences = (
        await conn.execute(
            text(
                "SELECT id, position FROM sequences "
                "WHERE project_id = :pid AND deleted_at IS NULL "
                "ORDER BY position"
            ),
            {"pid": project_id},
        )
    ).mappings().all()
    seq_positions = [r["position"] for r in sequences]
    if len(set(seq_positions)) != len(seq_positions):
        raise _corrupt(  # pragma: no cover - active uniqueness forbids it
            f"project {project_id} has duplicate active Sequence positions"
        )
    active_seq_ids = {r["id"] for r in sequences}

    # Active scenes with their parent sequence's reachability. Scenes under
    # other Projects' sequences are out of scope by Project-locality.
    scene_rows = (
        await conn.execute(
            text(
                "SELECT sc.id, sc.sequence_id, sc.position, "
                "sq.project_id AS seq_project, "
                "sq.deleted_at AS seq_deleted "
                "FROM scenes sc "
                "LEFT JOIN sequences sq ON sq.id = sc.sequence_id "
                "WHERE sc.deleted_at IS NULL "
                "ORDER BY sc.position"
            ),
            {},
        )
    ).mappings().all()

    scenes_by_sequence: dict[str, list[dict]] = {}
    for row in scene_rows:
        if row["seq_project"] != project_id:
            continue  # another Project's subtree — not this stream's business
        if row["seq_project"] is None:
            raise _corrupt(  # pragma: no cover - FK forbids missing parent
                f"active scene {row['id']} references missing sequence "
                f"{row['sequence_id']}"
            )
        if row["seq_deleted"] is not None:
            raise _corrupt(
                f"active scene {row['id']} sits under tombstoned sequence "
                f"{row['sequence_id']} of this project"
            )
        if row["sequence_id"] not in active_seq_ids:
            raise _corrupt(  # pragma: no cover - covered by checks above
                f"active scene {row['id']} unreachable from project"
            )
        scenes_by_sequence.setdefault(row["sequence_id"], []).append(
            dict(row)
        )
    for sid, rows in scenes_by_sequence.items():
        positions = [r["position"] for r in rows]
        if len(set(positions)) != len(positions):
            raise _corrupt(  # pragma: no cover - active uniqueness forbids
                f"sequence {sid} has duplicate active Scene positions"
            )

    # Assigned active shots OF THIS PROJECT with their scene/sequence
    # reachability. Shots are selected by their own authoritative
    # project_id (scene_id deliberately has no database FK — the M6 no-FK
    # decision — so ownership must be validated on the Shot itself, never
    # inferred from the Scene's Sequence). A different Project's Shot
    # never enters this query, so it can neither be imported into this
    # stream nor silently mask this Project's corruption.
    shot_rows = (
        await conn.execute(
            text(
                "SELECT sh.id, sh.scene_id, sh.scene_position, "
                "sc.sequence_id AS scene_sequence_id, "
                "sc.deleted_at AS scene_deleted, "
                "sq.project_id AS seq_project, "
                "sq.deleted_at AS seq_deleted "
                "FROM shots sh "
                "LEFT JOIN scenes sc ON sc.id = sh.scene_id "
                "LEFT JOIN sequences sq ON sq.id = sc.sequence_id "
                "WHERE sh.project_id = :pid "
                "AND sh.deleted_at IS NULL AND sh.scene_id IS NOT NULL "
                "ORDER BY sh.scene_position"
            ),
            {"pid": project_id},
        )
    ).mappings().all()

    active_scene_ids = {
        row["id"]
        for rows in scenes_by_sequence.values()
        for row in rows
    }
    active_scene_to_sequence = {
        row["id"]: row["sequence_id"]
        for rows in scenes_by_sequence.values()
        for row in rows
    }
    shots_by_scene: dict[str, list[dict]] = {}
    for row in shot_rows:
        if row["scene_sequence_id"] is None:
            raise _corrupt(
                f"assigned active shot {row['id']} references missing "
                f"scene {row['scene_id']}"
            )
        if row["scene_deleted"] is not None:
            raise _corrupt(
                f"assigned active shot {row['id']} sits under tombstoned "
                f"scene {row['scene_id']}"
            )
        if row["seq_project"] is None:
            raise _corrupt(  # pragma: no cover - scene existence checked
                f"assigned active shot {row['id']} reaches a scene whose "
                f"sequence is missing"
            )
        if row["seq_deleted"] is not None:
            raise _corrupt(
                f"assigned active shot {row['id']} sits under tombstoned "
                f"sequence {row['scene_sequence_id']}"
            )
        if row["seq_project"] != project_id:
            raise _corrupt(
                f"assigned active shot {row['id']} of this project points "
                f"at a scene of another project"
            )
        if row["scene_id"] not in active_scene_ids:
            # Active scene of this project that never reached the stream:
            # only possible if its own sequence path was corrupt — but that
            # was already raised during scene classification, so this is
            # unreachable defense in depth.
            raise _corrupt(  # pragma: no cover - scene checks precede
                f"assigned active shot {row['id']} unreachable from project"
            )
        assert active_scene_to_sequence[row["scene_id"]] == \
            row["scene_sequence_id"]
        shots_by_scene.setdefault(row["scene_id"], []).append(dict(row))
    for cid, rows in shots_by_scene.items():
        positions = [r["scene_position"] for r in rows]
        if len(set(positions)) != len(positions):
            raise _corrupt(  # pragma: no cover - active uniqueness forbids
                f"scene {cid} has duplicate active shot scene_positions"
            )

    # Flattened emission in the frozen precedence order; sorting is by the
    # persisted position columns ONLY.
    boundaries: list[Boundary] = []

    def emit(anchor_type: str, anchor_id: str, boundary: str) -> None:
        boundaries.append(
            Boundary(
                anchor_type=anchor_type,
                anchor_id=anchor_id,
                boundary=boundary,
                rank=len(boundaries),
            )
        )

    for seq in sequences:  # already ORDER BY position
        emit(ANCHOR_SEQUENCE, seq["id"], BOUNDARY_START)
        for scene in sorted(
            scenes_by_sequence.get(seq["id"], []), key=lambda r: r["position"]
        ):
            emit(ANCHOR_SCENE, scene["id"], BOUNDARY_START)
            for shot in sorted(
                shots_by_scene.get(scene["id"], []),
                key=lambda r: r["scene_position"],
            ):
                emit(ANCHOR_SHOT, shot["id"], BOUNDARY_START)
                emit(ANCHOR_SHOT, shot["id"], BOUNDARY_END)
            emit(ANCHOR_SCENE, scene["id"], BOUNDARY_END)
        emit(ANCHOR_SEQUENCE, seq["id"], BOUNDARY_END)

    return NarrativeOrdering(
        project_id=project_id, boundaries=tuple(boundaries)
    )


def boundaries_through(
    ordering: NarrativeOrdering, rank: int
) -> tuple[Boundary, ...]:
    """All boundaries through ``rank`` INCLUSIVE — the effective-state
    eligibility set at that boundary position.

    The frozen M7 semantic rule: state at target Shot/start includes every
    transition anchored at a boundary with ``transition_rank <= shot_start_rank``
    — the target's own /start boundary IS eligible — while everything after
    it (including the target's own /end) is not. The M7B resolver must use
    this inclusive comparison (or this helper), never a strict `<`.
    """
    return tuple(b for b in ordering.boundaries if b.rank <= rank)


def boundaries_before(
    ordering: NarrativeOrdering, rank: int
) -> tuple[Boundary, ...]:
    """All boundaries strictly before ``rank``.

    NOT the effective-state rule (that is ``boundaries_through``); this
    strict prefix exists only for generic prefix inspection.
    """
    return tuple(b for b in ordering.boundaries if b.rank < rank)
