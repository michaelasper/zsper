import json
from pathlib import Path

from zsper.cli import app


def test_cli_air_profile_init_show_list_and_doctor(
    capsys,
    monkeypatch,
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    monkeypatch.setenv("ZSPER_PROFILE_REGISTRY", str(isolated_registry_path))
    root = tmp_path / "air-profile"

    init_code = app(
        ["profile", "init", "--mode", "air-offline", "--root", str(root)]
    )
    init_output = capsys.readouterr()
    list_code = app(["profile", "list"])
    list_output = capsys.readouterr()
    show_code = app(["profile", "show", "--profile", "air"])
    show_output = capsys.readouterr()
    doctor_code = app(["profile", "doctor", "--profile", "air"])
    doctor_output = capsys.readouterr()

    assert init_code == 0
    assert "created profile air" in init_output.out
    assert init_output.err == ""
    assert (root / "profile.json").is_file()

    assert list_code == 0
    assert "air" in list_output.out
    assert "air-offline" in list_output.out
    assert str(root.resolve()) in list_output.out

    assert show_code == 0
    profile_json = json.loads(show_output.out)
    assert profile_json["name"] == "air"
    assert profile_json["network_policy"] == "offline"
    assert profile_json["model_profile"] == "zsper-air-gemma4-12b-it-6bit-128k"

    assert doctor_code == 0
    assert "profile air OK" in doctor_output.out
    assert doctor_output.err == ""


def test_cli_air_profile_blocks_url_ingest_before_placeholder(
    capsys,
    monkeypatch,
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    monkeypatch.setenv("ZSPER_PROFILE_REGISTRY", str(isolated_registry_path))
    root = tmp_path / "air-profile"
    assert app(["profile", "init", "--mode", "air-offline", "--root", str(root)]) == 0
    capsys.readouterr()

    exit_code = app(
        ["brain", "ingest", "https://example.com/research.md", "--profile", "air"]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "offline policy blocks url-ingest" in captured.err
    assert "not implemented" not in captured.err


def test_cli_air_profile_local_file_ingest_reaches_placeholder(
    capsys,
    monkeypatch,
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    monkeypatch.setenv("ZSPER_PROFILE_REGISTRY", str(isolated_registry_path))
    root = tmp_path / "air-profile"
    local_file = tmp_path / "notes.md"
    local_file.write_text("offline notes", encoding="utf-8")
    assert app(["profile", "init", "--mode", "air-offline", "--root", str(root)]) == 0
    capsys.readouterr()

    exit_code = app(["brain", "ingest", str(local_file), "--profile", "air"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "ingested document" in captured.out
    assert "offline policy blocks" not in captured.err

    search_code = app(["brain", "search", "offline notes", "--profile", "air"])
    search_output = capsys.readouterr()

    assert search_code == 0
    assert "offline notes" in search_output.out
    assert str(local_file.resolve()) in search_output.out
