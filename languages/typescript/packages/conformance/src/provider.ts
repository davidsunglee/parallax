/**
 * The `CompatibilityDatabaseProvider` **port** — the only database surface the
 * runner depends on (design "provider placement" decision).
 *
 * `@parallax/conformance` imports **no driver and no dialect package**: it
 * depends only on this interface. The concrete provider (Testcontainers
 * `postgres:17` + the `postgres` driver, delegating type coercion / SQL
 * execution to `@parallax/dialect`) lives in the `@parallax/typescript`
 * composition root and is injected through this port. That keeps the harness
 * allowlist-clean and keeps `@parallax/dialect` free of a Testcontainers
 * dependency.
 *
 * The seam mirrors the Python harness `DatabaseProvider`: `reset` / `applyDdl` /
 * `loadFixtures` / `query` / `exec`, each already normalizing values to the
 * neutral wire form so the runner compares against goldens directly.
 */

/** A materialized row keyed by projected column name. Values are wire-normalized. */
export type ProviderRow = Record<string, unknown>;

/**
 * A clean, isolated database for one case run. Implementations provision a fresh
 * schema per `reset()` so each case starts from an empty, deterministic state.
 */
export interface CompatibilityDatabaseProvider {
  /** The dialect this provider answers for (e.g. `"postgres"`). */
  readonly dialect: string;

  /** Drop and recreate the schema — a clean, empty database. */
  reset(): Promise<void>;

  /** Apply the ordered `CREATE TABLE` DDL statements derived from the descriptor. */
  applyDdl(statements: readonly string[]): Promise<void>;

  /**
   * Insert fixture rows into a table. `columns` are the physical column names in
   * descriptor order; each row is a value list aligned to `columns` (missing
   * attributes arrive as `null`).
   */
  loadFixtures(
    table: string,
    columns: readonly string[],
    rows: readonly (readonly unknown[])[],
  ): Promise<void>;

  /**
   * Execute a read query (canonical `?`-placeholder SQL + ordered binds) and
   * return its rows with values already normalized to the neutral wire form
   * (the dialect's raw-string parsers run inside the provider).
   */
  query(sql: string, binds: readonly unknown[]): Promise<readonly ProviderRow[]>;

  /**
   * Execute a DML statement (`?` placeholders + binds) and return the affected
   * row count (for writeSequence / conflict shapes in later phases).
   */
  exec(sql: string, binds: readonly unknown[]): Promise<number>;

  /**
   * Apply a DML statement inside a transaction and then ROLL IT BACK, returning
   * the affected-row count it reported before the rollback. This is the M8 abort
   * contract's execution seam: the write lands inside an atomic scope that is
   * discarded, so a subsequent `query` observes the ORIGINAL rows. Used by the
   * `rollback: true` scenario write step.
   */
  execRolledBack(sql: string, binds: readonly unknown[]): Promise<number>;

  /** Release the database resources held by this provider. */
  close(): Promise<void>;
}
