import json
from pathlib import Path

from zsper.code.adapters.opencode import generate_opencode_adapter
from zsper.code.adapters.pi import generate_pi_adapter
from zsper.code.adapters.zed import generate_zed_adapter
from zsper.profiles import initialize_profile, resolve_profile


def test_work_and_personal_profiles_do_not_share_foundation_state(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    work = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    personal = initialize_profile(
        mode="personal",
        root=tmp_path / "personal",
        registry_path=isolated_registry_path,
    )

    for profile in (work, personal):
        generate_zed_adapter(profile)
        generate_opencode_adapter(profile)
        generate_pi_adapter(profile)

    work_root = Path(work.root)
    personal_root = Path(personal.root)

    assert work.root != personal.root
    assert work.database_name != personal.database_name
    assert work_root / "secrets" != personal_root / "secrets"
    assert work_root / "runtime" / "code" != personal_root / "runtime" / "code"
    assert work_root / "agent-runs" / "runs.jsonl" != personal_root / "agent-runs" / "runs.jsonl"

    for relative in (
        "code/zed/settings.json",
        "code/zed/context_servers.json",
        "code/opencode/opencode.json",
        "code/pi/pi-provider.yml",
        "code/pi/AGENTS.md",
        "code/pi/little-coder.md",
    ):
        work_file = work_root / relative
        personal_file = personal_root / relative
        assert work_file.is_file(), relative
        assert personal_file.is_file(), relative

    for relative in (
        "code/zed/context_servers.json",
        "code/pi/pi-provider.yml",
    ):
        assert str(work_root) in (work_root / relative).read_text(encoding="utf-8")
        assert str(personal_root) in (personal_root / relative).read_text(
            encoding="utf-8"
        )

    rendered_configs = "\n".join(
        path.read_text(encoding="utf-8")
        for root in (work_root, personal_root)
        for path in (root / "code").rglob("*")
        if path.is_file()
    )
    assert "OPENAI_API_KEY" not in rendered_configs
    assert "sk-" not in rendered_configs

    assert resolve_profile("work", registry_path=isolated_registry_path).root == work.root
    assert (
        resolve_profile("personal", registry_path=isolated_registry_path).root
        == personal.root
    )

    registry = json.loads(isolated_registry_path.read_text(encoding="utf-8"))
    roots_by_name = {entry["name"]: entry["root"] for entry in registry["profiles"]}
    assert roots_by_name == {"work": work.root, "personal": personal.root}
