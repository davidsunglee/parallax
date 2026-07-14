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
from parallax.conformance.stories import WRITE_STORIES, story_snippet

__all__ = [
    "CASE_SKIP_REASONS",
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
    # The developer transaction surface (m-unit-work, M4): each write example IS
    # an executable story (`parallax.conformance.stories`) — the snippet is the
    # story's own source, the real-Postgres suite executes it through the shipped
    # `parallax.snapshot.connect` + `parallax-postgres` (test_story_run), and the
    # fake-port write no-drift guard drives the same function against the golden
    # DML. One source, three consumers: the guide cannot drift from execution.
    *(Example(story.case_id, story.title, story_snippet(story)) for story in WRITE_STORIES),
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

# Case-scoped skips take precedence over the module registry and exist so a
# module can be MOSTLY exercised without a broad bucket silently absorbing a
# case that loses its example (the backbone review's partition red-check): with
# no `m-unit-work` module entry, dropping any exercised m-unit-work example
# fails the partition ("covered by neither") instead of inheriting a reason.
_COALESCING_WITNESS_REASON: Final[str] = (
    "a same-transaction coalescing witness: it buffers an insert+update / insert+delete "
    "pair whose one-statement / zero-statement collapse is m-batch-write behavior "
    "(COR-3 Phase 8); the planner folding is already unit-pinned (test_write_lowering)"
)
CASE_SKIP_REASONS: Final[dict[str, str]] = {
    "m-unit-work-008": _COALESCING_WITNESS_REASON,
    "m-unit-work-010": _COALESCING_WITNESS_REASON,
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
    case_reasons: Mapping[str, str] = CASE_SKIP_REASONS,
) -> list[Skip]:
    """Reasoned skips for un-exercised active cases the registries cover.

    A case-scoped reason (``case_reasons``, keyed by case id) takes precedence
    over the module registry. A case covered by neither is deliberately left
    uncovered — the partition then flags it as covered by neither, forcing a
    human to classify the newly reachable case rather than letting a broad
    module bucket absorb it.
    """
    exercised = {example.case_id for example in examples}
    skips: list[Skip] = []
    for case in active:
        if case.case_id in exercised:
            continue
        if case.case_id in case_reasons:
            skips.append(Skip(case.case_id, case_reasons[case.case_id]))
        elif case.primary_module in reasons:
            skips.append(Skip(case.case_id, reasons[case.primary_module]))
    return skips


def stale_skip_reasons(
    active: list[case_format.Case],
    examples: list[Example],
    reasons: Mapping[str, str] = SKIP_REASONS,
    case_reasons: Mapping[str, str] = CASE_SKIP_REASONS,
) -> list[str]:
    """Error strings for registry entries that name no un-exercised active case.

    A module entry is stale when its module is absent from the active slice or
    every case it would cover is already exercised (or case-scoped); a
    case-scoped entry is stale when its case is inactive or exercised. Either
    way the entry produces no skip and is dead weight that must be pruned.
    """
    exercised = {example.case_id for example in examples}
    unexercised = [case for case in active if case.case_id not in exercised]
    covered = {case.primary_module for case in unexercised if case.case_id not in case_reasons}
    stale = [
        f"stale skip-registry entry {module!r}: names no un-exercised active case"
        for module in sorted(reasons)
        if module not in covered
    ]
    unexercised_ids = {case.case_id for case in unexercised}
    stale.extend(
        f"stale case-skip entry {case_id!r}: not an un-exercised active case"
        for case_id in sorted(case_reasons)
        if case_id not in unexercised_ids
    )
    return stale


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
        staging_notice_pending = True
        for example in sorted(examples, key=lambda item: item.case_id):
            if staging_notice_pending and example.case_id.startswith("m-unit-work"):
                # The D-16 staged-realization notice: the transaction examples
                # below use the provisional neutral verbs, and readers must not
                # mistake them for the final entity-instance surface.
                lines.append("## Transactions — a provisional surface (ledger D-16)")
                lines.append("")
                lines.append(
                    "> The transaction examples below use the **neutral, provisional** "
                    "write surface: `tx.insert` / `tx.update` / `tx.delete` take an "
                    "entity **name** and a plain row document, and `tx.find` returns "
                    "plain rows. These spellings are the deliberate M4 staging of the "
                    "spec §5 transaction surface; they graduate to entity-instance "
                    "signatures (`insert(instance)`, sparse `update(edited_copy)`, "
                    "materialized finds) when the Phase-7 instance model lands "
                    "(deferred-work ledger D-16)."
                )
                lines.append("")
                staging_notice_pending = False
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
