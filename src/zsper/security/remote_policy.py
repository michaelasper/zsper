"""Remote access policy checks."""

from __future__ import annotations

from dataclasses import dataclass


class RemotePolicyError(RuntimeError):
    """Raised when a remote access policy is forbidden."""


@dataclass(frozen=True)
class RemoteDecision:
    allowed: bool
    reason: str

    def raise_for_status(self) -> None:
        if not self.allowed:
            raise RemotePolicyError(self.reason)


def _allow(reason: str) -> RemoteDecision:
    return RemoteDecision(allowed=True, reason=reason)


def _deny(reason: str) -> RemoteDecision:
    return RemoteDecision(allowed=False, reason=reason)


def check_remote_policy(mode: str, remote_access_policy: str) -> RemoteDecision:
    if "funnel" in remote_access_policy.lower():
        return _deny("Tailscale Funnel is forbidden for all profiles")

    if mode == "work":
        if remote_access_policy == "disabled":
            return _allow("work remote access disabled")
        return _deny("work remote access defaults to disabled")

    if mode == "personal":
        if remote_access_policy in {"disabled", "tailscale-serve-only"}:
            return _allow("personal remote access policy allowed")
        return _deny("personal remote access may use Tailscale Serve only")

    if mode == "air-offline":
        if remote_access_policy == "disabled":
            return _allow("air/offline remote access disabled")
        return _deny("air-offline remote access is disabled")

    return _deny(f"unknown profile mode: {mode}")
