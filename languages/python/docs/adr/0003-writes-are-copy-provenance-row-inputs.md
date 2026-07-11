# Writes are copy-provenance row inputs, not predicates plus assignments

Update inputs are edited copies: the entity base overrides `model_copy` so a
copy of a frozen node carries a change record mapping each touched field to
its original (first-touched) value — copies of copies merge records, keeping
the earliest original — and `tx.update` lowers it to the canonical row-shaped
write input: the sparse row (primary key plus the effective change set —
touched fields whose current value differs from the recorded original) for
non-temporal entities, the full row for temporal close-and-chain. Recording
originals rather than a touched-name set is what detects net-zero edit chains
(`100 → 200 → 100` drops out), and an update whose effective change set is
empty issues no DML at all — the core no-op-update rule. Because Pydantic's
own `model_copy` does not validate `update=` data, the override revalidates
with the same build-time rules as construction (unknown fields rejected,
framework-owned and primary-key fields unassignable, scalar input policies
applied). A predicate-plus-typed-assignments update API
(`tx.update(Entity.where(...), Entity.attr.set(v))`) was designed and then
retracted once the corpus showed every canonical write input is row-shaped
and no predicate-shaped write input exists in the claimed slice; "set-based
write" in core describes how the unit of work flushes buffered rows, not a
public predicate-update surface.

Immutability is the enabler, not the obstacle: because nodes are frozen, the
copy API is the only mutation idiom, so the change record is complete by
construction — no dirty flags, no proxies. The optimistic close still gates on
the version analogue observed by the in-transaction read-before-write; gating
on the snapshot's own coordinates (offline-edit conflict detection) remains
managed-pole merge-back semantics and is deliberately not pulled into this
slice. The stale-web-edit workflow needs no such gate — provided the display
instant is finite: the service captures a finite instant at render time and
pins the display read at it (an unpinned latest read exposes only the LATEST
sentinel, which re-resolves to whatever milestone is current at replay time
and so cannot detect the conflict), then re-fetches `as_of` that instant
inside an optimistic transaction, where the observed `in_z` gate rejects
concurrent changes.
