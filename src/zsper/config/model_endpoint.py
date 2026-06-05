"""OpenAI-compatible model endpoint records."""

from __future__ import annotations

from dataclasses import dataclass

from zsper.profiles import Profile


PRIMARY_MODEL_ID = "zsper-qwen35-oq6-fp16-mtp-omlx-128k"
LONG_CONTEXT_MODEL_ID = "zsper-qwen35-oq6-omlx-256k"
AIR_MODEL_ID = "zsper-air-gemma4-12b-it-6bit-128k"
LOCAL_BASE_URL = "http://127.0.0.1:9127/v1"


@dataclass(frozen=True)
class ModelEndpoint:
    provider_id: str
    base_url: str
    model_id: str
    context_window: int
    output_limit: int
    tool_support: bool
    health_path: str = "/models"

    @classmethod
    def primary(cls, model_id: str = PRIMARY_MODEL_ID) -> "ModelEndpoint":
        return cls(
            provider_id="zsper-code",
            base_url=LOCAL_BASE_URL,
            model_id=model_id,
            context_window=131072,
            output_limit=4096,
            tool_support=True,
        )

    @classmethod
    def long_context(cls, model_id: str = LONG_CONTEXT_MODEL_ID) -> "ModelEndpoint":
        return cls(
            provider_id="zsper-code-long",
            base_url=LOCAL_BASE_URL,
            model_id=model_id,
            context_window=262144,
            output_limit=4096,
            tool_support=True,
        )

    @classmethod
    def air(cls, model_id: str = AIR_MODEL_ID) -> "ModelEndpoint":
        return cls(
            provider_id="zsper-air-code",
            base_url=LOCAL_BASE_URL,
            model_id=model_id,
            context_window=131072,
            output_limit=4096,
            tool_support=True,
        )

    @property
    def health_url(self) -> str:
        return f"{self.base_url}{self.health_path}"

    @property
    def chat_completions_url(self) -> str:
        return f"{self.base_url}/chat/completions"

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "base_url": self.base_url,
            "model_id": self.model_id,
            "context_window": self.context_window,
            "output_limit": self.output_limit,
            "tool_support": self.tool_support,
            "health_path": self.health_path,
        }


def endpoints_for_profile(
    profile: Profile,
    *,
    include_fallback: bool = False,
) -> list[ModelEndpoint]:
    if profile.mode == "air-offline":
        return [ModelEndpoint.air(model_id=profile.model_profile)]

    endpoints = [ModelEndpoint.primary(model_id=profile.model_profile)]
    if include_fallback and profile.long_context_fallback:
        endpoints.append(
            ModelEndpoint.long_context(model_id=profile.long_context_fallback)
        )
    return endpoints
