from pathlib import Path

from zsper.code.adapters.pi import generate_pi_adapter
from zsper.config.writer import LOCAL_SENTINEL_API_KEY
from zsper.profiles import default_profile


def test_pi_adapter_writes_provider_yaml_and_little_coder_guidance(
    tmp_path: Path,
) -> None:
    profile = default_profile(mode="work", root=tmp_path / "work")

    generated = generate_pi_adapter(profile)

    pi_root = Path(profile.root) / "code" / "pi"
    provider_path = pi_root / "pi-provider.yml"
    agents_path = pi_root / "AGENTS.md"
    little_coder_path = pi_root / "little-coder.md"
    assert generated.files == [provider_path, agents_path, little_coder_path]

    provider = provider_path.read_text(encoding="utf-8")
    assert "type: openai-compatible" in provider
    assert "base_url: http://127.0.0.1:9127/v1" in provider
    assert f"api_key: {LOCAL_SENTINEL_API_KEY}" in provider
    assert f"model_id: {profile.model_profile}" in provider
    assert str(tmp_path / "work") in provider

    agents = agents_path.read_text(encoding="utf-8")
    little_coder = little_coder_path.read_text(encoding="utf-8")
    combined = f"{agents}\n{little_coder}".lower()
    for phrase in (
        "local model",
        "short loops",
        "explicit file reads",
        "small diffs",
        "deterministic checks",
        "conservative task expansion",
        "global shell mutation",
    ):
        assert phrase in combined
