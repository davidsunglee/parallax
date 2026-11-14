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
plus the Inheritance and Relationship Facets, and publishes the immutable
`StorageLayoutFacet`.

Storage Layout adds exactly one descriptor authoring form: the root-owned
Storage Layout selection below. It adds no per-member placement authoring form —
a member declares at most a Column Override, never a path — and no escape by
which one ordinary member opts out of its layout. Temporal axes and optional
Audit Metadata designate Attributes already declared in the Metamodel; they do
not introduce storage declarations. Relationships, narrowed relationship views,
SQL aliases, and `_type` are result or query concerns and never
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
occurrence contributes its own Structured Column. A scalar collection Attribute
contributes a direct Column too, but that Column is a Structured Column holding
the collection's encoded array.

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

Who may declare a layout is `m-inheritance`'s rule
(`inheritance-layout-not-root-owned`).

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

### Logical judging roots

Stored-shape classification is derived from the logical model before Member
Placement is consulted. Each Entity is one Logical Judging Root over its
applicable top-level members, and each top-level Value Object occurrence is one
root over its member tree (`m-document-codec`). The root set and member trees are
therefore equal under `Columns` and `Document`; neither a physical Structured
Column boundary nor the depth of a derived Document Path is a judging boundary.

Placement determines only how materialization reaches a requested position; the
verdict belongs to the logical member. An absent or JSON-null non-nullable top-level
Entity Attribute under `Document` and an SQL-null value for that Attribute under
`Columns` both produce `stored-data-attribute-null` with unavailable hydration. The
shared Structured Column's database type guarantees a non-SQL-null document, and a
generated Table's root-object constraint (*Document root constraint*) an
object-shaped one, but a Table created before that constraint can still hold another
root: when its raw value is JSON null, an array, or a scalar, every
requested document-resident member of that row reads as absent and takes that
member's existing verdict and hydration, and the raw carrier creates no stored-data
issue or recursive validation work. A top-level occurrence and a top-level scalar
collection receive the same presence and kind verdict under either placement, and a
scalar collection's Column is never read as a native scalar.

Logical roots do not authorize subtree validation. Classification remains one
requested branch at a time. A nested occurrence supplies no additional root, but
a conforming requested carrier advances an `m-document-codec` Logical Judging
Cursor anchored to the existing root. This makes a requested descendant
classifiable without inspecting its siblings. Unrequested descendants are
neither decoded nor judged. Predicate extraction may follow deeper physical paths
without creating classification work.

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

`Table(name)` is a declared storage name, not a physical identity: it is the
default local name a Database Binding gives the owner's physical table
(`m-database-binding`). Every table this module lays out has exactly one
independent mapping owner, and the mapping owner is the table's identity:

- a standalone Entity is one owner of its declared Table;
- one table-per-hierarchy root/family is one owner of its root-declared shared
  Table, including all abstract and concrete family participants; and
- each table-per-concrete-subtype concrete Entity is one owner of its declared
  Table and ancestry-derived mapping.

Participants within one table-per-hierarchy family are contributors to their
single family owner, not competing mapping owners. By contrast, two standalone
Entities, two different TPH families, two TPCS concrete mappings, or any mixture
of those forms are independent owners even when they declare equal Table
values; each lays out its own table.

During validation, Storage Layout obtains one owner group per unambiguous
standalone mapping, TPH family, or TPCS concrete mapping from Inheritance's
table-group projection (`m-inheritance`). Each group exposes its structural
Table, mapping owner, row owners, and complete declaration sequence. The mapping
provenance is the
`EntityLocation` of the standalone Entity, TPH root, or TPCS concrete Entity
whose declaration supplies the Table. Descendant TPH participants have no
separate Table mapping provenance.

The projection preserves declaration provenance, emits no Issue, and depends on
no other Rule Set's outcome. It returns only groups whose family, strategy,
ancestry, and intended Table are unambiguous. The Inheritance Rule Set reports malformed topology or Table
ownership; Storage Layout neither duplicates those issues nor guesses a group.
Rule Sets therefore remain independent of invocation order and no validation-
time facet exists. After validation the compiler reads each family's complete
declaration sequence from the real `InheritanceFacet` instead.

