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

Entry numbering is continuous and never reused. The next new number is **D-85**.

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

### D-56 — A table-per-concrete-subtype union-all read cannot run inside a transaction whose target resolves to the Locking strategy

*Low — one concurrency mode of a legal read shape is unreachable from
`Transaction.find`.* Relates to `parallax.core.sql_gen._inheritance._plan_tpcs_read`,
`m-sql` *Ordered or limited abstract read*.

**What.** `_plan_tpcs_read` refuses a union-all read that requests a shared row
lock. PostgreSQL grants a locking clause over neither a `UNION` result nor any
input of one, and the suffix cannot be silently dropped because that lock is what
licenses a later ungated write. So a TPCS family — the corpus's `Rate` — is
readable inside a transaction whose target resolves to `optimistic`, and not
inside one that falls back to `locking` (an unversioned Non-Temporal or
Valid-Time-only target, or an explicit `concurrency="locking"`).

**Why it is deferred rather than fixed.** It is a database restriction rather than
a lowering gap: no spelling of the union acquires the lock the caller asked for.
Closing it means either locking the concrete rows through a second statement per
branch — which is a new statement-count contract — or refusing the fallback at the
`m-read-lock` layer instead, where the caller can see it. Both are design choices
with cross-language reach, so neither belongs in an incidental fix.

*(The wider half of this entry — every mode refused, including `optimistic`, and
`orderBy` / `limit` refused with them — is closed. The guard now tests
`lock == "locking"`, matching the append site's own check, and an ordered or
limited union wraps as a derived table: `m-inheritance-134` / `-135`.)*

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
  values, and materializes as ONE shared node, so both positions render that
  node's own merged members rather than each view's own projection.

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
subtype class (`Dog.owner`) — `ObjectQuery._source_guard`
(`parallax.core.object_query._fluent`) and `RelationshipPath.source`
(`parallax.core.entity._expressions`) admit no multi-subtype union. This is not an unwritten story but the same structural
non-fit `parallax.conformance.api_suite.CASE_SKIP_REASONS` already records for
both ids (`_ROOT_GUARD_MULTI_SUBTYPE_SPELLING_UNREACHABLE_REASON`), so no Python
gate observes their graph at all, and none can be added in this shape. The
reference harness proves the goldens self-consistent against fixture data; it
grades no language implementation, so it covers none of this either.

