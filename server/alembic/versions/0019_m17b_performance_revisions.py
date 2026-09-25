"""M17B: performance revisions (frozen R7 §4).

Exactly four additive tables; no predecessor table is altered:
performance_candidates, performance_revisions,
performance_retarget_assessments, performance_retarget_reviews.

Downgrade refuses before DDL when any M17B row exists: M17B identity
intent, adopted authority, retarget assessments and review evidence
are never destroyed as an incidental schema downgrade.
"""

from alembic import op
import sqlalchemy as sa

revision = "0019_m17b_performance_revisions"
down_revision = "0018_m17a_dialogue_vocal_foundation"
branch_labels = None
depends_on = None

_M17B_TABLES = (
    "performance_candidates",
    "performance_revisions",
    "performance_retarget_assessments",
    "performance_retarget_reviews",
)

_SOURCE_KINDS = (
    "'authored','performance_capture','tracking','reconstruction',"
    "'generated','simulated','procedural','imported','retargeted'"
)

_HEX64 = "length({col}) = 64 AND {col} NOT GLOB '*[^0-9a-f]*'"


def _hex_checks(table: str, prefix: str, cols) -> None:
    for col in cols:
        op.create_check_constraint(
            f"ck_{prefix}_{col.split('_')[0]}_hex",
            table,
            _HEX64.format(col=col),
        )


