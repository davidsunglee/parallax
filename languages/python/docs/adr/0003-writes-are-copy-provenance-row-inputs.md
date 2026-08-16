# Writes are copy-provenance row inputs, not predicates plus assignments

Update inputs are edited copies: the entity base overrides `model_copy` so a
copy of a frozen node carries a change record mapping each touched field to
its original (first-touched) value — copies of copies merge records, keeping
the earliest original — and `tx.update` lowers it to the canonical row-shaped
write input: the sparse row (primary key plus the effective change set —
touched fields whose current value differs from the recorded original) for
non-temporal entities, the full row for temporal close-and-chain. Recording
originals rather than a touched-name set is what detects net-zero edit chains
(`100 → 200 → 100` drops out), and an edited copy whose effective change set
is empty issues no DML at all — uniformly for non-temporal and temporal
entities, so a value-identical temporal edit chains no spurious milestone
into the audit history (Reladomo's dated setters likewise refuse to enroll an
equal value). Because Pydantic's
own `model_copy` does not validate `update=` data, the override revalidates
with the same build-time rules as construction (unknown fields rejected,
framework-owned, primary-key, and relationship fields unassignable — only
mapped scalar attributes and value-object members may appear in `update=`,
because a relationship edit has no row lowering in this slice — scalar input
policies applied). A predicate-plus-typed-assignments update API was first designed,
then retracted on the belief that no predicate-shaped write input exists in
the claimed slice — a conclusion drawn from a writeSequence-only corpus
sweep. That retraction over-reached: scenario-shaped cases
(`m-opt-lock-003`/`-004`) carry genuine predicate-selected set-based writes,
so the typed-assignments surface returned as the distinct `_where` verb
family (`update_where`, `delete_where`, `terminate_where`, and the temporal
forms — spec §5), provided in full for API consistency with per-flavor
corpus-coverage annotations. Shipping the full family rather than only the
corpus-covered forms was a deliberate decision, made by a human reviewer with
the speculative-breadth trade-off on the table: API consistency won over a
minimal covered-forms-only surface, and the honesty mechanism for that
breadth is the per-flavor corpus-coverage annotation plus each uncovered
flavor's extension-status note (unit-proven, outside the coverage partition,
a recorded candidate for future corpus additions) — not a narrowed API. The
two surfaces coexist with distinct roles:
copy-provenance for keyed single-object writes, `_where` verbs for
predicate-selected sets, which materialize per-row observations for
versioned and temporal targets.

Immutability is the enabler, not the obstacle: because nodes are frozen, the
copy API is the only mutation idiom, so the change record is complete by
construction — no dirty flags, no proxies. The optimistic close still gates on
the version analogue the unit of work observed via a prior transaction-scoped
read (never an implicit write-path read — an unobserved keyed write raises);
gating
on the snapshot's own coordinates (offline-edit conflict detection) remains
managed-pole merge-back semantics and is deliberately not pulled into this
slice. The stale-web-edit workflow needs no such gate — provided the
observation coordinate is transported, not reconstructed: the service
captures the displayed milestone's edge on every declared axis
(`edge_of(node)`, whose strict `.transaction_time` accessor yields the milestone's
`in_z` as a plain `datetime`) at render time, then re-fetches with each
declared axis pinned at the transported edge
(`as_of(transaction_time=edge.transaction_time, valid_time=edge.valid_time)` for a
bitemporal entity) inside an optimistic transaction, where the close's own
address targets exactly the displayed rectangle and the observed `in_z` gate
rejects concurrent changes. Weaker transports fail — the LATEST sentinel re-resolves to whatever
milestone is current at replay time, and a wall-clock instant is racy because
Transaction-Time instants order by assignment, not commit. Edge transport is
Reladomo's own mechanism (a detached copy carries its milestone `IN_Z`; the
merge-back gate binds the carried value) translated to a slice without
detached objects.

