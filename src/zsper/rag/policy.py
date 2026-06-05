"""RAG network and hosted dependency policy gates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zsper.profiles import Profile
from zsper.security.hosted_dependencies import find_forbidden_hosted_settings
from zsper.security.network_policy import check_network_policy, looks_like_url


HOSTED_RAG_ACTIONS = frozenset(
    {
        "hosted-extraction-api",
        "hosted-model-api",
        "hosted-search-api",
        "model-artifact-download",
    }
)


class RagPolicyError(RuntimeError):
    """Raised when a RAG operation is blocked by profile policy."""


@dataclass(frozen=True)
class RagPolicyGate:
    profile: Profile

    def require_ingest(
        self,
        source: str | Path,
        *,
        user_triggered: bool = False,
        hosted_extraction_api_url: str | None = None,
        hosted_model_api_url: str | None = None,
        model_download_url: str | None = None,
    ) -> None:
        action = "url-ingest" if looks_like_url(source) else "local-file-read"
        self.require_action(source, action=action, user_triggered=user_triggered)
        if hosted_extraction_api_url:
            self.require_hosted_dependency(
                hosted_extraction_api_url,
                action="hosted-extraction-api",
            )
        if hosted_model_api_url:
            self.require_hosted_dependency(
                hosted_model_api_url,
                action="hosted-model-api",
            )
        if model_download_url:
            self.require_hosted_dependency(
                model_download_url,
                action="model-artifact-download",
            )

    def require_search(
        self,
        *,
        searxng_url: str | None = None,
        hosted_search_api_url: str | None = None,
        hosted_model_api_url: str | None = None,
    ) -> None:
        if searxng_url:
            self.require_action(
                searxng_url,
                action="searxng-query",
                local_searxng=True,
            )
        if hosted_search_api_url:
            self.require_hosted_dependency(
                hosted_search_api_url,
                action="hosted-search-api",
            )
        if hosted_model_api_url:
            self.require_hosted_dependency(
                hosted_model_api_url,
                action="hosted-model-api",
            )

    def require_hosted_dependency(self, target: str | Path, *, action: str) -> None:
        if action not in HOSTED_RAG_ACTIONS:
            allowed = ", ".join(sorted(HOSTED_RAG_ACTIONS))
            raise RagPolicyError(
                f"unsupported RAG hosted dependency action: {action}; "
                f"expected one of: {allowed}"
            )
        self.require_action(target, action=action)

    def require_no_hosted_settings(self, settings: Any) -> None:
        findings = sorted(set(find_forbidden_hosted_settings(settings)))
        if findings:
            raise RagPolicyError(
                "forbidden hosted RAG settings: " + ", ".join(findings)
            )

    def require_action(
        self,
        target: str | Path,
        *,
        action: str,
        user_triggered: bool = False,
        local_searxng: bool = False,
    ) -> None:
        decision = check_network_policy(
            self.profile.network_policy,
            target,
            action=action,
            user_triggered=user_triggered,
            local_searxng=local_searxng,
        )
        if not decision.allowed:
            raise RagPolicyError(decision.reason)
