from pathlib import Path

from zsper.brain.compose import render_brain_profile
from zsper.profiles import initialize_profile


def _render(mode: str, tmp_path: Path, isolated_registry_path: Path):
    profile = initialize_profile(
        mode=mode,
        root=tmp_path / mode,
        registry_path=isolated_registry_path,
    )
    return profile, render_brain_profile(profile, repo_root=tmp_path / "repo")


def test_brain_compose_renders_profile_local_files(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile, rendered = _render("work", tmp_path, isolated_registry_path)
    root = Path(profile.root)

    assert rendered.compose_path == root / "brain" / "docker-compose.yml"
    assert rendered.env_path == root / "brain" / ".env"
    assert rendered.schema_path == root / "brain" / "schema.sql"
    assert rendered.compose_path.is_file()
    assert rendered.env_path.is_file()
    assert rendered.schema_path.is_file()

    compose_text = rendered.compose_path.read_text(encoding="utf-8")
    env_text = rendered.env_path.read_text(encoding="utf-8")

    for service in (
        "postgres:",
        "redis:",
        "searxng:",
        "honcho:",
        "brain-api:",
        "brain-web:",
    ):
        assert service in compose_text

    assert f"POSTGRES_DB={profile.database_name}" in env_text
    assert f"ZSPER_PROFILE_ID={profile.name}" in env_text
    assert f"ZSPER_HOST_PROFILE_ROOT={root}" in env_text
    assert "ZSPER_PROFILE_ROOT=/profile" in env_text
    assert f"ZSPER_HOST_BRAIN_ROOT={root / 'brain'}" in env_text
    assert "ZSPER_BRAIN_ROOT=/profile/brain" in env_text
    assert f"ZSPER_HOST_RUNTIME_BRAIN_ROOT={root / 'runtime' / 'brain'}" in env_text
    assert "ZSPER_RUNTIME_BRAIN_ROOT=/profile/runtime/brain" in env_text
    assert f"- {root}:/profile" in compose_text
    assert f"- {root}/brain:/profile/brain" not in compose_text
    assert f"{root}/runtime/brain/postgres" in compose_text
    assert "context: ${ZSPER_REPO_ROOT}" in compose_text
    assert "dockerfile: services/brain-api/Dockerfile" in compose_text
    assert "${ZSPER_REPO_ROOT}/apps/brain-web" in compose_text
    assert "SEARXNG_URL=http://searxng:8080" in env_text
    assert "HONCHO_URL=http://honcho:8080" in env_text
    assert "BRAIN_API_URL=http://brain-api:8000" in env_text
    assert "NEXT_PUBLIC_BRAIN_API_BASE_URL" not in env_text
    assert (Path("services") / "brain-api" / "Dockerfile").is_file()
    assert (Path("apps") / "brain-web" / "Dockerfile").is_file()


def test_brain_compose_is_profile_specific_and_excludes_model_serving(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    work, work_rendered = _render("work", tmp_path, isolated_registry_path)
    personal, personal_rendered = _render("personal", tmp_path, isolated_registry_path)

    work_compose = work_rendered.compose_path.read_text(encoding="utf-8")
    personal_compose = personal_rendered.compose_path.read_text(encoding="utf-8")
    work_env = work_rendered.env_path.read_text(encoding="utf-8")
    personal_env = personal_rendered.env_path.read_text(encoding="utf-8")

    assert work.database_name == "zsper_work"
    assert personal.database_name == "zsper_personal"
    assert f"POSTGRES_DB={work.database_name}" in work_env
    assert f"POSTGRES_DB={personal.database_name}" in personal_env
    assert "zsper_work_postgres_data" in work_compose
    assert "zsper_personal_postgres_data" in personal_compose
    assert "BRAIN_API_PORT=7420" in work_env
    assert "BRAIN_API_PORT=7520" in personal_env

    combined = "\n".join((work_compose, personal_compose, work_env, personal_env))
    assert "llm" + "-server" not in combined.lower()
    assert "model-serving" not in combined.lower()
    assert "omlx" not in combined.lower()
