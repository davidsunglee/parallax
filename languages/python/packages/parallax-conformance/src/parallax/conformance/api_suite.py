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
from parallax.conformance.graph_stories import GRAPH_STORIES, graph_story_snippet
from parallax.conformance.read_stories import READ_STORIES, read_story_snippet
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
    # The op-algebra / temporal-read / navigate / single-concrete-inheritance
    # read examples: each is an executable read story
    # (`parallax.conformance.read_stories`) — the snippet is `read_story_
    # snippet(story)` (single-sourced from the story's own `concurrency`
    # field, review remediation finding 2 — never the bare `snippet` alone,
    # which would render a `m-read-lock` transactional story identically to
    # its non-transactional siblings), and the real-Postgres suite executes
    # the SAME `build()` through the shipped `parallax.snapshot.connect` +
    # `parallax-postgres` (test_story_run's generic runner), grading the
    # mirrored case's own `then.rows` (order-insensitive, exact-typed) and
    # `then.roundTrips`. The `navigate`-tagged siblings (a corpus spelling
    # redundancy for the identical correlated-EXISTS lowering `exists`
    # already expresses — m-op-algebra), the deep-fetch-bearing temporal
    # siblings, the multi-concrete polymorphic PROJECTING inheritance reads,
    # and the Customer value-object family are reasoned-skipped; see
    # CASE_SKIP_REASONS.
    *(Example(story.case_id, story.title, read_story_snippet(story)) for story in READ_STORIES),
    # The developer transaction surface (m-unit-work, M4): each write example IS
    # an executable story (`parallax.conformance.stories`) — the snippet is the
    # story's own source, the real-Postgres suite executes it through the shipped
    # `parallax.snapshot.connect` + `parallax-postgres` (test_story_run), and the
    # fake-port write no-drift guard drives the same function against the golden
    # DML. One source, three consumers: the guide cannot drift from execution.
    *(Example(story.case_id, story.title, story_snippet(story)) for story in WRITE_STORIES),
    # Rejected-case build-time proofs (m-op-algebra/m-navigate/m-value-object):
    # the idiomatic surface refuses the SAME invalid input the corpus's own
    # rejected lane grades, through the SAME model-aware validator
    # (`validate_operation`), naming the SAME classified rule — proven by
    # `test_idiomatic_statement_build_rejects_the_corpus_rule`.
    Example(
        "m-value-object-038",
        "A nested comparison whose literal type mismatches the declared attribute",
        "Customer.where(Customer.address.city == 42)\n"
        '# raises OperationRejectedError(rule="nested-literal-type-mismatch")',
    ),
    Example(
        "m-inheritance-040",
        "A narrow that broadens beyond its position",
        "Animal.where(Pet.narrow(WildBoar))\n"
        '# raises OperationRejectedError(rule="narrow-outside-position")',
    ),
    Example(
        "m-inheritance-041",
        "A concrete-subtype attribute referenced outside a narrow scope",
        "Animal.where(Dog.bark_volume > 5)\n"
        '# raises OperationRejectedError(rule="subtype-attribute-outside-narrow-scope")',
    ),
    Example(
        "m-inheritance-042",
        "A nested narrow that broadens back out of the enclosing position",
        "Animal.where(Pet.narrow(Dog, where=Animal.narrow(Cat)))\n"
        '# raises OperationRejectedError(rule="narrow-outside-position")',
    ),
    Example(
        "m-inheritance-064",
        "A relationship-scope narrow past its target's reachable set",
        "Person.pets.any(Pet.narrow(WildBoar))\n"
        '# raises OperationRejectedError(rule="narrow-outside-relationship-target")',
    ),
    Example(
        "m-inheritance-072",
        "A relationship-scope narrow naming the wrong position",
        "Person.pets.any(Animal.narrow(Dog))\n"
        '# raises OperationRejectedError(rule="narrow-outside-relationship-target")',
    ),
    # Rejected-case build/buffer-time proof (m-inheritance, COR-3 Phase 8
    # increment 2): the write-side counterpart of the read-side proofs above —
    # `tx.insert` refuses the SAME invalid write the corpus's own rejected
    # lane grades, through the SAME model-aware `validate_write`
    # (`Transaction._buffer`), naming the SAME classified rule — proven by
    # `test_idiomatic_write_build_rejects_the_corpus_rule`
    # (`tests/api_conformance/test_write_no_drift.py`).
    Example(
        "m-inheritance-088",
        "A keyed write aimed at an abstract inheritance position",
        'db.transact(lambda tx: tx.insert(Payment(id=10, amount=Decimal("200.00"))))\n'
        '# raises WriteRejectedError(rule="abstract-write-target")',
    ),
    Example(
        "m-value-object-039",
        "A write missing a required value-object attribute at depth 1",
        "db.transact(lambda tx: tx.insert(Contact(\n"
        '    id=1, name="Acme",\n'
        '    address=ContactAddress(city="Oslo", geo=ContactGeo(\n'
        '        country="NO", point=ContactPoint(lat=59.9, lon=10.7))),\n'
        ")))\n"
        '# raises WriteRejectedError(rule="write-required-attribute-missing")',
    ),
    Example(
        "m-value-object-040",
        "A write missing a required value-object attribute at depth 2",
        "db.transact(lambda tx: tx.insert(Contact(\n"
        '    id=2, name="Beacon",\n'
        '    address=ContactAddress(street="1 Main St", city="Oslo",\n'
        "        geo=ContactGeo(point=ContactPoint(lat=59.9, lon=10.7))),\n"
        ")))\n"
        '# raises WriteRejectedError(rule="write-required-attribute-missing")',
    ),
    Example(
        "m-value-object-041",
        "A write missing a required value-object attribute at depth 3",
        "db.transact(lambda tx: tx.insert(Contact(\n"
        '    id=3, name="Cairn",\n'
        '    address=ContactAddress(street="2 Fjord Vei", city="Bergen",\n'
        '        geo=ContactGeo(country="NO", point=ContactPoint(lon=5.3))),\n'
        ")))\n"
        '# raises WriteRejectedError(rule="write-required-attribute-missing")',
    ),
    Example(
        "m-value-object-042",
        "A write missing a required NESTED value object entirely",
        "db.transact(lambda tx: tx.insert(Contact(\n"
        '    id=4, name="Delta",\n'
        '    address=ContactAddress(street="3 Harbour Rd", city="Oslo"),\n'
        ")))\n"
        '# raises WriteRejectedError(rule="write-required-value-object-missing")',
    ),
    Example(
        "m-value-object-044",
        "A write missing a required TOP-LEVEL value object entirely",
        'db.transact(lambda tx: tx.insert(Shipment(id=5, name="Express")))\n'
        '# raises WriteRejectedError(rule="write-required-value-object-missing")',
    ),
    # Snapshot/graph semantics (m-snapshot-read, m-navigate x m-temporal-read):
    # each example IS an executable graph story
    # (`parallax.conformance.graph_stories`) — the snippet is the story's own
    # source, and the real-Postgres suite executes it through the shipped
    # `parallax.snapshot.connect` + `parallax-postgres` (test_story_run),
    # grading the mirrored case's own oracle (a `then.graph`/`identityChecks`
    # reference-identity assertion, a closed-world `UnloadedRelationshipError`,
    # a `pin`/`edge_of` coordinate, or a scenario's own per-step observable).
    *(Example(story.case_id, story.title, graph_story_snippet(story)) for story in GRAPH_STORIES),
]

