// RR21-M17CC-01: the ONE canonical exact Shot-duration transport
// grammar for the web boundary.
//
// A lawful backend duration is a signed-SQLite integer in
// [0, SQLITE_INT_MAX]; JavaScript `number` (IEEE-754) cannot carry
// every such integer (2^53+1 already rounds), so authoritative Shot
// duration crosses the web boundary as a CANONICAL DECIMAL STRING
// (the additive `duration_ms_dec` transport coordinate) and NEVER
// through `number`. This module owns the grammar and the domain
// validation; BigInt is used internally for exact comparison only
// (it never reaches native JSON serialization).
//
// Canonical grammar: optional-unset (null/undefined), or a bare
// decimal digit string — "0" or [1-9][0-9]* — no sign, exponent,
// decimal point, whitespace, leading-zero aliases, or lossy
// coercion. Derived transport data only; the backend integer stays
// the sole authority.

/** The signed SQLite INTEGER maximum (2^63 − 1) as a decimal string. */
export const SQLITE_INT_MAX_DEC = "9223372036854775807";

const CANONICAL_DECIMAL = /^(0|[1-9][0-9]*)$/;

/**
 * Is `value` a CANONICAL decimal string within [0, SQLITE_INT_MAX]?
 * Exact: parses via the grammar, compares via BigInt — never through
 * JavaScript `number`.
 */
export function isCanonicalDurationDec(value: string): boolean {
  if (!CANONICAL_DECIMAL.test(value)) return false;
  if (value.length > SQLITE_INT_MAX_DEC.length) return false;
  if (value.length === SQLITE_INT_MAX_DEC.length
    && value > SQLITE_INT_MAX_DEC) {
    // same-length lexicographic comparison IS numeric comparison
    // for equal-length canonical decimal strings
    return false;
  }
  return true;
}

/**
 * The exact display/init form of a duration: the canonical decimal
 * string, or "" when unset. `dec` is the additive transport
 * coordinate (`duration_ms_dec`); the legacy `number` field is
 * IGNORED for authoritative display/edit initialization.
 */
export function durationInput(
  dec: string | null | undefined,
): string {
  return dec === null || dec === undefined ? "" : dec;
}

/**
 * Validate a form value as the exact duration transport: "" → null
 * (unset); otherwise the value MUST already be canonical within
 * [0, SQLITE_INT_MAX]. Returns null for unset, the canonical string
 * for lawful values; THROWS on anything else (the caller surfaces a
 * typed validation error — never a silent `Number()` coercion).
 */
export function durationToTransport(
  raw: string,
): string | null {
  const trimmedAll = raw;
  const canonical = trimmedAll.trim() === "" ? "" : raw.trim();
  if (canonical === "") return null;
  if (!isCanonicalDurationDec(canonical)) {
    throw new Error(
      "duration_ms must be a whole number between 0 and "
        + SQLITE_INT_MAX_DEC
        + " (exact decimal digits only)",
    );
  }
  return canonical;
}

/**
 * Exact numeric comparison for the timeline interior-time guard:
 * is event `timeMs` (a JS-safe event coordinate, number) strictly
 * less than the exact duration decimal string? The event side stays
 * a `number` (SAFE_INT_MAX-bounded event grammar); the duration
 * side is compared exactly via BigInt.
 */
export function timeBelowExactDuration(
  timeMs: number,
  durationDec: string,
): boolean {
  return BigInt(Math.trunc(timeMs)) < BigInt(durationDec);
}
