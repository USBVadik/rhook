import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {rpcClient,LIMITS} from '../sdk/rhook_alpha/cases/witness/rpc.mjs';
async function fixture(behavior,exercise,limits=LIMITS){
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'rhook-rpc-test-'));let ms=1000,calls=0,closed=false;const starts=[];
  const transport={send:async(body,ctx)=>{calls++;starts.push(ms);return behavior(JSON.parse(body),ctx);},close:()=>{closed=true;}};
  const c=rpcClient(dir,{transport,now:()=>ms,sleep:async n=>{ms+=n;},limits});
  try{await exercise(c,()=>({calls,starts,dir,ms,closed}));}finally{await c.close();fs.rmSync(dir,{recursive:true,force:true});}
  assert(closed);
}
const response=(request,result)=>({status:200,body:Buffer.from(JSON.stringify({jsonrpc:'2.0',id:request.id,result})),headers:Buffer.from('[]')});
test('429 permanently latches the client; no retries or fallback',async()=>{
  await fixture(()=>({status:429,body:Buffer.from('{}'),headers:Buffer.from('[]')}),async(c,state)=>{
    await assert.rejects(c.call('eth_chainId',[]),/HTTP_429/);
    await assert.rejects(c.call('eth_chainId',[]),/HTTP_429/);
    assert.equal(state().calls,1);assert(fs.existsSync(path.join(state().dir,'body-1.bin')));
  });
});
test('read-only allowlist rejects a transaction before dispatch',async()=>{
  await fixture(q=>response(q,'0x1237'),async(c,state)=>{
    await assert.rejects(c.call('eth_sendRawTransaction',['0x01']),/READ_ONLY_METHOD/);assert.equal(state().calls,0);
  });
});
test('starts are paced and request ceiling is enforced',async()=>{
  await fixture(q=>response(q,'0x1237'),async(c,state)=>{
    await c.call('eth_chainId',[]);await c.call('eth_chainId',[]);
    assert(state().starts[1]-state().starts[0]>=334);
    await assert.rejects(c.call('eth_chainId',[]),/RPC_BUDGET/);assert.equal(state().calls,2);
  },{...LIMITS,requests:2});
});
test('JSON-RPC error and null results are terminal',async()=>{
  for(const error of [null,{code:-32000,message:'historical state not available'}])
    await fixture(q=>({...response(q,null),...(error?{body:Buffer.from(JSON.stringify({jsonrpc:'2.0',id:q.id,error}))}:{})}),async(c,state)=>{
      await assert.rejects(c.call('eth_getProof',[]),error?/RPC_ERROR/:/RPC_NULL_RESULT/);assert.equal(state().calls,1);
    });
});
test('wrong ID and duplicate result keys are rejected',async()=>{
  for(const body of ['{"jsonrpc":"2.0","id":99,"result":1}','{"jsonrpc":"2.0","id":1,"result":1,"result":2}'])
    await fixture(()=>({status:200,body:Buffer.from(body),headers:Buffer.from('[]')}),async c=>assert.rejects(c.call('eth_chainId',[])));
});
test('headers are charged to the global byte budget',async()=>{
  await fixture(q=>response(q,'0x1237'),async(c,state)=>{
    await assert.rejects(c.call('eth_chainId',[]),/RESPONSE_(BUDGET|RESERVATION)/);assert.equal(state().calls,1);
  },{...LIMITS,header:1,bytes:response({id:1},'0x1237').body.length+1});
});
test('request timeouts are not interpreted as missing-state capability',async()=>{
  await fixture(()=>({status:null,body:Buffer.alloc(0),headers:Buffer.alloc(0),failure:'REQUEST_TIMEOUT'}),async(c,state)=>{
    await assert.rejects(c.call('eth_getProof',[]),/REQUEST_TIMEOUT/);assert.equal(state().calls,1);
  });
});
