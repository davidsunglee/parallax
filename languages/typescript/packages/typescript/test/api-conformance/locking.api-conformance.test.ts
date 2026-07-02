/**
 * API Conformance Suite — **locking** family (Phase 10c): the automatic in-transaction
 * read lock (`0603`) and version-column optimistic locking (`0703` / `0704` /
 * `0707` / `0708`), written as a developer would and run against `postgres:17`
 * through the SHIPPED `@parallax/db-postgres` adapter.
 *
 * **Read lock (`0603`).** The default in-transaction read takes a shared row lock
 * AUTOMATICALLY (M8) — there is NO explicit developer lock call in V1. The suite
 * asserts the RETURNED ROW (what `0603` proves), demonstrating the "you write no
 * locking SQL" value prop; the `for share of t0` SQL-text assertion stays in the
 * conformance/compile lane (SQL text is not a developer-facing surface).
 *
 * **Optimistic locking.** A developer reads a managed object (capturing its
 * `version`), and a later `update` gates on THAT version (spec §3: conflicts are
 * caller-driven). A concurrent writer is modeled by the corpus `precondition` (raw
 * SQL) applied OUT OF BAND between the read and the write — harness-side, exactly
 * as the run lane does. `0703` conflicts (stale version → 0 rows →
 * `ParallaxOptimisticLockError`); `0704` succeeds; `0707` bumps the version with no
 * domain change; `0708` retries on the fresh version after the conflict.
 */

import { execFileSync } from "node:child_process";
import { ParallaxDecimal } from "@parallax/core";
import { afterAll, beforeAll, expect, describe as group, it } from "vitest";
import { PostgresProvider } from "../../src/conformance/postgres-provider.js";
import { AttributeExpression, ParallaxOptimisticLockError, Predicate } from "../../src/index.js";
import { assertRows, assertTableState, provisionCase } from "./_harness.js";
import { LOCKING } from "./covered.js";

const attr = (ref: string): AttributeExpression => new AttributeExpression(ref);
const dec = (text: string): ParallaxDecimal => ParallaxDecimal.from(text);
const Account = { id: attr("Account.id"), balance: attr("Account.balance") };

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
    "0703-optimistic-lock-conflict",
    "0704-optimistic-lock-success",
    "0707-optimistic-lock-version-only-bump",
    "0708-optimistic-lock-retry-after-conflict",
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
    "0703: a stale-version update conflicts (affects 0 rows) — the row is unchanged",
    async () => {
      const f = await provisionCase(provider, "0703-optimistic-lock-conflict");
      // The developer read account 2 at version 1 earlier.
      const readVersion = 1;
      // A concurrent transaction commits first (the precondition): balance 999, version 2.
      await applyPrecondition(f);
      // Our update gates on the version we read (1) — now stale ⇒ conflict.
      let conflicted = false;
      try {
        await f.px.transaction(async (tx) => {
          await tx
            .entity("Account")
            .update(new Predicate({ eq: { attr: "Account.id", value: 2 } }), {
              set: [Account.balance.set(dec("250.00"))],
              expectedVersion: readVersion,
            });
        });
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
      const result = await f.px.transaction((tx) =>
        tx.entity("Account").update(new Predicate({ eq: { attr: "Account.id", value: 2 } }), {
          set: [Account.balance.set(dec("500.00"))],
          expectedVersion: 1,
        }),
      );
      expect(result.affectedRows).toBe(1);
      await assertTableState(f.db, f.loaded, f.metamodel);
    },
    BOOT_TIMEOUT,
  );

  it(
    "0707: a version-only bump advances the version with no domain change",
    async () => {
      const f = await provisionCase(provider, "0707-optimistic-lock-version-only-bump");
      const result = await f.px.transaction((tx) =>
        tx.entity("Account").update(new Predicate({ eq: { attr: "Account.id", value: 2 } }), {
          set: [],
          expectedVersion: 1,
        }),
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
      // Concurrent writer commits (precondition): version 1 → 2.
      await applyPrecondition(f);
      const account = "Account";
      const pred = new Predicate({ eq: { attr: "Account.id", value: 2 } });
      // Attempt 1 (stale, gate on 1) conflicts; retry re-reads the fresh version (2)
      // and re-applies — a caller-driven retry loop (spec §3).
      const result = await f.px.transaction(async (tx) => {
        try {
          return await tx
            .entity(account)
            .update(pred, { set: [Account.balance.set(dec("250.00"))], expectedVersion: 1 });
        } catch (error) {
          if (!(error instanceof ParallaxOptimisticLockError)) {
            throw error;
          }
          // Re-read the fresh version off the row and retry.
          const fresh = await tx.entity(account).find(pred).single();
          const freshVersion = Number((fresh as { version: number }).version);
          return tx.entity(account).update(pred, {
            set: [Account.balance.set(dec("250.00"))],
            expectedVersion: freshVersion,
          });
        }
      });
      expect(result.affectedRows).toBe(1);
      await assertTableState(f.db, f.loaded, f.metamodel);
    },
    BOOT_TIMEOUT,
  );
});

/**
 * Apply the case's `precondition` (raw concurrent-writer SQL) out of band through
 * the shipped adapter — exactly as the conformance run lane does. This models the
 * OTHER transaction; it is not developer-authored code (it is harness plumbing).
 */
async function applyPrecondition(
  fixture: Awaited<ReturnType<typeof provisionCase>>,
): Promise<void> {
  const precondition = fixture.loaded.raw.precondition as string | undefined;
  if (precondition !== undefined) {
    await fixture.db.execute(precondition, []);
  }
}
