# The temporality profile is authored and the axes are derived

A descriptor spells one temporal fact — `temporality: nontemporal |
transaction-time | bitemporal` — and phase 3 of ingestion derives everything the
convention already implied: each As-Of Axis, both endpoint Attributes of each
axis, and their physical columns. The `asOfAxes` container, which authored each
axis and named its two endpoint Attributes, is retired.

The conventions were already normative and already universal; they were simply
not defaulted. A bitemporal Entity spent twelve lines restating them before its
first domain Attribute, and nothing mechanically held them: an axis whose
endpoints omitted `column` stored to `tx_start` rather than `in_z`, and an axis
whose endpoints were named `openedAt`/`closedAt` was accepted. Correctness rested
on fifteen model files happening to spell it the same way. Deriving the structure
from the profile makes the convention the only representable shape and removes
the second source of truth the axis block was.

Reladomo derives in the opposite direction. A `<MithraObject>` authors each axis
as an `<AsOfAttribute>` child carrying its own `name`, `fromColumnName`,
`toColumnName`, `infinityDate`, `infinityIsNull`, `toIsInclusive`, and
`isProcessingDate`, and the object's temporality is inferred from those
children — `hasAsOfAttributes()` is what decides whether `dated` is prepended to
the generator's template category
(`docs/research/reladomo/02-object-metamodel.md:14-21`). Authored axes, derived
profile. Parallax deliberately inverts it, because it keeps none of the per-axis
knobs that make an axis worth authoring: no free axis name, no per-model
infinity, no inclusivity flag, no physical column. With all of those fixed, the
only fact the axis block still carried was which axes exist — which is exactly
what `temporality` spells.

`temporality` is the same kind of property as `persistence` and `layout`:
family-wide, root-owned, a closed kebab-case vocabulary, defaulting on omission,
and preserved as absent rather than normalized at the record layer, because
absence on a root means the default while absence on a descendant means inherit.
The schema places it at the same entity position for every family participant
instead of structurally forbidding it on a descendant, for the same reason
`layout` is placed there: the family rule is not expressible per entity. A
descendant that declares it is refused by whole-model formation as
`inheritance-temporality-not-root-owned` — the renamed
`inheritance-temporal-axes-not-root-owned`, which now names the property an
author actually writes.

The derivation is discharged entirely before the `m-metamodel` seam, in one
frontend-neutral home both frontends call. An Unresolved Entity Declaration
carries the complete Attribute list and the resolved As-Of Axes exactly as if
both had been authored, so `m-metamodel`, `m-storage-layout`, `m-sql`,
`m-temporal-read`, and `m-opt-lock` see what they saw before and no consumer past
the seam knows a profile exists. The two frontends were already obliged to agree
there — the API Conformance Suite compares their `EntityMetadata` field for field
on every run — and one shared derivation is what makes that agreement structural
rather than coincidental.

Two authored shapes disappear with the container, and each is refused by name in
phase 3 rather than silently re-derived. An Attribute bearing a derived
endpoint's canonical name is `temporal-attribute-declared`; an Index component
naming one is `index-temporal-attribute`. There is no third rejection for
overriding a temporal column: the `column` an author would override now sits on
an Attribute the profile derives, so every way to reach it is already the first
rejection.

Valid-Time-Only stays deferred and stays unspellable. The enum's members are
exactly the composed profiles, so activating `m-validtime-only` is purely
additive — one further value deriving a single `valid-time` axis — and changes no
existing spelling.

Not chosen: keeping `asOfAxes` beside a derived default, which preserves exactly
the redundant second source of truth this removes and leaves the two free to
disagree; deriving past the `m-metamodel` seam, which would make `EntityMetadata`
construction depend on a profile that no longer exists at that layer and would
give every consumer a temporal fact to interpret; duplicating the derivation per
frontend, which leaves the most convention-dense table in the codebase in two
copies with nothing comparing them.
