"""Configuration-only test data. No proofs, receipts or native execution results."""
import json
from pathlib import Path


def metadata():
    profile = json.loads((Path(__file__).resolve().parents[1] /
                          'rhook_alpha/cases/scenario/native/profile.json').read_text())
    contracts = {row['role']: row['address'] for row in profile['manifest']['contracts']}
    baseline = list(profile['baselineConfigWords'])
    variant = list(baseline)
    mask = 65535 << 160
    variant[0] = '0x' + ((int(baseline[0], 16) & ~mask) | (50 << 160)).to_bytes(32, 'big').hex()
    actor = '0xd2480fd61af9bc73b8c73e8fdcabceb6f21ea8ff'  # Supported public simulation actor.
    return {
        'syntheticFixtureOnly': True,  # Header identity from the supported example; all witness material is fake.
        'checkpoint': dict(chainId=4663, blockNumber=99236464,
                           blockHash='0x3d8a7eff122421e924553d9ca0949e10c919da1703b3ddd07f8433999e6d0fd9',
                           stateRoot='0x7a947171a7c1620561d1ea629e1233d078518f422ddcb9ff8dcff346ae3624be'),
        'checkpointTimestamp': 1700000000,
        'source': {'workerSha256': 'e' * 64},
        'scenario': {
            'poolId': profile['poolId'], 'configurationAccount': contracts['rules'],
            'configurations': dict(baseline=baseline, variant=variant),
            'commonSetup': dict(actor=actor, fundingWei='1000000000000000000',
                                nonce=0, requireOriginalAbsence=True),
            'environment': dict(l2BlockNumber=99236465, l2Timestamp=1700000001,
                                l1BlockNumber=100, delayedMessagesRead=1,
                                poster='0xa4b000000000000000000073657175656e636572',
                                syntheticL1BaseFeeWei='1000000000'),
        },
    }
