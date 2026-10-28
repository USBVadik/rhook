// Exact original envelopes reconstructed from signed RPC transaction fields.
// Hash/root checks, followed by native admission, prevent invented inputs.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {hex,quantity,keccak256,toRlp} from '../../../engine/adapters/hookr-case/primitives.mjs';
const require=createRequire(new URL('../../../engine/adapters/hookr-case/package.json',import.meta.url));
const {serializeTransaction}=require('viem');
const q=value=>{const n=quantity(value);return n===0n?'0x':'0x'+n.toString(16).padStart(Math.ceil(n.toString(16).length/2)*2,'0');};

export function rawFromRpc(tx){
  const type=Number(quantity(tx.type));
  assert([0,1,2,106].includes(type),'UNSUPPORTED_TRANSACTION_TYPE');
  assert.equal(quantity(tx.chainId),4663n,'TRANSACTION_CHAIN');
  hex(tx.input);
  let raw;
  if(type===106){
    // Retained geth ArbitrumInternalTx{ChainId,Data}, ArbOS61 profile.
    raw='0x6a'+toRlp([q(tx.chainId),tx.input]).slice(2);
  }else{
    const nonce=quantity(tx.nonce);assert(nonce<=BigInt(Number.MAX_SAFE_INTEGER),'NONCE_RANGE');
    const base={type:['legacy','eip2930','eip1559'][type],chainId:4663,nonce:Number(nonce),gas:quantity(tx.gas),
      to:tx.to===null?undefined:hex(tx.to,20),value:quantity(tx.value),data:tx.input};
    if(type<2)base.gasPrice=quantity(tx.gasPrice);
    if(type===2){base.maxFeePerGas=quantity(tx.maxFeePerGas);base.maxPriorityFeePerGas=quantity(tx.maxPriorityFeePerGas);}
    if(type>0){assert(Array.isArray(tx.accessList),'ACCESS_LIST_REQUIRED');base.accessList=tx.accessList;}
    const scalar=v=>{const n=quantity(v);assert(n>0n&&n<(1n<<256n),'SIGNATURE_SCALAR');return '0x'+n.toString(16).padStart(64,'0');};
    const signature={r:scalar(tx.r),s:scalar(tx.s)};
    if(type===0)signature.v=quantity(tx.v);
    else{const parity=quantity(tx.yParity??tx.v);assert(parity<=1n,'Y_PARITY');signature.yParity=Number(parity);}
    raw=serializeTransaction(base,signature);
  }
  assert.equal(keccak256(raw),tx.hash,'ORIGINAL_RAW_HASH_MISMATCH');
  return raw;
}
