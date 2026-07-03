/**
 * Runtime `TransactionWriter` behavior (developer-surface remediation).
 *
 * Write-surface guarantees the conformance slice does not exercise directly:
 *
 *  1. FK-safe insert ordering (spec §4, `0612`): buffered inserts flush with a
 *     referenced parent's INSERT before a dependent child's, EVEN WHEN the
 *     developer authored the child `create` first (`combineWrites` does not infer
 *     FK dependencies, so the runtime must topologically order them itself).
 *  2. Plain `update` on a NON-versioned entity applies the WHOLE assignment array
 *     (spec §4) — `update <t> set c1 = ?, c2 = ? where pk = ?`.
 *  3. VERSIONED `update` (M10, ADR 0029): the version is framework-owned — a prior
 *     in-transaction find records the OBSERVED version, and a later keyed update
 *     advances it (both modes) and gates on it (optimistic mode). An unobserved row
 *     read-before-writes; a no-op `set` issues no DML; a 0-row optimistic gate is a
 *     conflict. In `locking` mode the read takes the `for share of t0` suffix.
 *
 * The runtime is built through the real `createParallax` factory with a stub
 * `ParallaxDatabase` that records the compiled SQL + binds and implements the
 * optional `transaction(body)` port (running the body against the same recording
 * stub), so the write path is exercised end to end the way the barrel drives it.
 */
import { loadCase } from "@parallax/conformance";
import { describe, expect, it } from "vitest";
import {
  createParallax,
  NavigationPath,
  type ParallaxDatabase,
  ParallaxOptimisticLockError,
  ParallaxReadBeforeWriteError,
  type ParallaxRow,
  Predicate,
} from "../src/index.js";

/** A recorded statement: the compiled SQL and its ordered binds. */
interface RecordedQuery {
  readonly sql: string;
  readonly binds: readonly unknown[];
}

/**
 * A stub database port that records every executed statement. A SELECT returns the
 * canned `selectRows`; a write (a statement ending `returning 1`) returns an array
 * whose length is the affected-row count (`updateAffected`, defaulting to the
 * select-row count) so a versioned update can be steered to success (1) or conflict
 * (0). It implements the optional `transaction(body)` port by running the body
 * against the same recording stub (commit == the body resolving).
 */
class StubDatabase implements ParallaxDatabase {
  readonly queries: RecordedQuery[] = [];
  private updateAffected: number | undefined;

  constructor(private rows: readonly ParallaxRow[] = []) {}

  setRows(rows: readonly ParallaxRow[]): void {
    this.rows = rows;
  }

  /** Force the affected-row count a write reports (else the select-row count). */
  setUpdateAffected(count: number): void {
    this.updateAffected = count;
  }

  execute(sql: string, binds: readonly unknown[]): Promise<readonly ParallaxRow[]> {
    this.queries.push({ sql, binds });
    if (/returning 1$/.test(sql)) {
      const count = this.updateAffected ?? this.rows.length;
      return Promise.resolve(Array.from({ length: count }, () => ({}) as ParallaxRow));
    }
    return Promise.resolve(this.rows);
  }

  transaction<T>(body: (tx: ParallaxDatabase) => Promise<T>): Promise<T> {
    return body(this);
  }
}

/** The orders descriptor (`Order` / `OrderItem`, the `0612` FK-ordering model). */
const ORDERS = loadCase("core/compatibility/cases/0612-fk-insert-ordering.yaml").descriptor;

/** The non-versioned `Wallet` descriptor (two updatable plain columns owner/balance). */
const WALLET = loadCase("core/compatibility/cases/0604-batched-write.yaml").descriptor;

/** The versioned `Account` descriptor (carries the optimistic-lock `version` column). */
const ACCOUNT = loadCase(
  "core/compatibility/cases/0611-versioned-update-locking-mode.yaml",
).descriptor;

/** A physical Account row the stub returns for an in-transaction find (version 1). */
const ACCOUNT_ROW: ParallaxRow = { id: 2, owner: "Linus", balance: "250.00", version: 1 };

/**
 * A synthetic VERSIONED root (`Vault`) that carries a to-many relationship
 * (`entries`) to a VERSIONED child (`VaultEntry`), so a `find(pred, { includes:
 * [Vault.entries] })` compiles to a DEEP FETCH whose root AND included child are
 * both versioned. The corpus versioned model (`Account`) declares no relationship
 * and is never a relationship target, so this synthetic model is the only way to
 * exercise a deep-fetch read of a versioned root (and a versioned included child) —
 * the M8 lock + M10 observed-version recording the flat path already has, applied to
 * every fetched level.
 */
