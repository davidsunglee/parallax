# M3 — SQL Generation & Equivalence Contract

`M3` is the contract that turns an M2 operation into per-dialect SQL, and the
rules that make "equivalent SQL per database" **testable**. `M3` depends on `M2`
(the algebra it lowers) and `M11` (the dialect that decides the concrete SQL).

The core does **not** mandate *how* an implementation produces SQL (a language
MAY lower the algebra onto an external SQL IR inside M3). The core mandates the
**output**: for each case, the SQL an implementation emits, after normalization,
**MUST** equal the case's `goldenSql` for that dialect, and **MUST** return the
case's `expectedRows`.

## The equivalence contract (DQ1)

The contract is layered. For a given dialect, an implementation is correct iff:

1. **Result equivalence.** The query returns exactly `expectedRows`. The suite
   cross-checks this with an independent `referenceSql` oracle (M12).
2. **Golden-SQL equivalence.** The SQL the implementation emits, **after
   normalization**, equals `goldenSql[dialect]`.

Round 1 ships golden SQL for **Postgres only**; the contract is per-dialect, so
additional dialects add `goldenSql.<dialect>` without changing the rules.

## Canonical normalization rules

Golden SQL is stored in **canonical normalized form**, and an implementation's
emitted SQL is compared **after applying the same normalization**. Normalization
makes the comparison deterministic and language-neutral. The rules:

1. **Table-alias scheme `t0, t1, …`.** Every table reference is aliased; aliases
   are assigned `t0`, `t1`, … in first-appearance order. Column references are
   always qualified by alias (`t0.id`, never bare `id`).
2. **Lowercase keywords and identifiers.** SQL keywords and unquoted identifiers
   are lowercased.
3. **Whitespace collapsed.** Runs of whitespace collapse to a single space;
   no leading/trailing whitespace; canonical single-space token separation.
4. **Bind placeholders, sorted.** Literal parameters are represented as bind
   placeholders (`?`), and the case's `binds` list is the ordered set of values.
   The placeholder ordering follows left-to-right appearance in the normalized
   statement.
5. **Deterministic clause order.** Clauses appear in the fixed order
   `select … from … [where …] [group by …] [having …] [order by …] [limit …]`.

The normative implementation of these rules is
`reference-harness/src/reference_harness/sql_normalize.py` (sqlglot-based). A
golden SQL string is valid only if `normalize(goldenSql) == goldenSql` — i.e. the
stored form is already a fixed point of normalization. The harness asserts this
per case (M12, layer 3).

> **Idempotence is the test.** Because normalization is idempotent, the stored
> golden SQL being a fixed point is exactly the property the harness checks.
> A contributor who hand-writes non-canonical golden SQL fails this check
> immediately, before any database is touched.

## What is normative vs. dialect-local

- **Normative:** the result (`expectedRows`) and the per-dialect golden SQL
  (after normalization).
- **Dialect-local:** the concrete SQL text itself — chosen by the M11 dialect.
  Two dialects legitimately emit *different* golden SQL for the same operation
  (different type casts, limit syntax, lock suffixes); both are normative for
  their dialect and both must return the same logical rows.

## This phase's surface

The walking skeleton lowers exactly two operations:

- `all` — no `WHERE` clause:
  `select t0.id, t0.name from orders t0`
- `eq` on a primary key — a single equality predicate with one bind:
  `select t0.id, t0.name from orders t0 where t0.id = ?`

Subsequent phases extend the emission + normalization rules for the full
predicate set, joins-by-navigation, deep fetch, aggregation, and temporal
predicates.
