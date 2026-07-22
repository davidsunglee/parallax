/**
 * The API Conformance Suite **coverage map**: every `slice-mvp-1` case
 * grouped by the family file that exercises it (Phase 10c).
 *
 * `coverage.test.ts` asserts the union of these ids plus the skip manifest equals
 * the whole 123-case slice — so a case that is neither exercised nor explicitly
 * skipped fails the build (no silent gaps). Each family file drives its `it.each`
 * off the matching list here, so the list and the tested cases stay in lockstep.
 *
 * Families (per the outline's file list):
 *  - **reads** — non-temporal single-entity reads (00xx / 02xx) + flat non-temporal
 *    navigate / exists reads (03xx flat);
 *  - **deep-fetch** — deep-fetch graph assembly (03xx graph, incl. the temporal
 *    deep-fetch subset);
 *  - **temporal** — temporal reads: exists-temporal-hop flat reads, Transaction-Time
 *    reads (05xx-read) and bitemporal reads (08xx);
 *  - **transactions** — audit-only writes (05xx-write) + batched / FK-ordered / per-key
 *    writes + read-your-own-writes (06xx);
 *  - **locking** — the automatic in-transaction read lock (06xx read) + the read-lock
 *    matrix (`m-read-lock-002`-`m-read-lock-005`, `api-conformance` lane) + optimistic locking happy + retry (07xx);
 *  - **boundary** — bounded automatic retry loop mechanics (`m-opt-lock-009`-`m-unit-work-004`,
 *    `api-conformance` lane): auto-retry, conflict surfacing, transient retry,
 *    `retries: 0`, bound exhaustion, callback-withheld-on-abort.
 */

/** Non-temporal single-entity + flat navigate/exists reads (`reads.api-conformance.test.ts`). */
export const READS: readonly string[] = [
  // 00xx scalars / identity / quoting
  "m-op-algebra-001-find-all",
  "m-op-algebra-002-eq",
  "m-core-001-scalar-types-roundtrip",
  "m-descriptor-001-quoted-reserved-identifier",
  // 02xx single-entity read algebra (m-op-algebra-024 is skip-manifest'd — equivalentEncodings)
  "m-op-algebra-003-not-eq",
  "m-op-algebra-004-greater-than",
  "m-op-algebra-005-greater-than-equals",
  "m-op-algebra-006-less-than",
  "m-op-algebra-007-less-than-equals",
  "m-op-algebra-008-between",
  "m-op-algebra-009-is-null",
  "m-op-algebra-010-is-not-null",
  "m-op-algebra-011-like",
  "m-op-algebra-012-not-like",
  "m-op-algebra-013-starts-with",
  "m-op-algebra-014-ends-with",
  "m-op-algebra-015-contains-escape",
  "m-op-algebra-016-like-case-insensitive",
  "m-op-algebra-017-contains-case-insensitive",
  "m-op-algebra-018-in",
  "m-op-algebra-019-not-in",
  "m-op-algebra-020-and",
  "m-op-algebra-021-or",
  "m-op-algebra-022-not",
  "m-op-algebra-023-none",
  "m-op-algebra-025-group-precedence-ungrouped",
  "m-op-algebra-026-order-by-limit",
  "m-op-algebra-027-order-by-asc-limit",
  "m-op-algebra-029-not-eq-null-excluded",
  "m-op-algebra-030-not-in-null-excluded",
  "m-op-algebra-031-and-three-operands",
  "m-op-algebra-032-order-by-multi-key",
  "m-op-algebra-033-starts-with-escape",
  "m-op-algebra-034-ends-with-escape",
  // 03xx flat navigate / exists reads (non-temporal)
  "m-navigate-001-items-sku",
  "m-navigate-002-exists-items",
  "m-navigate-003-not-exists-items",
  "m-navigate-004-exists-items-quantity",
  "m-navigate-005-statuses-code",
  "m-navigate-006-not-exists-items-and-active",
  "m-navigate-007-to-one-parent-predicate",
  "m-navigate-008-exists-multi-hop-items-status",
  "m-navigate-009-exists-to-one",
  "m-navigate-010-not-exists-multi-hop",
  "m-navigate-011-one-to-one",
];

