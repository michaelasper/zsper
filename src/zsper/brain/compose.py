"""Profile-specific Brain Docker Compose rendering."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from zsper.brain.db.schema import SCHEMA_SQL
from zsper.profiles import Profile


DEFAULT_MODEL_BASE_URL = "http://host.docker.internal:9127/v1"
DEFAULT_HONCHO_IMAGE = "ghcr.io/plastic-labs/honcho:latest"
POSTGRES_USER = "zsper"
POSTGRES_PASSWORD = "zsper-local-only"
TEMPLATE_ROOT = Path(__file__).resolve().parents[3] / "compose"


@dataclass(frozen=True)
class BrainPorts:
    api: int
    web: int
    postgres: int
    redis: int
    searxng: int
    honcho: int


@dataclass(frozen=True)
class RenderedBrainProfile:
    compose_path: Path
    env_path: Path
    schema_path: Path
    ports: BrainPorts


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "profile"


def profile_slug(profile: Profile) -> str:
    return _slug(profile.database_name)


def brain_ports_for_profile(profile: Profile) -> BrainPorts:
    default_bases = {
        ("work", "work"): 7420,
        ("personal", "personal"): 7520,
        ("air-offline", "air"): 7620,
    }
    base = default_bases.get((profile.mode, profile.name))
    if base is None:
        digest = hashlib.sha256(profile_slug(profile).encode("utf-8")).hexdigest()
        base = 7700 + ((int(digest[:6], 16) % 80) * 10)
    return BrainPorts(
        api=base,
        web=base + 1,
        postgres=base + 2,
        redis=base + 3,
        searxng=base + 4,
        honcho=base + 5,
    )


def local_postgres_dsn_for_profile(profile: Profile) -> str:
    """Return the host-side DSN for the profile's local Postgres service."""

    ports = brain_ports_for_profile(profile)
    return (
        f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@"
        f"127.0.0.1:{ports.postgres}/{profile.database_name}"
    )


def _render_template(template_name: str, values: Mapping[str, str]) -> str:
    template = (TEMPLATE_ROOT / template_name).read_text(encoding="utf-8")

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise KeyError(f"missing template value: {key}")
        return values[key]

    rendered = re.sub(r"{{\s*([A-Z0-9_]+)\s*}}", replace, template)
    if "{{" in rendered or "}}" in rendered:
        raise ValueError(f"unrendered placeholder in {template_name}")
    return rendered


def _ensure_brain_dirs(profile: Profile) -> None:
    root = Path(profile.root)
    for relative in (
        Path("brain"),
        Path("brain/ledgers"),
        Path("runtime/brain/postgres"),
        Path("runtime/brain/redis"),
        Path("runtime/brain/searxng"),
        Path("runtime/brain/honcho"),
        Path("agent-runs/events"),
        Path("logs"),
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)


def _template_values(
    profile: Profile,
    *,
    repo_root: Path,
    model_base_url: str,
    honcho_image: str,
) -> dict[str, str]:
    root = Path(profile.root).resolve(strict=False)
    brain_root = root / "brain"
    runtime_brain_root = root / "runtime" / "brain"
    ports = brain_ports_for_profile(profile)
    slug = profile_slug(profile)
    return {
        "PROFILE_ID": profile.name,
        "PROFILE_NAME": profile.name,
        "PROFILE_MODE": profile.mode,
        "PROFILE_SLUG": slug,
        "PROFILE_ROOT": str(root),
        "BRAIN_ROOT": str(brain_root),
        "RUNTIME_BRAIN_ROOT": str(runtime_brain_root),
        "REPO_ROOT": str(repo_root.resolve(strict=False)),
        "MODEL_BASE_URL": model_base_url,
        "POSTGRES_DB": profile.database_name,
        "POSTGRES_USER": POSTGRES_USER,
        "POSTGRES_PASSWORD": POSTGRES_PASSWORD,
        "POSTGRES_PORT": str(ports.postgres),
        "REDIS_PORT": str(ports.redis),
        "SEARXNG_PORT": str(ports.searxng),
        "HONCHO_PORT": str(ports.honcho),
        "HONCHO_IMAGE": honcho_image,
        "BRAIN_API_PORT": str(ports.api),
        "BRAIN_WEB_PORT": str(ports.web),
    }


def render_brain_profile(
    profile: Profile,
    *,
    repo_root: Path | str | None = None,
    model_base_url: str = DEFAULT_MODEL_BASE_URL,
    honcho_image: str = DEFAULT_HONCHO_IMAGE,
) -> RenderedBrainProfile:
    """Render Brain Compose, env, and schema files into a profile root."""

    _ensure_brain_dirs(profile)
    root = Path(profile.root)
    brain_root = root / "brain"
    resolved_repo_root = (
        Path(repo_root).expanduser() if repo_root is not None else Path(__file__).resolve().parents[3]
    )
    values = _template_values(
        profile,
        repo_root=resolved_repo_root,
        model_base_url=model_base_url,
        honcho_image=honcho_image,
    )

    compose_path = brain_root / "docker-compose.yml"
    env_path = brain_root / ".env"
    schema_path = brain_root / "schema.sql"
    compose_path.write_text(
        _render_template("brain.compose.yml.j2", values),
        encoding="utf-8",
    )
    env_path.write_text(_render_template("brain.env.j2", values), encoding="utf-8")
    schema_path.write_text(SCHEMA_SQL, encoding="utf-8")
    return RenderedBrainProfile(
        compose_path=compose_path,
        env_path=env_path,
        schema_path=schema_path,
        ports=brain_ports_for_profile(profile),
    )
