# m-op-algebra — Query & Operation Algebra

`m-op-algebra` defines the **operation algebra** — the framework's own query
language — and its **canonical serialization**. The algebra *is* the protocol: the
compatibility suite's queries are instances of it, and every implementation
provides operation serde behavior that round-trips them. `m-op-algebra` depends
on `m-metamodel` (resolved operations are bound to canonical Entity, Attribute,
Relationship, and Value Object Identities) and on `m-inheritance` (the `narrow`
node constrains a polymorphic entity position against the family's effective
concrete-subtype set). Relationship behavior is not reconstructed here:
`m-navigate` consumes the compiled `m-relationship` facet.

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

Every implementation **MUST** provide operation serialization/deserialization
behavior, with **round-trip** tests:
`serialize(deserialize(op)) == op`. The reference harness asserts this per case,
in both JSON and YAML. This behavior does not execute operations; its source
ownership, enforcement scope, and deployable-artifact placement are
language-owned under the topology rules in [`modules.md`](modules.md). Idiomatic
per-language re-expressions of a query (fluent builders, etc.) are **illustrative
only** — never the normative encoding.

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
a node may depend on other core modules: `m-metamodel` supplies canonical local
attributes, relationship declarations, As-Of Axes, and Value Objects;
`m-navigate` owns behavior over the compiled `m-relationship` facet; `m-sql`
owns SQL lowering; `m-temporal-read` owns temporal interval behavior.

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

**Bound-ordering rule.** The two bounds describe a range, so a `lower` strictly
greater than its `upper` names an empty range no row can satisfy; a resolver
**MUST** reject it (`between-bounds-inverted`) rather than emit a predicate that
silently matches nothing (`m-case-format` rejected vocabulary). Bounds are
compared by **literal kind**: the rule applies only when both bounds are the same
kind — both `number`s, or both `string`s — and is skipped when the kinds differ
or either bound is `null`. Only a **strictly** greater `lower` is rejected; equal
bounds name the single-value range `>= v AND <= v` and are legal. Comparing by
literal kind keeps the rule free of attribute-type resolution, and ISO-8601
`date` / `timestamp` literals order correctly under string comparison.

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
| `nestedBetween` | `{ "nestedBetween": { "path", "lower", "upper" } }` | the value at `path` lies in the inclusive range `[lower, upper]` |
| `nestedIn` | `{ "nestedIn": { "path", "values" } }` | the value at `path` is one of `values` (non-empty list) |
| `nestedNotIn` | `{ "nestedNotIn": { "path", "values" } }` | the value at `path` is not one of `values` (non-empty list) |
| `nestedLike` | `{ "nestedLike": { "path", "value", "caseInsensitive"? } }` | the value at `path` matches the pattern `value` |
| `nestedNotLike` | `{ "nestedNotLike": { "path", "value", "caseInsensitive"? } }` | the value at `path` does not match the pattern `value` |
| `nestedStartsWith` | `{ "nestedStartsWith": { "path", "value", "caseInsensitive"? } }` | the value at `path` begins with the literal `value` |
| `nestedEndsWith` | `{ "nestedEndsWith": { "path", "value", "caseInsensitive"? } }` | the value at `path` ends with the literal `value` |
| `nestedContains` | `{ "nestedContains": { "path", "value", "caseInsensitive"? } }` | the value at `path` contains the literal `value` |
| `nestedIsNull` | `{ "nestedIsNull": { "path" } }` | the value at `path` is **not present** (see the absence-collapse rule) |
| `nestedIsNotNull` | `{ "nestedIsNotNull": { "path" } }` | the value at `path` **is present** (the complement) |

The five string predicates carry a plain `string` `value` rather than a polymorphic
literal; the rest of the comparison / range / membership `value`(s) are polymorphic
`literal`s (`string`
/ `number` / `boolean` / `null`), and each type **MUST** match the leaf attribute's
declared neutral type; a resolver **MUST** reject a type-mismatched literal (e.g. a
`number` compared against a `string`-typed attribute). The presence tests
(`nestedIsNull` / `nestedIsNotNull`) carry a `path` only. `m-sql` lowers a nested
read to a dialect-specific extraction from the structured-document column and
**casts** it to the declared type before comparing; the extraction spelling, the
typed-cast form, and the **bind order** (per-segment JSON keys vs a single path
bind) are all `m-dialect` decisions (`m-sql`, `m-dialect`), not fixed by this
algebra.

`nestedBetween` is **one** canonical node — it is never rewritten into a pair of
comparisons, because the two forms diverge through a `many` segment (below). Both
its bounds are typed literals against the same leaf, and the bound-ordering rule
above governs it unchanged. Within a range node the checks are ordered **subject
first, bounds second**: the path resolves and both bounds are type-checked before
the bounds are ordered, so a mistyped bound draws `nested-literal-type-mismatch`
rather than being ordered as a raw literal.

