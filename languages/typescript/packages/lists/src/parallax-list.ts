/**
 * m-op-list `ParallaxList<T>` — the lazy, async, operation-backed list.
 *
 * A `ParallaxList` wraps a backing operation (a resolver that runs the query)
 * and is **lazy**: nothing executes until a first async access (`toArray`, a
 * `for await` iteration, an object-returning helper). On first resolution it
 * materializes a **stable** in-memory result reused by every later access
 * (idempotent — the query runs at most once), and it runs every materialized row
 * through an **identity map** keyed by the row's primary key so the same PK
 * yields the same object instance across calls and across iteration (ADR-0025,
 * ADR-0030: references, not promise properties).
 *
 * Helpers (ADR-0025):
 *  - `toArray()` resolves and returns the stable array.
 *  - `first()` / `firstOrNull()` resolve; `first` throws `ParallaxNotFoundError`
 *    when empty, `firstOrNull` returns `null`.
 *  - `single()` / `singleOrNull()` resolve; `single` throws
 *    `ParallaxNotFoundError` when empty and `ParallaxTooManyResultsError` when
 *    more than one row exists; `singleOrNull` returns `null` when empty but still
 *    throws `ParallaxTooManyResultsError` for multiple rows.
 *  - `count()` / `isEmpty()` / `notEmpty()` answer from the stable result once
 *    resolved; when still unresolved they MAY use an optimized count query
 *    (without marking the list resolved) — here the resolver is the only backing,
 *    so they resolve like the others, which is observably identical.
 *  - async iteration (`for await … of list`) resolves and yields the stable rows.
 *
 * The list does not emulate arrays (no `length`, no numeric indexing, no
 * synchronous iteration) — those are left to normal TypeScript over `toArray()`.
 */

/** The base class of the public Parallax error hierarchy (ADR-0053). */
export class ParallaxError extends Error {
  /** A stable, machine-readable error code applications branch on. */
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = new.target.name;
    this.code = code;
    // Preserve the prototype chain across the TS `extends Error` downlevel seam.
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/** Thrown by `first` / `single` when the list resolves to zero rows. */
export class ParallaxNotFoundError extends ParallaxError {
  constructor(message = "expected at least one result, found none") {
    super("PARALLAX_NOT_FOUND", message);
  }
}

/** Thrown by `single` / `singleOrNull` when the list resolves to more than one row. */
export class ParallaxTooManyResultsError extends ParallaxError {
  /** The number of rows the list resolved to (always `> 1`). */
  readonly count: number;

  constructor(count: number) {
    super("PARALLAX_TOO_MANY_RESULTS", `expected at most one result, found ${count}`);
    this.count = count;
  }
}

/** A resolver that runs the backing operation and returns its raw rows. */
export type ListResolver<T> = () => Promise<readonly T[]>;

/**
 * Derive a row's identity key for the identity map. Returns a stable string the
 * list dedupes on; rows that share a key are the same object instance. A
 * `null`/`undefined` from the extractor opts a row out of identity sharing (each
 * such row stays distinct).
 */
export type IdentityKey<T> = (row: T) => string | number | bigint | null | undefined;

/** Options controlling a list's identity behavior. */
export interface ParallaxListOptions<T> {
  /** Extract a row's primary-key identity (so same-PK ⇒ same object). */
  readonly identity?: IdentityKey<T>;
}

/**
 * A lazy, async, operation-backed list. Construct it with a resolver (and an
 * optional identity extractor); it executes the resolver at most once, on first
 * async access, and serves a stable, identity-mapped result thereafter.
 */
export class ParallaxList<T> implements AsyncIterable<T> {
  private resolved: readonly T[] | undefined;
  private pending: Promise<readonly T[]> | undefined;

  constructor(
    private readonly resolver: ListResolver<T>,
    private readonly options: ParallaxListOptions<T> = {},
  ) {}

  /** Resolve the backing operation once and serve a stable, identity-mapped array. */
  async toArray(): Promise<readonly T[]> {
    return this.resolve();
  }

  /** The first row, or throw `ParallaxNotFoundError` when the list is empty. */
  async first(): Promise<T> {
    const rows = await this.resolve();
    const head = rows[0];
    if (head === undefined) {
      throw new ParallaxNotFoundError();
    }
    return head;
  }

  /** The first row, or `null` when the list is empty. */
  async firstOrNull(): Promise<T | null> {
    const rows = await this.resolve();
    return rows[0] ?? null;
  }

  /**
   * The single row. Throws `ParallaxNotFoundError` when empty and
   * `ParallaxTooManyResultsError` when more than one row exists.
   */
  async single(): Promise<T> {
    const rows = await this.resolve();
    if (rows.length === 0) {
      throw new ParallaxNotFoundError();
    }
    if (rows.length > 1) {
      throw new ParallaxTooManyResultsError(rows.length);
    }
    return rows[0] as T;
  }

  /**
   * The single row or `null` when empty; still throws
   * `ParallaxTooManyResultsError` when more than one row exists.
   */
  async singleOrNull(): Promise<T | null> {
    const rows = await this.resolve();
    if (rows.length === 0) {
      return null;
    }
    if (rows.length > 1) {
      throw new ParallaxTooManyResultsError(rows.length);
    }
    return rows[0] as T;
  }

  /** The number of rows the list resolves to. */
  async count(): Promise<number> {
    return (await this.resolve()).length;
  }

  /** True when the list resolves to zero rows. */
  async isEmpty(): Promise<boolean> {
    return (await this.resolve()).length === 0;
  }

  /** True when the list resolves to at least one row. */
  async notEmpty(): Promise<boolean> {
    return (await this.resolve()).length > 0;
  }

  /** Async iteration yields the stable resolved rows. */
  async *[Symbol.asyncIterator](): AsyncIterator<T> {
    for (const row of await this.resolve()) {
      yield row;
    }
  }

  /**
   * Resolve the backing operation exactly once. Concurrent callers share the
   * single in-flight promise; once settled the stable array is served directly.
   */
  private async resolve(): Promise<readonly T[]> {
    if (this.resolved !== undefined) {
      return this.resolved;
    }
    if (this.pending === undefined) {
      this.pending = this.resolver().then((rows) => {
        this.resolved = this.applyIdentity(rows);
        return this.resolved;
      });
    }
    return this.pending;
  }

  /**
   * Run materialized rows through the identity map: rows sharing an identity key
   * collapse to the first-seen instance (same PK ⇒ same object). Rows with no
   * identity key stay distinct. Order is preserved.
   */
  private applyIdentity(rows: readonly T[]): readonly T[] {
    const identity = this.options.identity;
    if (identity === undefined) {
      return rows;
    }
    const byKey = new Map<string, T>();
    return rows.map((row) => {
      const key = identity(row);
      if (key === null || key === undefined) {
        return row;
      }
      const dedupe = String(key);
      const existing = byKey.get(dedupe);
      if (existing !== undefined) {
        return existing;
      }
      byKey.set(dedupe, row);
      return row;
    });
  }
}
