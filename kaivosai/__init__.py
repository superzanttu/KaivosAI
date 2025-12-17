"""KaivosAI package API.

This package re-exports the legacy API and new modules during refactor.
"""
from ._legacy import *
from .cli import *

__all__ = [n for n in dir() if not n.startswith("_")]
