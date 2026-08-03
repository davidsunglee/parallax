# Relational Document Layout architecture

**Status:** Accepted design, non-normative

**Accepted:** 2026-08-01

**Scope:** COR-48; relational tables whose domain state is primarily stored in
one structured column

## Purpose

Parallax conventionally maps an Entity's scalar attributes to individual
relational columns and each top-level Value Object to its own structured column.
That layout is useful when the database schema should expose most domain state
directly. Some applications instead want the relational database to retain the
row identity, referential structure, temporal shape, and provenance columns
while storing most domain state together as one document.

Relational Document Layout is that alternate physical mapping. Each stored
object remains a row in a relational Table. PostgreSQL uses a `jsonb` column and
MariaDB uses a `json` column for the document-resident state; primary keys,
relationship joins, temporal bounds, Audit Provenance, optimistic locking, and
the table-per-hierarchy tag remain ordinary columns.

This is not Document Collection storage. It does not introduce collections,
MongoDB-style provider behavior, a new transaction model, or a second operation
algebra. The existing relational runtime, SQL lowering, and database port remain
in force.

This document explains the accepted architecture and intended implementation
shape. Parallax specifications, schemas, and compatibility cases remain
authoritative.

## Goals and non-goals

### Goals

- Let one root-owned declaration select document-oriented storage for a
  standalone Entity or complete Inheritance Family.
- Keep structurally significant members in direct relational columns.
- Give every other Entity member one canonical logical path in a shared
  Structured Column.
- Preserve the existing logical query and write surface.
- Support PostgreSQL and MariaDB through dialect-specific structured-document
  expressions.
- Preserve unknown document keys across ordinary and temporal partial updates.
- Centralize typed document encoding and decoding so Entity documents and Value
  Object documents cannot drift.
- Keep `m-storage-layout` as the single physical-placement authority.

### Non-goals

- Document Collection storage or a document-database adapter
- Custom document paths
- Arbitrary domain members escaping into direct columns
- Document-path or provider-native index authoring
- Generated deep JSON schema constraints
- Partial assignment to a nested Value Object member
- Dual-layout reads or writes during a schema migration
- A production MariaDB adapter in the initial Python implementation

## Authoring

Omitting `layout` retains conventional column storage. Selecting Relational
Document Layout requires the Structured Column name in *accepted metadata*, but
not from the author: a frontend may supply a conventional name during
normalization. Python does — `layout=Document()` selects the column `payload`,
and `Document(column="…")` overrides it — while the canonical descriptor always
carries the resolved name explicitly at `layout.document.column`. Nothing
downstream of authoring handles an unresolved name.

Python authors:

```python
class Customer(
    Entity,
    table="customer",
    layout=Document(column="payload"),
):
    id: Attr[int] = attr(primary_key=True)
    display_name: Attr[str]
    preferred_name: Attr[str | None] = None
```

The canonical descriptor form is:

```yaml
entities:
  - name: Customer
    table: customer
    layout:
      document:
        column: payload
    attributes:
      - name: id
        type: int64
        primaryKey: true
      - name: displayName
        type: string
      - name: preferredName
        type: string
        nullable: true
```

The normalized declaration is a closed layout value:

```text
StorageLayout =
    Columns
  | Document(column: Column)
```

`Columns` is the default. A frontend may omit it while authoring, but accepted
metadata retains the root-owned choice explicitly.

An ordinary member's optional `column` declaration is a Column Override, not
its effective placement. Columns layout retains its existing scalar and
top-level Value Object override behavior. Under Relational Document Layout, a
direct-role Attribute may use a non-default override where the module owning
that role permits one, while a document-resident Attribute or top-level Value
Object may not because the override would contradict the root layout.
Framework-fixed temporal and audit spellings remain fixed. Writing the
conventional spelling is normalized to absence rather than retained as a
semantically empty override.

There is no `path` authoring form. Document paths use canonical logical model
names and Value Object containment.

## Ownership

Layout follows the same family ownership rule as Persistence Mode, temporal
axes, Audit Metadata, and optimistic locking:

- A standalone Entity owns its layout.
- A table-per-hierarchy abstract root owns one layout for its shared Table.
- A table-per-concrete-subtype abstract root owns one layout policy and one
  Structured Column name for every concrete table in the family.
