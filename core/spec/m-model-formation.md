# m-model-formation — Deterministic Model Formation

`m-model-formation` owns deterministic composition of module-owned model rules
and compilers. It depends only on `m-metamodel`; contributing semantic modules
depend on both. It imports no contributor, performs no discovery, and owns no
semantic rule or Issue Code.

The explicit composition root supplies one Formation Profile. Import-time
registration, decorators, entry points, plugins, ambient registries, and
mutable contributor lists are forbidden.

## Contributor interfaces

The following interfaces are exact. `ModuleIdentity` is a canonical
`m-<slug>` identity from the core module catalog.

```text
ModelRuleSet
  owner: ModuleIdentity
  issue_codes: immutable set<IssueCode>
  validate(candidate: CandidateMetamodel)
    -> immutable sequence<MetamodelIssue>

MetadataCompiler
  owner: ModuleIdentity = m-metamodel
  compile(candidate: CandidateMetamodel) -> CompiledMetadata

ModelCompiler<T>
  owner: ModuleIdentity
  facet_key: FacetKey<T>
  requires: immutable set<FacetKey<?>>
  compile(metadata: CompiledMetadata,
          required_facets: immutable mapping<FacetKey<?>, object>) -> T

FormationProfile
  rule_sets: immutable sequence<ModelRuleSet>
  metadata_compiler: MetadataCompiler
  model_compilers: immutable sequence<ModelCompiler<?>>
```

`required_facets` contains exactly the compiler's declared `requires` keys.
Each returned value is immutable and is installed only under its compiler's
`facet_key`. Rule sets emit issues only; compilers emit facets only. A compiler
cannot return an issue sequence, metadata patch, or partial Entity update.

The fixed foundational resolver is owned by `m-metamodel` and is not a profile
contributor. Its exact collaboration result is:

```text
ResolutionResult =
    Resolved(candidate: CandidateMetamodel)
  | Rejected(issues: nonempty immutable sequence<MetamodelIssue>)

resolve(unresolved: UnresolvedMetamodel) -> ResolutionResult
```

## Authoritative formation manifest

Catalog completeness is measured against this manifest, never against the
runtime objects that happen to be supplied. The manifest is the authoritative
closed set for the normalized metamodel contract. A runtime Formation Profile
is complete only when its contributors match every required row and no other
row.

