/**
 * Bounded automatic retry loop (m-auto-retry/m-opt-lock, core ADR 0008 / ts ADR 0026) — Docker-free
 * mechanics over a controlled `ParallaxDatabase` stub.
 *
 * These pin the retry-loop branches the `api-conformance`-lane boundary cases
 * (`m-opt-lock-009`-`m-unit-work-004`) declare, without a real database: each `px.transaction` attempt
 * opens a fresh `transaction(body)` on the stub, and the stub is configured to
 * inject a per-attempt fault (a `ParallaxTransientError`) or a per-attempt
 * affected-row count (to steer the optimistic gate to conflict / success) through
 * `executeWrite`. The fault-injection-at-the-port shape mirrors the decorator the
 * real API Conformance Suite wraps around the shipped adapter.
 *
 *  - a transient (`ParallaxTransientError.retriable`) is auto-retried by default,
 *    with or without `retryOptimisticConflicts` — the flag has no bearing on it;
 *  - an optimistic conflict is retried ONLY with `retryOptimisticConflicts: true`,
 *    else it surfaces as `ParallaxOptimisticLockError`;
 *  - `retries: 0` disables the loop (even a transient surfaces);
 *  - an exhausted bound surfaces the failure, annotated with the attempt count;
 *  - a body that throws aborts — `px.transaction` rejects and yields no value.
 */
import { loadCase } from "@parallax/conformance";
import { ParallaxTransientError } from "@parallax/db";
import { postgresDialect } from "@parallax/dialect";
import { describe, expect, it } from "vitest";
import {
  createParallax,
  type ParallaxDatabase,
  ParallaxOptimisticLockError,
  type ParallaxRow,
  Predicate,
  type TransactionOptions,
} from "../src/index.js";

/** The versioned `Account` descriptor (carries the optimistic-lock `version` column). */
const ACCOUNT = loadCase(
  "core/compatibility/cases/m-opt-lock-002-versioned-update-locking-mode.yaml",
).descriptor;

/** A physical Account row the stub returns for an in-transaction find (version 1). */
const ACCOUNT_ROW: ParallaxRow = { id: 2, owner: "Linus", balance: "250.00", version: 1 };

const accountPk = (id: number): Predicate =>
  new Predicate({ eq: { attr: "Account.id", value: id } });

/** The per-attempt behavior a controlled transaction attempt applies to its write. */
interface AttemptPlan {
  /** An error the FIRST write of this attempt throws (a transient / injected fault). */
  readonly fault?: Error;
  /** The affected-row count a write reports (steers the optimistic gate: 0 conflict, 1 success). */
  readonly affected?: number;
}

/**
 * A controlled port stub: `transaction(body)` opens a fresh bound attempt (counting
 * attempts), and each attempt applies its own `AttemptPlan` (a per-attempt injected
 * fault + affected-row count). A SELECT always returns the account row; a write
 * throws the attempt's fault once, else reports its affected count.
 */
class ControlledDatabase implements ParallaxDatabase {
  attempts = 0;

  constructor(private readonly plan: (attempt: number) => AttemptPlan) {}

  execute(_sql: string, _binds: readonly unknown[]): Promise<readonly ParallaxRow[]> {
    return Promise.resolve([ACCOUNT_ROW]);
  }

  executeWrite(_sql: string, _binds: readonly unknown[]): Promise<number> {
    return Promise.resolve(1);
  }

  transaction<T>(body: (tx: ParallaxDatabase) => Promise<T>): Promise<T> {
    const attempt = this.attempts++;
    return body(new BoundAttempt(this.plan(attempt)));
  }
}

/** One transaction attempt's bound connection: a SELECT reads the row, a write applies the plan. */
class BoundAttempt implements ParallaxDatabase {
  private threwFault = false;

  constructor(private readonly plan: AttemptPlan) {}

  execute(sql: string, _binds: readonly unknown[]): Promise<readonly ParallaxRow[]> {
    void sql;
    return Promise.resolve([ACCOUNT_ROW]);
  }

  executeWrite(_sql: string, _binds: readonly unknown[]): Promise<number> {
    if (this.plan.fault && !this.threwFault) {
      this.threwFault = true;
      return Promise.reject(this.plan.fault);
    }
    return Promise.resolve(this.plan.affected ?? 1);
  }
}

/** A retriable transient (the `deadlock` category — a serialization failure folds in). */
const transient = (): ParallaxTransientError => new ParallaxTransientError("deadlock", true);

