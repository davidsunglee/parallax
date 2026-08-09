# Entity Classes compose into explicit sealed Metamodel Hubs

> **Amended 2026-08 by COR-64 — the Metamodel Hub is now the Domain Model.** The
> decision this ADR records — that Entity Class headers declare mapping facts
> and enroll nothing, and that one constructor call composes a complete class
> set through the shared formation gates or raises — stands unchanged. What
> COR-64 retired is the *identity* half built on top of it: the permanent
> one-model-per-class claim, the `MetamodelBinding` that published it, the
> opaque exact-hub identity every query value carried, and the ownership
> refusals stated in terms of it. The body below has been reconciled with what
> landed; the closing "Amendment (2026-08)" section records what was retired,
> what replaced it, and why, so the superseded design is auditable rather than
> merely absent.

Python Entity Class headers declare their mapping facts but do not enroll the
class in a model or mutate shared state. A class-backed `DomainModel` receives
its complete Entity Class set in one constructor call, and that call is
construct-or-raise: it submits an Unresolved Metamodel to the shared resolution,
validation, and compilation gates and freezes the accepted Metamodel before
returning. The model does not implement those rules. Entity
Classes are always frozen; typed class-header keywords replace `EntityConfig`,
`__parallax__`, and the redundant Pydantic `frozen=True` option.

The internal declaration direction is shared and acyclic. A lower-level
`entity._declaration` engine owns the common Pydantic metaclass machinery,
typed header and annotation parsing, `Attr`/`Rel` extraction, immutable
declaration payloads, and private Entity-versus-Value-Object kind markers.
Both concrete frontends depend on that engine; it imports neither of them and
classifies no type through a registry or registered callback. It also imports
no model, expression/query behavior, graph state, or row/provenance code. The
Value Object frontend therefore does not maintain a second annotation parser.

The runtime member seam is separate from the operation algebra.
`entity._members` owns the public `Attr`/`Rel` annotations, `attr`/`rel`
declaration values, and the installed class/instance descriptors; it is the
only runtime module in this cluster that touches owner classes. Those
descriptors carry the declaration's own facts — the member's Metadata and its
structured identity — into the nodes they seed, and reach no model to do it.
`entity._expressions`
owns only immutable Attribute Expressions, Relationship Paths, Predicates,
Assignments, and Sort Keys. It performs no Python class lookup and imports no
member, Entity, query, or model implementation; its enforcement scope grants
`m-metamodel` and `m-op-algebra` alone. `entity._query` depends forward
on that class-free algebra and on errors. No lazy back-import is used to
hide a cycle.

`FindQuery[E, S]` retains its independently authored, already validated clauses
as private authoring state so method-call order does not become canonical
operation order. `E` is the Entity queried and `S` the Entity the result
returns, which `narrow` and only `narrow` moves; the split is what lets
`include` measure a path's source against the queried position while
`order_by` measures a Sort Key against the returned one. The advanced
first-party `lower_find_query` seam performs the
total frontend-to-operation transformation and returns a `LoweredFindQuery`
containing only a structured target Entity Identity and one
canonical Operation. It exposes no model, Entity Class, class index, Snapshot
feature classification, SQL, serialization, or developer-facing inspection
surface. It is deliberately not named `CanonicalFindQuery`: only the Operation
is canonical, while the target is a position the connected model resolves at
execution. Lowering is recomputed
once per execution and retained only for that execution; the Find Query and
global runtime carry no memoized lowering.

`entity._errors` is a strict leaf within the Entity implementation cluster. It
imports only the standard library and class-free core identity/issue values,
and it imports no model, declaration, member, expression, query, row,
graph-state, Entity, or Value Object implementation. Callers pass structured
error data; exception values do not retain those concrete implementation
objects or callbacks. Every Entity module can consequently depend on errors
without creating a return edge.

The class-backed constructor validates its arguments left-to-right before a
model exists. No arguments raises
`MetamodelDefinitionError(code="metamodel-empty")` without an argument index.
An Entity instance, ordinary class, Value Object class, or framework root
(`Entity`, `TxTemporal`, or `Bitemporal`) raises
`MetamodelDefinitionError(code="metamodel-invalid-entity-class")`; repeating
the same class object raises
`MetamodelDefinitionError(code="metamodel-duplicate-entity-class")`. Both
identify the zero-based argument index. Distinct classes that declare the same
Entity Identity are instead valid source inputs whose conflict is aggregated
during whole-model formation. Descriptor-backed construction likewise rejects an
empty Entity source during schema parsing, so every Unresolved Metamodel is
nonempty before formation.

