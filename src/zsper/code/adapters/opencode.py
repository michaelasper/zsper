"""Generate profile-local OpenCode adapter config."""

from __future__ import annotations

from zsper.code.adapters.base import GeneratedAdapter
from zsper.config.model_endpoint import endpoints_for_profile
from zsper.config.writer import LOCAL_SENTINEL_API_KEY, ProfileConfigWriter
from zsper.profiles import Profile


def generate_opencode_adapter(profile: Profile) -> GeneratedAdapter:
    writer = ProfileConfigWriter(profile)
    endpoints = endpoints_for_profile(profile, include_fallback=True)
    primary = endpoints[0]
    config = {
        "agents": {
            "zsper-code": {
                "provider": "zsper-code",
                "model": profile.model_profile,
            }
        },
        "providers": {
            "zsper-code": {
                "package": "@ai-sdk/openai-compatible",
                "base_url": primary.base_url,
                "api_key": LOCAL_SENTINEL_API_KEY,
                "models": {
                    endpoint.model_id: {
                        "context_window": endpoint.context_window,
                        "output_limit": endpoint.output_limit,
                        "tool_support": endpoint.tool_support,
                    }
                    for endpoint in endpoints
                },
            }
        },
    }
    config_path = writer.write_json("opencode/opencode.json", config)
    return GeneratedAdapter(name="opencode", files=[config_path])
