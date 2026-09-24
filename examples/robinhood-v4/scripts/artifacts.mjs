import assert from 'node:assert/strict'
import { readFileSync, mkdirSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { gunzipSync } from 'node:zlib'
import { sha, objectDigest } from './common.mjs'
import { verifyEnvelopeEvidenceJson } from '../../../core/src/index.mjs'

export const example = fileURLToPath(new URL('../', import.meta.url))
export function unpackVerified(bytes, pin) {
  assert.equal(bytes.length, pin.bytes, `${pin.file}: length`)
  assert.equal(sha(bytes), pin.sha256, `${pin.file}: SHA-256`)
  return JSON.parse(gunzipSync(bytes, { maxOutputLength: 64 * 1024 * 1024 }))
}
export function loadArtifacts() {
  const integrity = JSON.parse(readFileSync(join(example, 'case-integrity.json')))
  const files = unpackVerified(readFileSync(join(example, integrity.archive.file)), integrity.archive)
  assert.deepEqual(Object.keys(files).sort(), Object.keys(integrity.files).sort())
  for (const [name, content] of Object.entries(files)) {
    assert(!name.startsWith('/') && !name.split('/').includes('..'))
    assert.equal(Buffer.byteLength(content), integrity.files[name].bytes, name)
    assert.equal(sha(content), integrity.files[name].sha256, name)
  }
  const reference = unpackVerified(readFileSync(join(example, integrity.reference.file)), integrity.reference)
  return { integrity, files, reference }
}
export function writeInputs(directory, files) {
  for (const [name, content] of Object.entries(files)) {
    mkdirSync(dirname(join(directory, name)), { recursive: true })
    writeFileSync(join(directory, name), content, { flag: 'wx' })
  }
}
export function checkIntervention(intervention, manifest) {
  assert.equal(sha(intervention.domain + intervention.bodyJson), intervention.commitmentSha256)
  assert.deepEqual(JSON.parse(intervention.bodyJson), intervention.body)
  const b = intervention.body
  const digestHex = hex => sha(Buffer.from(hex.slice(2), 'hex'))
  assert.equal(b.originalCalldataSha256, digestHex(manifest.X.input))
  assert.equal(b.replacementCalldataSha256, digestHex(manifest.proposedXPrime.calldata))
  const { Data: original, ...before } = b.messageBefore
  const { Data: replacement, ...after } = b.messageAfter
  assert.equal(original, manifest.X.input)
  assert.equal(replacement, manifest.proposedXPrime.calldata)
  assert.deepEqual(before, after)
  assert.deepEqual(b.canonicalEnvelopeIdentity, { blockNumber: manifest.X.block, transactionIndex: manifest.X.index, transactionHash: manifest.X.hash })
}
export function lifecycleTotals(records) {
  return records.reduce((counts, record) => {
    assert(Object.hasOwn(counts, record.body.execution.lifecycle))
    counts[record.body.execution.lifecycle]++
    return counts
  }, { SUCCESS: 0, REVERT: 0, PRE_EXECUTION_INVALIDATED: 0 })
}
export function verifyRecords(serialized, expected) {
  assert.equal(Object.keys(serialized).length, 321)
  const records = Object.values(serialized).map(text => {
    assert.equal(verifyEnvelopeEvidenceJson(text).valid, true)
    return JSON.parse(text)
  })
  assert.deepEqual(lifecycleTotals(records), expected)
  return records
}
export function checkSemantic(semantic) {
  const mod = 1n << 256n
  const delta = []
  for (let i = 0; i < 2; i++) {
    for (const branch of ['actual', 'counterfactual']) {
      const y = (BigInt(semantic[branch].values[i]) - BigInt(semantic.initial.values[i]) + mod) % mod
      assert.equal(y.toString(), semantic[branch].YX128[i])
    }
    delta.push((BigInt(semantic.actual.YX128[i]) - BigInt(semantic.counterfactual.YX128[i])).toString())
  }
  assert.deepEqual(delta, semantic.deltaActualMinusCounterfactualX128)
}
export function checkFrozenArtifacts({ files, reference }) {
  const { expected } = reference
  const manifest = JSON.parse(files['target-case-manifest.json'])
  checkIntervention(expected.intervention, manifest)
  verifyRecords(reference.envelopes.ACTUAL, expected.actualLifecycle)
  verifyRecords(reference.envelopes.COUNTERFACTUAL, expected.counterfactualLifecycle)
  assert.equal(expected.semantic.actual.root, expected.actualEndpointRoot)
  assert.equal(expected.semantic.counterfactual.root, expected.counterfactualEndpointRoot)
  assert.equal(expected.semantic.initial.root, expected.initialRoot)
  checkSemantic(expected.semantic)
  assert.equal(expected.blocks, 50)
  assert.equal(expected.envelopes, 321)
  for (const branch of ['ACTUAL', 'ORIGINAL', 'COUNTERFACTUAL']) {
    assert.equal(expected.nativeBlockDigests[branch].length, 50)
    expected.nativeBlockDigests[branch].forEach((b, i) => { assert.equal(b.number, 70397227 + i); assert.match(b.sha256, /^[0-9a-f]{64}$/) })
  }
  return { status: 'PASS', replayPerformed: false, evidenceRecords: 642, referenceDigest: objectDigest(reference) }
}