The separately installable Descriptor Frontend creates descriptor-backed models
through the Domain Model's private first-party Unresolved-source seam and separates
representation failures from model semantics. Invalid JSON/YAML raises
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
occur before a model exists. Only input every ingestion phase accepts reaches model
construction; all reference and semantic failures then use
`MetamodelValidationError` and semantic Model Locations, raised from the same
ingestion call. An ingestion function therefore raises both families, in that
fixed phase order, rather than deferring model semantics to a second call.

The Descriptor Frontend can canonically export every Domain Model without renewed
validation. Repeated descriptor documents are structurally equal, and repeated
JSON/YAML results are byte-identical. The model exposes no descriptor method, and
construction does not eagerly export or retain a mirrored descriptor graph. An
unexpected conversion or serialization defect raises
`DescriptorExportError(code="descriptor-export-failed")` with target
`document`, `json`, or `yaml` and the original cause, returns no partial output,
and leaves the model unchanged. A model exists only accepted, so the exporters have
no model state to check.

Invalid declarations produce `MetamodelValidationError` with canonical core
issues. A defective Formation Profile, undeclared or duplicate issue identity,
facet assembly defect, or compiler exception instead produces the coded
top-level `FormationContractError`, preserving the contributing module and
compiler cause when applicable. Neither failure publishes facets nor accepts the
Metamodel.

Acceptance happens in the constructor. `DomainModel(*classes)` and the private
`_from_unresolved(source)` seam each return a fully accepted model or raise, so
there is no `seal()` operation and no unsealed, sealing, or rejected state.
Nothing a construction builds is reachable while it runs — a model becomes
observable when its constructor returns; a failure
anywhere raises out of the constructor, letting no model object escape and
leaving no published facet. A corrected model
is a new constructor call, so nothing is retried, resealed, or interrogated for
a stored terminal cause.

Because a model exists only accepted, every model-dependent operation — Entity
enumeration, metadata/export, facet access, connection, and execution — is
available on every model a
caller can name, and none performs a lifecycle check. There is no model state
to misuse and therefore no state-error family: construction has no
synchronization point at all, so two constructor calls over any shared class
are two independent, equally authoritative models.

Query and path construction is deliberately not on that list. Authoring reaches
no model, so class-level expression use needs no model to have accepted the
class first; an ordinary frozen concrete Entity value is likewise constructible
from a class no model composed, because it reads no model facts. What such a
value cannot do is execute: a Database refuses a query whose target its
connected model does not declare, by name and before any I/O. Abstract-role
instantiation remains forbidden by the declaration itself.

We rejected an explicit `seal()` with an observable `UNSEALED -> SEALED |
REJECTED` state machine. Its unsealed state had no capabilities, so the type's
first state could do nothing but be forgotten, and preserving it would have cost
an idempotent-reseal rule, a stored terminal failure to reproduce, waiting
callers, and owning-thread re-entry detection for a phase boundary nothing
needs. The one real cost of accepting in the constructor is that the Descriptor
Frontend's ingestion functions now raise `MetamodelValidationError` as well as
`DescriptorError`, so the public API no longer separates representation failure
from model failure by call site.

After language-neutral formation succeeds, a class-backed model builds one
immutable **Class Index**: the bidirectional association between accepted Entity
Identities and the Python Entity Classes that realize them, reachable only
through a private first-party seam and carrying no identity of its own. A
descriptor-backed model has none, which is precisely the difference a Snapshot
connection tests, because materializing Entity Class instances is what a class
index is for. An Entity Class appears in the index of every model that composed
it and in no other, so one class participates in any number of models and the
index is a lookup rather than a claim.

Snapshot connection reads the model's accepted Metamodel and optional Class
Index through the private `model_of` / `class_index` collaboration pair before
inspecting the adapter. `Database.connect`'s static surface accepts only
`DomainModel`; a bare accepted Metamodel and a descriptor-backed model — which
composes no class and so has no index — both raise
`SnapshotConnectionError(snapshot-class-backed-model-required)` because neither
can support the Entity lifecycle. After that check, Snapshot—not Core—owns
one private connected-model value containing the accepted Metamodel and the
class index materialization requires, and no identity.
Provider connection state therefore does not become a model or Core concept.

The narrower Entity Runtime remains an atomic collaboration value containing
the accepted Metamodel, Entity Graph Construction, and
Entity Row Codec. It has no partial form: Snapshot may replace the connected
model's transitional materialization dependency only when that complete value
exists, without changing the connected Metamodel contract.

