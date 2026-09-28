"""M17C-B: Shot-local Performance working mappings (PF-02).

B-F1 corrective: migration identity 0021_m17c_shot_performance_mappings was
frozen with M17C-A (its exact c502b81 definition is untouched); this
successor creates the PF-02 working-mapping table so databases already
stamped at 0020 upgrade mechanically.

Downgrade refuses if the working-mapping table contains rows (working
intent is not deleted by schema downgrade).
"""

from alembic import op
import sqlalchemy as sa

revision = "0021_m17c_shot_performance_mappings"
down_revision = "0020_m17c_perf_capture_r2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shot_performance_segment_mappings",
        sa.Column("shot_id", sa.String(36), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("performance_revision_id", sa.String(36),
                  nullable=False),
        sa.Column("performance_start_num", sa.Integer(), nullable=False),
        sa.Column("performance_start_den", sa.Integer(), nullable=False),
        sa.Column("performance_end_num", sa.Integer(), nullable=False),
        sa.Column("performance_end_den", sa.Integer(), nullable=False),
        sa.Column("shot_anchor_num", sa.Integer(), nullable=False),
        sa.Column("shot_anchor_den", sa.Integer(), nullable=False),
        sa.Column("vocal_mapping_position", sa.Integer(), nullable=True),
        sa.Column("mapping_schema_version", sa.Integer(),
                  nullable=False),
        sa.Column("mapping_json", sa.Text(), nullable=False),
        sa.Column("mapping_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint("position >= 0", name="ck_spsm_position"),
        sa.CheckConstraint("performance_start_den > 0",
                           name="ck_spsm_start_den_positive"),
        sa.CheckConstraint("performance_end_den > 0",
                           name="ck_spsm_end_den_positive"),
        sa.CheckConstraint("shot_anchor_den > 0",
                           name="ck_spsm_anchor_den_positive"),
        sa.CheckConstraint("mapping_schema_version = 1",
                           name="ck_spsm_mapping_schema"),
        sa.CheckConstraint("length(mapping_hash) = 64",
                           name="ck_spsm_mapping_hash_len"),
        sa.ForeignKeyConstraint(
            ["shot_id"], ["shots.id"],
            name="fk_spsm_shot", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["performance_revision_id"], ["performance_revisions.id"],
            name="fk_spsm_pr", ondelete="RESTRICT"),
    )
    op.create_index("ix_spsm_pr", "shot_performance_segment_mappings",
                    ["performance_revision_id"])


def downgrade() -> None:
    conn = op.get_bind()
    n = conn.execute(sa.text(
        "SELECT COUNT(*) FROM shot_performance_segment_mappings")).scalar()
    if n:
        raise RuntimeError(
            f"0021 downgrade refused: "
            "shot_performance_segment_mappings contains {n} row(s); "
            "M17C-B working intent is not deleted by schema downgrade")
    op.drop_index("ix_spsm_pr",
                  table_name="shot_performance_segment_mappings")
    op.drop_table("shot_performance_segment_mappings")
