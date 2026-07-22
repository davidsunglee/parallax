# Behavioral modules depend on the Metamodel Interface

Parallax behavioral modules depend on a language-neutral **Metamodel
Interface**, not on the canonical YAML/JSON descriptor record graph. The
interface exposes a complete model's normalized, locally declared metadata and
model-relative lookup; inheritance expansion, temporal classification,
navigation, SQL lowering, and other derived semantics remain owned by their
existing specification modules. This keeps one semantic contract without
making one serialized representation the runtime architecture of every
language implementation.

`m-descriptor` remains the authoritative canonical interchange format, schema,
and JSON/YAML serialization contract for conformance, tooling, and
cross-language transport. A descriptor adapter and a native language frontend
each expose an Unresolved Metamodel input view; neither is an accepted
Metamodel implementation. The one Metadata Compiler produces the sole accepted
Compiled Metadata graph, and the accepted Metamodel exposes that exact graph
with its complete facet set. In particular, Python may index its Pydantic
Entity Classes at the unresolved and binding seams without creating either a
parallel descriptor graph or a second accepted Metadata graph. Canonical
descriptor export is an adapter over the accepted Metamodel rather than the
source of runtime truth.

Descriptor ingestion is complete before that adapter exists. Malformed
JSON/YAML raises `DescriptorSyntaxError(descriptor-invalid-syntax)` with format,
optional source coordinates, and cause; a decoded document outside the
canonical schema raises `DescriptorSchemaError(descriptor-schema-invalid)`
with canonically ordered structured document-path violations; schema-valid
text whose denoted core value is unconstructible — an out-of-bounds or
non-canonical decimal type spelling — raises
`DescriptorValueError(descriptor-value-invalid)` with the same canonically
ordered document-path violation shape over the value-rule vocabulary
`m-descriptor` owns. All three derive from `DescriptorError` and create no
hub. Only a document every ingestion phase accepts becomes an Unresolved
Metamodel, after which invalid references and semantic model rules use
representation-independent `MetamodelIssue` and `MetamodelValidationError`;
descriptor paths never become Model Locations.

Frontend equivalence is qualified by authoring reach: for models both
grammars can author, the two frontends must expose identical normalized
facts, name resolution, and formation outcomes, while grammar-level failures
stay representation-specific — each grammar rejects its own unspellable or
ill-formed inputs through its own error surface (the descriptor's ingestion
phases; Python class creation), and a shape only one grammar can spell
carries no equivalence obligation. Conformance continues to require
deterministic canonical descriptor export and the corpus canonicalization
law, but behavioral-module dependency
edges move from `m-descriptor` to the accepted Metamodel Interface wherever
serialization is not the concern. The accepted graph and its lookup indexes are
created once by compilation and frozen before the interface becomes usable, so
native reflection cannot change the model after validation. A hub may delegate
to that graph and add lifecycle, binding, or export context, but may not
reconstruct accepted Metadata/facets or maintain independent normalized
accepted-metadata indexes.

Every sealed Metamodel is canonically exportable by contract. Document exports
are structurally deterministic and JSON/YAML exports are byte-deterministic,
with no renewed validation, state change, partial output, or descriptor graph
cached during formation. An unexpected adapter failure raises
`DescriptorExportError(descriptor-export-failed)` with the export target and
cause while leaving the Metamodel sealed; use before sealing remains a hub
state error.

Model-formation rules remain with the modules that own their meaning rather
than moving into `m-metamodel`. Their deterministic composition is the separate
`m-model-formation` concern recorded in ADR 0030; behavioral algorithms consume
only a Metamodel that this composition has accepted.

The two frontends converge before validation on the same Unresolved Metamodel
contract rather than on one another's concrete representation. The
foundational `m-metamodel` resolver turns that value into a Candidate Metamodel
containing canonical structured Identities throughout. Semantic rule sets
consume only the Candidate Metamodel; behavioral algorithms consume only the
accepted Metamodel produced after every rule and compiler succeeds. A
resolution failure produces no Candidate Metamodel, and neither formation
input is a behavioral interface.

