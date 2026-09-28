"""M17C PF-03 dialogue-bound vocal/facial synchronization services.

M17C is additive to the published M17B Performance authority. Generic M17B
candidates/revisions remain lawful without a binding. Dialogue-bound creation
adds one immutable candidate companion; adoption and retargeting copy that
semantic closure exactly into successor companion rows.
"""

from __future__ import annotations

import hashlib
import json
from fractions import Fraction

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.domain.now import db_now
from soloring.errors import ErrorCode, SoloRingError, not_found
from soloring.performance import revision as revision_svc
from soloring.performance.m17c_contract import (
    ADMISSION,
    BINDING_FIELDS,
    HISTORICAL,
    PERFORMANCE_REQUIRED_ARTICULATION_MISSING,
    PERFORMANCE_VOCAL_ALIGNMENT_MISMATCH,
    PERFORMANCE_VOCAL_BINDING_INVALID,
    PERFORMANCE_VOCAL_BINDING_NOT_FOUND,
    PERFORMANCE_VOCAL_INTERVAL_INVALID,
    PERFORMANCE_VOCAL_PROJECT_MISMATCH,
    PERFORMANCE_VOCAL_SUBJECT_MISMATCH,
    REQUIRED_ARTICULATION,
    corrupt,
    invalid,
    strict_int,
)
from soloring.performance.m17c_models import (
    PerformanceCandidateSyncClassification,
    PerformanceCandidateVocalBinding,
    PerformanceRevisionSyncClassification,
    PerformanceRevisionVocalBinding,
)
from soloring.performance.models import (
    DialogueAlignment,
    DialogueLine,
    DialogueLineRevision,
    PerformanceCandidate,
    PerformanceRevision,
    VocalCandidate,
    VocalPerformanceRevision,
)
from soloring.performance.temporal import canonical_rational

_BINDING_INPUT_KEYS = {
    "vocal_performance_revision_id",
    "source_start_sample",
    "source_end_sample_exclusive",
    "sample_rate_hz",
    "performance_origin_ms",
}
_ORIGIN_KEYS = {"num", "den"}
_VOCAL_COPY_FIELDS = (
    "dialogue_line_revision_id",
    "retained_audio_blob_hash",
    "native_sample_rate_hz",
    "retained_sample_count",
    "trim_start_sample",
    "trim_end_sample_exclusive",
    "source_kind",
    "provenance_schema_version",
    "provenance_json",
    "provenance_hash",
)


def _binding_document(raw: dict) -> tuple[dict, tuple[int, int]]:
    if not isinstance(raw, dict) or set(raw) != _BINDING_INPUT_KEYS:
        got = sorted(raw) if isinstance(raw, dict) else type(raw).__name__
        raise invalid(
            PERFORMANCE_VOCAL_BINDING_INVALID,
            "vocal_binding keys must be exactly "
            f"{sorted(_BINDING_INPUT_KEYS)} (got {got!r})",
        )
    vp_id = raw["vocal_performance_revision_id"]
    if not isinstance(vp_id, str) or not vp_id:
        raise invalid(
            PERFORMANCE_VOCAL_BINDING_INVALID,
            "vocal_performance_revision_id must be a nonempty exact id",
        )
    start = strict_int(raw["source_start_sample"], "source_start_sample")
    end = strict_int(
        raw["source_end_sample_exclusive"], "source_end_sample_exclusive")
    rate = strict_int(raw["sample_rate_hz"], "sample_rate_hz")
    if start < 0 or start >= end:
        raise invalid(
            PERFORMANCE_VOCAL_INTERVAL_INVALID,
            "vocal source interval must satisfy 0 <= start < end",
        )
    if rate <= 0:
        raise invalid(
            PERFORMANCE_VOCAL_BINDING_INVALID,
            "sample_rate_hz must be positive",
        )
    origin = raw["performance_origin_ms"]
    if not isinstance(origin, dict) or set(origin) != _ORIGIN_KEYS:
        raise invalid(
            PERFORMANCE_VOCAL_BINDING_INVALID,
            "performance_origin_ms must contain exactly num and den",
        )
    on = strict_int(origin["num"], "performance_origin_ms.num")
    od = strict_int(origin["den"], "performance_origin_ms.den")
    cn, cd = canonical_rational(on, od)
    if (cn, cd) != (on, od):
        raise invalid(
            PERFORMANCE_VOCAL_BINDING_INVALID,
            "performance_origin_ms must already be canonical-reduced",
        )
    doc = {
        "binding_schema_version": 1,
        "synchronization_basis_version": 1,
        "vocal_performance_revision_id": vp_id,
        "source_start_sample": start,
        "source_end_sample_exclusive": end,
        "sample_rate_hz": rate,
        "performance_origin_ms": {"num": cn, "den": cd},
    }
    return doc, (cn, cd)


def _row_document(row) -> dict:
    return {
        "binding_schema_version": row.binding_schema_version,
        "synchronization_basis_version": row.synchronization_basis_version,
        "vocal_performance_revision_id": row.vocal_performance_revision_id,
        "source_start_sample": row.source_start_sample,
        "source_end_sample_exclusive": row.source_end_sample_exclusive,
        "sample_rate_hz": row.sample_rate_hz,
        "performance_origin_ms": {
            "num": row.performance_origin_num,
            "den": row.performance_origin_den,
        },
    }


