"""FastAPI app factory (plan §3, §99).

M0 surface: a health endpoint, CORS, and SQLite version logging at startup. The
generation worker never runs inside this process (plan §4).
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from soloring.api.errors import register_exception_handlers
from soloring.api.assets import router as assets_router
from soloring.api.blobs import router as blobs_router
from soloring.api.continuity import router as continuity_router
from soloring.api.intra_shot import router as intra_shot_router
from soloring.api.entities import router as entities_router
from soloring.api.generations import router as generations_router
from soloring.api.compositions import router as compositions_router
from soloring.api.production import router as production_router
from soloring.api.projects import router as projects_router
from soloring.api.sequences import router as narrative_router
from soloring.api.references import router as references_router
from soloring.api.realization import router as realization_router
from soloring.api.revisions import router as revisions_router
from soloring.api.shots import router as shots_router
from soloring.api.spatial_worlds import router as spatial_worlds_router
from soloring.api.spatial_tracks import router as spatial_tracks_router
from soloring.api.spatial_plans import router as spatial_plans_router
from soloring.api.production_world import router as production_world_router
from soloring.api.takes import router as takes_router
from soloring.api.visual import router as visual_router
from soloring.api.performance import router as performance_router
from soloring.api.m17b_performance import (router as m17b_performance_router)
from soloring.api.m17c_performance import (router as m17c_performance_router)
from soloring.db.engine import create_soloring_engine, create_session_factory
from soloring.settings import Settings, get_settings

log = logging.getLogger("soloring.api")

_M17C_TRANSITION_ROUTES = {
    ("POST", "/performance-candidates/{candidate_id}/adopt"),
    ("POST", "/performance-revisions/{revision_id}/retarget-candidates"),
}


def _m17b_without_m17c_transition_routes() -> APIRouter:
    """Return M17B routes excluding the two transition paths owned by M17C.

    M17C upgrades those published path/method pairs with PF-03 closure laws.
    Registering both predecessor and upgraded handlers would make runtime route
    selection depend on insertion order while OpenAPI could describe the other
    handler. Filtering at app assembly leaves exactly one public owner without
    mutating the published M17B router module.
    """
    filtered = APIRouter()
    for route in m17b_performance_router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if path is not None and any(
            (method, path) in _M17C_TRANSITION_ROUTES for method in methods
        ):
            continue
        filtered.routes.append(route)
    return filtered


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    engine = create_soloring_engine(settings)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    log.info("SQLite runtime version: %s", sqlite3.sqlite_version)
    try:
        yield
    finally:
        await engine.dispose()


def _install_exact_duration_openapi_maximum(app: FastAPI) -> None:
    """RR23-M17CC-01 (residual completion): the emitted OpenAPI
    document carries the EXACT signed-SQLite integer boundary.

    FastAPI's internal openapi Schema model declares
    ``maximum: float | None`` (verified on the installed 0.142.x
    line), so the default generator coerces the Shot-duration
    integer bound to the nearest IEEE double — the INCLUSIVE
    maximum rounds UP past the runtime boundary
    (float(SQLITE_INT_MAX) == 9223372036854775808.0), publishing
    9223372036854775808 as schema-valid while the endpoint
    rejects it. This wrapper generates FastAPI's ordinary document
    normally, verifies the expected Shot create/PATCH duration_ms
    structure is present (failing LOUDLY on any drift rather than
    quietly publishing an unpatched or mis-patched contract), then
    replaces ONLY that integer branch's rounded maximum with the
    exact Python integer from the ONE storage-domain owner. An
    already-exact integer maximum passes the SAME structural
    verification and is accepted as a verified no-op (RR24: the
    end-of-pass invariant requires exactly two VERIFIED target
    components while allowing zero, one, or two MUTATIONS — the
    hook must not depend on the current generator emitting the
    rounded float). The result is cached in ``app.openapi_schema``
    per the normal FastAPI pattern (subsequent requests reuse the
    corrected document; the wrapper does not re-enter itself). No
    unrelated maximum, response schema, or request model is
    touched."""
    from soloring.api.schemas.shots import (
        CANONICAL_DURATION_INPUT_PATTERN,
    )
    from soloring.domain.storage import SQLITE_INT_MAX

    original_openapi = app.openapi

    def openapi_with_exact_duration_maximum():
        if app.openapi_schema:
            return app.openapi_schema
        document = original_openapi()
        rounded = float(SQLITE_INT_MAX)
        try:
            return _verify_and_patch(document, rounded)
        except Exception:
            # the default generator has already cached its document
            # on app.openapi_schema by now — a refused drift must not
            # leave that unverified document served as if published;
            # every subsequent generation attempt fails loudly too
            app.openapi_schema = None
            raise

    def _verify_and_patch(document, rounded):
        # RR24-M17CC-01: distinguish VERIFIED target components from
        # MUTATED ones — the end-of-pass invariant requires exactly
        # two VERIFIED Shot components while allowing zero, one, or
        # two MUTATIONS (a future/already-exact upstream maximum is
        # a lawful no-op, never a failure; mutation count is never
        # evidence that both target schemas existed)
        verified = 0
        mutated = 0
        components = document.setdefault("components", {}) \
            .setdefault("schemas", {})
        for name, schema in components.items():
            if name not in ("ShotCreate", "ShotPatch"):
                continue
            node = schema.get("properties", {}).get("duration_ms")
            if node is None:
                raise RuntimeError(
                    f"RR23 OpenAPI correction drift: component "
                    f"{name!r} has no duration_ms property — the "
                    "Shot request schema changed; refusing to "
                    "publish an unverified contract")
            branches = node.get("anyOf")
            if not isinstance(branches, list) \
                    or len(branches) != 3:
                raise RuntimeError(
                    f"RR23 OpenAPI correction drift: component "
                    f"{name!r} duration_ms is not the expected "
                    "integer/string/null three-branch contract")
            int_branch = next(
                (b for b in branches if b.get("type") == "integer"),
                None)
            str_branch = next(
                (b for b in branches if b.get("type") == "string"),
                None)
            if int_branch is None or str_branch is None \
                    or not any(b.get("type") == "null"
                               for b in branches):
                raise RuntimeError(
                    f"RR23 OpenAPI correction drift: component "
                    f"{name!r} duration_ms branches are not the "
                    "integer/string/null contract")
            if int_branch.get("minimum") in (0, 0.0) \
                    and int_branch.get("minimum") is not None:
                pass
            else:
                raise RuntimeError(
                    f"RR23 OpenAPI correction drift: component "
                    f"{name!r} duration_ms integer minimum is not 0"
                    f" (got {int_branch.get('minimum')!r})")
            if str_branch.get("pattern") != \
                    CANONICAL_DURATION_INPUT_PATTERN:
                raise RuntimeError(
                    f"RR23 OpenAPI correction drift: component "
                    f"{name!r} duration_ms string branch does not "
                    "carry the canonical bounded decimal pattern")
            maximum = int_branch.get("maximum")
            # the accepted pre-correction values are exactly two:
            # the KNOWN rounded representation of the storage bound
            # (the current generator's float coercion) or the exact
            # integer itself (already-exact upstream output) —
            # never mutate whatever else resembles a duration schema
            if isinstance(maximum, int) and not isinstance(
                    maximum, bool):
                if maximum != SQLITE_INT_MAX:
                    raise RuntimeError(
                        f"RR23 OpenAPI correction drift: component "
                        f"{name!r} duration_ms integer maximum is an "
                        f"unexpected int {maximum!r}")
                # already exact — fully VERIFIED without mutation
            elif maximum == rounded:
                int_branch["maximum"] = SQLITE_INT_MAX
                mutated += 1
            else:
                raise RuntimeError(
                    f"RR23 OpenAPI correction drift: component "
                    f"{name!r} duration_ms integer maximum is not "
                    f"the known rounded storage bound ({rounded!r}) "
                    f"nor the exact integer; got {maximum!r}")
            verified += 1
        if verified != 2:
            raise RuntimeError(
                "RR23 OpenAPI correction drift: expected exactly the "
                "ShotCreate and ShotPatch duration_ms components; "
                f"verified {verified} (mutated {mutated})")
        app.openapi_schema = document
        return document

    app.openapi = openapi_with_exact_duration_maximum


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="SoloRing", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "sqlite_version": sqlite3.sqlite_version}

    # Stable SoloRing error envelope + validation normalization (plan §42, §43).
    register_exception_handlers(app)

    app.include_router(projects_router)
    app.include_router(shots_router)
    app.include_router(references_router)
    app.include_router(revisions_router)
    app.include_router(entities_router)
    app.include_router(narrative_router)
    app.include_router(continuity_router)
    app.include_router(intra_shot_router)
    app.include_router(realization_router)
    app.include_router(assets_router)
    app.include_router(production_router)
    app.include_router(compositions_router)
    app.include_router(blobs_router)
    app.include_router(generations_router)
    app.include_router(takes_router)
    app.include_router(visual_router)
    app.include_router(spatial_worlds_router)
    app.include_router(spatial_tracks_router)
    app.include_router(spatial_plans_router)
    app.include_router(production_world_router)
    app.include_router(performance_router)
    app.include_router(m17c_performance_router)
    app.include_router(_m17b_without_m17c_transition_routes())

    _install_exact_duration_openapi_maximum(app)

    return app


# uvicorn soloring.api.main:app
app = create_app()
