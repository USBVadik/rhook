"""Owned group for pinned SDK workflows, not a sandbox for arbitrary programs.

SDK helper/worker spawn paths inherit the isolated CLI group. Their supervisors
still reap their own child; the outer workflow can terminate the complete group.
"""
import os
import signal
import time
import types
from developer.files import require, save

ENV = 'RHOOK_OWNED_WORKFLOW_GROUP'
PROFILE = 'rhook/owned-cli-workflow/0.1'


def active_group():
    marker = os.environ.get(ENV)
    if marker is None:
        return None
    group = os.getpgrp()
    if marker == 'self':
        require(group == os.getpid() == os.getsid(0), 'ISOLATED_WORKFLOW_LEADER_REQUIRED')
    else:
        require(marker.isdecimal() and int(marker) == group == os.getsid(0), 'OWNED_WORKFLOW_GROUP_REQUIRED')
    require(group > 1, 'OWNED_WORKFLOW_GROUP_REQUIRED')
    return group


def guard_module(*, outer=False, helper_file=False, group=None):
    from sdk_alpha_v2._frozen import bind
    module = types.ModuleType('sdk_alpha_v2._owned_workflow_guards')
    module.__package__ = 'sdk_alpha_v2'
    edits = [('4<<30', '1<<30', 2),
             ("'GOMEMLIMIT':'1073741824'", "'GOMEMLIMIT':'536870912'", 1)]
    if outer:
        edits += [
            ('resource.setrlimit(resource.RLIMIT_CPU,(3,3))', 'resource.setrlimit(resource.RLIMIT_CPU,(120,120))', 1),
            ('resource.setrlimit(resource.RLIMIT_FSIZE,(1<<20,1<<20))', 'resource.setrlimit(resource.RLIMIT_FSIZE,(64<<20,64<<20))', 1),
            ('resource.setrlimit(resource.RLIMIT_NOFILE,(64,64))', 'resource.setrlimit(resource.RLIMIT_NOFILE,(256,256))', 1),
            ("'cpuSecondsPerChild':3", "'cpuSecondsPerChild':120", 1)]
    elif helper_file:
        edits += [('resource.setrlimit(resource.RLIMIT_FSIZE,(1<<20,1<<20))', 'resource.setrlimit(resource.RLIMIT_FSIZE,(8<<20,8<<20))', 1)]
    if group is not None:
        edits += [
            ('start_new_session=True', 'start_new_session=False', 2),
            ('os.killpg(proc.pid,signal.SIGKILL)', 'os.kill(proc.pid,signal.SIGKILL)', 2),
            ("'pgid':proc.pid", "'pgid':WORKFLOW_PGID", 2),
            ('int(pgid)==proc.pid', 'int(pgid)==WORKFLOW_PGID', 1),
            ("'ownedProcessGroupKilled':killed", "'ownedProcessGroupKilled':False,'ownedProcessKilled':killed", 1)]
    edits += [('Exact three-key whitelist PATH/LANG/TZ; no inherited environment read or dump.',
               'Whitelist PATH/LANG/TZ plus fixed owned-workflow marker; no inherited environment read or dump.', 1)]
    bind(vars(module), 'repro/portable/legacy_guards.py', edits)
    module.WORKFLOW_PGID = group
    module.CHILD_ENV = dict(module.CHILD_ENV, **{ENV: 'self' if outer else str(group)})
    return module


def finish_group(directory, result):
    """Only the group created for this CLI; never enumerate unrelated processes."""
    from developer.files import load
    process = load(directory / 'PROCESS.json', 4096) if (directory / 'PROCESS.json').exists() else None
    if process is None:
        return result
    group = process['pgid']
    require(group == process['pid'] and group > 1 and group != os.getpgrp(), 'WORKFLOW_GROUP_OWNERSHIP')
    present = False
    try:
        os.killpg(group, 0)
        present = True
        os.killpg(group, signal.SIGKILL)
    except ProcessLookupError:
        pass
    gone = False
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        try:
            os.killpg(group, 0)
        except ProcessLookupError:
            gone = True
            break
        time.sleep(0.01)
    cleanup = dict(profile=PROFILE, group=group, remainingGroupKilled=present, groupAbsent=gone)
    save(directory / 'WORKFLOW_CLEANUP.json', cleanup)
    result = dict(result, workflowGroupGone=gone, workflowCaptureProfile=PROFILE)
    if not gone:
        result['stop'] = result['stop'] or 'WORKFLOW_GROUP_CLEANUP_UNCONFIRMED'
    elif present:
        result['stop'] = result['stop'] or 'WORKFLOW_DESCENDANTS_REMAINED'
    save(directory / 'FINAL_PROCESS_RESULT.json', result)
    return result
