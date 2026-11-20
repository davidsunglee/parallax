# PostgreSQL compatibility for Parallax workloads

A vendor evaluation brief, based on Parallax revision `bda15087c`. The Python adapter targets PostgreSQL `>=18.6,<19`. The SQL below uses illustrative table names and PostgreSQL positional parameters. The source links identify emitted forms and existing tests. The proposed statements are design probes. No vendor endpoint was tested. [Adapter version declaration](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/languages/python/packages/parallax-postgres/pyproject.toml) · [SQL contract](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/core/spec/m-sql.md)

## What to demonstrate first

1. **Update 1,000 independently versioned rows in one statement.** Send a handful of real binary array parameters. Make input 317 stale. Return the ordinals of the other 999, in any order. The caller must be able to identify input 317 and roll back the transaction. Repeat with a delete, a JSONB patch and a matched update that sets a column to itself. [Grouped-effect contract](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/core/spec/m-sql.md#grouped-effects) · [Provider tests](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/languages/python/tests/provider_contract/test_postgres_grouped_effects.py)
2. **Have two sessions insert overlapping history for one business key.** Even when the rows have different physical primary keys, at most one may commit. Check the SQLSTATE and constraint name. Repeat with intervals that just touch, and with rectangles that overlap on only one axis. Both of those controls should succeed. [Temporal exclusion tests](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/languages/python/tests/provider_contract/test_postgres_temporal_exclusion.py) · [Storage decision](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/docs/adr/0079-postgresql-storage-refuses-overlapping-history-and-its-conflicts-are-retried.md)
3. **Fetch a bounded page late in an indexed table, crossing into NULL sort keys.** Check rows, order, and the actual plan. Repeat with a concurrent update while the reader waits on a shared lock. The page must return the locked base-row values. Also try one child fetch with more than 65,535 keys in a single array parameter. [Seek and lock tests](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/languages/python/tests/provider_contract/test_postgres_seek_locking.py) · [Large-array tests](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/languages/python/tests/provider_contract/test_postgres_authored_memberships.py)
4. **Run the examples through psycopg against the offered endpoint.** Compare small and large batches over the same prepared SQL. Report server plans, statements, protocol synchronizations and end-to-end latency separately. A translated statement that fans out into 1,000 backend calls can return the right rows and still lose the reason Parallax emits it. [PostgreSQL adapter](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/languages/python/packages/parallax-postgres/src/parallax/postgres/_connection.py) · [PostgreSQL pipeline protocol](https://www.postgresql.org/docs/18/libpq-pipeline-mode.html)

## DML and reads in use today

**Batch writes.** A singleton uses scalar `VALUES`. A batch binds one typed array per column and zips the arrays positionally. SQL text and parameter count stay constant as the row count changes. Nullable cells, exact numeric values, UUIDs, byte strings, JSONB documents and open-ended timestamps must survive binding. A JSONB array parameter can contain a complete document per row. [Batch SQL](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/core/spec/m-sql.md#batched-insert--update) · [Multi-row insert tests](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/languages/python/tests/provider_contract/test_postgres_multi_row_inserts.py)

```sql
INSERT INTO px.account (id, owner, balance)
SELECT * FROM unnest($1::bigint[], $2::text[], $3::numeric[]);

UPDATE px.ledger AS t
SET payload = t.payload || v.patch, version = v.new_version
FROM unnest($1::bigint[], $2::integer[], $3::integer[], $4::jsonb[])
     WITH ORDINALITY AS v(id, expected_version, new_version, patch, ord)
WHERE t.id = v.id AND t.version = v.expected_version
RETURNING v.ord;

DELETE FROM px.ledger AS t
USING unnest($1::bigint[], $2::integer[])
      WITH ORDINALITY AS v(id, expected_version, ord)
WHERE t.id = v.id AND t.version = v.expected_version
RETURNING v.ord;
```

The returned value comes from the **input relation**. Affected-row totals alone lose the failed input's identity. An unchanged temporal guard can be `SET in_z = t.in_z` and still has to count or return its matched row. Uniform updates and unversioned deletes can use `id = ANY($1::bigint[])`; composite targets use `(a,b) IN (SELECT * FROM unnest($1::bigint[], $2::text[]))`. The latter must preserve pairs. Independent membership tests on each column would write additional rows. Predicate-selected updates and deletes can select target keys via a joined subquery over the target table in the same statement. [Grouped effects](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/core/spec/m-sql.md#grouped-effects) · [Predicate-selected writes and isolation](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/core/spec/m-batch-write.md)

| Read surface | PostgreSQL behavior Parallax uses |
|---|---|
| Ordinary queries | Bound comparisons, ranges, NULL tests, `LIKE … ESCAPE`, `lower`, Boolean three-valued logic, explicit NULL ordering, ordered multi-column limits. [Predicate SQL](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/core/spec/m-sql.md#per-operator-sql-emission) |
| Relationships and deep fetch | Shared `LEFT JOIN` chains where cardinality is proven, correlated scalar subqueries elsewhere, and correlated `EXISTS` / `NOT EXISTS`. A scalar subquery with several rows must raise a cardinality violation. Child fetches gather parent keys into typed `ANY` parameters. [Relationship SQL](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/core/spec/m-sql.md#relationship-predicates) · [Deep fetch](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/core/spec/m-sql.md#deep-fetch--one-statement-per-relationship-level) |
| Pagination and inheritance | Lexicographic seeks with a leading index range. For a NULL tail, disjoint `UNION ALL` arms have individual order and limits, followed by a global order and limit. Locking pages join back on the complete physical key for `FOR SHARE OF` the base alias. Polymorphic reads also use typed NULL projections across concrete-table unions. [Seek SQL](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/core/spec/m-sql.md#continuation-coordinates--capture-seek-rebind) · [Inheritance SQL](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/core/spec/m-sql.md#inheritance--table-per-concrete-subtype-lowering) |
| Document queries and writes | `jsonb_extract_path` / `jsonb_extract_path_text` with bound path segments, typed casts, `jsonb_typeof`, guarded `jsonb_array_elements`, correlated collection quantifiers and scalar text extraction with `#>>`. Preserve SQL NULL, JSON null and absence where observable. A subtype-filtered derived table can use `OFFSET 0` to keep an incompatible subtype's value out of a cast. Amendments already use the shallow, right-biased `payload \|\| $1::jsonb` merge. An assigned subtree is replaced whole and unrelated top-level keys survive. [Document SQL](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/core/spec/m-sql.md#relational-document-layout--document-path-predicates-and-ordering) · [Document mutations](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/core/spec/m-dialect.md#document-mutation-expression-form-m-storage-layout) |
| History | Latest reads compare the upper bound to a bound native `timestamptz` infinity. A point read uses `in_z <= $1 AND out_z > $1`; a window uses `in_z < $end AND out_z > $start` (symbolic parameter names). Bitemporal reads compose both axes. Coverage reads can take row locks. [Temporal SQL](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/core/spec/m-sql.md#temporal-predicates-and-write-sequences) |

**What a temporal amendment costs today.** For a compatible batch of deferred transaction-time amendments, the shape can be one shared current-row read, one grouped predecessor close or guard, and one successor insert. If the unit already holds the rows it needs, acquisition can disappear. A conditional optimistic transaction-time termination can go straight to its gated close. In a bitemporal amendment, the unit may first acquire multiple overlapping predecessors, close them, revise or remove rows its own transaction opened, and insert the surviving and changed pieces. Compatible openings already share an insert. Eligible consecutive count-only effects can also travel in an ordered protocol pipeline with individual results. Transaction begin/commit and earlier reads are additional costs. Reladomo is prior art for the close-and-reopen and rectangle-splitting model. [Temporal execution decision](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/docs/adr/0096-transaction-time-only-writes-share-coverage-reads-and-an-optimistic-termination-reads-nothing.md) · [Flush execution](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/core/spec/m-execution.md#flush-execution) · [Reladomo prior art](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/docs/research/reladomo/06-bitemporal-milestoning.md)

## DDL, types and diagnostics

The distinctive DDL is a constraint over **logical key equality and range overlap**. A transaction-time table uses one range. A bitemporal table uses both ranges in one exclusion. The ordinary primary key also matters. This representative table shows both constraints. [DDL contract](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/core/spec/m-dialect.md#schema-ddl-primitives-m-schema-delta) · [PostgreSQL range constraints](https://www.postgresql.org/docs/18/rangetypes.html#RANGETYPES-CONSTRAINT)

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE px.position (
    id bigint NOT NULL,
    amount numeric(18,2) NOT NULL,
    from_z timestamptz NOT NULL, thru_z timestamptz NOT NULL,
    in_z   timestamptz NOT NULL, out_z  timestamptz NOT NULL,
    CONSTRAINT position_pk PRIMARY KEY (id, out_z, thru_z),
    CONSTRAINT valid_interval CHECK (from_z < thru_z),
    CONSTRAINT tx_interval CHECK (in_z < out_z),
    CONSTRAINT position_no_overlap EXCLUDE USING gist (
        id WITH =,
        tstzrange(from_z, thru_z) WITH &&,
        tstzrange(in_z, out_z) WITH &&
    )
);
```

The default range is half-open. The exclusion must apply immediately to every writer, including direct SQL clients. On a managed service, ask how a tenant obtains `btree_gist` and its scalar operator classes. A vendor-native equivalent is worth discussing separately if it would require different generated DDL or different diagnostics. [History constraint decision](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/docs/adr/0079-postgresql-storage-refuses-overlapping-history-and-its-conflicts-are-retried.md)

| Surface | Current requirement |
|---|---|
| Tables and evolution | Schema-qualified and quoted identifiers, scalar/composite primary keys, named checks, multi-column `CREATE [UNIQUE] INDEX`, schema-qualified `DROP INDEX`, `ALTER TABLE ADD COLUMN`, `ALTER COLUMN … TYPE` and `DROP NOT NULL`. Temporal authored indexes append the temporal end columns. A document-root check uses `jsonb_typeof(payload) = 'object'` alongside required-column enforcement. [Schema delta](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/core/spec/m-schema-delta.md) · [Indexes on temporal tables](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/languages/python/tests/provider_contract/test_postgres_temporal_authored_indices.py) |
| Physical types | Boolean, integer, bigint, real, double precision, exact numeric with precision and scale, text and bounded varchar, bytea, date, time, timestamptz with native positive infinity, UUID and JSONB. Support corresponding typed array parameters and codecs, including binary array element OIDs. [Dialect mapping](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/core/spec/m-dialect.md) · [Binary adapter](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/languages/python/packages/parallax-postgres/src/parallax/postgres/_connection.py) |
| Pooled generated keys | `CREATE / ALTER / DROP SEQUENCE`, integer/bigint, configurable increment, bounds, start and `NO CYCLE`. Reservation combines `pg_catalog.nextval`, `pg_sequence`, `to_regclass` and `format_type` in one query. A rolled-back business transaction must not reissue its reserved block. Migration uses `setval`, `last_value`, `is_called` and the maximum existing key across consuming tables. [Exact sequence SQL](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/core/spec/m-dialect.md#native-sequences) · [Sequence tests](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/languages/python/tests/provider_contract/test_postgres_key_sequences.py) |
| Transactions and errors | Commit/rollback, savepoints, read-only/read-write transactions, Read Committed, Repeatable Read and Serializable, shared row locks and lock waits. Preserve SQLSTATE and object diagnostics, especially named exclusions (`23P01`), unique and check failures (`23505`, `23514`), serialization (`40001`), deadlock (`40P01`) and lock timeout (`55P03`). Parallax uses the failed constraint's identity to decide which history conflicts qualify for retry. [Database errors](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/core/spec/m-db-error.md) · [Overlap retry decision](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/docs/adr/0079-postgresql-storage-refuses-overlapping-history-and-its-conflicts-are-retried.md) |
| Existing Python adapter | Extended query protocol, parameter binding, prepared statements, per-statement command tags and results, pipeline synchronization and error recovery. Startup reads real values for infinity, JSONB, float4/float8 and `session_user`; it expects UTF-8 and ISO DateStyle. Role-scoped execution also needs `SET ROLE` / `RESET ROLE`; timeout configuration uses `statement_timeout`. [Startup probe](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/languages/python/packages/parallax-postgres/src/parallax/postgres/_route.py) · [Session setup](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/languages/python/packages/parallax-postgres/src/parallax/postgres/_authorization.py) · [Ordered-write tests](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/languages/python/tests/provider_contract/test_postgres_ordered_writes.py) |

## SQL worth designing for next

**1. Fuse a guarded close and its successor with a data-modifying CTE.** This is the highest-value forward probe. Assume an existing transaction-time balance with only the columns shown, a changed amount already established by settlement, a new transaction instant later than the observed start, and an optimistic gate. A plain first creation already takes one insert. A change to an existing balance creates the dependency that makes `WITH` valuable. Parallax previously explored a hand-written modifying CTE for temporal ranges. That experiment predates the present grouped-write baseline. [Temporal transport investigation](https://linear.app/flimflam/issue/COR-201) · [PostgreSQL modifying CTE semantics](https://www.postgresql.org/docs/18/queries-with.html#QUERIES-WITH-MODIFYING)

```sql
WITH closed AS (
    UPDATE px.balance
    SET out_z = $1
    WHERE id = $2 AND out_z = 'infinity'::timestamptz AND in_z = $3
    RETURNING id
)
INSERT INTO px.balance (id, amount, in_z, out_z)
SELECT id, $4, $1, 'infinity'::timestamptz FROM closed
RETURNING id;
```

One match must close and open at the same instant. A stale start must produce zero successors and a result the caller can classify as stale. Force the insert to violate a check and verify the close also rolls back. Pass predecessor cells through `RETURNING` when a successor must preserve them. PostgreSQL's sibling modifying statements share a snapshot, so reading the base table again is insufficient to communicate an effect. Extend to batches only with exact per-input attribution. A bitemporal split has a higher bar still: preserve unchanged milestones, gaps, head/middle/tail pieces, same-transaction revisions, coalescing and all predecessor gates. Benchmark the incremental gain against the current shared read, grouped close and batched insert. [Range settlement](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/core/spec/m-sql.md#requested-ranges--coverage-read-and-statement-order) · [PostgreSQL modifying CTE semantics](https://www.postgresql.org/docs/18/queries-with.html#QUERIES-WITH-MODIFYING)

**2. Bind bitemporal coverage requests as a relation.** Today a coverage statement can grow a disjunction of key-specific windows. Three zipped arrays could give bounded and open-ended windows a common statement shape. A semijoin returns a predecessor once even if it intersects several requests. Compare plans for sparse and dense windows and add `FOR SHARE OF p` for the locking path. This is a proposed optimization over an existing read. [Current coverage SQL](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/core/spec/m-sql.md#requested-ranges--coverage-read-and-statement-order)

```sql
SELECT p.*
FROM px.position AS p
WHERE p.out_z = 'infinity'::timestamptz
  AND EXISTS (
      SELECT 1
      FROM unnest($1::bigint[], $2::timestamptz[], $3::timestamptz[])
           AS w(id, lo, hi)
      WHERE w.id = p.id AND p.from_z < w.hi AND p.thru_z > w.lo
  );
```

**3. Remove selected JSONB keys and merge the remaining patch.** Explicit unsetting and sparse document storage are backlog work. One candidate SQL form removes top-level keys, then applies assignments. Require a disjoint unset list and assignment object. Test missing keys, explicit JSON null, empty collections and preservation of undeclared sibling keys. The product decision on presence governs when the emitter could use this. [Sparse-document proposal](https://linear.app/flimflam/issue/COR-210) · [PostgreSQL JSONB operators](https://www.postgresql.org/docs/18/functions-json.html)

```sql
UPDATE px.ledger
SET payload = (payload - $1::text[]) || $2::jsonb, version = $3
WHERE id = $4 AND version = $5;
```

**4. Fetch relationships at each historical parent's own instant.** Historical includes are backlog work. A candidate implementation binds parent keys and their temporal coordinates together. Two milestones of the same parent key can legitimately see different children, so return the input ordinal for attachment. The example assumes one time axis and finite pins. A bitemporal version would also carry Valid Time. [Historical includes proposal](https://linear.app/flimflam/issue/COR-86) · [Temporal reads](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/core/spec/m-sql.md#as-of-read-predicates)

```sql
SELECT r.ord, c.*
FROM unnest($1::bigint[], $2::timestamptz[])
     WITH ORDINALITY AS r(parent_id, as_of, ord)
JOIN px.child AS c ON c.parent_id = r.parent_id
                 AND c.in_z <= r.as_of AND c.out_z > r.as_of;
```

**5. Make current-row reads cheaper on history-heavy tables.** A plausible opt-in DDL experiment is a partial B-tree for a common access path, such as the current balances of an account. Measure read cost, index size and close/open write cost at realistic history depth. The present read emitter binds infinity, so examine both custom and generic prepared plans. A generic plan cannot infer a fixed partial-index predicate from an arbitrary parameter. Adoption may require a specialized latest-read spelling. [Current latest-read SQL](https://github.com/davidsunglee/parallax/blob/bda15087c17f9cfdb3076bc9ca33928372d77025/core/spec/m-sql.md#as-of-read-predicates) · [PostgreSQL partial-index matching](https://www.postgresql.org/docs/18/indexes-partial.html)

```sql
CREATE INDEX balance_current_by_account ON px.balance (account_id, id)
WHERE out_z = 'infinity'::timestamptz;
```
