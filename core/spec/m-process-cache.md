# m-process-cache — Identity & Query Cache (deferred)

**Status: deferred.** `m-process-cache` is the in-process cache layer: the
**identity cache** (one interned object per primary key) and the **query cache**
(an operation mapped to its result list, so a repeated equal find costs no round
trip), plus their **invalidation** on write. These are process-level semantics
layered on the unit of work, not unit-of-work semantics themselves. The
**transaction-scoped floor** of the identity guarantee — one managed object per
identity key *within* a unit of work, with no round-trip-elimination claim — is
the active `m-identity-map`; this module is the process-wide widening (identity
*across* units of work, plus the query cache and its freshness rules).

- **Edge:** `m-process-cache --> m-unit-work`.
- **Behavioral floor.** Three scenario cases pin the observable minimum and stay
  green:
  - `m-process-cache-001` (cache-hit) — two identical finds cost **one** round
    trip; the second is served without a database statement.
  - `m-process-cache-002` (identity) — two finds for the same primary key denote
    the **same logical object**.
  - `m-process-cache-003` (cache-invalidation) — after a committed write, the same
    find re-resolves and observes the new value, never a stale cached row.

  The full identity/query-cache specification — cache scopes, the invalidation
  mechanism, and the mandatory-cache framing that makes deep-fetch round-trip
  counts a portable contract — is **deferred beyond what those three cases pin
  down**. Cross-process coherence of these caches is the separately deferred
  `m-coherence`.
