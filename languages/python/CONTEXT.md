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
The explicit, self-contained model scope owned by the common Python runtime.
Its public constructor receives the complete set of Entity Classes at once;
importing or declaring a class never mutates a hub. An optional Descriptor
Frontend can produce the same model scope through a narrow source seam, but
descriptor ingestion and export are not hub operations. Construction seals: it
returns an authoritative hub whose normalized declarations, compiled Metamodel
Facets, Entity Class bindings when applicable, and model-relative name
resolution are already fixed, or it raises and creates nothing.
_Avoid_: schema registry, entity registry, ambient registry, dual model, descriptor facade, class reflection cache

**Descriptor Frontend**:
The optional interchange boundary that translates canonical descriptor
documents into Metamodel Hubs and Metamodel Hubs back into
canonical descriptor documents. It owns descriptor formats, parsing, schema
checks, value conversion, serialization, and descriptor-specific errors while
depending inward on the common Python runtime.
_Avoid_: hub method, core descriptor module, serialization registry, runtime plugin

**Metamodel Binding**:
The one immutable Python realization of a successfully sealed class-backed
Metamodel Hub. It connects the hub's exact identity and single accepted
Metamodel to the complete bidirectional association between core Entity
Identities and their Python Entity Classes. Every participating class shares
the same Metamodel Binding; it contains no copied model facts.
_Avoid_: bound model, runtime model, model context, metadata copy

**Entity Runtime**:
The narrow immutable first-party execution view a class-backed Metamodel Hub
supplies to Snapshot as one atomic value: its accepted Metamodel, opaque
exact-hub identity, Entity Graph Construction capability, and Entity Row Codec.
No partial Entity Runtime exists; it exposes neither the Metamodel Binding nor
its Entity Class index and is absent for a descriptor-backed Hub.
_Avoid_: raw binding, sealed model pair, runtime registry, capability bag

**Entity Class Binding**:
One permanent association within a Metamodel Binding between a core Entity
Identity and the Entity Class that realizes it. It is a relationship in the
shared binding, not metadata, a second model representation, or necessarily a
separate value object.
_Avoid_: registry entry, class mapping, mirror registration, temporary binding

### Queries And Results

**Find Query**:
A free-standing, side-effect-free, immutable opaque query value bound to its
sealed Metamodel Hub. Only `Entity.where(...)` constructs one; its chainable
clauses return new values, and first-party lowering converts it to one
canonical operation for execution by a handle or transaction.
_Avoid_: find statement, statement, query builder, queryset, cursor, lazy result

**Lowered Find Query**:
The immutable first-party collaboration value produced from one valid Find
Query after its independently authored clauses are placed in canonical
operation order. It carries exact hub identity, structured target Entity
Identity, and one canonical Operation; it is neither SQL nor a public query
representation.
_Avoid_: canonical Find Query, query plan, SQL AST, serialized query

**Match-All Predicate**:
The non-callable `Entity.all` value spelling an explicitly unfiltered Find
Query as `Entity.where(Entity.all)`. It is bound to that Entity Class's exact
hub and target, lowers to the canonical All operation, and is valid only as the
sole `where(...)` argument. Empty `where()` and an `all()` query constructor do
not exist.
_Avoid_: empty where, implicit find-all, all query method, global ALL

**Query Definition Error**:
The single public Python Entity-frontend error family for constructing,
composing, or refining an invalid expression, relationship path, predicate,
assignment, sort key, or Find Query. Behavioral owner modules retain their
native errors behind this translation seam.
_Avoid_: statement error, query-scope error, leaked validator error

**Query Ownership Error**:
The Snapshot execution-preflight error raised when an ordinary valid Find Query
belongs to a different exact Metamodel Hub than the Database asked to execute
it. It exposes neither hub identity and is distinct from mixed-hub query
composition, which is a Query Definition Error.
_Avoid_: query definition error, structural model mismatch, provider error

**Deferred Feature Error**:
The Snapshot execution-preflight error raised when an ordinary valid Find Query
matches one of the installed implementation's Deferred Execution Features. It
names every matching canonical Feature in sorted order and is neither a Query
Definition Error nor a database-provider failure.
_Avoid_: unsupported capability, invalid query, adapter limitation

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
`history(...)`; a string dimension spelling is rejected during Find Query
construction.
_Avoid_: dimension string literal, axis name argument

**Execution Record**:
The per-query-execution provenance carried by a Snapshot — placeholder SQL, binds,
informational duration, and the round-trip count — mirroring the
conformance-adapter emission convention.
_Avoid_: query log, debug trace, profiler output

**Deferred Execution Features**:
The private immutable set of canonical Feature tags for valid, specified query
forms that Snapshot explicitly does not yet execute. Its expected completed
state is empty; every entry is reviewable implementation debt outside the
active Conformance Slice's claim, never an excuse for claimed-but-missing
behavior. One installed Snapshot package has one fixed set shared by every
Database; applications and providers cannot configure it.
_Avoid_: provider capabilities, optional adapter features, skipped tests, supported features

