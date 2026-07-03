/**
 * `@parallax/locking` — M10 optimistic locking.
 *
 * Owns the version-column optimistic-lock discipline: the versioned `UPDATE` that
 * gates on the read version and advances it in the same statement, and the
 * `updatedRows != 1` conflict signal. The M12 harness imports these directly over
 * the legal `M12 -> M10` edge; it reaches the M8 unit-of-work helpers over its own
 * direct `M12 -> M8` edge (importing `@parallax/transactions`), not through this
 * package.
 */
export {
  classifyOutcome,
  type OptimisticOutcome,
  type VersionedTarget,
  versionAdvancingUpdate,
  versionedUpdate,
} from "./optimistic.js";