Unresolved Metamodel is deliberately enumeration-only: it exposes a nonempty
immutable sequence of unresolved Entity declarations and no lookup, facets, or
uniqueness promise. Every frontend rejects an empty source before this seam.
Duplicate identities are valid resolver input, and frontend/source order is
diagnostic rather than semantic. Resolution alone constructs the canonical
Entity Declaration sequence and total identity lookup of
Candidate Metamodel. This state preserves identity-resolved authoring structure
for semantic validation, including defining/reverse relationship forms and
reusable Value Object shape graphs. Accepted Metamodel is a separate protocol,
not a subtype. After all Rule Sets succeed, the one issue-free `m-metamodel`
Metadata Compiler creates internal Compiled Metadata, then each semantic Model
Compiler consumes that view and its declared facet dependencies to return
exactly one typed facet. The accepted Metamodel combines the two atomically
without another metadata copy. Frontends may provide native read-only views at
the unresolved boundary and need not materialize a shared record graph.

The Metadata Compiler may normalize only representation after all owner rules
succeed—for example, preserve validated Relationship Declarations, expand a
validated acyclic Value Object shape graph, and build local indexes. It never
pairs relationship directions, swaps joins, or inverts cardinality; those
derivations belong to the `m-relationship` facet recorded in ADR 0032. It
cannot emit issues. Semantic compilers are facet-only; there is no mutable
Entity draft, metadata patch merge, or partial-field contribution protocol.

`UnresolvedEntityDeclaration` is shallow rather than an unresolved twin of the
Metadata graph. It carries identity, Storage Container, persistence, and
immutable Attribute Metadata, Unresolved Relationship Declaration, Value
Object Occurrence Declaration, As-Of Axis Metadata,
`Inheritance<EntityReference>`, and Index Metadata sequences. Only
reference-bearing or occurrence-relative shapes have separate Declaration
protocols. Its member names are unqualified because all facts are local, while
resolved Entity Metadata uses `declared_*`
to distinguish local and effective views. Entity-list position is
non-semantic, but every local sequence preserves authoring order.

`EntityDeclaration` preserves that exact shallow structure, replacing
Unresolved Relationship Declaration with Relationship Declaration and the
Entity Reference inheritance specialization with Inheritance Metadata. Its
reusable Value Object shape graph remains unchanged for owner validation. It
exposes no member lookup, effective view, facets, or behavioral authority.

The immutable `MetamodelIssue` value belongs to `m-metamodel`, allowing its
foundational resolver and every semantic rule set to report the same stable
code, primary Model Location, ordered related-location sequence, and message
without a reverse dependency on `m-model-formation`. Issue Codes are stable
module-owned kebab-case tokens prefixed by the canonical module-catalog stem,
not one central enum. Each Model Formation Rule Set declares its complete code
set; Formation Profile drift checks reject prefix or cross-owner collisions,
and the runner treats an undeclared emission as an implementation contract
failure. Every issue is fatal; message text is excluded from equality and
canonical ordering. The formation module owns `MetamodelValidationError`,
aggregation, and orchestration rather than another issue representation.

Profile drift, invalid or undeclared Issue Codes, duplicate issue identities,
missing or duplicate facets, and unexpected resolver, Rule Set, or compiler
failures are implementation contract defects rather than invalid metadata.
`m-model-formation` reports them through the supported coded
`FormationContractError(RuntimeError)`, with the responsible module when
applicable and the original exception as cause. Formation publishes no
accepted Metamodel or facets after either a contract error or validation error.

Model Location is the closed semantic union of model root, Entity, Attribute,
Relationship, Value Object, Value Object Attribute, Index, and As-Of Axis
locations, all carried by structured core identities. It does not expose a
descriptor path, Python class name, source span, or free-form property path.
Each frontend may map the same semantic location to its own source coordinates
outside the Metamodel Issue contract.

Canonical issue order is location-first, grouping non-root locations by the
established Entity Identity order and then by Entity, Attribute, Relationship,
Value Object, Value Object Attribute, As-Of Axis, and Index location rank.
Identity components and containment paths compare lexicographically; Valid
Time precedes Transaction Time. Issue Code and the semantic-order related
locations break ties. Messages, contributor order, frontend order, and
parallel scheduling do not participate.

The interface never flattens effective metadata into an entity declaration. A
subtype exposes only members introduced at that position, a TPH concrete
subtype exposes no inherited root table, and a descendant exposes no inherited
root axes. Owner modules compute effective members, table selection,
temporality, and other inherited consequences from the accepted local facts.
This prevents class-backed and descriptor-backed adapters from maintaining a
second derived model graph that could disagree with its semantic owner.
Protocol members whose effective value can differ through inheritance are
named with a `declared` qualifier; unqualified effective-looking accessors are
not part of the interface.

