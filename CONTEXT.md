# Parallax

Parallax defines a language-neutral object-relational mapping contract and lets each language provide an idiomatic API that conforms to that contract.

## Language

**Entity Symbol**:
A generated TypeScript API object for a mapped entity, exposing typed attributes, relationships, and entity-level operations.
_Avoid_: model singleton, finder class

**Descriptor**:
A canonical YAML or JSON document that describes part of a Parallax domain model and serves as generator input.
_Avoid_: spec, generated model

**Parallax Handle**:
The configured application-side entry point for Parallax reads and for opening transactions.
_Avoid_: client, database connection, global session, ambient context

**Parallax Error**:
A package-owned public error class with a stable machine-readable code and an exported name carrying the `Parallax` prefix.
_Avoid_: generic error name, message-only failure, Px error

**Validation Issue**:
One structured problem inside a `ParallaxValidationError`, including enough path and code information for tools and users to locate the invalid input.
_Avoid_: validation message string, first error

**Parallax Transaction**:
The explicit TypeScript entry point for reads, writes, and managed object graph mutation inside a transaction.
_Avoid_: transaction client, ambient transaction, hidden unit of work

**Clock Strategy**:
The Parallax-level strategy that supplies processing instants for transactions.
_Avoid_: per-transaction timestamp override, operation timestamp override

**Managed Object Graph Mutation**:
A change made through a managed domain object or one of its relationship references.
_Avoid_: object write, direct persistence

**Predicate**:
A typed expression that describes which rows or objects an entity operation targets.
_Avoid_: where object, filter object

**Assignment**:
A typed expression that describes a value change for one mapped attribute in a set-based update.
_Avoid_: setter call, update object

**Sort Key**:
A typed expression that describes attribute-based ordering for a query result.
_Avoid_: JavaScript comparator, order callback

**ParallaxList**:
An async, operation-backed result collection returned by `find`; it may resolve to zero, one, or many objects.
_Avoid_: array, result array

**Identity Cache**:
A Parallax cache scope that interns managed objects so the same database identity resolves to the same logical object within that scope.
_Avoid_: global object store, equality cache

**Optimistic Lock Conflict**:
A detected write conflict where a versioned update affected no rows because another transaction advanced the version first.
_Avoid_: transient failure, automatic retry

**Includes**:
The query option that requests eager relationship loading for a `find`.
_Avoid_: deepFetch, populate

**Include Path**:
A generated relationship path listed in `includes`; longer paths imply any intermediate relationship paths needed to load them.
_Avoid_: include tree, populate path

**Relationship Collection**:
A managed collection reached through an object relationship, with enough ownership and join metadata to add or remove related objects.
_Avoid_: array property, child list

**To-One Relationship**:
A relationship whose navigation reaches at most one related object and may be used for direct predicate path navigation.
_Avoid_: scalar relationship

**To-Many Relationship**:
A relationship whose navigation can reach multiple related objects and must use an explicit quantifier in predicates.
_Avoid_: collection relationship

**Dependent Relationship**:
A relationship whose target is owned by the source and participates in dependent delete or terminate behavior.
_Avoid_: cascade-only relationship, child relationship

**Association Relationship**:
A non-dependent relationship whose mutation changes an association, foreign key, or join row without creating or deleting the related object.
_Avoid_: owned relationship

**Set-Based Write**:
An update or delete expressed over a predicate or an unresolved `ParallaxList`, intended to operate on the matching set rather than by materializing each object.
_Avoid_: mass operation, list setter

**Domain Snapshot**:
A plain JSON-serializable representation of a domain object graph, detached from Parallax relationship references and runtime state.
_Avoid_: POJO, DTO

**Create Payload**:
A plain input object accepted by a create operation to construct and persist a new managed domain object.
_Avoid_: unmanaged entity, insert entity

**Entity Input**:
A generated TypeScript type and validation namespace, such as `OrderInput`, for validating unknown input as a create payload without creating a managed object or opening a transaction.
_Avoid_: detached object parser, snapshot parser, create namespace

**Projection**:
A future plain-data query shape that retrieves selected attribute paths, grouped aggregate values, or both rather than managed domain objects.
_Avoid_: partial entity, selected entity, aggregate entity

**Aggregate Query**:
A projection query that groups rows and returns aggregate values in plain data.
_Avoid_: aggregate find, grouped entity

**Serialization Shape**:
The declared JSON form used to convert managed domain objects into domain snapshots, expressed in terms of selected attributes and relationships.
_Avoid_: JSON mapper, object dump

**Domain Function**:
An application-owned TypeScript function that implements domain behavior over generated domain objects, snapshots, `Parallax`, or `ParallaxTransaction`.
_Avoid_: custom generated-object method, entity subclass
