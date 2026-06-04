"""Handlers for `zsper code` commands."""

from __future__ import annotations

import sys
from argparse import Namespace
from collections.abc import Callable

from zsper.code.adapters.opencode import generate_opencode_adapter
from zsper.code.adapters.pi import generate_pi_adapter
from zsper.code.adapters.zed import generate_zed_adapter
from zsper.code.llm_server_contract import LLMServerContract
from zsper.config.model_endpoint import endpoints_for_profile
from zsper.profiles import ProfileError, resolve_profile


def _resolve(namespace: Namespace):
    try:
        return resolve_profile(namespace.profile)
    except ProfileError as exc:
        print(str(exc), file=sys.stderr)
        return None


def _contract_for_profile(profile) -> LLMServerContract:
    return LLMServerContract(endpoint=endpoints_for_profile(profile)[0])


def _run_process_command(namespace: Namespace, method_name: str) -> int:
    profile = _resolve(namespace)
    if profile is None:
        return 1
    contract = _contract_for_profile(profile)
    completed = getattr(contract, method_name)()
    if completed.stdout:
        print(completed.stdout.strip())
    if completed.stderr:
        print(completed.stderr.strip(), file=sys.stderr)
    return completed.returncode


def start(namespace: Namespace) -> int:
    return _run_process_command(namespace, "start")


def stop(namespace: Namespace) -> int:
    return _run_process_command(namespace, "stop")


def status(namespace: Namespace) -> int:
    profile = _resolve(namespace)
    if profile is None:
        return 1
    result = _contract_for_profile(profile).status()
    if result.available:
        print(f"model server available for {profile.name}: {', '.join(result.models)}")
        return 0
    print(f"model server unavailable for {profile.name}: {result.error}", file=sys.stderr)
    return 1


def smoke(namespace: Namespace) -> int:
    profile = _resolve(namespace)
    if profile is None:
        return 1
    result = _contract_for_profile(profile).smoke()
    if result.ok:
        print(f"smoke OK for {profile.name}: {result.content}")
        return 0
    print(f"smoke failed for {profile.name}: {result.error}", file=sys.stderr)
    return 1


def _install_adapter(
    namespace: Namespace,
    *,
    name: str,
    generator: Callable,
) -> int:
    profile = _resolve(namespace)
    if profile is None:
        return 1
    generated = generator(profile)
    print(f"installed {name} adapter for {profile.name}")
    for path in generated.files:
        print(path)
    return 0


def install_zed(namespace: Namespace) -> int:
    return _install_adapter(namespace, name="zed", generator=generate_zed_adapter)


def install_opencode(namespace: Namespace) -> int:
    return _install_adapter(
        namespace,
        name="opencode",
        generator=generate_opencode_adapter,
    )


def install_pi(namespace: Namespace) -> int:
    return _install_adapter(namespace, name="pi", generator=generate_pi_adapter)


def handler(command: str):
    return {
        "start": start,
        "stop": stop,
        "status": status,
        "smoke": smoke,
        "install-zed": install_zed,
        "install-opencode": install_opencode,
        "install-pi": install_pi,
    }[command]
