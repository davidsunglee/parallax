/**
 * Runtime `EntityFinder` behavior (developer-surface remediation).
 *
 * Two spec-fidelity guarantees the conformance slice does not exercise, because
 * conformance reads through the case-driven `MetamodelSchema`/`readProjection`
 * path, not the application `RuntimeSchema` + `EntityFinder` path:
 *
 *  1. No-arg `find()` is shorthand for `find(Entity.all())` (spec §2.3): a
 *     no-predicate call compiles to an `all` read (`select … from <table>`, no
 *     `where`), not a runtime throw.
 *  2. A `bytes` managed-object attribute is projected VERBATIM (never the
 *     `encode(…) <col>_hex` conformance lowering) and materialized as a fresh
 *     `Uint8Array` at the adapter boundary (spec §3.2.1), whether the adapter
 *     returns a Node `Buffer` or a hex string.
 *
 * The runtime is built through the real `createParallax` factory with a stub
 * `ParallaxDatabase` that records the compiled SQL + binds and returns canned
 * rows, so the assertions ride the same compile path the generated barrel uses.
 */
import { loadCase } from "@parallax/conformance";
import { ParallaxDecimal, Temporal } from "@parallax/core";
import { postgresDialect } from "@parallax/dialect";
import { describe, expect, it } from "vitest";
import { createParallax, type ParallaxDatabase, type ParallaxRow } from "../src/index.js";

/** A recorded query: the compiled SQL and its ordered binds. */
interface RecordedQuery {
  readonly sql: string;
  readonly binds: readonly unknown[];
}

/**
 * A stub database port that records every compiled read and returns canned rows.
 * `rows` is what the next `execute` resolves to; `queries` accumulates every call.
 */
class StubDatabase implements ParallaxDatabase {
  readonly queries: RecordedQuery[] = [];

  constructor(private rows: readonly ParallaxRow[] = []) {}

  setRows(rows: readonly ParallaxRow[]): void {
    this.rows = rows;
  }

  execute(sql: string, binds: readonly unknown[]): Promise<readonly ParallaxRow[]> {
    this.queries.push({ sql, binds });
    return Promise.resolve(this.rows);
  }
}

/** The scalars descriptor (`ScalarThing`, the only in-corpus `bytes`-bearing model). */
const SCALARS = loadCase("core/compatibility/cases/0003-scalar-types-roundtrip.yaml").descriptor;

describe("EntityFinder no-arg find() shorthand (spec §2.3)", () => {
  it("compiles find() with no predicate to an `all` read (no where clause)", async () => {
    const db = new StubDatabase([]);
    const px = createParallax({ descriptor: SCALARS, database: db, dialect: postgresDialect });

    await px.entity("ScalarThing").find().toArray();

    expect(db.queries).toHaveLength(1);
    const { sql } = db.queries[0] as RecordedQuery;
    expect(sql).toContain("from scalar_thing t0");
    expect(sql).not.toContain(" where ");
  });
});

describe("EntityFinder bytes materialization (spec §3.2.1)", () => {
  it("projects bytes verbatim (no encode/_hex) and materializes a Node Buffer to a fresh Uint8Array", async () => {
    const payload = Buffer.from([1, 2, 3, 4]);
    const db = new StubDatabase([{ id: "1", payload }]);
    const px = createParallax({ descriptor: SCALARS, database: db, dialect: postgresDialect });

    const rows = await px.entity("ScalarThing").find().toArray();

    // (a) the projection is verbatim: no `encode(` and no `payload_hex` alias.
    const { sql } = db.queries[0] as RecordedQuery;
    expect(sql).toContain("t0.payload");
    expect(sql).not.toContain("encode(");
    expect(sql).not.toContain("payload_hex");

    // (b) the row's payload is a FRESH Uint8Array with equal contents, not the
    // input Buffer instance.
    const materialized = (rows[0] as ParallaxRow).payload;
    expect(materialized).toBeInstanceOf(Uint8Array);
    expect(Array.from(materialized as Uint8Array)).toEqual([1, 2, 3, 4]);
    expect(materialized).not.toBe(payload);
  });

  it("materializes a plain hex string to the same Uint8Array", async () => {
    const db = new StubDatabase([{ id: "1", payload: "01020304" }]);
    const px = createParallax({ descriptor: SCALARS, database: db, dialect: postgresDialect });

    const rows = await px.entity("ScalarThing").find().toArray();

    const materialized = (rows[0] as ParallaxRow).payload;
    expect(materialized).toBeInstanceOf(Uint8Array);
    expect(Array.from(materialized as Uint8Array)).toEqual([1, 2, 3, 4]);
  });

  it("materializes a \\x-prefixed hex string to the same Uint8Array", async () => {
    const db = new StubDatabase([{ id: "1", payload: "\\x01020304" }]);
    const px = createParallax({ descriptor: SCALARS, database: db, dialect: postgresDialect });

    const rows = await px.entity("ScalarThing").find().toArray();

    const materialized = (rows[0] as ParallaxRow).payload;
    expect(materialized).toBeInstanceOf(Uint8Array);
    expect(Array.from(materialized as Uint8Array)).toEqual([1, 2, 3, 4]);
  });

  it("leaves a nullable bytes value null", async () => {
    const db = new StubDatabase([{ id: "1", payload: null }]);
    const px = createParallax({ descriptor: SCALARS, database: db, dialect: postgresDialect });

    const rows = await px.entity("ScalarThing").find().toArray();

    expect((rows[0] as ParallaxRow).payload).toBeNull();
  });
});

