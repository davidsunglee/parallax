/**
 * Shared real-database adapter smoke suite.
 *
 * This proves the shipped concrete adapters directly, before the m-case-format provider
 * layer gets involved: connection-string construction, managed scalar reads,
 * transaction callback behavior, bytes writes, affected-row semantics, and
 * feasible transient classification.
 */
import { execFileSync } from "node:child_process";
import { ParallaxDecimal, Temporal } from "@parallax/core";
import type { ParallaxDatabase } from "@parallax/db";
import { ParallaxTransientError } from "@parallax/db";
import { MariaDbDatabase } from "@parallax/db-mariadb";
import { PostgresDatabase } from "@parallax/db-postgres";
import { type Dialect, mariadbDialect, postgresDialect, rawJson } from "@parallax/dialect";
import { MySqlContainer } from "@testcontainers/mysql";
import { PostgreSqlContainer } from "@testcontainers/postgresql";
import { afterAll, beforeAll, expect, describe as group, it } from "vitest";

const BOOT_TIMEOUT = 600_000;
const SAMPLE_INSTANT = Temporal.Instant.from("2024-03-01T12:00:00.123456Z");
const SAMPLE_UUID = "123e4567-e89b-12d3-a456-426614174000";

interface AdapterHandle {
  readonly db: ParallaxDatabase;
  readonly peer: ParallaxDatabase;
  close(): Promise<void>;
}

interface AdapterSmokeSpec {
  readonly name: string;
  readonly dialect: Dialect;
  readonly scalarDdl: string;
  start(): Promise<AdapterHandle>;
  proveTransient(db: ParallaxDatabase, peer: ParallaxDatabase): Promise<void>;
}

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

const SPECS: readonly AdapterSmokeSpec[] = [
  {
    name: "@parallax/db-postgres adapter (Testcontainers postgres:17)",
    dialect: postgresDialect,
    scalarDdl:
      "create table adapter_scalar (" +
      "big bigint, num numeric(10,2), ts timestamptz, d date, tm time, " +
      "payload bytea, ext_id uuid, note text)",
    start: startPostgres,
    proveTransient: provePostgresLockTimeout,
  },
  {
    name: "@parallax/db-mariadb adapter (Testcontainers mariadb:11.4)",
    dialect: mariadbDialect,
    scalarDdl:
      "create table adapter_scalar (" +
      "big bigint, num decimal(10,2), ts datetime(6), d date, tm time, " +
      "payload longblob, ext_id char(36), note text)",
    start: startMariaDb,
    proveTransient: proveMariaDbLockTimeout,
  },
];