**What COR-83 does not settle.** COR-83 ("Stream deep fetch reads at fixed
memory") is likely to remove the graph-level node-uniqueness requirement
(`parallax.snapshot.materialize._merge`) so each route in memory carries its own
full deep-fetch tree. That bears on divergence (c) alone — one logical row
reached twice sharing a node — and only on `m-inheritance-078`, the one case
among the eleven that reaches a row a second time by revisiting an ANCESTOR
(`m-snapshot-read-012`'s diamond reaches its shared row through two independent
views instead, and the include tree renders it in full at both positions either
way). Divergences (a) and (b) are decided
upstream of any merge — by `convert_row`'s per-row, per-concrete-entity
narrowing (`parallax.snapshot.materialize._convert`) and by
`_family_variant`'s per-node, per-concrete-entity spelling
(`parallax.snapshot.materialize._wire`) — and neither reads whether
the resulting node was merged with another, so removing the merge leaves all
nine (a)/(b) cases diverging exactly as they do now. `m-inheritance-078` itself
carries an (a) mismatch in its own `pets` child level besides its (c) sharing, so
even it would not go green on the merge change alone. D-67 therefore survives
COR-83 and still needs the `m-case-format` reconciliation it names.

### D-69 — A hand-written skip-reason bucket states a cause untrue of some member, once per review round

*Should-fix — misleading to a reader; no grade and no coverage partition moves.*
Relates to `parallax.conformance.api_suite.CASE_SKIP_REASONS`.

**What.** Every active case the API Conformance Suite does not exercise as an
idiomatic example carries prose saying why, and cases sharing one cause share one
constant. That prose returned a finding in every round of COR-93's Phase F
boundary review — five rounds, five findings:

- round 1 (P2) — thirteen reasons named retired D-numbers as their owners;
- round 2 (S6) — reasons cited execution artifacts (tickets, increments, "this
  round") in place of the durable rationale beside them;
- round 3 (S8) — four buckets stated one blanket cause across case families whose
  causes differ;
- round 4 (S8) — one further bucket did, and the sweep found a fifth case the
  bucket's clause was false of;
- round 5 (S8) — **open.** `_INHERITANCE_AUDIT_TERMINATE_REASON`
  (`api_suite.py:687`) and `_INHERITANCE_BITEMPORAL_TERMINATE_REASON` (`:699`)
  both say the family composition adds "table routing plus the shared-table tag
  guard", and each is assigned to table-per-concrete-subtype cases that have no
  tag guard: `m-inheritance-091` (`:1359`), `-095` (`:1361`), `-097` (`:1363`),
  whose case headers state that a TPCS termination targets the subtype's own
  table "with NO tag guard". A table-per-hierarchy property is stated as common
  to every member.

**The cause,** diagnosed in round 4: a bucket keyed on case **shape** rather than
**cause**. A shape-keyed bucket — inheritance × temporal × termination answers
"what kind of case is this", not "why is no story possible" — absorbs any case
matching the shape whatever its actual reason, and its causal sentence then
stretches to cover members it is not true of. Most constants in the file are
already cause-keyed (`_OPT_LOCK_STALE_GATE_SECOND_WRITER_REASON`,
`_ROOT_GUARD_MULTI_SUBTYPE_SPELLING_UNREACHABLE_REASON`); the shape-keyed
survivors are the generator.

**Why hand-correction does not close it.** Four successive rounds each found a
real inaccuracy and each left another standing, two of them aimed squarely at
this class. Nothing in the repository gates that a bucket's stated reason is true
of its members: the coverage partition
(`tests/unit/test_api_suite.py::test_registry_classifies_every_active_module_without_stale_entries`)
checks that every active case is claimed by exactly one registry and that no
entry names nothing, and is indifferent to what the prose asserts. A wrong
sentence therefore costs nothing until an external reviewer reads it, which is
why only a reviewer finds these.

**Why it is deferred rather than fixed.** The repair is to stop hand-writing
bucket prose and derive the coverage rationale mechanically from the traits that
decide it — the case's storage strategy, its mutation verb, and which story does
or does not spell that verb — so a stated reason cannot drift from the cases it
covers. That restructures `api_suite.py` and its registries rather than rewording
them, and it needs a review of its own; taking it as COR-93 closed would have
landed an unreviewed restructuring of the very surface the boundary review was
measuring. Until it is taken the residue is reader-facing only: no case id enters
or leaves the skip map, no case changes lane, and no grade moves.

### D-70 — A transaction's own buffered insert leaves a later keyed write of that object with no evidence once a flush intervenes

*High — a correct program earns a refusal it cannot avoid.* Relates to
`parallax.snapshot.handle._write_inputs.resolve_write_evidence`,
`parallax.snapshot.handle.Transaction`'s buffered-insert ledger.

**What.** `tx.insert(a)` exempts a later keyed write of `a` from the
provenance rule, because a row this unit of work inserted is a row it stores. The
exemption is keyed by the object and is never retired. So the sequence
`tx.insert(a)`, then a participating read that force-flushes the buffer, then a
keyed write of that same object, resolves **no** evidence: the insert is no
longer pending, the value the caller still holds carries no Source Hint, and the
write reaches settlement with nothing to advance from or gate on. A versioned
target fails at settlement despite the transaction holding a perfectly fresh
observation of the row the flush just wrote. It reproduces identically through
both representations, because they share one buffer and one ledger.

**Why it is deferred rather than fixed.** It is an evidence-**lifetime** question
rather than an ingress one: what has to be decided is when an insert's exemption
ends, and what the transaction owes the caller at that moment — re-reading the
row itself is one answer, retiring the exemption at the flush and requiring the
caller to write what the post-flush read returned is another, and they differ in
whether the framework is permitted to issue a read on a keyed write's behalf,
which every other rule in this area says it is not. The gap predates the write
surface's own rework and no acceptance criterion reaches it.

### D-72 — Milestone-set staging and predicate-write staging still refuse an issue-bearing read instead of classifying it

*Medium — one stored state is classified on the ordinary read lane and refused on
two others.* Relates to `parallax.snapshot.materialize` staging seams,
`core/spec/m-snapshot-read.md`.

**What.** A read whose stored state contradicts the declared model is classified
at the result root and published as an ordinary union member. Two staging paths
keep the older shared publication refusal instead: milestone-set staging, which
must decode a temporal edge before it can partition, and predicate-write staging,
which has no channel to put a classified verdict on. So the same row reads as a
classified result through one door and raises through the other two.

**Why it is deferred rather than fixed.** Converting either now would move a
refusal without giving the verdict anywhere to go: a milestone partition needs an
edge it cannot decode from an unhydratable row, and a predicate-selected write
needs a decision about what selecting an invalid row even means, which is a write
contract rather than a read one. Only the values lane was required, and it was
converted.

### D-74 — No corpus model pairs a versioned root with an unversioned relationship target, so one preference resolving two ways has a single grader

*Medium — shipped behavior proven at one interface instead of two.* **Owned by
the compatibility corpus, not this target**, and kept here because Python work
surfaced it and nothing else tracks it. Relates to `core/compatibility/models`,
`tests/unit/_mixed_strategy_model.py`.

**What.** An Effective Concurrency Strategy is a property of the target Entity,
so one `optimistic` preference over one connected model resolves per Entity: a
deep read whose root declares a version and whose related Entity does not emits
no row lock at the versioned level, the shared row lock at the unversioned one,
and gates only the versioned target's write. No corpus model pairs a versioned
root with an unversioned relationship target, so the derivation is witnessed
only by this target's own model twin
(`_mixed_strategy_model.py`, read through `test_transaction_reads.py` and
written through `test_transaction_writes.py`). `m-opt-lock-023` proves the
one-preference-one-Entity arm alone.

**Why it is deferred rather than fixed.** The shape is perfectly authorable, so
this is corpus work rather than a limit: a descriptor pairing the two Entities,
its fixtures, and regenerated storage and table-layout baselines, for an
observation an interface test already pins exactly. Nothing in the write or read
contract depends on it, and no acceptance criterion reaches it — what it buys is
the second grader every other claimed observable has.

### D-75 — A READLESS predicate write step is refused on the snapshot-scenario lane, though nothing about that shape conflicts with it

*Low — a refusal narrower than it needs to be, on a shape no case authors.*
Relates to `parallax.conformance.engine._snapshot_write_entries`.

**What.** The snapshot-scenario lane now executes `write:` steps, and it admits
the buffered KEYED instruction list alone: `_snapshot_write_entries` classifies
every other `write` form and refuses each by its own name. A MATERIALIZING
predicate write is refused permanently and correctly — it resolves through the
find step that precedes it (`_run_materializing_pair`), and a find on this lane
materializes a view a later `access` states rather than the rows a write settles
against, so the two step roles genuinely conflict. A READLESS predicate write
(the `m-batch-write-005` / `-006` shape) needs no find at all, so nothing about
it conflicts with this lane; its refusal says so — the shape is unwired here, not
mis-authored. Wiring it would reuse `_lower_predicate_write_step` and
`_run_readless_predicate_write` unchanged, as the unit-of-work lane already does.

**Why it is deferred rather than fixed.** No corpus case pairs a predicate write
with a lifecycle action step, so the branch would ship unexercised — a coverage
cost for a shape nothing asks for. The moment a case authors one, the repair is
the branch plus its own DB-free driver; until then the honest state is the
refusal this entry describes, which already says which half of itself is
permanent.

### D-77 — The interleaved-`uow`-group runner refuses a step stating relationship contents, though its own find interpreter already holds what would answer one

*Low — a refusal on a shape no case authors.* Relates to
`parallax.conformance.engine.run_interleaved_scenario_case`.

**What.** `expectGraph`'s READ placement is legal on any include-bearing read step
(`core/spec/m-case-format.md` *Relationship contents at a step*), and three of
this target's four find interpreters answer it: the ungrouped standalone find,
`_run_uow_group`'s own step loop, and the snapshot lane's find each publish a
`stepGraphs` entry through `_read_step_graph`. The fourth —
`run_interleaved_scenario_case`, the two-group optimistic-lock race entry point —
refuses such a step by name before either worker thread starts, because its
return is a four-tuple (emissions, round trips, the conflict's `actual`, every
find's own rows) carrying no `stepGraphs` channel at all. Nothing about the
interleaved shape conflicts with the observable: `_run_interleaved_group` drives
the SAME `_run_group_step` interpreter the contiguous runner does and already
holds each find's own published output, which is exactly what `_read_step_graph`
takes. The reference harness grades the same authored `expectGraph` on an
interleaved read step today, so the limit is this target's rather than the case
format's — the shape is unwired here, not mis-authored.

**Why it is deferred rather than fixed.** No corpus case pairs an interleaved race
with an include-bearing read, so the channel would ship unexercised — a coverage
cost for a shape nothing asks for. Reaching it also costs more than the call
site: this entry point's tuple would widen to five across the run sweep and its
unit drivers, repeating the width `run_scenario_case` already retired into
`ScenarioRun`. The moment a case authors the combination, the repair is the
channel, a value object for the return, and its own DB-free driver; until then
the honest state is the refusal, which names precisely what it lacks.

### D-78 — Two conformance write lanes run DML no Handle opened, so their work reaches no Execution Lifecycle

*Medium — it bounds which case shapes may author `then.executionLifecycle`.*
Relates to `parallax.conformance.engine._execute_framework_write_unit`,
`parallax.conformance.engine._run_conflict_close`.

**What.** Every other write lane drives its DML through a real `db.transact`, so
its statements and round trips are read off the delivered lifecycle. Two do not,
because the DML they run has no public verb to be stated through: a
`{"increment": n}` DB-computed write marker is the PK allocator's own statement,
and a conflict case's standalone temporal close is unreachable through any keyed
verb — every closure-bearing `bitemp_write._TOPOLOGIES` entry chains at least the
head rectangle, and a Transaction-Time-Only `terminate` derives its address from
the milestone its observation names while a conflict case authors both
coordinates directly. Both therefore execute a plan of their own against
`m-db-port` and STATE their round trips, exactly as `run_error_case` does for
authored trigger DML. The consequence is bounded and real: a case reaching either
shape opens no Root Execution for that work, so it can author no
`then.executionLifecycle` — the stream would omit calls the run made, and the
record's own count cross-check (`reference_harness.execution_validate`) would
report the disagreement rather than the case grading a stream missing them.

**Why it is deferred rather than fixed.** Closing it is a design choice with real
costs on every branch, and no case needs it today. Routing the work through
`parallax.snapshot.handle` means giving a DB-computed write marker a public
ingress — developer surface over the framework's own bookkeeping — or adding a
bare-close verb no application wants. Adding an instrumented seam for the adapter
alone puts a test-shaped door in production. Restricting the oracle instead is
free but states the limit nowhere the corpus can see it. What holds the gap shut
meanwhile is that neither lane can silently grow a second: every `handle.Database`
the engine builds installs a Provider, asserted over the source
(`tests/unit/test_lifecycle_observation.py`), so an unobserved lane is one that
opens no Handle at all and says so.

### D-79 — The logging built-in builds a field mapping for every transition, including the ones its Logger will drop

*Medium — 1.25 µs/event of the production fan-out's 4.34, paid at every level.*
Relates to
`parallax.core.execution_lifecycle._logging._LoggingHandler.handle`.

**What.** `handle` renders each event and fills a `dict` of correlation, payload,
and — for a root's Finished — ten counters, then hands it to `Logger.log` through
`extra=`. Under any production level most of those records are dropped
immediately: the level rule gives `DEBUG` to every Started and every non-root
Finished, so an `INFO` Logger over the baseline workload keeps two of twenty
records and the mapping is built for all twenty.
`languages/python/docs/execution-lifecycle-baseline.md` isolates the cost — the
configuration whose Logger keeps nothing still measures 1.25 µs/event, 29% of the
production fan-out's dispatch.

The repair that has no correctness premise is a **lazily materialized `extra`
mapping**: pass `Logger.log` a `Mapping` that holds the event, the detail, and
the Handler's counters and renders the fields on first access. `Logger.makeRecord`
iterates `extra` only for a record that has already survived `isEnabledFor`, so a
dropped record touches nothing and a kept one pays exactly what it pays today,
with no question asked of the Logger that the Logger did not already answer.

**Why it is deferred rather than fixed.** It is a redesign of what the built-in
hands the standard library, and it deserves its own change and its own review.
`makeRecord` copies `extra` key by key and rejects the three reserved names, so
the lazy mapping has to satisfy the whole `Mapping` protocol against an
implementation detail of the standard library, and every Provider composed
downstream — a `QueueHandler`, a formatter, an exporter — reads the record's
attributes after that copy rather than the mapping, which has to be verified
rather than assumed.

What must NOT be done instead, because it was tried and reverted: asking
`Logger.isEnabledFor` before describing, and skipping the mapping when the answer
is no. `Logger.log` and `Logger.handle` reach overridable Logger state, so a
Logger an application legitimately configures can answer the guard's query and
`log`'s own query differently and lose a record that ships today — a subclass
whose `log` emits past the level, a Logger carrying another Logger's bound `log`,
and a stateful `disabled` descriptor or `isEnabledFor` are three such shapes, and
narrowing the guard to exclude each of them found a fourth each time. An
optimization on a built-in Provider may not decide which records exist.

### D-80 — A logical node's whole member row is first-projection-wins, and nothing states the equal-positions premise that makes it sound

*Low today, latent — sound for every read shape this target compiles now, and
silently lossy for the first one that projects a proper subset of a concrete's
members.* Relates to
`parallax.snapshot.materialize._merge.GraphMerge.member_values`,
`parallax.snapshot.materialize._merge.GraphMerge._walk`.

**What.** Merging duplicate projections of one logical node used to union member
*sets* across those projections, first-wins per member. The indexed merge picks
ONE winning projection for the node's whole member row and answers
`member_values(node)` as that projection's own row by reference, comparing
nothing. The two rules agree only while every projection of one concrete Entity
carries the same positions: row width is fixed by the exact-model member layout,
and a concrete's compiled attribute reads and projected documents are a function
of the concrete rather than of which read reached it, so a member a read did not
project occupies its declared position and reads `ABSENT` rather than being
absent from the row. Where that premise fails — one projection holding `ABSENT`
at a position another projection holds a value at, with the first walked winning
— the merged node silently drops what the other carried, with no issue recorded
and no refusal.

No unit test states the premise. The corpus compile and run sweeps, the graph
stories against real Postgres, and the database suites all grade its consequence
over the shapes production compiles today, which is what makes the representation
cutover safe; none of them would name the rule if a future read shape broke it.

**Why it is deferred rather than fixed.** A witness needs a graph whose two
projections of one logical row genuinely disagree by position, and no read this
target compiles is known to produce one. Manufacturing one means either doctoring
a member layout after the catalog answered it, which grades the merge against a
row shape no accepted model can hold, or widening a compiled read to project a
proper subset of its concrete — which is exactly the change
[COR-83](https://linear.app/flimflam/issue/COR-83/stream-deep-fetch-reads-at-fixed-memory)
makes when it streams a deep fetch at fixed memory. The witness belongs with that
change, where the disagreeing shape is a real read rather than a fixture, and it
is owed before that change lands rather than after.

### D-81 — The retained-graph gate proves no carrier per member, record, occurrence or slot, and cannot prove none per projection

*Low, and a limit of the instrument rather than a suspected defect.* Relates to
`tests/unit/test_snapshot_graph_retention.py`,
`languages/python/docs/snapshot-graph-baseline.md`.

**What.** The gate reads a retained total against the same graph declaring no
Value Object, prices the whole declared tree by the recursion the reduction
descends it with, and steps each population — members, leaves, records,
occurrences of each multiplicity, view slots — with a negative control per step.
That closes a carrier charged per member, per record, per occurrence, or per
slot, at any depth, in any state a conforming read can leave a position in.

It cannot close a carrier held exactly **once per projection**. Such a wrapper
scales with the projection count every step holds fixed, so it lands in the fit's
origin and moves no difference; and being a built-in `tuple` or `dict` it is
indistinguishable by type from the graph's own arrays, so the survivor census
— which keeps only Parallax's own types — does not name it either. Two readings
bound it without closing it: the retained total is affine in the populations with
no per-projection term the layout does not explain, and the census names every
surviving type and its count.

Two narrower shapes sit beside it. A state point puts a whole population in one
state, so rows mixing zero and carried members across one row are unread — what
is closed is that each kind of position reaches each state its contract admits.
And the primary key and the three join Attributes stay carried in every state,
because a row holding one of them zero is one no query would have returned, so
their own zero states are reached through the other Attributes.

**Why it is deferred rather than fixed.** Closing it needs an instrument that
distinguishes a graph's own arrays from a wrapper over them by provenance rather
than by type — the census filter would have to know which `tuple` a sealed graph
allocated, which `tracemalloc` and the gc do not record. The bound the affine fit
and the census already give is what a byte-level instrument can state, and the
representation this gate was written for allocates no such wrapper: the sealed
graph's arrays are its rows. The gap is worth an entry because it is the one part
of "zero retained per-cell carriers" that is argued rather than measured, and a
future representation could reintroduce exactly the shape it cannot see.

### D-82 — A published dump builds the same presentation twice, and removing the second build needs no bracket

*Medium — two identical mapping builds are 62% of a published `model_dump`, and
1.55x of it is recoverable with retained memory measured flat.* Relates to
`parallax.core.entity._instance_state._DeclaredState.__get__`,
`parallax.core.entity._instance_state.plan_of`,
`parallax.core.entity._instance_state._PresentedState`.

A published value's serialization cost is an accepted part of the Interface:
`_instance_state`'s module docstring and `spec/python.md` §2 both state that a
published `model_dump` runs roughly twice an ordinary one because the presentation
is built per read. This entry is the optimization path for that stated cost, held
here so the accepted fact and what is known about reducing it cannot drift apart.

**What.** The two `__dict__` reads per instance per dump are both in
pydantic-core's `ModelSerializer`, and the first one's value is discarded.
`ModelSerializer::allow_value` answers the `SerCheck::None` case with
`value.hasattr("__dict__")` and uses only the boolean;
`ModelSerializer::get_inner_value` then performs the real
`getattr(...).cast_into::<PyDict>()`. Because `hasattr` on a data descriptor
invokes `__get__`, answering that boolean costs a whole presentation build.
Measured on CPython 3.14.7 / pydantic 2.13.4 / pydantic-core 2.46.4, against real
published values built through `allocate` and `publish` over the six canonical
scenarios of `languages/python/docs/instance-state-baseline.md`: one published
`__dict__` read is 542–576 ns, and the two of them are 62% of the dump. Three
independent readings agree — the Rust source at 2.41.5 and at 2.48.0, which
bracket the installed 2.46.4 (whose own tag was not fetchable); a poison test on
the installed binary, proving the first read's value is discarded and the second
is the cast; and a union differential, where a plain union makes `SerCheck`
`Strict`/`Lax`, answers by type, and drops the count to exactly one.

**When these were read, and against what.** Every nanosecond and every factor in
this entry — the retained-memory readings and the template-copy comparison aside —
was taken against a presentation build that reached the auxiliary slot through a
helper function and let `_PresentedState` inherit `dict`'s own initializer. That
build has since been inlined into `_DeclaredState.__get__` and the class has been
given an initializer of its own, so the per-read cost these figures divide has
moved. They stand as readings of that earlier build rather than of the tree today,
and a pass taking this entry re-baselines them before claiming any one of them.

**The pair is structurally adjacent, and that is the load-bearing result.** No
Python executes between the two reads, at any depth and inside any container. The
scope that needs covering is therefore the pair rather than the run, and a pair
disposes of itself on its second read: **no bracket is needed**, which is what
makes every bracketing mechanism below unnecessary rather than merely expensive.

**What it buys.** Three ingredients, measured over a `TypeAdapter(list[…])` dump
of 1000 distinct published instances of one all-optional-member declared class —
1557 µs published against 585 µs for the same class ordinarily backed:

- **Drop `strict=True` from the `zip`** that builds the presentation — −50 ns per
  read, **1.09x**, no behavior change. It is a redundant assertion, because the
  widths cannot disagree: `PublicationPlan.field_values` is built from one index
  per name in `plan.fields` and answers a tuple of exactly that width at each of
  the three widths `_permutation` spells it at — `operator.itemgetter` at two or
  more, and the lambdas that answer `()` and a one-tuple at the degenerate two —
  while `install` already refuses a plan whose members and the class's collected
  Pydantic fields name different sets. The same argument covers the sibling zips
  in `declared` and `named_state`, which were not priced.
- **Replace `plan_of`'s MRO `getattr` with a type-keyed dict lookup** — 66.5 ns
  to 17.2 ns, a further **1.08x**. No lookup answers differently and no domain
  value changes; what does change is observable elsewhere. The caveat to decide
  rather than absorb: a `dict[type, PublicationPlan]` pins every published class
  for the life of the process, and a `WeakKeyDictionary` costs more than the
  `getattr` it replaces. Nothing pins one today. No registry holds a declared
  class, so an Entity declared inside a function and composed into a Domain Model
  is collected once that model and every reference to the class are dropped — a
  weak reference to it clears on the next `gc.collect()`. The strong dict is
  therefore a real change in class lifetime rather than a cost already paid.
- **A one-slot, one-shot, `has_auxiliary`-gated memo on the presentation** — hit
  returns the mapping and clears the slot, miss builds and stores, and a class
  whose `PublicationPlan.has_auxiliary` is true never memoizes at all. The hit
  rate is exactly 50.0% in every scenario, which is the adjacency above restated:
  every pair hits. **1.39x alone**, **1.55x** with the two ingredients above, and
  **1.65x** with the gated fourth below — taking a published dump from 2.66x an
  ordinary value's to 1.62x.

**Retained memory is O(1) and measured flat**, which is what distinguishes this
memo from the per-node cache `_DeclaredState` forbids. `tracemalloc` after a full
run with the output freed and `gc.collect()` called reads 656 / 592 / 512 B total
at 1k / 5k / 20k nodes today and 624 / 544 / 480 B for the memo arm, and
`gc.get_referents(node)` names zero `dict` referents on every node in every arm.
The memo holds one `(instance, mapping)` pair in one module-level slot, never a
node's own storage, so no node acquires an instance dictionary. A pass taking it
must also reword the prohibition: `_DeclaredState`'s docstring and `spec/python.md`
§2 forbid memoizing the presentation *on the value*, and a reader will apply that
sentence to this memo unless it is restated as the per-node rule it means.

**Hazards, each concrete and each to be carried forward whole.**

- **A stale entry on a `has_auxiliary` class is reproducible and observable.**
  Three reads leave a memoized mapping that a later auxiliary write does not
  update, so a hit returns a mapping missing the warmed key while a fresh build
  includes it. Because equality compares whole presented mappings, it surfaces as
  a wrong `__eq__` rather than as a slow path. The `has_auxiliary` gate closes it
  completely: auxiliary state is the only thing that can change between two reads
  of a frozen published value.
- **Presentation identity becomes observable.** `v.__dict__ is v.__dict__` is
  always `False` today and sometimes `True` with the memo, so any assertion in the
  Pydantic-floor corpus or the unit suites that depends on freshness will see it.
- **An O(1) residue survives at odd-read sites.** A plain union, `__eq__`, and
  `repr` each read once, leaving one `(instance, mapping)` pair alive — 424 B,
  constant, and healed by the next run. It satisfies the letter of the
  retained-memory rule while holding one arbitrary Typed node alive indefinitely
  after a run finishes, which is a thing to decide deliberately rather than
  discover.
- **Free-threaded builds are reasoned about, not verified.** No free-threaded
  interpreter was available. Eight threads on a GIL build showed no errors and an
  unchanged hit rate, and the `entry[0] is value` identity gate degrades a lost
  race to a miss rather than to a wrong answer — but a real free-threaded run is
  owed before this ships.

**A fourth ingredient that is not free, and is a decision rather than an
optimization.** Returning a plain `dict` instead of `_PresentedState` for
`has_auxiliary=False` classes buys another **1.09x**, and makes an unknown-key
write to `v.__dict__` on such a class **silently evaporate** where today it
refuses loudly: nothing seeds a presentation of such a class from the auxiliary
slot, so `_PresentedState` answers that write with a `TypeError` naming the class
fact rather than absorbing it into a slot no read consults. The rule that every
write path ends as a documented demotion or a loud refusal, and that silently
inert survives nowhere, is what makes this a decision — it may only be taken
explicitly.

**What is already closed, so no later pass re-explores it.** A
`@model_serializer(mode="wrap")` bracket does bracket both reads at every depth,
and is rejected anyway: it costs +394 ns per instance to save roughly 530,
reintroduces the core-schema mechanism this seam exists without, and is silently
displaced by any authored subclass `@model_serializer`. A `model_dump` /
`model_dump_json` override bracket is never entered for a nested instance or for
a `TypeAdapter` entry point. `__pydantic_serializer__` re-entry has the same
reach problem. No lazier or cheaper mapping type helps, because
`cast_into::<PyDict>()` followed by concrete dict C-API access bypasses every
Python-level override; a template `.copy()` plus `update(zip(...))` measures
300 ns against `dict(zip(...))`'s 299.

**The order a pass should take.** The `strict=True` drop first: no behavior change,
no new hazard, nothing to decide. The `plan_of` dictionary next — 1.18x with it,
and no lookup or domain value changes with it either, but not before the
class-lifetime question on it is answered, because a strong dictionary pins every
published class for the life of the process, and a declared class that is
collectable today — its weak references clearing, its finalizers running — would
stop being collectable at all. That is observable behavior a caller can write a
test against rather than an implementation cost. Then the memo behind its `has_auxiliary` gate, with the identity and
residue hazards stated and a free-threaded run taken; and the plain-`dict` question
only behind an explicit decision on silent evaporation.

**Why it is deferred rather than fixed.** The cost it removes is stated at the
seam as a settled trade, so taking it is a revision of the Interface's own
performance statement in two documents and not only an implementation change.
Two of the three ingredients need a decision that outlives them — pinning every
published class in a strong dict, and what a one-entry process-lifetime memo may
hold after a run — and the memo needs an interpreter nobody here has run it on.
Each of those is cheap to answer and expensive to answer wrongly inside a change
whose gates are about representation rather than about serialization speed.

### D-83 — A published value's declared-member read costs a Python frame where an ordinary value's costs a dictionary lookup

*Medium — 4.3x on the read itself, structural, and the price of the retained-byte
reduction rather than a defect in it.* Relates to
`parallax.core.entity._members.Attr.__get__`,
`parallax.core.entity._members.ElementAttr.__get__`,
`parallax.core.entity._instance_state.COMPACT_STATE_SLOT`.

A published value's cost on serialization is stated at the seam and carried by
D-82. This is the same fact from the other side, on the operation the claim was
most careful not to make ordinary values pay for, and it is held here so the
accepted fact and what is known about reducing it cannot drift apart.

**What.** A published node has no instance dictionary at all, so
`object.__getattribute__` finds nothing at the instance and falls through to the
non-data member descriptor, which reads the row off its slot and indexes it. An
ordinary value's storage answers first and the descriptor is never entered.
Measured on CPython 3.14.7 over the `wide` scenario of
`docs/instance-state-baseline.md`, 200,000 repetitions, net of an 11.8 ns
call floor measured the same way:

```text
ordinary member read                                 17.8 ns
published member read                                77.0 ns      4.3x
a Python non-data descriptor returning a constant    26.8 ns
the slot descriptor's own __get__ plus a subscript   28.4 ns
object.__getattribute__(value, slot) plus a subscript 30.4 ns
```

Over the whole canonical mix, and against the *ordinary* arm this entry's subject
is — a published node's member read divided by an ordinary node's — the report
reads 3.22x on CPython 3.14 and 3.34x on 3.13. The same operation against the
*legacy* publication fixture, which is the pair the regression rule is stated
over, reads 3.21x and 3.33x. All four are taken with one shared harness on every arm.

**The floor is the frame, and it is not reachable from Python.** Roughly a third
of the 77 ns is entering a Python-level `__get__` at all — the third line above is
a descriptor whose whole body is `return 1` — and the rest is what the body does,
which is itself two Python-level calls. The one in-Python saving located is
holding the slot's member descriptor rather than naming it through
`object.__getattribute__`, worth about 2 ns of the 77, which is not worth a
second way to reach the row. Nothing else in the body is removable: the index is
already resolved at class creation, the row is already a tuple, and there is no
branch to hoist.

**The ticket foresaw the distinction and measured the wrong half.** COR-111's own
directional probe reads "about 4.5 ns for a direct tuple read, 8.7 ns with a
sentinel identity check, 4.7 ns while ignoring a bitmap, and 9.3 ns with a bitmap
check", and says in the same breath that these are not end-to-end descriptor
benchmarks. They are not: they price the row access inside the frame, and the
frame is four fifths of what a caller pays. What the probe was for still holds —
presence stays off the read, and the bitmap check that would have cost another
4.6 ns is not made — but a reader taking those figures as the read's cost will be
wrong by an order of magnitude.

**What it buys, and who pays it.** The frame is what makes the row the whole of a
published node's state: 51.8% fewer retained bytes on 3.14 and 54.7% on 3.13 over
the canonical mix against the legacy publication fixture, and 56.2% and 59.0%
against an ordinary instance. It is confined to published values — an ordinary value's member
read is a plain Pydantic model's, unchanged and equal to a hand-written twin's,
which is the trade the claim forbids making silently and therefore makes
explicitly. The seam is also what keeps the frame from spreading: giving `Attr` a
`__set__` would turn it into a data descriptor and put this frame on every
ordinary read too, which is why every published write path is closed some other
way.

**The two repairs that would actually move it, neither cheap.** A C accelerator
for the member descriptor removes the frame and nothing else does; it is a build,
a wheel matrix, and a second implementation of the read to keep in step, against a
saving that only published values see. Materializing a published node's storage
removes the frame by removing the representation, which is the whole of what this
claim did. Anything between the two — caching a mapping on the node, or a
per-instance fast path — reintroduces exactly the per-node retained slope
`_instance_state._DeclaredState` forbids and D-82 records the prohibition for.

**Why it is deferred rather than fixed.** It is not unfinished work: it is a
measured consequence of the representation, surfaced for the human review the
measurement contract requires and open until that review returns a decision on it.
The entry exists so that a later pass reading the ratio in the report finds the
decomposition, the two real repairs, and the reason the obvious third one is
forbidden, rather than rediscovering all three.

## Forwarding pointers

Removed entries whose number a live document still cites. One line each; drop a
line once nothing cites it. This section is not an entry list and must never grow
prose.

- **D-38** → [COR-67](https://linear.app/flimflam/issue/COR-67/triage-residual-defects-and-coverage-gaps-surfaced-by-cor-64) P7. Mirror the remaining 15 corpus models.
- **D-40** → [COR-67](https://linear.app/flimflam/issue/COR-67/triage-residual-defects-and-coverage-gaps-surfaced-by-cor-64) P4. Eager `fetchall` at the adapter boundary; port-level streaming is [COR-83](https://linear.app/flimflam/issue/COR-83/stream-deep-fetch-reads-at-fixed-memory).
- **D-44** → [COR-67](https://linear.app/flimflam/issue/COR-67/triage-residual-defects-and-coverage-gaps-surfaced-by-cor-64) P2. Deep-fetch depth beyond two hops.
- **D-45** → [COR-86](https://linear.app/flimflam/issue/COR-86/implement-history-with-includes-execution-and-empty-the-deferred). History-with-includes execution.
- **D-46**, **D-48** → closed by [COR-85](https://linear.app/flimflam/issue/COR-85/report-nodes-whose-stored-state-violates-the-declared-model-instead-of). Stored state violating the declared model; the staging residue is D-72.
- **D-47** → fixed. `reduce_declared_members` preserves member presence at every containment depth, as `python.md` §3 and `core/spec/m-document-codec.md` state.
- **D-51** → [COR-67](https://linear.app/flimflam/issue/COR-67/triage-residual-defects-and-coverage-gaps-surfaced-by-cor-64) P6, item 6d. A defining to-one whose foreign key sits on the target side.
- **D-52** → closed by [COR-51](https://linear.app/flimflam/issue/COR-51/integrate-snapshot-writes-and-remove-legacy-frontend-surfaces). The silent unbinding it describes was already gone: [COR-89](https://linear.app/flimflam/issue/COR-89/let-an-operation-reference-name-a-namespaced-entity-and-migrate-the) made `targets(model)` register canonical spellings unconditionally and every serialized surface emit `identity.canonical`, so no in-tree producer can supply an ambiguous one. What COR-51 added is classification at the external-producer boundary — `unit_work.instructions._entity` and `snapshot.handle._read._metadata` both raise `reference-ambiguous-entity-name` — so a spelling arriving from outside is one refusal naming both candidates rather than a missing observation binding.
- **D-54** → fixed. A subtype's Pydantic field for a member it inherits is the declaring class's own — same default, same requiredness, at every depth — as `python.md` §2's realization-technique paragraph states. Class creation empties the inherited names out of the namespace it hands Pydantic and restores them once the class exists, so Pydantic's own inheritance path supplies each field; the entry's `Tug()` now raises for its missing required members, and a family whose root declares a Value Object occurrence can hydrate a subtype at all, which the undeep-copyable expression made impossible.
- **D-57** → closed by [COR-51](https://linear.app/flimflam/issue/COR-51/integrate-snapshot-writes-and-remove-legacy-frontend-surfaces). `_identity_row` applies `serialize_member`, so all three Entity Row Codec operations carry one form; `python.md` §5 states that uniform contract in place of the asymmetry, and no golden moved, because a primary key is structurally a scalar Attribute that `serialize_member` passes through unchanged.
- **D-58** → closed by [COR-85](https://linear.app/flimflam/issue/COR-85/make-a-models-observable-behavior-independent-of-storage-layout) Phase 4. The holistic decision was taken rather than postponed, and it is neither shape alone: the merged graph keeps graph-local node identity, and the Wire read renders a FINITE value tree by unwinding the requested include tree (`parallax.snapshot.materialize._wire`), so a back-reference terminates because the tree strictly shrinks rather than because a cycle detector fired. Aliasing survives the tree — positions reaching one merged node under one subtree answer the identical frozen object — so the cost this entry accepted in advance (one logical node materializing as distinct objects) is not paid, and `then.graph` grades JSON-renderable values directly. Bounded-memory streaming is the one part left, and [COR-83](https://linear.app/flimflam/issue/COR-83/stream-deep-fetch-reads-at-fixed-memory) carries it: what it revisits is graph-level node uniqueness, not the wire shape this settled.
- **D-60** → closed by this claim, and the module it named is since retired (ADR 0060): `MODULE_SCOPE` carries `parallax.core.execution_lifecycle`, the generated `[tool.importlinter]` block contracts it, and `core/spec/modules.md` carries `m-snapshot-read --> m-execution-lifecycle`. One consequence the entry did not foresee outlived the rename: the module reaches `m-sql`, so mapping the tag to `parallax.snapshot.materialize` would put SQL generation inside the closure of the grant `parallax.snapshot.handle._materializer` holds, dissolving the containment that child scope exists for. The tag therefore maps to `parallax.snapshot._read_result` — the scope that actually names the lifecycle seam — while `parallax.snapshot.materialize` carries the remaining `m-snapshot-read` edges as a support row.
- **D-59** → [COR-95](https://linear.app/flimflam/issue/COR-95/reference-harness-grades-thenexecution-second-witness-for-m-execution). `then.execution` has one grader; `spec/python.md` §1 carries the single-witness limit.
- **D-61** → [COR-95](https://linear.app/flimflam/issue/COR-95/reference-harness-grades-thenexecution-second-witness-for-m-execution). The envelope half: `validate_execution_observation` has no envelope-grading seam, and `core/spec/m-conformance-adapter.md` *Execution provenance* binds the adapter regardless.
- **D-62** → closed by [COR-96](https://linear.app/flimflam/issue/COR-96/decide-what-a-row-returning-wrapper-over-a-deep-fetch-means). The shape is retired rather than answered: an Object Query's Includes and its cap are sibling clauses, so a row-returning wrapper OVER a deep fetch has no spelling to reach execution with, on the typed surface or the neutral one. What remains of the neighbourhood is stated positively — a row-form request naming Include Paths is refused by the shared read gate (`handle.preflight`'s `form` argument), and Includes over a scanned temporal axis stay the `snapshot-history-includes` Deferred Execution Feature. That classification is now two field reads over the canonical query — `includes` is non-empty AND some dimension's Temporal Selection is `history` or `asOfRange` (`handle._features`) — rather than a walk looking for a deep fetch under or over a scan, so no clause can stand between a scan and its own classification.
- **D-63** → [COR-95](https://linear.app/flimflam/issue/COR-95/reference-harness-grades-thenexecution-second-witness-for-m-execution). The round-trip half: the eleven `then.roundTrips` authored on `boundary` and retry-shaped `conflict` cases have only this target's suites as a reader, because the harness runs no `api-conformance` lane and a retry-shaped conflict never reaches its round-trip assertion.
- **D-64** → closed by [COR-85](https://linear.app/flimflam/issue/COR-85/make-a-models-observable-behavior-independent-of-storage-layout). Both Relational Document Layout milestone refusals it named: the grouped-find one is gone, and the case-state one survives as a settled adapter contract stated at `engine._refuse_unaccounted_document_milestone` rather than as deferred work.
- **D-65** → [COR-97](https://linear.app/flimflam/issue/COR-97/give-a-transaction-a-supported-abandon-and-the-execution-log-an-abort). A `rollback: true` step's abort sentinel records a `commit`-phase failure and an unclassified retry verdict, which no oracle reads; `engine._AbortingPort` states the untruth and its bound, and COR-97's `Transaction.abandon()` plus an `aborted` attempt status removes the decorator.
- **D-66** → [COR-99](https://linear.app/flimflam/issue/COR-99/audit-the-compatibility-corpus-against-what-production-would). A keyed temporal write settling against case state a committed materializing predicate write of the same case moved is refused (`engine._refuse_materialized_case_state`, marked by `temporal_state.TemporalShadow.note_materialized_write`): production resolves and plans that write internally and returns neither, so the adapter would issue a zero-row close where a real caller — who could only reach the step by reading — gets a stale write. COR-99 is the systematic pass over adapter/production divergences of that kind and cites this composition as its motivating example; this refusal is the one hand-placed instance of what that audit generalizes.
- **D-68** → closed by [COR-93](https://linear.app/flimflam/issue/COR-93/make-python-conformance-a-thin-adapter-over-the-production). `parallax.conformance` reaches a corpus model through the public `domain_model_from_document` door alone and reads the accepted Metamodel's own vocabulary, so no `parallax.descriptor` private import and no `parallax.core._formation_profile` reach survives; `ACCEPTED_CONFORMANCE_PRIVATE_REACHES` ends at three `parallax.core.entity` entries that `spec/python.md` §7 states as a rebuttal rather than an exemption. One question the accepted model cannot answer survives the conversion, and it is not a model question: the order a document declared its Entities in, which `m-case-format` makes load-bearing for a case naming no target and which `conformance.models.declared_entity_spellings` therefore reads off the decoded document. This target pins that order in a unit assertion of its own (`tests/unit/test_corpus_models.py`), but no compatibility case distinguishes it from the accepted model's canonical order: exactly one case resolves the convention over a model whose two orders disagree (`m-predicate-048`), and it is refused by the same rule under either root. Which order `m-case-format` means is therefore ungated across targets, and [COR-99](https://linear.app/flimflam/issue/COR-99/audit-the-compatibility-corpus-against-what-production-would) carries it.
- **D-76** → closed by the decision it asked for. An invalid scenario `mutate` `set` is a **case-authoring failure**: `core/spec/m-case-format.md` states it in the register the bare write row already uses, and the corpus's own model-aware validation (`reference_harness.schema_validate._validate_scenario_edit`, run by `just core-check-schemas`) refuses such a case before either executor sees it. Undeclarability is the design rather than a gap — an edit refusal is deliberately not an `expectError` member — so what the entry called a divergence is now one rule with one enforcement point, and the Python lane's own verdict (`engine._judged_assignments`) is a restatement rather than the portability mechanism.
- **D-71** → fixed. `_row_codec._assignment_matches_original` compares both sides whole and presence-preserving — with the nested-`many` exception, which has no absence to preserve and reads as the empty collection on both sides — as `python.md`'s *Provenance comparison* paragraph and `docs/adr/0003` state.
- **D-73** → fixed. A Wire read publishes what one materialization carries — the members the stored document held, plus and minus what `m-snapshot-read` fixes at each — so both representations observe one value; `core/spec/m-snapshot-read.md` *What a materialized value carries* states the read contract and `python.md` §4 the published node.

### D-84 — A streamed run reports no emissions, because a Snapshot Stream publishes no Database Call activity

*Medium — the conformance envelope a streamed case gets back is one observation
short of what the contract states, and nothing but the corpus runner's own
execution covers the gap.* Relates to `parallax.conformance.engine.run_stream_case`,
`parallax.conformance.engine._DeliveredCalls`, `parallax.snapshot.handle._stream`.

**What.** `core/spec/m-conformance-adapter.md` *Streamed reads* says a streamed
run reports its `emissions` off the Database Calls the delivery publishes, and
never off the database port — a port carries the driver's own statement text
rather than the lowered statement a Database Call borrows, and recovering one
from the other reports a statement nobody ran (pinned by
`tests/unit/test_lifecycle_observation.py::test_no_conformance_module_recovers_a_statement_from_driver_text`).
A Snapshot Stream publishes no such activity: its pages run through the executor
with an inert Database Call scope, so `LifecycleObservation` records nothing for
one. `run_stream_case` therefore reports an EMPTY `emissions` list, and the one
number the run envelope still owes — `observations.roundTrips`, which the
adapter schema requires — is counted at the port by `_DeliveredCalls`, which
reads no statement at all.

The statements a streamed case authors are still graded twice against a real
database: the reference harness executes every authored page itself and derives
the page partition from the result (`core-check` plus the compatibility sweep),
and `tests/compatibility/test_run_sweep.py` compares what the delivery executed
at its own port seam against the goldens translated OUTWARD through
`Dialect.to_driver_sql`, never recovered inward. What is missing is the envelope
observation, which is what a second language target would be held to.

**Why it is deferred rather than fixed.** The repair is the Snapshot Stream's own
Execution Lifecycle producer: the Root Execution, the Stream Batch per page, and
the real Database Call scope in place of the inert one. That is a core contract
(`core/spec/m-execution-lifecycle.md` states what a Stream Batch spans and when
it completes) with no producer anywhere yet, and it is owned in full by
[COR-83](https://linear.app/flimflam/issue/COR-83/stream-deep-fetch-reads-at-fixed-memory).
Once a delivery publishes those events, `run_stream_case` reads its emissions and
round trips off them like every other lane, `_DeliveredCalls` is deleted, and the
run sweep's own port seam goes with it.

## History

Per-ticket files under `.humanlayer/tasks/` hold the full text of entries this
file no longer carries, each named for the ticket that closed them. Consult them
when a commit message or document cites a D-number this file does not hold:

- `.humanlayer/tasks/cor-3-build-python-slice/05-deferred-ledger.md` — D-1 … D-37.
- `.humanlayer/tasks/cor-47-build-python-declarations/09-deferred-ledger.md` — D-36 … D-48.
- `.humanlayer/tasks/cor-85-typed-and-wire-apis/19-deferred-ledger.md` — D-71, D-73.
