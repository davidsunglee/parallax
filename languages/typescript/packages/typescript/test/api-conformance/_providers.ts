/**
 * The API Conformance Suite **provider selection** helper — the one place the
 * dialect-agnostic suites reach a CONCRETE composition-root provider.
 *
 * Each suite parametrizes over {@link selectedProviders}, so it runs against every
 * database `PARALLAX_DATABASES` selects (default `postgres`; add `mariadb`, or a
 * comma-separated list, to fan out), mirroring the CLI's provider-selection
 * convention (`src/cli/parallax-conformance.ts`). Both concrete providers satisfy
 * {@link ApiConformanceProvider}, so a suite never names a concrete class.
 *
 * Docker gating lives here too ({@link HAS_DOCKER}): the Testcontainers lane is
 * skipped — reported, never silently passed — when no Docker daemon is reachable.
 *
 * ## Why the developer WRITE surface is guarded off MariaDB
 *
 * The developer write surface (`px.create` / `px.update` / `px.terminate`, spec
 * §4.1) is Postgres-only TODAY: the M7 / M8 / M10 write generators the runtime
 * lowers to (`runtime/writes.ts`) are not yet behind the M11 dialect seam. They emit
 * ANSI double-quote identifier quoting (MariaDB uses backticks and does not enable
 * `ANSI_QUOTES`) and a trailing `returning 1` (MariaDB `UPDATE` has no `RETURNING`,
 * and the rows-only `ParallaxDatabase` port cannot surface an `UPDATE`'s affected
 * count on MariaDB any other way). Making writes dialect-aware needs a port/dialect
 * affected-count seam — a separate phase. So the write-DRIVING cases (see
 * {@link WRITE_SURFACE_POSTGRES_ONLY}) run only on Postgres here; the MariaDB WRITE
 * path is already proven end-to-end by `test/mariadb-run.test.ts` against
 * `goldenSql.mariadb`. READ cases (which go through the dialect-aware M3 compiler)
 * run on both databases.
 */
import { execFileSync } from "node:child_process";
import { MARIADB_DIALECT, POSTGRES_DIALECT } from "@parallax/dialect";
import { MariaDbProvider } from "../../src/conformance/mariadb-provider.js";
import { PostgresProvider } from "../../src/conformance/postgres-provider.js";
import type { ApiConformanceProvider } from "./_harness.js";

/** A selected database: its dialect id, a human label, and a boot function. */
export interface SelectedProvider {
  /** The dialect id (`"postgres"` / `"mariadb"`) — keys the suite group name + write guard. */
  readonly dialect: string;
  /** A human label for the Testcontainers image (the suite group description). */
  readonly label: string;
  /** Boot a fresh provider (one container) for this database. */
  readonly start: () => Promise<ApiConformanceProvider>;
}

/** The registered providers, keyed by dialect id (mirrors the CLI's provider selection). */
const REGISTRY: Readonly<Record<string, SelectedProvider>> = {
  [POSTGRES_DIALECT]: {
    dialect: POSTGRES_DIALECT,
    label: "Testcontainers postgres:17",
    start: () => PostgresProvider.start(),
  },
  [MARIADB_DIALECT]: {
    dialect: MARIADB_DIALECT,
    label: "Testcontainers mariadb:11.4",
    start: () => MariaDbProvider.start(),
  },
};

/**
 * The providers this run exercises, from `PARALLAX_DATABASES` (comma-separated),
 * defaulting to `["postgres"]` when unset/empty — so the DEFAULT run is Postgres
 * exactly as before (no regression). An unknown key throws (a typo never silently
 * drops coverage).
 */
export function selectedProviders(): readonly SelectedProvider[] {
  const requested = (process.env.PARALLAX_DATABASES ?? "").trim();
  const keys =
    requested === ""
      ? [POSTGRES_DIALECT]
      : requested
          .split(",")
          .map((key) => key.trim())
          .filter((key) => key !== "");
  return keys.map((key) => {
    const provider = REGISTRY[key];
    if (provider === undefined) {
      throw new Error(
        `unknown PARALLAX_DATABASES entry '${key}' (known: ${Object.keys(REGISTRY).join(", ")})`,
      );
    }
    return provider;
  });
}

