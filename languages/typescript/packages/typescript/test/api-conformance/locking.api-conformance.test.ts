/**
 * API Conformance Suite — **locking** family (Phase 10c): the automatic in-
 * transaction read lock (`0603`), the no-op versioned update (`0609`), the
 * locking-mode version-advancing update (`0611`), the versioned set-based
 * materialize scenarios (`0614` / `0615` — a set-based update on a versioned entity
 * resolves the predicate, then updates per object), and optimistic-mode version-
 * column locking (`0703` / `0704` / `0708`), written as a developer would and run
 * against `postgres:17` through the SHIPPED `@parallax/db-postgres` adapter.
 *
 * **Strategy is a per-unit-of-work mode (M8 / M10).** `px.transaction(body, {
 * concurrency })` selects it: the default `locking` mode takes the shared read lock
 * on in-transaction reads (no developer lock SQL) and advances a versioned entity's
 * version WITHOUT a gate; `optimistic` mode takes no lock and GATES a versioned
 * update on the version the unit of work observed. Version values are framework-
 * owned (ADR 0029): the developer reads the row (which records the observed
 * version), then `update`s — no raw version number is ever passed. A concurrent
 * writer is modeled by the corpus `precondition` (raw SQL) applied out of band,
 * AFTER the read and BEFORE the write, so the gate is genuinely stale.
 */

import { execFileSync } from "node:child_process";
import { ParallaxDecimal } from "@parallax/core";
import { afterAll, beforeAll, expect, describe as group, it } from "vitest";
import { PostgresProvider } from "../../src/conformance/postgres-provider.js";
import {
  AttributeExpression,
  NavigationPath,
  ParallaxOptimisticLockError,
  ParallaxTemporalCloseError,
  Predicate,
} from "../../src/index.js";
import { assertGraph, assertRows, assertTableState, provisionCase } from "./_harness.js";
import { LOCKING } from "./covered.js";

const attr = (ref: string): AttributeExpression => new AttributeExpression(ref);
const dec = (text: string): ParallaxDecimal => ParallaxDecimal.from(text);
const Account = { id: attr("Account.id"), balance: attr("Account.balance") };
const accountPk = (id: number): Predicate =>
  new Predicate({ eq: { attr: "Account.id", value: id } });
const all = (): Predicate => new Predicate({ all: {} });

// Balance — the audit-only (processing-temporal) model the optimistic × temporal
// close cases (`0730`-`0733`) drive: the observed processing-from (`in_z`) is the
// optimistic-lock version analogue (M7/M10).
const Balance = { id: attr("Balance.id"), value: attr("Balance.value") };
const balancePk = (id: number): Predicate =>
  new Predicate({ eq: { attr: "Balance.id", value: id } });

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

it("the locking suite covers exactly the LOCKING family", () => {
  const covered = [
    "0603-read-lock",
    "0609-no-op-update-no-dml",
    "0611-versioned-update-locking-mode",
    // the versioned set-based materialize scenarios (0614/0615)
    "0614-versioned-set-based-materialize-optimistic",
    "0615-versioned-set-based-materialize-locking",
    // the read-lock matrix (0616-0619, api-conformance lane)
    "0616-locking-txn-object-find-locks",
    "0617-locking-txn-projection-omits-lock",
    "0618-locking-txn-deep-fetch-locks-every-level",
    "0619-optimistic-txn-reads-omit-lock",
    "0703-optimistic-lock-conflict",
    "0704-optimistic-lock-success",
    "0708-optimistic-lock-retry-after-conflict",
    // the optimistic x temporal close cases (0730-0733)
    "0730-temporal-close-optimistic-success",
    "0731-temporal-close-optimistic-conflict",
    "0732-temporal-close-retry-after-conflict",
    "0733-temporal-close-zero-rows-error",
  ];
  expect(covered.sort()).toEqual([...LOCKING].sort());
});

