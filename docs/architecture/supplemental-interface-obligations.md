# Supplemental Interface Obligations

Status: provisional and non-normative. Parallax specifications remain authoritative.

This note catalogues behaviors the compatibility corpus **structurally cannot
state**, so that a second language implementation does not have to rediscover
each one by reasoning its way to the same dead end. Every entry here is real
shipped behavior; what it lacks is a case, and the reason it lacks a case is a
property of the case format, the conformance adapter contract, or the reference
harness — never an authoring gap someone forgot to fill.

## What this is for

[COR-103](https://linear.app/flimflam/issue/COR-103) is the consumer. It makes
this catalogue binding: a **Supplemental Interface Obligations** registry as a
numbered section of `core/spec/language-testing.md` — which already owns *what a
test proves* and defines `unit/` as the Internal-behavior surface — with
applicability reusing the language-spec template's existing
`**(decide and record — When claimed: <module>)**` grammar, and
`core-check-language-spec` verifying that a completed language spec answers every
obligation whose module tag is in its claimed set. The precedent for that
enforcement is §6's coverage-partition assertion (exercised union reasoned-skipped
equals the active slice), extended from cases to behaviors that have no case.

This note deliberately stops short of that. It changes no contract, adds no gate,
and grades nothing. It is the inventory COR-103 turns into a rule.

Obligations do **not** belong in the `m-*.md` module specs (`core/AGENTS.md`
forbids those from naming slices or claim status, and scattering them defeats
enumeration), nor in `slices.md` (slice-to-module relationships only), nor as a
case field (most obligations have no case).

## How to read an entry

Each entry carries five things:

- **Id** — stable. Never reused, never renumbered. A retired obligation keeps its
  id and says what retired it, and so does one withdrawn because its reason did
  not survive inspection — an entry whose behavior the corpus turns out to be
  able to state is not an obligation, and reusing its number would hide that it
  was ever claimed.
- **Module tag** — the `core/spec/modules.md` tag that drives applicability. An
  implementation owes the obligation when that module is in its claimed
  `capabilities.modules` set.
- **Supplements** — the compatibility case whose claim the obligation completes,
  or *standalone* where no case is nearby.
- **Why the corpus cannot state it** — the structural reason, stated so a reader
  can check it rather than take it on trust.
- **Required assertion** — what an implementation must prove, in **behavioral**
  terms only. Never "a test named X exists" and never a named function: verifying
  that a particular test exists is not portable across languages, and the point of
  an obligation is the observable, not the fixture.

A **withdrawn** entry obliges nothing, so it carries a different and shorter set —
its id, its module tag, **Withdrawn**, and **Residue** — and never a Supplements,
a structural reason, or a Required assertion. A consumer reads the two kinds apart
by the assertion: an entry with none is a tombstone and is owed by no
implementation. The module tag stays so the withdrawal is visible from the module
its claim was filed under.

- **Withdrawn** — the reason the entry stated, and why that reason did not survive
  inspection.
- **Residue** — what is true nonetheless and where it now lives, or *none* where
  nothing survived the withdrawal.

Three structural reasons recur, and the entries name them by these labels.

**The action-step lane.** The corpus's one shape for a refusal over a live client
value is the `api-conformance` keyed-write action step (`m-case-format` *Keyed
write action steps*). Its `value` token is drawn from a closed provenance
partition (`unmanaged` / `thisSource` / `anotherSource`), it carries no golden SQL,
it declares `roundTrips: 0`, and the suite verifies that zero as *the absence of
any durable effect*. A refusal that turns on a write the same unit of work already
admitted therefore cannot be expressed there: the first write buffers something,
which the lane's zero denies.

**The instruction oracle.** A write case's goldens are graded by a pure
re-lowering over write **instructions**. A restoration is the *absence* of an
assignment — a fact about the source value the caller holds, not about any
instruction — so an entry that states it is indistinguishable from an entry that
assigns the restored value, which is a different case.

**The single-grader observable.** A case is graded by two independent
implementations. Where the reference harness does not implement a contract, a case
turning on that contract can only be graded on one side, which is not what a
compatibility case is.

---

## Write claims and write evidence

### SIO-001 — A second temporal write of one observed state with different authored bounds is refused

- **Module tag**: `m-unit-work`
- **Supplements**: `m-unit-work-021` (the admitted coalescing arm of the same rule)
- **Why the corpus cannot state it**: the action-step lane. The refusal is
  synchronous at the second verb and turns on the first write already sitting in
  the buffer.