for (const spec of SPECS) {
  group.skipIf(!HAS_DOCKER)(spec.name, () => {
    let handle: AdapterHandle | undefined;

    beforeAll(async () => {
      handle = await spec.start();
    }, BOOT_TIMEOUT);

    afterAll(async () => {
      await handle?.close();
    });

    it("constructs from a connection string and returns managed scalar rows", async () => {
      const db = mustHandle(handle).db;
      await db.execute("drop table if exists adapter_scalar", []);
      await db.execute(spec.scalarDdl, []);
      await db.executeWrite(
        "insert into adapter_scalar (big, num, ts, d, tm, payload, ext_id, note) " +
          "values (?, ?, ?, ?, ?, ?, ?, ?)",
        [
          "9007199254740993",
          "19.99",
          spec.dialect.bindValue("timestamp", SAMPLE_INSTANT),
          "2024-03-01",
          "12:34:56",
          spec.dialect.bindValue("bytes", new Uint8Array([1, 2, 3, 4])),
          SAMPLE_UUID,
          "hello",
        ],
      );

      const [row] = await db.execute("select * from adapter_scalar where big = ?", [
        "9007199254740993",
      ]);
      expect(row).toBeDefined();
      const record = row as Record<string, unknown>;
      expect(record.big).toBe(9007199254740993n);
      expect(record.num).toBeInstanceOf(ParallaxDecimal);
      expect((record.num as ParallaxDecimal).toFixedString()).toBe("19.99");
      expect(record.ts).toBeInstanceOf(Temporal.Instant);
      expect((record.ts as Temporal.Instant).toString({ smallestUnit: "microsecond" })).toBe(
        "2024-03-01T12:00:00.123456Z",
      );
      expect(record.d).toBeInstanceOf(Temporal.PlainDate);
      expect((record.d as Temporal.PlainDate).toString()).toBe("2024-03-01");
      expect(record.tm).toBeInstanceOf(Temporal.PlainTime);
      expect((record.tm as Temporal.PlainTime).toString()).toBe("12:34:56");
      expect(record.payload).toBeInstanceOf(Uint8Array);
      expect(Array.from(record.payload as Uint8Array)).toEqual([1, 2, 3, 4]);
      expect(record.ext_id).toBe(SAMPLE_UUID);
      expect(record.note).toBe("hello");
    });

    it("runs a callback inside a transaction and commits on success", async () => {
      const db = mustHandle(handle).db;
      expect(db.transaction).toBeDefined();
      await db.execute("drop table if exists adapter_tx", []);
      await db.execute("create table adapter_tx (id int primary key, note text)", []);

      const value = await db.transaction?.(async (tx) => {
        await tx.executeWrite("insert into adapter_tx (id, note) values (?, ?)", [1, "inside"]);
        const [row] = await tx.execute("select note from adapter_tx where id = ?", [1]);
        return (row as { note: string }).note;
      });

      expect(value).toBe("inside");
      const [row] = await db.execute("select note from adapter_tx where id = ?", [1]);
      expect((row as { note: string }).note).toBe("inside");
    });

    it("round-trips a bytes value written through the dialect bind seam", async () => {
      const db = mustHandle(handle).db;
      await db.execute("drop table if exists adapter_bytes", []);
      await db.execute(
        `create table adapter_bytes (id int primary key, payload ${bytesType(spec)})`,
        [],
      );
      const payload = new Uint8Array([0xde, 0xad, 0xbe, 0xef]);
      await db.executeWrite("insert into adapter_bytes (id, payload) values (?, ?)", [
        1,
        spec.dialect.bindValue("bytes", payload),
      ]);

      const [row] = await db.execute("select payload from adapter_bytes where id = ?", [1]);
      expect((row as { payload: unknown }).payload).toBeInstanceOf(Uint8Array);
      expect(Array.from((row as { payload: Uint8Array }).payload)).toEqual([
        0xde, 0xad, 0xbe, 0xef,
      ]);
    });

    it("reports affected rows for matched and unmatched DML", async () => {
      const db = mustHandle(handle).db;
      await db.execute("drop table if exists adapter_affected", []);
      await db.execute("create table adapter_affected (id int primary key, note text)", []);
      await db.executeWrite("insert into adapter_affected (id, note) values (?, ?)", [1, "same"]);

      await expect(
        db.executeWrite("update adapter_affected set note = ? where id = ?", ["same", 1]),
      ).resolves.toBe(1);
      await expect(
        db.executeWrite("update adapter_affected set note = ? where id = ?", ["miss", 99]),
      ).resolves.toBe(0);
    });

    it(
      "classifies a feasible transient lock timeout through the portable error surface",
      async () => {
        const { db, peer } = mustHandle(handle);
        await spec.proveTransient(db, peer);
      },
      BOOT_TIMEOUT,
    );
  });
}

/**
 * Postgres-only `json` / `jsonb` round-trip through the shipped adapter — the
 * fail-safe-by-default fix proven on a real server. A `json` value binds through the
 * SAME seam the runtime write path uses (`postgresDialect.bindValue("json", value)`,
 * which pre-serializes to canonical JSON and wraps it in the raw sentinel the adapter's
 * `serializeJson` emits verbatim), and must read back equal for every JSON shape —
 * including a STRING scalar, the regression that was bound as the raw, invalid-JSON text
 * `hello` instead of the jsonb string `"hello"`. A companion test proves the
 * DIRECT-adapter fail-safe: a bare string bound with NO wrapper still lands as valid JSON
 * via `serializeJson`'s `JSON.stringify` default (the exact missed-path the finding is
 * about). A third proves the read-side empty-array guard `'[]'` still passes through raw
 * (a jsonb ARRAY, not the jsonb string scalar `"[]"`), so the fix does not re-break the
 * value-object to-many read.
 */
