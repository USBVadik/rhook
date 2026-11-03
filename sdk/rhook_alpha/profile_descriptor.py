"""Profile Descriptor 0.1 (SDK 0.6, offline): reviewed hook profiles as data, one interpreter.

A descriptor (`rhook/hook-profile-descriptor/0.1`) states, as canonical JSON, what the SDK 0.4 worker keeps in
Go constants and the embedded profile.json: chain and engine, contract identities, pool, storage targets and
their slot derivations, named bit fields, the authenticated original words, typed intervention kinds with
parameters, original-state predicates, assignments, result invariants and conflicts, the action, setup,
measures and declared witness reads.

The descriptor contains no expressions, scripts, opcodes or code. Predicates are a closed vocabulary
(`compare`, `productBound`). Its SHA-256 identifies it; it does not prove that it describes the contract
correctly. Whether a descriptor may be used is a separate review record in the catalogue
(`descriptors/CATALOGUE.json`): only RHOOK-internal reviewed profiles are loadable, never user files.

Everything here is offline: no worker, EVM, network, authority or result. Python mirror of native/descriptor.go;
both raise the same codes.
"""
import copy
import json
import re
from pathlib import Path

from developer.files import canonical, digest, strict

SDK_ROOT = Path(__file__).resolve().parents[1]
DESCRIPTOR_DIR = SDK_ROOT / 'rhook_alpha/cases/scenario/native/descriptors'
COMPILED_PROFILE = SDK_ROOT / 'rhook_alpha/cases/scenario/native/profile.json'
SCHEMA = 'rhook/hook-profile-descriptor/0.1'
CATALOGUE_SCHEMA = 'rhook/hook-profile-catalogue/0.1'
SPEC_DOMAIN = 'rhook/hookr-profile-overlay/0.1'
ORIGIN_KIND = 'AUTHENTICATED_CHECKPOINT_PROFILE_OVERLAY'
SESSION_KIND = 'HOOK_PROFILE_OVERLAY'
# The descriptor-driven worker's linked profile.
BACKEND_PROFILE = 'nitro-hook-profile-overlay/0.1'
# Three separate facts, kept apart:
# 1. build verification (G4B, records outside the SDK): two byte-identical builds of commit 74916e4 with
#    independent caches in one fixed neutral root; source commitment and compiled inventory as predicted;
# 2. the reviewed engine identity below (G5 preflight): an operation for exactly this worker becomes bindable;
# 3. execution authorization: none here. A native run additionally needs the owner's record for that one operation
#    (cases/scenario/api.py require_profile_authorization), consent and the one-shot workflow.
# This file is not staged into the worker module, so the worker source commitment is unchanged by it. The embedded
# catalogue still reads NOT_ACCEPTED_NO_ENGINE_IDENTITY_G4B_G5_REQUIRED: it was fixed before G4B and is part of
# the worker source commitment, so it is not rewritten.
ACCEPTED_PROFILE_ENGINE = dict(sourceSha256='4db4269aad9e28970eb3b13508366771c12827aa8fc5687399e28ff418251546',
                               binarySha256='a56db9e53a13331e21c8e45fbb20632a7bc13ef12c864afedf4169a90b35ae04',
                               policySha256='792b13a533f79d8d66ade565a5ad41cdb45bd1da4684e06dcdc1825c1a04abc6')
# The rest of the reviewed identity record: the linked profile and the exact descriptor and catalogue bytes the
# worker embeds. Preparation and operation binding require all of it.
PROFILE_ENGINE_RECORD = dict(profile=BACKEND_PROFILE, engine=ACCEPTED_PROFILE_ENGINE,
                             descriptor=dict(profileId='hookr-1', revision=2,
                                             sha256='29f21a174b49a306737729da3ad48ef6e9438cd9a0c2a343504b8025ef9e9596'),
                             catalogueSha256='93a2f234259c861e25d07b5b3257f7fea1f777c0b8526b766d55b069a7f1fe92',
                             buildVerification='G4B_TWO_BYTE_IDENTICAL_BUILDS_FIXED_NEUTRAL_ROOT',
                             status='REVIEWED_ENGINE_IDENTITY_NOT_EXECUTION_AUTHORIZATION')
ENGINE_RECORD_KEYS = {'profile', 'engine', 'descriptor', 'catalogueSha256', 'buildVerification', 'status'}
ENGINE_BUILD_VERIFICATION = 'G4B_TWO_BYTE_IDENTICAL_BUILDS_FIXED_NEUTRAL_ROOT'
ENGINE_RECORD_STATUS = 'REVIEWED_ENGINE_IDENTITY_NOT_EXECUTION_AUTHORIZATION'
TARGET_AUTHENTICATOR = SDK_ROOT / 'rhook_alpha/profile-target-state.mjs'
RELEASE_DOMAIN = 'rhook/hookr-scenario/0.1/release'
PURPOSES = ('OFFLINE_PREPARATION', 'NATIVE_EXECUTION')
MAX_DESCRIPTOR_BYTES = 1 << 20
MAX_SAFE = (1 << 53) - 1

HEX32 = re.compile('0x[0-9a-f]{64}')
ADDRESS = re.compile('0x[0-9a-f]{40}')
SHA = re.compile('[0-9a-f]{64}')
NAME = re.compile('[A-Za-z][A-Za-z0-9_]{0,47}')
KIND_NAME = re.compile('[A-Z][A-Z0-9_]{0,47}')
DECIMAL = re.compile('0|[1-9][0-9]{0,77}')
OPS = ('eq', 'ne', 'lt', 'le', 'gt', 'ge')
BOUND_OPS = ('lt', 'le')
FIELD_TYPES = ('uint', 'flag', 'address')
FACTOR_KEYS = ('field', 'diff', 'square', 'constMinusSquare')
MAX_FACTORS = 4
MEASURE_SOURCES = {
    'SUBJECT_RECEIPT_GAS_USED': set(),
    'SUBJECT_RECEIPT_STATUS': set(),
    'WORLD_ACTOR_BALANCE_AFTER': set(),
    'EVENT_DATA_WORD': {'emitter', 'topic0', 'topic1', 'word'},
    'ERC20_TRANSFER_NET': {'emitter', 'topic0', 'party'},
}


class DescriptorError(ValueError):
    def __init__(self, code, detail=''):
        super().__init__(f'{code}: {detail}' if detail else code)
        self.code = code
        self.detail = detail


def require(ok, code, detail=''):
    if not ok:
        raise DescriptorError(code, detail)


def commit(domain, value):
    return digest(domain.encode() + b'\n' + canonical(value))


# ----- Keccak-256 (Ethereum), dependency-free -------------------------------------------------------------

_RC = [0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000, 0x000000000000808B,
       0x0000000080000001, 0x8000000080008081, 0x8000000000008009, 0x000000000000008A, 0x0000000000000088,
       0x0000000080008009, 0x000000008000000A, 0x000000008000808B, 0x800000000000008B, 0x8000000000008089,
       0x8000000000008003, 0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
       0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008]
_ROT = [[0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61], [28, 55, 25, 21, 56], [27, 20, 39, 8, 14]]
_M = (1 << 64) - 1


def _rotl(v, r):
    return ((v << r) | (v >> (64 - r))) & _M if r else v


def _keccak_f(a):
    for rc in _RC:
        c = [a[x] ^ a[x + 5] ^ a[x + 10] ^ a[x + 15] ^ a[x + 20] for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rotl(c[(x + 1) % 5], 1) for x in range(5)]
        a = [a[i] ^ d[i % 5] for i in range(25)]
        b = [0] * 25
        for x in range(5):
            for y in range(5):
                b[y + 5 * ((2 * x + 3 * y) % 5)] = _rotl(a[x + 5 * y], _ROT[x][y])
        a = [b[x + 5 * y] ^ ((~b[(x + 1) % 5 + 5 * y]) & b[(x + 2) % 5 + 5 * y]) for y in range(5) for x in range(5)]
        a[0] ^= rc
    return a