# The reviewed skip registry: primary module -> the reason its active cases carry
# no idiomatic API example yet. Keyed by module (a reason bucket), and NOT derived
# from the active slice, so a corpus case whose module is absent here fails the
# partition (see module docstring). Each reason names the COR-3 phase that brings
# the module's developer surface online; the entry is dropped when that lands.
#
# The instance-native API story build-out (ledger D-23): the developer-facing
# KEYED temporal-window verbs themselves landed (`Transaction.terminate` /
# `.update_until` / `.terminate_until`, and an optional bitemporal
# `business_from` on the existing `.update`) — every bucket below that cites
# this deferral is a capability the shipped surface can now express. The
# STORIES demonstrating them through the API Conformance Suite remain
# unbuilt: authoring one for a temporal write needs per-story processing-
# instant control in the `WriteStory` test harnesses
# (`tests/api_conformance/test_write_no_drift.py`'s `_db()`,
# `tests/api_conformance/test_story_run.py`'s `connect()` calls), which
# default to the system clock today and have no way to pin a corpus write-
# sequence case's own authored `at` instant(s) — an open prerequisite this
# ledger entry's own verb landing did not itself resolve, named here rather
# than left an unexplained absence.
_STORY_BUILD_OUT_DEFERRAL: Final[str] = (
    "no idiomatic TYPED-verb example exists yet: the underlying verb landed (ledger "
    "D-23), but the story demonstrating it does not — building one needs per-story "
    "processing-instant control in the `WriteStory` test harnesses (`test_write_no_"
    "drift.py` / `test_story_run.py`), which default to the system clock and cannot "
    "pin a corpus case's own authored instant(s); an open prerequisite, not a dated "
    "promise"
)

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
        "— including the optimistic-lock temporal-close conflict/retry witnesses "
        "(`m-temporal-read-009`..`-012`: gated success, stale-`in_z` conflict, the "
        "`when.attempts` 0-then-1 retry, and the locking-mode non-retriable stale close, "
        "COR-3 Phase 8 increment 4) — are graded end-to-end by the compile/run "
        f"conformance lanes now; {_STORY_BUILD_OUT_DEFERRAL}"
    ),
    "m-db-error": (
        "the m-db-error corpus cases are graded end-to-end by the M4 run lanes — the "
        "single-connection triggers by the error run sweep, the two-connection "
        "choreography by the provider deadlock proof; the neutral DatabaseError surface "
        "the developer sees is exercised through the transact abort/retry unit tests"
    ),
    "m-pk-gen": (
        "write-side id allocation (`max`/`sequence`) is graded end-to-end by the "
        "compile/run conformance lanes now (COR-3 Phase 8 increment 3) — "
        f"{_STORY_BUILD_OUT_DEFERRAL}. `m-pk-gen-014` (a "
        "temporal pk-generated insert) landed in increment 4 and has its own "
        "case-scoped entry below (`_PK_GEN_TEMPORAL_INSERT_REASON`)"
    ),
    "m-auto-retry": (
        "the bounded retry loop is implemented (parallax.core.auto_retry) and proven "
        "by fake-port unit tests of db.transact (test_transact), including the "
        "optimistic-lock opt-in classification (COR-3 Phase 8 increment 6); the five "
        "boundary-shape cases (transient retry with the opt-in unset/set, the opt-in "
        "inert in locking mode, `retries: 0` disabling the loop, and bound exhaustion) "
        "are now graded end-to-end by the D-17 case-driven boundary runner "
        "(`tests/api_conformance/test_boundary_run.py`, driving the REAL db.transact "
        "against the provisioned database through a fault-injecting port decorator); "
        f"{_STORY_BUILD_OUT_DEFERRAL}"
    ),
    "m-opt-lock": (
        "the predicate-selected / materializing write forms (the readless "
        "unversioned/non-temporal exception, and the versioned materialize-then-lower "
        "family) landed in COR-3 Phase 8 increment 5 — graded end-to-end by the "
        "compile/run conformance lanes now (the readless forms) or the run lane alone "
        f"(the materializing ones, query-result-dependent); {_STORY_BUILD_OUT_DEFERRAL}. "
        "The non-temporal keyed gate/advance/"
        "conflict forms landed in increment 3; the auto-retry conflict-lane witness "
        "(`-009`), the D-17 boundary runner's conflict-opt-in pair (`-010`/`-011`), and "
        "the interleaved two-session race (`-012`, over the increment 6 `peer` seam) "
        "each landed in increment 6 — every one its own case-scoped entry below"
    ),
    "m-audit-write": (
        "the milestone-chaining write forms (insert / close-and-chain update / "
        "terminate, plus the TPH/TPCS and value-object compositions) landed in COR-3 "
        "Phase 8 increment 4 — graded end-to-end by the compile/run conformance lanes "
        f"now; {_STORY_BUILD_OUT_DEFERRAL}. "
        "The materializing predicate-write scenarios (`m-audit-write-007`/`-009`) "
        "landed in increment 5 — run-lane covered (query-result-dependent), same "
        "deferral"
    ),
    "m-bitemp-write": (
        "the rectangle-split write forms (insert / updateUntil / terminateUntil / "
        "plain update / plain terminate, the optimistic business-discriminator gate, "
        "and the TPH/TPCS compositions) landed in COR-3 Phase 8 increment 4 — graded "
        f"end-to-end by the compile/run conformance lanes now; {_STORY_BUILD_OUT_DEFERRAL}. "
        "The materializing predicate-write "
        "scenarios (`m-bitemp-write-010`..`-013`) landed in increment 5 — run-lane "
        "covered (query-result-dependent), same deferral"
    ),
    "m-batch-write": (
        "the set-based collapse / readless / materialize forms (multi-row INSERT "
        "collapse, batched UPDATE, IN-list DELETE, readless predicate update/delete, "
        "and the versioned materialize-then-lower family) landed in COR-3 Phase 8 "
        f"increment 5 — graded end-to-end by the compile/run conformance lanes now; "
        f"{_STORY_BUILD_OUT_DEFERRAL}"
    ),
}

# Case-scoped skips take precedence over the module registry and exist so a
# module can be MOSTLY exercised without a broad bucket silently absorbing a
# case that loses its example (the backbone review's partition red-check): with
# no `m-unit-work` module entry, dropping any exercised m-unit-work example
# fails the partition ("covered by neither") instead of inheriting a reason.
_COALESCING_WITNESS_REASON: Final[str] = (
    "a same-transaction coalescing witness: it buffers an insert+update / insert+delete "
    "pair whose one-statement / zero-statement collapse is m-batch-write behavior — the "
    "planner folding is unit-pinned (test_write_lowering) and, since COR-3 Phase 8 "
    "increment 5, graded end-to-end by the compile/run conformance lanes too; "
    f"{_STORY_BUILD_OUT_DEFERRAL}"
)

# --------------------------------------------------------------------------- #
# COR-3 Phase 7 increment 6b: the five flipped module buckets (m-navigate,     #
# m-deep-fetch, m-snapshot-read, m-value-object, m-inheritance) retire their  #
# blanket "lands with Phase 7" entries above — Phase 7 has landed. Every      #
# remaining active case under those modules gets its OWN reasoned, honest,   #
# case-scoped entry below, grouped by identical justification.               #
# --------------------------------------------------------------------------- #

