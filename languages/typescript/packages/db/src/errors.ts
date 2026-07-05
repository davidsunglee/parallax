/**
 * `@parallax/db` — the port's **portable error surface** (M8/M10 bounded automatic
 * retry).
 *
 * The port carries no dialect and no driver, but the unit-of-work retry loop above
 * it (in `@parallax/typescript`) needs a **portable, driver-neutral signal** for a
 * transient database failure so it can decide whether to re-execute the closure.
 * A concrete adapter (`@parallax/db-postgres`, `@parallax/db-mariadb`) classifies
 * its driver's native code through the dialect's error map (`@parallax/dialect`
 * `classifyErrorCode`) and surfaces the result as this error — so nothing above
 * the seam ever inspects a driver-specific `.code` / `.errno`.
 *
 * This is the first error-kind surface on the port; before the retry contract the
 * port had none.
 */

/**
 * The portable transient-failure vocabulary (the M11 neutral category names, the
 * `@parallax/dialect` `ErrorCategory` minus `unknown`). `deadlock` — a true
 * deadlock or a serialization failure (retriable); `lockWaitTimeout` — blocked
 * past the lock-wait budget (not retriable); `uniqueViolation` — duplicate key;
 * `connectionDead` — reserved.
 */
export type TransientErrorKind =
  | "deadlock"
  | "lockWaitTimeout"
  | "uniqueViolation"
  | "connectionDead";

/**
 * A driver-neutral database failure a concrete adapter surfaces after classifying
 * its native error code. `retriable` is the retry loop's decision input (true only
 * for the `deadlock` category); the original driver error is preserved as `cause`.
 * The loop keys on `instanceof ParallaxTransientError && retriable`, so it never
 * reaches into a driver's error shape.
 */
export class ParallaxTransientError extends Error {
  /** The neutral category the driver's native code classified to. */
  readonly kind: TransientErrorKind;
  /** Whether the retry loop should re-execute the closure (only `deadlock`). */
  readonly retriable: boolean;

  constructor(kind: TransientErrorKind, retriable: boolean, options?: { cause?: unknown }) {
    super(
      `database transient failure (${kind}, ${retriable ? "retriable" : "not retriable"})`,
      options as ErrorOptions,
    );
    this.name = "ParallaxTransientError";
    this.kind = kind;
    this.retriable = retriable;
    Object.setPrototypeOf(this, ParallaxTransientError.prototype);
  }
}
