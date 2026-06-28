# M11 — Database Seam & Portability

All SQL-dialect variation **MUST** live behind a single normative `Dialect`
interface. This is the **only** place dialect-specific SQL is allowed. The
promise "equivalent SQL per database, optimized per dialect" is made enforceable
precisely because dialect divergence is localized to one swappable component.
`M11` depends only on `M0`.

This mirrors Reladomo's `DatabaseType` seam — obtained from the connection
manager at every SQL decision point, never from a global registry.

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
| **read-lock suffix** (M8) | `for share of t0` | **`lock in share mode`** (no `for share`; MDEV-17514) |
| temp-table DDL | `CREATE TEMPORARY TABLE … ON COMMIT DROP` | `CREATE TEMPORARY TABLE …` |
| **infinity representation** (M7) | native `'infinity'::timestamptz` | **max-sentinel** `datetime` (no native infinity) |
| error-code classification | SQLSTATE `40P01`/`40001` deadlock, `23505` unique | error `1213` deadlock, `1062` duplicate |

The two decision points MariaDB **diverges** on — the read-lock suffix and the
infinity representation — are exactly the ones the second dialect was chosen to
exercise; they are detailed below. The divergent **type mappings** are
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

## Decision points needed now

- **Type mapping.** The dialect maps each M0 neutral type to a concrete column
  type (the Postgres column on the right of the M0 table). DDL derivation (M12
  harness) asks the dialect for these.
- **Timestamp precision.** The dialect MUST preserve the M0 `timestamp`
  contract at microsecond precision. Dialects with higher-resolution client
  types MUST reject or explicitly normalize non-zero sub-microsecond values
  before binding; dialects with lower-resolution storage cannot satisfy the core
  `timestamp` type without an additional adapter or degraded optional profile.
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
- **Read-lock suffix (M8).** The shared-row-lock clause an in-transaction read
  appends for automatic read correctness (M8) is a dialect decision. **Postgres**
  appends `for share of t0` (the alias-qualified `for share`). **MariaDB** has no
  `for share` keyword (MDEV-17514); its shared lock is the unaliased
  **`lock in share mode`**, appended after every other clause. This divergence is
  surfaced here and **only** here — the operation, the result, and the
  independent oracle are identical; just the lock spelling differs. Each form is
  the canonical fixed point of the M3 normalizer for its own dialect (fully
  lowercase per rule 2; the normalizer renders the MariaDB lock through the seam
  rather than through sqlglot's MySQL generator, which would otherwise rewrite it
  to `for share`).

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
