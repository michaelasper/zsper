from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"
BOUNDARY_DOC = REPO_ROOT / "docs" / "architecture" / "repository-boundary.md"
SRC_ZSPER = REPO_ROOT / "src" / "zsper"
DOCS = REPO_ROOT / "docs"


def _old_external_serving_markers() -> tuple[str, ...]:
    return (
        "llm" + "-server",
        "source." + "llm" + "-server",
        "ZSPER_" + "LLM_SERVER_DIR",
        "llm" + "_server",
    )


def read_text(path: Path) -> str:
    assert path.exists(), f"Expected {path.relative_to(REPO_ROOT)} to exist"
    return path.read_text(encoding="utf-8")


def assert_contains_all(text: str, required_phrases: tuple[str, ...]) -> None:
    for phrase in required_phrases:
        assert phrase in text


def test_readme_links_to_ultimate_spec() -> None:
    readme = read_text(README)

    assert "docs/zsper-local-ai-platform-ultimate-spec.md" in readme


def test_readme_limitations_reflect_phase4_rag_commands() -> None:
    readme = read_text(README)

    for stale_claim in (
        "Air ingest accepts UTF-8 local text only",
        "Search is exact local token search",
        "`brain answer` is still reserved",
    ):
        assert stale_claim not in readme

    assert "Hybrid BM25 + dense retrieval" in readme
    assert "`brain answer` returns citation objects" in readme


def test_repository_boundary_names_zsper_owned_model_serving() -> None:
    boundary = read_text(BOUNDARY_DOC)
    readme = read_text(README)
    required_phrases = (
        "/Users/michaelasper/source/zsper",
        "owns profiles",
        "CLI",
        "configs",
        "Brain",
        "RAG",
        "orchestrator",
        "profile-local oMLX",
        "local OpenAI-compatible HTTP",
        "docs",
        "tests",
    )

    assert_contains_all(boundary, required_phrases)
    assert_contains_all(readme, required_phrases)

    assert_contains_all(
        boundary,
        (
            "ZSPER_OMLX_BIN",
            "profile-local runtime",
            "Brain Compose must not include model serving",
        ),
    )

    assert_contains_all(
        boundary,
        (
            "profile data outside the profile root",
            "hosted model API",
            "generated editor configs outside profile-owned paths",
        ),
    )


def _text_marker_violations(source_root: Path) -> list[str]:
    violations: list[str] = []
    for source_file in source_root.rglob("*"):
        if source_file.is_file() and source_file.suffix in {".md", ".py", ".toml", ".sh"}:
            source = source_file.read_text(encoding="utf-8")
            for marker in _old_external_serving_markers():
                if marker in source:
                    violations.append(f"{source_file} references {marker}")
    return violations


def test_boundary_detector_flags_old_external_serving_markers(tmp_path: Path) -> None:
    source_root = tmp_path / "docs"
    source_root.mkdir(parents=True)
    old_repo_name = "llm" + "-server"
    (source_root / "bad.md").write_text(
        f"Use {old_repo_name} for model serving.\n",
        encoding="utf-8",
    )

    assert _text_marker_violations(source_root) == [
        f"{source_root / 'bad.md'} references {old_repo_name}"
    ]


def test_zsper_source_and_docs_do_not_reference_old_external_serving_dependency() -> None:
    assert _text_marker_violations(SRC_ZSPER) == []
    assert _text_marker_violations(DOCS) == []
