# Writes are copy-provenance row inputs, not predicates plus assignments

Update inputs are edited copies: the entity base overrides `model_copy` so a
copy of a frozen node carries an accumulated change record, and `tx.update`
lowers it to the canonical row-shaped write input — the sparse row (primary
key plus changed attributes) for non-temporal entities, the full row for
temporal close-and-chain. A predicate-plus-typed-assignments update API
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
slice. The stale-web-edit workflow needs no such gate: re-fetch `as_of` the
original display instant inside an optimistic transaction and the observed
`in_z` gate rejects concurrent changes.
