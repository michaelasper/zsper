from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest


REAL_USER_HOME = Path("/Users/michaelasper")
WRITE_MODE_CHARS = frozenset("wax+")


def _is_under_real_user_home(path: Path) -> bool:
    try:
        resolved_path = path.resolve(strict=False)
        resolved_home = REAL_USER_HOME.resolve(strict=False)
    except OSError:
        resolved_path = path.absolute()
        resolved_home = REAL_USER_HOME.absolute()

    return resolved_path == resolved_home or resolved_path.is_relative_to(resolved_home)


def assert_not_real_home_write(path: Path | str, *, allow_real_home: bool = False) -> None:
    if allow_real_home:
        return

    candidate = Path(path)
    if _is_under_real_user_home(candidate):
        raise RuntimeError(f"Refusing to write under real user home during tests: {candidate}")


def _is_write_mode(mode: str) -> bool:
    return any(char in mode for char in WRITE_MODE_CHARS)


@pytest.fixture(autouse=True)
def isolated_test_home(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest, tmp_path: Path) -> None:
    allow_real_home = bool(request.node.get_closest_marker("real_home"))

    original_write_text = Path.write_text
    original_write_bytes = Path.write_bytes
    original_touch = Path.touch
    original_mkdir = Path.mkdir
    original_open = Path.open

    def guarded_write_text(self: Path, *args: Any, **kwargs: Any) -> int:
        assert_not_real_home_write(self, allow_real_home=allow_real_home)
        return original_write_text(self, *args, **kwargs)

    def guarded_write_bytes(self: Path, *args: Any, **kwargs: Any) -> int:
        assert_not_real_home_write(self, allow_real_home=allow_real_home)
        return original_write_bytes(self, *args, **kwargs)

    def guarded_touch(self: Path, *args: Any, **kwargs: Any) -> None:
        assert_not_real_home_write(self, allow_real_home=allow_real_home)
        return original_touch(self, *args, **kwargs)

    def guarded_mkdir(self: Path, *args: Any, **kwargs: Any) -> None:
        assert_not_real_home_write(self, allow_real_home=allow_real_home)
        return original_mkdir(self, *args, **kwargs)

    def guarded_open(self: Path, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if _is_write_mode(mode):
            assert_not_real_home_write(self, allow_real_home=allow_real_home)
        return original_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", guarded_write_text)
    monkeypatch.setattr(Path, "write_bytes", guarded_write_bytes)
    monkeypatch.setattr(Path, "touch", guarded_touch)
    monkeypatch.setattr(Path, "mkdir", guarded_mkdir)
    monkeypatch.setattr(Path, "open", guarded_open)

    if allow_real_home:
        return

    home = tmp_path / "home"
    config_home = home / ".config"
    data_home = home / ".local" / "share"
    cache_home = home / ".cache"

    for path in (home, config_home, data_home, cache_home):
        path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_home))


@pytest.fixture
def profile_root_factory(tmp_path: Path) -> Callable[[str], Path]:
    counter = 0

    def make_profile_root(name: str = "profile") -> Path:
        nonlocal counter
        counter += 1
        profile_root = tmp_path / "profiles" / f"{counter}-{name}"
        profile_root.mkdir(parents=True)
        return profile_root

    return make_profile_root


@pytest.fixture
def isolated_registry_path(tmp_path: Path) -> Path:
    registry_path = tmp_path / "registry" / "profiles.json"
    registry_path.parent.mkdir(parents=True)
    return registry_path
