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
| `relationship-defining-duplicate` | More than one defining declaration claims the same bidirectional association. |
| `relationship-order-on-to-one` | Ordering is declared for a direction whose target multiplicity is One. |
| `relationship-order-attribute-invalid` | An ordering term does not name a target-local Attribute. |

Reference absence is a foundational `m-metamodel` issue, not a second
relationship-owned missing-reference code.

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

`RelationshipOrder` contains one target Attribute Identity and Ascending or
Descending Sort Direction. An omitted authored direction normalizes to
Ascending. Direct many-to-many is invalid; applications use an explicit
association Entity.