# Rows-form inheritance reads (TPH tag-predicate/abstract-root/narrow, TPCS
# union-all/narrow) that are a REPRESENTATIVE SIBLING of an already-exercised
# SINGLE-CONCRETE example: the SAME correlated tag-predicate / superset-projection
# mechanism, proven once per shape (m-inheritance-001/012, the two exercised
# single-concrete-resolving reads), applied to a different family or narrow
# combination. No new developer-facing spelling to add; the no-drift guard
# already proves the mechanism these siblings would only repeat. (The
# MULTI-concrete-resolving siblings — abstract-root / narrow-to-2+-concretes —
# are NOT covered by this reason: see
# `_INHERITANCE_MULTI_CONCRETE_PROJECTION_UNREACHABLE_REASON` below, which is
# a genuinely different, structural block, not a mere spelling repeat.)
_TPH_ROW_SIBLING_REASON: Final[str] = (
    "a representative sibling of the exercised TPH single-concrete tag-predicate "
    "examples (m-inheritance-001/012): the SAME correlated tag-predicate + "
    "superset-projection mechanism, over a different family or narrow combination — no "
    "distinct developer-facing spelling to add"
)
_TPCS_ROW_SIBLING_REASON: Final[str] = (
    "a representative sibling of the exercised TPCS single-concrete/semi-join examples "
    "(m-inheritance-005/070/071): the SAME union-all-over-concretes + narrow-scope "
    "mechanism, over a different subtype combination — no distinct developer-facing "
    "spelling to add"
)
_TPH_POLYMORPHIC_EXISTS_SIBLING_REASON: Final[str] = (
    "a representative sibling of the exercised polymorphic-navigation examples "
    "(m-inheritance-070/071 for table-per-concrete-subtype; m-navigate-004/008/010 for "
    "the correlated-EXISTS form itself): the TPH analogue is the SAME "
    "EXISTS-over-effective-concrete-set mechanism, just the other inheritance strategy"
)
_TEMPORAL_INHERITANCE_ROW_SIBLING_REASON: Final[str] = (
    "a representative sibling combining two INDEPENDENTLY exercised capabilities — the "
    "as-of spelling (m-temporal-read-003) and the TPH/TPCS single-concrete tag-predicate "
    "read (m-inheritance-001/005) — over a bitemporal instrument/rate family neither "
    "existing example mirrors; no new mechanism, no distinct spelling"
)

# The TPH concrete-target temporal read (m-inheritance-101, Bond): a strategy sibling
# of the concrete-target root-owned-axis inheritance mechanism m-inheritance-100's
# OWN ReadStory proves for real (through `db.find`, real Postgres, the SAME generic
# case-driven runner every other read story uses) — TPH's own tag-predicate
# composition is independently proven by m-inheritance-001, and its as-of
# composition by m-temporal-read-003; the residual-finding binding decision's
# genuinely new mechanism (a concrete-target read resolves its family's
# root-declared axes) is proven once, by the TPCS witness, not twice.
_CONCRETE_TARGET_TEMPORAL_ROOT_AXIS_SIBLING_REASON: Final[str] = (
    "a table-per-hierarchy strategy sibling of the concrete-target root-owned-axis "
    "inheritance mechanism `m-inheritance-100`'s own ReadStory proves for real (through "
    "`db.find`, real Postgres): TPH's own tag-predicate composition is already proven "
    "by `m-inheritance-001`, its as-of composition by `m-temporal-read-003` — the "
    "genuinely new mechanism (a concrete-target read resolves its family's root-declared "
    "axes) is proven once by the TPCS witness, not twice"
)

# Multi-concrete polymorphic PROJECTING inheritance reads (an abstract-root read,
# or a narrow resolving to 2+ concretes) — the ROW-FORM (values-lane) originals
# (m-inheritance-003/-013/-015/-052): `db.find` is instance-form, never row-form
# (python.md §4: the right observation is `type(node)`, not a flattened dict),
# so a flat `then.rows` comparison can never be reproduced from typed instances
# for these — a permanent, structural non-fit, not a capability gap. Ledger
# D-22 closes the INSTANCE-FORM half: each of these four now has an executed
# `then.graph` sibling proving the identical
# capability through the shipped surface (m-inheritance-106/-107/-108/-109,
# `graph_stories.py`, DQ7b "both lanes of the same behavior are now
# expressed") — these four ROW-FORM originals stay the values-lane witnesses
# permanently, cross-referencing their own instance-form sibling.
_INHERITANCE_MULTI_CONCRETE_PROJECTION_UNREACHABLE_REASON: Final[str] = (
    "a multi-concrete polymorphic PROJECTING read (an abstract-root read, or a narrow "
    "resolving to 2+ concretes) — the ROW-FORM (values-lane) original: `db.find` is "
    "instance-form, never row-form (python.md §4: the right observation is "
    "`type(node)`, not a flattened dict), so a flat `then.rows` comparison can never be "
    "reproduced from typed instances — a permanent, structural non-fit. Its own "
    "INSTANCE-FORM sibling (m-inheritance-106/-107/-108/-109 respectively) IS executed "
    "through `db.find` (`graph_stories.py`), proving the identical capability the OTHER "
    "way (DQ7b: both lanes of the same behavior are now expressed)"
)

