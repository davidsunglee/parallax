# Python queries and results

Portable meaning belongs to [Object Query](../../../core/spec/m-object-query.md),
[Predicate](../../../core/spec/m-predicate.md),
[Temporal Read](../../../core/spec/m-temporal-read.md), and
[Snapshot Read](../../../core/spec/m-snapshot-read.md). This page owns Python
authoring, carrier, and failure choices that those contracts do not decide.

## Authoring

`Entity.where(*predicates)` requires at least one predicate and conjoins them;
`Entity.where(Entity.all)` is explicitly unfiltered. Query construction performs
no I/O and returns an opaque immutable `ObjectQuery`. Each fluent clause returns
a new value. Direct construction, semantic equality, serialization, execution,
and state-inspection methods are not public query operations. Independently
authored queries compare by object identity. Truth-testing queries or expressions
raises `TypeError`.

Predicates compose with parenthesized `&`, `|`, and `~`; Python `and`, `or`,
`not`, and chained comparisons cannot express them. Boolean attributes use
`.is_(True)` / `.is_(False)`; these accept exact built-in booleans and serialize
like equality. `case_insensitive=` also requires an exact boolean.
`None` is refused as a comparison, range, string, or membership operand;
`.is_null()` / `.is_not_null()` are the null spellings and require a nullable
leaf. Membership takes one nonempty exact built-in list or tuple, copies it,
and preserves order and duplicates. Other iterables and subclasses are refused.

Attribute `.set(...)` validates an assignment immediately and raises `EditError`
on refusal. Its targets are top-level scalar members or whole Value Object
occurrences, not relationships or paths inside an occurrence. Assignments use
the same assignability and declared-type rules as `edit`; no value coercion is
performed at this boundary.

The fluent query clauses are `include`, `order_by`, `limit`, `narrow`, `as_of`,
`history`, and `as_of_range`. There is no query `.where` refinement. Include
paths are class-derived relationship paths; authored chains stop at two hops.
Relationship predicates use explicit `.exists(...)` or `.not_exists(...)`.
Value Object occurrence quantifiers use the same vocabulary. Sorting uses
attribute expressions and direction/null-placement modifiers. `limit` requires
a positive exact built-in integer, excluding `bool`.

The generic expression types bind their source and result Entity positions.
Their variance and overloads are the static contract. Some static rejections
cannot be repeated at runtime because canonical queries erase Python class
spelling and clause order; model-dependent facts instead require execution
preflight. The negative-typing suite pins those distinctions. Variadic narrowing
outside the fixed overloads conservatively retains the original result type.

Python authoring refusals use `QueryDefinitionError(ValueError)` with structured
context and stable codes, excluding literal values and internal model state.
A query's target absent from the connected model is instead
`QueryTargetError(query-target-not-in-model)` before I/O. Queries hold no model
identity and can be executed against any model that accepts their target.

## Temporal spelling

`as_of(valid_time=..., tx_time=...)` uses aware datetimes or `LATEST`;
`history(VALID_TIME)` and `history(TX_TIME)` use exported dimension constants,
not strings. `as_of_range` takes an exact built-in pair of finite aware instants
with increasing endpoints. Naive datetimes, `LATEST` range endpoints, and
non-tuple range carriers are refused. A dimension may be selected only once,
and axis-free `as_of` / `as_of_range` calls are errors.

Omitted Transaction Time means Latest. Bitemporal queries must select Valid
Time explicitly. Latest has no `now` alias: an ordinary finite current-clock
datetime is a finite pin. Temporal naming is `valid_time` / `tx_time` on queries,
`Pin`, and `Edge`; mutation keywords are `valid_from` and, for bounded verbs,
`until`.

## Eager results

`scope.find` and `tx.find` return `Snapshot[T]`. Nodes are frozen instances of
the authored Entity classes; loaded to-many relationships and Many Value Objects
are tuples. Accessing an unloaded relationship raises `UnloadedRelationshipError`;
loaded-null is `None`. Inspection uses `is_view_loaded`, `view`, `pin_of`, and
`edge_of`, including on edited materialized values. Narrowed views are distinct
from broad relationship fields.

