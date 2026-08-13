# m-storage-layout - Canonical Physical Table Layout

`m-storage-layout` owns the composed physical shape of every Table in an
accepted Metamodel. It depends on `m-metamodel`, `m-model-formation`,
`m-inheritance`, and `m-relationship`. Declarations continue to own member
identity and local storage, Inheritance continues to own family topology,
strategy, ancestry, concrete applicability, and discriminator semantics, and
Relationship continues to own join resolution and direction pairing. Storage
Layout combines those facts once so physical consumers never reconstruct a
competing table shape.

The module contributes both a Model Formation Rule Set and a Model Compiler.
The Rule Set validates physical Table ownership, Column claims, and the
consequences of the declared Storage Layout over the Candidate Metamodel;
whether that layout is declared where it may be is `m-inheritance`'s rule, not
this one's. The compiler runs only after validation, consumes Compiled Metadata
plus `FacetKey(m-inheritance)` and `FacetKey(m-relationship)`, and publishes the
immutable `StorageLayoutFacet`.

Storage Layout adds exactly one descriptor authoring form: the root-owned
Storage Layout selection below. It adds no per-member placement authoring form —
a member declares at most a Column Override, never a path — and no escape by
which one ordinary member opts out of its layout. Temporal axes and optional
Audit Metadata designate Attributes already declared in the Metamodel; they do
not introduce storage declarations. Relationships, narrowed relationship views,
SQL aliases, and `familyVariant` are result or query concerns and never
become physical slots.

## Storage Layout selection

```text
StorageLayout =
    Columns
  | Document(column: Column)
```

Storage Layout is a closed, root-owned mapping policy. `Columns` is the default
and is the layout of every Entity whose accepted metadata declares none. It is
the layout this module composed before the `Document` arm existed: each mapped
Attribute contributes its own direct Column and each top-level Value Object
occurrence contributes its own Structured Column.

`Document` selects Relational Document Layout. One Structured Column, named by
the arm's `Column`, carries the document-resident state of every governed row;
structurally significant members stay direct Columns. Each stored object remains
one row of one relational Table, so nothing else in this module's contract —
owner groups, tiers, effective nullability, the physical primary key, or the
views — becomes conditional on the layout.

The layout is one declaration per independent mapping owner:

- a standalone Entity declares its own layout;
- a table-per-hierarchy root declares one layout for its shared Table, covering
  every abstract and concrete participant; and
- a table-per-concrete-subtype root declares one layout policy and one
  Structured Column name that every concrete Table in the family receives.

An abstract or concrete descendant declares no layout of its own, even when
repeating the root's value. That invariant is one of the root-owned family
invariants and is reported by `m-inheritance` as
`inheritance-layout-not-root-owned`, exactly as for temporal axes, optimistic
locking, persistence, and the shared table. The compiler never copies the value
onto a descendant; it reads the family root's own declared metadata and derives
each participant's effective layout fresh.

Accepted metadata always carries a resolved Structured Column name under
`Document`. A frontend may supply a conventional name the author did not write,
but no accepted layout value, facet value, or diagnostic ever carries an
unresolved one.

Two independent mapping owners may select different layouts in one Metamodel.
Migrating an existing mapping between `Columns` and `Document` is an external
database schema change: this module defines no dual layout, no fallback from a
missing Document Path to a legacy Column, and no mixed accepted state.

## Storage Layout transparency

Storage Layout is a physical policy and is not observable as domain behavior.
For two accepted descriptors that declare one equal logical model and differ only
by root-owned `layout` blocks, the same logical stored state and the same authored
operation MUST produce equal logical observations under `Columns` and `Document`.
In particular:

- read result membership, ordering, declared member values, graph shape, and
  stored-data classification MUST NOT depend on the layout;
- a write MUST leave the same declared member values and the same occurrence
  replacement or preservation effects under either layout; and
- round-trip behavior promised by the operation's owning module MUST NOT change
  merely because several logical members share one Structured Column.

