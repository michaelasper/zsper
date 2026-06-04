import json
import subprocess
from pathlib import Path
from typing import Any

from zsper.code.llm_server_contract import LLMServerContract
from zsper.config.model_endpoint import ModelEndpoint


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


def test_start_and_stop_render_configured_llm_server_command_without_shell(
    tmp_path: Path,
    monkeypatch,
) -> None:
    llm_dir = tmp_path / "llm-server"
    monkeypatch.setenv("ZSPER_LLM_SERVER_DIR", str(llm_dir))
    calls: list[dict[str, Any]] = []

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append({"args": args, **kwargs})
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    contract = LLMServerContract(
        start_template='mise -C "$ZSPER_LLM_SERVER_DIR" run prod-start-zsper',
        stop_template='mise -C "$ZSPER_LLM_SERVER_DIR" run prod-stop-zsper',
    )

    start = contract.start()
    stop = contract.stop()

    assert start.returncode == 0
    assert stop.returncode == 0
    assert calls[0]["args"] == ["mise", "-C", str(llm_dir), "run", "prod-start-zsper"]
    assert calls[1]["args"] == ["mise", "-C", str(llm_dir), "run", "prod-stop-zsper"]
    assert calls[0]["shell"] is False
    assert calls[1]["shell"] is False


def test_status_checks_local_openai_models_endpoint(monkeypatch) -> None:
    requests: list[Any] = []

    def fake_urlopen(request: Any, timeout: float) -> FakeHTTPResponse:
        requests.append((request, timeout))
        return FakeHTTPResponse({"data": [{"id": ModelEndpoint.primary().model_id}]})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    contract = LLMServerContract(endpoint=ModelEndpoint.primary())

    status = contract.status(timeout=0.5)

    assert status.available is True
    assert status.status_code == 200
    assert status.models == [ModelEndpoint.primary().model_id]
    assert requests[0][0].full_url == "http://127.0.0.1:9127/v1/models"
    assert requests[0][1] == 0.5


def test_status_handles_non_object_success_payload(monkeypatch) -> None:
    def fake_urlopen(request: Any, timeout: float) -> FakeHTTPResponse:
        return FakeHTTPResponse([])  # type: ignore[arg-type]

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    contract = LLMServerContract(endpoint=ModelEndpoint.primary())

    status = contract.status()

    assert status.available is False
    assert status.error == "missing models payload"


def test_status_handles_non_list_models_payload(monkeypatch) -> None:
    def fake_urlopen(request: Any, timeout: float) -> FakeHTTPResponse:
        return FakeHTTPResponse({"data": None})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    contract = LLMServerContract(endpoint=ModelEndpoint.primary())

    status = contract.status()

    assert status.available is False
    assert status.error == "missing models payload"


def test_smoke_posts_chat_completion_to_local_openai_endpoint(monkeypatch) -> None:
    requests: list[Any] = []

    def fake_urlopen(request: Any, timeout: float) -> FakeHTTPResponse:
        requests.append((request, timeout))
        body = json.loads(request.data.decode("utf-8"))
        assert body["model"] == ModelEndpoint.primary().model_id
        assert body["messages"][-1]["content"] == "Reply with OK."
        return FakeHTTPResponse({"choices": [{"message": {"content": "OK"}}]})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    contract = LLMServerContract(endpoint=ModelEndpoint.primary())

    result = contract.smoke(prompt="Reply with OK.", timeout=0.25)

    assert result.ok is True
    assert result.content == "OK"
    assert requests[0][0].full_url == "http://127.0.0.1:9127/v1/chat/completions"
    assert requests[0][0].headers["Content-type"] == "application/json"
    assert requests[0][1] == 0.25


def test_contract_rejects_non_local_model_endpoint_before_http() -> None:
    endpoint = ModelEndpoint(
        provider_id="hosted",
        base_url="https://api.openai.com/v1",
        model_id="gpt-hosted",
        context_window=128000,
        output_limit=4096,
        tool_support=True,
    )
    contract = LLMServerContract(endpoint=endpoint)

    status = contract.status()
    smoke = contract.smoke()

    assert status.available is False
    assert status.error == "model endpoint must be localhost"
    assert smoke.ok is False
    assert smoke.error == "model endpoint must be localhost"


def test_smoke_handles_malformed_success_payload(monkeypatch) -> None:
    def fake_urlopen(request: Any, timeout: float) -> FakeHTTPResponse:
        return FakeHTTPResponse({"choices": []})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    contract = LLMServerContract(endpoint=ModelEndpoint.primary())

    result = contract.smoke()

    assert result.ok is False
    assert result.error == "missing chat completion content"


def test_smoke_handles_non_object_success_payload(monkeypatch) -> None:
    def fake_urlopen(request: Any, timeout: float) -> FakeHTTPResponse:
        return FakeHTTPResponse([])  # type: ignore[arg-type]

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    contract = LLMServerContract(endpoint=ModelEndpoint.primary())

    result = contract.smoke()

    assert result.ok is False
    assert result.error == "missing chat completion content"


def test_smoke_handles_non_object_choice(monkeypatch) -> None:
    def fake_urlopen(request: Any, timeout: float) -> FakeHTTPResponse:
        return FakeHTTPResponse({"choices": [None]})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    contract = LLMServerContract(endpoint=ModelEndpoint.primary())

    result = contract.smoke()

    assert result.ok is False
    assert result.error == "missing chat completion content"


def test_smoke_rejects_null_completion_content(monkeypatch) -> None:
    def fake_urlopen(request: Any, timeout: float) -> FakeHTTPResponse:
        return FakeHTTPResponse({"choices": [{"message": {"content": None}}]})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    contract = LLMServerContract(endpoint=ModelEndpoint.primary())

    result = contract.smoke()

    assert result.ok is False
    assert result.error == "missing chat completion content"