# Temporal inheritance-family writes: COR-3 Phase 8 increment 3 lifted
# `lower_write`'s (`parallax.snapshot.handle`) blanket inheritance-family
# refusal for the 11 NON-temporal inheritance writes below
# (`_INHERITANCE_WRITE_CONFORMANCE_LANE_REASON`); increment 4 lifts the
# remaining TEMPORAL inheritance-family refusal too (an audit/bitemporal
# close or chain over a table-per-hierarchy or table-per-concrete-subtype
# family) — both groups are now graded end-to-end by the compile/run
# conformance lanes, and share the SAME instance-native-story deferral.
_INHERITANCE_WRITE_PHASE8_REASON: Final[str] = (
    "a TEMPORAL inheritance-family write (an audit/bitemporal milestone close or chain "
    "over a table-per-hierarchy or table-per-concrete-subtype family): graded "
    "end-to-end by the compile/run conformance lanes now (COR-3 Phase 8 increment 4) — "
    f"{_STORY_BUILD_OUT_DEFERRAL}, the "
    "SAME deferral the non-temporal inheritance-family write forms carry "
    "(`_INHERITANCE_WRITE_CONFORMANCE_LANE_REASON`, landed in increment 3)"
)
# The 11 NON-temporal inheritance-family keyed writes COR-3 Phase 8 increment 3
# landed (TPH/TPCS insert/update/delete, the deep-chain and sibling-branch
# create witnesses, and the opt-lock composition pair): graded end-to-end by
# the compile/run conformance lanes now; the instance-native story build-out
# remains open (see `_STORY_BUILD_OUT_DEFERRAL`).
_INHERITANCE_WRITE_CONFORMANCE_LANE_REASON: Final[str] = (
    "a non-temporal inheritance-family keyed write (table-per-hierarchy or table-per-"
    "concrete-subtype insert/update/delete, including the opt-lock composition pair): "
    "graded end-to-end by the compile/run conformance lanes now (COR-3 Phase 8 "
    f"increment 3) — {_STORY_BUILD_OUT_DEFERRAL}"
)
# The non-temporal `m-opt-lock` keyed write family COR-3 Phase 8 increment 3
# landed (the conflict-shape gate/success/retry witnesses, the versioned
# locking-mode advance, and the versioned batched-delete materialize-per-key
# witness): graded end-to-end by the compile/run conformance lanes now, same
# deferral shape as the inheritance write family just above.
_OPT_LOCK_WRITE_CONFORMANCE_LANE_REASON: Final[str] = (
    "a non-temporal optimistic-lock keyed write (the version gate/advance/conflict, or "
    "a versioned batched delete's per-key materialize): graded end-to-end by the "
    f"compile/run conformance lanes now (COR-3 Phase 8 increment 3) — {_STORY_BUILD_OUT_DEFERRAL}"
)
# The auto-retry optimistic-conflict opt-in's OWN conflict-lane witness (COR-3
# Phase 8 increment 6, `m-opt-lock` "Retry contract"): `retryOptimisticConflicts:
# true` over a two-attempt, 0-then-1 `when.attempts` choreography — the SAME
# caller-visible attempts-sequence lane `m-opt-lock-007` already exercises
# (pinned semantics #7); the runtime auto-retry LOOP itself is `-011`'s own
# boundary witness, below.
_OPT_LOCK_CONFLICT_LANE_OPT_IN_REASON: Final[str] = (
    "the auto-retry optimistic-conflict opt-in's own conflict-lane witness "
    "(`retryOptimisticConflicts: true` over a two-attempt, 0-then-1 `when.attempts` "
    "choreography) lands in COR-3 Phase 8 increment 6 — graded end-to-end by the run "
    "lane now (the SAME caller-visible `when.attempts` choreography `m-opt-lock-007` "
    "already exercises; the runtime auto-retry loop itself is `m-opt-lock-011`'s own "
    f"boundary witness); {_STORY_BUILD_OUT_DEFERRAL}"
)
# The auto-retry optimistic-conflict opt-in's OWN boundary pair (COR-3 Phase 8
# increment 6, D-17): the conflict surfacing after one attempt without the
# opt-in (`-010`) / auto-retried to success with it (`-011`) — graded by the
# SAME case-driven boundary runner the `m-auto-retry` module bucket names.
_OPT_LOCK_BOUNDARY_RUNNER_REASON: Final[str] = (
    "the auto-retry optimistic-conflict opt-in's own boundary witness (the conflict "
    "surfacing after one attempt without the opt-in, or auto-retried to success with "
    "it) lands in COR-3 Phase 8 increment 6 — graded end-to-end by the D-17 "
    "case-driven boundary runner (`tests/api_conformance/test_boundary_run.py`) "
    "against the real, provisioned database now (the boundary runner's own generic "
    "action mapping is deliberately not itself an idiomatic developer surface, D-17); "
    f"{_STORY_BUILD_OUT_DEFERRAL}"
)
# The interleaved two-session optimistic-lock race (COR-3 Phase 8 increment 6,
# `m-opt-lock-012`, `m-case-format` uow grouping): two concurrently-held
# `db.transact` units of work over the `Provisioner.peer` seam, sequenced in
# authored order — `parallax.conformance.engine.run_interleaved_scenario_case`.
_OPT_LOCK_INTERLEAVED_RACE_REASON: Final[str] = (
    "the interleaved two-session optimistic-lock race (two concurrently-held "
    "`db.transact` units of work over the `Provisioner.peer` seam, sequenced in "
    "authored order) lands in COR-3 Phase 8 increment 6 — graded end-to-end by the "
    "run sweep's own interleaved-group runner now "
    "(`parallax.conformance.engine.run_interleaved_scenario_case`); no idiomatic "
    "example exists (a two-connection race has no single-callback developer "
    "expression) — the reference harness remains its independent behavioral "
    "cross-check"
)
# The read-lock module's OWN harness-lane single-connection golden (COR-3
# Phase 8 increment 6, `m-read-lock-001`): the default (locking-mode) object
# find carries the shared read lock, graded end-to-end by the compile AND run
# sweeps now — no `db.transact` participation-mode configuration to
# demonstrate beyond the module's own declared default (its api-conformance-
# lane runtime siblings, `-002`/`-003`/`-005`, are already exercised above).
_READ_LOCK_HARNESS_GOLDEN_REASON: Final[str] = (
    "the module's own harness-lane single-connection golden (the default locking-"
    "mode object find carries the shared read lock) is graded end-to-end by the "
    "compile AND run sweeps now (COR-3 Phase 8 increment 6); no idiomatic example is "
    "needed beyond the runtime matrix's own api-conformance siblings "
    "(`m-read-lock-002`/`-003`/`-005`, exercised as idiomatic read-story examples "
    "above) — this witness needs no `db.transact` participation-mode configuration, "
    "only the module's own declared default"
)
# The read-lock module's OWN two-session behavioral proofs (COR-3 Phase 8
# increment 6, `m-read-lock-006`/`-007`/`-008`): a genuine two-connection
# concurrency property (a shared lock blocking/admitting a writer or a second
# reader, or a projection's own omission admitting a writer) no single-session
# idiomatic example can demonstrate — graded by the case-driven `when.concurrency`
# rounds runner instead.
_READ_LOCK_TWO_SESSION_REASON: Final[str] = (
    "the two-session behavioral proof (a locking-mode reader's shared lock "
    "blocking/admitting a writer or a second reader, or a projection's own omission "
    "admitting a writer) is graded end-to-end by the case-driven `when.concurrency` "
    "rounds runner now (COR-3 Phase 8 increment 6, "
    "`parallax.conformance.concurrency_runner`, "
    "`test_run_sweep.test_read_lock_concurrency_rounds`) — a genuine two-connection "
    "concurrency property no single-session idiomatic example can demonstrate; the "
    "reference harness remains its own independent cross-check"
)
# `m-pk-gen-014` (a `sequence`-strategy insert on a temporal entity) was the
# sole pk-gen case COR-3 Phase 8 increment 3 left deferred — every other
# pk-gen case's write-side allocation landed there (the module-bucket reason
# above). Increment 4 lands this composition (a non-temporal `sequence`
# registry UPDATE plus an audit-only INSERT, one writeSequence, two
# post-re-route transactions) — graded end-to-end now, still no idiomatic
# story.
_PK_GEN_TEMPORAL_INSERT_REASON: Final[str] = (
    "a `sequence`-strategy primary-key allocation on a TEMPORAL entity (a non-temporal "
    "registry UPDATE composed with an audit-only INSERT in one writeSequence): pk-gen's "
    "non-temporal insert forms landed in COR-3 Phase 8 increment 3 (the module-bucket "
    "reason above), and this temporal composition landed in increment 4 — graded "
    f"end-to-end by the compile/run conformance lanes now; {_STORY_BUILD_OUT_DEFERRAL}"
)
####################################################################################
# Subtype-write payload-shape rejects (COR-3 Phase 8 increment 2, `validate_write`  #
# / `parallax.core.inheritance.validate_subtype_write`): the rejected sweep now     #
# grades all four (m-inheritance-086..089) through the SAME shared validator        #
# `Transaction._buffer` calls (`test_transact.py`'s own per-rule unit tests exercise#
# it directly at the neutral seam) — `m-inheritance-088` (abstract-write-target)    #
# gets an idiomatic build/buffer-time proof below (`Payment`/`CardPayment`/         #
# `CashPayment` already have a production-reachable mirror, `read_models.py`); the  #
# other three payload SHAPES have no idiomatic spelling through the TYPED verb      #
# surface, each for a DIFFERENT, empirically-verified reason.                       #
####################################################################################
_INHERITANCE_SIBLING_ATTRIBUTE_UNREACHABLE_REASON: Final[str] = (
    "a payload combining two SIBLING branches' own columns (CardPayment's `cardNetwork` AND "
    "CashPayment's `tendered`) has no idiomatic spelling: each concrete mirror class declares "
    "only its OWN branch's fields, and Pydantic's default `extra='ignore'` policy SILENTLY "
    "DROPS a field the target class does not declare (empirically verified: "
    "`CardPayment(..., tendered=...)` constructs successfully but never carries `tendered`), "
    "so no single typed instance can reproduce this payload's cross-branch shape to drive "
    "`tx.insert`/`tx.update` through it — `test_transact.py`'s own unit test exercises the "
    "classified rule directly at the neutral seam (`Transaction._buffer`) instead"
)
_INHERITANCE_METADATA_FIELD_UNREACHABLE_REASON: Final[str] = (
    "an authored `tagValue` has no idiomatic spelling: it is framework-owned metadata "
    '(m-inheritance "Metadata is framework-owned, never authored"), derived from '
    "`EntityConfig(inheritance=Concrete(tag_value=...))` at CLASS-DEFINITION time, never a "
    "per-instance Pydantic field a caller can pass to `tx.insert`/`tx.update` — "
    "`test_transact.py`'s own unit test exercises the classified rule directly at the neutral "
    "seam (`Transaction._buffer`) instead"
)
_INHERITANCE_SET_BASED_UNSUPPORTED_UNREACHABLE_REASON: Final[str] = (
    "the idiomatic spelling now EXISTS: `subtype-write-set-based-unsupported`'s natural "
    "developer-facing trigger is a set-based `_where` verb (`tx.update_where` / "
    "`tx.delete_where`) targeting an inheritance family (python.md §5), landed with the "
    "`_where` verb family (COR-3 Phase 8 increment 5; `inheritance.reject_predicate_write`) — "
    "`test_transact.py`'s own unit test exercises it directly through `tx.update_where`; the "
    "rejected-case's OWN keyless-row shape (`m-inheritance-089`) still has no idiomatic keyed "
    "spelling (no single typed instance construction denotes a payload with no primary key at "
    "all), so this remains a reasoned skip for the CASE's OWN authored shape — a permanent, "
    "structural non-fit, not a deferred story"
)

