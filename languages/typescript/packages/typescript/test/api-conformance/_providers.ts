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
 * Developer writes run through the same selected provider set as reads. The runtime
 * writer receives the injected M11 dialect for identifier quoting and reports
 * affected rows through `ParallaxDatabase.executeWrite`, so Postgres and MariaDB
 * both exercise the developer write surface when selected.
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
 * drops coverage), and so does a NON-empty value that resolves to zero keys — e.g.
 * `","` or `" , "`, which split/trim/filter down to `[]`. Without that guard a
 * comma-only value would silently select no databases (zero coverage, no error);
 * it must fail loudly, same spirit as the unknown-key throw. (A value that is empty
 * OR pure whitespace trims to `""` and takes the unchanged `[postgres]` default.)
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
  if (requested !== "" && keys.length === 0) {
    throw new Error(
      `PARALLAX_DATABASES='${process.env.PARALLAX_DATABASES}' selects no databases ` +
        `(comma/whitespace only); set a comma-separated list of known keys ` +
        `(${Object.keys(REGISTRY).join(", ")}) or leave it unset for the ${POSTGRES_DIALECT} default`,
    );
  }
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
 * Whether the developer WRITE surface runs against `provider`. All registered
 * providers support it; this helper remains so mixed read/write suites can keep a
 * single guard point for future provider-specific gaps.
 */
export function supportsDeveloperWrites(provider: SelectedProvider): boolean {
  void provider;
  return true;
}

/**
 * The selected providers a WRITE-only suite (transactions / boundary) fans out over
 * — {@link selectedProviders} restricted to those that support developer writes.
 */
export function writeProviders(): readonly SelectedProvider[] {
  return selectedProviders().filter(supportsDeveloperWrites);
}

/**
 * READ/temporal cases guarded OFF MariaDB, each for a SPECIFIC dialect/runtime gap
 * (developer-WRITE cases guard separately via {@link supportsDeveloperWrites}).
 *
 * Currently EMPTY — the two gaps that used to live here are both fixed:
 *  - `m-core-001` (a RAW `bytes` read) — the shipped MariaDB adapter's `typeCast` now
 *    reads a raw (un-wrapped) `bytes` column via the driver's raw `Buffer`
 *    (`field.buffer()`) instead of parsing `field.string()` through the hex-text
 *    parser, so the runtime `find`'s VERBATIM `bytes` projection
 *    (`RuntimeSchema.rootProjection`) materializes correctly. It is told apart
 *    from the dialect's `hex(col)` projection by the codebase-owned `_hex`
 *    output-alias convention (`mysql2`'s `Field.name`; see `adapter.ts`'s
 *    `typeCast` doc) — that hex path is unaffected (still proven by
 *    `mariadb-run.test.ts`'s `m-core-004`).
 *  - `m-temporal-read-013`-`m-temporal-read-017` (the `Position` table, a MariaDB reserved word `POSITION()`) —
 *    both the DDL derivation's reserved-word set AND the M3 compiler's root/
 *    EXISTS-child `from` clause (now routed through `dialect.quoteIdentifier`,
 *    same as every column) quote it.
 *
 * Kept as an (empty) `ReadonlyMap` + {@link readCaseGuarded} helper — a
 * ready-made guard point for a future dialect/runtime gap.
 */
export const MARIADB_GUARDED_READS: ReadonlyMap<string, string> = new Map();

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
