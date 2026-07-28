# m-storage-layout - Canonical Physical Table Layout

`m-storage-layout` owns the composed physical shape of every Table in an
accepted Metamodel. It depends on `m-metamodel`, `m-model-formation`, and
`m-inheritance`. Declarations continue to own member identity and local storage,
and Inheritance continues to own family topology, strategy, ancestry, concrete
applicability, and discriminator semantics. Storage Layout combines those facts
once so physical consumers never reconstruct a competing table shape.

The module contributes both a Model Formation Rule Set and a Model Compiler.
The Rule Set validates physical Table ownership and Column claims over the
Candidate Metamodel. The compiler runs only after validation, consumes Compiled
Metadata plus `FacetKey(m-inheritance)`, and publishes the immutable
`StorageLayoutFacet`.

Storage Layout adds no descriptor authoring form. Temporal axes and optional
Audit Metadata designate Attributes already declared in the Metamodel; they do
not introduce storage declarations. Relationships, narrowed relationship views,
SQL aliases, and `familyVariant` are result or operation concerns and never
become physical slots.

## Physical table ownership and groups

`Table(name)` is a name-only structural identity, not an owner-qualified
declaration. Every accepted structural Table has exactly one independent
physical mapping owner:

- a standalone Entity is one owner of its declared Table;
- one table-per-hierarchy root/family is one owner of its root-declared shared
  Table, including all abstract and concrete family participants; and
- each table-per-concrete-subtype concrete Entity is one owner of its declared
  Table and ancestry-derived mapping.

Participants within one table-per-hierarchy family are contributors to their
single family owner, not competing mapping owners. By contrast, two standalone
Entities, two different TPH families, two TPCS concrete mappings, or any mixture
of those forms are independent owners even when they name equal Table values.

During validation, Storage Layout obtains one owner group per unambiguous
standalone mapping, TPH family, or TPCS concrete mapping from Inheritance's
pure, total projection. Each group exposes its structural Table, mapping owner,
row owners, and complete declaration stream. The mapping provenance is the
`EntityLocation` of the standalone Entity, TPH root, or TPCS concrete Entity
whose declaration supplies the Table. Descendant TPH participants have no
separate Table mapping provenance.

The projection preserves declaration provenance and emits no Issue. It returns
only groups whose family, strategy, ancestry, and intended Table are
unambiguous. The Inheritance Rule Set reports malformed topology or Table
ownership; Storage Layout neither duplicates those issues nor guesses a group.
Rule Sets therefore remain independent of invocation order and no validation-
time facet exists.

Storage Layout visits owner groups in canonical mapping-owner Entity Identity
order. The first owner of a structural Table establishes its mapping claim.
Every later independent owner of that Table is rejected as
`storage-layout-table-mapping-collision`; independent owners are never merged
into one physical key, contributor applicability set, or eventual layout. After
all Rule Sets succeed, each structural Table therefore has one owner group and
the compiler publishes exactly one coherent layout for it.

Within a uniquely owned group, the declaration stream is deterministic.
Ancestors are visited root first, each Entity's local Attributes and top-level
Value Objects retain their respective declaration orders, and the concrete
contributors of a shared Table are visited in canonical concrete Entity order.
A contributor already encountered through another applicable concrete is
retained once and accumulates that concrete's applicability.

## Layout values

The closed semantic tiers, in canonical order, are:

```text
ColumnTier =
    Identity
  | Discriminator
  | Domain
  | Temporal
  | Audit
  | Document
```

The closed contributor algebra is:

```text
InheritanceDiscriminator
  root: EntityIdentity

ColumnContributor =
    AttributeIdentity
  | ValueObjectIdentity
  | InheritanceDiscriminator
```

Only a top-level Value Object occurrence is a `ValueObjectIdentity`
contributor. Its nested occurrences and scalar fields live inside the one
document column and contribute no slot.

```text
ColumnSlot
  column: Column
  tier: ColumnTier
  contributor: ColumnContributor
  declaringOwner: EntityIdentity
  effectiveNullable: boolean
  applicableEntities: immutable set<EntityIdentity>

TableLayout
  table: Table
  columns: immutable sequence<ColumnSlot>
  physicalPrimaryKey: immutable sequence<ColumnSlot>
  column(Column) -> ColumnSlot | absent
  contribution(ColumnContributor) -> ColumnSlot | absent
```

`TableLayout.columns` is the complete physical Table sequence and is the sole
physical order exposed to consumers. `physicalPrimaryKey` selects the same
immutable slot values from `columns`; it does not copy slots or restate Columns.
The structural identity of a slot is `(Table, ColumnContributor)`. An inherited
Attribute in two table-per-concrete-subtype Tables therefore has one distinct
slot per Table even though both slots reference the same declaration identity.
Python object identity or any other implementation allocation identity is not
contractual.

