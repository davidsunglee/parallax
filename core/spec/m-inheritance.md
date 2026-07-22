# m-inheritance — Inheritance Mapping

`m-inheritance` is the **class-hierarchy mapping** strategy a normalized Entity
may declare. Its formation contribution consumes `m-metamodel` through
`m-model-formation`; `m-descriptor` is only an authoring/serde adapter.

Inheritance is a **closed tree** of entities: one abstract **root**, zero or more
abstract intermediate nodes, and the concrete, instantiable leaves (or any
concrete node). The family behaves conceptually like a **discriminated union** —
every returned row has exactly one concrete variant — even when the physical
strategy uses no discriminator column. An entity that participates declares an
`inheritance` element naming its **role** and, for the root, the family
**strategy**.

## Roles

| Role | Meaning | Table / rows |
|---|---|---|
| `root` | the abstract hierarchy root; declares the family strategy and (for table-per-hierarchy) the shared table plus `tag` column | **rowless and non-instantiable** — a polymorphic position naming the whole family |
| `abstract-subtype` | an abstract interior node between the root and its concrete descendants | **tableless, rowless** — a polymorphic position naming its concrete descendants |
| `concrete-subtype` | an instantiable participant, the only one that owns rows | uses the root table under TPH; owns its table under TPCS |

The `root` and every `abstract-subtype` are **abstract**, rowless, and
addressable only as polymorphic Entity positions. A TPH root nevertheless owns
the family's one shared table mapping; owning a mapping does not make it
instantiable or row-owning. Only a `concrete-subtype` owns rows.

## Strategies

The **root alone** declares the family strategy; every descendant inherits it and
**MUST NOT** redeclare it. Core admits exactly two strategies and **rejects the
rest**:

| Strategy | Meaning | In core? |
|---|---|---|
| `table-per-hierarchy` | the whole family in **one** shared table; rows discriminated by the root's `tag` column carrying each concrete subtype's `tagValue` | **yes** |
| `table-per-concrete-subtype` | one table **per concrete subtype**; no shared table, no tag | **yes** |
| `table-per-leaf` | the pre-ADR name for per-concrete-subtype mapping | **REJECTED** — strictly replaced by `table-per-concrete-subtype`; not a canonical alias |
| `table-per-class` | one table per class, joined at query time | **REJECTED** — the metamodel schema does not admit it |

`table-per-class` is intentionally excluded: per-query joins to assemble a single
object are exactly the hidden N+1 / fan-out cost the suite exists to prevent, and
the two admitted strategies cover the field's real use. `table-per-leaf` is the
retired name; the descriptor vocabulary uses `table-per-concrete-subtype`. A
descriptor declaring either **MUST** fail schema validation (negative
metamodel-extension tests assert this).

## Descriptor surface

| Property | Values / meaning |
|---|---|
| `role` | `root` \| `abstract-subtype` \| `concrete-subtype` (REQUIRED) |
| `strategy` | `table-per-hierarchy` \| `table-per-concrete-subtype`; declared by the `root` ONLY (REQUIRED there, FORBIDDEN on any descendant) |
| `parent` | the entity this node directly extends (REQUIRED for a non-root, FORBIDDEN for a root) |
| `tag` | `{ column }`, the shared-table discriminator column — declared on the `table-per-hierarchy` ROOT only (FORBIDDEN elsewhere and under table-per-concrete-subtype) |
| `tagValue` | the value the tag column carries for THIS concrete subtype's rows — a `concrete-subtype` under `table-per-hierarchy` only |

The pre-ADR `discriminator` / `discriminatorValue` vocabulary is **strictly
replaced** by `tag` / `tagValue`; the inheritance block is closed, so the retired
keys fail validation.

### Canonical descriptor blocks

Table-per-hierarchy root (abstract and rowless, but mapping owner):

```yaml
table: animal
inheritance:
  role: root
  strategy: table-per-hierarchy
  tag:
    column: kind
```

Abstract subtype (tableless):

```yaml
inheritance:
  role: abstract-subtype
  parent: Animal
```

Table-per-hierarchy concrete subtype:

```yaml
inheritance:
  role: concrete-subtype
  parent: Pet
  tagValue: dog
```

Table-per-concrete-subtype concrete subtype:

```yaml
table: dog
inheritance:
  role: concrete-subtype
  parent: Pet
```

## Inherited members

Attributes, Value Objects, relationships, and persistence declared on an abstract
ancestor are **inherited by every descendant**. A concrete subtype descriptor
**does not repeat** inherited attributes merely to satisfy
`table-per-concrete-subtype`; validation and lowering **derive the full inherited
attribute/column chain from the ancestry** (root → … → self). A concrete subtype
whose members are entirely inherited declares no `attributes` of its own (the
conditional requirement in `m-descriptor`).

**Temporal axes are different: they are family-level metadata, not an ordinary
inherited member.** Temporality is a property of the **whole inheritance
family**, not of any one entity in it. Only the family **root** may declare
`asOfAxes`; every abstract and concrete descendant **inherits the root's
complete axis set unchanged**. A descendant **MUST NOT** redeclare, add, remove,
override, or shadow a temporal axis — not even to repeat the root's own
declaration verbatim. A family is therefore either **entirely non-temporal**
(the root declares no axes, and no descendant may declare any) or **entirely
temporal** (the root declares one or two axes, and every descendant is temporal
along exactly those axes). Mixed temporality within one family — some concrete
subtypes temporal, others not, or descendants disagreeing on which axes apply —
is **not supported**: it would leave the family's root-owned as-of coordinate
system, root-result identity, and relationship-propagation target ill-defined
(see *Family invariants* below and the family-wide rejection rule there). Every
concrete table in a temporal family derives its temporal physical primary key
from the root's axes (`m-descriptor` "physical primary key"); reads through the
root, an intermediate abstract position, or a concrete subtype all resolve and
inject the same root-owned axes (`m-temporal-read`, `m-navigate`).

This is a deliberate simplification relative to Reladomo, whose generator can
merge inherited axes declared at multiple levels of a class hierarchy: Parallax's
first-class abstract-root reads, family-normalized identity, whole-graph pins, and
relationship propagation all need one uniform per-family coordinate system, so the
root is made the family's single temporal-schema owner.

**Optimistic-locking version attributes are root-owned in exactly the same way.**
The version attribute (`optimisticLocking: true`, `m-descriptor` "attribute") is
likewise family-level metadata, not an ordinary inherited member. Only the family
**root** may declare it; every abstract and concrete descendant **inherits the
root's version column unchanged**, and a descendant **MUST NOT** redeclare it, add
a second version attribute of its own, or leave the family's version column
undeclared while carrying one of its own — inheritance is never selective here
(see *Family invariants*, below, for the rejection rule). A family is therefore
either **entirely non-versioned** (the root declares no `optimisticLocking`
attribute, and no descendant may declare one) or **entirely versioned together**
(the root declares exactly one, and every descendant advances — and, in optimistic
mode, gates on — that same inherited column, `m-opt-lock`). Physically this needs
no new machinery: table-per-hierarchy already lands the root's version column in
the one shared table every concrete subtype's rows occupy, and table-per-concrete-
subtype's ancestry-derived column chain (*Physical mapping*, below) already
replicates the root's version column onto every concrete subtype's own table — the
same mechanism that already threads the primary key and every ordinary inherited
attribute. Combining an explicit `optimisticLocking` Attribute with
`asOfAxes` on one Entity remains invalid (`m-descriptor`); a temporal family's
root therefore derives its optimistic key from the Transaction-Time start
Attribute (`m-opt-lock`) rather than declaring a version Attribute, so a temporal family
is never also an explicitly-versioned one. Unlike the temporal-axis narrowing
above, this is not a simplification relative to a Reladomo feature Parallax
declines to support as broadly: Reladomo has no considered design for optimistic
locking composed with inheritance at all (ADR 0027).

## Physical mapping

**Table-per-hierarchy.** The whole family maps to **one shared table** declared
by the root; descendants never repeat it. The root's `tag` column distinguishes
rows. The shared
table physically carries the union of every concrete subtype's columns, so a
subtype-declared column is **nullable** in the shared table (a `card` row leaves
the `cash` column null and vice-versa). The `tag` column is **framework-owned
metadata, not a declared attribute**: a concrete-subtype read injects
`t0.<tag> = ?` (its `tagValue`); an abstract-target read projects the tag column
raw so `familyVariant` can be materialized (`m-sql` / `m-case-format`). `m-sql`
fixes the tag-filter golden SQL.

