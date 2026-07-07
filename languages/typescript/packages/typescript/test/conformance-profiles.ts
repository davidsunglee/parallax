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
  ...Array.from({ length: 32 }, (_, i) => `m-op-algebra-${String(3 + i).padStart(3, "0")}`),
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
  "m-opt-lock-003",
  "m-opt-lock-004",
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

export const MARIADB_CURATED_PROFILE: MatrixProfile = {
  name: "mariadb-curated-25",
  dialect: "mariadb",
  kind: "partial",
  description:
    "Curated MariaDB m-case-format profile: every harness-lane slice case with goldenSql.mariadb plus marquee dialect/error cases.",
  select: ({ id, loaded }) =>
    (POSTGRES_FULL_PROFILE.select({ id, loaded }) && hasMariaDbGolden(loaded)) ||
    MARIADB_CURATED_ID_SET.has(id),
  exclusionReason: ({ loaded }) =>
    POSTGRES_FULL_PROFILE.select({ id: caseId(loaded.casePath), loaded }) &&
    !hasMariaDbGolden(loaded)
      ? "no goldenSql.mariadb in this partial MariaDB profile"
      : undefined,
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
 * (e.g. the curated-profile coverage assertion, which touches 25) re-reads and
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
