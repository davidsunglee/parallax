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
The explicit entry point for reads, writes, and managed object graph mutation inside a transaction.
_Avoid_: transaction client, ambient transaction, hidden unit of work

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

**Includes**:
The query option that requests eager relationship loading for a `find`.
_Avoid_: deepFetch, populate

**Include Path**:
A relationship path listed in `includes`; longer paths imply any intermediate relationship paths needed to load them.
_Avoid_: include tree, populate path

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

**Managed Object Graph Mutation**:
A change made through a managed domain object or one of its relationship references.
_Avoid_: object write, direct persistence

**Identity Cache**:
A Parallax cache scope that interns managed objects so the same database identity resolves to the same logical object within that scope.
_Avoid_: global object store, equality cache

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
A plain JSON-serializable representation of a domain object graph, detached from Parallax relationship references and runtime state.
_Avoid_: POJO, DTO

**Serialization Shape**:
The declared JSON form used to convert managed domain objects into domain snapshots, expressed in terms of selected attributes and relationships.
_Avoid_: JSON mapper, object dump

**Create Payload**:
A plain input object accepted by a create operation to construct and persist a new managed domain object.
_Avoid_: unmanaged entity, insert entity

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
