/**
 * `@parallax/db-postgres` adapter integration test (Phase 10a).
 *
 * Proves the shipped adapter's contract end-to-end against a real `postgres:17`:
 * connect by **connection string**, run a compiled `?`-placeholder statement
 * through `execute`, and assert every returned scalar is a **managed** value
 * (`bigint` / `ParallaxDecimal` / `Temporal.Instant` / `Temporal.PlainDate` /
 * `Temporal.PlainTime` / `Uint8Array` / string), NOT a porsager driver default
 * (a ms-precision `Date`, a binary-float `numeric`, a raw `Buffer`). This is the
 * §3.2.1 "normalize at the adapter boundary" contract the M11 decomposition
 * mandates — the adapter returns managed types and no wire/grading logic.
 *
 * Testcontainers lives in the composition root, so this integration test lives
 * here (not in `@parallax/db-postgres`, which deliberately has NO Testcontainers
 * and NO `@parallax/typescript` dependency). It boots the container directly and
 * hands the URI to `PostgresDatabase.fromConnectionString`, exercising the exact
 * path a real application uses. Skipped (reported, never silently passed) when
 * Docker is unavailable.
 */
import { execFileSync } from "node:child_process";
import { ParallaxDecimal, Temporal } from "@parallax/core";
import { PostgresDatabase } from "@parallax/db-postgres";
import { postgresDialect } from "@parallax/dialect";
import { PostgreSqlContainer, type StartedPostgreSqlContainer } from "@testcontainers/postgresql";
import { afterAll, beforeAll, expect, describe as group, it } from "vitest";

/** True when a Docker daemon is reachable (gates the Testcontainers lane). */
function dockerAvailable(): boolean {
  try {
    execFileSync("docker", ["info"], { stdio: "ignore", timeout: 10_000 });
    return true;
  } catch {
    return false;
  }
}

const HAS_DOCKER = dockerAvailable();
const BOOT_TIMEOUT = 600_000;

group.skipIf(!HAS_DOCKER)("@parallax/db-postgres adapter (Testcontainers postgres:17)", () => {
  let container: StartedPostgreSqlContainer;
  let db: PostgresDatabase;

  beforeAll(async () => {
    container = await new PostgreSqlContainer("postgres:17").start();
    db = PostgresDatabase.fromConnectionString(container.getConnectionUri());
    // A table covering every managed-carrier column family. The `payload` is
    // `\x01020304` written through the adapter's own bytea bind serializer.
    await db.execute(
      "create table t (" +
        "big bigint, num numeric(10,2), ts timestamptz, d date, tm time, " +
        "payload bytea, ext_id uuid, note text, flag boolean)",
      [],
    );
    await db.execute(
      "insert into t (big, num, ts, d, tm, payload, ext_id, note, flag) " +
        "values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
      [
        "9007199254740993", // beyond 2^53 — proves bigint, not a lossy number
        "19.99",
        "2024-03-01T12:00:00.123456+00:00",
        "2024-03-01",
        "12:34:56",
        Buffer.from([1, 2, 3, 4]),
        "123e4567-e89b-12d3-a456-426614174000",
        "hello",
        true,
      ],
    );
  }, BOOT_TIMEOUT);

  afterAll(async () => {
    await db?.close();
    await container?.stop();
  });

  it("returns rows keyed by physical column as managed scalars", async () => {
    const rows = await db.execute("select * from t where big = ?", ["9007199254740993"]);
    expect(rows).toHaveLength(1);
    const row = rows[0] as Record<string, unknown>;

    // int8 -> bigint (exact beyond 2^53, never a lossy JS number)
    expect(typeof row.big).toBe("bigint");
    expect(row.big).toBe(9007199254740993n);

    // numeric -> ParallaxDecimal (exact decimal, never a binary float)
    expect(row.num).toBeInstanceOf(ParallaxDecimal);
    expect((row.num as ParallaxDecimal).toFixedString()).toBe("19.99");

    // timestamptz -> Temporal.Instant at microsecond precision (never a ms Date)
    expect(row.ts).toBeInstanceOf(Temporal.Instant);
    expect((row.ts as Temporal.Instant).toString({ smallestUnit: "microsecond" })).toBe(
      "2024-03-01T12:00:00.123456Z",
    );

    // date -> Temporal.PlainDate, time -> Temporal.PlainTime
    expect(row.d).toBeInstanceOf(Temporal.PlainDate);
    expect((row.d as Temporal.PlainDate).toString()).toBe("2024-03-01");
    expect(row.tm).toBeInstanceOf(Temporal.PlainTime);
    expect((row.tm as Temporal.PlainTime).toString()).toBe("12:34:56");

    // bytea -> Uint8Array (a fresh byte array, not a driver Buffer proxy)
    expect(row.payload).toBeInstanceOf(Uint8Array);
    expect(Array.from(row.payload as Uint8Array)).toEqual([1, 2, 3, 4]);

    // uuid / text -> string, boolean -> boolean
    expect(row.ext_id).toBe("123e4567-e89b-12d3-a456-426614174000");
    expect(row.note).toBe("hello");
    expect(row.flag).toBe(true);
  });

  it("runs a callback inside a transaction over a bound connection", async () => {
    const seen = await db.transaction(async (tx) => {
      const rows = await tx.execute("select big from t where big = ?", ["9007199254740993"]);
      return (rows[0] as Record<string, unknown>).big;
    });
    expect(seen).toBe(9007199254740993n);
  });

  it("round-trips a `bytes` value written through the dialect bind seam", async () => {
    // The runtime write path binds a `bytes` value via `postgresDialect.bindValue`,
    // then hands it to `executeWrite`. The `Uint8Array` must reach porsager as its
    // raw carrier (inferred `bytea`), NOT `toWire`'s hex TEXT — a hex string would be
    // coerced through the `bytea` ESCAPE format and store the ASCII characters, so
    // the round-trip guards the finding-#1 fix end-to-end against a real Postgres.
    await db.execute("drop table if exists bytes_rt", []);
    await db.execute("create table bytes_rt (id int primary key, payload bytea)", []);
    const payload = new Uint8Array([0xde, 0xad, 0xbe, 0xef]);
    await db.executeWrite("insert into bytes_rt (id, payload) values (?, ?)", [
      1,
      postgresDialect.bindValue("bytes", payload),
    ]);

    const [row] = await db.execute("select payload from bytes_rt where id = ?", [1]);
    expect((row as { payload: unknown }).payload).toBeInstanceOf(Uint8Array);
    expect(Array.from((row as { payload: Uint8Array }).payload)).toEqual([0xde, 0xad, 0xbe, 0xef]);
  });
});
