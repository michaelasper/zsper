import importlib
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"


def load_pyproject() -> dict:
    assert PYPROJECT.exists(), "Expected pyproject.toml to define package metadata"
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def test_package_import_exposes_version_string() -> None:
    package = importlib.import_module("zsper")

    assert isinstance(package.__version__, str)
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:[a-zA-Z0-9.+-]+)?", package.__version__)


def test_pyproject_configures_src_package_discovery() -> None:
    pyproject = load_pyproject()

    assert pyproject["project"]["name"] == "zsper"
    assert pyproject["build-system"]["build-backend"] == "setuptools.build_meta"
    assert pyproject["tool"]["setuptools"]["packages"]["find"]["where"] == ["src"]
    assert pyproject["tool"]["setuptools"]["packages"]["find"]["include"] == [
        "zsper*"
    ]


def test_pyproject_configures_pytest_defaults() -> None:
    pytest_options = load_pyproject()["tool"]["pytest"]["ini_options"]

    assert pytest_options["testpaths"] == ["tests"]
    assert pytest_options["pythonpath"] == ["src"]
    assert "-ra" in pytest_options["addopts"]


def test_pyproject_declares_required_dependency_groups() -> None:
    groups = load_pyproject()["dependency-groups"]

    expected_groups = {
        "cli": ("typer", "rich"),
        "api": ("fastapi", "uvicorn"),
        "database": ("sqlalchemy", "alembic", "psycopg"),
        "rag": ("docling", "rank-bm25"),
        "web-integration": ("pytest-playwright", "httpx"),
        "dev": ("pytest", "ruff", "mypy"),
    }

    for group_name, expected_dependencies in expected_groups.items():
        dependency_names = "\n".join(groups[group_name]).lower()
        for expected_dependency in expected_dependencies:
            assert expected_dependency in dependency_names


def test_project_declares_core_cli_runtime_dependencies() -> None:
    dependencies = "\n".join(load_pyproject()["project"]["dependencies"]).lower()

    assert "typer" in dependencies
    assert "rich" in dependencies


def test_console_script_points_to_cli_module() -> None:
    scripts = load_pyproject()["project"]["scripts"]

    assert scripts["zsper"] == "zsper.cli:app"


def test_console_script_target_is_importable_and_callable() -> None:
    target = load_pyproject()["project"]["scripts"]["zsper"]
    module_name, attribute_name = target.split(":", maxsplit=1)

    module = importlib.import_module(module_name)
    attribute = getattr(module, attribute_name)

    assert callable(attribute)


def test_console_script_target_renders_cli_help(capsys) -> None:
    target = load_pyproject()["project"]["scripts"]["zsper"]
    module_name, attribute_name = target.split(":", maxsplit=1)
    app = getattr(importlib.import_module(module_name), attribute_name)

    exit_code = app(["--help"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    assert "profile" in captured.out
    assert "code" in captured.out
    assert "brain" in captured.out
    assert "agent" in captured.out


def test_module_main_forwards_injected_arguments(capsys) -> None:
    main = importlib.import_module("zsper.__main__").main

    exit_code = main(["--help"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    assert "profile" in captured.out
    assert "code" in captured.out
    assert "brain" in captured.out
    assert "agent" in captured.out


def test_python_module_entrypoint_renders_help_from_source_checkout() -> None:
    env = os.environ.copy()
    src_path = str(REPO_ROOT / "src")
    env["PYTHONPATH"] = (
        src_path
        if not env.get("PYTHONPATH")
        else f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
    )

    result = subprocess.run(
        [sys.executable, "-m", "zsper", "--help"],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0
    assert result.stderr == ""
    assert "profile" in result.stdout
    assert "code" in result.stdout
    assert "brain" in result.stdout
    assert "agent" in result.stdout
