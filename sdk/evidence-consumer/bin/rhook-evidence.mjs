#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
// Modified for the Common Developer Consumer case command.
import {loadEvidencePackage} from '../src/index.mjs';

function argumentsFor(args) {
  let file=null,json=false,requireEstablished=false,expectedSha256;const seen=new Set();
  for (let i=0;i<args.length;i++) {
    const key=args[i];
    if (key.startsWith('--')) {
      if (seen.has(key)) throw Error('ARGUMENT_INVALID');seen.add(key);
      if (key==='--json') json=true;
      else if (key==='--require-established') requireEstablished=true;
      else if (key==='--sha256' && /^[a-f0-9]{64}$/.test(args[i+1]??'')) expectedSha256=args[++i];
      else throw Error('ARGUMENT_INVALID');
    } else {if(file!==null) throw Error('ARGUMENT_INVALID');file=key}
  }
  if (!file) throw Error('ARGUMENT_INVALID');return {file,json,requireEstablished,expectedSha256};
}
const args = process.argv.slice(2);
if (args[0] === 'case' && args.some(arg => arg === '--id' || arg.startsWith('--id='))) {
  try {
    const {caseCommand} = await import('./case-command.mjs');
    process.exitCode = await caseCommand(args.slice(1));
  } catch (error) {
    const reason = error.code ?? 'CASE_INPUT_INVALID';
    if (args.includes('--json')) {
      console.log(JSON.stringify({policy: {verdict: 'REJECTED', reason}}));
    } else {
      console.error('Case rejected: ' + reason);
    }
    process.exitCode = 2;
  }
} else try {
  const options=argumentsFor(process.argv.slice(2));
  const result=loadEvidencePackage(options.file,options.expectedSha256?{expectedSha256:options.expectedSha256}:{});
  if(options.json) console.log(JSON.stringify(result,null,2));
  else if(result.status==='INVALID') console.log(`Evidence rejected: ${result.code}\nConsumer assurance: UNRESOLVED`);
  else {
    const c=result.recordedComparison,n=result.inspection.counts;
    console.log(`Recorded RHOOK evidence — ${c.subject}\nRecorded ACTUAL: ${c.actual}\nRecorded BRANCH: ${c.branch}`);
    console.log(`Local commitment checks: ${result.bindings.status}\nInspection: ${result.inspection.rowCount} rows; ${n.changed} changed, ${n.unchanged} unchanged, ${n.unresolved} unresolved`);
    console.log(`Recorded verifier report: ${result.reportedVerification?.assurance??'NOT_SUPPLIED'} (not independently verified)`);
    console.log('Consumer assurance: UNRESOLVED\nProfile verification context unavailable. No producer authentication or execution proof.');
  }
  process.exitCode=result.status==='INVALID'?2:options.requireEstablished && !result.verification.accepted?3:0;
} catch {
  console.error('Usage: rhook-evidence <package.json> [--sha256 <digest>] [--json] [--require-established]');
  process.exitCode=2;
}
