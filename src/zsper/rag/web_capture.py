"""Policy-gated local web capture for RAG raw assets."""

from __future__ import annotations

import hashlib
import mimetypes
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Final
from urllib.parse import parse_qsl, unquote, urlparse
from urllib.request import Request, urlopen

from zsper.profiles import Profile
from zsper.rag.models import Document
from zsper.rag.policy import RagPolicyGate
from zsper.rag.store import ProfileRagStore
from zsper.security.network_policy import looks_like_url


_SAFE_SUFFIX_RE: Final[re.Pattern[str]] = re.compile(
    r"^\.[A-Za-z0-9][A-Za-z0-9._+-]{0,31}$"
)
_DEFAULT_WEB_SUFFIX: Final[str] = ".html"
_SECRET_QUERY_KEYS: Final[frozenset[str]] = frozenset(
    {
        "apikey",
        "api_key",
        "authorization",
        "password",
        "secret",
        "token",
    }
)


class WebCaptureError(ValueError):
    """Raised when a webpage cannot be captured into a raw asset."""


@dataclass(frozen=True)
class WebCaptureResult:
    """Fetched webpage bytes returned by an injectable fetcher."""

    content: bytes | str
    final_url: str | None = None
    media_type: str | None = None
    title: str | None = None
    extraction_status: str = "captured"


WebCaptureFetcher = Callable[[str], WebCaptureResult]


@dataclass(frozen=True)
class ResearchRecord:
    """Selected research record that can be bridged into explicit ingestion."""

    id: str
    url: str
    title: str | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise WebCaptureError("research record id must be non-empty")
        if not looks_like_url(self.url):
            raise WebCaptureError("research record url must be an http(s) URL")
        if self.title is not None and not self.title.strip():
            raise WebCaptureError("research record title must be non-empty when set")


def capture_research_record_asset(
    profile: Profile,
    store: ProfileRagStore,
    record: ResearchRecord,
    *,
    fetcher: WebCaptureFetcher | None = None,
    user_triggered: bool = False,
    gate: RagPolicyGate | None = None,
) -> Document:
    """Capture a selected research record as a URL raw asset."""

    return capture_webpage_asset(
        profile,
        store,
        record.url,
        fetcher=fetcher,
        user_triggered=user_triggered,
        title=record.title,
        research_record_id=record.id,
        gate=gate,
    )


def capture_webpage_asset(
    profile: Profile,
    store: ProfileRagStore,
    url: str,
    *,
    fetcher: WebCaptureFetcher | None = None,
    user_triggered: bool = False,
    title: str | None = None,
    research_record_id: str | None = None,
    gate: RagPolicyGate | None = None,
) -> Document:
    """Capture a webpage into profile-local raw assets after policy approval."""

    if not looks_like_url(url):
        raise WebCaptureError("web capture requires an http(s) URL")
    _reject_secret_bearing_url(url, label="source URL")
    if title is not None and not title.strip():
        raise WebCaptureError("web capture title must be non-empty when set")
    if research_record_id is not None and not research_record_id.strip():
        raise WebCaptureError("research_record_id must be non-empty when set")

    policy_gate = gate or RagPolicyGate(profile)
    policy_gate.require_ingest(url, user_triggered=user_triggered)

    response = (fetcher or _default_fetcher)(url)
    final_url = response.final_url or url
    _reject_secret_bearing_url(final_url, label="final URL")
    content = _content_bytes(response.content)
    content_hash = _content_hash(content)
    media_type = _normalize_media_type(response.media_type)
    extraction_status = _non_empty(
        response.extraction_status,
        field_name="extraction_status",
    )
    resolved_title = _resolve_title(
        explicit_title=title,
        response_title=response.title,
        content=content,
        media_type=media_type,
        url=url,
    )

    existing = _existing_url_document(
        profile,
        store,
        original_url=url,
        content_hash=content_hash,
    )
    if existing is not None:
        return existing

    document_id = _document_id(profile, url, content_hash)
    suffix = _safe_suffix(url, media_type)
    asset_dir = _profile_child(profile, Path("brain/assets"))
    parsed_dir = _profile_child(profile, Path("brain/parsed"))
    raw_asset_path = asset_dir / f"{document_id}{suffix}"
    parsed_representation_path = parsed_dir / f"{document_id}.txt"
    _require_child(raw_asset_path, asset_dir, label="raw asset path")
    _require_child(
        parsed_representation_path,
        parsed_dir,
        label="parsed representation path",
    )

    _write_immutable(raw_asset_path, content, content_hash)

    captured_at = _utc_now()
    metadata = {
        "byte_size": len(content),
        "captured_at": captured_at,
        "content_hash": content_hash,
        "extraction_status": extraction_status,
        "final_url": final_url,
        "media_type": media_type,
        "original_path": None,
        "original_url": url,
        "source_filename": _source_filename(url),
        "source_suffix": suffix,
        "source_type": "url",
        "title": resolved_title,
        "version": _next_version(profile, store, url),
    }
    if research_record_id is not None:
        metadata["research_record_id"] = research_record_id.strip()

    document = Document(
        id=document_id,
        profile_id=profile.name,
        source_type="url",
        raw_asset_path=str(raw_asset_path),
        parsed_representation_path=str(parsed_representation_path),
        title=resolved_title,
        metadata=metadata,
        content_hash=content_hash,
        parser="web-capture",
        created_at=captured_at,
        updated_at=captured_at,
    )
    store.upsert_document(profile, document)
    return document