# `when.model` descriptor-shape rejects (m-inheritance-020..032, plus the
# residual-finding root-ownership witnesses 098/099, plus the D-25 optimistic-
# locking root-ownership witnesses 102/103): a DIFFERENT validation surface
# than the operation-level rejected lane increment 1 built.
# `parallax.core.inheritance.validate` classifies these exact rules, but the
# class metaclass never calls it (grep-verified) — DQ2's hierarchy-derived
# `parent`/`role` obsoletes most of what it checks. Most of these malformed
# shapes have literally no idiomatic spelling (`parent`/`role` are DERIVED from
# the live Python class hierarchy, never separately authored; Python's own
# class system additionally forbids a literal inheritance cycle), and the two
# table-placement rules that ARE independently authorable (`EntityConfig
# (table=...)` on an abstract node) are already rejected by the class
# frontend's own, DIFFERENT, unclassified error (`test_inheritance_frontend.py`
# "tableless and rowless"), not by `InheritanceError.rule`. A descendant
# declaring `EntityConfig(as_of=...)` (098/099's own rule,
# `inheritance-temporal-axes-not-root-owned`) or its own `optimisticLocking`
# attribute (102/103's own rule,
# `inheritance-optimistic-locking-not-root-owned`, D-25 / ADR 0027) is ALSO
# independently authorable, and likewise rejected by the class frontend's own,
# DIFFERENT, unclassified error (`test_inheritance_frontend.py`
# "family SUBCLASS cannot declare EntityConfig(as_of..." /
# "only the inheritance family root may declare"), joining the table-placement
# rules in the same posture — so no case in this whole group reproduces
# `then.rejectedRule` through today's public surface. This gap is PERMANENT
# (the metaclass-never-calls-`inheritance.validate` posture pre-dates and
# outlives this phase), not a forward promise.
_INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON: Final[str] = (
    "a `when.model` raw-descriptor invariant `parallax.core.inheritance.validate` "
    "classifies (parent/root/cycle/strategy/tag/temporal-axis-ownership/optimistic-"
    "locking-ownership shape) — the class metaclass never calls this validator (DQ2: "
    "`parent`/`role` are DERIVED from the live Python class hierarchy, never separately "
    "authored, so most of these malformed shapes — an unknown parent, a cycle, multiple "
    "roots, a missing root, a redeclared strategy, a duplicate/misplaced tag — have no "
    "idiomatic spelling at all); the table-placement rules AND a descendant's own "
    "`as_of` / `optimisticLocking` ARE independently authorable, but the class "
    "frontend's own existing checks raise a different, unclassified error in each case, "
    "not `InheritanceError.rule` — wiring an idiomatic path to the classified "
    "vocabulary is unbuilt infrastructure, not a capability gap this phase closes "
    "(permanent, pre-dating and outliving Phase 7/8)"
)

# `navigate`-tagged corpus siblings: a deliberate spelling redundancy for the
# IDENTICAL correlated-EXISTS lowering the exercised `.any()`/`.none()` examples
# already prove (m-navigate-002/003/004/006/008/009/010) — m-op-algebra's own
# framing ("navigate and exists are the same correlated-EXISTS lowering").
_NAVIGATE_TAG_REDUNDANT_REASON: Final[str] = (
    "a `navigate`-tagged corpus spelling redundancy for the IDENTICAL correlated-EXISTS "
    "lowering the exercised `.any()`/`.none()` examples already prove "
    "(m-navigate-002/003/004/006/008/009/010) — no distinct developer-facing shape to add"
)

# Temporal deep-fetch GRAPH siblings of the executed m-navigate-013 story (the
# ONE representative proof that a root as-of pin propagates per-hop into a
# deep-fetch child level): every other axis/cardinality/model permutation of
# the SAME propagation mechanism.
_TEMPORAL_DEEPFETCH_GRAPH_SIBLING_REASON: Final[str] = (
    "a representative sibling of the EXECUTED `m-navigate-013` graph story (the "
    "as-of-pin-propagates-per-hop-into-a-deep-fetch-level capability, real-Postgres "
    "proven via `parallax.snapshot.connect` + `db.find`): the SAME propagation "
    "mechanism, a different axis/cardinality/model permutation — building a second "
    "executable story would re-prove the identical mechanism, not a new one"
)

# Snapshot-graph siblings of the executed orders-family graph stories (diamond
# identity, back-reference cycle, closed-world, empty root/intermediate): a
# different relationship shape (to-one nullable, shared-prefix dedup, declared
# ordering) over the SAME materializer already exercised for real.
_ORDERS_GRAPH_SIBLING_REASON: Final[str] = (
    "a representative sibling of the executed orders-family graph stories "
    "(m-snapshot-read-001/004/005/009/010/011): a different relationship shape "
    "(to-one nullable, shared-prefix dedup, declared child ordering) over the SAME "
    "assembler + frozen-node wrap already proven for real against Postgres"
)

