# Indices on Bitemporal tables end with the Transaction-Time end first

This supersedes part of
[ADR 0081](0081-authored-indices-on-temporal-tables-end-with-the-axis-ends.md):
its order for the axis ends, Valid Time before Transaction Time. ADR 0081's other
decisions stand: every index of a temporal table ends with the derived axis ends,
and an authored unique index means uniqueness per milestone end. The derived key
of [ADR 0050](0050-primary-key-index-is-derived.md) and the end columns of
[ADR 0051](0051-temporal-physical-key-uses-axis-end-columns.md) stand too; only
the order they first spelled for the two ends changes.

The derived primary key of a Bitemporal Entity is its model key, then the
Transaction-Time end, then the Valid-Time end: `(key, out_z, thru_z)` rather than
`(key, thru_z, out_z)`. Every authored index on a Bitemporal table ends the same
way, so one ending rule still covers every index of a temporal table
(`m-storage-layout` *Physical primary key*, *Physical indices*). The rule is a
derived-layout rule, so every dialect inherits it. On MariaDB the primary key is
InnoDB's clustered index, so each key's current rows would also be stored
together; that is to be measured when the MariaDB adapter ships, and is not a
condition of this decision. Transaction-Time-only tables have one end and are
unaffected.

Only index component order changes. Read and DML statements keep their
predicates and binds, uniqueness is defined over column sets and is unchanged,
and the GiST exclusion, its name and its retry classification
([ADR 0079](0079-postgresql-storage-refuses-overlapping-history-and-its-conflicts-are-retried.md))
are unchanged. So are column and projection order, `from_z, thru_z, in_z, out_z`,
and descriptor canonical export, which keeps authored components alone. A
statement whose own rule renders every key column in key order, such as a
locking read's join back to its base table, lists the key's columns in the new
order. Both kept rationales hold: a Latest predicate and a milestone close pin
both ends, so each remains a key hit.

## Why

Reads at the present Transaction Time, `out_z = 'infinity'` with a finite Valid
Time, are the case to optimize. They include every licensing read for an observed
Bitemporal write, every coverage read inside a flush, target writes' reads, and
ordinary `as_of(valid_time=…)` reads. Reads at a past Transaction Time are
read-only (`transaction-time-pin-read-only`), never on the write path, and may
cost more per key.

On PostgreSQL 18, the only supported major, the old order made the planner
abandon the key for those reads and fall back to the GiST exclusion index, at
4–25× the real cost. PostgreSQL 18 costs a btree scan whose second column is a
range far higher than PostgreSQL 16 does (683 against 62 for the same scan),
then picks the GiST index, uses it only as a key index, and reads every row of
the key. PostgreSQL 16 never picked GiST; there, the two orders mirror each
other.

## Evidence

Measured on 2026-11-14 at `ab94a5ff4` on PostgreSQL 18.7, with 16.14 for
information only. The table was generated `price` DDL with the exclusion
`(sku =, tstzrange(from_z, thru_z) &&, tstzrange(in_z, out_z) &&)`, holding about
4.1M rows in each of four history shapes: amend from a date, where closed rows
keep `thru_z = infinity`, and window corrections, where closed rows have a
finite `thru_z`, each with 20k keys of 50 changes plus 10 hot keys of 2,000. The
heap was loaded in `in_z` order, indices built afterwards, then `VACUUM ANALYZE`,
with `shared_buffers=1GB` and `jit=off`. Each reading is the median of five runs
after one warm-up, under per-call and generic plans.

The key, on PostgreSQL 18 (index chosen, time):

| Read | `(sku, thru_z, out_z)` | `(sku, out_z, thru_z)` |
| -- | -- | -- |
| R1 licensing read `sku = any(?) and from_z <= V and thru_z > V and out_z = ∞`, 50 keys, recent V | GiST, 2.84 ms | key, 0.12 ms |
| R1, one hot key, generic plan | GiST, 1.35 ms | key, 0.003 ms |
| R1, one typical key | GiST, 0.05–0.06 ms | key, 0.004–0.016 ms |
| R2 coverage read `sku = ? and thru_z > V and out_z = ∞` | GiST for typical keys and every generic plan, up to 1.46 ms | key, ≤ 0.24 ms |
| R3 Latest/Latest | key, ≤ 0.09 ms | key, ≤ 0.10 ms |
| R4 past Transaction Time, Latest Valid Time `thru_z = ∞ and in_z <= t and out_z > t`, 50 keys | key, 0.11–0.67 ms | GiST, ~3.0 ms |
| R5 past Transaction Time, finite Valid Time | mostly GiST | mostly GiST |
| R6 close, every key column by equality | key, 0.12 / 0.42 ms | key, 0.13 / 0.44 ms |
| Writes, 20k-key amend from date | 7,870 ms | 7,867 ms |

