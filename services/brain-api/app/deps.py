"""Dependency helpers for the Brain API service."""

from __future__ import annotations

import os
from typing import Mapping

from zsper.brain.redis import RedisRuntimeConfig, redis_config_from_env


def get_service_env(environ: Mapping[str, str] | None = None) -> Mapping[str, str]:
    return os.environ if environ is None else environ


def get_profile_id(environ: Mapping[str, str] | None = None) -> str:
    env = get_service_env(environ)
    profile_id = env.get("ZSPER_PROFILE_ID")
    if not profile_id:
        raise RuntimeError("ZSPER_PROFILE_ID is required")
    return profile_id


def get_redis_config(environ: Mapping[str, str] | None = None) -> RedisRuntimeConfig:
    return redis_config_from_env(get_service_env(environ))
