# M2 — Query, Operation & Aggregation Algebra

`M2` defines the **operation algebra** — the framework's own query language — and
its **canonical serialization**. The algebra *is* the protocol: the
compatibility suite's queries are instances of it, and every implementation
ships a serde module that round-trips them. `M2` depends on `M1` (operations are
bound to metamodel attributes).

The canonical schema is
[`core/schemas/operation.schema.json`](../schemas/operation.schema.json).

## Positioning (DQ13)

The core defines **its own higher-level, metamodel-bound algebra** rather than
adopting a SQL-oriented IR (SQLGlot, Substrait) as the core representation. The
algebra is deliberately *above* SQL:

- Relationship traversal is a **single navigation** (`Order.items`), not a
  user-written join with ON-conditions.
- Temporal joins (the per-axis `<`/`<=`/`>`/`>=` as-of predicates) are
  **auto-injected** from the as-of model, never written by the user.

A SQL IR forces those joins and predicates to be explicit — the wrong
abstraction level for a finder language. The algebra translates **down** to SQL
(M3); a language **MAY** implement M3 by lowering this algebra onto an external
SQL IR to get many dialects "for free", but that is a per-language decision
behind the M3 seam, not a core mandate.

## Canonical operation encoding (serde seam)

An operation is a tree of **nodes** with a **format-agnostic canonical
serialization**. This serialized form is the suite's normative encoding — one
source of truth so every implementation tests the same operation. Concrete
encodings exist in at least **JSON and YAML** (a format-agnostic core plus
pluggable writers); the format set is consistent with metamodel serde (M1).

Every implementation **MUST** ship a serde module whose sole job is operation
serialize/deserialize, with **round-trip** tests:
`serialize(deserialize(op)) == op`. The reference harness asserts this per case,
in both JSON and YAML. Idiomatic per-language re-expressions of a query (fluent
builders, etc.) are **illustrative only** — never the normative encoding.

The encoding is a tagged object: each node is a single-key object whose key names
the operation. Attribute references are `Class.attribute` strings, resolved
against the model. Examples:

```json
{ "all": {} }
```

```json
{ "eq": { "attr": "Order.id", "value": 42 } }
```

## Operation set (this phase)

The full algebra is large; this phase introduces the two query identities and
the canonical equality predicate. Later phases add the full equality/range, null,
string, membership, boolean, relationship, directive, temporal, and aggregate
nodes.

| Category | Operation | Meaning |
|---|---|---|
| Identity | `all` | no filter — selects every row |
| Identity | `none` | the empty result — matches nothing |
| Equality | `eq` | typed attribute equality (`attr` = `value`) |

- **`all`** — the identity of the algebra; lowers to a `SELECT` with no `WHERE`.
- **`none`** — the absorbing element; lowers to a query that returns no rows. It
  is the dual of `all` and is defined now so the schema's identity pair is
  complete; it gains a dedicated fixture alongside the boolean combinators in a
  later phase.
- **`eq`** — `{ "eq": { "attr": "Class.attribute", "value": <literal> } }`. The
  value becomes a bind placeholder in the golden SQL.

## Forward map of the full algebra

For orientation, later phases fill in (each node carries a canonical
serialization):

- Equality / range: `notEq`, `greaterThan`, `greaterThanEquals`, `lessThan`,
  `lessThanEquals`, `between`.
- Null: `isNull`, `isNotNull`.
- String: `like`, `notLike`, `startsWith`, `endsWith`, `contains`, and
  case-insensitive variants.
- Membership: `in(values)`, `notIn(values)`, `in(subquery)`.
- Boolean: `and`, `or`, `not`, and a first-class `group` node (precedence and
  serialization fidelity).
- Relationship: `navigate(rel) → predicate`, `exists`, `notExists`.
- Directives: `orderBy`, `limit`, `distinct`, `deepFetch`.
- Temporal (M7): `asOf`, `asOfRange`, `history`.
- Aggregate (M2 sub-area): `sum`/`avg`/`count`/`min`/`max`/`stdDev*`/`variance*`,
  `groupBy`, and having comparators.
