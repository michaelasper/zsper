"""Profile-local oMLX launcher for Zsper's OpenAI-compatible model endpoint."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from zsper.config.model_endpoint import ModelEndpoint
from zsper.profiles import Profile
from zsper.security.network_policy import LOCALHOST_NAMES


DEFAULT_OMLX_BIN = "omlx"
DEFAULT_OMLX_API = "openai"


@dataclass(frozen=True)
class OMLXCommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class OMLXStatus:
    available: bool
    status_code: int | None
    models: list[str]
    error: str | None = None


@dataclass(frozen=True)
class OMLXSmokeResult:
    ok: bool
    content: str
    status_code: int | None
    error: str | None = None


class OMLXLauncher:
    def __init__(
        self,
        *,
        profile: Profile,
        endpoint: ModelEndpoint | None = None,
        omlx_bin: str | None = None,
    ) -> None:
        self.profile = profile
        self.endpoint = endpoint or ModelEndpoint.primary()
        self.omlx_bin = omlx_bin or os.environ.get("ZSPER_OMLX_BIN", DEFAULT_OMLX_BIN)

    @property
    def runtime_dir(self) -> Path:
        return Path(self.profile.root) / "runtime" / "code"

    @property
    def pid_path(self) -> Path:
        return self.runtime_dir / "omlx.pid"

    @property
    def launch_record_path(self) -> Path:
        return self.runtime_dir / "omlx-launch.json"

    def _parsed_endpoint(self):
        return urlparse(self.endpoint.base_url)

    def _is_local_endpoint(self) -> bool:
        parsed = self._parsed_endpoint()
        return parsed.scheme in {"http", "https"} and parsed.hostname in LOCALHOST_NAMES

    def _host_port(self) -> tuple[str, int]:
        parsed = self._parsed_endpoint()
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return host, port

    def _command(self) -> list[str]:
        host, port = self._host_port()
        return [
            self.omlx_bin,
            "serve",
            "--model",
            self.endpoint.model_id,
            "--host",
            host,
            "--port",
            str(port),
            "--api",
            DEFAULT_OMLX_API,
        ]

    def start(self) -> OMLXCommandResult:
        if not self._is_local_endpoint():
            return OMLXCommandResult(
                returncode=1,
                stderr="model endpoint must be local",
            )

        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        command = self._command()
        try:
            process = subprocess.Popen(
                command,
                shell=False,
                cwd=str(self.runtime_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            return OMLXCommandResult(returncode=1, stderr=str(exc))

        self.pid_path.write_text(f"{process.pid}\n", encoding="utf-8")
        self.launch_record_path.write_text(
            json.dumps(
                {
                    "pid": process.pid,
                    "command": command,
                    "model_id": self.endpoint.model_id,
                    "base_url": self.endpoint.base_url,
                    "started_at": datetime.now(UTC).isoformat(),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return OMLXCommandResult(
            returncode=0,
            stdout=f"started oMLX pid {process.pid} for {self.profile.name}",
        )

    def stop(self) -> OMLXCommandResult:
        if not self.pid_path.exists():
            return OMLXCommandResult(
                returncode=0,
                stdout=f"oMLX not running for {self.profile.name}",
            )

        raw_pid = self.pid_path.read_text(encoding="utf-8").strip()
        try:
            pid = int(raw_pid)
        except ValueError:
            self.pid_path.unlink(missing_ok=True)
            return OMLXCommandResult(
                returncode=1,
                stderr=f"invalid oMLX pid file: {self.pid_path}",
            )

        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            self.pid_path.unlink(missing_ok=True)
            return OMLXCommandResult(
                returncode=0,
                stdout=f"removed stale oMLX pid {pid} for {self.profile.name}",
            )
        except OSError as exc:
            return OMLXCommandResult(returncode=1, stderr=str(exc))

        self.pid_path.unlink(missing_ok=True)
        return OMLXCommandResult(
            returncode=0,
            stdout=f"stopped oMLX pid {pid} for {self.profile.name}",
        )

    def status(self, *, timeout: float = 2.0) -> OMLXStatus:
        if not self._is_local_endpoint():
            return OMLXStatus(
                available=False,
                status_code=None,
                models=[],
                error="model endpoint must be local",
            )
        request = urllib.request.Request(self.endpoint.health_url)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, dict):
                    return OMLXStatus(
                        available=False,
                        status_code=getattr(response, "status", 200),
                        models=[],
                        error="missing models payload",
                    )
                data = payload.get("data", [])
                if not isinstance(data, list):
                    return OMLXStatus(
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
                return OMLXStatus(
                    available=True,
                    status_code=getattr(response, "status", 200),
                    models=models,
                )
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            return OMLXStatus(
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
    ) -> OMLXSmokeResult:
        if not self._is_local_endpoint():
            return OMLXSmokeResult(
                ok=False,
                content="",
                status_code=None,
                error="model endpoint must be local",
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
                    return OMLXSmokeResult(
                        ok=False,
                        content="",
                        status_code=getattr(response, "status", 200),
                        error="missing chat completion content",
                    )
                choices = payload.get("choices")
                if not isinstance(choices, list) or not choices:
                    return OMLXSmokeResult(
                        ok=False,
                        content="",
                        status_code=getattr(response, "status", 200),
                        error="missing chat completion content",
                    )
                first_choice = choices[0]
                if not isinstance(first_choice, dict):
                    return OMLXSmokeResult(
                        ok=False,
                        content="",
                        status_code=getattr(response, "status", 200),
                        error="missing chat completion content",
                    )
                message = first_choice.get("message", {})
                raw_content = message.get("content") if isinstance(message, dict) else None
                content = raw_content if isinstance(raw_content, str) else ""
                if not content:
                    return OMLXSmokeResult(
                        ok=False,
                        content="",
                        status_code=getattr(response, "status", 200),
                        error="missing chat completion content",
                    )
                return OMLXSmokeResult(
                    ok=bool(content),
                    content=content,
                    status_code=getattr(response, "status", 200),
                )
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            return OMLXSmokeResult(
                ok=False,
                content="",
                status_code=None,
                error=str(exc),
            )
