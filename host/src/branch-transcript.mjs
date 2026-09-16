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
  return freeze({ body, integrationCommitment: runtimeDigest('rhook/generic-host-03/integration-evidence/1', body) })
}

function plainBoundary(value) {
  return {
    kind: 'EthereumStateBoundary',
    algorithm: value.algorithm,
    stateRoot: value.stateRoot,
    commitment: { kind: 'Digest', value: value.commitment },
  }
}

export function verifyIntegrationEvidenceBundle(bundle) {
  const findings = []
  const add = (code, detail) => findings.push({ code, detail })
  try {
    const body = bundle?.body
    if (body?.schema !== 'generic-engine-host-03-integration-evidence/1') add('INVALID_BUNDLE_SCHEMA', 'integration evidence schema mismatch')
    if (!isBranchEvidenceTranscriptVerified(verifyBranchEvidenceTranscript(body?.coreTranscript))) add('INVALID_CORE_TRANSCRIPT', 'embedded core transcript does not independently verify')
    if (runtimeDigest('rhook/generic-host-03/integration-evidence/1', body) !== bundle?.integrationCommitment) add('INTEGRATION_COMMITMENT_MISMATCH', 'bundle body was modified')
    for (const mode of ['actual', 'counterfactual']) {
      const projection = body?.replayProjections?.[mode]
      const expectedExecution = runtimeDigest('rhook/generic-host-03/replay-projection/1', projection)
      if (expectedExecution !== body?.executionCommitments?.[mode]) add('EXECUTION_COMMITMENT_MISMATCH', `${mode} replay projection mismatch`)
      const changed = body?.coreTranscript?.body?.changedTransitions ?? []
      const unchanged = body?.coreTranscript?.body?.unchangedCommitments ?? []
      for (const item of body?.stateRootBindings?.[mode] ?? []) {
        const predecessor = plainBoundary(item.predecessor)
        const successor = plainBoundary(item.successor)
        if (!verifyStateBoundary(predecessor) || !verifyStateBoundary(successor)) add('STATE_ROOT_BINDING_MISMATCH', `${mode} envelope ${item.envelopeIndex} native root binding mismatch`)
        const transition = changed.find((entry) => entry.envelopeIndex === item.envelopeIndex)
        const compact = unchanged.find((entry) => entry.envelopeIndex === item.envelopeIndex)
        const evidence = transition?.[mode]
        const predecessorCommitment = evidence?.body?.predecessorStateCommitment
        const successorCommitment = evidence?.body?.execution?.successorStateCommitment ?? compact?.[`${mode}PostStateCommitment`]
        if (predecessorCommitment !== undefined && predecessorCommitment !== item.predecessor.commitment) add('STATE_ROOT_BINDING_MISMATCH', `${mode} envelope ${item.envelopeIndex} predecessor is detached`)
        if (successorCommitment !== item.successor.commitment) add('STATE_ROOT_BINDING_MISMATCH', `${mode} envelope ${item.envelopeIndex} successor is detached`)
      }
    }
    if (body?.provenance?.frozenRunnerLifecycleEvents !== true || body?.provenance?.transcriptBuiltFromExecutedEnvelopeEvidence !== true || body?.provenance?.semanticObservationsCapturedAtAfterTxStateBoundary !== true || body?.provenance?.scientificValidationClaimed !== false) add('INVALID_PROVENANCE', 'integration provenance flags mismatch')
  } catch (error) {
    add('MALFORMED_BUNDLE', String(error?.message ?? error))
  }
  return freeze({ valid: findings.length === 0, findings })
}

export function exportIntegrationEvidenceBundle(bundle) {
  const verification = verifyIntegrationEvidenceBundle(bundle)
  requireCondition(verification.valid, 'UNVERIFIED_INTEGRATION_EVIDENCE', canonicalRuntimeJson(verification.findings))
  return `${canonicalRuntimeJson(bundle)}\n`
}