def _verify_binding_bytes(row) -> dict:
    if row.binding_schema_version != 1 or row.synchronization_basis_version != 1:
        raise corrupt("M17C vocal binding schema/basis version is not 1")
    try:
        cn, cd = canonical_rational(
            row.performance_origin_num, row.performance_origin_den)
    except SoloRingError as exc:
        # SR26-05: a malformed persisted rational is corruption of
        # immutable history, never a client request problem.
        raise corrupt(
            f"M17C vocal binding stores an invalid persisted rational: "
            f"{exc.message}") from exc
    if (cn, cd) != (row.performance_origin_num, row.performance_origin_den):
        raise corrupt("M17C vocal binding stores a noncanonical rational")
    doc = _row_document(row)
    expected_json = canonical_json_str(doc)
    expected_hash = canonical_hash(doc)
    if row.binding_json != expected_json or row.binding_hash != expected_hash:
        raise corrupt("M17C vocal binding canonical bytes/hash diverge")
    return doc


async def _verify_vp_structural_authority(
    session: AsyncSession,
    vp: VocalPerformanceRevision,
) -> str:
    """C3-01: the CHEAP structural VP authority verifier — no retained
    blob read/hash/WAVE inspection anywhere.

    Proves: adopted VocalCandidate exists and is adopted exactly once;
    every immutable VP copied-authority field equals the adopted
    candidate (including dialogue_line_revision_id); VocalCandidate
    provenance closed grammar/canonical bytes/hash/source_kind; the VP
    DialogueLineRevision exists and matches the adopted candidate's; VP
    speaker == DLR speaker; the DialogueLine exists; the speaker
    CreativeEntity exists and belongs to that project. Returns the
    authoritative VP/DialogueLine project id.
    """
    vc = await session.get(VocalCandidate, vp.adopted_candidate_id)
    if vc is None:
        raise corrupt("bound VocalPerformanceRevision adopted candidate missing")
    count = (await session.execute(
        select(func.count()).select_from(VocalPerformanceRevision).where(
            VocalPerformanceRevision.adopted_candidate_id == vc.id)
    )).scalar_one()
    if count != 1:
        raise corrupt("bound VocalCandidate is not adopted exactly once")
    if any(getattr(vp, f) != getattr(vc, f) for f in _VOCAL_COPY_FIELDS):
        raise corrupt("bound VocalPerformanceRevision closure != adopted candidate")

    try:
        provenance = json.loads(vc.provenance_json)
    except json.JSONDecodeError as exc:
        raise corrupt("bound VocalCandidate provenance is not JSON") from exc
    from soloring.performance.vocal import _provenance_v1
    try:
        normalized = _provenance_v1(provenance)
    except SoloRingError as exc:
        raise corrupt(
            f"bound VocalCandidate provenance violates its closed grammar: {exc.message}"
        ) from exc
    if normalized != provenance or canonical_json_str(normalized) != vc.provenance_json:
        raise corrupt("bound VocalCandidate provenance is not canonical")
    if canonical_hash(normalized) != vc.provenance_hash:
        raise corrupt("bound VocalCandidate provenance hash diverges")
    if normalized["source_kind"] != vc.source_kind:
        raise corrupt("bound VocalCandidate source_kind/provenance disagree")

    dlr = await session.get(DialogueLineRevision, vp.dialogue_line_revision_id)
    if dlr is None:
        raise corrupt("bound VP DialogueLineRevision is missing")
    if vc.dialogue_line_revision_id != dlr.id:
        raise corrupt("bound VocalCandidate and VP name different line revisions")
    if vp.speaker_subject_id != dlr.speaker_subject_id:
        raise corrupt("bound VP speaker != DialogueLineRevision speaker")
    line = await session.get(DialogueLine, dlr.dialogue_line_id)
    if line is None:
        raise corrupt("bound VP DialogueLine is missing")
    from soloring.continuity.models import CreativeEntity
    speaker = await session.get(CreativeEntity, vp.speaker_subject_id)
    if speaker is None or speaker.project_id != line.project_id:
        raise corrupt("bound VP speaker does not belong to DialogueLine project")
    return line.project_id


async def _verify_vp_physical_media(
    session: AsyncSession,
    settings,
    vp: VocalPerformanceRevision,
) -> None:
    """C3-01: the EXPENSIVE retained-media verifier — retained blob
    existence/integrity/rehash, WAVE validity, sample rate, sample-frame
    count, and authoritative trim containment. Transitions and recovery
    pay this cost; authoritative reads do not."""
    from soloring.performance.vocal import _verify_blob
    try:
        blob = await _verify_blob(session, settings, vp.retained_audio_blob_hash)
    except SoloRingError as exc:
        raise corrupt(f"bound VP retained audio integrity failed: {exc.message}") from exc
    if hashlib.sha256(blob["data"]).hexdigest() != vp.retained_audio_blob_hash:
        raise corrupt("bound VP retained audio bytes do not rehash")
    from soloring.performance.audio_inspection import inspect_wave
    try:
        info = inspect_wave(blob["data"])
    except SoloRingError as exc:
        raise corrupt(f"bound VP retained WAVE is invalid: {exc.message}") from exc
    if info["sample_rate_hz"] != vp.native_sample_rate_hz or \
            info["sample_frame_count"] != vp.retained_sample_count:
        raise corrupt("bound VP WAVE properties disagree with stored authority")
    if not (0 <= vp.trim_start_sample < vp.trim_end_sample_exclusive <=
            vp.retained_sample_count):
        raise corrupt("bound VP authoritative trim is illegal")


