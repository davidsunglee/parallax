"""PredicateNode no-drift guard (m-api-conformance).

Each idiomatic public-API query the suite authors must LOWER to the exact
``m-predicate`` operation the mirrored corpus case authors — the developer
surface cannot drift from the graded protocol. The builders here are the source of
truth for the ``api_suite.EXAMPLES`` snippets; the guard compares each query's
canonical lowering to the case's ``when.objectQuery``.

Two case shapes carry no single top-level ``when.objectQuery`` to compare a built
``ObjectQuery`` against, so they get their OWN comparison instead of a ``BUILDERS``
entry: a ``rejected`` case (the invalid input is authored under ``when.objectQuery``,
but building it through the idiomatic surface never returns a ``ObjectQuery`` at all
— the model-aware validator raises immediately, exactly as it does for the corpus's
own operation-input path) proves no-drift by comparing
the RAW built predicate's own serialization to the case's ``when.objectQuery`` and
separately asserting the SAME build raises the classified ``then.rejectedRule``;
a ``scenario`` case's per-step ``find`` bodies are graded by the executable graph
stories (``test_story_run.py``) instead, when their own query is trivial
(a bare primary-key equality already proven by the ``m-predicate`` examples
above) or their behavior is not a query at all (a mutation/access step).

Most read-only entries below are **derived** from
``parallax.conformance.read_stories.READ_STORIES`` — the SAME ``build()`` the
real-database generic runner (``test_story_run.py``) executes against real
Postgres, so this guard's no-drift proof and that execution share one source,
never a second, hand-duplicated expression that could drift from it. The
remaining hand-authored entries are the ones that genuinely have no executable
real-database story yet, OR that pair with a `graph_stories.GraphStory` (a
graph story's own bare-query half — including the Customer value-object
family: `db.find`'s
always-instance-form materialization means these grade bespoke there rather
than through `read_stories.ReadStory`'s byte-exact generic runner, see that
module's own docstring), OR that genuinely cannot: a multi-concrete
polymorphic read `db.find` cannot grade as flat rows — see ``read_stories``'s
own module docstring and ``api_suite.CASE_SKIP_REASONS`` for exactly why each
remaining one stays build-only.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any, cast

import pytest

from _support import inheritance_models as im
from _support import snapshot_models as sm
from _support import value_object_models as vm
from _support.corpus import case_document
from _support.query_probes import canonical_document
from parallax.conformance import case_format
from parallax.conformance.animal_owner import ANIMAL_MODEL as ANIMAL_OWNER_MODEL
from parallax.conformance.animal_owner import Person as AnimalOwnerPerson
from parallax.conformance.graph_models import Policy
from parallax.conformance.read_models import Animal as AnimalRoot
from parallax.conformance.read_models import (
    Cat,
    Document,
    Dog,
    FinancialDocument,
    Payment,
    Person,
    Pet,
    WildBoar,
)
from parallax.conformance.read_stories import READ_STORIES
from parallax.conformance.story_models import ORDERS_MODEL, Order
from parallax.conformance.vo_models import (
    CONTACT_MODEL,
    Branch,
    Contact,
    ContactPhone,
    Customer,
    CustomerPhone,
    Supplier,
)
from parallax.core import (
    DomainModel,
    Entity,
    ObjectQuery,
    OperationRejectedError,
    Predicate,
    QueryDefinitionError,
)
from parallax.core.entity._model import model_of
from parallax.core.object_query import LATEST
from parallax.core.object_query._fluent import object_query_node
from parallax.snapshot.handle import preflight

# case id -> the idiomatic query that must lower to the case's operation.
BUILDERS: dict[str, Callable[[], ObjectQuery[Any, Any]]] = {
    # The Predicate / temporal-read / navigate / single-concrete-inheritance
    # read examples: derived from the SAME `build()` the real-database runner
    # executes (`read_stories.READ_STORIES`) — see this file's own docstring.
    **{story.case_id: story.build for story in READ_STORIES},
    # Deep-fetch include paths (m-deep-fetch) that also drive an executable graph
    # story (`parallax.conformance.graph_stories`) — the SAME query expression;
    # this entry is the query-shape no-drift half, the story is the execution half.
    "m-snapshot-read-001": lambda: Order.where(Order.id == 1).include(
        Order.items, Order.items_by_ship_date
    ),
    "m-snapshot-read-004": lambda: Order.where(Order.id == 999).include(Order.items.statuses),
    "m-snapshot-read-005": lambda: Order.where(Order.id == 4).include(Order.items.statuses),
    "m-snapshot-read-011": lambda: Order.where(Order.id == 1).include(Order.items.order),
    "m-navigate-013": lambda: (
        Policy.where(Policy.all)
        .as_of(valid_time=dt.datetime(2024, 3, 1, tzinfo=dt.UTC), tx_time=LATEST)
        .include(Policy.coverages)
    ),
    # Multi-concrete polymorphic PROJECTING reads (m-inheritance): build-only —
    # `db.find`'s instance-form materialization cannot reproduce a flat
    # `then.rows` comparison for these (a table-per-hierarchy multi-concrete
    # row's own typed instance carries only its own concrete class's fields;
    # table-per-concrete-subtype instance-form projection over 2+ resolved
    # concretes has no goldened lowering yet) — see `read_stories`'s own
    # module docstring.
    "m-inheritance-003": lambda: im.Payment.where(im.Payment.all),
    "m-inheritance-013": lambda: sm.Animal.where(sm.Animal.all).narrow(sm.Pet),
    "m-inheritance-015": lambda: sm.Animal.where(
        sm.Animal.narrow(sm.Dog, where=sm.Dog.bark_volume > 5)
        | sm.Animal.narrow(sm.Cat, where=sm.Cat.indoor.is_(True))
    ),
    "m-inheritance-052": lambda: im.Document.where(im.Document.all).narrow(im.FinancialDocument),
    # Value-object traversal over the installed Customer mirror — the query-shape
    # no-drift half of the executable graph stories in `graph_stories.py`
    # (see that module's own docstring for why these land as `GraphStory`
    # entries, bespoke-graded, rather than `read_stories.ReadStory` ones).
    "m-value-object-001": lambda: Customer.where(Customer.address.city == "Oslo"),
    "m-value-object-002": lambda: Customer.where(Customer.address.geo.country == "US"),
    "m-value-object-007": lambda: Customer.where(Customer.address.city.is_null()),
    "m-value-object-015": lambda: Customer.where(Customer.address.phones.exists()),
    "m-value-object-016": lambda: Customer.where(Customer.address.phones.not_exists()),
    "m-value-object-017": lambda: Customer.where(Customer.address.phones.type == "home"),
    "m-value-object-019": lambda: Customer.where(
        Customer.address.phones.exists(
            CustomerPhone.type == "home", CustomerPhone.number == "555-9999"
        )
    ),
    "m-value-object-023": lambda: Customer.where(Customer.all),
    "m-value-object-024": lambda: Customer.where(Customer.address.city == "Oslo"),
    "m-deep-fetch-018": lambda: Customer.where(Customer.all).include(Customer.locations),
    # Deep-fetch include paths over the installed Person/Passport and
    # animal-owner mirrors — the query-shape no-drift
    # half of the executable graph stories in `graph_stories.py`.
    "m-snapshot-read-007": lambda: Person.where(Person.all).include(Person.passport),
    "m-snapshot-read-012": lambda: AnimalOwnerPerson.where(AnimalOwnerPerson.id == 10).include(
        AnimalOwnerPerson.animals, AnimalOwnerPerson.pets.narrow(Dog)
    ),
    "m-inheritance-065": lambda: AnimalOwnerPerson.where(AnimalOwnerPerson.all).include(
        AnimalOwnerPerson.pets.narrow(Dog)
    ),
    "m-inheritance-066": lambda: AnimalOwnerPerson.where(AnimalOwnerPerson.all).include(
        AnimalOwnerPerson.pets.narrow(Pet), AnimalOwnerPerson.pets.narrow(Cat, Dog)
    ),
    "m-inheritance-067": lambda: AnimalOwnerPerson.where(AnimalOwnerPerson.all).include(
        AnimalOwnerPerson.pets.narrow(Dog), AnimalOwnerPerson.pets.narrow(Cat)
    ),
    "m-inheritance-068": lambda: AnimalOwnerPerson.where(AnimalOwnerPerson.all).include(
        AnimalOwnerPerson.pets, AnimalOwnerPerson.pets.narrow(Pet)
    ),
    # Path-ROOT guards: reaching the inherited `Animal.owner` through a subtype
    # keeps that one relationship identity and guards which queried objects the
    # path starts from, so the wire carries `narrow: {to}` beside
    # `segments` rather than on a segment.
    "m-inheritance-074": lambda: AnimalRoot.where(AnimalRoot.all).include(Dog.owner, Cat.owner),
    "m-inheritance-075": lambda: AnimalRoot.where(AnimalRoot.all).include(
        AnimalRoot.owner, Dog.owner
    ),
    "m-inheritance-076": lambda: AnimalRoot.where(AnimalRoot.all).include(
        Pet.owner.pets.narrow(Dog)
    ),
    "m-inheritance-078": lambda: AnimalRoot.where(AnimalRoot.all).include(
        Dog.owner, WildBoar.owner, Dog.owner.pets
    ),
    # Value-object-bearing temporal reads over the installed Supplier/
    # Branch mirrors.
    "m-value-object-028": lambda: Supplier.where(Supplier.all).as_of(tx_time=LATEST),
    "m-value-object-029": lambda: Supplier.where(Supplier.all).as_of(
        tx_time=dt.datetime(2024, 4, 1, tzinfo=dt.UTC)
    ),
    "m-value-object-030": lambda: Branch.where(Branch.all).as_of(valid_time=LATEST, tx_time=LATEST),
    "m-value-object-031": lambda: Branch.where(Branch.all).as_of(
        valid_time=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
        tx_time=dt.datetime(2024, 2, 1, tzinfo=dt.UTC),
    ),
    # Multi-concrete polymorphic INSTANCE-FORM reads: the SAME
    # query expression as their row-form values-lane siblings
    # (m-inheritance-003/-013/-015/-052 above), but built over the INSTALLED
    # `read_models` classes rather than the test-only `im`/`sm` mirrors — the
    # object-lane witness a real `db.find` executes against.
    "m-inheritance-106": lambda: Payment.where(Payment.all),
    "m-inheritance-107": lambda: AnimalRoot.where(AnimalRoot.all).narrow(Pet),
    "m-inheritance-108": lambda: AnimalRoot.where(
        AnimalRoot.narrow(Dog, where=Dog.bark_volume > 5)
        | AnimalRoot.narrow(Cat, where=Cat.indoor.is_(True))
    ),
    "m-inheritance-109": lambda: Document.where(Document.all).narrow(FinancialDocument),
}

_CASES = {c.case_id: c for c in case_format.load_cases()}


@pytest.mark.parametrize("case_id", sorted(BUILDERS), ids=sorted(BUILDERS))
def test_the_idiomatic_query_builds_the_corpus_object_query(case_id: str) -> None:
    expected = case_document(_CASES[case_id])["when"]["objectQuery"]
    assert canonical_document(BUILDERS[case_id]()) == expected


def test_expression_rejects_bool_misuse() -> None:
    with pytest.raises(TypeError, match="no truth value"):
        bool(Order.id == 1)  # a Predicate has no truth value
    with pytest.raises(TypeError, match="no truth value"):
        bool(Order.sku)  # a bare AttributeExpr has no truth value


# --------------------------------------------------------------------------- #
# Rejected-case proofs (m-predicate / m-navigate / m-value-object): a rejected #
# case's `when.objectQuery` never reaches execution — the SAME model-aware     #
# validation the corpus's own rejected lane calls (m-conformance-adapter) runs #
# at the shared read gate rather than at `Entity.where`, because authoring     #
# reaches no model. No-drift here is two proofs: the idiomatic query builds    #
# the case's own `when.objectQuery`, and executing it raises                   #
# `OperationRejectedError` naming the EXACT `then.rejectedRule`.               #
# --------------------------------------------------------------------------- #
# Each entry builds the whole rejected query, naming the same queried target the
# case does — a rejected case now carries its own `target` rather than falling
# back to a default the runner resolves.
#
# Two of these predicates deliberately address a position the query is NOT at,
# which is the very thing `Predicate`'s contravariance refuses statically. They
# go through `_out_of_position` so the erasure is stated once, where the reason
# is: the rejection under test is model-aware, and the whole point of the case
# is that no static parameter can decide it — the model is what says whether
# `Dog` is a subtype of the queried position at all.
REJECTED_BUILDERS: dict[str, Callable[[], ObjectQuery[Any, Any]]] = {
    "m-op-algebra-039": lambda: Order.where(Order.price.between(50.75, 20.00)),
    "m-op-algebra-040": lambda: vm.Customer.where(vm.Customer.address.geo.elevation.between(12, 5)),
    "m-op-algebra-041": lambda: vm.Customer.where(
        vm.Customer.address.phones.exists(vm.Phone.number.between(42, 7))
    ),
    "m-op-algebra-042": lambda: vm.Customer.where(
        vm.Customer.address.geo.elevation.starts_with("1")
    ),
    "m-op-algebra-043": lambda: Contact.where(Contact.address.phones.expires.starts_with("2024")),
    "m-op-algebra-044": lambda: Contact.where(
        Contact.address.phones.exists(ContactPhone.expires.ends_with("-01"))
    ),
    "m-value-object-038": lambda: vm.Customer.where(vm.Customer.address.city == 42),
    # The animal-owner mirror composes `Person` alongside the family, so a
    # predicate over the owner is CONSTRUCTIBLE at the family position and is
    # refused for naming an entity outside it rather than for naming nothing.
    "m-op-algebra-045": lambda: _out_of_position(AnimalRoot, AnimalOwnerPerson.name == "Ada"),
    "m-inheritance-040": lambda: AnimalRoot.where(AnimalRoot.narrow(AnimalOwnerPerson)),
    "m-inheritance-041": lambda: _out_of_position(sm.Animal, sm.Dog.bark_volume > 5),
    "m-inheritance-042": lambda: sm.Animal.where(
        sm.Animal.narrow(sm.Dog, where=sm.Animal.narrow(sm.Cat))
    ),
    # `Person.pets` targets the abstract subtype Pet; narrowing past its
    # reachable set (WildBoar, a sibling branch) raises the relationship rule.
    "m-inheritance-064": lambda: AnimalRoot.where(
        AnimalOwnerPerson.pets.exists(Pet.narrow(WildBoar))
    ),
    "m-inheritance-132": lambda: sm.Animal.where(sm.Animal.narrow(sm.Dog, sm.Pet)),
}


def _out_of_position[E: Entity](
    target: type[E], predicate: Predicate[Any]
) -> ObjectQuery[Any, Any]:
    """``target``'s query over a predicate addressing another position entirely."""
    return target.where(cast("Predicate[E]", predicate))


