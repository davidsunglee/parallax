# Inheritance family optimistic locking is declared only by the root

`m-descriptor`'s "attribute" wording let `optimisticLocking: true` be read as an
ordinary per-entity flag: declared on whichever entity wants a version column,
inheritance notwithstanding. Nothing in the spec text forbade a family's
`abstract-subtype` or `concrete-subtype` from declaring its own version
attribute alongside — or instead of — the root's, and empirically every one of
the three malformed shapes (a non-versioned root with a declaring descendant, a
versioned root whose descendant redeclares the same attribute, and a versioned
root whose descendant adds a second, differently-named one) was silently
accepted wherever it was tried. This mirrors exactly the ambiguity ADR 0026
closed for temporal axes, and for the identical reason: nothing pinned the
version column's declaration site to one level of the hierarchy.

The decision is that **optimistic locking is a family-wide property**, not a
per-entity one. Only the family root may declare an `optimisticLocking`
attribute; every abstract and concrete descendant inherits the root's version
column unchanged, and a descendant that declares its own — whether to redeclare
the root's verbatim, add a second one, or version a family the root itself
leaves unversioned — is rejected pre-SQL
(`inheritance-optimistic-locking-not-root-owned`). A family is therefore either
entirely non-versioned or entirely versioned together; mixed versioning across
branches is not supported. This is a narrowing, not an addition: every
descriptor the corpus already accepts (root-declared version only, per
`m-inheritance-084`'s witness) remains legal and behaves identically; only the
previously-unspecified descendant-declared shapes become rejected.

The rationale is that mixed versioning would leave the write boundary's
conflict contract ill-defined for exactly the rows that lack a version. A
shared-table (table-per-hierarchy) family versions its rows through one shared
column; a per-row optional version would need the gate/advance logic to branch
on which concrete a row belongs to, for no semantic gain the family's write
protocol already provides uniformly. A table-per-concrete-subtype family's
ancestry-derived column chain already replicates every root attribute onto each
concrete's own table — the identical mechanism that already threads the primary
key needs no new machinery to thread the version column too, so there is no
physical reason to allow a subtype to opt out or declare its own. And the
`m-opt-lock` × `m-inheritance` composition already fixed elsewhere (the tag
guard rides the identity predicates, the version gate binds last,
`m-inheritance-084`) presumes one family-wide version discipline; a family that
mixed versioned and unversioned branches would leave that composition
undefined for the unversioned rows.

Ordinary inherited members are unaffected: attributes, value objects,
relationships, and mutability still follow the existing ancestry rules and may
be declared on any abstract ancestor. Only the version-attribute declaration
site is pinned to the root. Every consumer that resolves an inheritance
participant's optimistic-lock key — the version projected alongside a read, the
gate a keyed `UPDATE` binds in optimistic mode, the advance every successful
`UPDATE` applies, and conflict classification — resolves through the family
root uniformly, whether the write targets the root's own table (table-per-
hierarchy) or a concrete's own table replicating the root's column
(table-per-concrete-subtype).

This is genuinely new ground relative to Reladomo, not a narrowing of an
existing Reladomo feature the way the temporal-axis decision was: Reladomo has
**no designed position** on optimistic locking composed with inheritance at
all. Its XSD attribute (`useForOptimisticLocking`, declared per `Attribute`
element) carries no restriction tying it to a superclass or to any particular
level of an `<Extends>` hierarchy — a subclass's own attribute file can set it
exactly as a superclass's can. The generator resolves whatever the XML happens
to declare through ordinary attribute merging, with no cross-level collision
check and no documented rule about which level should win if two levels both
declared one; the checked-out Reladomo test suite carries no fixture combining
optimistic locking with an inheritance hierarchy at all. So per-entity
declaration was never something Parallax could have cited Reladomo as
precedent for keeping — the permissiveness is an absence of a considered
answer, not a deliberate design this ADR narrows. Where the temporal-axis ADR
(0026) is Parallax choosing a stricter rule than Reladomo's considered
multi-level support, this one is Parallax supplying a rule Reladomo never
authored at all — following the SAME structural direction the read/write
boundary already needs (one family-wide coordinate system, `m-inheritance`
"Family invariants"), by analogy rather than by narrowing prior art.

The normative home is
[`core/spec/m-inheritance.md`](../../core/spec/m-inheritance.md) ("Inherited
members" and the "Optimistic locking is root-owned" family invariant), with a
supporting clarification in
[`core/spec/m-descriptor.md`](../../core/spec/m-descriptor.md) ("Composition
with inheritance (declaration site)") and
[`core/spec/m-opt-lock.md`](../../core/spec/m-opt-lock.md) ("The version
column"), and the closed `rejectedRule` vocabulary in
[`core/spec/m-case-format.md`](../../core/spec/m-case-format.md).
