import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import test from 'node:test'

import {
  buildIntegrationEvidenceBundle,
  buildTranscriptFromExecutedBranches,
  executeInstrumentedBlock,
  exportIntegrationEvidenceBundle,
  verifyIntegrationEvidenceBundle,
} from '../src/index.mjs'
import {
  buildStateBoundary,
  runtimeDigest,
} from '../../runtime/src/index.mjs'

const bytes = (value, length = 32) => Uint8Array.from({ length }, () => value)
const hex = (value) => `0x${Buffer.from(value).toString('hex')}`
const canonical = (value) => {
  if (value === null) return 'null'
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`
  if (typeof value === 'string') return JSON.stringify(value)
  if (typeof value === 'number') return String(value)
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`
}
const sha256Canonical = (value) => createHash('sha256').update(canonical(value)).digest('hex')

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

const CANONICAL_HASHES = Object.freeze([hex(bytes(0x11)), hex(bytes(0x12))])
const INITIAL_ROOT = bytes(0x01)

function branchFixture(mode) {
  const actual = mode === 'ACTUAL'
  const transactionHashes = actual ? CANONICAL_HASHES : [hex(bytes(0x21)), CANONICAL_HASHES[1]]
  const successorRoots = actual ? [bytes(0x02), bytes(0x03)] : [bytes(0x04), bytes(0x05)]
  const events = new Events()
  const stateManager = { root: INITIAL_ROOT, async getStateRoot() { return this.root } }
  const transactions = transactionHashes.map((transactionHash) => ({ gasLimit: 50_000n, hash: () => Uint8Array.from(Buffer.from(transactionHash.slice(2), 'hex')) }))
  const block = { header: { number: 200n }, transactions }
  const canonicalEnvelopeIdentities = CANONICAL_HASHES.map((transactionHash, transactionIndex) => ({
    blockNumber: '200',
    transactionIndex: String(transactionIndex),
    transactionHash,
  }))
  const vm = { events, stateManager }
  const runBlock = async (target) => {
    const results = []
    const receipts = []
    for (let index = 0; index < transactions.length; index += 1) {
      const transaction = transactions[index]
      await target.events.emit('beforeTx', transaction)
      target.stateManager.root = successorRoots[index]
      const reverted = !actual && index === 1
      const result = {
        transaction,
        totalGasSpent: BigInt(21_000 + index),
        amountSpent: BigInt(21_000 + index),
        receipt: { status: reverted ? 0 : 1 },
        execResult: {
          returnValue: new Uint8Array(),
          logs: [],
          ...(reverted ? { exceptionError: { error: 'revert' } } : {}),
        },
      }
      await target.events.emit('afterTx', result)
      results.push(result)
      receipts.push(result.receipt)
    }
    return {
      results,
      receipts,
      gasUsed: 42_001n,
      receiptsRoot: bytes(actual ? 0x31 : 0x32),
      stateRoot: successorRoots.at(-1),
    }
  }
  return { vm, block, mode, canonicalEnvelopeIdentities, runBlock }
}

async function validBundle() {
  const actual = await executeInstrumentedBlock({ ...branchFixture('ACTUAL'), evidenceEnabled: true })
  const counterfactual = await executeInstrumentedBlock({ ...branchFixture('COUNTERFACTUAL'), evidenceEnabled: true })
  const transcript = buildTranscriptFromExecutedBranches({
    actual,
    counterfactual,
    intervention: {
      kind: 'REPLACE_TRANSACTION_CALLDATA',
      target: actual.projection.canonicalEnvelopeIdentities[0],
    },
  })
  return buildIntegrationEvidenceBundle({ actual, counterfactual, transcript })
}

function rehashIntegration(bundle) {
  bundle.integrationCommitment = runtimeDigest('rhook/generic-host-03/integration-evidence/1', bundle.body)
}

function rehashProjectionAndTranscript(bundle, mode) {
  const executionCommitment = runtimeDigest('rhook/generic-host-03/replay-projection/1', bundle.body.replayProjections[mode])
  bundle.body.executionCommitments[mode] = executionCommitment
  bundle.body.coreTranscript.body.branches[mode].digest = executionCommitment
  bundle.body.coreTranscript.transcriptCommitment.digest = sha256Canonical(bundle.body.coreTranscript.body)
  rehashIntegration(bundle)
}