def upgrade() -> None:
    op.create_table(
        "performance_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("subject_id", sa.String(36), nullable=False),
        sa.Column("performance_kind", sa.Text(), nullable=False),
        sa.Column("performance_profile_id", sa.Text(), nullable=False),
        sa.Column("temporal_start_num", sa.Integer(), nullable=False),
        sa.Column("temporal_start_den", sa.Integer(), nullable=False),
        sa.Column("temporal_end_num", sa.Integer(), nullable=False),
        sa.Column("temporal_end_den", sa.Integer(), nullable=False),
        sa.Column("canonical_channel_payload_blob_hash", sa.String(64),
                  nullable=False),
        sa.Column("canonical_channel_payload_sha256", sa.Text(),
                  nullable=False),
        sa.Column("payload_schema_version", sa.Integer(), nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("provenance_schema_version", sa.Integer(),
                  nullable=False),
        sa.Column("provenance_json", sa.Text(), nullable=False),
        sa.Column("provenance_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "performance_kind IN ('BODY','FACIAL','BODY_FACIAL')",
            name="ck_pc_kind"),
        sa.CheckConstraint(
            "performance_profile_id = 'performance-profile/1'",
            name="ck_pc_profile"),
        sa.CheckConstraint("payload_schema_version = 1",
                            name="ck_pc_payload_schema"),
        sa.CheckConstraint("provenance_schema_version = 1",
                            name="ck_pc_provenance_schema"),
        sa.CheckConstraint(
            f"source_kind IN ({_SOURCE_KINDS})",
            name="ck_pc_source_kind"),
        sa.CheckConstraint("temporal_start_den > 0",
                            name="ck_pc_start_den"),
        sa.CheckConstraint("temporal_end_den > 0", name="ck_pc_end_den"),
        sa.CheckConstraint(
            _HEX64.format(col="canonical_channel_payload_blob_hash"),
            name="ck_pc_payload_blob_hash_hex"),
        sa.CheckConstraint(
            _HEX64.format(col="canonical_channel_payload_sha256"),
            name="ck_pc_payload_sha_hex"),
        sa.CheckConstraint(_HEX64.format(col="provenance_hash"),
                           name="ck_pc_provenance_hash_hex"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"],
                                name="fk_pc_project", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["subject_id"], ["creative_entities.id"],
                                name="fk_pc_subject", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["canonical_channel_payload_blob_hash"],
                                ["blobs.hash"],
                                name="fk_pc_payload_blob",
                                ondelete="RESTRICT"),
    )
    op.create_index("ix_pc_subject_created_id", "performance_candidates",
                    ["subject_id", "created_at", "id"])

    op.create_table(
        "performance_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("subject_id", sa.String(36), nullable=False),
        sa.Column("performance_kind", sa.Text(), nullable=False),
        sa.Column("performance_profile_id", sa.Text(), nullable=False),
        sa.Column("temporal_start_num", sa.Integer(), nullable=False),
        sa.Column("temporal_start_den", sa.Integer(), nullable=False),
        sa.Column("temporal_end_num", sa.Integer(), nullable=False),
        sa.Column("temporal_end_den", sa.Integer(), nullable=False),
        sa.Column("canonical_channel_payload_blob_hash", sa.String(64),
                  nullable=False),
        sa.Column("canonical_channel_payload_sha256", sa.Text(),
                  nullable=False),
        sa.Column("payload_schema_version", sa.Integer(), nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("provenance_schema_version", sa.Integer(),
                  nullable=False),
        sa.Column("provenance_json", sa.Text(), nullable=False),
        sa.Column("provenance_hash", sa.Text(), nullable=False),
        sa.Column("adopted_candidate_id", sa.String(36), nullable=False),
        sa.Column("adoption_id", sa.String(36), nullable=False),
        sa.Column("adopted_by", sa.Text(), nullable=False),
        sa.Column("adopted_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "performance_kind IN ('BODY','FACIAL','BODY_FACIAL')",
            name="ck_pr_kind"),
        sa.CheckConstraint(
            "performance_profile_id = 'performance-profile/1'",
            name="ck_pr_profile"),
        sa.CheckConstraint("payload_schema_version = 1",
                            name="ck_pr_payload_schema"),
        sa.CheckConstraint("provenance_schema_version = 1",
                            name="ck_pr_provenance_schema"),
        sa.CheckConstraint(
            f"source_kind IN ({_SOURCE_KINDS})",
            name="ck_pr_source_kind"),
        sa.CheckConstraint("temporal_start_den > 0",
                            name="ck_pr_start_den"),
        sa.CheckConstraint("temporal_end_den > 0", name="ck_pr_end_den"),
        sa.CheckConstraint(
            _HEX64.format(col="canonical_channel_payload_blob_hash"),
            name="ck_pr_payload_blob_hash_hex"),
        sa.CheckConstraint(
            _HEX64.format(col="canonical_channel_payload_sha256"),
            name="ck_pr_payload_sha_hex"),
        sa.CheckConstraint(_HEX64.format(col="provenance_hash"),
                           name="ck_pr_provenance_hash_hex"),
        sa.CheckConstraint("length(trim(adopted_by)) > 0",
                            name="ck_pr_adopted_by_nonempty"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"],
                                name="fk_pr_project", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["subject_id"], ["creative_entities.id"],
                                name="fk_pr_subject", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["canonical_channel_payload_blob_hash"],
                                ["blobs.hash"],
                                name="fk_pr_payload_blob",
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["adopted_candidate_id"],
                                ["performance_candidates.id"],
                                name="fk_pr_candidate", ondelete="RESTRICT"),
        sa.UniqueConstraint("adopted_candidate_id",
                            name="uq_pr_adopted_candidate"),
        sa.UniqueConstraint("adoption_id", name="uq_pr_adoption_id"),
    )
    op.create_index("ix_pr_subject_adopted_id", "performance_revisions",
                    ["subject_id", "adopted_at", "id"])

    op.create_table(
        "performance_retarget_assessments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("performance_revision_id", sa.String(36),
                  nullable=False),
        sa.Column("from_production_revision_id", sa.String(36),
                  nullable=False),
        sa.Column("from_production_revision_hash", sa.Text(),
                  nullable=False),
        sa.Column("to_production_revision_id", sa.String(36),
                  nullable=False),
        sa.Column("to_production_revision_hash", sa.Text(),
                  nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("evaluator_id", sa.Text(), nullable=False),
        sa.Column("evaluator_version", sa.Integer(), nullable=False),
        sa.Column("scope_json", sa.Text(), nullable=False),
        sa.Column("scope_hash", sa.Text(), nullable=False),
        sa.Column("report_json", sa.Text(), nullable=False),
        sa.Column("report_hash", sa.Text(), nullable=False),
        sa.Column("overall_verdict", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint("schema_version = 1", name="ck_pra_schema"),
        sa.CheckConstraint(
            "evaluator_id = 'soloring.performance_physical_retarget'",
            name="ck_pra_evaluator_id"),
        sa.CheckConstraint("evaluator_version = 1",
                            name="ck_pra_evaluator_version"),
        sa.CheckConstraint(
            "overall_verdict IN ('COMPATIBLE_AS_IS',"
            "'COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION',"
            "'REQUIRES_REVIEW','INCOMPATIBLE')",
            name="ck_pra_verdict"),
        sa.CheckConstraint(
            _HEX64.format(col="from_production_revision_hash"),
            name="ck_pra_from_hash_hex"),
        sa.CheckConstraint(
            _HEX64.format(col="to_production_revision_hash"),
            name="ck_pra_to_hash_hex"),
        sa.CheckConstraint(_HEX64.format(col="scope_hash"),
                           name="ck_pra_scope_hash_hex"),
        sa.CheckConstraint(_HEX64.format(col="report_hash"),
                           name="ck_pra_report_hash_hex"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"],
                                name="fk_pra_project", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["performance_revision_id"],
                                ["performance_revisions.id"],
                                name="fk_pra_revision", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["from_production_revision_id"],
                                ["production_revisions.id"],
                                name="fk_pra_from_revision",
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["to_production_revision_id"],
                                ["production_revisions.id"],
                                name="fk_pra_to_revision",
                                ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "performance_revision_id", "from_production_revision_id",
            "to_production_revision_id", "evaluator_id",
            "evaluator_version", "scope_hash",
            name="uq_pra_coordinate"),
    )

    op.create_table(
        "performance_retarget_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("assessment_id", sa.String(36), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "decision IN ('ACCEPT_FOR_NEW_CANDIDATE','REJECT')",
            name="ck_prr_decision"),
        sa.CheckConstraint("length(trim(reviewed_by)) > 0",
                            name="ck_prr_reviewed_by_nonempty"),
        sa.ForeignKeyConstraint(["assessment_id"],
                                ["performance_retarget_assessments.id"],
                                name="fk_prr_assessment",
                                ondelete="RESTRICT"),
    )
    op.create_index("ix_prr_assessment_reviewed_id",
                    "performance_retarget_reviews",
                    ["assessment_id", "reviewed_at", "id"])


def downgrade() -> None:
    conn = op.get_bind()
    for table in _M17B_TABLES:
        n = conn.execute(
            sa.text(f"SELECT COUNT(*) FROM {table}")).scalar()
        if n:
            raise RuntimeError(
                f"0019 downgrade refused: {table} contains {n} row(s); "
                "M17B candidates, adopted Performance authority, retarget "
                "assessments and review evidence are never destroyed as "
                "an incidental schema downgrade")
    op.drop_index("ix_prr_assessment_reviewed_id",
                  table_name="performance_retarget_reviews")
    op.drop_table("performance_retarget_reviews")
    op.drop_table("performance_retarget_assessments")
    op.drop_index("ix_pr_subject_adopted_id",
                  table_name="performance_revisions")
    op.drop_table("performance_revisions")
    op.drop_index("ix_pc_subject_created_id",
                  table_name="performance_candidates")
    op.drop_table("performance_candidates")
