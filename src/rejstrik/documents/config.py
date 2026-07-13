import os

from dotenv import find_dotenv, load_dotenv

DEFAULT_MODEL = "claude-opus-4-8"
DEFAULT_OPENAI_MODEL = "gpt-4.1"

# Set True by the test suite so a developer's real repo .env never leaks API
# keys into the offline, key-free tests.
_DOTENV_DISABLED = False
_dotenv_loaded = False


def _reset_dotenv_cache() -> None:
    """Test helper: forget that the .env was already loaded this process."""
    global _dotenv_loaded
    _dotenv_loaded = False


def _load_local_env() -> None:
    """Load the repo .env at most once per process.

    Loading once (instead of on every call) means environment mutations made
    after the first call are respected, and removes per-call disk I/O on a hot
    path.
    """
    global _dotenv_loaded
    if _DOTENV_DISABLED or _dotenv_loaded:
        return
    load_dotenv(find_dotenv(usecwd=True))
    _dotenv_loaded = True


def resolve_provider() -> str:
    _load_local_env()
    configured = os.environ.get("REJSTRIK_LLM_PROVIDER")
    if configured:
        return configured.strip().lower()
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return "anthropic"


def resolve_model(provider: str | None = None) -> str:
    provider = provider or "anthropic"
    fallback = DEFAULT_OPENAI_MODEL if provider == "openai" else DEFAULT_MODEL
    return os.environ.get("REJSTRIK_MODEL") or fallback


def has_llm_key() -> bool:
    _load_local_env()
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY"))
