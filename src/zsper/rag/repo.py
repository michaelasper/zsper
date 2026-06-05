"""Repo directory capture and parsing for local RAG ingestion."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from zsper.profiles import Profile
from zsper.rag.models import Document
from zsper.rag.parsers.selector import TEXT_EXTENSIONS, TEXT_FILENAMES
from zsper.rag.store import ProfileRagStore


REPO_MANIFEST_SCHEMA: Final[str] = "zsper.rag.repo_manifest.v1"
REPO_PARSED_SCHEMA: Final[str] = "zsper.rag.repo_parsed.v1"
MAX_REPO_TEXT_FILE_BYTES: Final[int] = 512 * 1024
_SAFE_SUFFIX_RE: Final[re.Pattern[str]] = re.compile(
    r"^\.[A-Za-z0-9][A-Za-z0-9._+-]{0,31}$"
)
_IGNORED_DIRS: Final[frozenset[str]] = frozenset(
    {
        ".git",
        ".hg",
        ".mypy_cache",
        ".next",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "target",
        "venv",
    }
)
_SENSITIVE_FILENAMES: Final[frozenset[str]] = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        ".netrc",
        "id_dsa",
        "id_ed25519",
        "id_ecdsa",
        "id_rsa",
    }
)
_SENSITIVE_SUFFIXES: Final[frozenset[str]] = frozenset(
    {".crt", ".der", ".key", ".p12", ".pem", ".pfx"}
)
_REPO_TEXT_FILENAMES: Final[frozenset[str]] = TEXT_FILENAMES | frozenset(
    {
        "changelog",
        "codeowners",
        "contributing",
        "copying",
        "license",
        "notice",
        "readme",
    }
)


class RepoCaptureError(ValueError):
    """Raised when a repo directory cannot be captured or parsed."""


@dataclass(frozen=True)
class RepoTextFile:
    relative_path: str
    source_path: str
    text: str
    byte_size: int
    content_hash: str
    media_type: str | None

    def metadata(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "source_path": self.source_path,
            "byte_size": self.byte_size,
            "content_hash": self.content_hash,
            "media_type": self.media_type,
        }

    def manifest_record(self) -> dict[str, object]:
        record = self.metadata()
        record["text"] = self.text
        return record


@dataclass(frozen=True)
class ParsedRepoDocument:
    document_id: str
    parser: str
    repo_root: str
    file_count: int
    text: str
    parsed_representation_path: str


def capture_repo_asset(
    profile: Profile,
    store: ProfileRagStore,
    source: str | Path,
    *,
    title: str | None = None,
) -> Document:
    """Capture supported text-like files from a local repo directory."""

    _reject_path_traversal(source)
    repo_root = _resolve_repo_dir(source)
    files = _collect_repo_text_files(repo_root)
    if not files:
        raise RepoCaptureError(f"repo source contains no supported text files: {repo_root}")

    content_hash = _repo_content_hash(files)
    existing = _existing_repo_document(
        profile,
        store,
        repo_root=repo_root,
        content_hash=content_hash,
    )
    if existing is not None:
        return existing

    document_id = _document_id(profile, repo_root, content_hash)
    asset_dir = _profile_child(profile, Path("brain/assets"))
    parsed_dir = _profile_child(profile, Path("brain/parsed"))
    raw_asset_path = asset_dir / f"{document_id}.repo.json"
    parsed_representation_path = parsed_dir / f"{document_id}.repo.json"
    _require_child(raw_asset_path, asset_dir, label="raw repo asset path")
    _require_child(
        parsed_representation_path,
        parsed_dir,
        label="parsed repo representation path",
    )

    manifest = {
        "schema": REPO_MANIFEST_SCHEMA,
        "document_id": document_id,
        "repo_root": str(repo_root),
        "content_hash": content_hash,
        "files": [file.manifest_record() for file in files],
    }
    _write_immutable_json(raw_asset_path, manifest)

    captured_at = _utc_now()
    resolved_title = _resolve_title(repo_root, title)
    metadata = {
        "captured_at": captured_at,
        "content_hash": content_hash,
        "file_count": len(files),
        "files": [file.metadata() for file in files],
        "media_type": "application/vnd.zsper.repo+json",
        "original_path": str(repo_root),
        "original_url": None,
        "source_filename": repo_root.name,
        "source_suffix": _safe_suffix(repo_root),
        "source_type": "repo",
        "title": resolved_title,
        "version": _next_version(profile, store, repo_root),
    }
    document = Document(
        id=document_id,
        profile_id=profile.name,
        source_type="repo",
        raw_asset_path=str(raw_asset_path),
        parsed_representation_path=str(parsed_representation_path),
        title=resolved_title,
        metadata=metadata,
        content_hash=content_hash,
        parser="repo",
        created_at=captured_at,
        updated_at=captured_at,
    )
    store.upsert_document(profile, document)
    return document


def parse_repo_document(document: Document) -> ParsedRepoDocument:
    """Write a parsed repo representation from a captured repo manifest."""

    if document.parser != "repo":
        raise RepoCaptureError(
            "repo parser only accepts repo routes; "
            f"document {document.id} is routed to {document.parser}"
        )

    manifest = _read_manifest(document)
    files = _manifest_files(manifest)
    repo_root = _manifest_str(manifest, "repo_root")
    segments: list[dict[str, object]] = []
    parts: list[str] = []
    for file in files:
        segment_text = (
            f"## {file.relative_path}\n\n"
            f"{file.text.rstrip()}\n"
        )
        parts.append(segment_text)
        segments.append(
            {
                "text": segment_text,
                "heading": file.relative_path,
                "section": file.relative_path,
                "metadata": {
                    "relative_path": file.relative_path,
                    "source_path_or_url": file.source_path,
                    "original_path": file.source_path,
                    "byte_size": file.byte_size,
                    "content_hash": file.content_hash,
                    "media_type": file.media_type,
                },
            }
        )

    text = "\n".join(parts)
    if not text.strip():
        raise RepoCaptureError(f"repo parser produced no text for document {document.id}")

    parsed_payload = {
        "schema": REPO_PARSED_SCHEMA,
        "document_id": document.id,
        "repo_root": repo_root,
        "text": text,
        "segments": segments,
    }
    parsed_path = Path(document.parsed_representation_path)
    parsed_path.parent.mkdir(parents=True, exist_ok=True)
    parsed_path.write_text(
        json.dumps(parsed_payload, ensure_ascii=True, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return ParsedRepoDocument(
        document_id=document.id,
        parser="repo",
        repo_root=repo_root,
        file_count=len(files),
        text=text,
        parsed_representation_path=str(parsed_path),
    )


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _reject_path_traversal(source: str | Path) -> None:
    try:
        parts = Path(source).parts
    except TypeError as exc:
        raise RepoCaptureError("repo source must be a local filesystem path") from exc
    if ".." in parts:
        raise RepoCaptureError("path traversal is not allowed in repo source paths")


def _resolve_repo_dir(source: str | Path) -> Path:
    if isinstance(source, str) and "://" in source:
        raise RepoCaptureError("repo capture requires a local directory")
    source_path = Path(source).expanduser()
    try:
        resolved = source_path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise RepoCaptureError(f"repo source not found: {source_path}") from exc
    if not resolved.is_dir():
        raise RepoCaptureError(f"repo source is not a directory: {resolved}")
    return resolved


def _collect_repo_text_files(repo_root: Path) -> tuple[RepoTextFile, ...]:
    files: list[RepoTextFile] = []
    for current_root, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = sorted(
            dirname for dirname in dirnames if dirname not in _IGNORED_DIRS
        )
        for filename in sorted(filenames):
            path = Path(current_root) / filename
            if not _should_capture_file(path):
                continue
            record = _read_repo_text_file(repo_root, path)
            if record is not None:
                files.append(record)
    files.sort(key=lambda file: file.relative_path)
    return tuple(files)


def _should_capture_file(path: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    name = path.name.lower()
    suffix = path.suffix.lower()
    if name in _SENSITIVE_FILENAMES or suffix in _SENSITIVE_SUFFIXES:
        return False
    return suffix in TEXT_EXTENSIONS or name in _REPO_TEXT_FILENAMES


def _read_repo_text_file(repo_root: Path, path: Path) -> RepoTextFile | None:
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size > MAX_REPO_TEXT_FILE_BYTES:
        return None
    try:
        content = path.read_bytes()
        text = content.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    relative_path = path.relative_to(repo_root).as_posix()
    return RepoTextFile(
        relative_path=relative_path,
        source_path=str(path.resolve(strict=False)),
        text=text,
        byte_size=len(content),
        content_hash=_content_hash(content),
        media_type=mimetypes.guess_type(path.name)[0],
    )


def _repo_content_hash(files: tuple[RepoTextFile, ...]) -> str:
    digest = hashlib.sha256()
    for file in files:
        digest.update(file.relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file.content_hash.encode("utf-8"))
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def _content_hash(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _document_id(profile: Profile, repo_root: Path, content_hash: str) -> str:
    digest = hashlib.sha256()
    digest.update(profile.name.encode("utf-8"))
    digest.update(b"\0")
    digest.update(str(repo_root).encode("utf-8"))
    digest.update(b"\0")
    digest.update(content_hash.encode("utf-8"))
    return f"doc-{digest.hexdigest()[:20]}"


def _profile_child(profile: Profile, relative_path: Path) -> Path:
    profile_root = Path(profile.root).expanduser().resolve(strict=False)
    path = (profile_root / relative_path).resolve(strict=False)
    _require_child(path, profile_root, label="profile path")
    return path


def _require_child(path: Path, parent: Path, *, label: str) -> None:
    resolved_path = path.resolve(strict=False)
    resolved_parent = parent.resolve(strict=False)
    if not resolved_path.is_relative_to(resolved_parent):
        raise RepoCaptureError(f"{label} must stay within {resolved_parent}")


def _safe_suffix(source_path: Path) -> str:
    suffix = source_path.suffix
    if suffix and _SAFE_SUFFIX_RE.fullmatch(suffix):
        return suffix
    return ""


def _write_immutable_json(path: Path, payload: dict[str, object]) -> None:
    content = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        indent=2,
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(content)
        return
    except FileExistsError:
        if path.read_bytes() == content:
            return
        raise RepoCaptureError(f"repo asset already exists with different bytes: {path}")


def _resolve_title(repo_root: Path, title: str | None) -> str:
    if title is not None and title.strip():
        return title.strip()
    return repo_root.name or str(repo_root)


def _existing_repo_document(
    profile: Profile,
    store: ProfileRagStore,
    *,
    repo_root: Path,
    content_hash: str,
) -> Document | None:
    original_path = str(repo_root)
    for document in store.list_documents(profile):
        if (
            document.source_type == "repo"
            and document.parser == "repo"
            and document.content_hash == content_hash
            and document.metadata.get("original_path") == original_path
        ):
            return document
    return None


def _next_version(
    profile: Profile,
    store: ProfileRagStore,
    repo_root: Path,
) -> int:
    original_path = str(repo_root)
    highest_version = 0
    for document in store.list_documents(profile):
        if document.metadata.get("original_path") != original_path:
            continue
        version = document.metadata.get("version")
        if isinstance(version, int) and not isinstance(version, bool):
            highest_version = max(highest_version, version)
    return highest_version + 1


def _read_manifest(document: Document) -> dict[str, Any]:
    raw_path = Path(document.raw_asset_path)
    try:
        data = json.loads(raw_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RepoCaptureError(
            f"repo parser could not read raw asset for document {document.id}: "
            f"{raw_path}"
        ) from exc
    if not isinstance(data, dict):
        raise RepoCaptureError("repo manifest must be a JSON object")
    if data.get("schema") != REPO_MANIFEST_SCHEMA:
        raise RepoCaptureError(
            f"repo manifest schema must be {REPO_MANIFEST_SCHEMA}"
        )
    parsed_document_id = data.get("document_id")
    if parsed_document_id is not None and parsed_document_id != document.id:
        raise RepoCaptureError("repo manifest document_id must match the document")
    return data


def _manifest_files(manifest: dict[str, Any]) -> tuple[RepoTextFile, ...]:
    raw_files = manifest.get("files")
    if not isinstance(raw_files, list):
        raise RepoCaptureError("repo manifest files must be a list")
    files: list[RepoTextFile] = []
    for raw_file in raw_files:
        if not isinstance(raw_file, dict):
            raise RepoCaptureError("repo manifest file entries must be JSON objects")
        text = raw_file.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        files.append(
            RepoTextFile(
                relative_path=_file_str(raw_file, "relative_path"),
                source_path=_file_str(raw_file, "source_path"),
                text=text,
                byte_size=_file_int(raw_file, "byte_size"),
                content_hash=_file_str(raw_file, "content_hash"),
                media_type=_file_optional_str(raw_file, "media_type"),
            )
        )
    if not files:
        raise RepoCaptureError("repo manifest contains no parseable text files")
    return tuple(files)


def _manifest_str(manifest: dict[str, Any], key: str) -> str:
    value = manifest.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RepoCaptureError(f"repo manifest {key} must be a non-empty string")
    return value


def _file_str(raw_file: dict[str, Any], key: str) -> str:
    value = raw_file.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RepoCaptureError(f"repo manifest file {key} must be a non-empty string")
    return value


def _file_optional_str(raw_file: dict[str, Any], key: str) -> str | None:
    value = raw_file.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise RepoCaptureError(f"repo manifest file {key} must be null or a string")
    return value


def _file_int(raw_file: dict[str, Any], key: str) -> int:
    value = raw_file.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise RepoCaptureError(
            f"repo manifest file {key} must be a non-negative integer"
        )
    return value


__all__ = [
    "REPO_MANIFEST_SCHEMA",
    "REPO_PARSED_SCHEMA",
    "ParsedRepoDocument",
    "RepoCaptureError",
    "capture_repo_asset",
    "parse_repo_document",
]
