"""The reachable corpus intersection for the compile / run sweeps.

The sweeps are parametrized from the corpus at runtime (never a hard-coded
count): the active slice intersected with the capability tags of the modules
already implemented, so a case joins a sweep exactly when every module it tags is
online. :data:`IMPLEMENTED_MODULES` grows one phase at a time — this is the COR-3
Phase 5 set (the read path across ``m-op-algebra`` / ``m-sql`` / ``m-dialect`` /
``m-db-port`` on top of the metamodel hub and the conformance spine), extended by
Phase 7's increments: increment 2 added ``m-inheritance`` / ``m-value-object``
(polymorphic TPH/TPCS read lowering); increment 3 adds ``m-navigate`` (relationship
navigation — the correlated-``EXISTS`` semi-join/anti-join, per-hop as-of
propagation, polymorphic navigation), which makes the 13 row-form navigate reads
and 6 polymorphic-relationship reads reachable alongside 3 rejected cases whose
rule the model-aware validator already classified (increment 1) — and, honestly,
the 11 deep-fetch-bearing navigate reads too, which stay reasoned-refused (deep
fetch is increment 5) rather than silently exercised; increment 5 adds
``m-deep-fetch`` / ``m-snapshot-read`` (the pure fetch planner, the graph
assembler, and the production find executor), which makes every graph-bearing
read (the 11 navigate deep-fetch reads, the 14 snapshot-read cases, the 3
polymorphic narrowed-deep-fetch inheritance reads, and ``m-deep-fetch-018``)
reachable, closes the query-result-dependent tail ledger D-10 anticipated
(``compileEligibility: run-only``), and reaches the ``m-value-object-035``
rejected case (deep-fetch-value-object-segment) that only ``m-deep-fetch``
gated; Phase 8 increment 3 adds ``m-opt-lock`` (the non-temporal optimistic-
locking write family: framework-owned version projection/advance/gate,
inheritance-family keyed writes, and the pk-gen ``max``/``sequence``
write-side allocation) — the 30-case flip enumerated in the increment's own
implementer prompt; the deferred m-opt-lock forms (predicate-write
materialization, the auto-retry boundary runner, temporal composition) stay
honestly reasoned-skipped toward increments 4-6. Phase 8 increment 4 adds
``m-audit-write`` / ``m-bitemp-write`` (the temporal keyed write family:
audit-only close-and-chain, the full-bitemporal rectangle split, the
observed-``in_z``/business-discriminator gate, and the DQ4 ``db.transact``
re-route) — the 32-case flip enumerated in that increment's own implementer
prompt; the deferred forms (materializing predicate temporal writes,
auto-retry, two-session choreography) stay honestly reasoned-skipped toward
increments 5-6. Phase 8 increment 6 adds ``m-read-lock`` (the read-lock case
matrix: the single-connection shared-suffix witness, the runtime lock/omit
`api-conformance` reads, and the two-session concurrency proofs over the
`Provisioner.peer` seam) and ``m-auto-retry`` (the bounded-retry boundary
cases the case-driven D-17 runner grades, and the optimistic-conflict
auto-retry conflict-lane witness), closing the correctness modules'
remaining honest gaps — the 15-case flip enumerated in that increment's own
implementer prompt (that increment's own report also names ``m-db-error``'s
five ``when.concurrency`` error cases as a reachable, ungraded gap: the SAME
rounds-runner choreography built for the m-read-lock two-session matrix could
grade them with zero extra machinery). The increment 7 completion round's
D-28 flip closes that gap: ``m-db-error-004``/``-005``/``-006``/``-007``/
``-009`` (deadlock cycle/reverse, lock-wait timeout x2, serialization
failure) now grade case-driven through the SAME rounds runner
(``parallax.conformance.concurrency_runner``, ``tests/conformance/
test_run_sweep.py``'s dispatch filter broadened from ``m-read-lock`` alone to
both modules) — one case (``-009``) needs its two sessions under genuine
Postgres SERIALIZABLE isolation, a runner-level knob (``run_rounds``'s own
``isolation`` argument) rather than a new schema field.
"""

from __future__ import annotations

from typing import Final

from parallax.conformance import case_format
from parallax.conformance.claim import SNAPSHOT_CLAIM, Claim

__all__ = ["IMPLEMENTED_MODULES", "reachable_cases"]

# The modules whose behaviour is implemented as of COR-3 Phase 6 (milestone 4, M4). A
# reachable case is one whose module tags are ALL in this set (case_format's
# always-on reachable-intersection filter). Phase-6 milestone 1 added `m-db-error`
# (all `error`-shape, reasoned-skipped until error/concurrency-shape `run` lands);
# milestone 2 added `m-temporal-read` (as-of / history / as-of-range read lowering);
# M4 adds `m-unit-work` (the keyed, non-temporal unit-of-work write path — scenario
# read-your-own-writes / rollback / mixed-op flushes + FK-ordered writeSequence),
# making those write cases reachable. This also unblocks the `m-pk-gen` writeSequence
# cases (which tag `m-unit-work`), whose WRITE-side id allocation is reasoned-skipped
# forward to the pk-gen write path. `m-batch-write` joined the set in COR-3 Phase 8
# increment 5 — see that entry's own comment below for why every one of its cases is
# now reachable rather than merely tagged online.
IMPLEMENTED_MODULES: Final[frozenset[str]] = frozenset(
    {
        "m-core",
        "m-case-format",
        "m-conformance-adapter",
        "m-descriptor",
        "m-pk-gen",
        "m-inheritance",
        "m-value-object",
        "m-op-algebra",
        "m-dialect",
        "m-db-port",
        "m-db-error",
        "m-sql",
        "m-temporal-read",
        "m-api-conformance",
        "m-unit-work",
        "m-navigate",
        "m-deep-fetch",
        "m-snapshot-read",
        "m-opt-lock",
        "m-audit-write",
        "m-bitemp-write",
        "m-read-lock",
        "m-auto-retry",
        # `m-batch-write-004` (the versioned per-key delete materialize) tags
        # BOTH `m-batch-write` and `m-opt-lock` — the sweep's own "every tagged
        # module must be online" rule needs this module online too for that
        # ONE witness to reach reachability. Every OTHER m-batch-write case is
        # ALSO now landed and joins `WRITE_EXERCISED` (the reviewed, byte-exact
        # set), never merely reasoned-skipped: the buffered-batch COLLAPSE
        # entries (`statements` < row count, m-batch-write-001/003, plus the
        # uniform/non-uniform keyed update m-batch-write-002) lower through
        # `lower_write`'s own multi-row collapse (COR-3 Phase 8 increment 5,
        # `m-batch-write` "Set-based flush"); the predicate-selected entries
        # (005/006) lower through the real readless predicate-write path
        # (increment 5, `m-batch-write` "Predicate-selected readless forms") —
        # the structured-predicate-write REFUSAL this comment once described
        # is retired entirely (`test_compile_sweep.py`'s own
        # `test_displayed_skip_text_stays_honest_for_a_representative_set`).
        "m-batch-write",
    }
)


def reachable_cases(
    claim: Claim = SNAPSHOT_CLAIM,
    cases: list[case_format.Case] | None = None,
) -> list[case_format.Case]:
    """The active-slice cases whose module tags are all implemented (this phase)."""
    corpus = cases if cases is not None else case_format.load_cases()
    flt = case_format.SelectionFilter(
        modules=frozenset(claim.modules),
        case_shapes=frozenset(claim.case_shapes),
        include=frozenset(claim.include),
        exclude=frozenset(claim.exclude),
    )
    return case_format.select(corpus, flt, implemented_modules=IMPLEMENTED_MODULES)