The five nested string predicates carry the **String** section's semantics above
unchanged, against the nested extraction instead of a column: `nestedLike` /
`nestedNotLike` take `value` as the SQL pattern with `%` and `_` as wildcards and
never escape it, the affix forms (`nestedStartsWith` / `nestedEndsWith` /
`nestedContains`) take it as literal text whose own `%`, `_`, and escape characters
the implementation **MUST** escape before wrapping with the affix wildcards, and
`caseInsensitive` folds both sides with `lower(...)`. There is one rule for both
scopes and for the top level; nothing about the pattern grammar changes because the
subject is nested. Their `value` is a plain `string` rather than a polymorphic
literal, which is why the leaf's own type carries the rule below rather than the
literal's.

**Non-string-member rule.** A string predicate reads text, so its resolved leaf's
declared neutral type **MUST** be `String`; a resolver **MUST** reject any other
leaf (`nested-string-predicate-non-string-member`, `m-case-format` rejected
vocabulary). This is a **separate** rule from the typed-literal one, and the two are
checked in order — **subject first**, exactly as a range's bound ordering is: the
path resolves, the leaf's type is checked against the predicate, and only then is
the literal checked.

```text
resolve nested member -> leaf
if the predicate is a string predicate and leaf.type is not String:
    reject("nested-string-predicate-non-string-member")
if not literal_matches_type(value, leaf.type):
    reject("nested-literal-type-mismatch")
```

Ordering them the other way would blame the literal for the member's problem, and —
because the algebra's portable literal vocabulary carries `Date` / `Time` /
`Timestamp` / `Uuid` / `Bytes` as `string`s — would **accept** `nestedStartsWith`
against a `Date` member rather than reject it. The dedicated rule names the real
fault and closes that hole.

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
(`nestedEq` / `nestedNotEq` / `nestedGt` / `nestedGte` / `nestedLt` / `nestedLte`),
a range (`nestedBetween`), a membership test (`nestedIn` / `nestedNotIn`), and a
string predicate (`nestedLike` / `nestedNotLike` / `nestedStartsWith` /
`nestedEndsWith` / `nestedContains`) are
neither true — the row is **excluded**, exactly as the scalar `notEq`/`notIn` null
behavior above. The negative forms are not exceptions: `nestedNotEq`,
`nestedNotIn`, and `nestedNotLike` over a not-present member yield `NULL`, not
true, so absence never satisfies a negative predicate. `nestedIsNull` is true
**exactly** on the
rows a comparison excludes for this reason (all four not-present states);
`nestedIsNotNull` is its complement (the present rows). An implementation **MUST
NOT** distinguish JSON `null` from a missing key or a null column at the predicate
level — the states stay distinguishable in the stored data but are indistinguishable
to the algebra.

#### To-many members — any-element and same-element semantics

A value object declared `multiplicity: many` is an ordered **JSON array** of documents in the
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

**A range still binds one element.** Because `nestedBetween` is one node rather
than two comparisons, a row matches it iff **some single element** satisfies
`>= lower AND <= upper` together. Rewriting it as
`and(nestedGte(…, lower), nestedLte(…, upper))` would be a *different* predicate
through a `many` segment: the two flat comparisons evaluate independently, so two
*different* elements could satisfy one bound each. That is precisely why the node
is canonical and never lowered as a pair.

