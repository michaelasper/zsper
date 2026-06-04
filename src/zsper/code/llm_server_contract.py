"""External contract for local llm-server model serving."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from zsper.config.model_endpoint import ModelEndpoint


DEFAULT_START_TEMPLATE = 'mise -C "$ZSPER_LLM_SERVER_DIR" run prod-start-zsper'
DEFAULT_STOP_TEMPLATE = 'mise -C "$ZSPER_LLM_SERVER_DIR" run prod-stop-zsper'
DEFAULT_LLM_SERVER_DIR = str(Path.home() / "source" / "llm-server")


@dataclass(frozen=True)
class LLMServerStatus:
    available: bool
    status_code: int | None
    models: list[str]
    error: str | None = None


@dataclass(frozen=True)
class LLMServerSmokeResult:
    ok: bool
    content: str
    status_code: int | None
    error: str | None = None


class LLMServerContract:
    def __init__(
        self,
        *,
        endpoint: ModelEndpoint | None = None,
        start_template: str = DEFAULT_START_TEMPLATE,
        stop_template: str = DEFAULT_STOP_TEMPLATE,
    ) -> None:
        self.endpoint = endpoint or ModelEndpoint.primary()
        self.start_template = start_template
        self.stop_template = stop_template

    def _render_command(self, template: str) -> list[str]:
        llm_server_dir = os.environ.get("ZSPER_LLM_SERVER_DIR", DEFAULT_LLM_SERVER_DIR)
        rendered = template.replace("$ZSPER_LLM_SERVER_DIR", llm_server_dir)
        rendered = rendered.replace("${ZSPER_LLM_SERVER_DIR}", llm_server_dir)
        return shlex.split(rendered)

    def _is_local_endpoint(self) -> bool:
        parsed = urlparse(self.endpoint.base_url)
        return parsed.scheme in {"http", "https"} and parsed.hostname in {
            "localhost",
            "127.0.0.1",
            "::1",
        }

    def start(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            self._render_command(self.start_template),
            shell=False,
            capture_output=True,
            text=True,
            check=False,
        )

    def stop(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            self._render_command(self.stop_template),
            shell=False,
            capture_output=True,
            text=True,
            check=False,
        )

    def status(self, *, timeout: float = 2.0) -> LLMServerStatus:
        if not self._is_local_endpoint():
            return LLMServerStatus(
                available=False,
                status_code=None,
                models=[],
                error="model endpoint must be localhost",
            )
        request = urllib.request.Request(self.endpoint.health_url)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, dict):
                    return LLMServerStatus(
                        available=False,
                        status_code=getattr(response, "status", 200),
                        models=[],
                        error="missing models payload",
                    )
                data = payload.get("data", [])
                if not isinstance(data, list):
                    return LLMServerStatus(
                        available=False,
                        status_code=getattr(response, "status", 200),
                        models=[],
                        error="missing models payload",
                    )
                models = [
                    str(model["id"])
                    for model in data
                    if isinstance(model, dict) and "id" in model
                ]
                return LLMServerStatus(
                    available=True,
                    status_code=getattr(response, "status", 200),
                    models=models,
                )
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            return LLMServerStatus(
                available=False,
                status_code=None,
                models=[],
                error=str(exc),
            )

    def smoke(
        self,
        *,
        prompt: str = "Reply with OK.",
        timeout: float = 5.0,
    ) -> LLMServerSmokeResult:
        if not self._is_local_endpoint():
            return LLMServerSmokeResult(
                ok=False,
                content="",
                status_code=None,
                error="model endpoint must be localhost",
            )
        body = json.dumps(
            {
                "model": self.endpoint.model_id,
                "messages": [{"role": "user", "content": prompt}],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint.chat_completions_url,
            data=body,
            headers={"Content-type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, dict):
                    return LLMServerSmokeResult(
                        ok=False,
                        content="",
                        status_code=getattr(response, "status", 200),
                        error="missing chat completion content",
                    )
                choices = payload.get("choices")
                if not isinstance(choices, list) or not choices:
                    return LLMServerSmokeResult(
                        ok=False,
                        content="",
                        status_code=getattr(response, "status", 200),
                        error="missing chat completion content",
                    )
                first_choice = choices[0]
                if not isinstance(first_choice, dict):
                    return LLMServerSmokeResult(
                        ok=False,
                        content="",
                        status_code=getattr(response, "status", 200),
                        error="missing chat completion content",
                    )
                message = first_choice.get("message", {})
                raw_content = message.get("content") if isinstance(message, dict) else None
                content = raw_content if isinstance(raw_content, str) else ""
                if not content:
                    return LLMServerSmokeResult(
                        ok=False,
                        content="",
                        status_code=getattr(response, "status", 200),
                        error="missing chat completion content",
                    )
                return LLMServerSmokeResult(
                    ok=bool(content),
                    content=content,
                    status_code=getattr(response, "status", 200),
                )
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            return LLMServerSmokeResult(
                ok=False,
                content="",
                status_code=None,
                error=str(exc),
            )
