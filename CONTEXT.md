# Parallax

Parallax defines a language-neutral object-relational mapping contract and lets each language provide an idiomatic API that conforms to that contract.

## Core Glossary

### Model And Runtime Surface

**Descriptor**:
A canonical YAML or JSON interchange document that encodes a Parallax domain
model for conformance, tooling, and cross-language transport. It is one input
to the Metamodel Interface, not the required runtime representation.
_Avoid_: runtime metamodel, metadata interface, spec, generated model

**Metamodel Interface**:
The language-neutral semantic view through which behavioral modules inspect a
complete, accepted Parallax domain model as locally declared, independent of
how that model was authored or stored. Inherited, flattened, or otherwise
effective views are derived by their owning semantic modules.
_Avoid_: descriptor record, serialized model, reflection API

**Entity Metadata**:
The read-only Metamodel Interface view of facts declared at one entity
position. It is self-identifying, keeps inheritable facts explicitly local,
and places non-inherited Index Metadata last as physical access-path metadata.
It never contains inherited or flattened members from another position.
_Avoid_: entity record, effective entity, reflected class

**Persistence Mode**:
The mapping-level capability governing whether Parallax may both read and
write an Entity or may only read it: `ReadWrite | ReadOnly`. Read Write is the
default; Read Only is declared for an exceptional non-writable mapping.
Persistence Mode does not describe in-memory mutation—Entity values remain
frozen—and is separate from security access, Transaction Time, and transaction
demarcation. It is family-wide: a standalone Entity or inheritance root owns
the value, and every descendant uses the root's value unchanged.
_Avoid_: access, mutability, transactional entity, writable object

**Entity Identity**:
The language-neutral `(namespace, name)` pair that uniquely identifies one
entity within a Metamodel. Its qualified spelling is `<namespace>.<name>`, or
the bare name when no namespace exists. `Identity` is not shortened to `Id`,
which denotes an entity instance's primary-key value.
_Avoid_: Entity ID, class name, bare entity name, table name, Python type

**Entity Reference**:
A closed unresolved union. A Relative Entity Reference carries one local name
and resolves in its containing Entity declaration's namespace; an Exact Entity
Reference carries an Entity Identity and resolves to it unchanged. It stores no
raw spelling, declaring owner, Python class, or module name.
_Avoid_: global name lookup, unique-name fallback, Python forward reference

**Inheritance Metadata**:
The locally declared closed inheritance-position value: an Abstract Root with
its Inheritance Strategy, an Abstract Subtype with its parent Entity Identity,
or a Concrete Subtype with its parent and optional local tag value. It never
copies a root strategy or other effective family facts onto a descendant.
_Avoid_: role record, flattened hierarchy, effective inheritance view

**Inheritance Strategy**:
The structured root-owned physical family mapping: Table Per Hierarchy with
one tag column, or Table Per Concrete Subtype. Descendants never repeat it.
_Avoid_: strategy string, descendant strategy, table-per-leaf

**Attribute Identity**:
The language-neutral `(Entity Identity, attribute name)` pair that identifies
one declared scalar attribute. It is shared by metadata and resolved operation
values. The full `Identity` name distinguishes it from an attribute value or
primary-key ID.
_Avoid_: Attribute ID, column name, dotted string, Python descriptor

**Index Identity**:
The language-neutral `(Entity Identity, index name)` pair that identifies one
locally declared physical index. The full Identity distinguishes the model
declaration from any database-generated identifier.
_Avoid_: Index ID, index column, global index name

**Index Metadata**:
The self-identifying local physical-index view: one Index Identity, a nonempty
declaration-ordered sequence of Attribute Identities, and its uniqueness flag.
An Entity carries its derived primary-key index first, then every index it
authors. Indexes are never inherited and contain no duplicated column names.
_Avoid_: index record, column list, effective index

**Relationship Identity**:
The language-neutral `(source Entity Identity, relationship name)` pair that
identifies one directional relationship declaration. Relationship paths reuse
it instead of carrying dotted names. The full `Identity` name distinguishes a
model declaration from any row identifier.
_Avoid_: Relationship ID, target name, relationship string, Python descriptor

**Attribute Metadata**:
The self-identifying, read-only Metamodel Interface view of one locally
declared Entity scalar attribute. It contains its Attribute Identity, Neutral
Type, an optional Column Override, a Not-Primary-Key or Primary-Key state (the
latter owns Primary-Key Generation), and normalized flags; it never contains
inherited context, effective Member Placement, or descriptor spellings.
_Avoid_: attribute record, reflected field, effective attribute

**Neutral Type**:
The `m-core` structured language-neutral scalar type used by metadata,
operations, rows, and behavioral contracts. Fixed types are closed variants
such as Int64 and Timestamp; Decimal additionally carries validated precision
and scale. Textual spellings such as `decimal(18,2)` exist only at interchange
boundaries.
_Avoid_: type string, database type, Python type annotation

**Neutral Value**:
A value drawn from the declared Neutral Type's `m-core` logical value space:
boolean, integer, float, decimal, string, bytes, date, time, timestamp, UUID,
or an immutable JSON value. Null is not a Neutral Value; a position admits
null only through its own contract, such as a nullable member.
Languages represent these idiomatically while preserving
their logical type and immutability.
_Avoid_: untyped object, descriptor literal, database value

**Relationship Join**:
The static mapping equality between one source Attribute Identity and one
target Attribute Identity. It is model metadata, not an executable Predicate
and does not separately repeat a foreign-key hint.
_Avoid_: join string, query comparison, SQL `ON` fragment

**Unresolved Relationship Declaration**:
The pre-resolution Defining-or-Reverse relationship union whose target and
ordering may still use model-relative references or target-local names.
_Avoid_: relationship metadata draft, parsed relationship, relationship config

**Relationship Declaration**:
The identity-resolved, validated Defining-or-Reverse local declaration
preserved in Entity Metadata before `m-relationship` derives a symmetric view.
_Avoid_: Relationship Metadata, resolved relationship, association cache

**Defining Relationship Declaration**:
The relationship variant that alone owns the association's join, cardinality,
dependency, and direction-specific ordering. Its target exists only inside the
join, and the accepted local declaration remains distinct from the symmetric
Relationship Metadata compiled by `m-relationship`.
_Avoid_: relationship mapping, anchor relationship, owning side

**Reverse Relationship Declaration**:
A relationship variant that names one Defining Relationship Declaration
through `reverse_of` and may add only direction-specific ordering. It repeats
no join, cardinality, dependency, or separate target.
_Avoid_: second mapping, repeated join, inferred class property

