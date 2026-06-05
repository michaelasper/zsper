import pytest

from zsper.cli import app


GROUP_COMMANDS = {
    "profile": ("init", "list", "show", "doctor"),
    "code": (
        "start",
        "stop",
        "status",
        "smoke",
        "install-zed",
        "install-opencode",
        "install-pi",
    ),
    "brain": ("up", "down", "status", "ingest", "search", "answer"),
    "agent": ("run", "attach", "status", "cancel"),
}
IMPLEMENTED_GROUP_COMMANDS = {
    "profile": GROUP_COMMANDS["profile"],
    "code": GROUP_COMMANDS["code"],
    "brain": ("up", "down", "status", "ingest", "search", "answer"),
}
PLACEHOLDER_GROUP_COMMANDS = {
    group: tuple(
        command
        for command in commands
        if command not in IMPLEMENTED_GROUP_COMMANDS.get(group, ())
    )
    for group, commands in GROUP_COMMANDS.items()
}


@pytest.mark.parametrize("help_flag", ["--help", "-h"])
def test_root_help_shows_all_cli_groups(capsys, help_flag: str) -> None:
    exit_code = app([help_flag])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    for group in GROUP_COMMANDS:
        assert group in captured.out


@pytest.mark.parametrize(("group", "commands"), GROUP_COMMANDS.items())
def test_group_help_shows_reserved_commands(
    capsys, group: str, commands: tuple[str, ...]
) -> None:
    exit_code = app([group, "--help"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    for command in commands:
        assert command in captured.out


@pytest.mark.parametrize(
    ("group", "command"),
    [
        (group, command)
        for group, commands in PLACEHOLDER_GROUP_COMMANDS.items()
        for command in commands
    ],
)
def test_reserved_commands_return_milestone_placeholder(
    capsys, group: str, command: str
) -> None:
    exit_code = app([group, command])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "not implemented in this milestone" in captured.err
    assert f"{group} {command}" in captured.err


@pytest.mark.parametrize(
    ("argv", "profile"),
    [
        (["brain", "search", "--profile", "air"], "air"),
        (["agent", "run", "--profile", "work"], "work"),
    ],
)
def test_operational_commands_accept_profile_option(
    capsys, argv: list[str], profile: str
) -> None:
    exit_code = app(argv)
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "not implemented in this milestone" in captured.err
    assert f"profile={profile}" in captured.err


@pytest.mark.parametrize(
    ("argv", "profile"),
    [
        (["brain", "ingest", "README.md", "--profile", "work"], "work"),
        (["brain", "search", "hybrid retrieval", "--profile", "work"], "work"),
        (
            ["agent", "run", "--harness", "pi", "--task", "123", "--profile", "work"],
            "work",
        ),
        (["agent", "attach", "--run", "123", "--profile", "work"], "work"),
        (["agent", "status", "--run", "123", "--profile", "work"], "work"),
        (["agent", "cancel", "--run", "123", "--profile", "work"], "work"),
    ],
)
def test_documented_reserved_command_shapes_reach_placeholder(
    capsys, argv: list[str], profile: str
) -> None:
    exit_code = app(argv)
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "error:" not in captured.err
    assert "not implemented in this milestone" in captured.err
    assert f"zsper {argv[0]} {argv[1]}" in captured.err
    assert f"profile={profile}" in captured.err
