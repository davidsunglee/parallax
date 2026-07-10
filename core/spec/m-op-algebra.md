# m-op-algebra — Query & Operation Algebra

`m-op-algebra` defines the **operation algebra** — the framework's own query
language — and its **canonical serialization**. The algebra *is* the protocol: the
compatibility suite's queries are instances of it, and every implementation ships
a serde module that round-trips them. `m-op-algebra` depends on `m-descriptor`
(operations are bound to metamodel attributes) and on `m-inheritance` (the
`narrow` node constrains a polymorphic entity position against the family's
effective concrete-subtype set).

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
(`m-sql`); a language **MAY** implement `m-sql` by lowering this algebra onto an
external SQL IR to get many dialects "for free", but that is a per-language
decision behind the `m-sql` seam, not a core mandate.

## Canonical operation encoding (serde seam)

An operation is a tree of **nodes** with a **format-agnostic canonical
serialization**. This serialized form is the suite's normative encoding — one
source of truth so every implementation tests the same operation. Concrete
encodings exist in at least **JSON and YAML** (a format-agnostic core plus
pluggable writers); the format set is consistent with metamodel serde
(`m-descriptor`).

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

## Operation set

`m-op-algebra` is the canonical operation algebra. Its schema covers the
single-entity predicate algebra, result-shaping directives, relationship
navigation, temporal read wrappers, and nested value-object predicates.
Aggregation (`groupBy` / aggregate functions / `having`) is a **deferred**
extension of the same algebra — see `m-agg`. Each node below carries a single
canonical serialization; a conforming operation serde implementation **MUST**
validate and round-trip every node in `operation.schema.json` unchanged. Executing
a node may depend on other core modules: `m-descriptor` supplies attributes,
relationships, as-of attributes, and value objects; `m-sql` owns SQL lowering;
`m-temporal-read` owns temporal interval behavior.

### Identities

| Operation | Encoding | Meaning |
|---|---|---|
| `all` | `{ "all": {} }` | the identity — selects every row (no `WHERE`) |
| `none` | `{ "none": {} }` | the absorbing element — matches nothing |

`none` is the dual of `all`; it lowers to an unsatisfiable predicate.

### Equality and range

Each takes `{ "attr": "Class.attribute", "value": <literal> }`. The value becomes
a bind placeholder in the golden SQL.

| Operation | SQL operator |
|---|---|
| `eq` | `=` |
| `notEq` | `<>` |
| `greaterThan` | `>` |
| `greaterThanEquals` | `>=` |
| `lessThan` | `<` |
| `lessThanEquals` | `<=` |

`between` is a convenience over a bounded pair and takes
`{ "attr", "lower", "upper" }`; it lowers to `attr between ? and ?` (two ordered
binds: lower, then upper) and is equivalent to `>= lower AND <= upper`.

### Null

`isNull` / `isNotNull` take `{ "attr": "Class.attribute" }`. Per SQL three-valued
logic, `isNotNull` excludes NULL rows; `notLike`/`notIn`/`notEq` against a NULL
column likewise yield NULL (not true) and so exclude that row.

### String

The string predicates take `{ "attr", "value", "caseInsensitive"? }`
(`caseInsensitive` defaults to `false`).

| Operation | Pattern semantics |
|---|---|
| `like` / `notLike` | `value` **is** the SQL pattern: `%` and `_` are wildcards |
| `startsWith` | `value` is a **literal** prefix ⇒ pattern `value%` |
| `endsWith` | `value` is a **literal** suffix ⇒ pattern `%value` |
| `contains` | `value` is a **literal** infix ⇒ pattern `%value%` |