/**
 * A synthetic entity that (a) exercises EVERY M0 scalar family and (b) renames
 * each physical column to a distinct DSL name, so the materializer's column → DSL
 * mapping and per-type managed coercion are both asserted in one place. Every
 * attribute's `column` differs from its `name` (snake_case → camelCase), so a
 * materialized object that carried the physical key would be observably wrong.
 */
const EVERY_SCALAR = {
  entity: {
    name: "EveryScalar",
    table: "every_scalar",
    mutability: "read-only",
    temporal: "non-temporal",
    attributes: [
      { name: "id", type: "int64", column: "id", primaryKey: true, pkGenerator: "none" },
      { name: "smallCount", type: "int32", column: "small_count" },
      { name: "ratioF32", type: "float32", column: "ratio_f32" },
      { name: "ratioF64", type: "float64", column: "ratio_f64" },
      { name: "amount", type: "decimal(18,2)", column: "amount_dec" },
      { name: "label", type: "string", column: "label_text" },
      { name: "externalId", type: "uuid", column: "external_id" },
      { name: "payload", type: "bytes", column: "payload_bytes" },
      { name: "bookedOn", type: "date", column: "booked_on" },
      { name: "localTime", type: "time", column: "local_time" },
      { name: "recordedAt", type: "timestamp", column: "recorded_at" },
      { name: "active", type: "boolean", column: "is_active" },
      { name: "meta", type: "json", column: "meta_json" },
    ],
    indices: [{ name: "every_scalar_pk", attributes: ["id"], unique: true }],
  },
};