Model Formation may precompute those effective views once as immutable,
module-owned Metamodel Facets. A facet retains declaration provenance and does
not mutate, replace, or masquerade as the local declaration view. Behavioral
modules read their own facets rather than repeating stable graph walks at query
or write time.

Each contributing semantic module owns a typed `FacetKey<T>` identified by its
canonical module-catalog identity and hides generic
`Metamodel.facet(FacetKey<T>) -> T` retrieval behind its typed `view(model)`
API. The explicit Formation Profile supplies exactly one compiler for every
required key, rejects missing or duplicate keys, and installs all compiled
facets atomically. This mechanism introduces no contributor imports,
registration, string-keyed public map, or ambient facet side table in
`m-metamodel`.

There is deliberately no generic flattened Entity Metadata view: effective
members depend on the question being asked. A concrete ancestry chain, an
abstract-position projection superset, a family identity, and a physical table
column set are distinct `m-inheritance` views even when they begin with the same
local declarations. `models.meta(...)` therefore remains the declaration view;
callers obtain contextual effective answers only through the owning facet.

The interface preserves semantic absence without preserving irrelevant source
spelling; generic Optional/Presence wrappers and
descriptor-owned unset sentinels are not part of the contract.

Ordering distinguishes sets from declared sequences. Entity enumeration and
other true sets use a specified identity-based total order, while every local
member collection preserves declaration order. Attributes, relationships,
Value Objects and their nested members, indices, As-Of Axes, composite-key
components, index components, and ordering clauses are therefore not
alphabetized during normalization or export.

Recursive metadata uses distinct shapes where the domain has distinct valid
states. A top-level Value Object Metadata view requires its Storage Location, a
Nested Value Object Metadata view has no storage position, and a Value Object
Attribute Metadata view cannot carry Entity-only storage, generation, or
locking facts. The initial `StorageLocation = Column(name)` algebra makes the
top-level location a Structured Column without equating model-member identity
with a column string. There is no `mapping` member or constant
`mapping="json"` declaration: structured-column storage is the only initially
supported semantics, and the dialect derives its concrete JSON-like database
type from Value Object Metadata.
Top-level and nested Value Object Metadata both expose
`multiplicity: Multiplicity`, reusing the closed `One | Many` algebra. One is a
single embedded object; Many is an ordered collection in the same Structured
Column. There is no Value Object-specific Cardinality or collection flag.
Nullability applies only to One. Many is always a present collection, possibly
empty; Model Formation rejects `Many + nullable` so null and empty cannot both
represent no contained values.

Each container has one navigable local-member namespace. Entity attributes,
relationships, and top-level Value Objects have mutually unique names; Value
Object scalar attributes and nested Value Objects have mutually unique names
at every recursive position. Temporal framework attributes reserve their
standard local names. Model Formation rejects cross-category collisions.
Indices and Temporal Dimensions remain separate key spaces because they are not
navigable members.

Inheritance extends that namespace through each ancestry chain. A descendant
cannot redeclare or cross-category-shadow an ancestor navigable member, even
with an identical declaration. Disjoint sibling branches may reuse a name.
Model Formation owns the stable `inheritance-member-shadowing` issue and names
both declarations, allowing effective facets to avoid override precedence and
compatibility rules.

Every top-level and nested Value Object declaration must contain at least one
direct scalar or nested Value Object. The two member collections may each be
empty independently, but not together, so every finite containment tree reaches
at least one scalar leaf. Model Formation reports `value-object-empty` rather
than accepting structurally useless `{}` composites.

Value Object type dependencies must be acyclic. A reusable Value Object class
may appear at multiple containment paths, and each occurrence receives its own
path-based identity and finite metadata subtree. Direct or indirect cycles
produce `value-object-containment-cycle` with the complete cycle; the Metamodel
Interface defines no lazy, depth-bounded, or named recursive-type behavior.
Every shape is nevertheless self-identifying as model metadata:
`ValueObjectIdentity` is `(EntityIdentity, nonempty containment path)`, and
`ValueObjectAttributeIdentity` is `(ValueObjectIdentity, attribute name)`. A
top-level Value Object path has one segment; a Nested Value Object path has two
or more. The declaration identity does not give identity to runtime Value
Object values, which remain identity-free.

