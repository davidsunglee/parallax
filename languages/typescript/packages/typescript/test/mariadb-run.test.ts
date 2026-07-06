/**
 * The MariaDB **curated m-case-format matrix profile** (Testcontainers `mariadb:11.4`) —
 * the driver-bound corner that proves `typescript × mariadb` end-to-end for the
 * declared `mariadb-curated-25` partial profile.
 *
 * The abstraction earns its keep by a real second implementer round-tripping
 * through an actual database: each case compiles against `mariadbDialect`, runs
 * through the shipped `@parallax/db-mariadb` adapter (via the composition-root
 * {@link MariaDbProvider}), and is graded on BOTH the observed result (rows / graph
 * / table state, under the shared m-case-format comparison rules) AND the emitted SQL
 * (`emission.sql === goldenSql.mariadb`). This is where MariaDB's divergences —
 * backtick quoting (`m-descriptor-001`), `is null,` NULL ordering (`m-deep-fetch-012`), ` lock in share
 * mode` (`m-read-lock-009`), max-sentinel infinity (`m-temporal-read-021` / `m-audit-write-001`), the scalar-type map +
 * `hex()` (`m-core-004`), and errno classification (`m-db-error-001`-`m-db-error-008`) — are proven by a real
 * round trip, not only by the Docker-free compile-golden / dialect-unit lanes.
 *
 * The 25-case set (14 `slice-mvp-1 ∩ goldenSql.mariadb` + 11 marquee proofs):
 *   - flat reads:  `m-op-algebra-002 m-descriptor-001 m-op-algebra-016 m-op-algebra-018 m-op-algebra-026 m-navigate-001 m-read-lock-009 m-temporal-read-021 m-core-004`
 *   - deep fetch:  `m-deep-fetch-012 m-navigate-013 m-navigate-015 m-navigate-020 m-navigate-024`
 *   - writes:      `m-core-002 m-core-003 m-audit-write-001`
 *   - errno:       `m-db-error-001`-`m-db-error-008` (uniqueViolation / deadlock / lock-wait timeout)
 *
 * The errno family asserts the thrown `ParallaxTransientError` / neutral category
 * via the adapter's classifier, and `m-db-error-004`-`m-db-error-007` drive the TWO-CONNECTION
 * `concurrency.rounds` choreography (the multi-connection harness, not single-shot
 * reads). Skipped when Docker is unavailable (reported, never silently passed);
 * this lane REQUIRES Docker (Testcontainers).
 */
import { execFileSync } from "node:child_process";
import {
  buildDeepFetchPlan,
  buildWriteSequencePlan,
  columnTypesForCase,
  compareGraph,
  compareRowSet,
  compareTableState,
  type Graph,
  type LoadedCase,
  type ProviderRow,
  schemaForReadCase,
  type TableState,
} from "@parallax/conformance";
import { ParallaxTransientError } from "@parallax/db";
import { classifyMariaError } from "@parallax/db-mariadb";
import { columnOrder, ddlForDescriptor, mariadbDialect } from "@parallax/dialect";
import { type EntityMetadata, Metamodel, parseOperation } from "@parallax/operation";
import { deepFetch, type Exec, type Row as GraphRow } from "@parallax/relationships";
import { compile } from "@parallax/sql";
import { afterAll, beforeAll, expect, describe as group, it } from "vitest";
import { MariaDbProvider } from "../src/conformance/mariadb-provider.js";
import {
  caseById,
  casesForProfile,
  exclusionsForProfile,
  MARIADB_CURATED_PROFILE,
  MARIADB_CURATED_PROFILE_IDS,
  MARIADB_DEADLOCK_PROFILE_IDS,
  MARIADB_DEEP_FETCH_PROFILE_IDS,
  MARIADB_FLAT_READ_PROFILE_IDS,
  MARIADB_LOCK_WAIT_PROFILE_IDS,
  MARIADB_UNIQUE_PROFILE_IDS,
  MARIADB_WRITE_PROFILE_IDS,
  POSTGRES_FULL_PROFILE,
} from "./conformance-profiles.js";

/** Load a corpus case by its four-digit id (throws if the id is not discovered). */
function loadedById(id: string): LoadedCase {
  return caseById(id).loaded;
}

