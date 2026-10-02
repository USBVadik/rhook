import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { resolve, sep } from 'node:path'
import { parseStrictEvidenceJson } from '../../../core/src/strict-json.mjs'

// Publication integrity only. No profile admission, native replay or execution proof.
const root = resolve(fileURLToPath(new URL('../../../', import.meta.url)))
const here = new URL('./', import.meta.url)
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex')
const expected = {
  query: '65fc23b618fa5012e7c059c270e423b07782f140bb5ad262f88cb2ef5c129288',
  actual: '169f83dd2088f03b0aa26b9d613775fb05ac25b9a548e8d9180931f0f4bb7454',
  branch: '5170c68b9cd2853bf4495599d7b0263165418ddfa4ece0057feba957657bd44d',
  claim: '1cb8488e019b5550d32ea1169b6a7fac72af8f840314709672973661156c33f0',
  claimBytes: 'ee8331c7e4116fd6fce0335519aae5a31b5a9c15f6dc3ab61458bab19c0bec51',
}

// All operands are parsed plain JSON. This bounded encoder checks this publication;
// it is not the retained research implementation or a new public commitment API.
function canonical(value) {
  let count = 0
  function encode(v, depth) {
    assert.ok(++count <= 100000 && depth <= 64, 'canonical resource limit')
    if (v === null || typeof v === 'boolean') return JSON.stringify(v)
    if (typeof v === 'string') {
      assert.ok(!/[^\x00-\x7f]/.test(v), 'non-ASCII string')
      return JSON.stringify(v)
    }
    if (typeof v === 'number') {
      assert.ok(Number.isSafeInteger(v) && !Object.is(v, -0), 'noncanonical number')
      return String(v)
    }
    assert.ok(v && typeof v === 'object', 'non-JSON value')
    if (Array.isArray(v)) return '[' + v.map(x => encode(x, depth + 1)).join(',') + ']'
    return '{' + Object.keys(v).sort().map(k => {
      assert.ok(!/[^\x00-\x7f]/.test(k), 'non-ASCII key')
      return JSON.stringify(k) + ':' + encode(v[k], depth + 1)
    }).join(',') + '}'
  }
  const bytes = Buffer.from(encode(value, 0), 'ascii')
  assert.ok(bytes.length <= 4000000, 'canonical byte limit')
  return bytes
}
const commit = (domain, body) => sha256(canonical({ domain, body }))
async function json(url) {
  const bytes = await readFile(url)
  assert.ok(bytes.length <= 4000000, 'transport byte limit')
  return { bytes, value: parseStrictEvidenceJson(bytes.toString('utf8')) }
}
function wire(object, format, fields) {
  assert.deepEqual(Object.keys(object).sort(), ['format', ...fields].sort(), 'wire fields')
  assert.equal(object.format, format)
  for (const field of fields) assert.match(object[field], /^[0-9a-f]{64}$/, field)
}

const { value: result } = await json(new URL('result.json', here))
let pinsChecked = 0
for (const [relative, pin] of Object.entries(result.includedFiles)) {
  const path = resolve(root, relative)
  assert.ok(!relative.startsWith('/') && path.startsWith(root + sep), 'pin escapes repository')
  const bytes = await readFile(path)
  assert.equal(bytes.length, pin.bytes, relative + ' byte count')
  assert.equal(sha256(bytes), pin.sha256, relative + ' SHA-256')
  pinsChecked++
}

const { bytes: queryBytes, value: query } = await json(new URL('query.json', here))
const { bytes: claimBytes, value: claim } = await json(new URL('claim.json', here))
const components = ['H', 'R', 'C', 'I', 'subject', 'P', 'theta']
wire(query, 'rhook/branch-query/0.2', components.map(k => k + 'Commitment'))
wire(claim, 'rhook/branch-claim/0.2', ['queryCommitment', 'actualResultCommitment', 'branchResultCommitment'])
assert.deepEqual(queryBytes, canonical(query), 'canonical query bytes')
assert.deepEqual(claimBytes, canonical(claim), 'canonical claim bytes')
assert.equal(claimBytes.length, 304)
assert.equal(sha256(claimBytes), expected.claimBytes)
assert.equal(commit('rhook/branch-query/0.2', query), expected.query)
assert.equal(claim.queryCommitment, expected.query)
assert.equal(query.HCommitment, result.excludedHistoryPreimage.componentCommitment)
assert.deepEqual(Object.keys(result.disclosedComponentBodies).sort(), components.filter(k => k !== 'H').sort())
for (const [component, body] of Object.entries(result.disclosedComponentBodies)) {
  assert.equal(commit('rhook/query-component/' + component + '/0.2', body), query[component + 'Commitment'], component)
}
const projected = value => commit('rhook/projected-result/0.2', {
  projectionCommitment: query.PCommitment,
  subjectCommitment: query.subjectCommitment,
  parametersCommitment: query.thetaCommitment,
  value,
})
assert.deepEqual(result.selectedResult, { ACTUAL: 'SUCCESS', BRANCH: 'REVERT' })
assert.equal(projected(result.selectedResult.ACTUAL), expected.actual)
assert.equal(projected(result.selectedResult.BRANCH), expected.branch)
assert.equal(claim.actualResultCommitment, expected.actual)
assert.equal(claim.branchResultCommitment, expected.branch)
assert.equal(commit('rhook/branch-claim/0.2', claim), expected.claim)
assert.equal(result.claimIdentity.claimCommitment, expected.claim)
assert.equal(result.claimIdentity.queryCommitment, expected.query)
assert.equal(result.claimIdentity.actualResultCommitment, expected.actual)
assert.equal(result.claimIdentity.branchResultCommitment, expected.branch)
assert.equal(result.claimIdentity.canonicalClaimBytesSha256, expected.claimBytes)
assert.equal(result.claimIdentity.canonicalClaimByteCount, 304)

console.log(JSON.stringify({
  status: 'PUBLICATION_BINDINGS_PASS', includedPinsChecked: pinsChecked,
  disclosedComponentsChecked: 6, canonicalClaimBytes: 304,
  claimCommitment: expected.claim,
  nativeExecution: false, historyAuthentication: false,
  excludedArchivesVerified: false, retainedABComparisonRerun: false,
}, null, 2))
