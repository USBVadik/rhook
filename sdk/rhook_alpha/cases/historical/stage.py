"""Closed, hash-checked derivative composition; accepted engine files stay intact."""
from pathlib import Path
from developer.files import load, require, sha


def once(text, old, new):
    require(text.count(old) == 1, 'HISTORICAL_STAGING_BOUNDARY: '+old[:70])
    return text.replace(old,new)


def compose(sdk, prestate, worker):
    here=Path(__file__).resolve().parent
    for n,pin in load(here/'staging-pins.json').items():
        require(sha(sdk/n)==pin,'RETAINED_STAGING_SOURCE_CHANGED: '+n)
    p=prestate/'runner.go';text=p.read_text()
    signature='func runNativeBlock(c *Candidate, b *Bridge, intervention func(*Bridge) (*LPWriteRecord, error)) (out *CalibrationResult, err error) {'
    wrapper='''func runNativeBlock(c *Candidate, b *Bridge, intervention func(*Bridge) (*LPWriteRecord, error)) (*CalibrationResult, error) {
 var patch *LPWriteRecord
 var apply func(*Bridge) error
 if intervention != nil { apply = func(b *Bridge) error { var e error; patch,e=intervention(b); return e } }
 out,e := runNativeBlockWithOverlay(c,b,apply)
 if out != nil { out.Patch=patch }
 return out,e
}
func runNativeBlockWithOverlay(c *Candidate, b *Bridge, intervention func(*Bridge) error) (out *CalibrationResult, err error) {'''
    text=once(text,signature,wrapper)
    text=once(text,'\t\tvar patch *LPWriteRecord\n','')
    text=once(text,'patch, e = intervention(b)','e = intervention(b)')
    text=once(text,'World: world, Patch: patch, Observation: b.observation','World: world, Observation: b.observation')
    p.write_text(text)
    for name in ['main.go','pair.go','main_test.go','pair_test.go']:
        t=(sdk/'rhook_alpha/cases/native'/name).read_text()
        t=t.replace('prestate.LPIntervention','prestate.HistoricalDynamicOff').replace('prestate.CalibrationResult','prestate.HistoricalDynamicResult').replace('prestate.LPWriteRecord','prestate.HistoricalDynamicOverlay')
        t=t.replace('prestate.RunCapsuleLP','prestate.RunHistoricalDynamic').replace('prestate.ValidateCapsuleLP','prestate.ValidateHistoricalDynamic').replace('prestate.CheckCapsuleLP','prestate.CheckHistoricalDynamic')
        t=t.replace('nitro-hookr-lp/0.1','nitro-hookr-historical-dynamic-fee-off/0.1').replace('hookr-1.lp-bps/1','hookr-1.historical-dynamic-fee-off/1')
        t=t.replace('b.Patch.Intervention != c.plan.Intervention','!prestate.EqualHistoricalDynamic(b.Patch.Intervention, c.plan.Intervention)')
        t=t.replace('b.Patch.SemanticInitialWrites != 1','b.Patch.SemanticInitialWrites != 2')
        if name=='pair.go':
            t=once(t,'\tClose()\n','\tClose() error\n')
            t=once(t,'return r != nil && r.World', 'return r != nil && r.CalibrationResult != nil && r.Patch == nil && r.World')
            t=once(t,'if b == nil || b.World','if b == nil || b.CalibrationResult == nil || b.World')
            t=once(t,'!b.Patch.OriginalWitnessUnchanged {','!b.Patch.OriginalWitnessUnchanged || b.Patch.OriginalWitnessCommitment != c.plan.Witness || b.Patch.OriginalRoot != c.plan.Checkpoint.StateRoot || b.Patch.InitialRoot == (common.Hash{}) || b.Patch.InitialRoot == c.plan.Checkpoint.StateRoot {')
            for label in ['actual','branch']:
                before='\tif '+('ae != nil || !canonical(a, c.plan)' if label=='actual' else 'be != nil')+' {'
                close='''\tif ce := %s.Close(); ce != nil { out.Terminal="INTERRUPTED_UNVERIFIED"; out.Cause="BRIDGE_CLEANUP_UNCONFIRMED: "+ce.Error(); return out,nil }
'''%label
                t=once(t,before,close+before)
            t=t.replace('map[string]any{"result": a,','map[string]any{"schema": prestate.HistoricalDynamicDomain+"/world", "profile": profile, "result": a,')
            t=t.replace('map[string]any{"result": b,','map[string]any{"schema": prestate.HistoricalDynamicDomain+"/world", "profile": profile, "result": b,')
        if name=='main.go':
            t=once(t,'r := p.Runtime','r := p.Runtime\n if r.PackageSHA != prestate.HistoricalPackageSHA || r.Input != prestate.HistoricalInput || r.Witness != prestate.HistoricalWitness || r.Transactions != 7 || r.Observation.NativeOrdinal != 3 || r.Subject != common.HexToHash("0xbdc353fe6485a1e4e14e6d6fa358d9e7cdd333a986ce0440e7a76fcdb09aa41c") { return c,p,nil,errors.New("EXACT_HISTORICAL_SCOPE") }')
            t=once(t,'type capsuleWorld struct {','type closeSummary struct { count int; failure error }\ntype capsuleWorld struct {\n closed *closeSummary\n didClose bool\n closeError error')
            t=once(t,'func (w *capsuleWorld) Close()                       { w.o.Bridge.Close() }', '''func (w *capsuleWorld) Close() error {
 if !w.didClose { w.didClose=true; w.closeError=prestate.CloseHistoricalBridge(w.o.Bridge); w.closed.count++; w.closed.failure=errors.Join(w.closed.failure,w.closeError) }; return w.closeError
}''')
            t=once(t,'calls := 0','calls := 0\n opened := 0\n closed := &closeSummary{}')
            t=once(t,'o.Bridge.Close()\n\t\treturn c, p, nil, e','e=errors.Join(e,prestate.CloseHistoricalBridge(o.Bridge))\n\t\treturn c, p, nil, e')
            t=once(t,'caps, req, o, e := openInputs(c, p, raw)','caps, req, o, e := openInputs(c, p, raw)\n if errors.Is(e,prestate.ErrHistoricalBridgeCleanup) { closed.failure=errors.Join(closed.failure,e) }')
            t=once(t,'&capsuleWorld{o, req.Runtime, caps.Adapter.Config.Code, phase, &failure}', '&capsuleWorld{o:o,p:req.Runtime,code:caps.Adapter.Config.Code,phase:phase,failure:&failure,closed:closed}')
            t=once(t,'return &capsuleWorld{o:o,','opened++\n return &capsuleWorld{o:o,')
            t=once(t,'n := map[string]any{"operationCommitment": b["operationCommitment"], "result": result}', '''if closed.failure != nil || closed.count != opened { result.Terminal="INTERRUPTED_UNVERIFIED"; result.Cause+="; BRIDGE_CLEANUP_UNCONFIRMED" }
 n := map[string]any{"operationCommitment": b["operationCommitment"], "result": result, "profile":profile, "schema":prestate.HistoricalDynamicDomain+"/completion", "ownedBridgesClosed":closed.failure==nil && closed.count==opened}''')
        if name=='pair_test.go':
            t=once(t,'func (w *fakeWorld) Close()                       {}','func (w *fakeWorld) Close() error { return nil }')
            t=t.replace('&prestate.HistoricalDynamicResult{World:', '&prestate.HistoricalDynamicResult{CalibrationResult: &prestate.CalibrationResult{World:')
            t=t.replace('InputCommitment: p.Input}', 'InputCommitment: p.Input}}')
            old='Receipts: types.Receipts{&types.Receipt{Status: 0, CumulativeGasUsed: 123, Logs: []*types.Log{}}}, Patch:'
            t=once(t,old,'Receipts: types.Receipts{&types.Receipt{Status: 0, CumulativeGasUsed: 123, Logs: []*types.Log{}}}}, Patch:')
            t=t.replace('SemanticInitialWrites: 1','SemanticInitialWrites: 2')
            t=t.replace('OriginalWitnessUnchanged: true','OriginalWitnessUnchanged: true, OriginalWitnessCommitment:p.Witness, OriginalRoot:p.Checkpoint.StateRoot, InitialRoot:common.Hash{4}')
        (worker/name).write_text(t)
