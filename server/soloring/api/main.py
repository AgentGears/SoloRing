"""FastAPI app factory (plan §3, §99).

M0 surface: a health endpoint, CORS, and SQLite version logging at startup. The
generation worker never runs inside this process (plan §4).
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from soloring.api.errors import register_exception_handlers
from soloring.api.assets import router as assets_router
from soloring.api.blobs import router as blobs_router
from soloring.api.continuity import router as continuity_router
from soloring.api.entities import router as entities_router
from soloring.api.generations import router as generations_router
from soloring.api.projects import router as projects_router
from soloring.api.sequences import router as narrative_router
from soloring.api.references import router as references_router
from soloring.api.revisions import router as revisions_router
from soloring.api.shots import router as shots_router
from soloring.api.takes import router as takes_router
from soloring.db.engine import create_soloring_engine, create_session_factory
from soloring.settings import Settings, get_settings

log = logging.getLogger("soloring.api")


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
    app.include_router(assets_router)
    app.include_router(blobs_router)
    app.include_router(generations_router)
    app.include_router(takes_router)

    return app


# uvicorn soloring.api.main:app
app = create_app()
