# m-relationship — Relationship Formation

`m-relationship` owns relationship-specific model-formation rules and the
immutable symmetric Relationship Facet. It depends on `m-metamodel` and
`m-model-formation`. It does not own runtime navigation, deep fetch, SQL
lowering, or cascade execution.

Accepted local Entity Metadata preserves the defining-versus-reverse
Relationship Declaration union. The fixed resolver resolves references only;
it does not pair directions, swap joins, or invert cardinality.

## Formation contribution

The module contributes the required `m-relationship` Rule Set and one Model
Compiler under `FacetKey(m-relationship)`. It requires no other facet. Its
complete Issue Code set is:

| Code | Rule |
|---|---|
| `relationship-join-source-invalid` | A defining join's source Attribute is not a local Attribute of the declaring Entity. |
| `relationship-join-target-invalid` | A defining join's target Attribute does not belong to the target Entity established by the declaration reference. |
| `relationship-cardinality-join-mismatch` | Cardinality and join orientation cannot identify the required one/many sides. |
| `relationship-reverse-cycle` | A reverse declaration names another reverse declaration, directly or transitively. |
| `relationship-reverse-not-defining` | A reverse declaration does not resolve to one defining declaration. |
| `relationship-reverse-inconsistent` | A reverse declaration's source/target orientation is inconsistent with the defining direction. |
| `relationship-defining-duplicate` | More than one reverse declaration claims the same defining declaration. |
| `relationship-order-on-to-one` | Ordering is declared for a direction whose target multiplicity is One. |
| `relationship-order-attribute-invalid` | An ordering term does not name a target-local Attribute. |

Reference absence is a foundational `m-metamodel` issue, not a second
relationship-owned missing-reference code.

## Validation-time join-endpoint projection

Rule Sets run in unspecified order over one Candidate Metamodel, so a Rule Set
that needs relationship facts cannot consume the Relationship Facet. This module
exposes a pure, total, issue-free projection of the bounded fact those Rule Sets
need:

```text
joinEndpoints(CandidateMetamodel) -> immutable set<AttributeIdentity>
```

It returns exactly the join endpoint Attributes of **defining** Relationship
declarations that resolve locally: for each defining declaration whose
`join.source` names a local Attribute of the declaring Entity and whose
`join.target` names an Attribute of the Entity its reference establishes, both
Identities. It emits no Issue, returns no partial or provisional value, and
never rejects, so a consumer's result does not depend on when it asks.

Restricting the projection to defining declarations loses nothing. A reverse
declaration introduces no Attribute of its own; the compiler swaps the sides of
the same join and inverts cardinality for it, so every Attribute any direction
names is already named by some defining declaration. The projection therefore
never depends on reverse resolution, which is where most of this module's
rejections live.

An endpoint of a malformed defining join is not locally resolvable and is
excluded. Such a model is rejected by this module's own Rule Set, and a consumer
that classified the excluded Attribute differently in the meantime has not
changed that outcome — a consumer's own Issue on an already-rejected model is
permitted and unordered with respect to this one.

`m-storage-layout` is the projection's consumer: accepted Relationship Joins
designate direct-role Attributes, and its Rule Set must know them before any
facet exists.

## Facet

```text
RelationshipFacet
  relationship(RelationshipIdentity) -> RelationshipMetadata | absent
  relationships(EntityIdentity)
    -> immutable sequence<RelationshipMetadata> | absent

RelationshipMetadata
  identity: RelationshipIdentity
  cardinality: OneToOne | ManyToOne | OneToMany
  join: RelationshipJoin(source: AttributeIdentity,
                         target: AttributeIdentity)
  reverse: nonempty local relationship name | absent
  dependent: boolean
  order_by: immutable sequence<RelationshipOrder>
```

Exact lookup is total, nonthrowing, and expected amortized `O(1)`. Per-Entity
enumeration returns absence for an unknown Entity, empty for a known Entity
with none, and otherwise preserves local declaration order.

The compiler returns one directional value for every accepted declaration. It
swaps join sides and inverts cardinality for reverse directions, but never
copies or replaces the accepted local Relationship Declarations. The target is
`join.target.entity` and is not repeated. No `relatedEntity`, `foreignKey`, or
parallel reverse-pair map exists.

`RelationshipOrder` contains one target Attribute Identity, Ascending or
Descending Sort Direction, and NullsFirst or NullsLast Null Placement. An
omitted authored direction normalizes to Ascending and an omitted authored
placement to NullsLast, which is the canonical placement in either direction.
Placement is independent of direction and is observable only on a nullable
Attribute (`m-dialect`). Direct many-to-many is invalid; applications use an
explicit association Entity.
