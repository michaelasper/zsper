import os
import subprocess
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SCRIPT = REPO_ROOT / "install.sh"


def test_install_script_help_is_profile_neutral() -> None:
    result = subprocess.run(
        [str(INSTALL_SCRIPT), "--help"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Usage: install.sh [options]" in result.stdout
    assert "does not create a profile" in result.stdout
    assert "--air" not in result.stdout


def test_install_script_dry_run_uses_home_config_without_default_profile(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    env = {
        **os.environ,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local" / "share"),
    }

    result = subprocess.run(
        [
            str(INSTALL_SCRIPT),
            "--dry-run",
            "--repo",
            "https://example.invalid/zsper.git",
            "--ref",
            "main",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "No profile was created and no default profile was selected." in result.stdout
    assert "ZSPER_CONFIG_DIR" in result.stdout
    assert "ZSPER_PROFILE_REGISTRY" in result.stdout
    assert "zsper profile use work" in result.stdout
    assert "--mode air" in result.stdout
    assert "--network-policy offline" in result.stdout
    assert "setup.sh --air" not in result.stdout
    assert not (home / ".config" / "zsper" / "config.toml").exists()
    assert not (home / ".config" / "zsper" / "profiles.json").exists()
    assert not (home / ".local" / "share" / "zsper" / "profiles").exists()


def test_install_script_has_valid_bash_syntax() -> None:
    result = subprocess.run(
        ["bash", "-n", str(INSTALL_SCRIPT)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_install_script_installs_brain_and_rag_runtime_extras() -> None:
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert '"$app_dir[api,database,rag]"' in script

    optional_dependencies = pyproject["project"]["optional-dependencies"]
    assert "fastapi>=0.115" in optional_dependencies["api"]
    assert "psycopg[binary]>=3.2" in optional_dependencies["database"]
    assert "sentence-transformers>=3.0" in optional_dependencies["rag"]
    assert "docling>=2.0" in optional_dependencies["rag"]
