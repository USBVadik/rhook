// Fail-closed boundary errors.
//
// A boundary violation throws a typed error. It never returns undefined or a
// coerced fallback.

export class BoundaryError extends Error {
  constructor(code, message, details = null) {
    super(`${code}: ${message}`)
    this.name = 'BoundaryError'
    this.code = code
    this.details = details
    // Freeze so a downstream consumer cannot mutate a rejection into a pass.
    Object.freeze(this)
  }
}

/** Throw a typed BoundaryError. Never returns. */
export function fail(code, message, details = null) {
  throw new BoundaryError(code, message, details)
}

/**
 * Fail-closed guard. If `condition` is falsy, throw BoundaryError(code).
 * Used at every ingress so a wrong-typed / undefined input is REJECTED,
 * never coerced.
 */
export function requireCondition(condition, code, message, details = null) {
  if (!condition) fail(code, message, details)
}

/**
 * Reject `undefined` explicitly at a boundary. `undefined` is NEVER a legal
 * boundary value: this is the single choke point that converts the
 * "missing member / unmatched find / optional-chain / absent map entry"
 * defect class into a typed error before it can cross.
 */
export function rejectUndefined(value, code, message) {
  if (value === undefined) fail(code, message ?? 'undefined is not a legal boundary value')
  return value
}

/**
 * Reject a raw scalar crossing a typed boundary.
 * A value that a typed boundary wraps as "present / VALID" must be a typed
 * (branded) object or a composite record built from typed members — never a
 * bare string, number, bigint, boolean or symbol. Those primitives are exactly
 * the un-parsed raw forms the single-conversion boundary exists to keep out, so
 * letting one through `present()`/`resultValid()` would let a raw string satisfy
 * a typed boundary. This rejects them fail-closed. `null` is a distinct case
 * handled by the presence/result encodings (VALID_ABSENT/ABSENT), not here.
 */
export function rejectRawScalar(value, code, message) {
  const t = typeof value
  if (t === 'string' || t === 'number' || t === 'bigint' || t === 'boolean' || t === 'symbol') {
    fail(code, message ?? `a raw ${t} is not a typed boundary value; parse it at ingress first`)
  }
  return value
}
