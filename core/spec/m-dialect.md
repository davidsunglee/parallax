# m-dialect — Database Dialect & Portability

All SQL-dialect variation **MUST** live behind a single normative `Dialect`
interface. This is the **only** place dialect-specific SQL is allowed. The
promise "equivalent SQL per database, optimized per dialect" is made enforceable
precisely because dialect divergence is localized to one swappable component.
`m-dialect` depends only on `m-core`.

This mirrors Reladomo's `DatabaseType` seam — obtained from the connection
manager at every SQL decision point, never from a global registry.

The database seam is **normatively decomposed** into three cooperating parts:
this **pure dialect / portability layer** (`m-dialect`), an **abstract runtime
database port** plus its **N concrete adapters** (`m-db-port`), and **error
classification** (`m-db-error`). The pure dialect layer performs **no I/O**: it
holds no connection, opens no socket, and imports no database driver. It is the
single source of truth for every dialect-specific string and every
dialect-specific parse rule — SQL-fragment production (SELECT shape, identifier
quoting, row-limit clause, read-lock application, temp-table DDL), the
neutral-type → column-type mapping, the typed-bind normalization rules, and the
type-parse functions that turn a driver's raw column value into a core managed
value.

## The `Dialect` interface

A `Dialect` is the abstract authority for every dialect-specific decision. With
the second concrete dialect (**MariaDB**) added behind the seam, the full
decision-point catalog is now fixed. Two dialects legitimately make *different*
choices at each point; both are normative for their dialect (`m-sql`). The catalog
(derived from the research matrix, research §11):

| Decision point | Postgres (round-1 concrete) | MariaDB (second concrete) |
|---|---|---|
| `dialect` identifier | `postgres` | `mariadb` |
| type mapping (neutral type → column type) | per the `m-core` Postgres column | per the `m-core` MariaDB column (see below) |
| `SELECT` shape (column list, alias scheme) | `select t0.col, … from tbl t0 where …` | identical |
| identifier quoting | unquoted lowercase; `"…"` quote on demand | unquoted lowercase; **backtick** quote on demand (divergent quote char) |
| row-limit clause | `limit ?` | `limit ?` |
| **read-lock application** (`m-read-lock`) | object find: `for share of t0`; projection/aggregation: omitted | object find: **`lock in share mode`** (no `for share`; MDEV-17514); projection/aggregation: omitted |
| temp-table DDL | `CREATE TEMPORARY TABLE … ON COMMIT DROP` | `CREATE TEMPORARY TABLE …` |
| typed bind normalization | managed values render to canonical `m-core` wire values | timestamp binds remain typed `Instant`/`infinity` so the adapter can render `datetime(6)`/max-sentinel; other values render to canonical `m-core` wire values |
| **infinity representation** | native `'infinity'::timestamptz` | **max-sentinel** `datetime` (no native infinity) |
| error-code classification (`m-db-error`) | SQLSTATE: `23505` unique, `40P01`/`40001` deadlock, `55P03` lock timeout | errno: `1062` duplicate, `1213` deadlock, `1205` lock timeout |

The two decision points MariaDB **diverges** on — the read-lock (application) and
the infinity representation — are exactly the ones the second dialect was chosen
to exercise; they are detailed below. The divergent **type mappings** are
round-tripped against real MariaDB by the scalar witness (compatibility case
`m-core-004`), and the UTC-instant normalization + microsecond precision of
`datetime(6)` by the timestamp write cases (`m-core-002`/`m-core-003`). Error-code
classification is `m-db-error`.

### MariaDB type mapping (the `m-core` table, MariaDB column)

The dialect maps each `m-core` neutral type to a concrete MariaDB column type. The
mappings that **differ** from Postgres:

