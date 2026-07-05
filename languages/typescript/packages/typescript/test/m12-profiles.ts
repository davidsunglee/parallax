import { discoverCasePaths, type LoadedCase, loadCase } from "@parallax/conformance";

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
  "0001",
  "0002",
  "0006",
  ...Array.from({ length: 32 }, (_, i) => String(201 + i).padStart(4, "0")),
];

export const POSTGRES_GRAPH_PROFILE_IDS: readonly string[] = Array.from({ length: 23 }, (_, i) =>
  String(301 + i).padStart(4, "0"),
);

export const POSTGRES_TXN_PROFILE_IDS: readonly string[] = [
  "0603",
  "0604",
  "0607",
  "0608",
  "0609",
  "0611",
  "0612",
  "0613",
  "0614",
  "0615",
  "0703",
  "0704",
  "0708",
  "0710",
  "0730",
  "0731",
  "0732",
  "0733",
];

export const POSTGRES_TEMPORAL_PROFILE_IDS: readonly string[] = [
  "0004",
  "0005",
  "0501",
  "0502",
  "0503",
  "0504",
  "0505",
  "0506",
  "0507",
  "0508",
  "0510",
  "0511",
  "0512",
  "0801",
  "0802",
  "0803",
  "0804",
  "0805",
  ...Array.from({ length: 13 }, (_, i) => String(324 + i).padStart(4, "0")),
];

export const MARIADB_FLAT_READ_PROFILE_IDS: readonly string[] = [
  "0002",
  "0006",
  "0214",
  "0216",
  "0224",
  "0301",
  "1001",
  "1002",
  "1005",
];

export const MARIADB_DEEP_FETCH_PROFILE_IDS: readonly string[] = [
  "0323",
  "0325",
  "0327",
  "0332",
  "0336",
];

export const MARIADB_WRITE_PROFILE_IDS: readonly string[] = ["0004", "0005", "0510"];

export const MARIADB_UNIQUE_PROFILE_IDS: readonly string[] = ["0720", "0721", "0722", "0727"];

export const MARIADB_DEADLOCK_PROFILE_IDS: readonly string[] = ["0723", "0724"];

export const MARIADB_LOCK_WAIT_PROFILE_IDS: readonly string[] = ["0725", "0726"];

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
  description: "Full harness-lane slice-mvp-1 M12 profile over Postgres.",
  select: ({ loaded }) => loaded.tags.includes("slice-mvp-1") && loaded.lane !== "api-conformance",
};

export const POSTGRES_READ_PROFILE: MatrixProfile = fixedIdProfile(
  "postgres-read-focused",
  "postgres",
  "Historical Docker-backed 00xx/02xx read profile, now a named subset.",
  POSTGRES_READ_PROFILE_IDS,
);

export const POSTGRES_GRAPH_PROFILE: MatrixProfile = fixedIdProfile(
  "postgres-graph-focused",
  "postgres",
  "Historical Docker-backed non-temporal 03xx graph profile, now a named subset.",
  POSTGRES_GRAPH_PROFILE_IDS,
);

export const POSTGRES_TXN_PROFILE: MatrixProfile = fixedIdProfile(
  "postgres-txn-focused",
  "postgres",
  "Historical Docker-backed 06xx/07xx transaction profile, now a named subset.",
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
    "Curated MariaDB M12 profile: every harness-lane slice case with goldenSql.mariadb plus marquee dialect/error cases.",
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

export function allProfileCases(): readonly MatrixProfileCase[] {
  return discoverCasePaths().map((path) => ({
    id: caseId(path),
    loaded: loadCase(path),
  }));
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

export function profileCaseIds(profile: MatrixProfile): readonly string[] {
  return casesForProfile(profile)
    .map(({ id }) => id)
    .sort();
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
  return (loaded.raw.goldenSql as { mariadb?: unknown } | undefined)?.mariadb !== undefined;
}

function caseId(path: string): string {
  const match = /(\d{4})-[^/]*\.ya?ml$/.exec(path);
  if (match === null) {
    throw new Error(`cannot derive case id from '${path}'`);
  }
  return match[1] as string;
}
