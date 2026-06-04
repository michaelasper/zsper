"""Secret redaction helpers for logs, ledgers, and config diffs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


SECRET_KEYS = frozenset(
    {
        "apikey",
        "api_key",
        "token",
        "authorization",
        "password",
        "secret",
    }
)
REDACTED = "[REDACTED]"


def _is_secret_key(key: object) -> bool:
    return isinstance(key, str) and key.lower() in SECRET_KEYS


def redact_secrets(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: REDACTED if _is_secret_key(key) else redact_secrets(nested)
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secrets(item) for item in value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_secrets(item) for item in value]
    return value
