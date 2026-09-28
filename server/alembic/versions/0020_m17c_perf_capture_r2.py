"""M17C: dialogue-bound Performance capture foundation (DR26-04 r2).

Revision identity note (DR26-04): this migration supersedes the
unpublished draft identity `0020_m17c_performance_capture`, whose
schema lacked the SR26-01 applicability classifications. Because 0020
is explicitly unpublished draft state, no heuristic preservation is
attempted: a database stamped with the superseded draft identity is
mechanically rejected (recovery refuses the unknown head; alembic
cannot locate the revision) and must be rebuilt from 0019. The r2
identity makes that incompatibility mechanical rather than
documentary.
"""

from alembic import op
import sqlalchemy as sa

revision = "0020_m17c_perf_capture_r2"
down_revision = "0019_m17b_performance_revisions"
branch_labels = None
depends_on = None

_M17C_TABLES = (
    "performance_candidate_vocal_bindings",
    "performance_revision_vocal_bindings",
    "performance_candidate_sync_classifications",
    "performance_revision_sync_classifications",
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


def _classification_table(name: str, parent_col: str, parent_table: str,
                          prefix: str) -> None:
    op.create_table(
        name,
        sa.Column(parent_col, sa.String(36), primary_key=True),
        sa.Column("sync_mode", sa.Text(), nullable=False),
        sa.Column("classification_schema_version", sa.Integer(),
                  nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint("sync_mode IN ('NONE', 'VOCAL_V1')",
                           name=f"ck_{prefix}_mode"),
        sa.CheckConstraint("classification_schema_version = 1",
                           name=f"ck_{prefix}_schema"),
        sa.ForeignKeyConstraint(
            [parent_col], [f"{parent_table}.id"],
            name=f"fk_{prefix}_parent", ondelete="RESTRICT"),
    )


def upgrade() -> None:
    _binding_table(
        "performance_candidate_vocal_bindings",
        "performance_candidate_id", "performance_candidates", "pcvb")
    _binding_table(
        "performance_revision_vocal_bindings",
        "performance_revision_id", "performance_revisions", "prvb")
    # SR26-01 corrective: immutable PF-03 applicability classifications
    # independent of the binding payload, so 'generic M17B' and
    # 'PF-03 companion lost' can never collapse into the same state.
    _classification_table(
        "performance_candidate_sync_classifications",
        "performance_candidate_id", "performance_candidates", "pcsc")
    _classification_table(
        "performance_revision_sync_classifications",
        "performance_revision_id", "performance_revisions", "prsc")

    # Backfill every existing candidate/revision. Bootstrap caveat
    # (recorded in the review register): a database whose bindings were
    # already totally lost before this migration classifies as NONE;
    # the discriminator protects all state created or verified after
    # it lands.
    op.execute(
        "INSERT INTO performance_candidate_sync_classifications "
        "(performance_candidate_id, sync_mode, "
        " classification_schema_version, created_at) "
        "SELECT c.id, CASE WHEN b.performance_candidate_id IS NULL "
        "THEN 'NONE' ELSE 'VOCAL_V1' END, 1, "
        "'1970-01-01T00:00:00.000Z' "
        "FROM performance_candidates c "
        "LEFT JOIN performance_candidate_vocal_bindings b "
        "  ON b.performance_candidate_id = c.id")
    op.execute(
        "INSERT INTO performance_revision_sync_classifications "
        "(performance_revision_id, sync_mode, "
        " classification_schema_version, created_at) "
        "SELECT r.id, CASE WHEN b.performance_revision_id IS NULL "
        "THEN 'NONE' ELSE 'VOCAL_V1' END, 1, "
        "'1970-01-01T00:00:00.000Z' "
        "FROM performance_revisions r "
        "LEFT JOIN performance_revision_vocal_bindings b "
        "  ON b.performance_revision_id = r.id")


def downgrade() -> None:
    conn = op.get_bind()
    for table in _M17C_TABLES:
        n = conn.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar()
        if n:
            raise RuntimeError(
                f"0020 downgrade refused: {table} contains {n} row(s); "
                "M17C dialogue-bound Performance authority is not deleted "
                "by schema downgrade")
    op.drop_table("performance_revision_sync_classifications")
    op.drop_table("performance_candidate_sync_classifications")
    op.drop_table("performance_revision_vocal_bindings")
    op.drop_table("performance_candidate_vocal_bindings")
