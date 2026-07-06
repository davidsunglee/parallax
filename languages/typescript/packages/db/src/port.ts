/**
 * `@parallax/db` — the abstract runtime **database port** (m-db-port decomposition,
 * core spec `m-db-port.md`, layer 2).
 *
 * This is the execution interface every layer above the seam calls to run
 * compiled SQL and demarcate transactions: `execute(sql, binds) → rows`,
 * `executeWrite(sql, binds) → affectedRows`, and an optional
 * `transaction(body)`. It **depends on nothing application-specific** —
 * no driver, no concrete database, no dialect, no harness — beyond the neutral
 * `@parallax/core` types its contract names, so any layer may hold the port
 * without acquiring a database dependency.
 *
 * The port carries the **normalize-at-boundary contract**: a concrete adapter
 * behind it (`@parallax/db-postgres`, and future `@parallax/db-*`) returns rows
 * whose scalars are already **managed values** — `bigint` / `ParallaxDecimal` /
 * `Temporal.Instant` / `Temporal.PlainDate` / `Temporal.PlainTime` /
 * `Uint8Array` / string — produced by the dialect layer's parse functions, never
 * raw driver representations. Nothing above the seam ever sees a driver's `Date`,
 * a binary-float `numeric`, or a raw byte buffer. Wire rendering + grading is a
 * grader concern that lives above the port, never in the port or an adapter
 * (*managed at the boundary, wire at the grader*).
 *
 * Extracted cleanly out of the `@parallax/typescript` runtime at this point (no
 * back-compat re-export — there were no external consumers of the inline
 * definition). The method is named `execute` for parity with the core m-db-port
 * contract; `ParallaxClock` stays in `@parallax/typescript` because it is a
 * runtime strategy, not a database concern.
 */

/** A row as the database port returns it (physical column name → managed value). */
export type ParallaxRow = Record<string, unknown>;

/**
 * The database port the runtime executes through. A concrete adapter (the
 * shippable `@parallax/db-postgres` over a connection string / pool, or an
 * application's own driver) implements it; the runtime imports no driver.
 * `execute` runs a compiled row-returning statement, `executeWrite` runs a DML
 * statement and returns the native affected-row count, and `transaction` runs a
 * callback with a bound connection.
 */
export interface ParallaxDatabase {
  /**
   * Execute a compiled statement (`?`-placeholder SQL + ordered binds) and
   * return its rows. Row scalars are **managed values** normalized at the
   * adapter boundary (§3.2.1), not raw driver output.
   */
  execute(sql: string, binds: readonly unknown[]): Promise<readonly ParallaxRow[]>;
  /**
   * Execute a compiled write statement (`?`-placeholder SQL + ordered binds) and
   * return the database driver's affected-row count. Write SQL is emitted without
   * dialect-specific row-returning clauses; concrete adapters surface their
   * native count through this method.
   */
  executeWrite(sql: string, binds: readonly unknown[]): Promise<number>;
  /**
   * Run `body` inside a database transaction, committing on resolve and rolling
   * back on throw. A connection-bound `ParallaxDatabase` is passed to `body`.
   */
  transaction?<T>(body: (tx: ParallaxDatabase) => Promise<T>): Promise<T>;
}
