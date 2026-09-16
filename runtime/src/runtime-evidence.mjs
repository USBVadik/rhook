import { createHash } from 'node:crypto'

import {
  ENVELOPE_LIFECYCLE,
  buildEnvelopeEvidence,
  createCommitment,
  exceptionNone,
  exceptionRevert,
  exceptionValidation,
  makeEndpoint,
  makeEnvelopeIdentity,
  makeExtraction,
  makeGasAndFee,
  notComputed,
  parseAddress,
  parseBlockNumber,
  parseDigest,
  parseHash32,
  parseHexBytes,
  parseQuantity,
  present,
  sourceAccountField,
  sourceCode,
  sourceReturnWord,
  sourceStorageSlot,
  validAbsent,
  validationInvalid,
  validationValid,
} from '../../core/src/index.mjs'

const STATE_DOMAIN = 'rhook/generic-runtime-03/ethereum-state-root/1'
const LOGS_DOMAIN = 'rhook/generic-runtime-03/evm-logs/1'
const RESULT_DOMAIN = 'rhook/generic-runtime-03/evm-execution-result/1'
const INVALIDATION_DOMAIN = 'rhook/generic-runtime-03/pre-execution-invalidation/1'
const HEX_RE = /^0x(?:[0-9a-f]{2})*$/
const ADDRESS_RE = /^0x[0-9a-f]{40}$/

function requireCondition(condition, code, message) {
  if (!condition) throw Object.assign(new Error(`${code}: ${message}`), { code })
}

export function canonicalRuntimeJson(value) {
  if (value === null) return 'null'
  if (Array.isArray(value)) return `[${value.map(canonicalRuntimeJson).join(',')}]`
  if (typeof value === 'string') return JSON.stringify(value)
  if (typeof value === 'number') {
    requireCondition(Number.isSafeInteger(value), 'NONDETERMINISTIC_RUNTIME_VALUE', 'number must be a safe integer')
    return String(value)
  }
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  requireCondition(value && typeof value === 'object', 'NONDETERMINISTIC_RUNTIME_VALUE', 'unsupported value')
  const keys = Object.keys(value).sort()
  return `{${keys.map((key) => {
    requireCondition(value[key] !== undefined, 'UNDEFINED_RUNTIME_VALUE', `undefined field ${key}`)
    return `${JSON.stringify(key)}:${canonicalRuntimeJson(value[key])}`
  }).join(',')}}`
}

export function runtimeDigest(domain, value) {
  requireCondition(typeof domain === 'string' && domain.length > 0, 'INVALID_RUNTIME_DOMAIN', 'non-empty domain required')
  return createHash('sha256').update(`${domain}\u0000${canonicalRuntimeJson(value)}`).digest('hex')
}

function hex(value, label) {
  if (value instanceof Uint8Array) return `0x${Buffer.from(value).toString('hex')}`
  requireCondition(typeof value === 'string' && HEX_RE.test(value), 'INVALID_RUNTIME_HEX', `${label} must be canonical lowercase hex bytes`)
  return value
}

function hash32(value, label) {
  const normalized = hex(value, label)
  requireCondition(normalized.length === 66, 'INVALID_RUNTIME_HASH32', `${label} must be 32 bytes`)
  return normalized
}

function decimal(value, label) {
  requireCondition(value !== undefined && value !== null, 'UNDEFINED_RUNTIME_VALUE', `${label} is absent`)
  if (typeof value === 'bigint') value = value.toString()
  if (typeof value === 'number') {
    requireCondition(Number.isSafeInteger(value) && value >= 0, 'INVALID_RUNTIME_QUANTITY', `${label} is not an unsigned safe integer`)
    value = String(value)
  }
  requireCondition(typeof value === 'string' && /^(?:0|[1-9][0-9]*)$/.test(value), 'INVALID_RUNTIME_QUANTITY', `${label} must be canonical unsigned decimal`)
  return value
}

function token(value, prefix = 'EVM') {
  requireCondition(typeof value === 'string' && value.length > 0, 'INVALID_RUNTIME_CLASSIFICATION', 'classification is absent')
  const normalized = `${prefix}_${value}`.toUpperCase().replace(/[^A-Z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 96)
  requireCondition(/^[A-Z][A-Z0-9_]{0,95}$/.test(normalized), 'INVALID_RUNTIME_CLASSIFICATION', 'classification cannot be normalized')
  return normalized
}

function freeze(value) {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    for (const child of Object.values(value)) freeze(child)
    Object.freeze(value)
  }
  return value
}

export function buildStateBoundary(rawStateRoot) {
  const stateRoot = parseHash32(hash32(rawStateRoot, 'state root'))
  const commitment = parseDigest(runtimeDigest(STATE_DOMAIN, {
    algorithm: 'ETHEREUM_STATE_ROOT_KECCAK256',
    stateRoot: stateRoot.value,
  }))
  return freeze({
    kind: 'EthereumStateBoundary',
    algorithm: 'ETHEREUM_STATE_ROOT_KECCAK256',
    stateRoot: stateRoot.value,
    commitment,
  })
}

