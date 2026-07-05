/**
 * The API Conformance Suite **coverage map**: every `slice-mvp-1` case
 * grouped by the family file that exercises it (Phase 10c).
 *
 * `coverage.test.ts` asserts the union of these ids plus the skip manifest equals
 * the whole 121-case slice — so a case that is neither exercised nor explicitly
 * skipped fails the build (no silent gaps). Each family file drives its `it.each`
 * off the matching list here, so the list and the tested cases stay in lockstep.
 *
 * Families (per the outline's file list):
 *  - **reads** — non-temporal single-entity reads (00xx / 02xx) + flat non-temporal
 *    navigate / exists reads (03xx flat);
 *  - **deep-fetch** — deep-fetch graph assembly (03xx graph, incl. the temporal
 *    deep-fetch subset);
 *  - **temporal** — temporal reads: exists-temporal-hop flat reads, processing-axis
 *    reads (05xx-read) and bitemporal reads (08xx);
 *  - **transactions** — audit-only writes (05xx-write) + batched / FK-ordered / per-key
 *    writes + read-your-own-writes (06xx);
 *  - **locking** — the automatic in-transaction read lock (06xx read) + the read-lock
 *    matrix (`0616`-`0619`, `api-conformance` lane) + optimistic locking happy + retry (07xx);
 *  - **boundary** — bounded automatic retry loop mechanics (`0710`-`0718`,
 *    `api-conformance` lane): auto-retry, conflict surfacing, transient retry,
 *    `retries: 0`, bound exhaustion, callback-withheld-on-abort.
 */

/** Non-temporal single-entity + flat navigate/exists reads (`reads.api-conformance.test.ts`). */
export const READS: readonly string[] = [
  // 00xx scalars / identity / quoting
  "0001-find-all",
  "0002-eq",
  "0003-scalar-types-roundtrip",
  "0006-quoted-reserved-identifier",
  // 02xx single-entity read algebra (0222 is skip-manifest'd — equivalentEncodings)
  "0201-not-eq",
  "0202-greater-than",
  "0203-greater-than-equals",
  "0204-less-than",
  "0205-less-than-equals",
  "0206-between",
  "0207-is-null",
  "0208-is-not-null",
  "0209-like",
  "0210-not-like",
  "0211-starts-with",
  "0212-ends-with",
  "0213-contains-escape",
  "0214-like-case-insensitive",
  "0215-contains-case-insensitive",
  "0216-in",
  "0217-not-in",
  "0218-and",
  "0219-or",
  "0220-not",
  "0221-none",
  "0223-group-precedence-ungrouped",
  "0224-order-by-limit",
  "0225-order-by-asc-limit",
  "0227-not-eq-null-excluded",
  "0228-not-in-null-excluded",
  "0229-and-three-operands",
  "0230-order-by-multi-key",
  "0231-starts-with-escape",
  "0232-ends-with-escape",
  // 03xx flat navigate / exists reads (non-temporal)
  "0301-navigate-items-sku",
  "0302-exists-items",
  "0303-not-exists-items",
  "0304-exists-items-quantity",
  "0305-navigate-statuses-code",
  "0306-not-exists-items-and-active",
  "0307-navigate-to-one-parent-predicate",
  "0308-exists-multi-hop-items-status",
  "0309-exists-to-one",
  "0317-not-exists-multi-hop",
  "0321-navigate-one-to-one",
];

/** Deep-fetch graph assembly (`deep-fetch.api-conformance.test.ts`), incl. temporal deep fetch. */
export const DEEP_FETCH: readonly string[] = [
  "0310-deep-fetch-to-one",
  "0311-deep-fetch-to-many",
  "0312-deep-fetch-multi-hop",
  "0313-deep-fetch-two-paths",
  "0314-deep-fetch-null-to-one",
  "0315-deep-fetch-empty-root",
  "0316-deep-fetch-shared-prefix",
  "0318-deep-fetch-empty-intermediate",
  "0319-deep-fetch-ordered-items-desc",
  "0320-deep-fetch-one-to-one",
  "0322-deep-fetch-ordered-tags-multikey",
  "0323-deep-fetch-ordered-nullable-nulls-last",
  "0324-deepfetch-temporal-both-latest",
  "0325-deepfetch-temporal-business-past",
  "0326-deepfetch-temporal-processing-past",
  "0327-deepfetch-temporal-both-past",
  "0328-deepfetch-temporal-multihop",
  "0329-deepfetch-temporal-to-one",
  "0331-deepfetch-processing-only-latest",
  "0332-deepfetch-processing-only-instant",
  "0333-deepfetch-nontemporal-to-temporal",
  "0334-deepfetch-temporal-to-nontemporal",
  "0336-deepfetch-temporal-ordered-root",
];