function forged(original, mutate, projectionMode = null) {
  const copy = structuredClone(original)
  mutate(copy)
  if (projectionMode === null) rehashIntegration(copy)
  else rehashProjectionAndTranscript(copy, projectionMode)
  return copy
}

function hasFinding(bundle, code) {
  const verification = verifyIntegrationEvidenceBundle(bundle)
  assert.equal(verification.valid, false)
  assert.ok(verification.findings.some((finding) => finding.code === code), JSON.stringify(verification.findings))
}

test('complete integration bundle verifies and exports canonically', async () => {
  const bundle = await validBundle()
  assert.deepEqual(verifyIntegrationEvidenceBundle(bundle), { valid: true, findings: [] })
  const exported = exportIntegrationEvidenceBundle(bundle)
  assert.equal(exported.endsWith('\n'), true)
  assert.equal(verifyIntegrationEvidenceBundle(JSON.parse(exported)).valid, true)
})

test('self-rehashed empty state-root bindings are rejected', async () => {
  const bundle = await validBundle()
  hasFinding(forged(bundle, (copy) => { copy.body.stateRootBindings.actual = [] }), 'STATE_ROOT_BINDING_COVERAGE_MISMATCH')
})

test('self-rehashed missing and duplicate state-root bindings are rejected', async () => {
  const bundle = await validBundle()
  hasFinding(forged(bundle, (copy) => { copy.body.stateRootBindings.counterfactual.pop() }), 'STATE_ROOT_BINDING_COVERAGE_MISMATCH')
  hasFinding(forged(bundle, (copy) => { copy.body.stateRootBindings.actual.push(structuredClone(copy.body.stateRootBindings.actual[0])) }), 'STATE_ROOT_BINDING_COVERAGE_MISMATCH')
})

test('self-rehashed arbitrary projection fields and lifecycle claims are rejected', async () => {
  const bundle = await validBundle()
  hasFinding(forged(bundle, (copy) => { copy.body.replayProjections.actual.untrusted = true }, 'actual'), 'INVALID_REPLAY_PROJECTION_SHAPE')
  hasFinding(forged(bundle, (copy) => { copy.body.replayProjections.actual.blockNumber = 200 }, 'actual'), 'INVALID_REPLAY_PROJECTION_TYPE')
  hasFinding(forged(bundle, (copy) => {
    copy.body.replayProjections.actual.receiptStatuses[0] = 0
    copy.body.replayProjections.actual.transactionExceptions[0] = 'forged revert'
  }, 'actual'), 'PROJECTION_LIFECYCLE_MISMATCH')
})

test('self-rehashed projection identity and cardinality mismatches are rejected', async () => {
  const bundle = await validBundle()
  hasFinding(forged(bundle, (copy) => { copy.body.replayProjections.counterfactual.canonicalEnvelopeIdentities[1].transactionHash = hex(bytes(0x77)) }, 'counterfactual'), 'PROJECTION_IDENTITY_MISMATCH')
  hasFinding(forged(bundle, (copy) => { copy.body.replayProjections.actual.canonicalEnvelopeIdentities.pop() }, 'actual'), 'PROJECTION_CARDINALITY_MISMATCH')
})

test('self-rehashed detached native state root is rejected', async () => {
  const bundle = await validBundle()
  hasFinding(forged(bundle, (copy) => {
    const detached = buildStateBoundary(bytes(0x09))
    copy.body.stateRootBindings.counterfactual[1].successor = {
      algorithm: detached.algorithm,
      stateRoot: detached.stateRoot,
      commitment: detached.commitment.value,
    }
  }), 'STATE_ROOT_BINDING_MISMATCH')
})

test('self-rehashed bundle requires both exact replay projection modes', async () => {
  const bundle = await validBundle()
  hasFinding(forged(bundle, (copy) => { delete copy.body.replayProjections.counterfactual }), 'INVALID_REPLAY_PROJECTIONS_SHAPE')
})

test('self-rehashed core branch commitment cannot detach from its replay projection', async () => {
  const bundle = await validBundle()
  hasFinding(forged(bundle, (copy) => {
    copy.body.coreTranscript.body.branches.actual.digest = 'cc'.repeat(32)
    copy.body.coreTranscript.transcriptCommitment.digest = sha256Canonical(copy.body.coreTranscript.body)
  }), 'PROJECTION_TRANSCRIPT_COMMITMENT_MISMATCH')
})