**Table-per-concrete-subtype.** Each concrete subtype maps to its **own table**;
no shared table and no tag exist. A concrete read is an ordinary single-table read
of that subtype's table — the subtype is selected by *which table* is queried.
Each concrete table **physically contains columns for the full inherited attribute
chain** plus the concrete subtype's own attributes, derived from the ancestry.

## Abstract-position reads

A read targeting an abstract position (the root or an abstract subtype,
optionally `narrow`ed) is a **discriminated-union read**: it returns every
concrete variant the position resolves to, each tagged by `familyVariant` (the
concrete subtype name, materialized from the tag metadata — never an authored
column, `m-sql` / `m-case-format`). What each returned leaf carries **beyond**
that tag depends on the read's result form (`m-case-format` *Read result
form*): a **row-form** (values lane) leaf is the flat SQL superset row (every
branch's columns, non-applicable ones `null`); an **instance-form** (object
lane) leaf, at a read case's own top-level leaves, is a **complete concrete
instance** in the ordinary sense — only its own branch's inherited-plus-own
members, never a sibling's null-padded column. Both forms read the **identical**
superset SQL row (`m-sql` *Read projection* fixes the projected column list as a
function of the target position alone, independent of result form); only the
instance-form materialization step narrows it to the variant's own declared
shape — the SQL itself never changes. This is the read-side counterpart of
*Concrete-subtype writes*, below: a discriminated union at both boundaries, with
the object lane's shape divergence confined to materialization, never SQL.

## Concrete-subtype writes

A create / update / delete of an inheritance participant is a **concrete-subtype
write**: it targets exactly one concrete subtype, and the family behaves as a
discriminated union at the write boundary just as it does at the read boundary. The
write protocol is the write-side counterpart of `targetEntity` / `narrow` read
targeting; a model-aware validator **MUST** enforce it **before any SQL**, and the
compatibility corpus pins each violation as a portable `rejected` / `when.write`
case with a `then.rejectedRule` (`m-case-format`). `m-sql` fixes the resulting DML.

- **Accepted fields are exactly the target's ancestry chain.** The fields a
  concrete-subtype write payload may carry are precisely the attributes / value
  objects on the target's ancestry (root → abstract ancestors → the concrete
  subtype itself) — the same inherited chain reads and DDL derive. A field declared
  on a **sibling** concrete branch, or on any **unrelated** branch of the family, is
  invalid: no single concrete subtype in the target's effective set accepts it
  (`subtype-write-sibling-attribute`).
- **Metadata is framework-owned, never authored.** A payload **MUST NOT** carry the
  `tag` column, `tag`, `tagValue`, or `familyVariant`. Under table-per-hierarchy the
  write **derives** the tag column from the concrete subtype's `tagValue` (exactly as
  a version bump or a milestone bound is derived, `m-sql`); `familyVariant` is a
  read-time materialization, not an input (resolved Q6). Authoring any of these is
  `subtype-write-metadata-field`.
- **Writes are concrete-subtype only.** A create / update / delete / terminate
  handle **MUST** name a concrete subtype. An abstract **root** or **abstract
  subtype** is a polymorphic read position, not a write handle; aiming a write at one
  is `abstract-write-target` — even when the payload is otherwise a well-formed
  concrete-subtype write.
- **Per-object writes are keyed; set-based inheritance writes are out of scope.** A
  concrete-subtype existing-row write is **keyed** by the primary key (the tag guard
  rides with the identity predicates, `m-sql` / resolved Q9), so a payload carrying
  **no primary-key** field denotes a predicate-driven **set-based** write over a
  result collection — unsupported for inheritance-family writes
  (`subtype-write-set-based-unsupported`). Changing an existing row's concrete
  subtype is likewise out of scope.

A validator checks these **payload-shape** rules (keyless → metadata → sibling)
before the **target-validity** rule (abstract handle), so a payload that trips more
than one defect pins the more specific shape defect; the harness fixes the same
order.

