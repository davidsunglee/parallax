# Inheritance families are closed trees with explicit concrete-subtype writes

Parallax inheritance is a closed tree with one `root`, optional
`abstract-subtype` nodes, and `concrete-subtype` nodes. The root and abstract
subtypes are non-instantiable, tableless, rowless entity positions; concrete
subtypes are the only instantiable inheritance participants and the only members
that own rows. The root alone declares the family strategy. The admitted
strategies are `table-per-hierarchy` and `table-per-concrete-subtype`;
`table-per-leaf` is not kept as a canonical alias, and `table-per-class` remains
rejected. `table-per-hierarchy` uses descriptor metadata `tag` / `tagValue`
rather than `discriminator` / `discriminatorValue`, keeping the physical tag
column explicit while preserving `familyVariant` as the portable result and
conformance value.

Reads may target any abstract position or concrete subtype. An abstract target
means the closed union of concrete descendants under that target, not the whole
family unless the target is the root. Subtype narrowing may be authored with
abstract or concrete subtype names; validation resolves the authored names to an
effective concrete subtype set, accepts only non-empty subsets of the current
polymorphic position, and treats redundant narrowing as valid. Narrowed
relationship views are keyed from the effective concrete subtype set in the
family's **canonical concrete-subtype order** (alphabetical by entity name — see
the Amendment below, which supersedes the originally recorded descriptor order),
so equivalent authored narrowings assemble under the same view.

Abstract-target reads materialize complete concrete instances. The canonical SQL
projection includes every attribute needed by every reachable concrete subtype,
and `table-per-concrete-subtype` abstract reads lower to a union over the
effective concrete subtype tables with null placeholders for reachable
attributes missing from a particular concrete table. Implementations must expose
concrete subtype identity without requiring a second database read merely to
hydrate concrete-subtype attributes for an already-returned row. A language may
expose subtype identity idiomatically through runtime subtypes, sealed variants,
type guards, pattern matching, or a similar mechanism; it does not have to
expose a public property literally named `familyVariant`.

Inheritance writes are explicit concrete-subtype writes through keyed/object
write APIs. Create and update payloads for a concrete subtype accept attributes
from the root plus that subtype's ancestry chain; sibling-branch attributes and
routing metadata (`tag`, `tagValue`, `familyVariant`) are rejected. Create,
keyed/object update, non-temporal physical delete, audit-only terminate, and
bitemporal terminate shapes target a concrete subtype directly. Abstract
root/subtype write handles, abstract-target routing by `familyVariant`,
set-based inheritance writes, changing an existing object's concrete subtype,
polymorphic relationship mutation, and polymorphic cascade behavior are out of
scope. For `table-per-hierarchy`, inserts set the tag column from metadata, and
existing-row writes include a metadata-derived tag guard; for
`table-per-concrete-subtype`, the concrete table identifies the subtype.

Reladomo is prior art for the semantic direction: it supports shared-table and
per-subclass inheritance patterns, generated subclass instantiation, and
conservative inherited writes. Parallax keeps those semantics portable by making
the inheritance roles, family strategy, variant tag metadata, narrowing rules,
materialization guarantee, and concrete-subtype write routing part of the core
descriptor, operation, SQL, compatibility-case, and conformance-adapter
contract.

## Amendment (2026-07): canonical concrete-subtype ordering is alphabetical

The original decision made **descriptor (declaration) order** the canonical order
in which a family's concrete subtypes are enumerated — for the table-per-hierarchy
tag `in (…)` list, the table-per-concrete-subtype `union all` branch order, the
grouped-`OR` per-branch `EXISTS` order, the narrowed view key
`<rel>[<Concrete>,<Concrete>]`, and the per-subtype own-column blocks of an
abstract-read superset projection. This made model-file layout semantically
load-bearing: reordering subtype entries, or splitting them across files, would
change golden SQL, view keys, and binds.

**Superseding decision:** the canonical sibling-set order is now **alphabetical by
concrete-subtype entity name, ordinal (Unicode codepoint) ascending** — a total
order that is a pure function of the entity names and **independent of the
descriptor's declaration order and file layout**. This is specified normatively in
`m-inheritance.md` ("Canonical concrete-subtype ordering") and referenced by
`m-op-algebra`, `m-sql`, `m-navigate`, `m-deep-fetch`, and `m-case-format`.

Unchanged by this amendment: the **inherited-column prefix** of a superset stays
**ancestry order** (root → abstract-subtype → concrete); a single entity's own
attribute/column order stays as declared; and a `narrow` node's authored `to` list
is still preserved verbatim by serde — only the *resolved* effective set is
canonicalized. The rationale for the earlier descriptor-order choice (a single fixed
order so equivalent authored narrowings converge) is preserved; only the choice of
*which* total order changed, to remove the layout dependence.
