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
Indexes are never inherited and contain no duplicated column names.
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
Type, Storage Location, a Not-Primary-Key or Primary-Key state (the latter owns
Primary-Key Generation), normalized flags, and Attribute Default; it never
contains inherited context or descriptor spellings.
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
null only through its own contract, such as a nullable member or
`DefaultValue(null)`. Languages represent these idiomatically while preserving
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

**Attribute Default**:
The declared default state of an attribute: either No Default or a Default
Value, which may itself be null. Absence and an explicitly declared null are
different states.
_Avoid_: optional value, nullable default, unset sentinel

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
is persisted beneath its top-level occurrence and has no Storage Location of
its own.
_Avoid_: stored value object, nested entity, child column

**Value Object Containment**:
The acyclic declaration relationship by which an Entity or Value Object
contains a Value Object occurrence. A reusable Value Object type may appear at
multiple paths, but direct or indirect containment cycles are invalid.
_Avoid_: recursive Value Object type, cyclic JSON shape, shared occurrence

**Value Object Multiplicity**:
The shared Multiplicity of a contained Value Object: One for a single embedded
object or Many for an ordered collection at the same top-level Storage
Location. It reuses `Multiplicity = One | Many` rather than defining Value
Object cardinality. A Many Value Object is always non-null; its empty ordered
collection is the sole representation of no contained values.
_Avoid_: Value Object cardinality, collection flag, relationship cardinality

**Storage Location**:
The normalized physical location of a mapped top-level Entity member,
independent of that member's model identity. The initial form is a named
Column; nested Value Object members have no Storage Location of their own.
_Avoid_: column property, storage binding, member identity

**Storage Container**:
The Entity-level physical container that holds its stored instances, declared
once rather than repeated by member Storage Locations. The initial form is a
Table; a future Document Collection is a different container form.
_Avoid_: repeated table mapping, member location, database

**Document Path**:
The structured pair of a Document Root and a nonempty ordered sequence of
member-name segments locating a value inside that document. The root is either
a document-bearing Column or the container record itself; a nested Value Object
member's full Document Path may be derived without giving that member an
independently owned Storage Location.
_Avoid_: dotted path, JSON Pointer, column-plus-path concatenation

**Document Collection**:
A Storage Container whose stored records are themselves structured documents.
Parallax applies one Metamodel shape to every document in the collection.
_Avoid_: schemaless Entity, table, document column

**Structured Column**:
A Column Storage Location carrying one whole top-level Value Object occurrence
as a structured value. The dialect selects its concrete JSON-like database
type; the model declares no constant mapping discriminator.
_Avoid_: flattened columns, JSON blob

### Expressions And Reads

**Predicate**:
A typed expression that describes which rows or objects an entity operation targets.
_Avoid_: where object, filter object

**Assignment**:
A typed expression that describes a value change for one mapped attribute in a set-based update.
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

**Optimistic Lock Conflict**:
A detected write conflict where a versioned update affected no rows because another transaction advanced the version first.
_Avoid_: transient failure, automatic retry

**Clock Strategy**:
The Parallax-level strategy that supplies Transaction Time instants for
transactions.
_Avoid_: per-transaction timestamp override, operation timestamp override

### Temporal And Milestoning

Prior art: the Valid Time and Transaction Time terms follow Richard
Snodgrass's standard bitemporal vocabulary; Reladomo's business/processing
dates are the same dimensions under retired names.

**Temporal Dimension**:
One of the two orthogonal temporal meanings recognized by Parallax: Valid Time
or Transaction Time. The dimension itself identifies an entity's As-Of Axis;
an axis has no independently authored name.
_Avoid_: axis name, axis kind, business/processing dimension

**Valid Time**:
The Temporal Dimension describing when a fact is true in the modeled world.
Its canonical interval attributes are `valid_start` and `valid_end`, mapped by
default to `from_z` and `thru_z`.
_Avoid_: business time, business date, effective date

**Transaction Time**:
The Temporal Dimension describing when a fact is present in the database. Its
canonical interval attributes are `tx_start` and `tx_end`, mapped by default
to `in_z` and `out_z`.
_Avoid_: processing time, processing date, system date

**As-Of Axis**:
A Temporal Dimension along which a milestoned entity is read and written. Its
metadata identifies inclusive start and exclusive end attributes; the
dimension itself is the axis identity. A Transaction-Time-Only entity declares
Transaction Time; a Bitemporal entity declares both Valid Time and Transaction
Time.
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
