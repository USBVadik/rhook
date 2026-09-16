import assert from 'node:assert/strict'
import { readFile, mkdir, writeFile } from 'node:fs/promises'
import { dirname, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  exportBranchEvidenceTranscript,
  verifyBranchEvidenceTranscript,
} from '../../core/src/index.mjs'
import {
  buildTranscriptFromExecutedBranches,
  executeInstrumentedBlock,
} from '../../host/src/index.mjs'

const BLOCK_NUMBER = '12500000'
const ENDPOINT_ADDRESS = '0x866a585978179d2a08f442fedba2b7d5035c54c2'
const SLOT_ZERO = `0x${'00'.repeat(32)}`
const CANONICAL_TRANSACTION_HASHES = Object.freeze([
  '0x2a5c9da80dfdef3fc22e8d26732ddd036d719d387ad49c0dd2af9828e85095e6',
  '0xbad4e406677d96e1338e05025aaeb3ed96f6c10e2817f8319ed15bcbf0d42442',
  '0x0261468b1e0aa7b85b9b96e7da166274c2f102b881344c567459f1e629eb58bb',
])
const GAS_LIMITS = Object.freeze([100_000n, 100_000n, 21_000n])
const INITIAL_STATE_ROOT = '0x3609c156e84f18d032925d9e5e1c5dbeee02fc4d507988b9401b8148054614b3'
// This fixture drives the public execution port; it is not an EVM implementation.
// These are retained observations from the canonical synthetic EVM run. The host
// must derive fresh evidence from the emitted lifecycle events rather than load
// or copy the pinned transcript.
const BRANCH = Object.freeze({
  ACTUAL: Object.freeze({
    transactionHashes: CANONICAL_TRANSACTION_HASHES,
    stateRoots: Object.freeze([
      INITIAL_STATE_ROOT,
      '0xf9b338be3544c951ad26bc6db224ae955875092af08df3cc07fb9d5c09cdd1fe',
      '0x018d8ab2c6cf1384cbd45ddfd94e639a1a6e3c19d91a571ed79eb643fe454aba',
      '0x0a72eaf2e55e657f1d076766e79b0d09a2cfb9c692d03c2772e41d280e4be67d',
    ]),
    receiptStatuses: Object.freeze([1, 1, 1]),
    gasUsed: Object.freeze([43_267n, 23_141n, 21_000n]),
    exceptions: Object.freeze([null, null, null]),
    semanticValue: `0x${'00'.repeat(31)}01`,
    totalGasUsed: 87_408n,
    receiptsRoot: '0x7eb0e7898b966dfc7bc82fcb883e7bc0666eeadab19fcdbde469134b335fc7aa',
    finalStateRoot: '0xd6b82d655b1ee04f45f0856432da88e6ecbb76a380f6dd28412f19ad421241cc',
  }),
  COUNTERFACTUAL: Object.freeze({
    transactionHashes: Object.freeze([
      '0x6cea722000ab2f39949126f2dc5c59ee479b3e01d3e3a8037e42fa41be4fcb41',
      CANONICAL_TRANSACTION_HASHES[1],
      CANONICAL_TRANSACTION_HASHES[2],
    ]),
    stateRoots: Object.freeze([
      INITIAL_STATE_ROOT,
      '0x280b78a24865e8780cfb1585d8e27953ee6f013729adbc9c3f85e2c2b63d31df',
      '0xfbabe216e4b9eb1c27a63d2134e9ecc00d1b65e0dbc5b3bf42be80a3ccd96533',
      '0xb1b49eb32dd88da52c9ee33a6489e7d13febbf6d5d04d2bedcd199a083479c8e',
    ]),
    receiptStatuses: Object.freeze([1, 0, 1]),
    gasUsed: Object.freeze([43_267n, 23_148n, 21_000n]),
    exceptions: Object.freeze([null, 'revert', null]),
    semanticValue: `0x${'00'.repeat(31)}02`,
    totalGasUsed: 87_415n,
    receiptsRoot: '0x6b4829bf3d0fe27f04fa056da3b7ae94d7735542b32e9264c49761646a39a7db',
    finalStateRoot: '0x5342871900f5d6b1661083ed60fbd3676b61d9f2595910e7a1d07a77bf06ff2c',
  }),
})

function bytes32(hex) {
  assert.match(hex, /^0x[0-9a-f]{64}$/)
  return Uint8Array.from(Buffer.from(hex.slice(2), 'hex'))
}

class Events {
  #listeners = new Map()

  on(name, listener) {
    const listeners = this.#listeners.get(name) ?? []
    listeners.push(listener)
    this.#listeners.set(name, listeners)
  }

  off(name, listener) {
    this.#listeners.set(name, (this.#listeners.get(name) ?? []).filter((candidate) => candidate !== listener))
  }

  async emit(name, payload) {
    for (const listener of this.#listeners.get(name) ?? []) {
      await new Promise((done) => listener(payload, done))
    }
  }
}