const VAULT_DESCRIPTOR = {
  entities: [
    {
      name: "Vault",
      namespace: "parallax.test",
      table: "vault",
      mutability: "transactional",
      temporal: "non-temporal",
      attributes: [
        { name: "id", type: "int64", column: "id", primaryKey: true, pkGenerator: "none" },
        { name: "owner", type: "string", column: "owner", maxLength: 64 },
        { name: "balance", type: "decimal(18,2)", column: "balance" },
        { name: "version", type: "int32", column: "version", optimisticLocking: true },
      ],
      relationships: [
        {
          name: "entries",
          relatedEntity: "VaultEntry",
          cardinality: "one-to-many",
          join: "this.id = VaultEntry.vaultId",
          reverseName: "vault",
          dependent: true,
          foreignKey: "vault_id",
        },
      ],
      indices: [{ name: "vault_pk", attributes: ["id"], unique: true }],
    },
    {
      name: "VaultEntry",
      namespace: "parallax.test",
      table: "vault_entry",
      mutability: "transactional",
      temporal: "non-temporal",
      attributes: [
        { name: "id", type: "int64", column: "id", primaryKey: true, pkGenerator: "none" },
        { name: "vaultId", type: "int64", column: "vault_id" },
        { name: "memo", type: "string", column: "memo", maxLength: 64 },
        { name: "version", type: "int32", column: "version", optimisticLocking: true },
      ],
      relationships: [
        {
          name: "vault",
          relatedEntity: "Vault",
          cardinality: "many-to-one",
          join: "this.vaultId = Vault.id",
          reverseName: "entries",
          foreignKey: "vault_id",
        },
      ],
      indices: [{ name: "vault_entry_pk", attributes: ["id"], unique: true }],
    },
  ],
};

/** A physical Vault row the stub returns for the deep-fetch ROOT read (version 1). */
const VAULT_ROW: ParallaxRow = { id: 2, owner: "Vera", balance: "250.00", version: 1 };

/** The `Vault.entries` include path — makes a `find` a deep fetch rooted at Vault. */
const VAULT_ENTRIES = new NavigationPath(["Vault.entries"]);

/** A pk-equality predicate on `Vault.id`. */
const vaultPk = (id: number): Predicate => new Predicate({ eq: { attr: "Vault.id", value: id } });

/** A pk-equality predicate on `Account.id`. */
const accountPk = (id: number): Predicate =>
  new Predicate({ eq: { attr: "Account.id", value: id } });

/** The index of the first recorded statement whose SQL contains `needle`. */
function indexOf(queries: readonly RecordedQuery[], needle: string): number {
  return queries.findIndex((q) => q.sql.includes(needle));
}

describe("TransactionWriter FK-safe insert ordering (spec §4, 0612)", () => {
  it("orders a parent INSERT before a child even when the child was created first", async () => {
    const db = new StubDatabase([]);
    const px = createParallax({ descriptor: ORDERS, database: db });

    await px.transaction(async (tx) => {
      // Author the CHILD before the PARENT — the failing order the bug preserves.
      await tx.entity("OrderItem").create({ id: 200, orderId: 100, sku: "X-1", quantity: 3 });
      await tx.entity("Order").create({
        id: 100,
        name: "Hopper",
        sku: "X-1",
        qty: 1,
        price: 9.99,
        active: true,
        orderedOn: "2024-07-01",
      });
    });

    const parentAt = indexOf(db.queries, "insert into orders");
    const childAt = indexOf(db.queries, "insert into order_item");
    expect(parentAt).toBeGreaterThanOrEqual(0);
    expect(childAt).toBeGreaterThanOrEqual(0);
    // The referenced parent's INSERT must precede the dependent child's.
    expect(parentAt).toBeLessThan(childAt);
  });

  it("keeps a parent-first author order unchanged (parent before child)", async () => {
    const db = new StubDatabase([]);
    const px = createParallax({ descriptor: ORDERS, database: db });

    await px.transaction(async (tx) => {
      await tx.entity("Order").create({
        id: 100,
        name: "Hopper",
        sku: "X-1",
        qty: 1,
        price: 9.99,
        active: true,
        orderedOn: "2024-07-01",
      });
      await tx.entity("OrderItem").create({ id: 200, orderId: 100, sku: "X-1", quantity: 3 });
    });

    const parentAt = indexOf(db.queries, "insert into orders");
    const childAt = indexOf(db.queries, "insert into order_item");
    expect(parentAt).toBeGreaterThanOrEqual(0);
    expect(childAt).toBeGreaterThanOrEqual(0);
    expect(parentAt).toBeLessThan(childAt);
  });
});

