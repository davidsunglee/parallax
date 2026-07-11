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
corpus-coverage annotations. The two surfaces coexist with distinct roles:
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
(`edge_of(node)`, whose `.processing` field is the milestone's `in_z`) at
render time, then re-fetches with each declared axis pinned at the
transported edge
(`as_of(processing=edge.processing, business=edge.business)` for a
bitemporal entity) inside an optimistic transaction, where the observed
`in_z` gate — joined by the business discriminator when the key's current
rows share an `in_z` — rejects concurrent changes and targets exactly the
displayed rectangle. Weaker transports fail — the LATEST sentinel re-resolves to whatever
milestone is current at replay time, and a wall-clock instant is racy because
processing instants order by assignment, not commit. Edge transport is
Reladomo's own mechanism (a detached copy carries its milestone `IN_Z`; the
merge-back gate binds the carried value) translated to a slice without
detached objects.