async def verify_vocal_performance_integrity(
    session: AsyncSession,
    settings,
    vp: VocalPerformanceRevision,
) -> str:
    """Live M17A-recovery-parity verifier for a VP seeding new authority.

    C3-01: implemented as the composition structural-authority verifier
    + physical retained-media verifier — behaviorally identical to the
    pre-split law set, so transitions and recovery keep the FULL
    existing protection.

    C2-02: this function is CONTEXT-NEUTRAL — it verifies the VP's own
    physical/identity closure and RETURNS the VP/DialogueLine project
    id. Project agreement with the consuming candidate is the caller's
    law, so the caller's ADMISSION/HISTORICAL context decides the error
    contract for a mismatch.
    """
    project_id = await _verify_vp_structural_authority(session, vp)
    await _verify_vp_physical_media(session, settings, vp)
    return project_id


def _vocal_performance_interval(row) -> tuple[Fraction, Fraction]:
    # Exact arithmetic without the persisted-rational i64 bound: the
    # induced interval is a derived check-time value, never persisted
    # in the binding (only the origin num/den pair is). A lawful origin
    # like (2**63-1)/(2**63-2) must not be rejected because an
    # intermediate numerator crosses the storage range before
    # reduction; persistence bounds apply where values are stored.
    start = Fraction(row.performance_origin_num, row.performance_origin_den)
    delta_ms = Fraction(
        (row.source_end_sample_exclusive - row.source_start_sample) * 1000,
        row.sample_rate_hz,
    )
    return start, start + delta_ms


def _temporal_domain(obj) -> tuple[Fraction, Fraction]:
    """C2-03: generic exact temporal domain over any object carrying
    temporal_start_num/den and temporal_end_num/den (candidate or
    revision) — each owner validates against its OWN domain."""
    return (
        Fraction(obj.temporal_start_num, obj.temporal_start_den),
        Fraction(obj.temporal_end_num, obj.temporal_end_den),
    )


async def _verify_alignment_exact_vp(
    session: AsyncSession, payload_document: dict, vp_id: str,
    *, context: str = HISTORICAL,
) -> None:
    seen: set[str] = set()
    for channel in payload_document["channels"]:
        for keyframe in channel["keyframes"]:
            aid = keyframe["provenance"]["source_alignment_id"]
            if aid is None or aid in seen:
                continue
            seen.add(aid)
            alignment = await session.get(DialogueAlignment, aid)
            if alignment is None:
                if context == ADMISSION:
                    raise not_found(
                        ErrorCode.PERFORMANCE_ALIGNMENT_NOT_FOUND,
                        f"dialogue alignment {aid!r} not found")
                raise corrupt(
                    f"persisted M17C payload cites missing dialogue "
                    f"alignment {aid!r}")
            if alignment.vocal_performance_revision_id != vp_id:
                if context == ADMISSION:
                    raise invalid(
                        PERFORMANCE_VOCAL_ALIGNMENT_MISMATCH,
                        "dialogue-bound keyframe cites an alignment derived "
                        "from a different VocalPerformanceRevision",
                    )
                raise corrupt(
                    "persisted M17C payload cites an alignment derived from "
                    f"a different VocalPerformanceRevision ({aid!r})")


def _verify_articulation(payload_document: dict,
                         interval: tuple[Fraction, Fraction],
                         *, context: str = HISTORICAL) -> None:
    lo, hi = interval
    by_key = {ch["channel_key"]: ch for ch in payload_document["channels"]}
    for key in REQUIRED_ARTICULATION:
        channel = by_key.get(key)
        if channel is None:
            if context == ADMISSION:
                raise invalid(
                    PERFORMANCE_REQUIRED_ARTICULATION_MISSING,
                    f"dialogue-bound performance requires articulation "
                    f"channel {key!r}",
                )
            raise corrupt(
                f"persisted dialogue-bound payload lost articulation "
                f"channel {key!r}")
        if not any(
            lo <= Fraction(kf["time_ms"]["num"], kf["time_ms"]["den"]) < hi
            for kf in channel["keyframes"]
        ):
            if context == ADMISSION:
                raise invalid(
                    PERFORMANCE_REQUIRED_ARTICULATION_MISSING,
                    f"articulation channel {key!r} has no keyframe inside "
                    "the bound vocal interval",
                )
            raise corrupt(
                f"persisted articulation channel {key!r} has no keyframe "
                "inside the bound vocal interval")


