import importlib
import tomllib
from collections.abc import Callable
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_USER_HOME = Path("/Users/michaelasper")


def load_pyproject() -> dict:
    return tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_profile_root_factory_returns_unique_roots_under_tmp_path(
    profile_root_factory,
    tmp_path: Path,
) -> None:
    work_root = profile_root_factory("work")
    personal_root = profile_root_factory("personal")

    assert work_root != personal_root
    assert work_root.is_dir()
    assert personal_root.is_dir()
    assert work_root.is_relative_to(tmp_path)
    assert personal_root.is_relative_to(tmp_path)


def test_isolated_registry_path_is_under_tmp_path(
    isolated_registry_path: Path,
    tmp_path: Path,
) -> None:
    assert isolated_registry_path == tmp_path / "registry" / "profiles.json"
    assert isolated_registry_path.parent.is_dir()
    assert isolated_registry_path.is_relative_to(tmp_path)
    assert not isolated_registry_path.is_relative_to(REAL_USER_HOME)


def test_default_home_is_isolated_under_tmp_path(tmp_path: Path) -> None:
    home = Path.home()

    assert home.is_dir()
    assert home.is_relative_to(tmp_path)
    assert not home.is_relative_to(REAL_USER_HOME)


def test_real_home_write_guard_blocks_unmarked_path_writes() -> None:
    target = REAL_USER_HOME / ".zsper-nonexistent-write-guard" / "sentinel.txt"

    with pytest.raises(RuntimeError, match="Refusing to write under real user home"):
        target.write_text("blocked", encoding="utf-8")


def _open_path(path: Path, mode: str) -> None:
    with path.open(mode, encoding="utf-8"):
        pass


@pytest.mark.parametrize(
    ("operation_name", "operation"),
    (
        pytest.param(
            "write_bytes",
            lambda path: path.write_bytes(b"blocked"),
            id="write_bytes",
        ),
        pytest.param("touch", lambda path: path.touch(), id="touch"),
        pytest.param("mkdir", lambda path: path.mkdir(), id="mkdir"),
        pytest.param("open_w", lambda path: _open_path(path, "w"), id="open-w"),
        pytest.param("open_r_plus", lambda path: _open_path(path, "r+"), id="open-r-plus"),
    ),
)
def test_real_home_write_guard_blocks_other_write_operations_on_nonexistent_paths(
    operation_name: str,
    operation: Callable[[Path], object],
) -> None:
    target = REAL_USER_HOME / ".zsper-nonexistent-write-guard" / operation_name

    with pytest.raises(RuntimeError, match="Refusing to write under real user home"):
        operation(target)

    assert not target.exists()


def test_real_home_write_guard_allows_explicit_opt_out_without_writing() -> None:
    harness = importlib.import_module("conftest")
    target = REAL_USER_HOME / ".zsper-not-written-by-test"

    harness.assert_not_real_home_write(target, allow_real_home=True)


def test_pytest_marker_definitions_exist() -> None:
    marker_definitions = load_pyproject()["tool"]["pytest"]["ini_options"]["markers"]
    marker_names = {definition.split(":", maxsplit=1)[0] for definition in marker_definitions}

    assert {"unit", "integration", "e2e", "security", "slow", "real_home"} <= marker_names
