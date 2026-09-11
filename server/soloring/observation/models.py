"""M14 derived-observation provenance models (frozen R2 §22).

Two execution-only tables, structurally disjoint from every authority
table: the convergence-unique artifact row and the composite-FK-bound
Generation input. No Asset or GenerationInput row may ever represent a
ProductionRevision, CompositionRevision, binding, retained Blob,
WorldObservationSpec, or derived observation artifact (§22.3 — the
no-fake-Asset boundary is structural, not just tested).
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
)
from sqlalchemy.orm import Mapped, mapped_column

from soloring.db.base import Base

UUID = String(36)


class DerivedObservationArtifact(Base):
    """Convergence-unique observation.world_depth provenance row.

    The complete semantic coordinate — project, observation spec hash,
    artifact role, materializer identity/version, materializer-contract
    hash, parameters hash — is UNIQUE: identical concurrent publication
    converges; the same coordinate with different bytes is an invariant
    failure, never a silent overwrite.
    """

    __tablename__ = "derived_observation_artifacts"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_derived_observation_artifacts"),
        ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            name="fk_doa_project", ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["blob_hash"], ["blobs.hash"],
            name="fk_doa_blob", ondelete="RESTRICT"),
        UniqueConstraint(
            "project_id", "observation_spec_hash", "artifact_role",
            "materializer_id", "materializer_version",
            "materializer_contract_hash", "parameters_hash",
            name="uq_doa_coordinate"),
        UniqueConstraint("id", "blob_hash",
                         name="uq_doa_id_blob"),
        CheckConstraint(
            "length(observation_spec_hash) = 64",
            name="ck_doa_spec_hash_len"),
        CheckConstraint(
            "artifact_role = 'observation.world_depth'",
            name="ck_doa_role"),
        CheckConstraint("materializer_version > 0",
                        name="ck_doa_materializer_version"),
        CheckConstraint(
            "length(materializer_contract_hash) = 64",
            name="ck_doa_contract_hash_len"),
        CheckConstraint("length(parameters_hash) = 64",
                        name="ck_doa_parameters_hash_len"),
        CheckConstraint("length(provenance_hash) = 64",
                        name="ck_doa_provenance_hash_len"),
        CheckConstraint("length(blob_hash) = 64",
                        name="ck_doa_blob_hash_len"),
        Index("ix_doa_spec", "observation_spec_hash"),
        Index("ix_doa_blob", "blob_hash"),
        Index("ix_doa_coordinate", "project_id",
              "observation_spec_hash", "materializer_contract_hash"),
    )
    id: Mapped[str] = mapped_column(UUID)
    project_id: Mapped[str] = mapped_column(UUID, nullable=False)
    observation_spec_hash: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_role: Mapped[str] = mapped_column(Text, nullable=False)
    materializer_id: Mapped[str] = mapped_column(Text, nullable=False)
    materializer_version: Mapped[int] = mapped_column(Integer, nullable=False)
    materializer_contract_hash: Mapped[str] = mapped_column(
        Text, nullable=False)
    parameters_json: Mapped[str] = mapped_column(Text, nullable=False)
    parameters_hash: Mapped[str] = mapped_column(Text, nullable=False)
    provenance_json: Mapped[str] = mapped_column(Text, nullable=False)
    provenance_hash: Mapped[str] = mapped_column(Text, nullable=False)
    blob_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class GenerationDerivedObservationInput(Base):
    """Immutable historical Generation binding to one exact artifact row
    AND its exact Blob hash through the composite FK (frozen §22.2)."""

    __tablename__ = "generation_derived_observation_inputs"
    __table_args__ = (
        PrimaryKeyConstraint(
            "generation_id", "input_key", "position",
            name="pk_generation_derived_observation_inputs"),
        ForeignKeyConstraint(
            ["generation_id"], ["generations.id"],
            name="fk_gdoi_generation", ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["derived_observation_artifact_id", "blob_hash"],
            ["derived_observation_artifacts.id",
             "derived_observation_artifacts.blob_hash"],
            name="fk_gdoi_artifact", ondelete="RESTRICT"),
        UniqueConstraint("generation_id", "input_key",
                         name="uq_gdoi_generation_input_key"),
        CheckConstraint(
            "artifact_role = 'observation.world_depth'",
            name="ck_gdoi_role"),
        CheckConstraint("position >= 0", name="ck_gdoi_position"),
        CheckConstraint("length(blob_hash) = 64",
                        name="ck_gdoi_blob_hash_len"),
        Index("ix_gdoi_artifact", "derived_observation_artifact_id"),
        Index("ix_gdoi_blob", "blob_hash"),
    )
    generation_id: Mapped[str] = mapped_column(UUID, nullable=False)
    input_key: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact_role: Mapped[str] = mapped_column(Text, nullable=False)
    derived_observation_artifact_id: Mapped[str] = mapped_column(
        UUID, nullable=False)
    blob_hash: Mapped[str] = mapped_column(Text, nullable=False)
