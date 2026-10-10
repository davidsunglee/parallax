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
canonical Entity, Attribute, Relationship, and Value Object Identities), on
`m-inheritance` (the `narrow` node constrains a polymorphic entity position
against the family's effective concrete-subtype set), and on `m-wire` (for
serialized typed-literal conversion and each scalar type's encoded JSON kind). Relationship behavior is
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
in both JSON and YAML. This behavior executes no predicate; its source
ownership, enforcement scope, and deployable-artifact placement are
language-owned under the topology rules in [`modules.md`](modules.md). Idiomatic
per-language re-expressions of a query (fluent builders, etc.) are **illustrative
only** — never the normative encoding.

The encoding is a tagged object: each node is a single-key object whose key names
the predicate kind. A field is addressed by a `path` string resolved against the
model. Examples:

```json
{ "true": {} }
```

```json
{ "eq": { "path": "Order.id", "value": 42 } }
```

Serialized Predicate literal positions admit only non-null string, number, or
boolean Wire Values. Arrays and objects remain valid at write and document seams
for a member declared as Json, but they are not Predicate literals. Static
Predicate schemas enforce only this model-free carrier shape; declared-type
grammar is checked after member resolution.

## Predicate set

`m-predicate` is the canonical Predicate algebra. Its schema covers Boolean
constants and composition, scalar operations over a field or a bound scalar
element, explicit quantifiers over every collection kind, single-object presence,
and Predicate-scoped subtype narrowing. Aggregation is a separate query form owned
by `m-agg`; its interchange schema does not extend this Predicate union. Each node
below carries a single canonical serialization; a conforming Predicate serde
implementation **MUST** validate and round-trip every node in
`predicate.schema.json` unchanged. Executing a node may depend on other core
modules: `m-metamodel` supplies canonical attributes, relationship declarations,
As-Of Axes, and Value Objects; `m-navigate` owns behavior over the compiled
`m-relationship` facet; `m-sql` owns SQL lowering; `m-temporal-read` owns temporal
interval behavior.

### Entity spellings in a reference position

Every predicate position that names an Entity spells it either **bare** — the
Entity's local name alone — or **canonically**, the namespace-qualified
`<namespace>.<Entity>` of `m-metamodel`. The positions are the Entity prefix of an
Entity-qualified `path`, plus each Subtype Selection alternative.
`m-object-query`'s own reference positions — the queried `target`, a Sort Key's
`attr`, an Include Segment's `rel` — carry the identical rule.

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
names the Entity `Order` and the member path `address.city`. A relative path
carries no capitalized segment and so names no Entity; its subject is the object
the enclosing scope binds (*Paths and scopes*).

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
hop resolves through a declaration rather than through the predicate's own
spelling. A position carried **beside** a predicate rather than inside it — the
queried position a read names, or the target entity of a predicate-selected
write — admits the same two spellings and resolves by the same rule; the surface
owning that position names the refusal in its own vocabulary rather than in this
one.

### Paths and scopes

Every operation reads its subject from a **scope**, and the scope decides how a
`path` is spelled:

| Scope | Opened by | Path spelling |
|---|---|---|
| the queried Entity position | the query (or predicate-selected write) itself | **Entity-qualified** (`Order.status`) |
| a related Entity | a quantifier over a to-many relationship, or a path-targeted `narrow` | **relative** to the bound Entity (`sku`) |
| a Value Object element | a quantifier over a `many` value object | **relative** to the element (`type`, `geo.country`) |
| a scalar element | a quantifier over a scalar collection | **none** — the operation omits `path` |

A path follows **single** members only: from its head it may continue through a
`one` value object or a to-one relationship, and it stops at the member it names —
a scalar attribute, a scalar collection, a value object, or a relationship. A
resolver **MUST** reject a path that

- names an undeclared member, or continues past a scalar
  (`path-unknown-member`);
- continues past a `many` value object or a to-many relationship
  (`path-crosses-many`) — every many crossing is an explicit quantifier, and the
  path continues relative to the element it binds;
- ends on a member the operation cannot address (`path-target-kind-mismatch`): a
  scalar operation needs a field, a quantifier a collection, a presence test a
  single value object or to-one relationship, and a path-targeted `narrow` a
  to-one relationship;
- is spelled for another scope (`predicate-subject-outside-scope`): a relative
  path at the queried position, an Entity-qualified one inside a bound scope, a
  field inside a scalar-element scope, a subjectless operation outside one, or a
  `narrow` without a target inside an element scope.

Each segment resolves against declared structure: an Entity's applicable members,
a value object's declared members (`m-value-object` — a recursive, typed
composite, never opaque JSON keys), and a relationship's declared target. Because
the structure is declared, a resolved field has a neutral type and every
comparison is **typed**. A subject reached through a to-one relationship is read
at that **related position**, and a quantifier over a collection reached that way
ranges over the related object's collection (*Single-valued traversal*).

