"""All version-bearing metadata must agree with pyproject.toml.

Prevents the server.json / manifest.json drift the Stage E spec calls out
(three places currently must agree by hand).
"""

import json
import pathlib
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _pyproject_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["version"]


def test_server_json_matches_pyproject() -> None:
    version = _pyproject_version()
    server = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    assert server["version"] == version
    assert server["packages"][0]["version"] == version


def test_manifest_json_matches_pyproject() -> None:
    version = _pyproject_version()
    manifest = json.loads((ROOT / "mcpb" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == version


def test_package_dunder_version_matches_pyproject() -> None:
    import rejstrik

    assert rejstrik.__version__ == _pyproject_version()
