import json
from pathlib import Path

from zsper.cli import app


def test_profile_cli_init_list_show_and_doctor(
    capsys,
    monkeypatch,
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    monkeypatch.setenv("ZSPER_PROFILE_REGISTRY", str(isolated_registry_path))
    root = tmp_path / "work"

    assert app(["profile", "init", "--mode", "work", "--root", str(root)]) == 0
    assert f"created profile work at {root.resolve()}" in capsys.readouterr().out

    assert app(["profile", "list"]) == 0
    listed = capsys.readouterr()
    assert f"work\twork\t{root.resolve()}" in listed.out

    assert app(["profile", "show", "--profile", "work"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["name"] == "work"
    assert shown["mode"] == "work"
    assert shown["root"] == str(root.resolve())
    assert "secret" not in json.dumps(shown).lower()

    assert app(["profile", "doctor", "--profile", "work"]) == 0
    assert "profile work OK" in capsys.readouterr().out


def test_profile_cli_errors_do_not_leak_secret_values(
    capsys,
    monkeypatch,
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    monkeypatch.setenv("ZSPER_PROFILE_REGISTRY", str(isolated_registry_path))
    root = tmp_path / "work"
    assert app(["profile", "init", "--mode", "work", "--root", str(root)]) == 0
    capsys.readouterr()

    secret_path = root / "secrets" / "token.txt"
    secret_path.write_text("super-secret-value", encoding="utf-8")

    assert app(["profile", "show", "--profile", "work"]) == 0
    captured = capsys.readouterr()

    assert "super-secret-value" not in captured.out


def test_profile_doctor_requires_profile_ref(capsys) -> None:
    assert app(["profile", "doctor"]) == 1

    captured = capsys.readouterr()
    assert "profile name or root is required" in captured.err
