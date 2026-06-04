import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ZSPER = REPO_ROOT / "src" / "zsper"
FORBIDDEN_IMPORT_ROOTS = (
    "benchmarks.local_server",
    "local_server",
)


def _import_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.ImportFrom):
        return node.module
    return None


def _forbidden_import_violations(source_root: Path) -> list[str]:
    violations: list[str] = []
    for source_file in source_root.rglob("*.py"):
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(FORBIDDEN_IMPORT_ROOTS):
                        violations.append(f"{source_file}: imports {alias.name}")
            module = _import_name(node)
            if module and module.startswith(FORBIDDEN_IMPORT_ROOTS):
                violations.append(f"{source_file}: imports from {module}")
            if isinstance(node, ast.ImportFrom) and node.module == "benchmarks":
                for alias in node.names:
                    if alias.name == "local_server":
                        violations.append(f"{source_file}: imports benchmarks.local_server")
    return violations


def test_boundary_detector_flags_llm_server_benchmark_imports(tmp_path: Path) -> None:
    source_root = tmp_path / "src" / "zsper"
    source_root.mkdir(parents=True)
    (source_root / "bad.py").write_text(
        "from benchmarks import local_server\n",
        encoding="utf-8",
    )

    assert _forbidden_import_violations(source_root) == [
        f"{source_root / 'bad.py'}: imports benchmarks.local_server"
    ]


def test_zsper_product_code_does_not_import_llm_server_internals() -> None:
    assert _forbidden_import_violations(SRC_ZSPER) == []
