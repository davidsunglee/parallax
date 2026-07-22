# Python Metamodel Hub and Entity frontend design

**Status:** Accepted

**Accepted:** 2026-07-20

**Scope:** Candidate 06 in the Python architecture review; the core metadata
contract it revealed; and the Python `parallax.core.entity` frontend,
introspection, query, row translation, provenance, and Snapshot-handle seams.

## Purpose

Replace the process-global, mutually dependent Entity frontend with one
explicit, sealed Metamodel Hub and a directed set of internal concerns. The
result should make the ordinary Python path pleasant, make the core metadata
contract representation-independent, and leave a fresh implementation session
with no ambient registry, descriptor mirror, lazy back-import, or migration
constraint to preserve.

This is an intentional interface and specification redesign, not a
behavior-preserving file split. Parallax specifications remain authoritative,
but this work may change those specifications where the cleaner model requires
it. There is no compatibility or data migration requirement.

The core decision is recorded in
[ADR 0028](../adr/0028-behavioral-modules-depend-on-the-metamodel-interface.md).
The table-per-hierarchy mapping decision is recorded in
[ADR 0029](../adr/0029-table-per-hierarchy-shared-table-is-root-owned.md).
The formation-composition decision is recorded in
[ADR 0030](../adr/0030-model-formation-is-explicitly-composed.md).
The cross-language identity decision is recorded in
[ADR 0031](../adr/0031-entity-identity-includes-namespace.md).
The relationship-ownership decision is recorded in
[ADR 0032](../adr/0032-relationship-formation-belongs-to-m-relationship.md).
The Python assembly decision is recorded in
[Python ADR 0007](../../languages/python/docs/adr/0007-entity-classes-compose-into-explicit-sealed-metamodel-hubs.md).

## Desired developer surface

```python
class Customer(
    Entity,
    table="customers",
    namespace="sales",
):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str]


class Order(
    Entity,
    table="orders",
    namespace="sales",
):
    id: Attr[int] = attr(primary_key=True)
    status: Attr[str]
    customer: Rel[Customer] = rel(...)


models = MetamodelHub(Customer, Order)
models.seal()

db = Database.connect(adapter, models)

query = Order.where(Order.status == "OPEN").include(Order.customer)
snapshot = db.find(query)

edited = snapshot.result().edit(status="CLOSED")
db.transact(lambda tx: tx.update(edited))
```

Entity Classes are always frozen. Pydantic's `frozen=True`, `EntityConfig`,
`__parallax__`, `registry=`, explicit registration calls, and default registry
selection are not part of the target interface.

## Settled design

### One explicit model scope

- `MetamodelHub` is the sole Python model scope.
- There is no process-global default, parent registry, `ScopedMetamodel`,
  ambient fallback, or inference of a scope from an arbitrary class list.
- A hub has exactly one fixed source: Entity Classes or a canonical descriptor.
  Sources cannot be mixed and classes cannot be late-bound into a
  descriptor-backed hub.
- One Entity Class may be bound to only one successfully sealed hub.

### Class declaration and model composition are separate

- Typed class-header keywords declare table, namespace, Persistence Mode, and
  inheritance role. Temporality is selected by the framework Entity base:
  ordinary `Entity`, `TxTemporal`, or `Bitemporal`.
- Persistence Mode is omitted for the ordinary Read Write mapping. A root uses
  `persistence=ReadOnly` only for the exceptional mapping on which Parallax
  must reject persistence writes. Persistence Mode is family-wide and
  root-owned: every descendant inherits the root's value unchanged, and a
  descendant declaration is rejected even when it merely repeats that value.
- Entity members use symmetric typed annotations and mapping factories:
  `Attr[T]` with optional `attr(...)`, and `Rel[T]` with required `rel(...)`.
  The old `Field(...)` / `Relationship(...)` configuration names are removed.
- Value Object members use the same `Attr[T]` / `attr(...)` vocabulary;
  `VoField` is removed. `attr(...)` options are checked against their context,
  so Entity-only storage or identity options on a Value Object fail during
  class creation. Value Object classes are inherently frozen too.
- A Value Object intended for one occurrence may be declared lexically inside
  its owning Entity or Value Object. A shape used at multiple occurrence paths
  is an ordinary standalone Value Object class referenced by each `Attr[...]`
  annotation. Neither form is a hub candidate or requires registration: only
  Entity Classes are passed to `MetamodelHub`, and the frontend follows their
  explicit annotations. Shape keys, occurrence keys, and shape registration
  are not part of the Python authoring interface.
- `TxTemporal` and `Bitemporal` are framework roots derived from
  `Entity`, exactly as `Entity` itself is. They are neither hub candidates nor
  domain inheritance positions. `TxTemporal` supplies the typed,
  read-only `tx_start`/`tx_end` attributes with `in_z`/`out_z` mappings;
  `Bitemporal` supplies typed, read-only `valid_start`/`valid_end` followed by
  `tx_start`/`tx_end`, mapped to `from_z`/`thru_z` and `in_z`/`out_z`.
  A domain family inherits its root's selected temporal base and cannot change
  temporal shape at a descendant.
- Python authors declare no `AsOfAxis`, temporal attribute, Timestamp type,
  interval flag, or standard column in the initial surface. The accepted
  Metamodel still carries explicit start/end Attribute Identities and ordinary
  Attribute Metadata Storage Locations. Consequently, a future advanced
  class-header override for legacy column mappings is additive authoring sugar;
  it requires no Metamodel Interface or behavioral-module change and need not
  weaken the default base-class form.

The single-use form keeps the declaration beside its only occurrence:

```python
class Customer(Entity, table="customer"):
    class Address(ValueObject):
        street: Attr[str]
        city: Attr[str]
        postal_code: Attr[str]

    id: Attr[int] = attr(primary_key=True)
    address: Attr[Address]


models = MetamodelHub(Customer)
models.seal()
```

The reusable form lifts only the shared shape out of its owners:

