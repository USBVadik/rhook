"""Private v2 guard context; pure file/baseline utilities remain shared."""
import json
import types
from sdk_alpha import common as v1
from ._frozen import isolated_guards

REPO = v1.REPO
require, sha, commitment = v1.require, v1.sha, v1.commitment
local_file, path_without_links = v1.local_file, v1.path_without_links
read_json, exact_copy, store = v1.read_json, v1.exact_copy, v1.store

portable = types.SimpleNamespace(**vars(v1.portable))
portable.guards = isolated_guards()
portable.LIMITS = dict(v1.portable.LIMITS, workerSampledRssBytes=1<<30,
                       GOMEMLIMIT_advisoryBytes=512<<20)
_policy = json.loads((REPO/'sdk_alpha_v2/policy.json').read_text())
require(_policy['workerRssBytes'] == 1<<30 and _policy['GOMEMLIMIT_advisoryBytes'] == 512<<20,
        'EXACT_PAIR03_MEMORY_CLASS_REQUIRED')
require(_policy['minimumAdmissionFreeBytes'] == _policy['workerRssBytes']+_policy['minimumRuntimeFreeBytes']
        and _policy['minimumRuntimeFreeBytes'] == _policy['osReserveBytes']+_policy['supervisorAllowanceBytes'],
        'ADMISSION_CLASS_MARGIN_MISMATCH')
_plan = portable.specification(REPO)
require(_policy['workload'] == dict(chainId=4663, blockNumber=_plan['blockNumber'], arrivals=7,
        packageSha256=_plan['packageSha256'], intervention='lpBps100to0', source='NIL_NO_HYDRATION'),
        'SAVED_PAIR03_WORKLOAD_ONLY')


def sources():
    result = v1.sources()  # Unmodified v1 source closure still verifies its build.
    for path in sorted((REPO/'sdk_alpha_v2').rglob('*')):
        if '__pycache__' in path.parts: continue
        require(not path.is_symlink(), 'SOURCE_SYMLINK')
        if path.is_file(): result[str(path.relative_to(REPO))] = sha(path)
    result['rhook-v2'] = sha(REPO/'rhook-v2')
    return result
