# PostgreSQL features Parallax could expose

A prioritized survey, written 2026-11-20 against Parallax revision `feaab4560`. Production use is PostgreSQL today, so the question is which PostgreSQL features would most improve performance or functionality for an application, and how each could be surfaced neutrally enough that MariaDB or MongoDB could honour the same declaration where they have an equivalent. A feature does not need an equivalent everywhere.

Statement-level ideas — modifying CTEs, relation-bound coverage reads, JSONB key removal — are out of scope here; [PostgreSQL compatibility for Parallax workloads](postgresql-vendor-compatibility.md) covers them.

## How far to trust this

- **Measured.** The PostgreSQL behaviours in [What PostgreSQL 18.6 does](#what-postgresql-186-does) were run on a throwaway `postgres:18.6` container. The script is in the [appendix](#appendix-probe-script).
- **Read from the repository.** Statements about what Parallax emits or omits come from the specifications and ADRs linked beside them.
- **Recalled, not tested.** Every MariaDB and MongoDB statement is from vendor documentation as remembered, and no MariaDB or MongoDB server was run. Two PostgreSQL statements are also untested and are marked where they appear: that an exclusion constraint has no concurrent build path, and the error a locker sees when a row moves between partitions.
- **Illustrative.** Every descriptor, binding, and API spelling below is a sketch of a shape, not a proposed name.

## Where each kind of fact should live

None of the features below is tapped today: the specifications declare no partitioning, no partial or expression index, no storage parameter, no foreign key, no online DDL, and no row lock other than the shared one. Before adding any, each needs a home, and four homes cover all of them.

| Home | What belongs there | Why |
|---|---|---|
| Model (descriptor) | Intent every backend can interpret: which rows an index covers, that a document member is indexed | It changes what the author means, and a backend either honours it or says why it cannot |
| [Database Binding](../../core/spec/m-database-binding.md) | Physical deployment facts: partitioning, storage and maintenance parameters | It is already keyed by `backend` and already varies per deployment, so a PostgreSQL-only knob never reaches the model. It only places tables and sequences today, so widening it is a design decision of its own |
| Database Root options | Per-execution behaviour: lock mode, durability, replica freshness | These follow the existing rule that boundary option defaults belong to the root |
| The dialect's answer | A backend with no equivalent | The schema DDL rule already has a dialect answer with its statement or with a neutral reason it cannot spell one ([`m-dialect`](../../core/spec/m-dialect.md#schema-ddl-primitives-m-schema-delta)) |

## What PostgreSQL 18.6 does

| Probe | Result |
|---|---|
| Partition a temporal table by `out_z`, keeping the table-level exclusion | Refused: `EXCLUDE constraint on table "a" lacks column "out_z" which is part of the partition key` |
| The same split, with the exclusion declared on each partition instead | Accepted. A current row overlapping a closed row in the other partition is then admitted |
| Hash-partition by the logical key, keeping the table-level exclusion | Accepted, and the overlap is still refused |
| List-partition a table-per-hierarchy table by its tag, key without the tag | Refused. With the tag in the key, the same `id` is accepted in two subtypes |
| Partial index `where out_z = 'infinity'`, infinity bound as a parameter, generic plan | Parallel sequential scan |
| The same read with infinity as a literal, or under a custom plan | The partial index is used |
| 10,000 milestone closes (`set out_z = …`) at fillfactor 70 | 0 heap-only (HOT) updates |
| 10,000 updates of a non-indexed column at fillfactor 70 | 4,330 HOT updates |

Three consequences shape the ranking:

1. The exclusion of [ADR 0079](../adr/0079-postgresql-storage-refuses-overlapping-history-and-its-conflicts-are-retried.md) and a time-based partition key cannot coexist as one table-level constraint. A partition key drawn from the logical key can.
2. A current-row index is usable only if a Latest read spells infinity as a literal. Under PostgreSQL's default plan cache mode the bound form would probably keep working through custom plans, replanning on every execution; that was not measured.
3. A milestone close is never a HOT update, because every index of a temporal table ends with `out_z` ([`m-storage-layout`](../../core/spec/m-storage-layout.md#physical-indices)). Each amendment leaves one dead heap tuple and one dead entry in every index.

## Prioritized list

### 1. Current-row and covering indexes

Every index on a temporal table spans all history. An index over current rows alone is smaller by the average number of versions per key, and reads at the present Transaction Time are the path [ADR 0094](../adr/0094-indices-on-bitemporal-tables-end-with-the-transaction-time-end-first.md) names as the one to optimize. Covering columns allow an index-only read of a hot projection.

```yaml
indices:
  - name: balance_by_account
    attributes: [accountId]
    rows: current          # default: all
    include: [amount]
```

| Backend | Rendering |
|---|---|
| PostgreSQL | `create index … (account_id) include (amount) where out_z = 'infinity'`; the appended `out_z` end is constant and drops out |
| MariaDB | No partial index. Build the full index: the predicate is implied, so a non-unique index loses only size |
| MongoDB | `partialFilterExpression`, native |

- **Precondition.** Latest reads must render infinity as a literal rather than a bind. That changes golden SQL across the temporal cases.
- **Index-only reads depend on vacuum.** A covering index pays off only while the visibility map is current, which ties this item to item 3.
- **Follow-on index kinds.** The same declaration could later carry a folded component for the `lower(…)` comparisons Parallax emits, a trigram index for substring `LIKE`, and a block-range index on `in_z` for audit windows. Each is a smaller decision once the declaration can vary.

### 2. Online schema changes

Creating an index on a large live table blocks writes for the length of the build. Every production deployment that evolves its model will meet this.

```python
schema_delta(earlier, later, binding, availability="online")
```

| Backend | Rendering |
|---|---|
| PostgreSQL | `create index concurrently`, constraints added `not valid` and validated afterwards, a `lock_timeout` preamble |
| MariaDB | `algorithm=inplace, lock=none`, or instant column adds |
| MongoDB | Index builds already do not block |

- **Prefix safety.** Statements are prefix-safe and deliberately not idempotent ([`m-schema-delta`](../../core/spec/m-schema-delta.md)). A failed concurrent build leaves an invalid index behind, so an online rendering needs a drop-if-invalid step, and a concurrent build cannot run inside a transaction.
- **The temporal exclusion.** As far as recalled, an exclusion constraint cannot be attached from a concurrently built index, so adopting it on a large existing table stays a blocking migration. Untested.

### 3. Maintenance defaults derived from the model, and a health report

Parallax knows each table's write pattern, which an operator otherwise has to infer.

- **Temporal tables.** Dead tuples accrue at one per amendment in the heap and in every index, and fillfactor cannot help because a close is never HOT. Autovacuum's default threshold is 20% of the table, so a 100-million-row history table waits for about 20 million dead rows. Generated DDL should set a small per-table scale factor.
- **Versioned non-temporal tables.** An update that changes only non-indexed columns is HOT when its page has room. A fillfactor around 85–90 keeps that room.
- **Planner statistics.** Skewed keys — a few keys with thousands of milestones — are what moved PostgreSQL 18 onto the GiST index in ADR 0094. A per-column statistics target and a tighter analyze threshold are candidates for the same derived profile, to be measured.

```yaml
# Database Binding, backend: postgres
entities:
  trading.Position:
    maintenance: { profile: derived }   # or explicit storage parameters
```

```python
root.storage_health()
# per Entity: dead-row ratio, last vacuum and analyze, never-used indexes,
# invalid indexes left by a failed concurrent build, sequence headroom
```

Parallax should report rather than run `VACUUM`: the binding specification places provisioning and migration execution with deployment tooling. This item is PostgreSQL-shaped. InnoDB purges on its own and offers persistent-statistics settings as its nearest knob; MongoDB needs nothing comparable.

### 4. Indexes on members stored inside a Structured Column

An Index component is a local Attribute of its Entity, so nothing stored inside a Structured Column can be indexed and a predicate on it scans the table. That covers both layouts:

- **`Columns`, the default.** Each top-level Value Object is one Structured Column holding every nested Value Object and inner Attribute at any depth ([`m-value-object`](../../core/spec/m-value-object.md)). A dotted path such as `Customer.address.geo.country` is filterable and never indexable.
- **`Document`.** Every member outside the direct roles lives in the layout's one Structured Column. [`m-storage-layout`](../../core/spec/m-storage-layout.md#physical-indices) refuses an index naming one and leaves document-path indexes to a separate design.

Both lower through the same nested extraction form, so one index design serves both. The `Columns` case is the larger audience, since it needs no layout opt-in.

```yaml
# Columns layout: a leaf inside a nested Value Object
indices:
  - name: customer_by_country
    attributes: [address.geo.country]

# Document layout: a document-resident member
layout: { document: { column: payload } }
indices:
  - name: order_by_customer
    attributes: [customer.id]
```

| Backend | Rendering |
|---|---|
| PostgreSQL | Expression index over the extraction and its typed cast |
| MariaDB | Indexed virtual generated column over `json_value` |
| MongoDB | An ordinary dotted-path index |

- **Most portable item.** MongoDB has no other kind of index, so this declaration is a prerequisite for the MongoDB prototype (COR-39) and document-collection storage (COR-49).
- **Precondition.** Nested reads bind path segments as parameters — one per segment on PostgreSQL, one whole path on MariaDB ([`m-dialect`](../../core/spec/m-dialect.md#nested-extraction-form-m-value-object)) — and an expression index matches only the literal expression. The segments derive from the model rather than from a caller, so rendering them as literals is safe.
- **Collections are a separate, harder case.** A `many` Value Object member and a scalar collection Attribute are filtered through a quantifier, which PostgreSQL lowers to `exists (… jsonb_array_elements(…))`. No index serves that form: a GIN index needs a containment (`@>`) spelling, so indexing collections means changing the emitted read as well as adding the index. MongoDB's multikey index covers it natively.

### 5. Partitioning

Three shapes were considered.

| Shape | Verdict | Reason |
|---|---|---|
| Hash by the model key | Recommended first | Keeps the key and the exclusion. Indexes are smaller and vacuum runs per partition. A read that does not carry the key probes every partition |
| Current and history split on `out_z` | Needs a decision | Gives cheap retention and archival, an append-only history partition, and a small hot partition. It gives up the cross-partition overlap guarantee, and every close becomes a row move between partitions |
| By table-per-hierarchy tag | Not recommended | Loses family-wide key uniqueness, and table-per-concrete-subtype already is that physical split |

```yaml
# Database Binding
entities:
  trading.Position:
    partitioning: { by: key, partitions: 16 }
    # later: { by: history, closed: { every: P1Y } }
```

| Backend | Rendering |
|---|---|
| PostgreSQL | `partition by hash (<key>)`; `partition by range (out_z)` for the split |
| MariaDB | `partition by key`, `hash`, or `range`, under the same rule that a unique key contains the partition column. Its native current-and-history split exists only for system-versioned tables, which Parallax does not use |
| MongoDB | `by: key` is a hashed shard key. There is no current-and-history analogue beyond archive collections |

- **Opt-in, never a default.** Measured on PostgreSQL 18.6 against the same table unpartitioned — 2 million rows, 400,000 keys with five milestones each, all in cache, one prepared-statement client, `jit=off`:

  | Statement | Unpartitioned | 16 hash partitions |
  |---|---|---|
  | Current row of one key | 0.006 ms | 0.016 ms |
  | Current rows of 10 keys (`id = any(…)`) | 0.018 ms | 0.141 ms |
  | Current rows of 10 values of an indexed non-key column | 0.062 ms | 0.230 ms |
  | Seek page of 50 ordered by key | 0.016 ms | 0.079 ms |
  | Grouped update of 200 keys joined to a relation | 2.04 ms | 2.32 ms |
  | Insert of 200 rows | 1.98 ms | 1.45 ms |
  | Total size | 399 MB | 447 MB |
  | Relations | 4 | 68 |

  Key reads cost 3–8× more at this size, because a multi-key read probes every partition its keys hash to and an ordered page merges all sixteen. The grouped update prunes per joined row and loses little; inserts gain from smaller GiST trees. The benefits — vacuum per partition, shallower indexes — appear only on tables far larger than memory.
- **Authored unique indexes.** PostgreSQL refuses a unique index on a partitioned table unless it contains the partition key, so an authored unique Index that omits the model key cannot be created. A binding should refuse partitioning for such an Entity.
- **Online index builds.** `create index concurrently` is refused on a partitioned table; item 2 would have to build per partition and attach.
- **Fixed count.** Changing the partition count means rewriting the table, and a hash partition cannot be dropped to retire old history.
- **The split's open decision.** Losing the cross-partition exclusion would revive the question ADR 0079 deferred: the in-statement lineage guard becomes the only protection against a current row opened inside closed history.
- **Row movement.** A close would delete from the current partition and insert into history. A concurrent locker of the moved row fails with an error about the tuple having moved to another partition; its SQLSTATE and Parallax's classification of it are untested.
- **Item 1 first.** A current-row index delivers most of the read benefit of the split without this trade.

### 6. Read-your-writes on the reader route

The `reader` route exists and is specified as possibly lagging the writer ([`m-db-port`](../../core/spec/m-db-port.md)). A commit position would let a caller read from a replica without missing its own write.

```python
receipt = root.transaction(work)
root.read(query, policy=ReaderPreferred(after=receipt.position))
```

| Backend | Rendering |
|---|---|
| PostgreSQL | Compare the commit LSN with the replica's replay LSN, and fall back to the writer when the replica is behind |
| MariaDB | GTID with `master_gtid_wait` |
| MongoDB | Causal-consistency sessions |

All three backends have an equivalent, and the fallback fits the existing Route Selection and its fallback reason.

### 7. Foreign keys from relationships

The delta algebra emits no foreign key ([`m-schema-delta`](../../core/spec/m-schema-delta.md#statement-order)).

| Backend | Rendering |
|---|---|
| PostgreSQL | `deferrable initially deferred` keys between non-temporal Entities, which enforce integrity at commit without constraining write-group order |
| MariaDB | Foreign keys are checked immediately and cannot be deferred, so write order would have to satisfy them |
| MongoDB | None |

Temporal tables are not expressible: PostgreSQL 18's `PERIOD` foreign keys need a range-typed column and a `WITHOUT OVERLAPS` key, and Parallax stores two timestamps per axis. This is the least portable item on the list.

### 8. Smaller items

| Feature | Sketch | MariaDB | MongoDB |
|---|---|---|---|
| Queue-style locking (`for update skip locked`, `nowait`) | `lock=Exclusive(skip_locked=True)` | 10.6 and later | `findOneAndUpdate` |
| Relaxed durability (`synchronous_commit`) | Root or transaction option `durability="relaxed"` | Global setting only | Write concern |
| Bulk load (`COPY` binary) | `root.bulk_insert(Entity, rows)` | `load data` | `insertMany` |
| Time-ordered UUID keys | `pkGeneration: {strategy: uuid-v7}`, generated in the client | Same | ObjectId is already time-ordered |
| Upsert (`on conflict do update`) | A keyed save | `on duplicate key update` | `upsert: true` |
| Change feed (logical decoding) | `root.changes(Entity, since=token)` | Binary log | Change streams |

- **Bulk load.** Inserts already bind one array per Column, so the gain over the existing form is for backfills and migrations. Measure before building.
- **Upsert.** It cuts against the observed-write model: `m-unit-work` requires a source's authority before anything opens, so that a replacement is never an upsert.
- **Session defaults.** `jit` and `plan_cache_mode` are adapter session settings worth measuring on short prepared statements; ADR 0094's evidence ran with `jit=off`.

### Not recommended

- **PostgreSQL 18 `WITHOUT OVERLAPS` keys.** One axis only, a range-typed column, and still GiST underneath, so nothing is gained over the present exclusion. MariaDB's `WITHOUT OVERLAPS` is the plausible route for one axis of COR-246.
- **Row-level security, advisory locks, full-text and vector indexes.** No Parallax use case calls for them yet.

## Appendix: probe script

Run against `postgres:18.6` with `psql -q` and errors allowed to continue.

```sql
create extension btree_gist;

-- A: current/history split on out_z, table-level exclusion over the range
create table a (id bigint not null, amount numeric, in_z timestamptz not null, out_z timestamptz not null,
  constraint a_pk primary key (id, out_z),
  constraint a_x exclude using gist (id with =, tstzrange(in_z, out_z) with &&)
) partition by range (out_z);

-- A2: the same split, exclusion declared per partition
create table a (id bigint not null, amount numeric, in_z timestamptz not null, out_z timestamptz not null,
  constraint a_pk primary key (id, out_z)) partition by range (out_z);
create table a_hist partition of a for values from (minvalue) to ('infinity');
create table a_cur  partition of a for values from ('infinity') to (maxvalue);
alter table a_hist add constraint a_hist_x exclude using gist (id with =, tstzrange(in_z, out_z) with &&);
alter table a_cur  add constraint a_cur_x  exclude using gist (id with =, tstzrange(in_z, out_z) with &&);
insert into a values (1, 10, '2026-01-01', 'infinity');
update a set out_z = '2026-02-01' where id = 1 and out_z = 'infinity';   -- moves to a_hist
insert into a values (1, 11, '2026-02-01', 'infinity');
insert into a values (2, 1, '2026-01-01', '2026-03-01');
insert into a values (2, 2, '2026-02-01', 'infinity');                    -- overlaps, accepted
select tableoid::regclass, * from a order by id, in_z;

-- B: hash partition on the logical key keeps the table-level exclusion
create table b (id bigint not null, in_z timestamptz not null, out_z timestamptz not null,
  constraint b_pk primary key (id, out_z),
  constraint b_x exclude using gist (id with =, tstzrange(in_z, out_z) with &&)
) partition by hash (id);
create table b0 partition of b for values with (modulus 2, remainder 0);
create table b1 partition of b for values with (modulus 2, remainder 1);
insert into b values (2, '2026-01-01', '2026-03-01');
insert into b values (2, '2026-02-01', 'infinity');                       -- refused

-- C: table-per-hierarchy list partition by tag
create table c (id bigint primary key, kind text not null) partition by list (kind);   -- refused
create table c (id bigint, kind text not null, primary key (id, kind)) partition by list (kind);
create table c_a partition of c for values in ('a');
create table c_b partition of c for values in ('b');
insert into c values (1, 'a');
insert into c values (1, 'b');                                            -- accepted

-- D: partial index and a bound infinity
create table d (id bigint, acct bigint, in_z timestamptz, out_z timestamptz, primary key (id, out_z));
insert into d
select g, g % 1000, now() - (g % 50) * interval '1 day',
       case when g % 50 = 0 then 'infinity'::timestamptz
            else now() - (g % 50) * interval '1 day' + interval '1 hour' end
from generate_series(1, 200000) g;
create index d_cur on d (acct) where out_z = 'infinity';
analyze d;
set plan_cache_mode = force_generic_plan;
prepare p1(bigint, timestamptz) as select id from d where acct = $1 and out_z = $2;
explain (costs off) execute p1(7, 'infinity');                            -- sequential scan
prepare p2(bigint) as select id from d where acct = $1 and out_z = 'infinity';
explain (costs off) execute p2(7);                                        -- d_cur
set plan_cache_mode = force_custom_plan;
explain (costs off) execute p1(7, 'infinity');                            -- d_cur

-- E: a close is never HOT; a non-indexed update is
create table e (id bigint, v int, in_z timestamptz, out_z timestamptz, primary key (id, out_z)) with (fillfactor = 70);
create table f (like e including all) with (fillfactor = 70);
insert into e select g, 0, now(), 'infinity' from generate_series(1, 10000) g;
insert into f select g, 0, now(), 'infinity' from generate_series(1, 10000) g;
update e set out_z = now() where true;
update f set v = v + 1 where true;
select pg_stat_force_next_flush();
select pg_sleep(1);
select relname, n_tup_upd, n_tup_hot_upd from pg_stat_user_tables where relname in ('e', 'f') order by 1;
```