- An abstract or concrete descendant cannot repeat or override the layout.

Every governed table contains its Structured Column, even when that table has
no document-resident members. Parallax binds the empty object `{}` for that
row shape. This makes the physical family policy uniform and avoids a second
"document present only when needed" table shape.

Different standalone Entities and different Inheritance Families may select
different layouts in the same Metamodel.

Changing an existing mapping between Columns and Document is an external
database schema migration. Parallax does not dual-read, dual-write, backfill,
or fall back from a missing document path to a legacy column.

## Structural columns and document-resident state

The direct-column role set is closed for the initial layout:

1. model primary-key Attributes;
2. every Attribute used by either endpoint of an accepted Relationship Join;
3. every temporal-axis start or end Attribute;
4. every Attribute designated by accepted Audit Metadata;
5. an explicit Non-Temporal optimistic-lock Attribute; and
6. the framework-owned table-per-hierarchy variant-tag column.

Everything else is document-resident. A member occupies exactly one place:
direct roles are not duplicated in the document for convenience.

Both Relationship Join endpoints remain direct. Storage Layout does not infer a
foreign-key orientation from cardinality or ownership and then leave the other
endpoint inside a document. Keeping both endpoints direct gives navigation,
joins, referential DDL, and relationship validation one uniform relational
shape.

The Transaction-Time start Attribute that also realizes temporal
`revisionInstantAttribute` is still one direct temporal column. Overlapping
semantic designations never duplicate storage.

## Physical slots and logical placements

The current conventional layout can treat each top-level member as a physical
column contributor. Relational Document Layout breaks that one-to-one
assumption: many logical members share one physical slot. `m-storage-layout`
therefore exposes physical slots and logical placement as separate views.

```text
MemberPlacement =
    DirectColumn(slot: ColumnSlot)
  | DocumentPath(
      slot: ColumnSlot,
      path: nonempty sequence<MemberName>,
    )

TableLayout
  table: Table
  columns: immutable sequence<ColumnSlot>
  physicalPrimaryKey: immutable sequence<ColumnSlot>
  column(Column) -> ColumnSlot | absent
  contribution(ColumnContributor) -> ColumnSlot | absent
  placement(MemberIdentity) -> MemberPlacement | absent
```

`TableLayout.columns` remains the complete physical column sequence and the
sole physical order used for DDL, projections, and writes. `placement` is the
sole authority for locating a logical member. SQL, fixture provisioning,
materialization, and write lowering do not independently reclassify members as
direct or document-resident.

The shared Structured Column is one physical contributor:

```text
RelationalDocument(layoutOwner: EntityIdentity)
```

It contributes one `Document`-tier Column Slot per governed Table. Document-
resident members point to that slot through their Document Paths; they do not
each contribute another physical slot.

Conventional Columns layout keeps its existing shape. Scalar Attributes
contribute direct slots and each top-level Value Object contributes its own
Structured Column in the `Document` tier.

The canonical tier sequence remains:

```text
Identity
Discriminator
Domain
Temporal
Audit
Document
```

Relationship-join and explicit optimistic-lock Attributes that are not primary
keys remain in the Domain tier. The shared Structured Column is last.

## Path derivation

A document-resident top-level Attribute uses its canonical Attribute name:

```text
displayName -> ("displayName")
```

A top-level Value Object uses its occurrence name as the root and extends the
path through its natural containment:

```text
address                    -> ("address")
address.city               -> ("address", "city")
address.geo.latitude       -> ("address", "geo", "latitude")
locations[].postalCode     -> ("locations", "postalCode")
```

Only the top-level Attribute or complete top-level Value Object occurrence is
assignable today. Deeper paths exist for materialization, predicates, ordering,
and future evolution; they do not introduce partial nested Value Object
assignment. Value Object shape metadata, rather than a synthetic path segment,
records where a path crosses a Many occurrence.

The path is a structured sequence. Dotted strings, JSON Pointer spellings, and
provider-native path strings are not accepted model values.

## Inheritance and applicability

### Table per hierarchy

One TPH row carries the root's direct structural columns, its variant tag, and
the family Structured Column. The document may contain root members and members
applicable to the row's concrete subtype.

Disjoint sibling branches may reuse the same Document Path. For example:

```text
Payment
  CardPayment
    detail: string
  CashPayment
    detail: decimal
```

