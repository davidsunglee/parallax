/**
 * `@parallax/dialect` unit tests (Docker-free, pure) — in-transaction read-lock
 * **application** (M8 automatic read-lock correctness, owned by the M11 seam;
 * delta `09` D2/D3, ADR 0030).
 *
 * The dialect owns the whole lock decision — whether, where, and how it attaches:
 *
 *  - a `locking`-mode **object find** gets `for share of t0` appended after every
 *    other clause (the `0603` regression proof that object finds still lock);
 *  - a `locking`-mode **projection / aggregation** (the `select distinct` shape) is
 *    returned **unchanged** — no suffix, and crucially **no throw** (the reversal of
 *    the former `ParallaxUnlockableReadError`: no base row to lock, unmanaged data
 *    per ADR 0024, so it proceeds unlocked);
 *  - a **non-`locking`** read (optimistic mode / out-of-transaction) is unchanged.
 */
import { applyReadLock } from "@parallax/dialect";
import { describe, expect, it } from "vitest";

describe("applyReadLock (M8 read-lock application, 0603)", () => {
  it("appends the Postgres shared-row-lock suffix to a locking object find", () => {
    const read = "select t0.id, t0.owner, t0.balance from account t0 where t0.id = ?";
    expect(applyReadLock(read, { locking: true })).toBe(`${read} for share of t0`);
  });

  it("returns a distinct/projection read UNCHANGED — no suffix, no throw", () => {
    // A row lock applies to base rows, so Postgres/MariaDB reject `FOR SHARE` on a
    // DISTINCT result. The dialect OMITS the lock (it proceeds unlocked) rather than
    // erroring — the D2 reversal (ADR 0030), even in locking mode.
    const distinctRead = "select distinct t0.owner from account t0";
    expect(applyReadLock(distinctRead, { locking: true })).toBe(distinctRead);
  });

  it("locks an ordinary read whose column name merely contains 'distinct'", () => {
    // The omit branch keys on the `select distinct` projection shape, not a
    // substring, so a plain read projecting a `distinct_flag` column still locks.
    const read = "select t0.distinct_flag from account t0 where t0.id = ?";
    expect(applyReadLock(read, { locking: true })).toBe(`${read} for share of t0`);
  });

  it("returns any read UNCHANGED when not locking (optimistic / out-of-transaction)", () => {
    const objectRead = "select t0.id from account t0 where t0.id = ?";
    const distinctRead = "select distinct t0.owner from account t0";
    expect(applyReadLock(objectRead, { locking: false })).toBe(objectRead);
    expect(applyReadLock(distinctRead, { locking: false })).toBe(distinctRead);
  });
});
