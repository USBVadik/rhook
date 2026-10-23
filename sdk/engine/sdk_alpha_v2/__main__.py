"""Versioned v2 entry point. No default command measures the host or runs history."""
from ._frozen import bind
bind(globals(), 'sdk_alpha/__main__.py')
