# m-predicate — Predicate Algebra

`m-predicate` defines the framework's recursive **Predicate algebra** and its
**canonical serialization**: the selection grammar and nothing else. A Predicate
answers *which objects*; it never states which position they are selected from,
how they are ordered, how many come back, at which temporal coordinates, or what
is fetched alongside them — every one of those is a sibling clause of the
`m-object-query` value that CARRIES a predicate. Recursion therefore buys
composition of selection logic alone, and the shapes a recursive query
representation admits by accident — a row cap as a Boolean term, an ordering over
an eager fetch — have no spelling here rather than a rejection rule.

`m-predicate` depends on `m-metamodel` (resolved predicates are bound to
canonical Entity, Attribute, Relationship, and Value Object Identities) and on
`m-inheritance` (the `narrow` node constrains a polymorphic entity position
against the family's effective concrete-subtype set). Relationship behavior is
not reconstructed here: `m-navigate` consumes the compiled `m-relationship`
facet.

The canonical schema is
[`core/schemas/predicate.schema.json`](../schemas/predicate.schema.json).

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

## Canonical Predicate encoding (serde seam)

A Predicate is a tree of **nodes** with a **format-agnostic canonical
serialization**. This serialized form is the suite's normative encoding — one
source of truth so every implementation tests the same Predicate. Concrete
encodings exist in at least **JSON and YAML** (a format-agnostic core plus
pluggable writers); the format set is consistent with metamodel serde
(`m-descriptor`).

Every implementation **MUST** provide Predicate serialization/deserialization
behavior, with **round-trip** tests:
`serialize(deserialize(op)) == op`. The reference harness asserts this per case,
in both JSON and YAML. This behavior does not execute operations; its source
ownership, enforcement scope, and deployable-artifact placement are
language-owned under the topology rules in [`modules.md`](modules.md). Idiomatic
per-language re-expressions of a query (fluent builders, etc.) are **illustrative
only** — never the normative encoding.

The encoding is a tagged object: each node is a single-key object whose key names
the predicate kind. Attribute references are `Class.attribute` strings, resolved
against the model. Examples:

```json
{ "all": {} }
```

```json
{ "eq": { "attr": "Order.id", "value": 42 } }
```

## Predicate set

`m-predicate` is the canonical Predicate algebra. Its schema covers the
single-entity predicate algebra, relationship navigation, Predicate-scoped
subtype narrowing, and nested value-object predicates. Aggregation is a separate
query form owned by `m-agg`; its interchange schema does not extend this
Predicate union. Each node below carries a single canonical
serialization; a conforming Predicate serde implementation **MUST**
validate and round-trip every node in `predicate.schema.json` unchanged. Executing
a node may depend on other core modules: `m-metamodel` supplies canonical local
attributes, relationship declarations, As-Of Axes, and Value Objects;
`m-navigate` owns behavior over the compiled `m-relationship` facet; `m-sql`
owns SQL lowering; `m-temporal-read` owns temporal interval behavior.

### Entity spellings in a reference position

Every predicate position that names an Entity spells it either **bare** — the
Entity's local name alone — or **canonically**, the namespace-qualified
`<namespace>.<Entity>` of `m-metamodel`. The positions are the Entity prefix of
an `attr`, a `rel`, and a nested value-object `path`, plus each Subtype Selection
alternative. `m-object-query`'s own reference positions — the queried `target`, a
Sort Key's `attr`, an Include Segment's `rel` — carry the identical rule.

**Input is permissive; output is exact.** A bare spelling remains legal at every
one of those positions and MUST resolve whenever it names exactly one declared
Entity model-wide. Everything an implementation **serializes** — every predicate
or query document a frontend emits — MUST carry the resolved canonical Entity
spelling.
The two rules are not in tension: an implementation accepts what an author
writes and emits what the model resolved it to.

Splitting a reference into its Entity spelling and its member path is
`m-metamodel`'s parse rule — *the last capitalized segment is the Entity's local
name* — and needs no model: `parallax.compatibility.Order.id` names the Entity
`parallax.compatibility.Order` and the member `id`, while `Order.address.city`
names the Entity `Order` and the member path `address.city`. An element-relative
path inside a scoped `where` carries no capitalized segment and so names no
Entity; its subject is the array element the enclosing exists binds.

Entity Identity is **namespace-qualified** (`m-metamodel`), so one model may
declare the same local name in two namespaces. A **bare** reference naming such a
name resolves to **no single Entity**, and a resolver **MUST** reject it
(`reference-ambiguous-entity-name`) rather than answer it with the first matching
declaration — that first match would be applicable, lowerable, and wrong,
answering against one Entity's table for a spelling that names another's equally.
The canonical spelling is the remedy: it names one of the two exactly, and a
resolver MUST accept it.

This rule and the two positional rules under *Subtype narrowing* partition one
condition in resolution order: this one fires when a reference resolves to **more
than one** Entity and therefore to none; those fire when a reference **did**
resolve, to an Entity outside the active position.

The refusal is a property of the **reference site**, not of the model. Both
Entities remain declarable, remain materializable under their exact qualified
identities, and remain readable through any position that names them
unambiguously — the canonical spelling, a family root, or a relationship target a
hop resolves through a declaration rather than through the operation's own
spelling. A position carried **beside** an operation rather than inside it — the
queried position a read names, or the target entity of a predicate-selected
write — admits the same two spellings and resolves by the same rule; the surface
owning that position names the refusal in its own vocabulary rather than in this
one.

### Identities

| Predicate | Encoding | Meaning |
|---|---|---|
| `all` | `{ "all": {} }` | the identity — selects every row (no `WHERE`) |
| `none` | `{ "none": {} }` | the absorbing element — matches nothing |

`none` is the dual of `all`; it lowers to an unsatisfiable predicate.

### Equality and range

Each takes `{ "attr": "Class.attribute", "value": <literal> }`. The value becomes
a bind placeholder in the golden SQL.

| Predicate | SQL operator |
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

| Predicate | Pattern semantics |
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

| Predicate | Encoding | Meaning |
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
read to a dialect-specific extraction from the structured-document column and,
where the declared type requires one, **casts** it before comparing; the extraction
spelling, which types cast and which compare as the canonical document text, the
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

| Predicate | Encoding | Meaning |
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

| Predicate | Encoding |
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

## Relationship algebra

Relationships are traversed **by canonical Relationship Identity** — never as a
user-written join. The canonical wire form spells that identity as
`Class.relationship`; resolution binds it to `m-metamodel`, while `m-navigate`
uses the compiled `m-relationship` facet for target and join behavior. A
navigation node references a relationship and (for
the filter forms) carries an optional inner predicate constraining the related
entity. These nodes lower to **correlated semi-joins** so a to-many traversal
never multiplies the queried entity's rows (`m-sql`, `m-navigate`).

### Navigation filters

| Predicate | Encoding | Meaning |
|---|---|---|
| `navigate` | `{ "navigate": { "rel", "op"? } }` | filter the queried entity by traversing `rel`; `op` (optional) constrains the related entity |
| `exists` | `{ "exists": { "rel", "op"? } }` | the queried entity has ≥1 related row (optionally matching `op`) |
| `notExists` | `{ "notExists": { "rel", "op"? } }` | the queried entity has no related row (optionally matching `op`) |

`rel` is a relationship reference of the form `Class.relationship`. `navigate`
and `exists` are the same correlated-`EXISTS` lowering (a navigation filter *is*
a positive existence check); `notExists` is the negated form. With no `op`,
`exists`/`notExists` are pure existence/absence checks. The inner `op` is a
normal predicate tree resolved **against the related entity's attributes**
(`OrderItem.sku`, …), so any predicate from the single-entity algebra composes
inside a navigation.

## Subtype narrowing

`m-inheritance` owns the shared **Subtype Selection** value, its canonical
construction, and its model-aware resolution inside a polymorphic position. The
`narrow` node here is **Predicate-scoped**: it narrows the active position for
its own inner predicate and is therefore a filter. Whole-result narrowing is
`narrowTo` on the Object Query and has no spelling in this grammar, so the two
can never be confused for one another:

| Predicate | Encoding | Meaning |
|---|---|---|
| `narrow` | `{ "narrow": { "to": [ … ], "operand" } }` | evaluate `operand` over the active position narrowed by the Subtype Selection `to` |

The containing structure supplies the position: at the top of a query's
`predicate` it is the query's own result position (its `target`, narrowed by its
`narrowTo` clause), a Boolean term uses that Boolean expression's active
position, a `navigate` / `exists` / `notExists` filter uses the relationship
target, and a `narrow` inside another `narrow`'s operand uses the enclosing
selection's resolved position. The position is never repeated in the node. `operand` is evaluated over the selection's resolved position, so a
concrete-subtype-declared attribute becomes referenceable there.

