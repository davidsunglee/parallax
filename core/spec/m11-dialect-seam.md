# M11 — Database Seam & Portability

All SQL-dialect variation **MUST** live behind a single normative `Dialect`
interface. This is the **only** place dialect-specific SQL is allowed. The
promise "equivalent SQL per database, optimized per dialect" is made enforceable
precisely because dialect divergence is localized to one swappable component.
`M11` depends only on `M0`.

This mirrors Reladomo's `DatabaseType` seam — obtained from the connection
manager at every SQL decision point, never from a global registry.

## The `Dialect` interface

A `Dialect` is the abstract authority for every dialect-specific decision. The
decision points the interface **MUST** cover (the catalog grows as later phases
add capabilities; the points relevant now are marked):

| Decision point | Phase | Postgres (round-1 concrete) |
|---|---|---|
| `dialect` identifier | now | `postgres` |
| type mapping (neutral type → column type) | now | per the M0 table |
| `SELECT` shape (column list, alias scheme) | now | `select t0.col, … from tbl t0 where …` |
| identifier quoting | now | unquoted lowercase identifiers; quote only on demand |
| row-limit clause | later | `LIMIT n` |
| read-lock suffix | later | `FOR SHARE OF t0` |
| temp-table DDL | later | `CREATE TEMPORARY TABLE … ON COMMIT DROP` |
| infinity representation | now (M7) | native `'infinity'::timestamptz` |
| error-code classification | later | SQLSTATE `40P01`/`40001` deadlock, `23505` unique |

Only the rows marked **now** are required for the walking skeleton. The rest are
named so the interface shape is fixed and additive.

## Decision points needed now

- **Type mapping.** The dialect maps each M0 neutral type to a concrete column
  type (the Postgres column on the right of the M0 table). DDL derivation (M12
  harness) asks the dialect for these.
- **SELECT shape.** The canonical SELECT projects explicit, table-aliased columns
  (`t0.id, t0.name`) from a single aliased table (`from orders t0`). The alias
  scheme is `t0, t1, …` (see M3 normalization). No `SELECT *`.
- **Identifier quoting.** Postgres identifiers are unquoted lowercase. The
  dialect decides when quoting is required; round-1 fixtures use plain
  lowercase identifiers that need no quoting.
- **Infinity representation (M7).** The open upper bound of a temporal interval
  (M0) is owned here. **Postgres** uses native `'infinity'::timestamptz`, so the
  current-row predicate is `to = infinity` and a milestone insert writes
  `out_z = infinity` directly. A future dialect without native timestamp infinity
  (MariaDB's `DATETIME` has no `'infinity'`) maps the sentinel to a documented
  **max-sentinel** behind this same seam — the only place the difference is
  allowed to surface; that fallback is finalized in the MariaDB phase.

## Postgres is round-1, and the seam stays open

- **Postgres** is the single round-1 concrete dialect. Its golden SQL is
  normative (M3); the harness boots real Postgres via Testcontainers (M12).
- **The matrix.** `goldenSql` is **keyed by dialect from day one**
  (`goldenSql.postgres`), and the database-provider seam in the harness selects a
  provider per dialect — so adding a second database (a later phase adds MariaDB)
  is a new provider + a new `goldenSql.<dialect>` key, **not** a redesign. The
  compatibility-matrix concept (implementations × databases) follows directly.
- **Not a one-way door (DQ9).** The seam **MUST** stay open enough that
  per-source / per-tenant connection routing could be added later without
  re-plumbing. Source-attribute sharding is out of scope for round 1, but
  nothing here may *preclude* it: the dialect/connection seam is the natural
  future home for a routing hook.
