import json
from pathlib import Path

from zsper.cli import app
from zsper.code.adapters.zed import generate_zed_adapter
from zsper.profiles import initialize_profile


def _init_profile(
    mode: str,
    root: Path,
    isolated_registry_path: Path,
    monkeypatch,
    *,
    network_policy: str | None = None,
):
    monkeypatch.setenv("ZSPER_PROFILE_REGISTRY", str(isolated_registry_path))
    return initialize_profile(
        mode=mode,
        root=root,
        registry_path=isolated_registry_path,
        network_policy=network_policy,
    )


def test_context_server_command_returns_profile_scoped_metadata(
    capsys,
    monkeypatch,
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = _init_profile(
        "work",
        tmp_path / "work",
        isolated_registry_path,
        monkeypatch,
    )

    assert app(["brain", "context-server", "--profile", "work"]) == 0

    metadata = json.loads(capsys.readouterr().out)
    assert metadata == {
        "schema_version": 1,
        "server": "zsper-brain-context",
        "status": "ready",
        "transport": "stdio",
        "endpoint": "stdio://zsper-brain-context",
        "profile": {
            "id": "work",
            "name": "work",
            "mode": "work",
            "root": profile.root,
            "database_name": "zsper_work",
            "network_policy": "local-first",
            "model_profile": profile.model_profile,
            "embedding_profile": profile.embedding_profile,
        },
        "capabilities": {
            "metadata": True,
            "retrieval": False,
            "tools": [],
        },
    }


def test_context_server_resolves_profile_roots(
    capsys,
    monkeypatch,
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = _init_profile(
        "personal",
        tmp_path / "personal",
        isolated_registry_path,
        monkeypatch,
    )

    assert app(["brain", "context-server", "--profile", profile.root]) == 0

    metadata = json.loads(capsys.readouterr().out)
    assert metadata["profile"]["id"] == "personal"
    assert metadata["profile"]["root"] == profile.root
    assert metadata["profile"]["database_name"] == "zsper_personal"


def test_context_server_refuses_offline_disallowed_network_endpoint(
    capsys,
    monkeypatch,
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    _init_profile(
        "air",
        tmp_path / "air",
        isolated_registry_path,
        monkeypatch,
        network_policy="offline",
    )

    assert (
        app(
            [
                "brain",
                "context-server",
                "--profile",
                "air",
                "--endpoint",
                "https://example.com/context",
            ]
        )
        == 1
    )

    captured = capsys.readouterr()
    assert "offline policy blocks localhost-service" in captured.err
    assert captured.out == ""


def test_zed_context_server_args_resolve_to_existing_cli_command(
    capsys,
    monkeypatch,
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = _init_profile(
        "work",
        tmp_path / "work",
        isolated_registry_path,
        monkeypatch,
    )
    generate_zed_adapter(profile)
    config_path = Path(profile.root) / "code" / "zed" / "context_servers.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    args = config["context_servers"]["zsper-brain"]["args"]

    assert app(args) == 0

    metadata = json.loads(capsys.readouterr().out)
    assert metadata["server"] == "zsper-brain-context"
    assert metadata["profile"]["id"] == "work"