def keccak256(data):
    rate = 136
    padded = bytearray(data) + b'\x01'
    padded += b'\x00' * ((-len(padded)) % rate)
    padded[-1] |= 0x80
    state = [0] * 25
    for offset in range(0, len(padded), rate):
        block = padded[offset:offset + rate]
        for i in range(rate // 8):
            state[i] ^= int.from_bytes(block[8 * i:8 * i + 8], 'little')
        state = _keccak_f(state)
    return b''.join(state[i].to_bytes(8, 'little') for i in range(4))


def _word(value):
    return '0x' + format(value, '064x')


def erc7201(namespace):
    """keccak256(abi.encode(uint256(keccak256(namespace)) - 1)) & ~0xff (ERC-7201)."""
    inner = int.from_bytes(keccak256(namespace.encode()), 'big') - 1
    return int.from_bytes(keccak256(inner.to_bytes(32, 'big')), 'big') & ~0xff


def pool_id(pool, hooks_address):
    words = [int(pool['currency0'], 16), int(pool['currency1'], 16), pool['fee'], pool['tickSpacing'] % (1 << 256),
             int(hooks_address, 16)]
    return '0x' + keccak256(b''.join(w.to_bytes(32, 'big') for w in words)).hex()


def derive_slot(derivation, pool_id_hex):
    kind = derivation.get('kind')
    if kind == 'ERC7201_MAPPING_POOL_ID':
        base = erc7201(derivation['namespace'])
        mapped = int.from_bytes(keccak256(bytes.fromhex(pool_id_hex[2:]) + base.to_bytes(32, 'big')), 'big')
        return _word((mapped + derivation['fieldOffset']) % (1 << 256))
    raise DescriptorError('DESCRIPTOR_SLOT_DERIVATION', f'unknown derivation {str(kind)[:40]}')


# ----- strict loading -------------------------------------------------------------------------------------

def _keys(value, required, optional=(), code='DESCRIPTOR_SCHEMA', where=''):
    require(type(value) is dict, code, f'{where}: object required')
    present = set(value)
    require(set(required) <= present and present <= set(required) | set(optional), code,
            f'{where}: keys {sorted(present)} not {sorted(required)} (+{sorted(optional)})')


def _int(value, code='DESCRIPTOR_SCHEMA', where='', low=0, high=MAX_SAFE):
    require(type(value) is int and low <= value <= high, code, f'{where}: integer {low}..{high} required')
    return value


def _str(value, pattern=None, code='DESCRIPTOR_SCHEMA', where=''):
    require(type(value) is str and (pattern is None or pattern.fullmatch(value)), code, f'{where}: string required')
    return value


def _list(value, code='DESCRIPTOR_SCHEMA', where='', empty=True):
    require(type(value) is list and (empty or value), code, f'{where}: list required')
    return value


def _decimal(value, where):
    _str(value, DECIMAL, 'DESCRIPTOR_SCHEMA', where)
    return int(value)


def parse(raw):
    """Canonical ASCII bytes -> validated descriptor dict. Encoding first, then shape, then semantics."""
    require(type(raw) is bytes and 0 < len(raw) <= MAX_DESCRIPTOR_BYTES, 'DESCRIPTOR_ENCODING', 'size')
    require(raw.isascii(), 'DESCRIPTOR_ENCODING', 'ASCII only')
    try:
        value = strict(raw)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise DescriptorError('DESCRIPTOR_ENCODING', str(error)[:120]) from error
    require(canonical(value) + b'\n' == raw, 'DESCRIPTOR_ENCODING', 'canonical JSON with one trailing newline required')
    validate(value)
    return value


def descriptor_sha256(raw):
    return digest(raw)


def _operand(value, where, fields, params, allow_param):
    _keys(value, (), ('const', 'field', 'param'), where=where)
    require(len(value) == 1, 'DESCRIPTOR_SCHEMA', f'{where}: exactly one of const, field, param')
    (key, ref), = value.items()
    if key == 'const':
        _decimal(ref, where)
    elif key == 'field':
        require(type(ref) is str and ref in fields, 'DESCRIPTOR_PREDICATE', f'{where}: unknown field {str(ref)[:40]}')
    else:
        require(allow_param and type(ref) is str and params.get(ref) == 'uint', 'DESCRIPTOR_PREDICATE',
                f'{where}: unknown or non-integer parameter {str(ref)[:40]}')


def _predicate(value, where, fields, params):
    # Unknown keys are a shape error everywhere (as Go's strict decoding); the closed choice is a predicate error.
    require(type(value) is dict and set(value) <= {'compare', 'productBound'}, 'DESCRIPTOR_SCHEMA', f'{where}: unknown predicate key')
    require(len(value) == 1, 'DESCRIPTOR_PREDICATE', f'{where}: exactly one of compare, productBound')
    if 'compare' in value:
        c = value['compare']
        _keys(c, ('left', 'op', 'right'), where=where)
        require(c['op'] in OPS, 'DESCRIPTOR_PREDICATE', f'{where}: unknown op {str(c["op"])[:20]}')
        _operand(c['left'], where + '.left', fields, params, True)
        _operand(c['right'], where + '.right', fields, params, True)
        return
    b = value['productBound']
    _keys(b, ('bound', 'factors', 'op'), where=where)
    require(b['op'] in BOUND_OPS, 'DESCRIPTOR_PREDICATE', f'{where}: bound op')
    _decimal(b['bound'], where + '.bound')
    factors = _list(b['factors'], 'DESCRIPTOR_PREDICATE', where + '.factors', empty=False)
    require(len(factors) <= MAX_FACTORS, 'DESCRIPTOR_PREDICATE', f'{where}: at most {MAX_FACTORS} factors')
    for i, f in enumerate(factors):
        w = f'{where}.factors[{i}]'
        require(type(f) is dict and set(f) <= set(FACTOR_KEYS), 'DESCRIPTOR_SCHEMA', f'{w}: unknown factor key')
        require(len(f) == 1, 'DESCRIPTOR_PREDICATE', f'{w}: exactly one factor form')
        (key, ref), = f.items()
        if key in ('field', 'square'):
            require(type(ref) is str and ref in fields, 'DESCRIPTOR_PREDICATE', f'{w}: unknown field')
        elif key == 'diff':
            require(type(ref) is list and len(ref) == 2 and all(type(r) is str and r in fields for r in ref), 'DESCRIPTOR_PREDICATE', f'{w}: diff')
        else:
            require(type(ref) is list and len(ref) == 2 and type(ref[0]) is str and DECIMAL.fullmatch(ref[0])
                    and type(ref[1]) is str and ref[1] in fields, 'DESCRIPTOR_PREDICATE', f'{w}: constMinusSquare')


def _manifest_commitment(manifest):
    return commit(RELEASE_DOMAIN, manifest)


def validate(d):
    """Semantic validation of a parsed descriptor. Raises DescriptorError with a specific code."""
    _keys(d, ('action', 'chain', 'configurationTarget', 'contracts', 'fields', 'interventions', 'measures', 'originalState',
              'pool', 'profileId', 'provenance', 'release', 'revision', 'schema', 'setup', 'targets', 'witness'), where='descriptor')
    require(d['schema'] == SCHEMA, 'DESCRIPTOR_VERSION', f'unsupported schema {str(d["schema"])[:60]}')
    _str(d['profileId'], re.compile('[a-z][a-z0-9-]{0,47}'), where='profileId')
    _int(d['revision'], where='revision', low=1)
    c = d['chain']
    _keys(c, ('arbosVersion', 'chainConfigSha256', 'chainId', 'engineFamily'), where='chain')
    _int(c['chainId'], where='chain.chainId', low=1)
    _int(c['arbosVersion'], where='chain.arbosVersion', low=1)
    _str(c['chainConfigSha256'], SHA, where='chain.chainConfigSha256')
    require(c['engineFamily'] == 'NITRO', 'DESCRIPTOR_CHAIN', 'only the NITRO engine family is supported')
    r = d['release']
    _keys(r, ('manifest', 'manifestCommitment'), where='release')
    require(type(r['manifest']) is dict and type(r['manifest'].get('contracts')) is list, 'DESCRIPTOR_SCHEMA', 'release.manifest')
    _str(r['manifestCommitment'], SHA, where='release.manifestCommitment')
    require(_manifest_commitment(r['manifest']) == r['manifestCommitment'], 'DESCRIPTOR_RELEASE', 'manifest commitment mismatch')
    manifest = {(m.get('role'), m.get('address')): m.get('runtimeHash') for m in r['manifest']['contracts'] if type(m) is dict}
    contracts = {}
    for i, k in enumerate(_list(d['contracts'], where='contracts', empty=False)):
        w = f'contracts[{i}]'
        require(type(k) is dict and type(k.get('requirement')) is str, 'DESCRIPTOR_SCHEMA', w)
        if k['requirement'] == 'CODE_HASH_EQUALS':
            _keys(k, ('address', 'name', 'releaseRole', 'requirement', 'runtimeCodeHash'), where=w)
            _str(k['runtimeCodeHash'], HEX32, where=w + '.runtimeCodeHash')
            require(k['runtimeCodeHash'] != _word(0), 'DESCRIPTOR_CONTRACT', w + ': zero code hash')
            require(manifest.get((k['releaseRole'], k['address'])) == k['runtimeCodeHash'], 'DESCRIPTOR_CONTRACT',
                    w + ': address and code hash must be the release manifest entry of that role')
        elif k['requirement'] == 'CODE_PRESENT':
            _keys(k, ('address', 'name', 'requirement'), where=w)
        else:
            raise DescriptorError('DESCRIPTOR_CONTRACT', w + ': unknown requirement')
        _str(k['name'], NAME, where=w + '.name')
        _str(k['address'], ADDRESS, where=w + '.address')
        require(k['name'] not in contracts and k['address'] != '0x' + '0' * 40, 'DESCRIPTOR_CONTRACT', w + ': duplicate or zero')
        contracts[k['name']] = k
    require(len({k['address'] for k in contracts.values()}) == len(contracts), 'DESCRIPTOR_CONTRACT', 'duplicate address')
    p = d['pool']
    _keys(p, ('currency0', 'currency1', 'fee', 'hooksContract', 'poolId', 'tickSpacing'), where='pool')
    _str(p['currency0'], ADDRESS, where='pool.currency0')
    _str(p['currency1'], ADDRESS, where='pool.currency1')
    _int(p['fee'], where='pool.fee', high=(1 << 24) - 1)
    require(type(p['tickSpacing']) is int and -(1 << 23) <= p['tickSpacing'] < (1 << 23), 'DESCRIPTOR_SCHEMA', 'pool.tickSpacing')
    _str(p['poolId'], HEX32, where='pool.poolId')
    hooks = contracts.get(p['hooksContract'])
    require(hooks is not None and hooks['requirement'] == 'CODE_HASH_EQUALS', 'DESCRIPTOR_CONTRACT', 'pool.hooksContract must be code-pinned')
    require(pool_id(p, hooks['address']) == p['poolId'], 'DESCRIPTOR_POOL_ID', 'poolId does not recompute from the pool key')
    targets = {}
    for i, t in enumerate(_list(d['targets'], where='targets', empty=False)):
        w = f'targets[{i}]'
        _keys(t, ('contract', 'name', 'slot', 'slotDerivation', 'words'), where=w)
        _str(t['name'], NAME, where=w + '.name')
        require(t['name'] not in targets, 'DESCRIPTOR_TARGET', w + ': duplicate name')
        k = contracts.get(t['contract'])
        require(k is not None and k['requirement'] == 'CODE_HASH_EQUALS', 'DESCRIPTOR_TARGET', w + ': target contract must be code-pinned')
        _int(t['words'], where=w + '.words', low=1, high=8)
        _str(t['slot'], HEX32, where=w + '.slot')
        sd = t['slotDerivation']
        require(type(sd) is dict and type(sd.get('kind')) is str, 'DESCRIPTOR_SCHEMA', w + '.slotDerivation')
        if sd['kind'] == 'ERC7201_MAPPING_POOL_ID':
            _keys(sd, ('fieldOffset', 'kind', 'namespace'), where=w + '.slotDerivation')
            _str(sd['namespace'], re.compile('[a-z][a-z0-9.]{0,63}'), where=w + '.namespace')
            _int(sd['fieldOffset'], where=w + '.fieldOffset', high=255)
            require(derive_slot(sd, p['poolId']) == t['slot'], 'DESCRIPTOR_SLOT_DERIVATION', w + ': declared slot does not recompute')
        elif sd['kind'] == 'FIXED':
            _keys(sd, ('kind',), where=w + '.slotDerivation')
        else:
            raise DescriptorError('DESCRIPTOR_SLOT_DERIVATION', w + ': unknown derivation')
        require(int(t['slot'], 16) + t['words'] <= 1 << 256, 'DESCRIPTOR_TARGET', w + ': slot range')
        targets[t['name']] = t
    slots = [(targets[n]['contract'], int(targets[n]['slot'], 16) + i) for n in targets for i in range(targets[n]['words'])]
    require(len(set(slots)) == len(slots), 'DESCRIPTOR_TARGET', 'targets overlap')
    require(d['configurationTarget'] in targets, 'DESCRIPTOR_TARGET', 'configurationTarget')
    fields = {}
    occupied = {}
    for i, f in enumerate(_list(d['fields'], where='fields', empty=False)):
        w = f'fields[{i}]'
        _keys(f, ('name', 'offset', 'semanticsSource', 'target', 'type', 'unit', 'width', 'word'), where=w)
        _str(f['name'], NAME, where=w + '.name')
        _str(f['unit'], re.compile('[a-z][a-z0-9]{0,15}'), where=w + '.unit')
        _str(f['semanticsSource'], re.compile('[A-Za-z0-9_.:/@+-]{1,120}'), where=w + '.semanticsSource')
        require(f['name'] not in fields, 'DESCRIPTOR_FIELD_LAYOUT', w + ': duplicate name')
        require(f['target'] in targets, 'DESCRIPTOR_FIELD_LAYOUT', w + ': unknown target')
        require(f['type'] in FIELD_TYPES, 'DESCRIPTOR_FIELD_LAYOUT', w + ': unknown type')
        _int(f['word'], where=w + '.word', high=7)
        _int(f['offset'], where=w + '.offset', high=255)
        _int(f['width'], where=w + '.width', high=256)
        require(f['word'] < targets[f['target']]['words'], 'DESCRIPTOR_FIELD_LAYOUT', w + ': word outside target')
        require(1 <= f['width'] and f['offset'] + f['width'] <= 256, 'DESCRIPTOR_FIELD_LAYOUT', w + ': bit range')
        require(f['type'] != 'flag' or f['width'] == 1, 'DESCRIPTOR_FIELD_LAYOUT', w + ': a flag is one bit')
        require(f['type'] != 'address' or f['width'] == 160, 'DESCRIPTOR_FIELD_LAYOUT', w + ': an address is 160 bits')
        mask = ((1 << f['width']) - 1) << f['offset']
        key = (f['target'], f['word'])
        require(occupied.get(key, 0) & mask == 0, 'DESCRIPTOR_FIELD_LAYOUT', w + ': overlaps another field')
        occupied[key] = occupied.get(key, 0) | mask
        fields[f['name']] = f
    o = d['originalState']
    _keys(o, ('policy', 'words'), where='originalState')
    require(o['policy'] == 'EXACT_WORDS', 'DESCRIPTOR_ORIGINAL_STATE', 'only EXACT_WORDS is supported')
    seen = set()
    for i, ow in enumerate(_list(o['words'], where='originalState.words', empty=False)):
        w = f'originalState.words[{i}]'
        _keys(ow, ('target', 'value', 'word'), where=w)
        require(ow['target'] in targets, 'DESCRIPTOR_ORIGINAL_STATE', w + ': unknown target')
        _int(ow['word'], where=w + '.word', high=7)
        _str(ow['value'], HEX32, where=w + '.value')
        require(ow['word'] < targets[ow['target']]['words'] and (ow['target'], ow['word']) not in seen, 'DESCRIPTOR_ORIGINAL_STATE', w)
        seen.add((ow['target'], ow['word']))
    require(seen == {(n, i) for n in targets for i in range(targets[n]['words'])}, 'DESCRIPTOR_ORIGINAL_STATE',
            'EXACT_WORDS must pin every word of every target')
    kinds = {}
    names = []
    for i, k in enumerate(_list(d['interventions'], where='interventions', empty=False)):
        w = f'interventions[{i}]'
        _keys(k, ('assign', 'conflictsWith', 'ensures', 'kind', 'parameters', 'requires'), where=w)
        _str(k['kind'], KIND_NAME, where=w + '.kind')
        require(k['kind'] not in kinds, 'DESCRIPTOR_KIND', w + ': duplicate kind')
        names.append(k['kind'])
        params = {}
        for j, prm in enumerate(_list(k['parameters'], where=w + '.parameters', empty=False)):
            pw = f'{w}.parameters[{j}]'
            require(type(prm) is dict and type(prm.get('type')) is str, 'DESCRIPTOR_SCHEMA', pw)
            if prm['type'] == 'uint':
                _keys(prm, ('max', 'min', 'name', 'type'), where=pw)
                _int(prm['min'], where=pw + '.min')
                _int(prm['max'], where=pw + '.max')
                require(prm['min'] <= prm['max'], 'DESCRIPTOR_KIND', pw + ': min above max')
            elif prm['type'] == 'enum':
                _keys(prm, ('name', 'type', 'values'), where=pw)
                values = _list(prm['values'], where=pw + '.values', empty=False)
                require(all(type(v) is str and KIND_NAME.fullmatch(v) for v in values) and len(set(values)) == len(values),
                        'DESCRIPTOR_KIND', pw + ': enum values')
            else:
                raise DescriptorError('DESCRIPTOR_KIND', pw + ': unknown parameter type')
            _str(prm['name'], NAME, where=pw + '.name')
            require(prm['name'] not in params, 'DESCRIPTOR_KIND', pw + ': duplicate parameter')
            params[prm['name']] = prm['type']
        for j, pred in enumerate(_list(k['requires'], where=w + '.requires')):
            _predicate(pred, f'{w}.requires[{j}]', fields, params)
        for j, pred in enumerate(_list(k['ensures'], where=w + '.ensures')):
            _predicate(pred, f'{w}.ensures[{j}]', fields, params)
        assigned = set()
        for j, a in enumerate(_list(k['assign'], where=w + '.assign', empty=False)):
            aw = f'{w}.assign[{j}]'
            _keys(a, ('field', 'value'), where=aw)
            require(a['field'] in fields, 'DESCRIPTOR_KIND', aw + ': unknown field')
            require(a['field'] not in assigned, 'DESCRIPTOR_KIND', aw + ': field assigned twice')
            require(fields[a['field']]['type'] != 'address', 'DESCRIPTOR_KIND', aw + ': address fields are not assignable')
            assigned.add(a['field'])
            _operand(a['value'], aw + '.value', fields, params, True)
        for c2 in _list(k['conflictsWith'], where=w + '.conflictsWith'):
            require(type(c2) is str and c2 != k['kind'], 'DESCRIPTOR_KIND', w + ': conflict')
        kinds[k['kind']] = k
    require(names == sorted(names), 'DESCRIPTOR_KIND', 'kinds must be sorted by name')
    for k in kinds.values():
        require(all(c2 in kinds for c2 in k['conflictsWith']), 'DESCRIPTOR_KIND', f'{k["kind"]}: unknown conflict')
        require(k['conflictsWith'] == sorted(set(k['conflictsWith'])), 'DESCRIPTOR_KIND', f'{k["kind"]}: conflicts sorted and unique')
        require(all(k['kind'] in kinds[c2]['conflictsWith'] for c2 in k['conflictsWith']), 'DESCRIPTOR_KIND', f'{k["kind"]}: conflicts must be symmetric')
    a = d['action']
    _keys(a, ('abi', 'amountInWei', 'campaigns', 'count', 'engagement', 'function', 'gas', 'minimumOutputBaseUnits', 'router',
              'sqrtPriceLimitX96', 'transactionType', 'type', 'zeroForOne'), where='action')
    _int(a['count'], where='action.count')
    require(type(a['zeroForOne']) is bool, 'DESCRIPTOR_SCHEMA', 'action.zeroForOne')
    require(a['type'] == 'HOOKR_ROUTER_EXACT_INPUT_BUY_V1' and a['transactionType'] == 'LEGACY' and a['function'] == 'swap'
            and a['count'] == 1 and a['zeroForOne'] is True and a['campaigns'] == [], 'DESCRIPTOR_ACTION', 'unsupported action form')
    require(a['router'] in contracts and contracts[a['router']]['requirement'] == 'CODE_HASH_EQUALS', 'DESCRIPTOR_ACTION', 'router must be code-pinned')
    require(type(a['abi']) is list and a['abi'], 'DESCRIPTOR_ACTION', 'abi')
    for key in ('amountInWei', 'minimumOutputBaseUnits', 'sqrtPriceLimitX96'):
        _decimal(a[key], 'action.' + key)
    _str(a['engagement'], ADDRESS, where='action.engagement')
    gas = _list(a['gas'], where='action.gas', empty=False)
    require(all(type(g) is int and 0 < g <= MAX_SAFE for g in gas) and gas == sorted(set(gas)), 'DESCRIPTOR_ACTION', 'gas options')
    s = d['setup']
    _keys(s, ('actor', 'fundingWei', 'nonce', 'requireOriginalAbsence'), where='setup')
    _keys(s['actor'], ('kind', 'seed'), where='setup.actor')
    require(s['actor']['kind'] == 'PUBLIC_SIMULATION_SIGNER_V1' and type(s['actor']['seed']) is str and s['actor']['seed'],
            'DESCRIPTOR_SETUP', 'actor')
    _decimal(s['fundingWei'], 'setup.fundingWei')
    _int(s['nonce'], where='setup.nonce')
    require(type(s['requireOriginalAbsence']) is bool and type(s['actor']['kind']) is str, 'DESCRIPTOR_SCHEMA', 'setup types')
    require(s['nonce'] == 0 and s['requireOriginalAbsence'] is True, 'DESCRIPTOR_SETUP', 'fresh absent actor required')
    measure_names = set()
    for i, m in enumerate(_list(d['measures'], where='measures', empty=False)):
        w = f'measures[{i}]'
        require(type(m) is dict and m.get('source') in MEASURE_SOURCES, 'DESCRIPTOR_MEASURE', w + ': unknown source')
        _keys(m, {'name', 'source'} | MEASURE_SOURCES[m['source']], where=w)
        _str(m['name'], NAME, where=w + '.name')
        require(m['name'] not in measure_names, 'DESCRIPTOR_MEASURE', w + ': duplicate')
        measure_names.add(m['name'])
        if 'emitter' in m:
            require(m['emitter'] in contracts, 'DESCRIPTOR_MEASURE', w + ': emitter')
            _str(m['topic0'], HEX32, where=w + '.topic0')
        if 'topic1' in m:
            require(m['topic1'] == 'POOL_ID', 'DESCRIPTOR_MEASURE', w + ': topic1')
            _int(m['word'], where=w + '.word', high=31)
        if 'party' in m:
            require(m['party'] == 'ACTOR', 'DESCRIPTOR_MEASURE', w + ': party')
    wt = d['witness']
    _keys(wt, ('readHints', 'systemSubjects', 'targetWords'), where='witness')
    require(wt['systemSubjects'] == 'NITRO_ARBOS61_SCENARIO_SYSTEM_V1' and wt['targetWords'] == 'ALL_DECLARED_TARGET_WORDS',
            'DESCRIPTOR_WITNESS', 'unsupported witness declaration')
    for i, h in enumerate(_list(wt['readHints'], where='witness.readHints')):
        _keys(h, ('path', 'sha256'), where=f'witness.readHints[{i}]')
        _str(h['path'], re.compile('[a-z_][a-z0-9_./-]{0,159}'), where='witness.path')
        require('..' not in h['path'].split('/'), 'DESCRIPTOR_WITNESS', 'path traversal')
        _str(h['sha256'], SHA, where='witness.sha256')
    pv = d['provenance']
    _keys(pv, ('contractSources', 'derivations', 'sources'), where='provenance')
    _str(pv['contractSources'], where='provenance.contractSources')
    for i, src in enumerate(_list(pv['sources'], where='provenance.sources', empty=False)):
        _keys(src, ('kind', 'name', 'ref', 'sha256'), where=f'provenance.sources[{i}]')
        _str(src['sha256'], SHA, where='provenance.sha256')
    for i, dv in enumerate(_list(pv['derivations'], where='provenance.derivations')):
        _keys(dv, ('method', 'result', 'subject'), where=f'provenance.derivations[{i}]')
    return d


# ----- catalogue: review status is separate from the descriptor ----------------------------------------------

def load_accepted(profile_id, purpose, *, directory=None):
    """The only loader for workflow use: a catalogue entry, its exact descriptor bytes, and a review status that
    admits the purpose. User-supplied descriptor files are never loaded here."""
    require(purpose in PURPOSES, 'PROFILE_REVIEW_INSUFFICIENT', 'unknown purpose')
    directory = directory or DESCRIPTOR_DIR
    cat = strict((Path(directory) / 'CATALOGUE.json').read_bytes())
    _keys(cat, ('entries', 'schema'), code='PROFILE_CATALOGUE', where='catalogue')
    require(cat['schema'] == CATALOGUE_SCHEMA, 'PROFILE_CATALOGUE', 'schema')
    entries = [e for e in cat['entries'] if type(e) is dict and e.get('profileId') == profile_id]
    require(len(entries) == 1, 'PROFILE_NOT_IN_CATALOGUE', profile_id[:48] if type(profile_id) is str else '')
    e = entries[0]
    _keys(e, ('descriptorFile', 'descriptorSha256', 'kinds', 'profileId', 'review', 'revision'), code='PROFILE_CATALOGUE', where='entry')
    require(re.fullmatch('[a-z0-9-]+\\.json', e['descriptorFile']) is not None, 'PROFILE_CATALOGUE', 'file name')
    raw = (Path(directory) / e['descriptorFile']).read_bytes()
    require(digest(raw) == e['descriptorSha256'], 'PROFILE_DESCRIPTOR_HASH', 'descriptor bytes differ from the reviewed hash')
    d = parse(raw)
    require(d['profileId'] == profile_id and d['revision'] == e['revision'], 'PROFILE_CATALOGUE', 'identity')
    allowed = e['review'].get('admits', []) if type(e['review']) is dict else []
    require(purpose in allowed, 'PROFILE_REVIEW_INSUFFICIENT', f'{profile_id} is not reviewed for {purpose}')
    require(set(e['kinds']) == {k['kind'] for k in d['interventions']}, 'PROFILE_CATALOGUE', 'kind review statuses')
    require(all(s in KIND_REVIEW_PURPOSES for s in e['kinds'].values()), 'PROFILE_CATALOGUE', 'unknown kind review status')
    return d, raw, copy.deepcopy(e)


# Closed vocabulary of per-kind review statuses and the purposes each admits (mirror of Go kindReviewPurposes).
# A selected kind admits a purpose only if its status lists it; the descriptor review must admit it as well.
KIND_REVIEW_PURPOSES = {'LEGACY_EQUIVALENT_SDK04': ('OFFLINE_PREPARATION', 'NATIVE_EXECUTION'),
                        'OFFLINE_PROBE_BIND_RULES_ONLY': ('OFFLINE_PREPARATION',)}


def require_kind_review(entry, items, purpose):
    for item in items:
        status = entry['kinds'].get(item.get('kind')) if type(item) is dict else None
        require(purpose in KIND_REVIEW_PURPOSES.get(status, ()), 'PROFILE_KIND_REVIEW_INSUFFICIENT',
                f"{item.get('kind') if type(item) is dict else item} is not reviewed for {purpose}")


# ----- interpretation -----------------------------------------------------------------------------------------

def _index(d):
    targets = {t['name']: t for t in d['targets']}
    fields = {f['name']: f for f in d['fields']}
    kinds = {k['kind']: k for k in d['interventions']}
    contracts = {c['name']: c for c in d['contracts']}
    return targets, fields, kinds, contracts


def _mask(f):
    return ((1 << f['width']) - 1) << f['offset']


def _get(words, f):
    return (words[f['target']][f['word']] >> f['offset']) & ((1 << f['width']) - 1)


def decode_fields(d, words):
    _, fields, _, _ = _index(d)
    return {name: _get(words, f) for name, f in fields.items()}


def _value(operand, words, fields, params):
    (key, ref), = operand.items()
    if key == 'const':
        return int(ref)
    if key == 'field':
        return _get(words, fields[ref])
    return params[ref]


def _holds(pred, words, fields, params):
    if 'compare' in pred:
        c = pred['compare']
        a, b = _value(c['left'], words, fields, params), _value(c['right'], words, fields, params)
        return dict(eq=a == b, ne=a != b, lt=a < b, le=a <= b, gt=a > b, ge=a >= b)[c['op']]
    b = pred['productBound']
    product = 1
    for f in b['factors']:
        (key, ref), = f.items()
        if key == 'field':
            v = _get(words, fields[ref])
        elif key == 'square':
            v = _get(words, fields[ref]) ** 2
        elif key == 'diff':
            v = _get(words, fields[ref[0]]) - _get(words, fields[ref[1]])
        else:
            v = int(ref[0]) - _get(words, fields[ref[1]]) ** 2
        require(v >= 0, 'PROFILE_NEGATIVE_FACTOR', 'a product-bound factor is negative')
        product *= v
    bound = int(b['bound'])
    return product < bound if b['op'] == 'lt' else product <= bound


def canonical_interventions(d, items):
    """Validate shape and return the set sorted by kind; each kind at most once, no declared conflicts."""
    _, _, kinds, _ = _index(d)
    require(type(items) in (list, tuple) and 1 <= len(items) <= len(kinds), 'PROFILE_INTERVENTION_COUNT', 'intervention count')
    for item in items:
        require(type(item) is dict and set(item) == {'kind', 'parameters'} and type(item.get('kind')) is str
                and type(item.get('parameters')) is dict, 'PROFILE_INTERVENTION_SHAPE', 'each intervention is {kind, parameters}')
        require(item['kind'] in kinds, 'PROFILE_UNKNOWN_INTERVENTION', item['kind'][:48])
    names = [i['kind'] for i in items]
    require(len(set(names)) == len(names), 'PROFILE_DUPLICATE_KIND', 'each kind at most once')
    for name in names:
        require(not set(kinds[name]['conflictsWith']) & set(names), 'PROFILE_KIND_CONFLICT', name)
    for item in items:
        declared = {p['name']: p for p in kinds[item['kind']]['parameters']}
        require(set(item['parameters']) == set(declared), 'PROFILE_PARAMETER', f'{item["kind"]}: parameters {sorted(declared)} required')
        for name, value in item['parameters'].items():
            p = declared[name]
            if p['type'] == 'uint':
                require(type(value) is int and p['min'] <= value <= p['max'], 'PROFILE_PARAMETER', f'{item["kind"]}.{name} out of range')
            else:
                require(type(value) is str and value in p['values'], 'PROFILE_PARAMETER', f'{item["kind"]}.{name} not admitted')
    return [copy.deepcopy(i) for i in sorted(items, key=lambda i: i['kind'])]


def originals_from_descriptor(d):
    """The EXACT_WORDS originals as {target: [int words]}; admission must authenticate them against the witness."""
    targets, _, _, _ = _index(d)
    words = {n: [None] * t['words'] for n, t in targets.items()}
    for w in d['originalState']['words']:
        words[w['target']][w['word']] = int(w['value'], 16)
    return words


def compose(d, items, originals):
    """Typed interventions -> masked writes on the authenticated original words. Same order of checks as Go."""
    targets, fields, kinds, contracts = _index(d)
    require(type(originals) is dict and set(originals) == set(targets)
            and all(type(originals[n]) is list and len(originals[n]) == targets[n]['words']
                    and all(type(v) is int and 0 <= v < 1 << 256 for v in originals[n]) for n in targets),
            'PROFILE_ORIGINAL_STATE_UNAVAILABLE', 'every target word must be supplied')
    for w in d['originalState']['words']:
        require(originals[w['target']][w['word']] == int(w['value'], 16), 'PROFILE_ORIGINAL_WORD',
                f'{w["target"]}[{w["word"]}] is not the reviewed original')
    canon = canonical_interventions(d, items)
    original = {n: list(v) for n, v in originals.items()}
    result = {n: list(v) for n, v in originals.items()}
    used = {n: [0] * targets[n]['words'] for n in targets}
    applied = []
    for item in canon:
        k = kinds[item['kind']]
        for pred in k['requires']:
            require(_holds(pred, original, fields, item['parameters']), 'PROFILE_ORIGINAL_PRECONDITION', item['kind'])
        for a in k['assign']:
            f = fields[a['field']]
            value = _value(a['value'], original, fields, item['parameters'])
            require(0 <= value < (1 << f['width']), 'PROFILE_VALUE_WIDTH', a['field'])
            m = _mask(f)
            require(used[f['target']][f['word']] & m == 0, 'PROFILE_MASK_CONFLICT', a['field'])
            used[f['target']][f['word']] |= m
            w = result[f['target']][f['word']]
            result[f['target']][f['word']] = (w & ~m) | (value << f['offset'])
            applied.append((f, value))
    for item in canon:
        for pred in kinds[item['kind']]['ensures']:
            require(_holds(pred, result, fields, item['parameters']), 'PROFILE_INVARIANT', item['kind'])
    for n in targets:
        for i in range(targets[n]['words']):
            require((result[n][i] ^ original[n][i]) & ~used[n][i] == 0, 'PROFILE_NON_TARGET_BITS', f'{n}[{i}]')
    for f, value in applied:
        require(_get(result, f) == value, 'PROFILE_FIELD_VALUE', f['name'])
    writes = []
    for n, t in targets.items():
        address = contracts[t['contract']]['address']
        for i in range(t['words']):
            if used[n][i]:
                require(result[n][i] != original[n][i], 'PROFILE_NO_EFFECT', f'{n}[{i}]')
                writes.append(dict(address=address, after=_word(result[n][i]), before=_word(original[n][i]),
                                   slot=_word(int(t['slot'], 16) + i), target=n, word=i))
    return dict(interventions=canon, writes=writes, words={n: [_word(v) for v in ws] for n, ws in result.items()},
                fields=dict(baseline=decode_fields(d, original), variant=decode_fields(d, result)))


class StateReader:
    """Interface of authenticated checkpoint state. Implementations return None for anything the witness cannot
    answer; None is never read as zero, empty code or absence."""

    def code_hash(self, address):
        raise NotImplementedError

    def has_code(self, address):
        raise NotImplementedError

    def storage(self, address, slot):
        raise NotImplementedError


def authenticate(d, reader):
    """Check contract identities and read every target word through the reader before any composition."""
    targets, _, _, contracts = _index(d)
    for c in contracts.values():
        if c['requirement'] == 'CODE_HASH_EQUALS':
            h = reader.code_hash(c['address'])
            require(h is not None, 'PROFILE_ORIGINAL_STATE_UNAVAILABLE', c['name'] + ' code')
            require(h == c['runtimeCodeHash'], 'PROFILE_CODE_IDENTITY', c['name'])
        else:
            present = reader.has_code(c['address'])
            require(present is not None, 'PROFILE_ORIGINAL_STATE_UNAVAILABLE', c['name'] + ' code')
            require(present is True, 'PROFILE_TOKEN_CODE_REQUIRED', c['name'])
    words = {}
    for n, t in targets.items():
        address = contracts[t['contract']]['address']
        row = []
        for i in range(t['words']):
            v = reader.storage(address, _word(int(t['slot'], 16) + i))
            require(v is not None, 'PROFILE_ORIGINAL_STATE_UNAVAILABLE', f'{n}[{i}]')
            row.append(int(v, 16))
        words[n] = row
    return words


def check_writes(d, writes):
    """Envelope check of an externally supplied write list: only declared target words, storage only."""
    targets, _, _, contracts = _index(d)
    allowed = {(contracts[t['contract']]['address'], _word(int(t['slot'], 16) + i)): (n, i)
               for n, t in targets.items() for i in range(t['words'])}
    require(type(writes) is list, 'PROFILE_WRITE_TARGET', 'writes')
    for w in writes:
        require(type(w) is dict and set(w) == {'address', 'after', 'before', 'slot', 'target', 'word'}, 'PROFILE_WRITE_TARGET', 'storage writes only')
        require(allowed.get((w['address'], w['slot'])) == (w['target'], w['word']), 'PROFILE_WRITE_TARGET', 'undeclared account or slot')
    return writes


def apply_writes(d, state, writes, label):
    """Authenticate every original word, then write only in the variant world. `state` has get/set_storage only."""
    require(label in ('SCENARIO_BASELINE', 'SCENARIO_VARIANT'), 'PROFILE_WORLD', 'unknown world')
    check_writes(d, writes)
    for w in writes:
        require(state.get_storage(w['address'], w['slot']) == w['before'], 'PROFILE_ORIGINAL_WORD_CHANGED', w['target'])
    if label == 'SCENARIO_VARIANT':
        for w in writes:
            state.set_storage(w['address'], w['slot'], w['after'])
    return [dict(w, after=w['after'] if label == 'SCENARIO_VARIANT' else w['before']) for w in writes]


# ----- legacy equivalence helpers ------------------------------------------------------------------------------

def legacy_items(items):
    """SDK 0.4 typed interventions -> descriptor interventions (same kinds, parameters moved under `parameters`)."""
    out = []
    for i in items:
        params = {k: v for k, v in i.items() if k != 'kind'}
        out.append(dict(kind=i['kind'], parameters=params))
    return out


def legacy_profile(d):
    """The SDK 0.4 profile.json value this descriptor reproduces (for G1)."""
    targets, fields, _, contracts = _index(d)
    originals = originals_from_descriptor(d)
    rules = targets['rulesConfig']
    root = targets['rootRecord']
    p = d['pool']
    return {
        'schema': 'rhook/hookr-scenario-profile/0.1',
        'manifest': copy.deepcopy(d['release']['manifest']),
        'poolKey': dict(currency0=p['currency0'], currency1=p['currency1'], fee=p['fee'], tickSpacing=p['tickSpacing'],
                        hooks=contracts[p['hooksContract']]['address']),
        'poolId': p['poolId'],
        'rootRecordSlot': root['slot'],
        'rulesNamespace': _word(erc7201(rules['slotDerivation']['namespace'])),
        'configSlot': rules['slot'],
        'swapAbi': copy.deepcopy(d['action']['abi']),
        'baselineConfigWords': [_word(v) for v in originals['rulesConfig']],
        'rootCapsWord': _word(originals['rootRecord'][1]),
        'baseLpFeePips': _get(originals, fields['rootBaseLpFeePips']),
    }


# ----- prepared-input binding (rhook/hookr-profile-overlay/0.1) ---------------------------------------------------

def _transform(spec_body, d, raw, canon, c):
    targets, _, _, contracts = _index(d)
    body = dict(schema=SPEC_DOMAIN + '/transform',
                descriptor=dict(profileId=d['profileId'], revision=d['revision'], sha256=digest(raw)),
                originalStateRoot=spec_body['checkpoint']['stateRoot'], poolId=d['pool']['poolId'],
                codeHashes={n: k['runtimeCodeHash'] for n, k in sorted(contracts.items()) if k['requirement'] == 'CODE_HASH_EQUALS'},
                interventions=canon, writes=c['writes'])
    return dict(body, interventionCommitment=commit(SPEC_DOMAIN + '/transform', body))


def _intent(d, raw, pool, canon):
    return dict(schema=SPEC_DOMAIN + '/intent', poolId=pool, profile=dict(profileId=d['profileId'], sha256=digest(raw)), interventions=canon)


def capsule(spec_body, d, raw, canon):
    return commit(SPEC_DOMAIN + '/checkpoint', dict(checkpoint=spec_body['checkpoint'], intent=_intent(d, raw, spec_body['poolId'], canon)))


def build_spec(source, raw, items, engine):
    """Prepared input from a session source (the LP100 scenario input), bound to the descriptor SHA-256."""
    d = parse(raw)
    require(type(source) is dict and source.get('poolId') == d['pool']['poolId'] and source.get('checkpoint', {}).get('chainId') == d['chain']['chainId'],
            'PROFILE_SPEC_BINDING', 'source pool or chain differs from the descriptor')
    require(type(engine) is dict and set(engine) == {'binarySha256', 'policySha256', 'sourceSha256'}, 'PROFILE_SPEC_BINDING', 'engine identity')
    originals = originals_from_descriptor(d)
    canon = canonical_interventions(d, items)
    c = compose(d, canon, originals)
    s = copy.deepcopy(source)
    s.pop('scenarioCommitment', None)
    for key in ('configOverlay', 'intervention'):
        s.pop(key, None)
    s['schema'] = SPEC_DOMAIN
    s['engine'] = copy.deepcopy(engine)
    s['profileOverlay'] = _transform(s, d, raw, canon, c)
    s['origin'] = dict(kind=ORIGIN_KIND, capsuleId=capsule(s, d, raw, canon))
    target = d['configurationTarget']
    s['configurations'] = dict(baseline=[_word(v) for v in originals[target]], variant=list(c['words'][target]))
    s['scenarioCommitment'] = commit(SPEC_DOMAIN, s)
    validate_spec(s, raw)
    return s


def validate_spec(spec, raw):
    """Mirror of Go validateProfileSpec: commitment, descriptor binding, derived writes, variant words, origin."""
    d = parse(raw)
    try:
        s = copy.deepcopy(spec)
        pin = s.pop('scenarioCommitment')
        require(s.get('schema') == SPEC_DOMAIN and pin == commit(SPEC_DOMAIN, s), 'PROFILE_SPEC_COMMITMENT', 'scenario commitment')
        require('configOverlay' not in s and 'intervention' not in s, 'PROFILE_SPEC_BINDING', 'no other intervention form')
        o = s['profileOverlay']
        require(o['descriptor'] == dict(profileId=d['profileId'], revision=d['revision'], sha256=digest(raw)), 'PROFILE_SPEC_BINDING',
                'descriptor identity and SHA-256')
        canon = canonical_interventions(d, o['interventions'])
        require(o['interventions'] == canon, 'PROFILE_CANONICAL_ORDER', 'canonical intervention order')
        c = compose(d, canon, originals_from_descriptor(d))
        body = copy.deepcopy(s)
        body.pop('profileOverlay')
        require(o == _transform(body, d, raw, canon, c), 'PROFILE_SPEC_DERIVED_WRITES', 'transform must be exactly the derived writes')
        target = d['configurationTarget']
        require(s['configurations'] == dict(baseline=[w['value'] for w in d['originalState']['words'] if w['target'] == target],
                                            variant=c['words'][target]), 'PROFILE_SPEC_VARIANT_WORD', 'configuration words')
        require(s['origin'] == dict(kind=ORIGIN_KIND, capsuleId=capsule(body, d, raw, canon)), 'PROFILE_SPEC_ORIGIN', 'origin capsule')
        require(s['poolId'] == d['pool']['poolId'] and s['checkpoint']['chainId'] == d['chain']['chainId']
                and s['releaseManifestSha256'] == d['release']['manifestCommitment'], 'PROFILE_SPEC_BINDING', 'pool, chain or release')
        return spec
    except DescriptorError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise DescriptorError('PROFILE_SPEC_BINDING', 'incomplete profile-overlay input') from error


def variant_descriptor(raw, items):
    """Session variant descriptor; its variantId commits to the descriptor SHA-256."""
    d = parse(raw)
    return dict(kind=SESSION_KIND, profileId=d['profileId'], revision=d['revision'], descriptorSha256=digest(raw),
                interventions=canonical_interventions(d, items), backendProfile=BACKEND_PROFILE)


def require_engine_for_native():
    require(ACCEPTED_PROFILE_ENGINE is not None, 'PROFILE_ENGINE_NOT_ACCEPTED',
            'No descriptor-driven worker has a reviewed identity; nothing may be bound.')
    return ACCEPTED_PROFILE_ENGINE


def require_engine_record(raw):
    """The descriptor and catalogue bytes are exactly those the reviewed engine embeds, and the record names the
    accepted identity and linked profile. Not an execution authorization."""
    rec = PROFILE_ENGINE_RECORD
    require(type(rec) is dict and set(rec) == ENGINE_RECORD_KEYS and ACCEPTED_PROFILE_ENGINE is not None
            and rec['engine'] == ACCEPTED_PROFILE_ENGINE and type(rec['engine']) is dict
            and set(rec['engine']) == {'sourceSha256', 'binarySha256', 'policySha256'}
            and all(type(v) is str and SHA.fullmatch(v) for v in rec['engine'].values())
            and rec['profile'] == BACKEND_PROFILE and rec['buildVerification'] == ENGINE_BUILD_VERIFICATION
            and rec['status'] == ENGINE_RECORD_STATUS and type(rec['descriptor']) is dict
            and set(rec['descriptor']) == {'profileId', 'revision', 'sha256'} and type(rec['catalogueSha256']) is str
            and SHA.fullmatch(rec['catalogueSha256']), 'PROFILE_ENGINE_RECORD', 'the reviewed engine identity record is incomplete')
    cat = (DESCRIPTOR_DIR / 'CATALOGUE.json').read_bytes()
    require(descriptor_ref(raw) == rec['descriptor'] and digest(cat) == rec['catalogueSha256'], 'PROFILE_ENGINE_RECORD',
            'the descriptor or catalogue differs from the reviewed engine identity record')
    return rec


# ----- G4A: backend integration (nitro-hook-profile-overlay/0.1) -------------------------------------------------

# The compiled bounds of the descriptor worker; mirror of Go validateProfileWorkerBounds (profile.go). A descriptor
# outside them needs a different worker, not different data.
WORKER_BOUNDS = dict(
    chainId=4663, arbosVersion=61, engineFamily='NITRO', systemSubjects='NITRO_ARBOS61_SCENARIO_SYSTEM_V1',
    chainConfigSha256='dfa6de28a2dcf9fa3079d97c73401af7c7df0bc7222a6a3fe1e927d98104ffe0',
    pinnedRoles=('poolManager', 'root', 'router', 'rules'),
    targets=dict(rulesConfig=('rules', 4), rootRecord=('root', 2)), configurationTarget='rulesConfig', policy='EXACT_WORDS',
    rootFields=dict(rootRulesAddress=('rootRecord', 0, 0, 160), rootBaseLpFeePips=('rootRecord', 0, 160, 24),
                    rootDynamicFeeFlag=('rootRecord', 0, 248, 1), rootRecaptureFlag=('rootRecord', 0, 249, 1),
                    rootFlagsReserved=('rootRecord', 0, 250, 6)),
    originalRootWord='0x030101000000000000000bb84a71c270b1520f94064268102aebd744b0de7942',
    rulesAddress='0x4a71c270b1520f94064268102aebd744b0de7942',
    action=dict(type='HOOKR_ROUTER_EXACT_INPUT_BUY_V1', router='router', function='swap', amountInWei='1000000000000000',
                minimumOutputBaseUnits='1', sqrtPriceLimitX96='4295128740', zeroForOne=True, engagement='0x' + '00' * 20,
                campaigns=[], transactionType='LEGACY', count=1, gas=[5000000, 10000000]),
    setup=dict(actor=dict(kind='PUBLIC_SIMULATION_SIGNER_V1', seed='RHOOK BUILD04 PUBLIC SIMULATION SIGNER; NEVER FUND OR BROADCAST'),
               fundingWei='1000000000000000000', nonce=0, requireOriginalAbsence=True))


def validate_worker_bounds(d):
    b = WORKER_BOUNDS
    c = d['chain']
    ok = (c['chainId'] == b['chainId'] and c['arbosVersion'] == b['arbosVersion'] and c['engineFamily'] == b['engineFamily']
          and c['chainConfigSha256'] == b['chainConfigSha256'] and d['witness']['systemSubjects'] == b['systemSubjects'])
    targets, fields, _, contracts = _index(d)
    for role in b['pinnedRoles']:
        k = contracts.get(role)
        ok = ok and k is not None and k['requirement'] == 'CODE_HASH_EQUALS' and k.get('releaseRole') == role
    tokens = [k for k in d['contracts'] if k['requirement'] == 'CODE_PRESENT']
    ok = ok and len(tokens) == 1 and tokens[0]['address'] == d['pool']['currency1'] and d['pool']['hooksContract'] == 'root' \
        and d['pool']['currency0'] == '0x' + '00' * 20
    ok = ok and set(targets) == set(b['targets']) and all((targets[n]['contract'], targets[n]['words']) == v for n, v in b['targets'].items())
    ok = ok and d['configurationTarget'] == b['configurationTarget'] and d['originalState']['policy'] == b['policy']
    for name, (target, word, offset, width) in b['rootFields'].items():
        f = fields.get(name)
        ok = ok and f is not None and (f['target'], f['word'], f['offset'], f['width']) == (target, word, offset, width)
    a = d['action']
    compiled = json.loads(COMPILED_PROFILE.read_bytes())['swapAbi']
    ok = ok and all(a.get(k) == v for k, v in b['action'].items()) and a['abi'] == compiled
    s = d['setup']
    ok = ok and all(s.get(k) == v for k, v in b['setup'].items())
    # Every SDK 0.4 compiled precondition stays compiled: the descriptor reproduces profile.json exactly
    # (release manifest, pool and key, slots, ABI, original words) and the original Root word; code pins match.
    compiled_profile = json.loads(COMPILED_PROFILE.read_bytes())
    ok = ok and legacy_profile(d) == compiled_profile
    ok = ok and [w['value'] for w in d['originalState']['words'] if w['target'] == 'rootRecord' and w['word'] == 0] == [b['originalRootWord']]
    # Go officialProfile pins root, router, poolManager and the one Rules contract of this pool (the manifest lists several).
    pins = {r['address']: r['runtimeHash'] for r in compiled_profile['manifest']['contracts']
            if r['role'] in ('root', 'router', 'poolManager') or r['address'] == b['rulesAddress']}
    ok = ok and {k['address']: k.get('runtimeCodeHash') for k in d['contracts'] if k['requirement'] == 'CODE_HASH_EQUALS'} == pins
    require(ok, 'PROFILE_WORKER_BOUNDS', 'the descriptor needs a capability this worker does not compile')
    return d


def intent(raw, pool, items):
    """Plan intent of a profile-overlay scenario: pool, descriptor identity and the canonical intervention set."""
    d = validate_worker_bounds(parse(raw))
    require(pool == d['pool']['poolId'], 'PROFILE_SPEC_BINDING', 'pool differs from the descriptor')
    return _intent(d, raw, pool, canonical_interventions(d, items))


def descriptor_ref(raw):
    d = parse(raw)
    return dict(profileId=d['profileId'], revision=d['revision'], sha256=digest(raw))


def load_for_intent(value, purpose, *, directory=None):
    """The accepted descriptor a plan intent names, under a review purpose; its bytes must be the planned ones."""
    require(type(value) is dict and type(value.get('profile')) is dict, 'PROFILE_SPEC_BINDING', 'plan intent')
    d, raw, entry = load_accepted(value['profile'].get('profileId'), purpose, directory=directory)
    require(digest(raw) == value['profile'].get('sha256'), 'PROFILE_SPEC_BINDING', 'planned descriptor differs from the catalogue')
    validate_worker_bounds(d)
    require(value == intent(raw, value.get('poolId'), value.get('interventions')), 'PROFILE_SPEC_BINDING', 'plan intent is not canonical')
    require_kind_review(entry, value['interventions'], purpose)
    return d, raw, entry


def native_operation_ref(value, engine, *, directory=None):
    """Descriptor binding of a native operation: refused unless the catalogue review admits NATIVE_EXECUTION for
    the descriptor and every selected kind, and the registered runtime is exactly the accepted descriptor-worker
    identity (source, binary, policy). The worker refuses an operation without this exact binding."""
    _, raw, _ = load_for_intent(value, 'NATIVE_EXECUTION', directory=directory)
    require(engine == require_engine_for_native(), 'PROFILE_ENGINE_NOT_ACCEPTED',
            'the registered runtime is not the accepted descriptor-worker identity')
    require_engine_record(raw)
    return descriptor_ref(raw)


def authenticate_targets(spec, raw, *, node):
    """Independent (Node, trie-only) authentication of every declared contract and target word of a prepared
    input against its checkpoint state root; the words must be the reviewed EXACT_WORDS. Offline; no worker."""
    import subprocess
    d = validate_worker_bounds(parse(raw))
    require(node is not None and str(node) != '', 'PROFILE_TARGET_AUTHENTICATOR_UNAVAILABLE', 'an explicit Node binary is required')
    try:
        r = subprocess.run([str(node), str(TARGET_AUTHENTICATOR)], input=canonical(dict(spec=spec, descriptor=d)), stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DescriptorError('PROFILE_TARGET_AUTHENTICATOR_UNAVAILABLE', str(error)[:200]) from error
    require(len(r.stdout) <= 1 << 20, 'PROFILE_TARGET_AUTHENTICATOR_OUTPUT')
    try:
        value = strict(r.stdout)
    except (ValueError, UnicodeError) as error:
        raise DescriptorError('PROFILE_TARGET_AUTHENTICATOR_UNAVAILABLE', r.stderr.decode(errors='replace')[:200]) from error
    require(r.returncode == 0 and value.get('schema') == 'rhook/profile-target-state/0.1', value.get('causeCode', 'PROFILE_TARGET_AUTHENTICATION'),
            json.dumps(value.get('details', {}))[:300])
    originals = {name: [_word(v) for v in words] for name, words in originals_from_descriptor(d).items()}
    require(value['checkpoint'] == spec['checkpoint'] and value['targets'] == originals, 'PROFILE_ORIGINAL_WORD',
            'authenticated target words differ from the reviewed originals')
    for c in d['contracts']:
        got = value['contracts'].get(c['name'], {})
        require(got.get('address') == c['address'] and got.get('codeBytes', 0) > 0
                and (c['requirement'] != 'CODE_HASH_EQUALS' or got.get('codeHash') == c['runtimeCodeHash']), 'PROFILE_CODE_IDENTITY', c['name'])
    return dict(status='PROFILE_TARGETS_MPT_AUTHENTICATED', schema=value['schema'], contracts=value['contracts'], targets=value['targets'],
                scope='Declared contract accounts, code preimages and every target word, from the checkpoint state root through the witness nodes. '
                      'Checkpoint trust is supplied, not consensus-verified.')


def validate_input(spec, raw):
    """Python side of the worker's input checks that are pure data: the descriptor binding, the worker bounds and
    the reviewed chain configuration bytes. Witness authentication remains the worker's (--profile-state)."""
    d = validate_worker_bounds(parse(raw))
    validate_spec(spec, raw)
    config = spec.get('chainConfig')
    require(type(config) is str and re.fullmatch('0x([0-9a-f]{2})*', config) is not None
            and digest(bytes.fromhex(config[2:])) == d['chain']['chainConfigSha256'], 'PROFILE_CHAIN_CONFIG', 'chain configuration bytes')
    return spec
