# Model formation is explicitly composed

Each core module remains the sole owner of its model-formation invariants,
stable issue codes, and derived effective semantics. A module with formation
work contributes a Model Formation Rule Set, a Model Compiler, or both through
the protocols owned by `m-model-formation`. `m-model-formation` depends only on
`m-metamodel`: it takes an Unresolved Metamodel through explicit resolution,
validation, and compilation gates, deterministically aggregates issues, and
produces immutable module-owned Metamodel Facets, but has no knowledge of
inheritance, temporal semantics, Value Objects, or which contributors exist.
Contributing modules depend on both contracts, so semantic knowledge does not
flow back into the metadata interface or formation runner.

An Unresolved Metamodel contains normalized declaration facts but may contain
structured model-relative references. The foundational resolver owned by
`m-metamodel` resolves every such reference to its canonical Identity and
collects all identity, namespace, duplicate-key, and reference issues needed
to make lookup unambiguous. Any resolution issue is a hard gate: no semantic
rule set runs and no Candidate Metamodel exists. This is a fixed foundational
phase, not a registered or contributor-supplied transform.

The state protocols intentionally expose different capabilities:

```text
UnresolvedMetamodel
  entities: nonempty immutable sequence<UnresolvedEntityDeclaration>

CandidateMetamodel
  entities: canonical immutable sequence<EntityDeclaration>
  entity(EntityIdentity) -> EntityDeclaration | absent

Metamodel
  entities: canonical immutable sequence<EntityMetadata>
  entity(EntityIdentity) -> EntityMetadata | absent
  facet(FacetKey<T>) -> T
```

An Unresolved Metamodel has no identity/member lookup, facet access, or
uniqueness guarantee because duplicate declarations are legitimate resolver
input. Every frontend rejects an empty source before producing this view. Its
sequence may preserve native source order for diagnostic mapping, but that
order has no semantic effect. The resolver builds private multimaps and creates
the canonical indexes only when it can return a Candidate Metamodel.
The latter provides total, non-throwing, expected-amortized-constant-time Entity
declaration lookup, but preserves declaration structure, has no facets, and has
no permission to enter behavioral execution. Metamodel is deliberately not a
subtype: only after validation and compilation does it expose normalized
Entity Metadata, its local member lookup, and facets. Both frontends may
implement unresolved declarations as read-only views over their native classes
or parsed document; the contract does not require a copied formation-input
record graph.

The unresolved Entity is a shallow, exact declaration protocol:

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

Reference-free facts whose final identity is known reuse their normalized
semantic values. In particular, Attribute, As-Of Axis, and Index Metadata
already have final owner-relative identities and need no parallel Declaration
types. A separate `*Declaration` protocol exists only when a shape still
carries a model-relative reference or its accepted identity depends on
occurrence expansion. The
unqualified member names are intentional because every fact in this type is
local; the resolved Entity Metadata uses `declared_*` where callers must
distinguish local from effective semantic views. The outer Entity sequence
position remains diagnostic only, while every member sequence above preserves
semantic authoring order through resolution. No declaration supplies lookup.

The resolved Entity has the same shallow local shape with only reference-bearing
facts advanced:

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

Relationship declarations retain their defining/reverse structure with
resolved identities. The Value Object declaration graph is unchanged, while
Inheritance has an Entity Identity parent. This declaration exposes no member
lookup, effective view, facets, or behavioral authority.

Inheritance does not duplicate the same variant records across candidate and
accepted phases. It uses one parent-parameterized algebra:

```text
Inheritance<Parent> =
    AbstractRoot(strategy: InheritanceStrategy)
  | AbstractSubtype(parent: Parent)
  | ConcreteSubtype(parent: Parent, tag_value: string | absent)

InheritanceMetadata = Inheritance<EntityIdentity>
```

The generic form is specification notation, not a third runtime state. An
Unresolved Entity Declaration instantiates it with Entity Reference, while
`InheritanceMetadata` names the Entity Identity specialization. Resolution
changes only descendant parents while preserving the selected variant and
every other fact.

Reusable Value Object declarations form an explicit formation-local graph:

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

One declaration node has one stable key throughout one formation run; distinct
nodes have distinct keys even when structurally equal. Keys have no canonical
spelling or order, no cross-formation equality, and never enter authoring,
export, issue locations, or accepted Metadata. They let `m-value-object`
validate reuse and cycles without relying on host-language object identity.
The Metadata Compiler expands every accepted occurrence to path-identified
Metadata and discards the key.