**Wildcard / escape rule.** For the affix forms (`startsWith`/`endsWith`/
`contains`) the implementation **MUST** escape any `%`, `_`, or escape character
occurring in the literal `value` before wrapping it with the affix wildcards, so
the literal matches literally. The canonical escape character is the backslash
(`\`), rendered with an explicit `escape ?` (or `escape '\'`) clause whenever the
pattern contains an escape sequence. `like`/`notLike` do **not** escape — their
`value` is already a pattern.

**Case-insensitive rule.** When `caseInsensitive` is `true`, both the column and
the pattern are folded with `lower(...)`: `lower(attr) like lower(?)`. (A language
MAY use a dialect-native case-insensitive operator behind the `m-sql` seam; the
golden SQL fixes the portable `lower(...)` form.)

### Membership

`in` / `notIn` take `{ "attr", "values": [ … ] }` (non-empty). Each value is a
bind, in list order; the SQL is `attr in (?, ?, …)`. The `in(subquery)` form is
not part of this schema revision.

### Nested value-object predicates

Nested predicates read an inner attribute of an `m-value-object`, which core
stores as a single dialect-mapped `json` column. They use a dotted path of the
form `Class.valueObject.segment[.segment...]` that resolves against the entity's
**declared** value-object structure (`m-value-object` — a recursive, typed
composite), never against opaque JSON keys:

- `Class` is the queried entity.
- The first segment **MUST** name a `valueObject` declared on that entity.
- Each intermediate segment **MUST** name a nested `valueObject` declared on the
  preceding member.
- The final (leaf) segment **MUST** name an `attribute` declared on the
  preceding member.

A resolver **MUST** validate every segment against the declared structure and
**MUST** reject a path whose first segment is not a declared value object, whose
intermediate segment is not a declared nested value object, or whose leaf is not a
declared attribute. Because the structure is declared, the leaf attribute has a
neutral type, and the comparison is **typed**.

The predicate family is **flat** and **parallel** to the scalar single-entity
algebra — one single-key tagged node per operator, each with a closed body:

| Operation | Encoding | Meaning |
|---|---|---|
| `nestedEq` | `{ "nestedEq": { "path", "value" } }` | the value at `path` equals `value` |
| `nestedNotEq` | `{ "nestedNotEq": { "path", "value" } }` | the value at `path` does not equal `value` |
| `nestedGt` | `{ "nestedGt": { "path", "value" } }` | the value at `path` is greater than `value` |
| `nestedGte` | `{ "nestedGte": { "path", "value" } }` | the value at `path` is greater than or equal to `value` |
| `nestedLt` | `{ "nestedLt": { "path", "value" } }` | the value at `path` is less than `value` |
| `nestedLte` | `{ "nestedLte": { "path", "value" } }` | the value at `path` is less than or equal to `value` |
| `nestedIn` | `{ "nestedIn": { "path", "values" } }` | the value at `path` is one of `values` (non-empty list) |
| `nestedIsNull` | `{ "nestedIsNull": { "path" } }` | the value at `path` is **not present** (see the absence-collapse rule) |
| `nestedIsNotNull` | `{ "nestedIsNotNull": { "path" } }` | the value at `path` **is present** (the complement) |

The comparison / membership `value`(s) are polymorphic `literal`s (`string` /
`number` / `boolean` / `null`), and each type **MUST** match the leaf attribute's
declared neutral type; a resolver **MUST** reject a type-mismatched literal (e.g. a
`number` compared against a `string`-typed attribute). The presence tests
(`nestedIsNull` / `nestedIsNotNull`) carry a `path` only. `m-sql` lowers a nested
read to a dialect-specific extraction from the structured-document column and
**casts** it to the declared type before comparing; the extraction spelling, the
typed-cast form, and the **bind order** (per-segment JSON keys vs a single path
bind) are all `m-dialect` decisions (`m-sql`, `m-dialect`), not fixed by this
algebra.

#### Absence-collapse rule

A nested field is in exactly one of two observable conditions: **present** — the
extraction yields a non-NULL, non-JSON-`null` scalar — or **not present**. Four
distinguishable storage states all collapse to **not present**, uniformly, for
every nested predicate:

- the value-object **column is SQL `NULL`** (the whole value object is absent);
- a **path segment is missing** from the stored document (no such key);
- the selected value is an explicit **JSON `null`**;
- an **intermediate segment is a non-object** (a scalar or array blocks descent).

In every one of these the extraction yields SQL `NULL`, so a comparison
(`nestedEq` / `nestedNotEq` / `nestedGt` / `nestedGte` / `nestedLt` / `nestedLte`)
and `nestedIn` are neither true — the row is **excluded**, exactly as the scalar
`notEq`/`notIn` null behavior above. `nestedIsNull` is true **exactly** on the
rows a comparison excludes for this reason (all four not-present states);
`nestedIsNotNull` is its complement (the present rows). An implementation **MUST
NOT** distinguish JSON `null` from a missing key or a null column at the predicate
level — the states stay distinguishable in the stored data but are indistinguishable
to the algebra.

#### To-many members — any-element and same-element semantics

A value object declared `cardinality: many` is a **JSON array** of documents in the
same column (`m-value-object`). Two things become expressible over it, and the
distinction between them is load-bearing.

**Flat predicates through a `many` segment mean *any element matches*.** A flat
`nested*` predicate whose path crosses a `many` member (e.g.
`nestedEq(Customer.address.phones.type, "home")`) is true for a row iff **some
element** of that array satisfies it. Each such predicate is evaluated
**independently**: ANDing two of them at the top level (`and(nestedEq(phones.type,
"home"), nestedEq(phones.number, "555-9999"))`) means "some element has
`type = home` **and** some — *possibly different* — element has
`number = 555-9999`". The absence-collapse rule still holds: a null column, a
missing array, an empty array, a **non-array value** (an explicit JSON `null`, a
JSON scalar, or a JSON object — anything that is not a JSON array collapses to
**zero elements**), or an element whose leaf is not present contributes no matching
element. A non-array value is read as not-present even when its own scalar value or
object content would match the predicate.

**`nestedExists` / `nestedNotExists` test the member itself**, over a
**value-object-terminated** path (`Class.valueObject(.valueObject)*`, ending at a
value object rather than at an inner attribute):

| Operation | Encoding | Meaning |
|---|---|---|
| `nestedExists` | `{ "nestedExists": { "path", "where"? } }` | the value object at `path` is **present** (`one`) or its array is **non-empty** (`many`); with `where`, **at least one** element satisfies the compound sub-predicate |
| `nestedNotExists` | `{ "nestedNotExists": { "path", "where"? } }` | the complement — the value object is **absent** (`one`) or the array is **empty or absent** (`many`); with `where`, **no** element satisfies the compound sub-predicate |

Without `where`, `nestedExists` on a `many` path is a pure non-empty test (an empty
array, a missing key, a JSON `null`, a SQL `NULL` column, **and any non-array value
— a JSON scalar or a JSON object** — all read as not-present, so `nestedNotExists`
matches every one of them — an empty array, a NULL column, and a non-array value are
**indistinguishable** to the algebra, exactly as the scalar absence-collapse rule
folds them).

**The scoped `where` expresses same-element matching.** With `where`, one element
must satisfy the **whole** compound sub-predicate — so `nestedExists` with `where`
is *not* the same as ANDing flat predicates. The sub-predicate inside `where` is
the same `nested*` family re-expressed over **element-relative** paths (`type`,
`geo.country` — declared members of the element, **no** leading `Class.valueObject`)
composed with the ordinary `and` / `or` / `not` / `group` combinators. It resolves
against the element's declared structure; a resolver **MUST** reject an
element-relative path that names an undeclared member.

The discriminating pair, with phones `[{home, 555-1234}, {work, 555-9999}]` (id 1 in
the corpus fixtures):

```yaml
# unscoped AND — MATCHES: different elements may satisfy each predicate
and:
  operands:
    - nestedEq: { path: Customer.address.phones.type,   value: home }
    - nestedEq: { path: Customer.address.phones.number, value: '555-9999' }

# scoped exists — does NOT match: ONE element must satisfy the whole compound
nestedExists:
  path: Customer.address.phones
  where:
    and:
      operands:
        - nestedEq: { path: type,   value: home }
        - nestedEq: { path: number, value: '555-9999' }
```

The unscoped form lowers to two **independent** existence checks (a row where `home`
and `555-9999` live in *different* elements matches); the scoped form lowers to a
**single** existence check binding one element, so both predicates must hold on the
*same* element. `nestedNotExists` with `where` is its negation — "no element
satisfies the compound". The array-traversal spelling per dialect is an `m-dialect`
decision (`m-sql`), never fixed by this algebra.

### Boolean combinators

| Operation | Encoding |
|---|---|
| `and` | `{ "and": { "operands": [ op, op, … ] } }` (≥2 operands) |
| `or` | `{ "or": { "operands": [ op, op, … ] } }` (≥2 operands) |
| `not` | `{ "not": { "operand": op } }` |
| `group` | `{ "group": { "operand": op } }` |

Operand **order is significant** (it is preserved through serde and drives bind
order). The first-class **`group`** node explicitly nests a sub-expression so
precedence round-trips unambiguously: a *prefix* surface (`group(a.or(b)).and(c)`)
and a *fluent* surface (`a.or(b).group().and(c)`) are per-language DX only and
**MUST** serialize to the same canonical `group` node. Because `and` binds tighter
than `or`, `(a or b) and c` requires a `group`, whereas `a or b and c` parses as
`a or (b and c)` and needs none — the two are distinct canonical nodes with
distinct golden SQL.

### Result-shaping directives

Directives wrap an inner operation rather than filtering:

| Operation | Encoding | Effect |
|---|---|---|
| `orderBy` | `{ "orderBy": { "operand", "keys": [ { "attr", "direction"? } ] } }` | order rows; `direction` ∈ `asc` (default) / `desc` |
| `limit` | `{ "limit": { "operand", "count" } }` | cap the row count |
| `distinct` | `{ "distinct": { "operand" } }` | deduplicate rows |

### Temporal read wrappers

Temporal read wrappers are operation nodes. `m-temporal-read` defines the interval
model, default-injection rule, and milestone behavior; `m-sql` fixes the SQL
fragments and bind order. These nodes are part of the algebra because operation
serde must round-trip the temporal query tree exactly.

| Operation | Encoding | Meaning |
|---|---|---|
| `asOf` | `{ "asOf": { "operand", "asOfAttr", "date" } }` | pin one temporal dimension to a single instant |
| `asOfRange` | `{ "asOfRange": { "operand", "asOfAttr", "from", "to" } }` | return milestones whose interval overlaps the half-open range `[from, to)` |
| `history` | `{ "history": { "operand", "asOfAttr" } }` | return the full milestone set on that dimension; no as-of predicate is injected for that axis |

`asOfAttr` is a metamodel as-of-attribute reference of the form
`Class.asOfAttribute`. `date`, `from`, and `to` are temporal pin strings: either
`now` or an ISO-8601 UTC instant. `now` means the current milestone on that axis,
whose upper bound is the `m-core` / `m-dialect` `infinity` sentinel.

Each temporal node wraps an `operand`. A single-axis temporal entity uses one
wrapper. A bitemporal entity pins or unpins both axes by nesting one temporal
wrapper per `asOfAttribute`; omitted axes follow the `m-temporal-read`
default-injection rule and are read as `now`. The injected temporal term composes
with the operand via `and`, after user predicates, so user binds precede temporal
binds.

## Relationship algebra

Relationships (`m-descriptor`) are traversed **by name** — never as a user-written
join. A navigation node references a relationship as `Class.relationship` and (for
the filter forms) carries an optional inner operation constraining the related
entity. These nodes lower to **correlated semi-joins** so a to-many traversal
never multiplies the queried entity's rows (`m-sql`, `m-navigate`).

### Navigation filters

| Operation | Encoding | Meaning |
|---|---|---|
| `navigate` | `{ "navigate": { "rel", "op"? } }` | filter the queried entity by traversing `rel`; `op` (optional) constrains the related entity |
| `exists` | `{ "exists": { "rel", "op"? } }` | the queried entity has ≥1 related row (optionally matching `op`) |
| `notExists` | `{ "notExists": { "rel", "op"? } }` | the queried entity has no related row (optionally matching `op`) |

`rel` is a relationship reference of the form `Class.relationship`. `navigate`
and `exists` are the same correlated-`EXISTS` lowering (a navigation filter *is*
a positive existence check); `notExists` is the negated form. With no `op`,
`exists`/`notExists` are pure existence/absence checks. The inner `op` is a
normal operation tree resolved **against the related entity's attributes**
(`OrderItem.sku`, …), so any predicate from the single-entity algebra composes
inside a navigation.

### `deepFetch` directive

`deepFetch` is an eager-fetch **directive**, not a predicate: it shapes the
result into an **object graph** rather than a flat row set.

| Operation | Encoding | Effect |
|---|---|---|
| `deepFetch` | `{ "deepFetch": { "operand", "paths": [ [ { "rel": …, "narrow"? }, … ], … ] } }` | resolve `operand`, then eager-fetch each navigation `path` |

Each `path` is an ordered list of **path segments** naming a chain to fetch, and
every segment is a **closed object** carrying the relationship to traverse under
`rel` (a `Class.relationship` reference) — one hop (`[{ "rel": "Order.items" }]`)
or multi-hop
(`[{ "rel": "Order.items" }, { "rel": "OrderItem.statuses" }]`). The object
segment is the single structural carrier for a hop, so a **polymorphic** hop (a
relationship whose target is an abstract position, `m-inheritance`) MAY add an
optional `narrow` alongside `rel` — the `{ "to": [ … ] }` subtype narrowing of that
hop's effective concrete set — without a second spelling of a path. Unlike the
operation-position `narrow` node (which carries `entity` + `operand`), a path
narrow carries only `to`: the position is the relationship target (implicit) and a
hop fetches a whole **view**, not a filtered predicate. A narrowed hop populates a
**distinct narrowed view** keyed `<rel>[<Concrete>,<Concrete>]`; the narrow must
resolve within the relationship target's effective set
(`narrow-outside-relationship-target`). The normative guarantee is **one SQL
statement per relationship level** (N+1 elimination): the root query plus one
statement per distinct hop, where hop identity is the pair **(relationship,
effective concrete set)** — a broad hop and a narrowed hop over the same
relationship, or two hops narrowed to different sets, are distinct; equivalent
narrow spellings resolving to the same set converge. Paths sharing a hop fetch it
**once**. This is specified in full in [`m-deep-fetch.md`](m-deep-fetch.md) and
proven by the round-trip-count layer of the compatibility harness
(`m-case-format`).

## Subtype narrowing

An inheritance family (`m-inheritance`) is a closed tree of one abstract `root`,
zero or more `abstract-subtype` interior nodes, and the instantiable
`concrete-subtype` leaves. A read starts at a **polymorphic position** — the
`targetEntity` (`m-case-format`) — which may be abstract: an abstract root spans
the whole family, an abstract subtype spans its concrete descendants, a concrete
subtype is itself. The **effective concrete-subtype set** of a position is the
concrete leaves it resolves over (`m-inheritance`), in the family's **canonical
sibling-set order** — alphabetical by entity name (`m-inheritance`).

`narrow` constrains a polymorphic position to a subset of its subtypes. It is a
node like any other — a single-key tagged object joining the operation `oneOf`:

| Operation | Encoding | Meaning |
|---|---|---|
| `narrow` | `{ "narrow": { "entity", "to": [ … ], "operand" } }` | evaluate `operand` over the position `entity` narrowed to the subtypes `to` |

- **`entity`** names the polymorphic position this node narrows — the queried
  entity at top level (so `entity` equals the read's `targetEntity`), or the
  **relationship target** when the `narrow` appears inside a navigation filter's
  `op` (`exists` / `navigate` / `notExists`), where the active position is the
  related entity the hop reaches (`m-navigate`). Inside a navigation filter's `op`
  the naming is **exact**: `narrow.entity` **MUST equal** the relationship target
  (`m-navigate` owns this rule), and subtypes are reached only through `to` — naming
  a **different** position there, even a broader ancestor, is
  `narrow-outside-relationship-target`, **not** clamped. A narrow whose resolved
  `to` set then escapes the relationship target's effective set is the same rule
  (`narrow-outside-relationship-target`, `m-navigate`, `m-case-format`).
- **`to`** is the non-empty, **order-preserved** list of authored subtype names
  the position is narrowed to. Each entry may name an abstract subtype (which
  resolves to its concrete descendants) or a concrete subtype (itself).
- **`operand`** is the inner operation evaluated over the narrowed position, so a
  **concrete-subtype-declared attribute** — one declared on a proper descendant,
  not inherited by every concrete in the original position — becomes referenceable
  inside it.

```yaml
# targetEntity: Animal (root); narrow to Pet (abstract subtype -> Dog, Cat):
narrow:
  entity: Animal
  to: [Pet]
  operand: { all: {} }
```

### The four-step validation rule

A model-aware validator (never the serde) checks a `narrow` node **before any SQL
is emitted**, threading the **active polymorphic position** as it descends — the
read's `targetEntity` at top level (defaulting to the family root when a case pins
no `targetEntity`), and the enclosing `narrow`'s resolved `to` set inside a nested
narrow:

1. Resolve `entity` to its effective concrete-subtype set and **intersect** it with
   the active position threaded into this node — the **effective position's set**.
   This clamp governs the **top-level** narrow and any **nested same-position**
   narrow (a narrow inside another narrow's `operand`): `entity` names the position
   this node narrows, but it can only ever *constrain* the active position, never
   broaden it, so an `entity` naming a position **broader** than the one in scope is
   **clamped** to the active position (not rejected), and when `entity` equals the
   active position — the normal case, where a top-level `narrow`'s `entity` equals
   the read's `targetEntity` — the intersection is a no-op. **Exception (relationship
   scope):** a narrow appearing in a **navigation filter's `op`** does **not** clamp
   — its `entity` **MUST first name the relationship target exactly** (`m-navigate`),
   and only then does the `to` effective-set subset check (step 4) apply; naming a
   different position there is `narrow-outside-relationship-target`, never a clamp.
2. Resolve each `to` entry to its effective concrete-subtype set (a concrete
   subtype -> itself; an abstract subtype -> its concrete descendants).
3. **Union** the resolved sets and **deduplicate**; the resolved effective set is
   presented in the family's **canonical alphabetical order** (`m-inheritance`),
   independent of the authored `to` spelling.
4. **Accept iff** the resolved set is **non-empty** and a **subset** of the
   effective position's set. The resolved set then becomes the active position for
   `operand`, so a nested `narrow` cannot broaden back out.

Consequences:

- **Redundant narrowing is valid.** Narrowing a position to itself (an abstract
  subtype `to` its own name, or `to` a list whose union equals the position's set)
  is a no-op that still lowers to the tag/branch selection for those concretes.
- **Broadening is invalid.** Narrowing the active position to a subtype **outside**
  it — even one sharing the family root — is rejected (`narrow-outside-position`).
  The check is against the **active** position, so a **nested** `narrow` cannot
  broaden back out of the set the enclosing `narrow` established, and naming a
  broader `entity` on the inner node does not re-widen it (the inner `entity` is
  clamped to the active position first). A `to` list that resolves to the empty set
  is rejected (`narrow-empty-effective-set`) (`m-case-format` rejected vocabulary).
- **A concrete-subtype attribute needs a compatible narrowing scope.** Referencing
  a concrete-subtype-declared attribute at a position whose effective set is not a
  subset of that subtype's is rejected
  (`subtype-attribute-outside-narrow-scope`); wrapping the predicate in a `narrow`
  to that subtype makes it valid.
- **The serde preserves the authored `to` list verbatim.** Semantic validation and
  SQL lowering derive the effective concrete set without rewriting the submitted
  operation, so two authored spellings that resolve to the same set (`to: [Pet]`
  vs `to: [Cat, Dog]`) round-trip as **distinct** canonical nodes.

`narrow`'s lowering — tag-equality / `in` selection under `table-per-hierarchy`,
`union all` over the selected concrete tables under `table-per-concrete-subtype`,
and grouped branch predicates when a branch carries a concrete-subtype predicate —
is fixed by `m-sql`.

## Forward map of the rest of the algebra

For orientation, this schema revision leaves membership `in(subquery)` out of the
required operation set. The temporal (`asOf`, `asOfRange`, `history`) and nested
value-object (the flat `nested*` family — `nestedEq`, `nestedNotEq`, `nestedGt`,
`nestedGte`, `nestedLt`, `nestedLte`, `nestedIn`, `nestedIsNull`,
`nestedIsNotNull` — plus the to-many `nestedExists` / `nestedNotExists` with their
optional element-scoped `where`) nodes are not deferred; their canonical
encodings are part of the algebra, with observable temporal behavior specified by
`m-temporal-read` and SQL lowering specified by `m-sql`. The aggregation nodes
(`groupBy` and friends) are present in `operation.schema.json` but the aggregation
feature is **deferred** — see `m-agg`.