Physical observations are deliberately outside this equality. Tables, Columns,
Structured Column documents, SQL text, bind grouping, and physical table-state
rows may differ because expressing those differences is this module's purpose.
The invariant is that no module consuming Member Placement may branch on its arm
to choose a different logical verdict or write meaning. It may branch only to
locate, encode, decode, project, or mutate the same logical member.

The invariant does not make a migration transparent: changing an already
deployed mapping still requires an external schema and data migration. It says
that once either accepted mapping represents the same logical stored state,
callers above the physical seam cannot tell which mapping was selected.

## Direct roles and document residency

Under `Document`, the direct-column role set is closed:

1. every model primary-key Attribute;
2. every Attribute named by either endpoint of an accepted Relationship Join;
3. every Attribute designated as the start or end of a temporal axis;
4. every Attribute designated by accepted Audit Metadata;
5. an explicit Non-Temporal optimistic-lock Attribute; and
6. the framework-owned table-per-hierarchy variant tag.

Every other Attribute and every top-level Value Object occurrence is
document-resident. A member occupies exactly one place: a direct-role member is
never also written into the document, and a document-resident member never also
receives a Column.

Both endpoints of a Relationship Join are direct. This module does not infer a
foreign-key orientation from cardinality or ownership and leave the other
endpoint inside a document, so navigation, joins, referential DDL, and
relationship validation keep one uniform relational shape.

Role designations that overlap still produce one direct Column. A
Transaction-Time start Attribute that also realizes an audit revision instant is
one Attribute, one role, and one slot.

Role 4 is specified against accepted Audit Metadata as the tier table already
defines the `Audit` tier. Where a model supplies no accepted Audit Metadata the
role selects nothing, exactly as the Audit tier is empty for such a model.

Under `Columns` every applicable member is direct, so this role set is not
consulted at all: the layout decides which members are document-resident, not
which Columns exist.

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

Relationship exposes a second projection of the same shape — pure, total, and
issue-free — returning the locally-resolvable join endpoint Attributes of
defining Relationship declarations (`m-relationship`). Storage Layout consumes
it during validation to know which Attributes hold direct role 2 before any
facet exists, which is what lets the Rule Set decide whether an Index component
is document-resident. After validation the compiler consumes the real
`RelationshipFacet` instead.

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

RelationalDocument
  layoutOwner: EntityIdentity

ColumnContributor =
    AttributeIdentity
  | ValueObjectIdentity
  | InheritanceDiscriminator
  | RelationalDocument
```

Only a top-level Value Object occurrence is a `ValueObjectIdentity`
contributor. Its nested occurrences and scalar fields live inside the document
that column carries and contribute no slot of their own, under either layout.

`RelationalDocument` is the shared Structured Column of a `Document` layout. Its
`layoutOwner` is the standalone Entity or family root whose declaration selected
the layout, so one TPH family has one contributor for its shared Table and a
TPCS family has one contributor per concrete Table, all naming the same owner
and the same Column. It is the **only** contributor that claims a Structured
Column under `Document`: document-resident members contribute no slot and make
no Column claim at all.

```text
ColumnSlot
  column: Column
  tier: ColumnTier
  contributor: ColumnContributor
  declaringOwner: EntityIdentity
  effectiveNullable: boolean
  applicableEntities: immutable set<EntityIdentity>

MemberPlacement =
    DirectColumn(slot: ColumnSlot)
  | DocumentPath(slot: ColumnSlot,
                 path: nonempty sequence<MemberName>)

TableLayout
  table: Table
  columns: immutable sequence<ColumnSlot>
  physicalPrimaryKey: immutable sequence<ColumnSlot>
  column(Column) -> ColumnSlot | absent
  contribution(ColumnContributor) -> ColumnSlot | absent
  placement(MemberIdentity) -> MemberPlacement | absent
