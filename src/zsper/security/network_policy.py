"""Network policy checks for local-first and offline profile states."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


HOSTED_ACTIONS = frozenset(
    {
        "hosted-model-api",
        "hosted-search-api",
        "hosted-extraction-api",
        "model-artifact-download",
    }
)
LOCALHOST_NAMES = frozenset(
    {
        "localhost",
        "127.0.0.1",
        "::1",
        "host.docker.internal",
        "host.containers.internal",
        "searxng",
        "honcho",
        "brain-api",
        "brain-web",
    }
)


class NetworkPolicyError(RuntimeError):
    """Raised when a profile network policy blocks an action."""


@dataclass(frozen=True)
class NetworkDecision:
    allowed: bool
    reason: str

    def raise_for_status(self) -> None:
        if not self.allowed:
            raise NetworkPolicyError(self.reason)


def looks_like_url(target: str | Path) -> bool:
    target = str(target)
    parsed = urlparse(target)
    return parsed.scheme in {"http", "https"}


def _is_localhost_url(target: str) -> bool:
    parsed = urlparse(target)
    return parsed.scheme in {"http", "https"} and parsed.hostname in LOCALHOST_NAMES


def _allow(reason: str) -> NetworkDecision:
    return NetworkDecision(allowed=True, reason=reason)


def _deny(policy: str, action: str) -> NetworkDecision:
    return NetworkDecision(
        allowed=False,
        reason=f"{policy} policy blocks {action}",
    )


def check_network_policy(
    network_policy: str,
    target: str | Path,
    *,
    action: str,
    user_triggered: bool = False,
    local_searxng: bool = False,
    plugin_policy_enabled: bool = False,
) -> NetworkDecision:
    target_text = str(target)

    if network_policy == "offline":
        if action == "local-file-read" and not looks_like_url(target_text):
            return _allow("offline policy allows local file reads")
        if action == "localhost-service" and _is_localhost_url(target_text):
            return _allow("offline policy allows localhost services")
        return _deny("offline", action)

    if network_policy != "local-first":
        return _deny(network_policy, action)

    if action == "local-file-read" and not looks_like_url(target_text):
        return _allow("local-first policy allows local file reads")
    if action == "localhost-service" and _is_localhost_url(target_text):
        return _allow("local-first policy allows localhost services")
    if action == "url-ingest" and user_triggered:
        return _allow("local-first policy allows explicit web capture")
    if action == "searxng-query" and local_searxng and _is_localhost_url(target_text):
        return _allow("local-first policy allows local SearXNG")
    if action == "plugin-network" and plugin_policy_enabled:
        return _allow("local-first policy allows enabled plugin network access")
    if action in HOSTED_ACTIONS or action == "plugin-network":
        return _deny("local-first", action)

    return _deny("local-first", action)
