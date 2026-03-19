"""Codd relational algebra."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("codd")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"