async def verify_candidate_vocal_binding(
    session: AsyncSession,
    settings,
    candidate: PerformanceCandidate,
    row: PerformanceCandidateVocalBinding,
    *,
    payload_document: dict | None = None,
    pending_binding: PerformanceCandidateVocalBinding | None = None,
    context: str = HISTORICAL,
) -> dict:
    """Verify a candidate vocal binding under an explicit context.

    DR26-03: ADMISSION validates a fresh client request and keeps the
    established 4xx codes; HISTORICAL revalidates persisted immutable
    authority, where impossible states are corruption. ``pending_binding``
    supplies the in-flight creation row to the discriminator cardinality
    check (an SR26-01 concern, orthogonal to the error contract).
    """
    if row.performance_candidate_id != candidate.id:
        raise corrupt("candidate vocal-binding parent id diverges")
    if candidate.performance_kind not in ("FACIAL", "BODY_FACIAL"):
        # C2-02: an impossible persisted kind is corruption; only a
        # fresh request keeps the admission 422.
        if context == ADMISSION:
            raise invalid(
                PERFORMANCE_VOCAL_BINDING_INVALID,
                "dialogue-bound performance must be FACIAL or BODY_FACIAL",
            )
        raise corrupt(
            f"persisted dialogue-bound candidate {candidate.id!r} has "
            f"impossible performance_kind {candidate.performance_kind!r}")
    candidate_classification = await verify_candidate_sync_classification(
        session, candidate, pending_binding=pending_binding)
    if candidate_classification.sync_mode != "VOCAL_V1":
        raise corrupt(
            "candidate carries a vocal binding but is not classified "
            "VOCAL_V1")
    _verify_binding_bytes(row)
    vp = await session.get(VocalPerformanceRevision,
                           row.vocal_performance_revision_id)
    if vp is None:
        if context == ADMISSION:
            raise not_found(
                ErrorCode.VOCAL_PERFORMANCE_NOT_FOUND,
                f"vocal performance revision "
                f"{row.vocal_performance_revision_id!r} not found",
            )
        raise corrupt(
            "persisted M17C vocal binding names a missing "
            f"VocalPerformanceRevision "
            f"{row.vocal_performance_revision_id!r}")
    # C2-02: project closure is the caller's law — the VP verifier is
    # context-neutral and returns the VP/DialogueLine project id.
    vp_project_id = await verify_vocal_performance_integrity(
        session, settings, vp)
    if vp_project_id != candidate.project_id:
        if context == ADMISSION:
            raise invalid(
                PERFORMANCE_VOCAL_PROJECT_MISMATCH,
                "bound VP/DialogueLine belongs to another Project",
            )
        raise corrupt(
            "persisted binding's VP/DialogueLine project "
            f"{vp_project_id!r} disagrees with the candidate's project "
            f"{candidate.project_id!r}")
    if candidate.subject_id != vp.speaker_subject_id:
        if context == ADMISSION:
            raise invalid(
                PERFORMANCE_VOCAL_SUBJECT_MISMATCH,
                "Performance subject != bound VP speaker",
            )
        raise corrupt("persisted binding subject != VP speaker")
    if row.sample_rate_hz != vp.native_sample_rate_hz:
        if context == ADMISSION:
            raise invalid(
                ErrorCode.SAMPLE_RATE_MISMATCH,
                "vocal binding sample rate != bound VP native sample rate",
            )
        raise corrupt("persisted binding sample rate != VP native rate")
    if not (vp.trim_start_sample <= row.source_start_sample <
            row.source_end_sample_exclusive <= vp.trim_end_sample_exclusive):
        if context == ADMISSION:
            raise invalid(
                PERFORMANCE_VOCAL_INTERVAL_INVALID,
                "vocal binding source interval lies outside the bound VP "
                "trim",
            )
        raise corrupt(
            "persisted binding source interval lies outside the VP trim")
    bound_interval = _vocal_performance_interval(row)
    domain = _temporal_domain(candidate)
    if not (domain[0] <= bound_interval[0] < bound_interval[1] <= domain[1]):
        if context == ADMISSION:
            raise invalid(
                PERFORMANCE_VOCAL_INTERVAL_INVALID,
                "induced vocal Performance interval lies outside candidate "
                "domain",
            )
        raise corrupt(
            "persisted binding interval lies outside the parent domain")
    if payload_document is None:
        payload_document = (await revision_svc.verify_candidate_integrity(
            session, settings, candidate))["payload_document"]
    await _verify_alignment_exact_vp(
        session, payload_document, row.vocal_performance_revision_id,
        context=context)
    _verify_articulation(payload_document, bound_interval, context=context)
    return {"vp": vp, "payload_document": payload_document,
            "performance_interval": bound_interval}


