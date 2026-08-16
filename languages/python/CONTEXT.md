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
namespace, Persistence Mode, inheritance role, and root-owned Storage Layout
without enrolling it in a model.
The framework base—`Entity`, `TxTemporal`, or `Bitemporal`—declares
its temporal shape. Python exposes no separate As-Of Axis authoring value.
Entity Classes are always frozen, so declaration headers do
not carry Pydantic's `frozen=True` option.
_Avoid_: `EntityConfig`, `__parallax__`, registry call, model options object

**Document Layout Declaration**:
The root-owned `Document(column=...)` Entity Class header value selecting core
Relational Document Layout and naming its required Structured Column. Omission
selects conventional Columns layout; descendants cannot repeat or override it.
_Avoid_: document entity, JSON model, payload option, Mongo mapping

**Attribute Declaration**:
An `Attr[T]` annotation on an Entity Class or Value Object, optionally paired
with context-checked `attr(...)` mapping options. Its optional `column=` is a
core Column Override rather than effective placement; Model Formation derives
the Direct Column or Document Path through Storage Layout. Class access yields
a typed attribute expression; instance access yields the plain `T` value.
_Avoid_: field, column property, Pydantic field, storage location

**Inline Value Object Class**:
A Value Object class declared lexically inside the Entity or Value Object that
owns its intended single occurrence. It is referenced through `Attr[...]` and
requires no shape name, registration, or separate Domain Model input.
_Avoid_: anonymous Value Object, inline schema, registered shape

**Standalone Value Object Class**:
An ordinary Value Object class declared outside its occurrence owners so the
same shape can be referenced through `Attr[...]` at multiple paths. It is not
an independent model or Domain Model input.
_Avoid_: registered Value Object, independent model, shared occurrence

**Relationship Declaration**:
A `Rel[T]` annotation on an Entity Class paired with `rel(...)` mapping options.
Class access yields a typed relationship path; instance access yields the plain
related value.
_Avoid_: navigation field, relationship property, foreign-key field

**Domain Model**:
The explicit, self-contained model scope owned by the common Python runtime.
Its public constructor receives the complete set of Entity Classes at once;
importing or declaring a class never mutates a model. An optional Descriptor
Frontend can produce the same model scope through a narrow source seam, but
descriptor ingestion and export are not model operations. Construction is
construct-or-raise: it returns an authoritative model whose normalized
declarations, compiled Metamodel Facets, Entity Class index when applicable, and
model-relative name resolution are already fixed, or it raises and creates
nothing. It carries no identity of its own and claims nothing, so one Entity
Class participates in any number of Domain Models and one Domain Model serves
any number of Databases.
_Avoid_: Metamodel Hub, schema registry, entity registry, ambient registry, dual model, descriptor facade, class reflection cache

**Descriptor Frontend**:
The optional interchange boundary that translates canonical descriptor
documents into Domain Models and Domain Models back into
canonical descriptor documents. It owns descriptor formats, parsing, schema
checks, value conversion, serialization, and descriptor-specific errors while
depending inward on the common Python runtime.
_Avoid_: model method, core descriptor module, serialization registry, runtime plugin

**Class Index**:
The immutable bidirectional association between core Entity Identities and the
Python Entity Classes that realize them, held by a class-backed Domain Model and
absent from a descriptor-backed one. It carries no identity of its own, is
reachable only through a private first-party seam, and is what a Snapshot
connection requires in order to materialize Entity Class instances.
_Avoid_: Metamodel Binding, Entity Class Binding, bound model, runtime model, model context, metadata copy

**Entity Runtime**:
The narrow immutable first-party execution view a class-backed Domain Model
supplies to Snapshot as one atomic value: its accepted Metamodel, Entity Graph
Construction capability, and Entity Row Codec. No partial Entity Runtime exists;
it exposes no Entity Class index and is absent for a descriptor-backed model.
_Avoid_: raw binding, sealed model pair, runtime registry, capability bag

### Queries And Results

