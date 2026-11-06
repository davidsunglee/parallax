# m-relationship — Relationship Formation

`m-relationship` owns relationship-specific model-formation rules and the
immutable symmetric Relationship Facet. It depends on `m-metamodel` and
`m-model-formation`. It does not own runtime navigation, deep fetch,
or SQL lowering.

Accepted local Entity Metadata preserves the defining-versus-reverse
Relationship Declaration union. The fixed resolver resolves references only;
it does not pair directions, swap joins, or invert cardinality.

## Formation contribution

The module contributes the required `m-relationship` Rule Set and one Model
Compiler, which requires no other facet. Its complete Issue Code set is:

| Code | Rule |
|---|---|
| `relationship-join-source-invalid` | A defining join's source Attribute is not a local Attribute of the declaring Entity. |
| `relationship-join-target-invalid` | A defining join's target Attribute does not belong to the target Entity established by the declaration reference. |
| `relationship-join-type-mismatch` | Resolved defining join endpoints have unequal declared neutral types or multiplicities. |
| `relationship-cardinality-join-mismatch` | Cardinality and join orientation cannot identify the required one/many sides. |
| `relationship-reverse-cycle` | A reverse declaration names another reverse declaration, directly or transitively. |
| `relationship-reverse-not-defining` | A reverse declaration does not resolve to one defining declaration. |
| `relationship-reverse-inconsistent` | A reverse declaration's source/target orientation is inconsistent with the defining direction. |
| `relationship-defining-duplicate` | More than one reverse declaration claims the same defining declaration. |
| `relationship-order-on-to-one` | Ordering is declared for a direction whose target multiplicity is One. |
| `relationship-order-attribute-invalid` | An ordering term does not name a target-local Attribute, or names a scalar collection. |

Reference absence is a foundational `m-metamodel` issue, not a second
relationship-owned missing-reference code.

Every defining join MUST have exactly equal declared neutral scalar types at its resolved source and target, including inherited Attributes. Int32 differs from Int64, and String differs from Uuid; input coercion, Wire spelling, physical layout, and database casts do not establish equality. Both endpoints MUST also have equal multiplicity; because a primary key is never a scalar collection (`m-metamodel`), an endpoint that is a scalar collection always fails this rule or the cardinality rule. Existing ownership, key orientation, cardinality, ordering, and nullability rules still apply.

A type mismatch is reported only when both endpoints resolve. Its location is the defining Relationship Declaration, its related locations are the join-addressed source and target Attributes in that order, and its message identifies both addressed endpoints and declared types. An inherited Attribute supplies its ancestor's declared type without replacing the descendant-addressed diagnostic location. Type, cardinality, and ordering defects aggregate independently after foundational resolution succeeds. Reverse declarations derive the same validated join and emit no second type-mismatch issue.

## Validation-time join-endpoint projection

Rule Sets run in unspecified order over one Candidate Metamodel, so a Rule Set
that needs relationship facts cannot consume the Relationship Facet. The join
endpoints such a Rule Set needs are, for each **defining** declaration whose
`join.source` names a local Attribute of the declaring Entity and whose
`join.target` names an Attribute of the Entity its reference establishes, both
Identities. Reading them emits no Issue and depends on no other Rule Set's
outcome.

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

The Relationship Facet answers one **Relationship Metadata**
(`RelationshipMetadata`) value per accepted declaration, by its Relationship
Identity and as a per-Entity enumeration. A value
states its direction: its identity, cardinality, `join` from `source` to `target`
Attribute Identity, the local name of its `reverse` when it has one, whether it is
`dependent`, and its ordering.

Exact lookup is total and nonthrowing. Per-Entity enumeration returns absence for
an unknown Entity, empty for a known Entity with none, and otherwise preserves
local declaration order.

The compiler returns one directional value for every accepted declaration,
swapping join sides and inverting cardinality for reverse directions. The target
is `join.target.entity`.

`RelationshipOrder` contains one target Attribute Identity, Ascending or
Descending Sort Direction, and NullsFirst or NullsLast Null Placement. An
omitted authored direction normalizes to Ascending and an omitted authored
placement to NullsLast, which is the canonical placement in either direction.
Placement is independent of direction and is observable only on a nullable
Attribute (`m-dialect`). A term orders by one scalar value, so it never names a
scalar collection, which has no whole-collection ordering. Direct many-to-many
is invalid; applications use an explicit association Entity.
