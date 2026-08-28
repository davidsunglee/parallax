"""``parallax.conformance.api_suite`` — API Conformance Suite machinery.

The coverage-partition computation and the Usage Guide model shared by the
``tests/api`` suite and the ``gen-usage-guide`` generator. The
partition asserts the union of exercised and reasoned-skipped cases equals the
active slice, with no stale case IDs and no empty skip reasons.

Reasoned skips are drawn from an explicit registry
(:data:`SKIP_REASONS`, keyed by module) rather than auto-derived from the active
set. An active case whose module is absent from the registry is covered by
neither exercised nor skipped, so the partition fails — forcing a human to
classify a newly reachable capability rather than letting it inherit a generic
reason. A registry entry that names no unexercised active case is reported as
stale. Entries are removed as each module's idiomatic examples land.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final

from parallax.conformance import (
    case_format,
    execution_lifecycle_stories,
    read_models,
    snapshot_recipes,
    stale_web_edit,
)
from parallax.conformance.claim import SNAPSHOT_CLAIM, Claim
from parallax.conformance.graph_stories import GRAPH_STORIES, graph_story_snippet
from parallax.conformance.read_stories import READ_STORIES, read_story_snippet
from parallax.conformance.stories import WRITE_STORIES, story_snippet
from parallax.conformance.story_models import OrderStatus

__all__ = [
    "CASE_SKIP_REASONS",
    "EXAMPLES",
    "RECIPES",
    "SKIP_REASONS",
    "Example",
    "Partition",
    "Recipe",
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
class Recipe:
    """A specification recipe rendered in the Usage Guide.

    Unlike an :class:`Example`, a recipe maps to a SPEC section rather than
    one corpus case — its choreography (e.g. the §3 stale-web-edit two-read
    render-then-submit round trip) is larger than any single case's goldens,
    and force-registering it under a borrowed case id would misrepresent what
    that case grades. It renders under its own Usage-Guide heading with a
    spec citation plus the tests that grade it end-to-end.

    ``notes`` carries prose the snippet itself cannot: a fact about the code
    rather than a citation of where it is specified or graded. It renders as a
    paragraph between the citation line and the snippet, and is omitted when
    empty."""

    title: str
    spec: str
    graded_by: str
    snippet: str
    notes: str = ""


RECIPES: Final[list[Recipe]] = [
    Recipe(
        title="Optional to one — the 1..1 and 0..1 declarations and the three runtime states",
        spec=(
            "`python.md` §2 (a to-one's multiplicity is its foreign key's nullability) "
            "and §3 (closed-world relationships and `is_view_loaded`)"
        ),
        graded_by=(
            "`tests/api/test_snapshot_recipes.py` (real Postgres: the 1..1 instance, "
            "the 0..1 loaded null, and the unloaded arm of both, distinguished by "
            "`is_view_loaded` and by the refusal an unloaded access raises)"
        ),
        snippet=(
            inspect.getsource(OrderStatus)
            + "\n\n"
            + inspect.getsource(snapshot_recipes.read_to_one_relationship_states)
        ),
    ),
    Recipe(
        title="Family materialization — table-per-hierarchy and table-per-concrete-subtype",
        spec=(
            "`python.md` §2 (`AbstractRoot` / `AbstractSubtype` / `ConcreteSubtype` "
            "declarations and the two strategies) and §4 (`type(node)` is the "
            "polymorphic observation)"
        ),
        graded_by=(
            "`tests/api/test_snapshot_recipes.py` (real Postgres: each root read "
            "materializes one instance of each declared concrete class, carrying that "
            "branch's own members and no sibling's). The corpus-keyed siblings "
            "`m-inheritance-106`/`-107`/`-108`/`-109` grade the same materializer "
            "against their own `then.graph` goldens"
        ),
        snippet=(
            inspect.getsource(read_models.Payment)
            + "\n\n"
            + inspect.getsource(read_models.CardPayment)
            + "\n\n"
            + inspect.getsource(read_models.CashPayment)
            + "\n\n"
            + inspect.getsource(snapshot_recipes.read_a_table_per_hierarchy_family)
            + "\n\n"
            + inspect.getsource(read_models.Document)
            + "\n\n"
            + inspect.getsource(read_models.FinancialDocument)
            + "\n\n"
            + inspect.getsource(read_models.Invoice)
            + "\n\n"
            + inspect.getsource(read_models.Receipt)
            + "\n\n"
            + inspect.getsource(read_models.Annotation)
            + "\n\n"
            + inspect.getsource(read_models.Memo)
            + "\n\n"
            + inspect.getsource(snapshot_recipes.read_a_table_per_concrete_subtype_family)
        ),
    ),
    Recipe(
        title="Stale web edit — Transaction-Time-Only (Balance)",
        spec="`python.md` §3 (the recipe and the edge it transports)",
        graded_by=(
            "`tests/api/test_stale_web_edit.py` (real Postgres: the clean submit and "
            "the concurrent-supersession refusal, each under both concurrency modes) "
            "and `tests/unit/test_transaction_reads.py`'s Docker-free recipe halves "
            "(the observed-`in_z` gate a zero-row close raises through)"
        ),
        snippet=(
            inspect.getsource(stale_web_edit.render_balance_milestone)
            + "\n\n"
            + inspect.getsource(stale_web_edit.submit_balance_edit)
        ),
    ),
    Recipe(
        title="Stale web edit — bitemporal (Branch, the displayed rectangle re-read)",
        spec="`python.md` §3 (the recipe and the edge it transports)",
        graded_by=(
            "`tests/api/test_stale_web_edit.py` (real Postgres: the clean submit and "
            "the concurrent-supersession refusal, each under both concurrency modes) "
            "and `tests/unit/test_transaction_reads.py`'s Docker-free recipe halves"
        ),
        snippet=(
            inspect.getsource(stale_web_edit.render_branch_milestone)
            + "\n\n"
            + inspect.getsource(stale_web_edit.submit_branch_edit)
        ),
    ),
    Recipe(
        title="Stale web edit — the staleness signal, and why either concurrency mode is legal",
        spec="`python.md` §3 (the recipe) and §5 (the concurrency modes)",
        graded_by=(
            "`tests/api/test_stale_web_edit.py` (real Postgres: each variant's "
            "clean submit is graded twice, once per mode, and the read-time "
            "refusal is graded under both)"
        ),
        notes=(
            "`StaleMilestoneError` is **application**-owned, defined by the recipe itself "
            "and shown below so the snippets above name nothing undefined. It must not "
            "borrow the framework's `OptimisticLockConflictError`: that error means an "
            "optimistic gate matched zero rows, which is neither what happened here nor "
            "something that can happen under `locking` at all. The submit body is legal "
            "under **both** modes, for different reasons — `locking` takes a shared read "
            "lock on the current row at read time, so once the edge comparison passes "
            "nothing can supersede the row before the flush; `optimistic` takes no lock, "
            "and the observed-`in_z` gate covers exactly the window between the read and "
            "the flush, raising `OptimisticLockConflictError` if a writer chains a "
            "replacement inside it."
        ),
        snippet=inspect.getsource(stale_web_edit.StaleMilestoneError),
    ),
]


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


# Registered idiomatic examples mirror corpus cases and are checked by the
# query no-drift guard, which serializes each example to its case's Object Query.
EXAMPLES: Final[list[Example]] = [
    # The Predicate / temporal-read / navigate / single-concrete-inheritance
    # read examples: each is an executable read story
    # (`parallax.conformance.read_stories`) — the snippet is `read_story_
    # snippet(story)` (single-sourced from the story's own `concurrency`
    # field rather than the bare `snippet`,
    # which would render a `m-read-lock` transactional story identically to
    # its non-transactional siblings), and the real-Postgres suite executes
    # the SAME `build()` through the shipped `parallax.snapshot.connect` +
    # `parallax-postgres` (test_story_run's generic runner), grading the
    # mirrored case's own `then.rows` (order-insensitive, exact-typed) and
    # `then.roundTrips`. The `navigate`-tagged siblings (a corpus spelling
    # redundancy for the identical correlated-EXISTS lowering `exists`
    # already expresses — m-predicate), the deep-fetch-bearing temporal
    # siblings, the multi-concrete polymorphic PROJECTING inheritance reads,
    # and the Customer value-object predicate-read siblings (whose flagship
    # reads are executed graph stories; see GRAPH_STORIES below)
    # are reasoned-skipped; see CASE_SKIP_REASONS.
    *(Example(story.case_id, story.title, read_story_snippet(story)) for story in READ_STORIES),
    # The developer transaction surface: each write example is
    # an executable story (`parallax.conformance.stories`) — the snippet is the
    # story's own source, the real-Postgres suite executes it through the shipped
    # `parallax.snapshot.connect` + `parallax-postgres` (test_story_run), and the
    # fake-port write no-drift guard drives the same function against the golden
    # DML. One source, three consumers: the guide cannot drift from execution.
    *(Example(story.case_id, story.title, story_snippet(story)) for story in WRITE_STORIES),
    # Rejected-case build-time proofs (m-predicate/m-navigate/m-value-object):
    # the idiomatic surface refuses the SAME invalid input the corpus's own
    # rejected lane grades, through the SAME model-aware validator
    # (`validate_predicate`), naming the SAME classified rule — proven by
    # `test_idiomatic_statement_build_rejects_the_corpus_rule`.
    Example(
        "m-value-object-038",
        "A nested comparison whose literal type mismatches the declared attribute",
        "Customer.where(Customer.address.city == 42)\n"
        '# raises ModelRejectedError(rule="nested-literal-type-mismatch")',
    ),
    Example(
        "m-inheritance-040",
        "A narrow that broadens beyond its position",
        "Animal.where(Animal.narrow(Person))\n"
        '# raises ModelRejectedError(rule="narrow-outside-position")',
    ),
    Example(
        "m-inheritance-041",
        "A concrete-subtype attribute referenced outside a narrow scope",
        "Animal.where(Dog.bark_volume > 5)\n"
        '# raises ModelRejectedError(rule="subtype-attribute-outside-narrow-scope")',
    ),
    Example(
        "m-inheritance-042",
        "A nested narrow that broadens back out of the enclosing position",
        "Animal.where(Pet.narrow(Dog, where=Animal.narrow(Cat)))\n"
        '# raises ModelRejectedError(rule="narrow-outside-position")',
    ),
    Example(
        "m-inheritance-064",
        "A relationship-scope narrow past its target's reachable set",
        "Person.pets.exists(Pet.narrow(WildBoar))\n"
        '# raises ModelRejectedError(rule="narrow-outside-relationship-target")',
    ),
    Example(
        "m-inheritance-132",
        "A Subtype Selection with overlapping alternatives",
        "Animal.where(Animal.narrow(Dog, Pet))\n"
        '# raises ModelRejectedError(rule="subtype-selection-overlapping-alternatives")',
    ),
    Example(
        "m-inheritance-133",
        "A Subtype Selection with an exact duplicate",
        'Animal.narrow(Dog, Dog)\n# raises QueryDefinitionError(code="query-path-invalid")',
    ),
    # Rejected-case build/buffer-time proof: the write-side counterpart of the
    # read-side proofs above —
    # `tx.insert` refuses the SAME invalid write the corpus's own rejected
    # lane grades, through the SAME model-aware `validate_write`
    # (`Transaction._buffer`), naming the SAME classified rule — proven by
    # `test_idiomatic_write_build_rejects_the_corpus_rule`
    # (`tests/api/test_write_no_drift.py`).
    Example(
        "m-inheritance-088",
        "A keyed write aimed at an abstract inheritance position",
        'db.transact(lambda tx: tx.insert(Payment(id=10, amount=Decimal("200.00"))))\n'
        '# raises WriteRejectedError(rule="abstract-write-target")',
    ),
    Example(
        "m-value-object-039",
        "A write missing a required value-object attribute at depth 1",
        "db.transact(\n"
        "    lambda tx: tx.insert(\n"
        "        Contact(\n"
        "            id=1,\n"
        '            name="Acme",\n'
        "            address=ContactAddress(\n"
        '                city="Oslo", geo=ContactGeo(country="NO", '
        "point=ContactPoint(lat=59.9, lon=10.7))\n"
        "            ),\n"
        "        )\n"
        "    )\n"
        ")\n"
        '# raises WriteRejectedError(rule="write-required-attribute-missing")',
    ),
    Example(
        "m-value-object-040",
        "A write missing a required value-object attribute at depth 2",
        "db.transact(\n"
        "    lambda tx: tx.insert(\n"
        "        Contact(\n"
        "            id=2,\n"
        '            name="Beacon",\n'
        "            address=ContactAddress(\n"
        '                street="1 Main St",\n'
        '                city="Oslo",\n'
        "                geo=ContactGeo(point=ContactPoint(lat=59.9, lon=10.7)),\n"
        "            ),\n"
        "        )\n"
        "    )\n"
        ")\n"
        '# raises WriteRejectedError(rule="write-required-attribute-missing")',
    ),
    Example(
        "m-value-object-041",
        "A write missing a required value-object attribute at depth 3",
        "db.transact(\n"
        "    lambda tx: tx.insert(\n"
        "        Contact(\n"
        "            id=3,\n"
        '            name="Cairn",\n'
        "            address=ContactAddress(\n"
        '                street="2 Fjord Vei",\n'
        '                city="Bergen",\n'
        '                geo=ContactGeo(country="NO", point=ContactPoint(lon=5.3)),\n'
        "            ),\n"
        "        )\n"
        "    )\n"
        ")\n"
        '# raises WriteRejectedError(rule="write-required-attribute-missing")',
    ),
    Example(
        "m-value-object-042",
        "A write missing a required NESTED value object entirely",
        "db.transact(\n"
        "    lambda tx: tx.insert(\n"
        "        Contact(\n"
        "            id=4,\n"
        '            name="Delta",\n'
        '            address=ContactAddress(street="3 Harbour Rd", city="Oslo"),\n'
        "        )\n"
        "    )\n"
        ")\n"
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
    # grading the mirrored case's own oracle (a `then.graph` position, a
    # closed-world `UnloadedRelationshipError`, a `pin`/`edge_of` coordinate, or
    # a scenario's own per-step observable, `sameObjectAs` included).
    *(Example(story.case_id, story.title, graph_story_snippet(story)) for story in GRAPH_STORIES),
    # The joined transaction under an installed Provider (m-execution-lifecycle):
    # the case's own oracle states the whole delivered stream and the boundary
    # runner grades it, so what this executable story adds is the SPELLING no
    # oracle can state — the Provider named at composition, the fresh Handler
    # per root, and events arriving while the boundary runs rather than a record
    # read back after it. Executed against real Postgres by
    # `tests/api/test_execution_lifecycle_story.py`.
    Example(
        "m-execution-lifecycle-006",
        "A joined unit of work is observed inside the OUTER transaction attempt",
        execution_lifecycle_stories.joined_lifecycle_snippet(),
    ),
]

# Primary module -> reason its active cases have no idiomatic API example.
# The registry is intentionally independent of the active slice, so an active
# case absent from both registries fails the coverage partition. Per-story
# clocks are factories, allowing temporal stories to use distinct
# Transaction-Time instants without sharing exhausted clock state.
SKIP_REASONS: Final[dict[str, str]] = {
    "m-core": (
        "m-core neutral-type behaviour has no standalone developer surface; it is "
        "exercised through the read path"
    ),
    "m-descriptor": (
        "descriptor introspection is proven by the descriptor no-drift guard; the read "
        "path compiles/runs its descriptor cases"
    ),
    "m-document-codec": (
        "the portable document encoding has no developer surface of its own: a leaf's "
        "spelling is never named, chosen, or observed by an application, which is the "
        "module's reason to exist. Its comparison decisions are graded byte-exact by "
        "the compile/run lanes over `models/document-codec.yaml`, whose declaration — "
        "one leaf of every neutral type inside one occurrence — is itself mirrored by "
        "idiomatic classes and proven equivalent by the descriptor no-drift guard; its "
        "two encoding witnesses are writeSequence cases the reference harness executes "
        "against both engines"
    ),
    "m-predicate": (
        "representative predicate and grouping spellings are exercised as idiomatic "
        "examples; the remaining cases in this bucket are graded through the "
        "compile/run lanes"
    ),
    "m-object-query": (
        "the ordering-and-cap spelling is exercised as an idiomatic example "
        "(`m-object-query-003`); the remaining clause witnesses — the single-key "
        "orderings, all four Null Placement combinations, the rejected Sort Key "
        "position, and the ordered narrowed include root — vary the query VALUE a "
        "developer builds rather than the call that builds it, which is one "
        "`order_by(...).limit(...)` story restated per clause value, so they are "
        "graded byte-exact through the compile/run lanes instead"
    ),
    "m-temporal-read": (
        "the representative as-of spelling is exercised as an idiomatic example; the "
        "remaining temporal-read cases — including the optimistic-lock temporal-close "
        "conflict/retry witnesses "
        "(`m-temporal-read-009`..`-012`: gated success, stale-`in_z` conflict, the "
        "`when.attempts` 0-then-1 retry, and the locking-mode non-retriable stale close) "
        "— are graded end-to-end by the case-driven boundary runner "
        "(`tests/api/test_boundary_run.py`, driving the REAL db.transact "
        "against the provisioned database through a fault-injecting port decorator): a "
        "gated-retry/conflict choreography has no single-callback idiomatic spelling "
        "distinct from what the boundary runner already exercises directly"
    ),
    "m-db-error": (
        "the m-db-error corpus cases are graded end-to-end by the run lanes — the "
        "single-connection triggers by the error run sweep, the two-connection "
        "choreography by the case-driven concurrency rounds runner "
        "(`parallax.conformance.concurrency_runner`); the neutral DatabaseError surface "
        "the developer sees "
        "is exercised through the transact abort/retry unit tests"
    ),
    "m-pk-gen": (
        "write-side id allocation (`max`/`sequence`) is graded end-to-end by the "
        "compile/run conformance lanes; no idiomatic story exists, because a "
        "pk-generated column (`pkGenerator: max`/`sequence`) lacks the "
        "construction-optionality treatment axis-governed columns carry (a caller cannot "
        "honestly construct a fresh instance naming a server-computed id), and the "
        "optional-at-construction surface covers axis columns only "
        "(`m-pk-gen-014`'s own case-scoped entry below names the same blocker)"
    ),
    "m-auto-retry": (
        "the bounded retry loop is implemented (parallax.core.auto_retry) and proven "
        "by fake-port unit tests of db.transact (test_database_transact), including the "
        "optimistic-lock opt-in classification; the five boundary-shape cases (transient "
        "retry with the opt-in unset/set, the opt-in inert in locking mode, `retries: 0` "
        "disabling the loop, and bound exhaustion) are graded end-to-end by the "
        "case-driven boundary runner (`tests/api/test_boundary_run.py`, "
        "driving the REAL db.transact against the provisioned database through a "
        "fault-injecting port decorator): a retry/backoff choreography has no "
        "single-callback idiomatic developer spelling distinct from what the boundary "
        "runner already exercises directly"
    ),
    "m-opt-lock": (
        "the predicate-selected / materializing write forms (the readless "
        "unversioned/non-temporal exception, and the versioned materialize-then-lower "
        "family) are graded end-to-end by the compile/run conformance lanes (the "
        "readless forms) or the run lane alone (the materializing ones, "
        "query-result-dependent). The versioned keyed LOCKING-mode advance has an "
        "idiomatic story (`m-opt-lock-002`); the OPTIMISTIC-mode forms have none, for "
        "two DIFFERENT reasons: `-005` and `-007` are stale-gate cases whose competing "
        "writer is applied out of band (`given.apply`), which no single-session story "
        "can stage, while `-006` and `-013` are single-session SUCCESSES needing no "
        "second writer at all — their developer spelling is the exercised `m-opt-lock-002` "
        "story's observe-edit-update, taken under optimistic concurrency, and what they add "
        "is framework-emitted SQL no caller spells (the `and version = ?` gate optimistic "
        "mode renders, and the multi-column SET ordering ahead of ONE version advance). The "
        "auto-retry conflict-lane witness (`-009`), the boundary runner's "
        "conflict-opt-in pair (`-010`/`-011`), and the interleaved two-session race "
        "(`-012`, over the `peer` seam) each have their own case-scoped entry below"
    ),
    "m-txtime-write": (
        "the milestone-chaining write forms (insert / close-and-chain update / "
        "terminate, plus the TPH/TPCS and value-object compositions) are graded "
        "end-to-end by the compile/run conformance lanes. Idiomatic stories exist for "
        "the insert / terminate / close-and-chain-update family "
        "(`m-txtime-write-001`..`-005`, each over a per-story scripted clock, which is "
        "what lets one story chain milestones across several Transaction-Time "
        "instants). The optimistic-gated close (`-006`, a single-session success whose "
        "observed `in_z` is FRESH, so what it adds over the exercised chaining-update "
        "stories is the framework-emitted `and in_z = ?` predicate on the closing UPDATE "
        "rather than a developer spelling) and the materializing predicate-write "
        "scenarios (`-007`/`-009`) have no idiomatic story, and are graded end-to-end by "
        "the compile/run conformance lanes (`-006`) or the run lane alone "
        "(`-007`/`-009`, query-result-dependent)"
    ),
    "m-bitemp-write": (
        "the rectangle-split write forms (insert / updateUntil / terminateUntil / plain "
        "update / plain terminate, the optimistic observed-in_z gate, and the "
        "TPH/TPCS compositions) are graded end-to-end by the compile/run conformance "
        "lanes. Idiomatic stories exist for the flagship insert / updateUntil "
        "rectangle split (`-001`), `insertUntil` (`-003`), the plain-update two-way "
        "degenerate (`-006`), and the plain insert (`-009`). The remaining cases have no "
        "idiomatic story, and what each is missing differs. `-002`/`-007` spell the "
        "TERMINATE half of the bounded/plain verb pair whose UPDATE half is exercised "
        "(`-001`/`-006`), so what distinguishes them is which segments the rectangle "
        "split leaves re-inserted. `-004`/`-008` add no second writer at all — their "
        "observed `in_z` is fresh and the gate matches — and what they grade beyond an "
        "exercised sibling is the framework-emitted `and in_z = ?` predicate no caller "
        "spells; `-005` is the stale-observation twin, and ITS staleness comes from a "
        "competing writer applied out of band (`given.apply`) that no single session can "
        "produce. `-010`..`-013` are predicate-selected writes whose `_where` verb the "
        "developer surface does carry, and what they pin is the per-resolved-row "
        "close-and-re-insert lowering. Every one of those distinctions is an emitted-SQL "
        "or concurrency-staging contract, graded end-to-end by the compile/run "
        "conformance lanes (or the run lane alone for the materializing ones, "
        "query-result-dependent)"
    ),
    "m-storage-layout": (
        "canonical physical composition has no standalone developer surface. Its "
        "positive witnesses (shared-table applicability and effective physical "
        "nullability, table-per-concrete-subtype ancestry with legal sibling Column "
        "reuse, and the top-level document slot's position after every scalar tier) "
        "are graded end-to-end by the compile/run conformance lanes over the "
        "`storage-layout` model, which places already-mirrored table-per-hierarchy, "
        "table-per-concrete-subtype, and value-object declarations in one descriptor "
        "so physical composition can be witnessed — it adds no declaration construct "
        "of its own, so it carries no class mirror to write an instance-native story "
        "against (`tests/_support/mirrored_models.py`'s own UNMIRRORED reason). Its physical "
        "Column and Table mapping rejects are model-declaration invariants the Rule "
        "Set classifies at model construction (a `MetamodelValidationError` issue), not "
        "a query or write the Usage Guide's statement- and verb-level examples "
        "could spell"
    ),
    "m-batch-write": (
        "the set-based collapse / readless / materialize forms (multi-row INSERT "
        "collapse, batched UPDATE, IN-list DELETE, readless predicate update/delete, "
        "and the versioned materialize-then-lower family) are graded end-to-end by the "
        "compile/run conformance lanes. The readless predicate delete has an idiomatic "
        "story (`m-batch-write-005`, `tx.delete_where`); the remaining forms have none, "
        "each for its own reason. `-001`/`-002`/`-003` are BUFFERED keyed writes — "
        "multi-row insert, per-key versus batched update, IN-list delete — spelling the "
        "same `tx.insert`/`tx.update`/`tx.delete` verbs the exercised `m-unit-work` "
        "stories show (`-001`/`-005`/`-006`/`-009`), and adding only the planner's "
        "COLLAPSE decision, an emitted-SQL contract the compile lane grades byte-exact. "
        "`-006` is the predicate-UPDATE complement of `-005`'s predicate delete, adding "
        "the SET column order its assignments render rather than a developer spelling of "
        "its own. The versioned per-key materialize (`-004`) carries its own case-scoped "
        "entry below"
    ),
}

# Case-scoped skips take precedence over the module registry. This lets a module
# be mostly exercised without a broad reason silently absorbing a case that
# loses its example; without an `m-unit-work` module entry, such a case fails the
# partition as "covered by neither."
_COALESCING_WITNESS_REASON: Final[str] = (
    "a same-transaction coalescing witness: it buffers an insert+update / insert+delete "
    "pair whose one-statement / zero-statement collapse is m-batch-write behavior — the "
    "planner folding is unit-pinned (test_write_lowering) and graded end-to-end by the "
    "compile/run conformance lanes too; no idiomatic story covers this exact "
    "same-transaction coalescing shape, for the m-batch-write bucket's own reason above"
)

_OBSERVED_STATE_COALESCING_REASON: Final[str] = (
    "an Observed-State Coalescing witness: several buffered writes settle against ONE "
    "observed state, and what the case grades is which single statement the flush emits "
    "for them. The developer spelling is ordinary — two `tx.update` calls, or an update "
    "then a delete — so an idiomatic story would narrate the verbs rather than the "
    "collapse, which is a planner property the compile/run conformance lanes already "
    "grade end to end and `tests/unit/test_write_claims.py` pins per rule"
)

_OBJECT_CLAIM_COALESCING_REASON: Final[str] = (
    "the same Observed-State Coalescing witness against a target that observes no state: "
    "an unversioned Non-Temporal row's writes claim the OBJECT, and what the case grades "
    "is the single statement the flush emits for two of them. The developer spelling is "
    "the ordinary keyed verb an idiomatic story already shows, so what would be narrated "
    "is the collapse — a planner property the compile/run conformance lanes grade end to "
    "end and `tests/unit/test_write_claims.py` pins per rule"
)

_OBSERVED_GENERATION_REASON: Final[str] = (
    "an observed-state KEYING witness: it grades which of a unit of work's several "
    "observed generations of one key a write settles against, which a case states by "
    "naming the find its value came from. A developer names it by holding the value that "
    "read returned, so there is nothing for an idiomatic story to spell — the reference "
    "exists because the corpus holds instructions rather than values"
)

# Remaining active cases under graph and inheritance modules use case-scoped
# reasons grouped by identical justification.

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
_TPCS_UNION_RESULT_SHAPE_REASON: Final[str] = (
    "the developer-facing spelling is `order_by(...)` / `.limit(...)`, already exercised "
    "as an idiomatic example (`m-object-query-003`), asked here of an abstract "
    "table-per-concrete-subtype target: the call a developer writes is identical and "
    "only the emitted statement differs, wrapping the union as a derived table so the "
    "result-shape tail has somewhere to land — which the compile/run lanes grade "
    "byte-exact on both dialects"
)
_TPH_POLYMORPHIC_EXISTS_SIBLING_REASON: Final[str] = (
    "a representative sibling of the exercised polymorphic-navigation examples "
    "(m-inheritance-070/071 for table-per-concrete-subtype; m-navigate-004/008/010 for "
    "the correlated-EXISTS form itself): the TPH analogue is the SAME "
    "EXISTS-over-effective-concrete-set mechanism, just the other inheritance strategy"
)
# A path-ROOT guard is authored by reaching an inherited relationship through a
# subtype (`Dog.owner`), so one class access spells exactly one subtype. Two guard
# relations need a multi-subtype `to` that no class access reaches: equivalence
# (`to: [Pet]` beside `to: [Cat, Dog]`) and proper overlap, which the family tree
# cannot produce from two single-class guards at all — any two of those are equal,
# disjoint, or nested. Both properties are graded by the corpus against the
# reference harness and by the planner's own unit tests, and the guard mechanism
# they share is executed for real by the three sibling stories.
_ROOT_GUARD_MULTI_SUBTYPE_SPELLING_UNREACHABLE_REASON: Final[str] = (
    "the guard relation needs a multi-subtype path-root guard (`to: [Cat, Dog]`), which no "
    "idiomatic spelling reaches: a root guard is authored by reaching an inherited "
    "relationship through ONE subtype class, and two single-class guards over one family "
    "are always equal, disjoint, or nested. Resolved-source-set hop identity at the root "
    "is graded by the corpus and by the planner's own unit tests, and the guard mechanism "
    "itself is executed for real (m-inheritance-074/075/076, `graph_stories.py`)"
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
# composition by m-temporal-read-003; the genuinely new mechanism (a
# concrete-target read resolves its family's
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
# for these — a permanent, structural non-fit, not a capability gap. Each of
# these four has an executed
# `then.graph` sibling proving the identical
# capability through the shipped surface (m-inheritance-106/-107/-108/-109,
# `graph_stories.py`) — these four row-form originals stay the values-lane witnesses
# permanently, cross-referencing their own instance-form sibling.
_INHERITANCE_MULTI_CONCRETE_PROJECTION_UNREACHABLE_REASON: Final[str] = (
    "a multi-concrete polymorphic PROJECTING read (an abstract-root read, or a narrow "
    "resolving to 2+ concretes) — the ROW-FORM (values-lane) original: `db.find` is "
    "instance-form, never row-form (python.md §4: the right observation is "
    "`type(node)`, not a flattened dict), so a flat `then.rows` comparison can never be "
    "reproduced from typed instances — a permanent, structural non-fit. Its own "
    "INSTANCE-FORM sibling (m-inheritance-106/-107/-108/-109 respectively) IS executed "
    "through `db.find` (`graph_stories.py`), proving the identical capability the OTHER "
    "way, so both lanes of the same behavior are expressed"
)

# Temporal inheritance-family termination splits into two skip reasons by which
# story the case is missing. The audit-only close's verb is exercised on a plain
# entity, so the family case adds only routing; the bitemporal terminations'
# verbs are exercised nowhere, on any surface.
_INHERITANCE_AUDIT_TERMINATE_REASON: Final[str] = (
    "an audit-only (Transaction-Time-Only) milestone close over a table-per-hierarchy or "
    "table-per-concrete-subtype family: graded end-to-end by the compile/run conformance "
    "lanes; no idiomatic story covers it because its developer spelling is the exercised "
    "`tx.terminate` close (`m-txtime-write-003`), typed at a concrete subtype, and what "
    "the family composition adds is table routing plus the shared-table tag guard — an "
    "emitted-SQL contract, not a spelling (the SAME posture the non-temporal "
    "inheritance-family write forms carry, `_INHERITANCE_WRITE_CONFORMANCE_LANE_REASON`)"
)
_INHERITANCE_BITEMPORAL_TERMINATE_REASON: Final[str] = (
    "a BITEMPORAL terminate / terminateUntil over a table-per-hierarchy or "
    "table-per-concrete-subtype family: graded end-to-end by the compile/run conformance "
    "lanes; no idiomatic story covers it because NO story spells a bitemporal "
    "termination at all — the exercised bitemporal stories are the insert and UPDATE "
    "halves (`m-bitemp-write-001`/`-003`/`-006`/`-009`), and the plain-entity TERMINATE "
    "halves these compose (`m-bitemp-write-007` plain, `-002` bounded) are themselves "
    "storyless for the `m-bitemp-write` bucket's own reason above. What the family "
    "composition adds over those is table routing plus the shared-table tag guard"
)
# The composed TPH/audit/optimistic-lock case is a CONFLICT shape, not a
# writeSequence: its skip turns on the staging its gate needs, not on a spelling
# an exercised story already shows.
_INHERITANCE_COMPOSED_CONFLICT_REASON: Final[str] = (
    "a table-per-hierarchy audit-only close GATED on a STALE observed Transaction-Time "
    "start (m-inheritance x m-txtime-write x m-opt-lock composed): graded end-to-end by "
    "the run lane; no idiomatic story covers it because the staleness it grades is "
    "produced by a competing writer applied out of band (`given.apply`), which one "
    "single-session callback cannot stage (the SAME posture the `m-opt-lock` stale-gate "
    "cases carry)"
)
# Non-temporal TPH/TPCS insert, update, and delete cases are graded end-to-end
# by the compile/run lanes, including deep-chain, sibling-branch, and
# optimistic-lock compositions. They have no idiomatic instance-native story.
_INHERITANCE_WRITE_CONFORMANCE_LANE_REASON: Final[str] = (
    "a non-temporal inheritance-family keyed write (table-per-hierarchy or table-per-"
    "concrete-subtype insert/update/delete, including the opt-lock composition pair): "
    "graded end-to-end by the compile/run conformance lanes; no idiomatic story covers "
    "an inheritance-family write, whose developer spelling is the plain-entity keyed "
    "write an exercised story already shows, typed at a concrete subtype"
)
# The abstract-root find licensing a concrete-subtype gated update is the one
# family write whose subject is NOT its write spelling: both halves of the
# observation it turns on are exercised, and what it pins is their junction.
_INHERITANCE_ABSTRACT_OBSERVATION_LICENSES_WRITE_REASON: Final[str] = (
    "an abstract-root find licensing the CONCRETE subtype's version-gated update: graded "
    "by the run lane alone (`compileEligibility: run-only` — the gate binds the version "
    "the group's OWN find returned). What it pins is not the write's spelling but the "
    "junction of two separately exercised halves: an abstract-root read resolving each "
    "row to its own concrete is executed for real (`m-inheritance-106`, "
    "`graph_stories.py`), and a write settling against the observation its own find "
    "produced is too (`m-unit-work-015`); no idiomatic story was authored for reading at "
    "the abstract root and naming the concrete in the write"
)
# The non-temporal optimistic-lock keyed write splits into two skip reasons: a
# stale gate needs a competing writer, while a matching gate needs none and is
# distinguished from its exercised locking-mode sibling only by emitted SQL.
_OPT_LOCK_STALE_GATE_SECOND_WRITER_REASON: Final[str] = (
    "a non-temporal optimistic-lock keyed write whose version gate is STALE when it "
    "runs (the 0-row conflict, and the 0-then-1 retry choreography over it): graded "
    "end-to-end by the run lane; no idiomatic story covers it because the staleness is "
    "produced by a competing writer applied out of band (`given.apply`), which one "
    "single-session callback cannot stage"
)
_OPT_LOCK_MATCHING_GATE_EMITTED_SQL_REASON: Final[str] = (
    "a non-temporal optimistic-lock keyed write whose version gate MATCHES — a "
    "single-session success needing no concurrent writer: graded end-to-end by the run "
    "lane; no idiomatic story covers it because its developer spelling is the exercised "
    "locking-mode advance's (`m-opt-lock-002`: observe, edit, update) taken under "
    "optimistic concurrency, and everything it adds is framework-emitted SQL no "
    "caller spells — the `and version = ?` gate optimistic mode renders, and the "
    "multi-column SET ordering ahead of ONE version advance"
)
# A versioned set-based delete refuses the IN-list collapse its unversioned
# sibling takes (m-batch-write-003) and lowers per resolved row instead.
_BATCH_WRITE_VERSIONED_MATERIALIZE_REASON: Final[str] = (
    "a versioned set-based delete's per-key materialize, running under the declared "
    "`locking` preference where each keyed delete is UNGATED: graded end-to-end by the "
    "run lane; no "
    "idiomatic story covers it because what it pins is the planner's refusal to collapse "
    "a versioned set delete into one IN-list statement, an emitted-SQL contract rather "
    "than a developer spelling (the resolving read half is proven by "
    "`m-opt-lock-003`/`-004`)"
)
# The auto-retry optimistic-conflict opt-in's conflict-lane witness uses
# `retryOptimisticConflicts: true` over a two-attempt, 0-then-1
# `when.attempts` choreography — the same
# caller-visible attempts-sequence lane `m-opt-lock-007` already exercises; the
# runtime auto-retry LOOP itself is `-011`'s own boundary witness, below.
_OPT_LOCK_CONFLICT_LANE_OPT_IN_REASON: Final[str] = (
    "the auto-retry optimistic-conflict opt-in's own conflict-lane witness "
    "(`retryOptimisticConflicts: true` over a two-attempt, 0-then-1 `when.attempts` "
    "choreography) is graded end-to-end by the run lane (the SAME caller-visible "
    "`when.attempts` choreography `m-opt-lock-007` already exercises; the runtime "
    "auto-retry loop itself is `m-opt-lock-011`'s own boundary witness); no idiomatic "
    "story was authored for this opt-in choreography — a retry/backoff choreography "
    "has no single-callback idiomatic developer spelling distinct from what the run "
    "lane already exercises directly"
)
# The auto-retry optimistic-conflict opt-in's boundary pair covers a conflict
# surfacing after one attempt without the
# opt-in (`-010`) / auto-retried to success with it (`-011`) — graded by the
# SAME case-driven boundary runner the `m-auto-retry` module bucket names.
_OPT_LOCK_BOUNDARY_RUNNER_REASON: Final[str] = (
    "the auto-retry optimistic-conflict opt-in's own boundary witness (the conflict "
    "surfacing after one attempt without the opt-in, or auto-retried to success with "
    "it) is graded end-to-end by the case-driven boundary runner "
    "(`tests/api/test_boundary_run.py`) against the real, provisioned "
    "database (the boundary runner's own generic action mapping is deliberately not "
    "itself an idiomatic developer surface); a retry/backoff choreography has no "
    "single-callback idiomatic developer spelling distinct from what the boundary "
    "runner already exercises directly"
)
# The interleaved two-session optimistic-lock race (`m-opt-lock-012`,
# `m-case-format` unit-of-work grouping) holds two concurrent
# `db.transact` units of work over the `Provisioner.peer` seam, sequenced in
# authored order — `parallax.conformance.engine.run_interleaved_scenario_case`.
_OPT_LOCK_INTERLEAVED_RACE_REASON: Final[str] = (
    "the interleaved two-session optimistic-lock race (two concurrently-held "
    "`db.transact` units of work over the `Provisioner.peer` seam, sequenced in "
    "authored order) is graded end-to-end by the run sweep's own interleaved-group "
    "runner (`parallax.conformance.engine.run_interleaved_scenario_case`); no idiomatic "
    "example exists (a two-connection race has no single-callback developer "
    "expression) — the reference harness remains its independent behavioral "
    "cross-check"
)
# The read-lock module's single-connection golden (`m-read-lock-001`) verifies
# that an object find resolving to the Locking strategy carries the shared read
# lock and is graded end-to-end by the compile and run sweeps. Its own declared
# `locking` preference is all it needs (its api-conformance-lane runtime
# siblings `-002` and `-005` are already exercised above).
_READ_LOCK_HARNESS_GOLDEN_REASON: Final[str] = (
    "the module's own harness-lane single-connection golden (a Locking-strategy "
    "object find carries the shared read lock) is graded end-to-end by the "
    "compile AND run sweeps; no idiomatic example is "
    "needed beyond the runtime matrix's own api-conformance siblings "
    "(`m-read-lock-002`/`-005`, exercised as idiomatic read-story examples "
    "above) — this witness needs nothing from `db.transact` beyond the "
    "`locking` preference the case itself declares"
)
_READ_LOCK_PARTITIONED_GOLDEN_REASON: Final[str] = (
    "the wire-level locking golden proves one outer base-row lock over the cast-safe "
    "tag-partitioned TPH document relation and is graded by the compile/run sweeps; "
    "the API suite's existing locking-mode object-find story already proves the "
    "developer Concurrency Preference surface, while this case isolates SQL shape"
)
# The read-lock module's two-session behavioral proofs
# (`m-read-lock-006`/`-007`/`-011`/`-012`) cover a genuine two-connection
# concurrency property (a shared lock blocking/admitting a writer or a second
# reader) no single-session idiomatic example can demonstrate — graded by the
# case-driven `when.concurrency` rounds runner instead.
_READ_LOCK_TWO_SESSION_REASON: Final[str] = (
    "the two-session behavioral proof (a Locking-strategy reader's shared lock "
    "blocking/admitting a writer or a second reader) is graded end-to-end by the "
    "case-driven `when.concurrency` "
    "rounds runner (`parallax.conformance.concurrency_runner`, "
    "`test_run_sweep.test_read_lock_concurrency_rounds`) — a genuine two-connection "
    "concurrency property no single-session idiomatic example can demonstrate; the "
    "reference harness remains its own independent cross-check"
)
# `m-pk-gen-014` composes a non-temporal sequence-registry update with an
# Transaction-Time-Only insert in one write sequence and two transactions. It is graded
# end-to-end but has no idiomatic story.
_PK_GEN_TEMPORAL_INSERT_REASON: Final[str] = (
    "a `sequence`-strategy primary-key allocation on a TEMPORAL entity (a non-temporal "
    "registry UPDATE composed with a Transaction-Time-Only INSERT in one writeSequence): "
    "graded end-to-end by the compile/run "
    "conformance lanes; no idiomatic story exists — the SAME pk-generated-column "
    "construction-optionality blocker the `m-pk-gen` module-bucket reason above names"
)
####################################################################################
# Subtype-write payload-shape rejects (`validate_write` /                         #
# / `parallax.core.inheritance.validate_subtype_write`): the rejected sweep         #
# grades all four (m-inheritance-086..089) through the SAME shared validator        #
# `Transaction._buffer` calls (`test_transaction_writes.py`'s per-rule unit tests exercise#
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
    "`tx.insert`/`tx.update` through it — `test_transaction_writes.py` exercises the "
    "classified rule directly at the neutral seam (`Transaction._buffer`) instead. The same "
    "holds for the keyed-instruction twin (m-inheritance-131), whose row carries the sibling "
    "column alone: the typed surface reaches `Transaction._buffer` only through an instance, "
    "and the instance cannot carry the field"
)
_INHERITANCE_METADATA_FIELD_UNREACHABLE_REASON: Final[str] = (
    "an authored `tagValue` has no idiomatic spelling: it is framework-owned metadata "
    '(m-inheritance "Metadata is framework-owned, never authored"), derived from '
    "`inheritance=ConcreteSubtype(tag_value=...)` at CLASS-DEFINITION time, never a "
    "per-instance Pydantic field a caller can pass to `tx.insert`/`tx.update` — "
    "`test_transaction_writes.py` exercises the classified rule directly at the neutral "
    "seam (`Transaction._buffer`) instead"
)
_INHERITANCE_SET_BASED_UNSUPPORTED_UNREACHABLE_REASON: Final[str] = (
    "the idiomatic spelling EXISTS: `subtype-write-set-based-unsupported`'s natural "
    "developer-facing trigger is a set-based `_where` verb (`tx.update_where` / "
    "`tx.delete_where`) targeting an inheritance family (python.md §5, refused by "
    "`inheritance.reject_predicate_write`) — "
    "`test_transaction_predicate_writes.py` exercises it through `tx.update_where`; the "
    "rejected-case's OWN keyless-row shape (`m-inheritance-089`) still has no idiomatic keyed "
    "spelling (no single typed instance construction denotes a payload with no primary key at "
    "all), so this remains a reasoned skip for the CASE's OWN authored shape — a permanent, "
    "structural non-fit, not a deferred story"
)

# `when.model` descriptor-shape rejects (m-inheritance-020..032, plus the
# root-ownership witnesses 098/099/129, plus the optimistic-
# locking root-ownership witnesses 102/103): a DIFFERENT validation surface
# than the Object Query rejected lane.
# `parallax.descriptor.validate_inheritance_families` classifies these exact rules for a raw
# descriptor, and the class grammar reaches most of them through a different
# surface: hierarchy-derived `parent`/`role` makes most of these shapes
# unspellable at all (Python's own class system additionally forbids a literal
# inheritance cycle), while the ones that stay spellable — a table on an
# abstract node, a descendant extending a temporal base of its own
# (098/099, `inheritance-temporality-not-root-owned`), a descendant declaring
# its own `optimisticLocking` attribute (102/103,
# `inheritance-optimistic-locking-not-root-owned`, ADR 0027) — are rejected
# either at class creation as an `EntityDefinitionError` or at model construction
# as the shared formation-time `inheritance-*` issue
# (`test_inheritance_frontend.py`), never as `InheritanceError.rule`. No case in
# this group can therefore reproduce `then.rejectedRule` through the public
# class surface.
_INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON: Final[str] = (
    "a `when.model` raw-descriptor invariant `descriptor.validate_inheritance_families` "
    "classifies (parent/root/cycle/strategy/tag/temporal-axis-ownership/optimistic-"
    "locking-ownership/layout-ownership shape) — the class metaclass never calls this "
    "validator ("
    "`parent`/`role` are DERIVED from the live Python class hierarchy, never separately "
    "authored, so most of these malformed shapes — an unknown parent, a cycle, multiple "
    "roots, a missing root, a redeclared strategy, a duplicate/misplaced tag — have no "
    "idiomatic spelling at all); the table-placement rules AND a descendant's own "
    "temporal base / `optimisticLocking` ARE independently authorable, but the class "
    "frontend's own existing checks raise a different, unclassified error in each case, "
    "not `InheritanceError.rule` — so reaching the classified vocabulary idiomatically "
    "would need a frontend path that does not exist, which is a structural non-fit "
    "rather than a missing story"
)

# `navigate`-tagged corpus siblings: a deliberate spelling redundancy for the
# IDENTICAL correlated-EXISTS lowering the exercised `.exists()`/`.not_exists()` examples
# already prove (m-navigate-002/003/004/006/008/009/010) — m-predicate's own
# framing ("navigate and exists are the same correlated-EXISTS lowering").
_NAVIGATE_TAG_REDUNDANT_REASON: Final[str] = (
    "a `navigate`-tagged corpus spelling redundancy for the IDENTICAL correlated-EXISTS "
    "lowering the exercised `.exists()`/`.not_exists()` examples already prove "
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

# The Relational Document Layout relationship witnesses. Both traverse the very
# relationship shapes an executed story already spells; what they pin is where the
# layout PUT each level's members, which no developer surface names.
_DOCUMENT_LAYOUT_RELATIONSHIP_REASON: Final[str] = (
    "a relationship traversal over Relational Document Layout: the developer spelling "
    "is the ordinary hop / deep fetch the exercised orders stories already show, and "
    "what this case pins is physical — that both join endpoints keep Columns while "
    "every other member moves into each level's one Structured Column, which is "
    "`m-storage-layout`'s subject and has no developer surface. The classes for "
    "models/document-layout.yaml live in the test-support mirror rather than in this "
    "package, so no story can be written against them here"
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
# own polymorphic owner (ALSO named `Person`) both name one canonical Entity,
# which is unremarkable once a model is an explicit class set: they are
# different classes in different models (`read_models.PERSON_MODEL` and
# `animal_owner.ANIMAL_MODEL`), so both flip to executable graph stories
# (`graph_stories.py`) and no case-scoped reason remains for either.
#
# Milestone-set GRAPH siblings of the executed history proof. `history` /
# `as_of_range` over a Transaction-Time entity answers one edge-pinned graph per
# milestone (`then.graphs`), and the shipped-surface half of that — a real
# `db.find(... .history(TX_TIME))` against Postgres resolving two milestones of
# one domain key as distinct edge-pinned nodes — is executed and graded as the
# supplemental `graph_stories.history_of_a_concrete_temporal_node_
# distinguishes_milestones`. The wire half is graded for these two cases
# THEMSELVES: both are compile-exercised and run-exercised
# (`sweep_goldens._SNAPSHOT_READ_MILESTONE_SET_READS`), materializing and
# grading their own `then.graphs`. Neither case combines a scan with an include
# — neither query carries Includes at all — so the deferred
# `snapshot-history-includes` Feature says nothing about them.
_MILESTONE_SET_GRAPH_SIBLING_REASON: Final[str] = (
    "a representative sibling of the executed milestone-set graph proof "
    "(`graph_stories.history_of_a_concrete_temporal_node_distinguishes_milestones`, "
    "real-Postgres via `parallax.snapshot.connect` + `db.find(....history(TX_TIME))`, "
    "resolving one key's two milestones as distinct edge-pinned nodes): the SAME "
    "per-milestone partition and edge pin over a different model, and — for "
    "`m-snapshot-read-014` — with `as_of_range`'s overlap window in place of the full "
    "chain; both cases are themselves graded end-to-end by the compile AND run sweeps, "
    "which materialize their own `then.graphs`"
)

_STREAMED_DELIVERY_REASON: Final[str] = (
    "the corpus's streamed-delivery lane, whose claim is the PAGE PARTITION rather than "
    "the values published: the size each page asks for, the Continuation Order coordinates "
    "each later page seeks from, and the statement a full final page costs to prove "
    "exhaustion. An idiomatic story publishes roots and never statements, so one over "
    "`db.stream` would grade the graph its eager sibling already grades and nothing that "
    "makes the case a streamed one. Both halves are graded for real elsewhere: the run "
    "sweep drives `db.wire.stream` itself against real Postgres, compares every statement "
    "the delivery executed to the authored pages, and materializes the case's own "
    "`then.graph`; and the delivery contract the surface adds on top — single pass, one "
    "view, scope binding, the cursorless-root rule, and page-size invariance in BOTH "
    "namespaces — is graded against the shipped surface by `tests/unit/test_snapshot_stream.py`"
)

# The composition family's Transaction-Time-only arm. `m-snapshot-read-021`
# reads `models/invoice.yaml`, which this package deliberately authors no
# idiomatic class family for (`tests/_support/mirrored_models.UNMIRRORED`: the
# model composes `balance`'s transaction-time-only axis with `orders`' dependent
# one-to-many, both mirrored already), so hosting a story for it means reversing
# that recorded partition rather than writing a story. What a story adds over the
# two wire executors is reference identity of the surviving view, and that is a
# materialization property rather than a write-verb one: `-020` proves it across
# the destructive verb and `-025` across the bitemporal rectangle split, which is
# the same coordinate rewrite this case performs on one axis instead of two.
_COMPOSITION_UNMIRRORED_MODEL_REASON: Final[str] = (
    "a representative sibling of the executed composition stories "
    "(m-snapshot-read-020 across a delete, m-snapshot-read-025 across a bitemporal "
    "rectangle split): the surviving view's reference identity is a materialization "
    "property, not a write-verb one, and this case's own composition is graded "
    "end-to-end by BOTH wire executors — golden close DML, `roundTrips: 0` on the "
    "access, the contents its `expectGraph` states, and the read-back that shows "
    "Latest moved. Its model (`models/invoice.yaml`) is one this package authors no "
    "idiomatic class family for by the recorded mirrored-model partition"
)

# Value-object nested/absence/cast/array-traversal PREDICATE reads: rows-form,
# representative siblings of the Customer.address predicate graph stories NOW
# EXECUTED for real (m-value-object-001/002/007/015/016/017/019 in
# `graph_stories.py`, via the installed
# `vo_models.Customer`/`Location`/`Depot` mirror) — the SAME
# nested-path resolution / absence-collapse / any-element lowering, a
# different operator, depth, or dialect-cast variant: no distinct developer-
# facing shape to add, the SAME mechanism already proven against Postgres.
_VO_PREDICATE_SIBLING_REASON: Final[str] = (
    "a representative sibling of the Customer.address predicate graph stories now "
    "executed for real (m-value-object-001/002/007/015/016/017/019, `graph_stories.py`): "
    "the SAME nested-path resolution / absence-collapse / any-element lowering, a "
    "different operator, depth, or dialect-cast variant — no distinct developer-facing "
    "shape to add, the SAME mechanism already proven against Postgres"
)

# Value-object STRUCTURE rejects: each empirically confirmed (a REPL probe
# against the shipped surface) to have NO idiomatic spelling that reaches
# `validate_predicate` with the corpus's own invalid shape — four DISTINCT
# failure modes, not one generic gap.
_VO_UNKNOWN_NESTED_FIELD_REASON: Final[str] = (
    "`Customer.contact` (the invalid path's first segment) is not a declared "
    "attribute at all: `vm.Customer.contact.city == ...` raises a plain Python "
    "`AttributeError` at attribute-access time — before any predicate exists to "
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
    "`Customer.address.exists()` builds successfully, but to a DIFFERENT, valid predicate "
    "(`nestedExists`, the to-many VO presence quantifier m-value-object-015/016 already "
    "exercise) — not the corpus's invalid `navigate` node targeting a value object; the "
    "idiomatic surface has no spelling that produces THAT exact shape, only a "
    "differently-typed valid one"
)

# Value-type mismatch (m-value-object-043): empirically confirmed (a REPL
# probe against the shipped surface) to have NO idiomatic spelling through
# `tx.insert` — `ContactAddress(street=42, ...)` raises Pydantic's own
# `ValidationError` (a `str` field never coerces an `int`) before the
# instance can even be constructed, let alone reach `validate_write`. Its
# four Contact/Shipment siblings (`-039..042`/`-044`) do have an idiomatic
# spelling through `vo_models.py` and are exercised as build-time proofs
# above. This case is a sanctioned exception because its invalid input is
# unrepresentable through the typed surface.
_VO_PORTABLE_LITERAL_UNREACHABLE_REASON: Final[str] = (
    'the case authors a WIRE literal — the string `"-0.00"` at a `decimal(12,2)` — and the '
    "typed surface has no position for one: `SampleProfile.amount` is a `decimal.Decimal` "
    "field, so a developer hands over a native `Decimal` the input policy never parses "
    "(`coerce_neutral_input` admits no string for a `Decimal`), and Pydantic refuses the "
    "string before construction. The portable literal grammar this case pins belongs to the "
    "serde ingress (`decode_neutral_literal`), which `test_metamodel_values.py` exercises "
    "directly; there is no idiomatic spelling that routes a wire literal through `tx.insert`"
)

_VO_VALUE_TYPE_MISMATCH_UNREACHABLE_REASON: Final[str] = (
    "`ContactAddress(street=42, ...)` raises Pydantic's own `ValidationError` (a `str` "
    "field never coerces an `int`) before the instance can even be constructed, let alone "
    "reach `validate_write` — the type system itself prevents authoring the corpus's "
    "invalid value-type-mismatch shape through `tx.insert`; its four Contact/Shipment "
    "siblings (`-039..042`/`-044`) DO have an idiomatic spelling and are exercised as "
    "build-time proofs against the installed mirror. This case's own skip is a "
    "sanctioned exception: Pydantic's own field-level coercion makes the "
    "corpus's invalid shape structurally unrepresentable through the typed surface, not "
    "a coverage gap this frontend can idiomatically close"
)

# Depth-0 write validation (m-value-object-069/070): the SAME sanctioned
# exception one level out. The corpus grades a bare `when.write` row against the
# ENTITY's own Attributes, and this frontend declares each of them a Python field,
# so a missing required Attribute and an uncoercible literal are refused at
# construction and neither shape can reach a validator.
_VO_DEPTH_ZERO_ATTRIBUTE_UNREACHABLE_REASON: Final[str] = (
    "the defect sits at the ENTITY's own Attribute, which this frontend declares as a "
    "Python field: `Contact(id=1, address=...)` (omitting the required `name`) and "
    "`Contact(id='five', ...)` each raise Pydantic's own `ValidationError` before the "
    "instance exists, let alone reaches `validate_write`. Same sanctioned exception as "
    "m-value-object-043's, one level out from the document: the type system prevents "
    "authoring the invalid shape, so this is not a coverage gap the frontend can close"
)

# Occurrence-shape write validation (m-value-object-071/072/073): a Value Object
# member position admits only its own class (or, for a `many`, a tuple of them), so
# the frontend refuses a scalar there with its OWN TypeError before any validator
# runs — a stronger refusal than Pydantic's, and equally unreachable.
_VO_OCCURRENCE_SHAPE_UNREACHABLE_REASON: Final[str] = (
    "a Value Object member accepts only an instance of its class — never a raw mapping "
    "and never a scalar — so `Contact(address='1 Main St')`, `phones='555'`, and "
    "`phones=('555',)` each raise the frontend's own `TypeError` at construction "
    "(\"requires a 'ContactAddress' instance\" / \"requires a tuple of 'ContactPhone' "
    "instances\" / \"element '555' is not a 'ContactPhone' instance\"), before "
    "`validate_write` sees anything. Same sanctioned exception as m-value-object-043's: "
    "the type system prevents authoring the corpus's invalid occurrence shape"
)

# The remaining value-object write-family siblings each use the matching
# module-level reason above.
_VO_BATCH_WRITE_REASON: Final[str] = (
    "a multi-row (batched) insert, each row's whole value-object document carried as "
    "one atomic document bind — the set-based flush collapse is graded "
    "end-to-end by the compile/run conformance lanes, matching this registry's own "
    "m-batch-write bucket reason; no idiomatic story was authored for this VO-bearing "
    "batched shape"
)
_VO_OPT_LOCK_CONFLICT_REASON: Final[str] = (
    "a versioned write under an optimistic-lock gate over a value-object-bearing "
    "entity: the m-opt-lock keyed-write machinery is graded end-to-end by the "
    "compile/run conformance lanes; no idiomatic story was authored for this VO-bearing "
    "optimistic-conflict shape, matching this registry's own m-opt-lock bucket reason"
)
# The finite-pin mutation contrast pair (a finite Valid-Time pin stays writable;
# a finite Transaction-Time pin is read-only) is graded end-to-end by the run
# sweep through the conformance adapter's `errors` observation, and the
# developer-facing refusal itself is unit-pinned at every keyed verb.
_BITEMP_PIN_CONTRAST_REASON: Final[str] = (
    "the finite-pin mutation contrast witness (a finite Valid-Time pin stays writable — "
    "the retroactive correction; a finite Transaction-Time pin is read-only, "
    "`transaction-time-pin-read-only`): graded end-to-end by the run sweep's "
    "`expectError` grading through the adapter's `errors` observation "
    "(`m-conformance-adapter`), and the developer-facing refusal itself is unit-pinned "
    "at every keyed verb (`TransactionTimePinReadOnlyError`, "
    "test_transaction_writes.py); no idiomatic story exists beyond that refusal — the "
    "writable half's full rectangle-split lowering already has its own idiomatic story "
    "(`m-bitemp-write-006`)"
)

_PER_VIEW_PIN_REASON: Final[str] = (
    "the per-view mutation witness (two reads of ONE primary key at coordinates "
    "resolving to DIFFERENT milestones leave two independently pinned views, so the "
    "mutation verb answers per view rather than per key): graded end-to-end by the run "
    "sweep's `expectError` grading through the adapter's `errors` observation "
    "(`m-conformance-adapter`) — accepted on the Valid-Time-pinned view, "
    "`transaction-time-pin-read-only` on the Transaction-Time-pinned one — and the "
    "refusal itself is unit-pinned at every keyed verb (test_transaction_writes.py); "
    "the idiomatic spelling is the ordinary find-then-mutate every managed story "
    "already shows, twice"
)

_VO_SCENARIO_COMBO_REASON: Final[str] = (
    "a scenario combining a managed (instance-form) find, a MATERIALIZING "
    "predicate-write resolving read (row-form, widened to project the VO document "
    "because the Temporal Observation it records is a complete Predecessor Row — the "
    "widening this case pins), and a txtime-write terminate under an "
    "optimistic-lock gate: the materializing predicate-write machinery (m-txtime-write / "
    "m-opt-lock / m-batch-write's readless/materialize split) is run-lane covered "
    "(query-result-dependent, `compileEligibility: run-only`); no idiomatic story was "
    "authored for this multi-capability combination scenario"
)
_VO_VERSIONED_RESOLVE_SCENARIO_REASON: Final[str] = (
    "the versioned counterpart of that scenario: a managed (instance-form) find and a "
    "MATERIALIZING predicate-write resolving read over the SAME predicate, where the "
    "resolve keeps the row-form default (pk + version only, the VO document omitted) "
    "because a Version Observation retains no predecessor row, followed by a "
    "version-gated per-row delete. The same materializing predicate-write machinery is "
    "run-lane covered (query-result-dependent, `compileEligibility: run-only`); no "
    "idiomatic story was authored for this multi-capability combination scenario"
)

_METAMODEL_MODEL_REJECT_UNREACHABLE_REASON: Final[str] = (
    "a `when.model` foundational Metamodel invariant the fixed resolver classifies at "
    "model construction (a `MetamodelValidationError` issue), not a query or write "
    "the Usage Guide's statement- and verb-level examples could spell. The class "
    "frontend reaches the SAME issue — it derives the primary-key Index and hands it to "
    "the same resolver, so an `indices=` entry claiming the derived name is refused "
    "identically (`test_domain_model.py` exercises it at that seam) — but the "
    "observable is a rejected model, not a developer verb an idiomatic story can narrate"
)

_TEMPORAL_KEYED_SINGLETON_UNREACHABLE_REASON: Final[str] = (
    "the rule is live and enforced on the developer path — `validate_instruction` refuses a "
    "plural keyed instruction on a temporal target before `Transaction._buffer` buffers it, "
    "and `WritePlanner._settle_temporal` refuses it again as the last structural check before "
    "SQL — but the CASE's own authored shape has no idiomatic spelling: every typed keyed verb "
    "(`tx.update` / `tx.terminate` / their bounded siblings) takes ONE instance and emits an "
    "instruction of one row, so no sequence of developer calls can construct the plural "
    "instruction this case authors. A permanent structural non-fit, not a deferred story"
)

_WRITE_VALUE_PROVENANCE_REASON: Final[str] = (
    "a keyed write value-provenance witness (m-unit-work *Write value provenance*, "
    "m-case-format *Keyed write action steps*): graded end-to-end by the case-driven "
    "write-value runner (`tests/api/test_write_value_run.py`, driving the REAL "
    "`tx.insert` / `tx.update` against the provisioned database, and "
    "`tests/unit/test_write_value_runner.py` Docker-free), which arranges each stated "
    "provenance through the source that produces it: a read through the source under "
    "test, a read through the second managed source the adapter supplies "
    "(`another_source.AnotherSource`), and a plain construction for the one token no "
    "managed read produced. The runner's generic "
    "provenance-to-value mapping is deliberately not a per-case hand function, and the "
    "refusals themselves are unit-pinned at every keyed verb "
    "(`KeyedWriteValueError`, test_transaction_writes.py); the idiomatic spelling is "
    "the ordinary find-then-write every managed story already shows, called with the "
    "value the other verb accepts"
)

_EXECUTION_LIFECYCLE_SWEEP_GRADED_REASON: Final[str] = (
    "the harness-lane half of the m-execution-lifecycle spine: each carries golden SQL and "
    "its `then.executionLifecycle` oracle is graded end-to-end by the run sweep "
    "(`tests/compatibility/test_run_sweep.py`) against the stream a REAL execution delivered "
    "to an installed Provider. The observable is the delivery itself rather than a developer "
    "verb — an application reaches it by naming a Provider at `connect`, which the joined "
    "story above already shows — so an idiomatic example would narrate the same seam twice"
)

_EXECUTION_LIFECYCLE_BOUNDARY_RUNNER_REASON: Final[str] = (
    "an m-execution-lifecycle spine case whose stream needs an injected fault and an "
    "exhausted retry bound — observables a single-connection harness cannot provoke — "
    "graded end-to-end by the case-driven boundary runner "
    "(`tests/api/test_boundary_run.py`), which drives the REAL `db.transact` against the "
    "provisioned database and compares the whole delivered stream to the case's own "
    "`then.executionLifecycle`. A retry/exhaustion choreography has no single-callback "
    "idiomatic spelling distinct from what that runner already exercises directly"
)

_EXECUTION_LIFECYCLE_STREAMED_ROOT_REASON: Final[str] = (
    "the m-execution-lifecycle spine's streamed arm: its `then.executionLifecycle` oracle is "
    "graded end-to-end by the run sweep (`tests/compatibility/test_run_sweep.py`) against the "
    "stream a REAL `db.wire.stream` delivered to an installed Provider, and the spelling an "
    "application reaches that stream through — a Provider named at `connect` — is the one the "
    "joined story above already shows. What a streamed story would ADD is the page partition, "
    "which is what an idiomatic example cannot show at all: it publishes roots and never "
    "activities, so it would grade the graph the eager sibling already grades. The stream's "
    "own activity tree — a root of its own, one Stream Batch per page, and per-root "
    "publication outside every batch — is graded against the shipped surface by "
    "`tests/unit/test_execution_lifecycle_stream.py`"
)

CASE_SKIP_REASONS: Final[dict[str, str]] = {
    # -- m-execution-lifecycle: the spine's own two graders -------------------- #
    # (`-006` is an exercised story above: the composition spelling no oracle states)
    "m-execution-lifecycle-001": _EXECUTION_LIFECYCLE_SWEEP_GRADED_REASON,
    "m-execution-lifecycle-002": _EXECUTION_LIFECYCLE_SWEEP_GRADED_REASON,
    "m-execution-lifecycle-003": _EXECUTION_LIFECYCLE_SWEEP_GRADED_REASON,
    "m-execution-lifecycle-004": _EXECUTION_LIFECYCLE_BOUNDARY_RUNNER_REASON,
    "m-execution-lifecycle-005": _EXECUTION_LIFECYCLE_BOUNDARY_RUNNER_REASON,
    "m-execution-lifecycle-007": _EXECUTION_LIFECYCLE_STREAMED_ROOT_REASON,
    "m-unit-work-008": _COALESCING_WITNESS_REASON,
    "m-unit-work-010": _COALESCING_WITNESS_REASON,
    "m-unit-work-021": _OBSERVED_STATE_COALESCING_REASON,
    "m-unit-work-022": _OBSERVED_STATE_COALESCING_REASON,
    "m-unit-work-023": _OBSERVED_STATE_COALESCING_REASON,
    "m-unit-work-024": _OBSERVED_GENERATION_REASON,
    "m-unit-work-025": _OBSERVED_STATE_COALESCING_REASON,
    "m-unit-work-026": _OBJECT_CLAIM_COALESCING_REASON,
    "m-unit-work-027": _OBJECT_CLAIM_COALESCING_REASON,
    "m-unit-work-017": _WRITE_VALUE_PROVENANCE_REASON,
    "m-unit-work-018": _WRITE_VALUE_PROVENANCE_REASON,
    "m-unit-work-019": _WRITE_VALUE_PROVENANCE_REASON,
    "m-unit-work-020": _WRITE_VALUE_PROVENANCE_REASON,
    "m-unit-work-016": _TEMPORAL_KEYED_SINGLETON_UNREACHABLE_REASON,
    # -- m-opt-lock: non-temporal write family, conformance-lane covered ----- #
    # (the locking-mode advance has an idiomatic story, m-opt-lock-002)        #
    "m-opt-lock-005": _OPT_LOCK_STALE_GATE_SECOND_WRITER_REASON,
    "m-opt-lock-006": _OPT_LOCK_MATCHING_GATE_EMITTED_SQL_REASON,
    "m-opt-lock-007": _OPT_LOCK_STALE_GATE_SECOND_WRITER_REASON,
    "m-opt-lock-013": _OPT_LOCK_MATCHING_GATE_EMITTED_SQL_REASON,
    # -- m-opt-lock / m-read-lock concurrency cases -------------------------- #
    "m-opt-lock-009": _OPT_LOCK_CONFLICT_LANE_OPT_IN_REASON,
    "m-opt-lock-010": _OPT_LOCK_BOUNDARY_RUNNER_REASON,
    "m-opt-lock-011": _OPT_LOCK_BOUNDARY_RUNNER_REASON,
    "m-opt-lock-012": _OPT_LOCK_INTERLEAVED_RACE_REASON,
    "m-read-lock-001": _READ_LOCK_HARNESS_GOLDEN_REASON,
    "m-read-lock-006": _READ_LOCK_TWO_SESSION_REASON,
    "m-read-lock-007": _READ_LOCK_TWO_SESSION_REASON,
    "m-read-lock-010": _READ_LOCK_PARTITIONED_GOLDEN_REASON,
    "m-read-lock-011": _READ_LOCK_TWO_SESSION_REASON,
    "m-read-lock-012": _READ_LOCK_TWO_SESSION_REASON,
    # -- m-batch-write: versioned per-key delete materialization ------------- #
    "m-batch-write-004": _BATCH_WRITE_VERSIONED_MATERIALIZE_REASON,
    # -- m-pk-gen: temporal composition -------------------------------------- #
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
    "m-inheritance-134": _TPCS_UNION_RESULT_SHAPE_REASON,
    "m-inheritance-135": _TPCS_UNION_RESULT_SHAPE_REASON,
    "m-inheritance-060": _TPH_POLYMORPHIC_EXISTS_SIBLING_REASON,
    "m-inheritance-061": _TPH_POLYMORPHIC_EXISTS_SIBLING_REASON,
    "m-inheritance-062": _TPH_POLYMORPHIC_EXISTS_SIBLING_REASON,
    "m-inheritance-063": _TPH_POLYMORPHIC_EXISTS_SIBLING_REASON,
    # -110 adds a branch predicate to -062's narrowed hop to pin BIND ORDER inside
    # the correlated EXISTS (m-sql "Grouped branch predicates"). Both halves of that
    # spelling — the narrow and the comparison — are already exercised developer
    # surface; what it adds is an emitted-SQL contract, which the compile/run sweeps
    # grade byte-exact rather than a story.
    "m-inheritance-110": _TPH_POLYMORPHIC_EXISTS_SIBLING_REASON,
    "m-inheritance-073": _ROOT_GUARD_MULTI_SUBTYPE_SPELLING_UNREACHABLE_REASON,
    "m-inheritance-077": _ROOT_GUARD_MULTI_SUBTYPE_SPELLING_UNREACHABLE_REASON,
    "m-inheritance-118": (
        "the portable deep-fetch graph collision witness is exercised by the database-backed "
        "run lane; no separate idiomatic API story is needed"
    ),
    "m-inheritance-119": (
        "the value-object/familyVariant materialization collision is exercised by the "
        "compile and database-backed run lanes; no separate idiomatic API story is needed"
    ),
    "m-inheritance-120": (
        "qualified duplicate-local variant identity and scalar-alias preservation are "
        "exercised by the compile and database-backed run lanes; no separate idiomatic API "
        "story is needed"
    ),
    "m-inheritance-123": (
        "heterogeneous TPH document decoding is exercised by the compile and database-backed "
        "run lanes; no separate idiomatic API story is needed"
    ),
    "m-inheritance-124": (
        "tag-partitioned sibling document-path predicates are exercised by the compile and "
        "database-backed run lanes; no separate idiomatic API story is needed"
    ),
    "m-inheritance-126": (
        "per-branch TPCS document decoding is exercised by the compile and database-backed "
        "run lanes; no separate idiomatic API story is needed"
    ),
    "m-inheritance-127": (
        "nested TPCS narrow lowering is exercised by the compile and database-backed run "
        "lanes; no separate idiomatic API story is needed"
    ),
    "m-inheritance-136": _TPCS_UNION_RESULT_SHAPE_REASON,
    "m-inheritance-137": (
        "the developer spelling is the exercised instance-form abstract-target `db.find` "
        "of m-inheritance-109, asked of the whole root position instead of a narrowed one: "
        "the call is identical and what differs is the emitted projection, which carries "
        "the document read pair for the one branch declaring the occurrence and the typed "
        "`NULL` placeholder for the branches declaring none — graded byte-exact by the "
        "compile lane and end to end by the database-backed run lane"
    ),
    "m-inheritance-092": _TEMPORAL_INHERITANCE_ROW_SIBLING_REASON,
    "m-inheritance-093": _TEMPORAL_INHERITANCE_ROW_SIBLING_REASON,
    "m-inheritance-101": _CONCRETE_TARGET_TEMPORAL_ROOT_AXIS_SIBLING_REASON,
    # -- m-inheritance: multi-concrete polymorphic PROJECTING reads, the       #
    # ROW-FORM originals (their instance-form siblings are executed) --------- #
    "m-inheritance-003": _INHERITANCE_MULTI_CONCRETE_PROJECTION_UNREACHABLE_REASON,
    "m-inheritance-013": _INHERITANCE_MULTI_CONCRETE_PROJECTION_UNREACHABLE_REASON,
    "m-inheritance-015": _INHERITANCE_MULTI_CONCRETE_PROJECTION_UNREACHABLE_REASON,
    "m-inheritance-052": _INHERITANCE_MULTI_CONCRETE_PROJECTION_UNREACHABLE_REASON,
    # -- m-inheritance: non-temporal write family, conformance-lane covered -- #
    # (instance-native examples are not available)                             #
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
    "m-inheritance-125": _INHERITANCE_WRITE_CONFORMANCE_LANE_REASON,
    "m-inheritance-128": _INHERITANCE_WRITE_CONFORMANCE_LANE_REASON,
    "m-inheritance-130": _INHERITANCE_ABSTRACT_OBSERVATION_LICENSES_WRITE_REASON,
    # -- m-inheritance: temporal write family -------------------------------- #
    "m-inheritance-090": _INHERITANCE_AUDIT_TERMINATE_REASON,
    "m-inheritance-091": _INHERITANCE_AUDIT_TERMINATE_REASON,
    "m-inheritance-094": _INHERITANCE_BITEMPORAL_TERMINATE_REASON,
    "m-inheritance-095": _INHERITANCE_BITEMPORAL_TERMINATE_REASON,
    "m-inheritance-096": _INHERITANCE_BITEMPORAL_TERMINATE_REASON,
    "m-inheritance-097": _INHERITANCE_BITEMPORAL_TERMINATE_REASON,
    "m-inheritance-105": _INHERITANCE_COMPOSED_CONFLICT_REASON,
    "m-inheritance-086": _INHERITANCE_SIBLING_ATTRIBUTE_UNREACHABLE_REASON,
    "m-inheritance-131": _INHERITANCE_SIBLING_ATTRIBUTE_UNREACHABLE_REASON,
    "m-inheritance-087": _INHERITANCE_METADATA_FIELD_UNREACHABLE_REASON,
    "m-inheritance-089": _INHERITANCE_SET_BASED_UNSUPPORTED_UNREACHABLE_REASON,
    # -- m-inheritance: `when.model` descriptor rejects (unreachable) -------- #
    "m-inheritance-020": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-021": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
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
    "m-inheritance-115": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-116": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-117": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-121": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-122": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-129": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    # -- m-metamodel: foundational model-declaration reject ------------------ #
    "m-metamodel-001": _METAMODEL_MODEL_REJECT_UNREACHABLE_REASON,
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
    # -- m-navigate / m-deep-fetch: Relational Document Layout traversals ----- #
    "m-navigate-025": _DOCUMENT_LAYOUT_RELATIONSHIP_REASON,
    "m-deep-fetch-024": _DOCUMENT_LAYOUT_RELATIONSHIP_REASON,
    "m-snapshot-read-002": _TEMPORAL_DEEPFETCH_GRAPH_SIBLING_REASON,
    # -- m-snapshot-read: orders-family graph siblings ----------------------- #
    "m-snapshot-read-003": _ORDERS_GRAPH_SIBLING_REASON,
    "m-snapshot-read-006": _ORDERS_GRAPH_SIBLING_REASON,
    "m-snapshot-read-008": _ORDERS_GRAPH_SIBLING_REASON,
    # -- m-snapshot-read: milestone-set graph siblings ----------------------- #
    "m-snapshot-read-013": _MILESTONE_SET_GRAPH_SIBLING_REASON,
    "m-snapshot-read-014": _MILESTONE_SET_GRAPH_SIBLING_REASON,
    # -- m-snapshot-read: the composition arm on an unmirrored model --------- #
    "m-snapshot-read-021": _COMPOSITION_UNMIRRORED_MODEL_REASON,
    # -- m-snapshot-read: the streamed-delivery lane ------------------------- #
    "m-snapshot-read-027": _STREAMED_DELIVERY_REASON,
    "m-snapshot-read-028": _STREAMED_DELIVERY_REASON,
    "m-snapshot-read-029": _STREAMED_DELIVERY_REASON,
    "m-snapshot-read-030": _STREAMED_DELIVERY_REASON,
    "m-snapshot-read-031": _STREAMED_DELIVERY_REASON,
    "m-snapshot-read-032": _STREAMED_DELIVERY_REASON,
    "m-snapshot-read-033": _STREAMED_DELIVERY_REASON,
    "m-snapshot-read-034": _STREAMED_DELIVERY_REASON,
    "m-snapshot-read-035": _STREAMED_DELIVERY_REASON,
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
    "m-value-object-048": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-049": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-050": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-051": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-052": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-053": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-054": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-055": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-056": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-057": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-058": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-059": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-060": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-061": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-062": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-063": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-064": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-065": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-068": (
        "a scoped `where` constraining ONE element-relative path twice with different "
        "values: the quantifier spelling is the same one the flagship same-element "
        "story already shows, and what this case pins is a DIALECT boundary — MariaDB's "
        "containment candidate cannot carry two values for one key — which no developer "
        "surface exposes and which this Postgres-only target never reaches"
    ),
    # -- m-value-object: structural rejects (no idiomatic spelling exists) --- #
    "m-value-object-034": _VO_UNKNOWN_NESTED_FIELD_REASON,
    "m-value-object-035": _VO_DEEPFETCH_SEGMENT_REASON,
    "m-value-object-036": _VO_NAVIGATE_TARGET_REASON,
    # -- m-value-object: write-input validation rejects ---------------------- #
    "m-value-object-043": _VO_VALUE_TYPE_MISMATCH_UNREACHABLE_REASON,
    "m-value-object-069": _VO_DEPTH_ZERO_ATTRIBUTE_UNREACHABLE_REASON,
    "m-value-object-070": _VO_DEPTH_ZERO_ATTRIBUTE_UNREACHABLE_REASON,
    "m-value-object-071": _VO_OCCURRENCE_SHAPE_UNREACHABLE_REASON,
    "m-value-object-072": _VO_OCCURRENCE_SHAPE_UNREACHABLE_REASON,
    "m-value-object-073": _VO_OCCURRENCE_SHAPE_UNREACHABLE_REASON,
    "m-value-object-074": _VO_PORTABLE_LITERAL_UNREACHABLE_REASON,
    # -- m-value-object: remaining write-family siblings --------------------- #
    "m-value-object-045": _VO_BATCH_WRITE_REASON,
    "m-value-object-046": _VO_OPT_LOCK_CONFLICT_REASON,
    "m-value-object-047": _VO_SCENARIO_COMBO_REASON,
    "m-value-object-066": _VO_VERSIONED_RESOLVE_SCENARIO_REASON,
    "m-value-object-067": (
        "a top-level occurrence inside an ENTITY document (Relational Document Layout): "
        "the developer spelling is the ordinary whole-occurrence assignment every "
        "mirrored value-object story already shows, and what this case pins is where "
        "the layout PUT that occurrence — its containment path inside the shared "
        "Structured Column, and the subtree the assignment replaces there. That is a "
        "physical composition question with no developer surface, exactly as the rest "
        "of `m-storage-layout` is, and models/document-layout.yaml carries no class "
        "mirror (`tests/_support/mirrored_models.py`'s own UNMIRRORED reason)"
    ),
    # -- m-bitemp-write: the finite-pin mutation contrast pair ---------------- #
    "m-bitemp-write-015": _BITEMP_PIN_CONTRAST_REASON,
    "m-bitemp-write-016": _BITEMP_PIN_CONTRAST_REASON,
    # -- m-bitemp-write: the per-view half of that contrast ------------------- #
    "m-bitemp-write-023": _PER_VIEW_PIN_REASON,
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
    "Do not edit by hand; run `just python-check` / `uv run gen-usage-guide`. -->"
)


def render_usage_guide(examples: list[Example], recipes: list[Recipe] | None = None) -> str:
    """Render the Usage Guide markdown from the registered examples, plus the
    spec-recipe section (:data:`RECIPES`) when supplied."""
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
            "_No idiomatic examples yet — each is added with the capability it demonstrates._"
        )
        lines.append("")
    else:
        # Every rendered transaction example uses the final entity-instance
        # signatures: `tx.insert(instance)`, `tx.update(edited_copy)`,
        # `tx.delete(node)`, and `tx.find` returning `Snapshot[T]`.
        for example in sorted(examples, key=lambda item: item.case_id):
            lines.append(f"## {example.title}")
            lines.append("")
            lines.append(f"Corpus case: `{example.case_id}`")
            lines.append("")
            lines.append("```python")
            lines.append(example.snippet)
            lines.append("```")
            lines.append("")
    if recipes:
        lines.append("## Recipes")
        lines.append("")
        lines.append("Spec-level idioms whose choreography spans more than any single corpus")
        lines.append("case: each recipe cites its normative spec section and the tests that")
        lines.append("grade it end-to-end (never a borrowed case id).")
        lines.append("")
        for recipe in recipes:
            lines.append(f"### {recipe.title}")
            lines.append("")
            lines.append(f"Spec: {recipe.spec}. Graded by {recipe.graded_by}.")
            lines.append("")
            if recipe.notes:
                lines.append(recipe.notes)
                lines.append("")
            lines.append("```python")
            lines.append(recipe.snippet.rstrip("\n"))
            lines.append("```")
            lines.append("")
    # Collapse the trailing separator blank(s) into a single terminating newline
    # so the generated Markdown satisfies markdownlint MD012 (no multiple blanks).
    return "\n".join(lines).rstrip("\n") + "\n"