```

`MemberName` is a canonical local declared member name — the same spelling the
Metamodel and a materialized result use. A `DocumentPath` therefore names no
physical spelling, no dotted string, no JSON Pointer, and no provider-native
path expression; rendering one into a dialect path expression is `m-dialect`'s
job and happens below this contract, never inside it.

`DocumentPath.slot` is the slot of the document the member lives in, and `path`
locates the member *within that document*: the Table's one `RelationalDocument`
slot under `Document`, and the containing top-level Value Object occurrence's own
Structured Column under `Columns`. `DirectColumn.slot` is always a slot the
member's own contributor owns, so under `Columns` layout `placement(m)` and
`contribution(m)` select the same slot for every applicable member that is itself
a contributor — a top-level Attribute or a top-level Value Object occurrence.

`TableLayout.columns` is the complete physical Table sequence and is the sole
physical order exposed to consumers. `physicalPrimaryKey` selects the same
immutable slot values from `columns`; it does not copy slots or restate Columns.
The structural identity of a slot is `(Table, ColumnContributor)`. An inherited
Attribute in two table-per-concrete-subtype Tables therefore has one distinct
slot per Table even though both slots reference the same declaration identity.
Python object identity or any other implementation allocation identity is not
contractual.

`declaringOwner` is the Entity that declares an Attribute or top-level Value
Object. The discriminator's declaring owner is its family root, and so is the
shared Structured Column's, which is its layout owner. Every returned identity
and Column is the accepted Metamodel value, not a copied declaration or
rendered string.

`applicableEntities` contains the concrete row-owning Entities whose rows in
this Table carry the contributor. For a standalone owner it is that
standalone Entity. For a shared table it may be the complete concrete family or
a strict subset. For a table-per-concrete-subtype owner group it contains that
group's concrete owner. The discriminator applies to every row owner in its
shared Table. The shared Structured Column applies to every row owner in its
governed Table, because every governed row carries a document even when that
document is the empty object.

All sequences and sets are immutable. The three lookups are total, nonthrowing,
and expected amortized O(1); they return absent for an unknown Column,
contributor, or member. Physical-column uniqueness makes the Column lookup
unambiguous.

## Member Placement is the sole logical locator

`contribution(...)` and `placement(...)` answer different questions and both
survive. `contribution(...)` answers *which physical slot does this contributor
own*, and is what DDL, physical order, fixture binding, and physical Table
read-back consume. `placement(...)` answers *where does this member live*, and
is what SQL predicates, projection, write lowering, and materialization consume.
Under `Columns` the two agree for every applicable member that is a contributor,
so conventional behavior is one case of this contract rather than a parallel
path. They are not one lookup under a second name: a member inside a top-level
Value Object occurrence has no contributor at all, so `contribution(...)` has no
answer for it while `placement(...)` does, and the Structured Column has no
member, so `placement(...)` has no answer for it while `contribution(...)` does.

`placement(...)` is **the sole authority for locating a logical member**. No
consumer may re-derive direct-versus-document residency, reconstruct a Document
Path from member names, or infer a placement from a Column spelling, a tier, or
the presence of a Structured Column. A consumer that needs a member's location
asks; a consumer that gets absence has asked about a member this Table does not
carry.

`placement(...)` is **total** over the members applicable to its Table. It
returns absent only for a member that is unknown or inapplicable — a lookup
miss, never a "not resolved yet". There is no partial, provisional, or
deferred placement value, and absence never means the compiler has more work to
do.

Totality is possible because the facet is published whole and only after every
Rule Set has succeeded, so relationship resolution, temporal designation, and
family topology are all settled before the first `placement(...)` call. **No
Rule Set may call `placement(...)`**, and no Rule Set may consume any part of
`StorageLayoutFacet`: during validation no facet exists. A Rule Set that needs
another module's facts consumes that module's pure Candidate Metamodel
projection instead.

Placement follows the accepted layout of the member's mapping owner:

- under `Columns`, a top-level Attribute and a top-level Value Object occurrence
  are placed `DirectColumn(slot)` over the slot their own contributor owns, and
  every member *inside* a top-level occurrence — a nested occurrence or a Value
  Object Attribute — is placed `DocumentPath(slot, path)` over that occurrence's
  own Structured Column;
- under `Document`, a direct-role Attribute's placement is `DirectColumn(slot)`
  and every other applicable member's placement is `DocumentPath(slot, path)`
  over the Table's one `RelationalDocument` slot.

Conventional storage therefore already has Document Paths. A top-level Value
Object occurrence has always been stored as a document and its leaves have always
been addressed inside it (`m-value-object`); what the layout selects is how many
documents a row carries and which members live in them, not whether a member can
live inside one. That is why `placement(...)` stays total over `MemberIdentity`
— `ValueObjectAttributeIdentity` included — under both layouts, and why no
consumer branches on the layout to locate a member.

A Document Path is derived, never authored, and every path is relative to the
root of the document its slot carries. Under `Document` that root is the shared
Structured Column's object: a document-resident top-level Attribute's path is the
one-segment sequence of its canonical Attribute name, a top-level Value Object
occurrence's path is the one-segment sequence of its canonical occurrence name,
and each contained member extends its container's path by one canonical segment,
at every depth. Under `Columns` that root is the containing occurrence's own
document, so the path begins at the first segment below that occurrence: the
`city` of a top-level occurrence `address` is `("city")` over the `address`
Structured Column, which is the location conventional nested access already
reads. A `Many` occurrence contributes exactly one segment like any other: a
`postalCode` inside a `Many` occurrence named `locations` is
`("locations", "postalCode")`, and that the path crosses a collection is recorded
by the occurrence's own declared multiplicity rather than by a synthetic segment.

Only a top-level Attribute or a complete top-level Value Object occurrence is
assignable, so deeper paths exist for predicates, ordering, and materialization
and do not make a nested member independently writable.

**Logical placement order** is the order members occupy in the Table's
deterministic declaration stream — root-first ancestry, each Entity's local
declaration order, and canonical concrete order for a shared Table — before the
tier partition that fixes physical Column order. It is a member order, not a
Column order, and it is what consumers use when several members must be applied
in one deterministic sequence.

Because a `DocumentPath` claims no Column, two declarations that can never apply
to the same concrete row may derive the same path over one Structured Column.
Disjoint sibling branches of
one table-per-hierarchy family reusing one Document Path is therefore not a
Column collision and is not rejected — see the Rule Set below. The Navigable
Member Namespace (`m-metamodel`) already prevents two declarations that *can*
apply to one row from deriving one path, because it prevents them from sharing
one canonical name.

## Assignment paths and mutation composition order

**Every assignment names a top-level member.** A scalar assignment reaches its
one Document Path. A complete top-level `one` occurrence assignment recursively
reaches only the declared members its authored document names; a `many`
assignment replaces its array whole. Nested members remain unassignable on their
own.

Two consequences depend on it, and both are stated here so a later contract that
made a nested member assignable would have to revisit them together.

First, **canonical logical placement order is a sufficient mutation order.**
When one statement applies several assignments to one Structured Column, it
applies them in the order the assigned members appear in the Table's logical
placement order — never caller mapping order, and never a per-statement
arbitrary order — so the emitted expression is deterministic and stable to
author as golden SQL. No dependency sort is needed because top-level assignments
name disjoint subtrees.

Second, **an occurrence assignment establishes every parent it descends
through.** Each occurrence level type-tests its stored subtree, substitutes an
empty object for absent, JSON-null, or non-object state, applies its inner
mutations, and writes the object back at that level. This order is internal to
one assignment tree and independent of the top-level placement order.

| Assignment | Effect on the Structured Column | What survives |
|---|---|---|
| a document-resident top-level Attribute | patches that one path in place | every other key, including keys no accepted member declares |
| a top-level `one` Value Object occurrence | patches named declared members recursively | every key outside it and every undeclared or omitted key inside it |
| a top-level `many` Value Object occurrence | replaces that one array in place | every key outside the array; nothing inside a replaced element |
| an insert, including a temporal successor | binds one complete document | whatever the bound document carries |

No ordinary update replaces the whole Structured Column. Changing a member
nested inside a Value Object means assigning the whole occurrence, whose named
declared members are patched recursively.

This is strictly finer-grained than conventional Value Object storage, where a
top-level occurrence's own Structured Column is bound atomically and every
update rewrites it whole (`m-value-object`). Path patching is what makes keys
written by a newer application version survive an update at all.

## Tier classification and ordering

Every contributor is classified exactly once:

1. A model primary-key Attribute is `Identity`.
2. The table-per-hierarchy tag is `Discriminator`.
3. An Attribute designated as the start or end of a temporal axis is
   `Temporal`.
4. An Attribute designated by accepted Audit Metadata is `Audit`.
5. Every other Attribute is `Domain`.
6. A top-level Value Object is `Document`.
7. The shared Structured Column of a `Document` layout is `Document`.

Under `Document`, rules 1 through 5 classify only the direct-role contributors:
a document-resident Attribute or top-level Value Object is not a contributor and
receives no tier. The governed Table's contributors are therefore its direct
Attributes, its table-per-hierarchy tag if any, and exactly one
`RelationalDocument`, which is the last column of the last tier. Relationship-
join and explicit optimistic-lock Attributes that are not primary keys remain
`Domain`.

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
false                                      when the contributor is RelationalDocument
true                                       when applicableEntities != rowOwners(layout)
the contributor's declared nullability    otherwise
```

