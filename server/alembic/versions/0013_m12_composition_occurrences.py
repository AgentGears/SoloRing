"""m12 composition occurrences

Revision ID: 0013_m12_composition_occurrences
Revises: 0012_m11_reusable_production_revisions
Create Date: 2026-09-06

Frozen M12 R3 §4: exactly ten additive tables with deterministic
convention-resolved constraint/index names matching ORM metadata exactly.
No predecessor table is rebuilt, widened, or backfilled. No Blob FK is
introduced (recovery's Blob inventory stays seven paths).

Downgrade (§4.12): fail-closed preflight BEFORE any DDL refuses when any of
the ten M12 tables has rows — including authored identity operations with
no published revision. Only a wholly unused 0013 schema may be dropped.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013_m12_composition_occurrences"
down_revision: Union[str, None] = "0012_m11_reusable_production_revisions"

_M12_TABLES = (
    "composition_identity_operation_targets",
    "composition_identity_operation_sources",
    "composition_identity_operations",
    "composition_revision_nested_dependencies",
    "composition_revision_production_dependencies",
    "composition_revision_occurrences",
    "composition_revisions",
    "composition_working_occurrences",
    "composition_occurrences",
    "compositions",
)

_SOURCE_XOR = (
    "(source_kind='production_revision' "
    "AND production_revision_id IS NOT NULL "
    "AND nested_composition_revision_id IS NULL) "
    "OR (source_kind='composition_revision' "
    "AND production_revision_id IS NULL "
    "AND nested_composition_revision_id IS NOT NULL)"
)


def _preflight_clear(conn) -> None:
    for table in _M12_TABLES:
        n = conn.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar()
        if n:
            raise RuntimeError(
                f"0013 downgrade refused: {table} contains {n} row(s); "
                "authored M12 composition/identity state is never destroyed"
            )


def upgrade() -> None:
    op.create_table(
        "compositions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metadata_version", sa.Integer(), nullable=False),
        sa.Column("working_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "length(trim(name)) BETWEEN 1 AND 500", name="name_len"),
        sa.CheckConstraint("metadata_version >= 0", name="metadata_version"),
        sa.CheckConstraint("working_version >= 0", name="working_version"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            name="fk_compositions_project_id_projects", ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_compositions_project_created", "compositions",
        ["project_id", "created_at"])

    op.create_table(
        "composition_occurrences",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("composition_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["composition_id"], ["compositions.id"],
            name="fk_composition_occurrences_composition", ondelete="RESTRICT"),
        sa.UniqueConstraint("id", "composition_id",
                            name="uq_composition_occurrences_id_comp"),
    )
    op.create_index(
        "ix_composition_occurrences_comp_created", "composition_occurrences",
        ["composition_id", "created_at"])

    op.create_table(
        "composition_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("composition_id", sa.String(36), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("snapshot_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint("revision_number >= 1",
                           name="number_pos"),
        sa.CheckConstraint("length(snapshot_hash) = 64",
                           name="hash_len"),
        sa.ForeignKeyConstraint(
            ["composition_id"], ["compositions.id"],
            name="fk_composition_revisions_composition", ondelete="RESTRICT"),
        sa.UniqueConstraint("composition_id", "revision_number",
                            name="uq_composition_revisions_comp_number"),
        sa.UniqueConstraint("composition_id", "snapshot_hash",
                            name="uq_composition_revisions_comp_hash"),
        sa.UniqueConstraint("id", "composition_id",
                            name="uq_composition_revisions_id_comp"),
    )
    op.create_index(
        "ix_composition_revisions_comp_created", "composition_revisions",
        ["composition_id", "created_at"])

    op.create_table(
        "composition_working_occurrences",
        sa.Column("composition_id", sa.String(36), primary_key=True),
        sa.Column("occurrence_id", sa.String(36), primary_key=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("production_revision_id", sa.String(36), nullable=True),
        sa.Column("nested_composition_revision_id", sa.String(36), nullable=True),
        sa.Column("visible", sa.Integer(), nullable=False),
        sa.Column("x_mm", sa.Integer(), nullable=False),
        sa.Column("y_mm", sa.Integer(), nullable=False),
        sa.Column("z_mm", sa.Integer(), nullable=False),
        sa.Column("yaw_udeg", sa.Integer(), nullable=False),
        sa.Column("pitch_udeg", sa.Integer(), nullable=False),
        sa.Column("roll_udeg", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "length(trim(display_name)) BETWEEN 1 AND 500",
            name="display_name_len"),
        sa.CheckConstraint("visible IN (0,1)", name="visible"),
        sa.CheckConstraint(_SOURCE_XOR, name="source_xor"),
        sa.ForeignKeyConstraint(
            ["occurrence_id", "composition_id"],
            ["composition_occurrences.id", "composition_occurrences.composition_id"],
            name="fk_cwo_occurrence", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["production_revision_id"], ["production_revisions.id"],
            name="fk_cwo_production_revision", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["nested_composition_revision_id"], ["composition_revisions.id"],
            name="fk_cwo_nested_revision", ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_cwo_production_revision", "composition_working_occurrences",
        ["production_revision_id"],
        sqlite_where=sa.text("production_revision_id IS NOT NULL"))
    op.create_index(
        "ix_cwo_nested_revision", "composition_working_occurrences",
        ["nested_composition_revision_id"],
        sqlite_where=sa.text("nested_composition_revision_id IS NOT NULL"))

    op.create_table(
        "composition_revision_occurrences",
        sa.Column("composition_revision_id", sa.String(36), primary_key=True),
        sa.Column("composition_id", sa.String(36), nullable=False),
        sa.Column("occurrence_id", sa.String(36), primary_key=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("production_revision_id", sa.String(36), nullable=True),
        sa.Column("nested_composition_revision_id", sa.String(36), nullable=True),
        sa.Column("visible", sa.Integer(), nullable=False),
        sa.Column("x_mm", sa.Integer(), nullable=False),
        sa.Column("y_mm", sa.Integer(), nullable=False),
        sa.Column("z_mm", sa.Integer(), nullable=False),
        sa.Column("yaw_udeg", sa.Integer(), nullable=False),
        sa.Column("pitch_udeg", sa.Integer(), nullable=False),
        sa.Column("roll_udeg", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "length(trim(display_name)) BETWEEN 1 AND 500",
            name="display_name_len"),
        sa.CheckConstraint("visible IN (0,1)", name="visible"),
        sa.CheckConstraint(_SOURCE_XOR, name="source_xor"),
        sa.ForeignKeyConstraint(
            ["composition_revision_id", "composition_id"],
            ["composition_revisions.id", "composition_revisions.composition_id"],
            name="fk_cro_revision", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["occurrence_id", "composition_id"],
            ["composition_occurrences.id", "composition_occurrences.composition_id"],
            name="fk_cro_occurrence", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["production_revision_id"], ["production_revisions.id"],
            name="fk_cro_production_revision", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["nested_composition_revision_id"], ["composition_revisions.id"],
            name="fk_cro_nested_revision", ondelete="RESTRICT"),
    )

    op.create_table(
        "composition_revision_production_dependencies",
        sa.Column("composition_revision_id", sa.String(36), primary_key=True),
        sa.Column("production_revision_id", sa.String(36), primary_key=True),
        sa.ForeignKeyConstraint(
            ["composition_revision_id"], ["composition_revisions.id"],
            name="fk_crpd_revision", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["production_revision_id"], ["production_revisions.id"],
            name="fk_crpd_production_revision", ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_crpd_production_revision",
        "composition_revision_production_dependencies", ["production_revision_id"])

    op.create_table(
        "composition_revision_nested_dependencies",
        sa.Column("composition_revision_id", sa.String(36), primary_key=True),
        sa.Column("nested_composition_revision_id", sa.String(36), primary_key=True),
        sa.CheckConstraint(
            "composition_revision_id <> nested_composition_revision_id",
            name="no_self"),
        sa.ForeignKeyConstraint(
            ["composition_revision_id"], ["composition_revisions.id"],
            name="fk_crnd_revision", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["nested_composition_revision_id"], ["composition_revisions.id"],
            name="fk_crnd_nested_revision", ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_crnd_nested_revision",
        "composition_revision_nested_dependencies", ["nested_composition_revision_id"])

    op.create_table(
        "composition_identity_operations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("composition_id", sa.String(36), nullable=False),
        sa.Column("operation_kind", sa.Text(), nullable=False),
        sa.Column("working_version_before", sa.Integer(), nullable=False),
        sa.Column("working_version_after", sa.Integer(), nullable=False),
        sa.Column("request_fingerprint", sa.Text(), nullable=False),
        sa.Column("impact_fingerprint", sa.Text(), nullable=False),
        sa.Column("operation_json", sa.Text(), nullable=False),
        sa.Column("operation_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "operation_kind IN ('mint','remove','replace_as_new','split','merge','fork')",
            name="operation_kind_domain"),
        sa.CheckConstraint("working_version_before >= 0", name="before_nonneg"),
        sa.CheckConstraint("working_version_after = working_version_before + 1",
                           name="version_step"),
        sa.CheckConstraint("length(request_fingerprint) = 64",
                           name="request_fp_len"),
        sa.CheckConstraint("length(impact_fingerprint) = 64",
                           name="impact_fp_len"),
        sa.CheckConstraint("length(operation_hash) = 64",
                           name="operation_hash_len"),
        sa.ForeignKeyConstraint(
            ["composition_id"], ["compositions.id"],
            name="fk_cio_composition", ondelete="RESTRICT"),
        sa.UniqueConstraint("id", "composition_id", name="uq_cio_id_comp"),
        sa.UniqueConstraint("composition_id", "operation_hash", name="uq_cio_comp_hash"),
        sa.UniqueConstraint("composition_id", "working_version_before",
                            name="uq_cio_comp_before"),
    )

    op.create_table(
        "composition_identity_operation_sources",
        sa.Column("composition_id", sa.String(36), nullable=False),
        sa.Column("operation_id", sa.String(36), primary_key=True),
        sa.Column("occurrence_id", sa.String(36), primary_key=True),
        sa.Column("terminates_identity", sa.Integer(), nullable=False),
        sa.CheckConstraint("terminates_identity IN (0,1)", name="terminates"),
        sa.ForeignKeyConstraint(
            ["operation_id", "composition_id"],
            ["composition_identity_operations.id",
             "composition_identity_operations.composition_id"],
            name="fk_cios_operation", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["occurrence_id", "composition_id"],
            ["composition_occurrences.id", "composition_occurrences.composition_id"],
            name="fk_cios_occurrence", ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_cios_occurrence", "composition_identity_operation_sources",
        ["occurrence_id"])
    op.create_index(
        "uq_cios_terminating_occurrence", "composition_identity_operation_sources",
        ["occurrence_id"], unique=True,
        sqlite_where=sa.text("terminates_identity = 1"))

    op.create_table(
        "composition_identity_operation_targets",
        sa.Column("composition_id", sa.String(36), nullable=False),
        sa.Column("operation_id", sa.String(36), primary_key=True),
        sa.Column("occurrence_id", sa.String(36), primary_key=True),
        sa.ForeignKeyConstraint(
            ["operation_id", "composition_id"],
            ["composition_identity_operations.id",
             "composition_identity_operations.composition_id"],
            name="fk_ciot_operation", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["occurrence_id", "composition_id"],
            ["composition_occurrences.id", "composition_occurrences.composition_id"],
            name="fk_ciot_occurrence", ondelete="RESTRICT"),
        sa.UniqueConstraint("occurrence_id", name="uq_ciot_occurrence"),
    )
    op.create_index(
        "ix_ciot_occurrence", "composition_identity_operation_targets",
        ["occurrence_id"])


def downgrade() -> None:
    conn = op.get_bind()
    _preflight_clear(conn)
    op.drop_table("composition_identity_operation_targets")
    op.drop_table("composition_identity_operation_sources")
    op.drop_table("composition_identity_operations")
    op.drop_table("composition_revision_nested_dependencies")
    op.drop_table("composition_revision_production_dependencies")
    op.drop_table("composition_revision_occurrences")
    op.drop_table("composition_working_occurrences")
    op.drop_table("composition_revisions")
    op.drop_table("composition_occurrences")
    op.drop_table("compositions")
