import json
from pathlib import Path

from zsper.profiles.doctor import profile_doctor
from zsper.profiles.init import initialize_profile


def test_doctor_passes_for_healthy_profiles(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    for mode in ("work", "personal", "air-offline"):
        name = "air" if mode == "air-offline" else mode
        initialize_profile(
            mode=mode,
            root=tmp_path / name,
            registry_path=isolated_registry_path,
        )

        report = profile_doctor(name, registry_path=isolated_registry_path)

        assert report.ok is True
        assert report.errors == []


def test_doctor_reports_missing_directory(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    (Path(profile.root) / "brain" / "documents").rmdir()

    report = profile_doctor("work", registry_path=isolated_registry_path)

    assert report.ok is False
    assert "missing directory: brain/documents" in report.errors


def test_doctor_reports_any_unwritable_required_directory(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    code_dir = Path(profile.root) / "code" / "zed"
    code_dir.chmod(0o500)

    try:
        report = profile_doctor("work", registry_path=isolated_registry_path)
    finally:
        code_dir.chmod(0o700)

    assert report.ok is False
    assert "directory not writable: code/zed" in report.errors


def test_doctor_reports_invalid_policy_and_forbidden_hosted_config(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    profile_path = Path(profile.root) / "profile.json"
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    payload["remote_access_policy"] = "tailscale-serve-only"
    payload["core_integrations"] = {"model_api": "https://api.openai.com/v1"}
    profile_path.write_text(json.dumps(payload), encoding="utf-8")

    report = profile_doctor(profile.root, registry_path=isolated_registry_path)

    assert report.ok is False
    assert any("work profiles default to disabled" in error for error in report.errors)
    assert any("forbidden hosted dependency" in error for error in report.errors)
