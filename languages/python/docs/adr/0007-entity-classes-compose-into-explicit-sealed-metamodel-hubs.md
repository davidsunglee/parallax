# Entity Classes compose into explicit sealed Metamodel Hubs

Python Entity Class headers declare their mapping facts but do not enroll the
class in a model or mutate shared state. A class-backed `MetamodelHub` receives
its complete Entity Class set in one constructor call, and an explicit
`seal()` submits an Unresolved Metamodel to the shared resolution, validation,
and compilation gates, freezes the accepted Metamodel, and binds every class
atomically. The hub does not implement those rules. Entity Classes are always
frozen; typed class-header keywords replace `EntityConfig`, `__parallax__`,
and the redundant Pydantic `frozen=True` option.

The internal declaration direction is shared and acyclic. A lower-level
`entity._declaration` engine owns the common Pydantic metaclass machinery,
typed header and annotation parsing, `Attr`/`Rel` extraction, immutable
declaration payloads, and private Entity-versus-Value-Object kind markers.
Both concrete frontends depend on that engine; it imports neither of them and
classifies no type through a registry or registered callback. It also imports
no hub, expression/query behavior, graph state, or row/provenance code. The
Value Object frontend therefore does not maintain a second annotation parser.

The runtime member seam is separate from the operation algebra.
`entity._members` owns the public `Attr`/`Rel` annotations, `attr`/`rel`
declaration values, and the installed class/instance descriptors; it is the
only runtime module in this cluster that touches owner classes. Those
descriptors resolve the owner's binding and construct operation nodes using
explicit hub identity and structured member identities. `entity._expressions`
owns only immutable Attribute Expressions, Relationship Paths, Predicates,
Assignments, and Sort Keys. It performs no Python class lookup and imports no
member, Entity, query, or hub implementation. `entity._query` depends forward
on that class-free algebra, binding, and errors. No lazy back-import is used to
hide a cycle.

`entity._errors` is a strict leaf within the Entity implementation cluster. It
imports only the standard library and class-free core identity/issue values,
and it imports no hub, binding, declaration, member, expression, query, row,
graph-state, Entity, or Value Object implementation. Callers pass structured
error data; exception values do not retain those concrete implementation
objects or callbacks. Every Entity module can consequently depend on errors
without creating a return edge.

The class-backed constructor validates its arguments left-to-right before a
hub exists. No arguments raises
`MetamodelDefinitionError(code="metamodel-empty")` without an argument index.
An Entity instance, ordinary class, Value Object class, or framework root
(`Entity`, `TxTemporal`, or `Bitemporal`) raises
`MetamodelDefinitionError(code="metamodel-invalid-entity-class")`; repeating
the same class object raises
`MetamodelDefinitionError(code="metamodel-duplicate-entity-class")`. Both
identify the zero-based argument index. Distinct classes that declare the same
Entity Identity are instead valid source inputs whose conflict is aggregated
during whole-model sealing. Descriptor-backed construction likewise rejects an
empty Entity source during schema parsing, so every Unresolved Metamodel is
nonempty before formation.

Descriptor-backed construction separates representation failures from model
semantics. Invalid JSON/YAML raises
`DescriptorSyntaxError(code="descriptor-invalid-syntax")` with format,
optional one-based source coordinates, and parser cause. A decoded document
outside the canonical schema raises
`DescriptorSchemaError(code="descriptor-schema-invalid")` with immutable
canonically ordered violations containing structured document paths and stable
schema-rule names. A schema-valid document whose denoted core value is
unconstructible — an out-of-bounds or non-canonical decimal type spelling —
raises `DescriptorValueError(code="descriptor-value-invalid")` with the same
canonically ordered document-path violation shape over the value-rule
vocabulary `m-descriptor` owns. All three share the public
`DescriptorError(ValueError)` base and
occur before a hub exists. Only input every ingestion phase accepts reaches
an `UNSEALED` hub;
all reference and semantic failures then use `MetamodelValidationError` and
semantic Model Locations during sealing.