**Relationship Facet**:
The immutable `m-relationship` view that pairs validated Defining and Reverse
Relationship Declarations into symmetric Relationship Metadata, with direct
identity lookup and declaration-ordered per-Entity enumeration.
_Avoid_: relationship registry, navigation metadata cache, metadata patch

**Relationship Metadata**:
The symmetric, execution-ready description of one relationship direction,
including its join, cardinality, reverse name, dependency, and ordering. It is
derived in the Relationship Facet rather than stored as a local declaration.
_Avoid_: relationship declaration, descriptor relationship, join configuration

**Primary-Key Generation**:
The normalized strategy by which a primary-key value is supplied: Application
Assigned, Max, or a fully resolved Sequence carrying its name, batch size,
initial value, and increment size. It is a structured semantic value, not a
strategy string plus conditional options.
_Avoid_: optional PK generator, generator config record, missing strategy

**Unresolved Metamodel**:
An immutable, representation-independent declaration view whose local facts
are normalized but whose model-relative references may still require
resolution. It exposes only a nonempty Entity declaration sequence: duplicates are
permitted input, no lookup or uniqueness promise exists, and frontend order is
diagnostic rather than semantic. Both native and descriptor frontends may
implement it as views over native declarations instead of copying a record
graph. It is never input to behavioral execution.
_Avoid_: Unresolved Candidate, raw descriptor, reflected classes, mutable model
builder

**Candidate Metamodel**:
An immutable Model Formation state in which every model-relative reference has
become its canonical structured Identity, but semantic module invariants have
not yet all been accepted. It preserves resolved declaration structure rather
than pretending to be final Metadata, allowing owner Rule Sets to validate and
the Metadata Compiler to normalize it. It introduces canonical Entity
enumeration and total non-throwing declaration lookup but no facets or
behavioral authority.
_Avoid_: Resolved Candidate, bare Candidate, accepted metamodel, partially
sealed hub, optional reference

**Entity Declaration**:
The shallow, identity-resolved counterpart of an Unresolved Entity Declaration.
Every model-relative reference is canonical, while defining-versus-reverse
relationships, reusable Value Object shape graphs, local inheritance roles,
and other declaration structure remain available to their semantic owner. It
is compiler input, not Entity Metadata.
_Avoid_: Resolved Entity Declaration, Entity Metadata, validated entity,
flattened declaration

**Compiled Metadata**:
The internal, immutable, canonical Entity Metadata view produced by the one
`m-metamodel` Metadata Compiler after every Rule Set succeeds. It has local
lookup but no facets or behavioral authority; the accepted Metamodel combines
it with the complete typed facet set without copying another metadata graph.
_Avoid_: accepted metamodel, metadata facet, mutable assembly draft

**Metadata Compiler**:
The one issue-free `m-metamodel` compiler that converts a validated Candidate
Metamodel into Compiled Metadata. It performs representation normalization
and index construction but owns no semantic validation; module Model Compilers
remain facet-only.
_Avoid_: compiler registry, metadata patch merger, validation transform

**Unresolved Entity Declaration**:
The shallow Entity declaration exposed by an Unresolved Metamodel. It reuses
normalized Metadata values for reference-free facts and uses separate
Declaration protocols only where resolution is still required. Its Entity-list
position is non-semantic, while each local member sequence preserves authoring
order. It provides no lookup and is not an unresolved duplicate of the full
Metadata graph.
_Avoid_: entity metadata draft, descriptor entity record, reflected class record

**Model Formation**:
The deterministic sealing process that resolves an Unresolved Metamodel,
validates the resulting Candidate Metamodel, and compiles module-owned effective
Metadata and facets into an accepted Metamodel.
_Avoid_: descriptor validation, hub mutation, transform registration

**Metamodel Facet**:
An immutable, module-owned effective view compiled during Model Formation from
the accepted local declarations. It accelerates behavioral interpretation
without becoming declared model truth.
_Avoid_: flattened metamodel, metadata cache, propagated declaration

**Facet Key**:
A typed internal key owned by one core semantic module and identified by that
module's canonical catalog identity. It attaches and retrieves that module's
Metamodel Facet from an accepted Metamodel; it is not a developer-authored
string or a registration mechanism.
_Avoid_: facet registry, plugin key, public metadata property

**Inheritance Facet**:
The immutable `m-inheritance` view giving every accepted Entity its family
root, ancestry, effective concrete-subtype set, applicable members, effective
physical container, tag facts, and effective root-owned Persistence Mode —
and, for any resolved position including a narrowed one, the canonical
effective concrete set with the attribute and Value Object projection
supersets — with declaring identities preserved.
_Avoid_: flattened entity view, effective metadata cache, ancestry walk helper

**Temporal Facet**:
The immutable `m-temporal-read` view classifying every accepted Entity as
Non-Temporal, Transaction-Time-Only, or Bitemporal and resolving its effective
root-owned As-Of Axes by dimension without copying axis metadata.
_Avoid_: axis registry, temporal flag, copied axis set

**Optimistic Lock Facet**:
The immutable `m-opt-lock` view resolving every accepted Entity's
family-uniform optimistic key: Unversioned, an explicit root-owned version
Attribute Identity, or the Transaction-Time-derived start Attribute.
_Avoid_: version column cache, per-subtype version, copied attribute metadata

**Audit Metadata**:
The family-wide, root-owned association between an audited Entity's provenance
semantics and explicitly declared Attribute Identities. Every descendant
inherits the metadata unchanged; frontend conveniences may expand to the
declarations before Model Formation, but accepted metadata contains no hidden
or synthesized audit attributes. Its presence denotes an audited mapping and
its absence denotes explicit opt-out. Principal audit attributes require
unbounded neutral strings, instant audit attributes require neutral timestamps,
and only the termination principal is nullable.
_Avoid_: audit flag, implicit audit columns, naming convention

**Metamodel Lookup**:
Total, non-throwing lookup of accepted local metadata by structured identity or
local member name. A miss is ordinary absence and direct access is expected
amortized constant time; language-level conveniences may translate a miss into
a coded public error.
_Avoid_: reflection search, stringly lookup, linear scan, exception control flow

**Parallax Handle**:
The configured application-side entry point for Parallax reads and for opening transactions.
_Avoid_: client, database connection, global session, ambient context

**Parallax Transaction**:
The explicit entry point for reads, writes, and managed object graph mutation inside a transaction; it is also the scope that owns managed objects and the Identity Map.
_Avoid_: transaction client, ambient transaction, hidden unit of work, session

