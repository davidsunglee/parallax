/**
 * API Conformance Suite — **boundary** family (Phase 4): the bounded automatic
 * retry loop mechanics (M8/M10, ADR 0031 / TS ADR 0065), driven the way a developer
 * would (`px.transaction(body, { retries, retryOptimisticConflicts })`) over the
 * SHIPPED `@parallax/db-postgres` adapter against `postgres:17`.
 *
 * These cases (`0710`-`0718`, `api-conformance` lane) prove loop branches a single-
 * connection harness cannot provoke — an injected transient auto-retried away, a
 * conflict surfacing without the opt-in, a conflict auto-retried WITH it, the flag's
 * no-op in locking mode, `retries: 0`, bound exhaustion, callback-value-withheld-on-
 * abort. Per the contract carve-out (api-conformance-contract §Required properties
 * 2), fault injection rides a **thin decorator wrapped around the shipped adapter**:
 * it injects the declared fault on a chosen attempt and delegates every other call
 * to the real adapter, so the actual DB work stays on the production path. Real
 * contention is not required — the decorator injects the transient, and a real
 * out-of-band precondition (on the provider's peer connection) makes the optimistic
 * conflict genuine.
 */

import { execFileSync } from "node:child_process";
import { ParallaxDecimal } from "@parallax/core";
import type { ParallaxDatabase, ParallaxRow } from "@parallax/db";
import { ParallaxTransientError } from "@parallax/db";
import { postgresDialect } from "@parallax/dialect";
import { afterAll, beforeAll, expect, describe as group, it } from "vitest";
import { PostgresProvider } from "../../src/conformance/postgres-provider.js";
import {
  AttributeExpression,
  createParallax,
  type Parallax,
  ParallaxOptimisticLockError,
  Predicate,
  type TransactionOptions,
} from "../../src/index.js";
import { provisionCase } from "./_harness.js";
import { BOUNDARY } from "./covered.js";

const attr = (ref: string): AttributeExpression => new AttributeExpression(ref);
const dec = (text: string): ParallaxDecimal => ParallaxDecimal.from(text);
const Account = { id: attr("Account.id"), balance: attr("Account.balance") };
const accountPk = (id: number): Predicate =>
  new Predicate({ eq: { attr: "Account.id", value: id } });

/** The out-of-band concurrent write that makes an optimistic conflict genuine (0703 shape). */
const CONCURRENT_WRITE = "update account set balance = 999.00, version = 2 where id = 2";

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

it("the boundary suite covers exactly the BOUNDARY family", () => {
  const covered = [
    "0710-optimistic-conflict-auto-retry",
    "0711-conflict-surfaces-without-optin",
    "0712-transient-retried-flag-unset",
    "0713-transient-retried-flag-set",
    "0714-conflict-auto-retry-loop",
    "0715-retry-flag-locking-mode",
    "0716-retries-zero-disables-loop",
    "0717-retry-bound-exhausted",
    "0718-callback-value-withheld-on-abort",
  ];
  expect(covered.sort()).toEqual([...BOUNDARY].sort());
});

/**
 * A thin fault-injecting decorator around the shipped adapter (the contract
 * carve-out). It counts `transaction` attempts and, on a bound connection, may (a)
 * run a one-shot side effect before the first write (a real concurrent write on the
 * peer, to make an optimistic conflict genuine) and (b) throw an injected transient
 * on the first write of chosen attempts. Every other call delegates to the real
 * adapter, so the DB work stays on the production path.
 */
class FaultInjectingDatabase implements ParallaxDatabase {
  attempts = 0;

  constructor(
    private readonly base: ParallaxDatabase,
    private readonly opts: {
      readonly transientOnAttempts?: readonly number[];
      readonly beforeWriteOnAttempt?: (attempt: number) => Promise<void>;
    },
  ) {}

  execute(sql: string, binds: readonly unknown[]): Promise<readonly ParallaxRow[]> {
    return this.base.execute(sql, binds);
  }

