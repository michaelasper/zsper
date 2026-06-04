import json
import subprocess
from pathlib import Path
from typing import Any

from zsper.cli import app


def test_code_cli_install_commands_write_profile_local_adapters(
    capsys,
    monkeypatch,
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    monkeypatch.setenv("ZSPER_PROFILE_REGISTRY", str(isolated_registry_path))
    root = tmp_path / "work"
    assert app(["profile", "init", "--mode", "work", "--root", str(root)]) == 0
    capsys.readouterr()

    for command, expected in (
        ("install-zed", ["code/zed/settings.json", "code/zed/context_servers.json"]),
        ("install-opencode", ["code/opencode/opencode.json"]),
        (
            "install-pi",
            ["code/pi/pi-provider.yml", "code/pi/AGENTS.md", "code/pi/little-coder.md"],
        ),
    ):
        assert app(["code", command, "--profile", "work"]) == 0
        captured = capsys.readouterr()
        assert f"installed {command.removeprefix('install-')}" in captured.out
        for relative in expected:
            assert (root / relative).is_file(), relative

    assert "OPENAI_API_KEY" not in (root / "code" / "opencode" / "opencode.json").read_text(
        encoding="utf-8"
    )


def test_code_cli_status_and_smoke_use_external_contract(
    capsys,
    monkeypatch,
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    monkeypatch.setenv("ZSPER_PROFILE_REGISTRY", str(isolated_registry_path))
    root = tmp_path / "work"
    assert app(["profile", "init", "--mode", "work", "--root", str(root)]) == 0
    capsys.readouterr()

    def fake_urlopen(request: Any, timeout: float):
        class Response:
            status = 200

            def __enter__(self) -> "Response":
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                if request.full_url.endswith("/models"):
                    return json.dumps({"data": [{"id": "zsper-qwen35-oq6-fp16-mtp-omlx-128k"}]}).encode(
                        "utf-8"
                    )
                return json.dumps({"choices": [{"message": {"content": "OK"}}]}).encode(
                    "utf-8"
                )

        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    assert app(["code", "status", "--profile", "work"]) == 0
    status = capsys.readouterr()
    assert "model server available" in status.out
    assert "work" in status.out

    assert app(["code", "smoke", "--profile", "work"]) == 0
    smoke = capsys.readouterr()
    assert "smoke OK" in smoke.out


def test_code_cli_start_and_stop_delegate_to_llm_server(
    capsys,
    monkeypatch,
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    monkeypatch.setenv("ZSPER_PROFILE_REGISTRY", str(isolated_registry_path))
    monkeypatch.setenv("ZSPER_LLM_SERVER_DIR", str(tmp_path / "llm-server"))
    root = tmp_path / "work"
    assert app(["profile", "init", "--mode", "work", "--root", str(root)]) == 0
    capsys.readouterr()
    calls: list[list[str]] = []

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert app(["code", "start", "--profile", "work"]) == 0
    assert app(["code", "stop", "--profile", "work"]) == 0

    assert calls == [
        ["mise", "-C", str(tmp_path / "llm-server"), "run", "prod-start-zsper"],
        ["mise", "-C", str(tmp_path / "llm-server"), "run", "prod-stop-zsper"],
    ]
