"""m16 intra-shot persistent consequences

Revision ID: 0017_m16_intra_shot_consequences
Revises: 0016_m15_revision_compatibility
Create Date: 2026-09-15

Frozen M16 R6 §7/§20: exactly five additive authority/evidence tables.
No predecessor table is altered or rebuilt; no row is backfilled; no Blob
foreign key is added. Downgrade refuses before DDL when any M16 row exists.
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017_m16_intra_shot_consequences"
down_revision: Union[str, None] = "0016_m15_revision_compatibility"

_M16_TABLES = (
    "shot_intra_shot_event_proposals",
    "shot_intra_shot_events",
    "shot_revision_intra_shot_specs",
    "shot_revision_intra_shot_events",
    "persistent_consequence_reviews",
)

_TARGET_KINDS = "('entity_feature','entity_relation','production_instance_feature')"
_PERSISTENCE = "('transient','require_handoff')"
_EVENT_SOURCE = "('authored','proposal_adoption')"
_PROPOSAL_SOURCE = "('generation','take','imported')"
_PROPOSER = "('human','analyzer')"
_REVIEW_SOURCE = "('event','proposal')"
_REVIEW_DECISIONS = "('adopt_event_only','adopt_persistence','ignore','decline_persistence')"


def _preflight_empty(conn) -> None:
    for table in _M16_TABLES:
        n = conn.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar()
        if n:
            raise RuntimeError(
                f"0017 downgrade refused: {table} contains {n} row(s); "
                "authored/captured M16 state is never destroyed silently")


def upgrade() -> None:
    # Proposal evidence comes first because current event rows may retain its id.
    op.create_table(
        "shot_intra_shot_event_proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("shot_id", sa.String(36), nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("source_shot_revision_id", sa.String(36), nullable=False),
        sa.Column("source_shot_revision_hash", sa.Text(), nullable=False),
        sa.Column("source_generation_id", sa.String(36), nullable=True),
        sa.Column("source_take_id", sa.String(36), nullable=True),
        sa.Column("proposer_kind", sa.Text(), nullable=False),
        sa.Column("analyzer_id", sa.Text(), nullable=True),
        sa.Column("analyzer_version", sa.Text(), nullable=True),
        sa.Column("analyzer_parameters_hash", sa.Text(), nullable=True),
        sa.Column("proposal_json", sa.Text(), nullable=False),
        sa.Column("proposal_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint(f"source_kind IN {_PROPOSAL_SOURCE}",
                           name="ck_sisep_source_kind"),
        sa.CheckConstraint(f"proposer_kind IN {_PROPOSER}",
                           name="ck_sisep_proposer_kind"),
        sa.CheckConstraint("length(source_shot_revision_hash) = 64",
                           name="ck_sisep_revision_hash_len"),
        sa.CheckConstraint("length(proposal_hash) = 64",
                           name="ck_sisep_proposal_hash_len"),
        sa.CheckConstraint(
            "analyzer_parameters_hash IS NULL OR "
            "length(analyzer_parameters_hash) = 64",
            name="ck_sisep_analyzer_hash_len"),
        sa.CheckConstraint(
            "(source_kind = 'generation' AND source_generation_id IS NOT NULL "
            "AND source_take_id IS NULL) OR "
            "(source_kind = 'take' AND source_generation_id IS NOT NULL "
            "AND source_take_id IS NOT NULL) OR "
            "(source_kind = 'imported' AND source_generation_id IS NULL "
            "AND source_take_id IS NULL)",
            name="ck_sisep_source_shape"),
        sa.CheckConstraint(
            "(proposer_kind = 'human' AND analyzer_id IS NULL "
            "AND analyzer_version IS NULL AND analyzer_parameters_hash IS NULL) OR "
            "(proposer_kind = 'analyzer' AND analyzer_id IS NOT NULL "
            "AND analyzer_version IS NOT NULL "
            "AND analyzer_parameters_hash IS NOT NULL)",
            name="ck_sisep_proposer_shape"),
        sa.ForeignKeyConstraint(["shot_id"], ["shots.id"],
                                name="fk_sisep_shot", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_shot_revision_id"],
                                ["shot_revisions.id"],
                                name="fk_sisep_revision", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_generation_id"], ["generations.id"],
                                name="fk_sisep_generation", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_take_id"], ["takes.id"],
                                name="fk_sisep_take", ondelete="RESTRICT"),
    )
    op.create_index("ix_sisep_shot_created", "shot_intra_shot_event_proposals",
                    ["shot_id", "created_at", "id"])

    op.create_table(
        "shot_intra_shot_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("shot_id", sa.String(36), nullable=False),
        sa.Column("time_ms", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("target_kind", sa.Text(), nullable=False),
        sa.Column("entity_feature_id", sa.String(36), nullable=True),
        sa.Column("entity_relation_id", sa.String(36), nullable=True),
        sa.Column("production_instance_feature_id", sa.String(36), nullable=True),
        sa.Column("before_state_json", sa.Text(), nullable=False),
        sa.Column("before_state_hash", sa.Text(), nullable=False),
        sa.Column("after_state_json", sa.Text(), nullable=False),
        sa.Column("after_state_hash", sa.Text(), nullable=False),
        sa.Column("persistence_mode", sa.Text(), nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("source_proposal_id", sa.String(36), nullable=True),
        sa.Column("event_json", sa.Text(), nullable=False),
        sa.Column("event_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.CheckConstraint("time_ms > 0", name="ck_sise_time_positive"),
        sa.CheckConstraint("ordinal >= 0", name="ck_sise_ordinal_nonneg"),
        sa.CheckConstraint(f"target_kind IN {_TARGET_KINDS}",
                           name="ck_sise_target_kind"),
        sa.CheckConstraint(f"persistence_mode IN {_PERSISTENCE}",
                           name="ck_sise_persistence"),
        sa.CheckConstraint(f"source_kind IN {_EVENT_SOURCE}",
                           name="ck_sise_source_kind"),
        sa.CheckConstraint("length(before_state_hash) = 64",
                           name="ck_sise_before_hash_len"),
        sa.CheckConstraint("length(after_state_hash) = 64",
                           name="ck_sise_after_hash_len"),
        sa.CheckConstraint("length(event_hash) = 64",
                           name="ck_sise_event_hash_len"),
        sa.CheckConstraint(
            "(target_kind = 'entity_feature' AND entity_feature_id IS NOT NULL "
            "AND entity_relation_id IS NULL "
            "AND production_instance_feature_id IS NULL) OR "
            "(target_kind = 'entity_relation' AND entity_feature_id IS NULL "
            "AND entity_relation_id IS NOT NULL "
            "AND production_instance_feature_id IS NULL) OR "
            "(target_kind = 'production_instance_feature' "
            "AND entity_feature_id IS NULL AND entity_relation_id IS NULL "
            "AND production_instance_feature_id IS NOT NULL)",
            name="ck_sise_target_xor"),
        sa.CheckConstraint(
            "(source_kind = 'authored' AND source_proposal_id IS NULL) OR "
            "(source_kind = 'proposal_adoption' "
            "AND source_proposal_id IS NOT NULL)",
            name="ck_sise_source_shape"),
        sa.ForeignKeyConstraint(["shot_id"], ["shots.id"],
                                name="fk_sise_shot", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["entity_feature_id"], ["continuity_features.id"],
                                name="fk_sise_entity_feature", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["entity_relation_id"], ["continuity_relations.id"],
                                name="fk_sise_entity_relation", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["production_instance_feature_id"],
                                ["production_instance_features.id"],
                                name="fk_sise_pi_feature", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_proposal_id"],
                                ["shot_intra_shot_event_proposals.id"],
                                name="fk_sise_proposal", ondelete="RESTRICT"),
    )
    op.create_index(
        "uq_sise_active_coordinate", "shot_intra_shot_events",
        ["shot_id", "time_ms", "ordinal"], unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"))
    op.create_index("ix_sise_shot_active", "shot_intra_shot_events",
                    ["shot_id", "deleted_at", "time_ms", "ordinal"])

    op.create_table(
        "shot_revision_intra_shot_specs",
        sa.Column("shot_revision_id", sa.String(36), primary_key=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("spec_json", sa.Text(), nullable=False),
        sa.Column("spec_hash", sa.Text(), nullable=False),
        sa.CheckConstraint("schema_version = 1", name="ck_sriss_schema_version"),
        sa.CheckConstraint("duration_ms > 0", name="ck_sriss_duration_positive"),
        sa.CheckConstraint("length(spec_hash) = 64", name="ck_sriss_hash_len"),
        sa.ForeignKeyConstraint(["shot_revision_id"], ["shot_revisions.id"],
                                name="fk_sriss_revision", ondelete="RESTRICT"),
    )

    op.create_table(
        "shot_revision_intra_shot_events",
        sa.Column("shot_revision_id", sa.String(36), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("source_event_id", sa.String(36), nullable=False),
        sa.Column("time_ms", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("target_kind", sa.Text(), nullable=False),
        sa.Column("captured_target_identity_json", sa.Text(), nullable=False),
        sa.Column("captured_target_identity_hash", sa.Text(), nullable=False),
        sa.Column("captured_before_state_json", sa.Text(), nullable=False),
        sa.Column("captured_before_state_hash", sa.Text(), nullable=False),
        sa.Column("captured_after_state_json", sa.Text(), nullable=False),
        sa.Column("captured_after_state_hash", sa.Text(), nullable=False),
        sa.Column("persistence_mode", sa.Text(), nullable=False),
        sa.Column("event_json", sa.Text(), nullable=False),
        sa.Column("event_hash", sa.Text(), nullable=False),
        sa.Column("entity_feature_transition_id", sa.String(36), nullable=True),
        sa.Column("entity_relation_transition_id", sa.String(36), nullable=True),
        sa.Column("production_instance_feature_transition_id", sa.String(36), nullable=True),
        sa.Column("captured_handoff_json", sa.Text(), nullable=True),
        sa.Column("captured_handoff_hash", sa.Text(), nullable=True),
        sa.Column("source_proposal_id", sa.String(36), nullable=True),
        sa.UniqueConstraint("shot_revision_id", "source_event_id",
                            name="uq_srise_source_event"),
        sa.CheckConstraint("position >= 0", name="ck_srise_position_nonneg"),
        sa.CheckConstraint("time_ms > 0", name="ck_srise_time_positive"),
        sa.CheckConstraint("ordinal >= 0", name="ck_srise_ordinal_nonneg"),
        sa.CheckConstraint(f"target_kind IN {_TARGET_KINDS}",
                           name="ck_srise_target_kind"),
        sa.CheckConstraint(f"persistence_mode IN {_PERSISTENCE}",
                           name="ck_srise_persistence"),
        sa.CheckConstraint("length(captured_target_identity_hash) = 64",
                           name="ck_srise_target_hash_len"),
        sa.CheckConstraint("length(captured_before_state_hash) = 64",
                           name="ck_srise_before_hash_len"),
        sa.CheckConstraint("length(captured_after_state_hash) = 64",
                           name="ck_srise_after_hash_len"),
        sa.CheckConstraint("length(event_hash) = 64", name="ck_srise_event_hash_len"),
        sa.CheckConstraint(
            "captured_handoff_hash IS NULL OR length(captured_handoff_hash) = 64",
            name="ck_srise_handoff_hash_len"),
        sa.CheckConstraint(
            "(persistence_mode = 'transient' "
            "AND entity_feature_transition_id IS NULL "
            "AND entity_relation_transition_id IS NULL "
            "AND production_instance_feature_transition_id IS NULL "
            "AND captured_handoff_json IS NULL AND captured_handoff_hash IS NULL) OR "
            "(persistence_mode = 'require_handoff' "
            "AND ((entity_feature_transition_id IS NOT NULL) + "
            "(entity_relation_transition_id IS NOT NULL) + "
            "(production_instance_feature_transition_id IS NOT NULL)) = 1 "
            "AND captured_handoff_json IS NOT NULL "
            "AND captured_handoff_hash IS NOT NULL)",
            name="ck_srise_handoff_shape"),
        sa.ForeignKeyConstraint(["shot_revision_id"],
                                ["shot_revision_intra_shot_specs.shot_revision_id"],
                                name="fk_srise_spec", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_event_id"], ["shot_intra_shot_events.id"],
                                name="fk_srise_event", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["entity_feature_transition_id"],
                                ["continuity_feature_transitions.id"],
                                name="fk_srise_entity_feature_transition",
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["entity_relation_transition_id"],
                                ["continuity_relation_transitions.id"],
                                name="fk_srise_entity_relation_transition",
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["production_instance_feature_transition_id"],
                                ["production_instance_feature_transitions.id"],
                                name="fk_srise_pi_feature_transition",
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_proposal_id"],
                                ["shot_intra_shot_event_proposals.id"],
                                name="fk_srise_proposal", ondelete="RESTRICT"),
    )

    op.create_table(
        "persistent_consequence_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("shot_id", sa.String(36), nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("source_event_id", sa.String(36), nullable=True),
        sa.Column("source_proposal_id", sa.String(36), nullable=True),
        sa.Column("source_hash", sa.Text(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("review_basis_hash", sa.Text(), nullable=False),
        sa.Column("result_event_id", sa.String(36), nullable=True),
        sa.Column("entity_feature_transition_id", sa.String(36), nullable=True),
        sa.Column("entity_relation_transition_id", sa.String(36), nullable=True),
        sa.Column("production_instance_feature_transition_id", sa.String(36), nullable=True),
        sa.Column("operation_json", sa.Text(), nullable=False),
        sa.Column("operation_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.UniqueConstraint("review_basis_hash", name="uq_pcr_review_basis"),
        sa.CheckConstraint(f"source_kind IN {_REVIEW_SOURCE}",
                           name="ck_pcr_source_kind"),
        sa.CheckConstraint(f"decision IN {_REVIEW_DECISIONS}",
                           name="ck_pcr_decision"),
        sa.CheckConstraint("length(source_hash) = 64", name="ck_pcr_source_hash_len"),
        sa.CheckConstraint("length(review_basis_hash) = 64",
                           name="ck_pcr_basis_hash_len"),
        sa.CheckConstraint("length(operation_hash) = 64",
                           name="ck_pcr_operation_hash_len"),
        sa.CheckConstraint(
            "(source_kind = 'event' AND source_event_id IS NOT NULL "
            "AND source_proposal_id IS NULL "
            "AND decision IN ('adopt_persistence','decline_persistence')) OR "
            "(source_kind = 'proposal' AND source_event_id IS NULL "
            "AND source_proposal_id IS NOT NULL "
            "AND decision IN ('adopt_event_only','adopt_persistence','ignore'))",
            name="ck_pcr_source_decision_shape"),
        sa.CheckConstraint(
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
        sa.ForeignKeyConstraint(["shot_id"], ["shots.id"],
                                name="fk_pcr_shot", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_event_id"], ["shot_intra_shot_events.id"],
                                name="fk_pcr_source_event", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_proposal_id"],
                                ["shot_intra_shot_event_proposals.id"],
                                name="fk_pcr_source_proposal", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["result_event_id"], ["shot_intra_shot_events.id"],
                                name="fk_pcr_result_event", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["entity_feature_transition_id"],
                                ["continuity_feature_transitions.id"],
                                name="fk_pcr_entity_feature_transition",
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["entity_relation_transition_id"],
                                ["continuity_relation_transitions.id"],
                                name="fk_pcr_entity_relation_transition",
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["production_instance_feature_transition_id"],
                                ["production_instance_feature_transitions.id"],
                                name="fk_pcr_pi_feature_transition",
                                ondelete="RESTRICT"),
    )
    op.create_index(
        "uq_pcr_event_source_hash", "persistent_consequence_reviews",
        ["source_event_id", "source_hash"], unique=True,
        sqlite_where=sa.text("source_event_id IS NOT NULL"))
    op.create_index(
        "uq_pcr_proposal_source_hash", "persistent_consequence_reviews",
        ["source_proposal_id", "source_hash"], unique=True,
        sqlite_where=sa.text("source_proposal_id IS NOT NULL"))
    op.create_index("ix_pcr_shot_created", "persistent_consequence_reviews",
                    ["shot_id", "created_at", "id"])


def downgrade() -> None:
    conn = op.get_bind()
    _preflight_empty(conn)
    op.drop_index("ix_pcr_shot_created", table_name="persistent_consequence_reviews")
    op.drop_index("uq_pcr_proposal_source_hash", table_name="persistent_consequence_reviews")
    op.drop_index("uq_pcr_event_source_hash", table_name="persistent_consequence_reviews")
    op.drop_table("persistent_consequence_reviews")
    op.drop_table("shot_revision_intra_shot_events")
    op.drop_table("shot_revision_intra_shot_specs")
    op.drop_index("ix_sise_shot_active", table_name="shot_intra_shot_events")
    op.drop_index("uq_sise_active_coordinate", table_name="shot_intra_shot_events")
    op.drop_table("shot_intra_shot_events")
    op.drop_index("ix_sisep_shot_created", table_name="shot_intra_shot_event_proposals")
    op.drop_table("shot_intra_shot_event_proposals")