- **Required assertion**: within one unit of work, two keyed temporal updates of
  the same observed state whose authored Valid-Time bounds differ — as authored,
  not as resolved — are not combined. The second verb raises the write-evidence
  refusal for an already-claimed state, synchronously, before it buffers anything
  and before any statement reaches the database. Equal authored bounds coalesce
  instead, which is the case's own arm.

### SIO-002 — An assignment after a destruction of the same observed state is refused

- **Module tag**: `m-unit-work`
- **Supplements**: `m-unit-work-022` (the admitted direction: a destruction
  supersedes assignments buffered before it)
- **Why the corpus cannot state it**: the action-step lane.
- **Required assertion**: within one unit of work, a keyed update of an observed
  state that a keyed delete or terminate of the same state has already claimed
  raises the already-claimed write-evidence refusal at the update verb. The
  reverse order is admitted and collapses to the destructive intent, so the pair
  is directional rather than symmetric.

### SIO-003 — A keyed write of a state a predicate write already selected is refused

- **Module tag**: `m-unit-work`
- **Supplements**: *standalone*
- **Why the corpus cannot state it**: **two** structural reasons at once. The
  refusal needs the action-step lane, and the arrangement additionally needs a
  predicate-selected write inside a `uow` group, which the scenario group runner
  cannot express — its write step reads a buffered **keyed** entry list, so a
  predicate-shaped entry has no route into a group.
- **Required assertion**: a Materialized Write Group claims every state its
  predicate selected. A later keyed write of one of those states raises the
  already-claimed write-evidence refusal at that verb, without the group being
  reindexed or mutated. The claim is one shared selection intent for the whole
  group, so *every* keyed intent against a selected state is incompatible with it,
  whatever that intent is.

### SIO-004 — An unversioned Non-Temporal write after a destruction of the same object is refused

- **Module tag**: `m-opt-lock`
- **Supplements**: `m-unit-work-026`, `m-unit-work-027` (the two wire-observable
  arms of object-scoped claiming)
- **Why the corpus cannot state it**: the action-step lane.
- **Required assertion**: an unversioned Non-Temporal keyed write is claimed by
  its **Object Key**, not by an observed state, because such a row observes none.
  A keyed update of an object this unit of work has already claimed destructively
  therefore raises the same already-claimed write-evidence refusal a versioned
  target raises for its state. Claim scope is derived totally from the Entity's
  Optimistic Key and the instruction kind; the absence of an observation is never
  the input that selects this arm.

### SIO-005 — A keyed write of a state a predicate write did *not* select is admitted

- **Module tag**: `m-unit-work`
- **Supplements**: *standalone* (the non-overlap partner of SIO-003)
- **Why the corpus cannot state it**: the arrangement needs a predicate-selected
  write inside a `uow` group, which the scenario group runner cannot express.
- **Required assertion**: a Materialized Write Group's claim reaches exactly the
  states its predicate selected. A keyed write of a different object of the same
  Entity in the same unit of work is admitted and flushes normally. The reverse
  order needs no claim at all, because the predicate write's resolving read
  force-flushes the buffer first and therefore selects state no pending intent
  still holds.

### SIO-006 — An edit chain that restores its own original emits no DML across two verbs

- **Module tag**: `m-unit-work`
- **Supplements**: `m-unit-work-020` (the single-verb net-zero arm)
- **Why the corpus cannot state it**: the instruction oracle. `100 -> 125 -> 100`
  authored as two write entries is two ordinary assignments that merge to `100`,
  which is a different claim; the corpus has no way to say *this verb restored
  what the previous one changed*.
- **Required assertion**: two keyed updates of one observed state, where the
  second sets a member back to the value the source published, emit **no**
  statement at all — not an update writing the intermediate value, and not an
  update writing the original. A restoration is the caller's last word on that
  member and cancels a pending assignment of the same member at the same claim
  scope. It holds for a wholly Typed chain, a wholly Wire chain, and a mixed one,
  because both representations share one buffer.

### SIO-007 — The restoration rule holds at object scope for an unversioned Non-Temporal target

