# Parallax Python

Parallax Python provides an idiomatic, Python-first (SQLModel-inspired) API for
the language-neutral Parallax core contract: class-authored models, frozen
plain-value snapshot graphs, and explicit copy-based writes.

## Python API Glossary

### Model Authoring

**Entity Class**:
A user-authored frozen Pydantic class that declares one mapped entity and
serves three roles: model metadata source, snapshot node type, and create
payload, while exposing the typed query surface at class level.
_Avoid_: table class, generated model, managed entity, DTO

**Entity Class Declaration**:
The typed class-header metadata that declares an Entity Class's table,
namespace, Persistence Mode, and inheritance role without enrolling it in a
model.
The framework base—`Entity`, `TxTemporal`, or `Bitemporal`—declares
its temporal shape. Python exposes no separate As-Of Axis authoring value.
Entity Classes are always frozen, so declaration headers do
not carry Pydantic's `frozen=True` option.
_Avoid_: `EntityConfig`, `__parallax__`, registry call, model options object

**Attribute Declaration**:
An `Attr[T]` annotation on an Entity Class or Value Object, optionally paired
with context-checked `attr(...)` mapping options. Omitted storage configuration
derives the conventional location from the attribute or containment name;
accepted metadata nevertheless contains an explicit Storage Location. Class
access yields a typed attribute expression; instance access yields the plain
`T` value.
_Avoid_: field, column property, Pydantic field

**Inline Value Object Class**:
A Value Object class declared lexically inside the Entity or Value Object that
owns its intended single occurrence. It is referenced through `Attr[...]` and
requires no shape name, registration, or separate Metamodel Hub input.
_Avoid_: anonymous Value Object, inline schema, registered shape

**Standalone Value Object Class**:
An ordinary Value Object class declared outside its occurrence owners so the
same shape can be referenced through `Attr[...]` at multiple paths. It is not
an independent model or Metamodel Hub input.
_Avoid_: registered Value Object, independent model, shared occurrence

**Relationship Declaration**:
A `Rel[T]` annotation on an Entity Class paired with `rel(...)` mapping options.
Class access yields a typed relationship path; instance access yields the plain
related value.
_Avoid_: navigation field, relationship property, foreign-key field

**Metamodel Hub**:
The explicit, self-contained model scope built by either frontend — Entity
Classes on the developer path or canonical descriptors on the conformance
path. The class-backed constructor receives the complete set of Entity Classes
at once; importing or declaring a class never mutates a hub. The hub becomes
authoritative when sealed, fixing its normalized declarations, compiled
Metamodel Facets, Entity Class bindings, and model-relative name resolution.
_Avoid_: schema registry, entity registry, ambient registry, dual model, class reflection cache

**Metamodel Binding**:
The one immutable Python realization of a successfully sealed class-backed
Metamodel Hub. It connects the hub's exact identity and single accepted
Metamodel to the complete bidirectional association between core Entity
Identities and their Python Entity Classes. Every participating class shares
the same Metamodel Binding; it contains no copied model facts.
_Avoid_: bound model, runtime model, model context, metadata copy

**Entity Class Binding**:
One permanent association within a Metamodel Binding between a core Entity
Identity and the Entity Class that realizes it. It is a relationship in the
shared binding, not metadata, a second model representation, or necessarily a
separate value object.
_Avoid_: registry entry, class mapping, mirror registration, temporary binding

### Queries And Results

**Find Query**:
A free-standing, side-effect-free query value bound to its sealed Metamodel
Hub, built from `Entity.where(...)` and its chainable clauses. It serializes to
one canonical operation and is executed only by a handle or transaction.
_Avoid_: find statement, statement, query builder, queryset, cursor, lazy result

**Snapshot**:
The fully materialized container returned by `find`, reifying one core
Snapshot Graph: arity accessors over plain frozen nodes, plus the graph's pin
and execution record. No method touches the database.
_Avoid_: result set, lazy list, query result proxy, domain snapshot

**Pin**:
A frozen point-coordinate value with one entry per actually pinned temporal
dimension, each a finite instant or the LATEST sentinel; scanned dimensions
are absent because a scan is not a pin.
_Avoid_: request shape, range marker, date parameter

**Edge**:
The frozen value `edge_of` returns for a temporal node, answering every
declared temporal dimension with the milestone's own finite start instant
(core's Edge Pin) through strict dimension accessors — `tx_time`
raises for an undeclared dimension and `tx_time_or_none` returns None
— so replay code needs no narrowing. Unlike a Pin, every declared dimension is
answered and every value is finite: never LATEST and never absent because a
dimension was scanned.
_Avoid_: pin, display instant, wall-clock timestamp, version stamp

**LATEST Sentinel**:
The module-level value spelling an explicit latest pin; it lowers to the
infinity coordinate and is deliberately not called "now".
_Avoid_: now, current timestamp, infinity literal

**Temporal Dimension Constant**:
One of the module-level values `VALID_TIME` and `TX_TIME` spelling a Temporal
Dimension wherever the developer surface takes a dimension argument, such as
`history(...)`; a string dimension spelling is rejected at statement build.
_Avoid_: dimension string literal, axis name argument

**Execution Record**:
The per-statement provenance carried by a Snapshot — placeholder SQL, binds,
informational duration, and the round-trip count — mirroring the
conformance-adapter emission convention.
_Avoid_: query log, debug trace, profiler output

**Narrowed View**:
The distinct relationship view a narrowed include populates on a node, keyed
by relationship name plus effective concrete-subtype set and read through the
`narrowed` accessor; equivalent authored narrowings converge on one view, and
differently narrowed views coexist on the same node.
_Avoid_: filtered relationship, cast collection, subtype list

### Writes

**Edited Copy**:
A frozen Entity Class copy produced through `edit`, carrying a Change Record.
It is the explicit write input for `update` and is never re-associated with
anything.
_Avoid_: dirty object, detached object, tracked entity, draft

**Change Record**:
The map an edited copy carries from each touched field to its original
(first-touched) value — copies of copies merge records, keeping the earliest
original. Lowering keeps only the effective change set (fields whose current
value differs from the original), emitting the canonical sparse row of primary
key plus changed attributes, or no DML at all when the set is empty.
_Avoid_: dirty set, touched-name set, change tracking, diff log

### Transactions

**Transaction Body**:
The closure passed to `db.transact`, receiving the Parallax Transaction; it
must be safe to re-execute because the bounded automatic retry loop re-runs it
against fresh state in a new atomic scope.
_Avoid_: with-block, context manager, transaction script
