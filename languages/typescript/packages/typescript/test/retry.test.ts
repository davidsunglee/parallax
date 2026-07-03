/**
 * Bounded automatic retry loop (M8/M10, ADR 0031 / TS ADR 0065) — Docker-free
 * mechanics over a controlled `ParallaxDatabase` stub.
 *
 * These pin the retry-loop branches the `api-conformance`-lane boundary cases
 * (`0710`-`0718`) declare, without a real database: each `px.transaction` attempt
 * opens a fresh `transaction(body)` on the stub, and the stub is configured to
 * inject a per-attempt fault (a `ParallaxTransientError`) or a per-attempt
 * affected-row count (to steer the optimistic gate to conflict / success). The
 * fault-injection-at-the-port shape mirrors the decorator the real API Conformance
 * Suite wraps around the shipped adapter.
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
  "core/compatibility/cases/0611-versioned-update-locking-mode.yaml",
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
 * (`returning 1`) throws the attempt's fault once, else reports its affected count.
 */
class ControlledDatabase implements ParallaxDatabase {
  attempts = 0;

  constructor(private readonly plan: (attempt: number) => AttemptPlan) {}

  execute(_sql: string, _binds: readonly unknown[]): Promise<readonly ParallaxRow[]> {
    return Promise.resolve([ACCOUNT_ROW]);
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
    if (/returning 1$/.test(sql)) {
      if (this.plan.fault && !this.threwFault) {
        this.threwFault = true;
        return Promise.reject(this.plan.fault);
      }
      const count = this.plan.affected ?? 1;
      return Promise.resolve(Array.from({ length: count }, () => ({}) as ParallaxRow));
    }
    return Promise.resolve([ACCOUNT_ROW]);
  }
}

/** A retriable transient (the `deadlock` category — a serialization failure folds in). */
const transient = (): ParallaxTransientError => new ParallaxTransientError("deadlock", true);

/** Drive a versioned find-then-update unit of work (the shape every boundary case uses). */
async function findThenUpdate(
  db: ControlledDatabase,
  options: TransactionOptions,
): Promise<{ affectedRows: number }> {
  const px = createParallax({ descriptor: ACCOUNT, database: db });
  return px.transaction(async (tx) => {
    const accounts = tx.entity("Account");
    await accounts.find(accountPk(2)).single(); // observe the version
    return accounts.update(accountPk(2), { set: [{ attr: "balance", value: "500.00" }] });
  }, options);
}

describe("bounded automatic retry (M8/M10)", () => {
  it("0712: an injected transient is auto-retried by default (flag unset) and commits", async () => {
    const db = new ControlledDatabase((attempt) =>
      attempt === 0 ? { fault: transient() } : { affected: 1 },
    );
    const result = await findThenUpdate(db, { concurrency: "optimistic" });
    expect(result.affectedRows).toBe(1);
    expect(db.attempts).toBe(2); // the body re-executed once
  });

  it("0713: a transient is auto-retried identically with the flag SET (no bearing on transients)", async () => {
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

  it("0711: an optimistic conflict is NOT retried without the opt-in — it surfaces", async () => {
    const db = new ControlledDatabase(() => ({ affected: 0 })); // every attempt conflicts
    await expect(findThenUpdate(db, { concurrency: "optimistic" })).rejects.toBeInstanceOf(
      ParallaxOptimisticLockError,
    );
    expect(db.attempts).toBe(1); // surfaced after ONE attempt, not retried
  });

  it("0714/0710: an optimistic conflict IS auto-retried with the opt-in, re-reads, and commits", async () => {
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

  it("0715: the conflict-retry flag is inert in locking mode (the update commits)", async () => {
    const db = new ControlledDatabase(() => ({ affected: 1 }));
    const result = await findThenUpdate(db, {
      concurrency: "locking",
      retryOptimisticConflicts: true,
    });
    expect(result.affectedRows).toBe(1);
    expect(db.attempts).toBe(1);
  });

  it("0716: retries: 0 disables the loop — even a transient surfaces", async () => {
    const db = new ControlledDatabase(() => ({ fault: transient() }));
    await expect(
      findThenUpdate(db, { concurrency: "optimistic", retries: 0 }),
    ).rejects.toBeInstanceOf(ParallaxTransientError);
    expect(db.attempts).toBe(1);
  });

  it("0717: a persistent transient surfaces after the bound is exhausted, annotated", async () => {
    const db = new ControlledDatabase(() => ({ fault: transient() })); // fails every attempt
    await expect(
      findThenUpdate(db, { concurrency: "optimistic", retries: 2 }),
    ).rejects.toMatchObject({ message: expect.stringContaining("surfaced after 3 attempts") });
    expect(db.attempts).toBe(3); // 1 initial + 2 retries
  });

  it("0718: a body that throws aborts — px.transaction rejects and yields no value", async () => {
    const db = new ControlledDatabase(() => ({ affected: 1 }));
    const px = createParallax({ descriptor: ACCOUNT, database: db });
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