**Object Query**:
A free-standing, side-effect-free, immutable opaque query value, `ObjectQuery[E,
S]` — parameterized by the Entity it queries and the Entity its result returns,
which `narrow` and only `narrow` moves. It retains no model. Only
`Entity.where(...)` constructs one; its chainable clauses return new values and
fill sibling clauses of the one canonical query value it holds throughout, which
a first-party seam reads for execution by a handle or transaction.
_Avoid_: find query, find statement, statement, query builder, queryset, cursor

**Predicate**:
`Predicate[E]`, the immutable typed filter expression one clause of an Object
Query is composed from, contravariant in the position it addresses so an
ancestor's member is addressable from a descendant position and never the
reverse. It composes with
`&`, `|`, `~`, and native parentheses; it names no model and executes nothing.
_Avoid_: where object, filter object, query, criteria

**Match-All Predicate**:
The non-callable `Entity.all` value spelling an explicitly unfiltered Object
Query as `Entity.where(Entity.all)`. It is bound to that Entity Class's target,
serializes as the canonical All node, and is valid only as the
sole `where(...)` argument. Empty `where()` and an `all()` query constructor do
not exist.
_Avoid_: empty where, implicit find-all, all query method, global ALL

**Query Definition Error**:
The public Python Entity-frontend error family for constructing, composing, or
refining an expression, relationship path, predicate, assignment, sort key, or
Object Query the frontend itself refuses. Its rules are the class-local ones,
because authoring reaches no model; a rule needing a whole model is stated once
at execution preflight and surfaces there as its owner module's own error,
untranslated.
_Avoid_: statement error, query-scope error, leaked validator error, translation seam

**Query Target Error**:
The Snapshot execution-preflight error raised when the connected model declares
no Entity for an Object Query's target. It retains and exposes neither the query,
the model, nor the Database, and it is not an ownership relation: one Entity
Class participates in any number of Domain Models and one Domain Model serves
any number of Databases.
_Avoid_: query ownership error, hub mismatch, structural model mismatch, provider error

**Runtime-Only Erasure**:
A query rule the frontend's type parameters cannot state, left to the
model-aware validator at execution preflight. The named cases are narrowing
relatedness — a type parameter's bound may not itself be generic, so neither
`Entity.narrow(...)` nor `ObjectQuery.narrow(...)` states that the classes it
names are subtypes of the position it narrows, and `narrow-outside-position`
alone refuses one that is not — and a relationship hop past the first, whose
member the composed segment can name but not resolve. A hop narrow is the
exception that keeps its static half, because its bound rides on the receiver.
_Avoid_: unchecked query, dynamic fallback, silent acceptance

**Deferred Feature Error**:
The Snapshot execution-preflight error raised when an ordinary valid Object Query
matches one of the installed implementation's Deferred Execution Features. It
names every matching canonical Feature in sorted order and is neither a Query
Definition Error nor a database-provider failure.
_Avoid_: unsupported capability, invalid query, adapter limitation

**Snapshot**:
The fully materialized generic container returned by a Typed or Wire `find`,
with arity accessors plus the result's Pin and Read Trace. Its element is an
Entity Class instance on the Typed interface and a Wire Entity Mapping on the
Wire interface; no method touches the database.
_Avoid_: result set, lazy list, query result proxy, domain snapshot

**Checked Snapshot**:
The read-only `CheckedSnapshot[T]` view returned by `Snapshot.checked()`. It
shares the Snapshot's result storage, Pin, and Read Trace while its ordinary
arity accessors return `InvalidData` in-band; constructing or using the view
performs no database work. Its ordinary accessors are the complete surface;
there is no separate valid/invalid partition method.
_Avoid_: lenient Snapshot, copied result, ignore-invalid mode, partitioned
result

**Wire Interface**:
The class-independent read-and-write interface reached through `db.wire` or
`tx.wire`. It shares the underlying handle and, within a transaction, the same
Unit Work and observations as the Typed interface; it is not a format option or
transaction mode. Its `find` accepts either the canonical Object Query mapping
or, for a class-backed model, the Typed Object Query authoring value; a
descriptor-backed caller therefore needs no Entity Class.
_Avoid_: Neutral API, Wire transaction, format selector, descriptor mode

