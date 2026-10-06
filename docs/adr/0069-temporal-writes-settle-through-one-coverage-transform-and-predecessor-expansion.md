# Temporal writes settle through one coverage transform and one predecessor expansion

Temporal geometry and the per-milestone write rules have one owner, `m-temporal-write`, beneath the unit of work and above the write plan. A written object's composed writes form one Coverage Transform of its existing coverage, and one Predecessor Expansion applies that transform to each existing milestone it reaches: whether it is reached, whether it stays unchanged, its close cause and gate, how the attempt's ownership disposes of it, and the successors it opens. A new lineage — an insert, a surviving part of a pending insert, or a replacement's Coverage Gap — is stamped by the same rules without a fabricated predecessor.

Before, the profile modules `m-txtime-write` and `m-bitemp-write` described each verb's topology as a table that the unit of work consulted for lone keyed writes and materialized groups, while ranges — compositions, caller-addressed writes, and writes crossing their predecessor — took their geometry from a transform the unit of work composed itself. The two decision sources implemented the unchanged rule, the close, the gate axis, and ownership disposal separately, and their copies differed: a range retired an overlapped observation by a fixed close that ignored the attempt's ownership, the refusal of an undeclared predecessor member depended on which path a write took, and the table gave a predicate-selected Bitemporal row starting after the write's `validFrom` a reversed head and a successor reaching back before the row's own start.

The merged module owns both profiles' contracts and the expansion that realizes them. `m-unit-work` keeps buffering, the drivers that classify originals and bind ranges, audit decoration, live ownership, and plan lifetime; it supplies the expansion its settled facts and the ownership standing at binding, and the expansion retains none of them. Validation of an overlapped observation goes through the same disposal as every other predecessor, so a row the attempt opened is removed rather than closed. An undeclared logical member is refused where the row is built, and expansion treats one as a broken invariant. The module's direct dependencies — `m-write-plan`, `m-temporal-read`, `m-inheritance`, `m-core`, `m-metamodel`, and `m-document-codec` — are named even where another edge implies them, as `m-write-plan`'s are.

Alternatives rejected:

- Keeping both decision sources behind a shared helper set leaves the geometry duplicated and the rule copies free to drift.
- Keeping the profile modules as specification-only modules realized inside `m-unit-work` separates the contracts from their code and needs a topology exception.
- Merging the profile rules into `m-unit-work` grows the module that already owns transactions, buffering, and execution, and leaves no owner a lower module could depend on.
- Having the temporal module emit an intermediate topology for `m-unit-work` to convert adds a transient structure and repeats work per row.

The contract lives in [`m-temporal-write`](../../core/spec/m-temporal-write.md); write finalization remains in [`m-unit-work`](../../core/spec/m-unit-work.md).