Relationship's join-endpoint projection likewise emits no Issue and depends on no
other Rule Set's outcome, answering the locally-resolvable join endpoint
Attributes of defining Relationship declarations (`m-relationship`). Storage
Layout consumes it during validation to know which Attributes hold direct role 2
before any facet exists, which is what lets the Rule Set decide whether an Index component
is document-resident. After validation the compiler consumes the real
`RelationshipFacet` instead.

Storage Layout visits owner groups in canonical mapping-owner Entity Identity
order. Independent owners are never merged into one physical key, contributor
applicability set, or eventual layout, whatever names they declare: the
compiler publishes exactly one coherent layout per mapping owner. Equal
declared names are no formation defect; two owners resolving to one physical
table is refused when a binding resolves the model
(`binding-table-collision`, `m-database-binding`).

Within a uniquely owned group, the declaration sequence is the one
`m-inheritance` fixes: a standalone Entity's own declarations, a
table-per-concrete-subtype concrete Entity's root-to-concrete ancestry, and a
table-per-hierarchy family's complete family declaration sequence
(`m-inheritance` "The family declaration sequence"), dormant participants
included. Each Entity's local Attributes and top-level Value Objects retain
their respective declaration orders. A contributor already encountered through
another applicable concrete is retained once and accumulates that concrete's
applicability.

## Layout values

The terms here and under *Entity and position views* name the derived facts other
modules cite. Their field sets, accessor spellings, and representation are not a
binding contract; the ordering, applicability, nullability, and placement rules
stated over them are.

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

A **Column Slot** is one physical Column of one Table. It names its `column`,
`tier`, `contributor`, `declaringOwner`, `effectiveNullable` answer, and
`applicableEntities`.

A **Member Placement** (`MemberPlacement`) locates one logical member. Its two arms
are `DirectColumn(slot)` and `DocumentPath(slot, path)`, whose `path` is a nonempty
sequence of `MemberName`.

A **Table Layout** (`TableLayout`) is the composed physical shape of one Table: its
`mappingOwner`, its declared `table`, its `columns`, its `physicalPrimaryKey`, its
`indices` with their `primaryKeyIndex` and `uniqueKeys`, its
`temporalConstraints`, and its `documentRootConstraint`. It answers a Column's slot and position, a contributor's
slot, and a member's Member Placement. The mapping owner is the Table's identity;
the declared `table` is that owner's storage name, carried as data.

`MemberName` is a canonical local declared member name — the same spelling the
Metamodel and a materialized result use. A `DocumentPath` therefore names no
physical spelling, no dotted string, no JSON Pointer, and no provider-native
path expression; rendering one into a dialect path expression is `m-dialect`'s
job and happens below this contract, never inside it.

`DocumentPath.slot` is the slot of the document the member lives in, and `path`
locates the member *within that document*: the Table's one `RelationalDocument`
slot under `Document`, and the containing top-level Value Object occurrence's own
Structured Column under `Columns`. `DirectColumn.slot` is always a slot the
member's own contributor owns, so under `Columns` layout every applicable member
that is itself a contributor — a top-level Attribute or a top-level Value Object
occurrence — is placed over the slot it contributes.

`TableLayout.columns` is the complete physical Table sequence and is the sole
physical order exposed to consumers. `physicalPrimaryKey` selects the same
immutable slot values from `columns`.
The structural identity of a slot is `(mapping owner, ColumnContributor)`. An
inherited Attribute in two table-per-concrete-subtype Tables therefore has one
distinct slot per Table even though both slots reference the same declaration
identity.
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

All sequences and sets are immutable. A Table Layout's lookups are total and
nonthrowing; they return absent for an unknown Column, contributor, or member.
Physical-column uniqueness makes both Column lookups unambiguous.

## Member Placement is the sole logical locator

Member Placement is the one answer to where a logical member lives; *Storage
Layout transparency* states what no consumer's use of it may change.

