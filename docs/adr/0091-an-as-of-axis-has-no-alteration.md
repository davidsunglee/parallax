# An As-Of Axis has no alteration

Model evolution no longer has an As-Of Axis alteration. `AsOfAxisAltered` and its two
field deltas, `StartAttributeChanged` and `EndAttributeChanged`, leave the Evolution
Operation and field-delta vocabularies. An axis is still added or removed. This
replaces the part of
[ADR 0063](0063-model-evolution-is-described-at-model-altitude-and-applied-by-the-application.md)
that defined the alteration and kept it in the closed vocabulary.

ADR 0063 kept the alteration because it held that an accepted Metamodel admits axis
endpoints no descriptor can spell. That premise no longer holds. `m-metamodel` requires
each endpoint to be an Attribute of the axis's own Entity, with the canonical name and
Column for its dimension and role, and both frontends derive their axes from a
Temporality Profile. An axis is identified by its Entity and dimension, so two accepted
models that declare one axis declare the same endpoints. No pair of accepted models,
whatever frontend formed them, could produce the alteration.

We considered keeping the names as reserved vocabulary for a future model that admits
other endpoints. We decided against it: every binding would carry an operation, its
deltas, a wire spelling, and schema arms that no input can produce or test. If a later
model admits other endpoints, it can add the alteration back with that change.
`m-model-evolution` now states the rule plainly: an axis has no alteration.
