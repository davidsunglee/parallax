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

`parent` is an Entity Reference (`m-descriptor`): a bare name resolves relative
to the declaring Entity's own namespace, and canonical export spells the
resolved Entity Identity exactly. The blocks below show the inheritance property
alone, so their bare parents are canonical only for an ownerless family; a
namespaced family spells `parent: <namespace>.<LocalName>`.

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

**The Temporality Profile is different: it is family-level metadata, not an
ordinary inherited member.** Temporality is a property of the **whole inheritance
family**, not of any one entity in it. Only the family **root** may declare
`temporality`; every abstract and concrete descendant **inherits the profile and
the axes it derives unchanged**. A descendant **MUST NOT** redeclare, widen,
narrow, override, or shadow the profile — not even to repeat the root's own
declaration verbatim. A family is therefore either **entirely non-temporal**
(the root declares no profile, and no descendant may declare one) or **entirely
temporal** (the root's profile derives one or two axes, and every descendant is
temporal along exactly those axes). Mixed temporality within one family — some concrete
subtypes temporal, others not, or descendants disagreeing on which axes apply —
is **not supported**: it would leave the family's root-owned as-of coordinate
system, root-result identity, and relationship-propagation target ill-defined
(see *Family invariants* below and the family-wide rejection rule there). Every
physical Table in a temporal family uses the root's axes when Storage Layout
selects its temporal-end physical primary-key slots (`m-storage-layout`);
reads through the
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
subtype Storage Layout includes the root's version Attribute slot in every
concrete subtype's own table — the same composition that places the primary key
and every ordinary inherited Attribute. Combining an explicit
`optimisticLocking` Attribute with a temporal
`temporality` profile on one Entity remains invalid (`m-descriptor`); a temporal family's
root therefore derives its optimistic key from the Transaction-Time start
Attribute (`m-opt-lock`) rather than declaring a version Attribute, so a temporal family
is never also an explicitly-versioned one. Unlike the temporal-axis narrowing
above, this is not a simplification relative to a Reladomo feature Parallax
declines to support as broadly: Reladomo has no considered design for optimistic
locking composed with inheritance at all (ADR 0027).

**Storage Layout is root-owned in the same way.** The `layout` selection
(`m-storage-layout`) is family-level physical policy: only the family root may
declare it, and every abstract and concrete descendant inherits the root's
choice unchanged. A family is therefore either entirely conventional or entirely
document-mapped; a descendant never mixes the two, and never repeats the root's
declaration verbatim (see *Family invariants*, below, for the rejection rule).
This module owns only the ownership rule. Which members the chosen layout keeps
in direct Columns, and where the others live, is composed once by
`m-storage-layout` from this same family topology.

## Physical mapping

**Table-per-hierarchy.** The whole family maps to **one shared table** declared
by the root; descendants never repeat it. The root's `tag` column distinguishes
rows. The shared Table's complete contributor union, semantic order, and
effective physical nullability are composed by `m-storage-layout` from this
family topology. A contributor applicable only to one concrete branch is
physically nullable so sibling rows can omit it, while Entity-level validation
retains its declared nullability. The `tag` column is **framework-owned
metadata, not a declared attribute**: a concrete-subtype read injects
`t0.<tag> = ?` (its `tagValue`); an abstract-target read projects the tag column
raw so `familyVariant` can be materialized (`m-sql` / `m-case-format`). `m-sql`
fixes the tag-filter golden SQL.

**Table-per-concrete-subtype.** Each concrete subtype maps to its **own table**;
no shared table and no tag exist. A concrete read is an ordinary single-table read
of that subtype's table — the subtype is selected by *which table* is queried.
Each concrete table **physically contains columns for the full inherited attribute
chain** plus the concrete subtype's own attributes, composed as one canonical
layout by `m-storage-layout`.

### Validation-time table-group projection

