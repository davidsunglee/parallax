# m-inheritance — Inheritance Mapping

`m-inheritance` is the **class-hierarchy mapping** strategy a metamodel entity may
declare. It depends on `m-descriptor` (the entity it annotates).

An entity that participates in a class hierarchy declares an `inheritance`
element naming its **strategy** and its **role**. Core admits exactly two
strategies and **rejects the third**:

| Strategy | Meaning | In core? |
|---|---|---|
| `table-per-hierarchy` | the whole hierarchy in **one** table; rows discriminated by a `discriminator` column | **yes** |
| `table-per-leaf` | one table **per concrete leaf**; no discriminator | **yes** |
| `table-per-class` | one table per class, joined at query time | **REJECTED** — the metamodel schema does not admit it |

`table-per-class` is intentionally excluded (DQ9): per-query joins to assemble a
single object are exactly the kind of hidden N+1 / fan-out cost the suite exists
to prevent, and the two admitted strategies cover the field's real use. A
descriptor declaring `strategy: table-per-class` **MUST** fail schema validation
(a negative compatibility test asserts this).

| Property | Values / meaning |
|---|---|
| `strategy` | `table-per-hierarchy` \| `table-per-leaf` (REQUIRED) |
| `role` | `root` (owns / names the hierarchy) \| `subtype` (a leaf) (REQUIRED) |
| `parent` | for a `subtype`: the entity it extends (REQUIRED for a subtype, FORBIDDEN for a root) |
| `discriminator` | table-per-hierarchy only, REQUIRED there and FORBIDDEN for table-per-leaf: `{ column }`, the column distinguishing leaves in the shared table |
| `discriminatorValue` | table-per-hierarchy only, REQUIRED there and FORBIDDEN for table-per-leaf: the discriminator value THIS entity's rows carry |

**Table-per-hierarchy.** The `root` and every `subtype` map to the **same
table** and declare the shared `discriminator` column plus their own
`discriminatorValue`; a query for a subtype injects a
**discriminator-equality predicate** (`t0.<discriminator> = ?`), and a query
across a family of subtypes injects a discriminator `in (?, …)`. The root query
(no discriminator predicate) sees every row. `m-sql` fixes the
discriminator-filter golden SQL.

**Table-per-leaf.** Each concrete leaf maps to its **own table** (its own
`table`), so a leaf query is an ordinary single-table read of that table with
**no** discriminator — the subtype is selected by *which table* is queried. No
shared table and no discriminator column exist.
