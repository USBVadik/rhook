// Offline RLP, MPT and bloom checks adapted from the preserved Pair03 verifier.
import assert from 'node:assert/strict';
import {keccak256,toRlp} from '../adapters/hookr-case/primitives.mjs';
const q=x=>{let n=BigInt(x);return n===0n?'0x':'0x'+n.toString(16).padStart(Math.ceil(n.toString(16).length/2)*2,'0');};
const nib=x=>[...x.slice(2)].map(c=>parseInt(c,16));
function compact(path,leaf){let ns=path.length%2?[(leaf?2:0)+1,...path]:[(leaf?2:0),0,...path];return '0x'+ns.map(n=>n.toString(16)).join('');}
export function trieRoot(values){
 const entries=values.map((v,i)=>({path:nib(toRlp(q(i))),value:v}));
 const ref=node=>{let raw=toRlp(node);return (raw.length-2)/2<32?node:keccak256(raw);};
 function build(rows,at){
  if(rows.length===1)return [compact(rows[0].path.slice(at),true),rows[0].value];
  let n=0;while(rows.every(r=>r.path.length>at+n&&r.path[at+n]===rows[0].path[at+n]))n++;
  if(n)return [compact(rows[0].path.slice(at,at+n),false),ref(build(rows,at+n))];
  let node=Array(17).fill('0x');
  for(let i=0;i<16;i++){let group=rows.filter(r=>r.path.length>at&&r.path[at]===i);if(group.length)node[i]=ref(build(group,at+1));}
  let ended=rows.filter(r=>r.path.length===at);assert(ended.length<=1);if(ended.length)node[16]=ended[0].value;
  return node;
 }
 return entries.length?keccak256(toRlp(build(entries,0))):keccak256(toRlp('0x'));
}
export function headerHash(h){
 for(const f of ['withdrawalsRoot','blobGasUsed','excessBlobGas','parentBeaconBlockRoot','requestsHash','blockAccessListHash','slotNumber'])assert(h[f]==null);
 return keccak256(toRlp([h.parentHash,h.sha3Uncles,h.miner,h.stateRoot,h.transactionsRoot,h.receiptsRoot,h.logsBloom,q(h.difficulty),q(h.number),q(h.gasLimit),q(h.gasUsed),q(h.timestamp),h.extraData,h.mixHash,h.nonce,q(h.baseFeePerGas)]));
}
export function bloom(logs){let buf=Buffer.alloc(256);for(const l of logs)for(const item of [l.address,...l.topics]){let h=Buffer.from(keccak256(item).slice(2),'hex');for(let i=0;i<6;i+=2){let bit=((h[i]<<8)|h[i+1])&2047;buf[255-(bit>>3)]|=1<<(bit&7);}}return '0x'+buf.toString('hex');}
export function receiptBytes(r){
 const raw=toRlp([r.root&&r.root!=='0x'?r.root:q(r.status),q(r.cumulativeGasUsed),r.logsBloom,(r.logs||[]).map(l=>[l.address,l.topics,l.data])]);
 assert([0,1,2,3,4,100,101,102,104,105,106,120].includes(Number(BigInt(r.type))));
 return Number(BigInt(r.type))===0||Number(BigInt(r.type))===120?raw:q(r.type)+raw.slice(2);
}
