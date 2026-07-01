/**
 * M4 deep-fetch strategy — eager relationship loading with **one bulk query per
 * level**, never N+1.
 *
 * Deep fetch resolves a root row set plus a set of navigation paths into a graph
 * in `1 + L` round trips, where `L` is the number of distinct relationship hops
 * (shared path prefixes are fetched once). The algorithm, per level:
 *
 *  1. Gather the **distinct, non-null** parent-key values from the rows already
 *     fetched at the level above (first-appearance order, so the `IN` binds are
 *     deterministic and match the golden).
 *  2. If that key set is **empty**, the level is elided — no query is issued and
 *     no descendant level below it runs either (an empty root short-circuits the
 *     whole subtree; an empty intermediate elides only its own descendants).
 *  3. Otherwise issue **one** `… where <childCol> in (?, …)` query (with the
 *     relationship's declared `orderBy`), then fan the returned child rows into
 *     per-parent buckets in memory by matching `child[childColumn]` to
 *     `parent[parentColumn]`.
 *
 * Each parent row is decorated with the relationship under its declared name: a
 * **to-many** hop attaches an array (empty when the parent has no children); a
 * **to-one** hop attaches the single matching child object or `null`. The same
 * child rows recurse as the parents of the next level down.
 *
 * This package owns only the **orchestration** (the graph algorithm + the round-
 * trip discipline): it imports no metamodel, compiler, or driver. The runner
 * (M12) supplies, per relationship node, the resolved correlation columns, the
 * relationship cardinality, and a `compileLevel(keys)` closure that produces the
 * `{ sql, binds }` for that level — and the `exec` function that runs a query.
 * That keeps `@parallax/relationships` allowlist-clean (it depends only on
 * `@parallax/lists` / `@parallax/transactions` / `@parallax/bitemporal`).
 */

/** A materialized row keyed by physical output column name. */
export type Row = Record<string, unknown>;

/** A correlation key value used in an `IN` list and for in-memory bucketing. */
export type Key = string | number | bigint;

/** Run one already-built query (canonical `?` SQL + ordered binds) → its rows. */
export type Exec = (sql: string, binds: readonly unknown[]) => Promise<readonly Row[]>;

/** A compiled level query: the canonical SQL and its ordered binds. */
export interface LevelQuery {
  readonly sql: string;
  readonly binds: readonly unknown[];
}

/**
 * One relationship hop in the deep-fetch tree, resolved by the runner. Shared
 * path prefixes are merged into a single node (so `[items]` and
 * `[items, statuses]` share one `items` node with `statuses` as its child).
 */
export interface DeepFetchNode {
  /** The relationship name as it appears on the parent graph object (`items`). */
  readonly name: string;
  /** `true` for a to-one peer (single object / null); `false` for a to-many list. */
  readonly toOne: boolean;
  /** The parent-side physical correlation column (a key in the parent row). */
  readonly parentColumn: string;
  /** The child-side physical correlation column (a key in each child row). */
  readonly childColumn: string;
  /**
   * Compile this level's bulk query for a set of distinct parent-key values
   * (`… where <childColumn> in (?, …) [order by …]`). Never called with an empty
   * key set (an empty level is elided before compilation).
   */
  readonly compileLevel: (keys: readonly Key[]) => LevelQuery;
  /** The next hops to fetch off this level's child rows (deeper path segments). */
  readonly children: readonly DeepFetchNode[];
}

/** The assembled deep-fetch result: the decorated root rows + the round-trip count. */
export interface DeepFetchResult {
  /** The root rows, each decorated in place with its fetched relationships. */
  readonly rows: readonly Row[];
  /** The total statements issued: `1` (root) + one per non-elided level. */
  readonly roundTrips: number;
}

/**
 * Execute the deep fetch over an already-fetched root row set. The root query
 * (the `1` in `1 + L`) is issued by the runner before this; `rootRows` are its
 * result, and `roundTrips` therefore starts at `1`. Each non-empty level adds one.
 */
export async function deepFetch(
  rootRows: readonly Row[],
  tree: readonly DeepFetchNode[],
  exec: Exec,
): Promise<DeepFetchResult> {
  const counter = { roundTrips: 1 };
  await fetchLevels(rootRows, tree, exec, counter);
  return { rows: rootRows, roundTrips: counter.roundTrips };
}

/**
 * Fetch every node in `nodes` against the already-materialized `parents`, then
 * recurse into each node's children. A childless or empty level decorates its
 * parents with empty buckets and issues no descendant query (short-circuit).
 */
async function fetchLevels(
  parents: readonly Row[],
  nodes: readonly DeepFetchNode[],
  exec: Exec,
  counter: { roundTrips: number },
): Promise<void> {
  for (const node of nodes) {
    const keys = distinctKeys(parents, node.parentColumn);
    if (keys.length === 0) {
      // No parent keys at this level ⇒ no query, and no descendant query either.
      // Still decorate the (zero) parents uniformly so the shape is consistent.
      decorate(parents, node, []);
      continue;
    }
    const { sql, binds } = node.compileLevel(keys);
    const childRows = await exec(sql, binds);
    counter.roundTrips += 1;
    decorate(parents, node, childRows);
    if (node.children.length > 0) {
      await fetchLevels(childRows, node.children, exec, counter);
    }
  }
}

/**
 * The distinct, non-null parent-key values from `rows` (first-appearance order).
 * Order is load-bearing: it fixes the `IN`-bind order the golden pins.
 */
function distinctKeys(rows: readonly Row[], parentColumn: string): readonly Key[] {
  const seen = new Set<string>();
  const out: Key[] = [];
  for (const row of rows) {
    const value = row[parentColumn];
    if (value === null || value === undefined) {
      continue;
    }
    const key = value as Key;
    const dedupe = String(key);
    if (!seen.has(dedupe)) {
      seen.add(dedupe);
      out.push(key);
    }
  }
  return out;
}

/**
 * Fan `childRows` into per-parent buckets and decorate each parent in place under
 * the relationship's declared name. A to-many hop attaches an array (empty when
 * the parent matched no child); a to-one hop attaches the single matching child
 * (or `null`). Child order is preserved from the query (the DB honored the
 * relationship `orderBy`), so the to-many list reflects the declared ordering.
 */
function decorate(parents: readonly Row[], node: DeepFetchNode, childRows: readonly Row[]): void {
  const buckets = new Map<string, Row[]>();
  for (const child of childRows) {
    const value = child[node.childColumn];
    if (value === null || value === undefined) {
      continue;
    }
    const bucketKey = String(value as Key);
    const bucket = buckets.get(bucketKey);
    if (bucket) {
      bucket.push(child);
    } else {
      buckets.set(bucketKey, [child]);
    }
  }
  for (const parent of parents) {
    const value = parent[node.parentColumn];
    const matches = value === null || value === undefined ? [] : (buckets.get(String(value)) ?? []);
    (parent as Record<string, unknown>)[node.name] = node.toOne ? (matches[0] ?? null) : matches;
  }
}
