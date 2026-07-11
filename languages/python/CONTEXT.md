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

**Metamodel Hub**:
The single in-memory metamodel that both frontends build — entity classes on
the developer path, canonical YAML descriptors on the conformance path — and
that owns canonical JSON/YAML serde and descriptor export.
_Avoid_: schema registry, dual model, class reflection cache

### Queries And Results

**Find Statement**:
A free-standing, side-effect-free query value built from `Entity.where(...)`
and its chainable clauses; it serializes to one canonical operation and is
executed only by a handle or transaction.
_Avoid_: query builder, queryset, cursor, lazy result

**Snapshot**:
The fully materialized container returned by `find`, reifying one core
Snapshot Graph: arity accessors over plain frozen nodes, plus the graph's pin
and execution record. No method touches the database.
_Avoid_: result set, lazy list, query result proxy, domain snapshot

**Pin**:
A frozen point-coordinate value with one entry per actually-pinned as-of axis,
each a finite instant or the LATEST sentinel; scanned axes are absent because
a scan is not a pin.
_Avoid_: request shape, range marker, date parameter

**Edge**:
The frozen value `edge_of` returns for a temporal node, carrying the
milestone's own finite from-instant on every declared as-of axis (core's edge
pin). Unlike a Pin, every declared axis is present and every value is finite
— never the LATEST sentinel, never absent because an axis was scanned.
_Avoid_: pin, display instant, wall-clock timestamp, version stamp

**LATEST Sentinel**:
The module-level value spelling an explicit latest pin; it lowers to the
infinity coordinate and is deliberately not called "now".
_Avoid_: now, current timestamp, infinity literal

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
A frozen node copy produced through the entity class's copy API, carrying a
change record; it is the explicit write input for updates and is never
re-associated with anything.
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