| Neutral type | Postgres | MariaDB | Why it differs |
|---|---|---|---|
| `boolean` | `boolean` | `tinyint(1)` | MariaDB has no native boolean (`true`/`false` alias `1`/`0`) |
| `timestamp` | `timestamptz` at core microsecond precision | `datetime(6)` | MariaDB `TIMESTAMP` is range-limited (2038) and auto-updates; `DATETIME(6)` is the UTC instant store, preserves the core microsecond precision, and has **no native infinity** |
| `float64` | `double precision` | `double` | spelling |
| `bytes` | `bytea` | `longblob` | |
| `uuid` | `uuid` | `char(36)` | no native UUID type |
| `json` | `jsonb` | `json` | structured-document storage; MariaDB `JSON` is a `longtext` alias |

`int32`/`int64`/`date`/`time`/`decimal(p,s)`/`string` map the same in spirit
(`int`/`bigint`/`date`/`time`/`decimal(p,s)`/`varchar(n)|text`).

Future dialects with a different document type, such as Snowflake `VARIANT`,
map the same `m-core` `json` neutral type behind this seam; the metamodel does not
name the concrete storage type.

### `NULL` ordering

The canonical ordered-relationship rule (`m-deep-fetch`) sorts `NULL`s **last** on
every key. The two dialects reach that order differently, because their native
`ORDER BY` `NULL` placement diverges:

| direction | Postgres | MariaDB |
|---|---|---|
| `asc` | `order by t0.c asc` (NULLs last by default) | `order by t0.c is null, t0.c asc` |
| `desc` | `order by t0.c desc nulls last` | `order by t0.c desc` (NULLs last by default) |

Postgres treats `NULL` as the largest value (so `asc` already trails `NULL`s and
`desc` needs an explicit `nulls last`); MariaDB/MySQL treat `NULL` as the
smallest and have **no** `NULLS FIRST/LAST` syntax, so the ascending case forces
`NULL`s last with a leading `<col> is null` term. The compatibility suite proves
both forms yield the identical observable order (case `m-deep-fetch-012`).

## Decision points needed now

- **Type mapping.** The dialect maps each `m-core` neutral type to a concrete
  column type (the Postgres column on the right of the `m-core` table). DDL
  derivation (`m-case-format` harness) asks the dialect for these.
- **Timestamp precision.** The dialect MUST preserve the `m-core` `timestamp`
  contract at microsecond precision. Dialects with higher-resolution client
  types MUST reject or explicitly normalize non-zero sub-microsecond values
  before binding; dialects with lower-resolution storage cannot satisfy the core
  `timestamp` type without an additional adapter or degraded optional profile.
- **Typed bind normalization.** Above-seam runtime code supplies the dialect with
  the target `m-core` neutral type when binding a managed value. The dialect MUST
  return the value shape expected by its concrete adapter without changing the
  emitted SQL. Postgres renders managed scalars to canonical `m-core` wire values
  because the driver can coerce those directly; MariaDB keeps `timestamp` values
  as typed instants (and the neutral `infinity` sentinel) so its adapter can bind
  `datetime(6)` and the max-sentinel without guessing whether an arbitrary string
  is text or time. Non-timestamp values render to canonical `m-core` wire values
  unless a future dialect documents a different typed carrier.
- **SELECT shape.** The canonical SELECT projects explicit, table-aliased columns
  (`t0.id, t0.name`) from a single aliased table (`from orders t0`). The alias
  scheme is `t0, t1, …` (see `m-sql` normalization). No `SELECT *`.
- **Identifier quoting.** Simple lowercase identifiers are unquoted on both
  dialects. A reserved word or otherwise non-simple name MUST be quoted, and the
  quote **character diverges** — Postgres double-quotes (`"order"`), MariaDB
  backticks (`` `order` ``). The compatibility case `m-descriptor-001` witnesses
  this on both dialects (a column literally named `order`); the `m-sql` normalizer
  preserves quoted identifiers, and the harness quotes reserved identifiers in the
  DDL/DML it generates while leaving simple names unquoted.
