"""Stdio placeholder for the Brain context server contract."""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from typing import Any
from urllib.parse import urlparse

from zsper.profiles import Profile, ProfileError, resolve_profile
from zsper.security.network_policy import (
    NetworkPolicyError,
    check_network_policy,
    looks_like_url,
)


CONTEXT_SERVER_SCHEMA_VERSION = 1
CONTEXT_SERVER_NAME = "zsper-brain-context"
DEFAULT_CONTEXT_SERVER_ENDPOINT = f"stdio://{CONTEXT_SERVER_NAME}"


class ContextServerError(RuntimeError):
    """Raised when the context server cannot start with the requested contract."""


def _transport_for_endpoint(endpoint: str) -> str:
    if endpoint.startswith("stdio://"):
        return "stdio"
    parsed = urlparse(endpoint)
    if parsed.scheme in {"http", "https"}:
        return "http"
    raise ContextServerError(
        "context server endpoint must be stdio:// or an http(s) localhost URL"
    )


def _ensure_endpoint_allowed(profile: Profile, endpoint: str) -> None:
    if endpoint.startswith("stdio://"):
        return
    if not looks_like_url(endpoint):
        raise ContextServerError(
            "context server endpoint must be stdio:// or an http(s) localhost URL"
        )

    decision = check_network_policy(
        profile.network_policy,
        endpoint,
        action="localhost-service",
    )
    decision.raise_for_status()


def build_context_server_metadata(
    profile: Profile,
    *,
    endpoint: str = DEFAULT_CONTEXT_SERVER_ENDPOINT,
) -> dict[str, Any]:
    """Return the stable metadata contract emitted by the context server stub."""
    _ensure_endpoint_allowed(profile, endpoint)
    transport = _transport_for_endpoint(endpoint)
    return {
        "schema_version": CONTEXT_SERVER_SCHEMA_VERSION,
        "server": CONTEXT_SERVER_NAME,
        "status": "ready",
        "transport": transport,
        "endpoint": endpoint,
        "profile": {
            "id": profile.name,
            "name": profile.name,
            "mode": profile.mode,
            "root": profile.root,
            "database_name": profile.database_name,
            "network_policy": profile.network_policy,
            "model_profile": profile.model_profile,
            "embedding_profile": profile.embedding_profile,
        },
        "capabilities": {
            "metadata": True,
            "retrieval": False,
            "tools": [],
        },
    }


def metadata_for_profile_ref(
    profile_ref: str | None,
    *,
    endpoint: str = DEFAULT_CONTEXT_SERVER_ENDPOINT,
) -> dict[str, Any]:
    profile = resolve_profile(profile_ref)
    return build_context_server_metadata(profile, endpoint=endpoint)


def command(namespace: Namespace) -> int:
    endpoint = namespace.endpoint or DEFAULT_CONTEXT_SERVER_ENDPOINT
    try:
        metadata = metadata_for_profile_ref(namespace.profile, endpoint=endpoint)
    except (ContextServerError, NetworkPolicyError, ProfileError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(metadata, sort_keys=True))
    return 0
