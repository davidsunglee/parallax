/**
 * Runtime `EntityFinder` behavior (developer-surface remediation).
 *
 * Two spec-fidelity guarantees the conformance slice does not exercise, because
 * conformance reads through the case-driven `MetamodelSchema`/`readProjection`
 * path, not the application `RuntimeSchema` + `EntityFinder` path:
 *
 *  1. No-arg `find()` is shorthand for `find(Entity.all())` (spec §1.3): a
 *     no-predicate call compiles to an `all` read (`select … from <table>`, no
 *     `where`), not a runtime throw.
 *  2. A `bytes` managed-object attribute is projected VERBATIM (never the
 *     `encode(…) <col>_hex` conformance lowering) and materialized as a fresh
 *     `Uint8Array` at the adapter boundary (spec §2.2.1), whether the adapter
 *     returns a Node `Buffer` or a hex string.
 *
 * The runtime is built through the real `createParallax` factory with a stub
 * `ParallaxDatabase` that records the compiled SQL + binds and returns canned
 * rows, so the assertions ride the same compile path the generated barrel uses.
 */
import { loadCase } from "@parallax/conformance";
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

describe("EntityFinder no-arg find() shorthand (spec §1.3)", () => {
  it("compiles find() with no predicate to an `all` read (no where clause)", async () => {
    const db = new StubDatabase([]);
    const px = createParallax({ descriptor: SCALARS, database: db });

    await px.entity("ScalarThing").find().toArray();

    expect(db.queries).toHaveLength(1);
    const { sql } = db.queries[0] as RecordedQuery;
    expect(sql).toContain("from scalar_thing t0");
    expect(sql).not.toContain(" where ");
  });
});

describe("EntityFinder bytes materialization (spec §2.2.1)", () => {
  it("projects bytes verbatim (no encode/_hex) and materializes a Node Buffer to a fresh Uint8Array", async () => {
    const payload = Buffer.from([1, 2, 3, 4]);
    const db = new StubDatabase([{ id: "1", payload }]);
    const px = createParallax({ descriptor: SCALARS, database: db });

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
    const px = createParallax({ descriptor: SCALARS, database: db });

    const rows = await px.entity("ScalarThing").find().toArray();

    const materialized = (rows[0] as ParallaxRow).payload;
    expect(materialized).toBeInstanceOf(Uint8Array);
    expect(Array.from(materialized as Uint8Array)).toEqual([1, 2, 3, 4]);
  });

  it("materializes a \\x-prefixed hex string to the same Uint8Array", async () => {
    const db = new StubDatabase([{ id: "1", payload: "\\x01020304" }]);
    const px = createParallax({ descriptor: SCALARS, database: db });

    const rows = await px.entity("ScalarThing").find().toArray();

    const materialized = (rows[0] as ParallaxRow).payload;
    expect(materialized).toBeInstanceOf(Uint8Array);
    expect(Array.from(materialized as Uint8Array)).toEqual([1, 2, 3, 4]);
  });

  it("leaves a nullable bytes value null", async () => {
    const db = new StubDatabase([{ id: "1", payload: null }]);
    const px = createParallax({ descriptor: SCALARS, database: db });

    const rows = await px.entity("ScalarThing").find().toArray();

    expect((rows[0] as ParallaxRow).payload).toBeNull();
  });
});