/** Drive a versioned find-then-update unit of work (the shape every boundary case uses). */
async function findThenUpdate(
  db: ControlledDatabase,
  options: TransactionOptions,
): Promise<{ affectedRows: number }> {
  const px = createParallax({ descriptor: ACCOUNT, database: db, dialect: postgresDialect });
  return px.transaction(async (tx) => {
    const accounts = tx.entity("Account");
    await accounts.find(accountPk(2)).single(); // observe the version
    return accounts.update(accountPk(2), { set: [{ attr: "balance", value: "500.00" }] });
  }, options);
}

describe("bounded automatic retry (m-auto-retry/m-opt-lock)", () => {
  it("m-auto-retry-001: an injected transient is auto-retried by default (flag unset) and commits", async () => {
    const db = new ControlledDatabase((attempt) =>
      attempt === 0 ? { fault: transient() } : { affected: 1 },
    );
    const result = await findThenUpdate(db, { concurrency: "optimistic" });
    expect(result.affectedRows).toBe(1);
    expect(db.attempts).toBe(2); // the body re-executed once
  });

  it("m-auto-retry-002: a transient is auto-retried identically with the flag SET (no bearing on transients)", async () => {
    const db = new ControlledDatabase((attempt) =>
      attempt === 0 ? { fault: transient() } : { affected: 1 },
    );
    const result = await findThenUpdate(db, {
      concurrency: "optimistic",
      retryOptimisticConflicts: true,
    });
    expect(result.affectedRows).toBe(1);
    expect(db.attempts).toBe(2);
  });

  it("m-opt-lock-010: an optimistic conflict is NOT retried without the opt-in — it surfaces", async () => {
    const db = new ControlledDatabase(() => ({ affected: 0 })); // every attempt conflicts
    await expect(findThenUpdate(db, { concurrency: "optimistic" })).rejects.toBeInstanceOf(
      ParallaxOptimisticLockError,
    );
    expect(db.attempts).toBe(1); // surfaced after ONE attempt, not retried
  });

  it("m-opt-lock-011/m-opt-lock-009: an optimistic conflict IS auto-retried with the opt-in, re-reads, and commits", async () => {
    const db = new ControlledDatabase((attempt) =>
      attempt === 0 ? { affected: 0 } : { affected: 1 },
    );
    const result = await findThenUpdate(db, {
      concurrency: "optimistic",
      retryOptimisticConflicts: true,
    });
    expect(result.affectedRows).toBe(1);
    expect(db.attempts).toBe(2); // the body re-executed and re-read
  });

  it("m-auto-retry-003: the conflict-retry flag is inert in locking mode (the update commits)", async () => {
    const db = new ControlledDatabase(() => ({ affected: 1 }));
    const result = await findThenUpdate(db, {
      concurrency: "locking",
      retryOptimisticConflicts: true,
    });
    expect(result.affectedRows).toBe(1);
    expect(db.attempts).toBe(1);
  });

  it("m-auto-retry-004: retries: 0 disables the loop — even a transient surfaces", async () => {
    const db = new ControlledDatabase(() => ({ fault: transient() }));
    await expect(
      findThenUpdate(db, { concurrency: "optimistic", retries: 0 }),
    ).rejects.toBeInstanceOf(ParallaxTransientError);
    expect(db.attempts).toBe(1);
  });

  it("m-auto-retry-005: a persistent transient surfaces after the bound is exhausted, annotated", async () => {
    const db = new ControlledDatabase(() => ({ fault: transient() })); // fails every attempt
    await expect(
      findThenUpdate(db, { concurrency: "optimistic", retries: 2 }),
    ).rejects.toMatchObject({ message: expect.stringContaining("surfaced after 3 attempts") });
    expect(db.attempts).toBe(3); // 1 initial + 2 retries
  });

  it("m-unit-work-004: a body that throws aborts — px.transaction rejects and yields no value", async () => {
    const db = new ControlledDatabase(() => ({ affected: 1 }));
    const px = createParallax({ descriptor: ACCOUNT, database: db, dialect: postgresDialect });
    const sentinel = new Error("domain rule violated");
    await expect(
      px.transaction(async (tx) => {
        await tx.entity("Account").find(accountPk(2)).single();
        throw sentinel;
      }),
    ).rejects.toBe(sentinel);
    expect(db.attempts).toBe(1); // an application throw is not retriable
  });
});
