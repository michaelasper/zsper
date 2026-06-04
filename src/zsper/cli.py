"""Public command-line interface for Zsper."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence


GROUP_COMMANDS: dict[str, tuple[str, ...]] = {
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


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        raise SystemExit(f"{self.prog}: error: {message}")


def _placeholder(namespace: argparse.Namespace) -> int:
    profile = namespace.profile or "default"
    print(
        f"zsper {namespace.group} {namespace.command} is not implemented "
        f"in this milestone (profile={profile}).",
        file=sys.stderr,
    )
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="zsper",
        description="Local-first AI platform CLI.",
    )
    subparsers = parser.add_subparsers(
        title="groups",
        dest="group",
        metavar="{profile,code,brain,agent}",
    )
    subparsers.required = True

    for group, commands in GROUP_COMMANDS.items():
        group_parser = subparsers.add_parser(
            group,
            help=f"{group} commands",
            description=f"Reserved {group} command group.",
        )
        command_parsers = group_parser.add_subparsers(
            title="commands",
            dest="command",
            metavar="COMMAND",
        )
        command_parsers.required = True

        for command in commands:
            command_parser = command_parsers.add_parser(
                command,
                help="Reserved for a later implementation task.",
                description=(
                    f"zsper {group} {command} is reserved for a later "
                    "implementation task."
                ),
            )
            command_parser.add_argument(
                "--profile",
                help="Profile name to resolve when this command is implemented.",
            )
            command_parser.set_defaults(func=_placeholder)

    return parser


def app(argv: Sequence[str] | None = None) -> int:
    """Run the Zsper CLI and return an exit code."""
    args = list(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()

    try:
        namespace = parser.parse_args(args)
    except SystemExit as exc:
        code = exc.code
        if isinstance(code, int):
            return code
        print(code, file=sys.stderr)
        return 2

    handler = getattr(namespace, "func", None)
    if handler is None:
        parser.print_help()
        return 0
    return handler(namespace)


if __name__ == "__main__":
    raise SystemExit(app())