Every member applicable to a Table has exactly one location. A member has no
Member Placement only when it is unknown or inapplicable — a lookup miss, never a
"not resolved yet". There is no partial, provisional, or deferred placement value,
and absence never means the compiler has more work to do.

Every Rule Set judges the Candidate Metamodel; validation depends on nothing
compilation produces.

Placement follows the accepted layout of the member's mapping owner:

- under `Columns`, a top-level Attribute — a scalar collection included — and a
  top-level Value Object occurrence are placed `DirectColumn(slot)` over the
  slot their own contributor owns, and
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
live inside one. That is why Member Placement covers every `MemberIdentity`
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
declaration sequence (*Physical table ownership and groups*), before the
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
one Document Path. A top-level Value Object occurrence assignment binds that
occurrence's complete document at the occurrence's own Document Path, at either
cardinality. Nested members remain unassignable on their own.

Two consequences depend on it, and both are stated here so a later contract that
made a nested member assignable would have to revisit them together.

First, **canonical logical placement order is a sufficient mutation order.**
When one statement applies several assignments to one Structured Column, it
applies them in the order the assigned members appear in the Table's logical
placement order — never caller mapping order, and never a per-statement
arbitrary order — so the emitted expression is deterministic and stable to
author as golden SQL. No dependency sort is needed because top-level assignments
name disjoint subtrees.

Second, **an assignment establishes no parent**, because it descends through
none: a top-level member's Document Path is one segment, whose parent is the
Structured Column's own root object, and every governed row carries that object.
An assignment therefore creates only the final path segment, which is all a
document-mutation expression is required to do (`m-dialect`).

| Assignment | Effect on the Structured Column | What survives |
|---|---|---|
| a document-resident top-level Attribute | writes that one path in place | every other key, including keys no accepted member declares |
| a top-level Value Object occurrence, `one` or `many` | replaces the subtree at that one path | every key outside it; nothing inside it |
| an insert, including a temporal successor | binds one complete document | whatever the bound document carries |

No ordinary update replaces the whole Structured Column: the unit of replacement
is the assigned occurrence, never the row. Changing a member nested inside a
Value Object means assigning the whole occurrence, and what that stores is the
document the author stated — an omitted declared member is absent afterwards and
an undeclared key inside the occurrence does not survive, at any depth.

The rule is therefore identical to conventional Value Object storage, where a
top-level occurrence's own Structured Column is bound atomically and every update
rewrites it whole (`m-value-object`). The two layouts differ only in whether the
row as stored is one document or several columns; assigning an occurrence
replaces its value under both, and neither layout merges an assigned occurrence
into the stored one. What still distinguishes this layout is that an update
leaves every key it does not assign standing, which is what makes a key written
by a newer application version survive an unrelated write.

## Tier classification and ordering

Every contributor is classified exactly once:

1. A model primary-key Attribute is `Identity`.
2. The table-per-hierarchy tag is `Discriminator`.
3. An Attribute designated as the start or end of a temporal axis is
   `Temporal`.
4. An Attribute designated by accepted Audit Metadata is `Audit`.
5. A scalar collection Attribute (`multiplicity: many`) is `Document`.
6. Every other Attribute is `Domain`.
7. A top-level Value Object is `Document`.
8. The shared Structured Column of a `Document` layout is `Document`.

Under `Document`, rules 1 through 6 classify only the direct-role contributors:
a document-resident Attribute or top-level Value Object is not a contributor and
receives no tier. A scalar collection holds no direct role (`m-metamodel`), so
under `Document` it is always document-resident. The governed Table's contributors are therefore its direct
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
sequence by `ColumnTier` order. Declaration order remains stable inside each
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

This physical non-null guarantee does not assert that stored JSON is object-shaped;
the separate root-object constraint does, for a Table created with it (*Document root
constraint*). Neither is a deep shape constraint: no member inside the root is
validated by the DDL. Read materialization treats a JSON-null, array, or scalar
carrier, which a Table without the constraint can hold, by the member-local missing
projection, and creates no cursor for it.

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

## Physical indices

