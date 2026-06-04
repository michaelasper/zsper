import json
from pathlib import Path

from zsper.code.adapters.zed import generate_zed_adapter
from zsper.config.writer import LOCAL_SENTINEL_API_KEY
from zsper.profiles import default_profile


def test_zed_adapter_writes_profile_local_settings_and_context_server(
    tmp_path: Path,
) -> None:
    profile = default_profile(mode="work", root=tmp_path / "work")

    generated = generate_zed_adapter(profile)

    settings_path = Path(profile.root) / "code" / "zed" / "settings.json"
    context_path = Path(profile.root) / "code" / "zed" / "context_servers.json"
    assert generated.files == [settings_path, context_path]

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    provider = settings["language_models"]["zsper-code"]
    assert provider["type"] == "openai-compatible"
    assert provider["base_url"] == "http://127.0.0.1:9127/v1"
    assert provider["api_key"] == LOCAL_SENTINEL_API_KEY
    assert provider["models"][0]["model_id"] == profile.model_profile
    assert "huggingface.co" not in settings_path.read_text(encoding="utf-8").lower()

    context_servers = json.loads(context_path.read_text(encoding="utf-8"))
    brain_server = context_servers["context_servers"]["zsper-brain"]
    assert brain_server["command"] == "zsper"
    assert brain_server["args"] == ["brain", "context-server", "--profile", profile.root]
    assert brain_server["command_line"].startswith("zsper brain context-server")


def test_personal_zed_adapter_includes_long_context_fallback(tmp_path: Path) -> None:
    profile = default_profile(mode="personal", root=tmp_path / "personal")

    generate_zed_adapter(profile)

    settings = json.loads(
        (Path(profile.root) / "code" / "zed" / "settings.json").read_text(
            encoding="utf-8"
        )
    )
    models = settings["language_models"]["zsper-code"]["models"]
    assert [model["model_id"] for model in models] == [
        profile.model_profile,
        profile.long_context_fallback,
    ]
