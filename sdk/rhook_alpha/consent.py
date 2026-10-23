"""Installation-bound local consent. Not a remote execution credential."""
import hmac
import os
from pathlib import Path
import re
import time

from developer.files import canonical, digest, load, no_links, require, save, sync

SCHEMA = 'rhook/local-owner-consent/0.1'


def scope(root, binding, context, key):
    root = no_links(root)
    require(len(key) == 32, 'INSTALLATION_KEY_REQUIRED')
    require(binding.get('domain') == 'HOOKR_UNIFIED_PLAN_NATIVE_0_1' and
            binding.get('profile') == 'hookr-case-darwin-arm64/0.1', 'LOCAL_MAC_PROFILE_ONLY')
    require(context.get('platform') == 'darwin' and context.get('machine') == 'arm64', 'LOCAL_MAC_ENVIRONMENT_ONLY')
    require(binding.get('workspace') == str(root), 'LOCAL_WORKSPACE_REQUIRED')
    require(binding.get('maximumInvocations') == {'ACTUAL': 1, 'BRANCH': 1, 'B': 0} and
            binding.get('RPC') == 0 and binding.get('WSS') == 0 and
            binding.get('workflowSeconds') == 180 and binding.get('nativeStageSeconds') == 140 and
            binding.get('executionContext') == 'require_escalated', 'LOCAL_LIMITS_REQUIRED')
    require(type(binding.get('planId')) is str and re.fullmatch('[0-9a-f]{32}', binding['planId']), 'INVALID_PLAN_ID')
    require(re.fullmatch('[0-9a-f]{64}', binding.get('operationCommitment', '')), 'INVALID_OPERATION')
    return root / 'local-consents' / binding['planId']


def issue(root, binding, context, key, *, local_owner=False, mac_ready=False, now=None):
    require(local_owner is True and mac_ready is True, 'EXPLICIT_LOCAL_OWNER_AND_POWER_LID_CONSENT_REQUIRED')
    directory = scope(root, binding, context, key)
    now = int(time.time()) if now is None else now
    require(type(now) is int, 'CONSENT_TIME')
    body = {'schema': SCHEMA, 'scope': 'LOCAL_OWNER_MAC_ONLY_NOT_REMOTE',
            'environment': context, 'bindingSha256': digest(canonical(binding)),
            'operationCommitment': binding['operationCommitment'], 'planId': binding['planId'],
            'notBeforeUnix': now, 'expiresUnix': now + 600,
            'localOwnerConfirmed': True, 'macOnPowerOpenLid': True, 'noRetry': True}
    directory.parent.mkdir(mode=0o700, exist_ok=True); sync(directory.parent.parent)
    directory.mkdir(mode=0o700); sync(directory.parent)
    path = directory / 'GRANT.json'
    save(path, {'body': body, 'hmacSha256': hmac.digest(key, canonical(body), 'sha256').hex()})
    path.chmod(0o600)
    return path


def consume(path, root, binding, context, key, *, now=None):
    directory = scope(root, binding, context, key)
    path = no_links(path)
    require(path == directory / 'GRANT.json', 'EXACT_LOCAL_GRANT_PATH_REQUIRED')
    value = load(path, 16384)
    require(type(value) is dict and set(value) == {'body', 'hmacSha256'}, 'LOCAL_GRANT_SHAPE')
    body = value['body']
    require(type(body) is dict and type(value['hmacSha256']) is str and
            hmac.compare_digest(value['hmacSha256'], hmac.digest(key, canonical(body), 'sha256').hex()), 'LOCAL_GRANT_AUTHENTICATION')
    begin, end = body.get('notBeforeUnix'), body.get('expiresUnix')
    now = int(time.time()) if now is None else now
    require(type(begin) is int and type(end) is int and type(now) is int and
            begin <= now < end and 0 < end - begin <= 600 and end - now >= 180, 'LOCAL_GRANT_WINDOW')
    expected = {'schema': SCHEMA, 'scope': 'LOCAL_OWNER_MAC_ONLY_NOT_REMOTE',
                'environment': context, 'bindingSha256': digest(canonical(binding)),
                'operationCommitment': binding['operationCommitment'], 'planId': binding['planId'],
                'notBeforeUnix': begin, 'expiresUnix': end,
                'localOwnerConfirmed': True, 'macOnPowerOpenLid': True, 'noRetry': True}
    require(canonical(body) == canonical(expected), 'LOCAL_GRANT_SCOPE_MISMATCH')
    # Exclusive, fsynced consumption precedes admission or any engine dispatch.
    save(directory / 'CONSUMED.json', {'operationCommitment': binding['operationCommitment'],
         'grantSha256': digest(canonical(value)), 'consumedUnix': now, 'automaticRetry': False})
    # Compatibility with the preserved local runtime schema. founderApproved is
    # an internal legacy field, not a claim of direct founder or remote approval.
    authority = dict(binding, founderApproved=True, macOnPowerOpenLid=True, noRetry=True,
                     notBeforeUnix=begin, expiresUnix=end)
    destination = directory / 'ENGINE_AUTHORITY.json'
    save(destination, authority); destination.chmod(0o600)
    return destination
