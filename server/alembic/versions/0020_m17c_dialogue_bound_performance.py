"""M17C: dialogue-bound Performance capture foundation.

R4 freezes migration 0020 as the additive M17C migration.  This first
implementation slice creates the PF-03 immutable synchronization companions.
The remaining PF-02/capture/execution tables are added to this same migration
before publication; the branch is not published while 0020 is partial.

Downgrade refuses if either M17C binding table contains rows.
"""

from alembic import op
import sqlalchemy as sa

revision = "0020_m17c_dialogue_bound_performance_capture"
down_revision = "0019_m17b_performance_revisions"
branch_labels = None
depends_on = None

_M17C_TABLES = (
    "performance_candidate_vocal_bindings",
    "performance_revision_vocal_bindings",
)


def _binding_table(name: str, parent_col: str, parent_table: str,
                   prefix: str) -> None:
    op.create_table(
        name,
        sa.Column(parent_col, sa.String(36), primary_key=True),
        sa.Column("vocal_performance_revision_id", sa.String(36),
                  nullable=False),
        sa.Column("source_start_sample", sa.Integer(), nullable=False),
        sa.Column("source_end_sample_exclusive", sa.Integer(), nullable=False),
        sa.Column("sample_rate_hz", sa.Integer(), nullable=False),
        sa.Column("performance_origin_num", sa.Integer(), nullable=False),
        sa.Column("performance_origin_den", sa.Integer(), nullable=False),
        sa.Column("synchronization_basis_version", sa.Integer(),
                  nullable=False),
        sa.Column("binding_schema_version", sa.Integer(), nullable=False),
        sa.Column("binding_json", sa.Text(), nullable=False),
        sa.Column("binding_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "source_start_sample >= 0",
            name=f"ck_{prefix}_start_nonneg"),
        sa.CheckConstraint(
            "source_start_sample < source_end_sample_exclusive",
            name=f"ck_{prefix}_sample_order"),
        sa.CheckConstraint(
            "sample_rate_hz > 0", name=f"ck_{prefix}_rate_positive"),
        sa.CheckConstraint(
            "performance_origin_den > 0",
            name=f"ck_{prefix}_origin_den_positive"),
        sa.CheckConstraint(
            "synchronization_basis_version = 1",
            name=f"ck_{prefix}_sync_basis"),
        sa.CheckConstraint(
            "binding_schema_version = 1", name=f"ck_{prefix}_schema"),
        sa.CheckConstraint(
            "length(binding_hash) = 64 AND "
            "binding_hash NOT GLOB '*[^0-9a-f]*'",
            name=f"ck_{prefix}_hash_hex"),
        sa.ForeignKeyConstraint(
            [parent_col], [f"{parent_table}.id"],
            name=f"fk_{prefix}_{'candidate' if prefix == 'pcvb' else 'revision'}",
            ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["vocal_performance_revision_id"],
            ["vocal_performance_revisions.id"],
            name=f"fk_{prefix}_vp", ondelete="RESTRICT"),
    )


def upgrade() -> None:
    _binding_table(
        "performance_candidate_vocal_bindings",
        "performance_candidate_id", "performance_candidates", "pcvb")
    _binding_table(
        "performance_revision_vocal_bindings",
        "performance_revision_id", "performance_revisions", "prvb")


def downgrade() -> None:
    conn = op.get_bind()
    for table in _M17C_TABLES:
        n = conn.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar()
        if n:
            raise RuntimeError(
                f"0020 downgrade refused: {table} contains {n} row(s); "
                "M17C dialogue-bound Performance authority is not deleted "
                "by schema downgrade")
    op.drop_table("performance_revision_vocal_bindings")
    op.drop_table("performance_candidate_vocal_bindings")
