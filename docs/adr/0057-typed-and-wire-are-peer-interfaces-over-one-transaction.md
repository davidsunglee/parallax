# Typed and Wire are peer interfaces over one transaction

Typed and Wire reads and writes are peer interfaces over the same handle and,
inside a transaction, the same Unit Work, observation ledger, locking, and
transient Execution Lifecycle. Each keyed write takes an observed source from
its own
representation, while writes from both representations coalesce and flush
through the shared transaction machinery. A Wire Entity returned by a Parallax
Wire read may carry an opaque Source Hint identifying its exact concrete Entity
and original Object Key and, when the Entity requires write evidence, selecting
its observed state. The hint is not itself a Write Observation or public
authority; it selects the authentic source's privately retained evidence, which
the writing Unit Work validates and adopts. Observed State Keys remain internal.
Every existing-object keyed write requires
an authentic Parallax read source. Under the source Entity's effective Locking strategy the source must have
participated in the current transaction: that read acquired the shared row lock
which licenses the otherwise ungated write, and a `db.wire.find` result cannot
prove current lock ownership. Under its effective Optimistic strategy, an authentic versioned or
temporal source from `db.wire.find` may contribute its retained version or
milestone evidence without an in-transaction read; the emitted database gate
detects an intervening write. Optimistic mode requests no shared-lock SQL for
any find, including a participating transaction find. An unversioned
Non-Temporal source has no such gate and gains no detached-source exception.
This permits mixed and classless flows without public provenance metadata or
representation-specific transaction authority.

A Wire read result is deeply frozen: ordinary mutation of its mapping or any
nested dictionary or list raises `TypeError`. Python preserves ordinary
dictionary/list structural equality and unhashability; freezing does not invent
hash semantics. The write verb's separate changes mapping is therefore the sole
assignment input, and the frozen source remains a reliable statement of the
values that were observed. Immutable copy operations may return the same hinted
value. Converting or serializing it produces ordinary
Wire data without the Source Hint; that data may still be used for inserts,
changes, predicates, and Object Query input, but not as a keyed write source. A
caller that crosses a serialization boundary rereads the object through
`tx.wire.find` before updating, deleting, or terminating it.

Every Wire verb snapshots its complete required caller-owned input at the call
boundary. Insert data, explicit changes, predicate targets, and temporal bounds
are recursively captured into immutable buffered intent. A keyed source is
already deeply frozen; the verb captures its identity, resolved evidence, and
original values only for explicitly changed members. Later mutation of any
caller-owned mapping or nested collection cannot change what flush executes.
This work is proportional to authored write input and does not duplicate a Wire
read result.

Wire verb validation has one observable phase order. It first validates the
verb and target shape, source key and required version, temporal bounds, member
names and values, and assignment legality, then rejects an ordinary or
reconstructed mapping where a frozen Parallax Wire source is required. Only a
statically valid request may resolve the source Entity's Effective Concurrency
Strategy and its evidence: current-transaction read participation under Locking
or authentic retained version/milestone evidence under Optimistic. It then enforces unavailability,
consumption, or an existing claim. A successfully resolved request is
snapshotted and buffered. Thus malformed input has the same refusal regardless
of evidence state. Typed `edit()` already enforces its assignment legality
before a transaction verb receives the value.

Wire Entity mappings expose no temporal milestone coordinate. The frozen
source's private Source Hint selects the exact temporal state. Losing that hint
loses keyed-source status rather than starting an Object Key candidate search.
Temporal bounds authored as verb arguments remain ordinary static write input
and do not identify source provenance.

Observation eligibility follows source liveness rather than transaction
lifetime. Each independently writable materialized Entity node and each
buffered write may retain a claim on its exact observation; the ledger does not
keep released source values alive merely to preserve write authority. Several
observed states of one object may coexist, and a later read never upgrades an
older source's evidence. A successful flush consumes the observations used by
surviving writes, while a write coalesced away before DML consumes none. This
bounds retained read evidence while the representation-specific source object
selects the evidence its corresponding keyed verb validates and adopts.
An `InvalidData` wrapper never claims an observation. When `data=None`, no
writable node exists and no eligible evidence is retained, regardless of the
diagnostic Object Key, version, or Edge. When data hydrates, its independently
writable Entity nodes claim observations exactly as ordinary read results do.