Every sealed hub supports pure canonical export without renewed validation.
Repeated descriptor documents are structurally equal, and repeated JSON/YAML
results are byte-identical. Sealing does not eagerly export or retain a mirrored
descriptor graph. An unexpected conversion or serialization defect raises
`DescriptorExportError(code="descriptor-export-failed")` with target
`document`, `json`, or `yaml` and the original cause, returns no partial output,
and leaves the hub `SEALED`; export from any other hub state raises
`MetamodelStateError`.

Invalid declarations produce `MetamodelValidationError` with canonical core
issues. A defective Formation Profile, undeclared or duplicate issue identity,
facet assembly defect, or compiler exception instead produces the coded
top-level `FormationContractError`, preserving the contributing module and
compiler cause when applicable. Neither failure publishes facets, accepts the
Metamodel, or installs an Entity Class binding.

Sealing is a synchronized single-flight `UNSEALED -> SEALED | REJECTED`
transition. Concurrent callers wait for the owning attempt and observe its
terminal outcome; successful resealing is an idempotent no-op, while rejected
resealing reproduces the terminal failure. `SEALING` is internal: ordinary hub
operations still fail as unsealed, and owning-thread re-entry fails immediately
with coded `MetamodelStateError` instead of deadlocking. The accepted
Metamodel, complete facet set, and all Entity Class bindings become visible
together only at `SEALED`.

Only `seal()` participates in single-flight waiting. During `UNSEALED` and the
internal `SEALING` phase, Entity enumeration, metadata/export, facet access,
query/path construction, resolver/codec access, connection, and execution fail
immediately as `MetamodelStateError(code="metamodel-unsealed")`. In `REJECTED`
they fail as `metamodel-rejected` with the terminal seal failure as cause;
calling `seal()` itself reproduces that failure. In `SEALED` they are available
and every successful or idempotent `seal()` returns `None`. Direct expression
use of an unbound Entity Class raises `metamodel-class-not-bound`.

Ordinary frozen concrete Entity construction is the sole pre-binding exception
because it reads no model facts and creates no binding. Such a value cannot be
queried or persisted until its class is permanently bound; abstract-role
instantiation remains forbidden by the declaration itself.

After language-neutral formation succeeds, one synchronized realization phase
checks the complete Entity Class set before installing any binding. A class
already claimed by another sealed hub is process-dependent state, so the
losing hub raises
`MetamodelStateError(code="metamodel-class-already-bound")`, reports every
conflicting Entity Identity in canonical order, installs nothing, and becomes
`REJECTED`; it is not a metadata-validation or formation-contract failure.
Racing hubs that share any class therefore have exactly one winner.

A successful binding is permanent for that Entity Class object's lifetime and
keeps its immutable sealed hub reachable. There is no supported unbind, hub
close, reset hook, or weak-reference expiry: the same class can never acquire
different metadata semantics later. Reload and test-isolation scenarios that
need another model use fresh class objects.

One immutable **Metamodel Binding** is created per successfully sealed
class-backed hub. It contains the opaque exact-hub identity, a reference to the
one accepted Metamodel, and the immutable bidirectional Entity Identity to
Entity Class index. The binding implementation separately retains the
concrete hub as a private strong owner reference required by the lifetime
guarantee. Every claimed class points to this same Metamodel Binding, so no
metadata is copied per class.

Runtime consumers receive the Metamodel Binding, never hub construction,
sealing, export, connection, or other lifecycle operations. An **Entity Class
Binding** is only one class-to-Entity-Identity association within it, not a
second metadata implementation or necessarily another concrete value type.
Descriptor-backed hubs have neither kind of Python binding. Consequently
`_hub` depends on `_binding`, while `_binding` neither imports nor exposes the
concrete hub type.

Before resolution, the class-backed hub supplies only an enumeration-only
Unresolved Metamodel view over the fixed Entity Class tuple. It does not build
a duplicate metadata-record graph or define lookup over potentially duplicate
identities. Successful resolution creates the canonical indexed Candidate
Metamodel of identity-resolved declarations; only successful owner compilation
creates final Entity Metadata, adds facets, and produces the separate Metamodel
used for binding and behavior. Specifically, the one `m-metamodel` Metadata Compiler
creates immutable Compiled Metadata after every Rule Set succeeds; semantic
Model Compilers add one typed facet each. The runner combines them without a
mutable class-metadata draft, partial patches, or another copied metadata graph.