Physically: a **table-per-hierarchy** insert writes the shared table, setting the
tag column from the subtype's `tagValue`, and every existing-row statement (update /
delete / temporal close) carries a **tag guard** (`and <tag.column> = ?`) among the
identity predicates so it touches only that subtype's rows. A
**table-per-concrete-subtype** write targets the concrete subtype's **own table**
(no shared table, no tag); the subtype is selected by *which* table the DML names.
`m-sql` fixes the canonical DML, bind order, and the opt-lock composition.

## Canonical concrete-subtype ordering

Whenever a family's concrete subtypes are **enumerated** in a canonical artifact,
they appear in one fixed **total order**: **ascending by concrete-subtype entity
name, compared codepoint-by-codepoint (Unicode scalar value)** — i.e. plain
**alphabetical order by entity name**. This order is a pure function of the entity
names and is **independent of the descriptor's declaration order and file layout**:
reordering the subtype entries in a model file, or splitting them across files,
never changes it. The **effective concrete-subtype set** of any polymorphic
position (root, abstract subtype, concrete subtype, or a resolved `narrow`) is
presented in this order.

This canonical sibling-set order is the one every downstream module uses to
enumerate a family's concretes:

- the table-per-hierarchy tag predicate `in (…)` list and its binds (`m-sql`);
- the table-per-concrete-subtype `union all` **branch order** (`m-sql`);
- the grouped-`OR` per-branch `EXISTS` **branch order** for polymorphic navigation
  (`m-navigate`, `m-sql`);
- the derived **narrowed view key** `<rel>[<Concrete>,<Concrete>]` (`m-deep-fetch`);
- the **per-subtype own-column blocks** of an abstract-read superset projection
  (`m-sql`, below).

Three orderings are deliberately **not** this alphabetical sibling order and are
specified elsewhere:

- The **inherited-column prefix** of a superset stays **ancestry order**
  (root → abstract-subtype → concrete): columns are enumerated down the inheritance
  chain, never alphabetized across it.
- A **single entity's own attributes/columns** keep their **declared order**.
- A `narrow` node's authored **`to` list** is preserved **verbatim** by serde
  (`m-op-algebra`); only the *resolved/effective* concrete set it denotes is
  canonicalized to this alphabetical order, so `to: [Pet]` and `to: [Cat, Dog]`
  round-trip as distinct spellings yet resolve to the same ordered set.

## Family invariants

The following cross-Entity invariants are the complete `m-inheritance` Model
Formation Rule Set. They are semantic (not expressible per Entity in the
schema) and are reported before any SQL. The authoritative formation manifest
owns the complete code-set declaration; this module owns each code's meaning.

- **Parent resolution** is foundational `m-metamodel` reference resolution;
  an unknown parent is `metamodel-unresolved-entity-reference`, not a duplicate
  inheritance-owned code.
- **Acyclicity** — parent links form no cycle (`inheritance-cycle`).
- **Single root** — a family has **exactly one** root. A descriptor with
  inheritance participants but **no** root (a zero-root / abstract-orphan family) is
  rejected with `inheritance-missing-root`; one that reaches **more than one** root
  is rejected with `inheritance-multiple-roots`. (A concrete participant that never
  tops out at a root is the distinct concrete-without-abstract-root case below.)
- **Concrete under an abstract root** — every concrete subtype has an abstract
  root ancestor (`inheritance-concrete-without-abstract-root`).
- **TPH table ownership** — the root declares exactly one table
  (`inheritance-tph-root-table-required`) and every descendant omits it
  (`inheritance-tph-descendant-table-forbidden`). The root remains abstract,
  rowless, and non-instantiable despite owning the shared mapping.
- **TPCS table ownership** — the root and abstract subtypes omit tables
  (`inheritance-tpcs-abstract-table-forbidden`) and every concrete subtype
  declares one (`inheritance-tpcs-concrete-table-required`). Fixture rows under
  abstract nodes remain a case-format/fixture error rather than a Metamodel
  Issue because fixtures are not Candidate Metamodel input.
- **One family primary key** — the applicable ancestry chain contains exactly
  one primary-key Attribute (`inheritance-primary-key-missing` /
  `inheritance-primary-key-multiple`). Declaration identity stays with the
  ancestor that introduced it.
- **Root-only strategy** — a non-root does not redeclare the strategy
  (`inheritance-strategy-redeclared`).
