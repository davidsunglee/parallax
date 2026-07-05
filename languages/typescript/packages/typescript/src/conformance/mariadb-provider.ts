/**
 * The **concrete** MariaDB `CompatibilityDatabaseProvider` — a Testcontainers
 * `mariadb:11.4` (booted through `@testcontainers/mysql`'s `MySqlContainer`) for
 * provisioning, assembled at the composition root and injected into the runner /
 * the MariaDB run lane through the port. The MariaDB sibling of
 * {@link PostgresProvider}.
 *
 * Like the Postgres provider it **delegates SQL execution to the shipped
 * `@parallax/db-mariadb` adapter** (bound to the container URI) — the same adapter
 * a real application imports — and owns only the two grader-side concerns the
 * adapter deliberately does not:
 *
 *  - **Provisioning** — booting a clean container, dropping every base table per
 *    `reset`, applying the derived MariaDB DDL, and loading fixtures. Fixture binds
 *    go through the adapter's `toMariaBinds` (the `infinity` → max-sentinel and
 *    ISO-instant → naive-UTC normalization), so a fixture authored once against
 *    native-infinity Postgres loads correctly here.
 *  - **Wire rendering** — the adapter returns **managed** scalars; the runner
 *    grades in the wire domain, so the provider renders each returned scalar to its
 *    canonical neutral wire form with the core serializer (`toWire`). *Managed at
 *    the boundary, wire at the grader* — no wire/grading logic lives in the adapter.
 *
 * There is **no `M12 → M11` edge**: the provider lives at the `@parallax/typescript`
 * composition root, the only place allowed to depend on a concrete adapter.
 */
import type { CompatibilityDatabaseProvider, ProviderRow } from "@parallax/conformance";
import { toWire } from "@parallax/core";
import { MariaDbDatabase, type MariaDbSession } from "@parallax/db-mariadb";
import { type Dialect, MARIADB_DIALECT, mariadbDialect } from "@parallax/dialect";
import { MySqlContainer, type StartedMySqlContainer } from "@testcontainers/mysql";

/** Pinned at a current stable MariaDB major (M12/DQ15), matching the Python oracle. */
const MARIADB_IMAGE = "mariadb:11.4";