**Inheritance Family**:
A closed polymorphic entity tree with one abstract root, optional abstract subtypes, and concrete subtypes, where reads may address any abstract position or concrete subtype and may narrow to a specific effective concrete subtype set.
_Avoid_: class tree, inheritance graph, open hierarchy

**Abstract Root Type**:
The non-instantiable, rowless entity that names an inheritance family, owns the
family strategy and its temporal as-of axes (a family is either entirely
non-temporal or entirely temporal), and carries attributes common to every
descendant concrete subtype. Under table-per-hierarchy it also owns the
family's one shared table mapping; under table-per-concrete-subtype it has no
table mapping of its own.
_Avoid_: base class object, root row

**Abstract Subtype**:
A non-instantiable, tableless subtype below the abstract root that may declare attributes, value objects, and relationships common to its descendants, and may be used as a read, relationship, or narrowing position.
_Avoid_: intermediate row, superclass table, abstract leaf

**Concrete Subtype**:
An instantiable member of an inheritance family that owns rows and represents one concrete variant of the family.
_Avoid_: subclass table, child class, concrete leaf

**Family Variant**:
The concrete subtype identity of a polymorphic result, represented canonically in compatibility data and exposed idiomatically by each language.
_Avoid_: discriminator value, class name string, mandatory type property

**Variant Tag**:
The descriptor metadata that maps `table-per-hierarchy` rows to concrete subtypes through a family `tag` and concrete subtype `tagValue`.
_Avoid_: discriminator, discriminator value

**Subtype-Declared Attribute**:
An attribute declared by an abstract or concrete subtype rather than by the abstract root; it may be common to an abstract subtype's descendants or specific to one concrete subtype.
_Avoid_: subclass field, subtype column

**Concrete-Subtype Attribute**:
An attribute declared by exactly one concrete subtype and not guaranteed on sibling concrete subtypes or unrelated abstract-subtype branches.
_Avoid_: subclass-only field, leaf column

**Value Object**:
An identity-free, nonempty composite value owned by an entity and read or
written as part of that owning entity. Every Value Object declaration contains
at least one scalar or nested member and every finite containment tree reaches
at least one scalar leaf.
_Avoid_: embedded entity, component object, relationship target

**Value Object Identity**:
The language-neutral `(Entity Identity, nonempty containment path)` pair that
identifies one top-level or nested Value Object declaration. The identity
belongs to the model declaration, not to a Value Object value, which remains
identity-free. Reusing one Value Object type at multiple containment paths
creates distinct declaration identities at those paths.
_Avoid_: Value Object ID, dotted JSON path, object identity

**Value Object Attribute Identity**:
The language-neutral `(Value Object Identity, attribute name)` pair that
identifies one scalar member declaration inside a Value Object at any depth.
_Avoid_: nested Attribute ID, dotted field string, JSON key

**Navigable Member Namespace**:
The one local name namespace used by members addressable through a typed model
path. Entity attributes, relationships, and top-level Value Objects share it;
inside a Value Object, scalar attributes and nested Value Objects share it.
Indices and Temporal Dimensions are not navigable members and remain in their
own key spaces. Inheritance extends the namespace through the ancestry chain:
a descendant cannot shadow an ancestor member, while disjoint sibling branches
may independently reuse a name.
_Avoid_: per-member-kind namespace, ambiguous path, dotted-name disambiguation

**Nested Value Object**:
A Value Object member contained recursively inside another Value Object. It
is persisted beneath its top-level occurrence and has no Column Override or
independent Member Placement of its own.
_Avoid_: stored value object, nested entity, child column

**Value Object Containment**:
The acyclic declaration relationship by which an Entity or Value Object
contains a Value Object occurrence. A reusable Value Object type may appear at
multiple paths, but direct or indirect containment cycles are invalid.
_Avoid_: recursive Value Object type, cyclic JSON shape, shared occurrence

**Value Object Multiplicity**:
The shared Multiplicity of a contained Value Object: One for a single embedded
object or Many for an ordered collection at the same top-level Member
Placement. It reuses `Multiplicity = One | Many` rather than defining Value
Object cardinality. A Many Value Object is always non-null; its empty ordered
collection is the sole representation of no contained values.
_Avoid_: Value Object cardinality, collection flag, relationship cardinality

**Column Override**:
An optional locally declared physical Column spelling for a top-level Entity
member when its eventual direct role permits customization. It is authoring
intent rather than effective placement; omission remains absence until Storage
Layout derives the member's Direct Column or Document Path.
_Avoid_: Storage Location, default column, effective column, document path

**Storage Container**:
The Entity-level physical container that holds its stored instances, declared
once rather than repeated by member placements. The initial form is a
Table; a future Document Collection is a different container form.
_Avoid_: repeated table mapping, member location, database

**Member Placement**:
The immutable `m-storage-layout` answer locating one applicable member in a
Table Layout: either one Direct Column or one Document Path beneath a Structured
Column Slot. It is the sole authority for where a member lives, is total over
the members applicable to its Table, and is derived from accepted metadata
rather than declared.
_Avoid_: Storage Location, declared column, member identity, SQL expression

**Member Identity**:
The closed union of the identity types addressing one logical member of an
Entity — Attribute Identity, Value Object Identity, and Value Object Attribute
Identity. It is what a consumer denotes a member with when it does not care
where that member is stored, and the successor to dotted member-path strings.
_Avoid_: dotted member string, column name, contributor, result key

**Direct Column**:
The Member Placement storing one top-level Entity member directly in one Column
Slot rather than beneath a Structured Column. Directness is an effective
Storage Layout role, not a second member declaration.
_Avoid_: escape column, duplicated document member, declared placement

**Table Layout**:
The immutable `m-storage-layout` view of one physical Table: its identity,
ordered Column Slots, effective physical primary key, contributor provenance,
effective nullability, and Member Placement lookup. It composes the storage
consequences of accepted Metadata and module-owned semantic designations without
making any contributing behavioral module mandatory.
_Avoid_: inheritance column order, DDL column list, flattened entity mapping

**Column Slot**:
One physical column position in a Table Layout, carrying its column identity,
Column Tier, declaring contributor, effective nullability, and the Entities to
which it applies. Many document-resident members may refer to one Structured
Column Slot through distinct Member Placements, while two model facts that
intentionally designate one Attribute Identity, such as temporal `revised_at`
and `txStart`, produce one slot rather than aliases competing for storage.
_Avoid_: selected field, result key, duplicate alias column