Both subtype declarations may occupy `("detail")`. The shared table's documents
are heterogeneous without a tag filter and homogeneous for the applicable
variant. The existing Navigable Member Namespace rules prevent two declarations
that can apply to the same concrete row from claiming the same canonical path.

A predicate or ordering term over a path that is not applicable to every
concrete variant the statement selects is **partitioned by variant**: per-variant
statements, or a `union all` of tag-filtered branches, so no cast ever evaluates
against a row of the wrong variant.

It is not sufficient to put `kind = 'cash'` elsewhere in the `where` clause and
rely on expression evaluation order. PostgreSQL and MariaDB may evaluate an
unguarded incompatible cast before the separate predicate.

Nor is a tag-aware expression sufficient, which is where this document
originally stopped one step short. Measurement against the pinned engines showed
that a `case when kind = 'cash' then cast(…) end` wrapper is not a guarantee
either: PostgreSQL's documented constant-folding of a `case` branch can raise
from a branch no row reaches, and MariaDB never raises at all — a failed `CAST`
in a non-data-modifying statement is a warning under every `SQL_MODE`, so the
same query returns a silently coerced value. One engine's hard error and the
other's wrong answer are not a portable contract. `m-sql` is normative; the
statement-shape rule replaced the expression-shape remedy.

Broad polymorphic reads first resolve the variant tag and decode only that
variant's applicable document shape, so projection needs no partitioning.

### Table per concrete subtype

The tableless root owns one layout policy and Structured Column name. Every
concrete table receives its own Structured Column slot and derives paths from
the complete ancestry applicable to that concrete Entity. Reuse across sibling
concrete tables is ordinary independent physical storage.

Polymorphic TPCS reads decode each branch using that concrete branch's
applicable document shape before normalizing the union result.

## Read behavior

Both read result forms preserve their existing logical output. They differ only
in which known members they need to decode.

An instance-form read selects each governed row's Structured Column once,
alongside the direct columns required by the resolved position. Its row
transform:

1. reads direct members from their direct slots;
2. chooses the applicable concrete shape from inheritance facts;
3. decodes each known Document Path through the shared Document Codec; and
4. ignores unknown document keys.

When a row-form read needs any document-resident member, it likewise projects
the Structured Column once and its row transform fans out only the requested
applicable paths under their logical result keys. The raw Structured Column is
not an extra result field. A row-form resolving read for an observed write
widens that requested set exactly as it does under Columns layout: assigned
members for equality comparison, or complete predecessor state for a temporal
target. Where it widens to complete predecessor state it also observes the
stored document itself, so it projects the Structured Column wherever the
governed table has one — an owner whose every member holds a direct-column role
included, since its retained document still carries keys no member declares.
Outside that observation lane, a row-form result that needs no
document-resident member does not project the Structured Column merely because
the Entity declares the layout.

The developer-facing Entity remains logically unchanged. The Structured Column
is not exposed as an extra Entity attribute, and callers use the same scalar
and Value Object expressions as in Columns layout.

Predicates and ordering over document-resident members lower to typed
structured-document extraction. The dialect owns path-expression syntax and
casts; the operation algebra and Metamodel retain neutral types and structured
logical paths.

Direct relationship joins continue to lower as column equality. No join
requires document extraction.

## Write behavior

### Inserts

An insert groups all present document-resident members into one canonical
document bind. Omitted nullable members remain absent. Explicit nullable values
are stored as JSON null. A Many Value Object is always present as an array and
uses `[]` when empty.

The Structured Column is `NOT NULL`, has no database default, and always
receives an explicit object bind, including `{}`.

### Ordinary updates

Direct-role assignments produce ordinary `SET column = ?` terms. Assignments
to document-resident scalar Attributes or whole top-level Value Objects compose
into one dialect-specific Structured Column expression.

PostgreSQL lowers the composition through `jsonb_set`; MariaDB uses `JSON_SET`.
Multiple assignments are applied in canonical logical placement order, never
caller mapping order. A whole Value Object assignment replaces its top-level
subtree. No read-modify-write of the complete row is required for an ordinary
partial update.

An observed keyed, versioned, or temporal update treats a missing nullable path
and JSON null as the same logical `None` for no-op equality. An unversioned,
Non-Temporal predicate update retains the established readless exception: it
does not observe equality first, so an explicit `set(member=None)` writes JSON
null even when the path was absent and reports the database's affected-row
count.