- **Module tag**: `m-opt-lock`
- **Supplements**: *standalone* (the object-scoped partner of SIO-006)
- **Why the corpus cannot state it**: the instruction oracle, exactly as SIO-006.
- **Required assertion**: the same `100 -> 125 -> 100` chain against an
  unversioned Non-Temporal target emits nothing. The cancellation is read at
  whichever claim scope the write takes, so an object-scoped restoration cancels
  an object-scoped assignment just as a state-scoped one does. Absence of an
  observed state changes the scope, never the rule.

### SIO-008 — A zero-row write under a non-conflict classification is not retried

- **Module tag**: `m-auto-retry`
- **Supplements**: `m-execution-log-004` (which grades the zero-row enforcement
  shape but not the retry verdict)
- **Why the corpus cannot state it**: the state is unreachable through public
  verbs. A zero-row write in these classes requires a row to have been deleted
  while the participating read that licenses the write holds its shared row lock —
  which correct locking makes unreachable in any client. The cases that arranged
  it out of band were retired with the conformance write bridge.
- **Required assertion**: a keyed write that affects zero rows classifies as
  **non-retriable** where its target's Effective Concurrency Strategy is Locking
  (a stale write) and where the target is unversioned (a missing target), and the
  bounded retry loop does **not** re-run the transaction body for either. Both
  classes sit outside the loop's caught set, so no opt-in flag and no caller
  extension of the retriable set can reach them. A retry loop over these is the
  genuinely bad failure mode, which is what the assertion protects against.

### SIO-009 — A collapsed multi-key delete cannot come up short

- **Module tag**: `m-batch-write`
- **Supplements**: *standalone* (the claim `m-batch-write-008` carried before it
  was retired)
- **Why the corpus cannot state it**: the same unreachable state as SIO-008 — the
  shortfall needs a row to vanish under a held shared read lock.
- **Required assertion**: a batch that collapses several single-row deletes into
  one statement carries the **aggregate** affected-row expectation of the rows it
  collapsed, and a shortfall against that aggregate is enforced as a failure
  rather than absorbed. A caller addresses only rows a read answered, so the
  shortfall is unreachable in practice; the enforcement must exist regardless,
  because what makes it unreachable is a guarantee below the write surface.

### SIO-010 — A shared read lock blocks a concurrent writer

- **Module tag**: `m-read-lock`
- **Supplements**: *standalone*
- **Why the corpus cannot state it**: a case asserts **ordering**, not **timing**.
  Blocking is a timing property: the assertion is that a second session's write
  does not proceed *until* the first commits, which no ordered step sequence can
  distinguish from a write that simply happened to run second.
- **Required assertion**: while a transaction holds the shared row lock its
  participating read acquired, a concurrent session's write of that row does not
  complete until the holding transaction ends. This is the guarantee the Locking
  arm's whole evidence model rests on — an ungated close is licensed *only* by
  that lock — and nothing in the corpus asserts it.

---

## Reads, classification, and value spaces

### SIO-011 — A non-hydrating stored-data violation classifies identically under both Storage Layouts

- **Module tag**: `m-snapshot-read`
- **Supplements**: `m-storage-layout-027` / `m-storage-layout-028` (the twin pair,
  which proves the **hydratable** half on both graders)
- **Why the corpus cannot state it**: the single-grader observable. The reference
  harness is a real second implementation of the read contract and it does not
  classify — it raises at its own document codec for a leaf no declared decoding
  admits, and it ignores `then.storedDataIssues` entirely, as an
  adapter-delegated observable. A non-hydrating twin case would therefore be green
  on one grader and red on the other.
- **Required assertion**: a stored state for which no conforming value can be
  produced without invention (one of the five no-invention codes) classifies the
  result root as invalid, carries **no** hydrated root, and reports the identical
  issue set under conventional Columns and under Relational Document Layout. The
  refusal must not be the codec raising; the read must complete and publish the
  classification.

### SIO-012 — A reread inside the writing unit of work still classifies

- **Module tag**: `m-snapshot-read`
- **Supplements**: `m-unit-work-028` (which pins the write settling against
  classified stored data, and the surviving document byte for byte)
- **Why the corpus cannot state it**: three independent reasons, each sufficient.
  A case's stored-data observable is **case-level and graph-only**; the
  conformance adapter fixes a scenario's reports to a closed set that does not
  include it; and the scenario read path ends in the shared publishable refusal,
  which raises on a classified row rather than returning it.
