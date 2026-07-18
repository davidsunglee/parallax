"""``parallax.conformance.read_stories`` — executable API-suite READ examples
(m-api-conformance; review remediation of the S1 finding against Phase-7
increment 6b: exercised MUST mean executed-and-graded through the shipped
surface, never serialization-only).

Every entry is ONE case-driven idiomatic read example: a pure ``build()``
returning the SAME idiomatic ``Statement`` expression
``tests/api_conformance/test_operation_no_drift.py``'s ``BUILDERS`` proves
no-drift against the corpus's own ``when.operation`` (the query-shape half),
plus the ``case_id`` / ``title`` / ``model`` it mirrors. Execution is
GENERIC, unlike the write/graph stories: a single runner
(``tests/api_conformance/test_story_run.py``) drives EVERY entry through the
SAME shipped surface (``parallax.snapshot.connect`` -> ``db.find``), grading
the mirrored case's own ``then.rows`` (order-insensitive, exact-typed) and
``then.roundTrips`` — a hand-rolled per-case story function would only repeat
the identical three-step shape (reset, `db.find(build())`, compare) for every
entry, exactly the case the API Conformance Suite contract's "generic
case-driven runner" language anticipates.

Every entity class referenced here lives in the installed ``parallax-conformance``
distribution (``story_models`` / ``graph_models`` / ``read_models``), never a
``tests/``-only mirror: this module is a real dev-only package module whose
statements the Usage Guide's coverage-partition machinery (``api_suite.py``)
and the real-database runner both need resolvable at ordinary import time, not
only under pytest's test-path magic.

Deliberately ABSENT, each for its own reasoned-skip in ``api_suite.CASE_SKIP_REASONS``
or its own ``graph_stories.GraphStory`` instead:

- the ``customer.yaml`` value-object predicate reads
  (``m-value-object-001/002/007/015/016/017/019``) and its materialization/
  deep-fetch siblings (``m-value-object-023/024``, ``m-deep-fetch-018``): now
  installed (``parallax.conformance.vo_models.Customer``, D-20 residue, COR-3
  Phase 8 increment 7 completion round) and executed, but as
  ``graph_stories.GraphStory`` entries rather than here — the corpus classifies
  the predicate reads ROW-FORM (``then.rows`` alone), while `db.find` is
  ALWAYS instance-form (python.md §4), so this module's byte-exact generic
  runner cannot grade them; ``graph_stories``'s own module docstring explains
  the bespoke rule that grades them instead;
- the multi-concrete polymorphic PROJECTING reads (``m-inheritance-003``/
  ``-013``/``-015``/``-052``): a table-per-hierarchy multi-concrete row's own
  typed instance carries only its OWN concrete class's fields, never a
  sibling's nullable column the wire row's superset includes, and
  table-per-concrete-subtype instance-form projection over 2+ resolved
  concretes has no goldened lowering at all yet (``SqlGenError``) — a genuine
  engine gap `db.find`'s instance-form materialization hits, not a
  partition-honesty concern to paper over by grading around it (ledger D-22).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from parallax.conformance.graph_models import Coverage, Policy
from parallax.conformance.read_models import (
    Animal,
    CardPayment,
    DepositRate,
    Document,
    Dog,
    FinancialDocument,
    Folder,
    Invoice,
)
from parallax.conformance.read_models import Balance as _Balance
from parallax.conformance.story_models import Account, Order, OrderItem, OrderStatus
from parallax.core import Statement
from parallax.core.temporal_read import LATEST
from parallax.core.unit_work import Concurrency

__all__ = ["READ_STORIES", "ReadStory", "read_story_snippet"]


@dataclass(frozen=True, slots=True)
class ReadStory:
    """One case-driven idiomatic read example: build the statement, mirror one
    corpus ``read``-shape case whose oracle is ``then.rows``/``then.roundTrips``.
    ``snippet`` is the bare ``op = ...`` reading every entry authors (a plain
    assignment, matching every other example's presentation) — kept alongside
    ``build`` rather than derived via ``inspect.getsource`` (a lambda's own
    source line would render the dict-literal/comma noise around it).
    :func:`read_story_snippet` is the Usage Guide's OWN rendered source: it
    layers the participation-mode wrapper on top of ``snippet``, single-
    sourced from ``concurrency`` below rather than a second, independently-
    authored string (review remediation finding 2).

    ``concurrency`` (COR-3 Phase 8 increment 6, the `m-read-lock` matrix's
    -002/-003/-005) opts a story into the TRANSACTIONAL read half instead of
    the default non-transactional one: ``None`` (every other entry, unchanged)
    runs ``db.find(build())``; a declared mode runs
    ``db.transact(lambda tx: tx.find(build()), concurrency=...)`` — a
    participating `tx.find`, whose emitted SQL carries (or, `optimistic`,
    omits) the dialect's shared read-lock suffix per the SAME `m-read-lock`
    policy `Transaction.find` derives production-side
    (`parallax.core.read_lock.mode_for`). `test_story_run.py`'s own generic
    runner branches on this SAME field to build the executed callable — the
    ONE place the mode is authored, flowing into both the rendered snippet
    (:func:`read_story_snippet`) and the execution, so neither can drift from
    the other."""

    case_id: str
    title: str
    model: str
    build: Callable[[], Statement]
    snippet: str
    concurrency: Concurrency | None = None


def read_story_snippet(story: ReadStory) -> str:
    """The story's rendered Usage Guide source: ``story.snippet``'s bare
    ``op = ...`` reading, PLUS — for a story whose own ``concurrency`` opts
    into the transactional read half — the SAME
    ``db.transact(lambda tx: tx.find(op), concurrency=...)`` wrapper
    `test_story_run.py`'s generic runner actually executes, rendered from
    that SAME field rather than a second, independently-typed copy of the
    mode (review remediation finding 2: a `m-read-lock-002` vs. `-005`-style
    pair renders IDENTICALLY otherwise, hiding the one thing the pair
    exists to demonstrate)."""
    if story.concurrency is None:
        return story.snippet
    return (
        f'{story.snippet}\ndb.transact(lambda tx: tx.find(op), concurrency="{story.concurrency}")'
    )


READ_STORIES: Final[tuple[ReadStory, ...]] = (
    # -- m-op-algebra (predicate/grouping/ordering spellings), models/orders.yaml #
    ReadStory(
        "m-op-algebra-002",
        "Equality on the primary key",
        "orders",
        lambda: Order.where(Order.id == 42),
        "op = Order.where(Order.id == 42)",
    ),
    ReadStory(
        "m-op-algebra-009",
        "Is-null predicate",
        "orders",
        lambda: Order.where(Order.sku.is_null()),
        "op = Order.where(Order.sku.is_null())",
    ),
    ReadStory(
        "m-op-algebra-011",
        "SQL-pattern LIKE",
        "orders",
        lambda: Order.where(Order.sku.like("A-%")),
        'op = Order.where(Order.sku.like("A-%"))',
    ),
    ReadStory(
        "m-op-algebra-013",
        "Literal starts-with (wildcards escaped)",
        "orders",
        lambda: Order.where(Order.sku.starts_with("A-")),
        'op = Order.where(Order.sku.starts_with("A-"))',
    ),
    ReadStory(
        "m-op-algebra-018",
        "Membership (IN)",
        "orders",
        lambda: Order.where(Order.id.in_([1, 2, 42])),
        "op = Order.where(Order.id.in_([1, 2, 42]))",
    ),
    ReadStory(
        "m-op-algebra-020",
        "Conjoined filters (big-AND)",
        "orders",
        lambda: Order.where(Order.active.is_(True), Order.qty > 10),
        "op = Order.where(Order.active.is_(True), Order.qty > 10)",
    ),
    ReadStory(
        "m-op-algebra-021",
        "Disjunction with parentheses",
        "orders",
        lambda: Order.where((Order.qty < 10) | (Order.qty > 25)),
        "op = Order.where((Order.qty < 10) | (Order.qty > 25))",
    ),
    ReadStory(
        "m-op-algebra-024",
        "Grouped precedence — an OR under an AND",
        "orders",
        lambda: Order.where((Order.qty >= 25) | (Order.qty <= 5), Order.active.is_(True)),
        "op = Order.where((Order.qty >= 25) | (Order.qty <= 5), Order.active.is_(True))",
    ),
    ReadStory(
        "m-op-algebra-025",
        "Natural precedence — an AND under an OR (no group)",
        "orders",
        lambda: Order.where((Order.qty >= 25) | ((Order.qty <= 5) & Order.active.is_(True))),
        "op = Order.where((Order.qty >= 25) | ((Order.qty <= 5) & Order.active.is_(True)))",
    ),
    ReadStory(
        "m-op-algebra-032",
        "Ordering and limiting",
        "orders",
        lambda: Order.where().order_by(Order.active.desc(), Order.qty.asc()).limit(2),
        "op = Order.where().order_by(Order.active.desc(), Order.qty.asc()).limit(2)",
    ),
    # -- m-temporal-read, models/balance.yaml -------------------------------- #
    ReadStory(
        "m-temporal-read-003",
        "As-of read at a past instant",
        "balance",
        lambda: _Balance.where().as_of(processing=dt.datetime(2024, 4, 1, tzinfo=dt.UTC)),
        "op = Balance.where().as_of(processing=datetime(2024, 4, 1, tzinfo=UTC))",
    ),
    # -- m-navigate (relationship existence), models/orders.yaml ------------- #
    ReadStory(
        "m-navigate-002",
        "Relationship existence (bare `.any()`)",
        "orders",
        lambda: Order.where(Order.items.any()),
        "op = Order.where(Order.items.any())",
    ),
    ReadStory(
        "m-navigate-003",
        "Relationship absence (bare `.none()`)",
        "orders",
        lambda: Order.where(Order.items.none()),
        "op = Order.where(Order.items.none())",
    ),
    ReadStory(
        "m-navigate-004",
        "Relationship existence with a predicate",
        "orders",
        lambda: Order.where(Order.items.any(OrderItem.quantity >= 4)),
        "op = Order.where(Order.items.any(OrderItem.quantity >= 4))",
    ),
    ReadStory(
        "m-navigate-006",
        "A navigation filter composed with a scalar predicate",
        "orders",
        lambda: Order.where(Order.items.none(), Order.active.is_(True)),
        "op = Order.where(Order.items.none(), Order.active.is_(True))",
    ),
    ReadStory(
        "m-navigate-008",
        "Multi-hop relationship existence",
        "orders",
        lambda: Order.where(Order.items.any(OrderItem.statuses.any(OrderStatus.code == "PACKED"))),
        "op = Order.where(\n"
        '    Order.items.any(OrderItem.statuses.any(OrderStatus.code == "PACKED"))\n'
        ")",
    ),
    ReadStory(
        "m-navigate-009",
        "Existence over a to-one (nullable) relationship",
        "orders",
        lambda: OrderStatus.where(OrderStatus.order_item.any()),
        "op = OrderStatus.where(OrderStatus.order_item.any())",
    ),
    ReadStory(
        "m-navigate-010",
        "Negated multi-hop relationship existence",
        "orders",
        lambda: Order.where(Order.items.none(OrderItem.statuses.any())),
        "op = Order.where(Order.items.none(OrderItem.statuses.any()))",
    ),
    # -- m-navigate x m-temporal-read (per-hop as-of), models/policy.yaml ---- #
    ReadStory(
        "m-navigate-018",
        "A semi-join across a temporal hop, explicitly pinned to latest",
        "policy",
        lambda: Policy.where(Policy.coverages.any(Coverage.amount >= 600.00)).as_of(
            processing=LATEST, business=LATEST
        ),
        "op = Policy.where(Policy.coverages.any(Coverage.amount >= 600.00)).as_of(\n"
        "    processing=LATEST, business=LATEST\n"
        ")",
    ),
    ReadStory(
        "m-navigate-023",
        "The same semi-join, defaulted to latest (no `.as_of()` at all)",
        "policy",
        lambda: Policy.where(Policy.coverages.any(Coverage.amount >= 600.00)),
        "op = Policy.where(Policy.coverages.any(Coverage.amount >= 600.00))",
    ),
    # -- m-inheritance (TPH/TPCS rows reads), payment/document/animal.yaml --- #
    ReadStory(
        "m-inheritance-001",
        "Table-per-hierarchy concrete-target read",
        "payment",
        lambda: CardPayment.where(),
        "op = CardPayment.where()",
    ),
    # `m-inheritance-003` (Payment abstract-root, familyVariant),
    # `m-inheritance-013`/`-015` (Animal narrowed to Pet / an OR of Dog+Cat
    # branches), and `m-inheritance-052` (Document narrowed to
    # FinancialDocument) are DELIBERATELY absent: every one resolves to a
    # MULTI-concrete polymorphic position it must PROJECT (not merely
    # semi-join), and `db.find`'s instance-form materialization cannot
    # reproduce a flat `then.rows` comparison for that shape — a table-per-
    # hierarchy multi-concrete row's own typed instance carries only ITS OWN
    # concrete class's fields (never a sibling's nullable column the wire
    # row's superset includes), and table-per-concrete-subtype instance-form
    # projection over 2+ resolved concretes has no goldened lowering at all
    # yet (`SqlGenError`, `sql_gen.compile._compile_tpcs_read`) — a genuine
    # engine gap, not a Spec-1 partition-honesty concern to paper over. See
    # `api_suite.CASE_SKIP_REASONS` for the reasoned skip.
    ReadStory(
        "m-inheritance-005",
        "Table-per-concrete-subtype concrete read",
        "document",
        lambda: Invoice.where(),
        "op = Invoice.where()",
    ),
    ReadStory(
        "m-inheritance-012",
        "The `Entity.narrow(...)` constructor, narrowed to one concrete subtype",
        "animal",
        lambda: Animal.where(Animal.narrow(Dog, where=Dog.bark_volume > 3)),
        "op = Animal.where(Animal.narrow(Dog, where=Dog.bark_volume > 3))",
    ),
    ReadStory(
        "m-inheritance-070",
        "Polymorphic navigation over table-per-concrete-subtype (grouped OR)",
        "document",
        lambda: Folder.where(Folder.documents.any()),
        "op = Folder.where(Folder.documents.any())",
    ),
    ReadStory(
        "m-inheritance-071",
        "The same polymorphic navigation, narrowed to one abstract subtype",
        "document",
        lambda: Folder.where(Folder.documents.any(Document.narrow(FinancialDocument))),
        "op = Folder.where(Folder.documents.any(Document.narrow(FinancialDocument)))",
    ),
    ReadStory(
        "m-inheritance-100",
        "Table-per-concrete-subtype concrete-target read pinning an inherited root-owned axis",
        "rate",
        lambda: DepositRate.where().as_of(processing=dt.datetime(2024, 1, 15, tzinfo=dt.UTC)),
        "op = DepositRate.where().as_of(processing=datetime(2024, 1, 15, tzinfo=UTC))",
    ),
    # -- m-read-lock (the runtime lock/omit matrix), models/account.yaml ----- #
    # (COR-3 Phase 8 increment 6): the `api-conformance`-lane runtime half of
    # the read-lock matrix — `tx.find` inside a `db.transact` of the declared
    # mode. `m-read-lock-001` (the harness-lane single-connection golden) and
    # `-006`/`-007`/`-008` (the two-session behavioral proofs) need no idiomatic
    # story: they need no `db.transact` participation-mode CONFIGURATION to
    # demonstrate (the harness proof runs the golden verbatim; the two-session
    # proofs are a concurrency property this generic single-session runner
    # cannot hold open) — see `api_suite.CASE_SKIP_REASONS`.
    ReadStory(
        "m-read-lock-002",
        "A locking-mode object find carries the shared read lock",
        "account",
        lambda: Account.where(Account.id == 2),
        "op = Account.where(Account.id == 2)",
        concurrency="locking",
    ),
    ReadStory(
        "m-read-lock-003",
        "A locking-mode projection read omits the shared read lock",
        "account",
        lambda: Account.where().distinct(),
        "op = Account.where().distinct()",
        concurrency="locking",
    ),
    ReadStory(
        "m-read-lock-005",
        "An optimistic-mode read omits the shared read lock",
        "account",
        lambda: Account.where(Account.id == 2),
        "op = Account.where(Account.id == 2)",
        concurrency="optimistic",
    ),
)
