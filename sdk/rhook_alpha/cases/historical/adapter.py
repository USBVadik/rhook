"""A single typed historical intervention, not caller-supplied storage writes."""
import copy
from pathlib import Path
from developer.files import canonical, digest, load, require, strict
from ..capsule import seal
from . import ADAPTER, DOMAIN, PROFILE


def profile():
    return load(Path(__file__).with_name('profile.json'))


def intervention():
    p = profile()
    body = dict(schema=DOMAIN+'/transform', checkpoint=p['checkpoint'], pool=p['pool'],
                rootCodeHash=p['rootCodeHash'], rulesCodeHash=p['rulesCodeHash'], writes=p['writes'])
    return dict(body, interventionCommitment=digest((DOMAIN+'/transform\n').encode()+canonical(body)))


class HistoricalDynamicFeeOff:
    identity = ADAPTER

    def plan(self, d, value):
        p = profile()
        require(value == {'rule': 'dynamicFee', 'value': 'OFF'} and type(value) is dict,
                'EXACT_DYNAMIC_FEE_OFF_INTERVENTION_REQUIRED')
        require(d['execution'] == dict(profile=PROFILE,inputCommitment=p['inputCommitment'],witnessCommitment=p['witnessCommitment']), 'HISTORICAL_EXECUTION_DOMAIN')
        require(d['checkpoint'] == p['checkpoint'] and d['target'] == p['target'] and d['arrivals'] == p['arrivals'], 'EXACT_HISTORICAL_TARGET')
        require(d['assets']['BLOCK_PACKAGE.json']['sha256'] == p['packageSha256'], 'EXACT_HISTORICAL_PACKAGE')
        expected = dict(rulesRuntimeHash=p['rulesCodeHash'], intervention=intervention(), observation=p['observation'])
        require(d['adapter'] == dict(id=ADAPTER,config=expected), 'HISTORICAL_ADAPTER_CONFIG')
        return dict(schema=DOMAIN+'/plan', packageSha256=p['packageSha256'], inputCommitment=p['inputCommitment'],
                    witnessCommitment=p['witnessCommitment'], checkpoint=p['checkpoint'], **p['target'],
                    arrivals=p['arrivals'], transactions=7, subject=p['subject'], sender=p['sender'],router=p['router'],
                    observation=p['observation'],intervention=intervention(),rulesRuntimeHash=p['rulesCodeHash'])

    def authentication_plan(self, d):
        return self.plan(d, {'rule':'dynamicFee','value':'OFF'})

    def capsule(self, raw, *, case_id, subject_index, input_commitment, witness_commitment, original_word=None):
        p = profile()
        require(digest(raw) == p['packageSha256'] and subject_index == p['ordinal'] and type(subject_index) is int,
                'EXACT_HISTORICAL_PACKAGE_AND_SUBJECT_REQUIRED')
        require(input_commitment == p['inputCommitment'] and witness_commitment == p['witnessCommitment'] and original_word is None, 'HISTORICAL_COMMITMENTS')
        pkg = strict(raw)
        require(pkg['checkpoint'] == p['checkpoint'], 'HISTORICAL_PARENT')
        d = seal(dict(schema='rhook/case-capsule/0.1',caseId=case_id,checkpoint=p['checkpoint'],target=p['target'],
                arrivals=p['arrivals'],assets={'BLOCK_PACKAGE.json':dict(sha256=digest(raw),bytes=len(raw))},
                execution=dict(profile=PROFILE,inputCommitment=input_commitment,witnessCommitment=witness_commitment),
                adapter=dict(id=ADAPTER,config=dict(rulesRuntimeHash=p['rulesCodeHash'],intervention=intervention(),observation=p['observation'])),
                provenance=dict(kind='RETAINED_CAPTURE',description='Saved seven-arrival block; operator checkpoint trust and native proof admission remain separate.'),
                coverage=dict(reads='UNKNOWN',writes='UNKNOWN')))
        self.authentication_plan(d)
        return d

    def compare(self, verified):
        require(verified.get('profile') == PROFILE and verified.get('schema') == DOMAIN+'/verification', 'HISTORICAL_EVIDENCE_DOMAIN')
        from ..adapters import HookrLP
        return dict(HookrLP().compare(verified), profile=PROFILE, intervention='DYNAMIC_FEE_OFF',
                    causalScope='ORIGINAL_PARENT_FULL_SEVEN_ARRIVAL_BLOCK',LP100=True,arbRecapture='RETAINED')
