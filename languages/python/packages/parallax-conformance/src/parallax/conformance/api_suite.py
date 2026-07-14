"""``parallax.conformance.api_suite`` — API Conformance Suite machinery.

The coverage-partition computation and the Usage Guide model shared by the
``tests/api_conformance`` suite and the ``gen-usage-guide`` generator. The
partition asserts the union of exercised and reasoned-skipped cases equals the
active slice, with no stale case IDs and no empty skip reasons.

Reasoned skips are drawn from an **explicit, reviewed** registry
(:data:`SKIP_REASONS`, keyed by module) rather than auto-derived from the active
set. An active case whose module is absent from the registry is covered by
neither exercised nor skipped, so the partition fails — forcing a human to
classify a newly reachable capability rather than letting it inherit a generic
reason. A registry entry that names no unexercised active case is reported as
stale. Entries are removed as each module's idiomatic examples land.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final

from parallax.conformance import case_format
from parallax.conformance.claim import SNAPSHOT_CLAIM, Claim

__all__ = [
    "EXAMPLES",
    "SKIP_REASONS",
    "Example",
    "Partition",
    "Skip",
    "active_slice",
    "build_skips",
    "compute_partition",
    "partition_report",
    "render_usage_guide",
    "stale_skip_reasons",
]


@dataclass(frozen=True, slots=True)
class Example:
    """A documented idiomatic public-API example exercising one corpus case."""

    case_id: str
    title: str
    snippet: str


@dataclass(frozen=True, slots=True)
class Skip:
    """A reasoned skip: a corpus case with no idiomatic example yet, plus why."""

    case_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class Partition:
    """The coverage-partition result over the active slice."""

    active: frozenset[str]
    exercised: frozenset[str]
    skipped: frozenset[str]
    errors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.errors


# The registered idiomatic examples. Each mirrors a corpus case and is proven by
# the operation no-drift guard (its statement serializes to the case's operation).
# Later phases append an Example per newly reachable case as its capability lands.
EXAMPLES: Final[list[Example]] = [
    Example(
        "m-op-algebra-002",
        "Equality on the primary key",
        "op = Order.where(Order.id == 42)",
    ),
    Example(
        "m-op-algebra-009",
        "Is-null predicate",
        "op = Order.where(Order.sku.is_null())",
    ),
    Example(
        "m-op-algebra-011",
        "SQL-pattern LIKE",
        'op = Order.where(Order.sku.like("A-%"))',
    ),
    Example(
        "m-op-algebra-013",
        "Literal starts-with (wildcards escaped)",
        'op = Order.where(Order.sku.starts_with("A-"))',
    ),
    Example(
        "m-op-algebra-018",
        "Membership (IN)",
        "op = Order.where(Order.id.in_([1, 2, 42]))",
    ),
    Example(
        "m-op-algebra-020",
        "Conjoined filters (big-AND)",
        "op = Order.where(Order.active.is_(True), Order.qty > 10)",
    ),
    Example(
        "m-op-algebra-021",
        "Disjunction with parentheses",
        "op = Order.where((Order.qty < 10) | (Order.qty > 25))",
    ),
    Example(
        "m-op-algebra-024",
        "Grouped precedence — an OR under an AND",
        "op = Order.where((Order.qty >= 25) | (Order.qty <= 5), Order.active.is_(True))",
    ),
    Example(
        "m-op-algebra-025",
        "Natural precedence — an AND under an OR (no group)",
        "op = Order.where((Order.qty >= 25) | ((Order.qty <= 5) & Order.active.is_(True)))",
    ),
    Example(
        "m-op-algebra-032",
        "Ordering and limiting",
        "op = Order.where().order_by(Order.active.desc(), Order.qty.asc()).limit(2)",
    ),
    # Temporal reads (m-temporal-read), unlocked by the D-7 class-frontend axis
    # declaration (`EntityConfig.as_of`); proven by the operation no-drift guard.
    Example(
        "m-temporal-read-003",
        "As-of read at a past instant",
        "op = Balance.where().as_of(processing=datetime(2024, 4, 1, tzinfo=UTC))",
    ),
    # The developer transaction surface (m-unit-work, M4): neutral keyed-write
    # verbs + participating finds through `db.transact`; proven by the write
    # no-drift guard (commit paths emit the golden DML; abort paths prove the
    # discard contract).
    Example(
        "m-unit-work-001",
        "Insert, then read your own write",
        """def fn(tx):
    row = {"id": 7, "owner": "Newton", "balance": 5.00, "version": 1}
    tx.insert("Account", row)
    return tx.find("Account", {"eq": {"attr": "Account.id", "value": 7}})