- **Required assertion**: after a write settles against a classified row and a
  read-your-own-writes flush puts it on the wire, a **reread of the same row in
  the same unit of work** reports the same classification alongside the written
  value. The residual risk this covers, which composition of a separate write case
  and a separate read case cannot, is a reread served from write-path state rather
  than from storage.

### SIO-013 — A timestamp outside the canonical Wire range is refused at every door

- **Module tag**: `m-core`
- **Supplements**: *standalone*
- **Why the corpus cannot state it**: the single-grader observable. The value
  space is bounded by what the canonical Wire spelling carries
  (`0001-01-01T00:00:00.000000Z` through `9999-12-31T23:59:59.999999Z`), and a
  twin case would require the reference harness to adopt the identical range
  before it could grade either arm.
- **Required assertion**: membership in the `timestamp` value space is a **total**
  predicate, and a host instant outside that range is not a member however the
  host spells it — awareness alone is not membership, and a zone offset beyond a
  day answers false rather than raising out of the check. Every write validator
  refuses such a value statically, at both representations and at keyed, insert,
  and predicate ingresses alike; and both codec legs refuse it, so neither a write
  nor a read of a stored document can overflow the encoder. One narrowing closes
  the ingress and both encoder legs together, because `m-wire` gives every value
  of a declared type exactly one Wire Value and admitting a value it cannot spell
  is what opens the gap.

### SIO-014 — Withdrawn: one Concurrency Preference resolving two ways is authorable

- **Module tag**: `m-opt-lock`
- **Withdrawn**: its stated reason was that no corpus model declares the shape —
  a versioned root related to an unversioned target in one read. That is an
  authoring gap, not a structural limit: the shape is perfectly authorable, and
  what it costs is a descriptor, its fixtures, and regenerated storage and
  table-layout baselines. An obligation records what the corpus *cannot* say, so
  work it merely has not done yet does not belong here.
- **Residue**: the gap is open and tracked as `D-74` in the Python target's
  deferred-work ledger, which names the corpus as its owner.

---

## Value Object writes and the copy verb

### SIO-015 — A Value Object's copy verb judges every assignment

- **Module tag**: `m-value-object`
- **Supplements**: *standalone*
- **Why the corpus cannot state it**: the copy verb is an **in-memory authoring
  door**. It produces a value; it issues no statement, reaches no database, and
  publishes no observable a case shape has. A case can only see what the resulting
  value stores once it is written, which is a different claim.
- **Required assertion**: deriving a copy of a Value Object by naming the members
  to change returns a validated value carrying every member the receiver
  **populates** and the caller did not name. The receiver's populated set is what
  carries forward, so a member the receiver never populated stays unpopulated
  rather than becoming an explicit null — the round trip that occurrence
  replacement rests on depends on it. Every named member is judged by the same
  assignment rules the model's other assignment surfaces use, all violations are
  reported together rather than the first, and a dotted authored name is refused
  as a nested path rather than as an unknown member, because there is no sparse
  write beneath an occurrence through any door. Naming **no** member is legal and
  answers a value equal to the receiver under the receiver's own populated set:
  the verb is total over its argument list rather than a request that must change
  something, so a caller deriving a copy from a computed set of changes needs no
  empty-set special case and gets no refusal for one.

### SIO-016 — Every inherited copy door on a model class is sealed

- **Module tag**: `m-value-object`
- **Supplements**: *standalone*
- **Why the corpus cannot state it**: the doors are **host-language inheritance**.
  What they are is a property of the language's object model, so there is nothing
  language-neutral for a case to name; what they must not do is produce an
  unjudged value, which again never reaches a statement.
- **Required assertion**: every copy path a model class inherits from its host
  runtime, on an Entity Class and on a Value Object Class alike, refuses with the
  framework's own edit refusal and creates **no value**. The concern is a
  validation bypass, so the seal must hold with and without an update payload: a
  door that copies unchanged is still a door that returns a value the framework
  did not judge, one write away from being stored. The copy verb's own name is
  reserved on both class kinds for the same reason — a class that declares a
  member of that name has no way left to derive a copy.

### SIO-017 — Every refusal code the copy verb declares is reachable

- **Module tag**: `m-value-object`
- **Supplements**: *standalone*
- **Why the corpus cannot state it**: closure over a **refusal vocabulary** is a
  property of a surface, not of any one input, so no case observes it. A case
  witnesses one refusal; nothing in the corpus can assert that the set has no
  unreachable member.
