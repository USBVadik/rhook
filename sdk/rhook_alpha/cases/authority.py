"""Durable, operation-bound local consent for a trusted local operator."""
import hmac
import os
import re
import time
from developer.files import canonical, digest, load, no_links, require, save, sync

def directory(root, binding):
    ref = binding.get('planId')
    require(type(ref) is str and re.fullmatch('c-[0-9a-f]{32}', ref), 'PLAN_ID')
    return no_links(root) / ref

def issue(root, binding, key, *, now=None):
    require(type(key) is bytes and len(key) == 32, 'CONSENT_KEY')
    now = int(time.time()) if now is None else now
    require(type(now) is int, 'CONSENT_TIME')
    d = directory(root, binding)
    d.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    sync(d.parent.parent)
    d.mkdir(mode=0o700)
    sync(d.parent)
    body = {'schema': 'rhook/case-consent/0.1', 'binding': binding, 'notBeforeUnix': now, 'expiresUnix': now + 600, 'localOwnerConfirmed': True, 'noRetry': True}
    save(d / 'GRANT.json', {'body': body, 'hmacSha256': hmac.digest(key, canonical(body), 'sha256').hex()})
    (d / 'GRANT.json').chmod(0o600)
    return d / 'GRANT.json'

def consume(path, root, binding, key, *, now=None):
    d = directory(root, binding)
    require(no_links(path) == d / 'GRANT.json', 'GRANT_PATH')
    v = load(path, 65536)
    require(type(v) is dict and set(v) == {'body', 'hmacSha256'} and (type(v['body']) is dict) and (type(v['hmacSha256']) is str), 'GRANT_SHAPE')
    body = v['body']
    require(hmac.compare_digest(v['hmacSha256'], hmac.digest(key, canonical(body), 'sha256').hex()), 'GRANT_HMAC')
    require(body.get('binding') == binding, 'GRANT_BINDING')
    begin, end = (body.get('notBeforeUnix'), body.get('expiresUnix'))
    now = int(time.time()) if now is None else now
    require(type(now) is int and type(begin) is int and (type(end) is int) and (begin <= now < end) and (0 < end - begin <= 600) and (end - now >= 180), 'GRANT_WINDOW')
    require(body == {'schema': 'rhook/case-consent/0.1', 'binding': binding, 'notBeforeUnix': begin, 'expiresUnix': end, 'localOwnerConfirmed': True, 'noRetry': True}, 'GRANT_FIELDS')
    save(d / 'CONSUMED.json', {'operationCommitment': binding['operationCommitment'], 'grantSha256': digest(canonical(v)), 'consumedUnix': now, 'automaticRetry': False})
    return body