# `models/person.yaml`'s own Person/Passport pair and `models/animal.yaml`'s
# own polymorphic owner (ALSO named `Person`) were both unreachable through a
# single, global, process-wide entity registry sharing one flat namespace
# (`mirrored_models.Person` claimed the name first). Ledger D-20 resolves
# this with explicit, scoped `EntityRegistry` instances:
# `read_models.Person`/`.Passport` are now installed (the DEFAULT
# registry), and `animal_owner.Person` (the animal family's REAL owner) is
# installed in its OWN registry (parent-chained to the default, so it also
# resolves `Animal`/`Pet`/`Dog`/`Cat`/`WildBoar`) — both flip to executable
# graph stories (`graph_stories.py`); no case-scoped reason remains for either.
#
# `.history()`/`.as_of_range()` combined with `.include(...)` is an EXPLICIT,
# documented deferral (spec §3 `snapshot-history-includes`): `Statement`
# refuses the combination with `UnsupportedFeatureError` naming it. Not a gap —
# a designed-in refusal.
_SNAPSHOT_HISTORY_INCLUDES_UNSUPPORTED_REASON: Final[str] = (
    "`.history()`/`.as_of_range()` combined with `.include(...)` is an EXPLICIT, "
    "designed-in deferral (spec §3 `snapshot-history-includes`): `Statement` refuses "
    "the combination with `UnsupportedFeatureError` naming it — not a capability gap, a "
    "documented refusal"
)

# Value-object nested/absence/cast/array-traversal PREDICATE reads: rows-form,
# representative siblings of the Customer.address predicate BUILD-TIME proofs
# (m-value-object-001/002/007/015/016/017/019 — themselves case-scoped skips
# below, never executed for real either) — the SAME nested-path resolution /
# absence-collapse / any-element lowering, a different operator, depth, or
# dialect-cast variant, and the SAME reachability block a real execution of
# any of them would hit.
_VO_PREDICATE_SIBLING_REASON: Final[str] = (
    "a representative sibling of the Customer.address predicate build-time proofs "
    "(m-value-object-001/002/007/015/016/017/019 — themselves case-scoped skips below): "
    "the SAME nested-path resolution / absence-collapse / any-element lowering, a "
    "different operator, depth, or dialect-cast variant — no distinct developer-facing "
    "shape to add, and the SAME reachability block a real execution would hit"
)

# Customer-model cases needing a REAL execution (a `db.find`/`db.transact`
# story, not a build-only statement): `value_object_models.Customer` is
# test-only, and no installed `parallax.conformance` mirror of
# Customer/Location/Depot exists YET to drive these for real — ledger D-20's
# structural registry-collision block that used to make this unreachable is
# RESOLVED (an installed mirror could coexist with the test-only one via a
# separate registry, or simply redeclare Customer under the default registry
# the same way Supplier/Branch/Contact/Shipment now do); building that mirror
# is a coverage-surface BREADTH item this increment's own scale judgment (Part
# D item 4) deprioritized behind the Supplier/Branch temporal-VO flips, the
# Contact/Shipment write-validation flips, and the typed-verb story build-out.
_CUSTOMER_UNREACHABLE_REASON: Final[str] = (
    "needs a REAL execution (a `db.find`/`db.transact` story) over the Customer "
    "entity, but `value_object_models.Customer` is test-only and no installed "
    "`parallax.conformance` mirror of Customer/Location/Depot exists yet — the "
    "structural registry-collision block ledger D-20 fixed no longer applies; building "
    "the mirror is a breadth item this increment's own scale judgment deprioritized "
    "behind the Supplier/Branch/Contact/Shipment flips and the typed-verb story "
    "build-out (Part D item 4)"
)

_VO_TEMPORAL_WRITE_PHASE8_REASON: Final[str] = (
    "an audit-write / bitemp-write temporal write over a value-object-bearing entity "
    "(the document rides every chained/split row whole, at its columnOrder slot, "
    "absent from every close): graded end-to-end by the compile/run conformance lanes "
    f"now (COR-3 Phase 8 increment 4) — {_STORY_BUILD_OUT_DEFERRAL}, matching this "
    "registry's own m-audit-write/m-bitemp-write bucket reason"
)

# Value-object STRUCTURE rejects: each empirically confirmed (a REPL probe
# against the shipped surface) to have NO idiomatic spelling that reaches
# `validate_operation` with the corpus's own invalid shape — four DISTINCT
# failure modes, not one generic gap.
_VO_UNKNOWN_NESTED_FIELD_REASON: Final[str] = (
    "`Customer.contact` (the invalid path's first segment) is not a declared "
    "attribute at all: `vm.Customer.contact.city == ...` raises a plain Python "
    "`AttributeError` at attribute-access time — before any operation tree exists to "
    "validate, so the corpus's own invalid shape (a schema-valid but model-unknown "
    "nested path) has no idiomatic spelling to build"
)
_VO_DEEPFETCH_SEGMENT_REASON: Final[str] = (
    "`.include(...)` only accepts `RelationshipPath` arguments; `Customer.address` (a "
    "value-object `Attr`, not a `Rel`) raises a plain Python `TypeError` when passed to "
    "it — the type system itself prevents authoring the corpus's invalid "
    "deep-fetch-through-a-value-object shape"
)
_VO_NAVIGATE_TARGET_REASON: Final[str] = (
    "`Customer.address.any()` builds successfully, but to a DIFFERENT, valid operation "
    "(`nestedExists`, the to-many VO presence quantifier m-value-object-015/016 already "
    "exercise) — not the corpus's invalid `navigate` node targeting a value object; the "
    "idiomatic surface has no spelling that produces THAT exact shape, only a "
    "differently-typed valid one"
)
_VO_FIND_ROOT_REASON: Final[str] = (
    "`ValueObject` classes have no `.where()` classmethod at all (only `Entity` does); "
    "`vm.Address.where(...)` raises a plain Python `AttributeError` — the type system "
    "itself prevents rooting a find at a value object"
)

# Value-type mismatch (m-value-object-043): empirically confirmed (a REPL
# probe against the shipped surface) to have NO idiomatic spelling through
# `tx.insert` — `ContactAddress(street=42, ...)` raises Pydantic's own
# `ValidationError` (a `str` field never coerces an `int`) before the
# instance can even be constructed, let alone reach `validate_write`. Its
# four Contact/Shipment siblings (`-039..042`/`-044`) DO have an idiomatic
# spelling (ledger D-21's now-installed mirror, `vo_models.py`) and are
# exercised as build-time proofs above. This single case's own skip is a
# SANCTIONED exception, ledger D-32 (S5, COR-3 Phase 8 increment 7
# remediation) — not an unreviewed gap.
_VO_VALUE_TYPE_MISMATCH_UNREACHABLE_REASON: Final[str] = (
    "`ContactAddress(street=42, ...)` raises Pydantic's own `ValidationError` (a `str` "
    "field never coerces an `int`) before the instance can even be constructed, let alone "
    "reach `validate_write` — the type system itself prevents authoring the corpus's "
    "invalid value-type-mismatch shape through `tx.insert`; its four Contact/Shipment "
    "siblings (`-039..042`/`-044`) DO have an idiomatic spelling and are exercised as "
    "build-time proofs (ledger D-21's installed mirror). This case's own skip is a "
    "sanctioned exception, ledger D-32: Pydantic's own field-level coercion makes the "
    "corpus's invalid shape structurally unrepresentable through the typed surface, not "
    "a coverage gap this frontend can idiomatically close"
)

