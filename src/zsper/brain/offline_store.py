"""Profile-local file ingest and exact search for air/offline mode."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from zsper.profiles import Profile
from zsper.security.network_policy import check_network_policy, looks_like_url


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


class BrainOfflineError(RuntimeError):
    """Raised when an air/offline Brain operation cannot proceed."""


@dataclass(frozen=True)
class OfflineDocument:
    document_id: str
    profile: str
    source_path: str
    asset_path: str
    parsed_path: str
    metadata_path: str
    byte_size: int
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "profile": self.profile,
            "source_path": self.source_path,
            "asset_path": self.asset_path,
            "parsed_path": self.parsed_path,
            "metadata_path": self.metadata_path,
            "byte_size": self.byte_size,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class SearchResult:
    document_id: str
    source_path: str
    score: int
    snippet: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "source_path": self.source_path,
            "score": self.score,
            "snippet": self.snippet,
        }


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _tokenize(text: str) -> list[str]:
    return [match.group(0).lower() for match in TOKEN_RE.finditer(text)]


def _root(profile: Profile) -> Path:
    return Path(profile.root)


def _document_id(source: Path, content: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(str(source.resolve(strict=False)).encode("utf-8"))
    digest.update(b"\0")
    digest.update(content)
    return digest.hexdigest()[:20]


def _ledger_path(profile: Profile) -> Path:
    return _root(profile) / "brain" / "ledgers" / "documents.jsonl"


def _metadata_dir(profile: Profile) -> Path:
    return _root(profile) / "brain" / "documents"


def _parsed_dir(profile: Profile) -> Path:
    return _root(profile) / "brain" / "parsed"


def _asset_dir(profile: Profile) -> Path:
    return _root(profile) / "brain" / "assets"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _ensure_air_offline(profile: Profile) -> None:
    if profile.mode != "air-offline" or profile.network_policy != "offline":
        raise BrainOfflineError("air/offline file store requires an air-offline profile")


def ingest_local_file(profile: Profile, source: str | Path) -> OfflineDocument:
    _ensure_air_offline(profile)
    source_text = str(source)
    action = "url-ingest" if looks_like_url(source_text) else "local-file-read"
    decision = check_network_policy(
        profile.network_policy,
        source_text,
        action=action,
        user_triggered=True,
    )
    if not decision.allowed:
        raise BrainOfflineError(decision.reason)

    source_path = Path(source).expanduser().resolve(strict=False)
    if not source_path.is_file():
        raise BrainOfflineError(f"local file not found: {source_path}")

    content = source_path.read_bytes()
    try:
        parsed_text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BrainOfflineError("air/offline MVP accepts UTF-8 text files only") from exc

    document_id = _document_id(source_path, content)
    created_at = _utc_now()
    suffix = source_path.suffix or ".txt"
    asset_path = _asset_dir(profile) / f"{document_id}{suffix}"
    parsed_path = _parsed_dir(profile) / f"{document_id}.txt"
    metadata_path = _metadata_dir(profile) / f"{document_id}.json"

    asset_path.parent.mkdir(parents=True, exist_ok=True)
    parsed_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, asset_path)
    parsed_path.write_text(parsed_text, encoding="utf-8")

    document = OfflineDocument(
        document_id=document_id,
        profile=profile.name,
        source_path=str(source_path),
        asset_path=str(asset_path),
        parsed_path=str(parsed_path),
        metadata_path=str(metadata_path),
        byte_size=len(content),
        created_at=created_at,
    )
    metadata = {
        **document.to_dict(),
        "mode": profile.mode,
        "network_policy": profile.network_policy,
        "parser": "utf-8-text-mvp",
    }
    _write_json(metadata_path, metadata)
    _append_jsonl(
        _ledger_path(profile),
        {
            "event": "document.ingested",
            "document_id": document_id,
            "profile": profile.name,
            "source_path": str(source_path),
            "created_at": created_at,
        },
    )
    return document


def _load_document_metadata(profile: Profile) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for metadata_path in sorted(_metadata_dir(profile).glob("*.json")):
        documents.append(json.loads(metadata_path.read_text(encoding="utf-8")))
    return documents


def _snippet(text: str, query_tokens: set[str]) -> str:
    for line in text.splitlines():
        if query_tokens & set(_tokenize(line)):
            return line.strip()
    return text[:160].strip()


def search_local_files(profile: Profile, query: str, *, limit: int = 10) -> list[SearchResult]:
    _ensure_air_offline(profile)
    query_tokens = set(_tokenize(query))
    if not query_tokens:
        return []

    results: list[SearchResult] = []
    for metadata in _load_document_metadata(profile):
        parsed_path = Path(metadata["parsed_path"])
        text = parsed_path.read_text(encoding="utf-8")
        text_tokens = _tokenize(text)
        score = sum(1 for token in text_tokens if token in query_tokens)
        if score == 0:
            continue
        results.append(
            SearchResult(
                document_id=metadata["document_id"],
                source_path=metadata["source_path"],
                score=score,
                snippet=_snippet(text, query_tokens),
            )
        )

    results.sort(key=lambda result: (-result.score, result.source_path))
    return results[:limit]