## Amendment (2026-08, COR-63): the copy verb is `edit`, and one codec owns the row

The decision above is unchanged — update inputs are edited copies carrying a
change record, and recording originals is what detects a net-zero chain. What
this amendment replaces is the mechanism named throughout it.

`Entity.edit(**changes)` is the copy verb. Every inherited Pydantic copy path —
`model_copy`, `copy`, `__copy__`, `__deepcopy__` — is actively refused as
`EditError(edit-use-edit)` and creates no value, with or without `update=`.
Overriding `model_copy` to validate was the wrong shape for the same reason
Pydantic's own version was: a method whose name promises a plain copy is not
where the framework's authoring rules belong, and leaving any inherited copy
path reachable leaves a way to produce a provenance-less value that fails much
later and elsewhere. `edit` is the object-copy verb; `update` remains the
transaction persistence verb.

One `EditError(ValueError)` covers both authoring surfaces — `edit(...)` and a
predicate write's `Attr.set(...)` — because the assignment rules are one set,
stated once in the shared judgement. A predicate-selected assignment is an edit
expressed over a predicate rather than over a value, so a second class would
give one rule family two names and two chances to drift. `ModelCopyError` and
`ProvenanceError` are deleted rather than renamed, and the closed code set
distinguishes the surfaces where they genuinely differ.

`EditError` reports every violation rather than the first. Core ADR 0001 already
requires a validation error to accumulate structured issues, and the edit
surface is where that matters most: the normal idiom is a payload, so an
application mapping a form into `edit(**payload)` needs every invalid field at
once or it will reimplement the framework's rules to pre-validate. Each member
contributes at most one violation — its own first verdict in the judgement's
settled order — and every member is examined; violations carry structured
locations and are canonically ordered by location, then code, then member name
— the third term because two names that reach no member share one location and
one code — so a report never depends on caller keyword order. The framework's assignment rules never
partially report: every violation of them is in the `EditError`, raised whole
before construction begins. Those are not Pydantic's rules, though — the shared
judgement decides conformance to the declared neutral type, while the validating
constructor decides the language annotation and any invariant an author declared
on top of it. A value that passes the judgement and then fails the constructor
propagates its `ValidationError` unchanged, because re-rendering it as an edit
refusal would launder a coverage defect in the framework's own judgement into a
refusal of developer input.

Row derivation moves behind one model-bound `EntityRowCodec` with `full_row`,
`identity_row`, and `edited_row`. `edited_row` is the composition the write path
already performed by hand — identity plus the canonical effective change set,
and `None` when that set is empty — so the codec names an existing composition
once rather than adding a layer. The module-level `full_row`, `primary_key_row`,
`canonical_row`, `changed_fields`, and `effective_change_set` helpers are
deleted: being model-free, they cannot delegate to a model-bound codec, so they
end rather than thin. Codec misuse is first-party misuse rather than rejected
developer input and raises `EntityRowError(RuntimeError)`; the developer-facing
steering for handing a persistence verb a value with no change record belongs to
that verb, which knows what the developer called.

The provenance semantics carry over unchanged and are now stated rather than
implied. A `one` value compares as a mask over the keys the caller authored, a
`many` value compares as a whole because its elements have no identity, and an
omitted key means un-authored rather than null — the same
explicit-versus-defaulted distinction the serializer already draws. An edit
whose effective change set is empty yields no row at all rather than an
identity-only one, so "nothing to write" has a single representation.

## Amendment (2026-08, COR-88): the transported edge is compared, not replayed as a pin

The decision above is unchanged — the stale-web-edit workflow still needs no
merge-back gate, and it still transports the displayed milestone's edge rather
than reconstructing a coordinate. What this amendment replaces is how the
submit half consumes it.

