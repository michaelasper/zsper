"""Generate optional Hermes launcher profile config."""

from __future__ import annotations

from zsper.code.adapters.base import GeneratedAdapter
from zsper.config.model_endpoint import endpoints_for_profile
from zsper.config.writer import ProfileConfigWriter
from zsper.profiles import Profile


def generate_hermes_adapter(profile: Profile) -> GeneratedAdapter:
    writer = ProfileConfigWriter(profile)
    endpoint = endpoints_for_profile(profile)[0]
    config_path = writer.write_json(
        "hermes/launcher-profile.json",
        {
            "name": "zsper-code",
            "optional": True,
            "purpose": "launch-oriented",
            "state_owner": "zsper-orchestrator",
            "endpoint": {
                "provider_id": endpoint.provider_id,
                "base_url": endpoint.base_url,
                "model_id": endpoint.model_id,
                "context_window": endpoint.context_window,
            },
        },
    )
    return GeneratedAdapter(name="hermes", files=[config_path])
