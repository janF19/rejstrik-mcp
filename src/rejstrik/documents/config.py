import os

from dotenv import load_dotenv

DEFAULT_MODEL = "claude-opus-4-8"
DEFAULT_OPENAI_MODEL = "gpt-4.1"


def _load_local_env() -> None:
    load_dotenv()


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