Each Entity Class directly implements the shallow
`UnresolvedEntityDeclaration` interface.
Already normalized reference-free facts, including Attribute, As-Of Axis, and
Index Metadata, are reused directly; Relationship, Value Object occurrence,
and inheritance facts use small Declaration protocols until resolution. The
adapter does not mirror every Metadata type. Class constructor order is
non-semantic, while each class's member order remains authoritative.
Successful foundational resolution preserves the same shallow Entity shape as
`EntityDeclaration`: only Relationship and inheritance references
advance, the reusable Value Object declaration graph remains intact, and no
member lookup or behavioral capability appears before accepted Metadata. The
separately accepted Metamodel is the sole normalized runtime truth; bindings
only refer classes back to it, and descriptor-backed hubs have no bindings.

Temporality is selected by one of three framework roots: `Entity` for a
non-temporal model, `TxTemporal`, or `Bitemporal`. The temporal roots
are not hub candidates or domain inheritance positions. They supply the
standard statically visible, read-only Timestamp attributes and default column
mappings, so ordinary declarations repeat no axes, types, flags, or columns:

```python
class AuditEvent(TxTemporal, table="audit_event"):
    id: Attr[int] = attr(primary_key=True)


class Position(Bitemporal, table="position"):
    id: Attr[int] = attr(primary_key=True)
```

The normalized Metamodel nevertheless retains explicit start/end Attribute
Identities and Attribute Metadata Storage Locations. A future advanced
class-header override can therefore remap legacy columns without changing the
Metamodel Interface, behavioral modules, or the terse default form.

We rejected `hub=` enrollment in the class header because importing a module
would mutate a shared hub and force the Entity metaclass to depend on model
assembly. We rejected public `add()` and class-backed `build()` paths because
they permit incrementally different model sets and duplicate the constructor's
ownership. The resulting developer path is intentionally explicit:

```python
class Order(Entity, table="orders"):
    id: Attr[int] = attr(primary_key=True)


models = MetamodelHub(Order)
models.seal()
```

