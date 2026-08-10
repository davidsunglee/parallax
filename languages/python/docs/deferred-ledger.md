# Deferred-work ledger — Python target

Work deliberately deferred while building the Python target, kept in one place so
it is not lost across sessions. It holds **only items that are actively open and
owned by nothing else** — work surfaced during design or implementation that
would otherwise have no home.

Scope is this target. An entry whose repair lands outside `languages/python`
still belongs here when Python work surfaced it and nothing else tracks it, but
it must name its true owner so a second language target inheriting the same gap
can find it. A neutral concern that outlives this target is promoted to a core
specification, an issue, or a ledger of its own rather than left here.

This is not a duplicate of the `languages/python/spec/python.md` §1 deferral
list, which is canonical for deferred capabilities, and it does not restate work
already tracked as a Linear issue.

## Protocol

Read this file at session start. Add an entry in the same session any deferral
happens — never only in a commit message, a code comment, or a task artifact.
Sweep it at claim closure.

Closing, graduating, or otherwise giving an entry a home means **removing it**
and leaving a forwarding line below, so this file stays a work list rather than
an archive. An entry that is resolved, closed, graduated to a Linear issue, or
carried in full by one is not an entry here.

Entry numbering is continuous and never reused. The next new number is **D-69**.

## Standing notes

Not deferrals — decisions already made that a future session is likely to try to
undo.

### `python.md` §3's document-resident nullability bullet is settled. Do not "tighten" it

The bullet states that no layer enforces declared nullability at a
document-resident position, what Entity Graph Construction still validates
there, and the judged boundary under Relational Document Layout stated by stored
state.

It reads like something that wants fixing. It does not. The behavior it
describes is corpus-mandated: `m-value-object-023` grades `city: null` for a leaf
`core/compatibility/models/customer.yaml` declares without `nullable: true`, and
core specifications plus the compatibility corpus outrank the language spec.
Enforcing nullability at construction was implemented once and reverted — it
fails five database-backed reads with `entity-graph-invalid-value:
parallax.compatibility.Customer.address.city is not nullable and admits no null`.

The bullet took five external review rounds to state correctly, because the
truth is a matrix over layout × depth × multiplicity × nullability × stored
state and earlier drafts quantified over positions rather than states. Rewriting
it casually will reintroduce a falsehood.

