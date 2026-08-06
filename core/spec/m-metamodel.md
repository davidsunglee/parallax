# m-metamodel — Normalized Metamodel

`m-metamodel` defines Parallax's representation-independent model contract.
It owns normalized declarations, canonical model identities, foundational
resolution, immutable accepted Metadata, and model-relative lookup. It does
not own JSON/YAML spelling, inherited/effective semantic views, query behavior,
SQL lowering, lifecycle behavior, or database execution.

The canonical descriptor (`m-descriptor`) and each native language declaration
frontend are inputs to this contract. They do not become alternative accepted
metamodel implementations.

## Formation states

Formation has three distinct immutable values:

```text
UnresolvedMetamodel -> CandidateMetamodel -> Metamodel
```

- **Unresolved Metamodel** is a nonempty enumeration-only frontend view. It may
  contain structured relative references and makes no uniqueness, lookup, or
  semantic source-order promise.
- **Candidate Metamodel** exists only after foundational resolution succeeds.
  All model-relative references are canonical Identities, Entity enumeration
  is canonical, and exact Entity lookup is total and nonthrowing. It retains
  owner-specific declaration structure for semantic validation.
- **Metamodel** exists only after every formation rule succeeds and compilation
  completes. It is not a subtype of either input state.

Neither formation input is behavioral authority. A frontend MAY expose native
read-only objects at the Unresolved boundary, but MUST NOT bypass formation or
present those objects as an accepted Metamodel.

Every frontend resolves member storage before this boundary. A descriptor
frontend applies `m-descriptor`'s `effectiveColumn(name, suppliedColumn)` after
reading the canonical member name; a native frontend first resolves its own
source spelling to a canonical member name and then applies the same portable
default unless its language surface supplies an explicit override. Therefore
every `AttributeMetadata.storage` and top-level
`ValueObjectOccurrenceDeclaration.storage` entering an Unresolved Metamodel is
a concrete `Column`. Nested Value Object occurrences and fields remain
storage-neutral and acquire no column during formation.

## Sole accepted metadata ownership

The mandatory Metadata Compiler produces exactly one immutable
`CompiledMetadata` object graph. The accepted Metamodel owns that exact graph
and attaches the complete immutable facet set to it without copying Entity,
member, occurrence, or facet values.

This is the sole canonical accepted metadata object graph for one formation:

- a hub MAY own lifecycle state, export context, and language-class bindings;
- a hub MAY delegate the Metamodel interface to the accepted object;
- a hub MUST NOT reconstruct accepted Metadata or compiled facets;
- a hub MUST NOT create independent normalized accepted-metadata indexes;
- language bindings MAY index canonical Entity Identity to native class, but
  that index is binding state, not model metadata; and
- descriptor export MUST derive from the accepted Metamodel and MUST NOT retain
  a mirrored accepted descriptor graph.

`CompiledMetadata` itself contains the immutable canonical Entity sequence and
the immutable indexes used by all accepted local lookup. The Metamodel adds
facet retrieval only. This ownership rule applies equally to descriptor-backed
and class-backed hubs.

## Canonical identities and order

```text
EntityIdentity(namespace: string | absent, name: nonempty dot-free string)
AttributeIdentity(entity: EntityIdentity, name: nonempty string)
RelationshipIdentity(source: EntityIdentity, name: nonempty string)
IndexIdentity(entity: EntityIdentity, name: nonempty string)
ValueObjectIdentity(entity: EntityIdentity,
                    path: nonempty sequence<nonempty string>)
ValueObjectAttributeIdentity(value_object: ValueObjectIdentity,
                             name: nonempty string)

MemberIdentity =
    AttributeIdentity
  | ValueObjectIdentity
  | ValueObjectAttributeIdentity
```

`MemberIdentity` is the closed union of the identity types that address one
logical member of an Entity: a top-level Attribute, a Value Object occurrence at
any containment depth, or a scalar field inside one. Relationships, Indices, and
Temporal Dimensions are not members in this sense and are not union arms.
The union names no new identity and adds no lookup; it is the addressing
vocabulary a consumer uses when it must denote a member without caring where
that member is stored, and it is what `m-storage-layout` accepts when it answers
where a member lives.

`MemberIdentity` is the successor to dotted-string member addressing. Nested
members travel some existing surfaces as an authored `Entity.occurrence.field`
string that each consumer re-splits; every such string denotes exactly one
`MemberIdentity`, and a consumer that resolves the string once and then carries
the identity is conforming. Replacing those authored spellings is not required
by this contract: the operation algebra's wire form is unchanged, and no
descriptor or operation position accepts a `MemberIdentity` as a serialized
value.

