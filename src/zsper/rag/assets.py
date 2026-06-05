"""Raw asset capture for profile-local RAG documents."""

from __future__ import annotations

import hashlib
import mimetypes
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from zsper.profiles import Profile
from zsper.rag.models import Document
from zsper.rag.store import ProfileRagStore


_SAFE_SUFFIX_RE: Final[re.Pattern[str]] = re.compile(
    r"^\.[A-Za-z0-9][A-Za-z0-9._+-]{0,31}$"
)
_DOCLING_SUFFIXES: Final[frozenset[str]] = frozenset(
    {
        ".doc",
        ".docx",
        ".htm",
        ".html",
        ".pdf",
        ".ppt",
        ".pptx",
        ".xls",
        ".xlsx",
    }
)


class RawAssetCaptureError(ValueError):
    """Raised when a raw asset cannot be captured safely."""


def capture_local_asset(
    profile: Profile,
    store: ProfileRagStore,
    source: str | Path,
    *,
    title: str | None = None,
) -> Document:
    _reject_path_traversal(source)
    source_path = _resolve_local_file(source)
    content = source_path.read_bytes()
    content_hash = _content_hash(content)

    existing = _existing_local_document(
        profile,
        store,
        source_path=source_path,
        content_hash=content_hash,
    )
    if existing is not None:
        return existing

    document_id = _document_id(profile, source_path, content_hash)
    asset_dir = _profile_child(profile, Path("brain/assets"))
    parsed_dir = _profile_child(profile, Path("brain/parsed"))
    raw_asset_path = asset_dir / f"{document_id}{_safe_suffix(source_path)}"
    parsed_representation_path = parsed_dir / f"{document_id}.txt"
    _require_child(raw_asset_path, asset_dir, label="raw asset path")
    _require_child(
        parsed_representation_path,
        parsed_dir,
        label="parsed representation path",
    )

    _write_immutable(raw_asset_path, content, content_hash)

    captured_at = _utc_now()
    resolved_title = _resolve_title(source_path, title)
    metadata = {
        "byte_size": len(content),
        "captured_at": captured_at,
        "content_hash": content_hash,
        "media_type": mimetypes.guess_type(source_path.name)[0],
        "original_path": str(source_path),
        "original_url": None,
        "source_filename": source_path.name,
        "source_suffix": source_path.suffix,
        "source_type": "file",
        "title": resolved_title,
        "version": _next_version(profile, store, source_path),
    }
    document = Document(
        id=document_id,
        profile_id=profile.name,
        source_type="file",
        raw_asset_path=str(raw_asset_path),
        parsed_representation_path=str(parsed_representation_path),
        title=resolved_title,
        metadata=metadata,
        content_hash=content_hash,
        parser=_parser_for(source_path),
        created_at=captured_at,
        updated_at=captured_at,
    )
    store.upsert_document(profile, document)
    return document


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _reject_path_traversal(source: str | Path) -> None:
    try:
        parts = Path(source).parts
    except TypeError as exc:
        raise RawAssetCaptureError("source path must be a local filesystem path") from exc
    if ".." in parts:
        raise RawAssetCaptureError("path traversal is not allowed in source paths")


def _resolve_local_file(source: str | Path) -> Path:
    if isinstance(source, str) and "://" in source:
        raise RawAssetCaptureError("URL raw asset capture is not part of RAG-002")
    source_path = Path(source).expanduser()
    try:
        resolved = source_path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise RawAssetCaptureError(f"local source file not found: {source_path}") from exc
    if not resolved.is_file():
        raise RawAssetCaptureError(f"local source is not a file: {resolved}")
    return resolved


def _content_hash(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _document_id(profile: Profile, source_path: Path, content_hash: str) -> str:
    digest = hashlib.sha256()
    digest.update(profile.name.encode("utf-8"))
    digest.update(b"\0")
    digest.update(str(source_path).encode("utf-8"))
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
        raise RawAssetCaptureError(f"{label} must stay within {resolved_parent}")


def _safe_suffix(source_path: Path) -> str:
    suffix = source_path.suffix
    if suffix and _SAFE_SUFFIX_RE.fullmatch(suffix):
        return suffix
    return ".bin"


def _write_immutable(path: Path, content: bytes, content_hash: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(content)
        return
    except FileExistsError:
        if _content_hash(path.read_bytes()) == content_hash:
            return
        raise RawAssetCaptureError(f"raw asset already exists with different bytes: {path}")


def _resolve_title(source_path: Path, title: str | None) -> str:
    if title is not None and title.strip():
        return title.strip()
    return source_path.stem or source_path.name


def _parser_for(source_path: Path) -> str:
    if source_path.suffix.lower() in _DOCLING_SUFFIXES:
        return "docling"
    return "text"


def _existing_local_document(
    profile: Profile,
    store: ProfileRagStore,
    *,
    source_path: Path,
    content_hash: str,
) -> Document | None:
    original_path = str(source_path)
    for document in store.list_documents(profile):
        if (
            document.source_type == "file"
            and document.content_hash == content_hash
            and document.metadata.get("original_path") == original_path
        ):
            return document
    return None


def _next_version(
    profile: Profile,
    store: ProfileRagStore,
    source_path: Path,
) -> int:
    original_path = str(source_path)
    highest_version = 0
    for document in store.list_documents(profile):
        if document.metadata.get("original_path") != original_path:
            continue
        version = document.metadata.get("version")
        if isinstance(version, int) and not isinstance(version, bool):
            highest_version = max(highest_version, version)
    return highest_version + 1