describe("TransactionWriter plain update applies every assignment (spec §4)", () => {
  it("sets ALL columns in a multi-assignment plain update and binds values then pk", async () => {
    const db = new StubDatabase([]);
    const px = createParallax({ descriptor: WALLET, database: db });

    // A plain (non-versioned Wallet) update of TWO columns.
    await px.transaction(async (tx) => {
      await tx.entity("Wallet").update(new Predicate({ eq: { attr: "Wallet.id", value: 10 } }), {
        set: [
          { attr: "owner", value: "Mira" },
          { attr: "balance", value: 500 },
        ],
      });
    });

    const update = db.queries.find((q) => q.sql.includes("update wallet"));
    expect(update).toBeDefined();
    const { sql, binds } = update as RecordedQuery;
    // BOTH columns are set (the bug drops everything after the first assignment).
    expect(sql).toContain("set owner = ?, balance = ?");
    expect(sql).toContain("where id = ?");
    // Bind order: each assignment value (wire form) in declaration order, then the pk.
    expect(binds).toEqual(["Mira", 500, 10]);
  });

  it("is a no-op for an empty assignment set", async () => {
    const db = new StubDatabase([]);
    const px = createParallax({ descriptor: WALLET, database: db });

    let result: { affectedRows: number } | undefined;
    await px.transaction(async (tx) => {
      result = await tx
        .entity("Wallet")
        .update(new Predicate({ eq: { attr: "Wallet.id", value: 10 } }), { set: [] });
    });

    expect(result).toEqual({ affectedRows: 0 });
    expect(db.queries.some((q) => q.sql.includes("update wallet"))).toBe(false);
  });
});

describe("TransactionWriter versioned update (M10 framework-owned versions)", () => {
  it("locking mode: an observed row advances the version WITHOUT a gate, and the read locks", async () => {
    const db = new StubDatabase([ACCOUNT_ROW]);
    const px = createParallax({ descriptor: ACCOUNT, database: db });

    const result = await px.transaction(async (tx) => {
      const accounts = tx.entity("Account");
      // A prior in-transaction find observes version 1 (and takes the shared lock).
      await accounts.find(accountPk(2)).single();
      return accounts.update(accountPk(2), { set: [{ attr: "balance", value: "500.00" }] });
    });

    // The locking-mode read appends the M8 shared-row-lock suffix (0603).
    const read = db.queries.find((q) => q.sql.startsWith("select"));
    expect(read?.sql.endsWith("for share of t0")).toBe(true);
    // The versioned update advances the version (observed 1 -> 2) with NO gate.
    const update = db.queries.find((q) => q.sql.includes("update account"));
    expect(update?.sql).toContain("set balance = ?, version = ? where id = ?");
    expect(update?.sql).not.toContain("and version = ?");
    expect(update?.binds).toEqual(["500.00", 2, 2]);
    expect(result.affectedRows).toBe(1);
  });

  it("optimistic mode: the read takes NO lock and the update GATES on the observed version", async () => {
    const db = new StubDatabase([ACCOUNT_ROW]);
    const px = createParallax({ descriptor: ACCOUNT, database: db });

    const result = await px.transaction(
      async (tx) => {
        const accounts = tx.entity("Account");
        await accounts.find(accountPk(2)).single(); // observes version 1, no lock
        return accounts.update(accountPk(2), { set: [{ attr: "balance", value: "500.00" }] });
      },
      { concurrency: "optimistic" },
    );

    const read = db.queries.find((q) => q.sql.startsWith("select"));
    expect(read?.sql.includes("for share")).toBe(false);
    const update = db.queries.find((q) => q.sql.includes("update account"));
    // The gated form: advance the version AND gate on the observed one.
    expect(update?.sql).toContain("set balance = ?, version = ? where id = ? and version = ?");
    expect(update?.binds).toEqual(["500.00", 2, 2, 1]);
    expect(result.affectedRows).toBe(1);
  });

  it("read-before-write: updating an UNOBSERVED versioned row throws", async () => {
    const db = new StubDatabase([ACCOUNT_ROW]);
    const px = createParallax({ descriptor: ACCOUNT, database: db });

    await expect(
      px.transaction(async (tx) => {
        // No prior find — the version was never observed.
        return tx.entity("Account").update(accountPk(2), {
          set: [{ attr: "balance", value: "500.00" }],
        });
      }),
    ).rejects.toBeInstanceOf(ParallaxReadBeforeWriteError);
    // No UPDATE was issued (the read-before-write short-circuits).
    expect(db.queries.some((q) => q.sql.includes("update account"))).toBe(false);
  });

  it("no-op: a versioned update whose set changes no attribute issues no DML", async () => {
    const db = new StubDatabase([ACCOUNT_ROW]);
    const px = createParallax({ descriptor: ACCOUNT, database: db });

    let result: { affectedRows: number } | undefined;
    await px.transaction(async (tx) => {
      const accounts = tx.entity("Account");
      await accounts.find(accountPk(2)).single();
      result = await accounts.update(accountPk(2), { set: [] });
    });

    expect(result).toEqual({ affectedRows: 0 });
    expect(db.queries.some((q) => q.sql.includes("update account"))).toBe(false);
  });

  it("optimistic conflict: a 0-row gated update throws ParallaxOptimisticLockError", async () => {
    const db = new StubDatabase([ACCOUNT_ROW]);
    db.setUpdateAffected(0); // the gate matches no row — a concurrent writer advanced it
    const px = createParallax({ descriptor: ACCOUNT, database: db });

    await expect(
      px.transaction(
        async (tx) => {
          const accounts = tx.entity("Account");
          await accounts.find(accountPk(2)).single();
          return accounts.update(accountPk(2), { set: [{ attr: "balance", value: "500.00" }] });
        },
        { concurrency: "optimistic" },
      ),
    ).rejects.toBeInstanceOf(ParallaxOptimisticLockError);
  });
});

