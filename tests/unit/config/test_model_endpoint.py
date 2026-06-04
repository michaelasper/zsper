from pathlib import Path

from zsper.config.model_endpoint import (
    AIR_MODEL_ID,
    LONG_CONTEXT_MODEL_ID,
    PRIMARY_MODEL_ID,
    ModelEndpoint,
    endpoints_for_profile,
)
from zsper.profiles import default_profile


def test_primary_model_endpoint_serializes_to_openai_compatible_record() -> None:
    endpoint = ModelEndpoint.primary()

    assert endpoint.to_dict() == {
        "provider_id": "zsper-code",
        "base_url": "http://127.0.0.1:9127/v1",
        "model_id": PRIMARY_MODEL_ID,
        "context_window": 131072,
        "output_limit": 4096,
        "tool_support": True,
        "health_path": "/models",
    }
    assert endpoint.health_url == "http://127.0.0.1:9127/v1/models"


def test_personal_profile_can_expose_long_context_fallback(tmp_path: Path) -> None:
    profile = default_profile(mode="personal", root=tmp_path / "personal")

    endpoints = endpoints_for_profile(profile, include_fallback=True)

    assert [endpoint.provider_id for endpoint in endpoints] == [
        "zsper-code",
        "zsper-code-long",
    ]
    assert [endpoint.model_id for endpoint in endpoints] == [
        PRIMARY_MODEL_ID,
        LONG_CONTEXT_MODEL_ID,
    ]
    assert endpoints[1].context_window == 262144


def test_air_offline_profile_uses_air_endpoint(tmp_path: Path) -> None:
    profile = default_profile(mode="air-offline", root=tmp_path / "air")

    endpoints = endpoints_for_profile(profile)

    assert len(endpoints) == 1
    assert endpoints[0].provider_id == "zsper-air-code"
    assert endpoints[0].model_id == AIR_MODEL_ID
    assert endpoints[0].context_window == 131072