**Physical Primary Key**:
The ordered Column Slots by which a physical Table identifies one stored row,
selected from the derived primary-key Index. It combines model primary-key
Attributes with every temporal dimension's end Attribute, so its designated
slots may span identity and temporal Column Tiers.
_Avoid_: identity tier, domain key, declared primary key alone

**Column Tier**:
One table-wide semantic band in canonical physical order: identity,
discriminator, domain, temporal, audit, then document. A mapping with no
applicable contributor for a tier leaves it empty. Tiers take precedence over
declaration ancestry while declaration order remains stable within a tier.
_Avoid_: framework columns, per-entity prefix, module load order

**Document Path**:
The Member Placement consisting of one Structured Column Slot and a nonempty
ordered sequence of canonical member-name segments locating a value inside its
document. Every segment is derived from a canonical declared name, so a Document
Path is never authored and is never a declared Storage Location. A nested Value
Object member's full path extends its top-level occurrence's rather than coming
from a declaration of its own. Only a top-level member is assignable, so every
assignment path has exactly one segment.
_Avoid_: dotted path, JSON Pointer, column-plus-path concatenation

**Storage Layout**:
The root-owned mapping policy choosing conventional Columns or Relational
Document Layout for a standalone Entity or complete Inheritance Family. It
governs Member Placement but is distinct from the compiled physical Table
Layout.
_Avoid_: Table Layout, per-member mapping, provider capability, storage mode

**Relational Document Layout**:
A root-owned physical mapping for an Entity or Inheritance Family stored in
relational Tables, where one Structured Column contains its document-resident
domain state and structurally significant members remain in separate direct
columns. It is distinct from a Document Collection because each stored object
remains a relational table row.
_Avoid_: document storage, Mongo layout, JSON entity, blob mapping

**Document Collection**:
A Storage Container whose stored records are themselves structured documents.
Parallax applies one Metamodel shape to every document in the collection.
_Avoid_: schemaless Entity, table, document column

**Structured Column**:
A physical Column carrying a structured document. In conventional Columns
layout one Structured Column carries one top-level Value Object occurrence; in
Relational Document Layout one shared Structured Column is the document root
for every document-resident member in its Table, and compilation gives that
Column one physical Column Slot.
_Avoid_: payload column, entity JSON column, document root column, JSON blob

### Expressions And Reads

**Predicate**:
A typed expression that describes which rows or objects an entity operation targets.
_Avoid_: where object, filter object

**Assignment**:
A typed authored expression that describes a value change for one assignable
mapped scalar attribute or whole Value Object occurrence in a set-based update.
_Avoid_: setter call, update object

**Sort Key**:
A typed expression that describes attribute-based ordering for a query result.
_Avoid_: comparator callback, order callback

**Result Collection**:
An operation-backed result collection returned by `find`; it may resolve to zero, one, or many objects.
_Avoid_: array, result array

**Snapshot Graph**:
A typed plain value graph returned by a snapshot read: identity-resolved within the graph (one node per row), connected by hard pointers, pinned whole-graph at one set of as-of coordinates, and closed-world — it never issues further database work.
_Avoid_: domain snapshot, JSON output, serialization form, lazy collection

**Includes**:
The query option that requests eager relationship loading for a `find`.
_Avoid_: deepFetch, populate

**Include Path**:
A relationship path listed in `includes`; longer paths imply any intermediate relationship paths needed to load them.
_Avoid_: include tree, populate path

**Subtype Narrowing**:
A query or include constraint that limits a polymorphic entity position to an effective concrete subtype set, authored with abstract subtype and/or concrete subtype names while preserving the surrounding operation shape.
_Avoid_: manual tag filter, type cast

**Nested Value-Object Path**:
A typed path that starts at an entity-owned value object and addresses a nested member inside that value.
_Avoid_: relationship path, join path, dotted JSON string

### Execution Provenance

**Database Call**:
One attempted database round trip for a Read or Write Lowered Statement,
carrying its elapsed duration and a closed completion that distinguishes a
completed read, completed write, and database failure. A failed call still
counts as one round trip; transaction demarcation does not.
_Avoid_: Executed Statement, emission, SQL log entry, operation group

**Read Trace**:
The immutable provenance of one read that reached the database: its ordered,
non-empty Database Calls and derived round-trip count.
_Avoid_: Execution Record, query log, profiler output

**Write Batch Trace**:
The immutable provenance of one flushed write batch: its ordered, non-empty DML
Database Calls, plus whether Read Dependency or Finalization triggered it. A read
that resolved rows for one of those writes is its own Read Trace, not part of
this one.
_Avoid_: Write Execution, flush result, plan log, statement prediction

**Transaction Attempt**:
One physical database transaction within a logical transaction invocation,
carrying its ordered Read Traces and Write Batch Traces and an Active, Committed,
or Rolled Back status. A Rolled Back attempt carries an Attempt Failure.
_Avoid_: Execution Attempt, retry log, nested transaction, Transaction Result

**Attempt Failure**:
The immutable diagnostic explaining why one Transaction Attempt rolled back,
carrying its Body, Finalization, or Commit phase, stable error facts,
retry-eligibility classification, and any causative Database Call without
retaining the raised exception or transaction state.
_Avoid_: caught exception, traceback record, Database Call failure, retry decision

**Execution Log**:
The production-owned, read-only history of one logical transaction invocation,
grouping traces by Transaction Attempt across automatic retries and retaining
the effective concurrency and retry policy. It is live while the boundary is
active and seals at terminal completion.
_Avoid_: mutable logger, query log, profiler output, Write Plan history

**Transaction Result**:
The value returned by a successful transaction invocation, containing the
Transaction Body's value and its Execution Log while exposing the Committed
Transaction Attempt as the common execution view.
_Avoid_: callback value alone, transaction tuple, commit receipt

### Relationships And Object Graphs

**To-One Relationship**:
A relationship whose navigation reaches at most one related object and may be used for direct predicate path navigation.
_Avoid_: scalar relationship

**To-Many Relationship**:
A relationship whose navigation can reach multiple related objects and must use an explicit quantifier in predicates.
_Avoid_: collection relationship

**Relationship Cardinality**:
The structured source/target multiplicity of a direct relationship:
OneToOne, ManyToOne, or OneToMany. Each variant exposes `source` and `target`
as One or Many. ManyToMany is not a variant; it requires an explicit
Association Entity and two direct relationships.
_Avoid_: cardinality string, collection flag, unsupported many-to-many shortcut

**Sort Direction**:
The semantic direction of an actual ordering term: Ascending or Descending.
No ordering is represented by an empty ordering sequence, not by an
Unspecified direction.
_Avoid_: direction string, unspecified direction, natural-order sentinel

