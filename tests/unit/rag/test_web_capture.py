import hashlib
from datetime import datetime
from pathlib import Path

import pytest

from zsper.profiles import Profile, initialize_profile
from zsper.rag.policy import RagPolicyError
from zsper.rag.store import ProfileRagStore
from zsper.rag.web_capture import (
    ResearchRecord,
    WebCaptureError,
    WebCaptureResult,
    capture_research_record_asset,
    capture_webpage_asset,
)


def _content_hash(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _assert_no_capture_writes(profile: Profile, store: ProfileRagStore) -> None:
    profile_root = Path(profile.root)
    asset_dir = profile_root / "brain" / "assets"
    ledger_path = profile_root / "brain" / "ledgers" / "documents.jsonl"

    assert store.list_documents(profile) == []
    assert not ledger_path.exists()
    if asset_dir.exists():
        assert list(asset_dir.iterdir()) == []


@pytest.mark.parametrize(
    "url",
    [
        "https://user:password@example.com/research",
        "https://example.com/research?token=s3cr3t",
        "https://example.com/research?api_key=s3cr3t",
        "https://example.com/research?authorization=Bearer+s3cr3t",
        "https://example.com/research?password=s3cr3t",
        "https://example.com/research?secret=s3cr3t",
        "https://example.com/research?ToKeN=s3cr3t",
        "https://example.com/research?ApiKey=s3cr3t",
        "https://example.com/callback#token=s3cr3t",
    ],
)
def test_secret_bearing_source_urls_are_rejected_before_fetch(
    tmp_path: Path,
    isolated_registry_path: Path,
    url: str,
) -> None:
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    store = ProfileRagStore.sqlite(tmp_path / "rag.sqlite")
    calls: list[str] = []

    def forbidden_fetcher(target_url: str) -> WebCaptureResult:
        calls.append(target_url)
        raise AssertionError("secret-bearing source URL must not fetch")

    with pytest.raises(WebCaptureError, match="source URL is secret-bearing"):
        capture_webpage_asset(
            profile,
            store,
            url,
            fetcher=forbidden_fetcher,
            user_triggered=True,
        )

    assert calls == []
    _assert_no_capture_writes(profile, store)


@pytest.mark.parametrize(
    "final_url",
    [
        "https://redirected:password@example.com/research",
        "https://example.com/research?AUTHORIZATION=Bearer+s3cr3t",
        "https://example.com/callback#ToKeN=s3cr3t",
    ],
)
def test_secret_bearing_final_urls_are_rejected_before_asset_writes(
    tmp_path: Path,
    isolated_registry_path: Path,
    final_url: str,
) -> None:
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    store = ProfileRagStore.sqlite(tmp_path / "rag.sqlite")
    url = "https://example.com/research/rag-006"
    calls: list[str] = []

    def redirected_fetcher(target_url: str) -> WebCaptureResult:
        calls.append(target_url)
        return WebCaptureResult(
            content=b"<html><body>redirected</body></html>",
            final_url=final_url,
            media_type="text/html",
            extraction_status="captured",
        )

    with pytest.raises(WebCaptureError, match="final URL is secret-bearing"):
        capture_webpage_asset(
            profile,
            store,
            url,
            fetcher=redirected_fetcher,
            user_triggered=True,
        )

    assert calls == [url]
    _assert_no_capture_writes(profile, store)


def test_benign_fragments_are_preserved_for_web_capture(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    store = ProfileRagStore.sqlite(tmp_path / "rag.sqlite")
    url = "https://example.com/research/rag-006#section-2"
    html = b"<html><body>section anchor</body></html>"
    calls: list[str] = []

    def fake_fetcher(target_url: str) -> WebCaptureResult:
        calls.append(target_url)
        return WebCaptureResult(
            content=html,
            final_url=target_url,
            media_type="text/html",
            extraction_status="captured",
        )

    document = capture_webpage_asset(
        profile,
        store,
        url,
        fetcher=fake_fetcher,
        user_triggered=True,
    )

    assert calls == [url]
    assert Path(document.raw_asset_path).is_file()
    assert document.metadata["original_url"] == url
    assert document.metadata["final_url"] == url
    assert store.list_documents(profile) == [document]


def test_mocked_webpage_capture_creates_unparsed_raw_asset_metadata(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    store = ProfileRagStore.sqlite(tmp_path / "rag.sqlite")
    url = "https://example.com/research/rag-006"
    html = b"<html><head><title>RAG 006 Notes</title></head><body>Local first.</body></html>"
    calls: list[str] = []

    def fake_fetcher(target_url: str) -> WebCaptureResult:
        calls.append(target_url)
        return WebCaptureResult(
            content=html,
            final_url=target_url,
            media_type="text/html; charset=utf-8",
            extraction_status="extracted",
        )

    document = capture_webpage_asset(
        profile,
        store,
        url,
        fetcher=fake_fetcher,
        user_triggered=True,
    )

    raw_asset_path = Path(document.raw_asset_path)
    parsed_path = Path(document.parsed_representation_path)
    assert calls == [url]
    assert raw_asset_path.is_file()
    assert raw_asset_path.is_relative_to(Path(profile.root) / "brain" / "assets")
    assert raw_asset_path.suffix == ".html"
    assert raw_asset_path.read_bytes() == html
    assert parsed_path.parent == Path(profile.root) / "brain" / "parsed"
    assert not parsed_path.exists()
    assert document.profile_id == profile.name
    assert document.source_type == "url"
    assert document.parser == "web-capture"
    assert document.title == "RAG 006 Notes"
    assert document.content_hash == _content_hash(html)
    assert document.metadata["source_type"] == "url"
    assert document.metadata["original_url"] == url
    assert document.metadata["final_url"] == url
    assert document.metadata["original_path"] is None
    assert document.metadata["title"] == "RAG 006 Notes"
    assert document.metadata["content_hash"] == document.content_hash
    assert document.metadata["media_type"] == "text/html"
    assert document.metadata["extraction_status"] == "extracted"
    assert document.metadata["captured_at"] == document.created_at
    assert document.metadata["version"] == 1
    datetime.fromisoformat(document.metadata["captured_at"])
    assert store.list_documents(profile) == [document]


def test_research_record_bridge_uses_selected_record_metadata(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="personal",
        root=tmp_path / "personal",
        registry_path=isolated_registry_path,
    )
    store = ProfileRagStore.sqlite(tmp_path / "rag.sqlite")
    record = ResearchRecord(
        id="research-1",
        url="https://example.com/selected",
        title="Selected Research",
    )

    document = capture_research_record_asset(
        profile,
        store,
        record,
        fetcher=lambda url: WebCaptureResult(
            content=b"<html><body>Selected record.</body></html>",
            final_url=url,
            media_type="text/html",
            extraction_status="captured",
        ),
        user_triggered=True,
    )

    assert document.title == "Selected Research"
    assert document.metadata["research_record_id"] == "research-1"
    assert document.metadata["original_url"] == record.url
    assert document.metadata["extraction_status"] == "captured"


def test_local_first_web_capture_requires_explicit_user_action_before_fetch(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
    )
    store = ProfileRagStore.sqlite(tmp_path / "rag.sqlite")
    calls: list[str] = []

    def forbidden_fetcher(url: str) -> WebCaptureResult:
        calls.append(url)
        raise AssertionError("implicit web capture must not fetch")

    with pytest.raises(RagPolicyError, match="local-first policy blocks url-ingest"):
        capture_webpage_asset(
            profile,
            store,
            "https://example.com/implicit",
            fetcher=forbidden_fetcher,
            user_triggered=False,
        )

    assert calls == []
    assert store.list_documents(profile) == []


def test_air_offline_web_capture_rejected_before_fetch(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="air-offline",
        root=tmp_path / "air",
        registry_path=isolated_registry_path,
    )
    store = ProfileRagStore.sqlite(tmp_path / "rag.sqlite")
    calls: list[str] = []

    def forbidden_fetcher(url: str) -> WebCaptureResult:
        calls.append(url)
        raise AssertionError("offline web capture must not fetch")

    with pytest.raises(RagPolicyError, match="offline policy blocks url-ingest"):
        capture_webpage_asset(
            profile,
            store,
            "https://example.com/research",
            fetcher=forbidden_fetcher,
            user_triggered=True,
        )

    assert calls == []
    assert store.list_documents(profile) == []
