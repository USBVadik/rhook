// SYNTHETIC, hash-linked original state for Counterfactual Session tests. Not chain data.
// The tries, parent header and code are made up; only their hashes are internally consistent.
//   node sdk/tests_cases/session-fixture.mjs [complete|unknown-sibling]   prints {checkpoint,parent,inventory}
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const sdk=new URL('../',import.meta.url);
const {toRlp,keccak256,EMPTY_ROOT}=await import(new URL('engine/adapters/hookr-case/primitives.mjs',sdk));
const {headerHash}=await import(new URL('engine/plan_native/ethereum.mjs',sdk));
const {C}=await import(new URL('rhook_alpha/cases/witness/material.mjs',sdk));
const profile=JSON.parse(fs.readFileSync(new URL('rhook_alpha/cases/scenario/native/profile.json',sdk)));

const nibbles=h=>[...h.slice(2)].map(c=>parseInt(c,16));
const compact=(p,leaf)=>{const f=(leaf?2:0)+(p.length%2);return '0x'+(p.length%2?[f,...p]:[f,0,...p]).map(n=>n.toString(16)).join('');};
const minimal=w=>{const n=BigInt(w);if(n===0n)return '0x';const h=n.toString(16);return '0x'+(h.length%2?'0'+h:h);};
export const word=n=>'0x'+BigInt(n).toString(16).padStart(64,'0');

// Secure Merkle-Patricia trie over already hashed keys; every hashed node is appended to nodes.
export function buildTrie(entries,nodes){
 const ref=node=>{const raw=toRlp(node);if((raw.length-2)/2<32)return node;nodes.push(raw);return keccak256(raw);};
 function build(rows,at){
  if(rows.length===1)return [compact(rows[0].path.slice(at),true),rows[0].value];
  let n=0;while(rows.every(r=>r.path[at+n]===rows[0].path[at+n]))n++;
  if(n)return [compact(rows[0].path.slice(at,at+n),false),ref(build(rows,at+n))];
  const node=Array(17).fill('0x');
  for(let i=0;i<16;i++){const g=rows.filter(r=>r.path[at]===i);if(g.length)node[i]=ref(build(g,at+1));}
  return node;
 }
 if(!entries.length)return EMPTY_ROOT;
 const raw=toRlp(build(entries.map(e=>({path:nibbles(e.key),value:e.value})),0));nodes.push(raw);return keccak256(raw);
}

export const RULES_CODE='0x6000';
export const CONFIG_KEYS=[0,1,2,3].map(i=>word(BigInt(C.slot)+BigInt(i)));

export function syntheticState({unknownSibling=false}={}){
 const nodes=[];
 // Zero words are absent from a storage trie, exactly as on chain.
 const storageRoot=buildTrie(CONFIG_KEYS.map((k,i)=>({key:keccak256(k),word:profile.baselineConfigWords[i]}))
  .filter(e=>BigInt(e.word)!==0n).map(e=>({key:e.key,value:toRlp(minimal(e.word))})),nodes);
 const account=toRlp(['0x01','0x',storageRoot,keccak256(RULES_CODE)]);
 let stateRoot,missing=null;
 if(!unknownSibling)stateRoot=buildTrie([{key:keccak256(C.rules),value:account}],nodes);
 else{
  // Root branch: the Rules account is known; every other first nibble points to an unknown node.
  const path=nibbles(keccak256(C.rules)),leaf=toRlp([compact(path.slice(1),true),account]);nodes.push(leaf);
  missing=keccak256(toRlp(['0x20','0x01']));
  const root=Array(17).fill('0x');for(let i=0;i<16;i++)root[i]=i===path[0]?keccak256(leaf):missing;
  const raw=toRlp(root);nodes.push(raw);stateRoot=keccak256(raw);
 }
 return {nodes,codes:[RULES_CODE],stateRoot,storageRoot,missing};
}

export function syntheticScenarioParts(options={}){
 const state=syntheticState(options);
 // mixHash bytes 0..8 hold the send count and bytes 16..24 the ArbOS version, as Nitro encodes them.
 const mixHash='0x'+word(5).slice(-16)+'0'.repeat(16)+word(61).slice(-16)+'0'.repeat(16);
 const header={parentHash:word(7),sha3Uncles:'0x1dcc4de8dec75d7aab85b567b6ccd41ad312451b948a7413f0a142fd40d49347',
  miner:'0xa4b000000000000000000073657175656e636572',stateRoot:state.stateRoot,transactionsRoot:EMPTY_ROOT,receiptsRoot:EMPTY_ROOT,
  logsBloom:'0x'+'00'.repeat(256),difficulty:'0x1',number:'0x'+(99236464).toString(16),gasLimit:'0x4000000000000',gasUsed:'0x0',
  timestamp:'0x'+(1700000000).toString(16),extraData:word(11),mixHash,nonce:'0x0000000000000001',baseFeePerGas:'0x1'};
 const parent={...header,hash:headerHash(header)};
 return {syntheticFixtureOnly:true,checkpoint:{chainId:4663,blockNumber:99236464,blockHash:parent.hash,stateRoot:state.stateRoot},
  parent,inventory:{nodes:state.nodes,codes:state.codes},missingNodeHash:state.missing};
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 process.stdout.write(JSON.stringify(syntheticScenarioParts({unknownSibling:process.argv[2]==='unknown-sibling'}))+'\n');
}