**Relationship Order**:
One target Attribute Identity plus its Sort Direction in a to-many
relationship's declared ordering. Terms preserve declaration order; an empty
sequence emits no database ordering.
_Avoid_: order string, default database order, unordered sort term

**Relationship Collection**:
A managed collection reached through an object relationship, with enough ownership and join metadata to add or remove related objects.
_Avoid_: array property, child list

**Dependent Relationship**:
A relationship whose target is owned by the source and participates in dependent delete or terminate behavior.
_Avoid_: cascade-only relationship, child relationship

**Association Relationship**:
A non-dependent relationship whose mutation changes an association, foreign key, or join row without creating or deleting the related object.
_Avoid_: owned relationship

**Association Entity**:
A mapped entity whose rows represent links between entity identities, usually
backed by an association table. It is modeled and navigated explicitly through
two direct relationships; Parallax does not currently hide it behind a
many-to-many relationship shortcut.
_Avoid_: join entity, mapping type, link table

**Polymorphic Relationship**:
A relationship whose target is an abstract root or abstract subtype and whose navigation may produce objects belonging to one or more concrete subtypes in that target's effective concrete subtype set.
_Avoid_: generic relationship, untyped relationship

**Narrowed Relationship View**:
A named relationship view produced by subtype narrowing, keyed by the relationship name and effective concrete subtype set, representing the exact narrowed relationship requested without implying the full relationship collection is loaded.
_Avoid_: partially loaded relationship, filtered array

**Managed Object**:
A live domain object owned by an open Parallax Transaction: interned in the Identity Map, with mutations buffered into the unit of work as operations at mutation time.
_Avoid_: tracked entity, active record, entity instance

**Detached Object**:
An object no longer owned by any live scope — the scope that owned it (today, the transaction) ended, or it was deliberately copied out. Mutations land only in the object; persistence happens through merge-back inside a new transaction.
_Avoid_: stale object, evicted object, offline entity

**Managed Object Graph Mutation**:
A change made through a managed domain object or one of its relationship references.
_Avoid_: object write, direct persistence

**Deferred Relationship Load**:
An on-demand resolution of a relationship for one or more already-materialized managed objects, batched over the requested set and resolved through the live transaction at each source object's as-of coordinates. The trigger idiom is per-language; the semantic is one.
_Avoid_: lazy loading, implicit fetch, N+1 loop

**Identity Cache**:
A Parallax cache scope that interns managed objects so the same database identity resolves to the same logical object within that scope.
_Avoid_: global object store, equality cache, session cache

**Identity Map**:
The transaction-scoped Identity Cache: within one Parallax Transaction, one managed object per entity family, primary key, and as-of coordinates. It makes no promise across transactions.
_Avoid_: session, session cache, first-level cache

### Writes And Correctness

**Set-Based Write**:
An update or delete expressed over a predicate or an unresolved result collection, intended to operate on the matching set rather than by materializing each object.
_Avoid_: mass operation, list setter

**Readless Write**:
A Set-Based Write whose Write Target remains a Predicate through execution, so
its exact row set is not materialized or known during planning.
_Avoid_: materialized write, bulk write, batch

**Write Target**:
The semantic row selection of a Planned Write: one Key Target, every row
matching a Predicate, or one Milestone Target. It is distinct from both
observed predecessor state and a concurrency condition.
_Avoid_: SQL where clause, observation, optimistic-lock predicate

**Key Target**:
The nonempty planner-ordered sequence of distinct complete primary-key tuples
addressed by one Planned Update or Planned Delete. A singleton and a compatible
multi-key selection are cardinalities of the same target kind; repeated
authored keys are invalid rather than silently deduplicated. Its compact shape
stores the canonical nonempty primary-key Attribute Identity sequence once and
an aligned nonempty sequence of concrete, non-null value tuples.
_Avoid_: Key Set Target, unordered key set, key predicate

**Predicate Target**:
The bare typed Predicate retained by a readless Planned Update or Planned
Delete. The enclosing Planned Write owns its Entity Identity; the target carries
no materialized keys, observation, pin, concurrency data, or redundant barrier
flag.
_Avoid_: result collection, materialized predicate, entity predicate pair

**Milestone Target**:
The current temporal milestone slot addressed by a primary-key tuple and one
write-required exclusive upper bound per As-Of Axis: the observed predecessor's
Valid-Time end when present, and invariant Infinity for Transaction Time. It is
derived independently of any optimistic concurrency gate. Its compact shape
aligns one complete primary-key value tuple and one upper-bound value per
canonical axis with their Attribute Identities; it contains no axis starts.
_Avoid_: current-row predicate, temporal gate, key-only target

**Temporal Upper Bound**:
The closed value of an As-Of Axis exclusive end in a Milestone Target: either a
finite normalized Instant or the dialect-neutral Infinity sentinel.
_Avoid_: nullable instant, database max timestamp, raw infinity string

**Object Key**:
One object's structured Entity Identity plus its ordered primary-key values,
used to address that object during write coalescing and observation lookup.
_Avoid_: object ID, row key, primary-key mapping, entity spelling

**Observation Key**:
The production-issued address of one Write Observation: an Object Key plus the
observed milestone's Edge, with no Edge for a versioned Non-Temporal row. It
names evidence in one active Unit Work and is neither the evidence nor a read
pin.
_Avoid_: reconstructed observation address, object key alone, snapshot pin, write observation

**Write Observation**:
The database evidence retained for a surviving write against existing state: an
observed positive version for a versioned Non-Temporal Entity, or one Temporal
Observation containing a complete immutable Predecessor Row. It is filed under
the object it observed plus the observed milestone's own coordinate, so two
reads at coordinates resolving to different milestones retain evidence about
each, and two resolving to one milestone share one piece of evidence. The
Temporal Facet, not a separate observation variant, distinguishes
Transaction-Time-only from Bitemporal expansion. Inserts and unversioned
Non-Temporal writes have no Write Observation by construction.
_Avoid_: optional row bag, no-observation value, write target, read pin

**Predecessor Row**:
The complete, immutable, concrete persisted state retained by a Temporal
Observation, including every applicable scalar attribute, Value Object
occurrence, primary-key value, temporal bound, audit value, and any raw
Structured Column document needed to preserve unknown keys. It contains no
generated-value expression and may be shared by every successor derived from
it. In bulk materialization this is a logical row view over Predecessor Columns,
not a requirement to allocate one row object per observation.
_Avoid_: Planned Row, sparse observation, copied successor state

