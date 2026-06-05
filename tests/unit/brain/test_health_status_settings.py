from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from zsper.brain.api import ComponentStatus
from zsper.profiles import initialize_profile


SERVICE_ROOT = Path(__file__).resolve().parents[3] / "services" / "brain-api"
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.main import create_app  # noqa: E402


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


def _service_env(profile, registry_path: Path, **overrides: str) -> dict[str, str]:
    env = {
        "ZSPER_PROFILE_ID": profile.name,
        "ZSPER_PROFILE_ROOT": profile.root,
        "ZSPER_PROFILE_REGISTRY": str(registry_path),
        "POSTGRES_DB": profile.database_name,
        "POSTGRES_DSN": f"postgresql://zsper:local@127.0.0.1/{profile.database_name}",
        "REDIS_URL": "redis://127.0.0.1:6379/0",
        "REDIS_KEY_PREFIX": f"zsper:{profile.name}:",
        "ZSPER_MODEL_BASE_URL": "http://127.0.0.1:9127/v1",
        "SEARXNG_URL": "http://127.0.0.1:8080",
        "HONCHO_URL": "http://127.0.0.1:8001",
        "BRAIN_API_URL": "http://127.0.0.1:7420",
        "BRAIN_WEB_URL": "http://127.0.0.1:7421",
    }
    env.update(overrides)
    return env


