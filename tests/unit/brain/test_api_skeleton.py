from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

from zsper.profiles import initialize_profile


SERVICE_ROOT = Path(__file__).resolve().parents[3] / "services" / "brain-api"
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.main import create_app  # noqa: E402


def _service_env(profile, registry_path: Path) -> dict[str, str]:
    return {
        "ZSPER_PROFILE_ID": profile.name,
        "ZSPER_PROFILE_ROOT": profile.root,
        "ZSPER_PROFILE_REGISTRY": str(registry_path),
        "POSTGRES_DB": profile.database_name,
        "POSTGRES_DSN": f"postgresql://zsper:local@127.0.0.1/{profile.database_name}",
        "REDIS_URL": "redis://127.0.0.1:6379/0",
        "REDIS_KEY_PREFIX": f"zsper:{profile.name}:",
        "ZSPER_MODEL_BASE_URL": "http://127.0.0.1:9127/v1",
    }


def test_api_ping_does_not_require_profile_context() -> None:
    client = TestClient(create_app(environ={}))

    response = client.get("/api/ping")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "brain-api"}


def test_api_app_imports_and_serves_profile_aware_test_client(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    app = create_app(environ=_service_env(profile, isolated_registry_path))
    client = TestClient(app)

    response = client.get(
        "/api/settings",
        headers={
            "Origin": "http://localhost:3000",
            "X-Zsper-Profile-Id": "work",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    body = response.json()
    assert body["profile_id"] == "work"
    assert body["profile"]["mode"] == "work"
    assert body["database"]["profile_id"] == "work"
    assert body["database"]["name"] == "zsper_work"
    assert body["redis"]["profile_id"] == "work"
    assert body["redis"]["key_prefix"] == "zsper:work:"


def test_local_only_cors_does_not_allow_hosted_origins(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="personal",
        root=tmp_path / "personal",
        registry_path=isolated_registry_path,
    )
    app = create_app(environ=_service_env(profile, isolated_registry_path))
    client = TestClient(app)

    response = client.get(
        "/api/settings",
        headers={
            "Origin": "https://example.com",
            "X-Zsper-Profile-Id": "personal",
        },
    )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_missing_profile_context_returns_structured_error() -> None:
    client = TestClient(create_app(environ={}))

    response = client.get("/api/settings")

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "missing_profile_context",
            "message": "profile context is required",
            "status_code": 400,
            "profile_id": None,
            "details": {},
        }
    }


def test_wrong_profile_context_returns_structured_error(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    work = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    initialize_profile(
        mode="personal",
        root=tmp_path / "personal",
        registry_path=isolated_registry_path,
    )
    client = TestClient(create_app(environ=_service_env(work, isolated_registry_path)))

    response = client.get(
        "/api/settings",
        headers={"X-Zsper-Profile-Id": "personal"},
    )

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "profile_context_mismatch",
            "message": "request profile context does not match service profile",
            "status_code": 403,
            "profile_id": "work",
            "details": {"requested_profile_id": "personal"},
        }
    }


def test_wrong_profile_root_context_returns_structured_error(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    work = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    personal = initialize_profile(
        mode="personal",
        root=tmp_path / "personal",
        registry_path=isolated_registry_path,
    )
    client = TestClient(create_app(environ=_service_env(work, isolated_registry_path)))

    response = client.get(
        "/api/settings",
        headers={"X-Zsper-Profile-Root": personal.root},
    )

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "profile_context_mismatch",
            "message": "request profile root does not match service profile",
            "status_code": 403,
            "profile_id": "work",
            "details": {
                "requested_profile_id": "personal",
                "requested_profile_root": personal.root,
            },
        }
    }


def test_database_context_must_match_resolved_profile(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    work = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    personal = initialize_profile(
        mode="personal",
        root=tmp_path / "personal",
        registry_path=isolated_registry_path,
    )
    env = _service_env(work, isolated_registry_path)
    env["POSTGRES_DB"] = personal.database_name
    env["POSTGRES_DSN"] = (
        f"postgresql://zsper:local@127.0.0.1/{personal.database_name}"
    )
    client = TestClient(create_app(environ=env))

    response = client.get(
        "/api/settings",
        headers={"X-Zsper-Profile-Id": "work"},
    )

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "invalid_service_config",
            "message": "database configuration does not match service profile",
            "status_code": 500,
            "profile_id": "work",
            "details": {
                "expected_database_name": "zsper_work",
                "configured_database_name": "zsper_personal",
                "dsn_database_name": "zsper_personal",
            },
        }
    }


def test_invalid_profile_context_returns_structured_error(
    isolated_registry_path: Path,
) -> None:
    client = TestClient(
        create_app(
            environ={
                "ZSPER_PROFILE_ID": "missing",
                "ZSPER_PROFILE_REGISTRY": str(isolated_registry_path),
            }
        )
    )

    response = client.get("/api/settings")

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "invalid_profile_context"
    assert body["error"]["status_code"] == 400
    assert body["error"]["profile_id"] == "missing"
    assert "profile not found: missing" in body["error"]["message"]