### Constants

| Predicate | Encoding | Meaning |
|---|---|---|
| `true` | `{ "true": {} }` | the identity — selects every row (no `WHERE`) |
| `false` | `{ "false": {} }` | the absorbing element — matches nothing |

Constants are subjectless and carry empty bodies; they are not Boolean field
tests. A constant does not bypass a query's other clauses: an unfiltered query is
still positioned, ordered, limited, and temporally selected by them.

### Equality and range

Each takes `{ "path"?, "value": <literal> }`. The value becomes a bind placeholder
in the golden SQL. `path` names an object field; it is omitted exactly when the
subject is the scalar element a scalar-collection quantifier binds.

| Predicate | SQL operator |
|---|---|
| `eq` | `=` |
| `notEq` | `<>` |
| `greaterThan` | `>` |
| `greaterThanEquals` | `>=` |
| `lessThan` | `<` |
| `lessThanEquals` | `<=` |

`between` is **one** canonical node over a bounded pair and takes
`{ "path"?, "lower", "upper" }`; it lowers to `<subject> between ? and ?` (two
ordered binds: lower, then upper). It is never rewritten into a pair of
comparisons: inside a quantifier one element must satisfy both bounds together.

**Bound-ordering rule.** The two bounds describe a range, so a `lower` strictly
greater than its `upper` names an empty range no row can satisfy; a resolver
**MUST** reject it (`between-bounds-inverted`) rather than emit a predicate that
silently matches nothing (`m-case-format` rejected vocabulary). Resolution is
ordered: resolve the subject, decode the lower bound, decode the upper bound,
then compare the two managed values. A conversion failure therefore wins over
`between-bounds-inverted`. Only a **strictly** greater lower bound is rejected;
equal bounds name the single-value range and are legal.

After resolving the subject, a resolver **MUST** call
`m-wire.decodeWire(member.neutralType, literal)` exactly once per typed literal and
retain only the managed result. Wire failures map to
`neutral-literal-type-mismatch`, `neutral-literal-noncanonical`, or
`neutral-literal-out-of-space`, with the canonical resolved member and literal
location.

### Null

`isNull` / `isNotNull` take `{ "path" }` — always a field: a scalar element is
never null to the algebra, so a subjectless null check is refused
(`predicate-subject-outside-scope`). Per SQL three-valued logic, `isNotNull`
excludes NULL rows; `notLike`/`notIn`/`notEq` against a NULL subject likewise
yield NULL (not true) and so exclude that row.

A null check is meaningful only where the declared member admits null. A
model-aware resolver **MUST** reject a null check over a non-nullable member
(`null-check-non-nullable-member`, `m-case-format` rejected vocabulary) before
emitting SQL. This is checked at the resolved member in every scope; physical
Columns or Document placement does not change the verdict. A scalar collection is
never nullable, so a null check over one is refused by this rule.

### Scalar collections

A scalar collection (`m-metamodel`) is a sequence of values rather than one
value, and no operation reaches its elements implicitly. A model-aware resolver
**MUST** reject a comparison, range, membership, or string predicate whose `path`
resolves to a scalar collection (`scalar-collection-unquantified`, `m-case-format`
rejected vocabulary). The subject is judged before any literal is decoded, so the
rule is named rather than a literal mismatch against the element type. The
elements are reached only through a quantifier (*Quantifiers*).