Index Metadata remains the owner of each Index's identity, ordered components,
and uniqueness. The compiler maps every accepted Index once onto each Table
carrying all of its components, and `indices` publishes the result: the derived
primary-key Index first, then every other Index in the accepted model's
canonical Entity order and, within one Entity, declaration order. Every other
entry references its accepted declaration without copying it; the primary-key
entry's declaration is instead derived from the declaring Entity's key and axes
by `m-descriptor`'s rule, so it equals that Entity's derived Index without being
looked up among its accepted Indices. Each entry selects the Table's existing
slots for its components in component order. On a Table carrying
`temporalConstraints`, every other entry — unique and non-unique alike — then
selects the Table's axis end slots in canonical dimension order, Valid Time
before Transaction Time, which are the ends the primary-key entry's own
components already close with; every Index of a temporal Table therefore ends
with the axis ends. An entry names a slot once where two temporal dimensions
designate one end Attribute. It copies no slot and creates no other
layout-owned column sequence. `primaryKeyIndex` is that first entry, whose
`columns` are exactly `physicalPrimaryKey`; `uniqueKeys` selects the unique
entries of `indices` in the same order.

The appended ends are the layout's, not the author's: an authored Index's
declaration keeps exactly its authored components, and the entry rather than
the declaration describes the Columns a consumer emits, as
`physicalPrimaryKey` does for a key. The family root's axes are resolved into
each Table's own end slots, so an Index a descendant declares ends with the
root's ends there too. Whether a Table carries an Index is decided by its
authored components alone, before the ends follow them: every Table of a
temporal family carries the ends, and that never brings a sibling's Index onto
it.

An Index names only local Attributes of its declaring Entity, so it reaches
exactly the Tables carrying that Entity's members: a standalone Entity's own
Table, a table-per-hierarchy family's shared Table for any participant, and
every concrete Table descending from the declaring position under
table-per-concrete-subtype. A root-declared Index therefore has one entry per
concrete Table, each over that Table's own slots. An entry constrains rows of
its own Table only; it is never a family-wide guarantee across concrete Tables.
Each component slot keeps its own `effectiveNullable` answer. Consumers read
these entries rather than resolving components themselves.

A DDL consumer creates **every** entry of `indices` except `primaryKeyIndex` —
unique and non-unique alike — as a separately named statement of its own, never
as an inline table constraint and never suppressed for spanning Columns another
Index already spans. Only the derived primary-key Index is inline, as the
Table's key. That is what lets a uniqueness violation report a physical name the
consumer can correlate with the Index it created; the naming rule is
`m-schema-delta`'s.

Under `Document`, an Index may name only direct-role Attributes, so every
component still has a direct slot and the mapping above is unchanged. An Index
naming a document-resident Attribute is rejected by the Rule Set below.
Document-path indices, expression indices, generated columns, and
provider-native document indices are outside this contract; adding one requires
its own design rather than a looser index rule.

## Temporal history constraints

`temporalConstraints` is a temporal Table's own constraint definitions, compiled
once with the layout and retained for the accepted model's lifetime; it is absent
exactly when the family mapped to the Table declares no As-Of Axis. Each of its axes
references the family root's accepted `AsOfAxisMetadata` and selects the Table's
existing slots for its start and end Attributes, resolved through the Table's own
contributor lookup exactly as the physical primary key's components are. So a
table-per-hierarchy Table and every table-per-concrete-subtype concrete Table
carry the root's axes over their own slots, and no consumer infers an axis from a
Column tier, a Column spelling, or the physical key.

Each axis carries one **interval check**: every row of the Table has `start <
end` on that axis, so no stored interval is empty or inverted. `transactionAxis`
is present on every temporal Table and `validAxis` on a Bitemporal one. The
checks constrain each row alone.

The **exclusion** constrains how rows relate: no two rows equal on every
`logicalKey` slot overlap, as half-open intervals, on every axis at once — in
Transaction Time on a Transaction-Time-only Table, and in both periods on a
Bitemporal one. This is *Milestones of one object never overlap*
(`m-temporal-write`) stated over the Table's own rows, so it governs history as
well as current coverage and every writer of the Table. Intervals that only meet
do not overlap.

