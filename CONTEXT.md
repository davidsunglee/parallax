# Parallax

Parallax defines a language-neutral object-relational mapping contract and lets each language provide an idiomatic API that conforms to that contract.

## Core Glossary

### Model And Runtime Surface

**Descriptor**:
A canonical YAML or JSON document that describes part of a Parallax domain model and serves as generator input.
_Avoid_: spec, generated model

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
The non-instantiable, tableless entity that names an inheritance family, owns the family strategy and its temporal as-of axes (a family is either entirely non-temporal or entirely temporal), and carries attributes common to every descendant concrete subtype.
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
An identity-free composite value owned by an entity and read or written as part of that owning entity.
_Avoid_: embedded entity, component object, relationship target

**Structured Column**:
The single persisted storage position for a value object, carrying the whole composite value as one structured value.
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
A mapped entity whose rows represent links between entity identities, usually backed by an association table. It may be exposed directly for explicit writes and link attributes, while a many-to-many relationship can navigate through it without making callers name it for ordinary reads.
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
The Parallax-level strategy that supplies processing instants for transactions.
_Avoid_: per-transaction timestamp override, operation timestamp override

### Temporal And Milestoning

**As-Of Axis**:
A temporal dimension a milestoned entity is read and written along: `processing` records when the system knew a fact, `business` records when a fact was true in the world. A unitemporal entity declares one; a bitemporal entity declares both.
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
The current wall-clock instant. It coincides with **Latest** on the processing axis (milestones there are never future-dated) but not necessarily on the business axis, where a future-effective milestone can make the latest version differ from the version effective at the current instant.
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
