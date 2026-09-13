"""M15 compatibility ORM tables (frozen R4 §11).

Exactly five additive tables; no predecessor table is altered. All
parent pins are RESTRICT; composite pins bind children to the exact
assessment report/operation identity they were derived from.
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from soloring.db.base import Base
from soloring.db.timeutil import DB_NOW_SQL

_UUID = String(36)

_FOUR_VERDICTS = (
    "('COMPATIBLE_AS_IS',"
    " 'COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION',"
    " 'REQUIRES_REVIEW',"
    " 'INCOMPATIBLE')"
)


class ProductionCompatibilityAssessment(Base):
    """Immutable consumer-specific compatibility evidence parent (§11.1)."""

    __tablename__ = "production_compatibility_assessments"
    __table_args__ = (
        CheckConstraint("schema_version = 1", name="schema_version"),
        CheckConstraint(
            "evaluator_id = 'soloring.production_revision_compatibility'",
            name="ck_pca_evaluator"),
        CheckConstraint("evaluator_version = 1", name="ck_pca_evaluator_v"),
        CheckConstraint("length(from_revision_hash) = 64",
                        name="ck_pca_from_hash_len"),
        CheckConstraint("length(to_revision_hash) = 64",
                        name="ck_pca_to_hash_len"),
        CheckConstraint("length(scope_hash) = 64", name="ck_pca_scope_len"),
        CheckConstraint("length(report_hash) = 64",
                        name="ck_pca_report_len"),
        CheckConstraint(f"overall_verdict IN {_FOUR_VERDICTS}",
                        name="ck_pca_verdict_domain"),
        ForeignKeyConstraint(["project_id"], ["projects.id"],
                             name="fk_pca_project", ondelete="RESTRICT"),
        ForeignKeyConstraint(["production_object_id"],
                             ["production_objects.id"],
                             name="fk_pca_object", ondelete="RESTRICT"),
        ForeignKeyConstraint(["from_revision_id"], ["production_revisions.id"],
                             name="fk_pca_from", ondelete="RESTRICT"),
        ForeignKeyConstraint(["to_revision_id"], ["production_revisions.id"],
                             name="fk_pca_to", ondelete="RESTRICT"),
        UniqueConstraint(
            "project_id", "from_revision_id", "to_revision_id",
            "evaluator_id", "evaluator_version", "scope_hash",
            name="uq_pca_coordinate"),
        UniqueConstraint("id", "report_hash", name="uq_pca_id_report"),
        Index("ix_pca_object_created", "production_object_id", "created_at"),
        Index("ix_pca_pair", "from_revision_id", "to_revision_id"),
        Index("ix_pca_verdict", "overall_verdict"),
    )

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    project_id: Mapped[str] = mapped_column(_UUID, nullable=False)
    production_object_id: Mapped[str] = mapped_column(_UUID, nullable=False)
    from_revision_id: Mapped[str] = mapped_column(_UUID, nullable=False)
    from_revision_hash: Mapped[str] = mapped_column(Text, nullable=False)
    to_revision_id: Mapped[str] = mapped_column(_UUID, nullable=False)
    to_revision_hash: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluator_id: Mapped[str] = mapped_column(Text, nullable=False)
    evaluator_version: Mapped[int] = mapped_column(Integer, nullable=False)
    scope_json: Mapped[str] = mapped_column(Text, nullable=False)
    scope_hash: Mapped[str] = mapped_column(Text, nullable=False)
    report_json: Mapped[str] = mapped_column(Text, nullable=False)
    report_hash: Mapped[str] = mapped_column(Text, nullable=False)
    overall_verdict: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL))


class ProductionCompatibilityUse(Base):
    """One direct current working use with its exact consumer contract
    (§11.2). Translator fields are controlled by the dimension result,
    never the folded verdict."""

    __tablename__ = "production_compatibility_uses"
    __table_args__ = (
        PrimaryKeyConstraint("assessment_id", "position",
                             name="pk_production_compatibility_uses"),
        CheckConstraint("position >= 0", name="ck_pcu_position"),
        CheckConstraint("composition_working_version >= 0",
                        name="ck_pcu_working_version"),
        CheckConstraint("length(use_contract_hash) = 64",
                        name="ck_pcu_contract_len"),
        CheckConstraint("length(dimension_results_hash) = 64",
                        name="ck_pcu_dimensions_len"),
        CheckConstraint(f"verdict IN {_FOUR_VERDICTS}",
                        name="ck_pcu_verdict_domain"),
        CheckConstraint(
            "length(translator_parameters_hash) = 64 "
            "OR translator_parameters_hash IS NULL",
            name="ck_pcu_translator_params_len"),
        CheckConstraint(
            "length(translator_output_hash) = 64 "
            "OR translator_output_hash IS NULL",
            name="ck_pcu_translator_output_len"),
        ForeignKeyConstraint(
            ["assessment_id"],
            ["production_compatibility_assessments.id"],
            name="fk_pcu_assessment", ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["occurrence_id", "composition_id"],
            ["composition_occurrences.id", "composition_occurrences.composition_id"],
            name="fk_pcu_occurrence", ondelete="RESTRICT"),
        UniqueConstraint("assessment_id", "composition_id", "occurrence_id",
                         name="uq_pcu_use"),
        Index("ix_pcu_occurrence", "composition_id", "occurrence_id"),
    )

    assessment_id: Mapped[str] = mapped_column(_UUID, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    composition_id: Mapped[str] = mapped_column(_UUID, nullable=False)
    occurrence_id: Mapped[str] = mapped_column(_UUID, nullable=False)
    composition_working_version: Mapped[int] = mapped_column(
        Integer, nullable=False)
    use_contract_json: Mapped[str] = mapped_column(Text, nullable=False)
    use_contract_hash: Mapped[str] = mapped_column(Text, nullable=False)
    dimension_results_json: Mapped[str] = mapped_column(
        Text, nullable=False)
    dimension_results_hash: Mapped[str] = mapped_column(
        Text, nullable=False)
    verdict: Mapped[str] = mapped_column(Text, nullable=False)
    translator_id: Mapped[str | None] = mapped_column(Text)
    translator_version: Mapped[int | None] = mapped_column(Integer)
    translator_parameters_json: Mapped[str | None] = mapped_column(Text)
    translator_parameters_hash: Mapped[str | None] = mapped_column(Text)
    translator_output_hash: Mapped[str | None] = mapped_column(Text)


class CompositionOccurrenceRevisionTracking(Base):
    """Current-authoring tracking policy (§11.3); absence = PINNED/v0."""

    __tablename__ = "composition_occurrence_revision_tracking"
    __table_args__ = (
        PrimaryKeyConstraint("composition_id", "occurrence_id",
                             name="pk_composition_occurrence_revision_tracking"),
        CheckConstraint("mode IN ('PINNED', 'TRACK_COMPATIBLE')",
                        name="ck_cort_mode"),
        CheckConstraint("policy_version >= 1", name="ck_cort_version"),
        ForeignKeyConstraint(
            ["occurrence_id", "composition_id"],
            ["composition_occurrences.id", "composition_occurrences.composition_id"],
            name="fk_cort_occurrence", ondelete="RESTRICT"),
    )

    composition_id: Mapped[str] = mapped_column(_UUID, nullable=False)
    occurrence_id: Mapped[str] = mapped_column(_UUID, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL))
    updated_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL))


class ProductionUpdateOperation(Base):
    """Immutable applied-update audit parent (§11.4); the composite FK
    mechanically binds the exact assessment report hash."""

    __tablename__ = "production_update_operations"
    __table_args__ = (
        CheckConstraint("schema_version = 1", name="schema_version"),
        CheckConstraint("length(assessment_report_hash) = 64",
                        name="ck_puo_report_len"),
        CheckConstraint("length(operation_hash) = 64",
                        name="ck_puo_operation_len"),
        ForeignKeyConstraint(["project_id"], ["projects.id"],
                             name="fk_puo_project", ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["assessment_id", "assessment_report_hash"],
            ["production_compatibility_assessments.id",
             "production_compatibility_assessments.report_hash"],
            name="fk_puo_assessment_report", ondelete="RESTRICT"),
        UniqueConstraint("assessment_id", "operation_hash",
                         name="uq_puo_assessment_operation"),
        UniqueConstraint("id", "assessment_id", name="uq_puo_id_assessment"),
    )

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    project_id: Mapped[str] = mapped_column(_UUID, nullable=False)
    assessment_id: Mapped[str] = mapped_column(_UUID, nullable=False)
    assessment_report_hash: Mapped[str] = mapped_column(
        Text, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    operation_json: Mapped[str] = mapped_column(Text, nullable=False)
    operation_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL))


class ProductionUpdateItem(Base):
    """One applied selected use with frozen before/after snapshots
    (§11.5)."""

    __tablename__ = "production_update_items"
    __table_args__ = (
        PrimaryKeyConstraint("operation_id", "position",
                             name="pk_production_update_items"),
        CheckConstraint("position >= 0", name="ck_pui_position"),
        CheckConstraint("assessment_use_position >= 0",
                        name="ck_pui_use_position"),
        CheckConstraint(f"verdict IN {_FOUR_VERDICTS}",
                        name="ck_pui_verdict_domain"),
        CheckConstraint("review_accepted IN (0,1)",
                        name="ck_pui_review_accepted"),
        CheckConstraint(
            "length(translator_parameters_hash) = 64 "
            "OR translator_parameters_hash IS NULL",
            name="ck_pui_translator_params_len"),
        CheckConstraint(
            "length(translator_output_hash) = 64 "
            "OR translator_output_hash IS NULL",
            name="ck_pui_translator_output_len"),
        CheckConstraint("working_version_before >= 0",
                        name="ck_pui_before"),
        CheckConstraint("working_version_after >= 1",
                        name="ck_pui_after"),
        CheckConstraint("length(before_spec_hash) = 64",
                        name="ck_pui_before_spec_len"),
        CheckConstraint("length(after_spec_hash) = 64",
                        name="ck_pui_after_spec_len"),
        ForeignKeyConstraint(
            ["operation_id", "assessment_id"],
            ["production_update_operations.id",
             "production_update_operations.assessment_id"],
            name="fk_pui_operation", ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["assessment_id", "assessment_use_position"],
            ["production_compatibility_uses.assessment_id",
             "production_compatibility_uses.position"],
            name="fk_pui_use", ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["occurrence_id", "composition_id"],
            ["composition_occurrences.id", "composition_occurrences.composition_id"],
            name="fk_pui_occurrence", ondelete="RESTRICT"),
        ForeignKeyConstraint(["from_revision_id"], ["production_revisions.id"],
                             name="fk_pui_from", ondelete="RESTRICT"),
        ForeignKeyConstraint(["to_revision_id"], ["production_revisions.id"],
                             name="fk_pui_to", ondelete="RESTRICT"),
        UniqueConstraint("operation_id", "composition_id", "occurrence_id",
                         name="uq_pui_use"),
    )

    operation_id: Mapped[str] = mapped_column(_UUID, nullable=False)
    assessment_id: Mapped[str] = mapped_column(_UUID, nullable=False)
    assessment_use_position: Mapped[int] = mapped_column(
        Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    composition_id: Mapped[str] = mapped_column(_UUID, nullable=False)
    occurrence_id: Mapped[str] = mapped_column(_UUID, nullable=False)
    from_revision_id: Mapped[str] = mapped_column(_UUID, nullable=False)
    to_revision_id: Mapped[str] = mapped_column(_UUID, nullable=False)
    verdict: Mapped[str] = mapped_column(Text, nullable=False)
    review_accepted: Mapped[int] = mapped_column(Integer, nullable=False)
    translator_id: Mapped[str | None] = mapped_column(Text)
    translator_version: Mapped[int | None] = mapped_column(Integer)
    translator_parameters_hash: Mapped[str | None] = mapped_column(Text)
    translator_output_hash: Mapped[str | None] = mapped_column(Text)
    working_version_before: Mapped[int] = mapped_column(
        Integer, nullable=False)
    working_version_after: Mapped[int] = mapped_column(
        Integer, nullable=False)
    before_spec_hash: Mapped[str] = mapped_column(Text, nullable=False)
    after_spec_hash: Mapped[str] = mapped_column(Text, nullable=False)