The declaration frontend compiles Python annotations and `attr(...)` options
directly into core semantic values. In particular, scalar types become
structured Neutral Types and primary-key allocation becomes
`ApplicationAssigned`, `Max`, or a fully resolved `Sequence`; descriptor type
and strategy strings never become the class-backed hub's internal contract.
The class-header `table=` value similarly normalizes to the core
`StorageContainer = Table(name)` value. Member Storage Locations never repeat
that container; the reserved future `DocumentCollection` variant adds no
current authoring or runtime behavior.
Persistence Mode is the separate `ReadWrite | ReadOnly` mapping capability.
Omission on a standalone Entity or family root normalizes to ReadWrite, the
ordinary ORM case; only an exceptional non-writable mapping spells
`persistence=ReadOnly`. Persistence Mode is family-wide and root-owned. A
descendant declaration is rejected even when it repeats the root; omission is
the only valid descendant form. Entity values remain frozen in either mode,
and the vocabulary is unrelated to security access or transaction semantics.
Read-only Metamodel Interface protocols retain the full `Metadata` suffix;
Python reserves `*Meta` for metaclasses and removes the old `EntityMeta` /
`EntityMetaView` introspection names.
Relationship declarations compile to core Relationship Identity and a
source/target Relationship Join. `Rel[T]` is the sole target declaration;
`rel(...)` supplies only source- and target-scoped attribute names. Accepted
metadata derives the target from the join, validates reverse names in that
scope, and exposes no redundant target or `foreign_key` option. The full
`*Identity` names remain distinct from instance primary-key IDs.
`rel(...)` admits direct one-to-one, many-to-one, and one-to-many cardinality
only. A many-to-many association is an explicit Entity with two relationships;
the frontend does not offer a shortcut that the core join and write models
cannot represent.
The frontend normalizes authored cardinality to core OneToOne, ManyToOne, or
OneToMany values. Each exposes source/target One-or-Many multiplicity; behavioral
code never receives the descriptor's hyphenated cardinality strings.
Bidirectional relationships have one defining declaration. The defining form of
`rel(...)` declares cardinality, a source/target attribute-name pair,
dependency, and optional ordering. The reverse form declares only
`reverse_of="name_on_target"` plus optional ordering; `Rel[T]` supplies its sole
target. Foundational resolution retains both forms with canonical identities.
The shared `m-relationship` Rule Set validates them and its Model Compiler
swaps the join, inverts cardinality, and links both directions in the symmetric
Relationship Facet. Repeating join, cardinality, dependency, or a second
target on the reverse form is a declaration error.
The class adapter exposes those forms as the shared unresolved union. The
defining form stores its sole target in
`UnresolvedRelationshipJoin.target.entity`; reverse stores its sole target in
`RelationshipReference.entity`. Ordering remains a target-local attribute name
until resolution. No Python-specific target, foreign-key, or reverse-name field
survives into the Unresolved Metamodel protocol.
`Rel[Customer]` becomes `ExactEntityReference(Customer's EntityIdentity)`, even
when Customer is unnamespaced. `Rel["Customer"]` becomes
`RelativeEntityReference("Customer")`; `Rel["crm.Customer"]` parses directly
to an Exact Entity Reference. The shared value stores no Python class, module
name, raw spelling, duplicated owner, or arbitrary global evaluation state.
Relationship ordering compiles to target Attribute Identity plus the shared
Ascending-or-Descending Sort Direction. An empty `order_by` emits no sort;
there is no Unspecified direction. If an authored term omits direction it
normalizes to Ascending, and ordering a to-one direction is rejected.
The class-free lookup protocol accepts structured identities or local member
names, returns ordinary absence, and uses immutable constant-time indexes.
Python's `models.meta(...)` convenience alone accepts Entity Classes and
canonical strings; failed lookups raise a stable-coded `MetamodelLookupError`
instead of returning null.
Index declarations compile to self-identifying Index Metadata containing a
nonempty ordered Attribute Identity sequence and uniqueness. They remain local,
are never inherited, and carry no duplicated column names.

Top-level and nested Value Object declarations compile to path-based core
Value Object Identity; inner scalar declarations compile to Value Object
Attribute Identity. Resolved nested expression paths carry those identities
rather than dotted strings. The identities describe declarations only and do
not give runtime Value Object values independent identity. Authors declare the
top-level occurrence's initial Column Storage Location but no `mapping="json"`;
structured-column storage is intrinsic and the dialect selects its concrete
JSON-like database type. The Value Object class itself remains storage-neutral.
When `column=` is omitted, an Entity scalar or top-level Value Object occurrence
normalizes to `Column(attribute_or_occurrence_name)`. Only a legacy or otherwise
nonconventional direct column requires `attr(column=...)`; accepted Metadata
always contains the explicit Storage Location. A future document-oriented
Entity follows the same authoring principle: one Entity-level document-column
choice plus ordinary member names derives structured `DocumentPath` values,
rather than requiring per-member or per-nested-path configuration. The reserved
future value is always
`DocumentPath(Column(document_column), nonempty_path_segments)` for a
relational document column or
`DocumentPath(ContainerDocument, nonempty_path_segments)` for a document
collection record; dotted strings and concatenation notation are not alternate
forms. A top-level Value Object occurrence would own the path to its root,
while full nested paths would be derived by extending that value with
structured member identities.
Single and collection annotations compile to the shared One-or-Many
Multiplicity; the frontend defines no separate Value Object Cardinality. A
Many annotation is a non-null `tuple[T, ...]` that may be empty. Optional
collection annotations are rejected; only a One Value Object may be nullable.
Python's ordinary class namespace enforces the same navigable-member rule as
core formation: Entity attributes, relationships, and top-level Value Objects
cannot share a name, nor can a Value Object scalar and nested Value Object.
The temporal framework bases reserve their standard temporal attribute names.
Sealing also rejects a domain descendant that shadows any ancestor navigable
member, including a cross-category or identical redeclaration. Separate sibling
branches may reuse a name.
Class creation rejects an empty top-level or nested Value Object declaration.
Each must contain at least one scalar or nested member; sealing retains the
core `value-object-empty` guard for representation-independent conformance.
One Value Object class may be reused at multiple Entity or nested paths; each
use compiles to a distinct path-identified occurrence. Direct and indirect
Value Object class-containment cycles are rejected as
`value-object-containment-cycle`; forward references never enable recursive
runtime shapes.