/** Deep-fetch graph assembly (`deep-fetch.api-conformance.test.ts`), incl. temporal deep fetch. */
export const DEEP_FETCH: readonly string[] = [
  "m-deep-fetch-001-to-one",
  "m-deep-fetch-002-to-many",
  "m-deep-fetch-003-multi-hop",
  "m-deep-fetch-004-two-paths",
  "m-deep-fetch-005-null-to-one",
  "m-deep-fetch-006-empty-root",
  "m-deep-fetch-007-shared-prefix",
  "m-deep-fetch-008-empty-intermediate",
  "m-deep-fetch-009-ordered-items-desc",
  "m-deep-fetch-010-one-to-one",
  "m-deep-fetch-011-ordered-tags-multikey",
  "m-deep-fetch-012-ordered-nullable-nulls-last",
  "m-navigate-012-deepfetch-temporal-both-latest",
  "m-navigate-013-deepfetch-temporal-valid-time-past",
  "m-navigate-014-deepfetch-temporal-transaction-time-past",
  "m-navigate-015-deepfetch-temporal-both-past",
  "m-navigate-016-deepfetch-temporal-multihop",
  "m-navigate-017-deepfetch-temporal-to-one",
  "m-navigate-019-deepfetch-transaction-time-only-latest",
  "m-navigate-020-deepfetch-transaction-time-only-instant",
  "m-navigate-021-deepfetch-nontemporal-to-temporal",
  "m-navigate-022-deepfetch-temporal-to-nontemporal",
  "m-navigate-024-deepfetch-temporal-ordered-root",
];

/** Temporal reads: exists-temporal flat reads + processing (05xx) + bitemporal (08xx). */
export const TEMPORAL: readonly string[] = [
  "m-navigate-018-exists-temporal-hop",
  "m-navigate-023-exists-temporal-hop-defaulted",
  "m-temporal-read-001-as-of-latest-defaulted",
  "m-temporal-read-002-as-of-latest-explicit",
  "m-temporal-read-003-as-of-past-instant",
  "m-temporal-read-004-history",
  "m-temporal-read-005-as-of-latest-with-predicate",
  "m-temporal-read-006-as-of-range",
  "m-temporal-read-007-as-of-boundary-exclusive",
  "m-temporal-read-008-as-of-boundary-inclusive",
  "m-temporal-read-013-bitemporal-as-of-latest-both-dimensions",
  "m-temporal-read-014-bitemporal-valid-time-past-transaction-time-latest",
  "m-temporal-read-015-bitemporal-both-axes-past",
  "m-temporal-read-016-bitemporal-history",
  "m-temporal-read-017-bitemporal-omitted-transaction-time-default",
];

/** Transactions: timestamp-shape inserts (00xx write) + audit writes (05xx-write) + batched (06xx). */
export const TRANSACTIONS: readonly string[] = [
  "m-core-002-timestamp-utc-normalization",
  "m-core-003-timestamp-microsecond-precision",
  "m-audit-write-001-insert",
  "m-audit-write-002-update-chaining",
  "m-audit-write-003-terminate",
  "m-batch-write-001-set-based-flush",
  "m-unit-work-001-read-your-own-writes",
  "m-unit-work-002-rollback-discards-writes",
  "m-unit-work-003-fk-insert-ordering",
  "m-batch-write-002-update-per-key",
];

/**
 * Locking: the automatic in-transaction read lock (`m-read-lock-001`), the no-op versioned
 * update (`m-opt-lock-001`), the locking-mode version-advancing update (`m-opt-lock-002`), the read-lock
 * matrix (`m-read-lock-002`-`m-read-lock-005`, `api-conformance` lane — object find locks, projection
 * omits, deep fetch locks every level, optimistic omits), optimistic-mode
 * version-column locking (07xx), and the optimistic × temporal close cases
 * (`m-temporal-read-009`-`m-temporal-read-012` — the observed Transaction-Time start `in_z` is the version analogue:
 * a gated close on a fresh `in_z` succeeds, a stale `in_z` conflicts, a retry
 * re-reads and succeeds, and a locking-mode zero-row close raises).
 */