Several compatible updates may claim the same observed state before one flush.
The planner coalesces them into one surviving write when their temporal bounds
are identical, merging sparse assignments in authored order so the later value
wins for a repeated member. This is representation-independent: Typed, Wire,
and mixed calls use the same authored-order merge. The surviving write carries
and eventually consumes the observation once. Effective-change elimination runs
after this merge. A winning Typed assignment is compared with its Change Record
original, and a winning Wire assignment is compared with the corresponding
value in its frozen observed source. Those two originals are one observed value:
a Wire read publishes what one materialization carries, position for position
with a hydrated Typed value — the members the stored document held, plus and
minus what `m-snapshot-read` fixes at each — so the peer interfaces cannot reach
different verdicts about one authored value by observing the same row
differently. A
wholly eliminated Typed, Wire, or mixed intent emits no DML and consumes no
observation.

An incompatible second intent against an observation already claimed by a
buffered write is refused at that second verb as
`write-evidence-already-claimed`. In particular, temporal updates with
different bounds do not acquire implicit interval-composition semantics. An
identical destructive intent deduplicates instead. A caller needing sequential
temporal effects must let a participating read flush the first write, read the
state relevant to the second interval, and author the second write from that
fresh observation.

A later destructive intent does coalesce when it addresses the exact same state
and region: Non-Temporal update-then-delete becomes one delete, and temporal
update-then-terminate with identical bounds becomes one terminate. The reverse
order is incompatible because assignment after destruction would require
resurrection semantics. The rules apply identically to Typed, Wire, and mixed
ingress.

An observation selected into a Materialized Write Group is already claimed by
that predicate write. A later keyed write overlapping the group raises
`write-evidence-already-claimed`, while a non-overlapping key is accepted;
keyed intent is not merged into the compact group. In the reverse order, the
predicate write's participating resolution force-flushes the keyed write and
selects fresh state. Typed, Wire, and mixed keyed calls share this behavior.

Write-evidence failures use one representation-independent closed
classification. `write-evidence-unavailable` means that no eligible
current-transaction participation or state-specific observation can authorize
the requested write, and `write-evidence-consumed` means that an exact frozen
Wire or Typed source names evidence already used by a successful flush.
`write-evidence-already-claimed` means that a buffered write already depends on
the exact evidence and the new intent neither coalesces nor deduplicates safely.
Each failure identifies the attempted visible Object Key but exposes neither the
Source Hint nor the Observed State Key. Evidence resolution and every such
refusal occur synchronously at the keyed write verb, before buffering or
database access. A database change discovered after buffering remains the
existing optimistic-lock or temporal flush conflict; it is not reclassified as
a write-evidence failure.

The ledger key is the closed internal `ObservedStateKey` union: an Object Key
plus the observed positive version for a versioned Non-Temporal state, or an
Object Key plus the milestone Edge for a temporal state. Object Key remains
state-independent because coalescing, cancellation, buffered-insert recognition,
and object identity address the object across states. This replaces the earlier
`ObservationKey` shape, whose absent milestone arm collapsed every observed
version of one object into one slot.

Python realizes the peer interface as `db.find` / `tx.find` for Typed work and
`db.wire.find` / `tx.wire.find` plus `tx.wire` verbs for Wire work. The Wire
namespace is a lightweight view, not a connection or transaction mode. This was
chosen over partitioned transaction protocols, a runtime `format=` argument,
overloaded Typed verbs, public observation values, flat `wire_*` methods, and a
general write-instruction method because the representation varies per call
while transaction semantics do not. Insert verbs take an explicit Entity name
and ordinary Wire data. Existing-object update, delete, and terminate verbs take
only a frozen observed Wire source; they have no explicit-Entity overload for an
ordinary mapping.

Python keeps `WireValue` as a structural alias for the ordinary dictionary/list
Wire shape and exposes `WireEntity` as a non-constructible, read-only nominal
`Mapping[str, WireValue]`. The private frozen runtime carrier inherits from both
`dict` and `WireEntity`, preserving ordinary dictionary behavior and JSON
compatibility while letting type checkers distinguish read entity nodes from
ordinary mappings. Inserts, changes, predicates, and Object Queries continue to
accept structural mappings. Nominal identity cannot prove that a source belongs
to the current transaction, so keyed Wire verbs still validate locking-mode
participation or optimistic-mode retained evidence dynamically. Ordinary
mappings are rejected with `WriteInstructionError`. The structural `WireValue`
alias does not grow nominal frozen container types solely to describe deep
immutability. Standard JSON serialization continues to see ordinary objects and
arrays; decoding produces plain data without keyed-source status.
