/**
 * m-db-error error-code classification — the dialect-owned SQLSTATE → neutral-category
 * map (the TypeScript peer of `reference-harness/.../errors.py`).
 *
 * A driver surfaces a native code (Postgres keys on the SQLSTATE *string*; a
 * future MariaDB adapter would key on the vendor *errno*). The dialect owns the
 * map from that native code to a **closed neutral category** vocabulary, so a
 * predicate (the retry loop's "is this retriable?") is category membership and can
 * never drift from its category. This is exactly `errors.classify(dialect, code)`
 * in the reference harness, ported so the shipped Postgres adapter and the runtime
 * retry loop share one classification contract.
 *
 * The retriable set is `{deadlock}` — a true deadlock (`40P01`) OR a serialization
 * failure (`40001`), both folded into the `deadlock` category and both retriable.
 * A lock-not-available timeout (`55P03`) is the `lockWaitTimeout` category and is
 * **NOT** retriable — mirroring the normative reference model exactly.
 */

/**
 * The closed neutral error-category vocabulary (mirrors the reference harness
 * `errors.py` constants). `deadlock` covers a true deadlock AND a serialization
 * failure (both retriable); `lockWaitTimeout` is blocked past the lock-wait budget
 * (not retriable); `connectionDead` is reserved (not exercised); `unknown` is an
 * unrecognized / missing code.
 */
export type ErrorCategory =
  | "uniqueViolation"
  | "deadlock"
  | "lockWaitTimeout"
  | "connectionDead"
  | "unknown";

/** Postgres keys on the SQLSTATE string (the porsager error's `.code`). */
const POSTGRES_ERROR_CODES: Readonly<Record<string, ErrorCategory>> = {
  "23505": "uniqueViolation",
  "40P01": "deadlock", // deadlock_detected
  "40001": "deadlock", // serialization_failure — retriable, folded into deadlock
  "55P03": "lockWaitTimeout", // lock_not_available (SET lock_timeout exceeded)
};

/**
 * Classify a native Postgres error code (the SQLSTATE string a driver surfaces)
 * to a neutral m-db-error category. Returns `unknown` for an unrecognized or missing code
 * so an unclassified error is never silently treated as retriable.
 */
export function classifyErrorCode(code: string | number | null | undefined): ErrorCategory {
  if (code === null || code === undefined) {
    return "unknown";
  }
  return POSTGRES_ERROR_CODES[String(code)] ?? "unknown";
}

/**
 * The transaction retry loop's question: is a failure of this category retriable?
 * True iff the category is `deadlock` (a true deadlock OR a serialization failure).
 * A `lockWaitTimeout` is explicitly NOT retriable (mirrors `errors.is_retriable`).
 */
export function isRetriableCategory(category: ErrorCategory): boolean {
  return category === "deadlock";
}