**Wire Entity Mapping**:
The mapping-shaped Python representation of one Entity node in a Wire Snapshot,
keyed by declared member names and carrying no serialized framework metadata.
Its Value Object occurrences key exactly the members the read contract carries —
`core/spec/m-snapshot-read.md` _What a materialized value carries_ — so presence is
something a consumer reads off the mapping rather than assuming, and the mapping is
the same document the Typed value of that row serializes to.
It may retain a core Source Hint privately without changing its mapping value.
The hint identifies the concrete Entity and original Object Key and optionally
an exact observed state; an unversioned Non-Temporal source has no observed
state.
The returned mapping and every nested dictionary or list are frozen; ordinary
mutation raises `TypeError`. They retain ordinary structural equality with
plain dictionaries and lists and remain unhashable. Only the verb's separate
changes mapping authors an update. Immutable copy operations may return the same
hinted value, while `dict(value)`, serialization, and reconstruction produce
ordinary data that is not a keyed write source. Standard JSON serialization
treats the private subclasses as ordinary objects and arrays and sees no Source
Hint; decoding returns plain dictionaries and lists. A keyed Wire verb accepts
only a frozen value returned by a Parallax Wire read; an ordinary mapping is
malformed source input and must be reread before writing. Every existing-object
keyed write requires an authentic Parallax read source. Under the source Entity's effective Locking strategy that
source must have participated in the current transaction, proving that it
acquired and still holds the shared row lock. Under its effective Optimistic strategy an authentic
versioned or temporal source from `db.wire.find` may instead contribute its
privately retained version or milestone evidence; the emitted database gate
detects intervening writes. An unversioned Non-Temporal source has no optimistic
gate and must still come from the current transaction's locking read.
The recursive `WireValue` alias contains canonical scalar values, lists, and
string-keyed dictionaries. `WireEntity` is instead a public, non-constructible,
read-only nominal `Mapping[str, WireValue]` implemented by the private frozen
`dict` subclass. It gives result annotations and keyed verbs static source
discrimination while retaining indexing, iteration, `get`, `items`, and other
idiomatic mapping operations; runtime values remain instances of `dict`.
Ordinary mappings remain the structural inputs for inserts, changes, predicates,
and Object Queries. Nominal identity does not prove that a source belongs to the
current transaction, so keyed verbs still validate private provenance and any
required locking participation or optimistic state evidence at runtime.
`WireValue` deliberately does not add public frozen mapping/list types merely to
express deep immutability statically; the runtime contract enforces it. Neither
type exposes a Source Hint constructor.
_Avoid_: Neutral Node, metadata dictionary, physical row, DTO

**Write Evidence Error**:
The `LookupError` raised when a Typed or Wire keyed write cannot resolve usable
evidence, encompassing current-transaction lock participation and authentic
source-retained Write Observations. Its public `code` is one of
`write-evidence-unavailable`, `write-evidence-consumed`, or
`write-evidence-already-claimed`, and its `object_key` identifies the attempted
visible object. Consumed means that the exact source's evidence authorized a
write that reached a successful flush;
the still-live source remains readable but must not authorize another write.
The keyed verb raises the error synchronously before buffering or I/O; later
optimistic or temporal conflicts keep their flush-time error families.
Several pre-flush updates may use one observation when their temporal bounds
match; Unit Work coalesces Typed, Wire, and mixed changes in call order, with the
later value winning for a repeated member, and consumes the observation once.
Typed ingress preserves touched assignments until that merge, so an edit that
is net-zero by itself can cancel an earlier pending assignment. Net-zero
elimination then compares Typed assignments with their Change Record originals
and Wire assignments with their frozen observed source values. The Wire verb
captures originals only for explicitly changed members, so it does not retain a
second copy of the read result. A wholly Typed, Wire, or mixed intent may
therefore collapse without DML or consumption.
An incompatible second intent, including a temporal update with different
bounds, raises already-claimed at that verb. Identical destructive intents
deduplicate. For the same state and region, update-then-delete or
update-then-terminate collapses to the destructive intent; the reverse order
raises already-claimed.
An observation already selected into a predicate Materialized Write Group also
raises already-claimed for a later overlapping keyed verb; non-overlapping keys
remain valid. Keyed-before-predicate force-flushes and resolves fresh state.
_Avoid_: Write Observation Error, concurrency error, hint error, stale model,
observation exception

