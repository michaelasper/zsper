"""Profile health checks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from zsper.profiles.init import PROFILE_LAYOUT_DIRS
from zsper.profiles.resolver import resolve_profile
from zsper.profiles.schema import Profile, ProfileError, validate_profile
from zsper.security.hosted_dependencies import find_forbidden_hosted_settings
from zsper.security.network_policy import check_network_policy
from zsper.security.remote_policy import check_remote_policy


@dataclass(frozen=True)
class DoctorReport:
    ok: bool
    profile: Profile
    errors: list[str]


def _is_writable(path: Path) -> bool:
    mode = path.stat().st_mode
    return path.exists() and path.is_dir() and mode & 0o222 != 0


def _load_raw_profile(root: Path) -> dict[str, object]:
    profile_path = root / "profile.json"
    if not profile_path.is_file():
        return {}
    try:
        payload = json.loads(profile_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProfileError(f"invalid profile JSON at {profile_path}: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ProfileError(f"profile JSON must be an object at {profile_path}")
    return payload


def profile_doctor(
    profile_ref: str | None,
    *,
    registry_path: Path | str | None = None,
) -> DoctorReport:
    if not profile_ref:
        raise ProfileError("profile name or root is required")

    path_hint = Path(profile_ref).expanduser().resolve(strict=False)
    root_hint = path_hint.parent if path_hint.name == "profile.json" else path_hint
    resolve_error: ProfileError | None = None
    try:
        profile = resolve_profile(profile_ref, registry_path=registry_path)
        root = Path(profile.root)
        raw_profile = _load_raw_profile(root)
    except ProfileError as exc:
        resolve_error = exc
        root = root_hint if (root_hint / "profile.json").exists() else Path.cwd()
        raw_profile = _load_raw_profile(root_hint)
        if not raw_profile:
            raise
        profile = Profile(
            schema_version=int(raw_profile.get("schema_version", 0)),
            name=str(raw_profile.get("name", "")),
            mode=str(raw_profile.get("mode", "")),
            root=str(root_hint),
            model_profile=str(raw_profile.get("model_profile", "")),
            long_context_fallback=raw_profile.get("long_context_fallback"),  # type: ignore[arg-type]
            embedding_profile=str(raw_profile.get("embedding_profile", "")),
            storage_backend=str(raw_profile.get("storage_backend", "")),
            remote_access_policy=str(raw_profile.get("remote_access_policy", "")),
            network_policy=str(raw_profile.get("network_policy", "")),
            database_name=str(raw_profile.get("database_name", "")),
            created_at=str(raw_profile.get("created_at", "")),
            updated_at=str(raw_profile.get("updated_at", "")),
        )

    errors: list[str] = []

    def add_error(message: str) -> None:
        if message not in errors:
            errors.append(message)

    if resolve_error is not None:
        add_error(str(resolve_error))

    try:
        validate_profile(profile)
    except ProfileError as exc:
        add_error(str(exc))

    remote_decision = check_remote_policy(profile.mode, profile.remote_access_policy)
    if not remote_decision.allowed:
        add_error(remote_decision.reason)

    network_decision = check_network_policy(
        profile.network_policy,
        "http://127.0.0.1:9127/v1/models",
        action="localhost-service",
    )
    if not network_decision.allowed:
        add_error(network_decision.reason)

    if not (root / "profile.json").is_file():
        add_error("missing profile.json")
    for relative_dir in PROFILE_LAYOUT_DIRS:
        path = root / relative_dir
        if not path.is_dir():
            add_error(f"missing directory: {relative_dir}")
        elif not _is_writable(path):
            add_error(f"directory not writable: {relative_dir}")
    if not (root / "agent-runs" / "runs.jsonl").is_file():
        add_error("missing agent-runs/runs.jsonl")

    for dependency in find_forbidden_hosted_settings(raw_profile):
        add_error(f"forbidden hosted dependency configured: {dependency}")

    return DoctorReport(ok=not errors, profile=profile, errors=errors)