  transaction<T>(body: (tx: ParallaxDatabase) => Promise<T>): Promise<T> {
    if (this.base.transaction === undefined) {
      throw new Error("the base adapter does not support transactions");
    }
    const attempt = this.attempts++;
    return this.base.transaction((bound) => body(new BoundInjector(bound, attempt, this.opts)));
  }
}

/** One attempt's bound connection: applies the side effect + injected transient, then delegates. */
class BoundInjector implements ParallaxDatabase {
  private handledWrite = false;

  constructor(
    private readonly base: ParallaxDatabase,
    private readonly attempt: number,
    private readonly opts: {
      readonly transientOnAttempts?: readonly number[];
      readonly beforeWriteOnAttempt?: (attempt: number) => Promise<void>;
    },
  ) {}

  async execute(sql: string, binds: readonly unknown[]): Promise<readonly ParallaxRow[]> {
    const isWrite = /returning 1$/.test(sql);
    if (isWrite && !this.handledWrite) {
      this.handledWrite = true;
      await this.opts.beforeWriteOnAttempt?.(this.attempt);
      if (this.opts.transientOnAttempts?.includes(this.attempt)) {
        // A serialization failure surfaces as the portable transient (deadlock
        // category) — exactly what the shipped adapter produces for SQLSTATE 40001.
        throw new ParallaxTransientError("deadlock", true);
      }
    }
    return this.base.execute(sql, binds);
  }
}

/** Build a `px` over the fault-injecting decorator wrapping the provisioned adapter. */
function pxOver(
  fixture: Awaited<ReturnType<typeof provisionCase>>,
  db: ParallaxDatabase,
): Parallax {
  return createParallax({
    database: db,
    descriptor: fixture.loaded.descriptor,
    dialect: postgresDialect,
  });
}

/** Drive the versioned find-then-update unit of work every boundary case uses. */
function findThenUpdate(
  px: Parallax,
  options: TransactionOptions,
): Promise<{ affectedRows: number }> {
  return px.transaction(async (tx) => {
    const accounts = tx.entity("Account");
    await accounts.find(Account.id.eq(2)).single(); // observe the version
    return accounts.update(accountPk(2), { set: [Account.balance.set(dec("500.00"))] });
  }, options);
}