Frontend authoring defaults have already been normalized at this seam. In
particular, an omitted conventional Python or descriptor `column` has become
the explicit `Column(member_name)` Storage Location before Attribute Metadata
appears in an Unresolved Metamodel.

Relationship authoring remains a closed defining-versus-reverse union until the
foundational resolver establishes identities:

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

The defining target exists only at `join.target.entity`; the reverse target
exists only at `reverse_of.entity`. Each ordering attribute is a target-local
name interpreted against that single derived target, so it repeats no Entity
Reference. Neither variant contains another target, reverse name, foreign-key
hint, or the other variant's mapping facts. Resolution changes only references
and target-local names into canonical identities and produces:

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

Resolution performs no pairing or relationship derivation. The
`m-relationship` Rule Set validates the union; its Model Compiler produces the
symmetric Relationship Facet, including swapped joins, inverted cardinality,
and target-scoped reverse names. A defining declaration with no reverse
compiles with `reverse = absent`.

Entity Reference itself is the closed union:

```text
EntityReference =
    RelativeEntityReference(name: nonempty dot-free string)
  | ExactEntityReference(identity: EntityIdentity)

resolve(owner: EntityIdentity, reference):
  RelativeEntityReference(name) -> EntityIdentity(owner.namespace, name)
  ExactEntityReference(identity) -> identity
```

Containment in an Unresolved Entity Declaration supplies the owner; the
reference never repeats it. A native class target becomes Exact even when its
identity is unnamespaced. A bare authored declaration string becomes Relative,
while a qualified string is parsed immediately to an Exact Entity Reference.
No raw spelling, optional namespace, module name, native class, or global
fallback remains in the contract. Ownerless core operations accept resolved
Entity Identity, not Relative Entity Reference. A language-level string lookup
may separately parse canonical identity spelling: a bare spelling is exact and
unnamespaced, while a qualified spelling is exact and namespaced.

`m-metamodel` also owns the dependency-free immutable issue contract:

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

The code belongs to the semantic module whose rule it identifies and starts
with its canonical module-catalog stem after removing `m-`:
`m-metamodel` owns `metamodel-*`, `m-inheritance` owns `inheritance-*`, and
`m-value-object` owns `value-object-*`. Issue Code is an open vocabulary rather
than a centrally closed enum. `location` is the primary tooling focus and
`related` preserves semantic order for supporting declarations, such as an
ancestor or the remaining path through a cycle. An empty related sequence is
valid. Message text is explanatory and is excluded from equality and canonical
ordering. Every issue prevents acceptance, so the contract has no severity.

A Model Location identifies a semantic declaration, not a field inside one
source representation. The Issue Code identifies the failing rule: an invalid
attribute option therefore focuses its Attribute, a reverse mismatch focuses
one Relationship and relates the other, and a Value Object cycle preserves the
remaining semantic locations in traversal order. `ModelRoot` is reserved for
model-wide problems. No location carries JSON Pointer, Python class name,
source span, or arbitrary property string. Frontends may maintain a separate
mapping from semantic locations to their own source coordinates without
changing issue equality or conformance.

Issue aggregation ignores emission and contributor execution order. The
runner sorts by the following total key after either the resolution gate or all
semantic rule sets finish:

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

Identity and path strings compare codepoint by codepoint; containment paths and
the related-location sequence compare lexicographically without reordering
their elements. Issue equality is `(code, location, related)` while ordering is
location-first as shown. Message text, frontend source position, Formation
Profile order, and parallel scheduling do not participate.

The resolver and every contributed rule set return that same value, allowing
resolution to emit issues without depending back on `m-model-formation`.
`m-model-formation` owns the aggregate `MetamodelValidationError` and
orchestration protocols, but performs no issue translation and defines no
second resolution-issue type.

Every Model Formation Rule Set receives only an immutable Candidate Metamodel,
whose references are canonical Identities but whose semantic module invariants
may still fail. Rule sets all run and their issues are aggregated in canonical
order. Only an issue-free Candidate Metamodel enters compilation. The accepted
Metamodel receives final normalized Entity Metadata and the complete facet set
atomically; neither formation input is usable by behavioral modules.

One mandatory Metadata Compiler owned by `m-metamodel` performs the
declaration-to-representation boundary after validation:

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

