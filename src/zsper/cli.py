"""Public command-line interface for Zsper."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence


GROUP_COMMANDS: dict[str, tuple[str, ...]] = {
    "profile": ("init", "list", "show", "doctor", "use"),
    "code": (
        "start",
        "stop",
        "status",
        "smoke",
        "install-zed",
        "install-opencode",
        "install-pi",
    ),
    "brain": (
        "up",
        "down",
        "status",
        "context-server",
        "ingest",
        "search",
        "answer",
    ),
    "agent": ("run", "attach", "status", "cancel"),
}
PROFILE_MODES = ("work", "personal", "air-offline")
AGENT_HARNESSES = ("pi", "opencode", "hermes")


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        raise SystemExit(f"{self.prog}: error: {message}")


def _placeholder(namespace: argparse.Namespace) -> int:
    if namespace.group == "brain" and namespace.command == "ingest":
        policy_exit_code = _maybe_reject_ingest_by_profile_policy(namespace)
        if policy_exit_code is not None:
            return policy_exit_code

    profile = _profile_ref_for_command(namespace.profile, missing_ok=True) or "unconfigured"
    print(
        f"zsper {namespace.group} {namespace.command} is not implemented "
        f"in this milestone (profile={profile}).",
        file=sys.stderr,
    )
    return 1


def _profile_init(namespace: argparse.Namespace) -> int:
    from zsper.profiles import ProfileError, initialize_profile

    try:
        profile = initialize_profile(
            mode=namespace.mode,
            root=namespace.root,
            name=namespace.name,
        )
    except ProfileError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"created profile {profile.name} at {profile.root}")
    return 0


def _profile_list(namespace: argparse.Namespace) -> int:
    del namespace
    from zsper.profiles import ProfileError, list_profiles

    try:
        profiles = list_profiles()
    except ProfileError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    for profile in profiles:
        print(f"{profile.name}\t{profile.mode}\t{profile.root}")
    return 0


def _profile_show(namespace: argparse.Namespace) -> int:
    from zsper.config.user import UserConfigError, profile_ref_or_default
    from zsper.profiles import ProfileError, resolve_profile

    try:
        profile = resolve_profile(profile_ref_or_default(namespace.profile))
    except (ProfileError, UserConfigError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(profile.to_dict(), indent=2, sort_keys=True))
    return 0


def _profile_doctor(namespace: argparse.Namespace) -> int:
    from zsper.config.user import UserConfigError, profile_ref_or_default
    from zsper.profiles import ProfileError, profile_doctor

    try:
        report = profile_doctor(profile_ref_or_default(namespace.profile))
    except (ProfileError, UserConfigError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if report.ok:
        print(f"profile {report.profile.name} OK")
        return 0

    for error in report.errors:
        print(error, file=sys.stderr)
    return 1


def _profile_use(namespace: argparse.Namespace) -> int:
    from zsper.config.user import UserConfigError, set_default_profile
    from zsper.profiles import ProfileError, resolve_profile

    try:
        profile = resolve_profile(namespace.profile_name)
        config_path = set_default_profile(profile.name)
    except (ProfileError, UserConfigError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"default profile set to {profile.name}")
    print(f"config: {config_path}")
    return 0


def _profile_ref_for_command(
    explicit_profile_ref: str | None,
    *,
    missing_ok: bool = False,
) -> str | None:
    from zsper.config.user import UserConfigError, profile_ref_or_default

    try:
        return profile_ref_or_default(explicit_profile_ref)
    except UserConfigError:
        if missing_ok:
            return None
        raise


def _maybe_reject_ingest_by_profile_policy(namespace: argparse.Namespace) -> int | None:
    from zsper.config.user import UserConfigError
    from zsper.profiles import ProfileError, resolve_profile
    from zsper.security.network_policy import check_network_policy, looks_like_url

    if not namespace.path_or_url:
        return None

    try:
        profile = resolve_profile(_profile_ref_for_command(namespace.profile))
    except (ProfileError, UserConfigError):
        return None

    action = "url-ingest" if looks_like_url(namespace.path_or_url) else "local-file-read"
    decision = check_network_policy(
        profile.network_policy,
        namespace.path_or_url,
        action=action,
        user_triggered=True,
    )
    if decision.allowed:
        return None

    print(decision.reason, file=sys.stderr)
    return 1


def _brain_ingest(namespace: argparse.Namespace) -> int:
    from zsper.config.user import UserConfigError
    from zsper.brain.offline_store import BrainOfflineError, ingest_local_file
    from zsper.profiles import ProfileError, resolve_profile

    try:
        profile = resolve_profile(_profile_ref_for_command(namespace.profile))
    except UserConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ProfileError:
        return _placeholder(namespace)

    if profile.mode != "air-offline":
        return _placeholder(namespace)

    if not namespace.path_or_url:
        print("path-or-url is required for brain ingest", file=sys.stderr)
        return 2

    try:
        document = ingest_local_file(profile, namespace.path_or_url)
    except BrainOfflineError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"ingested document {document.document_id}\t{document.source_path}")
    return 0


def _brain_search(namespace: argparse.Namespace) -> int:
    from zsper.config.user import UserConfigError
    from zsper.brain.offline_store import BrainOfflineError, search_local_files
    from zsper.profiles import ProfileError, resolve_profile

    try:
        profile = resolve_profile(_profile_ref_for_command(namespace.profile))
    except UserConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ProfileError:
        return _placeholder(namespace)

    if profile.mode != "air-offline":
        return _placeholder(namespace)

    query = " ".join(namespace.query)
    try:
        results = search_local_files(profile, query)
    except BrainOfflineError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    for result in results:
        print(
            f"{result.score}\t{result.document_id}\t{result.source_path}\t{result.snippet}"
        )
    return 0


def _configure_reserved_signature(
    command_parser: argparse.ArgumentParser,
    *,
    group: str,
    command: str,
) -> None:
    if group == "profile" and command == "init":
        command_parser.add_argument("--mode", choices=PROFILE_MODES, required=True)
        command_parser.add_argument("--root", required=True)
        command_parser.add_argument("--name")
        return

    if group == "profile" and command == "use":
        command_parser.add_argument("profile_name")
        return

    if group == "brain" and command == "ingest":
        command_parser.add_argument("path_or_url", nargs="?")
        return

    if group == "brain" and command == "context-server":
        command_parser.add_argument(
            "--endpoint",
            help=(
                "Context server endpoint to advertise. Defaults to the "
                "stdio placeholder contract."
            ),
        )
        return

    if group == "brain" and command in {"search", "answer"}:
        command_parser.add_argument("query", nargs="*")
        return

    if group == "agent" and command == "run":
        command_parser.add_argument("--harness", choices=AGENT_HARNESSES)
        command_parser.add_argument("--task")
        return

    if group == "agent" and command in {"attach", "status", "cancel"}:
        command_parser.add_argument("--run")
        return


def _profile_handler(command: str):
    return {
        "init": _profile_init,
        "list": _profile_list,
        "show": _profile_show,
        "doctor": _profile_doctor,
        "use": _profile_use,
    }[command]


def _brain_handler(command: str):
    if command in {"up", "down", "status"}:
        from zsper.brain.commands import handler

        return handler(command)
    if command == "context-server":
        from zsper.brain.context_server import command as context_server_command

        return context_server_command

    return {
        "ingest": _brain_ingest,
        "search": _brain_search,
    }.get(command, _placeholder)


def _code_handler(command: str):
    from zsper.code.commands import handler

    return handler(command)


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
            _configure_reserved_signature(
                command_parser,
                group=group,
                command=command,
            )
            if group == "profile":
                handler = _profile_handler(command)
            elif group == "code":
                handler = _code_handler(command)
            elif group == "brain":
                handler = _brain_handler(command)
            else:
                handler = _placeholder
            command_parser.set_defaults(func=handler)

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
