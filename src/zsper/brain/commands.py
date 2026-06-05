"""Handlers for `zsper brain` service commands."""

from __future__ import annotations

import os
import subprocess
import sys
from argparse import Namespace
from typing import Mapping

from zsper.brain.api import (
    DEFAULT_MODEL_BASE_URL,
    DefaultServiceProbes,
    ServiceProbes,
    build_health_report,
    resolve_api_profile_context,
)
from zsper.brain.compose import (
    RenderedBrainProfile,
    brain_ports_for_profile,
    render_brain_profile,
)
from zsper.config.user import UserConfigError, profile_ref_or_default
from zsper.profiles import Profile, ProfileError, resolve_profile


STATUS_COMPONENT_LABELS: tuple[tuple[str, str], ...] = (
    ("database", "DB"),
    ("redis", "Redis"),
    ("brain_api", "API"),
    ("web_ui", "web"),
    ("searxng", "SearXNG"),
    ("honcho", "Honcho"),
    ("local_model_models", "local model endpoint"),
)


def _resolve(namespace: Namespace) -> Profile | None:
    try:
        return resolve_profile(profile_ref_or_default(namespace.profile))
    except (ProfileError, UserConfigError) as exc:
        print(str(exc), file=sys.stderr)
        return None


def _compose_args(rendered: RenderedBrainProfile, command: str) -> list[str]:
    args = [
        "docker",
        "compose",
        "--env-file",
        str(rendered.env_path),
        "-f",
        str(rendered.compose_path),
        command,
    ]
    if command == "up":
        args.append("-d")
    return args


def _run_compose(rendered: RenderedBrainProfile, command: str) -> int:
    try:
        completed = subprocess.run(
            _compose_args(rendered, command),
            cwd=rendered.compose_path.parent,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        print(f"docker compose {command} failed: {exc}", file=sys.stderr)
        return 127

    if completed.stdout:
        print(completed.stdout.strip())
    if completed.stderr:
        print(completed.stderr.strip(), file=sys.stderr)
    return completed.returncode


def _host_status_env(profile: Profile) -> dict[str, str]:
    ports = brain_ports_for_profile(profile)
    env = {
        "ZSPER_PROFILE_ID": profile.name,
        "ZSPER_PROFILE_NAME": profile.name,
        "ZSPER_PROFILE_MODE": profile.mode,
        "ZSPER_PROFILE_ROOT": profile.root,
        "POSTGRES_DB": profile.database_name,
        "POSTGRES_USER": "zsper",
        "POSTGRES_PASSWORD": "zsper-local-only",
        "POSTGRES_HOST": "127.0.0.1",
        "POSTGRES_PORT": str(ports.postgres),
        "POSTGRES_DSN": (
            "postgresql://zsper:zsper-local-only@"
            f"127.0.0.1:{ports.postgres}/{profile.database_name}"
        ),
        "REDIS_URL": f"redis://127.0.0.1:{ports.redis}/0",
        "REDIS_KEY_PREFIX": f"zsper:{profile.name}:",
        "ZSPER_MODEL_BASE_URL": os.environ.get(
            "ZSPER_MODEL_BASE_URL",
            DEFAULT_MODEL_BASE_URL,
        ),
        "SEARXNG_URL": f"http://127.0.0.1:{ports.searxng}",
        "HONCHO_URL": f"http://127.0.0.1:{ports.honcho}",
        "BRAIN_API_URL": f"http://127.0.0.1:{ports.api}",
        "BRAIN_WEB_URL": f"http://127.0.0.1:{ports.web}",
    }
    registry_path = os.environ.get("ZSPER_PROFILE_REGISTRY")
    if registry_path:
        env["ZSPER_PROFILE_REGISTRY"] = registry_path
    return env


def health_report_for_profile(
    profile: Profile,
    *,
    probes: ServiceProbes | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, object]:
    context = resolve_api_profile_context(environ or _host_status_env(profile))
    return build_health_report(context, probes or DefaultServiceProbes())


def up(namespace: Namespace) -> int:
    profile = _resolve(namespace)
    if profile is None:
        return 1

    rendered = render_brain_profile(profile)
    exit_code = _run_compose(rendered, "up")
    if exit_code == 0:
        print(f"brain services started for {profile.name}")
    return exit_code


def down(namespace: Namespace) -> int:
    profile = _resolve(namespace)
    if profile is None:
        return 1

    rendered = render_brain_profile(profile)
    exit_code = _run_compose(rendered, "down")
    if exit_code == 0:
        print(f"brain services stopped for {profile.name}")
    return exit_code


def status(namespace: Namespace) -> int:
    profile = _resolve(namespace)
    if profile is None:
        return 1

    try:
        report = health_report_for_profile(profile)
    except Exception as exc:
        print(f"brain status failed for {profile.name}: {exc}", file=sys.stderr)
        return 1

    overall_status = str(report["overall_status"])
    components = report["components"]
    if not isinstance(components, Mapping):
        print("brain status response has invalid components", file=sys.stderr)
        return 1

    print(f"brain status for {profile.name}: {overall_status}")
    for component, label in STATUS_COMPONENT_LABELS:
        value = components.get(component, {})
        component_status = "unknown"
        if isinstance(value, Mapping):
            component_status = str(value.get("status", "unknown"))
        print(f"{label}: {component_status}")

    return 0 if overall_status == "pass" else 1


def handler(command: str):
    return {
        "up": up,
        "down": down,
        "status": status,
    }[command]