async def create_dialogue_bound_performance_candidate(
    session: AsyncSession,
    settings,
    *,
    subject_id: str,
    performance_kind: str,
    performance_profile_id: str,
    temporal_start_num: int,
    temporal_start_den: int,
    temporal_end_num: int,
    temporal_end_den: int,
    channels: list[dict],
    source_provenance: dict,
    vocal_binding: dict,
) -> tuple[PerformanceCandidate, PerformanceCandidateVocalBinding]:
    if performance_kind not in ("FACIAL", "BODY_FACIAL"):
        raise invalid(
            PERFORMANCE_VOCAL_BINDING_INVALID,
            "dialogue-bound candidate route accepts FACIAL or BODY_FACIAL only",
        )
    doc, (on, od) = _binding_document(vocal_binding)
    candidate = await revision_svc.create_performance_candidate(
        session,
        settings,
        subject_id=subject_id,
        performance_kind=performance_kind,
        performance_profile_id=performance_profile_id,
        temporal_start_num=temporal_start_num,
        temporal_start_den=temporal_start_den,
        temporal_end_num=temporal_end_num,
        temporal_end_den=temporal_end_den,
        channels=channels,
        source_provenance=source_provenance,
        sync_mode="VOCAL_V1",
    )
    row = PerformanceCandidateVocalBinding(
        performance_candidate_id=candidate.id,
        vocal_performance_revision_id=doc["vocal_performance_revision_id"],
        source_start_sample=doc["source_start_sample"],
        source_end_sample_exclusive=doc["source_end_sample_exclusive"],
        sample_rate_hz=doc["sample_rate_hz"],
        performance_origin_num=on,
        performance_origin_den=od,
        synchronization_basis_version=1,
        binding_schema_version=1,
        binding_json=canonical_json_str(doc),
        binding_hash=canonical_hash(doc),
        created_at=await db_now(session),
    )
    integrity = await revision_svc.verify_candidate_integrity(
        session, settings, candidate)
    # pending_binding: the SR26-01 cardinality law normally reads the
    # companion through the session; during creation the row is not yet
    # persisted, so it is handed to the classification check directly.
    # DR26-03: creation is ADMISSION context — client-shaped failures
    # keep their 4xx codes.
    await verify_candidate_vocal_binding(
        session, settings, candidate, row,
        payload_document=integrity["payload_document"],
        pending_binding=row, context=ADMISSION)
    session.add(row)
    await session.flush()
    return candidate, row


async def verify_candidate_sync_classification(
    session: AsyncSession, candidate: PerformanceCandidate,
    *, pending_binding=None,
) -> PerformanceCandidateSyncClassification:
    """SR26-01 discriminator law for a candidate row.

    Every candidate carries exactly one immutable classification; its
    absence is corruption. VOCAL_V1 requires exactly one binding row;
    NONE prohibits one. ``pending_binding`` supplies an in-flight,
    not-yet-persisted binding during creation.
    """
    classification = await session.get(
        PerformanceCandidateSyncClassification, candidate.id)
    if classification is None:
        raise corrupt(
            f"performance candidate {candidate.id!r} has no PF-03 sync "
            "classification; applicability cannot be determined")
    if classification.classification_schema_version != 1:
        raise corrupt("PF-03 sync classification schema version is not 1")
    binding = await session.get(
        PerformanceCandidateVocalBinding, candidate.id)
    if binding is None:
        binding = pending_binding
    if classification.sync_mode == "VOCAL_V1":
        if binding is None:
            raise corrupt(
                f"performance candidate {candidate.id!r} is classified "
                "VOCAL_V1 but its PF-03 binding companion is missing "
                "(total companion loss)")
    elif classification.sync_mode == "NONE":
        if binding is not None:
            raise corrupt(
                f"performance candidate {candidate.id!r} is classified "
                "NONE but carries a PF-03 binding companion")
    else:
        raise corrupt(
            f"PF-03 sync classification has unknown mode "
            f"{classification.sync_mode!r}")
    return classification


async def verify_revision_sync_classification(
    session: AsyncSession, revision: PerformanceRevision,
) -> PerformanceRevisionSyncClassification:
    """Adopted-pair classification closure (SR26-01 + DR26-01 + C2-01).

    One non-recursive call proves: the adopted candidate's LOCAL
    classification law (exists, schema, NONE/VOCAL_V1 cardinality — via
    the shared candidate-local verifier, not a bare row fetch), the
    revision's own LOCAL law, and pair equality — before either side's
    mode may be interpreted.
    """
    candidate = await session.get(PerformanceCandidate,
                                  revision.adopted_candidate_id)
    if candidate is None:
        raise corrupt("adopted revision's candidate is missing")
    candidate_classification = await verify_candidate_sync_classification(
        session, candidate)

    classification = await session.get(
        PerformanceRevisionSyncClassification, revision.id)
    if classification is None:
        raise corrupt(
            f"performance revision {revision.id!r} has no PF-03 sync "
            "classification; applicability cannot be determined")
    if classification.classification_schema_version != 1:
        raise corrupt("PF-03 sync classification schema version is not 1")
    if candidate_classification.sync_mode != classification.sync_mode:
        raise corrupt(
            f"revision {revision.id!r} PF-03 classification "
            f"{classification.sync_mode!r} != adopted candidate "
            f"classification {candidate_classification.sync_mode!r}")
    binding = await session.get(
        PerformanceRevisionVocalBinding, revision.id)
    if classification.sync_mode == "VOCAL_V1":
        if binding is None:
            raise corrupt(
                f"performance revision {revision.id!r} is classified "
                "VOCAL_V1 but its PF-03 binding companion is missing "
                "(total companion loss)")
    elif classification.sync_mode == "NONE":
        if binding is not None:
            raise corrupt(
                f"performance revision {revision.id!r} is classified "
                "NONE but carries a PF-03 binding companion")
    else:
        raise corrupt(
            f"PF-03 sync classification has unknown mode "
            f"{classification.sync_mode!r}")
    return classification


