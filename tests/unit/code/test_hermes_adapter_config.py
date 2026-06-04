import json
from pathlib import Path

from zsper.code.adapters.hermes import generate_hermes_adapter
from zsper.profiles import default_profile


def test_hermes_adapter_writes_optional_launcher_profile_under_profile_root(
    tmp_path: Path,
) -> None:
    profile = default_profile(mode="work", root=tmp_path / "work")

    generated = generate_hermes_adapter(profile)

    config_path = Path(profile.root) / "code" / "hermes" / "launcher-profile.json"
    assert generated.files == [config_path]
    config = json.loads(config_path.read_text(encoding="utf-8"))

    assert config["name"] == "zsper-code"
    assert config["optional"] is True
    assert config["purpose"] == "launch-oriented"
    assert config["state_owner"] == "zsper-orchestrator"
    assert config["endpoint"]["base_url"] == "http://127.0.0.1:9127/v1"
    assert config["endpoint"]["model_id"] == profile.model_profile