# The three remaining m-value-object write-family siblings, each a DIFFERENT
# Phase-8 concern already named by an existing module bucket above.
_VO_BATCH_WRITE_REASON: Final[str] = (
    "a multi-row (batched) insert, each row's whole value-object document binding "
    "atomically in columnOrder position — the set-based flush collapse landed in "
    "COR-3 Phase 8 increment 5 (m-batch-write) and is graded end-to-end by the "
    "compile/run conformance lanes now, matching this registry's own m-batch-write "
    f"bucket reason; {_STORY_BUILD_OUT_DEFERRAL}"
)
_VO_OPT_LOCK_CONFLICT_REASON: Final[str] = (
    "a versioned write under an optimistic-lock gate over a value-object-bearing "
    "entity: the m-opt-lock keyed-write machinery landed in COR-3 Phase 8 increment 3, "
    "and this case joins the exercised conflict set in increment 4 (already "
    "tag-reachable) — graded end-to-end by the compile/run conformance lanes now; "
    f"{_STORY_BUILD_OUT_DEFERRAL}, matching this registry's own m-opt-lock bucket reason"
)
_VO_SCENARIO_COMBO_REASON: Final[str] = (
    "a scenario combining a managed (instance-form) find, a MATERIALIZING "
    "predicate-write resolving read (row-form, the VO document omitted — the "
    "result-form contrast this case pins), and an audit-write terminate under an "
    "optimistic-lock gate: the materializing predicate-write machinery landed in "
    "COR-3 Phase 8 increment 5 (m-audit-write / m-opt-lock / m-batch-write's "
    "readless/materialize split) and is run-lane covered now (query-result-dependent, "
    f"`compileEligibility: run-only`); {_STORY_BUILD_OUT_DEFERRAL}"
)