A whole Value Object assignment retains structural document equality for
observed no-op detection. Missing and explicit-null members inside that
assigned subtree are distinct, including a missing nullable top-level
occurrence versus an explicit null occurrence; the scalar missing/null collapse
does not recursively rewrite Value Object structure.

### Temporal successors and unknown keys

A temporal mutation closes one predecessor row and inserts one or more
successors. The successor insert must bind a complete Structured Column value,
so reconstructing it only from members known to the current application can
destroy forward-version data.

Assume the stored Transaction-Time row is:

```text
customer
id  in_z        out_z       payload
42  2026-01-01  infinity    {
                              "name": "Ada",
                              "preferences": {"theme": "dark"},
                              "loyaltyTier": "gold"
                            }
```

The running application knows `name` and `preferences` but predates
`loyaltyTier`. It changes `name` to `"Grace"`.

If temporal planning reconstructs the successor only from decoded known
members, it inserts:

```json
{
  "name": "Grace",
  "preferences": {"theme": "dark"}
}
```

The newer writer's `loyaltyTier` value is silently lost.

Instead, the already-required temporal predecessor observation retains the raw
Structured Column document. Successor construction starts with that document
and applies the declared path assignment:

```json
{
  "name": "Grace",
  "preferences": {"theme": "dark"},
  "loyaltyTier": "gold"
}
```

This retention requires no additional database query. Temporal writes already
materialize the predecessor to obtain its key, milestone bounds, complete
state, and concurrency basis. The observation path must carry the raw document
instead of discarding it after known members are decoded.

Bulk materialization retains the same value in its Predecessor Columns: the
shared row shape has an aligned raw Structured Column document value column
alongside its decoded Attribute and Value Object value columns. A logical
Predecessor Row view therefore exposes the raw document without allocating
another per-row carrier.

Ordinary path updates preserve unknown keys in place. Fresh inserts have no
predecessor to preserve. Explicit whole Value Object assignment intentionally
replaces that subtree, including unknown descendant keys inside it.

## Missing, null, and invalid stored data

Presence has these canonical meanings:

- omitted nullable member: key absent;
- explicit nullable value: key present with JSON null;
- required member: key present with a non-null valid encoding;
- non-applicable subtype member: key absent;
- empty Many Value Object: key present with `[]`.

Unknown keys are valid forward-version data. Reads ignore them and mutations
preserve them unless an explicitly assigned subtree contains them.

Missing required paths, malformed nested structures, and values that do not
decode into their declared Neutral Type are invalid stored data. Relational
Document Layout does not add repair, defaulting, or cross-dialect corruption
error normalization. Predicates over corrupt values may surface the underlying
database cast failure.

## Document Codec

Entity documents and dedicated Value Object documents share one deep, pure
`m-document-codec` module. Its small interface accepts a declared document
shape and presence-aware values and supports:

- constructing one complete driver-neutral document bind;
- decoding known paths by declared Neutral Type;
- applying one or more path patches in memory;
- retaining unknown keys while patching a predecessor; and
- replacing an explicitly assigned subtree.

The portable JSON encodings are:

| Neutral value | Document representation |
|---|---|
| Boolean, integer, finite float, string | native JSON scalar |
| Decimal | exact decimal string |
| Bytes | lowercase hexadecimal string |
| Date | ISO-8601 date string |
| Time | ISO-8601 time string at supported precision |
| Timestamp | UTC ISO-8601 string at microsecond precision |
| UUID | canonical lowercase string |
| JSON | native JSON value |

The codec contains no driver or database-adapter seam. `m-db-port` continues to
carry a neutral managed document bind, and each concrete adapter hands that
value to its driver's structured-document wrapper.

Document object-member order is not observable database state. Construction
uses canonical logical placement order for deterministic binds and tests, while
compatibility comparisons treat documents structurally.

## DDL, constraints, and indexes

The dialect maps the Structured Column to:

- PostgreSQL `jsonb not null`; or
- MariaDB `json not null`.

There is no database default of `{}` because every Parallax write binds the
complete required object. The initial feature adds no generated deep `CHECK`
constraints.