| Owner | Rule set | Complete owned Issue Codes | Compiler / facet | Required modules | Required facets |
|---|---|---|---|---|---|
| `m-metamodel` | fixed resolver, not a supplied Rule Set | `metamodel-invalid-entity-identity`, `metamodel-duplicate-entity-identity`, `metamodel-unresolved-entity-reference`, `metamodel-unresolved-attribute-reference`, `metamodel-unresolved-relationship-reference`, `metamodel-local-member-collision`, `metamodel-temporal-member-reserved`, `metamodel-primary-key-missing`, `metamodel-primary-key-multiple`, `metamodel-index-empty`, `metamodel-index-attribute-missing`, `metamodel-index-attribute-not-local`, `metamodel-index-attribute-duplicate`, `metamodel-as-of-dimension-duplicate`, `metamodel-as-of-attribute-missing`, `metamodel-as-of-attribute-owner`, `metamodel-as-of-attribute-type`, `metamodel-as-of-attribute-duplicate` | mandatory Metadata Compiler; no facet | none | none |
| `m-pk-gen` | none; invalid generator states are unconstructible in normalized Metadata | none | none | `m-metamodel` | none |
| `m-inheritance` | required | `inheritance-cycle`, `inheritance-missing-root`, `inheritance-multiple-roots`, `inheritance-concrete-without-abstract-root`, `inheritance-strategy-redeclared`, `inheritance-missing-tag-value`, `inheritance-duplicate-tag-value`, `inheritance-tag-on-concrete-subtype-strategy`, `inheritance-tph-root-table-required`, `inheritance-tph-descendant-table-forbidden`, `inheritance-tpcs-abstract-table-forbidden`, `inheritance-tpcs-concrete-table-required`, `inheritance-primary-key-missing`, `inheritance-primary-key-multiple`, `inheritance-temporal-axes-not-root-owned`, `inheritance-optimistic-locking-not-root-owned`, `inheritance-persistence-not-root-owned`, `inheritance-member-shadowing` | `InheritanceFacet` under `FacetKey(m-inheritance)` | `m-metamodel`, `m-model-formation` | none |
| `m-value-object` | required | `value-object-empty`, `value-object-containment-cycle`, `value-object-many-nullable` | none; accepted occurrences are expanded by the Metadata Compiler after validation | `m-metamodel`, `m-model-formation` | none |
| `m-relationship` | required | `relationship-join-source-invalid`, `relationship-join-target-invalid`, `relationship-cardinality-join-mismatch`, `relationship-reverse-cycle`, `relationship-reverse-not-defining`, `relationship-reverse-inconsistent`, `relationship-defining-duplicate`, `relationship-order-on-to-one`, `relationship-order-attribute-invalid` | `RelationshipFacet` under `FacetKey(m-relationship)` | `m-metamodel`, `m-model-formation` | none |
| `m-temporal-read` | none | none | `TemporalFacet` under `FacetKey(m-temporal-read)` | `m-metamodel`, `m-model-formation`, `m-inheritance` | `FacetKey(m-inheritance)` |
| `m-opt-lock` | required | `opt-lock-multiple-attributes`, `opt-lock-temporal-explicit-attribute` | `OptimisticLockFacet` under `FacetKey(m-opt-lock)` | `m-metamodel`, `m-model-formation`, `m-inheritance`, `m-temporal-read` | `FacetKey(m-inheritance)`, `FacetKey(m-temporal-read)` |

An owner named here owns its complete Issue Code set exclusively. The owning
module's specification defines each rule's semantics. A rule moves between
owners only by changing this manifest and both affected module specifications
together. The fixed resolver owns every `metamodel-*` code; the formation
runner owns none.

When the normalized contract is activated, every manifest owner and required
module MUST be present in the module catalog with matching dependency edges.
Until that catalog/schema/corpus activation is complete, no runtime profile may
claim conformance to this manifest.

## Profile drift checks

Before resolution, the runner validates the complete profile against the
manifest in this exact order:

1. The Metadata Compiler is present exactly once and owned by `m-metamodel`.
2. Rule Set owner presence and absence match the manifest exactly.
3. Each Rule Set's `issue_codes` equals its manifest set exactly.
4. Every Issue Code is nonempty kebab-case and begins with the owner's catalog
   stem after `m-`.
5. No Issue Code is owned by more than one row.
6. Model Compiler owner/key presence and absence match the manifest exactly.
7. Every compiler key is unique and its owner matches the manifest.
8. Every required facet key is declared, and the dependency graph of compiler
   keys is acyclic.
9. Required module and facet edges match the manifest.

The first failing step raises `formation-profile-drift` except where the closed
error table below assigns a more specific code. Manifest row order is the table
order above and makes drift diagnostics deterministic.

## Invocation and ordering

Formation is single-publication even if an implementation parallelizes pure
work. Observable invocation and failure selection follow this deterministic
order:

1. Drift-check the complete Formation Profile.
2. Invoke the fixed resolver exactly once.
3. If resolution returns issues, canonical-sort them and raise one
   `MetamodelValidationError`; invoke no Rule Set or compiler.
4. Invoke Rule Sets sequentially in manifest order, skipping rows without one.
   Each Rule Set is invoked exactly once with the same Candidate Metamodel.
5. Validate every returned issue against that Rule Set's declared set. Reject
   duplicate issue identities, then canonical-sort the aggregate.
6. If the aggregate is nonempty, raise one `MetamodelValidationError`; invoke
   no compiler.
