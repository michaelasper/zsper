import pytest

from zsper.security.remote_policy import RemotePolicyError, check_remote_policy


@pytest.mark.parametrize(
    ("mode", "policy"),
    [
        ("work", "disabled"),
        ("personal", "tailscale-serve-only"),
        ("air-offline", "disabled"),
    ],
)
def test_allowed_remote_policies(mode: str, policy: str) -> None:
    decision = check_remote_policy(mode, policy)

    assert decision.allowed is True


@pytest.mark.parametrize(
    ("mode", "policy"),
    [
        ("work", "tailscale-serve-only"),
        ("personal", "tailscale-funnel"),
        ("air-offline", "tailscale-serve-only"),
    ],
)
def test_forbidden_remote_policies(mode: str, policy: str) -> None:
    decision = check_remote_policy(mode, policy)

    assert decision.allowed is False
    with pytest.raises(RemotePolicyError):
        decision.raise_for_status()


def test_any_funnel_policy_is_rejected() -> None:
    decision = check_remote_policy("personal", "Tailscale Funnel public")

    assert decision.allowed is False
    assert "Funnel is forbidden" in decision.reason
