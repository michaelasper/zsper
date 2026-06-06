from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ZSPER = REPO_ROOT / "src" / "zsper"


def _old_external_serving_markers() -> tuple[str, ...]:
    return (
        "llm" + "-server",
        "llm" + "_server",
        "ZSPER_" + "LLM_SERVER_DIR",
        "prod-start" + "-zsper",
        "prod-stop" + "-zsper",
    )


def _text_marker_violations(source_root: Path) -> list[str]:
    violations: list[str] = []
    for source_file in source_root.rglob("*.py"):
        source = source_file.read_text(encoding="utf-8")
        for marker in _old_external_serving_markers():
            if marker in source:
                violations.append(f"{source_file}: references {marker}")
    return violations


def test_boundary_detector_flags_old_external_serving_markers(tmp_path: Path) -> None:
    source_root = tmp_path / "src" / "zsper"
    source_root.mkdir(parents=True)
    old_repo_name = "llm" + "-server"
    (source_root / "bad.py").write_text(
        f"EXTERNAL_MODEL_REPO = {old_repo_name!r}\n",
        encoding="utf-8",
    )

    assert _text_marker_violations(source_root) == [
        f"{source_root / 'bad.py'}: references {old_repo_name}"
    ]


def test_zsper_product_code_owns_model_serving_without_old_dependency() -> None:
    assert _text_marker_violations(SRC_ZSPER) == []
