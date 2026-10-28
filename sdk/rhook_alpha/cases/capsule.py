"""Versioned local content addressing; no chain-trust inference from hashes."""
import copy
import re
from developer.files import canonical, digest, require
SCHEMA = 'rhook/case-capsule/0.1'
PROFILE = 'nitro-hookr-lp/0.1'
MAX_PACKAGE = 8 << 20

def hash32(value):
    return type(value) is str and re.fullmatch('0x[0-9a-f]{64}', value) is not None

def sha32(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None

def seal(document):
    body = copy.deepcopy(document)
    body.pop('capsuleId', None)
    body['capsuleId'] = digest(SCHEMA.encode() + b'\n' + canonical(body))
    return body

def validate(document, package):
    d = document
    require(type(d) is dict and set(d) == {'schema', 'caseId', 'capsuleId', 'checkpoint', 'target', 'arrivals', 'assets', 'execution', 'adapter', 'provenance', 'coverage'}, 'CAPSULE_FIELDS')
    require(d['schema'] == SCHEMA and d['capsuleId'] == seal(d)['capsuleId'], 'CAPSULE_CONTENT_ADDRESS')
    require(type(d['caseId']) is str and re.fullmatch('[a-z0-9][a-z0-9-]{0,63}', d['caseId']), 'CASE_ID')
    c, t = (d['checkpoint'], d['target'])
    require(type(c) is dict and set(c) == {'chainId', 'blockNumber', 'blockHash', 'stateRoot'}, 'CHECKPOINT_FIELDS')
    require(type(t) is dict and set(t) == {'blockNumber', 'blockHash', 'stateRoot', 'receiptsRoot'}, 'TARGET_FIELDS')
    require(type(c['chainId']) is int and 0 < c['chainId'] < 2 ** 53 and (type(c['blockNumber']) is int) and (0 <= c['blockNumber'] < 2 ** 53), 'CHECKPOINT_NUMBER')
    require(type(t['blockNumber']) is int and t['blockNumber'] == c['blockNumber'] + 1, 'ORIGINAL_PARENT_REQUIRED')
    require(all((hash32(v[k]) for v, keys in [(c, ('blockHash', 'stateRoot')), (t, ('blockHash', 'stateRoot', 'receiptsRoot'))] for k in keys)), 'HEADER_HASH')
    a = d['arrivals']
    require(type(a) is list and 0 < len(a) <= 4096 and all(map(hash32, a)) and (len(set(a)) == len(a)), 'ORDERED_ARRIVALS')
    require(type(package) is bytes and len(package) <= MAX_PACKAGE, 'PACKAGE_SIZE')
    require(d['assets'] == {'BLOCK_PACKAGE.json': {'sha256': digest(package), 'bytes': len(package)}}, 'CAPSULE_ASSET_INTEGRITY')
    e = d['execution']
    require(type(e) is dict and set(e) == {'profile', 'inputCommitment', 'witnessCommitment'} and (type(e['profile']) is str) and (len(e['profile']) <= 96) and sha32(e['inputCommitment']) and sha32(e['witnessCommitment']), 'EXECUTION_DESCRIPTOR')
    a = d['adapter']
    require(type(a) is dict and set(a) == {'id', 'config'} and (type(a['id']) is str) and (0 < len(a['id']) <= 96) and (type(a['config']) is dict), 'ADAPTER_DESCRIPTOR')
    require(type(d['provenance']) is dict and set(d['provenance']) == {'kind', 'description'} and (d['provenance']['kind'] in {'USER_SUPPLIED', 'RETAINED_CAPTURE'}) and (type(d['provenance']['description']) is str) and (len(d['provenance']['description']) <= 1024), 'PROVENANCE_DESCRIPTION')
    require(d['coverage'] == {'reads': 'UNKNOWN', 'writes': 'UNKNOWN'}, 'COVERAGE_IS_NOT_SELF_CERTIFIED')
    return d
