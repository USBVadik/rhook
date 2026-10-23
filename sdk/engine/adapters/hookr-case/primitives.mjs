import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {keccak256, fromRlp, toRlp} from 'viem';
export {keccak256, fromRlp, toRlp};
export const sha256=bytes=>createHash('sha256').update(bytes).digest('hex');
export function canonical(value){
 if(value===null||typeof value==='string'||typeof value==='boolean')return JSON.stringify(value);
 if(typeof value==='number'){assert(Number.isSafeInteger(value),'NON_CANONICAL_NUMBER');return JSON.stringify(value);}
 if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';
 assert(value&&typeof value==='object'&&Object.getPrototypeOf(value)===Object.prototype,'NON_CANONICAL_OBJECT');
 return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
}
export const commitment=(domain,value)=>sha256(Buffer.from(domain+'\n'+canonical(value),'utf8'));
export function hex(value,bytes){
 assert(typeof value==='string'&&/^0x(?:[0-9a-fA-F]{2})*$/.test(value),'MALFORMED_BYTES');
 if(bytes!==undefined)assert.equal((value.length-2)/2,bytes,'INCORRECT_BYTE_LENGTH');
 return value.toLowerCase();
}
export function quantity(value){
 assert(typeof value==='string'&&/^0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)$/.test(value),'MALFORMED_QUANTITY');
 return BigInt(value);
}
export const address=value=>hex(value,20);
export const hash=value=>hex(value,32);
export function slot(value){
 assert(typeof value==='string'&&/^0x[0-9a-fA-F]{1,64}$/.test(value),'MALFORMED_SLOT');
 return '0x'+BigInt(value).toString(16).padStart(64,'0');
}
export const EMPTY_ROOT=keccak256(toRlp('0x'));
export const EMPTY_CODE=keccak256('0x');
