"""Profile-aware Brain API contracts and health helpers."""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol
from urllib.error import URLError
from urllib.parse import quote, unquote, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from zsper.brain.redis import RedisRuntimeConfig, redis_config_from_env
from zsper.profiles import PROFILE_LAYOUT_DIRS, Profile, ProfileError, resolve_profile
from zsper.profiles.schema import validate_profile
from zsper.security.hosted_dependencies import find_forbidden_hosted_settings
from zsper.security.network_policy import check_network_policy, looks_like_url


DEFAULT_MODEL_BASE_URL = "http://127.0.0.1:9127/v1"
DEFAULT_LOCAL_CORS_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:7421",
    "http://127.0.0.1:7421",
    "http://localhost:7521",
    "http://127.0.0.1:7521",
    "http://localhost:7621",
    "http://127.0.0.1:7621",
)
LOCALHOST_NAMES = frozenset(
    {
        "localhost",
        "127.0.0.1",
        "::1",
        "host.docker.internal",
        "host.containers.internal",
        "searxng",
        "honcho",
        "brain-api",
        "brain-web",
    }
)
STATUS_VALUES = frozenset({"pass", "fail", "disabled", "unknown"})


class ApiError(RuntimeError):
    """Structured API error rendered by the FastAPI service layer."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int,
        profile_id: str | None = None,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.profile_id = profile_id
        self.details = dict(details or {})

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "status_code": self.status_code,
            "profile_id": self.profile_id,
            "details": self.details,
        }


@dataclass(frozen=True)
class DatabaseRuntimeConfig:
    profile_id: str
    dsn: str
    database_name: str

    @property
    def redacted_dsn(self) -> str:
        return redact_url_secret(self.dsn)


@dataclass(frozen=True)
class ComponentStatus:
    status: str
    message: str
    details: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in STATUS_VALUES:
            raise ValueError(f"invalid component status: {self.status}")

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "message": self.message,
            "details": self.details,
        }


class ServiceProbes(Protocol):
    def check_database(self, database: DatabaseRuntimeConfig) -> ComponentStatus:
        """Verify database reachability."""

    def check_redis(self, redis: RedisRuntimeConfig) -> ComponentStatus:
        """Verify Redis reachability."""

    def check_http(self, component: str, url: str) -> ComponentStatus:
        """Verify local HTTP service reachability."""


@dataclass(frozen=True)
class ApiProfileContext:
    profile: Profile
    raw_profile: dict[str, object]
    database: DatabaseRuntimeConfig
    redis: RedisRuntimeConfig
    model_base_url: str
    searxng_url: str | None
    honcho_url: str | None
    brain_api_url: str | None
    brain_web_url: str | None
    extraction_base_url: str | None
    environ: Mapping[str, str]

    @property
    def profile_id(self) -> str:
        return self.profile.name


class DefaultServiceProbes:
    """Best-effort local probes used outside unit tests."""

    timeout_seconds = 1.0

    def check_database(self, database: DatabaseRuntimeConfig) -> ComponentStatus:
        try:
            import psycopg  # type: ignore[import-not-found]
        except ModuleNotFoundError:
            return ComponentStatus(
                status="unknown",
                message="psycopg is not installed in this environment",
                details={"dsn": database.redacted_dsn},
            )

        try:
            with psycopg.connect(database.dsn, connect_timeout=self.timeout_seconds) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
        except Exception as exc:  # pragma: no cover - depends on local services.
            return ComponentStatus(
                status="fail",
                message=f"database check failed: {exc}",
                details={"dsn": database.redacted_dsn},
            )
        return ComponentStatus(
            status="pass",
            message="database reachable",
            details={"dsn": database.redacted_dsn},
        )

    def check_redis(self, redis: RedisRuntimeConfig) -> ComponentStatus:
        try:
            import redis as redis_module  # type: ignore[import-not-found]
        except ModuleNotFoundError:
            return ComponentStatus(
                status="unknown",
                message="redis package is not installed in this environment",
                details={"url": redis.url, "key_prefix": redis.key_prefix},
            )

        try:
            client = redis_module.Redis.from_url(redis.url, socket_timeout=self.timeout_seconds)
            client.ping()
        except Exception as exc:  # pragma: no cover - depends on local services.
            return ComponentStatus(
                status="fail",
                message=f"redis check failed: {exc}",
                details={"url": redis.url, "key_prefix": redis.key_prefix},
            )
        return ComponentStatus(
            status="pass",
            message="redis reachable",
            details={"url": redis.url, "key_prefix": redis.key_prefix},
        )

    def check_http(self, component: str, url: str) -> ComponentStatus:
        request = Request(url, method="GET")
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                status_code = response.status
        except (OSError, socket.timeout, URLError) as exc:
            return ComponentStatus(
                status="fail",
                message=f"{component} check failed: {exc}",
                details={"url": url},
            )

        status = "pass" if 200 <= status_code < 400 else "fail"
        return ComponentStatus(
            status=status,
            message=f"{component} returned HTTP {status_code}",
            details={"url": url, "status_code": status_code},
        )


def redact_url_secret(value: str) -> str:
    parts = urlsplit(value)
    if not parts.password:
        return value

    username = quote(parts.username or "", safe="")
    hostname = parts.hostname or ""
    host = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
    port = f":{parts.port}" if parts.port else ""
    netloc = f"{username}:***@{host}{port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _env_value(environ: Mapping[str, str], *keys: str) -> str | None:
    for key in keys:
        value = environ.get(key)
        if value:
            return value
    return None


def _service_url_from_port(environ: Mapping[str, str], url_key: str, port_key: str) -> str | None:
    configured_url = environ.get(url_key)
    if configured_url:
        return configured_url.rstrip("/")
    port = environ.get(port_key)
    if port:
        return f"http://127.0.0.1:{port}"
    return None


def database_config_from_env(
    environ: Mapping[str, str],
    *,
    profile_id: str,
    expected_database_name: str | None = None,
) -> DatabaseRuntimeConfig:
    expected_name = expected_database_name or f"zsper_{profile_id}"
    database_name = environ.get("POSTGRES_DB", expected_name)
    dsn = environ.get("POSTGRES_DSN")
    if not dsn:
        user = environ.get("POSTGRES_USER", "zsper")
        password = environ.get("POSTGRES_PASSWORD", "zsper-local-only")
        host = environ.get("POSTGRES_HOST", "127.0.0.1")
        port = environ.get("POSTGRES_PORT", "5432")
        dsn = f"postgresql://{user}:{password}@{host}:{port}/{database_name}"
    dsn_database_name = database_name_from_dsn(dsn)
    if database_name != expected_name or (
        dsn_database_name is not None and dsn_database_name != expected_name
    ):
        raise ApiError(
            code="invalid_service_config",
            message="database configuration does not match service profile",
            status_code=500,
            profile_id=profile_id,
            details={
                "expected_database_name": expected_name,
                "configured_database_name": database_name,
                "dsn_database_name": dsn_database_name,
            },
        )
    return DatabaseRuntimeConfig(
        profile_id=profile_id,
        dsn=dsn,
        database_name=database_name,
    )


def database_name_from_dsn(dsn: str) -> str | None:
    parsed = urlsplit(dsn)
    if not parsed.scheme.startswith("postgres"):
        return None
    database_name = unquote(parsed.path.rsplit("/", 1)[-1])
    return database_name or None


def _load_raw_profile(profile: Profile) -> dict[str, object]:
    profile_path = Path(profile.root) / "profile.json"
    if not profile_path.is_file():
        return profile.to_dict()
    try:
        payload = json.loads(profile_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return profile.to_dict()
    if not isinstance(payload, dict):
        return profile.to_dict()
    return payload


def resolve_api_profile_context(
    environ: Mapping[str, str],
    *,
    request_profile_id: str | None = None,
    request_profile_root: str | None = None,
) -> ApiProfileContext:
    env_profile_id = _env_value(environ, "ZSPER_PROFILE_ID", "ZSPER_PROFILE_NAME")
    env_profile_root = environ.get("ZSPER_PROFILE_ROOT")
    registry_path = environ.get("ZSPER_PROFILE_REGISTRY")
    profile_ref = env_profile_root or env_profile_id or request_profile_root or request_profile_id
    profile_id_for_error = env_profile_id or request_profile_id

    if not profile_ref:
        raise ApiError(
            code="missing_profile_context",
            message="profile context is required",
            status_code=400,
        )

    try:
        profile = resolve_profile(profile_ref, registry_path=registry_path)
    except ProfileError as exc:
        raise ApiError(
            code="invalid_profile_context",
            message=str(exc),
            status_code=400,
            profile_id=profile_id_for_error,
        ) from exc

    if env_profile_id and profile.name != env_profile_id:
        raise ApiError(
            code="invalid_profile_context",
            message="service profile id does not match resolved profile",
            status_code=400,
            profile_id=env_profile_id,
            details={"resolved_profile_id": profile.name},
        )

    if request_profile_id and request_profile_id != profile.name:
        raise ApiError(
            code="profile_context_mismatch",
            message="request profile context does not match service profile",
            status_code=403,
            profile_id=profile.name,
            details={"requested_profile_id": request_profile_id},
        )

    if request_profile_root:
        try:
            request_root_profile = resolve_profile(
                request_profile_root,
                registry_path=registry_path,
            )
        except ProfileError as exc:
            raise ApiError(
                code="invalid_profile_context",
                message=str(exc),
                status_code=400,
                profile_id=profile.name,
                details={"requested_profile_root": request_profile_root},
            ) from exc

        if Path(request_root_profile.root) != Path(profile.root):
            raise ApiError(
                code="profile_context_mismatch",
                message="request profile root does not match service profile",
                status_code=403,
                profile_id=profile.name,
                details={
                    "requested_profile_id": request_root_profile.name,
                    "requested_profile_root": request_root_profile.root,
                },
            )

    redis_env = dict(environ)
    redis_env["ZSPER_PROFILE_ID"] = profile.name
    try:
        redis = redis_config_from_env(redis_env)
    except ValueError as exc:
        raise ApiError(
            code="invalid_service_config",
            message=str(exc),
            status_code=500,
            profile_id=profile.name,
        ) from exc

    return ApiProfileContext(
        profile=profile,
        raw_profile=_load_raw_profile(profile),
        database=database_config_from_env(
            environ,
            profile_id=profile.name,
            expected_database_name=profile.database_name,
        ),
        redis=redis,
        model_base_url=environ.get("ZSPER_MODEL_BASE_URL", DEFAULT_MODEL_BASE_URL).rstrip("/"),
        searxng_url=_service_url_from_port(environ, "SEARXNG_URL", "SEARXNG_PORT"),
        honcho_url=_service_url_from_port(environ, "HONCHO_URL", "HONCHO_PORT"),
        brain_api_url=_service_url_from_port(environ, "BRAIN_API_URL", "BRAIN_API_PORT"),
        brain_web_url=_service_url_from_port(environ, "BRAIN_WEB_URL", "BRAIN_WEB_PORT"),
        extraction_base_url=_env_value(environ, "EXTRACTION_BASE_URL", "ZSPER_EXTRACTION_BASE_URL"),
        environ=environ,
    )


def model_models_url(model_base_url: str) -> str:
    base = model_base_url.rstrip("/")
    if base.endswith("/models"):
        return base
    return f"{base}/models"


def is_localhost_url(value: str | None) -> bool:
    if not value or not looks_like_url(value):
        return False
    parsed = urlsplit(value)
    return parsed.hostname in LOCALHOST_NAMES


def is_hosted_url(value: str | None) -> bool:
    return bool(value and looks_like_url(value) and not is_localhost_url(value))


def hosted_config_findings(context: ApiProfileContext) -> list[str]:
    config_values: dict[str, object] = {
        "model_base_url": context.model_base_url,
        "searxng_url": context.searxng_url,
        "extraction_base_url": context.extraction_base_url,
    }
    findings = find_forbidden_hosted_settings(context.raw_profile)
    findings.extend(find_forbidden_hosted_settings(config_values))
    return sorted(set(findings))


def _coerce_status(value: ComponentStatus | Mapping[str, object]) -> ComponentStatus:
    if isinstance(value, ComponentStatus):
        return value
    details = value.get("details", {})
    return ComponentStatus(
        status=str(value.get("status", "unknown")),
        message=str(value.get("message", "")),
        details=dict(details) if isinstance(details, Mapping) else {},
    )


def _profile_schema_status(profile: Profile) -> ComponentStatus:
    try:
        validate_profile(profile)
    except ProfileError as exc:
        return ComponentStatus(
            status="fail",
            message=str(exc),
            details={"profile_id": profile.name},
        )
    return ComponentStatus(
        status="pass",
        message="profile schema is valid",
        details={"profile_id": profile.name, "schema_version": profile.schema_version},
    )


def _writable_dirs_status(profile: Profile) -> ComponentStatus:
    root = Path(profile.root)
    issues: list[str] = []
    for relative_dir in PROFILE_LAYOUT_DIRS:
        path = root / relative_dir
        if not path.is_dir():
            issues.append(f"missing directory: {relative_dir}")
        elif path.stat().st_mode & 0o222 == 0:
            issues.append(f"directory not writable: {relative_dir}")

    status = "pass" if not issues else "fail"
    message = "profile runtime directories are writable" if not issues else "profile runtime directory check failed"
    return ComponentStatus(
        status=status,
        message=message,
        details={"root": str(root), "issues": issues},
    )


def _forbidden_hosted_status(context: ApiProfileContext) -> ComponentStatus:
    findings = hosted_config_findings(context)
    if findings:
        return ComponentStatus(
            status="fail",
            message="forbidden hosted configuration is present",
            details={"findings": findings},
        )
    return ComponentStatus(
        status="pass",
        message="no forbidden hosted configuration detected",
        details={"findings": []},
    )


def _local_http_status(
    *,
    component: str,
    url: str | None,
    context: ApiProfileContext,
    probes: ServiceProbes,
    missing_status: str = "unknown",
    missing_message: str | None = None,
) -> ComponentStatus:
    if not url:
        return ComponentStatus(
            status=missing_status,
            message=missing_message or f"{component} URL is not configured",
            details={},
        )
    if not is_localhost_url(url):
        return ComponentStatus(
            status="fail",
            message=f"{component} endpoint must be localhost",
            details={"url": url},
        )

    decision = check_network_policy(
        context.profile.network_policy,
        url,
        action="localhost-service",
    )
    if not decision.allowed:
        return ComponentStatus(
            status="fail",
            message=decision.reason,
            details={"url": url},
        )
    return _coerce_status(probes.check_http(component, url))


def _searxng_status(context: ApiProfileContext, probes: ServiceProbes) -> ComponentStatus:
    if context.profile.network_policy == "offline":
        return ComponentStatus(
            status="disabled",
            message="offline policy disables SearXNG",
            details={"network_policy": context.profile.network_policy},
        )
    if not context.searxng_url:
        return ComponentStatus(
            status="unknown",
            message="SearXNG URL is not configured",
            details={"network_policy": context.profile.network_policy},
        )
    if not is_localhost_url(context.searxng_url):
        return ComponentStatus(
            status="fail",
            message="SearXNG endpoint must be localhost",
            details={"url": context.searxng_url},
        )

    decision = check_network_policy(
        context.profile.network_policy,
        context.searxng_url,
        action="searxng-query",
        local_searxng=True,
    )
    if not decision.allowed:
        return ComponentStatus(
            status="fail",
            message=decision.reason,
            details={"url": context.searxng_url},
        )
    return _coerce_status(probes.check_http("searxng", context.searxng_url))


def _overall_status(components: Mapping[str, ComponentStatus]) -> str:
    if any(component.status == "fail" for component in components.values()):
        return "fail"
    if any(component.status == "unknown" for component in components.values()):
        return "unknown"
    return "pass"


def build_health_report(
    context: ApiProfileContext,
    probes: ServiceProbes | None = None,
) -> dict[str, object]:
    service_probes = probes or DefaultServiceProbes()
    components: dict[str, ComponentStatus] = {
        "profile_schema": _profile_schema_status(context.profile),
        "writable_dirs": _writable_dirs_status(context.profile),
        "database": _coerce_status(service_probes.check_database(context.database)),
        "redis": _coerce_status(service_probes.check_redis(context.redis)),
        "searxng": _searxng_status(context, service_probes),
        "honcho": _local_http_status(
            component="honcho",
            url=context.honcho_url,
            context=context,
            probes=service_probes,
        ),
        "local_model_models": _local_http_status(
            component="local_model_models",
            url=model_models_url(context.model_base_url),
            context=context,
            probes=service_probes,
        ),
        "brain_api": _local_http_status(
            component="brain_api",
            url=context.brain_api_url,
            context=context,
            probes=service_probes,
            missing_status="pass",
            missing_message="Brain API handled this request",
        ),
        "web_ui": _local_http_status(
            component="web_ui",
            url=context.brain_web_url,
            context=context,
            probes=service_probes,
            missing_message="web UI URL is not configured",
        ),
        "forbidden_hosted_config": _forbidden_hosted_status(context),
    }
    return {
        "profile_id": context.profile_id,
        "overall_status": _overall_status(components),
        "components": {
            name: component.to_dict()
            for name, component in components.items()
        },
    }


def build_status_report(health_report: Mapping[str, object]) -> dict[str, object]:
    components = health_report["components"]
    if not isinstance(components, Mapping):
        raise ValueError("health report components must be a mapping")
    status_by_component = {
        name: str(value["status"])
        for name, value in components.items()
        if isinstance(value, Mapping)
    }
    return {
        "profile_id": health_report["profile_id"],
        "overall_status": health_report["overall_status"],
        "components": status_by_component,
        "failed_components": [
            name for name, status in status_by_component.items() if status == "fail"
        ],
        "unknown_components": [
            name for name, status in status_by_component.items() if status == "unknown"
        ],
        "disabled_components": [
            name for name, status in status_by_component.items() if status == "disabled"
        ],
    }


def build_settings_report(context: ApiProfileContext) -> dict[str, object]:
    hosted_findings = hosted_config_findings(context)
    searxng_hosted = is_hosted_url(context.searxng_url)
    return {
        "profile_id": context.profile_id,
        "profile": {
            "id": context.profile_id,
            "name": context.profile.name,
            "mode": context.profile.mode,
            "root": context.profile.root,
            "network_policy": context.profile.network_policy,
            "storage_backend": context.profile.storage_backend,
            "model_profile": context.profile.model_profile,
            "embedding_profile": context.profile.embedding_profile,
        },
        "database": {
            "profile_id": context.profile_id,
            "name": context.database.database_name,
            "dsn": context.database.redacted_dsn,
        },
        "redis": {
            "profile_id": context.profile_id,
            "url": context.redis.url,
            "key_prefix": context.redis.key_prefix,
        },
        "model": {
            "base_url": context.model_base_url,
            "models_url": model_models_url(context.model_base_url),
            "hosted": is_hosted_url(context.model_base_url),
        },
        "search": {
            "searxng_url": context.searxng_url,
            "searxng_enabled": (
                context.profile.network_policy != "offline"
                and bool(context.searxng_url)
                and not searxng_hosted
            ),
            "hosted": searxng_hosted,
        },
        "extraction": {
            "base_url": context.extraction_base_url,
            "hosted": is_hosted_url(context.extraction_base_url),
        },
        "honcho": {
            "url": context.honcho_url,
            "enabled": bool(context.honcho_url),
        },
        "brain_api": {
            "url": context.brain_api_url,
        },
        "web_ui": {
            "url": context.brain_web_url,
            "available": bool(context.brain_web_url),
        },
        "cors": {
            "allowed_origins": list(DEFAULT_LOCAL_CORS_ORIGINS),
        },
        "hosted_config": {
            "status": "fail" if hosted_findings else "pass",
            "findings": hosted_findings,
        },
    }
