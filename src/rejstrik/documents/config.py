import os

DEFAULT_MODEL = "claude-opus-4-8"


def resolve_model() -> str:
    return os.environ.get("REJSTRIK_MODEL") or DEFAULT_MODEL
