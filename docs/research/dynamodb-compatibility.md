# DynamoDB compatibility with the Parallax model and API

A compatibility survey, written 2026-11-20 against Parallax revision `52938cb11`. It maps the model and API surface onto Amazon DynamoDB, separates what works from what cannot, recommends changes that would make Parallax easier to map, and lists DynamoDB features Parallax cannot express today, each with its PostgreSQL analog where one exists.

## How far to trust this

- **Read from the repository.** Statements about Parallax come from digests of `core/spec`, the ADRs, and the Python guide prepared for this survey. Only the flush rules in [`m-unit-work`](../../core/spec/m-unit-work.md) were re-read directly.
- **Recalled, not tested.** DynamoDB statements are from vendor documentation as remembered, except the ones listed under [Sources](#sources), which were looked up. No DynamoDB table was created and no request was sent.
- **Illustrative.** Every request shape, descriptor key, binding key, and API spelling below is a sketch of a shape, not a proposed name.

## Verdict

- **Model: maps well.** Single-attribute keys, value objects, table-per-hierarchy inheritance, framework-owned versions, and the temporal physical key all have direct DynamoDB forms. Parallax's deliberate omissions — no foreign keys, no cascade, no aggregates, no projections, no offset — remove most of what a key-value store cannot do.
- **Read API: maps for key-shaped and index-shaped reads.** Relationship predicates, which lower to server-side semi-joins today, have no native form.
- **Transaction model: the real gap.** Parallax runs an interactive transaction: read, write, flush, read again, roll back. DynamoDB commits one fixed list of at most 100 conditional writes.
- **DynamoDB cannot be a dialect.** SQL is rendered above the database port, so an adapter has to plug in at the Planned Step and Object Query level. That answers the open question in the [document storage sketch](parallax-future-document-storage-sketch.md) — whether a non-relational store belongs behind the existing port — with "above SQL".

## DynamoDB limits that shape the mapping

| Limit | Value |
|---|---|
| Item size | 400 KB, attribute names included |
| Transaction | 100 actions and 4 MB, one action per item, all or nothing |
| Transaction isolation | Serializable between transactions and single-item operations; read-committed for multi-item reads |
| Batch get | 100 items and 16 MB per call, not atomic |
| Number type | 38 significant digits |
| Key attribute types | String, number, binary |
| Base-table key | One partition attribute and at most one sort attribute |
| Global secondary index key | Up to four partition attributes and four sort attributes; always eventually consistent; about 20 per table by default |
| Constraints | Primary-key uniqueness and per-write condition expressions only |

## Model mapping

| Parallax | DynamoDB | Fit |
|---|---|---|
| Entity in `Table(name)` | One table per entity | Native |
| Single-attribute key (Int32, Int64, String, Uuid) | Partition key (number or string) | Native; Parallax's key rule is exactly DynamoDB's simple key |
| Scalars | Boolean, number, string, binary; dates, times, timestamps and UUIDs as fixed-width strings | Native; numeric precision capped at 38 digits, float64 extremes unrepresentable |
| Value objects, `many`, scalar collections | Maps and lists, with native nested-path filters | Native; the whole item is capped at 400 KB |
| Document layout rules | Every item is a document; only key types are enforced | The host-checked-on-read precedent already covers it |
| Transaction-Time key `(pk, out_z)` | Partition `pk`, sort `out_z`, max-sentinel infinity as on MariaDB | Native; a Latest read is a single `GetItem` |
| Bitemporal key `(pk, out_z, thru_z)` | Sort key is the two ends concatenated | Works; a base-table sort key is one attribute |
| Version attribute, `in_z` as temporal version | Condition expression on the write | Native |
| `key-sequence` | Counter item incremented by the block size | Works by emulation; block reservation outside the transaction is the same shape |
| Indices | Global secondary indexes, temporal ends as the sort suffix | Works, but eventually consistent and missing a hash and range split |
| `unique` index | Guard item written in the same transaction | Emulated at double write cost |
| Relationships: one-attribute equality, no foreign keys, no cascade | Nothing to enforce | Native |
| Table-per-hierarchy | Tag attribute; subtype attributes simply absent | Native |
| Table-per-concrete-subtype | One table per leaf; polymorphic reads merged in the host | Works |
| Temporal overlap exclusion ([ADR 0079](../adr/0079-postgresql-storage-refuses-overlapping-history-and-its-conflicts-are-retried.md)) | Per-object lineage item conditioned by every temporal write | Emulated, and stronger than MariaDB's unguarded state |
| NOT NULL, `maxLength`, column types | None | Host-checked |
| Schema delta | `CreateTable` and index updates as requests; adding an attribute needs nothing | Needs a statement form that is not SQL text |

Notes on the rows that need more than a cell:

- **Temporal key.** Keeping the axis end in the key ([ADR 0051](../adr/0051-temporal-physical-key-uses-axis-end-columns.md)) makes a Latest read a point get, the path [ADR 0094](../adr/0094-indices-on-bitemporal-tables-end-with-the-transaction-time-end-first.md) names as the one to optimize. The cost is that a key attribute cannot be updated, so a close rewrites the old milestone under a new key. The alternative — sorting on `in_z` — makes a close an in-place update and turns Latest into a one-item descending query.
- **Lineage item.** DynamoDB has no range constraint. One extra item per object, with a counter that every temporal write to that object advances conditionally, serializes writers per object and makes overlap impossible by construction. It costs one action of the 100.
- **Numbers.** The canonical document encoding spells a numeric as a string, and DynamoDB expressions cannot cast. A numeric has to be stored as a native number to be compared in a filter, so the item encoding is its own leaf mapping rather than the JSON one.
- **Indices.** A Parallax index is an ordered attribute list. A DynamoDB index needs to know which leading attributes are matched by equality (partition) and which are ranged (sort). Index keys must also be top-level scalars, so a member nested inside a value object would need a hoisted copy.

## Use cases that work

```python
db.find(Customer.where(Customer.id == 1)).result()
#  GetItem customer {id: 1}

tx.amend_if(Order, Order.total.set(t), key=7, version=3)
#  UpdateItem orders {id: 7} SET total, version = 4   IF version = 3
#  Zero reads: the stated-revision write is DynamoDB's native shape.

db.find(CreditLimit.where(CreditLimit.customer_id == 1).as_of(tx_time=when))
#  Query customer_id = 1 AND out_z > when, Limit 1, then check in_z <= when
#  .history(TX_TIME) is the same Query without the sort condition.
```

A transaction that inserts an order, amends a versioned customer, and amends a Transaction-Time credit limit commits as one request:

```text
TransactWriteItems
  Put    orders        {id 7, version 1}                  IF attribute_not_exists(id)
  Update customer      {id 1} SET email, version = 2      IF version = 1
  Put    credit_limit  {1, out_z ∞, in_z now, new state}  IF in_z = observed
  Put    credit_limit  {1, out_z now, old state}          IF attribute_not_exists(customer_id)
```

- **Temporal close.** The plan already retains the complete predecessor state ([ADR 0042](../adr/0042-temporal-plans-retain-complete-predecessor-state-and-close-cause.md)), which is what the rewrite under a new key needs. A stated-revision write on a temporal entity has no predecessor in hand and needs one read.
- **Bitemporal `amend(..., until=)`.** One close plus up to three inserts becomes four or five actions.
- **Unchanged-milestone guard.** The `set in_z = in_z` update becomes a native `ConditionCheck`.
- **Shortfall classification.** A failed condition can return the stored item, so the adapter can tell a missing target from a stale one directly. An excess count cannot occur.
- **Whole-callback retry.** A failed version condition maps to Optimistic Lock Conflict and a transaction conflict maps to the `deadlock` category of [`m-db-error`](../../core/spec/m-db-error.md).
- **To-one `include`.** `BatchGetItem`, 100 keys per call.
- **Indexed attribute lookup.** A query on a global secondary index, with the temporal ends as the sort condition for an as-of read.

## Incompatibilities

### Unimplemented portions

Each of these would be refused with a capability diagnostic rather than approximated, following the MariaDB lane of [`m-dialect`](../../core/spec/m-dialect.md).

| Parallax promise | Why DynamoDB cannot keep it |
|---|---|
| Read-your-own-writes by force-flushing inside the open transaction | Nothing can be flushed and later rolled back, and [`m-unit-work`](../../core/spec/m-unit-work.md) forbids a flush that survives the abort. A read that depends on a pending write must be refused, or served from memory for key reads only |
| `locking` preference, and unversioned non-temporal entities | No row locks. The README's `place_an_order` is refused as written, because `Customer` has no version |
| Predicate writes (`amend_where`, `replace_where`, `delete_where`) | No set-based write |
| `repeatable-read` and `serializable` | Only Read Committed is honest; a range read cannot be validated against phantoms at commit |
| Unbounded transaction size | 100 actions and 4 MB per commit, guard and lineage items included |
| `all`, filtered quantifiers over `many` value objects, `endsWith`, general `like`, `caseInsensitive` | No per-element predicates, no pattern matching beyond prefix and substring, no case folding |
| Golden SQL, Database Call counts, physical table state | Nothing to emit; no conformance mode grades on behaviour alone |

### Exact results at a different cost

- **Relationship predicates.** `Customer.orders.any(Order.total > x)` is a server-side semi-join today. DynamoDB needs two steps: query the children, collect keys, batch-get the roots.
- **To-many `include`.** One query per parent key against an index on the child's join attribute. That breaks the "never one call per parent" promise in round trips, though the calls can run in parallel.
- **Unindexed predicates.** A full scan, billed per item read.
- **`order_by` off an index.** Fetch every match and sort in the host.
- **Index reads lag.** Global secondary indexes are always eventually consistent, which matches the existing `reader` route wording. A stale read cannot license a bad write, because the version condition at commit catches it. In a writable transaction the safer form reads keys from the index and then gets the base items consistently.
- **Null handling.** As recalled, `<>` on a missing attribute is true in DynamoDB, and an index omits items whose key attribute is absent. The lowering has to add explicit existence guards to keep three-valued results, and a nullable attribute cannot serve an ordered read from an index alone.
- **Streams.** The native continuation key replaces seek predicates, but a scan returns hash order, not primary-key order.

## Recommended changes

Ranked by how much each one unlocks.

1. **Adapter seam above SQL.** `m-unit-work` already avoids `m-sql`, and Planned Steps name attributes, never columns ([`m-planned-step`](../../core/spec/m-planned-step.md)). Promote the step-execution and row-acquisition ports to a provider seam, with an equivalent on the read side.
2. **Commit-only atomic scope as a declared capability.** Of the three flush triggers, read dependency and predicate write become refusals; pre-commit becomes the single request.
3. **A neutral capability-refusal vocabulary.** Generalize the MariaDB lane ("reject, never approximate") to cover locks, isolation levels, set-based writes, and semi-join predicates. No neutral core error code exists for this today.
4. **Mandatory version on a lock-free backend.** Refuse at binding any read-write entity that is neither versioned nor temporal. Predicate writes are admitted only on unversioned non-temporal targets, so this also leaves them with no admissible target, which is consistent.
5. **Two new error categories.** Throttling (retriable with backoff, not a conflict) and limit exceeded (transaction or item too large, never retriable).
6. **Index physical facts in the Database Binding.** Add a `dynamodb` backend and a per-index split between equality attributes and range attributes. The `rows: current` and `include:` declarations from the [PostgreSQL feature survey](postgresql-feature-opportunities.md) map directly onto sparse indexes and index projections.
7. **A behaviour-graded conformance lane.** Grade rows and logical state where a backend has no SQL.
8. **Unordered stream order left unspecified.** The continuation order falls back to primary key ascending, which a scan cannot produce.

## DynamoDB features Parallax cannot express

| Feature | What it would give Parallax | PostgreSQL analog |
|---|---|---|
| Item collections (parent and children in one partition) | A parent with its children in one query; see the next section | Weak: partitioning or clustering by parent key |
| Arbitrary write conditions | `amend_if(..., when=<predicate>)` instead of version only | `update … where pk = ? and <predicate>` plus the row count |
| In-place update expressions (add, append, set-if-absent) | Conflict-free counters without read-then-retry | `set n = n + 1` |
| Time-to-live expiry | Retention for closed history milestones | Dropping range partitions (survey item 5) |
| Streams | A change feed per entity | Logical decoding (survey item 8) |
| Idempotent commit token | Safe retry of an ambiguous commit | No built-in; `pg_xact_status` can resolve one |
| Sparse indexes and index projections | Current-row and covering indexes | Partial and `INCLUDE` indexes (survey item 1) |
| Consistent or eventual read flag | Already expressible as route policy | Replicas (survey item 6) |
| Resumable page token | A public cursor; Parallax keeps its keyset coordinates private | Keyset paging, already used internally |
| Bulk put from S3 with per-item conditions | Backfill | `COPY` (survey item 8) |
| Global tables | Multi-region writes | None in core PostgreSQL |
| Vector search, native set types, unconditional upsert | No current use case; upsert cuts against observed writes | pgvector, arrays, `on conflict` |

Global tables carry a trap. The strongly consistent mode rejects transactional calls and has no time-to-live. The eventually consistent mode checks a condition only in the local region. Parallax's version gates are therefore not safe across regions in either mode.

## Item collections and nested value objects

These are two different DynamoDB patterns, and Parallax already models one of them. Nested value objects are the embedded pattern: the children live inside the parent's item. An item collection is separate items that share a partition key. Those children are independently addressable, writable, and queryable, so they correspond to top-level Parallax entities plus a co-location fact that Parallax has no way to state today.

```text
Embedded (value objects)              Item collection (entities)
------------------------              --------------------------
customer {id 1}                       pk=1  sk=CUSTOMER      {name, version}
  name                                pk=1  sk=ORDER#7       {total, version}
  orders: [ {id 7, total},            pk=1  sk=ORDER#9       {total, version}
            {id 9, total} ]
one item, one version, <= 400 KB      three items, each with its own version
```

| | Nested value objects | Item collection |
|---|---|---|
| Child identity | None | Own key (partition and sort) |
| Read one child | Read the whole parent | `GetItem`, or a sort-key range within the parent |
| Query children across parents | Scan only; index keys must be top-level scalars | Secondary index on any child attribute |
| Write one child | Rewrites the parent item and bumps its version, so all writers of that parent conflict | Conditional write on that child alone |
| Size | All children fit in the parent's 400 KB | Unbounded count |
| History | A child change is a new milestone of the whole parent | The child has its own milestones |
| Relationship target, query root | No | Yes |

Value objects have a further weakness on DynamoDB: a filtered quantifier over a `many` value object has no native filter expression, so "customers with an order over X" cannot be pushed down.

**Rule of thumb.** Use a value object when the children are few, small, and always read and written with the parent. Use an entity when they are unbounded, written concurrently, queried on their own, or need their own history.

What Parallax would need for the entity form:

- **A co-location declaration.** For example, "`Order` is stored under `Customer` through `customer_id`". It fits the Database Binding as a physical fact, or the existing `dependent` flag, which is metadata only today.
- **A composite physical key under a single-attribute model key.** The child's physical key becomes (`customer_id`, `id`). Temporal tables already do this, with the model key plus `out_z`, so the pattern is not new.
- **An immutable, non-null join attribute.** It is now part of the physical key; `readOnly` already expresses immutability.
- **A decision on key-only lookups.** `Order.where(Order.id == 7)` no longer names the partition. It either goes through an eventually consistent index on `id`, or is refused unless the predicate also pins `customer_id`.

Fetching the parent and its children in one query additionally requires them to share a table, which cuts against one table per entity. Children in their own table keyed by the parent still give a strongly consistent to-many `include` without an index, at one query per parent.

## Sources

- [Multi-attribute composite keys in global secondary indexes](https://aws.amazon.com/about-aws/whats-new/2025/11/amazon-dynamodb-multi-attribute-composite-keys-global-secondary-indexes)
- [Multi-attribute keys pattern](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GSI.DesignPattern.MultiAttributeKeys.html)
- [DynamoDB transactions: how it works](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html)
- [TransactGetItems API reference](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_TransactGetItems.html)
- [100 actions per transaction](https://aws.amazon.com/about-aws/whats-new/2022/09/amazon-dynamodb-supports-100-actions-per-transaction)
- [How global tables work](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/V2globaltables_HowItWorks.html)
- [Global tables FAQ](https://docs.aws.amazon.com/prescriptive-guidance/latest/dynamodb-global-tables/faq.html)
- [Bulk put items](https://aws.amazon.com/jp/about-aws/whats-new/2026/11/amazon-dynamodb-now-supports-bulk-put-items/)
- [Vector search](https://aws.amazon.com/about-aws/whats-new/2026/08/amazon-dynamodb-vector-search/)
- [Streams timestamp-based processing](https://aws.amazon.com/about-aws/whats-new/2026/10/amazon-dynamodb-streams-timestamp-processing/)
- [Filtered export to S3](https://aws.amazon.com/about-aws/whats-new/2026/10/amazon-dynamodb-introduces-filtered-export/)