### String

The string predicates take `{ "path"?, "value", "caseInsensitive"? }`
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

**Case-insensitive rule.** When `caseInsensitive` is `true`, both the subject and
the pattern are folded with `lower(...)`: `lower(<subject>) like lower(?)`. (A
language MAY use a dialect-native case-insensitive operator behind the `m-sql`
seam; the golden SQL fixes the portable `lower(...)` form.)

**Non-string-member rule.** A string predicate reads text, so its resolved
member's declared neutral type **MUST** be `String`; a resolver **MUST** reject any
other member (`string-predicate-non-string-member`, `m-case-format` rejected
vocabulary), in every scope. This is a **separate** rule from the typed-literal
one, and the two are checked in order — **subject first**, exactly as a range's
bound ordering is: the subject resolves, its type is checked against the
predicate, and only then is the pattern checked.

Ordering them the other way would blame the pattern for the member's problem, and
— because the algebra's portable literal vocabulary carries `Date` / `Time` /
`Timestamp` / `Uuid` / `Bytes` as `string`s — would **accept** `startsWith` against
a `Date` member rather than reject it.

### Membership

`in` / `notIn` take `{ "path"?, "values": [ … ] }` (non-empty). Each value is a
bind, in list order; the SQL is `<subject> in (?, ?, …)`. The `in(subquery)` form
is not part of this schema revision.

### Value-object fields

A field inside a value object is addressed by the same dotted `path` as any other
field (`Order.address.city`, or `geo.country` inside a value-object quantifier).
`m-sql` lowers it to a dialect-specific extraction from the structured-document
column and, where the declared type requires one, **casts** it before comparing;
the extraction spelling, which types cast and which compare as the canonical
document text, the typed-cast form, and the **bind order** are `m-dialect`
decisions (`m-sql`), not fixed by this algebra.

#### Absence-collapse rule

A value-object field is in exactly one of two observable conditions: **present** —
the extraction yields a non-NULL, non-JSON-`null` scalar — or **not present**. Four
distinguishable storage states all collapse to **not present**, uniformly, for
every operation over the field:

- the value-object **column is SQL `NULL`** (the whole value object is absent);
- a **path segment is missing** from the stored document (no such key);
- the selected value is an explicit **JSON `null`**;
- an **intermediate segment is a non-object** (a scalar or array blocks descent).

In every one of these the extraction yields SQL `NULL`, so a comparison, a range,
a membership test, and a string predicate are neither true — the row is
**excluded**, exactly as the scalar `notEq`/`notIn` null behavior above. The
negative forms are not exceptions: `notEq`, `notIn`, and `notLike` over a
not-present field yield `NULL`, not true, so absence never satisfies a negative
predicate. `isNull` is true **exactly** on the rows a comparison excludes for this
reason (all four not-present states); `isNotNull` is its complement. An
implementation **MUST NOT** distinguish JSON `null` from a missing key or a null
column at the predicate level — the states stay distinguishable in the stored data
but are indistinguishable to the algebra.

This collapse is a **predicate observation**, not a stored-data-validity verdict.
It decides whether a predicate matches and nothing else. In particular, it does
not make a missing or JSON-null required member valid, authorize a result
materializer to discard the contradiction, or turn a wrong-kind occurrence into
conforming stored data. A read may therefore both exclude a row from an ordinary
comparison for the reason above and report that the stored member violates its
declared shape when that row is otherwise materialized. The predicate answer stays
the same in either case.

The distinction also fixes the judging boundary. SQL extraction never judges a
document's declared shape: it follows the requested path and applies this collapse
at any depth. Classified decoding starts at an `m-document-codec` Logical Judging
Root: the Entity or one of its top-level Value Object occurrences. Materialization
classifies each occurrence on a requested branch and advances a Logical Judging
Cursor only through a conforming carrier, so a requested deeper member returns a
finding for malformed stored state without scanning siblings. A multi-segment
placement used only to lower a predicate creates no such cursor and performs no
judgement. Consequently path depth and physical placement never select a second
validity rule: every requested position within a logical root has the
`m-document-codec` verdict under either layout, while every predicate extraction
retains the collapse defined here.

