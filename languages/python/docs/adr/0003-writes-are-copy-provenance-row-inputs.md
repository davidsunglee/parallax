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
policies applied). A predicate-plus-typed-assignments update API
(`tx.update(Entity.where(...), Entity.attr.set(v))`) was designed and then
retracted once the corpus showed every canonical write input is row-shaped
and no predicate-shaped write input exists in the claimed slice; "set-based
write" in core describes how the unit of work flushes buffered rows, not a
public predicate-update surface.

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
captures the displayed milestone's edge (`edge_of(node).processing`, its
`in_z`) at render time, then re-fetches `as_of` that edge inside an
optimistic transaction, where the observed `in_z` gate rejects concurrent
changes. Weaker transports fail — the LATEST sentinel re-resolves to whatever
milestone is current at replay time, and a wall-clock instant is racy because
processing instants order by assignment, not commit. Edge transport is
Reladomo's own mechanism (a detached copy carries its milestone `IN_Z`; the
merge-back gate binds the carried value) translated to a slice without
detached objects.
