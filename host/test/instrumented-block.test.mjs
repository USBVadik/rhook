import assert from 'node:assert/strict'
import test from 'node:test'

import { verifyEnvelopeEvidence } from '../../core/src/index.mjs'
import { executeInstrumentedBlock } from '../src/index.mjs'

const bytes = (value, length = 32) => Uint8Array.from({ length }, () => value)
const hex = (value) => `0x${Buffer.from(value).toString('hex')}`

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
      await new Promise((resolve) => listener(payload, resolve))
    }
  }

  count(name) {
    return (this.#listeners.get(name) ?? []).length
  }
}

function fixture() {
  const events = new Events()
  const stateManager = { root: bytes(1), getStateRoot: async function getStateRoot() { return this.root } }
  const transactions = [
    { gasLimit: 50_000n, hash: () => bytes(0x11) },
    { gasLimit: 50_000n, hash: () => bytes(0x12) },
  ]
  const block = { header: { number: 100n }, transactions }
  const identities = transactions.map((transaction, transactionIndex) => ({ blockNumber: '100', transactionIndex: String(transactionIndex), transactionHash: hex(transaction.hash()) }))
  const vm = { events, stateManager }
  const runBlock = async (target, options) => {
    assert.equal(options.block, block)
    const results = []
    const receipts = []
    for (let index = 0; index < transactions.length; index += 1) {
      const transaction = transactions[index]
      await target.events.emit('beforeTx', transaction)
      target.stateManager.root = bytes(index + 2)
      const reverted = index === 1
      const execResult = { returnValue: new Uint8Array(), logs: [], ...(reverted ? { exceptionError: { error: 'revert' } } : {}) }
      const result = { transaction, totalGasSpent: BigInt(21_000 + index), amountSpent: BigInt(21_000 + index), receipt: { status: reverted ? 0 : 1 }, execResult }
      await target.events.emit('afterTx', result)
      results.push(result)
      receipts.push(result.receipt)
    }
    return { results, receipts, gasUsed: 42_001n, receiptsRoot: bytes(0x21), stateRoot: target.stateManager.root }
  }
  return { vm, block, canonicalEnvelopeIdentities: identities, runBlock }
}

test('host captures executed lifecycle and state boundaries through an injected runBlock port', async () => {
  const input = fixture()
  const result = await executeInstrumentedBlock({ ...input, mode: 'ACTUAL', evidenceEnabled: true })
  assert.deepEqual(result.envelopes.map((record) => record.body.execution.lifecycle), ['SUCCESS', 'REVERT'])
  assert.equal(result.envelopes.every((record) => verifyEnvelopeEvidence(record).valid), true)
  assert.equal(result.stateBindings[0].predecessor.stateRoot, hex(bytes(1)))
  assert.equal(result.stateBindings[0].successor.stateRoot, hex(bytes(2)))
  assert.equal(input.vm.events.count('beforeTx'), 0)
  assert.equal(input.vm.events.count('afterTx'), 0)
})

test('evidence-disabled execution attaches no persistent listeners and reserved options fail before execution', async () => {
  const input = fixture()
  const result = await executeInstrumentedBlock({ ...input, mode: 'COUNTERFACTUAL', evidenceEnabled: false })
  assert.equal(result.evidenceEnabled, false)
  assert.equal('envelopes' in result, false)
  assert.equal(input.vm.events.count('beforeTx'), 0)
  await assert.rejects(
    () => executeInstrumentedBlock({ ...fixture(), mode: 'ACTUAL', runOptions: { forcedHistoricalEnvelopeReplay: true } }),
    (error) => error.code === 'RESERVED_RUN_OPTION',
  )
})

test('a non-extensible execution error is rethrown unchanged rather than masked by sidecar attachment', async () => {
  const input = fixture()
  const original = Object.freeze(Object.assign(new Error('nonce mismatch'), { code: 'INVALID_NONCE' }))
  const runBlock = async (vm) => {
    await vm.events.emit('beforeTx', input.block.transactions[0])
    throw original
  }
  await assert.rejects(
    () => executeInstrumentedBlock({ ...input, runBlock, mode: 'ACTUAL', evidenceEnabled: true }),
    (error) => error === original && !Object.hasOwn(error, 'runtimeEvidence'),
  )
})
