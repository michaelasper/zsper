"""FastAPI error handlers for the Brain API service."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from zsper.brain.api import ApiError


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    del request
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.to_dict()},
    )


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, api_error_handler)
