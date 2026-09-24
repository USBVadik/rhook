import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { example, loadArtifacts, checkFrozenArtifacts, unpackVerified, checkIntervention, verifyRecords, checkSemantic } from '../scripts/artifacts.mjs'

const artifacts = loadArtifacts()
const manifest = JSON.parse(artifacts.files['target-case-manifest.json'])
const { expected } = artifacts.reference

test('pinned artifacts, exact semantic results and 642 existing strict evidence records verify', () => {
  assert.equal(checkFrozenArtifacts(artifacts).status, 'PASS')
  assert.deepEqual(expected.actualLifecycle, { SUCCESS:303,REVERT:18,PRE_EXECUTION_INVALIDATED:0 })
  assert.deepEqual(expected.counterfactualLifecycle, { SUCCESS:287,REVERT:21,PRE_EXECUTION_INVALIDATED:13 })
  assert.equal(expected.actualEndpointRoot, '0xd5b84a377ee7ed7b7bf04f88c98988ed0cb5fd0a4679670515a9bac2f0a90193')
  assert.equal(expected.counterfactualEndpointRoot, '0x47601a8a2f7fb0e68778fab892470e7577169c1c2f041df95261f60abe5a5792')
  assert.deepEqual(expected.semantic.deltaActualMinusCounterfactualX128, ['117060586159353039445023394650','11819869034461332460683614049294489639'])
})
test('tampered archive is rejected before unpacking', () => {
  const bytes = readFileSync(join(example, artifacts.integrity.archive.file))
  bytes[30] ^= 1
  assert.throws(() => unpackVerified(bytes, artifacts.integrity.archive), /SHA-256/)
})
test('intervention cannot change a preserved field or replacement calldata', () => {
  const altered = structuredClone(expected.intervention)
  altered.body.messageAfter.Nonce++
  assert.throws(() => checkIntervention(altered, manifest))
  const changed = structuredClone(manifest)
  changed.proposedXPrime.calldata += '00'
  assert.throws(() => checkIntervention(expected.intervention, changed))
})
test('wrong lifecycle counts or missing real invalidation evidence fail', () => {
  assert.throws(() => verifyRecords(artifacts.reference.envelopes.COUNTERFACTUAL, expected.actualLifecycle))
  const records = { ...artifacts.reference.envelopes.COUNTERFACTUAL }
  const name = Object.keys(records).find(k => JSON.parse(records[k]).body.execution.lifecycle === 'PRE_EXECUTION_INVALIDATED')
  delete records[name]
  assert.throws(() => verifyRecords(records, expected.counterfactualLifecycle))
})
test('changed semantic endpoint, delta or terminal root fails frozen checks', () => {
  const s = structuredClone(expected.semantic)
  s.counterfactual.values[0] = '0x01'
  assert.throws(() => checkSemantic(s))
  const changed = structuredClone(artifacts)
  changed.reference.expected.counterfactualEndpointRoot = expected.actualEndpointRoot
  assert.throws(() => checkFrozenArtifacts(changed))
})
test('public source and decompressed data contain no predecessor workspace dependencies', () => {
  const strings = Object.values(artifacts.files).concat(JSON.stringify(artifacts.reference))
  function walk(dir) {
    for (const n of readdirSync(dir)) {
      if (n === 'node_modules') continue
      const p = join(dir, n)
      if (statSync(p).isDirectory()) walk(p)
      else if (!p.endsWith('.gz') && !p.endsWith('artifacts.test.mjs')) strings.push(readFileSync(p, 'utf8'))
    }
  }
  walk(example)
  const text = strings.join('\n')
  const privatePath = new RegExp('[/](?:Users|home)[/]|rhook-(?:native-d1|d2-observational|phase3-case|phase4-divergence)-01')
  assert.doesNotMatch(text, privatePath)
})
