import json
from pathlib import Path

import pytest

from zsper.brain.offline_store import (
    BrainOfflineError,
    ingest_local_file,
    search_local_files,
)
from zsper.profiles import initialize_profile


def test_air_file_ingest_writes_profile_local_artifacts_and_ledger(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="air",
        root=tmp_path / "air",
        registry_path=isolated_registry_path,
        network_policy="offline",
    )
    source = tmp_path / "flight-notes.md"
    source.write_text(
        "# Flight notes\n\nGemma 4 12B offline setup and local retrieval notes.\n",
        encoding="utf-8",
    )

    document = ingest_local_file(profile, source)

    root = Path(profile.root)
    assert document.profile == "air"
    assert document.source_path == str(source.resolve())
    assert document.asset_path.startswith(str(root / "brain" / "assets"))
    assert document.parsed_path.startswith(str(root / "brain" / "parsed"))
    assert document.metadata_path.startswith(str(root / "brain" / "documents"))
    assert Path(document.asset_path).read_text(encoding="utf-8") == source.read_text(
        encoding="utf-8"
    )
    assert "Gemma 4 12B" in Path(document.parsed_path).read_text(encoding="utf-8")

    metadata = json.loads(Path(document.metadata_path).read_text(encoding="utf-8"))
    assert metadata["document_id"] == document.document_id
    assert metadata["network_policy"] == "offline"

    ledger_rows = [
        json.loads(line)
        for line in (root / "brain" / "ledgers" / "documents.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert ledger_rows[-1]["event"] == "document.ingested"
    assert ledger_rows[-1]["document_id"] == document.document_id


def test_air_file_search_returns_exact_local_matches(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="air",
        root=tmp_path / "air",
        registry_path=isolated_registry_path,
        network_policy="offline",
    )
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    first.write_text("Gemma offline retrieval notes.\n", encoding="utf-8")
    second.write_text("Airport checklist and charger notes.\n", encoding="utf-8")
    ingest_local_file(profile, first)
    ingest_local_file(profile, second)

    results = search_local_files(profile, "gemma retrieval")

    assert len(results) == 1
    assert results[0].source_path == str(first.resolve())
    assert results[0].score >= 2
    assert "Gemma offline retrieval" in results[0].snippet


def test_air_file_search_treats_punctuation_as_delimiters(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="air",
        root=tmp_path / "air",
        registry_path=isolated_registry_path,
        network_policy="offline",
    )
    source = tmp_path / "punctuation.md"
    source.write_text("hello notes. charger-ready, offline/search.\n", encoding="utf-8")
    ingest_local_file(profile, source)

    notes_results = search_local_files(profile, "notes")
    charger_results = search_local_files(profile, "charger")
    search_results = search_local_files(profile, "search")

    assert notes_results
    assert charger_results
    assert search_results
    assert notes_results[0].source_path == str(source.resolve())


def test_offline_file_store_supports_work_profile_degraded_offline_state(
    tmp_path: Path,
    isolated_registry_path: Path,
) -> None:
    profile = initialize_profile(
        mode="work",
        root=tmp_path / "work",
        registry_path=isolated_registry_path,
        network_policy="offline",
    )
    source = tmp_path / "work-notes.md"
    source.write_text("offline work notes remain searchable.\n", encoding="utf-8")

    document = ingest_local_file(profile, source)
    results = search_local_files(profile, "work searchable")

    assert document.profile == "work"
    assert results
    assert results[0].source_path == str(source.resolve())


@pytest.mark.parametrize(
    "target",
    [
        "https://example.com/research.md",
        "http://localhost:8080/search?q=offline",
    ],
)
def test_air_file_ingest_rejects_urls(
    tmp_path: Path,
    isolated_registry_path: Path,
    target: str,
) -> None:
    profile = initialize_profile(
        mode="air",
        root=tmp_path / "air",
        registry_path=isolated_registry_path,
        network_policy="offline",
    )

    with pytest.raises(BrainOfflineError, match="offline policy blocks"):
        ingest_local_file(profile, target)