Before resolution, the class-backed model supplies only an enumeration-only
Unresolved Metamodel view over the fixed Entity Class tuple. It does not build
a duplicate metadata-record graph or define lookup over potentially duplicate
identities. Successful resolution creates the canonical indexed Candidate
Metamodel of identity-resolved declarations; only successful owner compilation
creates final Entity Metadata, adds facets, and produces the separate Metamodel
used for behavior. Specifically, the one `m-metamodel` Metadata Compiler
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
separately accepted Metamodel is the sole normalized runtime truth; a class
index only refers classes back to it, and a descriptor-backed model has none.

Temporality is selected by one of three framework roots: `Entity` for a
non-temporal model, `TxTemporal`, or `Bitemporal`. The temporal roots
are not model candidates or domain inheritance positions. They supply the
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

We rejected `model=` enrollment in the class header because importing a module
would mutate a shared model and force the Entity metaclass to depend on model
assembly. We rejected public `add()` and class-backed `build()` paths because
they permit incrementally different model sets and duplicate the constructor's
ownership. The resulting developer path is intentionally explicit:

```python
class Order(Entity, table="orders"):
    id: Attr[int] = attr(primary_key=True)


models = DomainModel(Order)
```

The declaration frontend compiles Python annotations and `attr(...)` options
directly into core semantic values. In particular, scalar types become
structured Neutral Types and primary-key allocation becomes
`ApplicationAssigned`, `Max`, or a fully resolved `Sequence`; descriptor type
and strategy strings never become the class-backed model's internal contract.
The class-header `table=` value similarly normalizes to the core
`StorageContainer = Table(name)` value. Member Storage Locations never repeat
that container; the reserved future `DocumentCollection` variant adds no
current authoring or runtime behavior.
Persistence Mode is the separate `ReadWrite | ReadOnly` mapping capability.
Omission on a standalone Entity or family root normalizes to ReadWrite, the
ordinary ORM case; only an exceptional non-writable mapping spells
`persistence=READ_ONLY`. Persistence Mode is family-wide and root-owned. A
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
Formation also rejects a domain descendant that shadows any ancestor navigable
member, including a cross-category or identical redeclaration. Separate sibling
branches may reuse a name.
Class creation rejects an empty top-level or nested Value Object declaration.
Each must contain at least one scalar or nested member; formation retains the
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
to `DomainModel`; the class-backed frontend reaches them only through the
explicit annotations of the model's Entity Classes.

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


models = DomainModel(Customer, Supplier)
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

A class-backed Domain Model supplies one deep Entity Graph Construction
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
query target, deferred feature, transaction, adapter, SQL, and
pre-materialization neutral-decoding failures retain their own public
classifications. Direct
advanced Entity Graph Construction callers continue to receive the original
exception.

Entity Graph Construction owns concrete class selection through the Class
Index, Pydantic allocation and population, canonical-to-Python member
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

Ordinary frozen values may be constructed from a class no model composed, and so
may queries: authoring reaches no model at all. What such a value cannot do is
execute. An Entity Class participates in any number of Domain Models, one Domain
Model serves any number of Databases, and no value carries a model or a model
identity, so there is no ownership relation between a query and a Database to
check. There is no
default or parent registry, ambient lookup, class-list scope inference, public
incremental registration API, or unbind/reset path; descriptor-backed models
enter through the Descriptor Frontend's private fixed-source seam and compose no
Entity Class.

What replaces model identity is Python's type system. Every Attribute
Expression, Relationship Path including narrowing, Predicate, Assignment, Sort
Key, and Find Query is parameterized by the Entity it addresses, and variance
states the inheritance rule: a Predicate, Sort Key, Assignment, and match-all
Predicate are contravariant in their position, a Relationship Path covariant in
its source and target. Composing a value from an inapplicable Entity is
therefore a static error where the call is written, which is the failure model
identity never observed — `Order.where(Customer.id == 1)` is same-model and no
identity check could ever have seen it. Neutral literal and assignment values
carry no parameter until incorporated into a parameterized value. Each such
static rejection also has an equivalent model-aware rejection at execution
preflight, which is what covers the serialized ingress and any untyped caller;
narrowing relatedness is the single stated exception, because a type parameter's
bound may not itself be generic.