**Any-element is uniform across the whole flat family, negative forms included.**
`nestedNotEq`, `nestedNotIn`, and `nestedNotLike` through a `many` segment mean
"**some** element's member is not equal to / not in the list / not like the
pattern", never "**no** element's member is". The
two readings differ on real data, so the choice is observable: with phones
`[{home, 555-1234}, {work, 555-9999}]`, `nestedNotIn(phones.type, [work])` matches
that row (its first element's `type` is `home`), while the no-element reading does
not. The no-element reading is already spellable, and that is why it is not
overloaded onto `nestedNotIn`:

```yaml
# any-element — the meaning of nestedNotIn: SOME element's type is not `work`
nestedNotIn: { path: Customer.address.phones.type, values: [work] }

# no-element — spelled with nestedNotExists: NO element's type is `work`
nestedNotExists:
  path: Customer.address.phones
  where:
    nestedIn: { path: type, values: [work] }
```

**The absence rule inside an element.** An element that does not carry the member
at all — a missing key, an explicit JSON `null`, or a non-object blocking descent —
extracts SQL `NULL`, so ordinary three-valued logic excludes it: that element
satisfies neither the positive nor the negative form and contributes no matching
element. A row therefore matches `nestedNotIn` only when some element **has** the
member and its value is outside the list, exactly as it matches `nestedIn` only
when some element has the member and its value is inside it.

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
| `orderBy` | `{ "orderBy": { "operand", "keys": [ { "attr", "direction"?, "nulls"? } ] } }` | order rows; `direction` ∈ `asc` (default) / `desc`; `nulls` ∈ `first` / `last` (default `last`) |
| `limit` | `{ "limit": { "operand", "count" } }` | cap the row count |
| `distinct` | `{ "distinct": { "operand" } }` | deduplicate rows |

A Sort Key's `nulls` member is its **Null Placement**: where `NULL`s sort on that
key, independent of `direction`. Omitting it means `last` — the canonical,
dialect-independent default in both directions — and an authored value survives
canonical round-trip distinctly from omission. Placement is a property of the key,
not of the dialect: the two dialects' native placement diverges, so `m-dialect`
carries the per-dialect lowering that makes the observable order identical
everywhere. It is observable only on a **nullable** attribute; on a non-nullable one
both placements denote the same order and lower to the same term.

These directives shape the **result set** — its order, its cardinality, its
deduplication — but **none of them changes the projected column list**. The algebra
carries **no projection node** at all: a read's `select` list is a pure function of
its target and result form, supplied by `m-sql` (its *Read projection* section),
never chosen by the operation. A column-subset result is therefore expressible only
through the aggregation algebra (`m-agg`, deferred); and because the primary key is
always projected, `distinct` over an entity read is structurally row-preserving.

### Temporal read wrappers

Temporal read wrappers are operation nodes. `m-temporal-read` defines the interval
model, default-injection rule, and milestone behavior; `m-sql` fixes the SQL
fragments and bind order. These nodes are part of the algebra because operation
serde must round-trip the temporal query tree exactly.

| Operation | Encoding | Meaning |
|---|---|---|
| `asOf` | `{ "asOf": { "operand", "dimension", "coordinate" } }` | pin one temporal dimension to Latest or a finite instant |
| `asOfRange` | `{ "asOfRange": { "operand", "dimension", "start", "end" } }` | return milestones whose interval overlaps the half-open range `[start, end)` |
| `history` | `{ "history": { "operand", "dimension" } }` | return the full milestone set on that dimension; no as-of predicate is injected for that axis |

`dimension` is `validTime` or `transactionTime`, resolved against the target
Entity's effective As-Of Axes. `coordinate` is either the literal `latest` or an
ISO-8601 UTC instant. Latest lowers to the dimension's physical end column equal
to the `m-core` / `m-dialect` `infinity` sentinel. A finite current-clock instant
is Now and lowers to interval containment; `now` is not a serde alias for Latest.
`start` and `end` are finite ISO-8601 UTC instants with `start < end`.

Each temporal node wraps an `operand`. A Transaction-Time-Only Entity uses one
wrapper. A Bitemporal Entity pins or unpins both dimensions by nesting one
temporal wrapper per dimension; omitted dimensions follow the `m-temporal-read`
default-injection rule and are read as Latest. The canonical nesting and bind
order is Valid Time followed by Transaction Time. The injected temporal term
composes with the operand via `and`, after user predicates, so user binds precede
temporal binds.

## Relationship algebra

Relationships are traversed **by canonical Relationship Identity** — never as a
user-written join. The canonical wire form spells that identity as
`Class.relationship`; resolution binds it to `m-metamodel`, while `m-navigate`
uses the compiled `m-relationship` facet for target and join behavior. A
navigation node references a relationship and (for
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
| `deepFetch` | `{ "deepFetch": { "operand", "paths": [ { "narrow"?: { "entity", "to": [ … ] }, "segments": [ { "rel": …, "narrow"? }, … ] }, … ] } }` | resolve `operand`, then eager-fetch each navigation `path` |

Each `path` is a **closed object** whose required `segments` member is the
ordered, non-empty list of **path segments** naming the chain to fetch, and
every segment is itself a **closed object** carrying the relationship to traverse
under `rel` (a `Class.relationship` reference) — one hop
(`{ "segments": [{ "rel": "Order.items" }] }`) or multi-hop
(`{ "segments": [{ "rel": "Order.items" }, { "rel": "OrderItem.statuses" }] }`).
The object path is the single structural carrier for a path, keeping what
qualifies the path as a whole distinguishable from what qualifies one hop. The
object segment is likewise the single structural carrier for a hop, so a
**polymorphic** hop (a relationship whose target is an abstract position,
`m-inheritance`) MAY add an optional `narrow` alongside `rel` — the
`{ "to": [ … ] }` subtype narrowing of that hop's effective concrete set —
without a second spelling of a path. Unlike the operation-position `narrow` node
(which carries `entity` + `operand`), a path narrow carries only `to`: the
position is the relationship target (implicit) and a hop fetches a whole
**view**, not a filtered predicate. A narrowed hop populates a
**distinct narrowed view** keyed `<rel>[<Concrete>,<Concrete>]`; the narrow must
resolve within the relationship target's effective set
(`narrow-outside-relationship-target`). The normative guarantee is **one SQL
statement per relationship level** (N+1 elimination): the root query plus one
statement per distinct hop, where hop identity is the triple **(relationship,
whether a narrow was authored, effective concrete set)** — a broad hop and any
authored narrow over the same relationship, or two hops narrowed to different
sets, are distinct; equivalent narrow spellings resolving to the same set
converge. Paths sharing a hop fetch it **once**. This is specified in full in [`m-deep-fetch.md`](m-deep-fetch.md) and
proven by the round-trip-count layer of the compatibility harness
(`m-case-format`).

A path MAY additionally carry a **path-root `narrow`** — `{ "entity", "to" }`,
both required — beside `segments`. It **guards which queried objects the path
starts from** without changing the read's own result set, so a caller whose
`targetEntity` is polymorphic can eager-fetch a relationship for one branch of
the family alone:

```yaml
# targetEntity: Animal; `owner` is declared on Animal, so Dogs and Cats reach it
# under the one relationship identity `Animal.owner`:
deepFetch:
  operand: { all: {} }
  paths:
    - { narrow: { entity: Animal, to: [Dog] }, segments: [{ rel: Animal.owner }] }
    - { narrow: { entity: Animal, to: [Cat] }, segments: [{ rel: Animal.owner }] }
```

The root position and the segment position narrow **opposite things**, and their
hop identities follow:

- a **root** guard restricts a hop's SOURCE objects and creates **no** view key —
  every hop of a guarded path populates the view its unguarded spelling would, on
  fewer objects. Identity at the root keys on the **resolved source set** alone,
  so two guards resolving to the same concretes are one hop and a guard admitting
  every queried object *is* the broad path.
- a **segment** narrow restricts a hop's TARGET and creates a distinct narrowed
  view. Identity there keys on whether a narrow was **authored** as well as on the
  set it resolves to, because the view key is derived from the authoring.

`m-deep-fetch` specifies the consequences in full; `m-inheritance` owns the
resolution of `entity` and `to`, which is the same four-step rule the
operation-position `narrow` node below follows, with the same rejections.

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

Narrowing appears at exactly **three positions**, which differ in what names the
position and in what the narrowing produces:

| Position | Shape | Position named by | Produces |
|---|---|---|---|
| operation | `{ entity, to, operand }` | `entity`, clamped to the active position | the narrowed position `operand` evaluates over |
| deep-fetch path root | `{ entity, to }` | `entity`, clamped the same way | a source guard — no view key |
| deep-fetch path segment | `{ to }` | the hop's relationship target, implicitly | a distinct narrowed view key |

The four-step rule below governs the first two; the third resolves against the
relationship target instead (`narrow-outside-relationship-target`, `m-navigate`).

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

A **path-root narrow** is checked by the same four steps against the position
active where its `deepFetch` node sits, and raises the same
`narrow-empty-effective-set` / `narrow-outside-position`. Only step 4's second
half differs: a guard carries no `operand`, so its resolved set becomes the
path's **source set** rather than an active position — it qualifies which objects
the path's hops start from, never what the read returns and never what any
predicate resolves against.

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
- **An attribute reference outside the active position's family is rejected
  outright.** The rule above is the **family** half of one positional rule: an
  attribute reference is applicable only where the active position's effective set
  is a subset of the referenced Entity's. When the referenced Entity and the active
  position share **no** inheritance family — an unrelated Entity, or one in another
  family — no `narrow` can make the reference applicable, so it is rejected as
  `attribute-outside-active-position` rather than as a scope a narrow could fix. The
  two rules partition one condition: same family, `subtype-attribute-outside-narrow-scope`;
  different family, `attribute-outside-active-position`.
- **An order key's attribute reference is checked at the position it orders.**
  An `orderBy` key names an attribute exactly as a predicate does and takes the
  same positional rule, but the position it is asked of is the one its **ordered
  rows** occupy: a **top-level `narrow`** in the ordered operand — the node a
  whole-result narrowing produces, reached through the result-shaping and temporal
  wrappers that may carry it — moves that position, while a `narrow` appearing as a
  predicate term inside a boolean combinator is a filter and moves nothing. So
  ordering an abstract position by a concrete subtype's attribute is rejected, and
  ordering that same position **narrowed to** that subtype is not.
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