Core identity values are shared below behavioral algebras. An Attribute
Identity is `(Entity Identity, attribute name)` and a Relationship Identity is
`(source Entity Identity, relationship name)`. Accepted Entity Metadata
preserves the identity-resolved defining-versus-reverse declaration union:

```text
RelationshipDeclaration =
    DefiningRelationshipDeclaration(
      identity: RelationshipIdentity,
      cardinality: RelationshipCardinality,
      join: RelationshipJoin,
      dependent: boolean,
      order_by: sequence<RelationshipOrder>,
    )
  | ReverseRelationshipDeclaration(
      identity: RelationshipIdentity,
      reverse_of: RelationshipIdentity,
      order_by: sequence<RelationshipOrder>,
    )
```

Resolved operation nodes use the same identities. Relationship Join remains a
static mapping fact rather than reusing an executable attribute-to-literal
comparison node, preserving the one-way `m-op-algebra -> m-metamodel`
dependency. Python authoring gets its sole target from `Rel[T]`, while
descriptor authoring gets it from the target side of the join. The old
`relatedEntity` and optional `foreignKey` fields are removed from the
declaration vocabulary and canonical descriptor.

The active `m-relationship` module owns every relationship-specific formation
rule and compiles the symmetric Relationship Facet:

```text
RelationshipFacet
  relationship(RelationshipIdentity) -> RelationshipMetadata | absent
  relationships(EntityIdentity)
    -> immutable sequence<RelationshipMetadata> | absent

RelationshipMetadata
  identity: RelationshipIdentity
  cardinality: RelationshipCardinality
  join: RelationshipJoin(source, target)
  reverse: string | absent
  dependent: boolean
  order_by: sequence<RelationshipOrder>
```

Exact-identity lookup is total, nonthrowing, and expected amortized O(1).
Per-Entity enumeration returns absent for an unknown Entity Identity, an empty
sequence for a known Entity with no relationships, and otherwise preserves
local Relationship Declaration order. Each accepted declaration contributes
exactly one directional Relationship Metadata value; a paired association
therefore contributes one value per source Entity. The facet has no global
enumeration or separate reverse-pair lookup.

The facet requires the identity's source entity to equal the join source
entity. Its target is `join.target.entity` and is not repeated. `reverse` is a
local name scoped to that target, not another repeated Relationship Identity.
Cardinality and the join identify the many-side attribute where one exists; if
future behavior requires independent FK ownership, it must be a meaningful
Relationship Join variant rather than a parallel hint.

Direct Relationship Cardinality admits one-to-one, many-to-one, and
one-to-many only. Many-to-many is removed because one source/target attribute
equality cannot represent its association table and two joins, and the current
write model has no coherent association-row semantics for it. Applications
model the association as an explicit Entity with two direct relationships. A
future convenience requires a first-class Association Join covering reads,
writes, ownership, and temporal behavior; it cannot revive the old unsupported
cardinality string alone.

Accepted metadata represents cardinality as the closed algebra
`OneToOne | ManyToOne | OneToMany`, not as descriptor text. Each variant exposes
`source` and `target` Multiplicity values, where
`Multiplicity = One | Many`. Behavioral modules inspect those values rather
than compare strings. `m-descriptor` alone parses and renders spellings such as
`one-to-many`; no `ManyToMany` semantic value exists.

Bidirectional authoring has one Defining Relationship Declaration. It owns
cardinality, join, dependency, and any ordering for its own
direction. A Reverse Relationship Declaration supplies `reverse_of` plus
optional ordering for the reverse direction; it cannot repeat join,
cardinality, or dependency. In Python, `Rel[T]` establishes the reverse target,
so `reverse_of` is only a relationship name in `T`'s scope. In a descriptor,
which has no type annotation, `reverseOf` is a qualified authored Relationship
Reference. Foundational resolution changes references and target-local names
into canonical identities only. The `m-relationship` Rule Set rejects missing
targets, two reverse-only cycles, incoherent join/cardinality/dependency facts,
invalid ordering, incompatible Python annotations, or multiple defining
declarations. Its Model Compiler then swaps join sides, inverts
OneToOne/ManyToOne/OneToMany, and installs symmetric `reverse` names in the
facet.