/** Temporal reads: exists-temporal flat reads + processing (05xx) + bitemporal (08xx). */
export const TEMPORAL: readonly string[] = [
  "0330-exists-temporal-hop",
  "0335-exists-temporal-hop-defaulted",
  "0501-as-of-now-defaulted",
  "0502-as-of-now-explicit",
  "0503-as-of-past-instant",
  "0504-history",
  "0505-as-of-now-with-predicate",
  "0506-as-of-range",
  "0507-as-of-boundary-exclusive",
  "0508-as-of-boundary-inclusive",
  "0801-bitemporal-as-of-now-both-axes",
  "0802-bitemporal-business-past-processing-now",
  "0803-bitemporal-both-axes-past",
  "0804-bitemporal-history",
  "0805-bitemporal-omitted-processing-default",
];

/** Transactions: timestamp-shape inserts (00xx write) + audit writes (05xx-write) + batched (06xx). */
export const TRANSACTIONS: readonly string[] = [
  "0004-timestamp-utc-normalization",
  "0005-timestamp-microsecond-precision",
  "0510-write-insert",
  "0511-write-update-chaining",
  "0512-write-terminate",
  "0604-batched-write",
  "0607-read-your-own-writes",
  "0608-rollback-discards-writes",
  "0612-fk-insert-ordering",
  "0613-batched-update-per-key",
];

/**
 * Locking: the automatic in-transaction read lock (`0603`), the no-op versioned
 * update (`0609`), the locking-mode version-advancing update (`0611`), the
 * versioned set-based materialize scenarios (`0614`/`0615` — a set-based update on
 * a versioned entity resolves the predicate, then updates per object, gated in
 * optimistic mode / ungated version-advancing in locking mode), the read-lock
 * matrix (`0616`-`0619`, `api-conformance` lane — object find locks, projection
 * omits, deep fetch locks every level, optimistic omits), optimistic-mode
 * version-column locking (07xx), and the optimistic × temporal close cases
 * (`0730`-`0733` — the observed processing-from `in_z` is the version analogue:
 * a gated close on a fresh `in_z` succeeds, a stale `in_z` conflicts, a retry
 * re-reads and succeeds, and a locking-mode zero-row close raises).
 */
export const LOCKING: readonly string[] = [
  "0603-read-lock",
  "0609-no-op-update-no-dml",
  "0611-versioned-update-locking-mode",
  "0614-versioned-set-based-materialize-optimistic",
  "0615-versioned-set-based-materialize-locking",
  "0616-locking-txn-object-find-locks",
  "0617-locking-txn-projection-omits-lock",
  "0618-locking-txn-deep-fetch-locks-every-level",
  "0619-optimistic-txn-reads-omit-lock",
  "0703-optimistic-lock-conflict",
  "0704-optimistic-lock-success",
  "0708-optimistic-lock-retry-after-conflict",
  "0730-temporal-close-optimistic-success",
  "0731-temporal-close-optimistic-conflict",
  "0732-temporal-close-retry-after-conflict",
  "0733-temporal-close-zero-rows-error",
];

/**
 * Boundary: the bounded automatic retry loop mechanics (`api-conformance` lane),
 * driven by a fault-injecting decorator wrapped around the shipped adapter. `0710`
 * is dual-covered — the harness runs its `attempts` golden AND the suite drives the
 * auto-retry-via-flag path here.
 */
export const BOUNDARY: readonly string[] = [
  "0710-optimistic-conflict-auto-retry",
  "0711-conflict-surfaces-without-optin",
  "0712-transient-retried-flag-unset",
  "0713-transient-retried-flag-set",
  "0714-conflict-auto-retry-loop",
  "0715-retry-flag-locking-mode",
  "0716-retries-zero-disables-loop",
  "0717-retry-bound-exhausted",
  "0718-callback-value-withheld-on-abort",
];

/** Every exercised case stem across all families. */
export const EXERCISED: readonly string[] = [
  ...READS,
  ...DEEP_FETCH,
  ...TEMPORAL,
  ...TRANSACTIONS,
  ...LOCKING,
  ...BOUNDARY,
];

/** The four-digit id of a case stem (`0002-eq` → `0002`). */
export function idOf(stem: string): string {
  return stem.slice(0, 4);
}
