import assert from 'node:assert/strict'
import test from 'node:test'

import {
  exportBranchEvidenceTranscript,
  exportEnvelopeEvidence,
  parseStrictEvidenceJson,
  verifyBranchEvidenceTranscriptJson,
  verifyEnvelopeEvidenceJson,
} from '../src/index.mjs'
import { frozenTranscript } from './helpers.mjs'

test('strict text parser preserves canonical valid transcript and envelope JSON', async () => {
  const transcript = await frozenTranscript()
  const transcriptText = exportBranchEvidenceTranscript(transcript)
  const envelopeText = exportEnvelopeEvidence(transcript.body.changedTransitions[0].actual)
  assert.deepEqual(parseStrictEvidenceJson(transcriptText), transcript)
  assert.equal(verifyBranchEvidenceTranscriptJson(transcriptText).valid, true)
  assert.equal(verifyEnvelopeEvidenceJson(envelopeText).valid, true)
})

test('duplicate object keys are rejected before schema validation', async () => {
  const transcript = await frozenTranscript()
  const text = exportBranchEvidenceTranscript(transcript).replace('{"body":', '{"body":null,"body":')
  const result = verifyBranchEvidenceTranscriptJson(text)
  assert.equal(result.valid, false)
  assert.equal(result.findings[0].code, 'STRICT_JSON_SYNTAX')
  assert.match(result.findings[0].detail, /duplicate object key/)
})

test('nested duplicate keys are rejected', () => {
  assert.throws(() => parseStrictEvidenceJson('{"a":{"x":1,"x":2}}'), (error) => error.code === 'STRICT_JSON_SYNTAX')
})

test('floats, exponents, leading zeros, and unsafe integers are rejected', () => {
  for (const text of ['{"a":1.5}', '{"a":1e3}', '{"a":01}', '{"a":-0}', '{"a":9007199254740992}']) assert.throws(() => parseStrictEvidenceJson(text), (error) => error.code === 'STRICT_JSON_SYNTAX')
})

test('trailing content and malformed escapes are rejected', () => {
  assert.throws(() => parseStrictEvidenceJson('{"a":1} trailing'), (error) => error.code === 'STRICT_JSON_SYNTAX')
  assert.throws(() => parseStrictEvidenceJson('{"a":"\\q"}'), (error) => error.code === 'STRICT_JSON_SYNTAX')
})

test('non-string parser input fails explicitly', () => {
  assert.throws(() => parseStrictEvidenceJson({}), (error) => error.code === 'STRICT_JSON_INPUT')
  const result = verifyBranchEvidenceTranscriptJson(null)
  assert.equal(result.valid, false)
  assert.equal(result.findings[0].code, 'STRICT_JSON_INPUT')
})

test('__proto__ is parsed as an inert own key without prototype mutation', () => {
  const parsed = parseStrictEvidenceJson('{"__proto__":{"polluted":true}}')
  assert.equal(Object.getPrototypeOf(parsed), Object.prototype)
  assert.equal(Object.hasOwn(parsed, '__proto__'), true)
  assert.equal(parsed.__proto__.polluted, true)
  assert.equal({}.polluted, undefined)
})