describe("EntityFinder managed-object materialization (spec §3.2.1)", () => {
  it("maps physical column → DSL name and coerces a RAW (thin BYO adapter) row per type", async () => {
    // Every value is the raw driver representation a thin BYO adapter would hand
    // back: bigint/decimal/timestamp/date/time as strings, bytes as hex, booleans
    // and json as their Postgres text renderings — all keyed by PHYSICAL column.
    const db = new StubDatabase([
      {
        id: "9007199254740993", // beyond 2^53 — proves bigint, not a lossy number
        small_count: "7",
        ratio_f32: "1.5",
        ratio_f64: "2.25",
        amount_dec: "19.99",
        label_text: "hello",
        external_id: "123e4567-e89b-12d3-a456-426614174000",
        payload_bytes: "\\x01020304",
        booked_on: "2024-03-01",
        local_time: "12:34:56",
        recorded_at: "2024-03-01 12:00:00.123456+00",
        is_active: "t",
        meta_json: '{"k":1}',
      },
    ]);
    const px = createParallax({ descriptor: EVERY_SCALAR, database: db, dialect: postgresDialect });

    const rows = await px.entity("EveryScalar").find().toArray();
    const row = rows[0] as ParallaxRow;

    // (1) keyed by DSL name — the physical columns are gone (the rename bug).
    expect(Object.keys(row).sort()).toEqual(
      [
        "active",
        "amount",
        "bookedOn",
        "externalId",
        "id",
        "label",
        "localTime",
        "meta",
        "payload",
        "ratioF32",
        "ratioF64",
        "recordedAt",
        "smallCount",
      ].sort(),
    );
    expect(row.local_time).toBeUndefined();
    expect(row.external_id).toBeUndefined();

    // (2) per-type managed carriers, by shape (instanceof / typeof) AND value.
    expect(typeof row.id).toBe("bigint");
    expect(row.id).toBe(9007199254740993n);

    expect(typeof row.smallCount).toBe("number");
    expect(row.smallCount).toBe(7);
    expect(row.ratioF32).toBe(1.5);
    expect(row.ratioF64).toBe(2.25);

    expect(row.amount).toBeInstanceOf(ParallaxDecimal);
    expect((row.amount as ParallaxDecimal).toFixedString(2)).toBe("19.99");

    expect(typeof row.label).toBe("string");
    expect(row.label).toBe("hello");
    expect(row.externalId).toBe("123e4567-e89b-12d3-a456-426614174000");

    expect(row.payload).toBeInstanceOf(Uint8Array);
    expect(Array.from(row.payload as Uint8Array)).toEqual([1, 2, 3, 4]);

    expect(row.bookedOn).toBeInstanceOf(Temporal.PlainDate);
    expect((row.bookedOn as Temporal.PlainDate).toString()).toBe("2024-03-01");

    expect(row.localTime).toBeInstanceOf(Temporal.PlainTime);
    expect((row.localTime as Temporal.PlainTime).toString()).toBe("12:34:56");

    expect(row.recordedAt).toBeInstanceOf(Temporal.Instant);
    expect((row.recordedAt as Temporal.Instant).toString({ smallestUnit: "microsecond" })).toBe(
      "2024-03-01T12:00:00.123456Z",
    );

    expect(typeof row.active).toBe("boolean");
    expect(row.active).toBe(true);

    expect(row.meta).toEqual({ k: 1 });
  });

  it("passes MANAGED values through idempotently (managed adapter path)", async () => {
    // The same row already in managed form — as `@parallax/db-postgres` returns
    // it. Coercion must be idempotent: managed scalars pass through unchanged
    // (bytes are copied, never aliased).
    const payload = Uint8Array.from([1, 2, 3, 4]);
    const db = new StubDatabase([
      {
        id: 9007199254740993n,
        small_count: 7,
        ratio_f32: 1.5,
        ratio_f64: 2.25,
        amount_dec: ParallaxDecimal.from("19.99"),
        label_text: "hello",
        external_id: "123e4567-e89b-12d3-a456-426614174000",
        payload_bytes: payload,
        booked_on: Temporal.PlainDate.from("2024-03-01"),
        local_time: Temporal.PlainTime.from("12:34:56"),
        recorded_at: Temporal.Instant.from("2024-03-01T12:00:00.123456Z"),
        is_active: true,
        meta_json: { k: 1 },
      },
    ]);
    const px = createParallax({ descriptor: EVERY_SCALAR, database: db, dialect: postgresDialect });

    const row = (await px.entity("EveryScalar").find().toArray())[0] as ParallaxRow;

    expect(row.id).toBe(9007199254740993n);
    expect(row.amount).toBeInstanceOf(ParallaxDecimal);
    expect((row.amount as ParallaxDecimal).toFixedString(2)).toBe("19.99");
    expect(row.bookedOn).toBeInstanceOf(Temporal.PlainDate);
    expect(row.localTime).toBeInstanceOf(Temporal.PlainTime);
    expect((row.localTime as Temporal.PlainTime).toString()).toBe("12:34:56");
    expect(row.recordedAt).toBeInstanceOf(Temporal.Instant);
    // bytes: a fresh Uint8Array, equal contents, never the adapter's instance.
    expect(row.payload).toBeInstanceOf(Uint8Array);
    expect(Array.from(row.payload as Uint8Array)).toEqual([1, 2, 3, 4]);
    expect(row.payload).not.toBe(payload);
    expect(row.active).toBe(true);
    expect(row.meta).toEqual({ k: 1 });
  });

  it("leaves nullable columns null across every type", async () => {
    const db = new StubDatabase([
      {
        id: "1",
        small_count: null,
        ratio_f32: null,
        ratio_f64: null,
        amount_dec: null,
        label_text: null,
        external_id: null,
        payload_bytes: null,
        booked_on: null,
        local_time: null,
        recorded_at: null,
        is_active: null,
        meta_json: null,
      },
    ]);
    const px = createParallax({ descriptor: EVERY_SCALAR, database: db, dialect: postgresDialect });

    const row = (await px.entity("EveryScalar").find().toArray())[0] as ParallaxRow;

    expect(row.id).toBe(1n);
    for (const key of [
      "smallCount",
      "ratioF32",
      "ratioF64",
      "amount",
      "label",
      "externalId",
      "payload",
      "bookedOn",
      "localTime",
      "recordedAt",
      "active",
      "meta",
    ]) {
      expect(row[key]).toBeNull();
    }
  });

  it("keys identity on the PK's DSL name so same-PK rows collapse to one object", async () => {
    // Two rows with the SAME logical id but distinct payloads. Identity must key
    // on the PK's DSL name (`id`) AFTER the rename; the first-seen instance wins.
    const db = new StubDatabase([
      {
        id: "42",
        small_count: "1",
        ratio_f32: null,
        ratio_f64: null,
        amount_dec: null,
        label_text: "first",
        external_id: null,
        payload_bytes: null,
        booked_on: null,
        local_time: null,
        recorded_at: null,
        is_active: null,
        meta_json: null,
      },
      {
        id: "42",
        small_count: "2",
        ratio_f32: null,
        ratio_f64: null,
        amount_dec: null,
        label_text: "second",
        external_id: null,
        payload_bytes: null,
        booked_on: null,
        local_time: null,
        recorded_at: null,
        is_active: null,
        meta_json: null,
      },
    ]);
    const px = createParallax({ descriptor: EVERY_SCALAR, database: db, dialect: postgresDialect });

    const rows = await px.entity("EveryScalar").find().toArray();

    expect(rows).toHaveLength(2);
    // Same PK ⇒ same object instance (identity map hit on the DSL-named `id`).
    expect(rows[0]).toBe(rows[1]);
    expect((rows[0] as ParallaxRow).label).toBe("first");
  });
});
