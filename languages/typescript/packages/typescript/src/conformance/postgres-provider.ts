/**
 * The **concrete** `CompatibilityDatabaseProvider` — Testcontainers `postgres:17`
 * for provisioning, assembled at the composition root and injected into the
 * runner through the port.
 *
 * Since Phase 10a the provider **delegates SQL execution to the shipped
 * `@parallax/db-postgres` adapter** (bound to the container URI) instead of
 * driving porsager itself. This keeps the harness on the exact production path:
 * the same adapter a real application imports is the one the whole 99-case slice
 * runs through. The provider owns only the two grader-side concerns the adapter
 * deliberately does not:
 *
 *  - **Provisioning** — booting a clean container, dropping/recreating the schema
 *    per `reset`, applying the derived DDL, and loading fixtures. It runs these on
 *    the adapter's porsager pool (`db.pool`) so the fixture-insert bind path keeps
 *    the adapter's `bytea` serializer (the `\xDEADBEEF` hex wire form; a blanket
 *    `String(v)` would flatten a `Buffer` to `""`).
 *  - **Wire rendering** — the adapter returns **managed** scalars (`bigint` /
 *    `ParallaxDecimal` / `Temporal.*` / `Uint8Array` / string, §2.2.1); the runner
 *    grades in the **wire domain**, so the provider renders each returned scalar
 *    to its canonical neutral wire form with the core serializer (`toWire`, which
 *    dispatches to `timestampToWire` / `toFixedString` / `bytesToHex`). *Managed at
 *    the boundary, wire at the grader* — no wire/grading logic lives in the shipped
 *    adapter.
 *
 * The grader (`compare.ts`) + the run envelope are unchanged, and there is **no
 * `M12 → M11` edge**: the provider lives at the `@parallax/typescript` composition
 * root, the only place allowed to depend on a concrete adapter.
 */
import type { CompatibilityDatabaseProvider, ProviderRow } from "@parallax/conformance";
import { toWire } from "@parallax/core";
import { PostgresDatabase } from "@parallax/db-postgres";
import { POSTGRES_DIALECT, quoteIdentifier, toPositionalPlaceholders } from "@parallax/dialect";
import { PostgreSqlContainer, type StartedPostgreSqlContainer } from "@testcontainers/postgresql";
import type { Sql } from "postgres";

/** Pinned at the latest stable Postgres major (M12/DQ15). */
const POSTGRES_IMAGE = "postgres:17";

/**
 * porsager types `unsafe`'s parameter array over the connection's custom-type
 * map; because the adapter registers parsers via an untyped `types` map, that map
 * widens to `never`, so a plain `unknown[]` is not assignable. Provisioning binds
 * are neutral scalars / wire-form values the driver serializes, so this localized
 * cast at the driver boundary is sound.
 */
type DriverParams = Parameters<Sql["unsafe"]>[1];
function asParams(binds: readonly unknown[]): DriverParams {
  return binds as DriverParams;
}

/**
 * Render one column value the adapter returned (a **managed** scalar) to its
 * canonical neutral **wire** form (§2.2.1). Delegates to the core serializer, the
 * SAME renderer the run envelope uses — so this is "truly just formatting" by
 * construction (`bigint` → decimal string, `ParallaxDecimal` → fixed string,
 * `Temporal.Instant` → µs UTC string, `Temporal.PlainDate`/`PlainTime` → ISO,
 * `Uint8Array` → lowercase hex; the `infinity` sentinel string passes through).
 */
function renderRowToWire(row: ProviderRow): ProviderRow {
  const out: ProviderRow = {};
  for (const [key, value] of Object.entries(row)) {
    out[key] = toWire(value);
  }
  return out;
}

/**
 * Render the fixture `INSERT` for a table from its raw physical descriptor
 * `table` / `columns`, quoting every identifier through the SAME M11
 * `quoteIdentifier` seam the DDL uses. This is the seam that keeps creation and
 * insertion from diverging: a reserved or non-simple name (`order`, `User`) that
 * the `CREATE TABLE` quoted is quoted identically here (mirrors the Python
 * oracle's `PostgresProvider.load`). Extracted as a pure function so the quoting
 * invariant is unit-testable without a database.
 */
export function renderFixtureInsert(table: string, columns: readonly string[]): string {
  const target = quoteIdentifier(table);
  const colList = columns.map(quoteIdentifier).join(", ");
  const placeholders = columns.map((_, i) => `$${i + 1}`).join(", ");
  return `insert into ${target} (${colList}) values (${placeholders})`;
}

/** A Testcontainers-backed Postgres provider for one suite run. */
export class PostgresProvider implements CompatibilityDatabaseProvider {
  readonly dialect = POSTGRES_DIALECT;

  private constructor(
    private readonly container: StartedPostgreSqlContainer,
    /** The shipped adapter the harness delegates execution to (Phase 10a). */
    private readonly db: PostgresDatabase,
  ) {}

  /** Boot a pinned Postgres container and bind the shipped adapter to it. */
  static async start(): Promise<PostgresProvider> {
    const container = await new PostgreSqlContainer(POSTGRES_IMAGE).start();
    const db = PostgresDatabase.fromConnectionString(container.getConnectionUri());
    return new PostgresProvider(container, db);
  }

  /** The adapter's porsager pool — used only for grader-side provisioning. */
  private get sql(): Sql {
    return this.db.pool;
  }

  /**
   * The shipped `@parallax/db-postgres` adapter bound to this container — the
   * production execution path. The Phase-10c API Conformance Suite builds its `px`
   * handle on THIS adapter (not a bespoke provider) so the exercised developer
   * code runs the exact adapter a real application imports, on the provisioned DB.
   */
  get database(): PostgresDatabase {
    return this.db;
  }

  async reset(): Promise<void> {
    await this.sql.unsafe("drop schema if exists public cascade");
    await this.sql.unsafe("create schema public");
  }

  async applyDdl(statements: readonly string[]): Promise<void> {
    for (const statement of statements) {
      await this.sql.unsafe(statement);
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
    // `table` / `columns` are raw physical descriptor names; quote them through
    // the same M11 seam the DDL uses so creation and insertion never diverge. The
    // insert binds on the adapter's pool, so the adapter's `bytea` serializer runs
    // and a `Buffer` payload renders to the `\x…` hex wire form (never `""`).
    const insert = renderFixtureInsert(table, columns);
    for (const row of rows) {
      await this.sql.unsafe(insert, asParams(row));
    }
  }

  async query(sql: string, binds: readonly unknown[]): Promise<readonly ProviderRow[]> {
    // Delegate execution to the shipped adapter (managed scalars), then render to
    // the canonical wire form the runner grades against.
    const rows = await this.db.execute(sql, binds);
    return rows.map((row) => renderRowToWire(row));
  }

  async exec(sql: string, binds: readonly unknown[]): Promise<number> {
    // A DML statement (writeSequence / conflict) needs the affected-row COUNT,
    // which the adapter's `execute` (rows-only) does not surface — so run it on the
    // adapter's pool directly, translating `?`→`$n` through the same M11 dialect
    // seam. Binds serialize through the adapter's registered types (incl. the
    // `bytea` serializer), so a write's byte payload renders correctly.
    const text = toPositionalPlaceholders(sql);
    const result = await this.sql.unsafe(text, asParams(binds));
    return result.count;
  }

  async close(): Promise<void> {
    await this.db.close();
    await this.container.stop();
  }
}
