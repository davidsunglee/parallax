/**
 * Pure (Docker-free) unit tests for the `@parallax/db-mariadb` adapter's bind seam
 * and `openSession` cleanup discipline.
 *
 *  - `toMariaBind` contract (Finding 1): a TYPED `Temporal.Instant` is bound as a
 *    naive-UTC `DATETIME(6)` string, but a plain `string` — even one that LOOKS like
 *    a timestamp — passes through VERBATIM. The adapter must not heuristically
 *    coerce text; the untyped-corpus ISO-string coercion lives one layer up in the
 *    conformance provider (`mariadb-provider.ts` `toManagedBind`). The `"infinity"`
 *    sentinel still maps to the max-sentinel `DATETIME`.
 *  - `openSession` cleanup (Finding 2): a setup failure after `getConnection()`
 *    RESETS the lowered lock-wait budget (best-effort), RELEASES the pooled
 *    connection, and rethrows a CLASSIFIED {@link ParallaxTransientError} — driven
 *    by a lightweight fake pool connection (no mysql2 / Docker).
 */
import { Temporal } from "@parallax/core";
import { ParallaxTransientError } from "@parallax/db";
import { mariadbDialect } from "@parallax/dialect";
import { describe, expect, it } from "vitest";
import { MariaDbDatabase, toMariaBind } from "../src/adapter.js";

describe("toMariaBind — the shipping bind seam does not coerce text", () => {
  it("passes a timestamp-looking STRING through verbatim (genuine text survives)", () => {
    expect(toMariaBind("2024-03-01T12:00:00Z")).toBe("2024-03-01T12:00:00Z");
    expect(toMariaBind("2024-03-01T12:00:00+00:00")).toBe("2024-03-01T12:00:00+00:00");
    // A non-instant string that merely contains a `T` is untouched too.
    expect(toMariaBind("Trent")).toBe("Trent");
    // A bare date / business string is untouched.
    expect(toMariaBind("2024-03-01")).toBe("2024-03-01");
  });

  it("binds a TYPED Temporal.Instant as a naive-UTC DATETIME(6) string", () => {
    expect(toMariaBind(Temporal.Instant.from("2024-03-01T12:00:00Z"))).toBe(
      "2024-03-01 12:00:00.000000",
    );
    expect(toMariaBind(Temporal.Instant.from("2024-03-01T12:00:00.123456Z"))).toBe(
      "2024-03-01 12:00:00.123456",
    );
  });

  it("still maps the `infinity` sentinel to the max-sentinel DATETIME", () => {
    expect(toMariaBind("infinity")).toBe(mariadbDialect.infinityBind());
  });
});

/**
 * A minimal fake `mysql2` pool connection recording the queries it saw and whether
 * it was released, with per-call throwers to force a setup failure.
 */
interface FakeConnection {
  query: (sql: string) => Promise<unknown>;
  beginTransaction: () => Promise<void>;
  release: () => void;
}

/** Build a `MariaDbDatabase` over a fake pool (bypassing the private constructor). */
function databaseOverPool(connection: FakeConnection): MariaDbDatabase {
  const pool = { getConnection: async () => connection };
  const Ctor = MariaDbDatabase as unknown as new (db: unknown) => MariaDbDatabase;
  return new Ctor(pool);
}

/** A `mysql2`-style error carrying a native MariaDB errno. */
function errnoError(message: string, errno: number): Error {
  return Object.assign(new Error(message), { errno });
}

describe("openSession — a failed setup resets, releases, and classifies", () => {
  it("resets the lowered budget before releasing when beginTransaction fails", async () => {
    const calls: string[] = [];
    let released = false;
    const connection: FakeConnection = {
      query: async (sql) => {
        calls.push(sql);
        return undefined;
      },
      beginTransaction: async () => {
        throw errnoError("Lock wait timeout exceeded", 1205);
      },
      release: () => {
        released = true;
      },
    };
    const db = databaseOverPool(connection);

    let raised: unknown;
    try {
      await db.openSession();
    } catch (error) {
      raised = error;
    }

    // (a) the lowered budget was reset to default BEFORE release (mirrors close()).
    expect(calls).toEqual([
      "set innodb_lock_wait_timeout = 1",
      "set innodb_lock_wait_timeout = default",
    ]);
    // the connection was released (never leaked).
    expect(released).toBe(true);
    // (b) the propagated error is a CLASSIFIED transient, not the raw driver error.
    expect(raised).toBeInstanceOf(ParallaxTransientError);
    expect((raised as ParallaxTransientError).kind).toBe("lockWaitTimeout");
  });

  it("swallows a failing reset (broken connection) and still releases + classifies", async () => {
    const calls: string[] = [];
    let released = false;
    const connection: FakeConnection = {
      // Both the lowering SET and the best-effort reset throw (connection broken).
      query: async (sql) => {
        calls.push(sql);
        throw errnoError("Deadlock found when trying to get lock", 1213);
      },
      beginTransaction: async () => {
        throw new Error("unreachable — the SET already failed");
      },
      release: () => {
        released = true;
      },
    };
    const db = databaseOverPool(connection);

    let raised: unknown;
    try {
      await db.openSession();
    } catch (error) {
      raised = error;
    }

    // the reset was ATTEMPTED (harmless swallowed no-op) then the connection released.
    expect(calls).toEqual([
      "set innodb_lock_wait_timeout = 1",
      "set innodb_lock_wait_timeout = default",
    ]);
    expect(released).toBe(true);
    expect(raised).toBeInstanceOf(ParallaxTransientError);
    expect((raised as ParallaxTransientError).kind).toBe("deadlock");
  });
});