group.skipIf(!HAS_DOCKER)(
  "@parallax/db-postgres json column round-trip (Testcontainers postgres:17)",
  () => {
    let handle: AdapterHandle | undefined;

    beforeAll(async () => {
      handle = await startPostgres();
    }, BOOT_TIMEOUT);

    afterAll(async () => {
      await handle?.close();
    });

    it(
      "round-trips a json attribute value written through the dialect bind seam (Finding 1)",
      async () => {
        const db = mustHandle(handle).db;
        await db.execute("drop table if exists adapter_json", []);
        await db.execute("create table adapter_json (id int primary key, doc jsonb)", []);

        // A plain `json` m-core attribute holding each JSON shape a developer may
        // write: string / number / boolean / nested object / array.
        const cases: readonly (readonly [number, unknown])[] = [
          [1, "hello"],
          [2, 42],
          [3, true],
          [4, { street: "12 Aurora Ave", geo: { country: "NO" } }],
          [5, [{ type: "home" }, { type: "work" }]],
        ];
        for (const [id, value] of cases) {
          await db.executeWrite("insert into adapter_json (id, doc) values (?, ?)", [
            id,
            postgresDialect.bindValue("json", value),
          ]);
        }

        const rows = await db.execute("select id, doc from adapter_json", []);
        const doc = new Map(
          rows.map((row) => {
            const r = row as { id: number; doc: unknown };
            return [Number(r.id), r.doc] as const;
          }),
        );
        // A json STRING scalar round-trips as the string "hello" — the regression (it
        // was previously bound as the raw, invalid-JSON text `hello`, which Postgres
        // rejects). The adapter now JSON-ENCODES it to the jsonb string `"hello"`.
        expect(doc.get(1)).toBe("hello");
        expect(doc.get(2)).toBe(42);
        expect(doc.get(3)).toBe(true);
        expect(doc.get(4)).toEqual({ street: "12 Aurora Ave", geo: { country: "NO" } });
        expect(doc.get(5)).toEqual([{ type: "home" }, { type: "work" }]);
      },
      BOOT_TIMEOUT,
    );

    it(
      "fail-safe default: a bare string bound DIRECTLY (no wrapper) lands as valid JSON",
      async () => {
        const db = mustHandle(handle).db;
        await db.execute("drop table if exists adapter_json_direct", []);
        await db.execute("create table adapter_json_direct (id int primary key, doc jsonb)", []);

        // The exact missed path the finding is about: a bare string bound straight
        // through the adapter — NOT via bindValue / any sentinel wrapper — to a jsonb
        // column. The fail-safe serializer JSON-encodes it, so it lands as the valid
        // jsonb string "hello" (not the raw, invalid-JSON text `hello` Postgres rejects).
        await db.executeWrite("insert into adapter_json_direct (id, doc) values (?, ?)", [
          1,
          "hello",
        ]);

        const [row] = await db.execute("select doc from adapter_json_direct where id = ?", [1]);
        expect((row as { doc: unknown }).doc).toBe("hello");
      },
      BOOT_TIMEOUT,
    );

    it(
      "still passes the value-object to-many read's empty-array guard '[]' through raw",
      async () => {
        const db = mustHandle(handle).db;
        // The read lowering binds the array guard as `rawJson('[]')` to cast(? as jsonb);
        // the sentinel passes through raw so it stays a jsonb ARRAY (not the jsonb string
        // scalar `"[]"` the fail-safe default would encode), which jsonb_array_elements
        // accepts. This is exactly what `nestedArrayPredicate` emits into the read binds.
        const [row] = await db.execute(
          "select jsonb_typeof(cast(? as jsonb)) as kind, " +
            "(select count(*) from jsonb_array_elements(cast(? as jsonb))) as n",
          [rawJson("[]"), rawJson("[]")],
        );
        const r = row as { kind: string; n: unknown };
        expect(r.kind).toBe("array");
        expect(Number(r.n)).toBe(0);
      },
      BOOT_TIMEOUT,
    );
  },
);

function mustHandle(handle: AdapterHandle | undefined): AdapterHandle {
  if (handle === undefined) {
    throw new Error("adapter handle was not started");
  }
  return handle;
}