CASE_SKIP_REASONS: Final[dict[str, str]] = {
    "m-unit-work-008": _COALESCING_WITNESS_REASON,
    "m-unit-work-010": _COALESCING_WITNESS_REASON,
    # -- m-opt-lock: non-temporal write family, conformance-lane covered ----- #
    # (COR-3 Phase 8 increment 3; instance-native examples remain undelivered) - #
    "m-opt-lock-002": _OPT_LOCK_WRITE_CONFORMANCE_LANE_REASON,
    "m-opt-lock-005": _OPT_LOCK_WRITE_CONFORMANCE_LANE_REASON,
    "m-opt-lock-006": _OPT_LOCK_WRITE_CONFORMANCE_LANE_REASON,
    "m-opt-lock-007": _OPT_LOCK_WRITE_CONFORMANCE_LANE_REASON,
    "m-opt-lock-013": _OPT_LOCK_WRITE_CONFORMANCE_LANE_REASON,
    # -- m-opt-lock / m-read-lock: COR-3 Phase 8 increment 6 landings --------- #
    "m-opt-lock-009": _OPT_LOCK_CONFLICT_LANE_OPT_IN_REASON,
    "m-opt-lock-010": _OPT_LOCK_BOUNDARY_RUNNER_REASON,
    "m-opt-lock-011": _OPT_LOCK_BOUNDARY_RUNNER_REASON,
    "m-opt-lock-012": _OPT_LOCK_INTERLEAVED_RACE_REASON,
    "m-read-lock-001": _READ_LOCK_HARNESS_GOLDEN_REASON,
    "m-read-lock-006": _READ_LOCK_TWO_SESSION_REASON,
    "m-read-lock-007": _READ_LOCK_TWO_SESSION_REASON,
    "m-read-lock-008": _READ_LOCK_TWO_SESSION_REASON,
    # -- m-batch-write: the versioned per-key delete materialize landed ------ #
    "m-batch-write-004": _OPT_LOCK_WRITE_CONFORMANCE_LANE_REASON,
    # -- m-pk-gen: the sole case still deferred (temporal composition) ------- #
    "m-pk-gen-014": _PK_GEN_TEMPORAL_INSERT_REASON,
    # -- m-inheritance: rows-form representative siblings ------------------- #
    "m-inheritance-002": _TPH_ROW_SIBLING_REASON,
    "m-inheritance-004": _TPH_ROW_SIBLING_REASON,
    "m-inheritance-011": _TPH_ROW_SIBLING_REASON,
    "m-inheritance-014": _TPH_ROW_SIBLING_REASON,
    "m-inheritance-016": _TPH_ROW_SIBLING_REASON,
    "m-inheritance-017": _TPH_ROW_SIBLING_REASON,
    "m-inheritance-006": _TPCS_ROW_SIBLING_REASON,
    "m-inheritance-050": _TPCS_ROW_SIBLING_REASON,
    "m-inheritance-051": _TPCS_ROW_SIBLING_REASON,
    "m-inheritance-053": _TPCS_ROW_SIBLING_REASON,
    "m-inheritance-060": _TPH_POLYMORPHIC_EXISTS_SIBLING_REASON,
    "m-inheritance-061": _TPH_POLYMORPHIC_EXISTS_SIBLING_REASON,
    "m-inheritance-062": _TPH_POLYMORPHIC_EXISTS_SIBLING_REASON,
    "m-inheritance-063": _TPH_POLYMORPHIC_EXISTS_SIBLING_REASON,
    "m-inheritance-092": _TEMPORAL_INHERITANCE_ROW_SIBLING_REASON,
    "m-inheritance-093": _TEMPORAL_INHERITANCE_ROW_SIBLING_REASON,
    "m-inheritance-101": _CONCRETE_TARGET_TEMPORAL_ROOT_AXIS_SIBLING_REASON,
    # -- m-inheritance: multi-concrete polymorphic PROJECTING reads, the       #
    # ROW-FORM originals (their own instance-form sibling is now executed) --- #
    "m-inheritance-003": _INHERITANCE_MULTI_CONCRETE_PROJECTION_UNREACHABLE_REASON,
    "m-inheritance-013": _INHERITANCE_MULTI_CONCRETE_PROJECTION_UNREACHABLE_REASON,
    "m-inheritance-015": _INHERITANCE_MULTI_CONCRETE_PROJECTION_UNREACHABLE_REASON,
    "m-inheritance-052": _INHERITANCE_MULTI_CONCRETE_PROJECTION_UNREACHABLE_REASON,
    # -- m-inheritance: non-temporal write family, conformance-lane covered -- #
    # (COR-3 Phase 8 increment 3; instance-native examples remain undelivered) #
    "m-inheritance-007": _INHERITANCE_WRITE_CONFORMANCE_LANE_REASON,
    "m-inheritance-008": _INHERITANCE_WRITE_CONFORMANCE_LANE_REASON,
    "m-inheritance-009": _INHERITANCE_WRITE_CONFORMANCE_LANE_REASON,
    "m-inheritance-010": _INHERITANCE_WRITE_CONFORMANCE_LANE_REASON,
    "m-inheritance-080": _INHERITANCE_WRITE_CONFORMANCE_LANE_REASON,
    "m-inheritance-081": _INHERITANCE_WRITE_CONFORMANCE_LANE_REASON,
    "m-inheritance-082": _INHERITANCE_WRITE_CONFORMANCE_LANE_REASON,
    "m-inheritance-083": _INHERITANCE_WRITE_CONFORMANCE_LANE_REASON,
    "m-inheritance-084": _INHERITANCE_WRITE_CONFORMANCE_LANE_REASON,
    "m-inheritance-085": _INHERITANCE_WRITE_CONFORMANCE_LANE_REASON,
    "m-inheritance-104": _INHERITANCE_WRITE_CONFORMANCE_LANE_REASON,
    # -- m-inheritance: temporal write family (COR-3 Phase 8 increment 4) ---- #
    "m-inheritance-090": _INHERITANCE_WRITE_PHASE8_REASON,
    "m-inheritance-091": _INHERITANCE_WRITE_PHASE8_REASON,
    "m-inheritance-094": _INHERITANCE_WRITE_PHASE8_REASON,
    "m-inheritance-095": _INHERITANCE_WRITE_PHASE8_REASON,
    "m-inheritance-096": _INHERITANCE_WRITE_PHASE8_REASON,
    "m-inheritance-097": _INHERITANCE_WRITE_PHASE8_REASON,
    "m-inheritance-105": _INHERITANCE_WRITE_PHASE8_REASON,
    "m-inheritance-086": _INHERITANCE_SIBLING_ATTRIBUTE_UNREACHABLE_REASON,
    "m-inheritance-087": _INHERITANCE_METADATA_FIELD_UNREACHABLE_REASON,
    "m-inheritance-089": _INHERITANCE_SET_BASED_UNSUPPORTED_UNREACHABLE_REASON,
    # -- m-inheritance: `when.model` descriptor rejects (unreachable) -------- #
    "m-inheritance-020": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-021": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-022": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-023": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-024": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-025": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-026": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-027": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-028": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-029": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-030": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-031": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-032": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-098": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-099": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-102": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-103": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    # -- m-deep-fetch: the Customer mirror breadth deferral ------------------ #
    "m-deep-fetch-018": _CUSTOMER_UNREACHABLE_REASON,
    # -- m-navigate: `navigate`-tagged corpus spelling redundancy ------------ #
    "m-navigate-001": _NAVIGATE_TAG_REDUNDANT_REASON,
    "m-navigate-005": _NAVIGATE_TAG_REDUNDANT_REASON,
    "m-navigate-007": _NAVIGATE_TAG_REDUNDANT_REASON,
    "m-navigate-011": _NAVIGATE_TAG_REDUNDANT_REASON,
    # -- m-navigate / m-snapshot-read: temporal deep-fetch graph siblings ---- #
    "m-navigate-012": _TEMPORAL_DEEPFETCH_GRAPH_SIBLING_REASON,
    "m-navigate-014": _TEMPORAL_DEEPFETCH_GRAPH_SIBLING_REASON,
    "m-navigate-015": _TEMPORAL_DEEPFETCH_GRAPH_SIBLING_REASON,
    "m-navigate-016": _TEMPORAL_DEEPFETCH_GRAPH_SIBLING_REASON,
    "m-navigate-017": _TEMPORAL_DEEPFETCH_GRAPH_SIBLING_REASON,
    "m-navigate-019": _TEMPORAL_DEEPFETCH_GRAPH_SIBLING_REASON,
    "m-navigate-020": _TEMPORAL_DEEPFETCH_GRAPH_SIBLING_REASON,
    "m-navigate-021": _TEMPORAL_DEEPFETCH_GRAPH_SIBLING_REASON,
    "m-navigate-022": _TEMPORAL_DEEPFETCH_GRAPH_SIBLING_REASON,
    "m-navigate-024": _TEMPORAL_DEEPFETCH_GRAPH_SIBLING_REASON,
    "m-snapshot-read-002": _TEMPORAL_DEEPFETCH_GRAPH_SIBLING_REASON,
    # -- m-snapshot-read: orders-family graph siblings ----------------------- #
    "m-snapshot-read-003": _ORDERS_GRAPH_SIBLING_REASON,
    "m-snapshot-read-006": _ORDERS_GRAPH_SIBLING_REASON,
    "m-snapshot-read-008": _ORDERS_GRAPH_SIBLING_REASON,
    # -- m-snapshot-read: history+include (an explicit, designed-in deferral) #
    "m-snapshot-read-013": _SNAPSHOT_HISTORY_INCLUDES_UNSUPPORTED_REASON,
    "m-snapshot-read-014": _SNAPSHOT_HISTORY_INCLUDES_UNSUPPORTED_REASON,
    # -- m-value-object: predicate-read representative siblings ------------- #
    "m-value-object-004": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-005": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-006": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-008": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-009": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-010": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-011": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-012": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-013": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-014": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-018": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-020": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-021": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-022": _VO_PREDICATE_SIBLING_REASON,
    # -- m-value-object: the Customer-registry collision (read + write) ------ #
    "m-value-object-001": _CUSTOMER_UNREACHABLE_REASON,
    "m-value-object-002": _CUSTOMER_UNREACHABLE_REASON,
    "m-value-object-007": _CUSTOMER_UNREACHABLE_REASON,
    "m-value-object-015": _CUSTOMER_UNREACHABLE_REASON,
    "m-value-object-016": _CUSTOMER_UNREACHABLE_REASON,
    "m-value-object-017": _CUSTOMER_UNREACHABLE_REASON,
    "m-value-object-019": _CUSTOMER_UNREACHABLE_REASON,
    "m-value-object-023": _CUSTOMER_UNREACHABLE_REASON,
    "m-value-object-024": _CUSTOMER_UNREACHABLE_REASON,
    "m-value-object-025": _CUSTOMER_UNREACHABLE_REASON,
    "m-value-object-026": _CUSTOMER_UNREACHABLE_REASON,
    "m-value-object-027": _CUSTOMER_UNREACHABLE_REASON,
    # -- m-value-object: Supplier/Branch temporal VO writes (D-23, pending the #
    # typed temporal window verb `-033` needs) ------------------------------ #
    "m-value-object-032": _VO_TEMPORAL_WRITE_PHASE8_REASON,
    "m-value-object-033": _VO_TEMPORAL_WRITE_PHASE8_REASON,
    # -- m-value-object: structural rejects (no idiomatic spelling exists) --- #
    "m-value-object-034": _VO_UNKNOWN_NESTED_FIELD_REASON,
    "m-value-object-035": _VO_DEEPFETCH_SEGMENT_REASON,
    "m-value-object-036": _VO_NAVIGATE_TARGET_REASON,
    "m-value-object-037": _VO_FIND_ROOT_REASON,
    # -- m-value-object: write-input validation rejects ---------------------- #
    "m-value-object-043": _VO_VALUE_TYPE_MISMATCH_UNREACHABLE_REASON,
    # -- m-value-object: the remaining write-family siblings (COR-3 Phase 8) - #
    "m-value-object-045": _VO_BATCH_WRITE_REASON,
    "m-value-object-046": _VO_OPT_LOCK_CONFLICT_REASON,
    "m-value-object-047": _VO_SCENARIO_COMBO_REASON,
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
        # The D-16 staged-realization notice retired here (COR-3 Phase 7
        # increment 6b): the transaction verbs it warned about graduated to
        # their final entity-instance signatures in increment 6a
        # (`tx.insert(instance)` / `tx.update(edited_copy)` / `tx.delete(node)`,
        # `tx.find` returning `Snapshot[T]`) — every rendered transaction
        # example already uses that final surface, so a banner distinguishing
        # "provisional" from "final" has nothing left to warn about. Plain
        # removal, not a replacement "graduated" note: the ordinary per-example
        # rendering below already IS the final, non-provisional documentation.
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