function createBranchFixture(mode) {
  assert.ok(mode === 'ACTUAL' || mode === 'COUNTERFACTUAL')
  const branch = BRANCH[mode]
  const events = new Events()
  const stateManager = {
    root: bytes32(INITIAL_STATE_ROOT),
    async getStateRoot() { return this.root },
  }
  const transactions = branch.transactionHashes.map((transactionHash, index) => Object.freeze({
    gasLimit: GAS_LIMITS[index],
    hash: () => bytes32(transactionHash),
  }))
  const block = Object.freeze({ header: Object.freeze({ number: BigInt(BLOCK_NUMBER) }), transactions: Object.freeze(transactions) })
  const canonicalEnvelopeIdentities = Object.freeze(CANONICAL_TRANSACTION_HASHES.map((transactionHash, transactionIndex) => Object.freeze({
    blockNumber: BLOCK_NUMBER,
    transactionIndex: String(transactionIndex),
    transactionHash,
  })))
  const vm = { events, stateManager }

  const runBlock = async (target, options) => {
    assert.equal(target, vm)
    assert.equal(options.block, block)
    assert.equal(options.generate, true)
    assert.equal(options.skipHeaderValidation, true)
    assert.equal(options.skipBlockValidation, true)
    assert.equal(options.setHardfork, true)
    assert.equal(options.forcedHistoricalEnvelopeReplay, mode === 'COUNTERFACTUAL')

    const results = []
    const receipts = []
    for (let index = 0; index < transactions.length; index += 1) {
      const transaction = transactions[index]
      await target.events.emit('beforeTx', transaction)
      target.stateManager.root = bytes32(branch.stateRoots[index + 1])
      const exception = branch.exceptions[index]
      const execResult = {
        returnValue: new Uint8Array(),
        logs: [],
        ...(exception === null ? {} : { exceptionError: { error: exception } }),
      }
      const result = {
        transaction,
        totalGasSpent: branch.gasUsed[index],
        amountSpent: branch.gasUsed[index],
        receipt: { status: branch.receiptStatuses[index] },
        execResult,
      }
      await target.events.emit('afterTx', result)
      results.push(result)
      receipts.push(result.receipt)
    }
    return {
      results,
      receipts,
      gasUsed: branch.totalGasUsed,
      receiptsRoot: bytes32(branch.receiptsRoot),
      stateRoot: bytes32(branch.finalStateRoot),
    }
  }

  const observeSemantic = async ({ envelopeIndex, successorStateRoot }) => {
    if (envelopeIndex !== 2) return []
    assert.equal(successorStateRoot, branch.stateRoots[3])
    return [{
      endpointAddress: ENDPOINT_ADDRESS,
      selector: '0x',
      source: { kind: 'STORAGE_SLOT', slot: SLOT_ZERO },
      presence: 'PRESENT',
      value: branch.semanticValue,
    }]
  }

  return {
    vm,
    block,
    mode,
    canonicalEnvelopeIdentities,
    observeSemantic,
    runBlock,
    intervention: Object.freeze({
      kind: 'REPLACE_TRANSACTION_CALLDATA',
      target: Object.freeze({ ...canonicalEnvelopeIdentities[0] }),
    }),
  }
}

export async function generateMinimalTranscript() {
  const actualFixture = createBranchFixture('ACTUAL')
  const counterfactualFixture = createBranchFixture('COUNTERFACTUAL')
  const actual = await executeInstrumentedBlock({ ...actualFixture, evidenceEnabled: true })
  const counterfactual = await executeInstrumentedBlock({ ...counterfactualFixture, evidenceEnabled: true })
  const transcript = buildTranscriptFromExecutedBranches({
    actual,
    counterfactual,
    intervention: actualFixture.intervention,
  })
  const verification = verifyBranchEvidenceTranscript(transcript)
  assert.equal(verification.valid, true, JSON.stringify(verification.findings))
  return Object.freeze({ transcript, text: exportBranchEvidenceTranscript(transcript) })
}

const modulePath = fileURLToPath(import.meta.url)
if (process.argv[1] && resolve(process.argv[1]) === modulePath) {
  const outputPath = resolve(process.cwd(), process.argv[2] ?? '.rhook/minimal-transcript.json')
  const generated = await generateMinimalTranscript()
  const pinned = await readFile(new URL('./transcript.json', import.meta.url), 'utf8')
  assert.equal(generated.text, pinned, 'generated transcript differs from the pinned protocol-neutral fixture')
  await mkdir(dirname(outputPath), { recursive: true })
  await writeFile(outputPath, generated.text)
  console.log(JSON.stringify({
    status: 'PASS',
    output: relative(process.cwd(), outputPath),
    matchesPinnedTranscript: true,
    declaredEnvelopes: generated.transcript.body.coverage.declaredEnvelopes,
    divergence: generated.transcript.body.divergence,
  }, null, 2))
}
