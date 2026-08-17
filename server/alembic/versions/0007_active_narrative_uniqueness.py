"""active-only narrative uniqueness (M6B re-gate)

Revision ID: 0007_active_narrative_uniqueness
Revises: 0006_story_world_semantic_dependencies
Create Date: 2026-08-17

Corrects the interaction between soft deletion and ordered uniqueness
(M6B gate review blocker 1). The table-level UNIQUE constraints installed
by 0006 include tombstones, so active siblings can never compact to
0..N-1 after a soft deletion (a compacted active row would collide with
the vacated-but-still-occupied tombstone position).

The contract after this migration:

    sequences: UNIQUE(project_id, position)  WHERE deleted_at IS NULL
    scenes:    UNIQUE(sequence_id, position) WHERE deleted_at IS NULL
    shots:     UNIQUE(scene_id, scene_position)
               WHERE deleted_at IS NULL AND scene_id IS NOT NULL

Tombstones keep their last narrative coordinates forever; only ACTIVE
rows participate in uniqueness and ordering.

THIS IS THE FIRST STRUCTURAL MIGRATION THAT REBUILDS POPULATED TABLES:
sequences and scenes carry table-level constraints that SQLite cannot
drop in place, so each is batch-recreated from an explicit ``copy_from``
definition (all named constraints stated, so the recreate is exact) and
the data copy is proven by the populated-table preservation gate in
tests/test_migration_m6b.py — the previously deferred obligation,
deliberately activated here. ``shots`` only swaps a standalone index:
no rebuild.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from soloring.db.base import NAMING_CONVENTION
def _meta() -> sa.MetaData:
    return sa.MetaData(naming_convention=NAMING_CONVENTION)

# revision identifiers, used by Alembic.
revision: str = "0007_active_narrative_uniqueness"
down_revision: Union[str, None] = "0006_story_world_semantic_dependencies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOW = "strftime('%Y-%m-%dT%H:%M:%fZ','now')"


def _sequences_0006(with_unique: bool = True) -> sa.Table:
    """The exact 0006 sequences definition (table-level UNIQUE)."""
    constraints: list[sa.Constraint] = [
        sa.PrimaryKeyConstraint("id", name="pk_sequences"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            name="fk_sequences_project_id_projects", ondelete="RESTRICT",
        ),
        sa.CheckConstraint("position >= 0", name="ck_sequences_position_nonneg"),
        sa.Index(
            "ix_sequences_project_active", "project_id", "deleted_at",
            "position",
        ),
    ]
    if with_unique:
        constraints.append(sa.UniqueConstraint(
            "project_id", "position", name="uq_sequences_project_id_position"
        ))
    return sa.Table(
        "sequences",
        _meta(),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False,
                  server_default=sa.text(_NOW)),
        sa.Column("updated_at", sa.Text(), nullable=False,
                  server_default=sa.text(_NOW)),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        *constraints,
    )


def _scenes_0006(with_unique: bool = True) -> sa.Table:
    constraints: list[sa.Constraint] = [
        sa.PrimaryKeyConstraint("id", name="pk_scenes"),
        sa.ForeignKeyConstraint(
            ["sequence_id"], ["sequences.id"],
            name="fk_scenes_sequence_id_sequences", ondelete="RESTRICT",
        ),
        sa.CheckConstraint("position >= 0", name="ck_scenes_position_nonneg"),
        sa.Index(
            "ix_scenes_sequence_active", "sequence_id", "deleted_at",
            "position",
        ),
    ]
    if with_unique:
        constraints.append(sa.UniqueConstraint(
            "sequence_id", "position", name="uq_scenes_sequence_id_position"
        ))
    return sa.Table(
        "scenes",
        _meta(),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("sequence_id", sa.String(36), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False,
                  server_default=sa.text(_NOW)),
        sa.Column("updated_at", sa.Text(), nullable=False,
                  server_default=sa.text(_NOW)),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        *constraints,
    )


def upgrade() -> None:
    # Batch recreate from the explicit 0006 definition, dropping only the
    # table-level UNIQUE. copy_from carries every other named constraint,
    # so nothing else changes; data is copied by the batch move.
    with op.batch_alter_table(
        "sequences", copy_from=_sequences_0006()
    ) as batch:
        batch.drop_constraint(
            "uq_sequences_project_id_position", type_="unique"
        )
    op.create_index(
        "uq_sequences_project_id_position", "sequences",
        ["project_id", "position"], unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
    )

    with op.batch_alter_table("scenes", copy_from=_scenes_0006()) as batch:
        batch.drop_constraint(
            "uq_scenes_sequence_id_position", type_="unique"
        )
    op.create_index(
        "uq_scenes_sequence_id_position", "scenes",
        ["sequence_id", "position"], unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
    )
    # shots: index swap only — no rebuild of the populated table.
    op.drop_index("uq_shots_scene_position", table_name="shots")
    op.create_index(
        "uq_shots_scene_position", "shots",
        ["scene_id", "scene_position"], unique=True,
        sqlite_where=sa.text("deleted_at IS NULL AND scene_id IS NOT NULL"),
    )


def _preflight_downgrade_representable() -> None:
    """Refuse the 0007 -> 0006 downgrade BEFORE any DDL when current data
    cannot be represented by 0006's global uniqueness (M6B re-gate).

    Legal 0007 states — an active row reusing a tombstone's narrative
    coordinate — violate 0006's table-level/index-level uniqueness. Because
    SQLite DDL here is non-transactional, discovering that mid-swap leaves a
    half-migrated schema behind; instead the check runs first and the
    downgrade refuses with zero side effects. Tombstone coordinates are
    never rewritten to force compatibility (that would violate the 0007
    invariant they are frozen history).
    """
    bind = op.get_bind()
    checks = (
        ("sequences", "project_id, position", ""),
        ("scenes", "sequence_id, position", ""),
        ("shots", "scene_id, scene_position", "WHERE scene_id IS NOT NULL"),
    )
    collisions: list[str] = []
    for table, cols, where in checks:
        rows = bind.execute(
            sa.text(
                f"SELECT {cols}, COUNT(*) AS n FROM {table} {where} "
                f"GROUP BY {cols} HAVING COUNT(*) > 1"
            )
        ).fetchall()
        if rows:
            rendered = ", ".join(str(tuple(r)) for r in rows)
            collisions.append(f"{table}: {rendered}")
    if collisions:
        raise RuntimeError(
            "Cannot downgrade 0007 -> 0006: active rows legally reuse "
            "tombstone narrative coordinates under 0007, which the 0006 "
            "global uniqueness cannot represent. No schema was changed. "
            "Collisions: " + "; ".join(collisions)
        )


def downgrade() -> None:
    _preflight_downgrade_representable()
    op.drop_index("uq_shots_scene_position", table_name="shots")
    op.create_index(
        "uq_shots_scene_position", "shots",
        ["scene_id", "scene_position"], unique=True,
    )
    # copy_from describes the CURRENT (post-0007) table — no table-level
    # UNIQUE — and the batch op re-adds the 0006 constraint.
    op.drop_index("uq_scenes_sequence_id_position", table_name="scenes")
    with op.batch_alter_table(
        "scenes", copy_from=_scenes_0006(with_unique=False)
    ) as batch:
        batch.create_unique_constraint(
            "uq_scenes_sequence_id_position", ["sequence_id", "position"]
        )
    op.drop_index("uq_sequences_project_id_position", table_name="sequences")
    with op.batch_alter_table(
        "sequences", copy_from=_sequences_0006(with_unique=False)
    ) as batch:
        batch.create_unique_constraint(
            "uq_sequences_project_id_position", ["project_id", "position"]
        )
