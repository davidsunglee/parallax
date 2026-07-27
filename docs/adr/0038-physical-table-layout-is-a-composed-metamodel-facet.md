# Physical Table Layout is a composed Metamodel Facet

Physical table shape is owned by the deep `m-storage-layout` module rather than
by inheritance or by each storage consumer. For every physical Table, its
immutable Table Layout identifies the container, provides the complete ordered
Column Slot sequence and physical primary key, preserves each slot's contributor
provenance and Entity applicability, and resolves effective nullability. Read
projection, write shaping, DDL derivation, fixture provisioning, and table
read-back consume that one view instead of reconstructing physical shape.

Column order is table-wide and semantic. The canonical tiers are identity,
discriminator, domain, temporal, audit, then document. Declaration order remains
stable within a tier, but tiers take precedence over declaring ancestry. A
table-per-hierarchy layout considers the complete shared-table superset; each
table-per-concrete-subtype layout considers the concrete Entity's complete
ancestry-derived shape. The resulting order may place descendant domain
attributes before root-owned temporal or audit attributes. Preserving an older
per-ancestor or pre-capability column sequence as a prefix is not a contract.

A Column Slot records its physical column, tier, contributing Attribute, Value
Object occurrence, or inheritance discriminator, declaring owner, effective
nullability, and applicable Entity set. Primary-key layout selects identity-tier
slots rather than restating columns. Two distinct contributors claiming one
column in the same Table fail Model Formation as
`storage-layout-column-collision`; no storage consumer chooses a winner.
Inheritance continues to own `inheritance-materialization-key-collision`
because `familyVariant`, relationship views, and materialized object keys occupy
the result keyspace rather than physical table storage.

The module composes structural facts without requiring every possible behavioral
contributor. Its mandatory inputs are accepted Metadata and the Inheritance
Facet. Temporal axes and Audit Metadata, when present, designate already
declared Attribute Identities for their tiers; absence leaves the corresponding
tier empty. In particular, `m-storage-layout` does not depend on
`m-audit-provenance`. An audit-capable profile supplies explicit Audit Metadata
and the audit behavior depends on the resulting layout; a profile without audit
supplies none. The temporal `revisionInstantAttribute` alias of Transaction-Time
start therefore produces one temporal slot and no duplicate audit slot.

The direct dependency direction is:

```text
m-storage-layout --> m-metamodel
m-storage-layout --> m-inheritance

m-audit-provenance --> m-storage-layout
```

Inheritance retains family topology, strategy, concrete applicability,
discriminator semantics, and ancestry. Storage Layout asks those questions
through the Inheritance Facet and owns only the composed physical-table answer.
This keeps a small interface over the full storage-shape complexity while
allowing future structural contributors to add an optional tier or slot
classification without coupling every consumer to that contributor.
