"""M16 intra-Shot consequence ORM tables (frozen R6 §7).

Exactly five additive tables. Current event authority, immutable proposal/review
evidence, and captured schema-7 history remain distinct. No predecessor model
is altered here.
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
_TARGET_KINDS = "('entity_feature','entity_relation','production_instance_feature')"
_PERSISTENCE = "('transient','require_handoff')"
_EVENT_SOURCE = "('authored','proposal_adoption')"
_PROPOSAL_SOURCE = "('generation','take','imported')"
_PROPOSER = "('human','analyzer')"
_REVIEW_SOURCE = "('event','proposal')"
_REVIEW_DECISIONS = "('adopt_event_only','adopt_persistence','ignore','decline_persistence')"


class ShotIntraShotEventProposal(Base):
    __tablename__ = "shot_intra_shot_event_proposals"
    __table_args__ = (
        CheckConstraint(f"source_kind IN {_PROPOSAL_SOURCE}", name="ck_sisep_source_kind"),
        CheckConstraint(f"proposer_kind IN {_PROPOSER}", name="ck_sisep_proposer_kind"),
        CheckConstraint("length(source_shot_revision_hash) = 64",
                        name="ck_sisep_revision_hash_len"),
        CheckConstraint("length(proposal_hash) = 64",
                        name="ck_sisep_proposal_hash_len"),
        CheckConstraint("analyzer_parameters_hash IS NULL OR "
                        "length(analyzer_parameters_hash) = 64",
                        name="ck_sisep_analyzer_hash_len"),
        CheckConstraint(
            "(source_kind = 'generation' AND source_generation_id IS NOT NULL "
            "AND source_take_id IS NULL) OR "
            "(source_kind = 'take' AND source_generation_id IS NOT NULL "
            "AND source_take_id IS NOT NULL) OR "
            "(source_kind = 'imported' AND source_generation_id IS NULL "
            "AND source_take_id IS NULL)", name="ck_sisep_source_shape"),
        CheckConstraint(
            "(proposer_kind = 'human' AND analyzer_id IS NULL "
            "AND analyzer_version IS NULL AND analyzer_parameters_hash IS NULL) OR "
            "(proposer_kind = 'analyzer' AND analyzer_id IS NOT NULL "
            "AND analyzer_version IS NOT NULL "
            "AND analyzer_parameters_hash IS NOT NULL)",
            name="ck_sisep_proposer_shape"),
        ForeignKeyConstraint(["shot_id"], ["shots.id"],
                             name="fk_sisep_shot", ondelete="RESTRICT"),
        ForeignKeyConstraint(["source_shot_revision_id"], ["shot_revisions.id"],
                             name="fk_sisep_revision", ondelete="RESTRICT"),
        ForeignKeyConstraint(["source_generation_id"], ["generations.id"],
                             name="fk_sisep_generation", ondelete="RESTRICT"),
        ForeignKeyConstraint(["source_take_id"], ["takes.id"],
                             name="fk_sisep_take", ondelete="RESTRICT"),
        Index("ix_sisep_shot_created", "shot_id", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    shot_id: Mapped[str] = mapped_column(_UUID, nullable=False)
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    source_shot_revision_id: Mapped[str] = mapped_column(_UUID, nullable=False)
    source_shot_revision_hash: Mapped[str] = mapped_column(Text, nullable=False)
    source_generation_id: Mapped[str | None] = mapped_column(_UUID)
    source_take_id: Mapped[str | None] = mapped_column(_UUID)
    proposer_kind: Mapped[str] = mapped_column(Text, nullable=False)
    analyzer_id: Mapped[str | None] = mapped_column(Text)
    analyzer_version: Mapped[str | None] = mapped_column(Text)
    analyzer_parameters_hash: Mapped[str | None] = mapped_column(Text)
    proposal_json: Mapped[str] = mapped_column(Text, nullable=False)
    proposal_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL))


class ShotIntraShotEvent(Base):
    __tablename__ = "shot_intra_shot_events"
    __table_args__ = (
        CheckConstraint("time_ms > 0", name="ck_sise_time_positive"),
        CheckConstraint("ordinal >= 0", name="ck_sise_ordinal_nonneg"),
        CheckConstraint(f"target_kind IN {_TARGET_KINDS}", name="ck_sise_target_kind"),
        CheckConstraint(f"persistence_mode IN {_PERSISTENCE}", name="ck_sise_persistence"),
        CheckConstraint(f"source_kind IN {_EVENT_SOURCE}", name="ck_sise_source_kind"),
        CheckConstraint("length(before_state_hash) = 64", name="ck_sise_before_hash_len"),
        CheckConstraint("length(after_state_hash) = 64", name="ck_sise_after_hash_len"),
        CheckConstraint("length(event_hash) = 64", name="ck_sise_event_hash_len"),
        CheckConstraint(
            "(target_kind = 'entity_feature' AND entity_feature_id IS NOT NULL "
            "AND entity_relation_id IS NULL AND production_instance_feature_id IS NULL) OR "
            "(target_kind = 'entity_relation' AND entity_feature_id IS NULL "
            "AND entity_relation_id IS NOT NULL AND production_instance_feature_id IS NULL) OR "
            "(target_kind = 'production_instance_feature' "
            "AND entity_feature_id IS NULL AND entity_relation_id IS NULL "
            "AND production_instance_feature_id IS NOT NULL)", name="ck_sise_target_xor"),
        CheckConstraint(
            "(source_kind = 'authored' AND source_proposal_id IS NULL) OR "
            "(source_kind = 'proposal_adoption' AND source_proposal_id IS NOT NULL)",
            name="ck_sise_source_shape"),
        ForeignKeyConstraint(["shot_id"], ["shots.id"],
                             name="fk_sise_shot", ondelete="RESTRICT"),
        ForeignKeyConstraint(["entity_feature_id"], ["continuity_features.id"],
                             name="fk_sise_entity_feature", ondelete="RESTRICT"),
        ForeignKeyConstraint(["entity_relation_id"], ["continuity_relations.id"],
                             name="fk_sise_entity_relation", ondelete="RESTRICT"),
        ForeignKeyConstraint(["production_instance_feature_id"],
                             ["production_instance_features.id"],
                             name="fk_sise_pi_feature", ondelete="RESTRICT"),
        ForeignKeyConstraint(["source_proposal_id"],
                             ["shot_intra_shot_event_proposals.id"],
                             name="fk_sise_proposal", ondelete="RESTRICT"),
        Index("uq_sise_active_coordinate", "shot_id", "time_ms", "ordinal",
              unique=True, sqlite_where=text("deleted_at IS NULL")),
        Index("ix_sise_shot_active", "shot_id", "deleted_at", "time_ms", "ordinal"),
    )

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    shot_id: Mapped[str] = mapped_column(_UUID, nullable=False)
    time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    target_kind: Mapped[str] = mapped_column(Text, nullable=False)
    entity_feature_id: Mapped[str | None] = mapped_column(_UUID)
    entity_relation_id: Mapped[str | None] = mapped_column(_UUID)
    production_instance_feature_id: Mapped[str | None] = mapped_column(_UUID)
    before_state_json: Mapped[str] = mapped_column(Text, nullable=False)
    before_state_hash: Mapped[str] = mapped_column(Text, nullable=False)
    after_state_json: Mapped[str] = mapped_column(Text, nullable=False)
    after_state_hash: Mapped[str] = mapped_column(Text, nullable=False)
    persistence_mode: Mapped[str] = mapped_column(Text, nullable=False)
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    source_proposal_id: Mapped[str | None] = mapped_column(_UUID)
    event_json: Mapped[str] = mapped_column(Text, nullable=False)
    event_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False,
                                            server_default=text(DB_NOW_SQL))
    updated_at: Mapped[str] = mapped_column(Text, nullable=False,
                                            server_default=text(DB_NOW_SQL))
    deleted_at: Mapped[str | None] = mapped_column(Text)


class ShotRevisionIntraShotSpec(Base):
    __tablename__ = "shot_revision_intra_shot_specs"
    __table_args__ = (
        CheckConstraint("schema_version = 1", name="ck_sriss_schema_version"),
        CheckConstraint("duration_ms > 0", name="ck_sriss_duration_positive"),
        CheckConstraint("length(spec_hash) = 64", name="ck_sriss_hash_len"),
        ForeignKeyConstraint(["shot_revision_id"], ["shot_revisions.id"],
                             name="fk_sriss_revision", ondelete="RESTRICT"),
    )

    shot_revision_id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    spec_json: Mapped[str] = mapped_column(Text, nullable=False)
    spec_hash: Mapped[str] = mapped_column(Text, nullable=False)


class ShotRevisionIntraShotEvent(Base):
    __tablename__ = "shot_revision_intra_shot_events"
    __table_args__ = (
        PrimaryKeyConstraint("shot_revision_id", "position",
                             name="pk_srise_revision_position"),
        UniqueConstraint("shot_revision_id", "source_event_id",
                         name="uq_srise_revision_event"),
        CheckConstraint("position >= 0", name="ck_srise_position_nonneg"),
        CheckConstraint("time_ms > 0", name="ck_srise_time_positive"),
        CheckConstraint("ordinal >= 0", name="ck_srise_ordinal_nonneg"),
        CheckConstraint(f"target_kind IN {_TARGET_KINDS}", name="ck_srise_target_kind"),
        CheckConstraint(f"persistence_mode IN {_PERSISTENCE}", name="ck_srise_persistence"),
        CheckConstraint("length(captured_target_identity_hash) = 64",
                        name="ck_srise_target_hash_len"),
        CheckConstraint("length(captured_before_state_hash) = 64",
                        name="ck_srise_before_hash_len"),
        CheckConstraint("length(captured_after_state_hash) = 64",
                        name="ck_srise_after_hash_len"),
        CheckConstraint("length(event_hash) = 64", name="ck_srise_event_hash_len"),
        CheckConstraint("captured_handoff_hash IS NULL OR "
                        "length(captured_handoff_hash) = 64",
                        name="ck_srise_handoff_hash_len"),
        CheckConstraint(
            "(persistence_mode = 'transient' "
            "AND entity_feature_transition_id IS NULL "
            "AND entity_relation_transition_id IS NULL "
            "AND production_instance_feature_transition_id IS NULL "
            "AND captured_handoff_json IS NULL AND captured_handoff_hash IS NULL) OR "
            "(persistence_mode = 'require_handoff' "
            "AND ((entity_feature_transition_id IS NOT NULL) + "
            "(entity_relation_transition_id IS NOT NULL) + "
            "(production_instance_feature_transition_id IS NOT NULL)) = 1 "
            "AND captured_handoff_json IS NOT NULL AND captured_handoff_hash IS NOT NULL)",
            name="ck_srise_handoff_shape"),
        ForeignKeyConstraint(["shot_revision_id"],
                             ["shot_revision_intra_shot_specs.shot_revision_id"],
                             name="fk_srise_spec", ondelete="RESTRICT"),
        ForeignKeyConstraint(["source_event_id"], ["shot_intra_shot_events.id"],
                             name="fk_srise_event", ondelete="RESTRICT"),
        ForeignKeyConstraint(["entity_feature_transition_id"],
                             ["continuity_feature_transitions.id"],
                             name="fk_srise_entity_feature_transition",
                             ondelete="RESTRICT"),
        ForeignKeyConstraint(["entity_relation_transition_id"],
                             ["continuity_relation_transitions.id"],
                             name="fk_srise_entity_relation_transition",
                             ondelete="RESTRICT"),
        ForeignKeyConstraint(["production_instance_feature_transition_id"],
                             ["production_instance_feature_transitions.id"],
                             name="fk_srise_pi_feature_transition",
                             ondelete="RESTRICT"),
        ForeignKeyConstraint(["source_proposal_id"],
                             ["shot_intra_shot_event_proposals.id"],
                             name="fk_srise_proposal", ondelete="RESTRICT"),
    )

    shot_revision_id: Mapped[str] = mapped_column(_UUID, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    source_event_id: Mapped[str] = mapped_column(_UUID, nullable=False)
    time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    target_kind: Mapped[str] = mapped_column(Text, nullable=False)
    captured_target_identity_json: Mapped[str] = mapped_column(Text, nullable=False)
    captured_target_identity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    captured_before_state_json: Mapped[str] = mapped_column(Text, nullable=False)
    captured_before_state_hash: Mapped[str] = mapped_column(Text, nullable=False)
    captured_after_state_json: Mapped[str] = mapped_column(Text, nullable=False)
    captured_after_state_hash: Mapped[str] = mapped_column(Text, nullable=False)
    persistence_mode: Mapped[str] = mapped_column(Text, nullable=False)
    event_json: Mapped[str] = mapped_column(Text, nullable=False)
    event_hash: Mapped[str] = mapped_column(Text, nullable=False)
    entity_feature_transition_id: Mapped[str | None] = mapped_column(_UUID)
    entity_relation_transition_id: Mapped[str | None] = mapped_column(_UUID)
    production_instance_feature_transition_id: Mapped[str | None] = mapped_column(_UUID)
    captured_handoff_json: Mapped[str | None] = mapped_column(Text)
    captured_handoff_hash: Mapped[str | None] = mapped_column(Text)
    source_proposal_id: Mapped[str | None] = mapped_column(_UUID)


class PersistentConsequenceReview(Base):
    __tablename__ = "persistent_consequence_reviews"
    __table_args__ = (
        UniqueConstraint("review_basis_hash", name="uq_pcr_review_basis"),
        CheckConstraint(f"source_kind IN {_REVIEW_SOURCE}", name="ck_pcr_source_kind"),
        CheckConstraint(f"decision IN {_REVIEW_DECISIONS}", name="ck_pcr_decision"),
        CheckConstraint("length(source_hash) = 64", name="ck_pcr_source_hash_len"),
        CheckConstraint("length(review_basis_hash) = 64", name="ck_pcr_basis_hash_len"),
        CheckConstraint("length(operation_hash) = 64", name="ck_pcr_operation_hash_len"),
        CheckConstraint(
            "(source_kind = 'event' AND source_event_id IS NOT NULL "
            "AND source_proposal_id IS NULL "
            "AND decision IN ('adopt_persistence','decline_persistence')) OR "
            "(source_kind = 'proposal' AND source_event_id IS NULL "
            "AND source_proposal_id IS NOT NULL "
            "AND decision IN ('adopt_event_only','adopt_persistence','ignore'))",
            name="ck_pcr_source_decision_shape"),
        CheckConstraint(
            "(decision = 'ignore' AND result_event_id IS NULL "
            "AND entity_feature_transition_id IS NULL "
            "AND entity_relation_transition_id IS NULL "
            "AND production_instance_feature_transition_id IS NULL) OR "
            "(decision IN ('adopt_event_only','decline_persistence') "
            "AND result_event_id IS NOT NULL "
            "AND entity_feature_transition_id IS NULL "
            "AND entity_relation_transition_id IS NULL "
            "AND production_instance_feature_transition_id IS NULL) OR "
            "(decision = 'adopt_persistence' AND result_event_id IS NOT NULL "
            "AND ((entity_feature_transition_id IS NOT NULL) + "
            "(entity_relation_transition_id IS NOT NULL) + "
            "(production_instance_feature_transition_id IS NOT NULL)) = 1)",
            name="ck_pcr_result_shape"),
        ForeignKeyConstraint(["shot_id"], ["shots.id"],
                             name="fk_pcr_shot", ondelete="RESTRICT"),
        ForeignKeyConstraint(["source_event_id"], ["shot_intra_shot_events.id"],
                             name="fk_pcr_source_event", ondelete="RESTRICT"),
        ForeignKeyConstraint(["source_proposal_id"],
                             ["shot_intra_shot_event_proposals.id"],
                             name="fk_pcr_source_proposal", ondelete="RESTRICT"),
        ForeignKeyConstraint(["result_event_id"], ["shot_intra_shot_events.id"],
                             name="fk_pcr_result_event", ondelete="RESTRICT"),
        ForeignKeyConstraint(["entity_feature_transition_id"],
                             ["continuity_feature_transitions.id"],
                             name="fk_pcr_entity_feature_transition",
                             ondelete="RESTRICT"),
        ForeignKeyConstraint(["entity_relation_transition_id"],
                             ["continuity_relation_transitions.id"],
                             name="fk_pcr_entity_relation_transition",
                             ondelete="RESTRICT"),
        ForeignKeyConstraint(["production_instance_feature_transition_id"],
                             ["production_instance_feature_transitions.id"],
                             name="fk_pcr_pi_feature_transition",
                             ondelete="RESTRICT"),
        Index("uq_pcr_event_source_hash", "source_event_id", "source_hash",
              unique=True, sqlite_where=text("source_event_id IS NOT NULL")),
        Index("uq_pcr_proposal_source_hash", "source_proposal_id", "source_hash",
              unique=True, sqlite_where=text("source_proposal_id IS NOT NULL")),
        Index("ix_pcr_shot_created", "shot_id", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    shot_id: Mapped[str] = mapped_column(_UUID, nullable=False)
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    source_event_id: Mapped[str | None] = mapped_column(_UUID)
    source_proposal_id: Mapped[str | None] = mapped_column(_UUID)
    source_hash: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    review_basis_hash: Mapped[str] = mapped_column(Text, nullable=False)
    result_event_id: Mapped[str | None] = mapped_column(_UUID)
    entity_feature_transition_id: Mapped[str | None] = mapped_column(_UUID)
    entity_relation_transition_id: Mapped[str | None] = mapped_column(_UUID)
    production_instance_feature_transition_id: Mapped[str | None] = mapped_column(_UUID)
    operation_json: Mapped[str] = mapped_column(Text, nullable=False)
    operation_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False,
                                            server_default=text(DB_NOW_SQL))
