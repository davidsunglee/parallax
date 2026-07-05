# M11 — Database Seam & Portability

All SQL-dialect variation **MUST** live behind a single normative `Dialect`
interface. This is the **only** place dialect-specific SQL is allowed. The
promise "equivalent SQL per database, optimized per dialect" is made enforceable
precisely because dialect divergence is localized to one swappable component.
`M11` depends only on `M0`.

This mirrors Reladomo's `DatabaseType` seam — obtained from the connection
manager at every SQL decision point, never from a global registry.

## M11 decomposition — pure dialect, execution port, and concrete adapters

The seam is **not** a single indivisible unit. `M11` **MUST** decompose into three
cooperating logical layers plus N concrete adapters, and this decomposition is
itself normative — it is what makes "swap the database, not the application" real
rather than aspirational:

1. **A pure dialect / portability layer** — the `Dialect` authority detailed in
   the next section: SQL-fragment production (SELECT shape, identifier quoting,
   row-limit clause, read-lock application, temp-table DDL), the neutral-type →
   column-type mapping, the **typed-bind normalization rules** that prepare
   managed runtime values for the adapter boundary, and the **type-parse functions** that turn a driver's raw
   column value into a core **managed value** (`int8` → the language's big-integer
   type, `numeric` → its exact-decimal type, `timestamp` → a UTC instant at core
   microsecond precision, `bytes` → a byte array). This layer performs **no I/O**:
   it holds no connection, opens no socket, and imports no database driver. It
   depends only on `M0`, and it is the single source of truth for every
   dialect-specific string and every dialect-specific parse rule.