function bytesType(spec: AdapterSmokeSpec): string {
  return spec.dialect.id === "mariadb" ? "longblob" : "bytea";
}

async function startPostgres(): Promise<AdapterHandle> {
  const container = await new PostgreSqlContainer("postgres:17").start();
  const uri = container.getConnectionUri();
  const db = PostgresDatabase.fromConnectionString(uri);
  const peer = PostgresDatabase.fromConnectionString(uri);
  return {
    db,
    peer,
    close: async () => {
      await peer.close();
      await db.close();
      await container.stop();
    },
  };
}

async function startMariaDb(): Promise<AdapterHandle> {
  const container = await new MySqlContainer("mariadb:11.4").start();
  const uri = container.getConnectionUri();
  const db = MariaDbDatabase.fromConnectionString(uri);
  const peer = MariaDbDatabase.fromConnectionString(uri);
  await waitForReady(db);
  return {
    db,
    peer,
    close: async () => {
      await peer.close();
      await db.close();
      await container.stop();
    },
  };
}

async function waitForReady(db: ParallaxDatabase, attempts = 40, delayMs = 1000): Promise<void> {
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
  throw new Error(`could not connect to database after ${attempts} attempts: ${String(lastError)}`);
}

async function provePostgresLockTimeout(
  db: ParallaxDatabase,
  _peer: ParallaxDatabase,
): Promise<void> {
  // Symmetric to `proveMariaDbLockTimeout`: two held `PostgresSession`s prove the
  // m-read-lock shared read lock has locking EFFECT. Session A holds a `for share` read on
  // row 1; session B's UPDATE of the same row blocks and — with the session's
  // lowered `lock_timeout` — raises `55P03`, surfaced as `lockWaitTimeout`. This is
  // the exact behavior the harness-lane `m-read-lock-006` case grades through `runRun`.
  if (!(db instanceof PostgresDatabase)) {
    throw new Error("expected PostgresDatabase");
  }
  await db.execute("drop table if exists adapter_lock", []);
  await db.execute("create table adapter_lock (id int primary key, note text)", []);
  await db.executeWrite("insert into adapter_lock (id, note) values (?, ?)", [1, "one"]);

  const a = await db.openSession();
  const b = await db.openSession();
  try {
    // A takes the shared read lock and HOLDS it (no commit).
    await a.execute("select id from adapter_lock where id = ? for share", [1]);
    let raised: unknown;
    try {
      // B's write contends for the row A read-locked → blocks → 55P03 within budget.
      await b.execute("update adapter_lock set note = ? where id = ?", ["blocked", 1]);
    } catch (error) {
      raised = error;
    }
    expect(raised).toBeInstanceOf(ParallaxTransientError);
    expect((raised as ParallaxTransientError).kind).toBe("lockWaitTimeout");
    expect((raised as ParallaxTransientError).retriable).toBe(false);
  } finally {
    await a.rollback().catch(() => {});
    await b.rollback().catch(() => {});
    await a.close();
    await b.close();
  }
}

async function proveMariaDbLockTimeout(
  db: ParallaxDatabase,
  _peer: ParallaxDatabase,
): Promise<void> {
  if (!(db instanceof MariaDbDatabase)) {
    throw new Error("expected MariaDbDatabase");
  }
  await db.execute("drop table if exists adapter_lock", []);
  await db.execute("create table adapter_lock (id int primary key, note text)", []);
  await db.executeWrite("insert into adapter_lock (id, note) values (?, ?)", [1, "one"]);

  const a = await db.openSession();
  const b = await db.openSession();
  try {
    await a.execute("update adapter_lock set note = ? where id = ?", ["held", 1]);
    let raised: unknown;
    try {
      await b.execute("update adapter_lock set note = ? where id = ?", ["blocked", 1]);
    } catch (error) {
      raised = error;
    }
    expect(raised).toBeInstanceOf(ParallaxTransientError);
    expect((raised as ParallaxTransientError).kind).toBe("lockWaitTimeout");
    expect((raised as ParallaxTransientError).retriable).toBe(false);
  } finally {
    await a.rollback().catch(() => {});
    await b.rollback().catch(() => {});
    await a.close();
    await b.close();
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
