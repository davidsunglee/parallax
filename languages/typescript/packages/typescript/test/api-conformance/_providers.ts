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
 * writer receives the injected m-dialect dialect for identifier quoting and reports
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
 * Whether the developer WRITE surface runs against `provider` AT ALL — the
 * WHOLE-DIALECT capability gate. All registered providers support it; this helper
 * remains so a future database that cannot host the write surface can be dropped
 * from {@link writeProviders} wholesale. A gap in ONE case is not this gate's
 * business — that is {@link MARIADB_GUARDED_CASES}.
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
 * Cases guarded OFF MariaDB — READ and WRITE alike — each for a SPECIFIC, named
 * dialect/runtime gap, mapped `stem -> reason`.
 *
 * This is the PER-CASE gap seam. It is deliberately distinct from
 * {@link supportsDeveloperWrites}, which is the WHOLE-DIALECT capability gate
 * ("does this database run the developer write surface at all?", `true` for every
 * registered provider). The two axes are orthogonal: a per-case gap must not be
 * expressed by turning off a whole dialect's write surface, and a dialect that
 * cannot write at all is not a list of stems. Read-versus-write is NOT an axis
 * here — stems are disjoint, so one map is unambiguous and keeps read/write parity
 * structural rather than maintained by hand across a mirrored pair.
 *
 * Guarding is dialect-scoped, never a suite-wide skip: a guarded case still runs on
 * every other selected database. `m-value-object-025` below stays fully exercised
 * under Postgres — the V1 claim's dialect — and stays in `EXERCISED` for
 * `coverage.test.ts`'s exercised-∪-skipped partition rather than moving to
 * `SKIPPED_IDS`, which is dialect-blind and would drop the claimed Postgres coverage.
 *
 * Each reason is rendered into the consuming suite's `it.skip` title (see
 * {@link guardedCases}), so the test output names WHICH check was skipped and WHY,
 * as `core/spec/database-provider-test-contract.md:90-95` requires.
 *
 * Two gaps that used to live here are both fixed and are gone:
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
 *    both the DDL derivation's reserved-word set AND the m-sql compiler's root/
 *    EXISTS-child `from` clause (now routed through `dialect.quoteIdentifier`,
 *    same as every column) quote it.
 */
export const MARIADB_GUARDED_CASES: ReadonlyMap<string, string> = new Map([
  [
    "m-value-object-025-write-insert-document",
    "known MariaDB adapter defect — the developer write path binds a value-object " +
      "document as a plain object, which reaches mysql2's query() text protocol and " +
      "escapes to the literal SQL text '[object Object]', failing MariaDB's json_valid " +
      "CHECK with error 4025; unclaimed by the Postgres-only V1 conformance profile, and " +
      "unfixed because slice-mvp-1 is scheduled for retirement with the slice-managed-1 " +
      "migration",
  ],
]);

/** Whether a case is guarded off `provider` (a MariaDB-specific per-case gap). */
export function caseGuarded(provider: SelectedProvider, stem: string): boolean {
  return provider.dialect === MARIADB_DIALECT && MARIADB_GUARDED_CASES.has(stem);
}

/** One guarded case as a suite reports it: the stem, and why it was guarded. */
export interface GuardedCase {
  readonly stem: string;
  readonly reason: string;
}

/**
 * The guarded subset of `stems` for `provider`, each paired with its reason — the
 * rows a suite feeds to `it.skip.each` so the reason lands IN the test output
 * rather than only in this file. Empty for every non-guarded provider/stem set.
 */
export function guardedCases(
  provider: SelectedProvider,
  stems: readonly string[],
): readonly GuardedCase[] {
  return stems
    .filter((stem) => caseGuarded(provider, stem))
    .map((stem) => ({ stem, reason: MARIADB_GUARDED_CASES.get(stem) ?? "" }));
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