```yaml
# target: Animal (root); narrow to Pet (abstract subtype -> Dog, Cat):
narrow:
  to: [Pet]
  operand: { all: {} }
```

Subtype Selection construction and the clamp/resolve/union/subset rule are
specified once in `m-inheritance`. This module adds these operand consequences:

- **Redundant narrowing is valid.** Narrowing a position to itself (an abstract
  subtype `to` its own name, or `to` a list whose union equals the position's set)
  is a no-op that still lowers to the tag/branch selection for those concretes.
- **Broadening is invalid.** Narrowing the active position to a subtype **outside**
  it — even one sharing the family root — is rejected (`narrow-outside-position`).
  The check is against the **active** position, so a **nested** `narrow` cannot
  broaden back out of the set the enclosing `narrow` established. A `to` list that resolves to the empty set
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
  different family, `attribute-outside-active-position`. Both presuppose a
  reference that **resolved**; one whose bare spelling two namespaces share
  resolves nowhere and is `reference-ambiguous-entity-name` (*Entity spellings in
  a reference position*).
- **An order key's attribute reference is checked at the position it orders.**
  A Sort Key names an attribute exactly as a predicate does and takes the same
  positional rule, but the position it is asked of is the one its **ordered rows**
  occupy: the query's own `narrowTo` clause, which is a sibling of `orderBy`
  rather than a node between them. A Predicate-scoped `narrow` is a filter and
  moves nothing. So ordering an abstract position by a concrete subtype's
  attribute is rejected, and ordering that same position **narrowed to** that
  subtype is not (`m-object-query`).
- **Serde writes canonical selection order.** Two selections are equal regardless
  of authored order, and serialization orders alternatives by
  `EntityIdentity.sort_key`. Distinct selections that resolve to the same effective
  set (`to: [Pet]` versus `to: [Cat, Dog]`) remain distinct canonical nodes.

`narrow`'s lowering — tag-equality / `in` selection under `table-per-hierarchy`,
`union all` over the selected concrete tables under `table-per-concrete-subtype`,
and grouped branch predicates when a branch carries a concrete-subtype predicate —
is fixed by `m-sql`.

## Forward map of the rest of the algebra

For orientation, this schema revision leaves membership `in(subquery)` out of the
required predicate set. The nested value-object nodes — the flat `nested*` family
(`nestedEq`, `nestedNotEq`, `nestedGt`, `nestedGte`, `nestedLt`, `nestedLte`,
`nestedIn`, `nestedIsNull`, `nestedIsNotNull`) plus the to-many `nestedExists` /
`nestedNotExists` with their optional element-scoped `where` — have canonical
encodings and are part of the algebra, with SQL lowering specified by `m-sql`.
Temporal Selection is a clause of `m-object-query`, whose observable behavior
`m-temporal-read` specifies.