def _read_binding_scalar_laws(row, parent, vp) -> None:
    """DB-level immutable-identity laws shared by the read path.

    SR26-03 cost boundary (recorded): authoritative reads prove the
    PF-03 classification, canonical binding bytes/hash, parent/companion
    closure, and exact immutable identity against stored authority
    rows; they do not rehash the retained VP audio bytes (a
    transition-time and recovery-time check).
    """
    _verify_binding_bytes(row)
    if parent.performance_kind not in ("FACIAL", "BODY_FACIAL"):
        # C2-02: an impossible persisted kind is corruption on reads.
        raise corrupt(
            f"persisted dialogue-bound parent {parent.id!r} has "
            f"impossible performance_kind {parent.performance_kind!r}")
    if row.sample_rate_hz != vp.native_sample_rate_hz:
        raise corrupt("binding sample rate != VP native sample rate")
    if not (vp.trim_start_sample <= row.source_start_sample <
            row.source_end_sample_exclusive <= vp.trim_end_sample_exclusive):
        raise corrupt("binding source interval lies outside the VP trim")
    if parent.subject_id != vp.speaker_subject_id:
        raise corrupt("binding parent subject != VP speaker")


async def _read_project_law(session: AsyncSession, parent, vp) -> None:
    """C3-01: reads prove the FULL cheap VP structural authority closure
    (adopted-candidate identity, copied fields incl. DLR, provenance
    grammar/hash, speaker/project membership) via the shared structural
    verifier — never merely VP→DLR→DialogueLine project equality — and
    then require the verified VP project to equal the reading parent's
    project. No retained VP audio bytes are read or rehashed here."""
    vp_project_id = await _verify_vp_structural_authority(session, vp)
    if vp_project_id != parent.project_id:
        raise corrupt(
            "persisted binding's VP/DialogueLine project "
            f"{vp_project_id!r} disagrees with the reading parent's "
            f"project {parent.project_id!r}")


async def read_candidate_vocal_binding(
    session: AsyncSession, settings, *, candidate_id: str,
) -> PerformanceCandidateVocalBinding:
    """SR26-03: fail-closed authoritative candidate binding read."""
    candidate = await session.get(PerformanceCandidate, candidate_id)
    if candidate is None:
        raise not_found(
            ErrorCode.PERFORMANCE_CANDIDATE_NOT_FOUND,
            f"performance candidate {candidate_id!r} not found")
    classification = await verify_candidate_sync_classification(
        session, candidate)
    # C2-01: an ADOPTED candidate's read proves the FULL pair closure —
    # candidate-local law, revision-local law, and equality — via the
    # one shared revision verifier, BEFORE either mode is interpreted
    # (both the honest-NONE 404 path and the binding-return path).
    adopted_revision = (await session.execute(
        select(PerformanceRevision).where(
            PerformanceRevision.adopted_candidate_id == candidate.id)
    )).scalar_one_or_none()
    if adopted_revision is not None:
        await verify_revision_sync_classification(
            session, adopted_revision)
    if classification.sync_mode == "NONE":
        raise not_found(
            PERFORMANCE_VOCAL_BINDING_NOT_FOUND,
            f"performance candidate {candidate_id!r} has no vocal binding",
        )
    row = await session.get(PerformanceCandidateVocalBinding, candidate_id)
    # verify_candidate_sync_classification proved existence for VOCAL_V1
    vp = await session.get(VocalPerformanceRevision,
                           row.vocal_performance_revision_id)
    if vp is None:
        raise corrupt(
            "persisted M17C vocal binding names a missing "
            f"VocalPerformanceRevision "
            f"{row.vocal_performance_revision_id!r}")
    _read_binding_scalar_laws(row, candidate, vp)
    await _read_project_law(session, candidate, vp)
    interval = _vocal_performance_interval(row)
    domain = _temporal_domain(candidate)
    if not (domain[0] <= interval[0] < interval[1] <= domain[1]):
        raise corrupt(
            "persisted binding interval lies outside the candidate domain")
    integrity = await revision_svc.verify_candidate_integrity(
        session, settings, candidate)
    await _verify_alignment_exact_vp(
        session, integrity["payload_document"], vp.id)
    # DR26-02: the authoritative read enforces the same articulation
    # law as recovery, over the already-loaded canonical payload.
    _verify_articulation(integrity["payload_document"], interval)
    return row


