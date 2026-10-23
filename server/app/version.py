import tomllib
from functools import lru_cache
from importlib import metadata
from pathlib import Path

PACKAGE_NAME = "askharbor-server"


@lru_cache
def get_version() -> str:
    """Return the API version without keeping a second copy of it in code.

    Installed packages, including editable installs, answer from their
    metadata. A plain source checkout that was never installed falls back to
    the version field in pyproject.toml, which is the single source of truth.
    """
    try:
        return metadata.version(PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        with pyproject.open("rb") as handle:
            return tomllib.load(handle)["project"]["version"]
