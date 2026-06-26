from rejstrik.documents import config


def test_default_model_is_opus():
    assert config.DEFAULT_MODEL == "claude-opus-4-8"


def test_resolve_model_uses_env_override(monkeypatch):
    monkeypatch.setenv("REJSTRIK_MODEL", "claude-haiku-4-5")
    assert config.resolve_model() == "claude-haiku-4-5"


def test_resolve_model_defaults_to_opus(monkeypatch):
    monkeypatch.delenv("REJSTRIK_MODEL", raising=False)
    assert config.resolve_model() == "claude-opus-4-8"
