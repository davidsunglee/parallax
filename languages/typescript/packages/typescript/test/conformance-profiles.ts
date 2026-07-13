import {
  dialectStatements,
  discoverCasePaths,
  goldenEntries,
  type LoadedCase,
  loadCase,
} from "@parallax/conformance";

export type MatrixProfileKind = "full" | "partial";

export interface MatrixProfileCase {
  readonly id: string;
  readonly loaded: LoadedCase;
}

export interface MatrixProfileExclusion {
  readonly id: string;
  readonly loaded: LoadedCase;
  readonly reason: string;
}

export interface MatrixProfile {
  readonly name: string;
  readonly dialect: "postgres" | "mariadb";
  readonly kind: MatrixProfileKind;
  readonly description: string;
  readonly select: (item: MatrixProfileCase) => boolean;
  readonly exclusionReason?: (item: MatrixProfileCase) => string | undefined;
}

export const POSTGRES_READ_PROFILE_IDS: readonly string[] = [
  "m-op-algebra-001",
  "m-op-algebra-002",
  "m-descriptor-001",
  // The `m-op-algebra-003`–`-034` family MINUS the deleted `m-op-algebra-028`
  // (`distinct` on a projected column, removed with the base read-projection rule).
  ...Array.from({ length: 32 }, (_, i) => `m-op-algebra-${String(3 + i).padStart(3, "0")}`).filter(
    (id) => id !== "m-op-algebra-028",
  ),
];

export const POSTGRES_GRAPH_PROFILE_IDS: readonly string[] = [
  "m-navigate-001",
  "m-navigate-002",
  "m-navigate-003",
  "m-navigate-004",
  "m-navigate-005",
  "m-navigate-006",
  "m-navigate-007",
  "m-navigate-008",
  "m-navigate-009",
  "m-navigate-010",
  "m-navigate-011",
  "m-deep-fetch-001",
  "m-deep-fetch-002",
  "m-deep-fetch-003",
  "m-deep-fetch-004",
  "m-deep-fetch-005",
  "m-deep-fetch-006",
  "m-deep-fetch-007",
  "m-deep-fetch-008",
  "m-deep-fetch-009",
  "m-deep-fetch-010",
  "m-deep-fetch-011",
  "m-deep-fetch-012",
];

export const POSTGRES_TXN_PROFILE_IDS: readonly string[] = [
  "m-read-lock-001",
  "m-batch-write-001",
  "m-unit-work-001",
  "m-unit-work-002",
  "m-opt-lock-001",
  "m-opt-lock-002",
  "m-unit-work-003",
  "m-batch-write-002",
  "m-opt-lock-005",
  "m-opt-lock-006",
  "m-opt-lock-007",
  "m-opt-lock-009",
  "m-read-lock-006",
  "m-read-lock-007",
  "m-temporal-read-009",
  "m-temporal-read-010",
  "m-temporal-read-011",
  "m-temporal-read-012",
  "m-read-lock-008",
];

export const POSTGRES_TEMPORAL_PROFILE_IDS: readonly string[] = [
  "m-core-002",
  "m-core-003",
  "m-temporal-read-001",
  "m-temporal-read-002",
  "m-temporal-read-003",
  "m-temporal-read-004",
  "m-temporal-read-005",
  "m-temporal-read-006",
  "m-temporal-read-007",
  "m-temporal-read-008",
  "m-audit-write-001",
  "m-audit-write-002",
  "m-audit-write-003",
  "m-temporal-read-013",
  "m-temporal-read-014",
  "m-temporal-read-015",
  "m-temporal-read-016",
  "m-temporal-read-017",
  ...Array.from({ length: 13 }, (_, i) => `m-navigate-${String(12 + i).padStart(3, "0")}`),
];

export const MARIADB_FLAT_READ_PROFILE_IDS: readonly string[] = [
  "m-op-algebra-002",
  "m-descriptor-001",
  "m-op-algebra-016",
  "m-op-algebra-018",
  "m-op-algebra-026",
  "m-navigate-001",
  "m-read-lock-009",
  "m-temporal-read-021",
  "m-core-004",
];

export const MARIADB_DEEP_FETCH_PROFILE_IDS: readonly string[] = [
  "m-deep-fetch-012",
  "m-navigate-013",
  "m-navigate-015",
  "m-navigate-020",
  "m-navigate-024",
];

export const MARIADB_WRITE_PROFILE_IDS: readonly string[] = [
  "m-core-002",
  "m-core-003",
  "m-audit-write-001",
  // COR-26 DQ3 — the audit-chaining MariaDB backfill: the update-chaining `-002`,
  // terminate `-003`, and the new multi-attribute update `-004` now carry
  // goldenSql.mariadb, so the max-sentinel infinity round-trips on the audit close +
  // chain are proven on MariaDB, not only Postgres.
  "m-audit-write-002",
  "m-audit-write-003",
  "m-audit-write-004",
];