export const LOCKING: readonly string[] = [
  "m-read-lock-001-shared-suffix",
  "m-opt-lock-001-no-op-update-no-dml",
  "m-opt-lock-002-versioned-update-locking-mode",
  "m-read-lock-002-locking-txn-object-find-locks",
  "m-read-lock-003-locking-txn-projection-omits-lock",
  "m-read-lock-004-locking-txn-deep-fetch-locks-every-level",
  "m-read-lock-005-optimistic-txn-reads-omit-lock",
  "m-opt-lock-005-conflict",
  "m-opt-lock-006-success",
  "m-opt-lock-007-retry-after-conflict",
  "m-temporal-read-009-close-optimistic-success",
  "m-temporal-read-010-close-optimistic-conflict",
  "m-temporal-read-011-close-retry-after-conflict",
  "m-temporal-read-012-close-zero-rows-error",
];

/**
 * Boundary: the bounded automatic retry loop mechanics (`api-conformance` lane),
 * driven by a fault-injecting decorator wrapped around the shipped adapter. `m-opt-lock-009`
 * is dual-covered — the harness runs its `attempts` golden AND the suite drives the
 * auto-retry-via-flag path here.
 */
export const BOUNDARY: readonly string[] = [
  "m-opt-lock-009-conflict-auto-retry",
  "m-opt-lock-010-conflict-surfaces-without-optin",
  "m-auto-retry-001-transient-retried-flag-unset",
  "m-auto-retry-002-transient-retried-flag-set",
  "m-opt-lock-011-conflict-auto-retry-loop",
  "m-auto-retry-003-retry-flag-locking-mode",
  "m-auto-retry-004-retries-zero-disables-loop",
  "m-auto-retry-005-retry-bound-exhausted",
  "m-unit-work-004-callback-value-withheld-on-abort",
];

/**
 * Value objects (`value-objects.api-conformance.test.ts`): the typed
 * nested-predicate developer surface (m-value-object) — comparisons /
 * membership / null tests at shallow-to-three-level depth, to-many
 * exists/any-element/same-element (scoped `where`), the materialization graph
 * (the nested composite arriving with the owner in one round trip), and the
 * atomic document insert. The whole-document UPDATE / null-out /
 * temporal-chaining writes, the temporal value-object reads, and the `rejected`
 * negatives are reason-skipped (see `skip-manifest.ts`); the deep-fetch ×
 * value-object composition witness (`m-deep-fetch-018`) is likewise reason-skipped,
 * proven by the harness run lane.
 */
export const VALUE_OBJECTS: readonly string[] = [
  "m-value-object-001-nested-eq",
  "m-value-object-002-nested-deep-eq",
  "m-value-object-004-nested-not-eq",
  "m-value-object-005-nested-null-excluded",
  "m-value-object-006-nested-in",
  "m-value-object-007-nested-is-null",
  "m-value-object-008-nested-is-not-null",
  "m-value-object-009-nested-gt-cast",
  "m-value-object-010-nested-lt-cast",
  "m-value-object-011-nested-gte-deep-cast",
  "m-value-object-012-nested-lte-deep-cast",
  "m-value-object-013-nested-is-null-collapse",
  "m-value-object-014-nested-is-not-null-deep",
  "m-value-object-015-nested-exists-nonempty",
  "m-value-object-016-nested-not-exists-empty-or-null",
  "m-value-object-017-nested-any-element-eq",
  "m-value-object-018-nested-any-element-and-different",
  "m-value-object-019-nested-exists-scoped-where",
  "m-value-object-020-nested-not-exists-scoped-where",
  "m-value-object-021-nested-any-element-scalar-collapse",
  "m-value-object-022-nested-not-exists-scoped-scalar-collapse",
  "m-value-object-023-graph-nested-materialization",
  "m-value-object-024-graph-filtered-materialization",
  "m-value-object-025-write-insert-document",
];

/** Every exercised case stem across all families. */
export const EXERCISED: readonly string[] = [
  ...READS,
  ...DEEP_FETCH,
  ...TEMPORAL,
  ...TRANSACTIONS,
  ...LOCKING,
  ...BOUNDARY,
  ...VALUE_OBJECTS,
];

/** The per-module id of a case stem (`m-op-algebra-002-eq` → `m-op-algebra-002`). */
export function idOf(stem: string): string {
  return /^(m-[a-z0-9-]+-\d{3})/.exec(stem)?.[1] ?? stem;
}
