import test from 'node:test';
import assert from 'node:assert/strict';
import {configProfile} from '../sdk/rhook_alpha/cases/witness/profile.mjs';
const config=()=>({chainId:4663,homesteadBlock:0,eip150Block:0,eip155Block:0,eip158Block:0,byzantiumBlock:0,
  constantinopleBlock:0,petersburgBlock:0,istanbulBlock:0,muirGlacierBlock:0,berlinBlock:0,londonBlock:0,
  arbitrum:{EnableArbOS:true,MaxCodeSize:98304,MaxInitCodeSize:196608,InitialArbOSVersion:51}});
test('supported native configuration has no diagnostic blockers',()=>assert.deepEqual(configProfile(config()),[]));
test('changed fork schedule is classified before native admission',()=>{
  assert(configProfile({...config(),homesteadBlock:1}).includes('UNSUPPORTED_FORK_SCHEDULE'));
  const missing=config();delete missing.berlinBlock;assert(configProfile(missing).includes('UNSUPPORTED_FORK_SCHEDULE'));
});
test('unknown fields and changed Nitro limits are explicit blockers',()=>{
  assert(configProfile({...config(),shanghaiTime:0}).some(x=>x.startsWith('UNSUPPORTED_CHAIN_CONFIG_FIELD')));
  const c=config();c.arbitrum.MaxCodeSize=1;assert(configProfile(c).includes('UNSUPPORTED_NITRO_CHAIN_CONFIG'));
});
test('foreign chain and disabled ArbOS are unsupported',()=>{
  assert(configProfile({...config(),chainId:1}).includes('INCORRECT_CHAIN_CONFIG_OR_ARBOS_VERSION'));
  const c=config();c.arbitrum.EnableArbOS=false;assert(configProfile(c).includes('INCORRECT_CHAIN_CONFIG_OR_ARBOS_VERSION'));
});
