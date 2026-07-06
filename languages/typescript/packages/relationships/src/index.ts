/**
 * `@parallax/relationships` — relationships and deep fetch (`m-navigate`, `m-deep-fetch`).
 *
 * The correlated-EXISTS navigation semi-join lowers in `@parallax/sql` (the
 * compiler owns SQL text); this package owns the **deep-fetch orchestration** —
 * the one-bulk-query-per-level graph algorithm that eliminates N+1, plus the
 * round-trip discipline the conformance suite asserts. Temporal per-hop as-of
 * propagation lands in Phase 6.
 */
export {
  type DeepFetchNode,
  type DeepFetchResult,
  deepFetch,
  type Exec,
  type Key,
  type LevelQuery,
  type Row,
} from "./deepfetch.js";
