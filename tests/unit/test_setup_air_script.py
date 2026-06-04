import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SETUP_SCRIPT = REPO_ROOT / "setup.sh"


def test_setup_air_script_prepares_isolated_air_profile(tmp_path: Path) -> None:
    home = tmp_path / "home"
    config_home = tmp_path / "config"
    data_home = tmp_path / "data"
    env = {
        **os.environ,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(config_home),
        "XDG_DATA_HOME": str(data_home),
        "PYTHONPATH": str(REPO_ROOT / "src"),
    }

    result = subprocess.run(
        [str(SETUP_SCRIPT), "--air", "--no-venv"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Air profile ready" in result.stdout
    assert (config_home / "zsper" / "profiles.json").is_file()
    air_root = data_home / "zsper" / "profiles" / "air"
    assert (air_root / "profile.json").is_file()
    assert (air_root / "brain" / "ledgers" / "documents.jsonl").is_file()

    search = subprocess.run(
        [
            "python",
            "-m",
            "zsper",
            "brain",
            "search",
            "--profile",
            "air",
            "offline",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert search.returncode == 0, search.stderr
    assert "air-readiness.md" in search.stdout


def test_setup_air_script_is_rerunnable(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "PYTHONPATH": str(REPO_ROOT / "src"),
    }
    command = [str(SETUP_SCRIPT), "--air", "--no-venv"]

    first = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    second = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert "Using existing air profile" in second.stdout