`logicalKey` selects the Table's slots for the family root's declared
primary-key Attributes in declaration order: `primaryKey` without the axis end
Attributes it derives from them. It never includes the table-per-hierarchy
discriminator, so a shared Table protects an object's history whatever concrete
shape each row was written as, while a table-per-concrete-subtype family is
protected per concrete Table, matching its physical key. `primaryKey` is the
Table's own `primaryKeyIndex`; its Columns are unchanged.

These definitions carry no names. A constraint's name is a fact of the physical
table a Database Binding resolves for the mapping owner, derived once at
resolution from the definitions here (`m-database-binding`).

Rendering the checks, the key name, and the exclusion is `m-schema-delta`'s and
`m-dialect`'s.

## Document root constraint

`documentRootConstraint` is a `Document` Table's requirement that every row's shared
Structured Column hold a JSON object. It selects the Table's `RelationalDocument`
slot and is present exactly when the Table has one, so a table-per-hierarchy family's
shared Table carries one and each table-per-concrete-subtype concrete Table carries
its own over its own slot. No consumer infers it from a Column tier or spelling. A
`Columns` Table has none: a top-level Value Object occurrence's or scalar
collection's own Structured Column legitimately holds SQL NULL or an array.

The constraint is shallow. It governs the root's kind alone, never a member's
presence, kind, or value inside it, so member-local stored-data verdicts are
unchanged. Like the temporal constraints it carries no name; its name is derived at
binding resolution (`m-database-binding`), and rendering it is `m-schema-delta`'s and
`m-dialect`'s.

## Constraint names

Each constraint's name — the primary key's, the exclusion's, each axis's
interval check's, and the document root check's — is:

```text
pxc_<kind>_<readable-table-prefix>_<fingerprint>
kind: pk | tx | valid | excl | doc
```

The **fingerprint** is the first 128 bits of SHA-256, as 32 lowercase
hexadecimal characters, over this sequence of UTF-8 fields, each preceded by its
byte length as four big-endian bytes:

```text
"pxc-1", Table name, kind,
operand-group count, then per group: semantics, operand count, each operand Column
```

An interval check has one operand group, semantics `lt`, whose operands are the
start Column then the end Column. A primary key has one group, semantics
`unique`, whose operands are its Columns in key order. An exclusion has a group
of semantics `eq` over the `logicalKey` Columns, then one group of semantics
`overlap` per axis — its start then its end Column — Valid Time before
Transaction Time. A document root check has one group, semantics `object`, whose
operand is the shared Structured Column. Prefixing each group with its semantics and
operand count keeps group boundaries in the digest, and the version field makes
a later change to what is hashed produce different names by construction. The
Table name is the resolved physical table's raw local name, never its qualifier
or a quoted or qualified spelling: a binding that overrides the local name
changes every name, and a binding that only changes the location changes none.

The **readable prefix** is the Table name with every maximal run of characters
other than ASCII letters and digits replaced by one underscore, surrounding
underscores trimmed, and ASCII letters lowercased; an empty result becomes
`table`. Only that prefix is truncated, so that the whole name fits **63 bytes**
whatever the Dialect, and the trim and empty-result rules apply again after the
cut. The kind and the fingerprint are never truncated.

Every input is a fact of the constraint's own physical definition. A change to
the physical local table name or an operand Column changes the name; the
declared Table name a binding overrides, the qualifier, an unrelated Entity or
Class name, another Table, compilation order, and the model edition do not. Physical
Index Names are `m-schema-delta`'s separate convention.

## Entity and position views

The facet exposes table layouts plus selections that reference their existing
slots. `tables` is deterministic and contains exactly one layout per mapping
owner. `table(mappingOwner)` is total and returns absent for any Entity that owns
no Table: an unknown Entity, a table-per-hierarchy descendant, or a
table-per-concrete-subtype abstract position.

