import { createHash } from 'node:crypto'

import {
  buildBranchEvidenceTranscript,
  createCommitment,
  exportBranchEvidenceTranscript,
  extractionSlotKey,
  isBranchEvidenceTranscriptVerified,
  makeEnvelopeIdentity,
  parseBlockNumber,
  parseHash32,
  parseQuantity,
  verifyBranchEvidenceTranscript,
} from '../../core/src/index.mjs'
import {
  canonicalRuntimeJson,
  runtimeDigest,
  verifyStateBoundary,
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

function typedIdentity(raw) {
  return makeEnvelopeIdentity({
    blockNumber: parseBlockNumber(String(raw.blockNumber)),
    transactionIndex: parseQuantity(String(raw.transactionIndex)),
    transactionHash: parseHash32(raw.transactionHash),
  })
}

function semanticPairs(actual, counterfactual) {
  const counterfactualByKey = new Map(counterfactual.semanticExtractions.map((item) => [`${item.envelopeIndex}:${extractionSlotKey(item.extraction)}`, item]))
  const pairs = []
  for (const item of actual.semanticExtractions) {
    const key = `${item.envelopeIndex}:${extractionSlotKey(item.extraction)}`
    const other = counterfactualByKey.get(key)
    requireCondition(other, 'SEMANTIC_SLOT_ALIGNMENT_MISMATCH', `counterfactual semantic extraction missing for ${key}`)
    pairs.push({ envelopeIndex: parseQuantity(String(item.envelopeIndex)), actual: item.extraction, counterfactual: other.extraction })
    counterfactualByKey.delete(key)
  }
  requireCondition(counterfactualByKey.size === 0, 'SEMANTIC_SLOT_ALIGNMENT_MISMATCH', 'counterfactual branch has unmatched semantic extractions')
  return pairs
}

export function buildTranscriptFromExecutedBranches({ actual, counterfactual, intervention }) {
  requireCondition(actual?.evidenceEnabled === true && counterfactual?.evidenceEnabled === true, 'EVIDENCE_NOT_ENABLED', 'both executed branches must contain automatic evidence')
  requireCondition(Array.isArray(actual.envelopes) && actual.envelopes.length === counterfactual.envelopes?.length, 'ENVELOPE_ALIGNMENT_MISMATCH', 'executed branches must have aligned envelopes')
  return buildBranchEvidenceTranscript({
    branches: {
      actual: createCommitment(actual.executionCommitment, 'GENERIC_HOST_03_ACTUAL_EXECUTED_BRANCH'),
      counterfactual: createCommitment(counterfactual.executionCommitment, 'GENERIC_HOST_03_COUNTERFACTUAL_EXECUTED_BRANCH'),
    },
    intervention: { kind: intervention.kind, target: typedIdentity(intervention.target) },
    actualEnvelopes: actual.envelopes,
    counterfactualEnvelopes: counterfactual.envelopes,
    semanticPairs: semanticPairs(actual, counterfactual),
  })
}

function stateBindingProjection(run) {
  return run.stateBindings.map((item) => ({
    envelopeIndex: item.envelopeIndex,
    predecessor: { algorithm: item.predecessor.algorithm, stateRoot: item.predecessor.stateRoot, commitment: item.predecessor.commitment.value },
    successor: { algorithm: item.successor.algorithm, stateRoot: item.successor.stateRoot, commitment: item.successor.commitment.value },
  }))
}

export function buildIntegrationEvidenceBundle({ actual, counterfactual, transcript }) {
  requireCondition(isBranchEvidenceTranscriptVerified(verifyBranchEvidenceTranscript(transcript)), 'INVALID_CORE_TRANSCRIPT', 'strict core transcript must verify before bundling')
  const body = freeze({
    schema: 'generic-engine-host-03-integration-evidence/1',
    coreTranscript: transcript,
    replayProjections: { actual: actual.projection, counterfactual: counterfactual.projection },
    executionCommitments: { actual: actual.executionCommitment, counterfactual: counterfactual.executionCommitment },
    stateRootBindings: { actual: stateBindingProjection(actual), counterfactual: stateBindingProjection(counterfactual) },
    provenance: {
      frozenRunnerLifecycleEvents: true,
      transcriptBuiltFromExecutedEnvelopeEvidence: true,
      semanticObservationsCapturedAtAfterTxStateBoundary: true,
      scientificValidationClaimed: false,
    },
  })
  const bundle = freeze({ body, integrationCommitment: runtimeDigest('rhook/generic-host-03/integration-evidence/1', body) })
  const verification = verifyIntegrationEvidenceBundle(bundle)
  requireCondition(verification.valid, 'UNVERIFIED_INTEGRATION_EVIDENCE', canonicalRuntimeJson(verification.findings))
  return bundle
}

const MODES = Object.freeze(['actual', 'counterfactual'])
const DIGEST_RE = /^[0-9a-f]{64}$/
const HASH32_RE = /^0x[0-9a-f]{64}$/
const DECIMAL_RE = /^(?:0|[1-9][0-9]*)$/
const isDigest = (value) => typeof value === 'string' && DIGEST_RE.test(value)
const isHash32 = (value) => typeof value === 'string' && HASH32_RE.test(value)
const isDecimal = (value) => typeof value === 'string' && DECIMAL_RE.test(value)
const normalizedExceptionClassification = (value) => `EVM_${value}`.toUpperCase().replace(/[^A-Z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 96)
const PROJECTION_KEYS = Object.freeze([
  'blockNumber',
  'canonicalEnvelopeIdentities',
  'executedTransactionHashes',
  'finalStateRoot',
  'gasUsed',
  'receiptStatuses',
  'receiptsRoot',
  'schema',
  'transactionExceptions',
  'transactionFeesPaid',
  'transactionGasUsed',
])

function isRecord(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function exactObject(value, expectedKeys, add, code, path) {
  if (!isRecord(value)) {
    add(code, `${path} must be an object`)
    return false
  }
  const actual = Object.keys(value).sort()
  const expected = [...expectedKeys].sort()
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    add(code, `${path} must contain exactly ${expected.join(', ')}`)
    return false
  }
  return true
}

function shapeBundle(bundle, add) {
  if (!exactObject(bundle, ['body', 'integrationCommitment'], add, 'INVALID_BUNDLE_SHAPE', '$')) return
  const body = bundle.body
  if (!exactObject(body, ['coreTranscript', 'executionCommitments', 'provenance', 'replayProjections', 'schema', 'stateRootBindings'], add, 'INVALID_BUNDLE_BODY_SHAPE', '$.body')) return
  exactObject(body.replayProjections, MODES, add, 'INVALID_REPLAY_PROJECTIONS_SHAPE', '$.body.replayProjections')
  exactObject(body.executionCommitments, MODES, add, 'INVALID_EXECUTION_COMMITMENTS_SHAPE', '$.body.executionCommitments')
  exactObject(body.stateRootBindings, MODES, add, 'INVALID_STATE_ROOT_BINDINGS_SHAPE', '$.body.stateRootBindings')
  exactObject(body.provenance, ['frozenRunnerLifecycleEvents', 'scientificValidationClaimed', 'semanticObservationsCapturedAtAfterTxStateBoundary', 'transcriptBuiltFromExecutedEnvelopeEvidence'], add, 'INVALID_PROVENANCE_SHAPE', '$.body.provenance')

  for (const mode of MODES) {
    const projection = body.replayProjections?.[mode]
    if (exactObject(projection, PROJECTION_KEYS, add, 'INVALID_REPLAY_PROJECTION_SHAPE', `$.body.replayProjections.${mode}`)) {
      for (const field of ['canonicalEnvelopeIdentities', 'executedTransactionHashes', 'receiptStatuses', 'transactionGasUsed', 'transactionFeesPaid', 'transactionExceptions']) {
        if (!Array.isArray(projection[field])) add('INVALID_REPLAY_PROJECTION_SHAPE', `$.body.replayProjections.${mode}.${field} must be an array`)
      }
      if (Array.isArray(projection.canonicalEnvelopeIdentities)) {
        projection.canonicalEnvelopeIdentities.forEach((identity, index) => {
          exactObject(identity, ['blockNumber', 'transactionHash', 'transactionIndex'], add, 'INVALID_PROJECTION_IDENTITY_SHAPE', `$.body.replayProjections.${mode}.canonicalEnvelopeIdentities[${index}]`)
        })
      }
    }

    const bindings = body.stateRootBindings?.[mode]
    if (!Array.isArray(bindings)) add('INVALID_STATE_ROOT_BINDINGS_SHAPE', `$.body.stateRootBindings.${mode} must be an array`)
    else bindings.forEach((binding, index) => {
      const path = `$.body.stateRootBindings.${mode}[${index}]`
      if (!exactObject(binding, ['envelopeIndex', 'predecessor', 'successor'], add, 'INVALID_STATE_ROOT_BINDING_SHAPE', path)) return
      exactObject(binding.predecessor, ['algorithm', 'commitment', 'stateRoot'], add, 'INVALID_STATE_BOUNDARY_SHAPE', `${path}.predecessor`)
      exactObject(binding.successor, ['algorithm', 'commitment', 'stateRoot'], add, 'INVALID_STATE_BOUNDARY_SHAPE', `${path}.successor`)
    })
  }
}

function plainBoundary(value) {
  return {
    kind: 'EthereumStateBoundary',
    algorithm: value.algorithm,
    stateRoot: value.stateRoot,
    commitment: { kind: 'Digest', value: value.commitment },
  }
}

function validateTypes(bundle, add) {
  const { body, integrationCommitment } = bundle
  if (body.schema !== 'generic-engine-host-03-integration-evidence/1') add('INVALID_BUNDLE_SCHEMA', 'integration evidence schema mismatch')
  if (!isDigest(integrationCommitment)) add('INVALID_INTEGRATION_COMMITMENT', 'integration commitment must be a canonical SHA-256 digest')
  if (!isBranchEvidenceTranscriptVerified(verifyBranchEvidenceTranscript(body.coreTranscript))) add('INVALID_CORE_TRANSCRIPT', 'embedded core transcript does not independently verify')
  if (
    body.provenance.frozenRunnerLifecycleEvents !== true
    || body.provenance.transcriptBuiltFromExecutedEnvelopeEvidence !== true
    || body.provenance.semanticObservationsCapturedAtAfterTxStateBoundary !== true
    || body.provenance.scientificValidationClaimed !== false
  ) add('INVALID_PROVENANCE', 'integration provenance flags mismatch')

  for (const mode of MODES) {
    if (!isDigest(body.executionCommitments[mode])) add('INVALID_EXECUTION_COMMITMENT', `${mode} execution commitment must be a canonical SHA-256 digest`)
    const projection = body.replayProjections[mode]
    if (projection.schema !== 'generic-engine-host-03-replay-projection/1') add('INVALID_REPLAY_PROJECTION_SCHEMA', `${mode} replay projection schema mismatch`)
    if (!isDecimal(projection.blockNumber)) add('INVALID_REPLAY_PROJECTION_TYPE', `${mode} blockNumber must be canonical unsigned decimal`)
    if (!isDecimal(projection.gasUsed)) add('INVALID_REPLAY_PROJECTION_TYPE', `${mode} gasUsed must be canonical unsigned decimal`)
    if (!isHash32(projection.receiptsRoot) || !isHash32(projection.finalStateRoot)) add('INVALID_REPLAY_PROJECTION_TYPE', `${mode} receiptsRoot and finalStateRoot must be canonical 32-byte hashes`)

    projection.canonicalEnvelopeIdentities.forEach((identity, index) => {
      if (!isDecimal(identity.blockNumber) || !isDecimal(identity.transactionIndex) || !isHash32(identity.transactionHash)) add('INVALID_PROJECTION_IDENTITY', `${mode} canonical identity ${index} is malformed`)
    })
    projection.executedTransactionHashes.forEach((value, index) => {
      if (!isHash32(value)) add('INVALID_REPLAY_PROJECTION_TYPE', `${mode} executed transaction hash ${index} is malformed`)
    })
    projection.receiptStatuses.forEach((value, index) => {
      if (value !== 0 && value !== 1) add('INVALID_REPLAY_PROJECTION_TYPE', `${mode} receipt status ${index} must be 0 or 1`)
    })
    for (const field of ['transactionGasUsed', 'transactionFeesPaid']) {
      projection[field].forEach((value, index) => {
        if (!isDecimal(value)) add('INVALID_REPLAY_PROJECTION_TYPE', `${mode} ${field}[${index}] must be canonical unsigned decimal`)
      })
    }
    projection.transactionExceptions.forEach((value, index) => {
      if (value !== null && (typeof value !== 'string' || value.length === 0)) add('INVALID_REPLAY_PROJECTION_TYPE', `${mode} transaction exception ${index} must be a non-empty string or null`)
    })

    body.stateRootBindings[mode].forEach((binding, index) => {
      if (!Number.isSafeInteger(binding.envelopeIndex) || binding.envelopeIndex < 0) add('INVALID_STATE_ROOT_BINDING_INDEX', `${mode} state binding ${index} has an invalid envelope index`)
      for (const side of ['predecessor', 'successor']) {
        if (!verifyStateBoundary(plainBoundary(binding[side]))) add('STATE_ROOT_BINDING_MISMATCH', `${mode} envelope ${binding.envelopeIndex} ${side} native root binding is invalid`)
      }
    })
  }
}

function transcriptCoverage(transcript) {
  const declared = transcript.body.coverage.declaredEnvelopes
  const coverage = Array.from({ length: declared })
  for (const item of transcript.body.changedTransitions) {
    coverage[item.envelopeIndex] = {
      identity: item.actual.body.envelope,
      actual: { kind: 'full', body: item.actual.body },
      counterfactual: { kind: 'full', body: item.counterfactual.body },
    }
  }
  for (const item of transcript.body.unchangedCommitments) {
    coverage[item.envelopeIndex] = {
      identity: item.envelope,
      actual: { kind: 'compact', successorStateCommitment: item.actualPostStateCommitment },
      counterfactual: { kind: 'compact', successorStateCommitment: item.counterfactualPostStateCommitment },
    }
  }
  return coverage
}

function sameIdentity(left, right) {
  return left.blockNumber === right.blockNumber
    && left.transactionIndex === right.transactionIndex
    && left.transactionHash === right.transactionHash
}

function crossBind(bundle, add) {
  const { body } = bundle
  const transcript = body.coreTranscript
  const coverage = transcriptCoverage(transcript)
  const declared = coverage.length
  const target = transcript.body.intervention.target
  const targetIndex = coverage.findIndex((item) => sameIdentity(item.identity, target))

  for (const mode of MODES) {
    const projection = body.replayProjections[mode]
    const arrays = ['canonicalEnvelopeIdentities', 'executedTransactionHashes', 'receiptStatuses', 'transactionGasUsed', 'transactionFeesPaid', 'transactionExceptions']
    for (const field of arrays) {
      if (projection[field].length !== declared) add('PROJECTION_CARDINALITY_MISMATCH', `${mode} ${field} must contain exactly ${declared} entries`)
    }
    const bindings = body.stateRootBindings[mode]
    if (bindings.length !== declared) add('STATE_ROOT_BINDING_COVERAGE_MISMATCH', `${mode} must contain one state-root binding for each of ${declared} envelopes`)

    if (projection.canonicalEnvelopeIdentities.length === declared) {
      projection.canonicalEnvelopeIdentities.forEach((identity, index) => {
        if (!sameIdentity(identity, coverage[index].identity)) add('PROJECTION_IDENTITY_MISMATCH', `${mode} canonical identity ${index} is detached from the core transcript`)
        if (identity.blockNumber !== projection.blockNumber) add('PROJECTION_BLOCK_MISMATCH', `${mode} canonical identity ${index} is outside projection block ${projection.blockNumber}`)
      })
    }

    if (projection.executedTransactionHashes.length === declared) {
      projection.executedTransactionHashes.forEach((transactionHash, index) => {
        if ((mode === 'actual' || index !== targetIndex) && transactionHash !== coverage[index].identity.transactionHash) add('EXECUTED_TRANSACTION_IDENTITY_MISMATCH', `${mode} executed transaction ${index} is detached from the canonical envelope identity`)
      })
    }

    if (projection.transactionGasUsed.length === declared) {
      const summedGas = projection.transactionGasUsed.reduce((sum, value) => sum + BigInt(value), 0n).toString()
      if (summedGas !== projection.gasUsed) add('PROJECTION_GAS_MISMATCH', `${mode} block gasUsed does not equal the transaction gas sum`)
    }

    const expectedBranchDomain = mode === 'actual' ? 'GENERIC_HOST_03_ACTUAL_EXECUTED_BRANCH' : 'GENERIC_HOST_03_COUNTERFACTUAL_EXECUTED_BRANCH'
    if (transcript.body.branches[mode].domain !== expectedBranchDomain || transcript.body.branches[mode].digest !== body.executionCommitments[mode]) add('PROJECTION_TRANSCRIPT_COMMITMENT_MISMATCH', `${mode} projection commitment is detached from the core transcript branch`)

    for (let index = 0; index < declared; index += 1) {
      const covered = coverage[index][mode]
      const binding = bindings[index]
      if (binding?.envelopeIndex !== index) add('STATE_ROOT_BINDING_ORDER_MISMATCH', `${mode} state binding position ${index} must have envelopeIndex ${index}`)
      if (!binding) continue

      const expectedSuccessor = covered.kind === 'full' ? covered.body.execution.successorStateCommitment : covered.successorStateCommitment
      if (binding.successor.commitment !== expectedSuccessor) add('STATE_ROOT_BINDING_MISMATCH', `${mode} envelope ${index} successor is detached from core evidence`)
      if (covered.kind === 'full') {
        if (binding.predecessor.commitment !== covered.body.predecessorStateCommitment) add('STATE_ROOT_BINDING_MISMATCH', `${mode} envelope ${index} predecessor is detached from core evidence`)
        const lifecycle = covered.body.execution.lifecycle
        if (lifecycle !== 'SUCCESS' && lifecycle !== 'REVERT') add('UNREPRESENTABLE_PROJECTION_LIFECYCLE', `${mode} envelope ${index} lifecycle ${lifecycle} has no receipt projection in schema v1`)
        else {
          const expectedStatus = lifecycle === 'SUCCESS' ? 1 : 0
          if (projection.receiptStatuses[index] !== expectedStatus) add('PROJECTION_LIFECYCLE_MISMATCH', `${mode} envelope ${index} receipt status disagrees with core evidence`)
          if (projection.transactionGasUsed[index] !== covered.body.execution.gasAndFee.gasUsed || projection.transactionFeesPaid[index] !== covered.body.execution.gasAndFee.feePaid) add('PROJECTION_ACCOUNTING_MISMATCH', `${mode} envelope ${index} gas or fee is detached from core evidence`)
          const projectionException = projection.transactionExceptions[index]
          if (lifecycle === 'SUCCESS' && projectionException !== null) add('PROJECTION_EXCEPTION_MISMATCH', `${mode} envelope ${index} must not project an exception`)
          if (
            lifecycle === 'REVERT'
            && (projectionException === null || normalizedExceptionClassification(projectionException) !== covered.body.execution.exception.classification)
          ) add('PROJECTION_EXCEPTION_MISMATCH', `${mode} envelope ${index} exception classification disagrees with core evidence`)
        }
      }

      if (index > 0) {
        const previous = bindings[index - 1]
        if (
          previous
          && (binding.predecessor.commitment !== previous.successor.commitment || binding.predecessor.stateRoot !== previous.successor.stateRoot)
        ) add('STATE_ROOT_BINDING_CONTINUITY_MISMATCH', `${mode} envelope ${index} predecessor does not equal envelope ${index - 1} successor`)
      }
    }
  }

  const actualInitial = body.stateRootBindings.actual[0]?.predecessor
  const counterfactualInitial = body.stateRootBindings.counterfactual[0]?.predecessor
  if (
    actualInitial && counterfactualInitial
    && (actualInitial.commitment !== counterfactualInitial.commitment || actualInitial.stateRoot !== counterfactualInitial.stateRoot)
  ) add('INITIAL_STATE_ROOT_MISMATCH', 'actual and counterfactual projections do not start from the same native state boundary')
}

function verifyCommitments(bundle, add) {
  const { body } = bundle
  for (const mode of MODES) {
    const expectedExecution = runtimeDigest('rhook/generic-host-03/replay-projection/1', body.replayProjections[mode])
    if (expectedExecution !== body.executionCommitments[mode]) add('EXECUTION_COMMITMENT_MISMATCH', `${mode} replay projection commitment mismatch`)
  }
  if (runtimeDigest('rhook/generic-host-03/integration-evidence/1', body) !== bundle.integrationCommitment) add('INTEGRATION_COMMITMENT_MISMATCH', 'bundle body commitment mismatch')
}

export function verifyIntegrationEvidenceBundle(bundle) {
  const findings = []
  const add = (code, detail) => findings.push({ code, detail })
  const result = () => freeze({ valid: findings.length === 0, findings })
  try {
    shapeBundle(bundle, add)
    if (findings.length > 0) return result()
    validateTypes(bundle, add)
    if (findings.length > 0) return result()
    crossBind(bundle, add)
    if (findings.length > 0) return result()
    verifyCommitments(bundle, add)
  } catch (error) {
    add('MALFORMED_BUNDLE', String(error?.message ?? error))
  }
  return result()
}

export function exportIntegrationEvidenceBundle(bundle) {
  const verification = verifyIntegrationEvidenceBundle(bundle)
  requireCondition(verification.valid, 'UNVERIFIED_INTEGRATION_EVIDENCE', canonicalRuntimeJson(verification.findings))
  return `${canonicalRuntimeJson(bundle)}\n`
}
