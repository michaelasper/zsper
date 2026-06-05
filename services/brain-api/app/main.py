"""FastAPI application factory for the profile-aware Brain API."""

from __future__ import annotations

from typing import Mapping

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.errors import install_error_handlers
from app.routes import citations, documents, health, search, settings, status
from zsper.brain.api import DEFAULT_LOCAL_CORS_ORIGINS, DefaultServiceProbes, ServiceProbes


def create_app(
    *,
    environ: Mapping[str, str] | None = None,
    service_probes: ServiceProbes | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Zsper Brain API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.environ = environ
    app.state.service_probes = service_probes or DefaultServiceProbes()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(DEFAULT_LOCAL_CORS_ORIGINS),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "X-Zsper-Profile",
            "X-Zsper-Profile-Id",
            "X-Zsper-Profile-Root",
        ],
    )
    install_error_handlers(app)
    app.include_router(citations.router)
    app.include_router(documents.router)
    app.include_router(health.router)
    app.include_router(search.router)
    app.include_router(status.router)
    app.include_router(settings.router)
    return app


app = create_app()
