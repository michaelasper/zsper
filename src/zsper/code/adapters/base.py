"""Shared adapter generation types."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GeneratedAdapter:
    name: str
    files: list[Path]
