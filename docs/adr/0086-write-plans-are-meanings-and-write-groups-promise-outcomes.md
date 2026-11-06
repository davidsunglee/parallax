# Write plans are meanings and Write Groups promise outcomes

The contract now states what a write means and what a flush may be observed to
do, and leaves how a binding represents and schedules that work to the binding.
`m-write-plan` keeps its Planned Steps as a table of meanings rather than a closed
set of records, and `m-unit-work` *Write Group formation* states outcome rules
rather than a layout algorithm. Beyond those rules, the order of effects of
distinct objects is not promised. This supersedes the closed algebra of
[ADR 0068](0068-the-planned-write-algebra-is-its-own-module.md) as a normative
representation, though not the module it created. It also supersedes, as portable
requirements, the shape-by-shape layout and 1,024-write bound of
[ADR 0080](0080-write-groups-hold-up-to-1024-settled-writes.md) and the
consecutive-run formation of
[ADR 0076](0076-write-groups-run-every-effect-before-any-insert.md).

No schema, case field, adapter output, or public export named a Planned Step, and
no case could tell the layout algorithm from another that kept the same outcomes:
every grouped-effect case held one shape, and no case exercised a barrier. Text
that no observer can grade could only drift, and it did, while requiring a
specification edit for each private refactor. Every rule that rode inside the
records keeps a stated home. Row Origin and Close Cause stay as named meanings even
though nothing observes them today, because audit provenance reads them
([ADR 0037](0037-audit-provenance-decorates-finalized-neutral-write-plans.md)).
Write Target stays because a public error names it.

The cost is real. The overview makes emitted SQL normative, so it now carries a
carve-out: for interleaved writes, and above a group's bound, a flush's statement
order and count differ between conforming bindings. Writes adjacent in one phase
still share a group where that lets them share a statement, so a run of like writes
stays determinate. A unique value one object hands another is still released in
authored order, which is correctness rather than layout and now has its own case.
The bounds of a group, an acquisition span, and a coverage read become each
implementation's, with a group's no smaller than a span's, and `m-dialect`'s bind
limit still stops an unbounded statement. Python keeps 1,024, 32, and 64, and ADR
0080's measurements remain the reason for its constant.

Some golden cases still pin one legal order of distinct objects' effects, so a
binding using this latitude would fail them. They stay as they are: only one binding
runs the corpus today, and how a golden should treat an order a module leaves open
is worth deciding when another one would.

Two alternatives were rejected. Adding the write plan to the overview's seam list
would give bindings a shared vocabulary that nothing could grade. Keeping the layout
algorithm normative with new witnesses would preserve determinacy across bindings,
at the price of mandating an algorithm chosen for one binding's measurements.
