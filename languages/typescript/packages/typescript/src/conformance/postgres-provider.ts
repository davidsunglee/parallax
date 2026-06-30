/**
 * The **concrete** `CompatibilityDatabaseProvider` — Testcontainers `postgres:17`
 * + the `postgres` (porsager) driver — assembled at the composition root and
 * injected into the runner through the port.
 *
 * It owns provisioning (boot a clean container, drop/recreate the schema per
 * `reset`) and delegates every SQL decision to `@parallax/dialect` (M11): the
 * `?`→`$n` placeholder translation and the raw-string type coercion that
 * normalizes driver output to the neutral wire form at the adapter boundary
 * (§2.2.1). The driver lives only here — `@parallax/conformance` and
 * `@parallax/dialect` stay driver-free.
 *
 * Type coercion is **driver-independent**: porsager (like `pg`) parses
 * `timestamptz` into a millisecond `Date` and `numeric` into a float by default,
 * which would violate the M0 microsecond / exact-decimal contracts. We register
 * raw-text parsers per OID and materialize the value to its canonical wire form
 * (int64 / decimal → string, µs instant string, bytes → hex), exactly the
 * §2.2.1 "normalize at the adapter boundary" rule.
 */
import type { CompatibilityDatabaseProvider, ProviderRow } from "@parallax/conformance";
import {
  bytesToHex,
  type Infinity as InfinitySentinel,
  type ParallaxDecimal,
  type Temporal,
  timestampToWire,
} from "@parallax/core";
import {
  numericFromRaw,
  POSTGRES_DIALECT,
  RAW_TEXT_OIDS,
  timestampFromDb,
  toPositionalPlaceholders,
} from "@parallax/dialect";
import { PostgreSqlContainer, type StartedPostgreSqlContainer } from "@testcontainers/postgresql";
import postgres, { type Sql } from "postgres";

/** Pinned at the latest stable Postgres major (M12/DQ15). */
const POSTGRES_IMAGE = "postgres:17";

/**
 * porsager types `unsafe`'s parameter array over the connection's custom-type
 * map; because we register parsers via an untyped `types` cast, that map widens
 * to `never`, so a plain `unknown[]` is not assignable. The binds are already
 * neutral scalars / wire-form values the driver serializes, so this localized
 * cast at the driver boundary is sound.
 */
type DriverParams = Parameters<Sql["unsafe"]>[1];
function asParams(binds: readonly unknown[]): DriverParams {
  return binds as DriverParams;
}

/** Stable Postgres OIDs whose driver default we override to raw-text parsing. */
const OID = {
  date: 1082,
  time: 1083,
  uuid: 2950,
} as const;

/**
 * A `postgres` custom type that forces an OID to be **read** as raw text and
 * materialized by `parse`.
 *
 * `serialize` is load-bearing on the *bind* path: porsager looks up the
 * serializer by the prepared statement's parameter OID (what the server says the
 * column is), so registering a custom `int8` / `numeric` / `date` type means our
 * serializer runs when a fixture value binds to that column. The wire protocol
 * is text, so it MUST return a string (porsager's own `int8`/`numeric` defaults
 * likewise stringify). A `null` binds as SQL NULL untouched.
 */
function rawType(oid: number, parse: (raw: string) => unknown) {
  return {
    to: oid,
    from: [oid],
    serialize: (v: unknown) => (v === null || v === undefined ? v : String(v)),
    parse,
  };
}

/** Render a coerced scalar to its canonical neutral **wire** form (§2.2.1). */
function toWireScalar(
  value: bigint | ParallaxDecimal | Temporal.Instant | InfinitySentinel,
): string {
  if (typeof value === "bigint") {
    return value.toString();
  }
  if (value === "infinity") {
    return "infinity";
  }
  if (typeof (value as Temporal.Instant).epochNanoseconds === "bigint") {
    return timestampToWire(value as Temporal.Instant);
  }
  return (value as ParallaxDecimal).toFixedString();
}

/**
 * The per-OID parsers that normalize driver output to the neutral wire form.
 * int8 and numeric arrive as raw text by porsager default, but we register them
 * explicitly so the contract is owned here, not implicit.
 */
function wireParsers() {
  return {
    int8: rawType(RAW_TEXT_OIDS.int8, (raw) => raw.trim()),
    numeric: rawType(RAW_TEXT_OIDS.numeric, (raw) => numericFromRaw(raw).toFixedString()),
    timestamptz: rawType(RAW_TEXT_OIDS.timestamptz, (raw) => toWireScalar(timestampFromDb(raw))),
    timestamp: rawType(RAW_TEXT_OIDS.timestamp, (raw) => toWireScalar(timestampFromDb(raw))),
    bytea: rawType(RAW_TEXT_OIDS.bytea, (raw) =>
      bytesToHex(Buffer.from(raw.startsWith("\\x") ? raw.slice(2) : raw, "hex")),
    ),
    date: rawType(OID.date, (raw) => raw.trim()),
    time: rawType(OID.time, (raw) => raw.trim()),
    uuid: rawType(OID.uuid, (raw) => raw.trim()),
  };
}

/** A Testcontainers-backed Postgres provider for one suite run. */
export class PostgresProvider implements CompatibilityDatabaseProvider {
  readonly dialect = POSTGRES_DIALECT;

  private constructor(
    private readonly container: StartedPostgreSqlContainer,
    private readonly sql: Sql,
  ) {}

  /** Boot a pinned Postgres container and connect a driver bound to it. */
  static async start(): Promise<PostgresProvider> {
    const container = await new PostgreSqlContainer(POSTGRES_IMAGE).start();
    const sql = postgres(container.getConnectionUri(), {
      // biome-ignore lint/suspicious/noExplicitAny: porsager's custom-type map is loosely typed.
      types: wireParsers() as any,
      max: 1,
      onnotice: () => {},
    });
    return new PostgresProvider(container, sql);
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
    const colList = columns.join(", ");
    const placeholders = columns.map((_, i) => `$${i + 1}`).join(", ");
    const insert = `insert into ${table} (${colList}) values (${placeholders})`;
    for (const row of rows) {
      await this.sql.unsafe(insert, asParams(row));
    }
  }

  async query(sql: string, binds: readonly unknown[]): Promise<readonly ProviderRow[]> {
    const text = toPositionalPlaceholders(sql);
    const result = await this.sql.unsafe(text, asParams(binds));
    return [...result].map((row) => ({ ...(row as ProviderRow) }));
  }

  async exec(sql: string, binds: readonly unknown[]): Promise<number> {
    const text = toPositionalPlaceholders(sql);
    const result = await this.sql.unsafe(text, asParams(binds));
    return result.count;
  }

  async close(): Promise<void> {
    await this.sql.end({ timeout: 5 });
    await this.container.stop();
  }
}
