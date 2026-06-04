"""Generate profile-local Pi provider package."""

from __future__ import annotations

from zsper.code.adapters.base import GeneratedAdapter
from zsper.config.model_endpoint import endpoints_for_profile
from zsper.config.writer import LOCAL_SENTINEL_API_KEY, ProfileConfigWriter
from zsper.profiles import Profile


AGENTS_GUIDANCE = """# Zsper Pi Local Agent Guidance

Use the local model endpoint configured in pi-provider.yml.
Keep short loops, explicit file reads, small diffs, deterministic checks, and
conservative task expansion. Do not perform global shell mutation.
"""

LITTLE_CODER_GUIDANCE = """# little-coder

This profile is tuned for a local model. Prefer narrow tasks, explicit file
reads, small diffs, deterministic checks, and conservative task expansion.
Never rely on global shell mutation for project state.
"""


def generate_pi_adapter(profile: Profile) -> GeneratedAdapter:
    writer = ProfileConfigWriter(profile)
    endpoint = endpoints_for_profile(profile)[0]
    provider_path = writer.write_yaml(
        "pi/pi-provider.yml",
        {
            "provider": {
                "type": "openai-compatible",
                "base_url": endpoint.base_url,
                "api_key": LOCAL_SENTINEL_API_KEY,
                "model_id": endpoint.model_id,
                "context_window": endpoint.context_window,
                "profile_root": profile.root,
            }
        },
    )
    agents_path = writer.write_text("pi/AGENTS.md", AGENTS_GUIDANCE)
    little_coder_path = writer.write_text("pi/little-coder.md", LITTLE_CODER_GUIDANCE)
    return GeneratedAdapter(
        name="pi",
        files=[provider_path, agents_path, little_coder_path],
    )