- **Infinity representation.** The open upper bound of a temporal interval
  (`m-core`) is owned here. **Postgres** uses native `'infinity'::timestamptz`, so
  the current-row predicate is `to = infinity` and a milestone insert writes
  `out_z = infinity` directly. **MariaDB's `DATETIME` has no native `'infinity'`**,
  so the seam maps the open-bound sentinel to a documented **max-sentinel** —
  `9999-12-31 23:59:59.999999`, the largest `DATETIME(6)`. This is the **only**
  place the difference is allowed to surface: the suite authors the `infinity`
  literal once (against native-infinity Postgres), and the MariaDB dialect
  translates it to the max-sentinel on the way **in** (binds, fixture loads) and
  back to `infinity` on the way **out** (reads), so the golden SQL (`t0.out_z = ?`),
  the fixture history, and the asserted table state are all dialect-neutral. The
  sentinel orders correctly above every finite milestone, preserving the
  current-row predicate. (The cost relative to native infinity is the Y9999 cliff
  Postgres avoids — acceptable for a dialect that offers no alternative.)
- **Read-lock application (`m-read-lock`).** *Applying* the in-transaction shared
  read lock is a dialect decision — not merely spelling the suffix, but deciding
  **whether, where, and when** to attach it. Given a compiled read and the
  unit-of-work mode, the dialect returns the read with this dialect's locking
  applied:
  - a lockable **object find** in `locking` mode gets the shared-row-lock form
    appended after every other clause — **Postgres** `for share of t0` (the
    alias-qualified `for share`), **MariaDB** the unaliased **`lock in share
    mode`** (no `for share` keyword; MDEV-17514);
  - a **projection / aggregation** read (a `distinct` / grouped / aggregate
    result) is returned **unchanged** — it has no identifiable base row to lock and
    the database rejects the clause on such shapes, so the dialect **omits** the
    lock rather than erroring (ADR 0012; mirrors Reladomo's never-locking
    `getSelectForAggregatedData` beside the object-find `getSelect(isInTransaction)`);
  - any read in **optimistic** mode is returned unchanged (`m-opt-lock` takes no
    lock).

  This divergence is surfaced here and **only** here — the operation, the result,
  and the independent oracle are identical; just the lock spelling differs. Each
  object-find form is the canonical fixed point of the `m-sql` normalizer for its
  own dialect (fully lowercase per rule 2; the normalizer renders the MariaDB lock
  through the seam rather than through sqlglot's MySQL generator, which would
  otherwise rewrite it to `for share`).
- **Error-code classification.** A raised database error is mapped to a neutral
  category via this seam's per-dialect native code source; the category set, the
  call-site predicates, and the per-dialect code tables are `m-db-error`.

## Two concrete dialects prove the seam, and it stays open

- **Postgres** is the round-1 concrete dialect; **MariaDB** is the second,
  proving the seam beyond Postgres. Each dialect's golden SQL is normative for
  that dialect (`m-sql`); the harness boots real Postgres **and** real MariaDB via
  Testcontainers (`m-case-format`), and the compatibility-matrix report
  (implementations × databases) shows reference × {postgres, mariadb} green.
- **Localization, proven.** Adding MariaDB required changes **only** inside the
  dialect seam — the normalizer's dialect mapping + read-lock rendering, the
  `m-core` type table's MariaDB column, and the MariaDB provider's infinity /
  instant adapters. **No spec prose outside this file and no fixture was
  MariaDB-specific** beyond the additive per-dialect `mariadb` keys in the
  affected cases' `then.statements` entries (which are the seam's output, not a
  leak). This is the "equivalent SQL per database, optimized per dialect" promise
  made good.
- **The matrix.** A golden statement's `sql` is **keyed by dialect from day one**
  (a `postgres` key, a `mariadb` key), and the database-provider seam in
  the harness selects a provider per dialect — so a third database is a new
  provider + a new per-dialect `sql` key in each statement entry, **not** a
  redesign.
- **Not a one-way door (DQ9).** The seam **MUST** stay open enough that
  per-source / per-tenant connection routing could be added later without
  re-plumbing. Source-attribute sharding is out of scope for round 1, but
  nothing here may *preclude* it: the dialect/connection seam is the natural
  future home for a routing hook.