**Predecessor Columns**:
The compact immutable bulk representation of complete Predecessor Rows: one
shared row shape plus aligned Attribute, Value Object, and, where the Storage
Layout requires them, raw Structured Column document value columns with the same
positive row count. It can expose a logical Predecessor Row view without eagerly
allocating a row wrapper for every selected predecessor.
_Avoid_: predecessor object array, sparse observation columns, managed objects

**Materialized Write Group**:
The private compact result of resolving one observation-requiring predicate
write before pure planning. It retains the authored mutation, one shared
primary-key shape, one immutable value column per key attribute, and either
an aligned version column or complete Predecessor Columns. Every value column
has the same positive row count. It contains no managed Entity objects,
composite-key object per selected row, eager Predecessor Row object per
selected row, per-row planning wrapper, or observation-free variant. An empty
resolution produces no group. For an assignment-bearing mutation, input materialization
uses Unit Work's equality rules while streaming and retains only rows with an
effective change; delete and terminate mutations retain every resolved row.
_Avoid_: list of observed writes, result collection, public plan group, Atomic Unit, atomic planned unit

**Write Planner**:
The model-scoped, stateless Unit Work module whose single pure planning
operation converts one flush's boundary-captured Subject Identity, lazy
Transaction Instant, concurrency mode, buffered writes, and observations into a
Write Plan. Its planning strategies are wired at construction; it retains no
attempt state and performs no database, clock, SQL, dialect, or driver work.
_Avoid_: flush coordinator, SQL planner, mutable transaction planner, Final Write Planner

**Planned Write**:
One semantic execution step within a Write Plan: a planned insert, update,
close, or delete. It may address one row or multiple rows, but its target, row
topology, concurrency decision, and expected effect are settled before SQL
lowering. Insert Origin lives only on an insert entry and Close Cause only on a
close, so the variant carries every semantic fact a later decorator needs and no
separate label can contradict it.
_Avoid_: authored mutation, buffered instruction, SQL statement, Final Write, Finalized Write Disposition, In-Place Revision, generic disposition field, mutation-kind tag

**Planned Row**:
The immutable, duplicate-free semantic contents of one planned insert, keyed by
Attribute Identities and Value Object Identities. It may contain neutral or null
values, structured Value Object occurrences, closed generated-value
expressions, and planner-derived framework attributes, but no property names,
physical columns, SQL, dialect objects, or driver values.
_Avoid_: Attribute Row, Entity Row, database row

**Planned Assignments**:
The nonempty, immutable, duplicate-free logical value changes of one Planned
Update or Planned Close: one Attribute-Identity-keyed collection of concrete
neutral or null values and one Value-Object-Identity-keyed collection of
complete structured occurrences or null. It contains no authored Assignment
expressions, generated-value expressions, physical columns, or SQL ordering.
_Avoid_: assignment wrappers, mutable map, SET clause, sparse Planned Row

**Planned Steps**:
The immutable ordered logical sequence exposed by a Write Plan. Its semantic
elements are Planned Writes, while its representation may pack homogeneous
runs and produce logical views during iteration instead of allocating one
per-step container eagerly. Planning strategies preserve compact segments and
structural sharing; temporal expansion, provenance decoration, and lowering do
not require an eager row-wrapper graph. Every exposed Planned Write and nested
target is an immutable stable view; iteration never reuses a mutable flyweight.
Equal views need not have object identity.
_Avoid_: concrete tuple contract, statement list, eager wrapper array

**Write Plan**:
The possibly empty immutable description whose Planned Steps contain all
Planned Writes that survive coalescing, cancellation, and known no-op
elimination, with temporal topology and correctness semantics decided. Derived
instants and other planning context are materialized into those writes rather
than retained beside them. It is the semantic handoff through Audit Provenance
decoration to SQL lowering, not a mutation log or SQL batch.
_Avoid_: write queue, mutation history, statement list, Flush Plan, Final Write Plan

**Write Cardinality**:
The number of existing rows a non-insert Write Target claims: exactly the
number of keys in a Key Target, exactly one for a Milestone Target, and an
unconstrained count for a Predicate.
_Avoid_: database row count, batch size, optimistic-lock gate

**Affected Rows Policy**:
The fully resolved non-insert execution policy carried by a Planned Write:
`AnyCount`, or `ExactCount` with a positive expected count and the already
classified neutral shortfall tag: Missing Target, Stale Write, or Optimistic
Conflict. An excess over an exact count is always Cardinality Corruption.
Planned Inserts do not carry this policy. A driver batch containing multiple
Exact Count steps is valid only when it reports one aligned count per logical
step; one aggregate count is sufficient only for one step whose own Key Target
contains multiple keys.
_Avoid_: inferred row-count check, effect policy, optional expected count

**Write Gate**:
An optimistic-mode concurrency condition derived from a required Write
Observation and added to a keyed update, delete, or temporal close. Locking mode
records an explicit ungated decision and relies on the shared read lock instead.
The closed payloads are a Version Gate containing its Attribute Identity and
observed integer, or a Temporal Gate containing its Transaction-Time start
Attribute Identity and observed Instant; neither repeats assignments, the full
observation, or concurrency mode.
_Avoid_: Write Target, affected-row policy, locking predicate

**Non-Temporal Concurrency**:
The closed concurrency decision on a Planned Update or Planned Delete:
`Unversioned`, or `Versioned` containing either a Version Gate or the explicit
locking-mode `Ungated` decision. It makes gate applicability structural instead
of representing it with a nullable gate.
_Avoid_: optional gate, universal Ungated, No Observation

**Write Effect Error**:
The closed Unit Work-owned failure raised by the authoritative affected-row
enforcer: Missing Target Error, Stale Write Error, Optimistic Lock Conflict
Error, or Cardinality Corruption Error. The Write Plan carries neutral
shortfall tags rather than exception classes.
_Avoid_: adapter row-count error, SQL lowering error, database error

**Missing Target**:
A non-retriable keyed-write failure in which fewer rows exist than the Write
Cardinality promised and no optimistic or stale-write classification applies.
_Avoid_: optimistic conflict, successful idempotent delete, empty predicate result

**Stale Write**:
A non-retriable consistency failure in which an observation-requiring
locking-mode write affects fewer rows than its Write Cardinality promised
despite the shared read lock that licensed its ungated execution.
_Avoid_: Optimistic Lock Conflict, Missing Target, retryable failure

**Cardinality Corruption**:
A non-retriable correctness failure in which a write affects more rows than its
Write Cardinality permits, indicating that accepted identity, storage, or
lowering invariants do not hold.
_Avoid_: optimistic conflict, stale write, retryable database error