An authored index, on PostgreSQL 18, through `(supplier_id, …)` with a
`supplier_id` constant per key: typical suppliers own about 20 keys and big ones
about 2,000, and per-key timestamps carry millisecond jitter so that btree
deduplication does not hide the effect of order. Early V and t; index pages, then
milliseconds per-call / generic:

| Read | Ends `thru_z, out_z` | Ends `out_z, thru_z` |
| -- | -- | -- |
| S1 present Transaction Time, big supplier, window shape | 949 pages, 8.2 / 6.5 ms | 476 pages, 5.1 / 5.0 ms |
| S1, big supplier, amend shape | 481 pages, 5.3 / 5.9 ms | 477 pages, 4.2 / 4.3 ms |
| S5 present Transaction Time, 50 typical suppliers | 583–673 pages, 3.3–4.4 ms | 432–436 pages, 3.5–3.6 ms |
| S3 past Transaction Time, Latest Valid Time, big supplier, window shape | 3 pages, 0.003 ms | 480 pages, 0.7 ms |
| S4 past Transaction Time, finite Valid Time, big supplier, generic plan | 10.5 ms | 26.5 ms |
| Writes | equal | equal |

The planner never chose GiST, the primary key or a sequential scan for the
authored index. Verification is the generated DDL and these measurements: no test
asserts the planner's choice, and no cost workload was added.

## Accepted trade-offs and known limitations

- **R4 through the key** falls to GiST, at about 3 ms per 50 keys and growing with
  key history.
- **Past-Transaction-Time reads through authored indices** get slower: S3 goes
  from 3 to 480 pages. S4 under a generic plan goes from 10.5 to 26.5 ms because
  of a PostgreSQL 18 costing cliff: a range on `out_z` followed by a `thru_z`
  condition is costed so high that the planner switches from a bitmap scan to a
  plain index scan in index order.
- **R5**, past Transaction Time with a finite Valid Time, uses GiST under every
  order considered. It is a known limitation outside this decision.

An audit-heavy deployment that relies on R4 or S3 reads can add an index with the
old ending in its own migrations. On PostgreSQL 18 the reordered key plus such an
index served every R4 read at the old speed. Parallax cannot declare it, because
the ending is derived and an authored component naming an axis end is refused, by
every frontend, as `metamodel-index-temporal-attribute`
([ADR 0095](0095-model-formation-refuses-an-authored-index-naming-an-axis-endpoint.md));
a schema delta drops only
indices an earlier model edition declared, so it never touches one. The Python
binding's modeling guide documents it.

## Prior art

Reladomo generates the order Parallax had: it appends each axis's end column to
the declared key, business date (Valid Time) before processing date, through an
explicit canonical sort, `AsOfAttributeComparator`
(`generator/MithraObjectTypeWrapper.java:3600-3608`), and authored indices get
the same ending
([prior art](../research/reladomo/06-bitemporal-milestoning.md)). Nothing claims a
read advantage for that order; the derivable rationale is the update and delete
key hit, which both orders keep. Reladomo's `DatabaseIndexValidator` accepts any
primary key or unique index that is a superset of the key plus end columns, so it
accepts the reorder. Reladomo's cache also changes the picture: it keys dated
objects separately and serves many as-of reads from memory, while Parallax sends
every read to the database. Parallax departs from Reladomo on the evidence above.

## Migration

A schema delta compares two model editions compiled under the current rules and
never reads the catalog, so the change reaches an existing table only by a manual
migration (`m-schema-delta` *Physical Index Names*), as ADR 0079 also chose. There
is no model-evolution operation and no check at connect. Existing tables keep
working, with the old performance, until migrated, because uniqueness and SQL
meaning are unchanged. The primary-key name's fingerprint covers key columns in
key order, and Physical Index Names cover the index's columns in order, so both
change; the exclusion's name does not. Operators take the target names from fresh
provisioning output, and the Python release notes give the procedure.

## Rejected alternatives

- **Keep the key and derive a second `(key, out_z, thru_z)` index on every
  Bitemporal table.** It is the right btree for R1–R4 on PostgreSQL 18, and its
  write cost is hidden today (+0.5%). But every table and write would permanently
  pay for a second btree (+159 MB on the test table, +62% of btree-only write time
  once GiST maintenance no longer masks it) to serve the minority read, and the
  derived layout would grow a companion index with its own ordering and naming
  rule.
- **Leave the order as is.** It keeps the GiST fallback on the licensing read on
  the only supported major.
- **Make the exclusion unusable for reads**, for example with `collate "C"` on
  its key. It works only for text keys and is cryptic.
- **Keep the old ending for authored indices only.** That is two ending rules for
  one table, and present-Transaction-Time reads through authored indices keep
  scanning closed history.
- **A test asserting the planner's choice, or a new live-database cost
  workload.** Plan choice depends on the PostgreSQL version, statistics and data
  shape, and a workload would force a recapture for a path no current workload
  covers.
