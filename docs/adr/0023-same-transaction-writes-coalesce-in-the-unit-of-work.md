# Same-transaction writes coalesce in the unit of work

Neither `m-audit-write` nor `m-bitemp-write` stated what happens when a row created
earlier in the *same* unit of work is written again before flush, and the corpus had
no witness for it: the milestone modules describe the durable cross-transaction shapes
(close-and-chain, the rectangle split), each pinned by a sequence of separate
transactions. The open question is the intra-transaction combination — whether a
same-transaction insert-then-update fabricates an intermediate milestone, and whether a
same-transaction insert-then-delete leaves a milestone behind.

The decision is that buffered writes of the same object within one unit of work
**coalesce before flush**, and the rule is owned by `m-unit-work` rather than the
per-verb milestone modules, because it is a buffering decision, not a lowering one.

- An **insert-then-update** coalesces **in place**: the flush emits a single write
  carrying the final value, fabricating no intermediate milestone. A non-temporal pair
  emits one `INSERT` with the post-update values; an audit-only pair opens a single
  current milestone (no close-and-chain); a bitemporal pair opens a single fully-current
  rectangle (no inactivation or head/tail split).
- An **insert-then-delete** **cancels**: the two buffered writes annihilate and the
  flush emits no DML for that object — the net-zero effective-change-set elision,
  extended across two verbs.

The principle is that a state a transaction never durably exposed to any other reader is
never separately recorded. A milestone exists to make a past-observable value queryable
as-of; a value that was only ever pending inside one open transaction was never
observable, so recording it would manufacture audit history that never happened. The
milestone modules remain correct for the cross-transaction case they describe; this
decision fills the intra-transaction gap they deliberately left to the buffering scope.

Reladomo is the prior art. Its transaction write queue (`TxOperations` /
`GenericBiTemporalDirector` same-transaction handling) merges a same-transaction
insert-then-update into the pending insert and cancels a pending insert against a
matching same-transaction delete (`addDelete`). Parallax adopts that runtime semantics
without copying the Java queue: the rule is a single buffering stage, so a future core
ruling that chose differently would be a localized flip rather than a redesign.

The normative rule and its witnesses (`m-unit-work-008`, `m-audit-write-008`,
`m-bitemp-write-014`, `m-unit-work-010`) are recorded in
[`core/spec/m-unit-work.md`](../../core/spec/m-unit-work.md); the milestone modules
[`core/spec/m-audit-write.md`](../../core/spec/m-audit-write.md) and
[`core/spec/m-bitemp-write.md`](../../core/spec/m-bitemp-write.md) continue to own the
durable cross-transaction shapes and defer the same-transaction combination to it.
