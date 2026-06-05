import os
import subprocess
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
    assert "air-offline" in result.stdout
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