rows = db.transact(fn)""",
    ),
    Example(
        "m-unit-work-002",
        "An aborted update is discarded",
        """def fn(tx):
    tx.update("Account", {"id": 1, "balance": 999.00, "version": 2})
    raise RuntimeError("changed my mind")  # abort: the buffered update is discarded

db.transact(fn)  # raises; a later find still observes the original balance""",
    ),
    Example(
        "m-unit-work-003",
        "Foreign-key-ordered inserts in one transaction",
        """def fn(tx):
    order = {"id": 100, "name": "Hopper", "sku": "X-1", "qty": 1,
             "price": 9.99, "active": True, "orderedOn": "2024-07-01"}
    tx.insert("Order", order)
    tx.insert("OrderItem", {"id": 200, "orderId": 100, "sku": "X-1", "quantity": 3})

db.transact(fn)  # the flush inserts the parent before the child""",
    ),
    Example(
        "m-unit-work-004",
        "The callback value is withheld on abort",
        """def fn(tx):
    tx.update("Account", {"id": 1, "balance": 175.00, "version": 2})
    tx.find("Account", {"eq": {"attr": "Account.id", "value": 1}})  # forces the flush
    raise RuntimeError("abort")  # even the force-flushed write is rolled back

db.transact(fn)  # raises — no value is returned as though durable""",
    ),
    Example(
        "m-unit-work-005",
        "Keyed update, observed in-transaction",
        """def fn(tx):
    tx.update("Account", {"id": 1, "balance": 175.00, "version": 2})
    return tx.find("Account", {"eq": {"attr": "Account.id", "value": 1}})

rows = db.transact(fn)""",
    ),
    Example(
        "m-unit-work-006",
        "Keyed delete, observed in-transaction",
        """def fn(tx):
    tx.delete("Account", {"id": 3})
    return tx.find("Account", {"eq": {"attr": "Account.id", "value": 3}})

rows = db.transact(fn)  # [] — the dependent find observes the deletion""",
    ),
    Example(
        "m-unit-work-007",
        "Create, then later delete, a parent/child pair",
        """def create(tx):
    order = {"id": 100, "name": "Hopper", "sku": "X-1", "qty": 1,
             "price": 9.99, "active": True, "orderedOn": "2024-07-01"}
    tx.insert("Order", order)
    tx.insert("OrderItem", {"id": 200, "orderId": 100, "sku": "X-1", "quantity": 3})

def teardown(tx):
    tx.delete("OrderItem", {"id": 200})  # child first, mirroring the FK-ordered insert
    tx.delete("Order", {"id": 100})

db.transact(create)
db.transact(teardown)""",
    ),
    Example(
        "m-unit-work-009",
        "One flush, combined mixed-verb order",
        """def fn(tx):
    tx.insert("Account", {"id": 9, "owner": "Noether", "balance": 5.00, "version": 1})
    tx.update("Account", {"id": 1, "balance": 20.00, "version": 2})
    tx.delete("Account", {"id": 3})
    return tx.find("Account", {"lessThan": {"attr": "Account.balance", "value": 50.00}})

rows = db.transact(fn)  # one flush: insert, update, delete — then the find""",
    ),
    Example(
        "m-unit-work-011",
        "An aborted insert never becomes durable",
        """def fn(tx):
    tx.insert("Account", {"id": 7, "owner": "Newton", "balance": 5.00, "version": 1})
    raise RuntimeError("abort")

db.transact(fn)  # raises; a later find for account 7 observes no rows""",
    ),
    Example(
        "m-unit-work-012",
        "An aborted delete leaves the row standing",
        """def fn(tx):
    tx.delete("Account", {"id": 3})
    raise RuntimeError("abort")

db.transact(fn)  # raises; account 3 still stands""",
    ),
]

