import json
from pathlib import Path

from zsper.code.adapters.opencode import generate_opencode_adapter
from zsper.config.writer import LOCAL_SENTINEL_API_KEY
from zsper.profiles import default_profile


def test_opencode_adapter_writes_local_openai_compatible_provider(
    tmp_path: Path,
) -> None:
    profile = default_profile(mode="work", root=tmp_path / "work")

    generated = generate_opencode_adapter(profile)

    config_path = Path(profile.root) / "code" / "opencode" / "opencode.json"
    assert generated.files == [config_path]
    config = json.loads(config_path.read_text(encoding="utf-8"))

    assert config["agents"]["zsper-code"]["provider"] == "zsper-code"
    provider = config["providers"]["zsper-code"]
    assert provider["package"] == "@ai-sdk/openai-compatible"
    assert provider["base_url"] == "http://127.0.0.1:9127/v1"
    assert provider["api_key"] == LOCAL_SENTINEL_API_KEY
    assert provider["models"][profile.model_profile]["context_window"] == 131072
    assert "OPENAI_API_KEY" not in config_path.read_text(encoding="utf-8")
    assert "sk-" not in config_path.read_text(encoding="utf-8")


def test_opencode_adapter_uses_profile_specific_model_id(tmp_path: Path) -> None:
    profile = default_profile(
        mode="work",
        root=tmp_path / "work",
        overrides={"model_profile": "zsper-custom-code"},
    )

    generate_opencode_adapter(profile)

    config_path = Path(profile.root) / "code" / "opencode" / "opencode.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))

    provider = config["providers"]["zsper-code"]
    assert "zsper-custom-code" in provider["models"]
    assert "zsper-qwen35-oq6-fp16-mtp-omlx-128k" not in provider["models"]
