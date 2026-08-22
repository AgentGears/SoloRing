"""The ONE realization compiler (frozen plan §§12–21).

Pure value transformation: CapturedVisualAuthority + validated profile +
validated manifest → RealizationResult. No DB, no filesystem, no
network, no current Shot, no M8 resolver, no Settings, no Comfy API, no
legacy ShotReference resolution. Worker execution and Exact Rerun never
call this compiler.

Readiness semantics: required-facet blockers and channel-minimum
failures are COLLECTED (canonical order, deterministic) and returned as
``issues`` with ``ready=False`` and NO partial spec/inputs — §20's
result shape. Package/binding-shape violations remain raising 422s
(profile/fingerprint/input-binding are package errors, not Shot
readiness). Generation creation converts the first issue into the exact
409 blocker before queueing (§11.3).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from soloring.errors import ErrorCode, SoloRingError
from soloring.realization.authority import (
    CapturedFacet,
    CapturedVisualAuthority,
)

# Closed optional omission vocabulary (§12) — data, not errors.
OMISSION_REASONS = (
    "no_matching_rule",
    "no_allowed_items",
    "capacity_exceeded",
    "channel_minimum_unmet",
)

REQUIRED_BLOCKER_CODES = (
    ErrorCode.REALIZATION_REQUIRED_FACET_UNSUPPORTED,
    ErrorCode.REALIZATION_CAPACITY_EXCEEDED,
    ErrorCode.REALIZATION_CHANNEL_MINIMUM_UNMET,
)


def _binding_invalid(message: str) -> SoloRingError:
    return SoloRingError(
        ErrorCode.REALIZATION_INPUT_BINDING_INVALID, message,
        status_code=422,
    )


@dataclass(frozen=True)
class RealizationInputProjection:
    """One realization-backed GenerationInput (§18)."""

    input_key: str
    position: int
    asset_id: str
    blob_hash: str
    reference_role: str


@dataclass(frozen=True)
class OmittedOptional:
    visual_facet_id: str
    target_kind: str
    facet_key: str
    reason: str


@dataclass(frozen=True)
class FacetOutcome:
    """§34 inspection projection for ONE facet (r2-gate B3): derived
    from the deterministic allocation itself, populated on NOT-READY
    results too, so a blocked compile still reports which OTHER facets
    were supported — without fabricating any partial RealizationSpec."""

    visual_facet_id: str
    facet_key: str
    target_kind: str
    requirement: str
    status: str  # 'selected' | 'required_blocked' | 'optional_omitted'
    channel: str | None = None
    input_key: str | None = None
    eligible_items: tuple = ()
    reason: str | None = None
    issue_code: str | None = None


@dataclass(frozen=True)
class RealizationResult:
    ready: bool
    spec: dict | None
    inputs: tuple[RealizationInputProjection, ...] = ()
    parameter_overrides: dict = field(default_factory=dict)
    omitted_optional: tuple[OmittedOptional, ...] = ()
    issues: tuple[dict, ...] = ()
    facet_outcomes: tuple[FacetOutcome, ...] = ()

    def first_issue_code(self) -> str | None:
        return self.issues[0]["error_code"] if self.issues else None


def _facet_sort_key(facet: CapturedFacet) -> tuple:
    """§50 anchor ordering, re-derived on the captured facets so the
    compiler never trusts discovery order."""
    if facet.target_kind == "entity":
        return (
            0, facet.entity_id or "", facet.entity_revision_id or "",
            facet.facet_key, facet.visual_facet_id,
            facet.visual_anchor_revision_id,
        )
    return (
        1, facet.feature_id or "", facet.feature_value_hash or "",
        facet.visual_context_entity_revision_id or "", facet.facet_key,
        facet.visual_facet_id, facet.visual_anchor_revision_id,
    )


class _Compiler:
    def __init__(
        self, authority, profile, manifest_v2, profile_hash, fingerprint_hash
    ) -> None:
        self.authority = authority
        self.profile = profile
        self.manifest = manifest_v2
        self.profile_hash = profile_hash
        self.fingerprint_hash = fingerprint_hash

    def run(self) -> RealizationResult:
        self._validate_authority()                            # step 1
        self._validate_channel_contract()                     # steps 2–3
        rule_of = {
            (r.target_kind, r.facet_key): r for r in self.profile.rules
        }                                                      # step 4

        ordered = sorted(self.authority.facets, key=_facet_sort_key)
        order_index = {f.visual_facet_id: i for i, f in enumerate(ordered)}
        required = [f for f in ordered if f.requirement == "required"]
        optional = [f for f in ordered if f.requirement == "optional"]

        issues: list[dict] = []
        allocated: dict[str, list] = {k: [] for k in self.profile.channels}
        facet_channel: dict[str, str] = {}
        outcome_by_facet: dict = {}

        def _record(outcome) -> None:
            outcome_by_facet[outcome.visual_facet_id] = outcome

        # Steps 5–9: required facets in canonical order; blockers are
        # COLLECTED (the facet is not allocated), never truncated.
        for facet in required:
            rule = rule_of.get((facet.target_kind, facet.facet_key))
            if rule is None:
                issues.append({
                    "error_code": (
                        ErrorCode.REALIZATION_REQUIRED_FACET_UNSUPPORTED
                    ),
                    "visual_facet_id": facet.visual_facet_id,
                    "facet_key": facet.facet_key,
                    "message": (
                        f"Required facet {facet.facet_key!r} "
                        f"({facet.target_kind}) has no exact profile rule."
                    ),
                })
                _record(FacetOutcome(
                    facet.visual_facet_id, facet.facet_key,
                    facet.target_kind, "required",
                    "required_blocked",
                    issue_code=ErrorCode.REALIZATION_REQUIRED_FACET_UNSUPPORTED,
                ))
                continue
            channel = self.profile.channels[rule.channel]
            eligible = [
                it for it in facet.items if it.role in channel.allowed_roles
            ]
            if not eligible:
                issues.append({
                    "error_code": (
                        ErrorCode.REALIZATION_REQUIRED_FACET_UNSUPPORTED
                    ),
                    "visual_facet_id": facet.visual_facet_id,
                    "facet_key": facet.facet_key,
                    "message": (
                        f"Required facet {facet.facet_key!r} has no item "
                        f"allowed by channel {rule.channel!r}."
                    ),
                })
                _record(FacetOutcome(
                    facet.visual_facet_id, facet.facet_key,
                    facet.target_kind, "required",
                    "required_blocked",
                    issue_code=ErrorCode.REALIZATION_REQUIRED_FACET_UNSUPPORTED,
                ))
                continue
            if (
                len(allocated[rule.channel]) + len(eligible)
                > channel.max_items
            ):
                issues.append({
                    "error_code": ErrorCode.REALIZATION_CAPACITY_EXCEEDED,
                    "visual_facet_id": facet.visual_facet_id,
                    "facet_key": facet.facet_key,
                    "channel": rule.channel,
                    "message": (
                        f"Required facet {facet.facet_key!r} would exceed "
                        f"channel {rule.channel!r} max_items "
                        f"{channel.max_items}."
                    ),
                })
                _record(FacetOutcome(
                    facet.visual_facet_id, facet.facet_key,
                    facet.target_kind, "required",
                    "required_blocked",
                    issue_code=ErrorCode.REALIZATION_CAPACITY_EXCEEDED,
                ))
                continue
            allocated[rule.channel].extend((facet, it) for it in eligible)
            facet_channel[facet.visual_facet_id] = rule.channel
            _record(FacetOutcome(
                facet.visual_facet_id, facet.facet_key, facet.target_kind,
                "required", "selected", rule.channel,
                self.profile.channels[rule.channel].input_key,
                tuple(eligible),
            ))

        # Steps 10–11: optional facets in canonical order with the closed
        # whole-facet omission reasons (audited even when required
        # blockers exist — §36.2 previews show both).
        omitted: list[OmittedOptional] = []
        for facet in optional:
            rule = rule_of.get((facet.target_kind, facet.facet_key))
            if rule is None:
                omitted.append(OmittedOptional(
                    facet.visual_facet_id, facet.target_kind,
                    facet.facet_key, "no_matching_rule",
                ))
                _record(FacetOutcome(
                    facet.visual_facet_id, facet.facet_key,
                    facet.target_kind, "optional", "optional_omitted",
                    reason="no_matching_rule",
                ))
                continue
            channel = self.profile.channels[rule.channel]
            eligible = [
                it for it in facet.items if it.role in channel.allowed_roles
            ]
            if not eligible:
                omitted.append(OmittedOptional(
                    facet.visual_facet_id, facet.target_kind,
                    facet.facet_key, "no_allowed_items",
                ))
                _record(FacetOutcome(
                    facet.visual_facet_id, facet.facet_key,
                    facet.target_kind, "optional", "optional_omitted",
                    reason="no_allowed_items",
                ))
                continue
            if (
                len(allocated[rule.channel]) + len(eligible)
                > channel.max_items
            ):
                omitted.append(OmittedOptional(
                    facet.visual_facet_id, facet.target_kind,
                    facet.facet_key, "capacity_exceeded",
                ))
                _record(FacetOutcome(
                    facet.visual_facet_id, facet.facet_key,
                    facet.target_kind, "optional", "optional_omitted",
                    reason="capacity_exceeded",
                ))
                continue
            allocated[rule.channel].extend((facet, it) for it in eligible)
            facet_channel[facet.visual_facet_id] = rule.channel
            _record(FacetOutcome(
                facet.visual_facet_id, facet.facet_key, facet.target_kind,
                "optional", "selected", rule.channel,
                self.profile.channels[rule.channel].input_key,
                tuple(eligible),
            ))

        # Step 12 (§12.3): channel minimum, evaluated ONCE on the final
        # tentative allocation; no heuristic rerun. Only meaningful when
        # required allocation succeeded.
        if not issues:
            required_channels = {
                facet_channel[f.visual_facet_id]
                for f in required
                if f.visual_facet_id in facet_channel
            }
            for key, channel in self.profile.channels.items():
                bindings = allocated[key]
                if not bindings or len(bindings) >= channel.min_items:
                    continue  # inactive-or-satisfied
                if key in required_channels:
                    code = ErrorCode.REALIZATION_CHANNEL_MINIMUM_UNMET
                    issues.append({
                        "error_code": code,
                        "channel": key,
                        "message": (
                            f"Channel {key!r} contains required authority "
                            f"but ends below min_items {channel.min_items}."
                        ),
                    })
                    for facet in ordered:
                        if (
                            facet.requirement == "required"
                            and facet_channel.get(facet.visual_facet_id)
                            == key
                        ):
                            _record(FacetOutcome(
                                facet.visual_facet_id, facet.facet_key,
                                facet.target_kind, "required",
                                "required_blocked", issue_code=code,
                            ))
                    continue
                # Optional-only channel below minimum: omit ALL its
                # optional facets — ONE omission per FACET, never per
                # binding (B2) — and leave the channel inactive.
                rolled_back = {
                    facet.visual_facet_id for facet, _it in bindings
                }
                for fid in rolled_back:
                    facet_channel.pop(fid, None)
                for facet in ordered:
                    if facet.visual_facet_id in rolled_back:
                        omitted.append(OmittedOptional(
                            facet.visual_facet_id, facet.target_kind,
                            facet.facet_key, "channel_minimum_unmet",
                        ))
                        _record(FacetOutcome(
                            facet.visual_facet_id, facet.facet_key,
                            facet.target_kind, "optional",
                            "optional_omitted",
                            reason="channel_minimum_unmet",
                        ))
                allocated[key] = []

        ordered_omitted = tuple(sorted(
            omitted, key=lambda o: order_index[o.visual_facet_id]
        ))

        ordered_outcomes = tuple(
            outcome_by_facet[f.visual_facet_id] for f in ordered
            if f.visual_facet_id in outcome_by_facet
        )
        if issues:
            # No partial spec/hash is fabricated (§21) — but the honest
            # per-facet inspection projection IS returned (§34/B3).
            return RealizationResult(
                ready=False,
                spec=None,
                inputs=(),
                omitted_optional=ordered_omitted,
                issues=tuple(issues),
                facet_outcomes=ordered_outcomes,
            )

        # Step 13: profile parameter overrides (profile-owned, FINAL).
        overrides = self._resolve_overrides()

        # Steps 14–16: canonical spec + projection + cross-validation.
        spec = self._build_spec(allocated, overrides, ordered_omitted)
        inputs = self._project_inputs(allocated)
        self._cross_validate(spec, inputs)

        return RealizationResult(
            ready=True,
            spec=spec,
            inputs=inputs,
            parameter_overrides=overrides,
            omitted_optional=ordered_omitted,
            facet_outcomes=ordered_outcomes,
        )

    # --- helpers -----------------------------------------------------------

    def _validate_authority(self) -> None:
        seen: set[str] = set()
        for facet in self.authority.facets:
            if facet.visual_facet_id in seen:
                raise SoloRingError(
                    ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                    "CapturedVisualAuthority contains a duplicate facet.",
                    status_code=500,
                )
            seen.add(facet.visual_facet_id)
            if not facet.items:
                raise SoloRingError(
                    ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                    "CapturedVisualAuthority facet has no captured items.",
                    status_code=500,
                )
            if [it.role for it in facet.items].count("primary") != 1:
                raise SoloRingError(
                    ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                    "CapturedVisualAuthority facet violates the one-primary "
                    "capture invariant.",
                    status_code=500,
                )

    def _validate_channel_contract(self) -> None:
        for channel_key, channel in self.profile.channels.items():
            decl = self.manifest.inputs.get(channel.input_key)
            if decl is None or decl.source is None:
                raise _binding_invalid(
                    f"Profile channel {channel_key!r} input_key "
                    f"{channel.input_key!r} is not a manifest input with a "
                    "realization source."
                )
            if getattr(decl.source, "kind", None) != "realization_channel":
                raise _binding_invalid(
                    f"Profile channel {channel_key!r} input_key "
                    f"{channel.input_key!r} is not declared as a "
                    "realization_channel source."
                )

    def _resolve_overrides(self) -> dict:
        from soloring.workflows.manifest import ParameterDef, _check_type

        overrides: dict = {}
        for name, value in self.profile.parameter_overrides.items():
            decl = self.manifest.parameters.get(name)
            if decl is None:
                raise _binding_invalid(
                    f"Profile parameter override {name!r} is not a "
                    "manifest parameter."
                )
            pdef = ParameterDef(
                name=name, type=decl.type, default=decl.default,
                min=decl.min, max=decl.max,
                enum=tuple(decl.enum) if decl.enum is not None else None,
            )
            _check_type(name, pdef.type, value)
            if pdef.enum is not None and value not in pdef.enum:
                raise _binding_invalid(
                    f"Profile parameter {name!r} value not in enum."
                )
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if pdef.min is not None and value < pdef.min:
                    raise _binding_invalid(
                        f"Profile parameter {name!r} below minimum."
                    )
                if pdef.max is not None and value > pdef.max:
                    raise _binding_invalid(
                        f"Profile parameter {name!r} above maximum."
                    )
            overrides[name] = value
        return overrides

    def _ordered_bindings(self, bindings):
        """§15: required facets first, then optional, each group in exact
        M8 pack order; within a facet, captured item position."""
        return sorted(
            bindings,
            key=lambda pair: (
                0 if pair[0].requirement == "required" else 1,
                _facet_sort_key(pair[0]),
                pair[1].position,
            ),
        )

    def _build_spec(self, allocated, overrides, ordered_omitted) -> dict:
        channels = []
        for channel_key in sorted(self.profile.channels):  # §15 lex order
            bindings = allocated[channel_key]
            if not bindings:
                continue
            channel = self.profile.channels[channel_key]
            binding_entries = []
            for position, (facet, item) in enumerate(
                self._ordered_bindings(bindings)
            ):
                if facet.target_kind == "entity":
                    target = {
                        "kind": "entity",
                        "entity_id": facet.entity_id,
                        "entity_revision_id": facet.entity_revision_id,
                    }
                else:
                    target = {
                        "kind": "feature_value",
                        "feature_id": facet.feature_id,
                        "feature_value_hash": facet.feature_value_hash,
                        "feature_value_json": facet.feature_value_json,
                        "visual_context_entity_revision_id": (
                            facet.visual_context_entity_revision_id
                        ),
                    }
                binding_entries.append({
                    "visual_facet_id": facet.visual_facet_id,
                    "facet_key": facet.facet_key,
                    "required": facet.requirement == "required",
                    "visual_anchor_id": facet.visual_anchor_id,
                    "visual_anchor_revision_id": (
                        facet.visual_anchor_revision_id
                    ),
                    "visual_anchor_snapshot_hash": (
                        facet.visual_anchor_snapshot_hash
                    ),
                    "target": target,
                    "item": {
                        "asset_id": item.asset_id,
                        "blob_hash": item.blob_hash,
                        "role": item.role,
                        "view_key": item.view_key,
                        "source_position": item.position,
                    },
                    "binding_position": position,
                })
            channels.append({
                "channel": channel_key,
                "input_key": channel.input_key,
                "bindings": binding_entries,
            })
        return {
            "schema_version": 1,
            "profile": {
                "id": self.profile.profile_id,
                "version": self.profile.profile_version,
                "hash": self.profile_hash,
            },
            "model": {
                "id": self.profile.model.id,
                "version": self.profile.model.version,
                "execution_model_fingerprint_hash": self.fingerprint_hash,
            },
            "visual_reference_pack_hash": (
                self.authority.visual_reference_pack_hash
            ),
            "parameter_overrides": overrides,
            "channels": channels,
            "omitted_optional": [
                {
                    "visual_facet_id": o.visual_facet_id,
                    "target_kind": o.target_kind,
                    "facet_key": o.facet_key,
                    "reason": o.reason,
                }
                for o in ordered_omitted
            ],
        }

    def _project_inputs(self, allocated) -> tuple:
        projections = []
        # §15 channel order (lexicographic) — the same order the spec
        # emits, so the §18.1 cross-validation compares like-for-like.
        for channel_key in sorted(allocated):
            bindings = allocated[channel_key]
            if not bindings:
                continue
            channel = self.profile.channels[channel_key]
            for position, (_facet, item) in enumerate(
                self._ordered_bindings(bindings)
            ):
                projections.append(RealizationInputProjection(
                    input_key=channel.input_key,
                    position=position,
                    asset_id=item.asset_id,
                    blob_hash=item.blob_hash,
                    reference_role=item.role,
                ))
        return tuple(projections)

    def _cross_validate(self, spec, inputs) -> None:
        """§18.1: the spec's binding projection must equal the emitted
        GenerationInput projection exactly."""
        from soloring.errors import internal_invariant

        expected = [
            (
                channel["input_key"], b["binding_position"],
                b["item"]["asset_id"], b["item"]["blob_hash"],
                b["item"]["role"],
            )
            for channel in spec["channels"]
            for b in channel["bindings"]
        ]
        actual = [
            (p.input_key, p.position, p.asset_id, p.blob_hash,
             p.reference_role)
            for p in inputs
        ]
        if expected != actual:
            raise internal_invariant(
                "RealizationSpec binding projection disagrees with the "
                "realization GenerationInput projection."
            )


def compile_realization(
    *,
    captured_visual_authority: CapturedVisualAuthority,
    profile,
    manifest,
    profile_hash: str | None = None,
    execution_model_fingerprint_hash: str | None = None,
) -> RealizationResult:
    """§20 canonical API. ``profile_hash`` /
    ``execution_model_fingerprint_hash`` fill the spec's identity fields
    from the SAME captured release buffers (§14.1) — the compiler itself
    never reads files."""
    return _Compiler(
        captured_visual_authority, profile, manifest,
        profile_hash, execution_model_fingerprint_hash,
    ).run()
