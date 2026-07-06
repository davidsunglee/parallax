/**
 * `@parallax/dialect` unit tests (Docker-free, pure) — in-transaction read-lock
 * **application** (m-read-lock automatic read-lock correctness, owned by the m-dialect seam;
 * delta `09` D2/D3, core ADR 0012).
 *
 * The dialect owns the whole lock decision — whether, where, and how it attaches:
 *
 *  - a `locking`-mode **object find** gets `for share of t0` appended after every
 *    other clause (the `m-read-lock-001` regression proof that object finds still lock);
 *  - a `locking`-mode **projection / aggregation** (the `select distinct` shape) is
 *    returned **unchanged** — no suffix, and crucially **no throw** (the reversal of
 *    the former `ParallaxUnlockableReadError`: no base row to lock, unmanaged data
 *    per core ADR 0002, so it proceeds unlocked);
 *  - a **non-`locking`** read (optimistic mode / out-of-transaction) is unchanged.
 */
import { applyReadLock } from "@parallax/dialect";
import { describe, expect, it } from "vitest";

describe("applyReadLock (m-read-lock read-lock application, m-read-lock-001)", () => {
  it("appends the Postgres shared-row-lock suffix to a locking object find", () => {
    const read = "select t0.id, t0.owner, t0.balance from account t0 where t0.id = ?";
    expect(applyReadLock(read, { locking: true, projection: false })).toBe(
      `${read} for share of t0`,
    );
  });

  it("returns a distinct/projection read UNCHANGED — no suffix, no throw", () => {
    // A row lock applies to base rows, so Postgres/MariaDB reject `FOR SHARE` on a
    // DISTINCT result. The dialect OMITS the lock (it proceeds unlocked) rather than
    // erroring — the D2 reversal (core ADR 0012), even in locking mode.
    const distinctRead = "select distinct t0.owner from account t0";
    expect(applyReadLock(distinctRead, { locking: true, projection: true })).toBe(distinctRead);
  });

  it("keys the omit decision on the `projection` flag, not the SQL text", () => {
    // The omit branch trusts the caller-supplied `projection` boolean (the contract
    // flag `compile` derives from whether it emitted `distinct`), NOT a regex over
    // the SQL. So a non-projection read (`projection: false`) still locks even though
    // its column name merely contains "distinct".
    const read = "select t0.distinct_flag from account t0 where t0.id = ?";
    expect(applyReadLock(read, { locking: true, projection: false })).toBe(
      `${read} for share of t0`,
    );
  });

  it("returns any read UNCHANGED when not locking (optimistic / out-of-transaction)", () => {
    const objectRead = "select t0.id from account t0 where t0.id = ?";
    const distinctRead = "select distinct t0.owner from account t0";
    expect(applyReadLock(objectRead, { locking: false, projection: false })).toBe(objectRead);
    expect(applyReadLock(distinctRead, { locking: false, projection: true })).toBe(distinctRead);
  });
});