An empty namespace is invalid. The canonical Entity spelling is
`<namespace>.<name>` when namespaced and `<name>` otherwise. Namespaced export
is always qualified. `*Id` remains reserved for Entity instance primary-key
values.

Entity sets enumerate by ascending `(namespace or "", name)` codepoint order.
All local declared sequences preserve authoring order, including attributes,
relationships, Value Objects and their recursive members, As-Of Axes, indices,
key/index components, and ordering clauses.

## References and foundational resolution

```text
EntityReference =
    RelativeEntityReference(name: nonempty dot-free string)
  | ExactEntityReference(identity: EntityIdentity)

resolve(owner, RelativeEntityReference(name)) =
  EntityIdentity(owner.namespace, name)
resolve(owner, ExactEntityReference(identity)) = identity
```

Bare declaration strings are Relative. Qualified strings parse immediately to
Exact. Native class targets are Exact even when unnamespaced. There is no
module-global evaluation, global unique-name fallback, or retained source
spelling. Ownerless core calls consume exact Identities.

The fixed foundational resolver aggregates every foundational issue and
returns either one Candidate Metamodel or no resolved value. Semantic rule sets
never run after resolution issues. The resolver performs only identity,
reference, and foundational local-shape checks assigned to `m-metamodel`; it
does not implement another module's semantic rules.

## Formation-input protocols

The formation-input interfaces are exact. Implementations MAY use native
read-only frontend objects to satisfy them; the interfaces do not require a
second declaration record graph.

```text
UnresolvedMetamodel
  entities: nonempty immutable sequence<UnresolvedEntityDeclaration>

CandidateMetamodel
  entities: canonical nonempty immutable sequence<EntityDeclaration>
  entity(EntityIdentity) -> EntityDeclaration | absent

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

Unresolved Metamodel is enumeration-only. It has no Entity or member lookup,
facet access, effective view, uniqueness guarantee, or semantic source order.
Its outer sequence MAY retain frontend order for diagnostics, but that order is
not observable model semantics. Each Entity's local sequences preserve authored
order. No Unresolved declaration exposes lookup.

Candidate Metamodel enumerates Entities in canonical Entity Identity order and
provides total, nonthrowing, expected amortized `O(1)` exact Entity lookup. A
miss returns absence. It has no member lookup, facet access, effective view,
Metadata, or behavioral authority. Its local sequences retain authored order.

Only reference-bearing or occurrence-relative facts have separate Declaration
types. Attribute, As-Of Axis, and Index facts already have final Identities and
reuse their Metadata types at both input stages. Resolution changes only
relationship and inheritance references; it does not validate or compile their
owner-specific semantics.

### Attribute and relationship references

```text
AttributeReference
  entity: EntityReference
  name: nonempty string

RelationshipReference
  entity: EntityReference
  name: nonempty string

UnresolvedRelationshipJoin
  source: AttributeIdentity
  target: AttributeReference

RelationshipJoin
  source: AttributeIdentity
  target: AttributeIdentity

UnresolvedRelationshipOrder
  attribute: nonempty target-local Attribute name
  direction: SortDirection
  nulls: NullPlacement

RelationshipOrder
  attribute: AttributeIdentity
  direction: SortDirection
  nulls: NullPlacement
```

`SortDirection = Ascending | Descending`; omission in an authoring frontend
normalizes to Ascending before the Unresolved boundary.
`NullPlacement = NullsFirst | NullsLast` is independent of direction; omission
normalizes to NullsLast before that same boundary. The source Attribute
Identity belongs to the declaring Entity. A target-local ordering name repeats
no Entity Reference because the relationship target supplies its scope.

Unresolved relationship authoring is the closed union:

```text
UnresolvedRelationshipDeclaration =
    UnresolvedDefiningRelationshipDeclaration(
      identity: RelationshipIdentity,
      cardinality: RelationshipCardinality,
      join: UnresolvedRelationshipJoin,
      dependent: boolean,
      order_by: immutable sequence<UnresolvedRelationshipOrder>)
  | UnresolvedReverseRelationshipDeclaration(
      identity: RelationshipIdentity,
      reverse_of: RelationshipReference,
      order_by: immutable sequence<UnresolvedRelationshipOrder>)

RelationshipDeclaration =
    DefiningRelationshipDeclaration(
      identity: RelationshipIdentity,
      cardinality: RelationshipCardinality,
      join: RelationshipJoin,
      dependent: boolean,
      order_by: immutable sequence<RelationshipOrder>)
  | ReverseRelationshipDeclaration(
      identity: RelationshipIdentity,
      reverse_of: RelationshipIdentity,
      order_by: immutable sequence<RelationshipOrder>)