- **Tag presence** — under table-per-hierarchy, **every** concrete subtype
  declares a `tagValue` (`inheritance-missing-tag-value`); the shared table cannot
  discriminate a subtype's rows without one. The per-entity schema leaves
  `tagValue` optional and delegates this presence rule (a family-strategy fact) to
  semantic validation.
- **Family-wide tag uniqueness** — under table-per-hierarchy, `tagValue` values
  are unique across the **whole family**, not just siblings
  (`inheritance-duplicate-tag-value`).
- **Tag placement** — a table-per-concrete-subtype family declares no `tag` /
  `tagValue` anywhere (`inheritance-tag-on-concrete-subtype-strategy`).
- **Temporal axes are root-owned** — an `abstract-subtype` or `concrete-subtype`
  declares no `asOfAxes` of its own, regardless of whether the root itself
  is temporal (`inheritance-temporal-axes-not-root-owned`). This holds for BOTH
  malformed shapes: a non-temporal root with a descendant that declares axes, and
  a temporal root whose descendant redeclares, adds, removes, overrides, or
  shadows an axis. Only the root may ever carry `asOfAxes` (*Inherited
  members*, above).
- **Optimistic locking is root-owned** — an `abstract-subtype` or
  `concrete-subtype` declares no `optimisticLocking` attribute of its own,
  regardless of whether the root itself declares one
  (`inheritance-optimistic-locking-not-root-owned`). This holds for BOTH
  malformed shapes: a non-versioned root with a descendant that declares a
  version attribute, and a versioned root whose descendant redeclares or adds a
  second version attribute. Only the root may ever carry an `optimisticLocking`
  attribute (*Inherited members*, above).
- **Persistence is root-owned** — a descendant declares no `persistence`, even
  when repeating the root value (`inheritance-persistence-not-root-owned`).
  Absence means inherit.
- **Members do not shadow across ancestry** — a descendant cannot redeclare an
  ancestor Attribute, Relationship, or top-level Value Object name, including
  cross-category shadowing (`inheritance-member-shadowing`). Disjoint sibling
  branches may reuse a name.

## The Inheritance Facet

