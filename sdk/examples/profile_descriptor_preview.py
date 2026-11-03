"""Profile Descriptor developer preview (SDK 0.6): everything here runs from a public clone, offline.

    python3 -B sdk/examples/profile_descriptor_preview.py catalogue
    python3 -B sdk/examples/profile_descriptor_preview.py inspect --profile hookr-1
    python3 -B sdk/examples/profile_descriptor_preview.py plan --profile hookr-1 --lp-bps 23 --dynamic-fee OFF
    python3 -B sdk/examples/profile_descriptor_preview.py plan --profile hookr-1 --lp-bps 23 --purpose NATIVE_EXECUTION
    python3 -B sdk/examples/profile_descriptor_preview.py validate --descriptor my-descriptor.json
    python3 -B sdk/examples/profile_descriptor_preview.py native-requirements

`plan` turns typed interventions into the masked storage writes of the reviewed descriptor, checks the
descriptor's original-state predicates and result invariants, and prints the deterministic commitments a
prepared input would carry: the canonical intervention set, the writes, `interventionCommitment` and the
checkpoint capsule. By default it uses the public header of Robinhood Chain block 101935336, the checkpoint of
the SDK 0.6 G5 runs; the same values give the same commitments on any machine.

What it does not do: it reads no witness, starts no worker, executes no EVM, contacts no network and grants no
authority. A full prepared input (`profile-prepare`) additionally needs the pinned SDK 0.4 input with its
authenticated witness, and a native run needs the reviewed descriptor worker; neither is in this repository.
`native-requirements` lists them. Exit code 0 means the step was admitted; 2 means a reviewed check refused it,
with the SDK's error code in the JSON output.
"""
import argparse
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True

# Public chain data: the header of the checkpoint used by the SDK 0.6 G5 runs (Robinhood Chain, chain id 4663).
G5_CHECKPOINT = dict(blockHash='0xbb9453c43e5cc6c1b09df710237b1a042bd29f5fac5120796d279d078fcb768d', blockNumber=101935336,
                     chainId=4663, stateRoot='0xa27e6a4dda94a403b96ae88b92f2f1a75088c8fdf51c22b738fba124545032c6')


def sdk(root):
    sys.path.insert(0, str(root))
    from rhook_alpha import profile_descriptor as pd
    return pd


def interventions(args):
    items = []
    if args.lp_bps is not None:
        items.append(dict(kind='LP_REWARDS_BPS', parameters=dict(lpBps=args.lp_bps)))
    if args.dynamic_fee is not None:
        items.append(dict(kind='DYNAMIC_FEE', parameters=dict(dynamicFee=args.dynamic_fee)))
    if args.tuning_sens is not None or args.tuning_max_fee is not None:
        items.append(dict(kind='DYNAMIC_FEE_TUNING', parameters=dict(dynamicFeeSens=args.tuning_sens, maxFeePips=args.tuning_max_fee)))
    return items


def catalogue(pd):
    cat = json.loads((pd.DESCRIPTOR_DIR / 'CATALOGUE.json').read_bytes())
    rows = [dict(profileId=e['profileId'], revision=e['revision'], descriptorSha256=e['descriptorSha256'], status=e['review']['status'],
                 admits=e['review']['admits'], kinds={k: dict(review=s, purposes=list(pd.KIND_REVIEW_PURPOSES[s])) for k, s in sorted(e['kinds'].items())})
            for e in cat['entries']]
    rec = pd.PROFILE_ENGINE_RECORD
    return dict(status='PROFILE_CATALOGUE', catalogueSha256=pd.digest((pd.DESCRIPTOR_DIR / 'CATALOGUE.json').read_bytes()), profiles=rows,
                reviewedEngine=dict(profile=rec['profile'], engine=rec['engine'], status=rec['status'], distributed=False),
                note='Only descriptors listed here are loaded for workflow use; a caller-supplied file never is.')


def inspect(pd, profile):
    d, raw, entry = pd.load_accepted(profile, 'OFFLINE_PREPARATION')
    baseline = pd.decode_fields(d, pd.originals_from_descriptor(d))
    return dict(status='PROFILE_INSPECTED', profileId=d['profileId'], revision=d['revision'], descriptorSha256=pd.descriptor_sha256(raw),
                chain=d['chain'], pool=dict(poolId=d['pool']['poolId'], hooksContract=d['pool']['hooksContract']),
                contracts=[dict(name=c['name'], address=c['address'], requirement=c['requirement']) for c in d['contracts']],
                targets=[dict(name=t['name'], contract=t['contract'], slot=t['slot'], words=t['words']) for t in d['targets']],
                fields=[dict(name=f['name'], target=f['target'], word=f['word'], offset=f['offset'], width=f['width'], type=f['type'],
                             baseline=baseline[f['name']]) for f in d['fields']],
                interventions=[dict(kind=k['kind'], parameters=k['parameters'], conflictsWith=k['conflictsWith'],
                                    review=entry['kinds'][k['kind']], purposes=list(pd.KIND_REVIEW_PURPOSES[entry['kinds'][k['kind']]]))
                               for k in d['interventions']])


