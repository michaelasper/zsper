import subprocess
from pathlib import Path
from typing import Any

from zsper.brain.api import ComponentStatus
from zsper.cli import app


class FakeServiceProbes:
    def __init__(self, failures: dict[str, str] | None = None) -> None:
        self.failures = failures or {}
        self.http_urls: list[tuple[str, str]] = []

    def check_database(self, database) -> ComponentStatus:
        return self._result("database", {"dsn": database.redacted_dsn})

    def check_redis(self, redis) -> ComponentStatus:
        return self._result("redis", {"url": redis.url})

    def check_http(self, component: str, url: str) -> ComponentStatus:
        self.http_urls.append((component, url))
        return self._result(component, {"url": url})

    def _result(self, component: str, details: dict[str, str]) -> ComponentStatus:
        if component in self.failures:
            return ComponentStatus(
                status="fail",
                message=self.failures[component],
                details=details,
            )
        return ComponentStatus(
            status="pass",
            message=f"{component} reachable",
            details=details,
        )


def _init_profile(
    capsys,
    monkeypatch,
    tmp_path: Path,
    isolated_registry_path: Path,
) -> Path:
    monkeypatch.setenv("ZSPER_PROFILE_REGISTRY", str(isolated_registry_path))
    root = tmp_path / "work"
    assert app(["profile", "init", "--mode", "work", "--root", str(root)]) == 0
    capsys.readouterr()
    return root


def test_brain_up_renders_profile_files_and_starts_compose_without_model_serving(
    capsys,
    monkeypatch,
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    root = _init_profile(capsys, monkeypatch, tmp_path, isolated_registry_path)
    calls: list[dict[str, Any]] = []

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append({"args": args, "kwargs": kwargs})
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="started\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert app(["brain", "up", "--profile", "work"]) == 0

    captured = capsys.readouterr()
    assert "brain services started for work" in captured.out
    assert calls == [
        {
            "args": [
                "docker",
                "compose",
                "--env-file",
                str(root / "brain" / ".env"),
                "-f",
                str(root / "brain" / "docker-compose.yml"),
                "up",
                "-d",
            ],
            "kwargs": {
                "cwd": root / "brain",
                "capture_output": True,
                "text": True,
            },
        }
    ]

    compose_path = root / "brain" / "docker-compose.yml"
    env_path = root / "brain" / ".env"
    schema_path = root / "brain" / "schema.sql"
    assert compose_path.is_file()
    assert env_path.is_file()
    assert schema_path.is_file()

    rendered = "\n".join(
        (
            compose_path.read_text(encoding="utf-8"),
            env_path.read_text(encoding="utf-8"),
        )
    ).lower()
    assert "llm-server" not in rendered
    assert "model-serving" not in rendered
    assert "omlx" not in rendered
    assert "llm-server" not in " ".join(calls[0]["args"]).lower()


def test_brain_down_stops_compose_services(
    capsys,
    monkeypatch,
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    root = _init_profile(capsys, monkeypatch, tmp_path, isolated_registry_path)
    calls: list[list[str]] = []

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        del kwargs
        calls.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="stopped\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert app(["brain", "down", "--profile", "work"]) == 0

    captured = capsys.readouterr()
    assert "brain services stopped for work" in captured.out
    assert calls == [
        [
            "docker",
            "compose",
            "--env-file",
            str(root / "brain" / ".env"),
            "-f",
            str(root / "brain" / "docker-compose.yml"),
            "down",
        ]
    ]


def test_brain_status_reports_profile_scoped_component_statuses(
    capsys,
    monkeypatch,
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    _init_profile(capsys, monkeypatch, tmp_path, isolated_registry_path)
    probes = FakeServiceProbes()

    from zsper.brain import commands as brain_commands

    monkeypatch.setattr(brain_commands, "DefaultServiceProbes", lambda: probes)

    assert app(["brain", "status", "--profile", "work"]) == 0

    captured = capsys.readouterr()
    assert "brain status for work: pass" in captured.out
    assert "DB: pass" in captured.out
    assert "API: pass" in captured.out
    assert "web: pass" in captured.out
    assert "SearXNG: pass" in captured.out
    assert "Honcho: pass" in captured.out
    assert "local model endpoint: pass" in captured.out
    assert ("searxng", "http://127.0.0.1:7424") in probes.http_urls
    assert ("honcho", "http://127.0.0.1:7425") in probes.http_urls
    assert ("brain_api", "http://127.0.0.1:7420") in probes.http_urls
    assert ("web_ui", "http://127.0.0.1:7421") in probes.http_urls
    assert ("local_model_models", "http://127.0.0.1:9127/v1/models") in probes.http_urls