def test_health_status_and_settings_report_profile_and_local_service_checks(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    probes = FakeServiceProbes()
    client = TestClient(
        create_app(
            environ=_service_env(profile, isolated_registry_path),
            service_probes=probes,
        )
    )

    health = client.get("/api/health", headers={"X-Zsper-Profile-Id": "work"})
    status = client.get("/api/status", headers={"X-Zsper-Profile-Id": "work"})
    settings = client.get("/api/settings", headers={"X-Zsper-Profile-Id": "work"})

    assert health.status_code == 200
    health_body = health.json()
    assert health_body["profile_id"] == "work"
    assert health_body["overall_status"] == "pass"
    assert health_body["components"]["profile_schema"]["status"] == "pass"
    assert health_body["components"]["writable_dirs"]["status"] == "pass"
    assert health_body["components"]["database"]["status"] == "pass"
    assert health_body["components"]["redis"]["status"] == "pass"
    assert health_body["components"]["searxng"]["status"] == "pass"
    assert health_body["components"]["honcho"]["status"] == "pass"
    assert health_body["components"]["local_model_models"]["status"] == "pass"
    assert health_body["components"]["brain_api"]["status"] == "pass"
    assert health_body["components"]["web_ui"]["status"] == "pass"
    assert health_body["components"]["forbidden_hosted_config"]["status"] == "pass"
    assert ("local_model_models", "http://127.0.0.1:9127/v1/models") in probes.http_urls
    assert ("brain_api", "http://127.0.0.1:7420/api/ping") in probes.http_urls

    assert status.status_code == 200
    status_body = status.json()
    assert status_body["profile_id"] == "work"
    assert status_body["overall_status"] == "pass"
    assert status_body["failed_components"] == []
    assert status_body["components"]["database"] == "pass"

    assert settings.status_code == 200
    settings_body = settings.json()
    assert settings_body["profile_id"] == "work"
    assert settings_body["profile"]["network_policy"] == "local-first"
    assert settings_body["model"]["base_url"] == "http://127.0.0.1:9127/v1"
    assert settings_body["search"]["searxng_enabled"] is True
    assert settings_body["hosted_config"]["status"] == "pass"


def test_health_and_settings_redact_redis_credentials(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    client = TestClient(
        create_app(
            environ=_service_env(
                profile,
                isolated_registry_path,
                REDIS_URL="redis://:redis-secret@127.0.0.1:6379/0",
            ),
            service_probes=FakeServiceProbes(),
        )
    )

    health = client.get("/api/health", headers={"X-Zsper-Profile-Id": "work"}).json()
    settings = client.get("/api/settings", headers={"X-Zsper-Profile-Id": "work"}).json()

    serialized = json.dumps({"health": health, "settings": settings})
    assert "redis-secret" not in serialized
    assert settings["redis"]["url"] == "redis://:***@127.0.0.1:6379/0"
    assert health["components"]["redis"]["details"]["url"] == (
        "redis://:***@127.0.0.1:6379/0"
    )


def test_offline_profile_reports_searxng_disabled_not_failed(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="air-offline",
        root=tmp_path / "air",
        registry_path=isolated_registry_path,
    )
    client = TestClient(
        create_app(
            environ=_service_env(profile, isolated_registry_path),
            service_probes=FakeServiceProbes(),
        )
    )

    response = client.get("/api/health", headers={"X-Zsper-Profile-Id": "air"})

    assert response.status_code == 200
    body = response.json()
    assert body["profile_id"] == "air"
    assert body["components"]["searxng"]["status"] == "disabled"
    assert body["components"]["searxng"]["message"] == "offline policy disables SearXNG"
    assert body["components"]["searxng"]["status"] != "fail"


def test_docker_host_model_endpoint_is_treated_as_local_contract(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    probes = FakeServiceProbes()
    client = TestClient(
        create_app(
            environ=_service_env(
                profile,
                isolated_registry_path,
                ZSPER_MODEL_BASE_URL="http://host.docker.internal:9127/v1",
            ),
            service_probes=probes,
        )
    )

    health = client.get("/api/health", headers={"X-Zsper-Profile-Id": "work"}).json()
    settings = client.get("/api/settings", headers={"X-Zsper-Profile-Id": "work"}).json()

    assert health["components"]["local_model_models"]["status"] == "pass"
    assert (
        "local_model_models",
        "http://host.docker.internal:9127/v1/models",
    ) in probes.http_urls
    assert settings["model"]["hosted"] is False
    assert settings["hosted_config"]["status"] == "pass"


def test_health_reports_mocked_service_failures_with_clear_fields(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="personal",
        root=tmp_path / "personal",
        registry_path=isolated_registry_path,
    )
    client = TestClient(
        create_app(
            environ=_service_env(profile, isolated_registry_path),
            service_probes=FakeServiceProbes(
                {
                    "redis": "redis ping failed",
                    "local_model_models": "model endpoint refused connection",
                }
            ),
        )
    )

    response = client.get("/api/health", headers={"X-Zsper-Profile-Id": "personal"})

    assert response.status_code == 200
    body = response.json()
    assert body["profile_id"] == "personal"
    assert body["overall_status"] == "fail"
    assert body["components"]["redis"] == {
        "status": "fail",
        "message": "redis ping failed",
        "details": {"url": "redis://127.0.0.1:6379/0"},
    }
    assert body["components"]["local_model_models"]["status"] == "fail"
    assert body["components"]["local_model_models"]["message"] == (
        "model endpoint refused connection"
    )


def test_hosted_model_search_and_extraction_config_is_flagged(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    profile_path = Path(profile.root) / "profile.json"
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    payload["core_integrations"] = {
        "model_api": "https://api.openai.com/v1",
        "search_api": "https://serpapi.com/search",
        "extraction_api": "https://api.firecrawl.dev/v1/scrape",
    }
    profile_path.write_text(json.dumps(payload), encoding="utf-8")
    client = TestClient(
        create_app(
            environ=_service_env(
                profile,
                isolated_registry_path,
                ZSPER_MODEL_BASE_URL="https://api.openai.com/v1",
                SEARXNG_URL="https://serpapi.com/search",
                EXTRACTION_BASE_URL="https://api.firecrawl.dev/v1/scrape",
            ),
            service_probes=FakeServiceProbes(),
        )
    )

    health = client.get("/api/health", headers={"X-Zsper-Profile-Id": "work"}).json()
    settings = client.get("/api/settings", headers={"X-Zsper-Profile-Id": "work"}).json()

    hosted = health["components"]["forbidden_hosted_config"]
    assert hosted["status"] == "fail"
    assert set(hosted["details"]["findings"]) >= {
        "api.openai.com",
        "hosted search API",
        "hosted extraction API",
    }
    assert settings["hosted_config"]["status"] == "fail"
    assert settings["model"]["hosted"] is True
    assert settings["search"]["hosted"] is True
    assert settings["extraction"]["hosted"] is True