group.skipIf(!HAS_DOCKER)("locking suite (Testcontainers postgres:17)", () => {
  const BOOT_TIMEOUT = 600_000;
  let provider: PostgresProvider;

  beforeAll(async () => {
    provider = await PostgresProvider.start();
  }, BOOT_TIMEOUT);

  afterAll(async () => {
    await provider?.close();
  });

  it(
    "0603: a transaction-scoped read takes the automatic shared lock and returns the row",
    async () => {
      const f = await provisionCase(provider, "0603-read-lock");
      // A read-then-write pattern: the read holds the shared row lock automatically
      // (no developer lock call), so the row cannot be changed under us before we act.
      const account = await f.px.transaction((tx) =>
        tx.entity("Account").find(Account.id.eq(2)).single(),
      );
      assertRows([account], f.loaded, "Account", f.metamodel);
    },
    BOOT_TIMEOUT,
  );

  it(
    "a distinct/projection read in a locking transaction proceeds unlocked and returns rows",
    async () => {
      const f = await provisionCase(provider, "0603-read-lock");
      // A `distinct`/projection read cannot carry a row lock (no base row to lock),
      // so inside a locking transaction it proceeds UNLOCKED — no `for share`, and it
      // is never rejected (the D2 reversal; ADR 0030) — and returns its rows.
      const rows = await f.px.transaction((tx) =>
        tx.entity("Account").find(Account.id.eq(2), { distinct: true }).toArray(),
      );
      expect(rows.length).toBeGreaterThan(0);
    },
    BOOT_TIMEOUT,
  );

  // --- read-lock matrix (0616-0619, api-conformance lane) -------------------
  // These register the Phase-3 read-lock behaviors against portable core case ids.
  // Property 6 (golden SQL out of scope): the suite proves the developer-observable
  // BEHAVIOR (the read returns rows / graph, unlocked reads are never rejected); the
  // emitted lock/no-lock TEXT is pinned by the Docker-free StubDatabase unit tests
  // (`packages/typescript/test/writes.test.ts`, `packages/dialect/test/read-lock.test.ts`).

  it(
    "0616: an object find inside a locking transaction returns the row (it takes the shared lock)",
    async () => {
      const f = await provisionCase(provider, "0616-locking-txn-object-find-locks");
      const account = await f.px.transaction(
        (tx) => tx.entity("Account").find(Account.id.eq(2)).single(),
        { concurrency: "locking" },
      );
      assertRows([account], f.loaded, "Account", f.metamodel);
    },
    BOOT_TIMEOUT,
  );

  it(
    "0617: a projection read inside a locking transaction proceeds unlocked and returns rows",
    async () => {
      const f = await provisionCase(provider, "0617-locking-txn-projection-omits-lock");
      // A distinct/projection read cannot carry a row lock, so it proceeds UNLOCKED
      // and is never rejected (the D2 reversal, ADR 0030) — it returns its rows.
      const rows = await f.px.transaction(
        (tx) => tx.entity("Account").find(all(), { distinct: true }).toArray(),
        { concurrency: "locking" },
      );
      expect(rows.length).toBe(3);
    },
    BOOT_TIMEOUT,
  );

  it(
    "0618: a deep fetch inside a locking transaction locks every level and returns the graph",
    async () => {
      const f = await provisionCase(provider, "0618-locking-txn-deep-fetch-locks-every-level");
      // Root + each child level flow through the ONE shared in-transaction read path,
      // so every level takes the shared lock; the developer-observable is the graph.
      const rows = await f.px.transaction(
        (tx) =>
          tx
            .entity("OrderItem")
            .find(all(), { includes: [new NavigationPath(["OrderItem.order"])] })
            .toArray(),
        { concurrency: "locking" },
      );
      assertGraph(rows, f.loaded, "OrderItem", f.metamodel);
    },
    BOOT_TIMEOUT,
  );

  it(
    "0619: reads inside an optimistic transaction take no lock and return rows",
    async () => {
      const f = await provisionCase(provider, "0619-optimistic-txn-reads-omit-lock");
      const account = await f.px.transaction(
        (tx) => tx.entity("Account").find(Account.id.eq(2)).single(),
        { concurrency: "optimistic" },
      );
      assertRows([account], f.loaded, "Account", f.metamodel);
    },
    BOOT_TIMEOUT,
  );

  it(
    "0609: a versioned update that changes no attribute issues no DML",
    async () => {
      const f = await provisionCase(provider, "0609-no-op-update-no-dml");
      const observed = await f.px.transaction(async (tx) => {
        const accounts = tx.entity("Account");
        // Read account 2 (records the observed version).
        await accounts.find(Account.id.eq(2)).single();
        // An update whose `set` changes nothing issues no DML — zero rows affected.
        const result = await accounts.update(accountPk(2), { set: [] });
        expect(result.affectedRows).toBe(0);
        // The row is unchanged (the no-op wrote nothing).
        return accounts.find(Account.id.eq(2)).toArray();
      });
      assertRows(observed, f.loaded, "Account", f.metamodel);
    },
    BOOT_TIMEOUT,
  );

  it(
    "0611: a locking-mode update advances the version with no gate",
    async () => {
      const f = await provisionCase(provider, "0611-versioned-update-locking-mode");
      // Default `locking` mode: the read takes the shared lock and records version 1;
      // the update advances the version to 2 with no `and version = ?` gate.
      const result = await f.px.transaction(async (tx) => {
        const accounts = tx.entity("Account");
        await accounts.find(Account.id.eq(2)).single();
        return accounts.update(accountPk(2), { set: [Account.balance.set(dec("500.00"))] });
      });
      expect(result.affectedRows).toBe(1);
      await assertTableState(f.db, f.loaded, f.metamodel);
    },
    BOOT_TIMEOUT,
  );

  it(
    "0615: a versioned set-based update materializes into per-object version-advancing updates",
    async () => {
      const f = await provisionCase(provider, "0615-versioned-set-based-materialize-locking");
      // A set-based update on a VERSIONED entity with NO explicit prior find: the
      // update MATERIALIZES — it resolves `balance < 200` to rows (recording their
      // versions + taking the locking lock), then updates per object (ungated).
      const observed = await f.px.transaction(
        async (tx) => {
          const accounts = tx.entity("Account");
          const result = await accounts.update(Account.balance.lt(200), {
            set: [Account.balance.set(dec("0.00"))],
          });
          // Both matched rows (ids 1 and 3) were updated, one per-object UPDATE each.
          expect(result.affectedRows).toBe(2);
          // Verify by re-reading: the two accounts now carry balance 0.00, version 2.
          return accounts.find(Account.balance.lt(200)).toArray();
        },
        { concurrency: "locking" },
      );
      assertRows(observed, f.loaded, "Account", f.metamodel);
    },
    BOOT_TIMEOUT,
  );

  it(
    "0614: a versioned set-based update materializes into per-object GATED updates",
    async () => {
      const f = await provisionCase(provider, "0614-versioned-set-based-materialize-optimistic");
      // The optimistic companion: the materialize read takes no lock, and each
      // per-object UPDATE gates on that row's observed version (framework-owned).
      const observed = await f.px.transaction(
        async (tx) => {
          const accounts = tx.entity("Account");
          const result = await accounts.update(Account.balance.lt(200), {
            set: [Account.balance.set(dec("0.00"))],
          });
          expect(result.affectedRows).toBe(2);
          return accounts.find(Account.balance.lt(200)).toArray();
        },
        { concurrency: "optimistic" },
      );
      assertRows(observed, f.loaded, "Account", f.metamodel);
    },
    BOOT_TIMEOUT,
  );

  it(
    "0703: a stale-version update conflicts (affects 0 rows) — the row is unchanged",
    async () => {
      const f = await provisionCase(provider, "0703-optimistic-lock-conflict");
      let conflicted = false;
      try {
        await f.px.transaction(
          async (tx) => {
            const accounts = tx.entity("Account");
            // Read account 2 at version 1 (optimistic mode takes no lock).
            await accounts.find(Account.id.eq(2)).single();
            // A concurrent transaction commits first (the precondition): balance 999, version 2.
            await applyPrecondition(provider, f);
            // Our update gates on the version we observed (1) — now stale ⇒ conflict.
            await accounts.update(accountPk(2), { set: [Account.balance.set(dec("250.00"))] });
          },
          { concurrency: "optimistic" },
        );
      } catch (error) {
        conflicted = error instanceof ParallaxOptimisticLockError;
      }
      expect(conflicted, "expected a ParallaxOptimisticLockError").toBe(true);
      // The row still carries the concurrent writer's values (our write did NOT apply).
      await assertTableState(f.db, f.loaded, f.metamodel);
    },
    BOOT_TIMEOUT,
  );

  it(
    "0704: an update on the fresh version succeeds (affects 1 row)",
    async () => {
      const f = await provisionCase(provider, "0704-optimistic-lock-success");
      const result = await f.px.transaction(
        async (tx) => {
          const accounts = tx.entity("Account");
          // Read account 2 at version 1, then update gating on that observed version.
          await accounts.find(Account.id.eq(2)).single();
          return accounts.update(accountPk(2), { set: [Account.balance.set(dec("500.00"))] });
        },
        { concurrency: "optimistic" },
      );
      expect(result.affectedRows).toBe(1);
      await assertTableState(f.db, f.loaded, f.metamodel);
    },
    BOOT_TIMEOUT,
  );

  it(
    "0708: a retry re-reads the fresh version after the conflict and succeeds",
    async () => {
      const f = await provisionCase(provider, "0708-optimistic-lock-retry-after-conflict");
      // Attempt 1 (gate on the observed version 1) conflicts; the retry re-reads the
      // fresh version and re-applies — a caller-driven retry loop with NO raw version.
      const result = await f.px.transaction(
        async (tx) => {
          const accounts = tx.entity("Account");
          await accounts.find(Account.id.eq(2)).single(); // observes version 1
          await applyPrecondition(provider, f); // concurrent writer commits: version 1 -> 2
          try {
            return await accounts.update(accountPk(2), {
              set: [Account.balance.set(dec("250.00"))],
            });
          } catch (error) {
            if (!(error instanceof ParallaxOptimisticLockError)) {
              throw error;
            }
            // Re-read the fresh row (records the new observed version) and retry.
            await accounts.find(Account.id.eq(2)).single();
            return accounts.update(accountPk(2), { set: [Account.balance.set(dec("250.00"))] });
          }
        },
        { concurrency: "optimistic" },
      );
      expect(result.affectedRows).toBe(1);
      await assertTableState(f.db, f.loaded, f.metamodel);
    },
    BOOT_TIMEOUT,
  );

  // --- optimistic x temporal close (0730-0733) ------------------------------
  // A processing-axis (audit-only) temporal entity carries NO version column, so the
  // observed processing-from (in_z) is the optimistic-lock version analogue (M7/M10).
  // The developer reads the current milestone (which records its in_z), then closes
  // it; in optimistic mode the close gates on that observed in_z. Table state is NOT
  // asserted here — the runtime close's out_z is the transaction CLOCK instant, not
  // the corpus's authored txInstant, so the observable is the affected count / the
  // thrown conflict (the golden close text is pinned by the harness compile lane).

  it(
    "0730: an optimistic close on a fresh observed in_z closes exactly the current milestone",
    async () => {
      const f = await provisionCase(provider, "0730-temporal-close-optimistic-success");
      const result = await f.px.transaction(
        async (tx) => {
          const balances = tx.entity("Balance");
          // Read the current milestone of id 2 (records its observed in_z), then update
          // it (close the current row + chain a new one); the close gates on that in_z.
          await balances.find(Balance.id.eq(2)).single();
          return balances.update(balancePk(2), { set: [Balance.value.set(dec("250.00"))] });
        },
        { concurrency: "optimistic" },
      );
      // The gated close matched the one current milestone (fresh in_z) — 1 row closed.
      expect(result.affectedRows).toBe(1);
    },
    BOOT_TIMEOUT,
  );

  it(
    "0731: an optimistic close on a STALE observed in_z conflicts (a current row still exists)",
    async () => {
      const f = await provisionCase(provider, "0731-temporal-close-optimistic-conflict");
      let conflicted = false;
      try {
        await f.px.transaction(
          async (tx) => {
            const balances = tx.entity("Balance");
            // Observe id 2's current milestone (in_z 2024-02-01), no lock.
            await balances.find(Balance.id.eq(2)).single();
            // A concurrent writer fully re-chains id 2 (close old, open a fresh current
            // row at a new in_z) — so a current row EXISTS, but it is a different milestone.
            await applyPrecondition(provider, f);
            // Our close gates on the STALE observed in_z ⇒ 0 rows ⇒ conflict.
            await balances.update(balancePk(2), { set: [Balance.value.set(dec("250.00"))] });
          },
          { concurrency: "optimistic" },
        );
      } catch (error) {
        conflicted = error instanceof ParallaxOptimisticLockError;
      }
      expect(conflicted, "expected a ParallaxOptimisticLockError").toBe(true);
    },
    BOOT_TIMEOUT,
  );

  it(
    "0732: a retry re-reads the fresh current in_z after the temporal conflict and succeeds",
    async () => {
      const f = await provisionCase(provider, "0732-temporal-close-retry-after-conflict");
      const result = await f.px.transaction(
        async (tx) => {
          const balances = tx.entity("Balance");
          await balances.find(Balance.id.eq(2)).single(); // observes in_z 2024-02-01
          await applyPrecondition(provider, f); // concurrent writer re-chains id 2
          try {
            return await balances.update(balancePk(2), {
              set: [Balance.value.set(dec("250.00"))],
            });
          } catch (error) {
            if (!(error instanceof ParallaxOptimisticLockError)) {
              throw error;
            }
            // Re-read the fresh current milestone (records the new observed in_z) + retry.
            await balances.find(Balance.id.eq(2)).single();
            return balances.update(balancePk(2), { set: [Balance.value.set(dec("250.00"))] });
          }
        },
        { concurrency: "optimistic" },
      );
      expect(result.affectedRows).toBe(1);
    },
    BOOT_TIMEOUT,
  );

  it(
    "0733: a locking-mode close that finds no current row raises (never silent)",
    async () => {
      const f = await provisionCase(provider, "0733-temporal-close-zero-rows-error");
      // A concurrent writer TERMINATED id 2's current row out of band (committed BEFORE
      // our transaction opens, so our locking read takes no lock on an already-closed row).
      await applyPrecondition(provider, f);
      let raised = false;
      try {
        // Locking mode: the close is UNGATED, but a zero-row close still raises — a
        // distinct non-retriable stale/consistency error (the current milestone is gone).
        await f.px.transaction((tx) => tx.entity("Balance").terminate(balancePk(2)), {
          concurrency: "locking",
        });
      } catch (error) {
        raised = error instanceof ParallaxTemporalCloseError;
      }
      expect(raised, "expected a ParallaxTemporalCloseError").toBe(true);
    },
    BOOT_TIMEOUT,
  );
});

/**
 * Apply the case's `precondition` (raw concurrent-writer SQL) out of band on an
 * INDEPENDENT connection (the provider's peer adapter). This models the OTHER
 * transaction committing between our unit of work's read and its gated write; it
 * is harness plumbing, not developer-authored code. It MUST run on the peer, not
 * `fixture.db`: the shipped adapter is single-connection, so issuing it there while
 * `px.transaction` holds the connection would deadlock.
 */
async function applyPrecondition(
  provider: PostgresProvider,
  fixture: Awaited<ReturnType<typeof provisionCase>>,
): Promise<void> {
  const precondition = fixture.loaded.raw.precondition as string | readonly string[] | undefined;
  if (precondition === undefined) {
    return;
  }
  // A precondition may be a single statement (`0703`) or an ORDERED LIST — the
  // temporal-close conflict cases (`0731`/`0732`) chain a full new current row
  // (close the old milestone, then insert a fresh one). Apply each in order.
  const statements = Array.isArray(precondition) ? precondition : [precondition as string];
  for (const statement of statements) {
    await provider.peer.execute(statement, []);
  }
}
