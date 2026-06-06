import json
import os
import signal
import subprocess
from pathlib import Path
from typing import Any

from zsper.code.omlx_launcher import OMLXLauncher
from zsper.config.model_endpoint import ModelEndpoint
from zsper.profiles import default_profile


def _omlx_command(endpoint: ModelEndpoint | None = None) -> list[str]:
    endpoint = endpoint or ModelEndpoint.primary()
    return [
        "omlx",
        "serve",
        "--model",
        endpoint.model_id,
        "--host",
        "127.0.0.1",
        "--port",
        "9127",
        "--api",
        "openai",
    ]


def _write_launch_record(
    profile,
    *,
    pid: int,
    endpoint: ModelEndpoint | None = None,
) -> Path:
    endpoint = endpoint or ModelEndpoint.primary()
    runtime_dir = Path(profile.root) / "runtime" / "code"
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "omlx.pid").write_text(f"{pid}\n", encoding="utf-8")
    (runtime_dir / "omlx-launch.json").write_text(
        json.dumps(
            {
                "pid": pid,
                "command": _omlx_command(endpoint),
                "model_id": endpoint.model_id,
                "base_url": endpoint.base_url,
                "started_at": "2026-06-05T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    return runtime_dir


class FakeHTTPResponse:
    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self.payload = payload
        self.status = status

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class FakeCompletedProcess:
    def __init__(self, *, returncode: int = 0, stdout: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = ""


def test_start_launches_omlx_and_writes_profile_local_process_record(
    tmp_path: Path,
    monkeypatch,
) -> None:
    profile = default_profile(mode="work", root=tmp_path / "work")
    calls: list[dict[str, Any]] = []

    class FakeProcess:
        pid = 4242

    def fake_popen(args: list[str], **kwargs: Any) -> FakeProcess:
        calls.append({"args": args, **kwargs})
        return FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    launcher = OMLXLauncher(profile=profile, endpoint=ModelEndpoint.primary())

    result = launcher.start()

    assert result.returncode == 0
    assert "started oMLX" in result.stdout
    assert calls[0]["args"] == _omlx_command()
    assert calls[0]["shell"] is False
    assert calls[0]["start_new_session"] is True
    launch_record = json.loads(
        (Path(profile.root) / "runtime" / "code" / "omlx-launch.json").read_text(
            encoding="utf-8"
        )
    )
    assert launch_record["pid"] == 4242
    assert launch_record["model_id"] == ModelEndpoint.primary().model_id
    assert launch_record["base_url"] == ModelEndpoint.primary().base_url


def test_start_reuses_existing_verified_live_pid_without_overwriting_record(
    tmp_path: Path,
    monkeypatch,
) -> None:
    profile = default_profile(mode="work", root=tmp_path / "work")
    runtime_dir = _write_launch_record(profile, pid=4242)

    def fake_kill(pid: int, sig: int) -> None:
        assert (pid, sig) == (4242, 0)

    def fake_run(args: list[str], **kwargs: Any) -> FakeCompletedProcess:
        assert args == ["ps", "-p", "4242", "-o", "args="]
        assert kwargs["shell"] is False
        return FakeCompletedProcess(stdout=" ".join(_omlx_command()))

    def fake_popen(args: list[str], **kwargs: Any) -> None:
        del args, kwargs
        raise AssertionError("start should not launch a second oMLX process")

    monkeypatch.setattr(os, "kill", fake_kill)
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    result = OMLXLauncher(profile=profile, endpoint=ModelEndpoint.primary()).start()

    assert result.returncode == 0
    assert "already running oMLX pid 4242" in result.stdout
    assert (runtime_dir / "omlx.pid").read_text(encoding="utf-8") == "4242\n"
    launch_record = json.loads(
        (runtime_dir / "omlx-launch.json").read_text(encoding="utf-8")
    )
    assert launch_record["pid"] == 4242


def test_start_does_not_record_child_that_exits_immediately(
    tmp_path: Path,
    monkeypatch,
) -> None:
    profile = default_profile(mode="work", root=tmp_path / "work")
    runtime_dir = Path(profile.root) / "runtime" / "code"

    class FakeProcess:
        pid = 5151

        def poll(self) -> int:
            return 2

    def fake_popen(args: list[str], **kwargs: Any) -> FakeProcess:
        del args, kwargs
        return FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    result = OMLXLauncher(profile=profile, endpoint=ModelEndpoint.primary()).start()

    assert result.returncode == 1
    assert "exited before launch was recorded" in result.stderr
    assert not (runtime_dir / "omlx.pid").exists()
    assert not (runtime_dir / "omlx-launch.json").exists()


def test_start_uses_configured_omlx_binary_without_external_repo(
    tmp_path: Path,
    monkeypatch,
) -> None:
    profile = default_profile(mode="work", root=tmp_path / "work")
    calls: list[list[str]] = []

    class FakeProcess:
        pid = 5151

    def fake_popen(args: list[str], **kwargs: Any) -> FakeProcess:
        del kwargs
        calls.append(args)
        return FakeProcess()

    monkeypatch.setenv("ZSPER_OMLX_BIN", "/opt/zsper/bin/omlx")
    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    OMLXLauncher(profile=profile, endpoint=ModelEndpoint.primary()).start()

    assert calls[0][0] == "/opt/zsper/bin/omlx"
    old_external_repo = "llm" + "-server"
    assert not any(old_external_repo in part for part in calls[0])


def test_stop_terminates_profile_local_omlx_pid(
    tmp_path: Path,
    monkeypatch,
) -> None:
    profile = default_profile(mode="work", root=tmp_path / "work")
    runtime_dir = _write_launch_record(profile, pid=4242)
    killed: list[tuple[int, int]] = []

    def fake_kill(pid: int, sig: int) -> None:
        killed.append((pid, sig))

    def fake_run(args: list[str], **kwargs: Any) -> FakeCompletedProcess:
        assert args == ["ps", "-p", "4242", "-o", "args="]
        assert kwargs["shell"] is False
        return FakeCompletedProcess(stdout=" ".join(_omlx_command()))

    monkeypatch.setattr(os, "kill", fake_kill)
    monkeypatch.setattr(subprocess, "run", fake_run)
    launcher = OMLXLauncher(profile=profile, endpoint=ModelEndpoint.primary())

    result = launcher.stop()

    assert result.returncode == 0
    assert "stopped oMLX" in result.stdout
    assert killed == [(4242, 0), (4242, signal.SIGTERM)]
    assert not (runtime_dir / "omlx.pid").exists()


def test_stop_rejects_non_positive_pid_without_signaling(
    tmp_path: Path,
    monkeypatch,
) -> None:
    profile = default_profile(mode="work", root=tmp_path / "work")
    runtime_dir = Path(profile.root) / "runtime" / "code"
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "omlx.pid").write_text("-1\n", encoding="utf-8")
    killed: list[tuple[int, int]] = []

    def fake_kill(pid: int, sig: int) -> None:
        killed.append((pid, sig))

    monkeypatch.setattr(os, "kill", fake_kill)

    result = OMLXLauncher(profile=profile, endpoint=ModelEndpoint.primary()).stop()

    assert result.returncode == 1
    assert "invalid oMLX pid file" in result.stderr
    assert killed == []
    assert not (runtime_dir / "omlx.pid").exists()


def test_stop_rejects_pid_without_matching_launch_record(
    tmp_path: Path,
    monkeypatch,
) -> None:
    profile = default_profile(mode="work", root=tmp_path / "work")
    runtime_dir = Path(profile.root) / "runtime" / "code"
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "omlx.pid").write_text("4242\n", encoding="utf-8")
    killed: list[tuple[int, int]] = []

    def fake_kill(pid: int, sig: int) -> None:
        killed.append((pid, sig))

    monkeypatch.setattr(os, "kill", fake_kill)

    result = OMLXLauncher(profile=profile, endpoint=ModelEndpoint.primary()).stop()

    assert result.returncode == 1
    assert "does not match a verified oMLX launch" in result.stderr
    assert killed == [(4242, 0)]
    assert (runtime_dir / "omlx.pid").exists()


def test_stop_removes_stale_pid_without_signaling_sigterm(
    tmp_path: Path,
    monkeypatch,
) -> None:
    profile = default_profile(mode="work", root=tmp_path / "work")
    runtime_dir = _write_launch_record(profile, pid=4242)
    killed: list[tuple[int, int]] = []

    def fake_kill(pid: int, sig: int) -> None:
        killed.append((pid, sig))
        if sig == 0:
            raise ProcessLookupError

    monkeypatch.setattr(os, "kill", fake_kill)

    result = OMLXLauncher(profile=profile, endpoint=ModelEndpoint.primary()).stop()

    assert result.returncode == 0
    assert "removed stale oMLX pid 4242" in result.stdout
    assert killed == [(4242, 0)]
    assert not (runtime_dir / "omlx.pid").exists()


def test_status_checks_local_openai_models_endpoint(monkeypatch, tmp_path: Path) -> None:
    profile = default_profile(mode="work", root=tmp_path / "work")
    requests: list[Any] = []

    def fake_urlopen(request: Any, timeout: float) -> FakeHTTPResponse:
        requests.append((request, timeout))
        return FakeHTTPResponse({"data": [{"id": ModelEndpoint.primary().model_id}]})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    launcher = OMLXLauncher(profile=profile, endpoint=ModelEndpoint.primary())

    status = launcher.status(timeout=0.5)

    assert status.available is True
    assert status.status_code == 200
    assert status.models == [ModelEndpoint.primary().model_id]
    assert requests[0][0].full_url == "http://127.0.0.1:9127/v1/models"
    assert requests[0][1] == 0.5


def test_status_handles_non_object_success_payload(monkeypatch, tmp_path: Path) -> None:
    profile = default_profile(mode="work", root=tmp_path / "work")

    def fake_urlopen(request: Any, timeout: float) -> FakeHTTPResponse:
        del request, timeout
        return FakeHTTPResponse([])  # type: ignore[arg-type]

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    launcher = OMLXLauncher(profile=profile, endpoint=ModelEndpoint.primary())

    status = launcher.status()

    assert status.available is False
    assert status.error == "missing models payload"


def test_status_handles_non_list_models_payload(monkeypatch, tmp_path: Path) -> None:
    profile = default_profile(mode="work", root=tmp_path / "work")

    def fake_urlopen(request: Any, timeout: float) -> FakeHTTPResponse:
        del request, timeout
        return FakeHTTPResponse({"data": None})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    launcher = OMLXLauncher(profile=profile, endpoint=ModelEndpoint.primary())

    status = launcher.status()

    assert status.available is False
    assert status.error == "missing models payload"


def test_smoke_posts_chat_completion_to_local_openai_endpoint(
    monkeypatch,
    tmp_path: Path,
) -> None:
    profile = default_profile(mode="work", root=tmp_path / "work")
    requests: list[Any] = []

    def fake_urlopen(request: Any, timeout: float) -> FakeHTTPResponse:
        requests.append((request, timeout))
        body = json.loads(request.data.decode("utf-8"))
        assert body["model"] == ModelEndpoint.primary().model_id
        assert body["messages"][-1]["content"] == "Reply with OK."
        return FakeHTTPResponse({"choices": [{"message": {"content": "OK"}}]})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    launcher = OMLXLauncher(profile=profile, endpoint=ModelEndpoint.primary())

    result = launcher.smoke(prompt="Reply with OK.", timeout=0.25)

    assert result.ok is True
    assert result.content == "OK"
    assert requests[0][0].full_url == "http://127.0.0.1:9127/v1/chat/completions"
    assert requests[0][0].headers["Content-type"] == "application/json"
    assert requests[0][1] == 0.25


def test_smoke_handles_malformed_success_payload(monkeypatch, tmp_path: Path) -> None:
    profile = default_profile(mode="work", root=tmp_path / "work")

    def fake_urlopen(request: Any, timeout: float) -> FakeHTTPResponse:
        del request, timeout
        return FakeHTTPResponse({"choices": []})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    launcher = OMLXLauncher(profile=profile, endpoint=ModelEndpoint.primary())

    result = launcher.smoke()

    assert result.ok is False
    assert result.error == "missing chat completion content"


def test_smoke_handles_non_object_success_payload(monkeypatch, tmp_path: Path) -> None:
    profile = default_profile(mode="work", root=tmp_path / "work")

    def fake_urlopen(request: Any, timeout: float) -> FakeHTTPResponse:
        del request, timeout
        return FakeHTTPResponse([])  # type: ignore[arg-type]

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    launcher = OMLXLauncher(profile=profile, endpoint=ModelEndpoint.primary())

    result = launcher.smoke()

    assert result.ok is False
    assert result.error == "missing chat completion content"


def test_smoke_handles_non_object_choice(monkeypatch, tmp_path: Path) -> None:
    profile = default_profile(mode="work", root=tmp_path / "work")

    def fake_urlopen(request: Any, timeout: float) -> FakeHTTPResponse:
        del request, timeout
        return FakeHTTPResponse({"choices": [None]})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    launcher = OMLXLauncher(profile=profile, endpoint=ModelEndpoint.primary())

    result = launcher.smoke()

    assert result.ok is False
    assert result.error == "missing chat completion content"


def test_smoke_rejects_null_completion_content(monkeypatch, tmp_path: Path) -> None:
    profile = default_profile(mode="work", root=tmp_path / "work")

    def fake_urlopen(request: Any, timeout: float) -> FakeHTTPResponse:
        del request, timeout
        return FakeHTTPResponse({"choices": [{"message": {"content": None}}]})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    launcher = OMLXLauncher(profile=profile, endpoint=ModelEndpoint.primary())

    result = launcher.smoke()

    assert result.ok is False
    assert result.error == "missing chat completion content"


def test_launcher_rejects_non_local_model_endpoint_before_http(tmp_path: Path) -> None:
    profile = default_profile(mode="work", root=tmp_path / "work")
    endpoint = ModelEndpoint(
        provider_id="hosted",
        base_url="https://api.openai.com/v1",
        model_id="gpt-hosted",
        context_window=128000,
        output_limit=4096,
        tool_support=True,
    )
    launcher = OMLXLauncher(profile=profile, endpoint=endpoint)

    status = launcher.status()
    smoke = launcher.smoke()

    assert status.available is False
    assert status.error == "model endpoint must be local"
    assert smoke.ok is False
    assert smoke.error == "model endpoint must be local"