The submit reads the **current** milestone and compares its Transaction-Time
coordinate against the transported one, refusing the submit with the
application's own error when they differ. Pinning the re-fetch at the
transported coordinate was doing two jobs — selecting the displayed milestone,
and asserting it was still current — and only the second was ever wanted on
that axis. A pin cannot make the assertion, because it selects the displayed
milestone whether or not it is still current. A bitemporal target still pins
Valid Time at the transported coordinate: that pin genuinely selects which
rectangle was displayed, and a finite Valid-Time pin is the writable
retroactive correction.

The consequence for concurrency is that the workflow no longer depends on a
mode. Staleness before the submit read is caught by the comparison; staleness
between the read and the flush is caught by optimistic mode's observed-`in_z`
gate or prevented by locking mode's shared read lock on the compared row.

## Amendment (2026-08, COR-85): the copy verb and its sealed doors hold on both class kinds

The COR-63 amendment above states the copy verb and the sealed doors of an
**Entity** Class. They now hold on a **Value Object** Class identically, and the
extension is what makes the surrounding write contract safe rather than a
convenience.

Assigning a Value Object occurrence replaces its subtree whole under every
Storage Layout, so restating a whole occurrence to change one field is what
deletes the fields the restatement forgets. Deriving the new value from the old
one is the correct spelling, and giving a Value Object the same `edit` verb makes
that spelling also the shortest one. It is the same verb rather than an analogue:
one `EditError`, one closed code set, and the same assignment judgement over the
member's own accepted metadata, reached through the same resolve-judge-rebuild
core. Every inherited copy path is refused on a Value Object Class exactly as on
an Entity Class, closing the same validation bypass on the shape a write actually
stores.

Three things follow from a Value Object having no identity and no Entity, and
they are the whole difference. A violation locates at `ModelRoot`, because a
Value Object Class is a reusable shape rather than a position in a model — the
same class composes into occurrences of many Entities and none of them owns its
members — so no `EntityLocation` would be honest; `member_name` and the message
still name the member under its class. Four codes are structurally unreachable
from this surface, because a primary key, a read-only mark, a framework-owned
designation, and a relationship cannot be declared on a Value Object member at
all. And the copy restores the receiver's **populated** set plus the named
members, rather than marking every passed member populated the way the Entity
verb does: a Value Object's document is serialized by that set, so expanding it
would fabricate nulls for members storage never held and break the round trip
replacement rests on.

The verb's own name is consequently reserved on **both** class kinds, joining the
prefix and namespace reservations that already were. A Value Object Class
declaring a member of that name would install an attribute descriptor over the
verb and leave the class with no way to derive a copy at all.

## Amendment (2026-08, COR-85): an occurrence compares whole, not as a mask

The provenance-semantics paragraph above records that "a `one` value compares as
a mask over the keys the caller authored".

**Superseding decision:** an occurrence compares as a **whole** at either
cardinality, presence preserved on both sides. A declared member the authored
value omits is a difference like any other, so the edit is effective and a row is
derived.

The mask was written when assigning an occurrence patched the members it named,
where an omitted member genuinely was un-authored and unaffected. An assignment
now replaces the occurrence's subtree whole under every Storage Layout, so an
omitted member is one the write **removes** — and eliminating that write as a
net-zero edit preserved state the author's own value says is gone. Against a
stored `{street: "A", city: "Oslo"}`, `edit(profile=Profile(street="A"))` wrote
nothing and left `city` standing, while `edit(profile=Profile(street="B"))` wrote
and dropped it: one value's fate turned on whether some other member changed.

The `many` rule is unchanged, and the two cardinalities now answer one rule
rather than two. What the elimination still ignores is a key **no member
declares**: neither side of this comparison can hold one, so an occurrence
differing only there is equal and its write is eliminated, exactly as
`m-unit-work` states for every other comparison of an assigned member with its
persisted value.

The rule is a peer-interface obligation as much as a codec one. The Wire keyed
verb computes its own effective change set against the source its read published
and has always compared whole decoded values, so the mask was one authored value
getting two answers from two peer interfaces (ADR 0057).
