import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {keccak256,toRlp} from '../engine/adapters/hookr-case/primitives.mjs';
import {authenticateTargetState} from '../rhook_alpha/intervention-state.mjs';
const hex=n=>'0x'+BigInt(n).toString(16).padStart(64,'0');
const compact=(path,leaf)=>{const n=[leaf?2:0];if(path.length%2)n[0]++;else n.push(0);return '0x'+n.concat(path).map(x=>x.toString(16)).join('');};
function fixture(options={}){
 const p=JSON.parse(fs.readFileSync(new URL('../rhook_alpha/cases/scenario/native/profile.json',import.meta.url)));
 const root=p.manifest.contracts.find(x=>x.role==='root'),rules=p.manifest.contracts.find(x=>x.role==='rules');
 root.runtimeHash=keccak256('0x00');rules.runtimeHash=keccak256('0x01');
 const nodes=[];
 function trie(pairs){
  if(pairs.length===1){const raw=toRlp([compact(pairs[0][0],true),pairs[0][1]]);nodes.push(raw);return keccak256(raw);}
  let n=0;while(pairs.every(x=>x[0][n]===pairs[0][0][n])&&n<64)n++;
  let body;
  if(n)body=[compact(pairs[0][0].slice(0,n),false),trie(pairs.map(([k,v])=>[k.slice(n),v]))];
  else {body=Array(17).fill('0x');for(let i=0;i<16;i++){const row=pairs.filter(x=>x[0][0]===i);if(row.length)body[i]=trie(row.map(([k,v])=>[k.slice(1),v]));}}
  const raw=toRlp(body);nodes.push(raw);return keccak256(raw);
 }
 const key=x=>[...keccak256(x).slice(2)].map(x=>parseInt(x,16));
 const rows=[];
 for(const [c,slot,word] of [[root,p.rootRecordSlot,'0x030101000000000000000bb84a71c270b1520f94064268102aebd744b0de7942'],[rules,p.configSlot,p.baselineConfigWords[0]]]){
  const value='0x'+BigInt(word).toString(16).padStart(Math.ceil(BigInt(word).toString(16).length/2)*2,'0');
  const storageValue=options.storage?'0xb8'+((value.length-2)/2).toString(16).padStart(2,'0')+value.slice(2):toRlp(value);
  const storage=trie([[key(slot),storageValue]]);
  let account=toRlp(['0x','0x',storage,c.runtimeHash]);
  if(options.account)account='0xf900'+account.slice(4);
  rows.push([key(c.address),account]);
 }
 const rootHash=trie(rows);
 const s={checkpoint:{chainId:4663,blockNumber:99236464,blockHash:hex(1),stateRoot:rootHash},inventory:{nodes,codes:['0x00','0x01']}};
 return {s,p};
}
test('authenticates target fields and zero-storage absence from independent synthetic MPT',()=>{
 const {s,p}=fixture(),r=authenticateTargetState(s,p);
 assert.equal(r.accounts.rules.storage[p.configSlot],p.baselineConfigWords[0]);
 assert.equal(Object.keys(r.accounts.rules.storage).length,4);
 assert.equal(r.accounts.rules.storage[hex(BigInt(p.configSlot)+1n)],hex(0));
 assert.equal(r.accounts.root.storage[p.rootRecordSlot].slice(0,4),'0x03');
});
test('missing exact trie node reports original subject/key and hash',()=>{
 const {s,p}=fixture();s.inventory.nodes.pop();
 assert.throws(()=>authenticateTargetState(s,p),e=>e.code==='MISSING_TRIE_NODE'&&e.details.nodeHash===s.checkpoint.stateRoot&&e.details.role==='root');
});
test('code preimage must exist and match profile identity',()=>{
 const {s,p}=fixture();s.inventory.codes.pop();
 assert.throws(()=>authenticateTargetState(s,p),e=>e.code==='CODE_PREIMAGE_MISSING'&&e.details.role==='rules');
 const fresh=fixture();fresh.p.manifest.contracts.find(x=>x.role==='root').runtimeHash=hex(1);
 assert.throws(()=>authenticateTargetState(fresh.s,fresh.p),e=>e.code==='CONTRACT_CODE_IDENTITY');
});
test('wrong original root, corrupt node and malformed preimages fail closed',()=>{
 const {s,p}=fixture();s.checkpoint.stateRoot=hex(2);
 assert.throws(()=>authenticateTargetState(s,p),/MISSING_TRIE_NODE/);
 const f=fixture();f.s.inventory.nodes[0]='0x00';
 assert.throws(()=>authenticateTargetState(f.s,f.p));
 const g=fixture();g.s.inventory.nodes=['0xz'];
 assert.throws(()=>authenticateTargetState(g.s,g.p));
});

test('rejects noncanonical RLP payload inside storage leaves',()=>{
 const {s,p}=fixture({storage:true});
 assert.throws(()=>authenticateTargetState(s,p),/NON_CANONICAL_STORAGE_RLP/);
});
test('rejects noncanonical RLP payload inside account leaves',()=>{
 const {s,p}=fixture({account:true});
 assert.throws(()=>authenticateTargetState(s,p),/NON_CANONICAL_ACCOUNT_RLP/);
});
