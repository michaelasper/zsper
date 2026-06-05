import json
from pathlib import Path


def test_brain_web_start_script_binds_to_container_interface() -> None:
    package_path = Path("apps") / "brain-web" / "package.json"
    package_json = json.loads(package_path.read_text(encoding="utf-8"))

    assert "--hostname 127.0.0.1" in package_json["scripts"]["dev"]
    assert "--hostname 0.0.0.0" in package_json["scripts"]["start"]
    assert package_json["scripts"]["build"] == "rm -rf .next && next build"
