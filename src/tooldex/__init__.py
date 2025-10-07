"""Top-level package for the tooldex agent framework."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import tomllib


def _read_local_version() -> str | None:
    project_root = Path(__file__).resolve().parents[2]
    pyproject = project_root / "pyproject.toml"
    if not pyproject.is_file():
        return None

    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except Exception:  # pragma: no cover - defensive
        return None
    return data.get("project", {}).get("version")


_local_version = _read_local_version()

try:
    _dist_version = version("tooldex")
except PackageNotFoundError:
    _dist_version = None


__version__ = _local_version or _dist_version or "0.0.0"

__all__ = ["__version__"]