```python
class Address(ValueObject):
    street: Attr[str]
    city: Attr[str]
    postal_code: Attr[str]


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

The reusable class contributes one declaration shape, while compilation gives
each use its own path-based Value Object Identity. The class is still reached
only through Entity declarations and is not passed to the hub separately.

- Inheritance uses explicit, glossary-aligned declaration values:
  `AbstractRoot`, `AbstractSubtype`, and `ConcreteSubtype`. Every subclass in a
  family declares its role; absence never silently means abstract.
- Python class inheritance supplies each subtype's parent, so authors do not
  repeat it. An Abstract Root receives `TablePerHierarchy(tag_column=...)` or
  `TablePerConcreteSubtype`; an Abstract Subtype is a marker; a Concrete
  Subtype supplies only its TPH `tag_value` when applicable. Sealing resolves
  the Python parent to core Entity Identity.
- `table=` always remains a top-level Entity Class header keyword. An ordinary
  entity declares its own table; a TPH Abstract Root declares the family's one
  shared table and its concrete descendants omit it; a TPCS root and abstract
  subtypes omit it while every concrete subtype declares its own table.
- Defining or importing an Entity Class does not mutate a hub.
- `MetamodelHub(*entity_classes)` receives the complete class-backed candidate
  set in one call. The set is immutable after construction.
- All inheritance participants are supplied explicitly; the hub does not scan
  `__subclasses__()` or infer imported classes from process state.
- A Python `Rel[Target]` class value resolves directly within the candidate set.
  A string target such as `Rel["Customer"]` is relative only to the declaring
  class's core namespace, while `Rel["crm.Customer"]` is exact. Resolution
  never evaluates arbitrary module globals, calls `eval`, or searches outside
  the hub candidate set.
- `Rel[Target]` is the sole Python target declaration. `rel(...)` has exactly
  two mutually exclusive forms:

  ```text
  rel(cardinality=..., join=(source_attribute, target_attribute),
      dependent=False, order_by=...)
  rel(reverse_of=target_relationship_name, order_by=...)
  ```

  The defining form owns the association's cardinality, join, dependency, and
  direction-specific ordering. The reverse form gets its target scope from
  `Rel[Target]`, names only that target's defining relationship, and cannot
  repeat cardinality, join, or dependency. For example,
  `Rel[Customer] = rel(cardinality=ManyToOne,
  join=("customer_id", "id"))` pairs with
  `Rel[tuple[Order, ...]] = rel(reverse_of="customer")`.
- There is no public class-backed `add()` or `build()` path. Large applications
  may expand explicit tuples into the constructor.
- Every frontend source contains at least one Entity declaration.
  `MetamodelHub()` fails before construction with
  `MetamodelDefinitionError(code="metamodel-empty")` and no argument index.
  The canonical descriptor retains its schema-level nonempty Entity
  requirement, so an empty descriptor fails during descriptor parsing rather
  than during `seal()`. Every other Unresolved Metamodel adapter guarantees the
  same nonempty source invariant.
- `MetamodelHub(*classes)` validates its source arguments left-to-right before
  constructing a hub. Every argument must be a domain Entity Class; Entity
  instances, ordinary classes, Value Object classes, and the framework roots
  `Entity`, `TxTemporal`, and `Bitemporal` fail with
  `MetamodelDefinitionError(code="metamodel-invalid-entity-class")`. Repeating
  the same class object fails with
  `MetamodelDefinitionError(code="metamodel-duplicate-entity-class")`. Both
  errors expose the zero-based offending argument index. Distinct class
  objects that declare the same Entity Identity are valid constructor inputs
  and become an aggregated whole-model issue during `seal()`.
- Canonical descriptor input uses three separate fixed-source classmethod
  factories mirroring the three export methods:
  `MetamodelHub.from_descriptor(document)` for an already-decoded mapping
  (no syntax phase — schema validation is its first gate), and
  `MetamodelHub.from_json(text)` / `MetamodelHub.from_yaml(text)` for
  `str | bytes` UTF-8 text. There is no format sniffing — JSON is a YAML
  subset, so sniffing is unsound — and no path I/O; reading files is the
  caller's. Descriptor ingestion has three explicit phases. Invalid JSON/YAML text raises
  `DescriptorSyntaxError(code="descriptor-invalid-syntax")` before a hub
  exists, carrying its format, optional one-based line/column, and parser
  cause. A decoded document that violates the canonical schema raises
  `DescriptorSchemaError(code="descriptor-schema-invalid")`, also before a
  hub exists, carrying a canonically ordered immutable violation sequence.
  Only a schema-valid document creates an `UNSEALED` hub; missing references,
  invalid families, relationship incoherence, and all other model semantics
  then fail through `MetamodelValidationError` during `seal()`.
- `DescriptorError(ValueError)` is the public descriptor-ingestion base.
  `DescriptorSchemaViolation` contains a structured document path of string
  keys and nonnegative array indices, a stable schema-rule name, and an
  explanatory message. Violations sort by the typed path and then rule name;
  message and validator emission order do not participate. Descriptor document
  paths never enter `MetamodelIssue` or semantic `ModelLocation` values.

### Explicit sealing

- Construction produces an `UNSEALED` hub. `seal()` is the only lifecycle
  transition that makes it authoritative. Its public state machine is
  `UNSEALED -> SEALED | REJECTED`; `SEALING` is an internal single-flight
  coordination phase, not an observable public state.
- Before sealing, ordinary frozen Entity values may be constructed, but query
  construction, metadata lookup/export, handle binding, and execution fail
  with an unsealed-hub error.
- Sealing resolves model-relative references, validates the complete model,
  compiles immutable module-owned effective facets, freezes the accepted
  Metamodel, then installs Entity Class bindings only after every formation
  and realization check succeeds.
- The first `seal()` caller atomically claims the internal `SEALING` phase and
  owns the complete attempt. Other threads calling `seal()` on the same hub
  wait for that attempt and then observe its terminal outcome. Ordinary hub
  operations do not wait and continue to fail as unsealed until `SEALED` is
  published.
- A successful attempt publishes the accepted Metamodel, its complete facet
  set, and every Entity Class binding as one transition to `SEALED`. Calling
  `seal()` after success is an idempotent no-op.
- A failed attempt publishes none of them and transitions once to `REJECTED`.
  Because its candidate set is immutable, corrected declarations require a
  new hub. Waiting callers and later `seal()` calls reproduce an equivalent
  terminal failure with the same public type, stable code or canonical issue
  sequence, and preserved cause where the error contract exposes one. Other
  operations on the rejected hub raise its rejected-hub state error.
- Re-entering `seal()` on the owning thread fails immediately with
  `MetamodelStateError(code="metamodel-seal-reentrant")` rather than
  deadlocking. If that failure escapes the owning attempt, the hub makes the
  ordinary atomic transition to `REJECTED`.
- The complete operation state table is:

  | State | `seal()` | Model-dependent operations |
  |---|---|---|
  | `UNSEALED` | The first caller owns the attempt and returns `None` on success or raises its terminal failure. | Fail immediately with `MetamodelStateError(code="metamodel-unsealed")`. |
  | internal `SEALING` | Another thread waits and then returns `None` or reproduces the terminal failure; owning-thread re-entry raises `metamodel-seal-reentrant`. | Fail immediately as `metamodel-unsealed`; they never wait or observe provisional state. |
  | `SEALED` | Return `None` as an idempotent no-op. | Available. |
  | `REJECTED` | Reproduce the stored terminal failure. | Fail with `MetamodelStateError(code="metamodel-rejected")`, exposing the terminal failure as cause. |

  Model-dependent operations include Entity enumeration, metadata lookup,
  export, typed facet access, query and path construction, class resolver and
  row/graph codec access, database connection, and execution. Direct
  expression/path use of an Entity Class with no sealed binding instead raises
  `MetamodelStateError(code="metamodel-class-not-bound")`.
- Constructing an ordinary frozen concrete Entity value remains class-local and
  is allowed before binding because it reads no model metadata. It confers no
  binding: query construction and persistence still fail until the class has
  its permanent sealed-hub binding. Abstract-role instantiation remains
  forbidden by the class declaration itself.

### Model Formation boundary

- Class creation immediately rejects errors that prevent a coherent Python
  class: unknown class-header keywords, invalid keyword types or literals,
  reserved names, malformed `Attr`/`Rel` annotations, and Pydantic definition
  errors.
- Hub construction produces an immutable **Unresolved Metamodel**. `seal()`
  submits it to the runtime's explicit Formation Profile; it does not implement
  reference resolution or semantic rules itself.
- Candidate and accepted capabilities are exact:

  ```text
  UnresolvedMetamodel
    entities: immutable sequence<UnresolvedEntityDeclaration>

  CandidateMetamodel
    entities: canonical immutable sequence<EntityDeclaration>
    entity(EntityIdentity) -> EntityDeclaration | absent

  Metamodel
    entities: canonical immutable sequence<EntityMetadata>
    entity(EntityIdentity) -> EntityMetadata | absent
    facet(FacetKey<T>) -> T
  ```

  Unresolved Metamodel has no identity/member lookup, facet access, or
  uniqueness guarantee because duplicates are valid resolver input. Its
  sequence may retain frontend declaration order for source diagnostics, but
  that order is non-semantic. The resolver uses private multimaps and creates
  canonical indexes only on success. Candidate Metamodel provides total,
  non-throwing, expected-amortized-constant-time Entity declaration lookup and
  preserves resolved authoring structure, but has no Metadata, facets, or
  behavioral authority. Metamodel is deliberately a separate protocol: only
  compilation creates normalized Entity Metadata, local member lookup, and
  facets. Class and descriptor frontends may implement unresolved declarations
  as views over their native sources; neither must allocate a second
  formation-input record graph.
- The shallow unresolved Entity contract is:

  ```text
  UnresolvedEntityDeclaration
    identity: EntityIdentity
    container: StorageContainer | absent
    persistence: PersistenceMode | absent
    attributes: immutable sequence<AttributeMetadata>
    relationships: immutable sequence<UnresolvedRelationshipDeclaration>
    value_objects: immutable sequence<ValueObjectOccurrenceDeclaration>
    as_of_axes: immutable sequence<AsOfAxisMetadata>
    inheritance: Inheritance<EntityReference> | absent
    indices: immutable sequence<IndexMetadata>
  ```

  Reference-free facts whose final identity is already known reuse normalized
  Metadata types. A separate `*Declaration` protocol exists only when a shape
  may still carry references or its accepted identity depends on occurrence
  expansion. Attribute, As-Of Axis, and Index Metadata therefore have no
  unresolved twins, while a reusable Value Object leaf cannot yet be Value
  Object Attribute Metadata.
  Unqualified names are correct in this all-local declaration view; resolved
  Entity Metadata uses `declared_*` where local/effective ambiguity exists. An
  Entity's outer formation-input position is non-semantic, while every local
  sequence preserves authoring order. The declaration exposes no lookup.
- The resolved Entity contract is the same shallow local structure with only
  its reference-bearing facts advanced:

  ```text
  EntityDeclaration
    identity: EntityIdentity
    container: StorageContainer | absent
    persistence: PersistenceMode | absent
    attributes: immutable sequence<AttributeMetadata>
    relationships: immutable sequence<RelationshipDeclaration>
    value_objects: immutable sequence<ValueObjectOccurrenceDeclaration>
    as_of_axes: immutable sequence<AsOfAxisMetadata>
    inheritance: InheritanceMetadata | absent
    indices: immutable sequence<IndexMetadata>
  ```

  Relationship declarations contain resolved identities but retain their
  defining/reverse roles. Inheritance parents have advanced from Entity
  Reference to Entity Identity. The reusable Value Object declaration graph is
  unchanged until post-validation compilation expands it. The declaration has
  no member lookup, facet access, effective view, or behavioral authority, and
  its local sequences retain their authoring order.
- Reusable Value Object declarations have the exact formation-graph contract:

  ```text
  ValueObjectShapeKey
    opaque formation-local equality/hash token

  ValueObjectShapeDeclaration
    key: ValueObjectShapeKey
    attributes: immutable sequence<ValueObjectAttributeDeclaration>
    value_objects: immutable sequence<NestedValueObjectOccurrenceDeclaration>

  ValueObjectAttributeDeclaration
    name: nonempty string
    type: NeutralType
    nullable: boolean

  ValueObjectOccurrenceDeclaration
    name: nonempty string
    storage: StorageLocation
    multiplicity: Multiplicity
    nullable: boolean
    shape: ValueObjectShapeDeclaration

  NestedValueObjectOccurrenceDeclaration
    name: nonempty string
    multiplicity: Multiplicity
    nullable: boolean
    shape: ValueObjectShapeDeclaration
  ```

  A Shape Key denotes one reusable declaration node throughout one Model
  Formation. Every
  occurrence of that node carries the same key; distinct declaration nodes
  carry distinct keys even when structurally equal. The token promises stable
  equality and hashing only—no spelling, ordering, serialization, or equality
  across formation runs or frontends. Python derives it privately from the
  Value
  Object class declaration; the descriptor adapter creates private tokens for
  its inline shape nodes. It is never authored, registered, exported, used in a
  Model Location, or copied into accepted Metadata.

  Only a top-level occurrence owns Storage Location. Shapes and nested
  occurrences are storage-neutral. Each sequence preserves declaration order
  and exposes no lookup. The `m-value-object` Rule Set traverses Shape Keys to
  validate nonempty acyclic containment without relying on host-language object
  identity. After validation, the Metadata Compiler expands each occurrence
  into distinct path-identified Value Object Metadata and discards every Shape
  Key. Candidate Metamodel preserves this graph unchanged because it contains no
  model-relative Entity Reference.
- Unresolved relationships retain the exact authoring union until resolution:

  ```text
  UnresolvedRelationshipDeclaration =
      UnresolvedDefiningRelationshipDeclaration(
        identity: RelationshipIdentity,
        cardinality: RelationshipCardinality,
        join: UnresolvedRelationshipJoin,
        dependent: boolean,
        order_by: immutable sequence<UnresolvedRelationshipOrder>,
      )
    | UnresolvedReverseRelationshipDeclaration(
        identity: RelationshipIdentity,
        reverse_of: RelationshipReference,
        order_by: immutable sequence<UnresolvedRelationshipOrder>,
      )

  UnresolvedRelationshipJoin
    source: AttributeIdentity
    target: AttributeReference

  AttributeReference
    entity: EntityReference
    name: string

  RelationshipReference
    entity: EntityReference
    name: string

  UnresolvedRelationshipOrder
    attribute: string
    direction: SortDirection
  ```

  Defining target exists only in `join.target.entity`; reverse target exists
  only in `reverse_of.entity`. Ordering is a target-local attribute name and
  repeats no Entity Reference. There is no additional target, reverse name,
  foreign-key hint, or duplicated join/cardinality/dependency input.
- Foundational resolution produces the corresponding identity-resolved local
  declaration union:

  ```text
  RelationshipDeclaration =
      DefiningRelationshipDeclaration(
        identity: RelationshipIdentity,
        cardinality: RelationshipCardinality,
        join: RelationshipJoin,
        dependent: boolean,
        order_by: immutable sequence<RelationshipOrder>,
      )
    | ReverseRelationshipDeclaration(
        identity: RelationshipIdentity,
        reverse_of: RelationshipIdentity,
        order_by: immutable sequence<RelationshipOrder>,
      )
  ```

  Resolution changes only references and target-local attribute names into
  canonical identities. It does not pair declarations, swap joins, invert
  cardinality, decide validity, or synthesize Relationship Metadata.
  `m-relationship` owns one Rule Set that validates defining/reverse coherence,
  join and cardinality consistency, dependency, and ordering. Its Model
  Compiler then derives the immutable symmetric Relationship Facet. A one-way
  defining declaration compiles with `reverse = absent`.
- Entity Reference is exact and closed:

  ```text
  EntityReference =
      RelativeEntityReference(name: nonempty dot-free string)
    | ExactEntityReference(identity: EntityIdentity)

  resolve(owner: EntityIdentity, reference):
    RelativeEntityReference(name) -> EntityIdentity(owner.namespace, name)
    ExactEntityReference(identity) -> identity
  ```

  Containment supplies the owner, so the reference does not repeat it. A
  Python class target becomes Exact even when unnamespaced; a bare authored
  declaration string becomes Relative; a qualified string parses immediately
  to Exact. No raw spelling, optional namespace, Python class, module name,
  `eval`, or global fallback survives. Ownerless core operations consume
  resolved Entity Identity. The `models.meta(...)` string facade separately
  parses canonical identity spelling: bare is exact unnamespaced and qualified
  is exact namespaced.
- `m-metamodel` owns its foundational formation rules, including canonical
  identity uniqueness, member-name collisions, and model-relative reference
  resolution. Every other whole-model invariant and stable issue code remains
  owned by the semantic module that defines it: for example,
  `m-inheritance` owns inheritance closure and family-strategy rules.
- `m-metamodel` owns the immutable issue contract:

  ```text
  IssueCode = owner-prefixed nonempty kebab-case token

  MetamodelIssue
    code: IssueCode
    location: ModelLocation
    related: immutable sequence<ModelLocation>
    message: string

  ModelLocation =
      ModelRoot
    | EntityLocation(EntityIdentity)
    | AttributeLocation(AttributeIdentity)
    | RelationshipLocation(RelationshipIdentity)
    | ValueObjectLocation(ValueObjectIdentity)
    | ValueObjectAttributeLocation(ValueObjectAttributeIdentity)
    | AsOfAxisLocation(EntityIdentity, TemporalDimension)
    | IndexLocation(IndexIdentity)
  ```

  The primary location is the tooling focus; related locations preserve
  semantic order and may be empty. Issue Codes are stable and owned by the
  semantic module, not a centrally closed enum. Each begins with the owner's
  canonical catalog stem after `m-`: for example `metamodel-*`,
  `inheritance-*`, and `value-object-*`. Every issue prevents acceptance, so
  there is no severity. Message text is explanatory and is excluded from
  equality and canonical ordering. The foundational resolver and every
  contributed rule set emit this same value, allowing resolution to report
  issues without depending back on `m-model-formation`; no separate Resolution
  Issue or translation layer exists.
- A Model Location identifies only a semantic declaration. The Issue Code
  identifies the failed rule, so locations do not grow descriptor/Python
  property-path variants. Invalid Attribute configuration focuses the
  Attribute; a reverse mismatch relates the opposite Relationship; a Value
  Object cycle relates the remaining cycle locations in traversal order;
  model-wide problems use `ModelRoot`. Descriptor JSON Pointers, Python class
  names, source spans, and arbitrary property strings are excluded. A frontend
  may map a semantic location to source coordinates outside issue equality and
  conformance.
- Canonical issue ordering is independent of emission order:

  ```text
  MetamodelIssue.canonical_key =
    (location.canonical_key, code, related.map(_.canonical_key))

  ModelRoot                     -> (0)
  EntityLocation                -> (1, entity_key, 0)
  AttributeLocation             -> (1, entity_key, 1, attribute_name)
  RelationshipLocation          -> (1, entity_key, 2, relationship_name)
  ValueObjectLocation           -> (1, entity_key, 3, containment_path)
  ValueObjectAttributeLocation  -> (1, entity_key, 4,
                                    containment_path, attribute_name)
  AsOfAxisLocation              -> (1, entity_key, 5, dimension_key)
  IndexLocation                 -> (1, entity_key, 6, index_name)

  entity_key = (namespace or "", entity_name)
  dimension_key = 0 for ValidTime, 1 for TransactionTime
  ```

  Strings compare codepoint by codepoint; paths and related locations compare
  lexicographically without reordering their semantic sequence. Equality is
  `(code, location, related)`. Message, frontend source position, Formation
  Profile order, rule emission order, and parallel scheduling do not
  participate.
- A module with formation work contributes a Model Formation Rule Set, a Model
  Compiler, or both through the protocols owned by `m-model-formation`.
  `m-model-formation` depends only on `m-metamodel`; contributing modules
  depend on both.
- A Model Formation Rule Set has the exact collaboration contract:

  ```text
  ModelRuleSet
    owner: canonical module-catalog identity
    issue_codes: immutable set<IssueCode>
    validate(CandidateMetamodel) -> immutable sequence<MetamodelIssue>
  ```

  The fixed foundational resolver declares the complete `m-metamodel` code
  set. Formation Profile drift checks reject a code without its owner's prefix
  or declared by multiple contributors. Emitting an undeclared code is a
  formation-contract failure rather than a candidate issue. Two emitted issues
  with equal `(code, location, related)` identities are a contract failure, not
  silently deduplicated. Model Compilers return facets and cannot emit
  validation issues.
- Formation implementation and assembly failures have the exact supported
  contract:

  ```text
  FormationContractError(RuntimeError)
    code: FormationContractCode
    owner: module-catalog identity | absent
    cause: implementation exception | absent

  FormationContractCode =
      formation-profile-drift
    | formation-issue-code-invalid
    | formation-issue-undeclared
    | formation-issue-duplicate
    | formation-facet-missing
    | formation-facet-duplicate
    | formation-resolver-failed
    | formation-resolver-result-invalid
    | formation-rule-set-failed
    | formation-rule-set-result-invalid
    | formation-compiler-failed
  ```

  Unexpected resolver, Rule Set, and compiler exceptions are wrapped with
  `formation-resolver-failed`, `formation-rule-set-failed`, and
  `formation-compiler-failed`, respectively, plus their exact owner and
  original cause. A resolver or Rule Set that returns a mutable collection,
  the wrong closed result type, or a wrong-type element fails with
  `formation-resolver-result-invalid` or
  `formation-rule-set-result-invalid`, respectively. Profile,
  issue-declaration, duplicate-issue, and
  facet-assembly defects use their corresponding stable code. None becomes
  `MetamodelIssue` or `MetamodelValidationError`. Formation publishes no
  accepted Metamodel or facet set after either error category, and the hub
  installs no class binding.
- One explicit, deterministic composition root supplies two separate immutable
  values to the formation runner: a Formation Manifest containing only owner
  identities, complete Issue Code sets, facet keys, and dependency
  requirements; and a Formation Profile containing every active Rule Set and
  compiler implementation. The profile is drift-checked against the
  authoritative manifest in
  [`m-model-formation`](../../core/spec/m-model-formation.md), whose rows name
  every required Rule Set, complete owner Issue Code set, compiler/facet key,
  and module/facet dependency. Runtime contributors are checked against that
  separately supplied data; they do not define completeness by their own
  presence. The runner therefore knows contributor identities but imports and
  owns no contributor implementations. There is no import-time registration,
  decorator enrollment, entry-point discovery, or ambient formation registry.
- Formation has three gated phases: resolve, validate, and compile. The fixed
  foundational resolver first collects all identity, namespace, duplicate-key,
  and model-relative reference issues. Any such issue produces no Candidate
  Metamodel and prevents semantic validation. Every rule set then receives the
  immutable Candidate Metamodel and its issues are accumulated in canonical
  order. Only an issue-free Candidate Metamodel enters compilation, where
  the one `m-metamodel` Metadata Compiler produces Compiled Metadata, then
  semantic Model Compilers run in their declared acyclic dependency order and
  produce immutable module-owned Metamodel Facets.
- A rule or effective computation is implemented once, by its owner module;
  neither `m-metamodel` nor the formation runner duplicates contributed
  semantics. Resolution is one fixed foundational operation, not a registered
  transform. Formation never mutates or propagates facts into either
  formation-input state's local declarations.
- The accepted Metamodel contains the immutable normalized local Metadata view
  and compiled facets. Behavioral modules read their own facet for precomputed
  effective metadata — constant-time per-Entity lookups, output-sensitive
  position construction — instead of repeating stable graph walks.
- The compilation contracts are exact:

  ```text
  MetadataCompiler
    compile(CandidateMetamodel) -> CompiledMetadata

  CompiledMetadata
    entities: canonical immutable sequence<EntityMetadata>
    entity(EntityIdentity) -> EntityMetadata | absent

  ModelCompiler<T>
    owner: canonical module-catalog identity
    facet_key: FacetKey<T>
    requires: immutable set<FacetKey<?>>
    compile(CompiledMetadata, required_facets) -> T
  ```

  The mandatory issue-free Metadata Compiler belongs to `m-metamodel`. After
  all rules succeed it preserves validated Relationship Declarations, expands
  validated acyclic Value Object shapes, performs other total representation
  normalization, and builds immutable local indexes. It contains no
  relationship pairing, join swapping, or cardinality inversion. It cannot
  decide validity or emit issues; an impossible state is
  `FormationContractError(formation-compiler-failed)` owned by `m-metamodel`.
  Each semantic compiler consumes Compiled Metadata plus only its declared
  facet dependencies and returns exactly one typed facet. The runner combines
  the exact Compiled Metadata object and complete facets into the sole accepted
  Metamodel without another metadata graph. A hub may delegate that object and
  add lifecycle, binding, or export context, but may not reconstruct accepted
  Entity/member/facet values or maintain independent normalized
  accepted-metadata indexes. There is no mutable draft, patch merge, or partial
  Entity contribution protocol.
- Each compiling module owns one typed `FacetKey<T>` identified by its
  canonical module-catalog identity. Its compiler emits exactly one value for
  that key, and its public behavioral seam hides generic retrieval behind
  `view(model)`. The Formation Profile rejects missing or duplicate compiler
  keys and the runner installs the complete immutable facet set atomically.
  There is no registration, discovery, global side table, or public
  string-keyed facet map.
- Python-specific realization checks run as a separate atomic claim phase
  after the language-neutral profile succeeds. The relationship-annotation
  agreement rule (Python spec §2) runs first in that phase and reports every
  mismatch together; only an agreement-clean class set proceeds to claiming.
  Under one binding synchronization point, that phase checks the complete
  class set before installing any claim. If one or more classes already belong to another
  sealed hub, it raises
  `MetamodelStateError(code="metamodel-class-already-bound")` with the
  immutable conflicting Entity Identity sequence in canonical order. The
  losing hub publishes no binding and transitions to `REJECTED`; two hubs
  racing for any shared class therefore have exactly one winner. A claim
  collision is process-dependent realization state, not invalid model
  metadata or a Formation Profile defect.
- A successful Entity Class binding is permanent for that class object's
  lifetime and keeps its sealed hub reachable. There is no public or private
  supported `unbind`, hub `close`, reset hook, or weak-reference expiry. A
  class can therefore never acquire different metadata semantics after its
  first successful seal; reload and test-isolation scenarios that need a new
  model use fresh class objects.
- One immutable **Metamodel Binding** is created per successfully sealed
  class-backed hub. It contains the opaque exact-hub identity, a reference to
  the one accepted Metamodel, and the immutable bidirectional Entity Identity
  to Entity Class index. The binding module separately retains the concrete
  hub as a private strong owner reference. Every claimed class points to this
  same Metamodel Binding; no metadata is copied per class.
- Runtime consumers receive the Metamodel Binding, never the concrete
  `MetamodelHub` or its lifecycle, export, connection, or construction
  surface. An **Entity Class Binding** is the individual association between a
  class object and its Entity Identity within the Metamodel Binding, not
  another value graph or metadata implementation. Descriptor-backed hubs have
  neither kind of Python binding.

### Public error model

- `EntityDefinitionError(TypeError)` covers invalid Entity Class construction
  and declaration-grammar violations; its closed stable code set is normative
  in the Python spec's declaration grammar (§2). One code is seal-phase
  rather than class-creation: `entity-relationship-annotation-mismatch`, the
  realization check that a `Rel` optionality annotation agrees with the
  accepted model, reported with every mismatch in canonical order before any
  class claim and rejecting the hub like any failed seal.
- `MetamodelDefinitionError(TypeError)` covers an invalid class-backed hub
  constructor call before any hub exists. Its stable codes are
  `metamodel-empty`, `metamodel-invalid-entity-class`, and
  `metamodel-duplicate-entity-class`. The latter two expose the zero-based
  offending argument index; `metamodel-empty` has no index. It never
  represents a duplicate Entity Identity across distinct valid classes.
- `DescriptorError(ValueError)` is the base for descriptor ingestion before a
  hub exists. `DescriptorSyntaxError` uses stable code
  `descriptor-invalid-syntax`; `DescriptorSchemaError` uses
  `descriptor-schema-invalid` and exposes canonical structured violations.
  Neither is a `MetamodelValidationError`, whose locations are semantic rather
  than document-relative.
- `DescriptorExportError(RuntimeError)` is the descriptor adapter-defect
  boundary after successful sealing. It has stable code
  `descriptor-export-failed`, identifies `document`, `json`, or `yaml`, and
  preserves the cause. It never rejects or mutates the sealed hub and never
  exposes partial output.
- `FormationContractError(RuntimeError)` is a supported top-level error for a
  defective Formation Profile, Rule Set, issue emission, facet assembly, or
  compiler. Its stable code, optional owner, and optional cause distinguish an
  implementation/configuration defect from invalid model metadata.
- `MetamodelValidationError(ValueError)` is raised by `seal()` and carries an
  immutable sequence of `m-metamodel`'s
  `MetamodelIssue(code, location, related, message)` values. The aggregate
  error belongs to `m-model-formation` and does not translate issue types.
- `MetamodelStateError(RuntimeError)` covers use of an unsealed or rejected
  hub, direct use of an Entity Class that is not bound to a sealed hub,
  same-thread seal re-entry, and an atomic Entity Class claim collision. The
  stable codes are `metamodel-unsealed`, `metamodel-rejected`,
  `metamodel-class-not-bound`, `metamodel-seal-reentrant`, and
  `metamodel-class-already-bound`. A rejected-state error exposes the terminal
  seal failure as its cause. A claim collision exposes every conflicting
  Entity Identity in canonical order; it is neither a
  `MetamodelValidationError` nor a `FormationContractError`.
- `MetamodelLookupError(LookupError)` covers only a failed developer-facing
  `models.meta(...)` lookup. It has stable codes
  `metamodel-invalid-entity-reference`, `metamodel-entity-not-found`, and
  `metamodel-class-not-bound`; the class-free lookup protocol never raises it.
- `QueryDefinitionError(ValueError)` covers only Find Query construction and
  refinement of intrinsically invalid shapes and combinations.
  `query-hub-mismatch` rejects mixed-hub operation nodes;
  `query-not-mutation-compatible` rejects a read-shaped Find Query passed to a
  predicate-selected write; and `query-assignment-target-mismatch` rejects an
  Assignment from another hub or Entity target. These fail before connection,
  SQL, adapter, or Unit of Work mutation. Database and adapter errors remain
  execution errors.
- `UnsupportedCapabilityError(RuntimeError)` distinguishes a valid operation
  from a capability unavailable on the connected provider. It has stable code
  `capability-unsupported` and a canonical core feature-tag `capability` such as
  `snapshot-history-includes`. The handle raises it after query/hub validation
  but before SQL generation or adapter access. It is never a
  `QueryDefinitionError`.
- `EditError(ValueError)` covers invalid `edit(...)` input and active rejection
  of inherited Pydantic copy paths. `Entity.model_copy(...)` always raises
  `EditError(code="edit-use-edit")`; it never creates an Entity value, even
  without an `update=` argument.
- Registry-collision, copy, provenance, and query-scope exception classes are
  removed or become private implementation details. Unsupported capability
  remains a distinct supported public classification.

### Metadata contract and descriptor interchange

- New core module `m-metamodel` specifies normalized declared metadata and
  model-relative lookup as a language-neutral interface.
- Read-only interface protocols use the full `Metadata` suffix, including
  base `EntityMetadata` and `AttributeMetadata` plus the `m-relationship`
  facet's derived `RelationshipMetadata`. The Python `*Meta` suffix is reserved
  for metaclasses; it is never an abbreviation for a metadata view. The old
  ambiguous `EntityMeta` / `EntityMetaView` introspection vocabulary is removed.
- Core **Entity Identity** is the structured `(namespace, name)` pair. It is
  unique within a Metamodel and has canonical qualified spelling
  `<namespace>.<name>`, or `<name>` when namespace is absent. Namespace absence
  is distinct from a named namespace; empty namespaces and dots in entity names
  are rejected so the final dot unambiguously separates name from a possibly
  dotted namespace.
- Accepted relationship targets, inheritance parents, operation targets,
  expression references, formation indexes, and facets carry Entity Identity,
  not unresolved strings. Python adds only the private binding from that core
  identity to an Entity Class.
- Core **Attribute Identity** is `(Entity Identity, attribute name)` and core
  **Relationship Identity** is `(source Entity Identity, relationship name)`.
  The `m-relationship` facet's Relationship Metadata stores a structured
  `RelationshipJoin(source: AttributeIdentity, target: AttributeIdentity)`.
  Join text exists only in descriptor authoring/serde. The old `foreignKey`
  hint is removed from the canonical descriptor, declaration API, and accepted
  metadata; cardinality and the join identify the many-side attribute where one
  exists.
- Direct Relationship Cardinality permits one-to-one, many-to-one, and
  one-to-many. Many-to-many is rejected: a single source/target join cannot
  represent the association Entity and two joins it requires. Applications
  declare that Entity and its two direct relationships explicitly until a
  future first-class Association Join specifies coherent read, write,
  ownership, and temporal semantics.
- Accepted cardinality is the closed semantic algebra
  `OneToOne | ManyToOne | OneToMany`. Each variant exposes
  `source: Multiplicity` and `target: Multiplicity`, where Multiplicity is One
  or Many. Descriptor and declaration adapters parse authored spellings;
  behavioral code never compares cardinality strings, and `ManyToMany` cannot
  be constructed.
- Core retains the full `EntityIdentity`, `AttributeIdentity`, and
  `RelationshipIdentity` names. `*Id` is reserved for instance primary-key
  values and is not used for identities of model declarations.
- `m-core` owns the closed `NeutralType` algebra and matching `NeutralValue`
  vocabulary shared by metadata, operation literals, assignments, and neutral
  rows. Accepted Attribute Metadata exposes these core values rather than
  defining metadata-specific equivalents. The Neutral Type variants are:
  `Boolean`, `Int32`, `Int64`, `Float32`, `Float64`, `String`, `Bytes`, `Date`,
  `Time`, `Timestamp`, `Uuid`, `Json`, or `Decimal(precision, scale)`.
  Precision and scale are validated semantic components, not text to be parsed
  by consumers. Descriptor spellings such as `decimal(18,2)` exist only in
  authoring and serde; behavioral modules never receive or inspect type strings.
  A Neutral Value is a value drawn from its declared Neutral Type's logical
  value space (`m-core`); there is no tagged wrapper type, and null belongs to
  no value space — a position admits null only through its own contract, such
  as a `nullable` member.
  The `Json` space is an immutable structured tree that excludes a
  bare top-level null. An implementation uses idiomatic immutable
  host-language values while preserving the logical type.
- Primary-Key Generation is the structured
  `ApplicationAssigned | Max | Sequence(name, batch_size, initial_value,
  increment_size)` algebra. Attribute primary-key state is the sum
  `NotPrimaryKey | PrimaryKey(PrimaryKeyGeneration)`. Sequence values have all
  descriptor omissions replaced by their semantic defaults before acceptance;
  an omitted allocator on a primary key becomes
  `PrimaryKey(ApplicationAssigned)`. A non-primary-key Attribute cannot carry a
  generation value.
- An Entity declares its physical **Storage Container** once; member locations
  never repeat that container. The initial accepted algebra is:

  ```text
  StorageContainer = Table(name: string)
  ```

  Python `table=` and canonical descriptor `table` remain terse authoring forms
  that normalize to `Table(name)`. `DocumentCollection(name)` is the reserved
  future container variant but is not constructible in the current contract.
  Pushing a table or collection into every member Storage Location is rejected
  because it would duplicate Entity-wide truth and permit contradictory member
  mappings.
  [Future Document Storage Sketch](parallax-future-document-storage-sketch.md)
  preserves the provisional relational-document and document-collection
  configurations without making them part of the current contract.
- A mapped top-level member exposes its physical **Storage Location** rather
  than an unconditional column-name string. The initial algebra has one
  accepted variant:

  ```text
  StorageLocation = Column(name: string)
  ```

  The structural algebra is deliberate even while only direct columns are
  supported: member identity remains independent of physical placement, and a
  future document-storage change can add the reserved variant without
  redefining Attribute or Value Object identity:

  ```text
  DocumentRoot = Column(name: string) | ContainerDocument

  DocumentPath(
    root: DocumentRoot,
    path: nonempty sequence<string>,
  )
  ```

  A document in a relational structured column uses `Column(name)` as its
  root; a record that is itself a document uses `ContainerDocument`. The root
  and ordered path segments always travel in that one structured value. Dotted
  strings, JSON Pointers, and string/tuple concatenation are not alternate
  representations. `DocumentRoot`, `ContainerDocument`, and `DocumentPath` are
  reserved but not constructible in the current accepted contract or authoring
  surface.
- Python applies storage conventions at its authoring edge. An Entity scalar
  `name: Attr[str]` normalizes to `Column("name")`, and a top-level Value Object
  occurrence `address: Attr[Address]` normalizes to `Column("address")`.
  `attr(column="legacy_name")` is only the direct-column override. Omitted
  authoring configuration never becomes absent Storage Location in accepted
  Metadata. A future document-oriented Entity may analogously derive a
  `DocumentPath(Column(document_column), logical_containment_path)` from its
  one Entity-level document declaration and ordinary member names. A future
  document collection instead uses
  `DocumentPath(ContainerDocument, logical_containment_path)`. Neither every
  member nor every nested path should require configuration. A top-level Value
  Object occurrence would own the path to its object root. Nested members would
  still own no Storage Location; a physical consumer would derive their full
  address as another `DocumentPath` by appending the nested member identities
  to that root path.
- The canonical descriptor applies the same direct-column convention. Its
  `column` authoring member is omitted when the physical column exactly equals
  the Attribute name or top-level Value Object occurrence name, and is present
  only for an override. The descriptor adapter expands either form to explicit
  `Column(name)` before exposing an Unresolved Metamodel; canonical export
  omits a conventional `column` again. Descriptor terseness therefore does not
  introduce absent Storage Location into the Metamodel Interface.
- Attribute Metadata has the exact normalized contract below. It is
  self-identifying and does not duplicate `identity.name` as a separate field:

  ```text
  AttributeMetadata
    identity: AttributeIdentity
    type: NeutralType
    storage: StorageLocation
    primary_key: NotPrimaryKey | PrimaryKey(PrimaryKeyGeneration)
    nullable: boolean
    max_length: integer | absent
    read_only: boolean
    optimistic_locking: boolean
  ```

  Value Object Attribute Metadata is not this protocol: nested values have no
  Entity identity, Storage Location, generation, or locking facts.
- Core **Index Identity** is `(Entity Identity, index name)`, and Index Metadata
  has the exact contract:

  ```text
  IndexMetadata
    identity: IndexIdentity
    attributes: nonempty sequence<AttributeIdentity>
    unique: boolean
  ```

  Every component belongs to the Index Identity's entity, appears once, and
  preserves declaration order. Indexes are local and never inherited. They do
  not repeat column names; physical consumers resolve columns through Attribute
  Metadata's Storage Location. `unique` remains because it governs schema
  constraints and cache fast paths as well as physical tuning.
- Core recognizes the closed Temporal Dimension algebra
  `ValidTime | TransactionTime`. A dimension is itself the identity of an
  Entity's As-Of Axis; there is no separately authored axis name, identity, or
  kind. As-Of Axis Metadata has the exact normalized contract:

  ```text
  AsOfAxisMetadata
    dimension: TemporalDimension
    start_attribute: AttributeIdentity
    end_attribute: AttributeIdentity
  ```

  Both attributes belong to the containing Entity, have Timestamp Neutral
  Type, and form the fixed half-open interval `[start, end)`. Model Formation
  permits at most one axis per dimension. Valid Time conventionally uses
  `valid_start`/`valid_end` mapped to `from_z`/`thru_z`; Transaction Time uses
  `tx_start`/`tx_end` mapped to `in_z`/`out_z`. The physical column names do
  not define or identify either dimension.
- As-Of Axis Metadata contains no query-default member. `m-temporal-read` owns
  the one defaulting rule: an omitted dimension means Latest and lowers to
  `end = infinity`. Latest is an open-edge coordinate, not the current clock
  instant. `Now`, if explicitly exposed by a language API, means one finite
  current instant resolved once for the operation and lowers to
  `[start, end)` containment; neither descriptor serde nor an operation may use
  `now` as an alias for Latest.
- Declaration and accepted Inheritance use one parent-parameterized closed
  local-declaration algebra:

  ```text
  Inheritance<Parent> =
      AbstractRoot(strategy: InheritanceStrategy)
    | AbstractSubtype(parent: Parent)
    | ConcreteSubtype(
          parent: Parent,
          tag_value: string | absent,
      )

  InheritanceMetadata = Inheritance<EntityIdentity>

  InheritanceStrategy =
      TablePerHierarchy(tag_column: string)
    | TablePerConcreteSubtype
  ```

  `Inheritance<Parent>` is specification notation for the shared algebra, not
  a third runtime form or public authoring concept. An Unresolved Entity
  Declaration instantiates it with Entity Reference; `InheritanceMetadata`
  names the accepted Entity Identity specialization. Resolution changes only
  each descendant's parent from Entity Reference to Entity Identity; it
  neither rebuilds nor reinterprets the variants. The variant is the role;
  there is no
  separate role field. Roots cannot carry parents, descendants cannot repeat
  strategy, and only Table Per Hierarchy can carry a tag column. Storage
  Containers remain solely in
  `EntityMetadata.declared_container`; the current inheritance strategies
  require those containers to be `Table`. A Concrete Subtype's local
  `tag_value` is
  required under its root's Table Per Hierarchy strategy and absent under Table
  Per Concrete Subtype; Model Formation validates that family-relative rule.
  The Metamodel Interface does not copy the root strategy onto descendants.
- Resolved `m-op-algebra` nodes reuse Attribute Identity instead of dotted
  strings, but a Relationship Join remains distinct from an executable
  `Comparison`: the former is static attribute-to-attribute mapping equality,
  while the latter is an attribute-to-literal query condition. This preserves
  `m-op-algebra -> m-metamodel` and creates no reverse dependency.
- An authored bare Entity Reference with a declaring entity resolves only in
  that entity's namespace; a qualified reference resolves exactly. An
  ownerless string reference, including an operation target or direct
  `models.meta("...")` lookup, must be qualified when its target is namespaced.
  No lookup falls back to a globally unique bare name.
- The foundational Model Formation gate resolves Unresolved Metamodel
  relationship and inheritance references to Entity Identity. It either
  reports all foundational resolution issues or produces a Candidate Metamodel
  with no reference/identity unions. Canonical descriptor and operation export
  always emits qualified spelling for namespaced identities, even when the
  authored reference was namespace-relative.
- Entities form a true set and are canonically enumerated by ascending
  `(namespace or "", name)`, compared codepoint by codepoint. This order governs
  `models.entities`, canonical descriptor entity arrays, formation iteration,
  identity-keyed diagnostics, and family sibling sets; constructor, file, and
  import order are not semantic.
- Local member collections are declared sequences and preserve authoring order
  through normalization, introspection, formation, and canonical export. This
  includes attributes, relationships, Value Objects and recursive members,
  indices, As-Of Axes, composite-key components, index components, and
  relationship ordering clauses. They are never alphabetized merely to appear
  canonical.
- Every entity view contains only facts declared at that entity position. It
  never copies inherited attributes, relationships, Value Objects, persistence,
  axes, table mappings, or other effective facts onto descendants. References
  are normalized to canonical entity identity, but semantic owner modules
  derive their consequences.
- Optional Attribute Metadata properties use ordinary absence
  when null is not a valid value, and properties with semantic defaults
  normalize omission to the default value. There is no tagged value wrapper,
  generic `Optional`, `Presence`, descriptor `Unset`, or public parser
  sentinel in the interface.
- Recursive Value Object metadata uses three distinct read-only protocols:

  ```text
  ValueObjectIdentity =
    (EntityIdentity, nonempty containment path: sequence<string>)

  ValueObjectAttributeIdentity =
    (ValueObjectIdentity, attribute name)

  ValueObjectMetadata
    identity: ValueObjectIdentity  # path length = 1
    storage: StorageLocation
    multiplicity: Multiplicity
    nullable: boolean
    attributes: ValueObjectAttributeMetadata[]
    value_objects: NestedValueObjectMetadata[]

  NestedValueObjectMetadata
    identity: ValueObjectIdentity  # path length >= 2
    multiplicity: Multiplicity
    nullable: boolean
    attributes: ValueObjectAttributeMetadata[]
    value_objects: NestedValueObjectMetadata[]

  ValueObjectAttributeMetadata
    identity: ValueObjectAttributeIdentity
    type: NeutralType
    nullable: boolean
  ```

  Only the top-level Value Object occurrence owns a Storage Location. Under
  the initial `Column` variant, that location is a Structured Column. A nested
  object has no storage location of its own, and an inner attribute cannot
  represent Entity-only storage, generation, or locking facts. Metadata does
  not duplicate the final path segment as a separate name. Every recursive
  collection preserves declaration order. There is no `mapping` member or
  authored `mapping="json"`: structured-column storage is the only initially
  supported semantics, and each dialect derives its concrete JSON-like
  database type directly from Value Object Metadata. A genuinely different
  future storage
  representation requires a structured strategy and corresponding behavior.
  Both object shapes reuse the same `Multiplicity = One | Many` algebra used
  inside Relationship Cardinality. One means a single embedded object; Many
  means an ordered collection in the same Structured Column. There is no
  separate Value Object Cardinality or collection flag. Nullability is valid
  only with One: `One + false` is `T`, `One + true` is `T | null`, and Many is
  a non-null ordered collection that may be empty. Model Formation rejects
  `Many + nullable`; an empty collection is the only zero-element
  representation.
- Every container has one navigable local-member namespace. Entity attributes,
  relationships, and top-level Value Objects have mutually unique names. Value
  Object scalar attributes and nested Value Objects likewise have mutually
  unique names at each recursive position. The standard temporal attributes
  reserve `valid_start`, `valid_end`, `tx_start`, and `tx_end` when their
  corresponding framework base supplies them. Model Formation rejects every
  cross-category collision for both frontends. Index names remain separate
  because indices are not navigable members; Temporal Dimensions remain
  separate structured keys rather than member names.
- Inheritance extends the navigable namespace through every ancestry chain. A
  descendant cannot redeclare an ancestor attribute, relationship, or Value
  Object name, including an identical declaration or a cross-category shadow.
  Disjoint sibling branches may independently reuse a name because no concrete
  ancestry contains both. Model Formation emits the stable
  `inheritance-member-shadowing` issue with the descendant and original
  declaration identities. Effective owner facets therefore need no override
  precedence or compatibility rules.
- Every top-level and nested Value Object declaration is nonempty: its
  `attributes` and `value_objects` collections may each be empty independently,
  but not together. Consequently every finite containment tree reaches at
  least one scalar leaf. Model Formation reports the stable
  `value-object-empty` issue for either frontend; empty `{}` composites and
  collections of empty composites are not model shapes.
- Value Object type dependencies form an acyclic graph. Reusing the same Value
  Object class at multiple containment paths is valid; normalization expands
  each occurrence into distinct path-identified metadata. Direct and indirect
  cycles are invalid because the accepted metadata and canonical descriptor are
  finite occurrence trees. Model Formation reports
  `value-object-containment-cycle` with the complete cycle. The design does not
  introduce lazy, depth-bounded, or named recursive-type semantics.
- The active `m-relationship` module owns relationship formation. Its Rule Set
  validates the accepted local Relationship Declarations, and its Model
  Compiler produces the immutable Relationship Facet:

  ```text
  RelationshipFacet
    relationship(RelationshipIdentity) -> RelationshipMetadata | absent
    relationships(EntityIdentity)
      -> immutable sequence<RelationshipMetadata> | absent
  ```

  `relationship(...)` is total and nonthrowing, returns absent for an unknown
  Relationship Identity, and has expected amortized O(1) lookup. For
  `relationships(...)`, an unknown Entity Identity returns absent, while a
  known Entity with no relationships returns an empty sequence. Per-Entity
  enumeration preserves local Relationship Declaration order. Every accepted
  declaration produces exactly one directional Relationship Metadata value; a
  paired association therefore contributes one value to each source Entity's
  enumeration. The facet exposes neither global relationship enumeration nor
  a separate reverse-pair lookup.

  Navigation, deep fetch, cascade behavior, SQL correlation, and graph
  materialization consume this facet rather than re-pairing declarations. The
  generic Metamodel contains the facet but does not interpret it.
- Relationship Metadata in that facet has the normalized member contract:

  ```text
  identity: RelationshipIdentity
  cardinality: RelationshipCardinality
  join: RelationshipJoin(source, target)
  reverse: string | absent
  dependent: boolean
  order_by: RelationshipOrder[]
  ```

  `identity.source_entity` equals `join.source.entity`. The target is
  `join.target.entity` and is not repeated. `reverse` is a validated local
  relationship name scoped to that target; repeating either the target entity
  or full target Relationship Identity would be redundant. Model Formation
  proves the reverse exists and is coherent before acceptance.
  `RelationshipOrder` contains an Attribute Identity and direction, preserving
  declaration order. Its exact shape is
  `RelationshipOrder(attribute: AttributeIdentity,
  direction: SortDirection)`, where Sort Direction is
  `Ascending | Descending`. The attribute belongs to the join target and order
  terms are valid only when target Multiplicity is Many. Omitted authored
  direction normalizes to Ascending; empty `order_by` means no ordering and no
  emitted `ORDER BY`. There is no `Unspecified` direction. Neither join nor
  ordering consumers parse dotted strings or direction strings.
- Descriptor relationship authoring is also a closed two-form union. The
  defining form contains `name`, `cardinality`, `join`, optional `dependent`, and
  optional `orderBy`. The reverse form contains `name`, qualified `reverseOf`,
  and optional `orderBy`; it contains no join, cardinality, dependency, or
  separate target. Foundational resolution preserves those forms as local
  Relationship Declarations. After validation, the `m-relationship` Model
  Compiler swaps the join, inverts cardinality, and installs symmetric
  target-scoped `reverse` names in its facet. Canonical export reads the
  preserved declarations rather than reconstructing authoring from the facet.
- New core module `m-model-formation` specifies the Model Formation Rule Set,
  Model Compiler, Formation Profile, deterministic resolve-validate-compile
  runner, module-owned facet contract, aggregate validation error, and
  Formation Contract Error. It imports `MetamodelIssue` from `m-metamodel` and
  no contributing semantic module.
- New active core module `m-relationship` owns relationship formation rules,
  stable `relationship-*` issue codes, the Relationship Facet, and its compiler.
  It depends on `m-metamodel` and `m-model-formation`; `m-navigate` and other
  behavioral consumers depend on it.
- Behavioral modules depend on `m-metamodel`, not on descriptor record classes,
  unless serialization is their concern.
- Only modules that own model-formation rules or effective compilation
  additionally depend on `m-model-formation` and contribute the corresponding
  implementation. Behavioral modules with neither do not acquire that
  dependency.
- Effective relationship, inheritance, temporal, navigation, SQL, and write
  semantics remain
  owned by their existing modules. Stable effective metadata may be compiled
  once into those modules' immutable facets; `m-metamodel` does not absorb it.
- `m-descriptor` continues to own the exact canonical JSON/YAML document,
  schema, deterministic serde, corpus interchange, and export adapter.
- Class and descriptor frontends each expose an Unresolved Metamodel input
  view. The shared compiler produces the one accepted Metamodel and lookup
  indexes. A class-backed hub delegates that object and adds Entity Class
  bindings; a descriptor-backed hub delegates it without bindings. Neither hub
  implements a separate accepted Metadata graph or owns independent normalized
  accepted-metadata indexes.
- The conformance guard compares the two frontends through interface behavior
  and canonical descriptor export.
- Canonical TPH metadata declares `table` once on the Abstract Root alongside
  its inheritance block. Concrete subtypes do not repeat it. The root remains
  non-instantiable and rowless but owns the family's shared physical mapping.
  TPCS continues to declare one table on each concrete subtype.
- Temporal declarations use the glossary's **As-Of Axis** term consistently.
  The core metadata protocol exposes `AsOfAxisMetadata` and `as_of_axes`, and
  the canonical descriptor key is `asOfAxes`. Python authors select
  `TxTemporal` or `Bitemporal` and do not construct or import a public
  `AsOfAxis` authoring value. The inaccurate `AsOfAttribute` /
  `asOfAttributes` vocabulary is retired across specs, schema, corpus,
  implementation, and tests.

### Hub-owned introspection and export

- `models.meta(Order)` and `models.meta("sales.Order")` provide model-relative,
  read-only declaration-metadata lookup and return the public `EntityMetadata`
  protocol.
- `models.meta(EntityIdentity("sales", "Order"))` is the non-string lookup form.
  String lookup parses canonical qualified spelling; a bare string can resolve
  only an unnamespaced identity.
- A malformed string raises `MetamodelLookupError` with code
  `metamodel-invalid-entity-reference`; an absent identity uses
  `metamodel-entity-not-found`; a supplied class outside this hub uses
  `metamodel-class-not-bound`. These checks occur only after the sealed-state
  check and before adapter work.
- `models.entities` is the immutable, canonical-order sequence of
  `EntityMetadata` views.
- Entity metadata and its nested attribute, relationship, value-object,
  temporal, and inheritance declarations are read-only protocols. The
  class-backed and descriptor-backed concrete adapters are private and neither
  frontend constructs the other's record types.
- `EntityMetadata` is deliberately local, not an effective or flattened class
  view. Inheritance, temporal, navigation, SQL, and write modules compute their
  effective views from the accepted Metamodel and remain their sole owners.
- Every Entity Metadata property whose effective value may differ through
  inheritance uses the `declared_` prefix. Its exact contract is:

  ```text
  EntityMetadata
    identity: EntityIdentity
    declared_container: StorageContainer | absent
    declared_persistence: PersistenceMode | absent
    declared_attributes: sequence<AttributeMetadata>
    declared_relationships: sequence<RelationshipDeclaration>
    declared_value_objects: sequence<ValueObjectMetadata>
    declared_as_of_axes: sequence<AsOfAxisMetadata>
    inheritance: InheritanceMetadata | absent
    indices: sequence<IndexMetadata>
  ```

  Name and namespace are available only through `identity` and are not
  duplicated. Persistence Mode is the closed `ReadWrite | ReadOnly` algebra
  and describes persistence capability, never in-memory mutation, security
  access, or transaction participation. A standalone entity or family root
  normalizes omitted persistence to ReadWrite. On a descendant, absent
  `declared_persistence` means inherit and remains absent in this local view;
  presence is a model-formation error. The inheritance facet supplies the one
  effective root-owned value for every family position.
  Index Metadata appears last because it is
  physical access-path and runtime-optimization metadata rather than structural
  model shape. Every sequence is immutable and preserves declaration order.
  There is no unqualified `table`, `persistence`, `attributes`, `relationships`,
  `value_objects`, or `as_of_axes` alias. `indices` and `inheritance` remain
  unqualified because they have no separate inherited/effective value.
- The class-free accepted Metamodel direct-lookup contract is:

  ```text
  Metamodel.entity(EntityIdentity) -> EntityMetadata | absent
  EntityMetadata.attribute(local_name) -> AttributeMetadata | absent
  EntityMetadata.relationship(local_name) -> RelationshipDeclaration | absent
  EntityMetadata.value_object(local_name) -> ValueObjectMetadata | absent
  EntityMetadata.as_of_axis(TemporalDimension) -> AsOfAxisMetadata | absent
  EntityMetadata.index(local_name) -> IndexMetadata | absent
  ValueObjectMetadata.attribute(local_name)
    -> ValueObjectAttributeMetadata | absent
  ValueObjectMetadata.value_object(local_name)
    -> NestedValueObjectMetadata | absent
  NestedValueObjectMetadata.attribute(local_name)
    -> ValueObjectAttributeMetadata | absent
  NestedValueObjectMetadata.value_object(local_name)
    -> NestedValueObjectMetadata | absent
  ```

  It accepts no string or Entity Class overload, returns ordinary absence on a
  miss, and inspects local declarations only. Every direct lookup has expected
  amortized `O(1)` complexity through a private immutable index. Enumeration is
  separate and retains its canonical or declaration order.
- `EntityMetadata` exposes no derived `temporal`, `is_temporal`,
  `primary_key`, `column_order`, or effective-member convenience. Those
  computations stay with their semantic owner modules.
- `models.meta(...)` never switches to a generic flattened view after sealing.
  A concrete ancestry, abstract-position projection superset, family identity,
  and physical column set are different effective questions, not one
  `effective_attributes` collection. The owning compiled facet exposes each
  typed answer through the exact facet protocols in `m-inheritance`
  ("The Inheritance Facet"), `m-temporal-read` ("The Temporal Facet"), and
  `m-opt-lock` ("The Optimistic Lock Facet"); Python reaches them through each
  owner package's `view(model)` function with structured Entity Identities:

  ```text
  inheritance.view(models).entity(card_payment).applicable_attributes
  inheritance.view(models).entity(payment).superset_attributes
  inheritance.view(models).position(narrow_members).superset_value_objects
  temporal_read.view(models).shape(payment)
  opt_lock.view(models).key(card_payment)
  ```

  The per-Entity lookups (`entity(...)`, `shape(...)`, `key(...)` and their
  view members) are expected amortized constant-time reads of immutable
  formation output; `position(...)` constructs its view at output-sensitive
  cost — linear in the member count plus the returned view's size
  (`m-inheritance`). None repeats an ancestry walk at query or write time.
- The exact internal facet attachment contract is:

  ```text
  FacetKey<T>
    owner: canonical module-catalog identity

  Metamodel
    entities: immutable sequence<EntityMetadata>
    entity(EntityIdentity) -> EntityMetadata | absent
    facet(FacetKey<T>) -> T
  ```

  `facet(...)` is total for every key required by the accepted Formation
  Profile. It is an internal first-party collaboration seam, not a developer
  convenience. Each owner module retains its key and exposes typed operations
  such as `inheritance.view(models)`; callers do not enumerate facets or
  construct keys. The accepted Metamodel stores no contributor objects and the
  runner creates no ambient registry.
- `models.to_descriptor()`, `models.to_json()`, and `models.to_yaml()` perform
  explicit canonical representation conversion. Export is a method rather
  than a `.descriptor` property because it may allocate a complete document.
  An unsealed or rejected hub raises `MetamodelStateError`; every sealed
  Metamodel is exportable by contract without renewed validation or state
  change. Repeated document exports are structurally equal, and repeated JSON
  or YAML exports are byte-identical.
- Export is pure and returns its complete result or raises; it emits no partial
  output. An unexpected conversion or serialization defect raises
  `DescriptorExportError(code="descriptor-export-failed")`, carrying target
  `document | json | yaml` and the original cause. The hub remains `SEALED`.
  Sealing neither performs export nor caches a mirrored canonical descriptor
  graph; canonical output is derived from the accepted Metamodel on demand.
- There is no global `meta`, `meta_of`, `metamodel(classes)`,
  `entity_record_of`, `entity_records`, `descriptor_document`, registry helper,
  `Order.meta()` convenience, or public concrete metadata-record graph.
- Canonical descriptor documents and JSON/YAML are exports of the sealed hub,
  not its required in-memory representation.

### Query values and expressions

- The developer query value is named **Find Query**, represented as
  `FindQuery[T]`; `Statement` is retired from this surface.
- `Entity.where(...)` remains the query root. There is no competing
  `hub.find(...)` builder.
- Direct class-level expressions remain idiomatic:
  `Order.status == "OPEN"`, not `Order.fields.status == "OPEN"`.
- The declaration metaclass installs thin typed field and relationship
  descriptors. Expression and query behavior lives outside the metaclass.
- A `Predicate` is the lower-level typed filter expression consumed by a Find
  Query; it is not the name of the whole query.
- A Predicate is a non-executable boolean condition. A Find Query adds the
  target, hub identity, predicate, includes, narrowing, ordering, limit,
  distinctness, and temporal coordinates and is therefore the value accepted
  by `find`.
- Every `AttributeExpr`, `RelationshipPath`, `Predicate`, `Assignment`,
  `SortKey`, and `FindQuery` carries the opaque exact identity of the sealed hub
  that resolved it. Narrowing preserves the path's hub. Neutral literal and
  assignment values have no hub identity by themselves; incorporation into an
  operation node adopts the tagged expression's hub.
- Every operation-node constructor checks all tagged children and raises
  `QueryDefinitionError(query-hub-mismatch)` immediately on disagreement.
  Cross-hub composition therefore fails before a Database, Transaction, SQL
  generator, or adapter observes the operation.

### Predicate-selected writes

- The five predicate-selected verbs are `update_where`, `delete_where`,
  `terminate_where`, `update_until_where`, and `terminate_until_where`.
  `insert` has no predicate-selected form.
- They accept the same ordinary `FindQuery[T]` produced by
  `Entity.where(...)`; there is no public Mutation Target, Selection, Criteria,
  Statement, or second builder. A Find Query is mutation-compatible only when
  it contains exactly target, hub identity, and predicate. Includes, ordering,
  limit, distinctness, narrowing, temporal read clauses, history/range, or any
  other result-shaping state make it read-shaped and cause
  `QueryDefinitionError(query-not-mutation-compatible)` before Unit of Work or
  adapter access.
- Each `_where` verb privately normalizes a mutation-compatible Find Query to a
  `PredicateSelection(target, predicate, hub_identity)`. This is an ephemeral
  implementation value, not an exported operation model, authoring surface, or
  second serialized query representation.
- `update_where` and `update_until_where` require one or more Assignments;
  `delete_where`, `terminate_where`, and `terminate_until_where` accept none.
  Every Assignment carries the same exact hub identity and must target a member
  of the Find Query's exact Entity. A mismatch raises
  `QueryDefinitionError(query-assignment-target-mismatch)` while combining the
  inputs at the transaction method, before buffering, SQL, or adapter access.
- After composition succeeds, the Transaction still requires identity with its
  Database handle's hub. Structural Metamodel equality never substitutes for
  exact hub identity.

### Handles and execution

- `Database.connect(adapter, models)` requires a successfully sealed,
  class-backed hub and permanently pairs the handle with it.
- Transactions inherit that hub from their database handle.
- `find(query)` requires the query's hub to be identical to the handle's hub;
  structural metadata equality is insufficient.
- Cross-hub execution fails before adapter access or SQL generation.
- After query validity and identical-hub checks, execution compares the
  operation's required canonical core feature tags with the connected
  provider's captured capability set. A missing capability raises
  `UnsupportedCapabilityError(capability-unsupported)` naming the feature tag
  before SQL generation or adapter access. Valid-but-unavailable operations are
  never reclassified as invalid queries.
- Handles never infer model scope from a query and never consult ambient state.

### Transaction demarcation ownership

- The outermost `Database.transact(...)` demarcation stores a strong reference
  to the exact originating `Database` object beside its Transaction and resolved
  options. This owner is scoped to the active demarcation; it is not a registry,
  hub property, adapter property, or structural Database identity.
- A nested `transact(...)` call joins only when invoked through that exact
  object (`requested_database is active_owner`). An alias of the same object
  joins and receives the identical Transaction. Any other Database instance is
  rejected even when it uses the same sealed hub, adapter object, dialect,
  clock, or equivalent configuration, because those values do not make it the
  owner of the active connection/flush/retry boundary.
- A mismatch raises exported
  `TransactionOwnershipError(RuntimeError)` with stable code
  `transaction-owner-mismatch` before option comparison, rollback-only joining,
  closure execution, Unit of Work mutation, SQL, or adapter access. The error
  retains neither Database object. A non-Parallax active Unit of Work retains
  its existing distinct error.
- Once exact owner identity succeeds, existing joining semantics are unchanged:
  rollback-only foreclosure and option-conflict checks apply, the inner closure
  receives the same Transaction, no savepoint or nested database transaction is
  created, and the outermost boundary alone owns commit, abort, and retry.

### Snapshot collaboration

- Graph-local identity reuse, closed-world loaded/unloaded relationships,
  narrowed relationship views, whole-graph pins, and milestone edges are
  Snapshot-slice state. The common Entity implementation defines no generic
  `_graph_state` module or lifecycle-neutral graph-state container.
- A future managed-object slice owns a different transaction-scoped state
  model: Identity Map membership, operation-backed relationship resolution,
  mutation, deletion, and detachment. Snapshot state is not reused or extended
  for that surface.
- `m-deep-fetch` remains the shared fetch algorithm and the Metamodel provides
  shared Relationship Identities, narrowed-view keys, and temporal coordinates;
  neither shared layer owns a lifecycle result-state container.

- Entity Class bindings are Python realization data and are not part of the
  language-neutral Metamodel Interface.
- `parallax.snapshot` owns `SnapshotGraphMaterializer`,
  `SnapshotGraphInput`, and `SnapshotNodeInput`. The materializer owns
  graph-local logical identity and projection merging, broad and narrowed
  loaded-state decisions, whole-graph pin and milestone-edge decisions, and
  the transient merge index required while associating projections. It is not
  a `parallax.core.entity` capability.
- Snapshot graph input is already associated and structured rather than a row
  batch or fetch plan:

  ```text
  SnapshotGraphInput
    roots: ordered sequence<SnapshotNodeInput>
    pin: whole-graph temporal coordinates

  SnapshotNodeInput
    concrete_entity: EntityIdentity
    attributes: AttributeIdentity -> null | NeutralValue
    value_objects: structured occurrence values
    relationship_views:
      RelationshipViewKey -> null | one node | ordered nodes

  RelationshipViewKey =
      Broad(RelationshipIdentity)
    | Narrowed(RelationshipIdentity, canonical effective concrete set)
  ```

  Node references may be shared or cyclic, and separate input nodes may carry
  different projections of one logical identity. The Snapshot materializer
  treats the input as read-only, groups and merges those projections using the
  Metamodel and graph pin, and preserves root and to-many order. An absent
  relationship-view key means unloaded; a present null or empty sequence means
  loaded-null or loaded-empty respectively.
- `parallax.core.entity` instead provides one advanced concrete
  `EntityGraphConstruction` capability. It is backed by the Metamodel Binding,
  is not a protocol with interchangeable adapters, and is not re-exported from
  top-level `parallax.core`. Its complete interface is:

  ```text
  EntityGraphConstruction
    construct(build: EntityGraphWriter -> ordered sequence<NodeHandle>)
      -> ordered sequence<Entity>

  EntityGraphWriter
    allocate(concrete_entity: EntityIdentity) -> NodeHandle
    populate(
      node: NodeHandle,
      attributes: AttributeIdentity -> null | NeutralValue,
      value_objects: structured occurrence values,
      relationships:
        RelationshipIdentity ->
          Unloaded
          | LoadedNull
          | LoadedOne(NodeHandle)
          | LoadedMany(ordered sequence<NodeHandle>),
      lifecycle_state:
        absent
        | (EntityGraphResolution -> opaque object),
    ) -> None

  EntityGraphResolution
    entity(node: NodeHandle) -> Entity

  relationship_value_of(
    value: Entity,
    relationship: RelationshipIdentity,
  ) -> Unloaded | LoadedNull | LoadedOne(Entity) | LoadedMany(ordered sequence<Entity>)

  lifecycle_state_of(value: Entity) -> opaque object | absent
  ```

  `NodeHandle` is opaque, graph-local, and valid only during its `construct`
  callback. The callback first allocates every node, then populates them; the
  first population closes the allocation phase. Each allocated handle is
  populated exactly once, relationship values may refer to any handle from the
  same construction, and every returned root must be one of the populated
  handles. After structural population, Entity invokes each optional lifecycle
  state factory with a read-only resolution view over the same construction.
  A factory may resolve handles to their final Entity instances but cannot
  allocate, populate, or publish them. These rules provide cycle closure and
  lifecycle attachment without exposing a partially constructed Entity graph.
- `construct(...)` publishes the ordered Entity roots only after the callback
  returns successfully and the complete graph passes construction checks. A
  callback or population failure returns no graph; any partially allocated
  instances remain unreachable. The capability owns concrete Entity Class
  selection, Pydantic allocation and population, canonical-to-Python member
  mapping, recursive Value Object construction, broad relationship-slot
  installation, and private storage of exactly one opaque lifecycle-state
  value per node. It neither interprets that value nor decides Snapshot
  identity merging, loaded state, narrowing, pins, or edges.
- Violations detected by Entity raise the advanced
  `GraphConstructionError(RuntimeError)` from `parallax.core.entity`. It has a
  stable `code`, optional zero-based `node_index`, optional structured Entity
  or member identity, and optional cause. Its complete code set is:

  ```text
  entity-graph-invalid-entity
  entity-graph-invalid-member
  entity-graph-allocation-closed
  entity-graph-scope-closed
  entity-graph-foreign-handle
  entity-graph-node-already-populated
  entity-graph-node-unpopulated
  entity-graph-invalid-root
  entity-graph-invalid-value
  ```

  Invalid Entity means the requested identity has no concrete class in this
  Metamodel Binding. Invalid member means an Attribute or Relationship Identity
  is unknown, belongs to another Entity, or appears in the wrong member map.
  Allocation closes with the first `populate`. Scope closed covers use of a
  retained writer after the build callback or a retained resolution view after
  its state factory. Foreign handle covers every writer, relationship, root,
  or resolution use of a handle from another construction. Duplicate and
  missing population are reported by allocation index; the first missing node
  is deterministic. Invalid root covers a non-handle root value; a local but
  unpopulated root uses `entity-graph-node-unpopulated`. Invalid value covers a
  Neutral Value, Value Object occurrence, relationship cardinality/null shape,
  or concrete-class construction value incompatible with accepted metadata and
  retains the underlying conversion cause when one exists.
- `GraphConstructionError` is never an assertion and is not re-exported from
  top-level `parallax.core`. Exceptions raised by the lifecycle build function
  or an opaque-state factory are not translated or wrapped by Entity; they
  propagate unchanged to their lifecycle owner while the construction still
  publishes nothing. Snapshot may classify such a cause only at its own public
  read boundary.
- `parallax.snapshot` owns and exports
  `SnapshotMaterializationError(RuntimeError)`. Once adapter execution and
  neutral graph production have succeeded, the Snapshot Graph Materializer
  wraps any escaping `GraphConstructionError` or build/state-factory exception
  as `SnapshotMaterializationError(code="snapshot-materialization-failed",
  cause=original)`, using normal Python exception chaining. It returns no
  partial Snapshot or Entity roots. An existing `SnapshotMaterializationError`
  is passed through rather than double-wrapped.
- Query-definition, unsupported-capability, transaction, adapter, SQL, and
  neutral decoding failures raised before Snapshot graph materialization retain
  their existing public classifications. Direct advanced callers of
  `EntityGraphConstruction` continue to receive the original construction or
  callback exception.
- `parallax.snapshot` defines the private `SnapshotNodeState` stored in that
  slot. It contains narrowed relationship views, whole-graph pin coordinates,
  and the node's optional milestone edge. Its narrowed values are created by
  the deferred state factory, which resolves Node Handles only after structural
  population. `Pin` and `Edge` remain core semantic value types, but
  `is_loaded`, `narrowed`, `pin_of`, and `edge_of` belong to and are exported
  by `parallax.snapshot`.
- Snapshot reads its state only through the advanced Entity collaboration
  operations `lifecycle_state_of(...)` and `relationship_value_of(...)`. The
  latter exposes a broad relationship slot without triggering lifecycle
  behavior. Snapshot verifies that the opaque value is `SnapshotNodeState`;
  passing a plain or future Managed Entity to a Snapshot inspection function
  is therefore rejected rather than misinterpreted.
- `is_loaded`, `narrowed`, `pin_of`, and `edge_of` first require the opaque
  state to be `SnapshotNodeState`, before path, relationship, or temporal
  validation. A plain Entity, a future Managed Entity, or any other lifecycle
  value raises exported `SnapshotInspectionError(ValueError)` with stable code
  `snapshot-node-required` and `operation` equal to the invoked function name.
  The error never exposes the opaque state value. In particular,
  `is_loaded(non_snapshot, ...)` does not return `False` because wrong lifecycle
  and a valid Snapshot's unloaded relationship are different conditions.
- After that common precondition, operation-specific semantics remain distinct:
  `is_loaded` returns a boolean, an unrequested `narrowed` view raises
  `UnloadedRelationshipError`, and unavailable node temporal state raises
  `SnapshotInspectionError` with operation-specific codes.
- On a valid Snapshot node, `pin_of` without node pin state raises
  `SnapshotInspectionError(code="snapshot-pin-unavailable",
  operation="pin_of")`; `edge_of` without node edge state raises
  `SnapshotInspectionError(code="snapshot-edge-unavailable",
  operation="edge_of")`. Both errors carry the node's structured Entity
  Identity and expose no private state. This covers a non-temporal node and
  defensively classifies an invariant-defective temporal node.
- `TemporalReadError` remains the core temporal query/lowering error family.
  `UndeclaredAxisError` remains the core error for requesting an axis a valid
  `Pin` or `Edge` value does not declare. Snapshot node inspection no longer
  overloads either condition.
- Broad descriptor access and `narrowed(...)` use the same structured
  closed-world error:

  ```text
  UnloadedRelationshipError(AttributeError)
    code: "entity-relationship-unloaded"
    view:
      Broad(RelationshipIdentity)
      | Narrowed(RelationshipIdentity, canonical effective concrete set)
  ```

  `parallax.core.entity._errors` defines the class so the Entity relationship
  descriptor can raise it without importing Snapshot. The advanced
  `parallax.core.entity` interface exposes it, while `parallax.snapshot`
  re-exports the identical class for ordinary Snapshot callers. Top-level
  `parallax.core` does not re-export it. `is_loaded` remains the nonthrowing way
  to test a valid Snapshot view before access.
- The lifecycle slot is singular and opaque. It is not a generic property bag,
  keyed extension map, shared graph-state protocol, callback registry, or
  lifecycle-neutral state model. A future Managed Object materializer supplies
  its own state factory and concrete state value.
- Snapshot explicitly calls `construct(...)` with a per-invocation build
  function. There is no module-global or lifecycle-keyed callback registry,
  import-time enrollment, discovery mechanism, or mutable callback table. A
  future Managed Object materializer can supply a different build function to
  the same capability without depending on or replacing Snapshot behavior.
- No second whole-graph `EntityGraphPlan` crosses the seam. Snapshot may retain
  the transient identity/projection merge index required by its own
  materializer, but it emits construction operations directly through the
  callback-scoped writer. No descriptor record, column/wire name, Pydantic
  value, or private slot name crosses this seam.
- `parallax.core.entity` also provides a separate first-party `EntityRowCodec`
  protocol with `full_row(value)`, `identity_row(value)`, and
  `edited_row(value)`. `edited_row` returns the canonical sparse row of identity
  plus effective changes, or `None` for a net-zero edit.
- At connection time, a sealed class-backed hub supplies an immutable Entity
  Graph Construction capability backed by its Metamodel Binding and an
  immutable row-codec view over the private row/provenance implementation.
  Neither capability duplicates model facts. Snapshot constructs and stores
  its own materializer with the Entity Graph Construction capability beside
  the Metamodel Interface and Entity Row Codec.
- Read materialization crosses only Entity Graph Construction; transaction
  write preparation crosses only the Entity Row Codec. Snapshot imports the
  advanced Entity construction interface but no registry, concrete Entity
  implementation module, Pydantic/private-slot, wire-name, row, or provenance
  helper. `parallax.core.entity` never imports `parallax.snapshot`.
- The declaration compiler installs canonical names as Pydantic validation and
  serialization aliases, so resolved classes carry their own Python-to-
  canonical field mapping without an exported `WireNames` side table.
- Descriptor-backed hubs cannot supply either capability and are rejected by
  `Database.connect` before any adapter work.

### Edited copies

- `Entity.edit(**changes)` produces a frozen Edited Copy of the same Entity
  Class with a private Change Record.
- `edit` is the object-copy verb; `update` remains the transaction persistence
  verb.
- Copies of copies retain the first-touched original value. Lowering emits only
  effective changes, and a net-zero edit emits no DML.
- Entity actively overrides Pydantic's broad `model_copy(...)`; every call,
  with or without `update=`, raises `EditError(edit-use-edit)` and creates no
  value. `edit(...)` is the sole authored copy-with-changes path.

## Target source topology

```text
parallax/core/
  _formation_profile.py

  metamodel/
    __init__.py

  model_formation/
    __init__.py
    _runner.py

  relationship/
    __init__.py

  descriptor/
    ...

  entity/
    __init__.py
    _binding.py
    _declaration.py
    _hub.py
    _entity.py
    _expressions.py
    _query.py
    _graph_construction.py
    _rows.py
    _members.py
    _value_object.py
    _errors.py