`declaringOwner` is the Entity that declares an Attribute or top-level Value
Object. The discriminator's declaring owner is its family root. Every returned
identity and Column is the accepted Metamodel value, not a copied declaration or
rendered string.

`applicableEntities` contains the concrete row-owning Entities whose rows in
this Table carry the contributor. For a standalone owner it is that
standalone Entity. For a shared table it may be the complete concrete family or
a strict subset. For a table-per-concrete-subtype owner group it contains that
group's concrete owner. The discriminator applies to every row owner in its
shared Table.

All sequences and sets are immutable. The two lookups are total, nonthrowing,
and expected amortized O(1); they return absent for an unknown Column or
contributor. Physical-column uniqueness makes the Column lookup unambiguous.

## Tier classification and ordering

Every contributor is classified exactly once:

1. A model primary-key Attribute is `Identity`.
2. The table-per-hierarchy tag is `Discriminator`.
3. An Attribute designated as the start or end of a temporal axis is
   `Temporal`.
4. An Attribute designated by accepted Audit Metadata is `Audit`.
5. Every other Attribute is `Domain`.
6. A top-level Value Object is `Document`.

The precedence above resolves overlapping designations. In particular, an
Attribute that is both Transaction-Time start and the audit revision-instant
alias is one `Temporal` contributor and one slot; it does not also appear in the
Audit tier. A primary-key Attribute remains `Identity` if another designation
also names it. Absence of temporal axes or Audit Metadata leaves the
corresponding tier empty.

The compiler performs a stable partition of the deterministic declaration
stream by `ColumnTier` order. Declaration order remains stable inside each
tier, but tier precedence is table-wide and takes precedence over ancestry. A
descendant Domain Attribute may therefore precede a root-owned Temporal or
Audit Attribute. No per-ancestor or pre-capability column prefix is preserved.

## Effective physical nullability

Let `rowOwners(layout)` be the complete set of concrete Entities whose rows are
stored in the layout's Table. Effective physical nullability is determined in
this order:

```text
false                                      when the slot is in physicalPrimaryKey
false                                      when the tier is Discriminator
true                                       when applicableEntities != rowOwners(layout)
the contributor's declared nullability    otherwise
```

The third rule makes a required subtype-only member nullable in a shared
table-per-hierarchy Table, because rows of a sibling subtype have no value for
it. Entity-level write validation still requires that member for every Entity
to which it applies. A required root member applies to every shared-table row
owner and remains physically non-null. Standalone and table-per-concrete-
subtype contributors normally apply to every row owner and retain declared
nullability unless selected into the physical primary key.

The DDL surface must implement this answer. A dialect may omit a redundant
explicit `NOT NULL` on a primary-key column, but no consumer may substitute
authored nullability or an all-columns-nullable policy for
`effectiveNullable`.

## Physical primary key

The Physical Primary Key is the ordered selection of:

1. every model primary-key Attribute slot, in model-key order; then
2. each temporal dimension's start Attribute slot, in accepted axis order.

It may therefore span the Identity and Temporal tiers. A temporal-start
Attribute remains at its one canonical position in `columns`; selecting it into
`physicalPrimaryKey` does not create another slot. Inheritance owns the
root-wide temporal applicability of a family, so a shared table and every
concrete table use the same root axis designations.

Secondary Index Metadata remains an ordered declaration of Attribute
Identities. A DDL consumer resolves each index component through the applicable
layout's contributor lookup. An index does not create another layout-owned
column sequence.

## Entity and position views

The facet exposes table layouts plus selections that reference their existing
slots:

```text
DiscriminatorAssignment
  slot: ColumnSlot
  value: string

EntityLayoutView
  entity: EntityIdentity
  layout: TableLayout
  columns: immutable sequence<ColumnSlot>
  discriminator: DiscriminatorAssignment | absent

PositionColumn
  contributor: AttributeIdentity | ValueObjectIdentity
  tier: ColumnTier
  declaringOwner: EntityIdentity

PositionBranch
  layout: TableLayout
  concreteEntities: immutable sequence<EntityIdentity>
  slots: immutable sequence<ColumnSlot | absent>
  discriminatorSlot: ColumnSlot | absent

PositionLayoutView
  concreteEntities: immutable sequence<EntityIdentity>
  columns: immutable sequence<PositionColumn>
  branches: immutable sequence<PositionBranch>

StorageLayoutFacet
  tables: immutable sequence<TableLayout>
  table(Table) -> TableLayout | absent
  entity(EntityIdentity) -> EntityLayoutView | absent
  position(immutable sequence<EntityIdentity>) -> PositionLayoutView | absent
```

`tables` is deterministic and contains exactly one layout per physical Table.
`table(...)` is total and returns absent only for a Table outside the accepted
layout graph.

`entity(...)` returns a view for a standalone or concrete row-owning Entity and
returns absent for an unknown or rowless abstract Entity. Its `columns` are the
layout's slots applicable to that Entity, retained in complete table order; the
shared-table discriminator is included and its derived concrete tag value is
exposed by `discriminator`. The sequence references layout slots and creates no
second physical order.

