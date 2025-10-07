"""Top-level package for the tooldex agent framework."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("tooldex")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["__version__"]