export function verifyStateBoundary(boundary) {
  try {
    if (boundary?.kind !== 'EthereumStateBoundary' || boundary.algorithm !== 'ETHEREUM_STATE_ROOT_KECCAK256') return false
    const rebuilt = buildStateBoundary(boundary.stateRoot)
    return rebuilt.commitment.value === boundary.commitment?.value
  } catch {
    return false
  }
}

function normalizeIdentity(frame) {
  return makeEnvelopeIdentity({
    blockNumber: parseBlockNumber(decimal(frame.blockNumber, 'blockNumber')),
    transactionIndex: parseQuantity(decimal(frame.transactionIndex, 'transactionIndex')),
    transactionHash: parseHash32(hash32(frame.transactionHash, 'transactionHash')),
  })
}

function normalizeLogs(logs) {
  requireCondition(Array.isArray(logs), 'INVALID_RUNTIME_LOGS', 'logs must be an array')
  return logs.map((entry, index) => {
    if (Array.isArray(entry) && entry.length === 3) {
      const address = hex(entry[0], `log ${index} address`)
      requireCondition(ADDRESS_RE.test(address), 'INVALID_RUNTIME_LOGS', `log ${index} address must be 20 bytes`)
      requireCondition(Array.isArray(entry[1]), 'INVALID_RUNTIME_LOGS', `log ${index} topics must be an array`)
      return {
        address,
        topics: entry[1].map((topic, topicIndex) => hash32(topic, `log ${index} topic ${topicIndex}`)),
        data: hex(entry[2], `log ${index} data`),
      }
    }
    requireCondition(entry && typeof entry === 'object', 'INVALID_RUNTIME_LOGS', `log ${index} has unsupported shape`)
    const address = hex(entry.address, `log ${index} address`)
    requireCondition(ADDRESS_RE.test(address), 'INVALID_RUNTIME_LOGS', `log ${index} address must be 20 bytes`)
    requireCondition(Array.isArray(entry.topics), 'INVALID_RUNTIME_LOGS', `log ${index} topics must be an array`)
    return {
      address,
      topics: entry.topics.map((topic, topicIndex) => hash32(topic, `log ${index} topic ${topicIndex}`)),
      data: hex(entry.data, `log ${index} data`),
    }
  })
}

function receiptStatus(value) {
  if (typeof value === 'bigint') value = Number(value)
  if (typeof value === 'string' && /^(?:0|1)$/.test(value)) value = Number(value)
  requireCondition(value === 0 || value === 1, 'INVALID_RUNTIME_RECEIPT_STATUS', 'receipt status must be 0 or 1')
  return value
}

export function buildExecutedEnvelopeEvidence(frame) {
  requireCondition(frame && typeof frame === 'object', 'INVALID_RUNTIME_FRAME', 'execution frame required')
  const predecessor = buildStateBoundary(frame.predecessorStateRoot)
  const successor = buildStateBoundary(frame.successorStateRoot)
  const status = receiptStatus(frame.receiptStatus)
  const exceptionText = frame.exception === null ? null : frame.exception
  requireCondition((status === 1) === (exceptionText === null), 'CONTRADICTORY_RUNTIME_LIFECYCLE', 'receipt and exception disagree')
  const returnData = hex(frame.returnData ?? '0x', 'returnData')
  const logs = normalizeLogs(frame.logs ?? [])
  const classification = exceptionText === null ? null : token(String(exceptionText))
  const logsDigest = parseDigest(runtimeDigest(LOGS_DOMAIN, logs))
  const resultProjection = freeze({
    receiptStatus: status,
    exceptionClassification: classification,
    returnData,
    executedTransactionHash: hash32(frame.executedTransactionHash ?? frame.transactionHash, 'executedTransactionHash'),
    gasUsed: decimal(frame.gasUsed, 'gasUsed'),
    feePaid: decimal(frame.feePaid, 'feePaid'),
  })
  const resultDigest = parseDigest(runtimeDigest(RESULT_DOMAIN, resultProjection))
  const dataCommitment = exceptionText !== null && returnData !== '0x'
    ? parseDigest(runtimeDigest(`${RESULT_DOMAIN}/revert-data`, { returnData }))
    : null
  const evidence = buildEnvelopeEvidence({
    envelope: normalizeIdentity(frame),
    predecessorStateCommitment: predecessor.commitment,
    validation: validationValid(),
    lifecycle: status === 1 ? ENVELOPE_LIFECYCLE.SUCCESS : ENVELOPE_LIFECYCLE.REVERT,
    exception: status === 1 ? exceptionNone() : exceptionRevert(classification, dataCommitment),
    gasAndFee: makeGasAndFee({
      gasLimit: parseQuantity(decimal(frame.gasLimit, 'gasLimit')),
      gasUsed: parseQuantity(resultProjection.gasUsed),
      feePaid: parseQuantity(resultProjection.feePaid),
    }),
    logsCommitment: logsDigest,
    successorStateCommitment: successor.commitment,
    executionResultCommitment: resultDigest,
    semanticChangeCommitments: frame.semanticChangeCommitments ?? [],
  })
  return freeze({ evidence, predecessor, successor, logs, resultProjection })
}