Inheritance exposes a pure, total projection of Candidate Metamodel family facts
for the dependent `m-storage-layout` Rule Set. The projection accepts only the
Candidate Metamodel, emits no Issue, consumes no facet, and assumes no Rule Set
has run. It shares this module's topology walk without creating a
validation-time `InheritanceFacet`.

```text
InheritanceTableGroup
  table: Table
  mappingOwner: EntityIdentity
  mappingProvenance: EntityLocation
  rowOwners: immutable sequence<EntityIdentity>
  declarationContributors:
    immutable sequence<AttributeDeclaration
                       | TopLevelValueObjectDeclaration
                       | TablePerHierarchyTagDeclaration>

projectTableGroups(candidate: CandidateMetamodel)
  -> immutable sequence<InheritanceTableGroup>
```

The projection returns one mapping-owner group per standalone Entity, one per
unambiguous table-per-hierarchy family, and one per unambiguous table-per-
concrete-subtype concrete Entity, ordered by canonical mapping-owner Entity
Identity. A standalone Entity is its owner; a TPH root represents its whole
family owner, including all family participants; and a TPCS concrete Entity is
its own owner. `mappingProvenance` is that owner's `EntityLocation`, the precise
Model Location available for its Table declaration. TPH descendants are family
participants and never appear as competing owners.

The projection does not coalesce independent owners that name equal structural
`Table(name)` values. Storage Layout uses the ordered owner stream to reject
every later owner of an already-claimed Table at its mapping provenance, with
the first owner's provenance related. After that validation succeeds, each
Table has exactly one owner group and can produce exactly one coherent layout.

"Unambiguous" means that family membership, root, strategy, ancestry, and each
group's intended Table are uniquely derivable. The projection omits a group
when malformed topology makes one of those answers ambiguous; this Rule Set
retains exclusive ownership of the corresponding `inheritance-*` issue and the
dependent module never guesses. A distinct invalid property that does not
obscure the segment does not require the projection to suppress an otherwise
unambiguous contribution.

Each uniquely owned group's diagnostic declaration stream preserves accepted
provenance through four stable category passes: model primary-key Attributes,
the optional root-owned
TPH tag, remaining Attributes, then top-level Value Objects. Within an Attribute
or Value Object pass, a concrete-table group visits root-to-concrete ancestry,
and a shared-table group visits ancestry root first and concrete contributors in
canonical concrete Entity order. Every local category retains declaration order,
and a declaration reached through several concrete chains appears once. This
diagnostic encounter order does not define accepted physical order. The
projection supplies mapping-owner boundaries and declaration streams only.
`m-storage-layout` owns structural Table-owner uniqueness, physical-column
uniqueness within an owner, semantic tiers, final table order, effective
nullability, applicability sets, and physical primary keys.

Disjoint table-per-concrete-subtype branches that declare structurally distinct
Tables may therefore reuse a physical Column spelling because they remain
different owner groups. An abstract union preserves per-branch declaration
provenance even when two
branch-local columns share that spelling; it never infers one declaration from
the raw key. Sibling contributors in one shared table occupy one group and are
subject to Storage Layout's physical collision rule.

### Materialized field keys

Physical row keys and materialized graph keys are related but not identical. A
materialized Entity node has four provenance-bearing contributor categories:

1. scalar Attributes render under their physical column names;
2. top-level Value Objects render under their canonical occurrence names, even
   when their document storage columns differ;
3. loaded relationships render under their canonical local relationship names,
   or under a narrowed-view key; and
4. a polymorphic result renders the synthetic `familyVariant` key.

An implementation MUST preserve those categories until graph rendering. In
particular, a Value Object document column whose physical name equals a
relationship name is legal when the Value Object's canonical occurrence name is
different: attaching the relationship MUST neither overwrite the document nor
cause the relationship to be renamed as the Value Object. The physical document
key is an input-row key, not the occurrence's rendered graph key. The same
provenance rule permits a Value Object storage column named `familyVariant` when
the occurrence renders under a different canonical name: the decoded document
and the synthetic variant remain separate until rendering.

