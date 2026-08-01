"""Find Query frontend spellings (python.md §2):
``.include(*paths)`` (deep-fetch, chained ``Rel[T]`` class access, hop-level
``.narrow()``), relationship ``.exists()`` / ``.not_exists()`` quantifiers, the
``Entity.narrow(...)`` constructor, and the query-level ``.narrow(...)``
clause. Authoring reaches no model, so what a spelling BUILDS is checked here
directly and what a model makes of it runs through the shared read gate
`preflight_find`, the seam every execution path calls.

A deeper relationship hop is composed rather than resolved: the segment is
spelled from the path's own target, and the model settles its legality at that
same gate. ``test_relationship_hops`` pins the composition and the two authoring
facts it erases; here a multi-hop include is exercised only as far as it needs.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

from _support import inheritance_models as im
from _support import snapshot_models as sm
from _support.query_probes import lowered_operation
from parallax.conformance import read_models
from parallax.conformance.animal_owner import ANIMAL_MODEL as _ANIMAL_MODEL
from parallax.conformance.graph_models import Policy
from parallax.conformance.read_models import Animal, Cat, Dog, Pet, WildBoar
from parallax.core import (
    MANY_TO_ONE,
    TX_TIME,
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    DomainModel,
    Entity,
    QueryDefinitionError,
    Rel,
    TablePerHierarchy,
    UnsupportedFeatureError,
    attr,
    rel,
)
from parallax.core.entity import FindQuery, RelationshipPath
from parallax.core.entity._model import model_of
from parallax.core.entity._query import build_find_query
from parallax.core.metamodel import EntityIdentity
from parallax.core.op_algebra import (
    All,
    DeepFetch,
    Exists,
    Limit,
    Narrow,
    NavigationPath,
    NotExists,
    OperationRejectedError,
    PathRootNarrow,
    PathSegment,
)
from parallax.snapshot.handle._preflight import preflight_find

# The animal family's model composes its own polymorphic owner alongside it, so
# it is the composition every case here is measured against at the gate below.
# Authoring reaches no model, so these classes are queryable without one; what a
# model supplies is something to EXECUTE a query against, which is why every case
# here reaches the preflight rather than a connection.
assert _ANIMAL_MODEL is not None
_DOCUMENTS = read_models.DOCUMENT_MODEL


def preflighted(
    query: FindQuery[Any, Any], models: DomainModel = _ANIMAL_MODEL
) -> FindQuery[Any, Any]:
    """``query`` after the shared read preflight accepted it against ``models``,
    which defaults to the corpus animal model whose family every include/narrow
    case here traverses.

    Runs exactly what executing the query would run before any I/O, and answers
    the query itself so a case can go on to assert its canonical lowering. A
    rejection propagates.
    """
    preflight_find(query, model=model_of(models))
    return query


_LOCAL_NS = "parallax.tests.include"
_DOC_NS = "parallax.compatibility"


class Keeper(Entity, table="keeper", namespace=_LOCAL_NS):
    id: Attr[int] = attr(primary_key=True)


class Beast(
    Entity,
    table="beast",
    namespace=_LOCAL_NS,
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    keeper_id: Attr[int | None]


class Hound(Beast, namespace=_LOCAL_NS, inheritance=ConcreteSubtype(tag_value="hound")):
    # A relationship a SUBTYPE declares itself, so a path seeded through `Hound`
    # carries the relationship identity `Hound.handler` rather than an inherited
    # one. Every corpus family declares its relationships on the root, so this
    # shape reaches the root-guard rule from nowhere else.
    handler: Rel[Keeper | None] = rel(cardinality=MANY_TO_ONE, join=("keeper_id", "id"))


KENNEL = DomainModel(Beast, Hound, Keeper)


# --------------------------------------------------------------------------- #
# .include(...) — deep-fetch path building.                                   #
# --------------------------------------------------------------------------- #
def test_single_hop_include_builds_a_deep_fetch_node() -> None:
    query = sm.SnapOrder.where(sm.SnapOrder.all).include(sm.SnapOrder.items)
    op = lowered_operation(query)
    assert isinstance(op, DeepFetch)
    assert op.paths == (NavigationPath(segments=(PathSegment(rel="SnapOrder.items"),)),)


def test_multi_hop_include_resolves_the_deeper_hop_against_the_model() -> None:
    query = sm.SnapOrder.where(sm.SnapOrder.all).include(sm.SnapOrder.items.statuses)
    op = lowered_operation(query)
    assert isinstance(op, DeepFetch)
    assert op.paths == (
        NavigationPath(
            segments=(
                PathSegment(rel="SnapOrder.items"),
                PathSegment(rel="SnapOrderItem.statuses"),
            )
        ),
    )


def test_a_path_that_already_continued_cannot_continue_again() -> None:
    # A composed hop points at an Entity the path names no class for, so a third
    # hop has no owner to spell itself from.
    bare: RelationshipPath[sm.SnapOrder, Any] = RelationshipPath(
        segments=(PathSegment(rel="SnapOrder.items"),), target=None
    )
    with pytest.raises(AttributeError, match="already continued past the hop"):
        _ = bare.statuses


def test_a_deeper_hop_naming_no_declared_relationship_is_refused_at_the_gate() -> None:
    query = sm.SnapOrder.where(sm.SnapOrder.all).include(sm.SnapOrder.items.bogus_relationship)
    with pytest.raises(ValueError, match="names no declared relationship on SnapOrderItem"):
        preflighted(query, sm.SNAP_ORDERS_MODEL)


def test_include_accumulates_across_calls() -> None:
    query = (
        sm.SnapOrder.where(sm.SnapOrder.all)
        .include(sm.SnapOrder.items)
        .include(sm.SnapOrder.statuses)
    )
    op = lowered_operation(query)
    assert isinstance(op, DeepFetch)
    assert len(op.paths) == 2


def test_include_with_no_paths_raises() -> None:
    with pytest.raises(QueryDefinitionError, match="at least one path"):
        sm.SnapOrder.where(sm.SnapOrder.all).include()


def test_include_of_an_undeclared_relationship_raises_at_build() -> None:
    with pytest.raises(AttributeError, match="statuses"):
        sm.SnapOrderStatus.where(sm.SnapOrderStatus.all).include(sm.SnapOrderStatus.statuses)  # type: ignore[attr-defined] - deliberate reference to an undeclared member to drive the error


def test_relationship_path_dynamic_hop_rejects_a_private_name() -> None:
    with pytest.raises(AttributeError):
        sm.SnapOrder.items.__getattr__("_hidden")


def test_hop_narrow_derives_the_narrowed_view_path_segment() -> None:
    path = im.Folder.documents.narrow(im.Invoice, im.Receipt)
    assert path.segments[-1].rel == "Folder.documents"
    assert set(path.segments[-1].narrow) == {"Invoice", "Receipt"}


def test_include_of_a_narrowed_path_serializes_the_hop_narrow() -> None:
    query = im.Folder.where(im.Folder.all).include(im.Folder.documents.narrow(im.Invoice))
    op = lowered_operation(query)
    assert isinstance(op, DeepFetch)
    assert op.paths[0].segments[0].narrow == ("Invoice",)


# --------------------------------------------------------------------------- #
# Path-ROOT guards: reaching an INHERITED relationship through a subtype.      #
# --------------------------------------------------------------------------- #
def test_reaching_an_inherited_relationship_through_a_subtype_guards_the_path_root() -> None:
    # `owner` is declared once, on the abstract root, so a subtype does not
    # redeclare it: `Dog.owner` keeps the one relationship identity `Animal.owner`
    # and records `Dog` as the path's SOURCE, which the query turns into the guard
    # beside `segments` — never a per-subtype relationship and never a segment
    # narrow.
    path = Dog.owner
    assert path.segments == (PathSegment(rel="Animal.owner"),)
    assert path.source == "Dog"
    op = lowered_operation(Animal.where(Animal.all).include(path))
    assert isinstance(op, DeepFetch)
    assert op.paths[0].narrow == PathRootNarrow(entity="Animal", to=("Dog",))


def test_a_subtype_declared_relationship_guards_the_path_root_the_same_way() -> None:
    # `handler` is declared BY `Hound`, so the path's relationship identity and its
    # access source name the same Entity. The guard follows from the source against
    # the QUERIED position, not from that comparison, so a subtype-declared path
    # rooted at the family root guards exactly as an inherited one does.
    path = Hound.handler
    assert path.segments == (PathSegment(rel="Hound.handler"),)
    assert path.source == "Hound"
    op = lowered_operation(Beast.where(Beast.all).include(path))
    assert isinstance(op, DeepFetch)
    assert op.paths[0].narrow == PathRootNarrow(entity="Beast", to=("Hound",))


def test_a_subtype_declared_relationship_queried_at_its_own_position_guards_nothing() -> None:
    # The same path rooted at `Hound` starts from every queried object already.
    op = lowered_operation(Hound.where(Hound.all).include(Hound.handler))
    assert isinstance(op, DeepFetch)
    assert op.paths[0].narrow is None


def test_reaching_a_relationship_through_its_declaring_class_guards_nothing() -> None:
    op = lowered_operation(Animal.where(Animal.all).include(Animal.owner))
    assert isinstance(op, DeepFetch)
    assert op.paths[0].narrow is None


def test_include_through_two_subtypes_authors_two_guarded_paths() -> None:
    op = lowered_operation(Animal.where(Animal.all).include(Dog.owner, Cat.owner))
    assert isinstance(op, DeepFetch)
    assert op.paths == (
        NavigationPath(
            segments=(PathSegment(rel="Animal.owner"),),
            narrow=PathRootNarrow(entity="Animal", to=("Dog",)),
        ),
        NavigationPath(
            segments=(PathSegment(rel="Animal.owner"),),
            narrow=PathRootNarrow(entity="Animal", to=("Cat",)),
        ),
    )


def test_a_guarded_path_keeps_its_root_guard_through_deeper_and_narrowed_hops() -> None:
    # The guard qualifies the path, not a hop: continuing the path resolves the
    # deeper hop against the CURRENT target and leaves the root guard alone, and a
    # hop-level `.narrow()` adds its own segment narrow beside it.
    op = lowered_operation(Animal.where(Animal.all).include(Pet.owner.pets.narrow(Dog)))
    assert isinstance(op, DeepFetch)
    assert op.paths == (
        NavigationPath(
            segments=(
                PathSegment(rel="Animal.owner"),
                PathSegment(rel="Person.pets", narrow=("Dog",)),
            ),
            narrow=PathRootNarrow(entity="Animal", to=("Pet",)),
        ),
    )


def test_a_root_guard_outside_the_queried_position_is_rejected_at_the_gate() -> None:
    # A read already narrowed to the Pet branch cannot guard a path to the sibling
    # WildBoar: the guard is clamped to the active position exactly as an
    # operation-position narrow is. The suppression is the static half, which
    # `include`'s own parameter now states — a Relationship Path is covariant in
    # its source, so a sibling's path never reaches this query's position, and an
    # ignore that goes idle fails `just python-typecheck`.
    with pytest.raises(OperationRejectedError) as exc:
        preflighted(Pet.where(Pet.all).include(WildBoar.owner))  # pyright: ignore[reportArgumentType]
    assert exc.value.rule == "narrow-outside-position"


def test_a_query_narrow_does_not_restrict_which_root_guards_are_legal() -> None:
    # `.narrow(...)` filters the RESULT while a guard selects sources, so legality
    # is measured against the queried POSITION. A guard disjoint from the narrowed
    # result is therefore accepted and simply admits no queried object — the same
    # observation as a guard no result row happens to match.
    op = lowered_operation(Animal.where(Animal.all).narrow(Cat).include(Dog.owner))
    assert isinstance(op, DeepFetch)
    assert op.paths[0].narrow == PathRootNarrow(entity="Animal", to=("Dog",))


# --------------------------------------------------------------------------- #
# Relationship .exists() / .not_exists() quantifiers.                                  #
# --------------------------------------------------------------------------- #
def test_any_with_no_predicates_is_a_bare_existence_test() -> None:
    predicate = sm.SnapOrder.items.exists()
    assert predicate.op == Exists(rel="SnapOrder.items", op=None)


def test_any_with_predicates_conjoins_the_interior() -> None:
    predicate = sm.SnapOrder.items.exists(sm.SnapOrderItem.sku == "A")
    op = predicate.op
    assert isinstance(op, Exists)
    assert op.rel == "SnapOrder.items"


def test_none_builds_not_exists() -> None:
    predicate = sm.SnapOrder.items.not_exists()
    assert predicate.op == NotExists(rel="SnapOrder.items", op=None)


def test_any_none_on_a_multi_hop_path_is_rejected() -> None:
    with pytest.raises(ValueError, match="single relationship hop"):
        sm.SnapOrder.items.statuses.exists()


def test_a_quantifier_predicate_builds_a_query() -> None:
    # Order.items.exists(...) is a legal quantifier; the query builds cleanly.
    query = sm.SnapOrder.where(sm.SnapOrder.items.exists(sm.SnapOrderItem.sku == "A"))
    assert lowered_operation(query) is not None


def test_narrow_inside_a_relationship_scope_must_name_the_target_exactly() -> None:
    # Folder.documents targets Document (the family root); narrowing to a
    # concrete subtype inside the hop's own scope is legal.
    query = im.Folder.where(
        im.Folder.documents.exists(im.Document.narrow(im.Invoice, where=im.Invoice.amount_due > 0))
    )
    assert lowered_operation(query) is not None


# --------------------------------------------------------------------------- #
# Entity.narrow(...) constructor + relationship-scope exact-naming.            #
# --------------------------------------------------------------------------- #
def test_narrow_constructor_builds_the_canonical_node() -> None:
    predicate = im.Document.narrow(im.Invoice, im.Receipt)
    assert predicate.op == Narrow(entity="Document", to=("Invoice", "Receipt"), operand=All())


def test_narrow_with_where_scopes_attribute_access_to_the_subtype() -> None:
    predicate = im.Document.narrow(im.Invoice, where=im.Invoice.amount_due > 100)
    op = predicate.op
    assert isinstance(op, Narrow)
    assert op.to == ("Invoice",)


def test_narrow_or_composition_of_two_branches_validates_at_where_build() -> None:
    query = im.Document.where(
        im.Document.narrow(im.Invoice, where=im.Invoice.amount_due > 5)
        | im.Document.narrow(im.Receipt, where=im.Receipt.paid_amount > 5)
    )
    assert lowered_operation(query) is not None


def test_narrow_broadening_outside_the_threaded_position_is_rejected() -> None:
    # FinancialDocument's effective set is {Invoice, Receipt}; nesting a
    # same-position narrow to Memo (outside it) must be rejected.
    with pytest.raises(OperationRejectedError) as caught:
        preflighted(im.FinancialDocument.where(im.FinancialDocument.narrow(im.Memo)), _DOCUMENTS)
    assert caught.value.rule == "narrow-outside-position"


# --------------------------------------------------------------------------- #
# The whole-query .narrow(...) clause: single-shot, converges on the           #
# identical canonical node as the constructor form, grants no retroactive      #
# attribute scope to already-built `where` arguments.                         #
# --------------------------------------------------------------------------- #
def test_query_level_narrow_wraps_the_conjoined_predicate() -> None:
    query = im.Document.where(im.Document.all).narrow(im.Invoice, im.Receipt)
    op = lowered_operation(query)
    assert isinstance(op, Narrow)
    assert op.entity == "Document"
    assert op.to == ("Invoice", "Receipt")
    assert op.operand == All()


def test_query_level_narrow_is_single_shot() -> None:
    query = im.Document.where(im.Document.all).narrow(im.Invoice)
    with pytest.raises(QueryDefinitionError, match="single-shot"):
        query.narrow(im.Receipt)


def test_clause_and_constructor_forms_converge_on_the_identical_node() -> None:
    via_clause = lowered_operation(im.Document.where(im.Document.all).narrow(im.Invoice))
    via_constructor = lowered_operation(im.Document.where(im.Document.narrow(im.Invoice)))
    assert via_clause == via_constructor


def test_subtype_attribute_outside_narrow_scope_is_rejected_at_the_gate() -> None:
    # The predicate is measured against the UNCONSTRAINED queried position — a
    # later `.narrow(...)` clause grants no retroactive scope. The suppression is
    # the static half: `Predicate` is contravariant, so a subtype's predicate
    # never reaches an ancestor's position, and an ignore that goes idle fails
    # `just python-typecheck`.
    with pytest.raises(OperationRejectedError) as caught:
        preflighted(im.Document.where(im.Invoice.amount_due > 3), _DOCUMENTS)  # pyright: ignore[reportArgumentType]
    assert caught.value.rule == "subtype-attribute-outside-narrow-scope"


def test_a_query_states_no_model_rule_until_it_reaches_a_model() -> None:
    # Authoring reaches no model, so a query carries the very predicate the
    # gated `Document.where(...)` above refuses. That is what lets the
    # operation-shaping clauses be exercised with no whole model behind them, and
    # it is why the rule is stated where the model is certain.
    out_of_scope = im.Invoice.amount_due > 3
    query = build_find_query(EntityIdentity(_DOC_NS, "Document"), (out_of_scope,))
    assert lowered_operation(query) == out_of_scope.op
    assert lowered_operation(query.limit(2)) == Limit(operand=out_of_scope.op, count=2)


def test_the_narrow_clauses_no_retroactive_scope_rule_is_static_only() -> None:
    # The clause and the scoped constructor converge on ONE canonical node, so no
    # model-aware rule can refuse the first spelling while accepting the second:
    # the operation the gate sees is the same document either way, and its own
    # rule makes the narrowed set the position its operand is measured in.
    #
    # What still refuses the spelling is the parameter: `Predicate[Invoice]` never
    # addresses a `Document` position, so the suppression below is load-bearing
    # and an ignore that goes idle fails `just python-typecheck`. That is the
    # whole remaining force of "a narrow clause grants no retroactive scope".
    narrowed = im.Document.where(
        im.Invoice.amount_due > 3  # pyright: ignore[reportArgumentType]
    ).narrow(im.Invoice)
    scoped = im.Document.where(im.Document.narrow(im.Invoice, where=im.Invoice.amount_due > 3))
    assert lowered_operation(narrowed) == lowered_operation(scoped)
    preflighted(narrowed, _DOCUMENTS)


# --------------------------------------------------------------------------- #
# .history() / .as_of_range() + .include(...): the snapshot-history-includes  #
# deferral (spec §3) — UnsupportedFeatureError, distinct from a validation     #
# error, in both call orders.                                                 #
# --------------------------------------------------------------------------- #
def test_history_then_include_is_deferred() -> None:
    with pytest.raises(UnsupportedFeatureError, match="snapshot-history-includes"):
        Policy.where(Policy.all).history(TX_TIME).include(Policy.coverages)


def test_include_then_history_is_deferred() -> None:
    with pytest.raises(UnsupportedFeatureError, match="snapshot-history-includes"):
        Policy.where(Policy.all).include(Policy.coverages).history(TX_TIME)


def test_as_of_range_then_include_is_deferred() -> None:
    window = (dt.datetime(2024, 1, 1, tzinfo=dt.UTC), dt.datetime(2024, 6, 1, tzinfo=dt.UTC))
    with pytest.raises(UnsupportedFeatureError, match="snapshot-history-includes"):
        Policy.where(Policy.all).as_of_range(valid_time=window).include(Policy.coverages)


def test_include_then_as_of_range_is_deferred() -> None:
    window = (dt.datetime(2024, 1, 1, tzinfo=dt.UTC), dt.datetime(2024, 6, 1, tzinfo=dt.UTC))
    with pytest.raises(UnsupportedFeatureError, match="snapshot-history-includes"):
        Policy.where(Policy.all).include(Policy.coverages).as_of_range(valid_time=window)


def test_a_narrow_clause_requires_at_least_one_subtype() -> None:
    # A segment records "no narrow" as an empty list, so accepting a narrow to
    # nothing would answer the un-narrowed query rather than refuse the request.
    with pytest.raises(QueryDefinitionError, match="at least one subtype") as caught:
        im.Document.where(im.Document.all).narrow()
    assert caught.value.code == "query-clause-invalid"
