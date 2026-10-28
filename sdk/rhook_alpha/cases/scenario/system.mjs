import assert from 'node:assert/strict';
import {word} from './build.mjs';
import {keccak256,hash} from '../../../engine/adapters/hookr-case/primitives.mjs';
export const FILTER_ADDRESS='0xa4b0500000000000000000000000000000000001';
// Nitro KVStorage maps a 248-bit page hash and retains its final offset byte.
export function transactionFilterSlot(transactionHash){
 hash(transactionHash);return keccak256(transactionHash.slice(0,-2)).slice(0,-2)+transactionHash.slice(-2);
}
export function addActionSubjects(subjects,actions){
 if(!subjects.has(FILTER_ADDRESS))subjects.set(FILTER_ADDRESS,new Set());
 return actions.map(action=>{
  const transactionHash=keccak256(action.signedTransaction),slot=transactionFilterSlot(transactionHash);
  subjects.get(FILTER_ADDRESS).add(slot);return {address:FILTER_ADDRESS,transactionHash,slot};
 });
}
// ArbOS61's pinned HistoryStorageCodeArbitrum uses this L2-block ring.
export const HISTORY_ADDRESS='0x0000f90827f1c53a10cb7a02335b175320002935';
export const HISTORY_RING_BLOCKS=393168;
export function historySlot(checkpointNumber){
 assert(Number.isSafeInteger(checkpointNumber)&&checkpointNumber>=0,'CHECKPOINT_L2_NUMBER');
 return word(BigInt(checkpointNumber)%BigInt(HISTORY_RING_BLOCKS));
}
export function addHistorySubject(subjects,checkpoint){
 assert(checkpoint.chainId===4663,'HISTORY_CHAIN_PROFILE');
 if(!subjects.has(HISTORY_ADDRESS))subjects.set(HISTORY_ADDRESS,new Set());
 const slot=historySlot(checkpoint.blockNumber);subjects.get(HISTORY_ADDRESS).add(slot);return {address:HISTORY_ADDRESS,slot};
}
