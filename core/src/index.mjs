export { BoundaryError, fail, requireCondition, rejectUndefined, rejectRawScalar } from './errors.mjs'

export {
  KIND, PRESENCE, ZERO_STORAGE_WORD,
  parseAddress, createZeroAddress, isAddress, isZeroAddress, requireAddress,
  parseHash32, isHash32, parseDigest, isDigest, createCommitment, isCommitment,
  parseQuantity, createZeroQuantity, isQuantity, isZeroQuantity,
  parseBlockNumber, isBlockNumber,
  parseHexBytes, createEmptyCode, isHexBytes, isEmptyCode,
  present, validAbsent, notComputed, isPresent, isValidAbsent, isNotComputed,
  presentAccount, absentAccount, presentStorage, absentStorage, createZeroStorageWord,
} from './boundary-types.mjs'

export {
  RESULT, resultValid, resultAbsent, resultError, isValid, isAbsent, isError,
  matchResult, presenceToResult, reconcileVerifiedAgainstCached,
} from './port-results.mjs'

export {
  SOURCE, DIFF, makeEndpoint, isEndpoint, sourceStorageSlot, sourceReturnWord,
  sourceAccountField, sourceCode, makeExtraction, isExtraction, extractionSlotKey,
  diffExtractions, isDiffVerdict, diffAsResult,
} from './semantic-extraction.mjs'

export {
  VALIDATION_STATUS, ENVELOPE_LIFECYCLE, EXCEPTION_KIND,
  makeEnvelopeIdentity, isEnvelopeIdentity,
  validationValid, validationInvalid,
  exceptionNone, exceptionRevert, exceptionValidation, isExceptionOutcome,
  makeGasAndFee, isGasAndFee,
} from './envelope-evidence.mjs'

export {
  buildEnvelopeEvidence,
  verifyEnvelopeEvidence,
  isEnvelopeEvidenceVerified,
  exportEnvelopeEvidence,
  buildBranchEvidenceTranscript,
  verifyBranchEvidenceTranscript,
  isBranchEvidenceTranscriptVerified,
  exportBranchEvidenceTranscript,
  branchEvidenceTranscriptHash,
  verifyEnvelopeEvidenceJson,
  verifyBranchEvidenceTranscriptJson,
} from './strict-api.mjs'

export { parseStrictEvidenceJson } from './strict-json.mjs'