@pytest.mark.parametrize("case_id", sorted(REJECTED_BUILDERS), ids=sorted(REJECTED_BUILDERS))
def test_the_rejected_query_builds_the_corpus_object_query(case_id: str) -> None:
    expected = case_document(_CASES[case_id])["when"]["objectQuery"]
    assert canonical_document(REJECTED_BUILDERS[case_id]()) == expected


# case id -> the Domain Model the rejected query is executed against.
# Authoring reaches no model, so the rule fires at the shared read gate rather
# than at `Entity.where`; the model each target belongs to is what states it.
REJECTED_MODELS: dict[str, DomainModel] = {
    "m-op-algebra-039": ORDERS_MODEL,
    "m-op-algebra-040": vm.CUSTOMER_MODEL,
    "m-op-algebra-041": vm.CUSTOMER_MODEL,
    "m-op-algebra-042": vm.CUSTOMER_MODEL,
    "m-op-algebra-043": CONTACT_MODEL,
    "m-op-algebra-044": CONTACT_MODEL,
    "m-value-object-038": vm.CUSTOMER_MODEL,
    "m-op-algebra-045": ANIMAL_OWNER_MODEL,
    "m-inheritance-040": ANIMAL_OWNER_MODEL,
    "m-inheritance-041": sm.ANIMAL_MODEL,
    "m-inheritance-064": ANIMAL_OWNER_MODEL,
    "m-inheritance-132": sm.ANIMAL_MODEL,
    "m-inheritance-042": sm.ANIMAL_MODEL,
}


@pytest.mark.parametrize("case_id", sorted(REJECTED_BUILDERS), ids=sorted(REJECTED_BUILDERS))
def test_the_idiomatic_query_rejects_the_corpus_rule_at_the_read_gate(case_id: str) -> None:
    expected_rule = case_document(_CASES[case_id])["then"]["rejectedRule"]
    query = REJECTED_BUILDERS[case_id]()
    with pytest.raises(OperationRejectedError) as exc_info:
        preflight(object_query_node(query), model=model_of(REJECTED_MODELS[case_id]), form="graph")
    assert exc_info.value.rule == expected_rule


def test_duplicate_subtype_selection_is_rejected_during_query_construction() -> None:
    expected = case_document(_CASES["m-inheritance-133"])["when"]["objectQuery"]
    assert expected["narrowTo"] == [
        "parallax.compatibility.Dog",
        "parallax.compatibility.Dog",
    ]
    with pytest.raises(QueryDefinitionError) as caught:
        sm.Animal.narrow(sm.Dog, sm.Dog)
    assert caught.value.code == "query-path-invalid"
