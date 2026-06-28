from rejstrik.documents import config


def test_default_model_is_opus():
    assert config.DEFAULT_MODEL == "claude-opus-4-8"


def test_default_openai_model_is_gpt_4_1():
    assert config.DEFAULT_OPENAI_MODEL == "gpt-4.1"


def test_resolve_model_uses_env_override(monkeypatch):
    monkeypatch.setenv("REJSTRIK_MODEL", "claude-haiku-4-5")
    assert config.resolve_model() == "claude-haiku-4-5"


def test_resolve_model_defaults_to_opus(monkeypatch):
    monkeypatch.delenv("REJSTRIK_MODEL", raising=False)
    assert config.resolve_model() == "claude-opus-4-8"


def test_resolve_model_defaults_to_openai_model_for_openai_provider(monkeypatch):
    monkeypatch.delenv("REJSTRIK_MODEL", raising=False)
    assert config.resolve_model("openai") == "gpt-4.1"


def test_resolve_provider_prefers_openai_key_from_dotenv(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("OPENAI_API_KEY=sk-test\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("REJSTRIK_LLM_PROVIDER", raising=False)

    assert config.resolve_provider() == "openai"


def test_resolve_provider_can_be_overridden(monkeypatch):
    monkeypatch.setenv("REJSTRIK_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    assert config.resolve_provider() == "anthropic"
