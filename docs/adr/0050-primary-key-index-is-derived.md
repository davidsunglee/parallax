# The primary-key index is derived, not authored

An Entity's unique primary-key index is derived during descriptor phase 3 and
is no longer an authored `index` entry. Every Entity that declares a primary key
derives exactly one, placed before its authored indices, over its own
primary-key Attributes in declaration order followed by each declared As-Of
Axis's end Attribute in canonical dimension order. `m-storage-layout` defines
the Physical Primary Key as that index's slot selection, so the constraint a
table emits and the metadata that declares it cannot disagree.

The authored form carried no decision. Every one of the sixty-one corpus
declarations restated a composition the storage layout already computed, in a
name the table already fixed. Worse, the DDL surface derived its key constraint
from the layout while ignoring the index entirely, then suppressed any authored
unique index whose column set happened to match — so the authored index was
never emitted, and the constraint that was emitted came from behind its back.
Deriving the index makes metadata the single source of every constraint the DDL
emits: the derived index becomes the key constraint, each authored index becomes
a unique constraint, and the two sets are disjoint, so nothing is suppressed for
coinciding with something else.

The derivation triggers on the Entity that *declares* the key rather than the
one that owns the table. `m-metamodel` requires every index component to be a
distinct local Attribute of the index's Entity and does not inherit indices;
under `table-per-concrete-subtype` the concrete subtype declares neither the
primary key nor the axes, both being root-owned, so a subtype-owned index would
have either no legal components or non-local ones. Deriving on the declaring
Entity keeps every component local and lets the derivation read one declaration
and resolve nothing. Storage consumers already resolve an index component
through the applicable layout's contributor lookup, which reaches a
root-declared Attribute from every concrete table, so the constraint still lands
on each concrete table.

The name is `<table>_pk` when the declaring Entity owns a table. A tableless
`table-per-concrete-subtype` root owns the family's key and axes but no table,
so its index takes the Entity's own name lowercased at its first character and
folded by `defaultColumn` — `Rate` becomes `rate_pk`, which is what the corpus
already authored there.

Authoring an index whose component names an As-Of Axis endpoint becomes the
phase-3 value rejection `index-temporal-attribute`. Such an index either
restates the derived key in an author-chosen position or contradicts it.
Reladomo reaches the same rule for the same reason, rejecting at build time any
author-declared index naming an as-of attribute or either of its derived
endpoints, because its own DDL generation appends the as-of `to` columns
unconditionally.

Canonical export writes only authored facts and therefore omits the derived
index, which is what keeps `export(import(d))` structurally equal to
`canonicalize(d)`.

Two costs are accepted. The ninety-eight nontemporal corpus Entities gain index
metadata they did not carry, and `m-storage-layout`'s physical-key section
changes provenance as well as content. Both follow from the same principle: the
metadata describes what is actually emitted.