/**
 * Whether the developer WRITE surface runs against `provider` — Postgres only,
 * today (see the module note). A write-driving suite case guards on this; a read
 * case ignores it (reads are dialect-aware and run on both databases).
 */
export function supportsDeveloperWrites(provider: SelectedProvider): boolean {
  return provider.dialect !== MARIADB_DIALECT;
}

/**
 * The selected providers a WRITE-only suite (transactions / boundary) fans out over
 * — {@link selectedProviders} restricted to those that support developer writes. On
 * a MariaDB-only run this is empty, so the suite registers no group (the developer
 * write surface is Postgres-only today; see the module note).
 */
export function writeProviders(): readonly SelectedProvider[] {
  return selectedProviders().filter(supportsDeveloperWrites);
}

/**
 * The reason string a guarded write-driving case documents (surfaced in this
 * agent's report; the developer write surface is not yet behind the M11 dialect
 * seam — see the module note).
 */
export const WRITE_SURFACE_POSTGRES_ONLY =
  "developer write surface (px.create/update/terminate) is Postgres-only today: the " +
  "M7/M8/M10 write generators are not yet behind the M11 dialect seam (ANSI double-quote " +
  "quoting + `returning 1`, unsupported on MariaDB UPDATE). MariaDB writes are proven by " +
  "mariadb-run.test.ts.";

/**
 * READ/temporal cases guarded OFF MariaDB, each for a SPECIFIC dialect/runtime gap
 * (developer-WRITE cases guard separately via {@link supportsDeveloperWrites}):
 *
 *  - `0003` — a RAW `bytes` read: the runtime `find` projects a `bytes` column
 *    VERBATIM (`RuntimeSchema.rootProjection`), but the shipped MariaDB adapter's
 *    `bytes` parser assumes the `hex(col)` projection the conformance runner uses
 *    (`hexToBytes`), so a raw blob read fails at the adapter. The MariaDB hex path
 *    itself is proven by `mariadb-run.test.ts` (`1005`).
 *  - `0801`-`0805` — the `Position` table is a MariaDB reserved word (`POSITION()`).
 *    Neither the DDL derivation's curated reserved-word set nor the M3 compiler's
 *    root-table `from` clause (which is emitted UNQUOTED — Postgres tolerates
 *    `position`, MariaDB rejects it) quote it. Quoting the compiler root table is a
 *    dialect/compiler concern outside this harness.
 */
export const MARIADB_GUARDED_READS: ReadonlyMap<string, string> = new Map([
  [
    "0003-scalar-types-roundtrip",
    "raw `bytes` read: the shipped MariaDB adapter's bytes parser assumes the hex(col) " +
      "projection (hexToBytes), not the verbatim blob the runtime find projects",
  ],
  ...(
    [
      "0801-bitemporal-as-of-now-both-axes",
      "0802-bitemporal-business-past-processing-now",
      "0803-bitemporal-both-axes-past",
      "0804-bitemporal-history",
      "0805-bitemporal-omitted-processing-default",
    ] as const
  ).map(
    (stem) =>
      [
        stem,
        "the `Position` table is a MariaDB reserved word neither the DDL reserved-word set " +
          "nor the M3 compiler's UNQUOTED root-table FROM clause quotes",
      ] as const,
  ),
]);

/** Whether a READ/temporal case is guarded off `provider` (a MariaDB-specific dialect gap). */
export function readCaseGuarded(provider: SelectedProvider, stem: string): boolean {
  return provider.dialect === MARIADB_DIALECT && MARIADB_GUARDED_READS.has(stem);
}

/** True when a Docker daemon is reachable (gates the Testcontainers lane). */
export function dockerAvailable(): boolean {
  try {
    execFileSync("docker", ["info"], { stdio: "ignore", timeout: 10_000 });
    return true;
  } catch {
    return false;
  }
}

/** Whether Docker is reachable for this process (computed once at import). */
export const HAS_DOCKER = dockerAvailable();