**Narrowed View**:
The distinct relationship view a narrowed include populates on a node, keyed
by relationship name plus effective concrete-subtype set and read through the
Snapshot `view` accessor; equivalent authored narrowings converge on one view,
and differently narrowed views coexist on the same node.
_Avoid_: filtered relationship, cast collection, subtype list

**Relationship Path**:
An immutable exact-hub-bound sequence of relationship views used for includes
and Snapshot inspection. Its authored root position normally validates against
the Find Query target; a preceding root narrow may additionally authorize a
subtype-rooted first hop. The path retains that authored source Entity Identity
separately from the canonical Relationship Identity, so an inherited
`Dog.owner` relationship may still guard loading to Dog-family roots while
`Animal.owner` remains broad. Same-named sibling relationships never match
structurally. Canonically, the path has an optional root-position Narrow and a
nonempty relationship sequence whose segments may each narrow their target
position; a target position is the next segment's source. Applying a path
traverses loaded state left to right. Root narrowing guards which existing roots
traverse the path without creating a relationship view; narrowing a segment
changes the accepted target type for later segments and populates a distinct
Narrowed View. Broad and target-narrowed views remain separate fetches. The path
also authors cardinality-neutral relationship predicates through variadic
`exists(...)` and `not_exists(...)`; multi-hop paths lower to nested existence
operations, and multiple predicates must match one terminal related object.
_Avoid_: dotted relationship string, lazy traversal

**Existence Predicate**:
The uniform `exists(*predicates)` / `not_exists(*predicates)` quantifier on a
Relationship Path or Value Object occurrence path. Multiple predicates must
match the same terminal related Entity or embedded occurrence; storage-specific
lowering chooses relational or nested canonical operations. `~exists(...)`
canonicalizes to `not_exists(...)` and the inverse does the reverse. Python
exposes no `any()` / `none()` aliases.
_Avoid_: collection any, collection none, SQL-only existence

**Null Placement**:
The shared ordering value choosing whether nulls precede or follow non-null
values for one Sort Key or declared relationship-order term. Omission means
Nulls Last for both ascending and descending order; Python authors an override
with one `.nulls_first()` or `.nulls_last()` after explicitly choosing
`.asc()` or `.desc()`, and dialect lowering preserves the choice portably.
_Avoid_: provider-native null order, query-only null option

### Writes

**Audit Attribute**:
One of the conventional framework-owned properties realizing core Audit
Metadata: `created_by`, `created_at`, `revised_by`, and `revised_at` on every
audited Entity; `terminated_by` on a temporal Entity; and `state_changed_by`
plus `state_changed_at` on a Bitemporal Entity. `revised_at` is a mapped Audit
Attribute on a Non-Temporal Entity and a read-only alias of `tx_start` on a
temporal Entity, so both temporal spellings resolve to the same Attribute
Identity and physical column. Audit Attributes are readable and queryable on
persisted instances, but a fresh instance reports `None` until a write assigns
provenance. Caller-supplied construction, copying, assignment, and set-based
updates are rejected before DML. Each mapped Audit Attribute uses its Python
property name as its fixed physical column; the temporal `revised_at` exception
uses `in_z` through its `tx_start` alias. `terminated_by` always attributes an
explicit State Termination, never an ordinary update's revision closure.
At full-row extraction, an explicitly supplied Audit Attribute raises the
generic `FrameworkOwnedAttributeError` also shared by axis-governed
attributes; the existing `FrameworkOwnedAxisError` remains its temporal
compatibility subtype. Copy and set-based assignment paths retain their
established `ModelCopyError` and framework-owned assignment rejections.
_Avoid_: audit field, caller-authored provenance, `*_time`

**Audit Authoring**:
The root-owned Entity Class convention in which omission always requests Audit
Attributes with fixed conventional storage columns and `audit=NO_AUDIT`
explicitly forms an unaudited standalone Entity or family. An implementation
surface without Audit Provenance accepts only the explicit opt-out; it never
changes what omission means. There is no audit configuration object or
independent column override.
_Avoid_: audit mixin, `Audit(...)`, `audit=True`, descendant audit override

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

**Principal Protocol**:
The application-implemented structural interface whose `subject()` method
returns the stable, nonempty Subject Identity required by an outer database
operation. Parallax Python snapshots and otherwise preserves that string
verbatim before database interaction and outside any retry loop. A non-string
or empty result raises `InvalidPrincipalError`; an exception raised by
`subject()` propagates unchanged. Parallax supplies no generic concrete
Principal that would erase provider- or domain-specific identity structure. A
joined `db.transact(principal, body)` snapshots the supplied Principal once and
raises `PrincipalMismatchError` before `body` when it differs from the outer
transaction's captured identity; operations on `tx` inherit without a
Principal argument. A nested join first proves that the transaction belongs to
the exact originating Database, then checks rollback-only state without
evaluating the Principal, resolves and validates the Principal, compares Subject
Identity, and finally validates explicit transaction options before invoking
the body.
_Avoid_: raw subject string, generic Subject wrapper, framework user model

**Transaction Body**:
The closure passed to `db.transact`, receiving the Parallax Transaction; it
must be safe to re-execute because the bounded automatic retry loop re-runs it
against fresh state in a new atomic scope.
_Avoid_: with-block, context manager, transaction script