// COR-26 — the full-bitemporal `position` write/conflict cases carry goldenSql.mariadb
// (the harness reserved-word set became per-dialect, so `position` quotes as `position`
// on MariaDB while staying bare on Postgres). They JOIN the curated profile via
// `hasMariaDbGolden` AND now execute on the TypeScript run-lane (`mariadb-run.test.ts`):
// the temporal-insert builder emits the sqlglot-canonical quoted-table spacing
// (`` insert into `position` (…) ``, a space before `(` for a quoted table; the unquoted
// Postgres form `insert into position(…)` stays tight). The reference-harness oracle
// (`just oracle-test`, both dialects) is the independent second witness.
export const MARIADB_BITEMP_WRITE_PROFILE_IDS: readonly string[] = [
  "m-bitemp-write-001",
  "m-bitemp-write-002",
  "m-bitemp-write-003",
  "m-bitemp-write-006",
  "m-bitemp-write-007",
  "m-bitemp-write-008",
];

export const MARIADB_BITEMP_CONFLICT_PROFILE_IDS: readonly string[] = [
  "m-bitemp-write-004",
  "m-bitemp-write-005",
];

export const MARIADB_UNIQUE_PROFILE_IDS: readonly string[] = [
  "m-db-error-001",
  "m-db-error-002",
  "m-db-error-003",
  "m-db-error-008",
];

export const MARIADB_DEADLOCK_PROFILE_IDS: readonly string[] = ["m-db-error-004", "m-db-error-005"];

export const MARIADB_LOCK_WAIT_PROFILE_IDS: readonly string[] = [
  "m-db-error-006",
  "m-db-error-007",
];

export const MARIADB_CURATED_PROFILE_IDS: readonly string[] = [
  ...MARIADB_FLAT_READ_PROFILE_IDS,
  ...MARIADB_DEEP_FETCH_PROFILE_IDS,
  ...MARIADB_WRITE_PROFILE_IDS,
  ...MARIADB_BITEMP_WRITE_PROFILE_IDS,
  ...MARIADB_BITEMP_CONFLICT_PROFILE_IDS,
  ...MARIADB_UNIQUE_PROFILE_IDS,
  ...MARIADB_DEADLOCK_PROFILE_IDS,
  ...MARIADB_LOCK_WAIT_PROFILE_IDS,
];

const MARIADB_CURATED_ID_SET = new Set(MARIADB_CURATED_PROFILE_IDS);

export const POSTGRES_FULL_PROFILE: MatrixProfile = {
  name: "postgres-full-slice-mvp-1",
  dialect: "postgres",
  kind: "full",
  description: "Full harness-lane slice-mvp-1 m-case-format profile over Postgres.",
  select: ({ loaded }) => loaded.tags.includes("slice-mvp-1") && loaded.lane !== "api-conformance",
};

export const POSTGRES_READ_PROFILE: MatrixProfile = fixedIdProfile(
  "postgres-read-focused",
  "postgres",
  "Historical Docker-backed single-entity read profile, now a named subset.",
  POSTGRES_READ_PROFILE_IDS,
);

export const POSTGRES_GRAPH_PROFILE: MatrixProfile = fixedIdProfile(
  "postgres-graph-focused",
  "postgres",
  "Historical Docker-backed non-temporal navigation graph profile, now a named subset.",
  POSTGRES_GRAPH_PROFILE_IDS,
);

export const POSTGRES_TXN_PROFILE: MatrixProfile = fixedIdProfile(
  "postgres-txn-focused",
  "postgres",
  "Historical Docker-backed transaction profile, now a named subset.",
  POSTGRES_TXN_PROFILE_IDS,
);

export const POSTGRES_TEMPORAL_PROFILE: MatrixProfile = fixedIdProfile(
  "postgres-temporal-focused",
  "postgres",
  "Historical Docker-backed temporal profile, now a named subset.",
  POSTGRES_TEMPORAL_PROFILE_IDS,
);

/**
 * The value-object cases carry `mariadb` golden SQL, but MariaDB parity for them
 * is proven directly by the Phase-10 dialect-lowering compile tests
 * (`value-object-lowering.test.ts` / `value-object.test.ts`), NOT this run-lane
 * curated profile. Excluding them keeps the curated profile at its original
 * 25-case marquee set (impl-spec §5.4) rather than ballooning it with every
 * value-object golden. COR-26 grew the marquee write set by the three audit-chaining
 * MariaDB backfill cases (m-audit-write-002/-003/-004), lifting the profile to 28, then
 * by the eight full-bitemporal `position` write/conflict cases (m-bitemp-write-001..008)
 * once the harness reserved-word set became per-dialect, lifting it to 36.
 */
const VALUE_OBJECT_MARIADB_REASON =
  "value-object MariaDB parity is proven by the Phase-10 direct compile tests, not this run-lane profile";

// COR-26 Phase 5 — the pk-gen and writable-scalar write cases carry goldenSql.mariadb
// (pk-gen SQL is portable; the scalar round-trips are dual-dialect witnesses), but
// their MariaDB parity is proven by the reference-harness oracle on BOTH dialects
// (`just oracle-test`), not this TypeScript run-lane profile — keeping the curated
// MariaDB run lane the same marquee dialect/error set and off the newly-promoted
// scalar/pk-gen surface.
const PK_GEN_MARIADB_REASON =
  "pk-gen MariaDB parity is proven by the reference-harness oracle on both dialects, not this run-lane profile";
