"""Unmodified workflow logic in a separate v2 namespace, lock and guard context."""
from ._frozen import bind
bind(globals(), 'sdk_alpha/kit.py')