Internally, the class-backed formation input adapts each distinct Value Object
class declaration to one opaque formation-local Value Object Shape Key.
Repeated uses of that class reuse the key; structurally identical distinct
classes do not.
The key has no authoring, registration, lookup, ordering, export, or runtime
value surface. It exists only for core reuse/cycle validation and is discarded
when the Metadata Compiler expands path-identified occurrences.

A Value Object intended for one occurrence may be declared lexically inside
its owning Entity or Value Object and referenced by an ordinary `Attr[...]`
annotation. A shape used at multiple paths is an ordinary standalone Value
Object class referenced at each occurrence. Authors do not declare or register
shape keys, and neither inline nor standalone Value Object classes are passed
to `MetamodelHub`; the class-backed frontend reaches them only through the
explicit annotations of the hub's Entity Classes.

```python
class Customer(Entity, table="customer"):
    class Address(ValueObject):
        street: Attr[str]
        city: Attr[str]

    id: Attr[int] = attr(primary_key=True)
    address: Attr[Address]
```

```python
class Address(ValueObject):
    street: Attr[str]
    city: Attr[str]


class Customer(Entity, table="customer"):
    id: Attr[int] = attr(primary_key=True)
    billing_address: Attr[Address]
    shipping_address: Attr[Address]


class Supplier(Entity, table="supplier"):
    id: Attr[int] = attr(primary_key=True)
    address: Attr[Address]


models = MetamodelHub(Customer, Supplier)
models.seal()
```

Inheritance declarations and accepted metadata instantiate the same core
parent-parameterized union. Python class inheritance supplies an Entity
Reference parent, so Abstract and Concrete Subtype authoring does not repeat
it; resolution changes only that parent to Entity Identity. An Abstract Root
supplies either `TablePerHierarchy(tag_column=...)` or
`TablePerConcreteSubtype`; a Concrete Subtype supplies only its TPH
`tag_value` when required. The accepted variant is the role and carries no
redundant role string.

Snapshot graph state is not a common Entity-runtime abstraction. Graph-local
identity reuse, closed-world loaded/unloaded relationships, narrowed views,
whole-graph pins, and milestone edges belong to the Snapshot slice. The common
Entity cluster therefore has no generic `_graph_state` module. A future
managed-object slice owns its distinct transaction-scoped Identity Map,
operation-backed relationship resolution, mutation, deletion, and detachment
state instead of extending Snapshot state. The two surfaces share only the
lower-level deep-fetch behavior, Relationship Identities, narrowed-view keys,
and temporal coordinates defined by their core semantic owners.

A sealed class-backed hub supplies one deep Entity Graph Construction
capability rather than a standalone Entity Class Resolver or Snapshot-specific
materializer. Snapshot owns its Graph Materializer and calls
`EntityGraphConstruction.construct(build)` with an explicit build function for
each graph. The function receives a callback-scoped Entity Graph Writer,
allocates every opaque Node Handle before population, populates each handle
exactly once with complete attributes, recursive Value Objects, broad
relationship values, and an optional deferred opaque lifecycle-state factory,
then returns the ordered root handles.
Relationship values may refer to handles from the same construction, so the
two phases close diamonds and cycles without publishing partial Entity graphs.
After structural population, Entity gives each state factory a read-only view
that resolves same-construction handles to final Entity instances, then stores
the returned opaque value without interpreting it.

Entity-detected misuse raises the advanced `GraphConstructionError` with a
stable `entity-graph-*` code, optional zero-based allocation index, optional
structured Entity or member identity, and optional conversion cause. The
complete conditions are invalid Entity, invalid member, allocation after the
first population, retained writer/resolution use after its scope, a foreign
handle in any position, duplicate population, missing population, a non-handle
root, and a value incompatible with accepted metadata. A local unpopulated
root is missing population rather than invalid root, and the first missing
node is deterministic by allocation order. These are runtime contract errors,
never assertions.