parallax/snapshot/
  _errors.py
  _graph.py
  _state.py
  handle/
    _database.py
```

`parallax.core.metamodel` is the class-free implementation seam for the
`m-metamodel` protocols, foundational resolver, Metadata Compiler, Compiled
Metadata, `MetamodelIssue`, and model-relative lookup contract.
`parallax.core.model_formation` owns the class-free rule-set, compiler, facet,
Formation Manifest and Formation Profile protocols, deterministic runner,
issue aggregation, and both `MetamodelValidationError` and
`FormationContractError`; it imports and owns no contributor implementation
set, and sees contributor identities only through supplied manifest data.
`parallax.core.relationship` owns the relationship Rule Set,
Model Compiler, symmetric Relationship Facet, and typed `view(model)` seam; it
does not own navigation execution. The private
`parallax.core._formation_profile` composition root supplies the immutable
built-in Formation Manifest data and complete built-in contributor profile;
the runner drift-checks the two and contract tooling checks manifest/catalog
consistency.
`parallax.core.descriptor` owns canonical document parsing, serde, and adapters
to and from that interface. Its public seam exposes `DescriptorError`,
`DescriptorSyntaxError`, `DescriptorSchemaError`,
`DescriptorSchemaViolation`, and `DescriptorExportError`; these are not
top-level `parallax.core` conveniences. `parallax.core.entity` is the sole supported Python
Entity frontend; its underscored modules are implementation details rather than
additional caller seams.

### Internal ownership

| Module | Ownership |
|---|---|
| `metamodel.__init__` | Read-only Unresolved Metamodel, Candidate Metamodel, Compiled Metadata, and accepted Metamodel protocols, foundational resolver, Metadata Compiler, Metamodel Issue, typed Facet Key, and model-relative lookup contract. |
| `model_formation.__init__` | Formation Manifest data, Model Formation Rule Set, Model Compiler, Metamodel Facet, Formation Profile, aggregate validation error, Formation Contract Error, and runner protocols. |
| `model_formation._runner` | Deterministic resolve-validate-compile execution, issue aggregation, and immutable facet assembly; no contributor imports or semantic rules. |
| `relationship.__init__` | Relationship formation rules and issue codes, symmetric Relationship Metadata compilation, typed Relationship Facet access, and no navigation execution. |
| `_formation_profile` | Private composition root containing immutable built-in Formation Manifest data and the explicit, manifest-complete built-in Rule Set and compiler tuple. |
| `entity._binding` | Atomic class-claim synchronization and the one immutable Metamodel Binding per sealed class-backed hub: opaque hub identity, accepted-Metamodel reference, bidirectional Entity Identity/Class index, and private strong owner reference. It owns no model facts, exposes no hub lifecycle surface, and provides no unbind/reset path. |
| `entity._declaration` | Shared lower-level Pydantic metaclass engine for Entity and Value Object classes, typed header/annotation parsing through `_members`, immutable declaration payloads and private kind markers, and immediate class-shape validation. It imports neither concrete frontend class nor expression behavior. |
| `entity._hub` | `MetamodelHub`, fixed-source construction, seal state, delegation to the one accepted Metamodel, adapter selection, class binding, introspection, and export orchestration. It owns no accepted Metadata/facet copies or independent normalized accepted-metadata indexes. |
| `entity._entity` | The small frozen `Entity` façade built on `_declaration`, plus delegation to Find Query and Edited Copy behavior. |
| `entity._expressions` | Pure immutable, hub-tagged operation nodes: Attribute Expressions, Relationship Paths including narrowing, Predicates, Assignments, and Sort Keys. Nodes receive hub identity and structured member identities explicitly, reject mixed-hub children, and perform no class lookup. |
| `entity._query` | `FindQuery`, its chainable clauses, hub-identity checks, canonical operation construction, mutation-compatibility validation, and private ephemeral Predicate Selection normalization. |
| `entity._graph_construction` | The concrete callback-scoped Entity Graph Construction capability, opaque Node Handles, two-phase structural allocation/population, deferred opaque lifecycle-state creation, atomic publication, concrete class selection, Pydantic mechanics, recursive Value Object construction, broad relationship-slot installation, and raw relationship/lifecycle-state access for first-party collaborators. It owns no lifecycle-specific graph semantics. |
| `entity._rows` | Entity-to-row translation, Edited Copy construction, Change Record merging, and effective-change calculation. |
| `entity._members` | Public `Attr`/`Rel` annotations, `attr`/`rel` declaration values, and the installed class/instance descriptors that turn bound members into operation nodes. It is the only runtime module in this cluster that touches owner classes. |
| `entity._value_object` | The frozen Value Object frontend built on the shared `_declaration` metaclass engine. |
| `entity._errors` | Entity declaration, hub lifecycle, binding, query-scope, graph-construction, and edited-copy errors. It is a strict leaf within the Entity cluster and accepts only structured error data. |
| `snapshot._errors` | Snapshot-owned public materialization and inspection errors. It is a strict Snapshot-package leaf, retains structured data and causes, and imports no Entity implementation module. |
| `snapshot._graph` | Snapshot Graph Input and Materializer, graph-local identity/projection merging, broad and narrowed loaded-state decisions, whole-graph pin and milestone-edge decisions, and direct emission through Entity Graph Construction. |
| `snapshot._state` | Private Snapshot Node State plus Snapshot-owned `is_loaded`, `narrowed`, `pin_of`, and `edge_of`; it interprets only Snapshot state obtained through the advanced Entity collaboration seam. |
| `snapshot.handle._database` | Database connection identity, exact-owner transaction demarcation, same-owner joining, and the outermost commit/abort/retry boundary. |

### Enforced direction

```text
behavioral modules ------------------------------> metamodel
descriptor --------------------------------------> metamodel
model_formation ---------------------------------> metamodel
formation-contributing modules ------------------> model_formation
_formation_profile ------------------------------> model_formation + contributors
entity._errors -------> metamodel
entity._declaration --> entity._members + entity._errors + metamodel
entity._value_object -> entity._declaration
entity._hub ---------> entity._declaration + entity._binding
entity._hub ---------> descriptor + metamodel + _formation_profile
entity._hub ---------> entity._graph_construction + entity._rows
entity._entity ------> entity._declaration + entity._binding
entity._entity ------> entity._query + entity._rows
entity._members -----> entity._binding + entity._expressions + entity._errors
entity._expressions -> metamodel + entity._errors
entity._query -------> entity._expressions + entity._binding + entity._errors
entity._graph_construction -> entity._binding + entity._entity
entity._graph_construction -> entity._value_object
entity._graph_construction -> entity._errors + metamodel
entity._rows --------> entity._binding
snapshot._graph -----> snapshot._state + snapshot._errors
snapshot._graph -----> entity._graph_construction + metamodel
snapshot._state -----> snapshot._errors + entity._graph_construction + metamodel
snapshot.handle._database -> snapshot._errors + metamodel
```

- `metamodel` never imports `descriptor` or `entity`.
- `model_formation` imports `metamodel` but never imports a contributing module;
  only `_formation_profile` knows the complete rule-set and compiler tuple.
- `descriptor` never imports `entity`.
- `_errors` imports only the standard library and class-free core
  identity/issue values. It imports no other `entity` implementation module,
  and its exceptions retain structured values rather than concrete hubs,
  bindings, classes, queries, Entities, or implementation callbacks. Every
  other Entity module may therefore depend on `_errors` without a return edge.
- `_declaration` owns two thin Pydantic metaclass paths over one shared engine.
  It recognizes Entity versus Value Object declarations through private kind
  markers installed by those metaclasses, not by importing the concrete
  classes, consulting a registry, or invoking registered callbacks.
- Both `_entity` and `_value_object` import `_declaration`; `_declaration` never
  imports either of them. It also never imports the hub, query builder,
  expression behavior, graph state, or row/provenance implementation.
- `_members` is the sole class-aware runtime bridge. Its installed descriptors
  resolve the owner's binding and construct operation nodes from explicit hub
  identity and structured member identities.
- `_hub` creates the Metamodel Binding and installs its claims through
  `_binding`, but `_binding` never imports or exposes the concrete hub type.
  Its private owner reference preserves binding lifetime while all claimed
  classes share the same Metamodel Binding, so the directed
  `_hub -> _binding` edge has no return edge. The hub also constructs the
  Entity Graph Construction and Entity Row Codec capabilities it supplies to a
  connection; neither implementation imports the hub.
- `_expressions` is a class-free operation-node algebra. It imports no
  `_members`, `_entity`, `_query`, or `_hub`, and it never resolves a Python
  class. `_query` composes those nodes and may consult `_binding`; neither
  module back-imports `Entity`.
- `_graph_construction` depends only in the forward direction on the Entity and
  Value Object frontends, binding and error machinery, plus the class-free
  Metamodel. It accepts one explicit callback per construction, invokes
  deferred opaque-state factories before publication, and owns no callback
  registry or lifecycle-specific graph policy. `snapshot._graph` and
  `snapshot._state` depend on that advanced interface; no Entity module imports
  Snapshot.
- `snapshot._errors` is a strict leaf within the Snapshot package. The Snapshot
  Graph Materializer translates construction and callback failures through it
  only after neutral execution enters graph materialization; Entity never
  imports or raises Snapshot errors.
- Lazy imports used to conceal dependency cycles are removed.
- Import-linter enforces the class-free core seam and the internal direction.

## Deliberate compatibility breaks

The implementation removes, rather than forwards or deprecates, the following
concepts and names:

- `EntityConfig` and `__parallax__`;
- explicit `frozen=True` on Entity Classes;
- `Field`, `Relationship`, and `VoField` declaration factories, replaced by
  `attr` and `rel`;
- `FamilyRoot`, implicit abstract-subtype inference, and `Concrete`, replaced
  by `AbstractRoot`, `AbstractSubtype`, and `ConcreteSubtype`;
- `AsOfAttribute` and descriptor `asOfAttributes`, replaced by `AsOfAxis` and
  `asOfAxes`;
- descriptor/declaration `foreignKey` relationship hints, whose information is
  already carried by cardinality and Relationship Join;
- descriptor `relatedEntity` and any Python `rel(...)` target option; descriptor
  joins and `Rel[T]` respectively provide the sole authored target;
- duplicated bidirectional mappings and descriptor `reverseName`, replaced by
  one defining declaration plus a typed `reverse_of` / descriptor `reverseOf`
  declaration;
- direct `many-to-many` cardinality; association tables are explicit Entities
  connected by two supported direct relationships;
- `EntityRegistry`, `ScopedMetamodel`, `default_registry`, and `registry=`;
- `EntityMeta` and `EntityMetaView` introspection names;
- registry and class-list scope helpers;
- global/class-relative metadata lookup and descriptor export;
- `Statement` in favor of `FindQuery`;
- `model_copy` as the authored update-copy operation, in favor of `edit`.

Tests, fixtures, examples, specifications, and API-surface declarations change
to the new interface in the same work. No compatibility wrappers remain.

## Supported Python interfaces

Top-level `parallax.core` exposes the ordinary developer surface:

```text
Entity, TxTemporal, Bitemporal, ValueObject
Attr, Rel, attr, rel, index, desc, asc
ReadOnly, ReadWrite
AbstractRoot, AbstractSubtype, ConcreteSubtype
TablePerHierarchy, TablePerConcreteSubtype
Int32, Float32, Max, Sequence
MetamodelHub
FindQuery, Predicate
EntityIdentity, EntityMetadata, MetamodelIssue
ModelLocation
EntityDefinitionError, MetamodelDefinitionError, FormationContractError,
MetamodelValidationError, MetamodelStateError
MetamodelLookupError, QueryDefinitionError, UnsupportedCapabilityError,
EditError
LATEST, VALID_TIME, TX_TIME, Pin, Edge
TemporalReadError, UndeclaredAxisError
```

`parallax.core.entity` additionally exposes the advanced typing and first-party
collaboration values `Assignment`, `AttributeExpr`, `RelationshipPath`,
`SortKey`, `EntityGraphConstruction`, `EntityGraphWriter`,
`EntityGraphResolution`, `NodeHandle`, `GraphConstructionError`,
`UnloadedRelationshipError`, and `EntityRowCodec`, plus
`relationship_value_of` and `lifecycle_state_of`. The graph writer, graph
resolution view, and node handles are usable only inside a single
`EntityGraphConstruction.construct(...)` callback. The two inspection
operations are the only supported raw-state access for first-party lifecycle
packages.

`parallax.snapshot` exposes `is_loaded`, `narrowed`, `pin_of`, and `edge_of` as
Snapshot-node inspection functions and re-exports the Entity-defined
`UnloadedRelationshipError` for ordinary Snapshot callers. The concrete
`SnapshotNodeState` remains private. It also exposes
`SnapshotMaterializationError` with stable code
`snapshot-materialization-failed` and `SnapshotInspectionError` with stable
codes `snapshot-node-required`, `snapshot-pin-unavailable`, and
`snapshot-edge-unavailable`. It also exposes `TransactionOwnershipError` with
stable code `transaction-owner-mismatch`.

The dependency-free `parallax.core.base` seam implements `m-core` and exposes
`NeutralType` and `NeutralValue`. `NeutralType` values are constructible
structured values. `NeutralValue`, if exported, is typing vocabulary only — a
static alias naming the idiomatic immutable host values of the `m-core` value
spaces (bool, int, float, `Decimal`, str, bytes, date, time, datetime, UUID,
and the immutable JSON tree) — never a constructible runtime wrapper, tag, or
base class; null enters a position only through that position's own contract,
so `None` is not part of the alias. The class-free `parallax.core.metamodel` seam
exposes `UnresolvedMetamodel`, `CandidateMetamodel`, `Metamodel`,
`UnresolvedEntityDeclaration`, `EntityDeclaration`,
`MetadataCompiler`, `CompiledMetadata`,
`UnresolvedRelationshipDeclaration`, `UnresolvedDefiningRelationshipDeclaration`,
`UnresolvedReverseRelationshipDeclaration`, `UnresolvedRelationshipJoin`,
`RelationshipDeclaration`, `DefiningRelationshipDeclaration`,
`ReverseRelationshipDeclaration`,
`ValueObjectShapeKey`, `ValueObjectShapeDeclaration`,
`ValueObjectAttributeDeclaration`, `ValueObjectOccurrenceDeclaration`,
`NestedValueObjectOccurrenceDeclaration`,
`EntityReference`, `RelativeEntityReference`, `ExactEntityReference`,
`AttributeReference`, `RelationshipReference`,
`UnresolvedRelationshipOrder`,
`MetamodelIssue`, `ModelLocation`, `ModelRoot`, `EntityLocation`,
`AttributeLocation`, `RelationshipLocation`, `ValueObjectLocation`,
`ValueObjectAttributeLocation`, `IndexLocation`, `AsOfAxisLocation`,
`EntityIdentity`, `EntityMetadata`, `AttributeMetadata`,
`AttributeIdentity`, `IndexIdentity`, `IndexMetadata`,
`StorageContainer`, `Table`, `StorageLocation`, `Column`,
`RelationshipIdentity`, `RelationshipJoin`,
`RelationshipOrder`, `Multiplicity`, `One`, `Many`,
`RelationshipCardinality`, `OneToOne`, `ManyToOne`, `OneToMany`,
`SortDirection`, `Ascending`, `Descending`,
`PersistenceMode`, `ReadOnly`, `ReadWrite`,
`TemporalDimension`, `ValidTime`, `TransactionTime`,
`ValueObjectIdentity`, `ValueObjectAttributeIdentity`,
`ValueObjectMetadata`, `NestedValueObjectMetadata`,
`ValueObjectAttributeMetadata`, `AsOfAxisMetadata`, `InheritanceMetadata`,
`NotPrimaryKey`, `PrimaryKey`,
`PrimaryKeyGeneration`, `ApplicationAssigned`, `Max`, `Sequence`, and the nested member
protocols. It also exposes `FacetKey` for first-party semantic modules; the
generic `Metamodel.facet(...)` method is not a top-level developer
convenience. These are protocols and small semantic values, not a public concrete
record graph. `parallax.core.model_formation` exposes `ModelRuleSet`,
`ModelCompiler`, `MetamodelFacet`, `FormationProfile`, and
`FormationContractError`, `FormationContractCode`, and
`MetamodelValidationError` for first-party module implementations;
`MetamodelIssue` and both errors remain top-level developer exports. A facet is
retrieved through its owner module's typed API rather than a top-level generic
convenience.

The class-free `parallax.core.relationship` seam exposes
`RelationshipMetadata`, `RelationshipFacet`, and `view(model)`. Behavioral
modules use that typed seam; neither generic Metamodel lookup nor top-level
developer imports expose symmetric Relationship Metadata as declared truth.

## Delivery plan

The accepted work is tracked as one non-implementation parent and six
blocking implementation tickets. Work the frontier in order; each child must
leave the repository green before the next begins.

Parent: [COR-44 — Redesign metadata contracts and deepen the Python Metamodel
Hub](https://linear.app/flimflam/issue/COR-44/redesign-metadata-contracts-and-deepen-the-python-metamodel-hub)

Native blocking graph: `COR-45` → `COR-40` → `COR-46` → `COR-47` →
`COR-50` → `COR-51`. `COR-45` is the initial frontier.

The current COR-45/COR-40 readiness work deliberately does not close later
slice contracts. COR-46's complete enforceable dependency graphs, enforcement
scopes, and composition-root imports are specified normatively in §7 of the
Python spec ("The target topology after the metamodel dependency inversion")
and motivated in its section below, and
the compiled facet protocols its behavioral consumers read are normative in
`m-inheritance` ("The Inheritance Facet"), `m-temporal-read` ("The Temporal
Facet"), and `m-opt-lock` ("The Optimistic Lock Facet") — inheritance-aware
member applicability is the Inheritance Facet's `applicable_*` contract.
COR-47's exhaustive declaration and descriptor-input grammar is now normative
in the Python spec (§2 "Declaration and descriptor-input grammar"). Before
their respective tickets start, the following remain explicit blockers:
COR-50 needs the recursive Value Object input algebra, Node Handle
lifetime/factory order, and exact-hub Snapshot inspection keys; COR-51 needs
the normative row-codec and closed edit-error contracts plus its
temporary-symbol deletion ledger. None is silently assigned to COR-45 or
COR-40.

### COR-45 — Normalize the core Metamodel Interface and canonical descriptor

[Open COR-45 in Linear](https://linear.app/flimflam/issue/COR-45/normalize-the-core-metamodel-interface-and-canonical-descriptor).

Introduce `m-metamodel` and `m-model-formation`, move representation-independent
lookup and formation contracts out of `m-descriptor`, apply the As-Of Axis and
TPH table-ownership changes to the canonical schema and corpus, and migrate
every existing descriptor consumer to the new wire shape. This is the one
deliberately wide cross-repository contract change; it must finish without
compatibility aliases and without changing canonical SQL or runtime behavior.

This is the expand half of the dependency inversion: behavioral consumers may
temporarily continue to reach descriptor records until COR-46 moves them onto
the new interface. The final dependency direction is enforced in COR-46.

COR-45 is bounded to the authoritative core interface, formation contract,
canonical descriptor revision, and synchronized contract artifacts. It does
not own Python class construction, the complete future Python import graph, or
Snapshot materialization. Specification and contract changes land first:
`m-metamodel`, `m-model-formation`, the contributor manifest, and affected
owner specs are completed; then the catalog/DAG, schemas, corpus, generated
artifacts, and contract tooling switch together and pass; only then may runtime
descriptor consumers change.

Acceptance requires:

- the module catalog marks `m-metamodel`, `m-model-formation`, and
  `m-relationship` active and cases-covered, gives each at least one tagged
  case, and makes `m-descriptor` the interchange/serde adapter to
  `m-metamodel`;
- the dependency graph has `m-model-formation -> m-metamodel`,
  `m-relationship -> {m-metamodel, m-model-formation}`, and behavioral
  relationship consumers pointing to `m-relationship`; no reverse edge lets
  the runner know its contributors;
- the authoritative core specifications are complete and decision-ready before
  runtime work, and schema/corpus/generated/tooling synchronization is green
  before any runtime semantic migration;
- [`m-model-formation`](../../core/spec/m-model-formation.md) is the
  authoritative manifest from module owner to Rule Set requirement, complete
  owned Issue Code set, compiler/facet key, and required modules/facets;
  catalog-completeness tests compare the explicit profile to that manifest,
  never to the runtime tuple itself;
- the core contract defines locally declared protocol facts, Unresolved and
  Candidate Metamodel protocols, the foundational resolution gate, rule-set and
  compiler protocols, explicit Formation Profile, resolve-validate-compile
  ordering, immutable module-owned facets, deterministic issue aggregation,
  stable issue codes, and catalog/profile drift check, with no automatic
  registration or discovery;
- Unresolved Metamodel is enumeration-only over native-view-capable unresolved
  Entity declarations, with no lookup, facet, or uniqueness guarantee and no
  semantic source order; only successful resolution creates canonical Entity
  Declaration enumeration plus total constant-time lookup, while the
  separate Metamodel exists only after owner compilers produce final normalized
  Entity Metadata and the complete typed facet set;
- Candidate Metamodel preserves canonical identities plus declaration structure
  for owner validation—especially defining/reverse relationships and reusable
  Value Object shape graphs—and is neither Entity Metadata nor a Metamodel
  subtype;
- accepted Entity Metadata preserves the identity-resolved Relationship
  Declaration union, while `m-relationship` alone owns its Rule Set, stable
  issue codes, Model Compiler, symmetric Relationship Facet, exact-identity
  lookup, and declaration-ordered per-Entity enumeration;
  the generic Metadata Compiler performs no relationship pairing or derivation;
- Entity Declaration has the exact shallow shape of identity, Storage
  Container, persistence, Attribute Metadata, resolved defining/reverse
  Relationship declarations, unchanged Value Object occurrence declarations,
  As-Of Axis Metadata, Inheritance Metadata, and Index Metadata; it adds no
  member lookup, effective view, facets, or behavioral authority;
- after all rules succeed, the one issue-free `m-metamodel` Metadata Compiler
  creates canonical Compiled Metadata and immutable local indexes; semantic
  Model Compilers are facet-only, consume only declared facet dependencies,
  and the runner combines the exact Compiled Metadata object with all facets as
  the sole accepted graph, without mutable drafts, partial Entity patches,
  copied metadata/facets, or hub-owned accepted-metadata indexes;
- Unresolved Entity Declaration is the exact shallow all-local shape of
  identity, Storage Container, persistence, final-identity Attribute, As-Of
  Axis, and Index Metadata, plus Relationship, Value Object occurrence, and
  inheritance declarations; separate Declaration types exist only for
  unresolved references or occurrence-relative identities, and local
  sequences preserve authoring order;
- Value Object occurrence declarations reference reusable, storage-neutral
  shape declarations through opaque formation-local Shape Keys; keys have only
  equality/hash semantics, never enter authoring/export/locations/Metadata,
  support cycle and reuse validation without host object identity, and are
  discarded when compilation expands distinct path identities;
- unresolved Relationship Declaration is the exact defining-versus-reverse
  union: each branch has one target-bearing reference, ordering is target-local,
  defining alone owns join/cardinality/dependency, reverse alone names its
  defining declaration; resolution produces the identity-resolved declaration
  union, while `m-relationship` alone validates and compiles the symmetric
  facet;
- Entity Reference is exactly Relative local name or Exact Entity Identity;
  containment alone supplies Relative scope, class and qualified-string targets
  are Exact, bare declaration strings are Relative, and no raw spelling,
  owner, module/native type, optional namespace, or global fallback remains;
- resolution aggregates all foundational identity/reference issues and either
  produces one Candidate Metamodel or prevents every semantic
  rule set and compiler from running; neither formation input is behavioral;
- `m-metamodel` owns the one immutable `MetamodelIssue` value used by both the
  foundational resolver and contributed rule sets; `m-model-formation` owns
  aggregation and `MetamodelValidationError`, with no reverse dependency or
  issue translation;
- `MetamodelIssue` is exactly stable module-owned kebab-case Issue Code,
  primary Model Location, immutable semantic-order related locations, and
  explanatory message; all issues are fatal, message is excluded from equality
  and canonical ordering, and there is no severity or central code enum;
- every Issue Code starts with its owner module's catalog stem; each Rule Set
  declares its complete immutable code set, profile drift rejects missing
  prefixes and cross-owner collisions, runtime rejects undeclared emissions as
  contract failures, and compilers never emit validation issues;
- `FormationContractError` is the coded top-level `RuntimeError` for profile
  drift, invalid or undeclared codes, duplicate issue identities, missing or
  duplicate facets, and unexpected resolver, Rule Set, or compiler failure; it
  carries the responsible owner and preserved cause when applicable, never
  masquerades as metadata validation, and neither error category publishes
  facets, an accepted Metamodel, or class bindings;
- resolver, Rule Set, Metadata Compiler, and Model Compiler signatures,
  manifest order, canonical issue aggregation, facet topological order, tie
  breaking, failure selection, cause preservation, and every closed Formation
  Contract Code are normative and conformance-tested;
- Model Location is exactly the closed semantic union of model root, Entity,
  Attribute, Relationship, Value Object, Value Object Attribute, Index, and
  As-Of Axis locations; source-representation paths, class names, spans, and
  arbitrary property strings are excluded from the core issue contract;
- issue aggregation sorts by primary Model Location, then Issue Code, then the
  ordered related-location keys; Model Root sorts first, other locations group
  by canonical Entity Identity and fixed semantic kind rank, Valid Time precedes
  Transaction Time, and no frontend, rule, profile, message, or scheduling
  order participates;
- each compiling semantic module owns one typed `FacetKey<T>` identified by its
  canonical module-catalog identity; the profile rejects missing or duplicate
  compiler keys, formation installs all facets atomically, accepted retrieval
  is total, and owner `view(model)` APIs hide the generic mechanism;
- Entity Identity is the core `(namespace, name)` pair with canonical
  dot-qualified spelling, and every accepted cross-entity reference uses it;
- bare authored Entity References resolve only in their declaring entity's
  namespace, Exact references resolve unchanged, ownerless core operations use
  Entity Identity, string facades parse canonical bare-unnamespaced or
  qualified-namespaced identities, canonical export qualifies namespaced
  identities, and no global bare-name fallback exists;
- Attribute Identity is the shared resolved member reference for metadata and
  operations; Relationship Join is a distinct structured mapping equality, not
  an operation Comparison or descriptor string;
- Relationship Identity is `(source Entity Identity, name)`; accepted local
  Entity Metadata preserves defining/reverse Relationship Declarations, while
  the `m-relationship` facet derives symmetric Relationship Metadata whose
  target comes from the join and whose reverse is target-scoped, with no
  `relatedEntity`, `target_entity`, or `foreignKey` field;
- direct Relationship Cardinality is limited to one-to-one, many-to-one, and
  one-to-many; many-to-many requires an explicit association Entity;
- accepted Relationship Cardinality uses structured OneToOne, ManyToOne, and
  OneToMany variants with source/target Multiplicity; descriptor strings never
  enter behavioral code;
- bidirectional relationships have one defining declaration; reverse
  declarations repeat no join, cardinality, dependency, or target;
  `m-relationship` validates and compiles them to its symmetric facet;
- Relationship Order uses target Attribute Identity plus structured Ascending
  or Descending; empty ordering means no sort, and Unspecified does not exist;
- full `*Identity` type names are retained; `*Id` remains reserved for entity
  instance primary-key values;
- accepted attribute and Value Object leaf types use structured `NeutralType`
  variants, including parameterized Decimal, while descriptor type strings are
  confined to parsing and export;
- `m-core` owns `NeutralType` and `NeutralValue`; metamodel defaults, operation
  literals, assignments, and neutral rows reuse them rather than defining local
  value vocabularies;
- Primary-Key Generation is the normalized
  `ApplicationAssigned | Max | Sequence` algebra inside the
  `NotPrimaryKey | PrimaryKey(PrimaryKeyGeneration)` sum; Sequence
  configuration is complete and default-resolved, and a non-primary-key
  attribute cannot carry generation;
- the exact Attribute Metadata protocol is self-identifying and contains only
  identity, Neutral Type, Storage Location, primary-key sum, and normalized
  scalar flags; it has no duplicate name or descriptor-shaped
  fields;
- Index Metadata is self-identifying, local-only, component-ordered, and uses
  Attribute Identities without duplicated column names;
- all read-only protocol names use the full `Metadata` suffix, and Python
  exposes no metadata view named `*Meta`;
- entity enumeration uses the canonical Entity Identity order, while all local
  member and component sequences preserve declaration order;
- class-free identity/local-name lookup is non-throwing, local-only, and
  expected amortized `O(1)`; misses return absence and ordered enumeration is
  separate;
- top-level, nested, and inner-attribute Value Object metadata are distinct
  recursive protocols, so nested members cannot carry storage facts;
- every inheritable Entity Metadata member uses the accepted `declared_`
  vocabulary and no unqualified effective-looking alias exists;
- Entity Metadata has the exact self-identifying member set and order, keeps
  required descendant `declared_persistence` absence intact, rejects descendant
  declarations, and places Index Metadata
  last after structural and inheritance facts;
- schemas, specifications, models, cases, rejection-rule vocabulary, generated
  artifacts, reference-harness parsing, and active language consumers accept
  only `asOfAxes` and root-owned TPH tables;
- TPH validation requires one table on the root and forbids concrete table
  repetition, while TPCS continues to require one table per concrete subtype;
- canonical descriptor round-trips remain deterministic and all golden SQL and
  expected rows remain unchanged; and
- the core dependency, schema, contract-tool, and affected language static
  gates pass.

### COR-40 — Adopt Valid Time and Transaction Time terminology

[Open COR-40 in Linear](https://linear.app/flimflam/issue/COR-40/adopt-valid-time-and-transaction-time-terminology).

Propagate the normalized `ValidTime | TransactionTime` vocabulary introduced
by COR-45 through the canonical descriptor, temporal specifications,
operations, public APIs, implementation, corpus, generated artifacts, tests,
and documentation. The interval roles become `startAttribute` and
`endAttribute`; conventional Python attributes become `valid_start`,
`valid_end`, `tx_start`, and `tx_end`; physical columns remain `from_z`,
`thru_z`, `in_z`, and `out_z`.

The replacement is one closed mapping, not independent renaming work:

| Surface | Valid Time | Transaction Time |
|---|---|---|
| Meaning | fact true in the modeled world | fact present in the database |
| Core / descriptor dimension | `ValidTime` / `validTime` | `TransactionTime` / `transactionTime` |
| Python query keyword and Pin/Edge accessor | `valid_time` | `tx_time` |
| Metadata interval roles | `start_attribute`, `end_attribute` | `start_attribute`, `end_attribute` |
| Conventional Attributes | `valid_start`, `valid_end` | `tx_start`, `tx_end` |
| Physical columns | `from_z`, `thru_z` | `in_z`, `out_z` |
| Relationship propagation | source Valid-Time coordinate | source Transaction-Time coordinate |
| Write input | `valid_from`; bounded verbs also use `until` | finite Database-handle clock instant |
| Optimistic temporal observation | not used as the gate | observed `tx_start` / `in_z` |

Omitted coordinates are Latest. Now is a finite current-clock instant.
`TxTemporal` and `Bitemporal` supply the conventional Attributes and
columns; Python has no public As-Of Axis authoring surface. The normalized core
Metadata retains explicit start/end Attribute Identities so future legacy-column
overrides remain additive.

Acceptance requires:

- Transaction-Time-Only and Bitemporal are the only temporal model shapes;
- an axis is identified only by its Temporal Dimension and has the exact
  accepted start/end Attribute Identity contract;
- omitted coordinates mean Latest (`end = infinity`), while Now remains a
  distinct finite containment read and is never the serde spelling of Latest;
- the retired `axis: business|processing` vocabulary, `fromColumn`, and `toColumn` are
  absent from active specifications, schemas, cases, generated artifacts,
  implementation, and public APIs;
- no public alias or dual-read wire format remains;
- core and Python specifications/glossaries are decision-complete first, then
  descriptor/operation schemas, corpus, generated artifacts, and tooling switch
  together and pass before any runtime temporal behavior changes;
- the ticket closes with final Valid-/Transaction-Time semantics and leaves no
  temporary vocabulary or adapter for COR-46 to reinterpret;
- physical columns and SQL behavior are unchanged; and
- core, schema, generated-artifact, Markdown, Python static, and Python
  verification gates pass.

### COR-46 — Move Python behavioral modules onto `parallax.core.metamodel`

[Open COR-46 in Linear](https://linear.app/flimflam/issue/COR-46/move-python-behavioral-modules-onto-parallaxcoremetamodel).

Add the class-free metamodel, model-formation, and relationship packages,
implement descriptor-backed adapters, and change every Python behavioral
module to consume the Metamodel Interface and typed owner facets rather than
concrete descriptor records. Keep the old Entity frontend working temporarily
through an adapter so this prefactor lands independently of the public API
replacement.

#### Final dependency graphs and enforcement scopes

COR-46 lands the dependency inversion as one atomic flip: the core
`dependency-graph` edit in `core/spec/modules.md`, the `spec/python.md` §7
row and fence replacements, the DAG-sync tool's module-to-scope map, and the
regenerated import-linter complement change together and leave every gate
green. No temporary row survives the flip. The Python spec is the binding
product definition, so the complete target tables — behavioral scope mapping,
composition-root edges, and support-scope grants — live normatively in §7 of
`languages/python/spec/python.md` ("The target topology after the metamodel
dependency inversion"); this subsection records the core-side changes and the
design rationale behind those tables without repeating them.

**Core direct-edge changes.** Exactly three edges leave the fenced
`dependency-graph` block, and no other core edge changes:

```text
m-pk-gen --> m-descriptor        removed; m-pk-gen --> m-metamodel remains
m-inheritance --> m-descriptor   removed; m-metamodel / m-model-formation remain
m-value-object --> m-descriptor  removed; m-metamodel / m-model-formation remain
```

After the removal no behavioral module depends on `m-descriptor`. Its own
edges (`m-descriptor --> m-core`, `m-descriptor --> m-metamodel`) make it the
interchange/serde adapter over the Metamodel Interface (ADR 0028); the
conformance family may still reference it by construction.

**Python behavioral scopes.** The three temporary co-location rows in §7 and
the corresponding `MODULE_SCOPE` entries in
`languages/python/tools/check_dag_sync.py` are replaced in the same change:
`m-metamodel`, `m-model-formation`, and `m-relationship` move to their own
`parallax.core.metamodel`, `parallax.core.model_formation`, and
`parallax.core.relationship` scopes, `parallax.core.descriptor` becomes the
sole owner of its scope, and every behavioral row keeps mirroring the core
DAG mechanically. The §7 target table is normative.

**Composition root.** `parallax.core._formation_profile` becomes a declared
§7 support scope. Its allowed direct dependencies are exactly the formation
runner plus every module whose Formation Manifest row supplies a Rule Set or
compiler; `m-pk-gen` supplies neither, so the composition root does not
import it. The §7 target fence lists the resulting edges. The only production
importer of `_formation_profile` is the seam that seals a model: during
COR-46 the temporary Entity-frontend adapter inside `parallax.core.entity`,
and from COR-47 `entity._hub`.

**Support-scope grants.** In the same §7 edit, every support grant that
exists only to read descriptor record metadata moves to the Metamodel
Interface and typed owner facets, and each support row is completed to
declare every direct import its scope makes — the closure-based complement
cannot reject an undeclared-but-reachable direct import, so a support row is
the only honest declaration of its direct edges. (Behavioral scopes differ:
`modules.md` lists direct edges only and implies transitives, so a
behavioral module's reliance on a transitively reachable module remains
by-design legal.) The §7 target table is normative; the decisions behind it:

- `parallax.core.entity` alone keeps `m-descriptor`: serialization is that
  seam's concern — the temporary frontend adapter still reads the registry's
  descriptor records, and the final hub owns descriptor ingestion and export.
  Its row also declares the frontend's real direct imports that today ride
  the closure undeclared: `m-core` (neutral values in `entity/statement.py`)
  and `m-inheritance` (below).
- `parallax.snapshot.handle`'s row is completed the same way: its modules
  directly import `m-core`, `m-dialect`, `m-temporal-read`, `m-inheritance`,
  `m-op-algebra`, and `m-deep-fetch` today, and its descriptor-record reads
  (`_database`, `_read`, `_transaction`, `_predicate_writes`,
  `_write_inputs`) migrate to `m-metamodel` lookup plus the typed
  Inheritance, Temporal, and Optimistic Lock facet views — the handle gains
  `m-metamodel` and loses nothing but descriptor reachability as a licensed
  read. Relationship metadata is consumed only by `._wrap`, whose dedicated
  row grants `m-relationship` for the Relationship Facet; no parent-handle
  module reads it, so the parent row deliberately carries no
  `m-relationship` grant.
- `parallax.postgres`'s row declares its existing direct `m-core` imports.

The `m-inheritance` and `m-relationship` grants on the Entity row name where
the preserved frontend's inheritance- and relationship-shaped operations
land, so a COR-46 implementor moves them rather than reinventing them:

- assignment validation against the family write rules (today
  `inheritance.validate_write_assignment` in `entity/expressions.py`) and
  narrowed-position resolution (today `resolve_narrow_position` in
  `entity/graph_state.py`) delegate to the Inheritance Facet through
  `parallax.core.inheritance.view(model)` — narrowed positions specifically
  through its typed `position(...)` operation, whose view carries the
  canonical effective concrete set and the attribute and Value Object
  projection supersets (`m-inheritance` "The Inheritance Facet"); and
- relationship traversal and target resolution (today the descriptor-owned
  `relationship_target` helper in `entity/expressions.py`) delegate to the
  symmetric Relationship Facet through
  `parallax.core.relationship.view(model)`, whose Relationship Metadata
  derives the target from the join.

These grants also regularize declaration with reality: the frontend already
imports `parallax.core.inheritance` directly, which the closure-based
generated complement permits (inheritance is transitively reachable through
`m-op-algebra`) even though the current §7 row never declared it.

**Enforcement effect.** After the flip, `parallax.core.descriptor` is
reachable from no behavioral scope's transitive closure, so the regenerated
forbidden-edge complement mechanically rejects a descriptor import from every
behavioral scope — including `parallax.snapshot.materialize` — and from the
write-lowering group. `parallax.snapshot.handle` and `._wrap` still reach the
descriptor scope transitively through `parallax.core.entity`, so their
descriptor-record independence is proven by the no-descriptor-record
acceptance criteria and review rather than by the generated complement; the
COR-51 legacy-surface deletion removes the record surface those paths could
have reached.

Acceptance requires:

- `parallax.core.metamodel` exposes the accepted read-only
  `UnresolvedMetamodel`, `CandidateMetamodel`, and `Metamodel` protocols plus
  the foundational resolution contract; entity views expose local declarations
  only, inheritable members use the `declared_` vocabulary, and semantic owner
  modules retain every effective/flattened computation;
- Unresolved Metamodel exposes enumeration only and supports native class or
  descriptor views without a copied record graph; it promises neither lookup
  nor uniqueness, while successful resolution provides canonical resolved
  declaration enumeration and total Entity lookup without Metadata or facets;
- Candidate Metamodel retains owner-specific declaration structure for all Rule
  Sets; only the separately compiled Metamodel exposes final Entity Metadata,
  local member lookup, facets, and behavioral authority;
- Entity Declaration advances only Relationship and inheritance
  references in the shallow unresolved shape, preserves the reusable Value
  Object declaration graph and local sequence order, and exposes no member
  lookup;
- the mandatory Metadata Compiler alone creates Compiled Metadata after
  validation, every semantic Model Compiler returns exactly one typed facet,
  and Metamodel atomically combines those values without patch merging;
- each Entity Class directly implements `UnresolvedEntityDeclaration`; that
  declaration source reuses `AttributeMetadata` and other
  final-identity semantic values, introduces separate protocols only for
  unresolved references or occurrence-relative identities, uses unqualified
  all-local member names, and preserves local declaration order without adding
  lookup;
- its Value Object declaration graph uses the exact occurrence/shape/leaf
  protocols and opaque formation-local Shape Key semantics, accepts repeated
  class-backed shape use without public registration, detects containment
  cycles without object identity, and compiles keys away into path identities;
- its relationship declarations expose the one-target defining/reverse union,
  structured Attribute and Relationship References, target-local ordering, and
  no repeated target, reverse, foreign-key, join, or cardinality input;
- accepted Entity Metadata preserves the identity-resolved Relationship
  Declaration union; `parallax.core.relationship` alone validates it and
  compiles the symmetric Relationship Facet with exact-identity lookup and
  declaration-ordered per-Entity enumeration, while the generic Metadata
  Compiler performs no pairing, join swapping, or cardinality inversion;
- its Entity Reference variants preserve the exact difference between a class
  target, bare lexical target, and qualified exact target without module-global
  evaluation or stored frontend spelling;
- lookup, accepted references, facets, and the descriptor adapter use the core
  Entity Identity value rather than bare names;
- Python forward target resolution is confined to the hub candidate set and
  implements the core lexical namespace rule without module-global evaluation;
- Relationship joins and orderings resolve once to structured identity values,
  and operation nodes reuse Attribute Identity without importing operation
  behavior into metadata;
- relationship paths reuse Relationship Identity; descriptor-backed and
  class-backed adapters agree on source/target orientation and single-source
  target authoring, while `m-relationship` alone owns reverse validation and
  the absence of target/FK duplicates;
- descriptor and class declaration reject direct many-to-many cardinality, and
  conformance covers explicit association-Entity navigation instead;
- descriptor-backed and class-backed adapters produce identical structured
  Relationship Cardinality values, and behavioral consumers contain no
  cardinality-string comparisons;
- defining/reverse declaration unions reject mixed or incomplete forms, reverse
  cycles, missing mappings, incompatible annotations, and multiple owners;
- relationship ordering is target-scoped and to-many-only, omitted term
  direction normalizes to Ascending, empty ordering emits no sort, and operation
  Sort Keys reuse the same Sort Direction values;
- descriptor-backed and alternate implementations expose structured
  `NeutralType` values, and no behavioral consumer parses a descriptor type
  string;
- Python implements the shared values in `parallax.core.base`; metadata,
  operation, write, and row boundaries use those same types without reverse
  dependencies;
- both implementations expose the same normalized Primary-Key Generation
  variant, including resolved Sequence defaults, and write behavior performs no
  descriptor-shaped option interpretation;
- both implementations expose the exact Attribute Metadata member set,
  including structured Storage Location and the
  `NotPrimaryKey | PrimaryKey(PrimaryKeyGeneration)` sum, without a duplicated
  `name` field;
- both implementations expose the exact Entity Metadata member set and order,
  including required absence of descendant `declared_persistence` and final
  `indices`;
- both implementations expose the exact Index Metadata shape and reject empty,
  duplicate, cross-entity, or inherited index components;
- lookup conformance covers every Entity/member hit and miss, local-versus-
  inherited behavior, expected constant-time indexing, and the facade's stable
  `MetamodelLookupError` codes;
- class constructor order does not affect `models.entities` or export, while
  each class's member order is preserved exactly;
- both implementations expose the same three recursive Value Object shapes and
  preserve declaration order at every depth;
- `parallax.core.model_formation` implements the accepted Formation Manifest,
  rule-set, compiler, facet, and Formation Profile protocols, deterministic
  resolve-validate-compile runner, issue aggregation, and aggregate validation
  error without importing contributor implementations; it reuses
  `parallax.core.metamodel`'s `MetamodelIssue` value rather than defining
  another issue type;
- the explicit Python composition root separately supplies immutable built-in
  Formation Manifest data and the manifest-complete Rule Set/compiler profile;
  drift checks prove both manifest/profile and manifest/catalog consistency
  with no missing, duplicate, extra, or ambient contributors;
- descriptor parsing and export implement that interface without importing the
  Entity frontend;
- inheritance, temporal, navigation, SQL, read, and write behavior accepts any
  conforming Metamodel implementation, reads stable effective facts from its
  owner module's compiled facet — narrowed-position projection (the canonical
  effective concrete set plus the attribute and Value Object supersets)
  exclusively through the Inheritance Facet's `position(...)` operation — and
  does not import descriptor records;
- descriptor-backed behavior and canonical export remain unchanged;
- the core `dependency-graph` block no longer contains
  `m-pk-gen --> m-descriptor`, `m-inheritance --> m-descriptor`, or
  `m-value-object --> m-descriptor`, no behavioral module depends on
  `m-descriptor`, and `just core-dep-graph` stays green;
- §7 of the Python spec and the DAG-sync tool map `m-metamodel`,
  `m-model-formation`, and `m-relationship` to `parallax.core.metamodel`,
  `parallax.core.model_formation`, and `parallax.core.relationship`; no
  temporary co-location mapping remains anywhere, and the behavioral,
  composition-root, and support-scope grants equal §7's normative target
  tables ("The target topology after the metamodel dependency inversion"),
  including the new `parallax.core._formation_profile` row;
- the regenerated import-linter complement forbids `parallax.core.descriptor`
  imports from every behavioral scope and from the write-lowering scopes, and
  no lazy import hides a cycle; and
- `just python-static` and `just python-verify` pass.

### COR-47 → COR-50 → COR-51 — Replace the Python Entity registry frontend

[Open COR-47 in Linear](https://linear.app/flimflam/issue/COR-47/build-python-declarations-and-the-sealed-metamodel-hub),
[COR-50 in Linear](https://linear.app/flimflam/issue/COR-50/integrate-hub-provenance-queries-and-snapshot-graph-materialization),
and [COR-51 in Linear](https://linear.app/flimflam/issue/COR-51/complete-entity-edits-snapshot-writes-and-legacy-surface-removal).

The complete frontend contract is delivered as three independently green
slices:

- COR-47 builds Entity and Value Object declarations, the sealed class-backed
  Metamodel Hub, class binding, metadata lookup, and canonical export.
- COR-50 adds hub-provenance operations and Find Queries, Database connection,
  exact-handle transaction nesting, and Snapshot graph materialization.
- COR-51 completes Edited Copies, row translation, keyed and predicate-selected
  writes, and deletion of the legacy public surface.

Temporary transition support between slices must remain private and is deleted
by COR-51. Program-level acceptance requires:

Acceptance requires:

- Entity and Value Object declarations use the accepted class-header and
  `Attr`/`attr`/`Rel`/`rel` surface, explicit inheritance roles, the
  `TxTemporal`/`Bitemporal` framework bases, and implicit frozen
  configuration;
- `_declaration` is the lower-level shared Pydantic metaclass engine with
  immutable declaration payloads and private kind markers; `_entity` and
  `_value_object` both depend on it, it imports neither concrete frontend and
  uses no registry/callback classification, and Value Object construction has
  no parallel annotation parser;
- `_members` owns the public `Attr`/`Rel` authoring forms and installed
  class/instance descriptors and is the only runtime module that touches owner
  classes; `_declaration` parses those values without importing expression
  behavior;
- `_expressions` is a pure immutable operation-node algebra whose Attribute
  Expressions, Relationship Paths, Predicates, Assignments, and Sort Keys
  receive hub identity and structured member identities explicitly; it imports
  no `_members`, `_entity`, `_query`, or `_hub`, while `_query` depends only in
  the forward direction on `_expressions`, `_binding`, and `_errors`;
- `_errors` is a strict Entity-cluster leaf: it imports only the standard
  library and class-free core identity/issue values, accepts structured error
  data rather than concrete implementation objects, and is importable by every
  other Entity module without a return edge;
- no common `entity._graph_state` module exists: Snapshot owns its closed-world
  graph-local identity, relationship-view, pin, and edge state; a future
  managed-object surface owns its transaction, Identity Map, relationship
  resolution, mutation, deletion, and detachment state independently; only
  lower-level identities, narrowed-view keys, temporal coordinates, and deep
  fetch behavior are shared;
- the class-backed constructor rejects invalid non-domain inputs and repeated
  class objects before creating a hub with stable `MetamodelDefinitionError`
  codes and a zero-based argument index, while distinct classes with one
  Entity Identity proceed to aggregated whole-model validation;
- every frontend source is nonempty; `MetamodelHub()` fails immediately as
  `MetamodelDefinitionError(metamodel-empty)` without an argument index, while
  an empty canonical descriptor fails its schema before a hub exists;
- descriptor ingestion distinguishes syntax failure with format/source
  coordinates from canonical-schema violations with structured document paths;
  neither creates a hub or leaks document locations into semantic formation,
  and schema-valid semantic failures occur only during `seal()`;
- canonical export is total and deterministic for a sealed hub, performs no
  renewed validation or state change, and constructs no descriptor cache at
  seal time; unexpected adapter defects raise
  `DescriptorExportError(descriptor-export-failed)` with target and cause while
  leaving the hub sealed and returning no partial output;
- the complete class set enters through `MetamodelHub(*classes)`, seal is an
  atomic single-flight `UNSEALED -> SEALED | REJECTED` transition, concurrent
  callers share one terminal outcome, re-entry fails without deadlock,
  successful resealing is idempotent, rejected resealing reproduces its
  terminal failure, failures accumulate structured issues, and no ambient or
  incremental registration path exists;
- every model-dependent operation implements the complete hub state table:
  fail-fast `metamodel-unsealed` during both unsealed and internal-sealing
  phases, full availability only when sealed, and `metamodel-rejected` with
  terminal cause after failure; only concurrent `seal()` waits, every
  successful/idempotent seal returns `None`, and direct unbound class
  expressions use `metamodel-class-not-bound`;
- the post-formation Entity Class claim checks the complete set atomically,
  reports every conflict in canonical Entity Identity order as
  `MetamodelStateError(metamodel-class-already-bound)`, leaves the losing hub
  rejected and unbound, and gives exactly one winner under racing seals;
- each successful Entity Class binding is permanent for that class object's
  lifetime, keeps the immutable sealed hub reachable, and has no unbind,
  close, reset, or weak-expiry path; fresh model construction uses fresh class
  objects;
- `_binding` creates exactly one immutable Metamodel Binding per successfully
  sealed class-backed hub and returns that same value to `_members`, `_query`,
  and `_rows`; it contains opaque hub identity, the accepted-Metamodel
  reference, and the immutable bidirectional Entity Identity/Class index,
  exposes no `MetamodelHub` lifecycle/export/connection surface, copies no
  model facts, and creates no `_binding -> _hub` import edge;
- Entity Classes directly implement the unresolved declaration interface,
  while seal creates the sole normalized accepted Metamodel; every class
  binding only links its Python class to an Entity Identity in that shared
  Metamodel, and descriptor-backed hubs create no such links;
- class-backed and descriptor-backed hubs expose equivalent metadata and
  canonical exports without mirroring one another's record graph;
- Find Queries, Predicates, direct class expressions, Edited Copies, and
  cross-hub rejection behave as specified;
- intrinsically invalid operations raise `QueryDefinitionError`, while a valid
  operation whose canonical feature tag is absent from the connected provider
  raises `UnsupportedCapabilityError(capability-unsupported)` with that tag
  after hub validation but before SQL/adapter access; staged
  `snapshot-history-includes` proves the distinction;
- every Attribute Expression, Relationship Path including narrowed paths,
  Predicate, Assignment, Sort Key, and Find Query carries exact hub identity;
  literal values remain neutral, every mixed-hub composition fails immediately
  as `query-hub-mismatch`, and no connection, Unit of Work, SQL, or adapter work
  occurs on rejection;
- all five `_where` verbs accept only a mutation-compatible ordinary Find Query
  containing target/predicate/hub, privately normalize it to one ephemeral
  Predicate Selection, and reject every read-shaped clause as
  `query-not-mutation-compatible`; no public mutation query/builder or second
  serialized operation model exists;
- Assignment-bearing `_where` verbs require Assignments from the exact same hub
  and Entity target and reject mismatches as
  `query-assignment-target-mismatch` before buffering or adapter access, while
  delete/terminate forms accept no Assignments;
- nested `Database.transact(...)` joins only through the exact originating
  Database object and receives the identical Transaction; aliases of that object
  join, while different handles over the same hub/adapter, the same hub with a
  different adapter, different hubs, and otherwise equivalent configurations
  all fail first as
  `TransactionOwnershipError(transaction-owner-mismatch)` without closure,
  Unit of Work, SQL, or adapter work; after owner success, existing
  rollback-only and option-conflict behavior remains unchanged;
- `Database.connect` requires the identical sealed class-backed hub and
  receives `EntityGraphConstruction` and `EntityRowCodec`; Snapshot owns and
  explicitly composes its materializer from those capabilities;
- Snapshot graph state is owned by the Snapshot slice and no generic
  `entity._graph_state` module exists; a future managed-object slice defines a
  separate lifecycle state model rather than extending Snapshot state;
- Entity Graph Construction tests cover concrete class selection by core Entity
  Identity, allocate-all-before-populate cycle closure, callback-scoped and
  construction-local handles, cross-construction handle rejection,
  exactly-once complete population, valid populated roots, recursive Value
  Objects, canonical-to-Python mapping, broad relationship installation,
  post-population lifecycle-state factory resolution, singular opaque state
  storage, raw relationship/state inspection, and all-or-none publication
  after callback, state-factory, or construction failure;
- Graph Construction error tests cover every stable `entity-graph-*` code,
  deterministic allocation indices, structured identities and causes,
  writer/resolution scope closure, every foreign-handle position, and the
  distinction between invalid roots and unpopulated local roots; assertions
  are not part of the interface, while build/state-factory exceptions propagate
  unchanged with no graph publication;
- Snapshot materialization error tests prove every Graph Construction,
  lifecycle build, and opaque-state factory failure becomes exactly one
  `SnapshotMaterializationError(snapshot-materialization-failed)` at the public
  Snapshot read boundary with the original `.cause` and exception chain, no
  partial result, and no double wrapping; query, capability, transaction,
  adapter, SQL, and pre-materialization neutral-decoding errors retain their
  own classifications, while direct advanced construction preserves originals;
- Snapshot Graph Materializer tests cover graph-local identity/projection
  merging, diamonds and cycles, broad/unloaded/narrowed relationships,
  pins/edges, stable root and to-many order, and direct emission through the
  callback-scoped Entity Graph Writer without Snapshot-side
  Pydantic/private-slot manipulation;
- Snapshot inspection tests prove `is_loaded`, `narrowed`, `pin_of`, and
  `edge_of` are exported from `parallax.snapshot`, interpret only private
  `SnapshotNodeState`, use only the two advanced Entity inspection operations,
  and reject plain or differently lifecycled Entity values before all other
  validation as `SnapshotInspectionError(snapshot-node-required)` with the
  exact operation and no opaque-state disclosure; `is_loaded` never returns
  `False` for the wrong lifecycle, while valid-Snapshot operation-specific
  unloaded and temporal errors remain distinct;
- valid Snapshot nodes without pin or edge state raise respectively
  `SnapshotInspectionError(snapshot-pin-unavailable)` and
  `SnapshotInspectionError(snapshot-edge-unavailable)` with operation and
  Entity Identity but no private state; core `TemporalReadError` remains for
  temporal query/lowering and `UndeclaredAxisError` remains for absent axes on
  valid temporal values;
- broad unloaded descriptor access and an unrequested narrowed view raise the
  identical Entity-defined, Snapshot-re-exported
  `UnloadedRelationshipError(entity-relationship-unloaded)` carrying structured
  Broad or Narrowed Relationship View identity; top-level `parallax.core` does
  not export it, and `is_loaded` remains nonthrowing for valid Snapshot nodes;
- Snapshot Graph Input is already associated and uses only structured Entity,
  Attribute, Value Object, and Relationship View identities plus Neutral
  Values and whole-graph coordinates; tests prove shared/cyclic references,
  duplicate logical projections, absent-versus-null-versus-empty relationship
  state, stable root/to-many order, no input mutation, and the absence of row
  batches, fetch plans, classes, descriptor records, wire/column names,
  Pydantic values, or private slot names at the seam;
- no whole-graph `EntityGraphPlan`, global callback registration, import-time
  enrollment, discovery, or lifecycle-keyed mutable callback table exists;
  Snapshot and a future Managed Object materializer may coexist by supplying
  independent per-call build and opaque-state factory functions, and there is
  no keyed lifecycle extension bag or shared graph-state protocol;
- the old registries, configuration objects, global metadata/export helpers,
  row and wire-name helpers, `Statement`, and authored `model_copy` path are
  deleted without forwarding wrappers;
- `Entity.model_copy(...)` is actively overridden and every call raises
  `EditError(edit-use-edit)` without creating a value, while `edit(...)` alone
  creates an Edited Copy with a Change Record;
- the Python spec, usage guide, conformance models, public API snapshot,
  package artifacts, type checks, and focused lifecycle/error tests describe
  and prove only the new surface; and
- `just python-verify` passes.

## Verification commands

Run core gates from the repository root:

```text
just core-dep-graph
just core-schemas
just core-contract-tools
just lint-md
```

After a core module-graph edit, regenerate and verify Python enforcement from
the Python workspace:

```text
uv run python tools/check_dag_sync.py --write
uv run python tools/check_dag_sync.py
```

COR-47 finishes with `just python-static`. COR-40, COR-46, COR-50, and COR-51
finish with `just python-verify`; COR-46 also proves the narrower
`just python-static` gate. Run affected existing-language gates in COR-45 and
COR-40 because their canonical descriptor changes affect every implementation.