Every key that can coexist on one concrete node MUST nevertheless be distinct in
the rendered mapping. Formation rejects an Attribute physical column that equals
an applicable Value Object occurrence name or broad relationship name. It also
reserves every `<relationshipName>[` prefix from applicable Attribute physical
columns because narrowed views occupy that derived-key namespace. On an
inheritance participant, the synthetic `familyVariant` key is likewise reserved
from Attribute physical columns, Value Object occurrence names, and relationship
names. These ambiguities are
`inheritance-materialization-key-collision`; a materializer MUST NOT choose a
winner. Foundational canonical member-name collisions remain
`metamodel-local-member-collision`, and duplicate physical contributors remain
`storage-layout-column-collision` (`m-storage-layout`).

## Abstract-position reads

A read targeting an abstract position (the root or an abstract subtype,
optionally `narrow`ed) is a **discriminated-union read**: it returns every
concrete variant the position resolves to, each tagged by `familyVariant` (the
concrete subtype's **variant spelling**, materialized from the tag metadata —
never an authored column, `m-sql` / `m-case-format`). The variant spelling is the
bare local Entity name when that name is unique among the family's concrete
subtypes; when two concrete subtypes in one family share a local name across
namespaces, each such subtype uses its canonical qualified Entity spelling. Thus
existing families retain `Dog`, while duplicate local names render, for example,
`catalog.SharedVariant` and `archive.SharedVariant`. What each returned leaf carries **beyond**
that tag depends on the read's result form (`m-case-format` *Read result
form*): a **row-form** (values lane) leaf is the flat SQL superset row (every
branch's projected columns, non-applicable ones `null`); an **instance-form**
(object lane) leaf, at a read case's own top-level leaves, is a **complete
concrete instance** in the ordinary sense — only its own branch's inherited-
plus-own members, never a sibling's null-padded column. Inheritance resolves the
same effective concrete set and branch applicability for both forms. `m-sql`
owns result projection: both forms select the same applicable non-Document
Position Layout sequence, while instance-form additionally selects applicable
top-level Value Object Document slots and row-form omits them. The SQL is
therefore identical only when that Document-slot delta is empty. After the read,
instance-form materialization narrows the branch-backed values to the concrete
variant's own declared shape. This is the read-side counterpart of *Concrete-
subtype writes*, below: a discriminated union at both boundaries, with family
semantics retained here and result projection retained by SQL.

### The path root as a resolvable position

A deep-fetch path's **root** is a resolvable position of exactly the kind above:
the read's own queried position, which the path's optional root `narrow`
(`m-op-algebra`, `{ entity, to }`) may guard. Both members resolve through the
vocabulary this module already fixes — `entity` and each `to` entry resolve to
their effective concrete-subtype set, the union is presented in the canonical
alphabetical order, and acceptance is the four-step rule's non-empty-subset test
against the position clamped into that node. It reuses the existing rejections
rather than adding any: a `to` resolving to nothing is `narrow-empty-effective-set`,
and one escaping the clamped position is `narrow-outside-position`.

What the root position does **not** do is change the read. The guard selects
which already-resolved root objects a path traverses from, so the read's own
effective concrete set, its projection superset, and its `familyVariant` tagging
are exactly what they would be with no path authored at all. Relationship
identity is likewise unchanged: a relationship declared on an ancestor is
inherited by every concrete descendant under the **ancestor's** identity, so a
guarded path names that one relationship and adds only the source restriction —
never a per-subtype relationship. `m-deep-fetch` owns what the guard means for
hop identity and views.

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
  (`subtype-write-sibling-attribute`). The rule ranges over the names the family
  **declares somewhere**. A name declared nowhere in the family is on no branch, so
  it is outside this comparison — reading it as a sibling field would fail every
  candidate ancestry chain and report a branch conflict for a field that does not
  exist. What such a name is instead is a question for the surface that admitted
  it, not for this protocol.
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
they appear in one fixed **total order**: ascending by canonical Entity Identity
sort key `(namespace or "", name)`, compared codepoint-by-codepoint. For the
ordinary one-namespace family this is the existing alphabetical order by local
entity name. This order is a pure function of the Entity Identities and is
**independent of the descriptor's declaration order and file layout**:
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
- the per-subtype contributor visitation order used by Storage Layout's shared
  Table and cross-table position composition (`m-storage-layout`).

Three orderings are deliberately **not** this alphabetical sibling order and are
specified elsewhere:

- An inherited declaration stream stays **ancestry order**
  (root → abstract-subtype → concrete), never alphabetical across the chain.
  Storage Layout subsequently applies table-wide semantic tier precedence, so
  ancestry order is not a promised physical prefix.
- A **single entity's own members** keep their **declared order** within that
  stream and therefore remain stable within a Storage Layout tier.
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
- **Single root** — a family has **exactly one** root. A family is a position's own
  ancestry, not the whole model: a descriptor MAY declare **several independent
  families**, each with its own root and its own strategy, and each is judged alone.
  A family with **no** root (a zero-root / abstract-orphan family) is rejected with
  `inheritance-missing-root`. (A concrete participant that never tops out at a root
  is the distinct concrete-without-abstract-root case below.)
- **Concrete under an abstract root** — every concrete subtype has an abstract
  root ancestor (`inheritance-concrete-without-abstract-root`).
- **At least one concrete subtype** — a family contains at least one concrete
  subtype (`inheritance-missing-concrete-subtype`). Only concrete subtypes own
  rows, so a family of a root and abstract subtypes alone resolves **every** one
  of its positions to an **empty** effective concrete set: no read selects a row,
  no narrow has anything to narrow to, and no write names a target. The rule is
  asked of the family as **composed** — a model is free to compose a family's
  concrete leaves partially, but not to compose none of them.
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
- **Temporality is root-owned** — an `abstract-subtype` or `concrete-subtype`
  declares no `temporality` of its own, regardless of whether the root itself
  is temporal (`inheritance-temporality-not-root-owned`). This holds for BOTH
  malformed shapes: a non-temporal root with a descendant that declares a
  profile, and a temporal root whose descendant repeats, widens, or narrows one.
  Only the root may ever carry `temporality` (*Inherited members*, above).
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
- **Storage Layout is root-owned** — an `abstract-subtype` or `concrete-subtype`
  declares no `layout` of its own, regardless of whether the root itself
  declares one (`inheritance-layout-not-root-owned`). This holds for BOTH
  malformed shapes: a conventionally-mapped root with a descendant that declares
  a layout, and a root declaring one whose descendant redeclares, repeats, or
  overrides it. Only the root may ever carry `layout` (*Inherited members*,
  above); one table-per-hierarchy family therefore has one shared Structured
  Column and one table-per-concrete-subtype family applies the root's single
  policy and Structured Column name to every concrete table. The consequences of
  an accepted root-owned layout — placement, Column Overrides, Indices, and
  Structured Column collisions — belong to `m-storage-layout`.
- **Members do not shadow across ancestry** — a descendant cannot redeclare an
  ancestor Attribute, Relationship, or top-level Value Object name, including
  cross-category shadowing (`inheritance-member-shadowing`). Disjoint sibling
  branches may reuse a name. This module's validation-time projection exposes
  each independent mapping owner; `m-storage-layout` rejects a second owner of
  one structural Table, then checks every physical Column claim within the
  uniquely owned boundary.
- **Materialized field keys do not collide** — the scalar-column, canonical
  Value Object, relationship/narrowed-view, and synthetic `familyVariant`
  keyspaces described under *Materialized field keys* remain unambiguous on
  every concrete node (`inheritance-materialization-key-collision`). Value Object
  storage keys retain provenance and therefore do not collide merely because a
  relationship has the same local name.

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
  concrete-subtype write and the declaration chain Storage Layout composes for
  that Entity's Table.
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
  is never in these sequences; Storage Layout supplies its physical slot and
  `m-sql` retains the semantics for when that slot is projected or filtered.

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
