"""Same validated sensor format and fail-closed rules; distinct v2 thresholds."""
from ._frozen import bind
bind(globals(), 'sdk_alpha/resources.py', [
    ("REPO/'sdk_alpha/policy.json'", "REPO/'sdk_alpha_v2/policy.json'", 1),
])