**Temporal Write Topology**:
The ordered close-and-successor shape produced by one surviving temporal
mutation. It remains one semantic unit even when its close and successor rows
become separate Planned Writes, and adjacency in Planned Steps is its only
surviving evidence.
_Avoid_: SQL batch, statement group, independent row mutations, Milestone Plan, Milestone Open, Milestone Close, Milestone Step

**Insert Origin**:
The closed, provenance-neutral origin carried by each entry of a planned insert:
New Lineage, Carried From a retained predecessor, or Changed From a retained
predecessor. New Lineage begins a Provenance Lineage; Carried From preserves a
temporal predecessor's represented state, including a surviving head or tail
rectangle around a Bitemporal change or termination; Changed From changes that
represented state. Origin belongs to one insert entry rather than to a whole
step or a parallel array, so entries of different origins may share one planned
insert. A planned insert admits no other origin, and no other Planned Write
admits one at all.
_Avoid_: Finalized Write Disposition, Lineage Start, Carried-State Successor, Changed-State Successor, disposition tag

**Close Cause**:
The closed, provenance-neutral reason a planned close closes its temporal
predecessor: Superseded when a new database revision replaces it, or Terminated
when the mutation makes represented state explicitly absent. A terminate verb
produces Terminated even where head or tail successors survive; those successors
are independently Carried From. Only a planned close carries a cause.
_Avoid_: Finalized Write Disposition, Ordinary Revision Close, row inactivation, disposition tag

**Optimistic Lock Conflict**:
A detected gated-write shortfall because another transaction changed the
observed version or temporal milestone first. It is eligible for automatic retry
only when the surrounding transaction policy enables that retry.
_Avoid_: transient failure, automatic retry

**Audit Provenance**:
Framework-owned attribution for an audited Entity's original creation, current
revision, and, for a temporal milestone, explicit State Termination. A
Bitemporal Entity additionally distinguishes the principal and instant of the
represented state's last change from the revision that formed its current
rectangle.
Provenance is non-null where it applies to a persisted Entity, queryable as
ordinary attributes, and authored only by Parallax at the write boundary.
_Avoid_: audit columns, audit log, write-event log

**State Termination**:
An explicit temporal mutation that makes represented state absent, unbounded
or for a bounded Valid-Time window. Its `terminated_by` provenance names the
Principal that authored the absence; it does not name every Principal whose
update closed a database revision.
_Avoid_: revision close, row inactivation, physical purge

**Provenance Lineage**:
The succession of temporal milestones descended from one successful insert.
Every successor preserves that insert's creation provenance. Distinct inserts
start distinct lineages even when they reuse one primary key in disjoint
Valid-Time windows, so identical current coverage need not imply identical
creation provenance.
_Avoid_: first-ever primary-key creation, entity lifetime, row lineage

**Subject Identity**:
The stable, nonempty, opaque string by which a Principal is identified across
Parallax operations and Audit Provenance. It is captured once at an outer
database operation boundary and stored and compared verbatim: Parallax does
not trim, case-fold, parse, or impose provider syntax. Joined scopes and
automatic retries reuse the captured value.
_Avoid_: username, display name, credentials

**Principal**:
The caller-supplied identity carrier required by every outer database read and
unit of work, from which Parallax obtains and validates one Subject Identity
before database interaction and outside any retry loop. Operations inside a
unit of work inherit the captured identity rather than accepting or
reevaluating a Principal. An explicit joining unit-of-work boundary evaluates
its own required Principal once and joins only when its Subject Identity
matches the root boundary's verbatim. The operation context retains the opaque
Principal alongside that string for future provider-specific consumers; Audit
Provenance consumes only the string.
_Avoid_: Write Principal, current user, ambient principal, authorization claims

**Transaction Instant**:
The finite instant lazily captured for a unit-of-work attempt when its first
nonempty timestamp-requiring flush needs one. Once captured, it is shared by
every timestamped write in that attempt and supplies Transaction Time boundaries
and Audit Provenance timestamps. An attempt that never reaches such a flush has
no Transaction Instant and never consults the Clock Strategy; a retry captures a
fresh instant only if it independently reaches one.
_Avoid_: operation timestamp, audit timestamp, processing instant

**Clock Strategy**:
The Parallax-level strategy consulted at most once by a unit-of-work attempt,
and only when that attempt lazily captures its Transaction Instant.
_Avoid_: per-transaction timestamp override, operation timestamp override

### Temporal And Milestoning

Prior art: the Valid Time and Transaction Time terms follow Richard
Snodgrass's standard bitemporal vocabulary; Reladomo's business/processing
dates are the same dimensions under retired names.

**Temporal Dimension**:
One of the two orthogonal temporal meanings recognized by Parallax: Valid Time
or Transaction Time. The dimension itself identifies an entity's As-Of Axis;
an axis has no independently authored name.
_Avoid_: axis name, axis kind, business/processing dimension, validTime, transactionTime

**Temporality Profile**:
The single temporal fact an entity family's root declares — `nontemporal`,
`transaction-time`, or `bitemporal`. Every As-Of Axis, both endpoint attributes
of each axis, and their framework-fixed columns are derived from it, so a
descriptor spells nothing else temporal.
_Avoid_: temporal classification property, authored axis, axis block, asOfAxes

**Valid Time**:
The Temporal Dimension describing when a fact is true in the modeled world.
Its derived interval attributes are `validStart` and `validEnd`, over the
framework-fixed columns `from_z` and `thru_z`.
_Avoid_: business time, business date, effective date

**Transaction Time**:
The Temporal Dimension describing when a fact is present in the database. Its
derived interval attributes are `txStart` and `txEnd`, over the framework-fixed
columns `in_z` and `out_z`.
_Avoid_: processing time, processing date, system date

**As-Of Axis**:
A Temporal Dimension along which a milestoned entity is read and written. Its
metadata identifies inclusive start and exclusive end attributes; the
dimension itself is the axis identity. A `transaction-time` profile derives
Transaction Time; a `bitemporal` profile derives both Valid Time and
Transaction Time.
_Avoid_: temporal column, date dimension

**Milestone**:
One temporal row covering a half-open `[from, to)` interval on an as-of axis; a write chains a new milestone and closes the prior one rather than mutating a value in place, preserving an audit trail.
_Avoid_: version row, history row

**Latest**:
The open milestone on an as-of axis — its upper bound is the infinity sentinel (`to = infinity`), the version with no successor yet. A read pinned to latest lowers to the single equality `to = infinity`, the cheapest as-of predicate.
_Avoid_: now, current row (when the current wall-clock instant is meant)

