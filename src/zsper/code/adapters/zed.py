"""Generate profile-local Zed adapter config."""

from __future__ import annotations

from zsper.code.adapters.base import GeneratedAdapter
from zsper.config.model_endpoint import endpoints_for_profile
from zsper.config.writer import LOCAL_SENTINEL_API_KEY, ProfileConfigWriter
from zsper.profiles import Profile


def generate_zed_adapter(profile: Profile) -> GeneratedAdapter:
    writer = ProfileConfigWriter(profile)
    endpoints = endpoints_for_profile(profile, include_fallback=True)
    primary = endpoints[0]
    settings = {
        "language_models": {
            "zsper-code": {
                "type": "openai-compatible",
                "base_url": primary.base_url,
                "api_key": LOCAL_SENTINEL_API_KEY,
                "models": [
                    {
                        "model_id": endpoint.model_id,
                        "context_window": endpoint.context_window,
                        "output_limit": endpoint.output_limit,
                        "tool_support": endpoint.tool_support,
                    }
                    for endpoint in endpoints
                ],
            }
        }
    }
    context_servers = {
        "context_servers": {
            "zsper-brain": {
                "command": "zsper",
                "args": ["brain", "context-server", "--profile", profile.root],
                "command_line": f"zsper brain context-server --profile {profile.root}",
            }
        }
    }
    settings_path = writer.write_json("zed/settings.json", settings)
    context_path = writer.write_json("zed/context_servers.json", context_servers)
    return GeneratedAdapter(name="zed", files=[settings_path, context_path])