/** Pause helper for the connect-retry loop. */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Poll a `select 1` until the freshly-booted MariaDB accepts connections. MariaDB's
 * entrypoint reports the port ready during bootstrap and then restarts the server
 * before the final ready state, so the first handshake can be dropped — retry until
 * the server is genuinely accepting connections (mirrors the oracle's retry loop).
 */
async function waitForReady(db: MariaDbDatabase, attempts = 40, delayMs = 1000): Promise<void> {
  let lastError: unknown;
  for (let i = 0; i < attempts; i += 1) {
    try {
      await db.execute("select 1", []);
      return;
    } catch (error) {
      lastError = error;
      await sleep(delayMs);
    }
  }
  throw new Error(`could not connect to MariaDB after ${attempts} attempts: ${String(lastError)}`);
}

/**
 * Render one column value the adapter returned (a **managed** scalar) to its
 * canonical neutral wire form (§3.2.1), delegating to the core serializer — the
 * same renderer the run envelope uses (`bigint` → decimal string, `ParallaxDecimal`
 * → fixed string, `Temporal.Instant` → µs UTC string, `Uint8Array` → lowercase hex;
 * the `infinity` sentinel passes through).
 */
function renderRowToWire(row: ProviderRow): ProviderRow {
  const out: ProviderRow = {};
  for (const [key, value] of Object.entries(row)) {
    out[key] = toWire(value);
  }
  return out;
}

/**
 * Render the fixture `INSERT` for a table, quoting every identifier through the M11
 * `mariadbDialect.quoteIdentifier` seam the DDL uses (backticks), with native `?`
 * placeholders (MariaDB binds positionally). Mirrors the Postgres provider's
 * `renderFixtureInsert` but for the MariaDB dialect.
 */
export function renderFixtureInsert(table: string, columns: readonly string[]): string {
  const target = mariadbDialect.quoteIdentifier(table);
  const colList = columns.map((column) => mariadbDialect.quoteIdentifier(column)).join(", ");
  const placeholders = columns.map(() => "?").join(", ");
  return `insert into ${target} (${colList}) values (${placeholders})`;
}

/** A Testcontainers-backed MariaDB provider for one suite run. */
export class MariaDbProvider implements CompatibilityDatabaseProvider {
  /** The dialect id, keying `goldenSql` / `expectedNativeCode` (harness port). */
  readonly dialect = MARIADB_DIALECT;

  /**
   * The concrete M11 {@link Dialect} the composition root injects — so the run lane
   * compiles and materializes against the same strategy the shipped adapter parses
   * with (the MariaDB analogue of `PostgresProvider.dialectImpl`).
   */
  readonly dialectImpl: Dialect = mariadbDialect;

  /** A lazily-opened SECOND adapter (independent connection) modeling a peer/concurrent writer. */
  private peerDb: MariaDbDatabase | undefined;

  private constructor(
    private readonly container: StartedMySqlContainer,
    /** The shipped adapter the harness delegates execution to. */
    private readonly db: MariaDbDatabase,
    /** The container connection URI (for opening an independent peer connection). */
    private readonly connectionUri: string,
  ) {}

  /** Boot a pinned MariaDB container and bind the shipped adapter to it. */
  static async start(): Promise<MariaDbProvider> {
    const container = await new MySqlContainer(MARIADB_IMAGE).start();
    const uri = container.getConnectionUri();
    const db = MariaDbDatabase.fromConnectionString(uri);
    await waitForReady(db);
    return new MariaDbProvider(container, db, uri);
  }

  /**
   * The shipped `@parallax/db-mariadb` adapter bound to this container — the
   * production execution path a run-lane `createParallax` handle would build on.
   */
  get database(): MariaDbDatabase {
    return this.db;
  }

  /**
   * A SECOND adapter over an INDEPENDENT connection (its own pool) to the same
   * container — a concurrent writer's connection, the MariaDB analogue of
   * {@link PostgresProvider.peer}. The optimistic-lock cases model the concurrent
   * writer (the `precondition`) here, committing on its own connection between a
   * unit of work's read and its gated write, so a write issued through
   * {@link database} while a `px.transaction` holds its connection never deadlocks.
   */
  get peer(): MariaDbDatabase {
    if (this.peerDb === undefined) {
      this.peerDb = MariaDbDatabase.fromConnectionString(this.connectionUri);
    }
    return this.peerDb;
  }

  /** Open a manual-commit session for the two-connection lock-contention proofs. */
  openSession(): Promise<MariaDbSession> {
    return this.db.openSession();
  }

  async reset(): Promise<void> {
    // A clean, empty database: drop every base table in the working schema. The
    // derived DDL omits foreign keys, so drop order is unconstrained.
    const rows = await this.db.execute(
      "select table_name as name from information_schema.tables " +
        "where table_schema = database() and table_type = 'BASE TABLE'",
      [],
    );
    for (const row of rows) {
      const name = String(row.name);
      await this.db.pool.query(`drop table if exists ${mariadbDialect.quoteIdentifier(name)}`);
    }
  }

  async applyDdl(statements: readonly string[]): Promise<void> {
    for (const statement of statements) {
      await this.db.pool.query(statement);
    }
  }

  async loadFixtures(
    table: string,
    columns: readonly string[],
    rows: readonly (readonly unknown[])[],
  ): Promise<void> {
    if (rows.length === 0) {
      return;
    }
    const insert = renderFixtureInsert(table, columns);
    for (const row of rows) {
      await this.db.executeWrite(insert, row);
    }
  }

  async query(sql: string, binds: readonly unknown[]): Promise<readonly ProviderRow[]> {
    const rows = await this.db.execute(sql, binds);
    return rows.map((row) => renderRowToWire(row));
  }

  async exec(sql: string, binds: readonly unknown[]): Promise<number> {
    return this.db.executeWrite(sql, binds);
  }

  async execRolledBack(sql: string, binds: readonly unknown[]): Promise<number> {
    return this.db.executeRolledBack(sql, binds);
  }

  async close(): Promise<void> {
    await this.peerDb?.close();
    await this.db.close();
    await this.container.stop();
  }
}
