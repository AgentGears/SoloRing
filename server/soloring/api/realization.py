"""M9 realization-readiness endpoint (frozen plan §34).

Current inspection ONLY — not a reservation. Evaluates exactly the one
currently configured schema-2 package against one coherent current
M7/M8 read through the ONE compiler. M7/M8 blockers are reported
honestly as issues; package capture-integrity failures preempt (§11.1
Stage 0).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.api.deps import get_session
from soloring.domain.ids import is_uuid
from soloring.errors import ErrorCode, not_found
from soloring.realization.authority import build_captured_authority
from soloring.realization.compiler import compile_realization
from soloring.realization.packages import capture_current_package

router = APIRouter(tags=["realization"])


@router.get("/shots/{shot_id}/realization-readiness")
async def get_realization_readiness(
    shot_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    settings = getattr(request.app.state, "settings", None)
    from soloring.settings import get_settings

    settings = settings or get_settings()

    if not is_uuid(shot_id):
        raise not_found(ErrorCode.SHOT_NOT_FOUND, f"Shot {shot_id} not found.")

    # Stage 0: coherent package capture preempts everything (§11.1).
    package = await capture_current_package(settings)

    from soloring.continuity.snapshots import resolve_working_dependencies
    from soloring.continuity.state import (
        readiness_projection,
        resolve_effective_feature_state,
        resolve_effective_relation_state,
    )
    from soloring.visual.readiness import resolve_visual_readiness

    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN")
        try:
            shot = (
                await conn.execute(
                    __import__("sqlalchemy").text(
                        "SELECT id FROM shots WHERE id = :s "
                        "AND deleted_at IS NULL"
                    ),
                    {"s": shot_id},
                )
            ).first()
            if shot is None:
                raise not_found(
                    ErrorCode.SHOT_NOT_FOUND, f"Shot {shot_id} not found."
                )
            outcome = await resolve_effective_feature_state(conn, shot_id)
            relation_outcome = await resolve_effective_relation_state(
                conn, shot_id
            )
            projection = readiness_projection(outcome, relation_outcome)
            deps = await resolve_working_dependencies(conn, shot_id)
            visual = await resolve_visual_readiness(
                conn, shot_id,
                projection["continuity_state_ready"],
                projection["readiness_issues"],
                deps, outcome.states,
                blob_store=_preview_blob_store(settings),
            )
            await conn.commit()
        except Exception:
            import contextlib as _cl

            with _cl.suppress(Exception):
                await conn.rollback()
            raise

    base = {
        "shot_id": shot_id,
        "package": package.release.release_identity(),
        "model": {
            "id": package.profile.model.id,
            "version": package.profile.model.version,
        },
        "profile": {
            "id": package.profile.profile_id,
            "version": package.profile.profile_version,
            "hash": package.release.realization_profile_hash,
        },
    }

    issues: list[dict] = []
    for m7 in projection["readiness_issues"]:
        issues.append({**m7, "layer": "m7"})
    if not visual.visual_continuity_ready:
        for m8 in visual.issues:
            issues.append({**m8, "layer": "m8"})

    if not projection["continuity_state_ready"] or (
        not visual.visual_continuity_ready
    ):
        return {
            **base,
            "ready": False,
            "visual_reference_pack_hash": None,
            "issues": issues,
            "channels": _channel_rows(package, {}),
            "facet_statuses": [],
            "omitted_optional": [],
        }

    # Same capture-shaped authority value as historical reconstruction
    # (§10.2): pack + requirement map from the SAME coherent read.
    facet_requirements = {
        s.visual_facet_id: s.requirement for s in visual.facet_statuses
    }
    authority = build_captured_authority(
        visual.pack or {"schema_version": 1, "anchors": []},
        facet_requirements,
    )

    if not authority.facets:
        # Empty effective M8 authority: no realization content (§11.2).
        return {
            **base,
            "ready": True,
            "visual_reference_pack_hash": None,
            "issues": [],
            "channels": _channel_rows(package, {}),
            "facet_statuses": [],
            "omitted_optional": [],
        }

    result = compile_realization(
        captured_visual_authority=authority,
        profile=package.profile,
        manifest=package.manifest_v2,
        profile_hash=package.release.realization_profile_hash,
        execution_model_fingerprint_hash=(
            package.release.execution_model_fingerprint_hash
        ),
    )

    return {
        **base,
        "ready": result.ready,
        "visual_reference_pack_hash": (
            result.spec["visual_reference_pack_hash"] if result.spec
            else authority.visual_reference_pack_hash
        ),
        "issues": [
            {**i, "layer": "m9"} for i in result.issues
        ] if not result.ready else [],
        "channels": _channel_rows(package, _channel_usage(result)),
        "facet_statuses": _facet_status_rows(authority, result, package),
        "omitted_optional": [
            {
                "visual_facet_id": o.visual_facet_id,
                "target_kind": o.target_kind,
                "facet_key": o.facet_key,
                "reason": o.reason,
            }
            for o in result.omitted_optional
        ],
    }


def _preview_blob_store(settings):
    from soloring.assets.blob_store import BlobStore

    return BlobStore(settings)


def _channel_usage(result) -> dict[str, int]:
    usage: dict[str, int] = {}
    if result.spec:
        for channel in result.spec["channels"]:
            usage[channel["channel"]] = len(channel["bindings"])
    return usage


def _channel_rows(package, usage: dict[str, int]) -> list[dict]:
    rows = []
    for key in sorted(package.profile.channels):
        channel = package.profile.channels[key]
        used = usage.get(key, 0)
        rows.append({
            "channel": key,
            "input_key": channel.input_key,
            "min_items": channel.min_items,
            "max_items": channel.max_items,
            "used_items": used,
            "active": used > 0,
        })
    return rows


def _facet_status_rows(authority, result, package) -> list[dict]:
    """§34 facet_statuses: one row per applicable captured facet in
    canonical order; selected rows carry the server-selected items;
    blocked required rows carry the exact blocking code."""
    selected: dict[str, dict] = {}
    if result.spec:
        for channel in result.spec["channels"]:
            for b in channel["bindings"]:
                selected[b["visual_facet_id"]] = {
                    "channel": channel["channel"],
                    "input_key": channel["input_key"],
                    "binding": b,
                }
    issue_by_facet: dict[str, dict] = {}
    channel_issue: dict[str, dict] = {}
    for issue in result.issues:
        if issue.get("visual_facet_id"):
            issue_by_facet[issue["visual_facet_id"]] = issue
        elif issue.get("channel"):
            channel_issue[issue["channel"]] = issue
    omitted_by_facet = {
        o.visual_facet_id: o for o in result.omitted_optional
    }
    # Channel of a min-blocked facet for issue attribution.
    channel_of_facet = {
        b["visual_facet_id"]: c["channel"]
        for c in (result.spec or {}).get("channels", [])
        for b in c["bindings"]
    }

    rows = []
    first_code = result.first_issue_code()
    for facet in authority.facets:
        row = {
            "visual_facet_id": facet.visual_facet_id,
            "target_kind": facet.target_kind,
            "facet_key": facet.facet_key,
            "requirement": facet.requirement,
        }
        if facet.visual_facet_id in selected:
            entry = selected[facet.visual_facet_id]
            b = entry["binding"]
            row.update({
                "status": "selected",
                "channel": entry["channel"],
                "input_key": entry["input_key"],
                "selected_items": [b["item"]],
                "reason": None,
                "issue_code": None,
            })
        elif facet.requirement == "required":
            issue = issue_by_facet.get(facet.visual_facet_id)
            if issue is None and channel_issue:
                # Attribute channel-level blockers to the required facets
                # allocated to that channel (§12.3 fires post-allocation).
                for ckey, ci in channel_issue.items():
                    if channel_of_facet.get(facet.visual_facet_id) == ckey:
                        issue = ci
                        break
            code = issue["error_code"] if issue else first_code
            row.update({
                "status": "required_blocked",
                "channel": None,
                "input_key": None,
                "selected_items": [],
                "reason": None,
                "issue_code": code,
            })
        else:
            o = omitted_by_facet.get(facet.visual_facet_id)
            row.update({
                "status": "optional_omitted",
                "channel": None,
                "input_key": None,
                "selected_items": [],
                "reason": o.reason if o else "no_matching_rule",
                "issue_code": None,
            })
        rows.append(row)
    return rows