An exception raised by the lifecycle build function or opaque-state factory is
owned by that lifecycle and propagates unchanged through Entity. Construction
still publishes no graph. Snapshot may classify such failures only at its own
public read boundary.

Accordingly, once adapter execution and neutral graph production have
succeeded, the Snapshot Graph Materializer translates an escaping Graph
Construction, build-function, or state-factory exception to exported
`SnapshotMaterializationError(code="snapshot-materialization-failed",
cause=original)` with normal Python exception chaining. It publishes no partial
Snapshot or roots and does not double-wrap the same error. Query definition,
unsupported capability, transaction, adapter, SQL, and pre-materialization
neutral-decoding failures retain their own public classifications. Direct
advanced Entity Graph Construction callers continue to receive the original
exception.

Entity Graph Construction owns concrete class selection through the Metamodel
Binding, Pydantic allocation and population, canonical-to-Python member
mapping, recursive Value Object construction, private-state installation, and
atomic publication. Snapshot owns graph-local identity and projection merging,
loaded/unloaded and narrowed relationship decisions, whole-graph pins,
milestone edges, its private `SnapshotNodeState`, and its transient merge
index. The state contains narrowed views, pin, and optional edge; broad
relationship values remain structural Entity slots. Snapshot emits
construction operations directly through the writer; no second whole-graph
`EntityGraphPlan` crosses the seam. The separate Entity Row Codec remains the
write-side capability.

The Snapshot materializer accepts an already-associated structured Snapshot
Graph Input, not raw row batches or a fetch plan. Its ordered roots reference
neutral nodes
whose concrete Entity, attributes, Value Object occurrences, and broad or
narrowed relationship views use structured core identities and Neutral Values.
Node references may be shared or cyclic, and separate input nodes may carry
different projections of one logical identity. A missing relationship-view
key means unloaded; present null and empty values mean loaded-null and
loaded-empty. The Snapshot materializer treats the input as read-only, merges
logical projections under the graph pin, preserves root and to-many order, and
drives the Entity Graph Writer. Snapshot execution remains responsible for SQL
and row-to-view association. No descriptor record, column/wire name, Pydantic
value, or private slot name crosses the seam.

The build function is passed explicitly per construction. There is no global
or lifecycle-keyed callback registry, import-time enrollment, discovery, or
mutable callback table. A future Managed Object materializer can use the same
Entity Graph Construction capability with its own build function while
coexisting with Snapshot and without either lifecycle importing the other.

Entity stores exactly one opaque lifecycle-state value per constructed node;
there is no keyed extension bag or common lifecycle state protocol. Snapshot
reads that value and broad relationship slots only through the advanced Entity
collaboration functions `lifecycle_state_of` and `relationship_value_of`.
`is_loaded`, `narrowed`, `pin_of`, and `edge_of` therefore belong to
`parallax.snapshot`, while the `Pin` and `Edge` value types remain in their
core semantic owner. Snapshot inspection rejects a plain or differently
lifecycled Entity instead of interpreting another package's state. A future
Managed Object materializer supplies its own deferred state factory and opaque
state type.

Every Snapshot inspection function first requires that opaque value to be
`SnapshotNodeState`. A plain Entity, future Managed Entity, or other lifecycle
raises exported `SnapshotInspectionError(code="snapshot-node-required",
operation=<function name>)` before path, relationship, or temporal validation,
without exposing the opaque value. `is_loaded` therefore never returns `False`
for a non-Snapshot node. Once the lifecycle precondition succeeds, ordinary
Snapshot semantics remain distinct: `is_loaded` is boolean, an unrequested
narrowed view raises `UnloadedRelationshipError`, and unavailable node temporal
state raises Snapshot-owned inspection errors. On a valid Snapshot node,
`pin_of` without pin state raises
`SnapshotInspectionError(code="snapshot-pin-unavailable",
operation="pin_of")`; `edge_of` without edge state raises
`SnapshotInspectionError(code="snapshot-edge-unavailable",
operation="edge_of")`. Both carry the node's Entity Identity without exposing
private state. Core `TemporalReadError` remains for temporal query/lowering,
and `UndeclaredAxisError` remains for requesting an axis absent from a valid
`Pin` or `Edge`.