`QueryDefinitionError` represents only what the frontend itself judges. A query
executed through a Database whose connected model declares no Entity for its
target raises `QueryTargetError(code="query-target-not-in-model")`, retaining
neither the query, the model, nor the Database, before operation validation,
deferred-feature classification, or any I/O — a resolution failure rather than
an ownership one. After the target resolves and the operation validates,
Snapshot compares
the privately lowered canonical operation's Snapshot execution classification
with its private set of explicitly deferred execution features. The Find Query
carries no Snapshot feature tags. A match raises Snapshot's
`DeferredFeatureError(code="execution-feature-deferred",
features=<ascending core Feature tags>)` before SQL or Database Port access.
Thus the valid staged `snapshot-history-includes` composition is never
misclassified as an invalid query, while a missing implementation for a Feature
claimed by the active Conformance Slice remains a defect rather than an
allowable deferral. All four steps are one private seam, `preflight_find`, in
that fixed order, which `Database.find`, `Transaction.find`, and the later
Session read boundary call rather than reimplementing.

Predicate-selected writes introduce no public mutation-query type. All five
`_where` verbs accept the ordinary `FindQuery[E, S]` from `Entity.where(...)`,
but only its mutation-compatible form carrying nothing beyond target and
predicate. Any
include, order, limit, narrow, temporal read, history/range, or other
result-shaping clause raises
`QueryDefinitionError(code="query-not-mutation-compatible")`. The transaction
method privately normalizes the accepted value to an ephemeral
`MutationSelection(target, predicate)` that is neither exported
nor serialized, and the write boundary builds the canonical, model-neutral
`PredicateSelection` from those two facts, so a Find Query never reaches the
Unit of Work, the planner, or SQL lowering. Assignment-bearing verbs also
require every Assignment to address the exact Entity target; mismatch raises
`QueryDefinitionError(code="query-assignment-target-mismatch")` before Unit of
Work buffering, SQL, or adapter access, and before the inheritance-family
refusal, because an inherited member's Assignment addresses the declaring
Entity. Delete and terminate forms accept no Assignments.

The outermost `Database.transact(...)` demarcation stores a strong
reference to its exact originating Database object. A nested call joins only
through that same object (`requested_database is active_owner`); an alias joins
and receives the identical Transaction, while every different handle fails
even if it carries the same Domain Model, adapter, dialect, clock, or equivalent
configuration. A mismatch raises exported
`TransactionOwnershipError(RuntimeError)` with sole stable code
`transaction-owner-mismatch`, before option
comparison, rollback-only joining, Principal resolution, closure execution, Unit
of Work mutation, SQL, connection acquisition, or adapter access, and retains
neither handle. It is a `RuntimeError` rather than a `ValueError` because the
refusal reports that the ambient per-thread demarcation is owned by another
object: nothing about the call's arguments is wrong and the identical call
succeeds from the owner. That is what distinguishes it from
`TransactionOptionConflictError`, which rejects an argument *value*, and it
matches every sibling scoped-state refusal on this join path
(`UnitOfWorkError`, `RollbackOnlyError`) and the `RuntimeError` specified for
`QueryTargetError`. The class carries its code and no other state, so "retains
neither handle" holds by construction. After exact-owner success,
existing rollback-only, option-conflict, same-Transaction, and outermost-only
commit/abort/retry semantics remain unchanged. The demarcation owner is scoped
state, not a Database, model, or adapter registry.

Entity actively overrides Pydantic's inherited `model_copy(...)`. Every call,
with or without `update=`, raises `EditError(code="edit-use-edit")` and creates
no value. `edit(...)` is the only authored copy-with-changes path and the only
one that creates an Edited Copy with a Change Record.

## Amendment (2026-08, COR-64): model identity gave way to the type system

The composition decision above is unchanged. What this amendment retires is the
Python-realization layer that was built on it — the permanent class claim and
the opaque exact-model identity threaded through every query value — together
with the refusals stated in terms of them. The reason is that the identity did
not do the job it was chosen for. It was chosen to stop a query value composed
against one model from being executed against another, and:

- it never observed the dominant failure. `Order.where(Customer.id == 1)` is a
  single-model composition, so no identity comparison could see it; it compiled
  to a query over `orders` with the foreign prefix silently rebound, and on a
  predicate-selected write it deleted or updated the wrong rows. That defect was
  fixed by a positional rule in the model-aware validator
  (`attribute-outside-active-position`), which identity tags never reached;
- it was near-redundant with the claim rule. One model per class already made
  cross-model composition unconstructible, so a query's classes already
  determined its model;
- it foreclosed legitimate reuse: one Entity Class could belong to one model,
  for the lifetime of the class object.

Parameterizing every composed value by the Entity it addresses catches the
failures identity missed, catches them in the editor, and costs the claim
nothing to give up. The retirements, one for one:

| Retired | What answers now |
|---|---|
| `MetamodelHub` | `DomainModel` — same construct-or-raise contract, no claim, no identity, no synchronization point |
| `MetamodelBinding`, Entity Class Binding, `claim` / `binding_of`, the module-level claim registry and its lock | the model's own **Class Index**, a lookup reached through a private seam |
| `MetamodelStateError`, `metamodel-class-already-bound`, `metamodel-class-not-bound` | nothing — neither state exists. A class no model composed is queryable; the query simply has no connected model to run against yet |
| opaque exact-hub identity on every expression, path, predicate, assignment, sort key, and query | the value's own Entity type parameter, with variance stating the inheritance rule |
| `QueryDefinitionError(query-hub-mismatch)` | a static type error at the composition site, plus the model-aware positional rules at preflight |
| `QueryOwnershipError(query-owner-mismatch)` | `QueryTargetError(query-target-not-in-model)` — resolution, not ownership |
| `LoweredFindQuery.hub_identity` | removed; the value is exactly `target` and `operation` |
| `PredicateSelection(target, predicate, hub_identity)` as the frontend's normalization | `MutationSelection(target, predicate)`, from which the write boundary builds the canonical `PredicateSelection` |
| `sealed_model(hub)` / `SealedModel` | the `model_of` / `class_index` pair |
| `snapshot-class-backed-hub-required` | `snapshot-class-backed-model-required` |
| `FindQuery[T]` | `FindQuery[E, S]` — queried Entity and returned Entity |

Two consequences are worth stating because they are easy to misread as
regressions. First, **authoring-time model validation is gone**: a clause is
measured against the connected model at execution preflight instead, which is
also what covers the serialized ingress and any untyped caller, so no rule was
dropped — only relocated to the one place that can state it for every ingress.
Second, **narrowing relatedness has no static half**. Neither
`Entity.narrow(*subtypes, where=...)` nor `FindQuery.narrow(*subtypes)` states
that the classes it names are subtypes of the position it narrows: a type
parameter's bound may not itself be generic, and the two things a narrowing
signature could spend its parameter on — checking the position or moving the
result — are mutually exclusive because `type[…]` is covariant. Each form spends
it on what the narrowing produces, and `narrow-outside-position` refuses an
unrelated class at preflight. A hop narrow keeps its static half, because its
bound rides on the receiver.

## Amendment (2026-08, COR-50): the Snapshot graph section's spellings

The Snapshot collaboration this record describes was built by COR-50, and the
prose above states it in the names it was designed under —
`is_loaded` / `narrowed`, `EntityGraphResolution`, `EntityRuntime`,
`snapshot-model-mismatch`. Every one of them is retired. The one-for-one
tabulation of their shipped replacements lived in a design document that was
itself retired afterwards, so the shipped spellings are read from
`parallax.core.entity`'s exports and `languages/python/spec/python.md` §3
instead. The decision itself is unaffected: what moved is spelling, not
ownership.

## Amendment (2026-08, COR-63): capabilities are reached one at a time

The composition decision above is unchanged, as is the class index the COR-64
amendment left in place of model identity. What this amendment retires is the
atomic Entity Runtime — the three-part collaboration value containing the
accepted Metamodel, Entity Graph Construction, and the Entity Row Codec, stated
above to have no partial form.

It was specified and never built, and building the capabilities it would have
paired showed why: nothing wanted the composite. Read materialization
crosses graph construction alone and write preparation crosses the row codec
alone; the one caller that holds both, Snapshot's private connected-model value,
holds two references as cheaply as one. The atomicity claimed as a guarantee
therefore protected nothing — each capability derives on demand from the same
model, so no state existed in which one was present and the other could not be.
`graph_construction_of(model)` and `row_codec_of(model)` are the two seams, each
returning its own capability and each retained by the model on first reach. A
composite value would have bought only the appearance of a guarantee, at the
price of a name that has to be kept accurate as capabilities are added.

Codec binding resolves rather than owns, which extends this amendment's
predecessor to the write side. A value reaches the codec, the codec resolves the
Entity Identity that value's class declares, and a model declaring no such
Entity is a resolution failure — the same distinction `QueryTargetError` already
draws, and for the same reason: no ownership relation between a value and a
model exists. The class index answers which class a row instantiates and is not
an authorization structure, so it is not consulted to decide whether a value
belongs. What the codec emits is a function of the resolved identity's declared
members, so ownership could not have changed the answer anyway.