`position(...)` accepts the canonical effective concrete-Entity sequence
already resolved by Inheritance. An unknown Entity, a noncanonical sequence, or
Entities from different families returns absent. An empty valid sequence
returns an empty view. `columns` is one logical, declaration-provenance-bearing
union for the position: root-first ancestry, local declaration order, and
canonical concrete order, then stable tier partitioning, with an inherited
contributor included once. It excludes physical discriminators because a TPCS
position has none and `familyVariant` remains a result concern.

Each branch names one physical Table represented in the position and aligns its
`slots` with the logical `columns`. An entry references that Table's slot when
the contributor applies to at least one selected concrete in the branch and is
absent otherwise. TPH has one shared-table branch; TPCS has one branch per
selected concrete Table in canonical concrete order. `discriminatorSlot` names
the TPH Table slot independently so SQL can retain its abstract/concrete tag
semantics. Typed `NULL` expressions, result aliases, and synthetic branch
variants are not layout values.

Facet and view indexes are immutable and bounded by the accepted model. A
compiler may intern repeated applicability sets and store slot selections as
ordinals, but public values preserve structural equality and immutable access.
Arbitrary position views are operation-scoped and must not create an unbounded
model-lifetime cache.

## Table-mapping and physical-column collision Rule Set

The Rule Set receives projected owner groups in canonical mapping-owner Entity
Identity order and performs Table ownership validation before Column
validation. For each structural Table, the first owner establishes the claim.
Every later independent owner emits:

```text
storage-layout-table-mapping-collision
```

The Issue location is the later owner's mapping provenance: the
`EntityLocation` of its standalone Entity, TPH root, or TPCS concrete Entity.
Its related sequence contains the first owner's mapping provenance. Every owner
after the first is compared with that same first owner, making diagnostics
deterministic. Participants within one TPH family never enter this owner claim
stream separately.

A Table with competing owners does not proceed to Column validation. This keeps
`storage-layout-table-mapping-collision` exclusive to independent physical
mapping ownership and prevents secondary Column diagnostics from obscuring the
unsound table boundary. It also guarantees that a compiled layout never combines
independent model primary keys whose Entity DML supplies only owner-applicable
slots.

For every uniquely owned Table, physical Column claims share one registry. Their
diagnostic encounter order is an explicit stable category pass over that
owner's declaration stream:

1. model primary-key Attributes;
2. TPH discriminators;
3. all remaining Attributes; and
4. top-level Value Objects.

Within each Attribute or Value Object category, ancestry is root first,
shared-table concrete contributors use canonical concrete Entity order, and
each local category retains declaration order. The category pass determines
diagnostics only; the compiler's six-tier stable partition remains the sole
accepted physical order. A contributor reached repeatedly through several
applicable concrete chains is one claim.

The first contributor claiming a Column establishes that physical claim. A
later distinct contributor claiming the same Column emits:

```text
storage-layout-column-collision
```

The Issue location is the second contributor's declaration, or the root tag
declaration for a discriminator. Its related location is the first contributor's
declaration. Repeated applicability of the same structural contributor is not a
collision. The boundary is the uniquely owned structural Table: TPCS mappings
with structurally distinct Tables may reuse a Column spelling, while sibling or
otherwise co-located contributors within one owner may not.

This Rule Set receives only the Candidate Metamodel and owns exactly
`storage-layout-table-mapping-collision` and
`storage-layout-column-collision`. The latter remains exclusive to distinct
physical Column claims. The Rule Set consumes no `InheritanceFacet`, assumes no
other Rule Set has run, and makes no topology decision. The post-validation
Model Compiler emits no Issue and never chooses a winner for duplicate Table or
Column claims.

`inheritance-materialization-key-collision` remains owned by Inheritance.
Relationship names, narrowed-view keys, Value Object rendered occurrence names,
and `familyVariant` occupy the materialized result keyspace even when one of
their spellings equals a physical Column.

## Consumer contract

- SQL read lowering resolves physical Tables, ordered projected slots, and
  per-branch slot presence through layout views. It retains tag predicates,
  typed `NULL` expressions, result aliases, `familyVariant`, and row transforms.
- Physical DML filters present cells from an Entity view in layout order.
  Operation-specific primary-key, discriminator, optimistic, and temporal gates
  retain their semantic selection and map the selected identities to slots.
- DDL iterates `TableLayout.columns`, applies `effectiveNullable`, and selects
  `physicalPrimaryKey`; dialects only render the already-selected values.
- Fixture loading resolves logical members and derived discriminator values
  through an Entity view while preserving the surface's omitted-cell policy.
- Physical Table observation enumerates `StorageLayoutFacet.tables` once and
  reads every layout's complete slot sequence.

No consumer may infer a declaration from a duplicate raw Column spelling,
rebuild a whole-family table projection, or retain a competing canonical
physical order.