**As-Of Instant**:
A read pinned to a finite point in time on an as-of axis; it selects the milestone whose half-open interval contains that instant (`from <= instant and to > instant`), which may be a superseded version rather than the latest.
_Avoid_: as of now (for a finite past pin), point-in-time row

**As-Of Coordinate**:
The lowered pin value for one declared as-of axis under which a read, managed object, or snapshot graph is resolved; latest lowers to the infinity sentinel. A temporal object's identity and its relationship dereferencing are both anchored to its coordinates.
_Avoid_: date parameter, timestamp property

**Edge Pin**:
The from-instant of a milestone used as its as-of coordinate when history and range reads return one view per milestone, so each returned version is identified and navigable at its own pin.
_Avoid_: edge point (as a result shape), version date

**Now**:
The current wall-clock instant. It coincides with **Latest** on the Transaction
Time axis (milestones there are never future-dated) but not necessarily on the
Valid Time axis, where a future-valid milestone can make the latest version
differ from the version valid at the current instant. Now is a finite instant
and therefore lowers to interval containment; it is never an alias or wire
spelling for Latest.
_Avoid_: latest (treating the two as interchangeable)

**As-Of Propagation**:
The rule that an as-of value pinned at the root of a read flows per hop across
relationship navigation and eager loading to every temporal entity in the path,
matched by axis — auto-injected from the as-of model, never written by the user.
_Avoid_: per-hop as-of, manual temporal join

### Serialization And Input

**Domain Snapshot**:
A plain JSON-serializable representation of a domain object graph, detached from Parallax relationship references and runtime state. It is a serialization output produced through a Serialization Shape, not a query result.
_Avoid_: POJO, DTO, snapshot graph, read result

**Serialization Shape**:
The declared JSON form used to convert managed domain objects into domain snapshots, expressed in terms of selected attributes and relationships.
_Avoid_: JSON mapper, object dump

**Create Payload**:
A plain input object accepted by a create operation to construct and persist a new managed domain object.
_Avoid_: unmanaged entity, insert entity

### Conformance And Scope

**Feature**:
A named behavior within a module, identified by a feature tag on the compatibility cases that exercise it. Features are finer-grained than modules: a module names a whole behavior, while a Conformance Slice cuts the corpus at feature granularity — claiming some features of a module while deferring others.
_Avoid_: capability, sub-module, facet

**Conformance Slice**:
A declared, case-granular subset of the compatibility corpus that an implementation claims through the conformance adapter for a specific implementation milestone. Because cases carry both module and feature tags, a slice may include some features of a module while deferring others, without redefining that module's boundary.
_Avoid_: module tier, partial pass list, ad hoc skip list

**API Conformance Suite**:
A test suite that proves an implementation's idiomatic public developer API reproduces the claimed Conformance Slice — running the code a developer writes through the shipped adapter against a real database, partitioning the slice with reasoned skips, asserting the corpus's expected results, and guarding that the idiomatic query builds the corpus operation. Additive proof beside the conformance-adapter grade, never a substitute.
_Avoid_: showcase, demo, examples suite, idiomatic suite

**Usage Guide**:
A rendered document demonstrating idiomatic use of the developer surface, generated from the API Conformance Suite's source and drift-checked in CI so its examples are always executed, passing tests.
_Avoid_: showcase doc, cookbook

### Future Plain-Data Query Shapes

**Projection**:
A future plain-data query shape that retrieves selected attribute paths, grouped aggregate values, or both rather than managed domain objects.
_Avoid_: partial entity, selected entity, aggregate entity

**Aggregate Query**:
A projection query that groups rows and returns aggregate values in plain data.
_Avoid_: aggregate find, grouped entity

### Errors And Validation

**Parallax Error**:
A language implementation's public error surface for Parallax failures, with stable machine-readable codes.
_Avoid_: generic error name, message-only failure, transport error

**Validation Issue**:
One structured problem inside a validation error, including enough path and code information for tools and users to locate the invalid input.
_Avoid_: validation message string, first error

**Metamodel Issue**:
The immutable `m-metamodel` value describing one resolution or semantic
formation problem through a stable Issue Code, one primary Model Location, an
ordered sequence of related Model Locations, and a human message. The primary
location is the tooling focus; related locations retain semantic order for
facts such as an ancestor declaration or containment cycle. Message text is
excluded from issue equality and canonical ordering. The foundational resolver
and every Model Formation Rule Set emit the same value;
`MetamodelValidationError` aggregates it without translation. Every issue is
fatal to formation, so the value has no severity.
_Avoid_: resolution issue, module-specific issue record, exception per rule

**Formation Contract Error**:
A coded runtime error indicating a defect in the assembled Formation Profile,
a Rule Set's declared or emitted Issue Codes, canonical issue uniqueness,
facet assembly, or an unexpected resolver, Rule Set, or compiler failure—not
invalid application metadata. It names the contributing module when one owns
the defect and preserves the original implementation exception as its cause.
_Avoid_: validation issue, invalid model, assertion failure, swallowed compiler error

**Issue Code**:
A stable, nonempty kebab-case machine token owned by the semantic module whose
rule it identifies. It starts with that module's canonical catalog stem—for
example `m-inheritance` owns `inheritance-*`—and appears in its Model Formation
Rule Set's complete declared code set. The vocabulary is open across
contributing modules rather than one centrally closed enum.
_Avoid_: issue enum ordinal, exception class, message-derived code

**Model Location**:
A representation-independent, semantic location used by a Metamodel Issue. It
identifies the model root or one Entity, Attribute, Relationship, Value Object,
Value Object Attribute, Index, or As-Of Axis declaration through structured
core identities. It never embeds a descriptor path, Python class name, source
span, or arbitrary metadata-property string; frontends may map it to their own
source coordinates separately.
_Avoid_: JSON Pointer, Python qualified name, source location, property path

**Canonical Issue Order**:
The deterministic location-first ordering of Metamodel Issues. Model Root sorts
first; all other locations group by canonical Entity Identity, then by semantic
location kind and its identity components. Issue Code and the ordered related
locations break ties. Messages and contributor execution order never affect
the result.
_Avoid_: rule order, discovery order, message order, frontend order

**Metamodel Lookup Error**:
A coded language-level error raised when a developer-facing metadata lookup
cannot resolve its requested Entity. The class-free Metamodel Lookup protocol
itself returns absence instead of raising this error.
_Avoid_: core lookup exception, missing-key message, validation issue