The shared Structured Column is never nullable. Every governed row carries a
document, and a row with no applicable document-resident member carries the
empty object rather than `NULL`, so the family's physical shape stays uniform
and no consumer distinguishes "no document" from "an empty document". It also
takes no database default: every write this contract admits binds the complete
object explicitly.

The fourth rule makes a required subtype-only member nullable in a shared
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

The Physical Primary Key is the slot selection of the derived primary-key Index
of the Entity that declares the family's primary key, in that Index's own
component order:

1. every model primary-key Attribute slot, in model-key order; then
2. each temporal dimension's **end** Attribute slot, in accepted axis order.

The Index is the sole provenance: this module selects slots for components
`m-descriptor` already derived rather than composing a key of its own, so no
consumer can observe a physical key no Index Metadata declares. Keying on the
end Attributes is what makes a Latest predicate and a milestone close key hits,
since both pin the exclusive upper bounds.

It may therefore span the Identity and Temporal tiers. A temporal-end Attribute
remains at its one canonical position in `columns`; selecting it into
`physicalPrimaryKey` does not create another slot. Inheritance owns the
root-wide temporal applicability of a family, so a shared table and every
concrete table use the same root axis designations — and, under
`table-per-concrete-subtype`, the same root-declared Index, whose components
each concrete table resolves through its own contributor lookup.