async def verify_revision_vocal_binding_read_grade(
        session: AsyncSession, settings, revision: PerformanceRevision,
        row: PerformanceRevisionVocalBinding, *,
        classification) -> dict:
    """SR2-05: the ONE authoritative READ-GRADE revision-binding
    verifier — semantically complete except for the expensive retained
    VP audio/WAVE verification (``_verify_vp_physical_media``; the
    C3-01 read cost boundary). The authoritative binding GET and the
    PF-02 readiness/list seam consume THIS verifier, never a weaker
    parallel copy.

    Proves: parent identity; adopted candidate + source candidate
    binding presence; candidate↔revision binding semantic equality;
    binding scalar laws (schema versions, canonical bytes/hash, kind,
    rate == VP native rate, source interval inside the VP trim,
    subject == speaker); the full cheap VP structural authority closure
    plus VP/Performance project agreement; the induced interval inside
    the REVISION-owned temporal domain; the adopted candidate's
    immutable payload closure; exact-VP cited alignments; and required
    articulation inside the bound interval."""
    if row.performance_revision_id != revision.id:
        raise corrupt("revision vocal-binding parent id diverges")
    candidate = await session.get(PerformanceCandidate,
                                  revision.adopted_candidate_id)
    if candidate is None:
        raise corrupt("dialogue-bound revision adopted candidate is missing")
    # verify_revision_sync_classification already proved the candidate's
    # local law and pair equality (C2-01) — no duplicate comparison here.
    candidate_row = await session.get(
        PerformanceCandidateVocalBinding, candidate.id)
    if candidate_row is None:
        raise corrupt(
            "dialogue-bound revision source candidate binding is missing")
    if not _semantic_binding_equal(candidate_row, row):
        raise corrupt(
            "revision vocal binding != adopted candidate binding closure")
    vp = await session.get(VocalPerformanceRevision,
                           row.vocal_performance_revision_id)
    if vp is None:
        raise corrupt(
            "persisted M17C vocal binding names a missing "
            f"VocalPerformanceRevision "
            f"{row.vocal_performance_revision_id!r}")
    _read_binding_scalar_laws(row, revision, vp)
    await _read_project_law(session, revision, vp)
    interval = _vocal_performance_interval(row)
    # C2-03: the REVISION owns its temporal-domain law — the persisted
    # interval must fit the revision's own domain, matching recovery's
    # revision-owned check (never the adopted candidate's domain).
    domain = _temporal_domain(revision)
    if not (domain[0] <= interval[0] < interval[1] <= domain[1]):
        raise corrupt(
            "persisted binding interval lies outside the revision's own "
            "temporal domain")
    integrity = await revision_svc.verify_candidate_integrity(
        session, settings, candidate)
    await _verify_alignment_exact_vp(
        session, integrity["payload_document"], vp.id)
    # DR26-02: same articulation law as recovery, over the already-loaded
    # canonical payload.
    _verify_articulation(integrity["payload_document"], interval)
    return {"classification": classification, "binding": row,
            "candidate": candidate, "vp": vp,
            "payload_document": integrity["payload_document"]}


async def read_revision_vocal_binding(
        session: AsyncSession, settings, *, revision_id: str,
) -> PerformanceRevisionVocalBinding:
    """SR26-03: fail-closed authoritative revision binding read. The
    semantic laws live in the shared read-grade verifier above — the
    GET and PF-02 reads consume the SAME verifier (SR2-05)."""
    revision = await session.get(PerformanceRevision, revision_id)
    if revision is None:
        raise not_found(
            ErrorCode.PERFORMANCE_REVISION_NOT_FOUND,
            f"performance revision {revision_id!r} not found")
    classification = await verify_revision_sync_classification(
        session, revision)
    if classification.sync_mode == "NONE":
        raise not_found(
            PERFORMANCE_VOCAL_BINDING_NOT_FOUND,
            f"performance revision {revision_id!r} has no vocal binding",
        )
    row = await session.get(PerformanceRevisionVocalBinding, revision_id)
    await verify_revision_vocal_binding_read_grade(
        session, settings, revision, row, classification=classification)
    return row


def _semantic_binding_equal(candidate_row, revision_row) -> bool:
    return all(getattr(candidate_row, f) == getattr(revision_row, f)
               for f in BINDING_FIELDS)


async def verify_revision_vocal_binding(
    session: AsyncSession,
    settings,
    revision: PerformanceRevision,
    row: PerformanceRevisionVocalBinding,
) -> dict:
    if row.performance_revision_id != revision.id:
        raise corrupt("revision vocal-binding parent id diverges")
    revision_classification = await verify_revision_sync_classification(
        session, revision)
    if revision_classification.sync_mode != "VOCAL_V1":
        raise corrupt(
            "revision carries a vocal binding but is not classified "
            "VOCAL_V1")
    candidate = await session.get(PerformanceCandidate,
                                  revision.adopted_candidate_id)
    if candidate is None:
        raise corrupt("dialogue-bound revision adopted candidate is missing")
    candidate_row = await session.get(
        PerformanceCandidateVocalBinding, candidate.id)
    if candidate_row is None:
        raise corrupt("dialogue-bound revision source candidate binding is missing")
    if not _semantic_binding_equal(candidate_row, row):
        raise corrupt("revision vocal binding != adopted candidate binding closure")
    await verify_candidate_vocal_binding(
        session, settings, candidate, candidate_row)
    _verify_binding_bytes(row)
    return {"candidate": candidate, "candidate_binding": candidate_row}


async def adoption_binding_precheck(
    session: AsyncSession,
    settings,
    candidate: PerformanceCandidate,
) -> PerformanceCandidateVocalBinding | None:
    # SR26-01: the discriminator is verified FIRST — a VOCAL_V1
    # candidate whose binding companion has totally disappeared refuses
    # here instead of silently downgrading to generic M17B.
    classification = await verify_candidate_sync_classification(
        session, candidate)
    if classification.sync_mode == "NONE":
        return None
    row = await session.get(PerformanceCandidateVocalBinding, candidate.id)
    # classification law proved the row exists for VOCAL_V1
    await verify_candidate_vocal_binding(session, settings, candidate, row)
    return row


