// SPDX-License-Identifier: Apache-2.0
import {parseArgs} from 'node:util';
import {checkPolicyName, openCase} from '../src/case/index.mjs';

function textFor(report) {
  const {inspection: i, comparison: c, verification: v, policy: p} = report;
  const lines = [
    i.id + ' · chain ' + i.chainId + ' · block ' + i.history.blockNumber,
    'Subject ' + i.subject.transactionHash,
    'Intervention ' + i.intervention.field + ' ' + (i.intervention.from ?? i.intervention.fromBaseUnits) +
      ' → ' + (i.intervention.to ?? i.intervention.toBaseUnits),
    'Recorded ACTUAL ' + (c.actual.status ?? c.actual.subjectStatus) + ' · gas ' + (c.actual.gasUsed ?? c.actual.subjectGasUsed),
    'Recorded BRANCH ' + (c.branch.status ?? c.branch.subjectStatus) + ' · gas ' + (c.branch.gasUsed ?? c.branch.subjectGasUsed),
  ];
  for (const [field, unit] of Object.entries(c.units)) {
    const suffix = typeof unit === 'string' ? ' ' + unit : ' base units (decimals ' + unit.decimals + ', ' + unit.asset + ')';
    lines.push(field + ' ' + c.actual[field] + ' → ' + c.branch[field] + suffix);
  }
  for (const dimension of v.dimensions) {
    lines.push(dimension.id);
    for (const check of dimension.checks) {
      lines.push('  ' + check.name + ' · ' + check.status + (check.basis ? ' · ' + check.basis : '') + ' · ' + check.scope);
    }
  }
  for (const [name, result] of Object.entries(v.details)) {
    lines.push(name + ' · ' + result.status + ' · ' + (result.terminal ?? result.outcome ?? result.reason));
  }
  lines.push('Policy ' + p.policy + ' · ' + p.verdict + ' · ' + p.reason, 'Fresh EVM replay 0');
  return lines.join('\n');
}

export async function caseCommand(args) {
  const {values, tokens} = parseArgs({args, strict: true, tokens: true, options: {
    id: {type: 'string'}, input: {type: 'string'}, policy: {type: 'string'},
    'verify-pack-root': {type: 'string'}, 'trusted-block-hash': {type: 'string'},
    'trusted-checkpoint': {type: 'string'}, 'ethereum-verifier-root': {type: 'string'}, json: {type: 'boolean'},
  }});
  if (new Set(tokens.map(token => token.name)).size !== tokens.length) throw new Error('DUPLICATE_OPTION');
  const chosenPolicy = values.policy ?? 'recorded-review';
  checkPolicyName(chosenPolicy);
  const handle = openCase({id: values.id, input: values.input});
  const checks = [];
  if (values['verify-pack-root'] || values['trusted-block-hash']) checks.push('pair03-recorded-integrity');
  if (chosenPolicy === 'ethereum-consensus' || values['trusted-checkpoint'] || values['ethereum-verifier-root']) checks.push('ethereum-consensus');
  if (chosenPolicy === 'independent-native-replay') checks.push('independent-native-replay');
  const verification = await handle.verify({checks, verifyPackRoot: values['verify-pack-root'],
    trustedBlockHash: values['trusted-block-hash'], trustedCheckpoint: values['trusted-checkpoint'],
    ethereumVerifierRoot: values['ethereum-verifier-root']});
  const policy = handle.evaluatePolicy(chosenPolicy, verification);
  const dimensions = verification.dimensions.map(d => d.id === 'policyAcceptance'
    ? {...d, checks: [{name: policy.policy, status: policy.verdict, basis: null, scope: policy.reason, evidence: []}]}
    : d);
  const report = {inspection: handle.inspect(), comparison: handle.compare(),
    verification: {...verification, dimensions}, policy};
  console.log(values.json ? JSON.stringify(report, null, 2) : textFor(report));
  return {ACCEPTED: 0, REJECTED: 2, UNRESOLVED: 3}[policy.verdict];
}