def _default_fetcher(url: str) -> WebCaptureResult:
    request = Request(
        url,
        headers={"User-Agent": "zsper-local-web-capture/1"},
    )
    with urlopen(request, timeout=30) as response:
        return WebCaptureResult(
            content=response.read(),
            final_url=response.geturl(),
            media_type=response.headers.get("Content-Type"),
            extraction_status="captured",
        )


def _reject_secret_bearing_url(url: str, *, label: str) -> None:
    parsed = urlparse(url)
    if parsed.username is not None or parsed.password is not None:
        raise WebCaptureError(f"{label} is secret-bearing and cannot be captured")
    if _has_secret_key(parsed.query) or _has_secret_key(parsed.fragment):
        raise WebCaptureError(f"{label} is secret-bearing and cannot be captured")


def _has_secret_key(query_like: str) -> bool:
    pairs = parse_qsl(query_like, keep_blank_values=True)
    return any(key.lower() in _SECRET_QUERY_KEYS for key, _value in pairs)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _content_bytes(content: bytes | str) -> bytes:
    if isinstance(content, bytes):
        return content
    if isinstance(content, str):
        return content.encode("utf-8")
    raise WebCaptureError("web capture content must be bytes or text")


def _content_hash(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _document_id(profile: Profile, url: str, content_hash: str) -> str:
    digest = hashlib.sha256()
    digest.update(profile.name.encode("utf-8"))
    digest.update(b"\0")
    digest.update(url.encode("utf-8"))
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
        raise WebCaptureError(f"{label} must stay within {resolved_parent}")


def _normalize_media_type(media_type: str | None) -> str | None:
    if media_type is None:
        return None
    return media_type.split(";", 1)[0].strip().lower() or None


def _safe_suffix(url: str, media_type: str | None) -> str:
    media_suffix = mimetypes.guess_extension(media_type or "")
    if media_suffix and _SAFE_SUFFIX_RE.fullmatch(media_suffix):
        return media_suffix

    path_suffix = Path(unquote(urlparse(url).path)).suffix
    if path_suffix and _SAFE_SUFFIX_RE.fullmatch(path_suffix):
        return path_suffix
    return _DEFAULT_WEB_SUFFIX


def _write_immutable(path: Path, content: bytes, content_hash: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(content)
        return
    except FileExistsError:
        if _content_hash(path.read_bytes()) == content_hash:
            return
        raise WebCaptureError(f"raw asset already exists with different bytes: {path}")


def _resolve_title(
    *,
    explicit_title: str | None,
    response_title: str | None,
    content: bytes,
    media_type: str | None,
    url: str,
) -> str:
    for candidate in (explicit_title, response_title):
        resolved = _strip_optional(candidate)
        if resolved is not None:
            return resolved

    if media_type in {None, "text/html"}:
        parsed_title = _extract_html_title(content)
        if parsed_title is not None:
            return parsed_title

    parsed = urlparse(url)
    name = Path(unquote(parsed.path)).name
    return name or parsed.netloc or url


def _strip_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _non_empty(value: str, *, field_name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise WebCaptureError(f"{field_name} must be non-empty")
    return stripped


class _TitleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._in_title = False
        self.parts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        if tag.lower() == "title":
            self._in_title = True

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False


def _extract_html_title(content: bytes) -> str | None:
    parser = _TitleParser()
    parser.feed(content.decode("utf-8", errors="replace"))
    title = " ".join(" ".join(parser.parts).split())
    return title or None


def _source_filename(url: str) -> str | None:
    filename = Path(unquote(urlparse(url).path)).name
    return filename or None


def _existing_url_document(
    profile: Profile,
    store: ProfileRagStore,
    *,
    original_url: str,
    content_hash: str,
) -> Document | None:
    for document in store.list_documents(profile):
        if (
            document.source_type == "url"
            and document.content_hash == content_hash
            and document.metadata.get("original_url") == original_url
        ):
            return document
    return None


def _next_version(
    profile: Profile,
    store: ProfileRagStore,
    original_url: str,
) -> int:
    highest_version = 0
    for document in store.list_documents(profile):
        if document.metadata.get("original_url") != original_url:
            continue
        version = document.metadata.get("version")
        if isinstance(version, int) and not isinstance(version, bool):
            highest_version = max(highest_version, version)
    return highest_version + 1
