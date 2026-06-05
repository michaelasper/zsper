import ast
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"
BOUNDARY_DOC = REPO_ROOT / "docs" / "architecture" / "repository-boundary.md"
SRC_ZSPER = REPO_ROOT / "src" / "zsper"
FORBIDDEN_TEXT_REFERENCES = (
    "/Users/michaelasper/source/llm-server",
    "source.llm-server",
)
FORBIDDEN_IMPORT = "benchmarks.local_server"


def is_forbidden_import(node: ast.AST) -> bool:
    if isinstance(node, ast.Import):
        return any(
            alias.name == FORBIDDEN_IMPORT
            or alias.name.startswith(f"{FORBIDDEN_IMPORT}.")
            for alias in node.names
        )

    if isinstance(node, ast.ImportFrom):
        if node.module == "benchmarks":
            return any(alias.name == "local_server" for alias in node.names)
        return node.module == FORBIDDEN_IMPORT or (
            node.module is not None and node.module.startswith(f"{FORBIDDEN_IMPORT}.")
        )

    return False


def read_text(path: Path) -> str:
    assert path.exists(), f"Expected {path.relative_to(REPO_ROOT)} to exist"
    return path.read_text(encoding="utf-8")


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


def assert_contains_all(text: str, required_phrases: tuple[str, ...]) -> None:
    for phrase in required_phrases:
        assert phrase in text


def test_repository_boundary_names_owners_and_dependency_forms() -> None:
    boundary = read_text(BOUNDARY_DOC)

    assert_contains_all(
        boundary,
        (
            "/Users/michaelasper/source/llm-server",
            "owns model deployment",
            "oMLX serving",
            "/Users/michaelasper/source/zsper",
            "owns profiles",
            "CLI",
            "configs",
            "Brain",
            "RAG",
            "orchestrator",
            "docs",
            "tests",
        ),
    )

    readme = read_text(README)
    assert_contains_all(
        readme,
        (
            "/Users/michaelasper/source/llm-server",
            "owns model deployment",
            "oMLX serving",
            "/Users/michaelasper/source/zsper",
            "owns profiles",
            "CLI",
            "configs",
            "Brain",
            "RAG",
            "orchestrator",
            "docs",
            "tests",
        ),
    )

    for allowed_form in (
        "environment variable",
        "command template",
        "deploy contract file",
        "local OpenAI-compatible HTTP",
    ):
        assert allowed_form in boundary

    for disallowed_form in (
        "importing benchmark internals",
        "storing profile data in llm-server",
        "generating adapters from llm-server",
        "adding Brain/RAG/memory/tasks to llm-server",
        "benchmarks.local_server",
    ):
        assert disallowed_form in boundary


def find_forbidden_source_boundary_references(source_root: Path) -> list[str]:
    violations: list[str] = []
    source_files = list(source_root.rglob("*.py"))
    for source_file in source_files:
        source = source_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(source_file))
        for node in ast.walk(tree):
            if is_forbidden_import(node):
                violations.append(
                    f"{source_file.relative_to(source_root)} must not import "
                    f"{FORBIDDEN_IMPORT}"
                )

        for forbidden_fragment in FORBIDDEN_TEXT_REFERENCES:
            if forbidden_fragment in source:
                violations.append(
                    f"{source_file.relative_to(source_root)} must not import or reference "
                    f"{forbidden_fragment}"
                )
    return violations


def test_forbidden_benchmark_import_detector_flags_import_forms(tmp_path: Path) -> None:
    source_root = tmp_path / "src" / "zsper"
    source_root.mkdir(parents=True)

    (source_root / "direct_import.py").write_text(
        "import benchmarks.local_server\n",
        encoding="utf-8",
    )
    (source_root / "from_import.py").write_text(
        "from benchmarks import local_server\n",
        encoding="utf-8",
    )

    violations = find_forbidden_source_boundary_references(source_root)

    assert len(violations) == 2
    assert any("direct_import.py" in violation for violation in violations)
    assert any("from_import.py" in violation for violation in violations)


def test_zsper_source_does_not_import_llm_server_internals() -> None:
    if not SRC_ZSPER.exists():
        pytest.skip(
            "src/zsper does not exist yet; FND-002 will enforce source boundary once "
            "package exists"
        )

    violations = find_forbidden_source_boundary_references(SRC_ZSPER)
    assert not violations