```

The defining branch's only target is `join.target.entity`. The reverse branch's
only target is `reverse_of.entity`. There is no additional target, reverse name,
foreign-key hint, or repeated join/cardinality/dependency input. Resolution
turns references and target-local order names into canonical Identities but does
not pair directions, swap joins, invert cardinality, or synthesize Relationship
Metadata. A one-way defining declaration is valid input.

```text
Multiplicity = One | Many

RelationshipCardinality =
    OneToOne(source: One, target: One)
  | ManyToOne(source: Many, target: One)
  | OneToMany(source: One, target: Many)
```

Direct Many-to-Many is unconstructible. An association Entity represents that
model shape.

### Reusable Value Object declarations

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

A Shape Key denotes one reusable declaration node during one Model Formation.
Each occurrence of that node carries the same key; distinct declaration nodes
carry distinct keys even when structurally equal. A key promises equality and
hashing only. It has no spelling, order, serialization, cross-formation
identity, Model Location, or accepted-Metadata representation.

Only a top-level occurrence owns Storage Location. Shapes and nested
occurrences are storage-neutral. Every sequence preserves declaration order
and exposes no lookup. Candidate Metamodel retains the graph unchanged. The
`m-value-object` Rule Set uses Shape Keys to validate reuse and cycles without
host-object identity; after successful validation the Metadata Compiler expands
each occurrence into path-identified Metadata and discards all Shape Keys.

## Inheritance declarations

```text
Inheritance<Parent> =
    AbstractRoot(
      strategy: InheritanceStrategy)
  | AbstractSubtype(
      parent: Parent)
  | ConcreteSubtype(
      parent: Parent,
      tag_value: nonempty string | absent)

InheritanceMetadata = Inheritance<EntityIdentity>

InheritanceStrategy =
    TablePerHierarchy(tag_column: nonempty string)
  | TablePerConcreteSubtype
```

`Inheritance<EntityReference>` is the Unresolved specialization. Resolution
changes only a descendant parent to Entity Identity. The variant is the role;
there is no parallel role field. Root strategy, descendant tag, storage, and
family rules belong to `m-inheritance` formation rather than foundational
resolution.

## Declared metadata

`EntityMetadata` is the local declaration view:

```text
EntityMetadata
  identity: EntityIdentity
  declared_container: StorageContainer | absent
  declared_persistence: PersistenceMode | absent
  declared_attributes: immutable sequence<AttributeMetadata>
  declared_relationships: immutable sequence<RelationshipDeclaration>
  declared_value_objects: immutable sequence<ValueObjectMetadata>
  declared_as_of_axes: immutable sequence<AsOfAxisMetadata>
  inheritance: InheritanceMetadata | absent
  indices: immutable sequence<IndexMetadata>
```

It never copies inherited or otherwise effective facts. Every property whose
effective value may differ through inheritance has a `declared_` qualifier.
Owner modules expose contextual effective views through compiled facets.

Exact lookup is local-only, total, nonthrowing, and expected amortized `O(1)`:

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

Enumeration and lookup are distinct. A miss returns absence; it does not raise
a developer-facing lookup error.

## Storage and persistence

```text
StorageContainer = Table(name: nonempty string)
StorageLocation = Column(name: nonempty string)
PersistenceMode = ReadWrite | ReadOnly
```

`ReadWrite` is the standalone Entity and inheritance-root default. Persistence
is family-wide and root-owned: a descendant's absent
`declared_persistence` means inherit, while descendant presence is invalid.
Persistence Mode is unrelated to in-memory mutation, security policy,
Transaction Time, or Unit-of-Work demarcation.

`Table` is the only constructible Storage Container and `Column` the only
constructible Storage Location. The reserved future variants
`DocumentCollection` and `ContainerDocument` are not constructible in this
contract.

`DocumentPath` was reserved alongside them and is no longer a reserved Storage
Location. The name now belongs to `m-storage-layout`, where it is one arm of the
compiled `MemberPlacement` union, and it is constructible there. The two are
distinguished by kind rather than by spelling: a Storage Location is a
**declared** fact a member carries, while a Document Path is a **derived** fact
Storage Layout computes from the accepted model. Nothing declares a Document
Path — there is no authoring form for one, and a member's `storage` remains
`Column(name)` under every layout — so no declaration position ever needs the
reserved variant this contract gave up.

## Attributes and primary keys

```text
PrimaryKeyGeneration =
    ApplicationAssigned
  | Max
  | Sequence(name: nonempty string,
             batch_size: positive integer,
             initial_value: integer,
             increment_size: positive integer)