7. Invoke the Metadata Compiler exactly once.
8. Invoke Model Compilers in topological facet-dependency order. When two are
   simultaneously eligible, ascending owner Module Identity breaks the tie.
9. After every compiler succeeds, atomically construct the Metamodel from the
   exact Compiled Metadata object and complete facet mapping.

An implementation MAY execute independent rule sets or compilers concurrently
only if it reproduces the same returned issue order, compiler eligibility, and
failure selection as this sequence. No partial Metamodel, facet set, hub state,
class binding, or export cache is published.

## Validation and contract errors

`MetamodelValidationError(ValueError)` contains one nonempty immutable,
canonically ordered sequence of `MetamodelIssue`. It represents invalid model
input only.

Unexpected contributor behavior is a different supported error:

```text
FormationContractError(RuntimeError)
  code: FormationContractCode
  owner: ModuleIdentity | absent
  cause: exception | absent

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

The boundaries are exact:

| Failure | Code | Owner | Cause |
|---|---|---|---|
| Profile structure or manifest mismatch without a more specific code | `formation-profile-drift` | offending owner when known | preserved when raised while reading a contributor contract |
| Invalid owner prefix or malformed declared/emitted code | `formation-issue-code-invalid` | Rule Set owner, or `m-metamodel` for resolver output | absent |
| Resolver or Rule Set emits a well-formed code outside its declared complete set | `formation-issue-undeclared` | `m-metamodel` for resolver output; otherwise Rule Set owner | absent |
| Two emitted issues share `(code, location, related)` | `formation-issue-duplicate` | second emitter | absent |
| Required compiler/facet key is absent | `formation-facet-missing` | required owner when known | absent |
| Compiler/facet key occurs more than once | `formation-facet-duplicate` | duplicated owner | absent |
| Resolver raises instead of returning `ResolutionResult` | `formation-resolver-failed` | `m-metamodel` | original exception preserved |
| Resolver returns a value other than the closed `ResolutionResult`, a mutable issue collection, or an issue/value of the wrong semantic type | `formation-resolver-result-invalid` | `m-metamodel` | absent |
| Rule Set raises instead of returning its issue sequence | `formation-rule-set-failed` | Rule Set owner | original exception preserved |
| Rule Set returns a mutable collection or an element other than `MetamodelIssue` | `formation-rule-set-result-invalid` | Rule Set owner | absent |
| Metadata or Model Compiler raises, returns the wrong facet, or reaches an impossible state | `formation-compiler-failed` | compiler owner | original exception preserved when one exists |

Preserving a cause means retaining the original exception object where the host
language permits and using native exception chaining. Contract errors never
become Metamodel Issues or validation errors.

For resolver and Rule Set results, immutability is part of the return type, not
an implementation preference. A foreign-owner or malformed Issue Code is
`formation-issue-code-invalid`; a well-formed owner-local but undeclared code is
`formation-issue-undeclared`. A compiler that returns a mutable/wrong-type value,
the wrong facet type, or a facet under the wrong key is
`formation-compiler-failed`. No arbitrary callback exception escapes the runner.

## Facet ownership

Each compiling semantic module owns exactly one typed `FacetKey<T>` identified
by its Module Identity. `Metamodel.facet(key)` is total only after the complete
manifest profile succeeds. Generic facet lookup is hidden behind each owner's
typed `view(model)` interface.

Facets are immutable derived semantic views over the sole Compiled Metadata
graph. They retain declaration identities/provenance, do not mutate local
Metadata, and do not reproduce the accepted Entity/member graph. A facet MAY
own indexes over its own derived values.

## Activation order

Specification and contract artifacts precede runtime migration. Activation
must proceed in this order:

1. complete this manifest and every owning module specification;
2. update the module catalog and DAG;
3. update descriptor/operation schemas, compatibility models/cases, generated
   artifacts, and contract tooling together until their gates are green; and
4. only then change runtime formation or behavioral consumers.

There is no temporary runtime interpretation of an incomplete manifest.
