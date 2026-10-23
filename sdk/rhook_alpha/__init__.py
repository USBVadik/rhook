"""Executable, local-only Hookr Pair03 SDK."""
import sys

# The preserved runtime authenticates its complete source tree on every command.
sys.dont_write_bytecode = True

from .api import LpBps, SDK

__all__ = ['LpBps', 'SDK']
