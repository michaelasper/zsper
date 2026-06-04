import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CODEX_CONFIG = REPO_ROOT / ".codex" / "config.toml"
AGENT_FILES = (
    REPO_ROOT / ".codex" / "agents" / "implementer.toml",
    REPO_ROOT / ".codex" / "agents" / "reviewer.toml",
)
REQUIRED_AGENT_KEYS = {
    "name",
    "description",
    "model",
    "model_reasoning_effort",
    "sandbox_mode",
    "developer_instructions",
}


def load_toml(path: Path) -> dict:
    assert path.exists(), f"Expected {path.relative_to(REPO_ROOT)} to exist"
    return tomllib.loads(path.read_text(encoding="utf-8"))


def test_codex_agent_configures_thread_limits() -> None:
    agents = load_toml(CODEX_CONFIG)["agents"]

    assert agents["max_threads"] == 4
    assert agents["max_depth"] == 2
    assert agents["job_max_runtime_seconds"] == 3600


def test_codex_agent_definitions_use_supported_instruction_key() -> None:
    for path in AGENT_FILES:
        agent = load_toml(path)

        assert REQUIRED_AGENT_KEYS <= agent.keys()
        assert "instructions" not in agent
        assert agent["developer_instructions"].strip()


def test_zsper_agent_names_and_runtime_settings_are_stable() -> None:
    implementer, reviewer = (load_toml(path) for path in AGENT_FILES)

    assert implementer["name"] == "zsper_implementer"
    assert reviewer["name"] == "zsper_reviewer"

    for agent in (implementer, reviewer):
        assert agent["model"] == "gpt-5.5"
        assert agent["model_reasoning_effort"] == "xhigh"
        assert agent["sandbox_mode"] == "danger-full-access"