- **Required assertion**: the closed refusal vocabulary the copy verb declares is
  partitioned into codes reachable from that surface and codes structurally
  unreachable from it, with the unreachable ones justified by the shape of the
  surface rather than by absence of a test. On a Value Object surface, the codes
  that classify a primary key, a read-only member, a framework-owned member, and a
  relationship member are unreachable because none of those can be declared on a
  Value Object member at all. An implementation must state its own partition and
  keep it honest as the vocabulary changes; a code that becomes unreachable
  without anyone noticing is a rule that silently stopped being enforced.

### SIO-018 — A temporal successor carries forward a declared member the write does not name

- **Module tag**: `m-txtime-write`
- **Supplements**: `m-txtime-write-013` / `m-txtime-write-014` (the temporal twin
  pair, which restates the unchanged members explicitly)
- **Why the corpus cannot state it**: a temporal write-sequence entry states the
  **whole successor row** — a temporal step's row is classified as an opening row
  whatever verb the entry names — so the harness derives the successor from what
  the entry authored and refuses an omission. Carry-forward of a declared member
  the entry omits is therefore unauthorable. Only an *undeclared* key carries
  observably, and witnessing that needs out-of-band seeding.
- **Required assertion**: a keyed temporal update names some members and the
  successor row it opens carries every **declared** member the write did not name,
  at the value the predecessor held. Carry-forward is derived from the retained
  predecessor rather than from what the caller restated, so a caller that names
  one member does not silently blank the rest.

### SIO-019 — A temporal keyed close settles against a milestone the implementation's own read published

- **Module tag**: `m-txtime-write`
- **Supplements**: `m-unit-work-015` (a close settling against the milestone its
  own find observed, graded through a scenario)
- **Why the corpus cannot state it**: a scenario's temporal keyed write cannot be
  compile-eligible, because a close requires the Temporal Observation it addresses
  and gates on, which a scenario supplies only from a read the compile lane cannot
  perform. A write-sequence reconstructs that observation from case state —
  fixtures plus earlier entries — instead. So every temporal write golden in the
  corpus is graded against a milestone the **case** supplied, never one the
  implementation's own read published, except where a scenario forgoes the compile
  lane entirely.
- **Required assertion**: a keyed temporal close resolves the milestone it
  addresses from the **value being written** — that value's own temporal edge —
  rather than from the primary key it carries or from any implicit resolving read.
  A fresh instance and an edited copy of one name no milestone and are refused; a
  value a read of the same unit of work produced names one and closes it. The
  framework issues no resolving read on a keyed write's behalf under either
  Effective Concurrency Strategy.

### SIO-020 — Withdrawn: batch collapse by physical column set is statable per layout

- **Module tag**: `m-batch-write`
- **Withdrawn**: its stated reason was the twin gate, which its own text admitted
  is not a corpus-wide limit. An ordinary single-layout case states the assertion
  directly — `m-batch-write-001` already witnesses the collapse arm — so nothing
  structural stops the corpus from saying it, and an authoring choice inside one
  gate is not an obligation on a second implementation.
- **Residue**: an authoring constraint on twin pairs, recorded so the next
  cross-layout write case does not rediscover it. Batch collapse groups adjacent
  single-row inserts by physical column set, which Relational Document Layout
  makes uniform, so four inserts whose authored members differ emit three
  statements under Columns and one under Document Layout. A twin pair's
  round-trip count is layout-invariant by construction, which is why
  `m-storage-layout-029` / `-030` author one insert per step.

### SIO-021 — A Value Object copy records no provenance

- **Module tag**: `m-value-object`
- **Supplements**: *standalone*
- **Why the corpus cannot state it**: the in-memory authoring door, plus the
  absence of any independent write. A Value Object reaches storage only inside
  its owner's row, and what that row states is decided by the **owner's** own
  provenance record, so no case can distinguish a copy verb that recorded what it
  changed from one that recorded nothing — the owner emits the same statement
  either way.
- **Required assertion**: deriving a copy of a Value Object records nothing about
  what the derivation touched. A Value Object has no identity and is never
  independently written, so it carries no counterpart of the provenance record an
  Entity copy carries, and a copy is indistinguishable from a value constructed
  whole with the same members and the same populated set. The behavioral
  consequence is that occurrence copies contribute no write of their own: an owner
  assigned an occurrence edited away and then back to the value its own read
  published has an empty effective change set and emits no statement, because the
  owner's record is the only provenance in play.
