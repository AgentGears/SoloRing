"""ORM metadata registration point (plan §3).

``WorkerLease`` is defined here (M0). The temporal/storage/generation ORM models
live in their domain packages (``domain.models``, ``assets.models``,
``generation.models``) and are imported below so that ``Base.metadata`` is fully
populated for Alembic and ``create_all``. Alembic's ``env.py`` imports this
module to assemble the migration target metadata.
"""

from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from soloring.db.base import Base


class WorkerLease(Base):
    """Singleton worker lease (plan §30).

    ``name``  is the stable singleton role ("generation-worker").
    ``worker_id`` is the ephemeral process incarnation (fresh uuid4 at startup).
    """

    __tablename__ = "worker_leases"

    name: Mapped[str] = mapped_column(String, primary_key=True)
    worker_id: Mapped[str] = mapped_column(Text, nullable=False)
    acquired_at: Mapped[str] = mapped_column(Text, nullable=False)
    heartbeat_at: Mapped[str] = mapped_column(Text, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - diagnostic only
        return (
            f"WorkerLease(name={self.name!r}, worker_id={self.worker_id!r}, "
            f"heartbeat_at={self.heartbeat_at!r})"
        )


# --- Register temporal / storage / generation models on Base.metadata --------
from soloring.domain.models import (  # noqa: E402,F401
    Project,
    Shot,
    ShotReference,
    ShotRevision,
)
from soloring.assets.models import Asset, Blob  # noqa: E402,F401
from soloring.generation.models import (  # noqa: E402,F401
    Generation,
    GenerationInput,
    Take,
)
from soloring.continuity.models import (  # noqa: E402,F401
    CharacterRevisionSpec,
    CostumeRevisionSpec,
    CreativeEntity,
    EntityApprovedRevision,
    EntityRevision,
    LocationRevisionSpec,
    PropRevisionSpec,
    ShotEntityDependency,
    ShotRevisionEntityDependency,
    VehicleRevisionSpec,
)
from soloring.narrative.models import Scene, Sequence  # noqa: E402,F401

__all__ = [
    "WorkerLease",
    "Project",
    "Shot",
    "ShotReference",
    "ShotRevision",
    "Blob",
    "Asset",
    "Generation",
    "GenerationInput",
    "Take",
    "CreativeEntity",
    "EntityRevision",
    "CharacterRevisionSpec",
    "LocationRevisionSpec",
    "PropRevisionSpec",
    "CostumeRevisionSpec",
    "VehicleRevisionSpec",
    "EntityApprovedRevision",
    "Sequence",
    "Scene",
    "ShotEntityDependency",
    "ShotRevisionEntityDependency",
]