const SCALAR_WRITE_MARIADB_REASON =
  "writable-scalar MariaDB parity is proven by the reference-harness oracle on both dialects, not this run-lane profile";

function isValueObjectCase(loaded: LoadedCase): boolean {
  return loaded.tags.includes("m-value-object");
}

function isPkGenCase(loaded: LoadedCase): boolean {
  return loaded.tags.includes("m-pk-gen");
}

function isScalarWriteCase(loaded: LoadedCase): boolean {
  return loaded.raw.model === "models/writable-scalars.yaml";
}

export const MARIADB_CURATED_PROFILE: MatrixProfile = {
  name: "mariadb-curated-36",
  dialect: "mariadb",
  kind: "partial",
  description:
    "Curated MariaDB m-case-format profile: every harness-lane slice case with goldenSql.mariadb (excluding value-object cases, proven by Phase-10 compile tests) plus marquee dialect/error cases.",
  select: ({ id, loaded }) =>
    (POSTGRES_FULL_PROFILE.select({ id, loaded }) &&
      hasMariaDbGolden(loaded) &&
      !isValueObjectCase(loaded) &&
      !isPkGenCase(loaded) &&
      !isScalarWriteCase(loaded)) ||
    MARIADB_CURATED_ID_SET.has(id),
  exclusionReason: ({ id, loaded }) => {
    if (!POSTGRES_FULL_PROFILE.select({ id: caseId(loaded.casePath), loaded })) {
      return undefined;
    }
    if (MARIADB_CURATED_ID_SET.has(id)) {
      return undefined;
    }
    if (isValueObjectCase(loaded)) {
      return VALUE_OBJECT_MARIADB_REASON;
    }
    if (isScalarWriteCase(loaded)) {
      return SCALAR_WRITE_MARIADB_REASON;
    }
    if (isPkGenCase(loaded)) {
      return PK_GEN_MARIADB_REASON;
    }
    return hasMariaDbGolden(loaded)
      ? undefined
      : "no goldenSql.mariadb in this partial MariaDB profile";
  },
};

export const MATRIX_PROFILES: readonly MatrixProfile[] = [
  POSTGRES_FULL_PROFILE,
  POSTGRES_READ_PROFILE,
  POSTGRES_GRAPH_PROFILE,
  POSTGRES_TXN_PROFILE,
  POSTGRES_TEMPORAL_PROFILE,
  MARIADB_CURATED_PROFILE,
];

/**
 * Every discovered corpus case, discovered + parsed **once per process** and then
 * memoized. `caseById` / `casesForProfile` / `exclusionsForProfile` each fan out
 * over the full corpus, so without the cache a single test that resolves many ids
 * (e.g. the curated-profile coverage assertion, which touches 36) re-reads and
 * re-parses all ~200 case + model + fixture YAMLs *per id* — enough synchronous
 * I/O to blow the default 5s test timeout on a contended runner. The m-case-format corpus is
 * static within a run, so caching the loaded set is safe.
 */
let cachedProfileCases: readonly MatrixProfileCase[] | undefined;

export function allProfileCases(): readonly MatrixProfileCase[] {
  if (cachedProfileCases === undefined) {
    cachedProfileCases = discoverCasePaths().map((path) => ({
      id: caseId(path),
      loaded: loadCase(path),
    }));
  }
  return cachedProfileCases;
}

export function casesForProfile(
  profile: MatrixProfile,
  cases: readonly MatrixProfileCase[] = allProfileCases(),
): readonly MatrixProfileCase[] {
  return cases.filter((item) => profile.select(item));
}

export function exclusionsForProfile(
  profile: MatrixProfile,
  cases: readonly MatrixProfileCase[] = allProfileCases(),
): readonly MatrixProfileExclusion[] {
  return cases.flatMap((item) => {
    const reason = profile.exclusionReason?.(item);
    return reason === undefined ? [] : [{ ...item, reason }];
  });
}

export function caseById(id: string): MatrixProfileCase {
  const found = allProfileCases().find((item) => item.id === id);
  if (found === undefined) {
    throw new Error(`no corpus case with id '${id}'`);
  }
  return found;
}

function fixedIdProfile(
  name: string,
  dialect: "postgres" | "mariadb",
  description: string,
  ids: readonly string[],
): MatrixProfile {
  const set = new Set(ids);
  return {
    name,
    dialect,
    kind: "partial",
    description,
    select: ({ id }) => set.has(id),
  };
}

function hasMariaDbGolden(loaded: LoadedCase): boolean {
  return dialectStatements(goldenEntries(loaded.raw), "mariadb").length > 0;
}

function caseId(path: string): string {
  const match = /(m-[a-z0-9-]+-\d{3})-[^/]*\.ya?ml$/.exec(path);
  if (match === null) {
    throw new Error(`cannot derive case id from '${path}'`);
  }
  return match[1] as string;
}