The unresolved union is exact. Defining carries Relationship Identity,
Cardinality, `UnresolvedRelationshipJoin(source: AttributeIdentity, target:
AttributeReference(EntityReference, name))`, dependency, and target-local
Relationship Order Declarations. Reverse carries Relationship Identity,
`RelationshipReference(EntityReference, name)`, and target-local ordering
only. No branch repeats its target outside that one reference, and ordering
repeats only an attribute name. The resolver is the sole producer of the
identity-resolved Relationship Declaration union and contains no relationship
pairing or derivation.

`EntityReference` is the closed
`RelativeEntityReference(local name) | ExactEntityReference(EntityIdentity)`
union. The containing Entity supplies the lexical namespace for Relative; Exact
resolves unchanged. Direct native class targets are Exact, bare declaration
strings are Relative, and qualified strings parse to Exact. The value stores no
owner, raw spelling, optional namespace, native class, or module-global lookup
state. Ownerless behavioral operations consume resolved Entity Identity.

Relationship Order is a sequence of
`RelationshipOrder(attribute: AttributeIdentity, direction: SortDirection)`.
Sort Direction is the closed `Ascending | Descending` algebra and is shared by
operation Sort Keys through the existing `m-op-algebra -> m-metamodel`
dependency. Each relationship-order attribute belongs to the join target, and
ordering is legal only when target Multiplicity is Many. Omitted direction on
an authored term normalizes to Ascending. An omitted or empty order sequence
means no ordering and emits no `ORDER BY`; there is no `Unspecified` direction,
which would still require a database sort once a term exists.

The same rule applies to scalar types and values. `m-core` owns the closed
Neutral Type algebra—Boolean, Int32, Int64, Float32, Float64, String, Bytes,
Date, Time, Timestamp, Uuid, Json, and Decimal with precision and scale—and the
corresponding Neutral Value vocabulary. Metadata, operation literals,
assignments, and neutral rows reuse those dependency-free values. Accepted
Attribute Metadata exposes Neutral Type, not descriptor text or an untyped
object.
`m-descriptor` alone parses and renders spellings such as `decimal(18,2)`.
Behavioral modules therefore never parse type strings.

Primary-Key Generation is normalized to the closed algebra
`ApplicationAssigned | Max | Sequence`. Sequence carries a required name and
resolved batch size, initial value, and increment size; the latter three use
their semantic defaults before the model is accepted. Attribute primary-key
state is the sum `NotPrimaryKey | PrimaryKey(PrimaryKeyGeneration)`, so a
non-primary-key Attribute cannot carry a meaningless generation value.

The complete Attribute Metadata contract is deliberately small and
self-identifying:

```text
StorageLocation = Column(name: string)

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

Language authoring may omit a conventional physical name, but the Metamodel
Interface never exposes an absent or unresolved Storage Location. Each frontend
normalizes its authoring convention before publishing accepted Metadata.
The canonical descriptor specifically omits `column` when it equals the
Attribute or top-level Value Object occurrence name, retains it only for an
override, and deterministically exports the same abbreviated canonical form.

It does not duplicate `identity.name` as a second `name` member. An omitted
allocator on a primary-key Attribute normalizes to
`PrimaryKey(ApplicationAssigned)`. Value Object Attribute Metadata remains a
separate nested shape without Entity identity, column, generation, or locking
facts.

Read-only interface protocols use the full `Metadata` suffix:
`EntityMetadata`, `AttributeMetadata`, and their peers. Symmetric
`RelationshipMetadata` belongs to the typed `m-relationship` facet rather than
the base Metamodel's declared-local view. Python's conventional `*Meta` suffix
remains reserved for metaclasses and is not an abbreviation for metadata. This
prevents the old `EntityMeta` introspection vocabulary from colliding
conceptually with Entity class construction.

Lookup in the class-free interface is total and non-throwing:

```text
Metamodel.entity(EntityIdentity) -> EntityMetadata | absent
EntityMetadata.attribute(local_name) -> AttributeMetadata | absent
EntityMetadata.relationship(local_name) -> RelationshipDeclaration | absent
EntityMetadata.value_object(local_name) -> ValueObjectMetadata | absent
EntityMetadata.as_of_axis(TemporalDimension) -> AsOfAxisMetadata | absent
EntityMetadata.index(local_name) -> IndexMetadata | absent
ValueObjectMetadata.attribute(local_name) -> ValueObjectAttributeMetadata | absent
ValueObjectMetadata.value_object(local_name) -> NestedValueObjectMetadata | absent
NestedValueObjectMetadata.attribute(local_name) -> ValueObjectAttributeMetadata | absent
NestedValueObjectMetadata.value_object(local_name) -> NestedValueObjectMetadata | absent
```

These methods inspect local declarations only, accept no class or string-name
overloads, and return ordinary absence on a miss so Model Formation can
aggregate issues without exception control flow. Implementations maintain
private immutable indexes and provide expected amortized constant-time direct
lookup. Ordered enumeration remains a separate immutable sequence contract.
The Python `models.meta(...)` facade accepts its documented class/string/
identity conveniences and translates a miss into `MetamodelLookupError` rather
than returning null.

The complete Entity Metadata contract is:

```text
StorageContainer = Table(name: string)

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