Secondary Index Metadata remains an ordered declaration of Attribute
Identities. A DDL consumer resolves each index component through the applicable
layout's contributor lookup. An index does not create another layout-owned
column sequence.

Under `Document`, an Index may name only direct-role Attributes, so every
component still resolves to a Column and the resolution above is unchanged. An
Index naming a document-resident Attribute is rejected by the Rule Set below.
Document-path indexes, expression indexes, generated columns, and
provider-native document indexes are outside this contract; adding one requires
its own design rather than a looser index rule.

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
  placements: immutable sequence<MemberPlacement | absent>
  discriminatorSlot: ColumnSlot | absent

PositionLayoutView
  concreteEntities: immutable sequence<EntityIdentity>
  columns: immutable sequence<PositionColumn>
  members: immutable sequence<MemberIdentity>
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

`members` is the position's logical member union — every top-level Attribute and
top-level Value Object occurrence applicable to at least one selected concrete —
in the same derivation order `columns` uses, before tier partitioning is applied
to the physical view. Each branch aligns its `placements` with `members`,
answering *where does this member live in this branch's row*: the entry is that
branch's `MemberPlacement` when the member applies to at least one selected
concrete in the branch, and absent otherwise.

`placements` is a derived projection, not a second fact. Each entry **is**
`branch.layout.placement(members[i])` where the member applies, and absent where
it does not, so there is one authority and the sequence can no more disagree with
it than `slots` can disagree with `branch.layout.contribution(...)`.