An Index may contain only direct-role Attributes in Relational Document Layout.
Formation rejects an Index that names a document-resident Attribute. Expression
indexes, generated columns, JSON-path indexes, and provider-native document
indexes require a later explicit design.

The Structured Column may not collide with any direct Attribute column or the
TPH tag column. The existing physical-column collision rule reports the defect.

## Module ownership and dependencies

`m-storage-layout` owns:

- structural-role classification;
- physical Column Slots and order;
- logical Member Placements;
- Structured Column and direct-column collisions;
- rejection of document-resident Column Overrides; and
- rejection of Indexes over document-resident Attributes.

It does **not** own the root-ownership rejection. `m-inheritance` already owns
every other `*-not-root-owned` rule — temporal axes, optimistic locking, the
shared table, and persistence — with one emitting function and one diagnostic
shape, so layout became the fifth instance there rather than a sixth vocabulary
in a second module. `m-storage-layout` consumes the resulting root ownership and
rejects the *consequences* of a valid root-owned layout.

Its compiler consumes accepted Compiled Metadata, the Inheritance Facet, and the
Relationship Facet. The relationship dependency is explicit because accepted
Relationship Joins designate direct-role Attributes:

```text
m-storage-layout --> m-metamodel
m-storage-layout --> m-model-formation
m-storage-layout --> m-inheritance
m-storage-layout --> m-relationship
```

Validation remains Rule Set-order-independent. Inheritance and Relationship
each expose a pure Candidate Metamodel projection for the bounded facts Storage
Layout needs before facets exist. The compiler consumes the accepted facets
after every Rule Set succeeds.

Accepted Audit Metadata is input to storage compilation, not an Audit
Provenance facet. `m-storage-layout` therefore classifies designated audit
Attributes directly without depending on runtime `m-audit-provenance`; Audit
Provenance remains downstream and consumes the completed layout.

`m-document-codec` depends on `m-core` and `m-metamodel`. SQL, lifecycle
materialization, temporal observation, fixture provisioning, and conformance
code consume its pure interface. `m-dialect` owns only provider-specific
document expressions and typed casts.

## Formation errors

Inheritance owns the rejection of a layout declared outside a standalone Entity
or inheritance root, as it owns every other root-owned family policy.

Storage Layout owns the semantic rejection vocabulary for:

- a non-default Column Override on a document-resident member;
- an Index naming a document-resident Attribute; and
- a Structured Column colliding with a direct Attribute or discriminator
  column, through the existing physical-column collision rule.

Descriptor and Python frontends reject only malformed authoring syntax and
types. They do not duplicate semantic role classification.

## Compatibility and implementation coverage

The feature is not complete when only simple insert and find operations work.
Formation must not accept Relational Document Layout until the implementation
supports the existing applicable capability surface:

- standalone, TPH, and TPCS mappings;
- ordinary and optimistic-locking writes;
- Transaction-Time and Bitemporal reads and writes;
- relationships and navigation;
- scalar and nested Value Object predicates and ordering;
- PostgreSQL and MariaDB reference/conformance execution; and
- PostgreSQL through the production Python adapter.

The compatibility corpus needs focused witnesses for:

- descriptor layout normalization and root ownership;
- PostgreSQL and MariaDB DDL;
- every Document Codec leaf encoding — one witness per row of the encoding
  table, plus absence and explicit null — rather than a representative sample,
  because the six types with no defined spelling before this design got there by
  never being exercised;
- insert, read, scalar path update, whole Value Object replacement, and
  physical table state;
- predicates, ordering, missing/null behavior, and nested Value Objects;
- relationship joins and navigation;
- optimistic-lock advancement and no-op behavior;
- one Transaction-Time update and one Bitemporal split;
- TPH broad reads and tag-guarded sibling path reuse;
- TPCS polymorphic union reads;
- unknown-key preservation in a temporal successor; and
- each formation rejection owned by Storage Layout.

Audit placement receives specification and unit coverage with the layout.
Behavioral Audit Provenance corpus cases wait until Audit Metadata and its
runtime behavior are active.

Python unit coverage additionally exercises declaration authoring, descriptor
serde, layout rules and facet lookup, codec round trips, SQL compilation,
materialization, write lowering, temporal observation, and the PostgreSQL
adapter bind. The initial work does not add a production MariaDB Python adapter;
the language-neutral reference and conformance paths remain responsible for
both database types.