### Quantifiers

Scalar collections, `many` value objects, and to-many relationships share one
quantifier vocabulary. Each quantifier names its collection by a required `path`,
reached through single members from the scope it is written in; the collection's
canonical kind decides what its `where` binds — a scalar element, a value-object
element, or a related Entity.

| Predicate | Encoding | Meaning |
|---|---|---|
| `any` | `{ "any": { "path", "where"? } }` | some element makes `where` true; bare, the collection is non-empty |
| `none` | `{ "none": { "path", "where"? } }` | no element makes `where` true; bare, the collection is empty |
| `all` | `{ "all": { "path", "where" } }` | every element makes `where` true; it has no bare form |

`where` is evaluated once per element, as **one complete predicate** binding that
one element: every operation inside it — both bounds of a range, a negated
comparison, a whole Boolean compound — reads the same element. Its truth decides
the quantifier:

```text
one element's where   any   none   all
true                  true  false  true
false                 false true   false
unknown               false true   false
empty collection      false true   true
```

`all` succeeds only when every evaluation is **true**: false and unknown both fail
it, so `all(p)` is not `none(not p)` wherever `p` can be unknown. Matching a
non-empty collection all of whose elements satisfy `p` is the explicit
conjunction of a bare `any` with `all(p)`.

Separate quantifiers bind separately, and their elements may differ: two `any`
nodes over the same collection, joined by `and`, are satisfied by two different
elements, while one `any` whose `where` is their conjunction requires one element
carrying both. That distinction is observable and load-bearing:

```yaml
# two quantifiers — MATCHES when different phones satisfy each:
and:
  operands:
    - any: { path: Customer.address.phones, where: { eq: { path: type, value: home } } }
    - any: { path: Customer.address.phones, where: { eq: { path: number, value: '555-9999' } } }

# one quantifier — matches only when ONE phone satisfies both:
any:
  path: Customer.address.phones
  where:
    and:
      operands:
        - eq: { path: type, value: home }
        - eq: { path: number, value: '555-9999' }
```

Quantifiers nest: a `where` may quantify a collection of the element it binds,
with a path relative to that element. Negation complements the complete predicate
exactly where it is authored and never moves across a quantifier:

```yaml
# some line has no urgent tag — not "the order has no urgent tag anywhere":
any:
  path: Order.lines
  where:
    none:
      path: tags
      where: { eq: { value: urgent } }
```

**Carriers.** A collection stored as SQL `NULL`, a missing key, an explicit JSON
`null`, a JSON scalar, or a JSON object holds **zero elements** to a quantifier, as
does a collection reached through an absent single value object or to-one
relationship. This is a predicate observation only: a malformed carrier remains
invalid stored data that publication refuses (`m-document-codec`). An actual array
keeps every position.

**Scalar elements keep their declared encoding kind.** Before a scalar element is
compared, its JSON kind is checked against the kind its declared type encodes as
(`m-wire`): a Boolean collection expects JSON booleans, the integer and float types
JSON numbers, and Decimal and the text-encoded types JSON strings. An element of
another kind, and a JSON `null` element, remain candidates but supply no value, so
every operation over them is **unknown** — an integer collection holding the JSON
string `"42"` does not satisfy `eq 42`, and that element fails `all`. A
correct-kind element is compared through the ordinary typed projection; the kind
check is not canonical stored-data validation, and a conversion the database
cannot perform fails the statement through the execution error route.

```text
integer collection   any(eq 42)   none(eq 42)   all(eq 42)
[42]                 true         false         true
["42"]               false        true          false
[42, "42"]           true         false         false
```

### Presence

| Predicate | Encoding | Meaning |
|---|---|---|
| `exists` | `{ "exists": { "path" } }` | the single value object or to-one related Entity at `path` is present |
| `notExists` | `{ "notExists": { "path" } }` | it is absent |

A presence test carries no predicate and is always true or false. Presence of a
value object is an object at its path — SQL `NULL`, a missing key, JSON `null`, and
a non-object are all absent. Presence of a related Entity is a visible candidate
target at the read's temporal coordinates (`m-navigate`). A collection has no
presence of its own: bare `any` / `none` test its occupancy.

