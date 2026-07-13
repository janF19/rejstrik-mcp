import pytest

from rejstrik.documents import config


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch):
    """Make the suite pass identically with or without a repo .env present.

    Blanks the LLM keys and disables the dotenv loader so a developer's real
    .env (which legitimately holds OPENAI_API_KEY for keyed smoke testing)
    cannot leak into these offline, key-free tests. Keyed-mode tests set keys
    explicitly; the dotenv-loading tests re-enable the loader themselves.
    """
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "REJSTRIK_LLM_PROVIDER"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(config, "_DOTENV_DISABLED", True)
    config._reset_dotenv_cache()
