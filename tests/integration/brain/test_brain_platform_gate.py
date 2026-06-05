import json
from pathlib import Path

import pytest

from zsper.brain.commands import health_report_for_profile
from zsper.brain.compose import render_brain_profile
from zsper.brain.ledgers import LedgerKind, append_ledger_record, ledger_path
from zsper.profiles import initialize_profile


class PassingServiceProbes:
    def check_database(self, database):
        from zsper.brain.api import ComponentStatus

        return ComponentStatus(
            status="pass",
            message="database reachable",
            details={"database": database.database_name},
        )

    def check_redis(self, redis):
        from zsper.brain.api import ComponentStatus

        return ComponentStatus(
            status="pass",
            message="redis reachable",
            details={"key_prefix": redis.key_prefix},
        )

    def check_http(self, component: str, url: str):
        from zsper.brain.api import ComponentStatus

        return ComponentStatus(
            status="pass",
            message=f"{component} reachable",
            details={"url": url},
        )


def _env_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value
    return values


def _rendered_api_env(env: dict[str, str], registry_path: Path) -> dict[str, str]:
    api_env = {
        **env,
        "ZSPER_PROFILE_REGISTRY": str(registry_path),
    }
    if api_env.get("ZSPER_PROFILE_ROOT") == "/profile":
        api_env["ZSPER_PROFILE_ROOT"] = api_env["ZSPER_HOST_PROFILE_ROOT"]
    return api_env


@pytest.mark.integration
def test_brain_platform_outputs_are_profile_isolated(
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

    work_rendered = render_brain_profile(work, repo_root=tmp_path / "repo")
    personal_rendered = render_brain_profile(personal, repo_root=tmp_path / "repo")
    work_env = _env_values(work_rendered.env_path)
    personal_env = _env_values(personal_rendered.env_path)
    work_compose = work_rendered.compose_path.read_text(encoding="utf-8")
    personal_compose = personal_rendered.compose_path.read_text(encoding="utf-8")

    assert work_env["ZSPER_PROFILE_ID"] == "work"
    assert personal_env["ZSPER_PROFILE_ID"] == "personal"
    assert work_env["ZSPER_HOST_PROFILE_ROOT"] == str(Path(work.root))
    assert personal_env["ZSPER_HOST_PROFILE_ROOT"] == str(Path(personal.root))
    assert work_env["ZSPER_PROFILE_ROOT"] == "/profile"
    assert personal_env["ZSPER_PROFILE_ROOT"] == "/profile"
    assert work_env["POSTGRES_DB"] == "zsper_work"
    assert personal_env["POSTGRES_DB"] == "zsper_personal"
    assert work_env["REDIS_KEY_PREFIX"] == "zsper:work:"
    assert personal_env["REDIS_KEY_PREFIX"] == "zsper:personal:"
    assert work_env["BRAIN_API_PORT"] != personal_env["BRAIN_API_PORT"]
    assert work_env["BRAIN_WEB_PORT"] != personal_env["BRAIN_WEB_PORT"]

    assert "zsper_work_postgres_data" in work_compose
    assert "zsper_personal_postgres_data" in personal_compose
    assert "zsper_work_redis_runtime" in work_compose
    assert "zsper_personal_redis_runtime" in personal_compose
    assert f"{Path(work.root)}:/profile" in work_compose
    assert f"{Path(personal.root)}:/profile" in personal_compose
    assert str(Path(work.root) / "runtime" / "brain") in work_compose
    assert str(Path(personal.root) / "runtime" / "brain") in personal_compose

    combined = "\n".join((work_compose, personal_compose))
    assert "llm-server" not in combined.lower()
    assert "model-serving" not in combined.lower()
    assert "omlx" not in combined.lower()

    work_ledger = append_ledger_record(
        work,
        LedgerKind.TASKS,
        record_id="task-work",
        payload={"event": "task.created"},
    )
    personal_ledger = append_ledger_record(
        personal,
        LedgerKind.TASKS,
        record_id="task-personal",
        payload={"event": "task.created"},
    )

    assert work_ledger == Path(work.root) / "brain" / "ledgers" / "tasks.jsonl"
    assert personal_ledger == Path(personal.root) / "brain" / "ledgers" / "tasks.jsonl"
    assert work_ledger != personal_ledger
    assert json.loads(work_ledger.read_text(encoding="utf-8"))["profile_id"] == "work"
    assert (
        json.loads(personal_ledger.read_text(encoding="utf-8"))["profile_id"]
        == "personal"
    )
    assert ledger_path(work, LedgerKind.AGENT_RUNS) != ledger_path(
        personal,
        LedgerKind.AGENT_RUNS,
    )
    assert Path(work.root) / "logs" != Path(personal.root) / "logs"

    work_status = health_report_for_profile(
        work,
        probes=PassingServiceProbes(),
        environ=_rendered_api_env(work_env, isolated_registry_path),
    )
    personal_status = health_report_for_profile(
        personal,
        probes=PassingServiceProbes(),
        environ=_rendered_api_env(personal_env, isolated_registry_path),
    )

    assert work_status["profile_id"] == "work"
    assert personal_status["profile_id"] == "personal"
    assert work_status["overall_status"] == "pass"
    assert personal_status["overall_status"] == "pass"
    assert work_status["components"]["local_model_models"]["status"] == "pass"
    assert work_status["components"]["searxng"]["details"]["url"] == (
        "http://searxng:8080"
    )
    assert work_status["components"]["honcho"]["details"]["url"] == (
        "http://honcho:8080"
    )
    assert work_status["components"]["brain_api"]["details"]["url"] == (
        "http://brain-api:8000/api/ping"
    )
