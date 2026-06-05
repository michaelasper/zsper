import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SETUP_SCRIPT = REPO_ROOT / "setup.sh"


def _pythonpath_with_fake_sentence_transformers(tmp_path: Path) -> str:
    fake_root = tmp_path / "fake-pythonpath"
    package_root = fake_root / "sentence_transformers"
    package_root.mkdir(parents=True)
    (package_root / "__init__.py").write_text(
        """
class SentenceTransformer:
    def __init__(self, model_name_or_path, **kwargs):
        if kwargs.get("local_files_only") is not True:
            raise AssertionError("local_files_only must be true")
        if kwargs.get("trust_remote_code") is not False:
            raise AssertionError("trust_remote_code must be false")

    def encode(self, texts, **kwargs):
        if kwargs.get("show_progress_bar") is not False:
            raise AssertionError("show_progress_bar must be false")
        if kwargs.get("normalize_embeddings") is not True:
            raise AssertionError("normalize_embeddings must be true")
        vectors = []
        for text in texts:
            values = [0.0] * 384
            values[0] = float(len(text) or 1)
            values[1] = float(sum(text.encode("utf-8")) % 997)
            vectors.append(tuple(values))
        return tuple(vectors)
""".lstrip(),
        encoding="utf-8",
    )
    return f"{fake_root}:{REPO_ROOT / 'src'}"


def test_setup_air_script_prepares_isolated_air_profile(tmp_path: Path) -> None:
    home = tmp_path / "home"
    config_home = tmp_path / "config"
    data_home = tmp_path / "data"
    env = {
        **os.environ,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(config_home),
        "XDG_DATA_HOME": str(data_home),
        "PYTHONPATH": _pythonpath_with_fake_sentence_transformers(tmp_path),
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
        "PYTHONPATH": _pythonpath_with_fake_sentence_transformers(tmp_path),
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


def test_setup_air_default_venv_installs_rag_runtime_dependencies() -> None:
    script = SETUP_SCRIPT.read_text(encoding="utf-8")

    assert "--editable \"$repo_root\"" in script
    assert "sentence-transformers>=3.0" in script
    assert "docling>=2.0" in script
    assert "rank-bm25>=0.2" in script
