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
locations and are canonically ordered by location then code, so a report never
depends on caller keyword order. The framework's assignment rules never
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