describe("deep-fetch in-transaction read carries the M8/M10 read context", () => {
  it("locking mode: a deep-fetch root read locks and records the observed version (no read-before-write)", async () => {
    const db = new StubDatabase([{ ...VAULT_ROW }]);
    const px = createParallax({ descriptor: VAULT_DESCRIPTOR, database: db });

    // A deep-fetch find of the versioned root, THEN an update of that same root.
    // Before the read-context wiring, the deep-fetch read populated no observed
    // version, so this update threw ParallaxReadBeforeWriteError.
    const result = await px.transaction(async (tx) => {
      const vaults = tx.entity("Vault");
      await vaults.find(vaultPk(2), { includes: [VAULT_ENTRIES] }).toArray();
      return vaults.update(vaultPk(2), { set: [{ attr: "balance", value: "500.00" }] });
    });

    // (a) the ROOT deep-fetch read took the M8 shared row lock (0603), like a flat read.
    const rootRead = db.queries.find(
      (q) => q.sql.startsWith("select") && q.sql.includes("from vault t0"),
    );
    expect(rootRead?.sql.endsWith("for share of t0")).toBe(true);
    // (b) the CHILD level read is an in-transaction read too, so it takes the SAME M8
    //     shared lock (a concurrent writer cannot mutate an included row out from
    //     under a later read-then-write) — every fetched level participates.
    const childRead = db.queries.find((q) => q.sql.includes("from vault_entry"));
    expect(childRead).toBeDefined();
    expect(childRead?.sql.endsWith("for share of t0")).toBe(true);
    // (c) the versioned update advanced the OBSERVED version (1 -> 2), ungated, applied.
    const update = db.queries.find((q) => q.sql.includes("update vault "));
    expect(update?.sql).toContain("set balance = ?, version = ? where id = ?");
    expect(update?.sql).not.toContain("and version = ?");
    expect(update?.binds).toEqual(["500.00", 2, 2]);
    expect(result.affectedRows).toBe(1);
  });

  it("optimistic mode: a deep-fetch root read records the observed version the gate binds, and takes no lock", async () => {
    const db = new StubDatabase([{ ...VAULT_ROW }]);
    const px = createParallax({ descriptor: VAULT_DESCRIPTOR, database: db });

    const result = await px.transaction(
      async (tx) => {
        const vaults = tx.entity("Vault");
        await vaults.find(vaultPk(2), { includes: [VAULT_ENTRIES] }).toArray();
        return vaults.update(vaultPk(2), { set: [{ attr: "balance", value: "500.00" }] });
      },
      { concurrency: "optimistic" },
    );

    // Optimistic reads take NO lock, even through a deep fetch.
    const rootRead = db.queries.find(
      (q) => q.sql.startsWith("select") && q.sql.includes("from vault t0"),
    );
    expect(rootRead?.sql.includes("for share")).toBe(false);
    // The gated update binds the observed version (1) the deep-fetch read recorded.
    const update = db.queries.find((q) => q.sql.includes("update vault "));
    expect(update?.sql).toContain("set balance = ?, version = ? where id = ? and version = ?");
    expect(update?.binds).toEqual(["500.00", 2, 2, 1]);
    expect(result.affectedRows).toBe(1);
  });

  // A single stub row that serves as BOTH the Vault root row and the VaultEntry child
  // row: its `vault_id` equals the root `id`, so the fetched child attaches to the root
  // and is materialized (only attached children are recorded).
  const NESTED_ROW: ParallaxRow = {
    id: 2,
    owner: "Vera",
    balance: "250.00",
    version: 1,
    vault_id: 2,
    memo: "note",
  };
  const vaultEntryPk = (id: number): Predicate =>
    new Predicate({ eq: { attr: "VaultEntry.id", value: id } });

  it("locking mode: records an included versioned CHILD's version, so a later child update advances it (no read-before-write)", async () => {
    const db = new StubDatabase([{ ...NESTED_ROW }]);
    const px = createParallax({ descriptor: VAULT_DESCRIPTOR, database: db });

    // Deep-fetch the versioned root WITH its versioned child, THEN update the CHILD by
    // its own PK. Before child-level observed recording, the child version was never
    // observed, so this threw ParallaxReadBeforeWriteError.
    const result = await px.transaction(async (tx) => {
      await tx
        .entity("Vault")
        .find(vaultPk(2), { includes: [VAULT_ENTRIES] })
        .toArray();
      return tx.entity("VaultEntry").update(vaultEntryPk(2), {
        set: [{ attr: "memo", value: "changed" }],
      });
    });

    // The child update advanced the OBSERVED child version (1 -> 2), ungated (locking).
    const update = db.queries.find((q) => q.sql.includes("update vault_entry"));
    expect(update?.sql).toContain("set memo = ?, version = ? where id = ?");
    expect(update?.sql).not.toContain("and version = ?");
    expect(update?.binds).toEqual(["changed", 2, 2]);
    expect(result.affectedRows).toBe(1);
  });

  it("optimistic mode: an included versioned CHILD's update GATES on the observed child version", async () => {
    const db = new StubDatabase([{ ...NESTED_ROW }]);
    const px = createParallax({ descriptor: VAULT_DESCRIPTOR, database: db });

    const result = await px.transaction(
      async (tx) => {
        await tx
          .entity("Vault")
          .find(vaultPk(2), { includes: [VAULT_ENTRIES] })
          .toArray();
        return tx.entity("VaultEntry").update(vaultEntryPk(2), {
          set: [{ attr: "memo", value: "changed" }],
        });
      },
      { concurrency: "optimistic" },
    );

    // The gated child update binds the observed child version (1) the deep fetch recorded.
    const update = db.queries.find((q) => q.sql.includes("update vault_entry"));
    expect(update?.sql).toContain("set memo = ?, version = ? where id = ? and version = ?");
    expect(update?.binds).toEqual(["changed", 2, 2, 1]);
    expect(result.affectedRows).toBe(1);
  });
});