def plan(pd, profile, items, purpose, checkpoint):
    d, raw, entry = pd.load_accepted(profile, purpose)
    canon = pd.canonical_interventions(d, items)
    pd.require_kind_review(entry, canon, purpose)
    c = pd.compose(d, canon, pd.originals_from_descriptor(d))
    body = dict(checkpoint=checkpoint, poolId=d['pool']['poolId'])
    # The same derivation build_spec() applies to a prepared input (rhook/hookr-profile-overlay/0.1).
    transform = pd._transform(body, d, raw, canon, c)
    changed = {k: dict(baseline=v, variant=c['fields']['variant'][k]) for k, v in c['fields']['baseline'].items() if v != c['fields']['variant'][k]}
    return dict(status='PROFILE_PLAN_ADMITTED', purpose=purpose, descriptor=pd.descriptor_ref(raw), checkpoint=checkpoint,
                interventions=canon, writes=c['writes'], changedFields=changed,
                interventionCommitment=transform['interventionCommitment'], capsuleId=pd.capsule(body, d, raw, canon),
                witnessRead=False, nativeExecution='NOT_PERFORMED', operation='NOT_BOUND',
                next='A prepared input additionally needs the pinned SDK 0.4 input and its authenticated witness (profile-prepare).')


def validate(pd, path):
    raw = Path(path).read_bytes()
    value = pd.parse(raw)
    listed = json.loads((pd.DESCRIPTOR_DIR / 'CATALOGUE.json').read_bytes())['entries']
    sha = pd.descriptor_sha256(raw)
    reviewed = any(e['descriptorSha256'] == sha for e in listed)
    return dict(status='DESCRIPTOR_VALID', profileId=value['profileId'], revision=value['revision'], descriptorSha256=sha, reviewed=reviewed,
                workflowUse='CATALOGUE_DESCRIPTOR' if reviewed else 'REFUSED_NOT_IN_CATALOGUE',
                note='Validation checks encoding, shape and internal consistency only. It does not show that the descriptor describes '
                     'the deployed contract; that is the separate catalogue review.')


def native_requirements(pd):
    rec = pd.PROFILE_ENGINE_RECORD
    return dict(status='NATIVE_EXECUTION_NOT_AVAILABLE_FROM_PUBLIC_CLONE', publicCloneProvides=[
        'descriptor and catalogue bytes, the Python and Go interpreters and their tests',
        'offline planning: canonical interventions, writes, predicates, invariants, commitments'],
        requiredAndNotDistributed=[
        dict(item='descriptor worker', identity=rec['engine'], profile=rec['profile'],
             why='compiled Nitro/geth executable; its distribution terms are not cleared (sdk/DISTRIBUTION.md)'),
        dict(item='pinned SDK 0.4 input for checkpoint 101935336', why='holds the authenticated witness (state proofs and code); private'),
        dict(item='registered runtime: Node and the host sensor', why='part of the private runtime bundle'),
        dict(item='host', why='Apple Silicon macOS, owner-controlled, on AC power with the lid open (host admission v4)')],
        perRunGates=['the owner authorization record for one exact operation (profile-authorize)', 'one-shot consent and attempt marker',
                     'the doctor, host admission and in-run recorded-integrity verification'],
        offlineOnlyKinds=['DYNAMIC_FEE_TUNING'],
        cli='rhook-cases profile-prepare | profile-authenticate | profile-operation | profile-authorize | profile-run; each stops '
            'with an explicit error when an asset above is missing.')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--sdk-root', type=Path, default=Path(__file__).resolve().parents[1], help='Source sdk directory or an installed prefix/lib')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('catalogue')
    sub.add_parser('inspect').add_argument('--profile', default='hookr-1')
    q = sub.add_parser('plan')
    q.add_argument('--profile', default='hookr-1')
    q.add_argument('--lp-bps', type=int, help='LP_REWARDS_BPS: replacement lpBps (the reviewed range is in `inspect`)')
    q.add_argument('--dynamic-fee', help='DYNAMIC_FEE: OFF')
    q.add_argument('--tuning-sens', type=int, help='DYNAMIC_FEE_TUNING: dynamicFeeSens (offline only)')
    q.add_argument('--tuning-max-fee', type=int, help='DYNAMIC_FEE_TUNING: maxFeePips (offline only)')
    q.add_argument('--purpose', default='OFFLINE_PREPARATION', choices=['OFFLINE_PREPARATION', 'NATIVE_EXECUTION'],
                   help='Review purpose to check; NATIVE_EXECUTION only checks the review, it runs nothing')
    q.add_argument('--checkpoint', type=Path, help='JSON header {blockHash, blockNumber, chainId, stateRoot}; default: block 101935336')
    sub.add_parser('validate').add_argument('--descriptor', type=Path, required=True)
    sub.add_parser('native-requirements')
    args = p.parse_args(argv)
    pd = sdk(args.sdk_root)
    try:
        if args.command == 'catalogue':
            value = catalogue(pd)
        elif args.command == 'inspect':
            value = inspect(pd, args.profile)
        elif args.command == 'plan':
            checkpoint = json.loads(args.checkpoint.read_bytes()) if args.checkpoint else dict(G5_CHECKPOINT)
            value = plan(pd, args.profile, interventions(args), args.purpose, checkpoint)
        elif args.command == 'validate':
            value = validate(pd, args.descriptor)
        else:
            value = native_requirements(pd)
    except pd.DescriptorError as error:
        print(json.dumps(dict(status='REFUSED', code=error.code, detail=error.detail), indent=1, sort_keys=True))
        return 2
    print(json.dumps(value, indent=1, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