The envelope is not iterable, indexable, or sized, and exposes no lazy behavior.
`result()` requires exactly one root; `result_or_none()` permits zero or one;
`results()` returns a fresh list. Arity errors are `NoResultFound` and
`TooManyResultsFound`. Each envelope retains its adopted `edition` and `pin`.
Node hashing is conditional on all traversed field values being hashable;
back-reference cycles can make hashing non-terminating.

The default accessors check arity first, then raise `InvalidDataError` for invalid
roots in the selected result. `checked()` shares the same storage and arity rules
but returns `InvalidData[T]` records in band. Delayed accessor failures retain the
result edition and perform no execution. Stored-data issue evidence freezes
arrays as tuples, objects as `MappingProxyType` over detached copies, byte-like
values as bytes, null as `None`, and absent stored members as
`MISSING_STORED_VALUE`. Evidence is excluded from automatic error/log output.
Invalid hydrated values are inspectable but carry no write authority.

Inspection first requires a published Snapshot node; a plain Entity value raises
`SnapshotInspectionError(snapshot-node-required)` before path validation.
Failure during graph construction becomes
`SnapshotMaterializationError(snapshot-materialization-failed)` once, preserving
its cause and withholding the graph. Other read failures keep their owner's
classification. Inconsistent projections use
`SnapshotConsistencyError(snapshot-projection-conflict)` without raw payload
evidence. Its whole eager result is withheld; a stream preserves earlier roots
and withholds the conflicting root. These read failures remain subject to the
[execution failure boundary](execution.md#transactions-and-failure-boundaries).

## Wire results and projection

`scope.wire` and `tx.wire` select Wire representation; no `format=` argument
exists. Wire queries accept canonical mappings, `ObjectQueryNode`, and a typed
Object Query. `WireEntity` is an immutable mapping published by the runtime,
not directly constructible. Nested collections remain immutable; copying
returns the same value and pickling produces plain domain data. Domain members
do not contain framework metadata. Typed and Wire results use the same invalid
data verdicts and envelope edition.

A Typed Snapshot supports whole-result `wire()` and element
`wire(value, at=...)` projection without I/O or revalidation of stored data.
Projection preserves read provenance and invalid verdicts; it ignores Pydantic
computed fields, defaults, serializers, and private state. An omitted `at` or
`None` selects the original root position; a supplied relationship path must be
an exact requested prefix and admit the concrete value. Compatible published
nodes need not have been delivered by that envelope. Edited inputs are refused,
even for empty edits. Whole-result projection takes no position override, and
Wire envelopes cannot project again.

## Streams

`scope.stream`, `tx.stream`, and their Wire peers return context-managed,
single-pass `SnapshotStream` values. Construction validates model-independent
arguments; entry adopts the model and performs model-dependent preflight.
Unentered streams perform no I/O or model adoption. A standalone stream keeps
its selection across all pages; a transactional one inherits the transaction's.

Exactly one default or checked iterator may be selected. Entering twice,
selecting another view, repeating iteration, advancing after scope exit, or
reading `pin` / `edition` outside the entered scope raises
`SnapshotStreamStateError`. The default iterator raises at invalid roots;
the checked iterator returns their records. There are no arity accessors or
whole-stream projection.

`batch_size` defaults to 1000 and requires a positive exact built-in integer;
it counts root positions. It is a per-call option only. Core determines page
stability and continuation ordering. A non-total continuation raises
`SnapshotStreamContinuationError` with code
`snapshot-stream-continuation-order-not-total`; its coordinate is diagnostic
data excluded from default messages and logging.

Typed stream `wire(value, at=...)` is available only while delivery is paused
at a yielded root, including the final yielded root before the next advance.
Before the first yield, during advance, after exhaustion or failure, and after
scope exit it raises `SnapshotStreamStateError`. It neither advances nor reads.
Its input and requested-position rules are the eager projection rules.