async def converge_revision_binding(
    session: AsyncSession,
    settings,
    candidate: PerformanceCandidate,
    revision: PerformanceRevision,
    candidate_binding: PerformanceCandidateVocalBinding | None,
    *,
    allow_create: bool,
) -> PerformanceRevisionVocalBinding | None:
    candidate_classification = await verify_candidate_sync_classification(
        session, candidate)
    existing_cls = await session.get(
        PerformanceRevisionSyncClassification, revision.id)
    if existing_cls is None:
        if not allow_create:
            raise corrupt(
                "adopted winner is missing its PF-03 sync classification")
        existing_cls = PerformanceRevisionSyncClassification(
            performance_revision_id=revision.id,
            sync_mode=candidate_classification.sync_mode,
            classification_schema_version=1,
            created_at=await db_now(session),
        )
        session.add(existing_cls)
        await session.flush()
    else:
        if existing_cls.classification_schema_version != 1:
            raise corrupt(
                "PF-03 sync classification schema version is not 1")
        if existing_cls.sync_mode != candidate_classification.sync_mode:
            raise corrupt(
                "revision PF-03 classification != adopted candidate "
                "classification")

    if candidate_classification.sync_mode == "NONE":
        if candidate_binding is not None:
            raise corrupt(
                "generic M17B candidate has an unexpected vocal binding")
        existing = await session.get(
            PerformanceRevisionVocalBinding, revision.id)
        if existing is not None:
            raise corrupt(
                "generic M17B revision has an unexpected vocal binding")
        return None

    existing = await session.get(PerformanceRevisionVocalBinding, revision.id)
    if existing is not None:
        await verify_revision_vocal_binding(session, settings, revision, existing)
        return existing
    if not allow_create:
        raise corrupt(
            "adopted dialogue-bound winner is missing its revision vocal binding")
    row = PerformanceRevisionVocalBinding(
        performance_revision_id=revision.id,
        **{field: getattr(candidate_binding, field) for field in BINDING_FIELDS},
        created_at=await db_now(session),
    )
    session.add(row)
    await session.flush()
    await verify_revision_vocal_binding(session, settings, revision, row)
    return row


async def preserve_retarget_binding(
    session: AsyncSession,
    settings,
    *,
    source_revision: PerformanceRevision,
    candidate: PerformanceCandidate,
) -> PerformanceCandidateVocalBinding | None:
    # SR26-01: classification is copied independently of the binding
    # payload, and the source classification law runs FIRST — a VOCAL_V1
    # source whose binding has totally disappeared refuses here.
    source_cls = await session.get(
        PerformanceRevisionSyncClassification, source_revision.id)
    if source_cls is None:
        raise corrupt(
            "source revision has no PF-03 sync classification")
    if source_cls.classification_schema_version != 1:
        raise corrupt("PF-03 sync classification schema version is not 1")

    # the retarget service constructs candidates directly (not through
    # create_performance_candidate), so the classification companion is
    # installed here in the same transaction.
    existing_cls = await session.get(
        PerformanceCandidateSyncClassification, candidate.id)
    if existing_cls is None:
        existing_cls = PerformanceCandidateSyncClassification(
            performance_candidate_id=candidate.id,
            sync_mode=source_cls.sync_mode,
            classification_schema_version=1,
            created_at=await db_now(session),
        )
        session.add(existing_cls)
        await session.flush()
    elif existing_cls.sync_mode != source_cls.sync_mode:
        raise corrupt(
            "retarget candidate PF-03 classification != source revision "
            "classification")

    if source_cls.sync_mode == "NONE":
        if await session.get(PerformanceCandidateVocalBinding,
                             candidate.id) is not None:
            raise corrupt(
                "non-dialogue retarget candidate unexpectedly has binding")
        return None

    source = await session.get(PerformanceRevisionVocalBinding,
                               source_revision.id)
    # verify_revision_sync_classification below proves existence for
    # VOCAL_V1; total source loss refuses as corruption there.
    await verify_revision_sync_classification(session, source_revision)
    await verify_revision_vocal_binding(session, settings, source_revision, source)
    existing = await session.get(PerformanceCandidateVocalBinding,
                                 candidate.id)
    if existing is not None:
        for field in BINDING_FIELDS:
            if getattr(existing, field) != getattr(source, field):
                raise corrupt("retarget candidate vocal binding diverges from source")
        await verify_candidate_vocal_binding(session, settings, candidate, existing)
        return existing
    row = PerformanceCandidateVocalBinding(
        performance_candidate_id=candidate.id,
        **{field: getattr(source, field) for field in BINDING_FIELDS},
        created_at=await db_now(session),
    )
    session.add(row)
    await session.flush()
    await verify_candidate_vocal_binding(session, settings, candidate, row)
    return row


def binding_view(row) -> dict:
    return {
        "vocal_performance_revision_id": row.vocal_performance_revision_id,
        "source_start_sample": row.source_start_sample,
        "source_end_sample_exclusive": row.source_end_sample_exclusive,
        "sample_rate_hz": row.sample_rate_hz,
        "performance_origin_ms": {
            "num": row.performance_origin_num,
            "den": row.performance_origin_den,
        },
        "synchronization_basis_version": row.synchronization_basis_version,
        "binding_schema_version": row.binding_schema_version,
        "binding_hash": row.binding_hash,
        "created_at": row.created_at,
    }
