"""Execution profiles are registered by SDK source, never imported from case data."""
from developer.files import require
from .capsule import PROFILE
from . import native

from .historical import PROFILE as HISTORICAL_PROFILE
from .historical import backend as historical_backend
BUILTINS = {PROFILE: native, HISTORICAL_PROFILE: historical_backend}


def get_backend(profile):
    require(type(profile) is str and profile in BUILTINS, 'UNSUPPORTED_EXECUTION_PROFILE')
    return BUILTINS[profile]
