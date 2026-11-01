"""Counterfactual Session SDK: one checkpoint, several independently declared variants.

Profile adapters are registered here; the session core in core.py is profile-neutral.
"""
from .core import CounterfactualSession, SessionError, LIMITATIONS, MAX_VARIANTS, SCHEMA


def _adapters():
    from .hookr import HookrScenarioAdapter
    return {HookrScenarioAdapter.profile: HookrScenarioAdapter}


def adapter(home, profile):
    adapters = _adapters()
    if profile not in adapters:
        raise SessionError('UNSUPPORTED_PROFILE', 'Supported session profiles: ' + ', '.join(sorted(adapters)) + '.')
    return adapters[profile](home)


def create_session(home, *, source, expected_sha256, checkpoint, profile='hookr-buy/0.1'):
    """Create (or reopen, when identical) a session from one pinned source. Offline only."""
    return CounterfactualSession.create(home, adapter(home, profile), source=source,
                                        expected_sha256=expected_sha256, checkpoint=checkpoint)


def open_session(home, session_id, *, profile='hookr-buy/0.1'):
    """Reopen a session offline; every identity is re-derived from its retained source."""
    return CounterfactualSession.open(home, adapter(home, profile), session_id)


__all__ = ['CounterfactualSession', 'SessionError', 'LIMITATIONS', 'MAX_VARIANTS', 'SCHEMA',
           'create_session', 'open_session', 'adapter']
