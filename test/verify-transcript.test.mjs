import assert from 'node:assert/strict'
import { execFile } from 'node:child_process'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'
import { promisify } from 'node:util'

import {
  ENVELOPE_LIFECYCLE,
  buildBranchEvidenceTranscript,
  buildEnvelopeEvidence,
  createCommitment,
  exceptionNone,
  exportBranchEvidenceTranscript,
  makeEnvelopeIdentity,
  makeGasAndFee,
  parseBlockNumber,
  parseDigest,
  parseHash32,
  parseQuantity,
  validationValid,
} from '../core/src/index.mjs'

const run = promisify(execFile)
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const digest = (pair) => pair.repeat(32)
const identity = makeEnvelopeIdentity({
  blockNumber: parseBlockNumber('500'),
  transactionIndex: parseQuantity('4'),
  transactionHash: parseHash32(`0x${digest('11')}`),
})

function unchangedEnvelope() {
  return buildEnvelopeEvidence({
    envelope: identity,
    predecessorStateCommitment: parseDigest(digest('21')),
    validation: validationValid(),
    lifecycle: ENVELOPE_LIFECYCLE.SUCCESS,
    exception: exceptionNone(),
    gasAndFee: makeGasAndFee({ gasLimit: parseQuantity('50000'), gasUsed: parseQuantity('21000'), feePaid: parseQuantity('21000') }),
    logsCommitment: parseDigest(digest('31')),
    successorStateCommitment: parseDigest(digest('22')),
    executionResultCommitment: parseDigest(digest('41')),
  })
}

test('verify-transcript accepts a strictly valid transcript with no divergence', async () => {
  const envelope = unchangedEnvelope()
  const transcript = buildBranchEvidenceTranscript({
    branches: {
      actual: createCommitment(digest('aa'), 'ACTUAL_TEST_BRANCH'),
      counterfactual: createCommitment(digest('bb'), 'COUNTERFACTUAL_TEST_BRANCH'),
    },
    intervention: { kind: 'REPLACE_COMMITTED_INPUT', target: identity },
    actualEnvelopes: [envelope],
    counterfactualEnvelopes: [envelope],
    semanticPairs: [],
  })
  assert.deepEqual(transcript.body.divergence, {
    lifecycle: { status: 'NONE' },
    stateCommitment: { status: 'NONE' },
    semantic: { status: 'NONE' },
  })

  const directory = await mkdtemp(join(tmpdir(), 'rhook-generic-transcript-'))
  const path = join(directory, 'transcript.json')
  try {
    await writeFile(path, exportBranchEvidenceTranscript(transcript))
    const output = JSON.parse((await run(process.execPath, ['scripts/verify-transcript.mjs', path], { cwd: root })).stdout)
    assert.equal(output.status, 'PASS')
    assert.deepEqual(output.divergence, transcript.body.divergence)
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})
