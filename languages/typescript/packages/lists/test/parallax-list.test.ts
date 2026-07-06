/**
 * `ParallaxList<T>` unit tests (Docker-free) — the m-op-list lazy, operation-backed list.
 *
 * The 03xx conformance corpus grades the assembled deep-fetch graph (plain
 * decorated rows), not this developer-facing API, so `ParallaxList` is otherwise
 * unexercised by the run lanes. These tests pin its contract directly: laziness +
 * at-most-once resolution, the `first`/`single` error semantics (ADR-0014), and
 * the identity map (same PK ⇒ same object instance — ADR-0014/ADR-0016).
 */
import {
  ParallaxError,
  ParallaxList,
  ParallaxNotFoundError,
  ParallaxTooManyResultsError,
} from "@parallax/lists";
import { describe, expect, it, vi } from "vitest";

interface Order {
  readonly id: number;
  readonly name: string;
}

/** A resolver that counts its invocations, to assert at-most-once resolution. */
function countingResolver<T>(rows: readonly T[]): {
  resolver: () => Promise<readonly T[]>;
  calls: () => number;
} {
  const spy = vi.fn(async () => rows);
  return { resolver: spy, calls: () => spy.mock.calls.length };
}

describe("ParallaxList — laziness and idempotent resolution", () => {
  it("does not run the resolver until a first async access", () => {
    const { resolver, calls } = countingResolver<Order>([{ id: 1, name: "a" }]);
    // Constructing the list must not touch the backing operation.
    new ParallaxList(resolver);
    expect(calls()).toBe(0);
  });

  it("runs the resolver at most once across repeated accesses", async () => {
    const { resolver, calls } = countingResolver<Order>([{ id: 1, name: "a" }]);
    const list = new ParallaxList(resolver);
    await list.toArray();
    await list.toArray();
    await list.count();
    await list.first();
    expect(calls()).toBe(1);
  });

  it("shares a single in-flight resolution across concurrent callers", async () => {
    const { resolver, calls } = countingResolver<Order>([{ id: 1, name: "a" }]);
    const list = new ParallaxList(resolver);
    // Two accesses started before either settles must share the one promise.
    await Promise.all([list.toArray(), list.count(), list.first()]);
    expect(calls()).toBe(1);
  });

  it("serves a stable array instance on every access", async () => {
    const { resolver } = countingResolver<Order>([{ id: 1, name: "a" }]);
    const list = new ParallaxList(resolver);
    expect(await list.toArray()).toBe(await list.toArray());
  });
});

describe("ParallaxList — first / single semantics (ADR-0014)", () => {
  it("first() returns the head; firstOrNull() mirrors it", async () => {
    const list = new ParallaxList<Order>(async () => [
      { id: 1, name: "a" },
      { id: 2, name: "b" },
    ]);
    expect(await list.first()).toEqual({ id: 1, name: "a" });
    expect(await list.firstOrNull()).toEqual({ id: 1, name: "a" });
  });

  it("first() throws ParallaxNotFoundError when empty; firstOrNull() returns null", async () => {
    const list = new ParallaxList<Order>(async () => []);
    await expect(list.first()).rejects.toBeInstanceOf(ParallaxNotFoundError);
    await expect(list.first()).rejects.toBeInstanceOf(ParallaxError);
    expect(await list.firstOrNull()).toBeNull();
  });

  it("single() returns the one row when exactly one exists", async () => {
    const list = new ParallaxList<Order>(async () => [{ id: 7, name: "solo" }]);
    expect(await list.single()).toEqual({ id: 7, name: "solo" });
    expect(await list.singleOrNull()).toEqual({ id: 7, name: "solo" });
  });

  it("single() throws ParallaxNotFoundError when empty; singleOrNull() returns null", async () => {
    const list = new ParallaxList<Order>(async () => []);
    await expect(list.single()).rejects.toBeInstanceOf(ParallaxNotFoundError);
    expect(await list.singleOrNull()).toBeNull();
  });

  it("single()/singleOrNull() throw ParallaxTooManyResultsError (carrying the count) for >1", async () => {
    const list = new ParallaxList<Order>(async () => [
      { id: 1, name: "a" },
      { id: 2, name: "b" },
      { id: 3, name: "c" },
    ]);
    await expect(list.single()).rejects.toBeInstanceOf(ParallaxTooManyResultsError);
    await expect(list.singleOrNull()).rejects.toBeInstanceOf(ParallaxTooManyResultsError);
    await list.single().catch((error: unknown) => {
      expect(error).toBeInstanceOf(ParallaxTooManyResultsError);
      expect((error as ParallaxTooManyResultsError).count).toBe(3);
      expect((error as ParallaxTooManyResultsError).code).toBe("PARALLAX_TOO_MANY_RESULTS");
    });
  });
});

describe("ParallaxList — count / isEmpty / iteration", () => {
  it("answers count / isEmpty / notEmpty from the resolved rows", async () => {
    const empty = new ParallaxList<Order>(async () => []);
    expect(await empty.count()).toBe(0);
    expect(await empty.isEmpty()).toBe(true);
    expect(await empty.notEmpty()).toBe(false);

    const full = new ParallaxList<Order>(async () => [{ id: 1, name: "a" }]);
    expect(await full.count()).toBe(1);
    expect(await full.isEmpty()).toBe(false);
    expect(await full.notEmpty()).toBe(true);
  });

  it("async iteration yields the stable rows in order", async () => {
    const rows = [
      { id: 1, name: "a" },
      { id: 2, name: "b" },
    ];
    const list = new ParallaxList<Order>(async () => rows);
    const collected: Order[] = [];
    for await (const row of list) {
      collected.push(row);
    }
    expect(collected).toEqual(rows);
  });
});

describe("ParallaxList — identity map (same PK ⇒ same object)", () => {
  it("collapses rows sharing an identity key to the first-seen instance, preserving order", async () => {
    const list = new ParallaxList<Order>(
      async () => [
        { id: 1, name: "first" },
        { id: 2, name: "other" },
        { id: 1, name: "duplicate-key" },
      ],
      { identity: (row) => row.id },
    );
    const resolved = await list.toArray();
    // Order preserved; the duplicate-PK row is the SAME instance as the first.
    expect(resolved.map((r) => r.id)).toEqual([1, 2, 1]);
    expect(resolved[0]).toBe(resolved[2]);
    expect(resolved[0]).not.toBe(resolved[1]);
  });

  it("keeps rows with a null/undefined identity key distinct", async () => {
    const a = { id: 0, name: "a" };
    const b = { id: 0, name: "b" };
    const list = new ParallaxList<Order>(async () => [a, b], {
      identity: () => null,
    });
    const resolved = await list.toArray();
    expect(resolved[0]).toBe(a);
    expect(resolved[1]).toBe(b);
    expect(resolved[0]).not.toBe(resolved[1]);
  });

  it("leaves rows untouched when no identity extractor is supplied", async () => {
    const rows = [
      { id: 1, name: "a" },
      { id: 1, name: "b" },
    ];
    const list = new ParallaxList<Order>(async () => rows);
    expect(await list.toArray()).toEqual(rows);
  });
});
