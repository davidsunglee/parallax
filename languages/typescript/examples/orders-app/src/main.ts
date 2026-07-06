/**
 * Sample app (Phase 9 smoke feedback): import the generated `#parallax` barrel,
 * build a typed handle, and exercise a typed `find`.
 *
 * Run `parallax generate` first (it materializes `.parallax/generated/index.ts`
 * behind the `#parallax` alias), then run this. The `find` predicate is the
 * generated entity symbol (`Order.id.eq(...)`), which serializes to the SAME
 * canonical operation the conformance adapter compiles (design Q1 Option B), so
 * the developer surface and the graded runtime never diverge.
 *
 * `database` is any `ParallaxDatabase` — an application supplies its own pool; a
 * trivial in-memory stub is used here so the example runs with no container.
 */
import { postgresDialect } from "@parallax/dialect";
import { Order, parallax, type ParallaxDatabase, type ParallaxRow } from "#parallax";

/** A trivial in-memory `ParallaxDatabase` for the smoke example (no real driver). */
function stubDatabase(rows: readonly ParallaxRow[]): ParallaxDatabase {
  return {
    async execute(sql: string, binds: readonly unknown[]): Promise<readonly ParallaxRow[]> {
      // A real adapter runs `sql` (with `?`→`$n` translation) against Postgres;
      // the stub just echoes the fixture rows so the typed surface is exercised.
      void sql;
      void binds;
      return rows;
    },
    async executeWrite(sql: string, binds: readonly unknown[]): Promise<number> {
      void sql;
      void binds;
      return 0;
    },
  };
}

async function main(): Promise<void> {
  const px = parallax({
    database: stubDatabase([
      { id: 42n, name: "Grace", sku: null, qty: 3, price: "19.99", active: true },
    ]),
    // The m-dialect dialect is injected beside the database (a MariaDB runtime swaps
    // `mariadbDialect` here with no other change); `postgresDialect` is the shipped
    // adapter's matching strategy.
    dialect: postgresDialect,
  });

  // Typed finder + generated entity symbol → canonical operation → compiled SQL.
  // A predicate literal is the JSON wire form the operation carries (`42`), which
  // the compiler normalizes against the attribute's m-core `int64` type; the resolved
  // row's `id` materializes back to `bigint` (spec §3.2.1).
  const grace = await px.orders.find(Order.id.eq(42)).single();
  process.stdout.write(`found order: ${JSON.stringify(grace, (_k, v) => (typeof v === "bigint" ? v.toString() : v))}\n`);

  const active = await px.orders
    .find(Order.active.eq(true), { orderBy: [Order.id.desc()], limit: 10 })
    .toArray();
  process.stdout.write(`active orders: ${active.length}\n`);
}

void main();
