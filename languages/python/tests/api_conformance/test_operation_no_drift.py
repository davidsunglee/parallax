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

Most read-only entries below are **derived** from
``parallax.conformance.read_stories.READ_STORIES`` — the SAME ``build()`` the
real-database generic runner (``test_story_run.py``) executes against real
Postgres, so this guard's no-drift proof and that execution share one source,
never a second, hand-duplicated expression that could drift from it. The
remaining hand-authored entries are the ones that genuinely have no executable
real-database story yet (a graph-story's own bare-statement half; a
multi-concrete polymorphic read `db.find` cannot grade as flat rows; the
Customer value-object family's registry collision) — see
``read_stories``'s own module docstring and ``api_suite.CASE_SKIP_REASONS``
for exactly why each one stays build-only.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

import pytest

import inheritance_models as im
import snapshot_models as sm
import value_object_models as vm
from conftest import case_document
from parallax.conformance import case_format
from parallax.conformance.animal_owner import Person as AnimalOwnerPerson
from parallax.conformance.graph_models import Policy
from parallax.conformance.read_models import Animal as AnimalRoot
from parallax.conformance.read_models import Cat, Dog, Person, Pet, WildBoar
from parallax.conformance.read_stories import READ_STORIES
from parallax.conformance.story_models import Order
from parallax.core import Entity, OperationRejectedError, Predicate, Statement
from parallax.core.op_algebra import serialize
from parallax.core.temporal_read import LATEST

pytestmark = pytest.mark.api_conformance

# case id -> the idiomatic statement that must serialize to the case's operation.
BUILDERS: dict[str, Callable[[], Statement]] = {
    # The op-algebra / temporal-read / navigate / single-concrete-inheritance
    # read examples: derived from the SAME `build()` the real-database runner
    # executes (`read_stories.READ_STORIES`) — see this file's own docstring.
    **{story.case_id: story.build for story in READ_STORIES},
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
    # Multi-concrete polymorphic PROJECTING reads (m-inheritance): build-only —
    # `db.find`'s instance-form materialization cannot reproduce a flat
    # `then.rows` comparison for these (a table-per-hierarchy multi-concrete
    # row's own typed instance carries only its own concrete class's fields;
    # table-per-concrete-subtype instance-form projection over 2+ resolved
    # concretes has no goldened lowering yet) — see `read_stories`'s own
    # module docstring.
    "m-inheritance-003": lambda: im.Payment.where(),
    "m-inheritance-013": lambda: sm.Animal.where().narrow(sm.Pet),
    "m-inheritance-015": lambda: sm.Animal.where(
        sm.Animal.narrow(sm.Dog, where=sm.Dog.bark_volume > 5)
        | sm.Animal.narrow(sm.Cat, where=sm.Cat.indoor.is_(True))
    ),
    "m-inheritance-052": lambda: im.Document.where().narrow(im.FinancialDocument),
    # Value-object traversal (m-value-object): build-only — `value_object_
    # models.Customer` is test-only and no installed-package `Customer`
    # mirror exists yet to drive these as a real story. Ledger D-20 (COR-3
    # Phase 8 increment 7) removed the STRUCTURAL registry-collision block
    # the animal family's owner side once carried (see `read_models`'s own
    # docstring); an installed Customer/Location/Depot mirror is a
    # coverage-surface breadth item this increment's own scale judgment
    # (Part D item 4) deprioritized behind the Supplier/Branch/Contact/
    # Shipment flips and the typed-verb story build-out.
    "m-value-object-001": lambda: vm.Customer.where(vm.Customer.address.city == "Oslo"),
    "m-value-object-002": lambda: vm.Customer.where(vm.Customer.address.geo.country == "US"),
    "m-value-object-007": lambda: vm.Customer.where(vm.Customer.address.city.is_null()),
    "m-value-object-015": lambda: vm.Customer.where(vm.Customer.address.phones.any()),
    "m-value-object-016": lambda: vm.Customer.where(vm.Customer.address.phones.none()),
    "m-value-object-017": lambda: vm.Customer.where(vm.Customer.address.phones.type == "home"),
    "m-value-object-019": lambda: vm.Customer.where(
        vm.Customer.address.phones.any(vm.Phone.type == "home", vm.Phone.number == "555-9999")
    ),
    # Deep-fetch include paths over the now-installed Person/Passport and
    # animal-owner mirrors (ledger D-20/D-21) — the query-shape no-drift
    # half of the executable graph stories in `graph_stories.py`.
    "m-snapshot-read-007": lambda: Person.where().include(Person.passport),
    "m-snapshot-read-012": lambda: AnimalOwnerPerson.where(AnimalOwnerPerson.id == 10).include(
        AnimalOwnerPerson.animals, AnimalOwnerPerson.pets.narrow(Dog)
    ),
    "m-inheritance-065": lambda: AnimalOwnerPerson.where().include(
        AnimalOwnerPerson.pets.narrow(Dog)
    ),
    "m-inheritance-066": lambda: AnimalOwnerPerson.where().include(
        AnimalOwnerPerson.pets.narrow(Pet), AnimalOwnerPerson.pets.narrow(Cat, Dog)
    ),
    "m-inheritance-067": lambda: AnimalOwnerPerson.where().include(
        AnimalOwnerPerson.pets.narrow(Dog), AnimalOwnerPerson.pets.narrow(Cat)
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
    # `Person.pets` targets the abstract subtype Pet; narrowing past its
    # reachable set (WildBoar, a sibling branch) or naming the wrong `entity`
    # (Animal instead of Pet) both raise `narrow-outside-relationship-target`
    # over the now-installed animal-owner mirror (ledger D-20).
    "m-inheritance-064": lambda: AnimalOwnerPerson.pets.any(Pet.narrow(WildBoar)),
    "m-inheritance-072": lambda: AnimalOwnerPerson.pets.any(AnimalRoot.narrow(Dog)),
}

# case id -> the entity `Entity.where(...)` is called on to trigger validation
# (the rejected case's own target: the model's family root when it declares
# one, matching `engine._rejected_target`'s default; the animal-owner pair
# below targets `Person` itself instead — the predicate is fundamentally
# about `Person.pets`, and `Person`'s own registry scope is the one that
# resolves BOTH `Person` and `Pet`/`WildBoar`/`Animal` coherently, ledger D-20).
REJECTED_TARGETS: dict[str, type[Entity]] = {
    "m-value-object-038": vm.Customer,
    "m-inheritance-040": sm.Animal,
    "m-inheritance-041": sm.Animal,
    "m-inheritance-064": AnimalOwnerPerson,
    "m-inheritance-072": AnimalOwnerPerson,
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
