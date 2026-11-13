import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile, readdir, stat} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {createStudioModel, parameterValue} from '../studio-model.mjs';
import {comparison, burnTotals, validateRecord, createProvider} from '../provider.mjs';
import {PUBLIC_FILES} from '../public-files.mjs';
import {INTEGRITY_SHA256} from '../data-pins.mjs';
const file = path => new URL('../' + path, import.meta.url);
const json = async path => JSON.parse(await readFile(file(path),'utf8'));
const records = Object.fromEntries(await Promise.all(['a','b','burn'].map(async id => [id,await json('data/'+id+'.json')])));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
test('all publication bytes match the pinned manifest', async () => {
  assert.equal(hash(await readFile(file('data/integrity.json'))),INTEGRITY_SHA256);
  const manifest=await json('data/integrity.json');
  assert.deepEqual(Object.keys(manifest.files),['a.json','b.json','burn.json','catalog.json']);
  for(const [name,sha] of Object.entries(manifest.files)) assert.equal(hash(await readFile(file('data/'+name))),sha);
});
test('three records pass the retained Studio binding and token-flow contract', () => {
  for (const r of Object.values(records)) assert.equal(validateRecord(r),r);
});
test('A/B retain exact accepted identities, economics and same-binary control', () => {
  const {a,b}=records;
  assert.equal(a.projection.resultIdentity,'31573601b30bf407ee8c013262f91e790bfc0edaa3da1ea2a7cbcec94ed431d5');
  assert.equal(b.projection.resultIdentity,'45a426c599cbdf09ae47636556a34e7307c8efe1fad2df36bd20d6803ac44b4d');
  assert.equal(a.provenance.workerSha256,b.provenance.workerSha256);
  assert.deepEqual(a.projection.worlds[0],b.projection.worlds[0]);
  assert.equal(a.projection.commonBootstrapRoot,b.projection.commonBootstrapRoot);
  assert.notEqual(a.projection.requestCommitment,b.projection.requestCommitment);
  assert.deepEqual(a.projection.worlds[1].actions.slice(2).map(a=>a.outerSwapFeePips),[[3802],[3815]]);
  assert.deepEqual(b.projection.worlds[1].actions.slice(2).map(a=>a.outerSwapFeePips),[[4204],[4227]]);
  assert.deepEqual(comparison(a).map(r=>r.delta),['-981579265528','-958773092639']);
  for(const r of [a,b])assert.equal(r.acceptance.originalController,'VERIFY_COMPARE_READ_FINAL_PASS');
});
test('Auto Burn keeps original STOP and distinct later acceptance identities', () => {
  const r=records.burn, s=r.provenance.sidecar;
  assert.equal(r.projection.resultIdentity,'2ab39ec4a6591fb384240afe26d3bb22baadb530243607bc848879012fb89216');
  assert.equal(s.acceptanceIdentity,'e0cd11e4b764a8cf7a4d94db5a5b18b803940f2b3e00c27989ef1ad0c660ad5c');
  assert.equal(r.acceptance.originalController,'COMPARE_STOP');assert.equal(r.acceptance.originalLabResultInstalled,false);
  assert.equal(s.nativeExecutionPerformedNow,false);assert.equal(s.originalNativeExecutionPerformed,true);
  assert.equal(s.controllerRecordRewritten,false);assert.equal(s.quarantineUnchanged,1);
});
test('Auto Burn exact base-unit and quote accounting is reproducible with BigInt', () => {
  const r=records.burn, p=r.projection;
  assert.deepEqual(burnTotals(r).map(t=>t.sentToDeadBaseUnits),['0','15593966598643']);
  assert.deepEqual(burnTotals(r).map(t=>t.supplyDeltaBaseUnits),['0','0']);
  assert.deepEqual(burnTotals(r).map(t=>t.accruedProtocolClaimWei),['403000000000','4403000000000']);
  assert.deepEqual(comparison(r).map(t=>t.delta),['-9827116214347','-9597634977672']);
  assert.deepEqual(comparison(r).map(t=>t.gasDelta),[33702,16546]);
  for(const w of p.tokenFlow.worlds)for(const b of w.buys){assert.equal(BigInt(b.traderDeltaBaseUnits)+BigInt(b.sentToDeadBaseUnits)+BigInt(b.poolManagerDeltaBaseUnits),0n);assert.equal(b.supplyDeltaBaseUnits,'0');}
  assert.equal(p.tokenFlow.viewCalls,60);
  assert.notDeepEqual(r.projection.worlds[0],records.a.projection.worlds[0]);
});
for(const [name,change] of Object.entries({
  'swapped world':r=>r.projection.worlds.reverse(),
  'changed sidecar operation':r=>r.provenance.sidecar.originalOperation='0'.repeat(64),
  'promoted controller PASS':r=>r.acceptance.originalController='VERIFY_COMPARE_READ_FINAL_PASS',
  'claimed fresh sidecar EVM':r=>r.provenance.sidecar.nativeExecutionPerformedNow=true,
  'changed snapshot balance':r=>r.projection.tokenFlow.worlds[1].snapshots[1].values.deadBalance='1',
  'wrong buy transaction':r=>r.projection.tokenFlow.worlds[1].buys[0].transactionHash='0x'+'0'.repeat(64),
  'claimed supply destruction':r=>r.projection.tokenFlow.worlds[1].buys[0].supplyDeltaBaseUnits='-1',
  'independent proof claim':r=>r.projection.independentEVMReexecution=true
}))test('rejects '+name,()=>{const r=structuredClone(records.burn);change(r);assert.throws(()=>validateRecord(r));});
test('draft edits never produce new results or mutate a saved record', () => {
  const m=createStudioModel();m.accept(m.select('a'),records.a);assert.equal(m.resultForDraft,records.a);
  const original=JSON.stringify(records.a);m.edit(d=>d.blocks[0].parameters.snipeTaxPips=1234);
  assert.equal(m.resultForDraft,null);assert.equal(JSON.stringify(records.a),original);
  m.reset();assert.equal(m.resultForDraft,records.a);
  m.edit(d=>d.actions[0].amount='2000000000000000');assert.equal(m.resultForDraft,null);
});
test('late responses and responses for another record are refused', () => {
  const m=createStudioModel(), old=m.select('a'), latest=m.select('burn');
  assert.equal(m.accept(old,records.a),false);assert.equal(m.record,null);
  assert.throws(()=>m.accept(latest,records.b));assert.equal(m.accept(latest,records.burn),true);
  assert.equal(m.accept(old,records.a),false);assert.equal(m.record.id,'burn');
});
test('catalogue preserves 21 blocks and 131 fields without granting execution',async()=>{
  const c=await json('data/catalog.json');assert.equal(c.sdkVersion,'1.6.1');assert.equal(c.blocks.length,21);
  assert.equal(c.blocks.reduce((n,b)=>n+b.parameters.length,0),131);
  assert.equal(c.blocks.filter(b=>b.recordedCoverage==='EXACT_SAVED_CONFIGURATIONS_ONLY').length,3);
  assert.equal(parameterValue({type:'uint-string'},'1000000000000000000000000'),'1000000000000000000000000');
  assert.equal(parameterValue({type:'integer'},'42'),42);
});
test('provider is same-origin static only and fails closed on tampered bytes',async()=>{
  let tamper=false;const paths=[];
  const fake=async(url,options)=>{paths.push(url.pathname);assert.equal(options.credentials,'omit');const name=url.pathname.split('/').at(-1);let bytes=await readFile(file('data/'+name));if(tamper&&name==='a.json')bytes=Buffer.from('{}');return new Response(bytes);};
  const p=createProvider(fake);await p.init();assert.equal((await p.record('a')).id,'a');
  tamper=true;await assert.rejects(p.record('a'),/hash mismatch/);
  await assert.rejects(p.record('../secret'),/Unknown/);assert.equal(paths.length,3);
});
test('deploy allow-list excludes operator material; every static reference resolves',async()=>{
  const html=await readFile(file('index.html'),'utf8');
  for(const match of html.matchAll(/(?:href|src)="\.\/([^"#]+)"/g))assert.ok(PUBLIC_FILES.includes(match[1]),match[1]);
  for(const name of PUBLIC_FILES){const p=file(name);assert.equal((await stat(p)).isFile(),true);assert.ok((await stat(p)).size<100000);}
  const source=(await Promise.all(PUBLIC_FILES.map(n=>readFile(file(n),'utf8')))).join('\n');
  assert.doesNotMatch(source,/AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9_]{20,}/);
  for(const prefix of ['Users','home'])assert.equal(source.includes('/'+prefix+'/'),false);
  assert.doesNotMatch(source,/sqlite|Bearer |api[_-]?key\s*[:=]|BEGIN .*PRIVATE KEY|https?:\/\/[^\s"']+\/v2\//i);
  for(const name of ['app.mjs','provider.mjs','studio-view.mjs'])assert.doesNotMatch(await readFile(file(name),'utf8'),/fetch\(['"]https?:|\/api\/|localStorage|sessionStorage|WebSocket|innerHTML/);
  assert.ok(html.includes('disabled>Run'));
});
test('schemas cover both result versions, token snapshots and sidecar provenance',async()=>{
  const s=await json('schema.json');assert.equal(s.$schema,'https://json-schema.org/draft/2020-12/schema');
  assert.equal(s.$defs.tokenFlow.properties.viewCalls.const,60);
  assert.equal(s.$defs.sidecar.properties.nativeExecutionPerformedNow.const,false);
  assert.equal(s.$defs.record.allOf[0].then.properties.acceptance.properties.originalController.const,'COMPARE_STOP');
});
