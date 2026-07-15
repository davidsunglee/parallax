# Inheritance family temporal axes are declared only by the root

`m-inheritance`'s "Inherited members" wording let an `asOfAttribute` be read as
an ordinary inherited member: declared on any abstract ancestor and inherited by
its descendants, with no fixed level pinned. Independently, the reference
harness's `resolve_effective_definition` and an in-flight Python remediation
both generalized this the same way — walking an entity's own ancestry chain for
the NEAREST declarer rather than assuming the root — because nothing in the
spec text forbade an intermediate `abstract-subtype` (or a concrete subtype)
from declaring its own axes instead. Every existing corpus family (`instrument`,
`rate`) happens to declare axes only on the root, so the ambiguity was latent
until a concrete-target temporal read and a strengthened multi-milestone
fixture surfaced it: a non-temporal root with a temporal descendant, or a
temporal root whose descendant redeclares or adds an axis, had no rejection
rule at all, and "nearest declarer" would have silently accepted both.

The decision is that **temporality is a family-wide property**, not a
per-entity one. Only the family root may declare `asOfAttributes`; every
abstract and concrete descendant inherits the root's complete axis set
unchanged, and a descendant that redeclares, adds, removes, overrides, or
shadows an axis — or declares one under a non-temporal root — is rejected
pre-SQL (`inheritance-temporal-axes-not-root-owned`). A family is therefore
either entirely non-temporal or entirely temporal; mixed temporality across
branches is not supported. This is a narrowing, not an addition: every
descriptor the corpus already accepts (root-declared axes only) remains legal
and behaves identically; only the previously-unspecified mixed shapes become
rejected.

The rationale is that mixed temporality would leave several contracts
ambiguous or strategy-dependent. A root without axes could not expose a
uniform `Root.processingDate` / `Root.businessDate`; a non-temporal branch is
current-state data, not timeless data safely returned at every historical
coordinate an as-of read might pin. Root-result identity would otherwise mix
`(family, primary key)` and `(family, primary key, as-of coordinates)`
depending on which branch a row resolved through. Relationship propagation to
an abstract target would have no single axis set to propagate. Table-per-
hierarchy would need nullable or fabricated temporal primary-key components
for the family's non-temporal rows. And whether a temporal operation is even
available would depend on which branch a read had narrowed to, rather than
being a fact of the family as a whole. The abstract root owns no rows, but it
owns the family's temporal schema; every row-owning descendant is therefore
temporal together, or none is.

Ordinary inherited members are unaffected: attributes, value objects,
relationships, and mutability still follow the existing ancestry rules and may
be declared on any abstract ancestor. Only the temporal axis declaration site
is pinned to the root. Every consumer that resolves an inheritance
participant's temporal declaration — as-of default injection, explicit axis
resolution, milestone-edge computation, snapshot pin/edge attachment,
history/range materialization, graph identity coordinates, relationship and
deep-fetch propagation, and table-per-hierarchy / table-per-concrete-subtype
temporal primary-key derivation — resolves through the family root uniformly,
whether the read targets the root itself, an intermediate abstract position,
or a concrete subtype.

This is a deliberate simplification relative to Reladomo, prior art for the
semantic direction generally: Reladomo's generator can merge inherited axes
declared at multiple levels of a class hierarchy. Parallax's first-class
abstract-root reads, family-normalized identity, whole-graph pins, and
relationship propagation all need one uniform per-family coordinate system, so
the root is made the family's single temporal-schema owner rather than
supporting Reladomo's more permissive multi-level declaration.

The normative home is
[`core/spec/m-inheritance.md`](../../core/spec/m-inheritance.md) ("Inherited
members" and the "Temporal axes are root-owned" family invariant), with a
supporting clarification in
[`core/spec/m-descriptor.md`](../../core/spec/m-descriptor.md) (the derived
`temporal` classification, for an inheritance participant, is the family's
effective inherited classification, not necessarily the entity's own local
`asOfAttribute` children) and the closed `rejectedRule` vocabulary in
[`core/spec/m-case-format.md`](../../core/spec/m-case-format.md).