What it adds is alignment, which is the position view's whole shape. A
polymorphic read walks one logical member order and emits or decodes each branch
positionally, so it needs the per-branch answers *in that order* — the same
reason `slots` exists for contributors. The per-branch answers genuinely differ:
under table-per-concrete-subtype each branch has its own Structured Column, and
under `Document` the applicable document shape differs per variant, so a
polymorphic read that resolved placement once for the position would be wrong for
every branch but one. Under `Columns` each entry is the `DirectColumn` over the
slot that member's own contributor owns — the slot `slots` already names at that
contributor's own index in `columns` — so the two sequences carry the same
physical answers and the addition costs conventional consumers nothing.

`slots` and `placements` are each aligned with their own logical sequence and
never with each other. `columns` is tier-partitioned and `members` is not, so
equal indices name different declarations, and under `Document` the two
sequences are not even the same length: a document-resident member appears in
`members` and contributes no `columns` entry at all. A consumer that needs both
answers for one declaration reaches them through that declaration, not through a
shared index.

The union carries top-level members only. A Value Object leaf is located
through the branch's own `layout.placement(...)`, which is total over every
member applicable to that Table; enumerating leaves per position would grow the
view without adding an answer the branch's Table Layout does not already give.

Facet and view indexes are immutable and bounded by the accepted model. A
compiler may intern repeated applicability sets and store slot selections as
ordinals, but public values preserve structural equality and immutable access.
Arbitrary position views are statement-scoped and must not create an unbounded
model-lifetime cache.

## Layout, table-mapping, and physical-column Rule Set

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
3. all remaining Attributes;
4. top-level Value Objects; and
5. the shared Structured Column, when the owner's layout is `Document`.

Within each Attribute or Value Object category, ancestry is root first,
shared-table concrete contributors use canonical concrete Entity order, and
each local category retains declaration order. The category pass determines
diagnostics only; the compiler's six-tier stable partition remains the sole
accepted physical order. A contributor reached repeatedly through several
applicable concrete chains is one claim.

Only contributors enter this registry. Under `Document`, categories 3 and 4
therefore contain the owner's direct-role Attributes alone: a document-resident
Attribute or top-level Value Object claims no Column, so it can neither
establish a claim nor collide with one. Two disjoint sibling branches whose
members derive one Document Path are not a collision, because neither member is
a claimant. An implementation that modelled document-resident members as
contributors would re-create exactly the conflict this rule is written to
exclude.

The first contributor claiming a Column establishes that physical claim. A
later distinct contributor claiming the same Column emits:

```text
storage-layout-column-collision
```

The Issue location is the second contributor's declaration, or the root
declaration when the contributor is framework-owned: the tag declaration for a
discriminator, and the layout declaration — `EntityLocation(layoutOwner)` — for
a shared Structured Column. Its related location is the first contributor's
declaration, under the same rule. Repeated applicability of the same structural
contributor is not a collision. The boundary is the uniquely owned structural
Table: TPCS mappings with structurally distinct Tables may reuse a Column
spelling, while sibling or otherwise co-located contributors within one owner
may not.

Category 5 is last, so a Structured Column colliding with a direct Attribute
Column or a TPH tag is always the *later* claimant: the Issue is located at the
layout declaration and relates the direct contributor's declaration. That is
where an author fixes it, by naming a different Structured Column, and it needs
no separate code — the existing rule already locates a framework-owned
contributor at its root declaration rather than at a member's.

A member declaring a Column Override it cannot have emits:

```text
storage-layout-document-member-column-override
```

Under `Document`, a document-resident Attribute or top-level Value Object may
not carry a Column Override: the override would name a Column the member does
not occupy, so accepting it silently would let a model state two contradictory
placements for one member. The Issue location is the member's own declaration —
`AttributeLocation` or `ValueObjectLocation` — and its related sequence contains
`EntityLocation(layoutOwner)`, the layout declaration the override contradicts.
A direct-role Attribute may still carry an override wherever the module owning
that role permits one, and framework-fixed temporal and audit spellings stay
fixed. Writing a member's conventional Column spelling is normalized to absence
before this rule sees it, so restating the default is never a rejection.