group.skipIf(!HAS_DOCKER)("boundary suite (Testcontainers postgres:17)", () => {
  const BOOT_TIMEOUT = 600_000;
  let provider: PostgresProvider;

  beforeAll(async () => {
    provider = await PostgresProvider.start();
  }, BOOT_TIMEOUT);

  afterAll(async () => {
    await provider?.close();
  });

  it(
    "0710/0714: a conflict is auto-retried WITH the opt-in — the body re-reads and commits",
    async () => {
      const f = await provisionCase(provider, "0714-conflict-auto-retry-loop");
      // A real concurrent write commits before the first attempt's gated UPDATE, so
      // it conflicts; with the opt-in the loop re-executes, re-reads the fresh
      // version, and succeeds — no caller retry code.
      const db = new FaultInjectingDatabase(f.db, {
        beforeWriteOnAttempt: async (attempt) => {
          if (attempt === 0) {
            await provider.peer.execute(CONCURRENT_WRITE, []);
          }
        },
      });
      const px = pxOver(f, db);
      const result = await findThenUpdate(px, {
        concurrency: "optimistic",
        retryOptimisticConflicts: true,
      });
      expect(result.affectedRows).toBe(1);
      expect(db.attempts).toBe(2);
    },
    BOOT_TIMEOUT,
  );

  it(
    "0711: a conflict surfaces WITHOUT the opt-in (one attempt)",
    async () => {
      const f = await provisionCase(provider, "0711-conflict-surfaces-without-optin");
      const db = new FaultInjectingDatabase(f.db, {
        beforeWriteOnAttempt: async (attempt) => {
          if (attempt === 0) {
            await provider.peer.execute(CONCURRENT_WRITE, []);
          }
        },
      });
      const px = pxOver(f, db);
      await expect(findThenUpdate(px, { concurrency: "optimistic" })).rejects.toBeInstanceOf(
        ParallaxOptimisticLockError,
      );
      expect(db.attempts).toBe(1);
    },
    BOOT_TIMEOUT,
  );

  it(
    "0712: an injected transient is auto-retried by default (flag unset) and commits",
    async () => {
      const f = await provisionCase(provider, "0712-transient-retried-flag-unset");
      const db = new FaultInjectingDatabase(f.db, { transientOnAttempts: [0] });
      const px = pxOver(f, db);
      const result = await findThenUpdate(px, { concurrency: "optimistic" });
      expect(result.affectedRows).toBe(1);
      expect(db.attempts).toBe(2);
    },
    BOOT_TIMEOUT,
  );

  it(
    "0713: an injected transient is auto-retried identically WITH the flag set",
    async () => {
      const f = await provisionCase(provider, "0713-transient-retried-flag-set");
      const db = new FaultInjectingDatabase(f.db, { transientOnAttempts: [0] });
      const px = pxOver(f, db);
      const result = await findThenUpdate(px, {
        concurrency: "optimistic",
        retryOptimisticConflicts: true,
      });
      expect(result.affectedRows).toBe(1);
      expect(db.attempts).toBe(2);
    },
    BOOT_TIMEOUT,
  );

  it(
    "0715: the conflict-retry flag is inert in locking mode (the update commits)",
    async () => {
      const f = await provisionCase(provider, "0715-retry-flag-locking-mode");
      const db = new FaultInjectingDatabase(f.db, {});
      const px = pxOver(f, db);
      const result = await findThenUpdate(px, {
        concurrency: "locking",
        retryOptimisticConflicts: true,
      });
      expect(result.affectedRows).toBe(1);
      expect(db.attempts).toBe(1);
    },
    BOOT_TIMEOUT,
  );

  it(
    "0716: retries: 0 disables the loop — even a transient surfaces",
    async () => {
      const f = await provisionCase(provider, "0716-retries-zero-disables-loop");
      const db = new FaultInjectingDatabase(f.db, { transientOnAttempts: [0] });
      const px = pxOver(f, db);
      await expect(
        findThenUpdate(px, { concurrency: "locking", retries: 0 }),
      ).rejects.toBeInstanceOf(ParallaxTransientError);
      expect(db.attempts).toBe(1);
    },
    BOOT_TIMEOUT,
  );

  it(
    "0717: a persistent transient surfaces after the bound is exhausted",
    async () => {
      const f = await provisionCase(provider, "0717-retry-bound-exhausted");
      const db = new FaultInjectingDatabase(f.db, { transientOnAttempts: [0, 1, 2] });
      const px = pxOver(f, db);
      await expect(
        findThenUpdate(px, { concurrency: "locking", retries: 2 }),
      ).rejects.toMatchObject({ message: expect.stringContaining("surfaced after 3 attempts") });
      expect(db.attempts).toBe(3);
    },
    BOOT_TIMEOUT,
  );

  it(
    "0718: a body that throws aborts — px.transaction rejects and yields no value",
    async () => {
      const f = await provisionCase(provider, "0718-callback-value-withheld-on-abort");
      const sentinel = new Error("domain rule violated");
      let returned: unknown = "unset";
      try {
        returned = await f.px.transaction(async (tx) => {
          const accounts = tx.entity("Account");
          await accounts.find(Account.id.eq(2)).single();
          // buffer a write a dependent find observes (forces the RYOW flush) …
          await accounts.update(accountPk(2), { set: [Account.balance.set(dec("777.00"))] });
          await accounts.find(Account.id.eq(2)).single();
          throw sentinel; // … then abort — the callback value is withheld
        });
      } catch (error) {
        expect(error).toBe(sentinel);
      }
      // No value escaped the rejected transaction.
      expect(returned).toBe("unset");
      // The abort discarded the flushed write — the row still carries the fixture
      // value (250), never the aborted 777 (compared numerically, scale-agnostic).
      const after = await f.db.execute("select balance from account where id = 2", []);
      expect(Number(String((after[0] as { balance: unknown }).balance))).toBe(250);
    },
    BOOT_TIMEOUT,
  );
});