# The reviewed skip registry: primary module -> the reason its active cases carry
# no idiomatic API example yet. Keyed by module (a reason bucket), and NOT derived
# from the active slice, so a corpus case whose module is absent here fails the
# partition (see module docstring). Each reason names the COR-3 phase that brings
# the module's developer surface online; the entry is dropped when that lands.
SKIP_REASONS: Final[dict[str, str]] = {
    "m-core": (
        "m-core neutral-type behaviour has no standalone developer surface; it is "
        "exercised through the first read path (COR-3 Phase 5)"
    ),
    "m-descriptor": (
        "descriptor introspection is proven by the descriptor no-drift guard; the read "
        "path compiles/runs its descriptor cases (COR-3 Phase 5)"
    ),
    "m-op-algebra": (
        "representative predicate/grouping/ordering spellings are exercised as idiomatic "
        "examples (COR-3 Phase 5); the remaining op-algebra cases are graded through the "
        "compile/run lanes and land as examples incrementally"
    ),
    "m-temporal-read": (
        "the representative as-of spelling is exercised as an idiomatic example (the D-7 "
        "class-frontend axis declaration landed in M4); the remaining temporal-read cases "
        "are graded through the compile/run conformance lanes and land as examples "
        "incrementally"
    ),
    "m-unit-work": (
        "the same-transaction coalescing witnesses (m-unit-work-008/010) buffer an "
        "insert+update / insert+delete pair whose one-statement / zero-statement collapse "
        "is m-batch-write behavior (COR-3 Phase 8); their planner folding is already "
        "unit-pinned (test_write_lowering), and every other m-unit-work case is exercised "
        "as an idiomatic transact example"
    ),
    "m-db-error": (
        "the m-db-error corpus cases are graded end-to-end by the M4 run lanes — the "
        "single-connection triggers by the error run sweep, the two-connection "
        "choreography by the provider deadlock proof; the neutral DatabaseError surface "
        "the developer sees is exercised through the transact abort/retry unit tests"
    ),
    "m-pk-gen": (
        "write-side id allocation (the sequence/max registry reads an insert without an "
        "authored id needs) lands with the pk-gen write path (a later write increment)"
    ),
    "m-auto-retry": (
        "the bounded retry loop is implemented (parallax.core.auto_retry, M4) and proven "
        "by fake-port unit tests of db.transact (test_transact); the boundary cases need "
        "the case-driven boundary runner (when.boundary / given.fault / then.outcome over "
        "a fault-injecting port), which lands with the API-suite boundary lane build-out"
    ),
    "m-read-lock": (
        "the in-transaction shared-read-lock suffix is rendered by every locking-mode "
        "find (M4 — the write scenarios' golden reads carry it); the m-read-lock case "
        "matrix (projection suppression, two-session behavioral admits/blocks) lands "
        "with the lock path (COR-3 Phase 8)"
    ),
    "m-navigate": "relationship navigation lands with the snapshot branch (COR-3 Phase 7)",
    "m-deep-fetch": "deep-fetch includes land with the snapshot branch (COR-3 Phase 7)",
    "m-snapshot-read": "snapshot materialization lands with the snapshot branch (COR-3 Phase 7)",
    "m-value-object": (
        "value-object predicates and materialization land with the snapshot branch (COR-3 Phase 7)"
    ),
    "m-inheritance": (
        "polymorphic reads and narrowing land with the snapshot branch (COR-3 Phase 7)"
    ),
    "m-opt-lock": "optimistic-lock writes land with the write family (COR-3 Phase 8)",
    "m-audit-write": "audit (close-and-chain) writes land with the write family (COR-3 Phase 8)",
    "m-bitemp-write": "bitemporal writes land with the write family (COR-3 Phase 8)",
    "m-batch-write": "batched and set-based writes land with the write family (COR-3 Phase 8)",
}


def _selection_filter(claim: Claim) -> case_format.SelectionFilter:
    return case_format.SelectionFilter(
        modules=frozenset(claim.modules),
        case_shapes=frozenset(claim.case_shapes),
        include=frozenset(claim.include),
        exclude=frozenset(claim.exclude),
    )


def active_slice(
    claim: Claim = SNAPSHOT_CLAIM,
    cases: list[case_format.Case] | None = None,
) -> list[case_format.Case]:
    """The corpus cases the claim's selection expression admits."""
    corpus = cases if cases is not None else case_format.load_cases()
    return case_format.select(corpus, _selection_filter(claim))