PrimaryKey =
    NotPrimaryKey
  | PrimaryKey(generation: PrimaryKeyGeneration)

AttributeMetadata
  identity: AttributeIdentity
  type: NeutralType
  storage: StorageLocation
  primary_key: PrimaryKey
  nullable: boolean
  max_length: positive integer | absent
  read_only: boolean
  optimistic_locking: boolean
  framework_owned: boolean
```

Primary-key
generation is available only through the `PrimaryKey` branch; a
non-primary-key attribute cannot carry a meaningless ApplicationAssigned,
Max, or Sequence value. Frontends normalize an omitted generator on a declared
primary key to `PrimaryKey(ApplicationAssigned)`.

`framework_owned` is **derived, never authored**. It answers who supplies the
value — the framework, never the caller — and is true exactly when the
attribute carries `optimistic_locking`, or its `identity` appears as the
`start_attribute` or `end_attribute` of one of the containing Entity's As-Of
Axes (below). Further categories a later contract designates set the same
member, so designating one is the whole cost of adding it: no assigning surface
changes and no rejection joins the vocabulary.
Because the fact is a function of two levels — a flag on the attribute, and
axis membership knowable only from the Entity — a frontend derives it while
normalizing an Entity's declarations, and one derivation serves every frontend.

Derivation carries three consequences worth stating rather than inferring. The
designation has **no authoring form**: no descriptor key, no schema property,
no fixture, and no corpus record changes, and a frontend that accepted one
would be accepting a fact it must compute. It is a member of accepted Metadata
rather than a lookup a consumer performs, so a surface that resolves a member
without the Entity around it — a language frontend judging an assignment
against a class's own declared member — states the same verdict as one that
has the whole model. And it is a **distinct** fact from the two designations
beside it: `optimistic_locking` names a role, `read_only` says the caller
supplies the value once and may not change it, and keeping the three apart is
what lets a rejection say which of the three it is.

`NeutralType` and `NeutralValue` belong to `m-core`; descriptor type and value
spellings do not cross this interface.

## Value Objects and indices

```text
ValueObjectMetadata
  identity: ValueObjectIdentity                 # path length = 1
  storage: StorageLocation
  multiplicity: Multiplicity
  nullable: boolean
  attributes: immutable sequence<ValueObjectAttributeMetadata>
  value_objects: immutable sequence<NestedValueObjectMetadata>

NestedValueObjectMetadata
  identity: ValueObjectIdentity                 # path length >= 2
  multiplicity: Multiplicity
  nullable: boolean
  attributes: immutable sequence<ValueObjectAttributeMetadata>
  value_objects: immutable sequence<NestedValueObjectMetadata>

ValueObjectAttributeMetadata
  identity: ValueObjectAttributeIdentity
  type: NeutralType
  nullable: boolean

IndexMetadata
  identity: IndexIdentity
  attributes: nonempty immutable sequence<AttributeIdentity>
  unique: boolean
```

Only a top-level Value Object owns Storage Location. A nested occurrence and a
Value Object Attribute cannot carry Entity-only storage, primary-key,
generation, locking, or default facts. `One + nullable` represents an optional
single composite. `Many` is an ordered, non-null collection that may be empty;
`Many + nullable` is invalid. There is no mapping discriminator or separate
Value Object cardinality algebra.

Every Index component is a distinct local Attribute of the Index's Entity and
preserves declaration order. Indices are not inherited and do not repeat
physical column names; storage consumers resolve those through Attribute
Metadata.

Index Identities are distinct within one Entity, so `EntityMetadata.index` has
exactly one answer for every name. A frontend that derives an Index hands it
over as an ordinary Index, so it claims its name against the rest: identity
alone decides the collision, and matching components neither cause nor excuse
one.

## As-Of Axes

```text
TemporalDimension = ValidTime | TransactionTime

AsOfAxisMetadata
  dimension: TemporalDimension
  start_attribute: AttributeIdentity
  end_attribute: AttributeIdentity