### Single-valued traversal

A path continues through a to-one relationship exactly as through a single value
object: `Order.customer.active` reads the `active` field of the one customer the
order reaches. Traversal is by canonical Relationship Identity and keeps every
relationship rule — join, temporal visibility (`m-navigate`), direction, and the
target's family.

A dotted field keeps nullable-field truth: when no target is reached, the field
supplies no value and ordinary comparisons — negative ones included — are unknown,
never matches. A presence test, not a negated comparison, distinguishes an absent
target from a present one with a null field. A dotted operation never multiplies
the queried rows and is never an existential match: it evaluates the declared
target's candidates at the propagated temporal coordinates — before any subtype
selection or field condition could hide one — and **zero** candidates supply no
value, **one** supplies the demanded result, and **more than one** fail the
statement when it is evaluated, through the database execution route (`m-sql`,
`m-db-error` assigns the failure no neutral category). A collection reached
through an absent target is empty: bare `any` is false, `none` and `all` are true.
Loaded relationships and deep fetch, which take the first related target, are not
dotted traversal and are unchanged.

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

## Relationships

Relationships are traversed **by canonical Relationship Identity** — never as a
user-written join. A to-many relationship is a collection and is reached only
through a quantifier, whose `where` resolves **against the related Entity**: its
paths are relative to the bound Entity (`sku`, `product.category`). A to-one
relationship is a single member: dotted paths continue through it, `exists` /
`notExists` test its presence, and a path-targeted `narrow` tests its subtype.
`m-navigate` owns relationship behavior over the compiled `m-relationship` facet,
and `m-sql` lowers quantifiers to correlated sub-selects and to-one hops to scalar
subqueries, so a to-many traversal never multiplies the queried entity's rows.

## Subtype narrowing

`m-inheritance` owns the shared **Subtype Selection** value, its canonical
construction, and its model-aware resolution inside a polymorphic position. The
`narrow` node here is **Predicate-scoped**: it narrows the active position for
its own inner predicate and is therefore a filter. Whole-result narrowing is
`narrowTo` on the Object Query and has no spelling in this grammar, so the two
can never be confused for one another:

| Predicate | Encoding | Meaning |
|---|---|---|
| `narrow` | `{ "narrow": { "path"?, "to": [ … ], "operand" } }` | the Entity at the active position — or, with `path`, the to-one target `path` reaches — belongs to the Subtype Selection `to`, and `operand` holds there |

Without `path`, the containing structure supplies the position: at the top of a
query's `predicate` it is the query's own result position (its `target`, narrowed
by its `narrowTo` clause), a Boolean term uses that Boolean expression's active
position, a quantifier over a to-many relationship uses the Entity it binds, and a
`narrow` inside another `narrow`'s operand uses the enclosing selection's resolved
position. The position is never repeated in the node. `operand` is evaluated over
the selection's resolved position, so a concrete-subtype-declared attribute
becomes referenceable there. A subtype test alone carries the constant `true`
operand.

```yaml
# target: Animal (root); narrow to Pet (abstract subtype -> Dog, Cat):
narrow:
  to: [Pet]
  operand: { "true": {} }
```

**Target-local narrowing.** With `path`, the Subtype Selection resolves against
the to-one target that path reaches — through single members only — and `operand`
reads that target with relative paths:

```yaml
narrow:
  path: Order.customer
  to: [VipCustomer]
  operand:
    greaterThan: { path: creditLimit, value: 100 }
```

An absent target, and one outside the selection, make the node **false**; a
selected target keeps the operand's true, false, or **unknown** — narrowing does
not truth-normalize it. Ordinary negation complements the completed node, so
negating it includes absent and unselected targets but leaves an unknown operand
unknown:

```text
reached target                     narrow     not(narrow)
absent                             false      true
present, outside the selection     false      true
selected, operand true             true       false
selected, operand false            false      true
selected, operand unknown          unknown    unknown
```