**Buffered Wire Input**:
The recursively snapshotted immutable value captured by every `tx.wire` verb at
the call boundary. It includes all supplied data or changes, target and bounds,
the frozen keyed source facts and explicitly changed-member originals needed by
the verb, and resolved observation evidence. Mutating a caller dictionary or any
nested list or dictionary after the call cannot alter the buffered write. The
copy cost is proportional to authored write input and does not duplicate a Wire
read result.
_Avoid_: retained caller mapping, shallow write copy, lazy changes, live payload

**Wire Write Validation Order**:
The fixed verb-time phase order: validate verb and target shape, source key and
required version, temporal bounds, member names and values, and assignment
legality; reject any keyed source that is not a frozen Parallax Wire read; then
resolve the source Entity's Effective Concurrency Strategy and its evidence
requirement—current-transaction read participation under Locking, or retained
version/milestone evidence under Optimistic—then recursively snapshot and buffer. A malformed request
therefore raises `WriteInstructionError` before any possible write-evidence
failure.
_Avoid_: best-effort validation, ledger-first refusal, flush validation

**InvalidData**:
The checked Snapshot element carrying a `frozenset` of unique StoredDataIssues
and either the hydrated Typed or Wire root or `None` when hydration would
require invention. Its diagnostic locator is an optional `ObjectKey`, mutually
exclusive optional version or Edge, and an always-present zero-based result
ordinal; none grants write authority. Ordinary Snapshot access raises instead
of returning this value. When `data` is present, callers may write that ordinary
observed value under ordinary ingress rules. A Typed assignment equal to the
hydrated collapse remains a no-op; a keyed Wire assignment equal to the frozen
hydrated source is also a no-op. Python retains no repair-sensitive metadata and
promises no general remediation API. The wrapper and `data=None` are not write
sources. Storage-aware administrative repair is outside the interface.
Neither the wrapper nor its diagnostic locators retains an observation claim.
When `data=None`, reconstructing an ordinary mapping cannot use that read as a
keyed write source. Hydrated data nodes retain their ordinary per-node claims.
_Avoid_: failed Entity, skipped result, validation error, error side list

**InvalidDataError**:
The default eager Snapshot exception whose nonempty `invalid_data` tuple carries
the complete invalid roots selected by the accessor in result order. Its message
is derived; it exposes no singular code, flattened issue list, cause, or records
alias.
_Avoid_: decoding error, aggregate issue, checked result

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
`history(...)`; a string dimension spelling is rejected during Object Query
construction.
_Avoid_: dimension string literal, axis name argument

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
An immutable sequence of relationship views used for includes
and Snapshot inspection, `RelationshipPath[E, R]` — covariant in both its source
and its target. Its authored root position normally validates against
the Object Query target; a preceding result narrowing may additionally authorize a
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
predicates, and multiple predicates must match one terminal related object.
A Python-authored path stops at two hops: the segment past the first is composed
from the path's own target rather than resolved against a model, so a third hop
has no honest owner to name and raises instead.
_Avoid_: dotted relationship string, lazy traversal

**Existence Predicate**:
The uniform `exists(*predicates)` / `not_exists(*predicates)` quantifier on a
Relationship Path or Value Object occurrence path. Multiple predicates must
match the same terminal related Entity or embedded occurrence; storage-specific
lowering chooses relational or nested canonical predicates. `~exists(...)`
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
Designating an Audit Attribute framework-owned is the whole cost of adding one:
construction refuses a caller-supplied value where it is authored, copy and
set-based assignment paths reach the one shared framework-owned assignment
rejection, and row derivation omits the member rather than emitting it as an
authored assignment.
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