`entity(...)` returns an **Entity Layout** for a standalone or concrete row-owning
Entity and returns absent for an unknown or rowless abstract Entity. It names its
Entity and Table Layout. Its `columns` are the layout's slots applicable to that
Entity, retained in complete table order; the shared-table discriminator is
included and its derived concrete tag value is exposed by `discriminator`. The
sequence references layout slots and creates no second physical order.

`memberSelection` is the exact `m-inheritance` selection for this Entity, held by
reference rather than copied. `documentResidents` is present exactly under
`Document`. It selects the positions applicable to this concrete Entity whose
placement is a `DocumentPath` over the Table's `RelationalDocument` slot, in
logical placement order, and aligns those positions with their prepared paths.
Its shape references the selected definitions from `memberSelection.shape`; it
does not rebuild or copy member definitions or contextual bindings. Distinct
concrete variants of one shared Table therefore carry their own complete resident
selection. Under `Columns` it is absent, even though nested Value Object members
still have Document Paths inside their occurrence-owned Structured Columns.

`position(...)` answers a **Position Layout** for the canonical effective
concrete-Entity sequence already resolved by Inheritance, which the view names. An
unknown Entity, a noncanonical sequence, or
Entities from different families returns absent. An empty valid sequence
returns an empty view. `columns` is one logical, declaration-provenance-bearing
union for the position: the family's complete declaration sequence
(`m-inheritance`), keeping each contributor that applies to at least one
selected concrete, then stable tier partitioning, with an inherited
contributor included once. Each entry names its Attribute or top-level Value
Object contributor, its tier, and its declaring owner. `columns` excludes physical
discriminators because a TPCS position has none and `_type` remains a
result concern.

Each branch names one physical Table represented in the position, by its mapping
owner's layout, and the selected concretes stored in it, and aligns its
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

`placements` is a derived projection, not a second fact. Each entry **is** that
member's Member Placement in the branch's Table Layout where the member applies,
and absent where it does not, so there is one authority and the sequence can no
more disagree with it than `slots` can disagree with that layout's contributor
slots.

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
through its Member Placement in the branch's own Table Layout, which covers every
member applicable to that Table; enumerating leaves per position would grow the
view without adding an answer the branch's Table Layout does not already give.

Facet and view indices are immutable and bounded by the accepted model, and public
values preserve structural equality and immutable access.
Arbitrary position views are statement-scoped and must not create an unbounded
model-lifetime cache.

## Layout and physical-column Rule Set

The Rule Set receives projected owner groups in canonical mapping-owner Entity
Identity order and validates each owner's Columns independently. Owners
declaring equal Table names are not compared with each other here: physical
table ownership is a resolution rule (`m-database-binding`).

For every uniquely owned Table, physical Column claims share one registry. Their
diagnostic encounter order is an explicit stable category pass over that
owner's declaration sequence:

1. model primary-key Attributes;
2. TPH discriminators;
3. all remaining Attributes;
4. top-level Value Objects; and
5. the shared Structured Column, when the owner's layout is `Document`.

Within each Attribute or Value Object category, contributors follow the
owner group's declaration sequence (*Physical table ownership and groups*), and
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
contract adds no document-path, expression, or provider-native index form. Under
either layout a component naming a scalar collection emits the same Issue: under
`Columns` its Column holds a structured document rather than an indexable
scalar. The
Issue location is the Index declaration, `IndexLocation`, because the Index is
what must change; its related sequence contains the offending Attribute's
`AttributeLocation`.

### Rule Set boundary

This Rule Set receives only the Candidate Metamodel and owns exactly
`storage-layout-column-collision`,
`storage-layout-document-member-column-override`, and
`storage-layout-index-over-document-member`. The Column
collision code remains exclusive to distinct physical Column claims. The Rule
Set assumes no other Rule Set has run and makes no topology decision. The
post-validation Model Compiler
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
and `_type` occupy the materialized result keyspace even when one of
their spellings equals a physical Column.

## Consumer contract

The raw Structured Column value is never an Entity member, a result field, or a
navigable member: it reaches a consumer only as the carrier the codec decodes and
the writer patches.
