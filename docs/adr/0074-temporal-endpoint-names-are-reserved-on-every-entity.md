# Temporal endpoint names are reserved on every Entity

The four conventional As-Of Axis endpoint names — `validStart`, `validEnd`,
`txStart`, and `txEnd` — belong to framework temporal endpoints in every
Entity's top-level member namespace, whatever Temporality Profile the Entity
declares. A business Attribute, Relationship, or top-level Value Object
occurrence bearing one is refused at formation on every route: class, descriptor,
and generic core declarations, inherited declarations included. The fixed
resolver owns the refusal, so no frontend or publication path repeats it.

Reservation previously followed the declared axes: a Non-Temporal Entity could
use all four names for domain members, and a Transaction-Time Entity could use
`validStart` and `validEnd`. A published member name therefore could not say on
its own which axes a node carries. Making the reservation universal lets an
authenticated Wire read node identify its axes from its framework members alone,
so inspecting a Wire node's milestone coordinates needs no retained layout,
model, or per-node metadata. Every supported publication model derives its
endpoint names from its Temporality Profile, so on those surfaces a reserved name
is always the endpoint it names.

The cost is a deliberate authoring restriction. Previously accepted models are
now rejected: Non-Temporal Entities with business members under these names,
and Transaction-Time descriptors declaring `validStart` or `validEnd`. They must
rename those members. The restriction is no wider than the
problem it solves. Value Object scalar and nested members keep their own
namespaces and may still use the names. An As-Of Axis endpoint is exempt by
identity rather than by name, so generic formation and export still describe
axes over nonconventional endpoints such as `openedAt` and `closedAt`. A
descriptor that authors an endpoint its own profile already derives is still
refused by ingestion as a duplicate declaration, and a class below a temporal
base is still refused before framework injection could overwrite the authored
member.

This supersedes only the conditional temporal-vocabulary reservation sentence of
[ADR 0036](0036-audit-provenance-is-globally-defaulted-and-explicitly-opted-out.md).
ADR 0036's audit-provenance decision stands, including its conditional
reservation of the audit vocabulary.

Alternatives considered:

- Retaining each Wire node's Entity layout so inspection could read its effective
  axes. This keeps the old names legal, but every published node would retain a
  broader metadata closure than the Entity identity it carries today.
- Inferring a node's shape from whichever endpoint keys its mapping happens to
  contain. That inference is ambiguous while the names stay conditionally free.
- Reserving the names only in the Python frontends. That leaves generic and
  descriptor formation accepting models the inspection guarantee cannot cover.

The contract lives in `core/spec/m-metamodel.md` (*As-Of Axes*).