2. **An abstract runtime database port** — the execution interface the layers
   above the seam (transactions `M8`, and the composition root) call to run
   compiled SQL and demarcate transactions. The port names an
   `execute(sql, binds) → rows` /
   `executeWrite(sql, binds) → affected-row count` / `transaction(body)`
   contract and nothing more. `execute` is row/result oriented; DML that needs
   write outcome classification uses `executeWrite` and MUST NOT append
   dialect-specific row-returning clauses merely to infer an affected count.
   It **depends on nothing application-specific** (beyond the neutral `M0` types
   its contract names) — no driver, no concrete database, no harness — so any
   layer may hold the port without acquiring a database dependency. The port
   carries the **normalize-at-boundary contract**: an adapter behind it returns
   rows whose scalars are already **managed values** (produced by the dialect
   layer's parse functions), never raw driver representations. Nothing above the
   seam ever sees a driver's `Date`, a binary-float `numeric`, or a raw byte
   buffer. `executeWrite` returns the concrete driver's native affected-row count
   and no rows.
3. **N concrete adapter modules — one per database type.** Each adapter
   implements the port over exactly one driver. An adapter depends **only on the
   port and the pure dialect layer**: it owns driver setup and registration (which
   type codes to read as raw text, connection/pool acquisition) and delegates
   every parse decision to the dialect layer, so parse logic is never duplicated
   across adapters. Adding a database type is a **new adapter module**, not a
   change to the port, the dialect layer, or anything above the seam.

Two structural rules make the decomposition load-bearing:

- **Only the composition root may depend on a *concrete* adapter.** Every layer
  above the seam depends on the **port**, never on a specific adapter; a concrete
  adapter is selected and injected once, at the top. This is what lets one program
  target the production database and a test target a different one without
  recompiling the layers between.
- **The port depends on nothing application-specific, and the pure dialect layer
  performs no I/O.** A wrong-direction dependency here — the port reaching for a
  driver, or an above-seam module importing a concrete adapter — is the same class
  of spec violation the module-dependency graph forbids.

### Managed at the boundary, wire at the grader

The normalize-at-boundary contract fixes **where** a raw database value becomes a
first-class typed value: at the adapter boundary, **once**. An adapter returns
**managed** scalars — the language's exact-decimal type, big-integer type,
UTC-instant type, byte-array type — so every consumer above the seam reasons in
managed types and none re-parses driver text.

The compatibility harness (`M12`) grades in a **different** domain and must not be
conflated with the runtime path. It takes the adapter's **managed** rows and
**serializes them to the canonical wire form** (`M0`) for its result envelope,
then grades in **wire space** (decimals compared in decimal space, instants as
canonical UTC strings, and so on) so grading is cross-language-consistent and
independent of any one language's managed representation. **The wire rendering is a
grader concern, never an adapter concern:** a concrete adapter emits managed types
only and contains **no** wire or grading logic. This is the normative split —
*managed at the boundary, wire at the grader*: the runtime consumes managed types;
the harness serializes managed → canonical wire for its envelope and compares
there.

### Packaging latitude

This decomposition mandates the **separation** — one pure dialect layer, one
abstract port, and N concrete adapters, under the two dependency rules above —
**not** a particular packaging mechanism. Whether the port and the dialect layer
ship as one distributable or two, and how the N adapters are published, is a
per-ecosystem choice (consistent with the per-language enforcement-tooling table
in [`dependency-graph.md`](dependency-graph.md)). What every ecosystem MUST
preserve is the **direction**: above-seam code binds to the port, and concrete
adapters are leaf modules the composition root selects.

A **concrete dialect strategy** — one database's pure SQL strings and parse
functions — is a **different thing** from a **concrete adapter** — that database's
driver-bound port implementation — even though both are per-database. Only the
adapter carries a driver. The concrete dialect strategies MAY ship as a single
catalog or be split one pure module per database; either way they stay
**driver-free**, and each adapter depends on its matching dialect strategy (never
the reverse). Folding a database's dialect strings *into* its adapter is
**forbidden**: `M3` (SQL generation) and `M8` (transactions) depend on the dialect
layer to emit compiled SQL, so co-locating dialect strings with a driver would pull
that driver into modules that MUST stay database-free — defeating the driver-free
compile/golden path.

## The `Dialect` interface

A `Dialect` is the abstract authority for every dialect-specific decision. With
the second concrete dialect (**MariaDB**) added behind the seam, the full
decision-point catalog is now fixed. Two dialects legitimately make *different*
choices at each point; both are normative for their dialect (M3). The catalog
(derived from the research matrix, research §11):

| Decision point | Postgres (round-1 concrete) | MariaDB (second concrete) |
|---|---|---|
| `dialect` identifier | `postgres` | `mariadb` |
| type mapping (neutral type → column type) | per the M0 Postgres column | per the M0 MariaDB column (see below) |
| `SELECT` shape (column list, alias scheme) | `select t0.col, … from tbl t0 where …` | identical |
| identifier quoting | unquoted lowercase; `"…"` quote on demand | unquoted lowercase; **backtick** quote on demand (divergent quote char) |
| row-limit clause | `limit ?` | `limit ?` |
| **read-lock application** (M8) | object find: `for share of t0`; projection/aggregation: omitted | object find: **`lock in share mode`** (no `for share`; MDEV-17514); projection/aggregation: omitted |
| temp-table DDL | `CREATE TEMPORARY TABLE … ON COMMIT DROP` | `CREATE TEMPORARY TABLE …` |
| typed bind normalization | managed values render to canonical M0 wire values | timestamp binds remain typed `Instant`/`infinity` so the adapter can render `datetime(6)`/max-sentinel; other values render to canonical M0 wire values |
| **infinity representation** (M7) | native `'infinity'::timestamptz` | **max-sentinel** `datetime` (no native infinity) |
| error-code classification | SQLSTATE: `23505` unique, `40P01`/`40001` deadlock, `55P03` lock timeout | errno: `1062` duplicate, `1213` deadlock, `1205` lock timeout |

The two decision points MariaDB **diverges** on — the read-lock (application) and
the infinity representation — are exactly the ones the second dialect was chosen
to exercise; they are detailed below. The divergent **type mappings** are
round-tripped against real MariaDB by the scalar witness (compatibility case
`1005`), and the UTC-instant normalization + microsecond precision of
`datetime(6)` by the timestamp write cases (`0004`/`0005`).

### MariaDB type mapping (the M0 table, MariaDB column)

The dialect maps each M0 neutral type to a concrete MariaDB column type. The
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
map the same M0 `json` neutral type behind this seam; the metamodel does not
name the concrete storage type.

### `NULL` ordering

The canonical ordered-relationship rule (M4) sorts `NULL`s **last** on every
key. The two dialects reach that order differently, because their native
`ORDER BY` `NULL` placement diverges:

| direction | Postgres | MariaDB |
|---|---|---|
| `asc` | `order by t0.c asc` (NULLs last by default) | `order by t0.c is null, t0.c asc` |
| `desc` | `order by t0.c desc nulls last` | `order by t0.c desc` (NULLs last by default) |

Postgres treats `NULL` as the largest value (so `asc` already trails `NULL`s and
`desc` needs an explicit `nulls last`); MariaDB/MySQL treat `NULL` as the
smallest and have **no** `NULLS FIRST/LAST` syntax, so the ascending case forces
`NULL`s last with a leading `<col> is null` term. The compatibility suite proves
both forms yield the identical observable order (case `0323`).

## Decision points needed now

- **Type mapping.** The dialect maps each M0 neutral type to a concrete column
  type (the Postgres column on the right of the M0 table). DDL derivation (M12
  harness) asks the dialect for these.
- **Timestamp precision.** The dialect MUST preserve the M0 `timestamp`
  contract at microsecond precision. Dialects with higher-resolution client
  types MUST reject or explicitly normalize non-zero sub-microsecond values
  before binding; dialects with lower-resolution storage cannot satisfy the core
  `timestamp` type without an additional adapter or degraded optional profile.
- **Typed bind normalization.** Above-seam runtime code supplies the dialect with
  the target M0 neutral type when binding a managed value. The dialect MUST return
  the value shape expected by its concrete adapter without changing the emitted
  SQL. Postgres renders managed scalars to canonical M0 wire values because the
  driver can coerce those directly; MariaDB keeps `timestamp` values as typed
  instants (and the neutral `infinity` sentinel) so its adapter can bind
  `datetime(6)` and the max-sentinel without guessing whether an arbitrary string
  is text or time. Non-timestamp values render to canonical M0 wire values unless
  a future dialect documents a different typed carrier.
- **SELECT shape.** The canonical SELECT projects explicit, table-aliased columns
  (`t0.id, t0.name`) from a single aliased table (`from orders t0`). The alias
  scheme is `t0, t1, …` (see M3 normalization). No `SELECT *`.
- **Identifier quoting.** Simple lowercase identifiers are unquoted on both
  dialects. A reserved word or otherwise non-simple name MUST be quoted, and the
  quote **character diverges** — Postgres double-quotes (`"order"`), MariaDB
  backticks (`` `order` ``). The compatibility case `0006` witnesses this on both
  dialects (a column literally named `order`); the M3 normalizer preserves quoted
  identifiers, and the harness quotes reserved identifiers in the DDL/DML it
  generates while leaving simple names unquoted.
- **Infinity representation (M7).** The open upper bound of a temporal interval
  (M0) is owned here. **Postgres** uses native `'infinity'::timestamptz`, so the
  current-row predicate is `to = infinity` and a milestone insert writes
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
- **Read-lock application (M8).** *Applying* the in-transaction shared read lock
  is a dialect decision — not merely spelling the suffix, but deciding **whether,
  where, and when** to attach it. Given a compiled read and the unit-of-work mode,
  the dialect returns the read with this dialect's locking applied:
  - a lockable **object find** in `locking` mode gets the shared-row-lock form
    appended after every other clause — **Postgres** `for share of t0` (the
    alias-qualified `for share`), **MariaDB** the unaliased **`lock in share
    mode`** (no `for share` keyword; MDEV-17514);
  - a **projection / aggregation** read (a `distinct` / grouped / aggregate
    result) is returned **unchanged** — it has no identifiable base row to lock and
    the database rejects the clause on such shapes, so the dialect **omits** the
    lock rather than erroring (ADR 0030; mirrors Reladomo's never-locking
    `getSelectForAggregatedData` beside the object-find `getSelect(isInTransaction)`);
  - any read in **optimistic** mode is returned unchanged (M10 takes no lock).

  This divergence is surfaced here and **only** here — the operation, the result,
  and the independent oracle are identical; just the lock spelling differs. Each
  object-find form is the canonical fixed point of the M3 normalizer for its own
  dialect (fully lowercase per rule 2; the normalizer renders the MariaDB lock
  through the seam rather than through sqlglot's MySQL generator, which would
  otherwise rewrite it to `for share`).
- **Error-code classification (M11).** A raised database error MUST be mapped to a
  neutral **category** so language-neutral code can react without dialect
  knowledge. The categories are a closed set: `uniqueViolation` (duplicate key /
  unique-index violation), `deadlock` (a true deadlock **or** a serialization
  failure — both retriable), `lockWaitTimeout` (blocked past the lock-wait
  budget), plus `connectionDead` (reserved). Classification is interrogated at
  **distinct call sites**, so the seam exposes it as predicates defined as
  category membership — not one stringly-typed method: the transaction retry loop
  asks `isRetriable` (`category = deadlock`), the insert / detached merge-back
  path asks `violatesUniqueIndex` (`category = uniqueViolation`), the lock path
  asks `isTimedOut` (`category = lockWaitTimeout`). The native code source
  **diverges**: Postgres keys on the **`SQLSTATE` string**, MariaDB on the
  **vendor errno**. This is load-bearing: `SQLSTATE 40001` is a *serialization
  failure* on Postgres (distinct from deadlock `40P01`) but the *deadlock* state
  on MariaDB (whose errno `1213` is what the seam matches) — so a naive
  cross-dialect `SQLSTATE` compare would misclassify. The mapping:

  | Category | Postgres (`SQLSTATE`) | MariaDB (errno) |
  |---|---|---|
  | `uniqueViolation` | `23505` | `1062` |
  | `deadlock` | `40P01`, `40001` | `1213` |
  | `lockWaitTimeout` | `55P03` | `1205` |

  The compatibility suite exercises all three classes on both dialects (cases
  `0720`–`0727`): a case triggers a real error and asserts the neutral category,
  the per-dialect native code, and the call-site predicate partition. This is the
  **only** place native error codes are interpreted; everything above the seam
  reasons in categories.

## Two concrete dialects prove the seam, and it stays open

- **Postgres** is the round-1 concrete dialect; **MariaDB** is the second,
  proving the seam beyond Postgres. Each dialect's golden SQL is normative for
  that dialect (M3); the harness boots real Postgres **and** real MariaDB via
  Testcontainers (M12), and the compatibility-matrix report (implementations ×
  databases) shows reference × {postgres, mariadb} green.
- **Localization, proven.** Adding MariaDB required changes **only** inside the
  dialect seam — the normalizer's dialect mapping + read-lock rendering, the M0
  type table's MariaDB column, and the MariaDB provider's infinity / instant
  adapters. **No spec prose outside this file and no fixture was MariaDB-specific**
  beyond the additive per-dialect `goldenSql.mariadb` keys (which are the seam's
  output, not a leak). This is the "equivalent SQL per database, optimized per
  dialect" promise made good.
- **The matrix.** `goldenSql` is **keyed by dialect from day one**
  (`goldenSql.postgres`, `goldenSql.mariadb`), and the database-provider seam in
  the harness selects a provider per dialect — so a third database is a new
  provider + a new `goldenSql.<dialect>` key, **not** a redesign.
- **Not a one-way door (DQ9).** The seam **MUST** stay open enough that
  per-source / per-tenant connection routing could be added later without
  re-plumbing. Source-attribute sharding is out of scope for round 1, but
  nothing here may *preclude* it: the dialect/connection seam is the natural
  future home for a routing hook.
