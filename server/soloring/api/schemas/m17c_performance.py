"""M17C dialogue-bound Performance API schemas.

Request schemas are closed. Authority integers are strict and constrained to
SQLite's signed 64-bit INTEGER domain; services remain responsible for
canonical rational reduction and cross-row integrity.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from soloring.api.schemas.m17b_performance import ChannelIn, TemporalDomainIn

SQLITE_INT_MIN = -(2**63)
SQLITE_INT_MAX = 2**63 - 1


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RationalIn(_Closed):
    num: StrictInt = Field(ge=SQLITE_INT_MIN, le=SQLITE_INT_MAX)
    den: StrictInt = Field(ge=1, le=SQLITE_INT_MAX)


class SourceProvenanceIn(_Closed):
    schema_version: Literal[1] = 1
    source_kind: Literal[
        "authored",
        "performance_capture",
        "tracking",
        "reconstruction",
        "generated",
        "simulated",
        "procedural",
        "imported",
    ] = "authored"
    producer_id: str = Field(min_length=1, max_length=255)
    producer_version: str = Field(min_length=1, max_length=255)
    source_identity: str | None = Field(default=None, max_length=1024)
    parameters_sha256: str | None = Field(
        default=None, min_length=64, max_length=64)


class VocalBindingIn(_Closed):
    vocal_performance_revision_id: str
    source_start_sample: StrictInt = Field(ge=0, le=SQLITE_INT_MAX)
    source_end_sample_exclusive: StrictInt = Field(ge=1, le=SQLITE_INT_MAX)
    sample_rate_hz: StrictInt = Field(ge=1, le=SQLITE_INT_MAX)
    performance_origin_ms: RationalIn


class DialogueBoundPerformanceCandidateCreate(_Closed):
    performance_kind: Literal["FACIAL", "BODY_FACIAL"]
    performance_profile_id: str
    temporal_domain: TemporalDomainIn
    channels: list[ChannelIn]
    source_provenance: SourceProvenanceIn
    vocal_binding: VocalBindingIn


class VocalBindingRead(BaseModel):
    vocal_performance_revision_id: str
    source_start_sample: int
    source_end_sample_exclusive: int
    sample_rate_hz: int
    performance_origin_ms: dict
    synchronization_basis_version: int
    binding_schema_version: int
    binding_hash: str
    created_at: str
