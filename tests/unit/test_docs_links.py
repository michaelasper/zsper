import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC = REPO_ROOT / "docs" / "zsper-local-ai-platform-ultimate-spec.md"
DAG = (
    REPO_ROOT
    / "docs"
    / "superpowers"
    / "plans"
    / "2026-06-04-zsper-platform-implementation-dag.md"
)
PLATFORM_OVERVIEW = REPO_ROOT / "docs" / "architecture" / "platform-overview.md"
LOCAL_DEVELOPMENT = REPO_ROOT / "docs" / "runbooks" / "local-development.md"
TESTING = REPO_ROOT / "docs" / "runbooks" / "testing.md"

REQUIRED_DOCS = (SPEC, DAG, PLATFORM_OVERVIEW, LOCAL_DEVELOPMENT, TESTING)
REQUIRED_LINKS = (
    "docs/zsper-local-ai-platform-ultimate-spec.md",
    "docs/superpowers/plans/2026-06-04-zsper-platform-implementation-dag.md",
)
REQUIRED_SOURCE_TARGETS = (SPEC, DAG)
PHASES = (
    "Phase 1: Documentation And Project Baseline",
    "Phase 2: Profiles And Code Adapters",
    "Phase 3: Brain Storage And Compose",
    "Phase 4: Documents And RAG",
    "Phase 5: Notes, Tasks, Memories",
    "Phase 6: Orchestrator And Agent Runs",
    "Phase 7: Offline And Security Gates",
)
COMMAND_PURPOSES = {
    "`pytest tests/unit -v`": "fast unit checks",
    "`pytest tests/integration -v`": "service and profile integration checks",
    "`pytest tests/security -v`": "policy, redaction, and isolation gates",
    "`npm --prefix apps/brain-web test`": "Next.js Brain web flows",
    "`zsper profile doctor --profile work && zsper code smoke --profile work && zsper brain status --profile work && zsper agent status --profile work`": "full smoke verification",
}


def read_doc(path: Path) -> str:
    assert path.exists(), f"Expected {path.relative_to(REPO_ROOT)} to exist"
    return path.read_text(encoding="utf-8")


def linked_local_targets(path: Path) -> set[Path]:
    targets: set[Path] = set()
    for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", read_doc(path)):
        href = match.group(1).split("#", maxsplit=1)[0]
        if href.startswith(("http://", "https://", "mailto:")):
            continue
        targets.add((path.parent / href).resolve())
    return targets


def test_referenced_local_docs_exist() -> None:
    for path in REQUIRED_DOCS:
        assert path.exists(), f"Missing {path.relative_to(REPO_ROOT)}"


def test_new_docs_link_to_source_spec_and_dag() -> None:
    for path in (PLATFORM_OVERVIEW, LOCAL_DEVELOPMENT, TESTING):
        text = read_doc(path)
        resolved_targets = linked_local_targets(path)
        for link in REQUIRED_LINKS:
            assert link in text
        for target in REQUIRED_SOURCE_TARGETS:
            assert target.resolve() in resolved_targets


def test_platform_overview_summarizes_spec_phases_and_ownership() -> None:
    overview = read_doc(PLATFORM_OVERVIEW)

    for phase in PHASES:
        assert phase in overview

    required_phrases = (
        "zsper-brain is the product shell",
        "zsper-code is the local model adapter layer",
        "FastAPI",
        "Next.js",
        "Postgres + pgvector",
        "hybrid BM25 + dense",
        "tmux",
        "append-only JSONL ledgers",
    )
    for phrase in required_phrases:
        assert phrase in overview


def test_testing_runbook_lists_exact_commands_with_purpose() -> None:
    testing = read_doc(TESTING)

    for command, purpose in COMMAND_PURPOSES.items():
        assert command in testing
        assert purpose in testing
