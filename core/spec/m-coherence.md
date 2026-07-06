# m-coherence — Cross-Process Cache Coherence (deferred)

**Status: deferred.** `m-coherence` keeps the per-process caches of **multiple
application servers** consistent when they share **one** database — the multi-node
extension of `m-process-cache`'s in-process freshness rule. When node A commits a
write, node B (a different process, holding its own caches) **MUST** eventually
serve the new state rather than a stale cached copy. It is deliberately **not** a
client-server / remote concern: the motivating deployment is several stateless app
servers behind a load balancer, all pointed at one database.

- **Edge:** `m-coherence --> m-process-cache` (the caches it keeps coherent;
  `m-unit-work` stays reachable transitively).
- **Behavioral floor.** The observable rule (mechanism-agnostic): after node A's
  committed write, node B's next find for that entity re-resolves against the
  database and returns A's committed state, **preserving identity** (the re-fetch
  refreshes the interned object in place rather than forking a second object for
  the same primary key). Either invalidation strategy satisfies it — full-cache
  re-fetch or partial-cache mark-dirty. Verifiable with **two connections to one
  database** acting as two nodes: cases `m-coherence-001`–`m-coherence-006` cover
  update / mark-dirty / delete / insert-refetch and the two identity-preservation
  surfacings (re-fetch by primary key; surface by non-key predicate then re-fetch
  by key). That floor stays green; the full transport / notification specification
  is deferred beyond it.
