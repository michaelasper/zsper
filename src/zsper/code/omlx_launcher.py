"""Profile-local oMLX launcher for Zsper's OpenAI-compatible model endpoint."""

from __future__ import annotations

import json
import os
import signal
import shlex
import subprocess
import time
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
STARTUP_POLL_DELAY_SECONDS = 0.05


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


@dataclass(frozen=True)
class _RecordedProcess:
    state: str
    pid: int | None = None
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

    def _read_pid(self) -> tuple[int | None, str | None]:
        if not self.pid_path.exists():
            return None, None

        raw_pid = self.pid_path.read_text(encoding="utf-8").strip()
        try:
            pid = int(raw_pid)
        except ValueError:
            return None, f"invalid oMLX pid file: {self.pid_path}"
        if pid <= 0:
            return None, f"invalid oMLX pid file: {self.pid_path}"
        return pid, None

    def _launch_record_matches(self, pid: int) -> bool:
        try:
            record = json.loads(self.launch_record_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if not isinstance(record, dict):
            return False
        if record.get("pid") != pid:
            return False
        if record.get("model_id") != self.endpoint.model_id:
            return False
        if record.get("base_url") != self.endpoint.base_url:
            return False
        command = record.get("command")
        return command == self._command()

    def _process_exists(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except OSError:
            return True
        return True

    def _process_command_matches(self, pid: int) -> bool:
        try:
            completed = subprocess.run(
                ["ps", "-p", str(pid), "-o", "args="],
                shell=False,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return False
        if completed.returncode != 0:
            return False
        try:
            actual = shlex.split(completed.stdout.strip())
        except ValueError:
            return False
        expected = self._command()
        if len(actual) < len(expected):
            return False

        actual_bin = actual[0]
        expected_bin = expected[0]
        if Path(expected_bin).is_absolute():
            if actual_bin != expected_bin:
                return False
        elif Path(actual_bin).name != expected_bin:
            return False
        return actual[1 : len(expected)] == expected[1:]

    def _recorded_process(self) -> _RecordedProcess:
        pid, pid_error = self._read_pid()
        if pid_error is not None:
            return _RecordedProcess(state="invalid", error=pid_error)
        if pid is None:
            return _RecordedProcess(state="missing")

        process_exists = self._process_exists(pid)
        if not process_exists:
            return _RecordedProcess(state="stale", pid=pid)
        if not self._launch_record_matches(pid):
            return _RecordedProcess(
                state="unverified",
                pid=pid,
                error=f"pid {pid} does not match a verified oMLX launch",
            )
        if not self._process_command_matches(pid):
            return _RecordedProcess(
                state="unverified",
                pid=pid,
                error=f"pid {pid} does not match a verified oMLX launch",
            )
        return _RecordedProcess(state="valid", pid=pid)

    def _clear_runtime_record(self) -> None:
        self.pid_path.unlink(missing_ok=True)
        self.launch_record_path.unlink(missing_ok=True)

    @staticmethod
    def _process_returncode(process: subprocess.Popen[str]) -> int | None:
        poll = getattr(process, "poll", None)
        if callable(poll):
            return poll()
        return None

    def start(self) -> OMLXCommandResult:
        if not self._is_local_endpoint():
            return OMLXCommandResult(
                returncode=1,
                stderr="model endpoint must be local",
            )

        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        recorded = self._recorded_process()
        if recorded.state == "valid" and recorded.pid is not None:
            return OMLXCommandResult(
                returncode=0,
                stdout=f"already running oMLX pid {recorded.pid} for {self.profile.name}",
            )
        if recorded.state == "stale":
            self._clear_runtime_record()
        elif recorded.state == "invalid":
            self._clear_runtime_record()
        elif recorded.state == "unverified":
            return OMLXCommandResult(
                returncode=1,
                stderr=recorded.error or "recorded oMLX process is not verified",
            )

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

        time.sleep(STARTUP_POLL_DELAY_SECONDS)
        returncode = self._process_returncode(process)
        if returncode is not None:
            return OMLXCommandResult(
                returncode=1,
                stderr=(
                    f"oMLX pid {process.pid} exited before launch was recorded "
                    f"(returncode {returncode})"
                ),
            )

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

        recorded = self._recorded_process()
        if recorded.state == "missing":
            return OMLXCommandResult(
                returncode=0,
                stdout=f"oMLX not running for {self.profile.name}",
            )
        if recorded.state == "invalid":
            self.pid_path.unlink(missing_ok=True)
            return OMLXCommandResult(
                returncode=1,
                stderr=recorded.error or f"invalid oMLX pid file: {self.pid_path}",
            )
        if recorded.state == "stale" and recorded.pid is not None:
            self._clear_runtime_record()
            return OMLXCommandResult(
                returncode=0,
                stdout=f"removed stale oMLX pid {recorded.pid} for {self.profile.name}",
            )
        if recorded.state == "unverified":
            return OMLXCommandResult(
                returncode=1,
                stderr=recorded.error or "recorded oMLX process is not verified",
            )

        assert recorded.pid is not None
        pid = recorded.pid
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            self._clear_runtime_record()
            return OMLXCommandResult(
                returncode=0,
                stdout=f"removed stale oMLX pid {pid} for {self.profile.name}",
            )
        except OSError as exc:
            return OMLXCommandResult(returncode=1, stderr=str(exc))

        self._clear_runtime_record()
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