describe("in-transaction projection/aggregation read omits the lock (never throws)", () => {
  it("locking mode: a `distinct` read proceeds UNLOCKED and returns rows (no throw, no `for share`)", async () => {
    const db = new StubDatabase([ACCOUNT_ROW]);
    const px = createParallax({ descriptor: ACCOUNT, database: db });

    // A `distinct` projection has no base row to lock, so `for share` is illegal on
    // it — the dialect OMITS the lock and the read proceeds (the D2 reversal; ADR
    // 0030). It is never rejected, even in a locking transaction.
    const rows = await px.transaction(async (tx) =>
      tx.entity("Account").find(accountPk(2), { distinct: true }).toArray(),
    );
    expect(rows.length).toBeGreaterThan(0);
    const read = db.queries.find((q) => q.sql.includes("select distinct"));
    expect(read).toBeDefined();
    // No lock was appended (nothing to protect) — and no illegal SQL was emitted.
    expect(read?.sql.includes("for share")).toBe(false);
  });

  it("optimistic mode: a `distinct` read is fine — no lock is appended", async () => {
    const db = new StubDatabase([ACCOUNT_ROW]);
    const px = createParallax({ descriptor: ACCOUNT, database: db });

    await px.transaction(
      async (tx) => tx.entity("Account").find(accountPk(2), { distinct: true }).toArray(),
      { concurrency: "optimistic" },
    );
    const read = db.queries.find((q) => q.sql.includes("select distinct"));
    expect(read).toBeDefined();
    expect(read?.sql.includes("for share")).toBe(false);
  });
});
