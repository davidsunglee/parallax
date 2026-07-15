"""Operation no-drift guard (m-api-conformance).

Each idiomatic public-API statement the suite authors must serialize to the exact
``m-op-algebra`` operation the mirrored corpus case authors — the developer
surface cannot drift from the graded protocol. The builders here are the source of
truth for the ``api_suite.EXAMPLES`` snippets; the guard compares
``statement.serialize()`` to the case's ``when.operation``.

Two case shapes carry no single top-level ``when.operation`` to compare a built
``Statement`` against, so they get their OWN comparison instead of a ``BUILDERS``
entry: a ``rejected`` case (the invalid input is authored under ``when.operation``,
but building it through the idiomatic surface never returns a ``Statement`` at all
— the model-aware validator raises immediately, exactly as it does for the corpus's
own operation-input path, COR-3 Phase 7 increment 1) proves no-drift by comparing
the RAW built predicate's own serialization to the case's ``when.operation`` and
separately asserting the SAME build raises the classified ``then.rejectedRule``;
a ``scenario`` case's per-step ``find`` bodies are graded by the executable graph
stories (``test_story_run.py``) instead, when their own statement is trivial
(a bare primary-key equality already proven by the ``m-op-algebra`` examples
above) or their behavior is not a query at all (a mutation/access step).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

import pytest

import inheritance_models as im
import snapshot_models as sm
import value_object_models as vm
from conftest import case_document
from mirrored_models import Balance
from parallax.conformance import case_format
from parallax.conformance.graph_models import Coverage, Policy
from parallax.conformance.story_models import Order, OrderItem, OrderStatus
from parallax.core import Entity, OperationRejectedError, Predicate, Statement
from parallax.core.op_algebra import serialize
from parallax.core.temporal_read import LATEST

pytestmark = pytest.mark.api_conformance

# case id -> the idiomatic statement that must serialize to the case's operation.
BUILDERS: dict[str, Callable[[], Statement]] = {
    "m-op-algebra-002": lambda: Order.where(Order.id == 42),
    "m-op-algebra-009": lambda: Order.where(Order.sku.is_null()),
    "m-op-algebra-011": lambda: Order.where(Order.sku.like("A-%")),
    "m-op-algebra-013": lambda: Order.where(Order.sku.starts_with("A-")),
    "m-op-algebra-018": lambda: Order.where(Order.id.in_([1, 2, 42])),
    "m-op-algebra-020": lambda: Order.where(Order.active.is_(True), Order.qty > 10),
    "m-op-algebra-021": lambda: Order.where((Order.qty < 10) | (Order.qty > 25)),
    "m-op-algebra-024": lambda: Order.where(
        (Order.qty >= 25) | (Order.qty <= 5), Order.active.is_(True)
    ),
    "m-op-algebra-025": lambda: Order.where(
        (Order.qty >= 25) | ((Order.qty <= 5) & Order.active.is_(True))
    ),
    "m-op-algebra-032": lambda: (
        Order.where().order_by(Order.active.desc(), Order.qty.asc()).limit(2)
    ),
    # The temporal as-of spelling (m-temporal-read), unlocked by the D-7
    # class-frontend axis declaration (EntityConfig.as_of on the Balance mirror).
    "m-temporal-read-003": lambda: Balance.where().as_of(
        processing=dt.datetime(2024, 4, 1, tzinfo=dt.UTC)
    ),
    # Relationship navigation (m-navigate), COR-3 Phase 7 increment 6b: the
    # `.any()` / `.none()` quantifiers always serialize to the `exists` /
    # `notExists` wire spelling — the ONE canonical form the idiomatic surface
    # implements for a navigation filter (m-op-algebra: "navigate and exists are
    # the same correlated-EXISTS lowering", a spelling redundancy the corpus also
    # exercises through the `navigate`-tagged siblings this suite reasoned-skips,
    # see api_suite.py).
    "m-navigate-003": lambda: Order.where(Order.items.none()),
    "m-navigate-004": lambda: Order.where(Order.items.any(OrderItem.quantity >= 4)),
    "m-navigate-006": lambda: Order.where(Order.items.none(), Order.active.is_(True)),
    "m-navigate-008": lambda: Order.where(
        Order.items.any(OrderItem.statuses.any(OrderStatus.code == "PACKED"))
    ),
    "m-navigate-009": lambda: OrderStatus.where(OrderStatus.order_item.any()),
    "m-navigate-010": lambda: Order.where(Order.items.none(OrderItem.statuses.any())),
    # Temporal navigate (m-navigate x m-temporal-read): the propagated per-hop
    # as-of pin (m-navigate-018, explicit `.as_of(...)`) and its defaulted
    # equivalent (m-navigate-023, no `.as_of()` at all — the SAME golden SQL and
    # rows, m-temporal-read's own default-injection rule applied per hop).
    "m-navigate-018": lambda: Policy.where(Policy.coverages.any(Coverage.amount >= 600.00)).as_of(
        processing=LATEST, business=LATEST
    ),
    "m-navigate-023": lambda: Policy.where(Policy.coverages.any(Coverage.amount >= 600.00)),
    # Deep-fetch include paths (m-deep-fetch) that also drive an executable graph
    # story (`parallax.conformance.graph_stories`) — the SAME statement expression;
    # this entry is the query-shape no-drift half, the story is the execution half.
    "m-snapshot-read-001": lambda: Order.where(Order.id == 1).include(
        Order.items, Order.items_by_ship_date
    ),
    "m-snapshot-read-004": lambda: Order.where(Order.id == 999).include(Order.items.statuses),
    "m-snapshot-read-005": lambda: Order.where(Order.id == 4).include(Order.items.statuses),
    "m-snapshot-read-011": lambda: Order.where(Order.id == 1).include(Order.items.order),
    "m-navigate-013": lambda: (
        Policy.where()
        .as_of(business=dt.datetime(2024, 3, 1, tzinfo=dt.UTC), processing=LATEST)
        .include(Policy.coverages)
    ),
    # Inheritance reads (m-inheritance): table-per-hierarchy concrete/abstract
    # targets, the `Entity.narrow(...)` constructor, the statement-level
    # `.narrow(...)` clause, an OR of two narrowed branches, and the
    # table-per-concrete-subtype narrow clause.
    "m-inheritance-001": lambda: im.CardPayment.where(),
    "m-inheritance-003": lambda: im.Payment.where(),
    "m-inheritance-005": lambda: im.Invoice.where(),
    "m-inheritance-012": lambda: sm.Animal.where(
        sm.Animal.narrow(sm.Dog, where=sm.Dog.bark_volume > 3)
    ),
    "m-inheritance-013": lambda: sm.Animal.where().narrow(sm.Pet),
    "m-inheritance-015": lambda: sm.Animal.where(
        sm.Animal.narrow(sm.Dog, where=sm.Dog.bark_volume > 5)
        | sm.Animal.narrow(sm.Cat, where=sm.Cat.indoor.is_(True))
    ),
    "m-inheritance-052": lambda: im.Document.where().narrow(im.FinancialDocument),
    # TPCS polymorphic navigation (m-navigate x m-inheritance): a grouped-OR
    # semi-join over the abstract root's concrete tables, and the SAME shape
    # narrowed to one abstract subtype (dropping the sibling branch).
    "m-inheritance-070": lambda: im.Folder.where(im.Folder.documents.any()),
    "m-inheritance-071": lambda: im.Folder.where(
        im.Folder.documents.any(im.Document.narrow(im.FinancialDocument))
    ),
    # Value-object traversal (m-value-object): shallow/deep nested equality,
    # `.is_null()`, the bare `.any()` / `.none()` to-many presence quantifiers, a
    # flat any-element predicate, and the scoped same-element `.any(...)` form
    # (python.md §2's own worked example).
    "m-value-object-001": lambda: vm.Customer.where(vm.Customer.address.city == "Oslo"),
    "m-value-object-002": lambda: vm.Customer.where(vm.Customer.address.geo.country == "US"),
    "m-value-object-007": lambda: vm.Customer.where(vm.Customer.address.city.is_null()),
    "m-value-object-015": lambda: vm.Customer.where(vm.Customer.address.phones.any()),
    "m-value-object-016": lambda: vm.Customer.where(vm.Customer.address.phones.none()),
    "m-value-object-017": lambda: vm.Customer.where(vm.Customer.address.phones.type == "home"),
    "m-value-object-019": lambda: vm.Customer.where(
        vm.Customer.address.phones.any(vm.Phone.type == "home", vm.Phone.number == "555-9999")
    ),
}

_CASES = {c.case_id: c for c in case_format.load_cases()}


@pytest.mark.parametrize("case_id", sorted(BUILDERS), ids=sorted(BUILDERS))
def test_idiomatic_statement_serializes_to_the_corpus_operation(case_id: str) -> None:
    expected = case_document(_CASES[case_id])["when"]["operation"]
    assert BUILDERS[case_id]().serialize() == expected


def test_expression_rejects_bool_misuse() -> None:
    with pytest.raises(TypeError, match="no truth value"):
        bool(Order.id == 1)  # a Predicate has no truth value
    with pytest.raises(TypeError, match="no truth value"):
        bool(Order.sku)  # a bare AttributeExpr has no truth value


# --------------------------------------------------------------------------- #
# Rejected-case build-time proofs (m-op-algebra / m-navigate / m-value-object, #
# COR-3 Phase 7): a rejected case's `when.operation` never becomes a Statement #
# — the SAME model-aware `validate_operation` the corpus's own rejected lane   #
# calls (m-conformance-adapter, resolved DQ3) runs INSIDE `Entity.where()` /   #
# `.narrow()`, raising before a Statement is ever returned. No-drift here is   #
# two proofs: the raw built predicate serializes to the case's own            #
# `when.operation` (the SAME structural comparison every other example makes, #
# minus the `Statement` wrapper a rejected build never produces), and         #
# attempting to build it through `Entity.where(...)` raises                   #
# `OperationRejectedError` naming the EXACT `then.rejectedRule`.               #
# --------------------------------------------------------------------------- #
REJECTED_BUILDERS: dict[str, Callable[[], Predicate]] = {
    "m-value-object-038": lambda: vm.Customer.address.city == 42,
    "m-inheritance-040": lambda: sm.Pet.narrow(sm.WildBoar),
    "m-inheritance-041": lambda: sm.Dog.bark_volume > 5,
    "m-inheritance-042": lambda: sm.Pet.narrow(sm.Dog, where=sm.Animal.narrow(sm.Cat)),
}

# case id -> the entity `Entity.where(...)` is called on to trigger validation
# (the rejected case's own target: the model's family root when it declares
# one, matching `engine._rejected_target`'s default).
REJECTED_TARGETS: dict[str, type[Entity]] = {
    "m-value-object-038": vm.Customer,
    "m-inheritance-040": sm.Animal,
    "m-inheritance-041": sm.Animal,
    "m-inheritance-042": sm.Animal,
}


@pytest.mark.parametrize("case_id", sorted(REJECTED_BUILDERS), ids=sorted(REJECTED_BUILDERS))
def test_rejected_predicate_serializes_to_the_corpus_operation(case_id: str) -> None:
    expected = case_document(_CASES[case_id])["when"]["operation"]
    predicate = REJECTED_BUILDERS[case_id]()
    assert serialize(predicate.op) == expected


@pytest.mark.parametrize("case_id", sorted(REJECTED_BUILDERS), ids=sorted(REJECTED_BUILDERS))
def test_idiomatic_statement_build_rejects_the_corpus_rule(case_id: str) -> None:
    expected_rule = case_document(_CASES[case_id])["then"]["rejectedRule"]
    target = REJECTED_TARGETS[case_id]
    predicate = REJECTED_BUILDERS[case_id]()
    with pytest.raises(OperationRejectedError) as exc_info:
        target.where(predicate)
    assert exc_info.value.rule == expected_rule
