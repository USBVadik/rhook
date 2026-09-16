// Execution is dependency-injected: callers provide a compatible runBlock function.
import {
  buildExecutedEnvelopeEvidence,
  buildInvalidatedEnvelopeEvidence,
  buildSemanticExtractionFromRuntimeObservation,
  canonicalRuntimeJson,
  runtimeDigest,
} from '../../runtime/src/index.mjs'

function requireCondition(condition, code, message) {
  if (!condition) throw Object.assign(new Error(`${code}: ${message}`), { code })
}

function freeze(value) {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    for (const child of Object.values(value)) freeze(child)
    Object.freeze(value)
  }
  return value
}

function hex(value) {
  if (typeof value === 'string') return value
  return `0x${Buffer.from(value).toString('hex')}`
}

function status(receipt) {
  const value = receipt?.status
  if (typeof value === 'bigint') return Number(value)
  return value
}

function exceptionText(result) {
  const exception = result?.execResult?.exceptionError
  return exception === undefined ? null : String(exception.error ?? exception.message ?? exception)
}

export function projectRunBlockResult({ block, result, canonicalEnvelopeIdentities }) {
  requireCondition(result && Array.isArray(result.results) && Array.isArray(result.receipts), 'INVALID_RUN_BLOCK_RESULT', 'runner result lacks transaction results')
  requireCondition(result.results.length === block.transactions.length && result.receipts.length === block.transactions.length, 'RUNNER_RESULT_CARDINALITY_MISMATCH', 'runner result cardinality differs from block')
  requireCondition(canonicalEnvelopeIdentities.length === block.transactions.length, 'ENVELOPE_IDENTITY_CARDINALITY_MISMATCH', 'canonical identity cardinality differs from block')
  return freeze({
    schema: 'generic-engine-host-03-replay-projection/1',
    blockNumber: block.header.number.toString(),
    canonicalEnvelopeIdentities: canonicalEnvelopeIdentities.map((item) => ({ blockNumber: String(item.blockNumber), transactionIndex: String(item.transactionIndex), transactionHash: item.transactionHash })),
    executedTransactionHashes: block.transactions.map((transaction) => hex(transaction.hash())),
    receiptStatuses: result.receipts.map(status),
    transactionGasUsed: result.results.map((item) => item.totalGasSpent.toString()),
    transactionFeesPaid: result.results.map((item) => item.amountSpent.toString()),
    transactionExceptions: result.results.map(exceptionText),
    gasUsed: result.gasUsed.toString(),
    receiptsRoot: hex(result.receiptsRoot),
    finalStateRoot: hex(result.stateRoot),
  })
}

function eventListener(work, captureFailure) {
  return (payload, next) => {
    Promise.resolve().then(() => work(payload)).catch(captureFailure).finally(() => next?.())
  }
}

function removeListener(events, name, listener) {
  if (typeof events.off === 'function') events.off(name, listener)
  else if (typeof events.removeListener === 'function') events.removeListener(name, listener)
}

async function maybeAttachPreExecutionInvalidation({
  error,
  vm,
  block,
  mode,
  canonicalEnvelopeIdentities,
  before,
  after,
  classifyPreExecutionFailure,
}) {
  if (classifyPreExecutionFailure === null) return
  const failedIndex = before.length - 1
  if (failedIndex < 0 || after.length !== failedIndex) return

  const predecessorStateRoot = before[failedIndex].stateRoot
  try {
    if (hex(await vm.stateManager.getStateRoot()) !== predecessorStateRoot) return
    const decision = await classifyPreExecutionFailure(Object.freeze({
      error,
      mode,
      envelopeIndex: failedIndex,
      envelopeIdentity: Object.freeze({ ...canonicalEnvelopeIdentities[failedIndex] }),
    }))
    if (
      decision === null
      || !decision
      || decision.kind !== 'PRE_EXECUTION_VALIDATION'
      || typeof decision.classification !== 'string'
      || decision.classification.trim().length === 0
      || Object.keys(decision).sort().join(',') !== 'classification,kind'
    ) return
    if (hex(await vm.stateManager.getStateRoot()) !== predecessorStateRoot) return

    const identity = canonicalEnvelopeIdentities[failedIndex]
    const invalidation = buildInvalidatedEnvelopeEvidence({
      blockNumber: identity.blockNumber,
      transactionIndex: identity.transactionIndex,
      transactionHash: identity.transactionHash,
      gasLimit: block.transactions[failedIndex].gasLimit,
      stateRoot: predecessorStateRoot,
      classification: decision.classification,
    })
    if ((typeof error === 'object' || typeof error === 'function') && error !== null && Object.isExtensible(error)) {
      Object.defineProperty(error, 'runtimeEvidence', { value: invalidation, enumerable: false })
    }
  } catch {
    // Evidence collection must never replace the execution engine's original error.
  }
}

