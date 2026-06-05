"""Dependency helpers for the Brain API service."""

from __future__ import annotations

import os
from typing import Mapping

from fastapi import Depends, Request

from zsper.brain.api import (
    ApiProfileContext,
    DatabaseRuntimeConfig,
    ServiceProbes,
    database_config_from_env,
    resolve_api_profile_context,
)
from zsper.brain.redis import RedisRuntimeConfig, redis_config_from_env


def get_service_env(environ: Mapping[str, str] | None = None) -> Mapping[str, str]:
    return os.environ if environ is None else environ


def get_request_service_env(request: Request) -> Mapping[str, str]:
    app_env = getattr(request.app.state, "environ", None)
    return get_service_env(app_env)


def get_profile_id(environ: Mapping[str, str] | None = None) -> str:
    env = get_service_env(environ)
    profile_id = env.get("ZSPER_PROFILE_ID")
    if not profile_id:
        raise RuntimeError("ZSPER_PROFILE_ID is required")
    return profile_id


def get_redis_config(environ: Mapping[str, str] | None = None) -> RedisRuntimeConfig:
    return redis_config_from_env(get_service_env(environ))


def get_profile_context(request: Request) -> ApiProfileContext:
    return resolve_api_profile_context(
        get_request_service_env(request),
        request_profile_id=(
            request.headers.get("X-Zsper-Profile-Id")
            or request.headers.get("X-Zsper-Profile")
        ),
        request_profile_root=request.headers.get("X-Zsper-Profile-Root"),
    )


def get_database_config(
    context: ApiProfileContext = Depends(get_profile_context),
) -> DatabaseRuntimeConfig:
    return context.database


def get_redis_runtime_config(
    context: ApiProfileContext = Depends(get_profile_context),
) -> RedisRuntimeConfig:
    return context.redis


def get_service_probes(request: Request) -> ServiceProbes:
    return request.app.state.service_probes
