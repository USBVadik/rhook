"""Authenticated sensor/admission implementation, scoped to the new policy."""
from sdk_alpha_v2._frozen import bind
bind(globals(), 'sdk_alpha/resources.py', [
    ("REPO/'sdk_alpha/policy.json'", "REPO/'plan_native/policy.json'", 1),
])