```

The dimension identifies the axis. There is no separate axis name, identity,
kind, or query-default member. Both attributes belong to the containing Entity,
have Timestamp Neutral Type, are distinct, and form `[start, end)`. Valid Time
conventionally maps `validStart`/`validEnd` to `from_z`/`thru_z`; Transaction
Time maps `txStart`/`txEnd` to `in_z`/`out_z`. Both endpoint Attributes carry
the derived `framework_owned` designation, which is where that membership is
observable to a surface holding one Attribute and no axis.

## Issues and locations

`m-metamodel` owns the dependency-free issue value used by the resolver and
every semantic rule set:

```text
MetamodelIssue
  code: nonempty owner-prefixed kebab-case IssueCode
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

Every issue is fatal. Message text is explanatory and excluded from equality
and ordering. Equality is `(code, location, related)`. Descriptor paths,
language class names, source spans, and arbitrary property strings are outside
the issue contract.

Canonical issue ordering is
`(location.canonical_key, code, related.map(canonical_key))`. `ModelRoot` sorts
first. Other locations group by Entity Identity and then fixed rank Entity,
Attribute, Relationship, Value Object, Value Object Attribute, As-Of Axis,
Index. Within an axis location, Valid Time precedes Transaction Time.

The complete foundational Issue Code set is declared by the formation manifest
in [`m-model-formation`](m-model-formation.md). No other module may emit a
`metamodel-*` code.

| Code | Foundational rule |
|---|---|
| `metamodel-invalid-entity-identity` | Namespace/name violates the canonical Entity Identity grammar. |
| `metamodel-duplicate-entity-identity` | Two Unresolved declarations resolve to the same Entity Identity. |
| `metamodel-unresolved-entity-reference` | An Entity Reference does not resolve under the exact/relative namespace rule. |
| `metamodel-unresolved-attribute-reference` | An Attribute Reference does not resolve to a declared local Attribute. |
| `metamodel-unresolved-relationship-reference` | A Relationship Reference does not resolve to a declared local Relationship. |
| `metamodel-local-member-collision` | Attribute, Relationship, or top-level Value Object names collide in one Entity, or scalar/nested names collide in one Value Object. |
| `metamodel-temporal-member-reserved` | A non-framework member uses a derived temporal Attribute name reserved by the Entity's temporal shape. |
| `metamodel-primary-key-missing` | A standalone Entity has no local primary-key Attribute. |
| `metamodel-primary-key-multiple` | A standalone Entity has more than one local primary-key Attribute. |
| `metamodel-index-identity-duplicate` | Two Indices of one Entity bear the same name. |
| `metamodel-index-empty` | Index Metadata has no Attribute component. |
| `metamodel-index-attribute-missing` | An index component names no declared Attribute. |
| `metamodel-index-attribute-not-local` | An index component is inherited or belongs to another Entity; indices contain local components only. |
| `metamodel-index-attribute-duplicate` | One Attribute occurs more than once in an Index. |
| `metamodel-as-of-dimension-duplicate` | One Entity declares the same Temporal Dimension more than once. |
| `metamodel-as-of-attribute-missing` | An axis start or end Attribute does not exist. |
| `metamodel-as-of-attribute-owner` | An axis start or end Attribute belongs to another Entity. |
| `metamodel-as-of-attribute-type` | An axis start or end Attribute is not Timestamp. |
| `metamodel-as-of-attribute-duplicate` | Axis start and end identify the same Attribute. |

An unresolved relationship or inheritance parent uses the relevant
foundational reference code. Semantic coherence after successful resolution is
reported by the owning module's Rule Set, never by a second `metamodel-*` code.

## Compiled metadata and facets

```text
CompiledMetadata
  entities: canonical immutable sequence<EntityMetadata>
  entity(EntityIdentity) -> EntityMetadata | absent

FacetKey<T>
  owner: canonical module-catalog identity

Metamodel
  entities: canonical immutable sequence<EntityMetadata>
  entity(EntityIdentity) -> EntityMetadata | absent
  facet(FacetKey<T>) -> T
```

Facet retrieval is total for an accepted Formation Profile. The generic facet
mechanism is an internal collaboration seam; each owner exposes a typed
`view(model)` function. `m-metamodel` imports no semantic owner and knows no
contributor implementation; opaque facet keys and installed facet values do
not give it formation-composition responsibility.

The Metadata Compiler may expand an already validated acyclic Value Object
occurrence graph and build immutable local indexes. It may not decide semantic
validity, pair relationships, invert cardinalities, derive inheritance,
classify temporal behavior, or emit issues.

## Activation consistency

The normalized contract is activated atomically across the module catalog,
dependency graph, canonical descriptor schema, compatibility models and cases,
generated artifacts, conformance tools, and every active language consumer.
No runtime may claim this contract while those artifacts describe the previous
descriptor-shaped metamodel. Contract artifacts become green before runtime
behavior migrates.
