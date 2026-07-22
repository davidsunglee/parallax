# Reladomo-to-Parallax Gap Priority

This note summarizes the Reladomo capabilities called out by the module-system
research (originally a riptide task artifact, `02-research-module-system-catalog.md`,
not stored in this repo; the durable Reladomo findings now live in
[docs/research/reladomo/](reladomo/00-index.md)).

It is normalized against the current slug-based Parallax module catalog in
`core/spec/modules.md`, so items are classified as active, explicitly deferred,
explicitly excluded, partially acknowledged, or still missing.

## Priority Ordering

| Rank | Reladomo capability not fully in Parallax | Current Parallax status | Criticality |
|---:|---|---|---|
| 1 | Identity cache + query cache | Explicitly deferred: `m-process-cache` | Core ORM semantics. Affects identity, list behavior, unit-of-work freshness, optimistic locking ergonomics, benchmarks, and coherence. |
| 2 | Source attributes / tenant or shard routing | Explicitly excluded, with a "not a one-way door" seam note | Highest architectural risk. Even if not implemented now, the database port and transaction seams must keep room for it. |
| 3 | Calculated / computed attributes and SQL scalar expressions | Mostly missing | Important query-language gap: arithmetic, string functions, date extraction, expression attributes. Touches descriptor, operation algebra, SQL, and API shape. |
| 4 | DB-native identity / auto-increment primary keys | Missing | Common database integration gap. Current `m-pk-gen` has `none`, `max`, and simulated `sequence`, but not DB identity columns. |
| 5 | Aggregation and SQL lowering | Explicitly deferred: `m-agg`, `m-sql-agg` | Common reporting/query feature. Already modeled as a deferred module pair. |
| 6 | Bitemporal overlap detection / repair | Missing | Important for temporal data integrity. Current `m-bitemp-write` handles rectangle-split writes, not remediation of bad or overlapping history. |
| 7 | Broader list bulk operations and list merge API | Partially acknowledged in `m-batch-write`; merge missing | Current scope covers set-based flush, not Reladomo-style `deleteAll`, `insertAll`, `terminateAll`, `purgeAll`, or diff/merge of lists. |
| 8 | Temp-table / large-`IN` deep fetch | Acknowledged as deferred fast-follow | Important scalability feature for deep fetch and large relationship traversals. |
| 9 | Valid-Time-Only temporal writes | Explicitly deferred: `m-validtime-only` | Needed for temporal parity, but narrower than audit-only and full bitemporal support. |
| 10 | Runtime cache administration and declarative cache loader | Missing | Becomes important once `m-process-cache` exists: warm-up, reload, clear/renew, and dependent loaders. |
| 11 | Nested transaction, ambient transaction, JTA/external transaction-manager semantics | Partially acknowledged in TypeScript ADR; missing core decision | Parallax should decide whether this is core, per-language, or rejected. TypeScript currently joins active transactions. |
| 12 | Cross-process cache coherence | Explicitly deferred: `m-coherence` | Depends on process cache. Important in multi-node deployments, but downstream of rank 1. |
| 13 | Application-level data-change callbacks | Missing | Distinct from cache coherence: user-facing subscriptions or hooks on committed changes. |
| 14 | Streaming cursor / large-result handling | Not clearly present in current slug catalog | Important for memory behavior and production reads, but less central than query correctness. |
| 15 | DB-native bulk load | Missing | Performance/dialect feature, especially vendor-specific bulk loaders. Not core for parity MVP. |
| 16 | Query / SQL introspection and telemetry hooks | Missing | Valuable for debugging and performance contracts: explain/analyze surfaces, stats listener, SQL snooping. |
| 17 | Adhoc / queryable in-memory lists | Missing | Useful, but less essential than operation-backed persistent lists. |
| 18 | Pure in-memory objects | Missing; previously a might-do item in the numbered-module scope model | Separate from adhoc lists; likely not central to Parallax's ORM thesis. |
| 19 | Serialization framework and GraphQL tooling | Not core; descriptor serde exists | Useful ecosystem layer, but should probably stay optional or per-language unless Parallax wants a tooling contract. |
| 20 | Object-graph extraction and DB-to-model reverse engineering | Missing | Good for tests, migration, and tooling, but not core runtime behavior. |
| 21 | Multi-threaded deep fetch / cross-database adhoc deep fetch | Missing; cross-source behavior intersects excluded sharding | Nice scalability/enterprise behavior, but not a core contract until source routing exists. |
| 22 | Temporal `insertForRecovery` | Missing | Special recovery/admin temporal operation; lower than overlap repair. |
| 23 | MAY-tier temporal ops: `insertWithIncrement`, `incrementUntil`, `purge`, `inactivateForArchiving` | Acknowledged as MAY in `m-bitemp-write` | Properly nonessential for required parity. |
| 24 | XA / distributed transactions / transactional JMS | Missing | Enterprise integration surface; probably an explicit non-goal unless Parallax targets app-server parity. |
| 25 | Remote / client-server mode | Explicitly excluded | Reasonable non-goal for Parallax core. |
| 26 | Off-heap storage | Explicitly excluded | Implementation detail; not a behavioral spec priority. |
| 27 | XML config and codegen mandates | Explicitly excluded | Correctly excluded: Parallax mandates the metamodel, not XML or codegen. |
| 28 | Cache-monitoring UI | Missing | Product/tooling layer, not core spec. |

## Highest-Value Decisions

The items most worth either specifying or explicitly declining are ranks 1-11.
They affect core runtime semantics, public API shape, or future architectural
seams:

- `m-process-cache` and its interaction with unit-of-work, lists, optimistic
  locking, and benchmarks.
- Source/tenant routing as an intentionally unimplemented but preserved seam.
- Computed attributes and DB identity columns, because both change the descriptor
  and SQL contracts.
- Temporal integrity repair, especially overlap detection/repair.
- The boundary of list bulk operations versus list-level merge.
- Transaction nesting and external transaction-manager integration.

The remaining items are mostly optional tooling, enterprise integration, or
implementation-specific Reladomo surface. They still deserve explicit decisions
if the goal is a complete parity ledger, but they are less likely to block the
core Parallax contract.
