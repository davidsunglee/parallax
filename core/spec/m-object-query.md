# m-object-query — Object Query

`m-object-query` defines the **Object Query**: the non-recursive query value that
selects and returns **full objects**, optionally with related objects through
Includes. It is the language-neutral read request every supported entry point
receives, and the only value a read envelope carries.

An Object Query is **flat**. Every clause is a sibling property of one object, so
clause authoring order carries no meaning and no clause can nest inside another.
That is the whole structural point: an ordering or a row cap over an eager fetch
has **no spelling** here rather than a rejection rule, and the value fixes its own
semantics without a wrapper position or call sequence deciding them.

`m-object-query` depends on `m-predicate` (it carries one as a clause and never
extends the selection grammar), on `m-metamodel` (each clause names canonical
Identities), and on `m-inheritance` (the shared Subtype Selection resolves against
a family's effective concrete-subtype set). The three modules that **realize** a
clause — `m-temporal-read` for Temporal Selection, `m-deep-fetch` for Includes,
`m-sql` for ordering and the cap — depend on this module and never the reverse: a
clause's *value* belongs to the query, and the *behavior* realizing it belongs to
its own module.

The canonical schema is
[`core/schemas/object-query.schema.json`](../schemas/object-query.schema.json).

## Canonical encoding

An Object Query is one object with a **format-agnostic canonical
serialization**, in at least JSON and YAML, exactly as `m-predicate` and
`m-descriptor` are. Every implementation MUST provide serde behavior with
round-trip tests: `serialize(deserialize(query)) == query`.

```yaml
objectQuery:
  target: parallax.compatibility.Order
  predicate: { all: {} }
  narrowTo: [parallax.compatibility.PriorityOrder]
  temporal:
    transaction-time: { asOf: latest }
  orderBy:
    - { attr: parallax.compatibility.Order.name, direction: desc }
  limit: 2
  includes:
    - { segments: [{ rel: parallax.compatibility.Order.items }] }
```

`target` and `predicate` are **required**; every other clause is optional and
occurs at most once, which is a property of a JSON object rather than a rule a
validator restates.

An Object Query carries **no result form**: it always requests full objects.
There is no `distinct`, and no `offset` or pagination. Selected-field results and
aggregate values belong to future Projection / Aggregate Query work, and internal
SQL row projections stay implementation details of object hydration.

## `target` — the queried position

`target` names the Entity a read starts from. It names the whole family for an
abstract root, its concrete descendants for an abstract subtype, and itself for a
concrete subtype (`m-inheritance`). It spells the Entity bare or canonically under
`m-predicate`'s *Entity spellings in a reference position* rule, and everything an
implementation serializes carries the resolved canonical spelling.

Living **inside** the query is what lets a read envelope carry one document: no
case, step, or adapter pointer pairs a query with a sibling entity field, and a
query is therefore self-locating rather than position-relative.

Every queried-entity reference the query carries — its predicate's `attr` / `rel`
/ nested `path`, each Sort Key's `attr`, each Include Path's first hop `rel` — MUST
be **consistent** with `target`: the reference class's effective concrete set is a
subset of the target's. A navigation's inner predicate and an element-scoped
`where` resolve against a different position and are exempt.

## `predicate` — the selection

`predicate` is a `m-predicate` node and is required. An unfiltered query states
`{ "all": {} }` explicitly rather than omitting the clause: an unfiltered read is
a deliberate claim, not an absence.

The position the predicate is evaluated at is the query's **result** position —
`target`, narrowed by `narrowTo` when present — so a concrete subtype's attribute
becomes referenceable exactly where the result narrowing establishes its scope.

## `narrowTo` — result narrowing

`narrowTo` is the shared **Subtype Selection** (`m-inheritance`) constraining the
query's RESULT position. It decides which objects come back and nothing else: it
creates no relationship view, never restates `target`, and is not a recursive
node. Its selection resolves inside `target`'s effective concrete set — outside
it is `narrow-outside-position`, and a selection resolving to nothing is
`narrow-empty-effective-set`.

Redundant narrowing is valid: narrowing a position to itself still lowers to the
tag/branch selection for those concretes.

Two other narrowing positions exist and are deliberately separate: **Predicate-scoped**
narrowing (`m-predicate`'s `narrow`, a filter) and an Include Path's own two
positions below.

## `temporal` — Temporal Selection per dimension

`temporal` maps each declared **Temporal Dimension** to that dimension's own
selection. At most one selection per dimension is settled by the map's shape.
`m-temporal-read` defines the interval model, milestone behavior, and injection;
`m-sql` fixes the SQL fragments and bind order.

| Selection | Encoding | Meaning |
|---|---|---|
| `asOf` | `{ "asOf": "latest" \| "<instant>" }` | pin the dimension to Latest or a finite instant |
| `asOfRange` | `{ "asOfRange": { "start", "end" } }` | return milestones whose interval overlaps the half-open range `[start, end)` |
| `history` | `{ "history": {} }` | return the full milestone set on that dimension; no as-of predicate is injected for it |

The keys are `valid-time` and `transaction-time`, resolved against the target
Entity's effective As-Of Axes. An `asOf` coordinate is either the literal `latest`
or an ISO-8601 UTC instant; Latest lowers to the dimension's physical end column
equal to the `m-core` / `m-dialect` `infinity` sentinel, while a finite instant —
including one obtained from the current clock — lowers to interval containment.
There is no `now` variant or serde alias for Latest. `start` and `end` are finite
ISO-8601 UTC instants with `start < end`; neither Latest nor infinity is a range
endpoint, and `history` is how the unbounded scan is spelled.

**The canonical document is explicit.** It names a selection for every dimension
the queried Entity declares, and none for a dimension it does not
(`temporal-read-dimension-selection-cardinality`). Defaulting happens only on the
authoring surface, and only for one dimension:

```text
omitted transaction-time  ->  { "asOf": "latest" }
omitted valid-time        ->  rejected; never normalized silently
```

The asymmetry is semantic. Transaction-Time Latest means *current database
knowledge*, which is the only thing a caller who said nothing can have meant.
Valid-Time Latest means *the milestone whose valid-through boundary is infinity* —
a substantive claim about the business timeline that a caller has to make
deliberately.

Map key order carries no meaning: injection order is the declared axis rank, Valid
Time first, so user binds precede temporal binds in the same order whatever a
document's key order was.

Both dimensions compose independently — any selection on either, including a scan
on both.

## `orderBy` — Sort Keys

`orderBy`, when present, is a **non-empty ordered list** whose list order is key
**precedence**. Each Sort Key carries an attribute reference, a `direction`
(`asc` default / `desc`), and a Null Placement `nulls` (`first` / `last`, default
`last`).

A Sort Key's Null Placement is where `NULL`s sort on that key, independent of
`direction`. Omitting it means `last` — the canonical, dialect-independent default
in both directions — and an authored value survives canonical round-trip
distinctly from omission. Placement is a property of the key, not of the dialect:
the two dialects' native placement diverges, so `m-dialect` carries the per-dialect
lowering that makes the observable order identical everywhere. It is observable
only on a **nullable** attribute; on a non-nullable one both placements denote the
same order and lower to the same term.

**Sorting is exactly as authored.** No primary-key or temporal-edge tiebreaker is
injected, and equal authored keys leave their rows in unspecified relative order.

A Sort Key addresses the RESULT position, so ordering an abstract position by a
concrete subtype's attribute is rejected while ordering that same position
narrowed to that subtype is not.

## `limit` — the row cap

`limit` is an optional positive integer capping the number of **root objects**
returned, applied after predicate filtering, result narrowing, Temporal Selection,
and ordering. Includes execute only for the selected roots, and included children
never count toward it.

An unordered limit is legal and returns an unspecified matching subset: it is a
**cap, not pagination**. When a Temporal Selection scans milestones, each returned
milestone counts independently, including several sharing one business primary
key.

Neither `orderBy` nor `limit` changes the projected column list. The query carries
**no projection clause** at all: a read's `select` list is a pure function of its
target and result form, supplied by `m-sql` (its *Read projection* section), never
chosen by the query.

## `includes` — the requested graph shape

`includes` is the **Includes** clause: the graph shape a read asks for. **Deep
Fetch** (`m-deep-fetch`) is the execution behavior that realizes it — one SQL
statement per relationship level — and never a query tag of its own.

```yaml
includes:
  - segments: [{ rel: parallax.compatibility.Order.items }]
  - appliesTo: [zoo.Dog]
    segments: [{ rel: zoo.Animal.owner, narrowTo: [zoo.Staff] }]
```

### Include Path grammar

Each Include Path is a **closed object** whose required `segments` member is the
ordered, non-empty chain to fetch, read left to right from the queried position.
Every segment is itself a closed object carrying the relationship to traverse
under `rel` (a `Class.relationship` reference) and, for a **polymorphic** hop
(a relationship whose target is an abstract position, `m-inheritance`), an optional
`narrowTo` Subtype Selection. The object path is the single structural carrier for
a path, keeping what qualifies the path as a whole distinguishable from what
qualifies one hop.

An Include Path requests the **complete relationship view**. It carries no
predicate, no Sort Keys, no limit, no pagination, and no nested Object Query;
child ordering comes from Relationship Metadata (`m-deep-fetch`). Filtered,
sorted, or paginated relationship views are a separate future feature.

### The two selection positions narrow opposite things

A path MAY carry an `appliesTo` Subtype Selection beside `segments`. It **guards
which queried objects the path starts from** without changing the read's own
result set, so a caller whose `target` is polymorphic can eager-fetch a
relationship for one branch of the family alone:

```yaml
# target: Animal; `owner` is declared on Animal, so Dogs and Cats reach it
# under the one relationship identity `Animal.owner`:
includes:
  - { appliesTo: [Dog], segments: [{ rel: Animal.owner }] }
  - { appliesTo: [Cat], segments: [{ rel: Animal.owner }] }
```

- an `appliesTo` guard restricts a hop's SOURCE objects and creates **no** view
  key — every hop of a guarded path populates the view its unguarded spelling
  would, on fewer objects. Identity at the root keys on the **resolved source set**
  alone, so two guards resolving to the same concretes are one hop and a guard
  admitting every queried object *is* the broad path. It resolves inside the
  QUERIED position (`target`), never the narrowed result: result narrowing decides
  which objects come back, not which sources a path may start from.
- a segment's `narrowTo` restricts a hop's TARGET and creates a distinct narrowed
  view keyed `<rel>[<Concrete>,<Concrete>]`. Identity there keys on whether a
  selection was **authored** as well as on the set it resolves to, because the view
  key is derived from the authoring. It must resolve within the relationship
  target's effective set (`narrow-outside-relationship-target`).

The normative execution guarantee is **one SQL statement per relationship level**
(N+1 elimination): the root query plus one statement per distinct hop, where hop
identity is the triple **(relationship, whether a selection was authored, effective
concrete set)**. Paths sharing a hop fetch it **once**. `m-deep-fetch` specifies
this in full, and the round-trip-count layer of the compatibility harness
(`m-case-format`) proves it.

### Includes is an order-insensitive set

`includes` denotes a **set**, not a precedence list. Its canonical serialization
is the unique fixed point of these rules:

1. Canonicalize every `appliesTo` and `narrowTo` Subtype Selection in Entity
   Identity order while preserving the order of segments inside each path.
2. Sort paths lexicographically by each segment's structured Relationship Identity
   and optional target selection, using the optional `appliesTo` guard as the final
   tie-breaker. An absent selection sorts before an authored one.
3. Collapse structurally equal paths.
4. Retain only maximal paths: when one path is an exact segment prefix of an
   extension with the same source applicability and the same selection on every
   shared segment, remove the prefix. The extension still materializes every prefix
   level.

Broad and narrowed paths stay structurally distinct. In particular, an absent
segment selection does not equal an authored one, and different source guards do
not prefix one another. Canonicalization is idempotent and happens **before**
planning, so permuting paths, repeating one, or spelling an already-implied prefix
cannot change the canonical query or its planned levels.

This set rule is confined to `includes`. Boolean operand order, Sort Key
precedence, Subtype Selection authoring order at serialized ingress, and segment
order inside one path keep their own contracts.

### Includes with a scanned dimension

Includes is **legal** in the canonical query with point, `history`, and
`asOfRange` selections alike. Whether an implementation executes that combination
yet is a Feature classification owned by the lifecycle module that runs it
(`m-snapshot-read`'s `snapshot-history-includes`), never a shape this grammar
refuses.

## Clause invocation order is authoring syntax only

An authoring surface may fill clauses in any order. The Object Query value fixes
semantics directly, so no call sequence affects the result and every permutation
of the same clause calls produces the identical canonical query.

What an authoring surface owns instead is **repeated assignment**. A singleton
clause is refused on a second assignment rather than replaced:

- a second `limit`;
- a second `narrowTo`;
- a second selection for one Temporal Dimension;
- any equivalent singleton replacement.

Additive clauses remain additive: Sort Keys append in precedence order, Include
Paths accumulate into the canonical set, and separate temporal calls may fill
different dimensions.

## Planning boundary

A planner consumes the query's clauses **directly**. It never rebuilds a wrapper
tree, and no private value re-expresses the query as one.

Two internal values sit at that boundary, and neither is a wire encoding:

- an **Entity Query** is the normalized query for ONE root or related Entity —
  target, predicate with temporal terms already injected, resolved result
  narrowing, ordering, cap — and is what `m-sql` compiles. A deep-fetch child level
  derives one from gathered parent keys, so it exists without any authored query
  behind it.
- an **Object Query Plan** is the complete root-plus-levels plan `m-deep-fetch`
  produces.

Every supported read entry point validates and classifies the Object Query before
SQL generation, connection acquisition or port access, participating unit-of-work
force-flush, and any other observable side effect.