/** The MariaDB golden a case pins (a single string, or the per-statement array). */
function mariadbGolden(loaded: LoadedCase): string | readonly string[] {
  const golden = (loaded.raw.goldenSql as { mariadb?: string | readonly string[] } | undefined)
    ?.mariadb;
  if (golden === undefined) {
    throw new Error(`${loaded.casePath} carries no goldenSql.mariadb`);
  }
  return golden;
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

// --- provisioning + fixture loading (MariaDB DDL / dialect) ------------------

/** Provision a clean DB with fixtures loaded (read / deep-fetch cases). */
async function provision(provider: MariaDbProvider, loaded: LoadedCase): Promise<void> {
  await provider.reset();
  await provider.applyDdl(ddlForDescriptor(loaded.descriptor, mariadbDialect));
  await loadFixtures(provider, loaded);
}

/**
 * Provision a clean, EMPTY DB (reset + DDL), loading fixtures ONLY when the case
 * opts in (`loadFixtures: true` — the deadlock / lock-wait cases seed `gauge`);
 * write sequences and unique-violation cases build their own state from DML.
 */
async function provisionEmpty(provider: MariaDbProvider, loaded: LoadedCase): Promise<void> {
  await provider.reset();
  await provider.applyDdl(ddlForDescriptor(loaded.descriptor, mariadbDialect));
  if (loaded.raw.loadFixtures === true) {
    await loadFixtures(provider, loaded);
  }
}

/** Load every entity's fixture rows in descriptor column order (mirrors the runner). */
async function loadFixtures(provider: MariaDbProvider, loaded: LoadedCase): Promise<void> {
  const metamodel = Metamodel.fromDescriptor(loaded.descriptor);
  for (const entity of metamodel.entities()) {
    const rows = loaded.fixtures[entity.name] ?? [];
    if (rows.length === 0) {
      continue;
    }
    const attributes = entity.attributes();
    const columns = columnOrder({
      table: entity.table,
      attributes: attributes.map((a) => ({ type: a.type, column: a.column })),
    });
    const nameByColumn = new Map(attributes.map((a) => [a.column, a.name]));
    const tuples = rows.map((row) =>
      columns.map((column) => row[nameByColumn.get(column) ?? column] ?? null),
    );
    await provider.loadFixtures(entity.table, columns, tuples);
  }
}

/**
 * `select t0.<col>, … from <table> t0` for every table the case's
 * `expectedTableState` names — read back in column order through the MariaDB
 * dialect quoting (mirrors the runner's `readTableSql`).
 */
async function readTableState(provider: MariaDbProvider, loaded: LoadedCase): Promise<TableState> {
  const metamodel = Metamodel.fromDescriptor(loaded.descriptor);
  const byTable = new Map<string, EntityMetadata>();
  for (const entity of metamodel.entities()) {
    if (!byTable.has(entity.table)) {
      byTable.set(entity.table, entity);
    }
  }
  const expected = (loaded.raw.expectedTableState as Record<string, unknown> | undefined) ?? {};
  const state: Record<string, readonly ProviderRow[]> = {};
  for (const table of Object.keys(expected)) {
    const entity = byTable.get(table);
    if (entity === undefined) {
      throw new Error(`expectedTableState names table '${table}' not in the model`);
    }
    const columns = columnOrder({
      table: entity.table,
      attributes: entity.attributes().map((a) => ({ type: a.type, column: a.column })),
    });
    const projection = columns.map((c) => `t0.${mariadbDialect.quoteIdentifier(c)}`).join(", ");
    const sql = `select ${projection} from ${mariadbDialect.quoteIdentifier(entity.table)} t0`;
    state[table] = await provider.query(sql, []);
  }
  return state;
}

// --- shared harness (one container per file) --------------------------------

const BOOT_TIMEOUT = 600_000;
let provider: MariaDbProvider;

group.skipIf(!HAS_DOCKER)(
  `${MARIADB_CURATED_PROFILE.name} run lane (Testcontainers mariadb:11.4)`,
  () => {
    beforeAll(async () => {
      provider = await MariaDbProvider.start();
    }, BOOT_TIMEOUT);

    afterAll(async () => {
      await provider?.close();
    });

    // --- flat reads -----------------------------------------------------------

    group("flat reads (rows + emitted SQL)", () => {
      it.each(MARIADB_FLAT_READ_PROFILE_IDS.map((id) => ({ id, loaded: loadedById(id) })))(
        "$id returns the expected rows and emits goldenSql.mariadb",
        async ({ loaded }) => {
          await provision(provider, loaded);
          const operation = parseOperation(loaded.raw.operation);
          const schema = schemaForReadCase(loaded, operation, mariadbDialect);
          const { sql, binds } = compile(operation, schema, mariadbDialect, {
            locking: loaded.tags.includes("m-read-lock"),
          });

          expect(sql).toBe(mariadbGolden(loaded));

          const observed = await provider.query(sql, binds as readonly unknown[]);
          const expected =
            (loaded.raw.expectedRows as readonly Record<string, unknown>[] | undefined) ?? [];
          const comparison = compareRowSet(observed, expected, columnTypesForCase(loaded));
          expect(
            comparison.equal,
            `${loaded.casePath}: ${comparison.reason}\nobserved=${JSON.stringify(observed)}`,
          ).toBe(true);
        },
        BOOT_TIMEOUT,
      );
    });

    // --- deep fetch -----------------------------------------------------------

    group("deep fetch (graph + per-level emitted SQL)", () => {
      it.each(MARIADB_DEEP_FETCH_PROFILE_IDS.map((id) => ({ id, loaded: loadedById(id) })))(
        "$id assembles the expected graph and emits the per-level goldenSql.mariadb",
        async ({ loaded }) => {
          await provision(provider, loaded);
          const plan = buildDeepFetchPlan(loaded, mariadbDialect);
          const rootRows = await provider.query(plan.root.sql, plan.root.binds);
          const emissions: string[] = [plan.root.sql];
          const exec: Exec = async (levelSql, levelBinds) => {
            emissions.push(levelSql);
            return (await provider.query(levelSql, levelBinds)) as readonly GraphRow[];
          };
          const result = await deepFetch(rootRows as readonly GraphRow[], plan.tree, exec);

          expect(emissions).toEqual(mariadbGolden(loaded));

          const graph: Graph = {
            [plan.rootEntity]: result.rows as readonly Record<string, unknown>[],
          };
          const expectedGraph = (loaded.raw.expectedGraph ?? {}) as Graph;
          const comparison = compareGraph(graph, expectedGraph, columnTypesForCase(loaded));
          expect(comparison.equal, `${loaded.casePath}: ${comparison.reason}`).toBe(true);

          const roundTrips = loaded.raw.roundTrips as number | undefined;
          if (roundTrips !== undefined) {
            expect(result.roundTrips, loaded.casePath).toBe(roundTrips);
          }
        },
        BOOT_TIMEOUT,
      );
    });

    // --- write sequences ------------------------------------------------------

    group("write sequences (table state + emitted SQL)", () => {
      it.each(MARIADB_WRITE_PROFILE_IDS.map((id) => ({ id, loaded: loadedById(id) })))(
        "$id applies the DML and reads back the expected table state",
        async ({ loaded }) => {
          await provisionEmpty(provider, loaded);
          const plan = buildWriteSequencePlan(loaded, mariadbDialect);
          const emissions: string[] = [];
          for (const statement of plan.statements) {
            emissions.push(statement.sql);
            await provider.exec(statement.sql, statement.binds);
          }

          expect(emissions).toEqual(mariadbGolden(loaded));

          const observed = await readTableState(provider, loaded);
          const expected = (loaded.raw.expectedTableState ?? {}) as TableState;
          const comparison = compareTableState(observed, expected, columnTypesForCase(loaded));
          expect(comparison.equal, `${loaded.casePath}: ${comparison.reason}`).toBe(true);
        },
        BOOT_TIMEOUT,
      );
    });

    // --- bytes write round-trip (dialect bind seam) ---------------------------

    group("bytes write round-trip (dialect bind seam)", () => {
      it(
        "stores a `bytes` value as raw bytes, not hex TEXT",
        async () => {
          // The runtime write path binds a `bytes` value via `mariadbDialect.bindValue`,
          // then hands it to the shipped adapter's `executeWrite`. The `Uint8Array` must
          // survive as raw bytes (the adapter wraps a `Buffer` for the mysql2 blob bind),
          // NOT `toWire`'s hex TEXT — a hex string would be stored as its ASCII characters
          // in the `LONGBLOB`. Guards the finding-#1 fix end-to-end against a real MariaDB.
          const adapter = provider.database;
          await adapter.pool.query("drop table if exists bytes_rt");
          await adapter.pool.query("create table bytes_rt (id int primary key, payload longblob)");
          const payload = new Uint8Array([0xde, 0xad, 0xbe, 0xef]);
          await adapter.executeWrite("insert into bytes_rt (id, payload) values (?, ?)", [
            1,
            mariadbDialect.bindValue("bytes", payload),
          ]);

          const [row] = await adapter.execute("select payload from bytes_rt where id = ?", [1]);
          expect((row as { payload: unknown }).payload).toBeInstanceOf(Uint8Array);
          expect(Array.from((row as { payload: Uint8Array }).payload)).toEqual([
            0xde, 0xad, 0xbe, 0xef,
          ]);
        },
        BOOT_TIMEOUT,
      );
    });

    // --- errno: unique violations (single connection) -------------------------

    group("errno — uniqueViolation", () => {
      it.each(MARIADB_UNIQUE_PROFILE_IDS.map((id) => ({ id, loaded: loadedById(id) })))(
        "$id raises errno 1062 → uniqueViolation on the colliding statement",
        async ({ loaded }) => {
          await provisionEmpty(provider, loaded);
          const statements = mariadbGolden(loaded) as readonly string[];
          const binds = (loaded.raw.binds as readonly (readonly unknown[])[] | undefined) ?? [];

          let raised: unknown;
          for (let i = 0; i < statements.length; i += 1) {
            try {
              await provider.exec(statements[i] as string, binds[i] ?? []);
            } catch (error) {
              raised = error;
              // The violation is the LAST statement (earlier statements seed / commit).
              expect(i, `${loaded.casePath}: expected the violation on the last statement`).toBe(
                statements.length - 1,
              );
              break;
            }
          }

          expect(raised, `${loaded.casePath}: expected a uniqueViolation`).toBeDefined();
          expect(classifyMariaError(raised)).toBe("uniqueViolation");
          const expectedCode = (loaded.raw.expectedNativeCode as { mariadb?: number }).mariadb;
          expect((raised as { errno?: number }).errno).toBe(expectedCode);
        },
        BOOT_TIMEOUT,
      );
    });

    // --- errno: deadlock (two connections) ------------------------------------

    group("errno — deadlock (two-connection choreography)", () => {
      it.each(MARIADB_DEADLOCK_PROFILE_IDS.map((id) => ({ id, loaded: loadedById(id) })))(
        "$id victimizes one transaction with errno 1213 → deadlock",
        async ({ loaded }) => {
          await provisionEmpty(provider, loaded);
          const rounds = concurrencyRounds(loaded);
          const a = await provider.openSession();
          const b = await provider.openSession();
          try {
            // Round 0: A and B each acquire their first lock (both held — the barrier).
            await a.execute(...entry(rounds[0], "A"));
            await b.execute(...entry(rounds[0], "B"));
            // Round 1: both attempt the crossing lock CONCURRENTLY → a cycle; InnoDB
            // victimizes one immediately (errno 1213), the other proceeds.
            const results = await Promise.allSettled([
              a.execute(...entry(rounds[1], "A")),
              b.execute(...entry(rounds[1], "B")),
            ]);
            const victim = results
              .filter((r): r is PromiseRejectedResult => r.status === "rejected")
              .map((r) => r.reason)
              .find((reason) => reason instanceof ParallaxTransientError) as
              | ParallaxTransientError
              | undefined;
            expect(
              victim,
              `${loaded.casePath}: expected a ParallaxTransientError deadlock`,
            ).toBeInstanceOf(ParallaxTransientError);
            expect(victim?.kind).toBe("deadlock");
          } finally {
            await a.rollback().catch(() => {});
            await b.rollback().catch(() => {});
            await a.close();
            await b.close();
          }
        },
        BOOT_TIMEOUT,
      );
    });

    // --- errno: lock-wait timeout (two connections) ---------------------------

    group("errno — lockWaitTimeout (two-connection choreography)", () => {
      it.each(MARIADB_LOCK_WAIT_PROFILE_IDS.map((id) => ({ id, loaded: loadedById(id) })))(
        "$id blocks the second connection to errno 1205 → lockWaitTimeout",
        async ({ loaded }) => {
          await provisionEmpty(provider, loaded);
          const rounds = concurrencyRounds(loaded);
          const a = await provider.openSession();
          const b = await provider.openSession();
          try {
            // Round 0: A locks the row and holds it (no commit).
            await a.execute(...entry(rounds[0], "A"));
            // Round 1: B contends for the SAME row → blocks → errno 1205 within the
            // session's 1-second lock-wait budget.
            let raised: unknown;
            try {
              await b.execute(...entry(rounds[1], "B"));
            } catch (error) {
              raised = error;
            }
            expect(raised, `${loaded.casePath}: expected a lock-wait timeout`).toBeInstanceOf(
              ParallaxTransientError,
            );
            expect((raised as ParallaxTransientError).kind).toBe("lockWaitTimeout");
          } finally {
            await a.rollback().catch(() => {});
            await b.rollback().catch(() => {});
            await a.close();
            await b.close();
          }
        },
        BOOT_TIMEOUT,
      );
    });
  },
);

// --- concurrency round helpers ----------------------------------------------

/** One side (`A`/`B`) of a `concurrency.rounds` step: its MariaDB golden + binds. */
interface RoundEntry {
  readonly goldenSql: { readonly mariadb: string };
  readonly binds: readonly unknown[];
}

/** A `concurrency.rounds` step: the `A` and/or `B` statement issued that round. */
interface Round {
  readonly A?: RoundEntry;
  readonly B?: RoundEntry;
}

/** The case's declared two-connection choreography rounds. */
function concurrencyRounds(loaded: LoadedCase): readonly Round[] {
  const concurrency = loaded.raw.concurrency as { rounds?: readonly Round[] } | undefined;
  const rounds = concurrency?.rounds;
  if (rounds === undefined || rounds.length < 2) {
    throw new Error(`${loaded.casePath} declares no two-round concurrency choreography`);
  }
  return rounds;
}

/** Resolve one side's `[sql, binds]` for a session `execute(...)` call. */
function entry(round: Round, side: "A" | "B"): [string, readonly unknown[]] {
  const item = round[side];
  if (item === undefined) {
    throw new Error(`concurrency round has no '${side}' statement`);
  }
  return [item.goldenSql.mariadb, item.binds];
}

// Discovery is Docker-free; assert the exact 25-case set unconditionally so a
// discovery regression that silently drops a case fails loudly. The 21 top-level
// golden cases (reads / deep fetch / writes / unique inserts) carry
// `goldenSql.mariadb`; the 4 deadlock / lock-wait concurrency proofs carry their
// golden SQL inside `concurrency.rounds`.
it("covers exactly the declared mariadb-curated-25 profile", () => {
  const shapeGolden = [
    ...MARIADB_FLAT_READ_PROFILE_IDS,
    ...MARIADB_DEEP_FETCH_PROFILE_IDS,
    ...MARIADB_WRITE_PROFILE_IDS,
    ...MARIADB_UNIQUE_PROFILE_IDS,
  ];
  const concurrency = [...MARIADB_DEADLOCK_PROFILE_IDS, ...MARIADB_LOCK_WAIT_PROFILE_IDS];
  expect(
    casesForProfile(MARIADB_CURATED_PROFILE)
      .map(({ id }) => id)
      .sort(),
  ).toEqual([...MARIADB_CURATED_PROFILE_IDS].sort());
  expect(shapeGolden.length + concurrency.length).toBe(25);
  for (const id of shapeGolden) {
    expect(mariadbGolden(loadedById(id))).toBeDefined();
  }
  for (const id of concurrency) {
    expect(concurrencyRounds(loadedById(id)).length).toBeGreaterThanOrEqual(2);
  }
});

it("reports non-curated Postgres full-profile cases as explicit MariaDB exclusions", () => {
  const postgresFullCount = casesForProfile(POSTGRES_FULL_PROFILE).length;
  const exclusions = exclusionsForProfile(MARIADB_CURATED_PROFILE);
  expect(exclusions).toHaveLength(postgresFullCount - 14);
  expect(exclusions.every((item) => item.reason.includes("no goldenSql.mariadb"))).toBe(true);
});