An Entity's Storage Container is declared once and is not repeated by member
Storage Locations. Python `table=` and descriptor `table` normalize to the
initial `Table(name)` variant. `DocumentCollection(name)` is reserved as a
future container form but is not constructible under this decision.

It does not duplicate the name or namespace carried by `identity`. Persistence
Mode is the closed `ReadWrite | ReadOnly` persistence capability and does not
describe in-memory mutation, security access, or transaction semantics. A
standalone entity or family root normalizes omitted persistence to ReadWrite; a
descendant's absent `declared_persistence` means inherit and therefore remains
absent in the local view. Persistence Mode is family-wide and root-owned, so a
descendant declaration is invalid even when it repeats the effective value.
The inheritance facet supplies the root value for every position. Index
Metadata is deliberately last: it describes physical access paths and runtime
optimization rather than the preceding structural model.

Index Metadata is also self-identifying:

```text
IndexIdentity = (EntityIdentity, index name)

IndexMetadata
  identity: IndexIdentity
  attributes: nonempty sequence<AttributeIdentity>
  unique: boolean
```

Temporal Dimension is the closed `ValidTime | TransactionTime` algebra and is
itself the identity of an Entity's As-Of Axis. There is no separately authored
axis name, identity, or kind. The accepted axis shape is:

```text
AsOfAxisMetadata
  dimension: TemporalDimension
  start_attribute: AttributeIdentity
  end_attribute: AttributeIdentity
```

The attributes belong to the containing Entity, have Timestamp Neutral Type,
and form the fixed half-open interval `[start, end)`. Model Formation permits
at most one axis per dimension. Valid Time conventionally maps
`valid_start`/`valid_end` to `from_z`/`thru_z`; Transaction Time maps
`tx_start`/`tx_end` to `in_z`/`out_z`. Physical column names do not identify a
dimension.

As-Of Axis Metadata contains no defaulting member. Omission is behavioral and
is owned by `m-temporal-read`: an omitted dimension means Latest and lowers to
`end = infinity`. Now is a distinct finite current-clock instant and, if a
language exposes it explicitly, lowers to interval containment. Neither
descriptor nor operation serde may spell Latest as `now`.

Declaration and accepted Inheritance share one parent-parameterized closed
local-declaration algebra rather than parallel records or one record with
conditionally meaningful role fields:

```text
Inheritance<Parent> =
    AbstractRoot(strategy: InheritanceStrategy)
  | AbstractSubtype(parent: Parent)
  | ConcreteSubtype(parent: Parent, tag_value: string | absent)

InheritanceMetadata = Inheritance<EntityIdentity>

InheritanceStrategy =
    TablePerHierarchy(tag_column: string)
  | TablePerConcreteSubtype
```

`Inheritance<Parent>` is specification notation for the shared algebra, not a
third runtime form. An Unresolved Entity Declaration instantiates it with
Entity Reference, while `InheritanceMetadata` names the Entity Identity
specialization. Resolution replaces only a descendant's parent. The variant
is the role. Roots cannot carry parents,
descendants cannot repeat strategy, and only Table Per Hierarchy carries a tag
column. Tables remain in Entity Metadata. A Concrete Subtype's local tag value
is required for a TPH family and absent for TPCS; Model Formation validates
that rule against the root without copying effective strategy onto the
descendant's local view.

Every indexed attribute belongs to the Index Identity's entity. Components are
unique and preserve declaration order. Indexes are local and never inherited;
they contain no column strings because physical lowering resolves each column
through Attribute Metadata. The uniqueness flag remains semantic because it
controls both schema constraints and cache fast paths.
