"""Reuse the existing one-shot consent and historical resource supervisor."""
from .. import native
from . import PROFILE


class _ScopedSDK:
    _native_profile = PROFILE
    def __init__(self, sdk): self._sdk = sdk
    def __getattr__(self, key): return getattr(self._sdk, key)


def configure(sdk, path): return native.configure(_ScopedSDK(sdk), path)
def authenticate(sdk, case, **kwargs): return native.authenticate(_ScopedSDK(sdk), case, **kwargs)
def operation(sdk, ref, **kwargs): return native.operation(_ScopedSDK(sdk), ref, **kwargs)
def authorize(sdk, ref, **kwargs): return native.authorize(_ScopedSDK(sdk), ref, **kwargs)
def replay(sdk, ref, authority): return native.replay(_ScopedSDK(sdk), ref, authority)
def verify(sdk, run): return native.verify(_ScopedSDK(sdk), run)