Broad relationship descriptor access and `narrowed(...)` share the identical
structured `UnloadedRelationshipError(code="entity-relationship-unloaded",
view=Broad(RelationshipIdentity) | Narrowed(RelationshipIdentity,
canonical effective concrete set))`. Entity's error leaf defines it so the
descriptor never imports Snapshot. The advanced `parallax.core.entity` seam
exposes it and `parallax.snapshot` re-exports that same class for ordinary
callers; top-level `parallax.core` does not. For a valid Snapshot node,
`is_loaded` remains the nonthrowing preflight operation.

Before sealing, ordinary frozen values may be constructed, but model-dependent
operations such as queries, metadata lookup and export, and database-handle
binding fail. An Entity Class belongs permanently to at most one sealed hub
for that class object's lifetime. Each Find Query carries that hub's identity,
every database handle is permanently paired with the same sealed hub, and
cross-hub execution is rejected before adapter or SQL work. There is no
default or parent registry, ambient lookup, class-list scope inference, public
incremental registration API, or unbind/reset path; descriptor-backed hubs use
a separate fixed-source factory and do not create Entity Class bindings.

Every Attribute Expression, Relationship Path including narrowing, Predicate,
Assignment, Sort Key, and Find Query carries the opaque exact hub identity.
Neutral literal and assignment values are untagged until incorporated into a
tagged expression. Every composed operation checks its children immediately;
mixed hubs raise `QueryDefinitionError(code="query-hub-mismatch")` before a
Database, Transaction, SQL generator, or adapter observes the value.

`QueryDefinitionError` represents only intrinsically invalid operation shapes
or combinations. After query and identical-hub validation, a handle compares
the operation's required canonical core feature tags with the connected
provider's captured capability set. A missing capability raises top-level
`UnsupportedCapabilityError(code="capability-unsupported",
capability=<core feature tag>)` before SQL or adapter access. Thus the valid
staged `snapshot-history-includes` composition is never misclassified as an
invalid query merely because one adapter has not implemented it.

Predicate-selected writes introduce no public mutation-query type. All five
`_where` verbs accept the ordinary `FindQuery[T]` from `Entity.where(...)`, but
only its mutation-compatible form containing target, predicate, and hub. Any
include, order, limit, distinct, narrow, temporal read, history/range, or other
result-shaping clause raises
`QueryDefinitionError(code="query-not-mutation-compatible")`. The transaction
method privately normalizes the accepted value to an ephemeral
`PredicateSelection(target, predicate, hub_identity)` that is neither exported
nor serialized. Assignment-bearing verbs also require every Assignment to
carry the same hub and exact Entity target; mismatch raises
`QueryDefinitionError(code="query-assignment-target-mismatch")` before Unit of
Work buffering, SQL, or adapter access. Delete and terminate forms accept no
Assignments. Exact Transaction/Database hub identity is checked after
composition; structural metadata equality is never sufficient.

The outermost `Database.transact(...)` demarcation also stores a strong
reference to its exact originating Database object. A nested call joins only
through that same object (`requested_database is active_owner`); an alias joins
and receives the identical Transaction, while every different handle fails
even if it carries the same hub, adapter, dialect, clock, or equivalent
configuration. A mismatch raises exported
`TransactionOwnershipError(code="transaction-owner-mismatch")` before option
comparison, rollback-only joining, closure execution, Unit of Work mutation,
SQL, or adapter access and retains neither handle. After exact-owner success,
existing rollback-only, option-conflict, same-Transaction, and outermost-only
commit/abort/retry semantics remain unchanged. The demarcation owner is scoped
state, not a Database, hub, or adapter registry.

Entity actively overrides Pydantic's inherited `model_copy(...)`. Every call,
with or without `update=`, raises `EditError(code="edit-use-edit")` and creates
no value. `edit(...)` is the only authored copy-with-changes path and the only
one that creates an Edited Copy with a Change Record.