After validation, the `m-inheritance` Model Compiler produces the immutable
`InheritanceFacet` under `FacetKey(m-inheritance)`. Generic
`Metamodel.facet(...)` retrieval stays hidden behind this module's typed
`view(model) -> InheritanceFacet` function (`m-model-formation` "Facet
ownership"). The facet owns ancestry, family identity, effective member
applicability, strategy, table selection, and the effective root-owned
Persistence Mode; the Temporal and Optimistic Lock facets derive their own
root-owned facts through this facet rather than this facet repeating them.
Every Metadata value the facet returns is the accepted declaration value
itself — declaring identities and provenance preserved, so an inherited member
still names the ancestor that introduced it — never a copy, and the facet
neither mutates nor extends the local declaration view.

```text
InheritanceFacet
  entity(EntityIdentity) -> InheritanceEntityView | absent
  position(members: nonempty sequence<EntityIdentity>)
    -> InheritancePositionView | absent

InheritanceEntityView
  entity: EntityIdentity
  root: EntityIdentity
  strategy: InheritanceStrategy | absent
  ancestry: nonempty immutable sequence<EntityIdentity>
  concrete_subtypes: immutable sequence<EntityIdentity>
  container: StorageContainer | absent
  tag_column: string | absent
  tag_value: string | absent
  persistence: PersistenceMode
  applicable_attributes: immutable sequence<AttributeMetadata>
  applicable_relationships: immutable sequence<RelationshipDeclaration>
  applicable_value_objects: immutable sequence<ValueObjectMetadata>
  superset_attributes: immutable sequence<AttributeMetadata>
  superset_value_objects: immutable sequence<ValueObjectMetadata>
  applicable_attribute(local_name) -> AttributeMetadata | absent
  applicable_relationship(local_name) -> RelationshipDeclaration | absent
  applicable_value_object(local_name) -> ValueObjectMetadata | absent

InheritancePositionView
  concrete_subtypes: immutable sequence<EntityIdentity>
  superset_attributes: immutable sequence<AttributeMetadata>
  superset_value_objects: immutable sequence<ValueObjectMetadata>
```

`entity(...)` is total, nonthrowing, and expected amortized O(1); it returns
absent only for an identity outside the accepted Metamodel. It covers
**every** accepted Entity, not only inheritance participants: a standalone
Entity has the trivial view whose `root` is itself, whose `ancestry` and
`concrete_subtypes` are `[entity]`, and whose `strategy`, `tag_column`, and
`tag_value` are absent. Every view member and named lookup is an expected
amortized O(1) read of formation output — the compiler precomputes these
answers once, so behavioral modules never repeat ancestry walks at query or
write time.

- `root` names the family's root (the family identity); `ancestry` is the
  parent chain `root -> … -> entity` in that order.
- `concrete_subtypes` is the position's **effective concrete-subtype set** in
  the canonical alphabetical order above: every concrete node at or below the
  position.
- `strategy` is the root-declared family strategy, present on every
  participant's view.
- `container` is the one physical Storage Container a read or write of the
  position targets: the root's shared table on every table-per-hierarchy view,
  the concrete subtype's own table under table-per-concrete-subtype, and the
  declared table of a standalone Entity. It is absent exactly for a
  table-per-concrete-subtype root or abstract subtype, whose reads lower to
  per-concrete branches (`m-sql`).
- `tag_column` is the root strategy's tag column, present on every
  table-per-hierarchy view; `tag_value` is additionally present on a
  table-per-hierarchy concrete subtype's view. Both are absent under
  table-per-concrete-subtype and for a standalone Entity.
- `persistence` is the effective root-owned Persistence Mode and is never
  absent; a standalone Entity's view carries its own normalized value.
- The `applicable_*` sequences are the position's effective navigable members:
  the ancestry chain's declared members in ancestry order, each ancestor's in
  declaration order. The `applicable_*` lookups resolve one local name across
  the whole chain; ancestry-wide name uniqueness
  (`inheritance-member-shadowing`) makes each lookup unambiguous. A concrete
  subtype's `applicable_attributes` is exactly the accepted-field chain of a
  concrete-subtype write and the inherited column chain the physical mapping
  derives.
- `superset_attributes` and `superset_value_objects` are the abstract-read
  projection supersets (`m-sql`) and equal the corresponding
  `position([entity])` members exactly (the ordering rule below).

`position(...)` is the projection contract for an **arbitrary resolved
position**: the resolved members of a `narrow`'s authored `to` list — each a
root, abstract subtype, or concrete subtype — or one member for an ordinary
position; a standalone Entity is its own trivial one-member position. It is
total and nonthrowing, returning absent exactly when a member identity is
outside the accepted Metamodel or the members do not all belong to one
inheritance family (a standalone Entity forms a position only alone).
Duplicate and overlapping members are valid input — the position denotes
their union — and the facet resolves without re-validating: a `narrow`'s
nonempty-subset validity rule stays with the operation algebra, so a position
whose effective set is empty returns empty sequences rather than absence.

- `concrete_subtypes` is the position's effective concrete-subtype set — the
  union of every member's effective set — in the canonical alphabetical order
  above.
- `superset_attributes` and `superset_value_objects` are the projection
  supersets over that effective set. Ancestors contribute first: every
  ancestor of an effective-set member that is not itself in the set
  contributes its declared members, with ancestors ordered by traversing the
  effective set in canonical order and appending each member's root-first
  ancestor chain, keeping first encounters. Then every effective-set member,
  in canonical order, contributes its own declared members. Each declaring
  Entity contributes exactly once, its members in declaration order, so every
  Attribute and Value Object appears exactly once with its declaring identity
  preserved. The framework-owned tag column is not a declared Attribute and
  is never in these sequences; `m-sql` projects it separately.

`position(...)` is expected output-sensitive: its cost is linear in the
member count plus the returned view's size — resolution over precomputed
per-Entity formation output, never a repeated whole-model walk — and every
returned sequence is immutable with O(1) access.

## Prior art (Reladomo)

Reladomo's `table-for-all-subclasses` and `table-per-subclass` correspond to the
two admitted strategies; its own "not recommended" `table-per-class` mirrors this
module's rejection. Parallax's declarative `tag` / `tagValue` metadata
deliberately diverges from Reladomo's code-level `createObject` discriminator
dispatch — the portable contract lives in descriptors and golden SQL, not
generated code.