The behavior is owned onward by
[COR-85](https://linear.app/flimflam/issue/COR-85/report-nodes-whose-stored-state-violates-the-declared-model-instead-of).
Reopen the bullet only if a change to conversion alters the behavior it
describes — and read COR-85 first, since its first phase reconciles the
underlying core-spec contradiction.

### `SnapshotDecodingError` keeps its chained cause. The stored value is meant to be reachable

The refusal's own message names only the Entity and the member at fault. The
value that provoked it survives on the chained `LeafEncodingError`, which quotes
it. A review will read `python.md`'s "exposes no raw database value" as covering
the whole exception chain and call this a violation; it has been raised twice and
answered by decision.

Two facts make keeping the cause the right call. `core/spec/m-db-port.md:56` uses
"raw database value" for a driver-native value *before* normalization, so nothing
above the adapter seam holds one under the term of art. More importantly,
`decode_leaf` enforces **canonical spelling**, not type: a decimal short of its
declared scale, uppercase hexadecimal, a non-UTC timestamp, an uppercase or
hyphenless UUID, and a non-shortest float are all the right kind and the right
type and still wrong. `'12.5' is not the document encoding of any
Decimal(precision=10, scale=2) value` is diagnosable; the same sentence with the
value removed reads "a `str` is not the document encoding of a decimal", which is
both false and unactionable. Suppressing the value deletes exactly what
distinguishes these failures from one another.

The accepted cost is that a caller who logs the exception chain writes stored
data into a log. `python.md` §3 states the boundary the code implements —
message clean, cause carrying — rather than an absolute that contradicts the same
sentence's requirement to carry a cause.

Considered and not taken: carrying the value as a structured field while making
every rendered message value-free. It is a genuine improvement and would let both
readings hold at once, but it changes a shared core refusal's text for the
write-lowering and conformance-assembly lanes. Revisit it there, not by
re-litigating this bullet.

## Entries

### D-53 — Three off-path bare-name reductions remain, each with a reproduced defect and a non-determinate repair

*Low — off every production path, recorded so the sweep is not re-run from
scratch.* Relates to `parallax.descriptor._records.concrete_descendant_names`,
`parallax.conformance.engine`.

**What.** One defect class — an exact `EntityIdentity` reduced to a bare local
name — was chased through five call sites and fixed at all five. Two further
sites of the same class were found, verified off-path, and left:

- `_records.concrete_descendant_names` keys `by_name` on `candidate.name` and
  indexes children by the raw authored `parent` string, so two same-local-name
  entities overwrite each other and a model mixing qualified and relative parent
  spellings splits the child index. It has **no production caller at all** — only
  its own `__all__`, the module docstring, and a unit suite.
- The conformance engine's default-target convention returns bare names
  (`_rejected_target`, `_conflict_target`), which feed `meta.entity(...)` and
  would raise `KeyError` on a duplicated local name.

The pre-formation family walk carried a third instance of the same defect and no
longer does: `parallax.descriptor._family` keys every walk on
`Entity.canonical_name` and resolves a bare `parent` through
`_records.parent_identity`, with the two namespace shapes pinned by
`tests/unit/test_descriptor_family.py`.

**Why it is deferred rather than fixed.** Each repair changes an exported
contract with no caller to validate it against. `concrete_descendant_names`'s fix
makes both `position` and the returned names canonical, and the prior question is
whether an unused export should exist at all. Both are unwitnessed: no `rejected`
corpus model declares a namespace.

### D-54 — Every inherited Pydantic field on an Entity subtype defaults to the ancestor descriptor's class-access expression, so a subtype constructs with no arguments

*High — a required member silently holds a query expression.* Relates to
`parallax.core.entity._declaration._build_entity`.

**What.** `Tug()` — a concrete subtype of an abstract temporal root declaring no
members of its own — constructs with no arguments, and every inherited member,
**including required ones like `id`**, holds an `AttributeExpr`:

```text
Tug() -> Tug
  .id       -> <parallax.core.entity._expressions.AttributeExpr object>
  .tx_start -> <parallax.core.entity._expressions.AttributeExpr object>
```

**Why it is open.** `_build_entity` `setattr`s the class-access descriptor over
the class attribute *after* Pydantic has built the parent model, and Pydantic
re-reads that attribute when it collects a subclass's inherited fields — so the
descriptor object itself becomes the inherited field's default. The Entity's own
declared members are unaffected; only inherited ones are.

**Why it is deferred rather than fixed.** It is pre-existing: a subtype's
inherited members carried this default whether or not the parent supplied one.
The fix is an ordering change in the declaration engine — install descriptors
before Pydantic collects subclass fields, or strip them from the collected
defaults — which touches the shared metaclass engine both the Entity and Value
Object frontends depend on, so it wants its own coverage rather than a rider.

### D-55 — The reference harness grades a scenario find's `expectRows` against the raw projected row, disagreeing with `m-case-format` for a family target

*Low — narrows what a corpus case may assert, never produces a wrong pass.*
**Owned by the reference harness, not this target** — the only entry here whose
repair lands outside `languages/python`, kept because Python work surfaced it and
nothing else tracks it. Relates to `reference-harness`
`case_runner._materialize_family_variant`.

**What.** `m-case-format` (*Read result form*) states that a scenario observation
find is **instance-form**, and the Python run sweep grades it that way. The
harness grades that step's `expectRows` against the raw projected row instead.
The two agree except for a **family target**, where the projection and the
materialized instance differ.

**Why it is deferred rather than fixed.** The one case needing an abstract-root
find inside a `uow` group worked around the gap by having that find assert no
rows of its own, with the row assertion carried by the concrete verify read that
follows — so the case is correct and complete, and nothing is mis-graded. Closing
the gap means threading a step's own target and golden projection into
`_materialize_family_variant`, which is harness work outside any Python-target
ticket.

### D-56 — A table-per-concrete-subtype union-all read cannot run inside a transaction in either concurrency mode

*Medium — a legal read shape is unreachable from `Transaction.find`.* Relates to
`read_lock.mode_for`, `parallax.core.sql_gen._inheritance._plan_tpcs_read`.

**What.** `read_lock.mode_for` is the identity function, so a read carries a
non-`None` lock mode under **both** `locking` and `optimistic`, and
`_plan_tpcs_read` refuses a union-all read carrying any lock (its "has no
goldened lowering yet" refusal). A TPCS family — the corpus's `Rate` — is
therefore readable through `db.find` and not through `Transaction.find`.

**Why it is deferred rather than fixed.** It is a lowering gap with a goldening
cost. The abstract-target licensing proof that hit this used a
table-per-hierarchy family instead; the symptom the proof needed — one read whose
rows resolve to their own concretes — is the same either way, so nothing was
lost. Any later work reaching for a TPCS family through a transaction hits the
same wall and must plan around it or close it.

### D-58 — Neutral Snapshot graph, tree, wire, and streaming shapes need one holistic decision

*Design follow-up — deliberately excluded from COR-93.* Relates to
`m-snapshot-read`, `m-conformance-adapter`, `parallax.snapshot.handle`, and the
future streaming work tracked in COR-83.

**What.** COR-93 keeps the current Snapshot graph semantics for its provisional
Python `NeutralGraph`: roots are views over graph-local uniqued nodes, so cycles,
diamonds, and shared descendants retain identity without duplicating logical
nodes. A later representation may instead expose an ordered list of rooted
trees. That could give eager and streaming reads the same traversal API and let
neutral results render directly to JSON/wire, at the accepted cost that separate
roots or branches may materialize distinct in-memory objects for one logical
node.

**Why it is deferred rather than fixed.** Changing only COR-93's adapter would
silently fork core Snapshot semantics. The decision crosses core graph identity,
compatibility graph oracles, Python typed and neutral results, cycle rendering,
wire shape, and bounded-memory streaming. It needs its own grilling session and
ticket after conformance has been reduced to the production path; COR-93 must not
combine that semantic migration with deleting the duplicate engine.

### D-62 — A graph-form read whose deep fetch sits under a result wrapper passes the read gate and fails in SQL generation after a force-flush

*Medium — a legal operation reaches execution and fails late, having already
written.* **Owned by
[COR-96](https://linear.app/flimflam/issue/COR-96/decide-what-a-row-returning-wrapper-over-a-deep-fetch-means), not this
target** — what the shape denotes is a core-specification decision, and this
entry records only what Python does until that decision is made, so a second
language target inheriting the same ingress finds it. Relates to
`parallax.snapshot.handle._preflight.preflight_neutral`,
`parallax.snapshot.handle._features`, `parallax.core.deep_fetch.plan`.

**What.** `m-op-algebra` composes `deepFetch` freely under the nodes that return
their operand's own rows, so `limit(deepFetch(all, path), 5)` is a legal
operation. Find Query lowering never emits one — it places the deep fetch
outermost — but the model-neutral read ingress accepts any legal operation, so
the shape now reaches execution. `deep_fetch.plan` reads the outer node alone: it
plans zero levels and hands the whole operation, deep fetch included, to
`compile_read`, which raises `SqlGenError`. On a participating read that lands
after `uow.read`'s force-flush — the recorded port sequence is `['begin',
'write', 'rollback']`, with the buffered DML already executed.

Two neighbouring shapes are settled and are not this entry. A ROW-form request
carrying the same operation is refused at the read gate, which walks the wrapper
spine, because the values lane materializes no relationship level at any depth.
A wrapper-carried deep fetch over a SCANNED temporal axis is refused one step
earlier as the `snapshot-history-includes` Deferred Execution Feature, which
`m-snapshot-read` already defines.

**Why it is deferred rather than fixed.** Every available repair presumes an
answer to the unstated question: what the graph a row-returning wrapper over a
deep fetch denotes. Planner support would build one denotation into the
implementation. A new Deferred Execution Feature would name a Feature no core tag
defines, and would be retired the moment the denotation is stated. A gate
rejection would report the operation invalid when the specification permits it
and only the implementation is behind. Python therefore adds neither, states the
bound truthfully at the gate, and follows COR-96's decision.

### D-67 — A deep-fetch or snapshot CHILD level's graph node shape is authored per projection, and production materializes one merged, narrowed node

*Medium — a corpus-versus-production divergence with no defect on either side.*
Relates to `core/spec/m-case-format.md` *Read targeting*,
`parallax.snapshot.materialize`, the conformance engine's graph lane, and the
reference harness's own deep-fetch grader.

**What.** `then.graph` now grades the graph production materializes, and eleven
cases disagree with it structurally: `m-inheritance-065` / `-066` / `-067` /
`-068` / `-073` / `-074` / `-075` / `-076` / `-077` / `-078` and
`m-snapshot-read-012`. Three divergences, each an instance of one difference —
the corpus authors a child level's nodes PER PROJECTION and production
materializes one node per LOGICAL ROW:

- a multi-concrete level's node is authored as the unnarrowed concrete superset
  with a sibling branch's `null` padding, while a materialized node carries its
  own variant's declared members alone;
- `familyVariant` is authored by the VIEW that reached the node — present on a
  polymorphic view, absent on a single-concrete narrowed one — while a
  materialized node's variant spelling is its own, the same through every view;
- one logical row reached through two views is authored twice with different
  values, and materializes as one shared node, so a path that revisits it is a
  back-reference cycle and truncates to its primary-key stub.

**Why it is deferred rather than fixed.** `m-case-format` *Read targeting*
already names this as open: the per-variant node shape "is scoped, for now, to a
read case's own top-level `then.graph` leaves", and "a deep-fetch or snapshot
CHILD level's graph node shape (`m-snapshot-read-012`'s narrowed-vs-broad
diamond, for example) is a distinct, already-established convention this decision
does not touch; reconciling the two … is left open for a follow-up." Reconciling
it moves the corpus AND the reference harness's `_assert_deep_fetch` grader,
whose node registry is deliberately keyed per view, so it is a
core-specification decision rather than an adapter one. Until it is taken, the
Python run sweep grades everything else these eleven assert — every level's SQL
and binds, the round-trip count — and withholds the `then.graph` comparison
alone (`tests/compatibility/test_run_sweep.py._CHILD_LEVEL_GRAPH_SHAPE_DEFERRED`).

**What that leaves ungraded.** Nine of the eleven carry a graph story
(`parallax.conformance.graph_stories`), so `tests/api/test_story_run.py` still
walks the same merged graph through the typed developer surface against a real
database, and only the wire rendering goes ungraded. `m-inheritance-073` and
`-077` carry no story, and cannot: each needs a path-root guard resolving to two
or more concrete subtypes (`to: [Cat, Dog]` for both, plus `to: [Pet]` for `-073`
and `to: [Dog, WildBoar]` for `-077`), and the idiomatic developer surface
authors a path-root guard only by reaching an inherited relationship through ONE
subtype class (`Dog.owner`) — `FindQuery._root_guard` and
`RelationshipPath.source` (`parallax.core.entity._query`, `._expressions`) admit
no multi-subtype union. This is not an unwritten story but the same structural
non-fit `parallax.conformance.api_suite.CASE_SKIP_REASONS` already records for
both ids (`_ROOT_GUARD_MULTI_SUBTYPE_SPELLING_UNREACHABLE_REASON`), so no Python
gate observes their graph at all, and none can be added in this shape. The
reference harness proves the goldens self-consistent against fixture data; it
grades no language implementation, so it covers none of this either.

**What COR-83 does not settle.** COR-83 ("Stream deep fetch reads at fixed
memory") is likely to remove the graph-level node-uniqueness requirement
(`parallax.snapshot.materialize._merge`) so each route in memory carries its own
full deep-fetch tree. That bears on divergence (c) alone — one logical row
reached twice sharing a node and truncating to a primary-key stub
(`parallax.conformance.engine._render_node`'s `visiting` recursion anchor) — and
only on `m-inheritance-078`, the one case among the eleven whose graph is an
actual back-reference cycle rather than two independent views of the same row
(`m-snapshot-read-012`'s diamond renders its shared row in full at both
positions; nothing there is ever truncated). Divergences (a) and (b) are decided
upstream of any merge — by `convert_row`'s per-row, per-concrete-entity
narrowing (`parallax.snapshot.materialize._convert:227-231`) and by
`_family_variant`'s per-node, per-concrete-entity spelling
(`parallax.snapshot.materialize._neutral:365-377`) — and neither reads whether
the resulting node was merged with another, so removing the merge leaves all
nine (a)/(b) cases diverging exactly as they do now. `m-inheritance-078` itself
carries an (a) mismatch in its own `pets` child level besides its (c) cycle, so
even it would not go green on the merge change alone. D-67 therefore survives
COR-83 and still needs the `m-case-format` reconciliation it names.

## Forwarding pointers

Removed entries whose number a live document still cites. One line each; drop a
line once nothing cites it. This section is not an entry list and must never grow
prose.

- **D-38** → [COR-67](https://linear.app/flimflam/issue/COR-67/triage-residual-defects-and-coverage-gaps-surfaced-by-cor-64) P7. Mirror the remaining 15 corpus models.
- **D-40** → [COR-67](https://linear.app/flimflam/issue/COR-67/triage-residual-defects-and-coverage-gaps-surfaced-by-cor-64) P4. Eager `fetchall` at the adapter boundary; port-level streaming is [COR-83](https://linear.app/flimflam/issue/COR-83/stream-deep-fetch-reads-at-fixed-memory).
- **D-44** → [COR-67](https://linear.app/flimflam/issue/COR-67/triage-residual-defects-and-coverage-gaps-surfaced-by-cor-64) P2. Deep-fetch depth beyond two hops.
- **D-45** → [COR-86](https://linear.app/flimflam/issue/COR-86/implement-history-with-includes-execution-and-empty-the-deferred). History-with-includes execution.
- **D-46**, **D-48** → [COR-85](https://linear.app/flimflam/issue/COR-85/report-nodes-whose-stored-state-violates-the-declared-model-instead-of). Stored state violating the declared model.
- **D-47** → fixed. `reduce_declared_members` gained `preserve_presence`, orthogonal to the `named_by` authored-member mask; `snapshot.materialize._convert._decode_element` passes it. Presence survives materialization at every containment depth, as `python.md` §3 and `core/spec/m-document-codec.md` state.
- **D-51** → [COR-67](https://linear.app/flimflam/issue/COR-67/triage-residual-defects-and-coverage-gaps-surfaced-by-cor-64) P6, item 6d. A defining to-one whose foreign key sits on the target side.
- **D-52** → closed by [COR-51](https://linear.app/flimflam/issue/COR-51/integrate-snapshot-writes-and-remove-legacy-frontend-surfaces). The silent unbinding it describes was already gone: [COR-89](https://linear.app/flimflam/issue/COR-89/let-an-operation-reference-name-a-namespaced-entity-and-migrate-the) made `targets(model)` register canonical spellings unconditionally and every serialized surface emit `identity.canonical`, so no in-tree producer can supply an ambiguous one. What COR-51 added is classification at the external-producer boundary — `unit_work.instructions._entity` and `snapshot.handle._read._metadata` both raise `reference-ambiguous-entity-name` — so a spelling arriving from outside is one refusal naming both candidates rather than a missing observation binding.
- **D-57** → closed by [COR-51](https://linear.app/flimflam/issue/COR-51/integrate-snapshot-writes-and-remove-legacy-frontend-surfaces). `_identity_row` applies `serialize_member`, so all three Entity Row Codec operations carry one form; `python.md` §5 states that uniform contract in place of the asymmetry, and no golden moved, because a primary key is structurally a scalar Attribute that `serialize_member` passes through unchanged.
- **D-60** → closed by this claim. The module's own source landed, so `MODULE_SCOPE` carries `parallax.core.execution_log`, the generated `[tool.importlinter]` block contracts it, `core/spec/modules.md` carries `m-snapshot-read --> m-execution-log`, and `m-snapshot-read.md` names the Read Trace its round-trip count is observed through. One consequence the entry did not foresee: `m-execution-log` reaches `m-sql`, so mapping the tag to `parallax.snapshot.materialize` would put SQL generation inside the closure of the grant `parallax.snapshot.handle._materializer` holds, dissolving the containment that child scope exists for. The tag therefore maps to `parallax.snapshot._read_result` — the scope that actually names the Read Trace — while `parallax.snapshot.materialize` carries the remaining `m-snapshot-read` edges as a support row.
- **D-59** → [COR-95](https://linear.app/flimflam/issue/COR-95/reference-harness-grades-thenexecution-second-witness-for-m-execution). `then.execution` has one grader; `spec/python.md` §1 carries the single-witness limit.
- **D-61** → [COR-95](https://linear.app/flimflam/issue/COR-95/reference-harness-grades-thenexecution-second-witness-for-m-execution). The envelope half: `validate_execution_observation` has no envelope-grading seam, and `core/spec/m-conformance-adapter.md` *Execution provenance* binds the adapter regardless.
- **D-63** → [COR-95](https://linear.app/flimflam/issue/COR-95/reference-harness-grades-thenexecution-second-witness-for-m-execution). The round-trip half: the eleven `then.roundTrips` authored on `boundary` and retry-shaped `conflict` cases have only this target's suites as a reader, because the harness runs no `api-conformance` lane and a retry-shaped conflict never reaches its round-trip assertion.
- **D-64** → [COR-85](https://linear.app/flimflam/issue/COR-85/make-a-models-observable-behavior-independent-of-storage-layout). A temporal milestone this engine rebuilds carries declared members and no Structured Column, so under Relational Document Layout the write is refused rather than chained: `engine._refuse_document_layout_milestone` for a milestone a grouped find returned, `engine._refuse_unaccounted_document_milestone` for one tracked case state supplies but out-of-band statements may have overtaken. COR-85's own Phase 3 successor rule deletes both.
- **D-65** → [COR-97](https://linear.app/flimflam/issue/COR-97/give-a-transaction-a-supported-abandon-and-the-execution-log-an-abort). A `rollback: true` step's abort sentinel records a `commit`-phase failure and an unclassified retry verdict, which no oracle reads; `engine._AbortingPort` states the untruth and its bound, and COR-97's `Transaction.abandon()` plus an `aborted` attempt status removes the decorator.
- **D-66** → [COR-99](https://linear.app/flimflam/issue/COR-99/audit-the-compatibility-corpus-against-what-production-would). A keyed temporal write settling against case state a committed materializing predicate write of the same case moved is refused (`engine._refuse_materialized_case_state`, marked by `temporal_state.TemporalShadow.note_materialized_write`): production resolves and plans that write internally and returns neither, so the adapter would issue a zero-row close where a real caller — who could only reach the step by reading — gets a stale write. COR-99 is the systematic pass over adapter/production divergences of that kind and cites this composition as its motivating example; this refusal is the one hand-placed instance of what that audit generalizes.
- **D-68** → closed by [COR-93](https://linear.app/flimflam/issue/COR-93/make-python-conformance-a-thin-adapter-over-the-production). `parallax.conformance` reaches a corpus model through the public `domain_model_from_document` door alone and reads the accepted Metamodel's own vocabulary, so no `parallax.descriptor` private import and no `parallax.core._formation_profile` reach survives; `ACCEPTED_CONFORMANCE_PRIVATE_REACHES` ends at three `parallax.core.entity` entries that `spec/python.md` §7 states as a rebuttal rather than an exemption. One question the accepted model cannot answer survives the conversion, and it is not a model question: the order a document declared its Entities in, which `m-case-format` makes load-bearing for a case naming no target and which `conformance.models.declared_entity_spellings` therefore reads off the decoded document. Nothing gates that convention, and [COR-99](https://linear.app/flimflam/issue/COR-99/audit-the-compatibility-corpus-against-what-production-would) carries it.

## History

Entries D-1 … D-51 were kept in per-ticket task directories under
`.humanlayer/tasks/`, which hold the full text of every resolved, closed, and
graduated entry. Consult them when a commit message or document cites a D-number
this file does not hold:

- `.humanlayer/tasks/cor-3-build-python-slice/05-deferred-ledger.md` — D-1 … D-37.
- `.humanlayer/tasks/cor-47-build-python-declarations/09-deferred-ledger.md` — D-36 … D-48.