The Metadata Compiler preserves already-valid Relationship Declarations,
expands already-valid acyclic Value Object shapes, performs other total
representation normalization, and builds immutable local lookup indexes. It
contains no relationship pairing, join swapping, or cardinality inversion. It
cannot emit issues or make semantic-validity decisions. An impossible state is
`formation-compiler-failed` owned by `m-metamodel`.

`CompiledMetadata` is an internal formation value with no facets or behavioral
authority. Semantic Model Compilers consume it plus only their declared facet
dependencies, run in acyclic order, and return exactly one typed facet each.
The runner creates the accepted Metamodel from the exact Compiled Metadata
object and complete facet set atomically; this is the sole canonical accepted
Metadata graph. A hub may delegate it and add binding/lifecycle/export context,
but may not reconstruct accepted Metadata/facets or build independent
normalized accepted-metadata indexes. There is no mutable Entity draft,
metadata patch protocol, contributor merge, or second hub-owned graph.

Every rule set declares its ownership and complete issue vocabulary:

```text
ModelRuleSet
  owner: canonical module-catalog identity
  issue_codes: immutable set<IssueCode>
  validate(CandidateMetamodel) -> immutable sequence<MetamodelIssue>
```

The fixed foundational resolver similarly declares the complete
`m-metamodel` code set. The authoritative closed contributor/code/facet
manifest is [`m-model-formation`](../../core/spec/m-model-formation.md), not the
runtime tuple itself. Before execution, Formation Profile drift checks require
the complete manifest, every code to use its owner's prefix, and no code to be
declared by more than one owner. During validation, emitting a code absent from
that rule set's declaration is a formation-contract failure, not another
candidate issue. Model Compilers return facets and cannot emit validation
issues.

Those implementation and assembly defects use a separate supported error:

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

The runner reports `formation-issue-duplicate` when two emitted issues have the
same `(code, location, related)` equality identity; it never silently
deduplicates them. Unexpected resolver, Rule Set, and compiler exceptions are
wrapped as `formation-resolver-failed`, `formation-rule-set-failed`, and
`formation-compiler-failed`, respectively, with the exact owner and original
cause. A mutable or wrong-type resolver/Rule Set return is classified as
`formation-resolver-result-invalid` or
`formation-rule-set-result-invalid`, respectively. Profile, code-declaration,
and facet-assembly defects use their
corresponding stable code and owner when applicable. None becomes a
`MetamodelIssue` or `MetamodelValidationError`. On either validation or
contract failure, formation publishes no accepted Metamodel or facet set and a
class-backed hub installs no Entity Class binding.

Invocation is deterministic: drift-check the manifest; invoke the fixed
resolver once; invoke Rule Sets once each in manifest order; aggregate and
canonical-sort issues; invoke the Metadata Compiler once; then invoke Model
Compilers in facet-dependency topological order, breaking eligible ties by
owner identity. The first unexpected callback failure in that order is the
reported contract error. Implementations may parallelize only when they
reproduce the same issue order and failure selection.

Every runtime's composition root explicitly assembles two separate immutable
values: Formation Manifest data containing only contributor identities, Issue
Codes, facet keys, and dependencies; and a complete, ordered Formation Profile
containing the corresponding implementations. The runner receives both and
drift-checks the profile against the manifest; activation also checks that
every manifest owner/dependency is present in the active core module catalog.
The runner may inspect contributor identities from the manifest but imports
and owns no contributor implementation. The composition root is the one place
allowed to know all concrete contributors. Import-time registration,
decorator enrollment, plugin discovery, and ambient formation registries are
rejected because they would make model validity and effective behavior depend
on import order and process state.

Formation never propagates effective facts into or mutates either formation
input's authoritative local declarations. After every rule set succeeds,
the Metadata Compiler creates final normalized local Metadata, then semantic
Model Compilers create immutable facets such as ancestry, effective members,
physical table selection, and effective temporal axes while retaining
declaration provenance. A Metamodel Hub installs the resulting accepted
Metamodel and performs language-realization claims only after formation
succeeds completely.

Each compiling module owns one typed `FacetKey<T>` identified by its canonical
module-catalog identity. Its compiler emits exactly one value for that key, and
its behavioral API hides `Metamodel.facet(FacetKey<T>) -> T` behind a typed
`view(model)` function. The Formation Profile rejects missing or duplicate
compiler keys before formation; the runner installs the complete immutable
facet set atomically. `m-metamodel` provides only this generic typed attachment
mechanism and imports no contributor. There is no facet registry, side table,
string-keyed map, or runtime discovery.