export async function executeInstrumentedBlock({
  vm,
  block,
  mode,
  canonicalEnvelopeIdentities,
  evidenceEnabled = true,
  observeSemantic = null,
  runBlock,
  runOptions = {},
  classifyPreExecutionFailure = null,
}) {
  requireCondition(vm?.events && vm?.stateManager, 'INVALID_VM_PORT', 'VM with events and state manager required')
  requireCondition(mode === 'ACTUAL' || mode === 'COUNTERFACTUAL', 'INVALID_EXECUTION_MODE', 'mode must be ACTUAL or COUNTERFACTUAL')
  requireCondition(Array.isArray(canonicalEnvelopeIdentities) && canonicalEnvelopeIdentities.length === block.transactions.length, 'ENVELOPE_IDENTITY_CARDINALITY_MISMATCH', 'one canonical identity per transaction required')
  requireCondition(observeSemantic === null || typeof observeSemantic === 'function', 'INVALID_SEMANTIC_OBSERVER', 'semantic observer must be a function or null')
  requireCondition(typeof runBlock === 'function', 'INVALID_RUN_BLOCK_PORT', 'a compatible runBlock function is required')
  requireCondition(classifyPreExecutionFailure === null || typeof classifyPreExecutionFailure === 'function', 'INVALID_PRE_EXECUTION_CLASSIFIER', 'pre-execution classifier must be a function or null')

  const reservedRunOptions = ['block', 'generate', 'skipHeaderValidation', 'skipBlockValidation', 'setHardfork', 'forcedHistoricalEnvelopeReplay']
  for (const key of reservedRunOptions) requireCondition(!Object.hasOwn(runOptions, key), 'RESERVED_RUN_OPTION', `${key} is controlled by the host`)
  const options = {
    ...runOptions,
    block,
    generate: true,
    skipHeaderValidation: true,
    skipBlockValidation: true,
    setHardfork: true,
    forcedHistoricalEnvelopeReplay: mode === 'COUNTERFACTUAL',
  }
  if (!evidenceEnabled) {
    const result = await runBlock(vm, options)
    const projection = projectRunBlockResult({ block, result, canonicalEnvelopeIdentities })
    return freeze({ evidenceEnabled: false, projection, executionCommitment: runtimeDigest('rhook/generic-host-03/replay-projection/1', projection) })
  }

  const before = []
  const after = []
  let listenerFailure = null
  const captureFailure = (error) => { listenerFailure ??= error }
  const beforeListener = eventListener(async (transaction) => {
    const index = before.length
    requireCondition(index < block.transactions.length, 'UNEXPECTED_BEFORE_TX', 'too many beforeTx events')
    before.push({ index, executedTransactionHash: hex(transaction.hash()), stateRoot: hex(await vm.stateManager.getStateRoot()) })
  }, captureFailure)
  const afterListener = eventListener(async (event) => {
    const index = after.length
    requireCondition(index < before.length, 'UNEXPECTED_AFTER_TX', 'afterTx arrived without beforeTx')
    const successorStateRoot = hex(await vm.stateManager.getStateRoot())
    const observations = observeSemantic === null
      ? []
      : await observeSemantic({ mode, envelopeIndex: index, event, stateManager: vm.stateManager, successorStateRoot })
    requireCondition(Array.isArray(observations), 'INVALID_SEMANTIC_OBSERVER_RESULT', 'semantic observer must return an array')
    after.push({ index, event, successorStateRoot, observations })
  }, captureFailure)

  vm.events.on('beforeTx', beforeListener)
  vm.events.on('afterTx', afterListener)
  let result
  try {
    result = await runBlock(vm, options)
  } catch (error) {
    if (listenerFailure) throw listenerFailure
    await maybeAttachPreExecutionInvalidation({
      error,
      vm,
      block,
      mode,
      canonicalEnvelopeIdentities,
      before,
      after,
      classifyPreExecutionFailure,
    })
    throw error
  } finally {
    removeListener(vm.events, 'beforeTx', beforeListener)
    removeListener(vm.events, 'afterTx', afterListener)
  }
  if (listenerFailure) throw listenerFailure
  requireCondition(before.length === block.transactions.length && after.length === block.transactions.length, 'EXECUTION_EVENT_CARDINALITY_MISMATCH', 'runner lifecycle events do not cover every transaction')

  const integrations = []
  const semanticExtractions = []
  for (let index = 0; index < block.transactions.length; index += 1) {
    const identity = canonicalEnvelopeIdentities[index]
    const event = after[index].event
    const integration = buildExecutedEnvelopeEvidence({
      blockNumber: identity.blockNumber,
      transactionIndex: identity.transactionIndex,
      transactionHash: identity.transactionHash,
      executedTransactionHash: before[index].executedTransactionHash,
      gasLimit: event.transaction.gasLimit,
      gasUsed: event.totalGasSpent,
      feePaid: event.amountSpent,
      predecessorStateRoot: before[index].stateRoot,
      successorStateRoot: after[index].successorStateRoot,
      receiptStatus: status(event.receipt),
      exception: exceptionText(event),
      returnData: hex(event.execResult?.returnValue ?? new Uint8Array()),
      logs: event.execResult?.logs ?? [],
    })
    integrations.push(integration)
    for (const observation of after[index].observations) {
      semanticExtractions.push({
        envelopeIndex: index,
        extraction: buildSemanticExtractionFromRuntimeObservation({ observation, postStateBoundary: integration.successor, envelopeEvidence: integration.evidence }),
      })
    }
  }
  const projection = projectRunBlockResult({ block, result, canonicalEnvelopeIdentities })
  return freeze({
    evidenceEnabled: true,
    projection,
    executionCommitment: runtimeDigest('rhook/generic-host-03/replay-projection/1', projection),
    envelopes: integrations.map((item) => item.evidence),
    stateBindings: integrations.map((item, index) => ({ envelopeIndex: index, predecessor: item.predecessor, successor: item.successor })),
    semanticExtractions,
  })
}
