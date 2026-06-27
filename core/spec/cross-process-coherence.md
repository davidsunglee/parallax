# Cross-Process Cache Coherence

Cross-process coherence keeps the per-process caches of **multiple application
servers** consistent when they share **one** database. It is the multi-node
extension of `M8`'s in-process freshness rule (a committed write must not be
observed as stale): when node A commits a write, node B — a *different* process,
holding its own identity + query caches — **MUST** eventually serve the new state
rather than a stale cached copy.

This is a **fast-follow** capability (DQ4), not MVP, and it depends on `M8` (the
caches it keeps coherent). It is deliberately **not** a client-server / remote
concern: there is no app-to-app RPC and no three-tier topology. The motivating
deployment is the ordinary one — several stateless app servers behind a load
balancer, all pointed at one distributed Postgres (e.g. Aurora). Each server
caches independently; coherence is what stops two servers from disagreeing about
a row one of them just changed.

## Why it is fast-follow, not client-server-only (DQ4)

Reladomo's notification bus was historically associated with its three-tier
remote mode, which this spec **excludes** (won't-do, round 1). But the *need* is
independent of remoting: the moment **more than one process** caches rows from a
**shared** database, a write on one process can leave another's cache stale. That
is a single-tier, multi-app-server reality — so coherence is promoted to a
first-class fast-follow capability, decoupled from the excluded remote mode.

## The coherence contract

The mechanism is **non-normative**; the observable rule is normative.

- **Observable rule (normative).** After node A's write to an entity **commits**,
  a subsequent find on node B for that entity **MUST NOT** return stale rows: once
  B has been **notified** of (or otherwise observes) the invalidation, a find that
  would previously have been a cache hit **MUST** re-resolve against the database
  and return A's committed state. Identity is preserved across the refresh (the
  re-fetched row updates the existing interned object; B does not fork a second
  object for the same primary key).

- **Mechanism (non-normative).** Reladomo bumps a monotonic **version token**
  (`UpdateCountHolder` / update-count) per class/attribute on every write and
  broadcasts a notification event to peer processes; a receiving full-cache node
  **re-fetches** the changed rows by primary key, a partial-cache node simply
  **marks dirty** and lets the next find miss. An implementation **MAY** use any
  transport (a message bus, Postgres `LISTEN/NOTIFY`, polling a change table) and
  any granularity (per-row, per-entity) so long as the observable rule holds.

### Full-cache re-fetch vs. partial-cache mark-dirty

Two invalidation strategies satisfy the rule; both are permitted:

| Strategy | On notification of a peer write | Used by |
|---|---|---|
| **full-cache re-fetch** | re-fetch the changed primary keys from the database and update the interned objects in place | a node holding a complete cache it intends to keep warm |
| **partial-cache mark-dirty** | evict / mark the affected cache entries dirty; the next find for them misses and re-resolves | a node holding a bounded, evictable cache |

The **observable outcome is identical** — a post-invalidation find on node B
returns node A's committed row — so the suite asserts the outcome, not the
strategy. The mark-dirty strategy is the more conservative default; full-cache
re-fetch is an optimization that keeps the cache warm.

## What the suite pins down

Coherence is a **multi-process** property, but its *observable SQL-level* half is
verifiable with **two connections to one database** acting as two nodes. The
compatibility suite models this with a **coherence case** (`M12`): a two-node
operation sequence whose final step asserts what node B observes after node A's
committed write.

| Step | Node | Effect |
|---|---|---|
| seed read | B | B reads a row and would (in-process) cache it |
| write | A | A commits a change to that row (a different connection ⇒ a different "node") |
| re-fetch | B | B's declared invalidation behavior re-resolves the row against the database and observes A's committed state |

The case authors the golden SQL for each database-touching step and the rows node
B **MUST** observe after the write. The harness:

1. provisions one database and opens **two** connections (node A, node B) through
   the provider's two-node mode;
2. runs each step on its declared node, executing that step's golden SQL;
3. asserts node B's final re-fetch returns the **post-write** rows
   (`observeRows`) — the new state, never the pre-write cached state.

Because the harness **never compiles operations to SQL** (`M12`), it does not
implement a cache or a notification bus: it proves the *suite* is consistent — the
post-write golden SQL on node B is correct against real, committed data written by
node A on a separate connection. An implementation's actual invalidation
machinery is graded by the same observable rows it must produce.

The compatibility corpus covers the three basic write shapes that can invalidate
a peer cache entry: update, insert, and delete. For delete, node B's post-write
re-fetch must return an empty result for the deleted primary key.

> **What two connections do and do not prove.** Two connections prove the
> *result-correctness* half: node B's re-fetch golden SQL, run after node A's
> committed write, returns the new state. They do not exercise an actual
> cross-process notification transport (that is implementation machinery the
> harness deliberately does not contain). This is the same scoping the read-lock
> case uses for concurrency in `M8`: the suite proves the observable, well-formed,
> result-correct SQL contract that any conforming invalidation mechanism must
> satisfy.

## Relationship to M8

`M8`'s invalidation section covers the **in-process** rule (a committed write is
never observed as stale *within* a process). Cross-process coherence is the
**across-process** extension of exactly that rule, lifted to the multi-app-server
deployment. The in-process query cache (`M8`, mandatory) is the thing being kept
coherent; this capability adds the contract that the cache of a *peer* process
also converges on the committed state.