def build_skips(
    active: list[case_format.Case],
    examples: list[Example],
    reasons: Mapping[str, str] = SKIP_REASONS,
) -> list[Skip]:
    """Reasoned skips for un-exercised active cases whose module the registry covers.

    A case whose ``primary_module`` is absent from ``reasons`` is deliberately
    left uncovered — the partition then flags it as covered by neither, forcing a
    human to classify the newly reachable module rather than minting a generic
    reason for it.
    """
    exercised = {example.case_id for example in examples}
    return [
        Skip(case.case_id, reasons[case.primary_module])
        for case in active
        if case.case_id not in exercised and case.primary_module in reasons
    ]


def stale_skip_reasons(
    active: list[case_format.Case],
    examples: list[Example],
    reasons: Mapping[str, str] = SKIP_REASONS,
) -> list[str]:
    """Error strings for registry entries that name no un-exercised active case.

    An entry is stale when its module is absent from the active slice or every
    case it would cover is already exercised — either way it produces no skip and
    is dead weight that must be pruned.
    """
    exercised = {example.case_id for example in examples}
    covered = {case.primary_module for case in active if case.case_id not in exercised}
    return [
        f"stale skip-registry entry {module!r}: names no un-exercised active case"
        for module in sorted(reasons)
        if module not in covered
    ]


def compute_partition(
    active_ids: frozenset[str],
    exercised: list[Example],
    skips: list[Skip],
) -> Partition:
    """Compute and validate the coverage partition of the active slice.

    Records an error for any stale ID (exercised/skipped outside the slice), any
    empty skip reason, any case both exercised and skipped, and any active case
    covered by neither.
    """
    exercised_ids = frozenset(example.case_id for example in exercised)
    skipped_ids = frozenset(skip.case_id for skip in skips)
    errors: list[str] = []
    for case_id in sorted(exercised_ids - active_ids):
        errors.append(f"stale exercised id (not in active slice): {case_id}")
    for case_id in sorted(skipped_ids - active_ids):
        errors.append(f"stale skipped id (not in active slice): {case_id}")
    for skip in skips:
        if not skip.reason.strip():
            errors.append(f"empty skip reason: {skip.case_id}")
    for case_id in sorted(exercised_ids & skipped_ids):
        errors.append(f"case both exercised and skipped: {case_id}")
    for case_id in sorted(active_ids - (exercised_ids | skipped_ids)):
        errors.append(f"active case covered by neither exercised nor skipped: {case_id}")
    return Partition(active_ids, exercised_ids, skipped_ids, tuple(errors))


def partition_report(
    claim: Claim = SNAPSHOT_CLAIM,
    cases: list[case_format.Case] | None = None,
    examples: list[Example] | None = None,
) -> Partition:
    """Load the active slice and compute its partition against the skip registry."""
    active = active_slice(claim, cases)
    registered = examples if examples is not None else EXAMPLES
    skips = build_skips(active, registered, SKIP_REASONS)
    active_ids = frozenset(case.case_id for case in active)
    partition = compute_partition(active_ids, registered, skips)
    stale = stale_skip_reasons(active, registered, SKIP_REASONS)
    if not stale:
        return partition
    return Partition(
        partition.active,
        partition.exercised,
        partition.skipped,
        (*partition.errors, *stale),
    )


_GUIDE_HEADER: Final[str] = (
    "<!-- GENERATED by `gen-usage-guide` from the API Conformance Suite. "
    "Do not edit by hand; run `just python-verify` / `uv run gen-usage-guide`. -->"
)


def render_usage_guide(examples: list[Example]) -> str:
    """Render the Usage Guide markdown from the registered examples."""
    lines: list[str] = [
        _GUIDE_HEADER,
        "",
        "# Parallax Python — Usage Guide",
        "",
        "Idiomatic public-API usage, generated from the API Conformance Suite's",
        "examples. Each example mirrors a compatibility-corpus case, so the guide",
        "cannot drift from graded behavior.",
        "",
    ]
    if not examples:
        lines.append(
            "_No idiomatic examples yet — they are added as each COR-3 phase brings "
            "its capability online._"
        )
        lines.append("")
    else:
        for example in sorted(examples, key=lambda item: item.case_id):
            lines.append(f"## {example.title}")
            lines.append("")
            lines.append(f"Corpus case: `{example.case_id}`")
            lines.append("")
            lines.append("```python")
            lines.append(example.snippet)
            lines.append("```")
            lines.append("")
    # Collapse the trailing separator blank(s) into a single terminating newline
    # so the generated Markdown satisfies markdownlint MD012 (no multiple blanks).
    return "\n".join(lines).rstrip("\n") + "\n"
