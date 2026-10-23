"""Separate guard globals, with unchanged v2 numerical limits."""
import types
from sdk_alpha_v2 import common as v2
from sdk_alpha_v2._frozen import isolated_guards

REPO = v2.REPO
require, sha, commitment = v2.require, v2.sha, v2.commitment
local_file, path_without_links = v2.local_file, v2.path_without_links
portable = types.SimpleNamespace(**vars(v2.portable))
portable.guards = isolated_guards()
store = portable.guards.store