export function buildInvalidatedEnvelopeEvidence(frame) {
  requireCondition(frame && typeof frame === 'object', 'INVALID_RUNTIME_FRAME', 'invalidation frame required')
  const state = buildStateBoundary(frame.stateRoot)
  const classification = token(String(frame.classification), 'VALIDATION')
  const logsDigest = parseDigest(runtimeDigest(LOGS_DOMAIN, []))
  const resultDigest = parseDigest(runtimeDigest(INVALIDATION_DOMAIN, { classification, executed: false }))
  const evidence = buildEnvelopeEvidence({
    envelope: normalizeIdentity(frame),
    predecessorStateCommitment: state.commitment,
    validation: validationInvalid(classification),
    lifecycle: ENVELOPE_LIFECYCLE.PRE_EXECUTION_INVALIDATED,
    exception: exceptionValidation(classification),
    gasAndFee: makeGasAndFee({
      gasLimit: parseQuantity(decimal(frame.gasLimit, 'gasLimit')),
      gasUsed: parseQuantity('0'),
      feePaid: parseQuantity('0'),
    }),
    logsCommitment: logsDigest,
    successorStateCommitment: state.commitment,
    executionResultCommitment: resultDigest,
    semanticChangeCommitments: [],
  })
  return freeze({ evidence, predecessor: state, successor: state, logs: [], resultProjection: freeze({ classification, executed: false }) })
}

function sourceDescriptor(source) {
  requireCondition(source && typeof source === 'object', 'INVALID_RUNTIME_SEMANTIC_SOURCE', 'source descriptor required')
  if (source.kind === 'STORAGE_SLOT') return sourceStorageSlot(parseHash32(hash32(source.slot, 'storage slot')))
  if (source.kind === 'RETURN_WORD') return sourceReturnWord(parseHash32(hash32(source.position, 'return word position')))
  if (source.kind === 'ACCOUNT_FIELD') return sourceAccountField(source.field)
  if (source.kind === 'CODE') return sourceCode()
  throw Object.assign(new Error('INVALID_RUNTIME_SEMANTIC_SOURCE: unsupported source kind'), { code: 'INVALID_RUNTIME_SEMANTIC_SOURCE' })
}

function presentValue(source, value) {
  requireCondition(value !== undefined && value !== null, 'UNDEFINED_RUNTIME_VALUE', 'present semantic value is absent')
  if (source.kind === 'STORAGE_SLOT' || source.kind === 'RETURN_WORD') return parseHash32(hash32(value, 'semantic word'))
  if (source.kind === 'CODE' || (source.kind === 'ACCOUNT_FIELD' && source.field === 'code')) return parseHexBytes(hex(value, 'semantic code'))
  if (source.kind === 'ACCOUNT_FIELD') return parseQuantity(decimal(value, `account ${source.field}`))
  throw Object.assign(new Error('INVALID_RUNTIME_SEMANTIC_SOURCE: unsupported present value source'), { code: 'INVALID_RUNTIME_SEMANTIC_SOURCE' })
}

export function buildSemanticExtractionFromRuntimeObservation({ observation, postStateBoundary, envelopeEvidence }) {
  requireCondition(verifyStateBoundary(postStateBoundary), 'INVALID_STATE_BOUNDARY', 'semantic post-state boundary is not verified')
  requireCondition(envelopeEvidence?.body?.execution?.successorStateCommitment === postStateBoundary.commitment.value, 'SEMANTIC_STATE_BINDING_MISMATCH', 'semantic observation is detached from envelope successor state')
  requireCondition(observation && typeof observation === 'object', 'INVALID_RUNTIME_SEMANTIC_OBSERVATION', 'observation required')
  const source = sourceDescriptor(observation.source)
  let presence
  if (observation.presence === 'PRESENT') presence = present(presentValue(observation.source, observation.value))
  else if (observation.presence === 'VALID_ABSENT') {
    requireCondition(observation.value === undefined || observation.value === null, 'INVALID_RUNTIME_SEMANTIC_OBSERVATION', 'absent observation cannot carry a value')
    presence = validAbsent(token(String(observation.reason ?? 'VALID_ABSENCE'), 'ABSENCE'))
  } else if (observation.presence === 'NOT_COMPUTED') {
    requireCondition(observation.value === undefined || observation.value === null, 'INVALID_RUNTIME_SEMANTIC_OBSERVATION', 'not-computed observation cannot carry a value')
    presence = notComputed(token(String(observation.reason ?? 'NOT_COMPUTED'), 'NOT_COMPUTED'))
  } else throw Object.assign(new Error('INVALID_RUNTIME_SEMANTIC_OBSERVATION: explicit presence required'), { code: 'INVALID_RUNTIME_SEMANTIC_OBSERVATION' })

  return makeExtraction({
    endpoint: makeEndpoint(parseAddress(observation.endpointAddress), parseHexBytes(hex(observation.selector ?? '0x', 'selector'))),
    postState: postStateBoundary.commitment,
    recordIdentity: createCommitment(envelopeEvidence.receipt.digest, 'rhook/generic-runtime-03/envelope-evidence-record/1'),
    source,
    presence,
  })
}
