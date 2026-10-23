import importlib
import tomllib
from importlib import metadata
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main, version

PYPROJECT_VERSION = tomllib.loads(
    (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()
)["project"]["version"]


@pytest.fixture
def reload_main():
    yield lambda: importlib.reload(main)
    version.get_version.cache_clear()
    importlib.reload(main)


def test_api_version_matches_pyproject() -> None:
    assert main.app.version == PYPROJECT_VERSION
    assert TestClient(main.app).get("/openapi.json").json()["info"]["version"] == PYPROJECT_VERSION


def test_api_version_follows_installed_metadata(
    monkeypatch: pytest.MonkeyPatch, reload_main
) -> None:
    monkeypatch.setattr(version.metadata, "version", lambda name: "9.9.9+test")
    version.get_version.cache_clear()

    app = reload_main().app

    assert app.version == "9.9.9+test"
    assert TestClient(app).get("/openapi.json").json()["info"]["version"] == "9.9.9+test"


def test_source_checkout_falls_back_to_pyproject(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(name: str) -> str:
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr(version.metadata, "version", missing)
    version.get_version.cache_clear()
    try:
        assert version.get_version() == PYPROJECT_VERSION
    finally:
        version.get_version.cache_clear()


def test_no_hardcoded_version_literal_in_main() -> None:
    source = Path(main.__file__).read_text()
    assert 'version="' not in source
    assert PYPROJECT_VERSION not in source