An Index reaching into a document emits:

```text
storage-layout-index-over-document-member
```

Under `Document`, every Index component must be a direct-role Attribute. A
component naming a document-resident Attribute has no Column to index, and this
contract adds no document-path, expression, or provider-native index form. The
Issue location is the Index declaration, `IndexLocation`, because the Index is
what must change; its related sequence contains the offending Attribute's
`AttributeLocation`.

### Rule Set boundary

This Rule Set receives only the Candidate Metamodel and owns exactly
`storage-layout-table-mapping-collision`, `storage-layout-column-collision`,
`storage-layout-document-member-column-override`, and
`storage-layout-index-over-document-member`. The Column
collision code remains exclusive to distinct physical Column claims. The Rule
Set consumes no `InheritanceFacet` or `RelationshipFacet`, assumes no other Rule
Set has run, and makes no topology decision. The post-validation Model Compiler
emits no Issue and never chooses a winner for duplicate Table or Column claims.

Because Rule Sets run in unspecified order over one Candidate Metamodel, a model
may be rejected by this Rule Set **and** by another for independent reasons; a
Storage Layout Issue on such a model is permitted, and no ordering, suppression,
or precedence between the two is defined. In particular, an Attribute whose
defining Relationship Join is itself malformed is not a locally-resolvable join
endpoint, so it is classified document-resident here while `m-relationship`
rejects the join. Formation reports both, and neither module waits for the
other.

`inheritance-layout-not-root-owned` remains owned by Inheritance, with the four
other root-owned family policies. This module rejects the consequences of a
valid root-owned layout, not its ownership.

`inheritance-materialization-key-collision` remains owned by Inheritance.
Relationship names, narrowed-view keys, Value Object rendered occurrence names,
and `familyVariant` occupy the materialized result keyspace even when one of
their spellings equals a physical Column.

## Consumer contract

- SQL read lowering resolves physical Tables, ordered projected slots, and
  per-branch slot presence through layout views, and locates every logical
  member it projects, filters, or orders by through Member Placement. It retains
  tag predicates, typed `NULL` expressions, result aliases, `familyVariant`, and
  row transforms.
- Physical DML filters present cells from an Entity view in layout order.
  Operation-specific primary-key, discriminator, optimistic, and temporal gates
  retain their semantic selection and map the selected identities to slots.
  Assignments to document-resident members compose against the one Structured
  Column slot their placements name, in canonical logical placement order.
- DDL iterates `TableLayout.columns`, applies `effectiveNullable`, and selects
  `physicalPrimaryKey`; dialects only render the already-selected values. Every
  constraint it emits comes from an Index: the derived primary-key Index is
  rendered as the key constraint and each other unique Index as a unique
  constraint, and the two sets are disjoint because Model Formation refuses an
  Entity whose Indices share one name, so no consumer suppresses one constraint
  because another happens to span the same Columns. The Structured
  Column appears in DDL purely as a consequence of the layout owning one more
  `Document`-tier slot.
- Fixture loading resolves logical members and derived discriminator values
  through an Entity view while preserving the surface's omitted-cell policy. It
  places a document-resident member through its Member Placement rather than
  binding it to a Column of its own.
- Physical Table observation enumerates `StorageLayoutFacet.tables` once and
  reads every layout's complete slot sequence.
- Document Codec consumers — read materialization, write composition, temporal
  predecessor retention, and fixture construction — take the document shape they
  encode or decode from Member Placement and the accepted Metamodel, never from
  a Column spelling or a stored document's own keys.

No consumer may infer a declaration from a duplicate raw Column spelling,
rebuild a whole-family table projection, retain a competing canonical physical
order, or re-derive whether a member is direct or document-resident. The raw
Structured Column value is never an Entity member, a result field, or a
navigable member: it reaches a consumer only as the carrier the codec decodes
and the writer patches.
