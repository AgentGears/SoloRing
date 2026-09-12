"""m15 revision compatibility

Revision ID: 0016_m15_revision_compatibility
Revises: 0015_m14_world_observation_execution
Create Date: 2026-09-12

Frozen R4 §11: exactly five additive tables — compatibility
assessments/uses, occurrence revision tracking, update
operations/items. No predecessor table is altered or rebuilt; no
decision is backfilled; no Blob foreign key is introduced.

Downgrade (§11.6): fail-closed preflight BEFORE any DDL refuses when
ANY row exists in ANY M15 table; when all five are empty they are
dropped in FK-safe child-first order.
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016_m15_revision_compatibility"
down_revision: Union[str, None] = "0015_m14_world_observation_execution"

_M15_TABLES = (
    "production_compatibility_assessments",
    "production_compatibility_uses",
    "composition_occurrence_revision_tracking",
    "production_update_operations",
    "production_update_items",
)

_FOUR_VERDICTS = (
    "('COMPATIBLE_AS_IS',"
    " 'COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION',"
    " 'REQUIRES_REVIEW',"
    " 'INCOMPATIBLE')"
)


def _preflight_empty(conn) -> None:
    for table in _M15_TABLES:
        n = conn.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar()
        if n:
            raise RuntimeError(
                f"0016 downgrade refused: {table} contains {n} row(s); "
                "authored M15 state is never destroyed silently")


def upgrade() -> None:
    op.create_table(
        "production_compatibility_assessments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("production_object_id", sa.String(36), nullable=False),
        sa.Column("from_revision_id", sa.String(36), nullable=False),
        sa.Column("from_revision_hash", sa.Text(), nullable=False),
        sa.Column("to_revision_id", sa.String(36), nullable=False),
        sa.Column("to_revision_hash", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("evaluator_id", sa.Text(), nullable=False),
        sa.Column("evaluator_version", sa.Integer(), nullable=False),
        sa.Column("scope_json", sa.Text(), nullable=False),
        sa.Column("scope_hash", sa.Text(), nullable=False),
        sa.Column("report_json", sa.Text(), nullable=False),
        sa.Column("report_hash", sa.Text(), nullable=False),
        sa.Column("overall_verdict", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint("schema_version = 1", name="schema_version"),
        sa.CheckConstraint(
            "evaluator_id = 'soloring.production_revision_compatibility'",
            name="ck_pca_evaluator"),
        sa.CheckConstraint("evaluator_version = 1",
                           name="ck_pca_evaluator_v"),
        sa.CheckConstraint("length(from_revision_hash) = 64",
                           name="ck_pca_from_hash_len"),
        sa.CheckConstraint("length(to_revision_hash) = 64",
                           name="ck_pca_to_hash_len"),
        sa.CheckConstraint("length(scope_hash) = 64",
                           name="ck_pca_scope_len"),
        sa.CheckConstraint("length(report_hash) = 64",
                           name="ck_pca_report_len"),
        sa.CheckConstraint(f"overall_verdict IN {_FOUR_VERDICTS}",
                           name="ck_pca_verdict_domain"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"],
                                name="fk_pca_project", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["production_object_id"],
                                ["production_objects.id"],
                                name="fk_pca_object", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["from_revision_id"],
                                ["production_revisions.id"],
                                name="fk_pca_from", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["to_revision_id"],
                                ["production_revisions.id"],
                                name="fk_pca_to", ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "project_id", "from_revision_id", "to_revision_id",
            "evaluator_id", "evaluator_version", "scope_hash",
            name="uq_pca_coordinate"),
        sa.UniqueConstraint("id", "report_hash", name="uq_pca_id_report"),
    )
    op.create_index("ix_pca_object_created",
                    "production_compatibility_assessments",
                    ["production_object_id", "created_at"])
    op.create_index("ix_pca_pair",
                    "production_compatibility_assessments",
                    ["from_revision_id", "to_revision_id"])
    op.create_index("ix_pca_verdict",
                    "production_compatibility_assessments",
                    ["overall_verdict"])

    op.create_table(
        "production_compatibility_uses",
        sa.Column("assessment_id", sa.String(36), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("composition_id", sa.String(36), nullable=False),
        sa.Column("occurrence_id", sa.String(36), nullable=False),
        sa.Column("composition_working_version", sa.Integer(),
                  nullable=False),
        sa.Column("use_contract_json", sa.Text(), nullable=False),
        sa.Column("use_contract_hash", sa.Text(), nullable=False),
        sa.Column("dimension_results_json", sa.Text(), nullable=False),
        sa.Column("dimension_results_hash", sa.Text(), nullable=False),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column("translator_id", sa.Text(), nullable=True),
        sa.Column("translator_version", sa.Integer(), nullable=True),
        sa.Column("translator_parameters_json", sa.Text(), nullable=True),
        sa.Column("translator_parameters_hash", sa.Text(), nullable=True),
        sa.Column("translator_output_hash", sa.Text(), nullable=True),
        sa.CheckConstraint("position >= 0", name="ck_pcu_position"),
        sa.CheckConstraint("composition_working_version >= 0",
                           name="ck_pcu_working_version"),
        sa.CheckConstraint("length(use_contract_hash) = 64",
                           name="ck_pcu_contract_len"),
        sa.CheckConstraint("length(dimension_results_hash) = 64",
                           name="ck_pcu_dimensions_len"),
        sa.CheckConstraint(f"verdict IN {_FOUR_VERDICTS}",
                           name="ck_pcu_verdict_domain"),
        sa.CheckConstraint(
            "length(translator_parameters_hash) = 64 "
            "OR translator_parameters_hash IS NULL",
            name="ck_pcu_translator_params_len"),
        sa.CheckConstraint(
            "length(translator_output_hash) = 64 "
            "OR translator_output_hash IS NULL",
            name="ck_pcu_translator_output_len"),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["production_compatibility_assessments.id"],
            name="fk_pcu_assessment", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["occurrence_id", "composition_id"],
            ["composition_occurrences.id",
             "composition_occurrences.composition_id"],
            name="fk_pcu_occurrence", ondelete="RESTRICT"),
        sa.UniqueConstraint("assessment_id", "composition_id",
                            "occurrence_id", name="uq_pcu_use"),
    )
    op.create_index("ix_pcu_occurrence", "production_compatibility_uses",
                    ["composition_id", "occurrence_id"])

    op.create_table(
        "composition_occurrence_revision_tracking",
        sa.Column("composition_id", sa.String(36), primary_key=True),
        sa.Column("occurrence_id", sa.String(36), primary_key=True),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint("mode IN ('PINNED', 'TRACK_COMPATIBLE')",
                           name="ck_cort_mode"),
        sa.CheckConstraint("policy_version >= 1", name="ck_cort_version"),
        sa.ForeignKeyConstraint(
            ["occurrence_id", "composition_id"],
            ["composition_occurrences.id",
             "composition_occurrences.composition_id"],
            name="fk_cort_occurrence", ondelete="RESTRICT"),
    )

    op.create_table(
        "production_update_operations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("assessment_id", sa.String(36), nullable=False),
        sa.Column("assessment_report_hash", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("operation_json", sa.Text(), nullable=False),
        sa.Column("operation_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint("schema_version = 1", name="schema_version"),
        sa.CheckConstraint("length(assessment_report_hash) = 64",
                           name="ck_puo_report_len"),
        sa.CheckConstraint("length(operation_hash) = 64",
                           name="ck_puo_operation_len"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"],
                                name="fk_puo_project", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["assessment_id", "assessment_report_hash"],
            ["production_compatibility_assessments.id",
             "production_compatibility_assessments.report_hash"],
            name="fk_puo_assessment_report", ondelete="RESTRICT"),
        sa.UniqueConstraint("assessment_id", "operation_hash",
                            name="uq_puo_assessment_operation"),
        sa.UniqueConstraint("id", "assessment_id",
                            name="uq_puo_id_assessment"),
    )

    op.create_table(
        "production_update_items",
        sa.Column("operation_id", sa.String(36), primary_key=True),
        sa.Column("assessment_id", sa.String(36), nullable=False),
        sa.Column("assessment_use_position", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("composition_id", sa.String(36), nullable=False),
        sa.Column("occurrence_id", sa.String(36), nullable=False),
        sa.Column("from_revision_id", sa.String(36), nullable=False),
        sa.Column("to_revision_id", sa.String(36), nullable=False),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column("review_accepted", sa.Integer(), nullable=False),
        sa.Column("translator_id", sa.Text(), nullable=True),
        sa.Column("translator_version", sa.Integer(), nullable=True),
        sa.Column("translator_parameters_hash", sa.Text(), nullable=True),
        sa.Column("translator_output_hash", sa.Text(), nullable=True),
        sa.Column("working_version_before", sa.Integer(), nullable=False),
        sa.Column("working_version_after", sa.Integer(), nullable=False),
        sa.Column("before_spec_hash", sa.Text(), nullable=False),
        sa.Column("after_spec_hash", sa.Text(), nullable=False),
        sa.CheckConstraint("position >= 0", name="ck_pui_position"),
        sa.CheckConstraint("assessment_use_position >= 0",
                           name="ck_pui_use_position"),
        sa.CheckConstraint(f"verdict IN {_FOUR_VERDICTS}",
                           name="ck_pui_verdict_domain"),
        sa.CheckConstraint("review_accepted IN (0,1)",
                           name="ck_pui_review_accepted"),
        sa.CheckConstraint(
            "length(translator_parameters_hash) = 64 "
            "OR translator_parameters_hash IS NULL",
            name="ck_pui_translator_params_len"),
        sa.CheckConstraint(
            "length(translator_output_hash) = 64 "
            "OR translator_output_hash IS NULL",
            name="ck_pui_translator_output_len"),
        sa.CheckConstraint("working_version_before >= 0",
                           name="ck_pui_before"),
        sa.CheckConstraint("working_version_after >= 1",
                           name="ck_pui_after"),
        sa.CheckConstraint("length(before_spec_hash) = 64",
                           name="ck_pui_before_spec_len"),
        sa.CheckConstraint("length(after_spec_hash) = 64",
                           name="ck_pui_after_spec_len"),
        sa.ForeignKeyConstraint(
            ["operation_id", "assessment_id"],
            ["production_update_operations.id",
             "production_update_operations.assessment_id"],
            name="fk_pui_operation", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["assessment_id", "assessment_use_position"],
            ["production_compatibility_uses.assessment_id",
             "production_compatibility_uses.position"],
            name="fk_pui_use", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["occurrence_id", "composition_id"],
            ["composition_occurrences.id",
             "composition_occurrences.composition_id"],
            name="fk_pui_occurrence", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["from_revision_id"],
                                ["production_revisions.id"],
                                name="fk_pui_from", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["to_revision_id"],
                                ["production_revisions.id"],
                                name="fk_pui_to", ondelete="RESTRICT"),
        sa.UniqueConstraint("operation_id", "composition_id",
                            "occurrence_id", name="uq_pui_use"),
    )


def downgrade() -> None:
    conn = op.get_bind()
    _preflight_empty(conn)
    op.drop_table("production_update_items")
    op.drop_table("production_update_operations")
    op.drop_table("composition_occurrence_revision_tracking")
    op.drop_index("ix_pcu_occurrence",
                  table_name="production_compatibility_uses")
    op.drop_table("production_compatibility_uses")
    op.drop_index("ix_pca_verdict",
                  table_name="production_compatibility_assessments")
    op.drop_index("ix_pca_pair",
                  table_name="production_compatibility_assessments")
    op.drop_index("ix_pca_object_created",
                  table_name="production_compatibility_assessments")
    op.drop_table("production_compatibility_assessments")