The selection is a filter over one reached target, not a request for a narrowed
Include view or a narrowing of the returned roots, and it applies the cardinality
assertion of single-valued traversal to every declared candidate before the
selection is consulted. Inside a quantifier over a to-many relationship a `narrow`
needs no `path`: it tests the element, and it does not restrict which elements the
quantifier ranges over — `all` over a subtype test requires every element to pass
it.

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

## Semantic elaboration boundary

Public Wire predicate nodes are untrusted serialized syntax. Predicate
elaboration consumes that syntax plus the accepted model and returns one private
immutable `ResolvedPredicate`: a closed union of Boolean constants and
composition, scalar operations, subtype narrowing, quantifiers, and presence
tests. It is the sole execution representation of a predicate,
not a second public AST, and has no serialization contract. Construction is
restricted to this module so illegal subject/operator/literal combinations are
not representable downstream.

Each variant retains only its resolved facts, never its authored node. A scalar
operation retains its operator, the exact resolved member it reads — an
Attribute, or a Value Object leaf — the **position** it reads it at (the current
object, a related object reached through to-one relationships, or the bound
scalar element), and its complete managed operand shape: one value for
comparison, two ordered bounds for `between`, or one managed tuple for membership
rather than one wrapper per element. A string match retains its pattern text and
whether it folds case, and a null check its member alone. A related position
retains each resolved relationship direction, its target, both join endpoints,
and the temporal terms its candidates are visible under. Recursive variants retain
resolved children, and no variant carries storage placement or precomputed SQL
text. Reusing one authored node at
two semantic positions creates two resolved occurrences; repeating one resolved
occurrence across physical SQL branches reuses that occurrence.

A quantifier retains its kind, the collection it ranges over — a scalar
collection, a value-object occurrence, or a resolved relationship — the position
that collection is read at, and its `where` resolved in the scope of the element
it binds. A presence test retains its polarity, its single value-object occurrence
or resolved relationship, and its position. A narrowing retains its accepted
selection, the position it tests — the current object or a reached target — and
its operand resolved there, or no operand for subtype membership alone; the
constant `true` operand elaborates to that same absent operand. Elaboration never
manufactures an existential scope a node did not author.

Elaboration dispatches exhaustively over the closed authored union. For each
typed literal it resolves the subject and operator first, calls
`m-wire.decodeWire` exactly once, and stores the managed result. It never mutates
the authored node. A new authored variant therefore requires both an elaboration
arm and a lowering arm rather than falling through a default.

This module also owns private generated-term operations. A generated scalar term
receives an exact resolved Attribute and managed value, checks managed
membership, and adopts the value directly in a resolved comparison; a framework
sentinel such as the `m-core` infinity bound is adopted as a framework operand
instead. Generated membership adopts one already-owned managed tuple, or a
deferred key set bound after compilation. Neither operation encodes or decodes a
literal. Consumers compose and rewrite only already-resolved occurrences; none
resolves a member or admits an operand again.

`m-object-query` stores this elaborated product. `m-sql` and `m-deep-fetch`
compile it without resolving paths, inferring types, decoding literals, or
repeating validation. Programmatic fluent predicates instead use
`m-core.coerceNeutralInput` followed by managed membership and retain their
language-owned type mismatch behavior; they do not expose Wire failure names.

A language frontend may hand elaboration its own authored predicate rather than
a canonical node. An adapter for that input resolves each subject to its
canonical spelling and supplies managed operands, and elaboration applies the
same subject, operator, quantifier, and narrowing rules to it at the same stage,
so both inputs converge on one `ResolvedPredicate`. An operand the frontend
already prepared under a declared neutral type is adopted only where the resolved
member declares that identical type, Decimal precision and scale and float width
included; it is never normalized again for another type.

## Forward map of the rest of the algebra

For orientation, this schema revision leaves membership `in(subquery)` out of the
required predicate set. Temporal Selection is a clause of `m-object-query`, whose
observable behavior `m-temporal-read` specifies. Public truth-testing operations
— a node or method that turns an unknown into true or false — are not part of the
algebra; the complete-predicate truth test strict `all` requires is internal to
its lowering.
