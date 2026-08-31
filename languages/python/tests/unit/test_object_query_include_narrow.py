"""Object Query frontend spellings (python.md §2):
``.include(*paths)`` (deep-fetch, chained ``Rel[T]`` class access, hop-level
``.narrow()``), relationship ``.exists()`` / ``.not_exists()`` quantifiers, the
``Entity.narrow(...)`` constructor, and the query-level ``.narrow(...)``
clause. Authoring reaches no model, so what a spelling BUILDS is checked here
directly and what a model makes of it runs through the shared read gate
`preflight`, the seam every execution path calls.

A deeper relationship hop is composed rather than resolved: the segment is
spelled from the path's own target, and the model settles its legality at that
same gate. ``test_relationship_hops`` pins the composition and the two authoring
facts it erases; here a multi-hop include is exercised only as far as it needs.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, cast

import pytest

from _support import inheritance_models as im
from _support import snapshot_models as sm
from _support.query_probes import canonical_query
from parallax.conformance import read_models
from parallax.conformance.animal_owner import ANIMAL_MODEL as _ANIMAL_MODEL
from parallax.conformance.graph_models import POLICY_MODEL, Policy
from parallax.conformance.read_models import Animal, Cat, Dog, Pet, WildBoar
from parallax.core import (
    LATEST,
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
    attr,
    rel,
)
from parallax.core.base import TIMESTAMP
from parallax.core.entity import RelationshipPath
from parallax.core.entity._entity import build_object_query
from parallax.core.entity._model import model_of
from parallax.core.metamodel import EntityIdentity
from parallax.core.object_query import (
    AsOf,
    AsOfRange,
    History,
    IncludePath,
    IncludeSegment,
)
from parallax.core.object_query._fluent import ObjectQuery, object_query_node
from parallax.core.predicate import All, Exists, ModelRejectedError, Narrow, NotExists, Or
from parallax.core.wire import encode_wire
from parallax.snapshot import DeferredFeatureError
from parallax.snapshot.handle._preflight import preflight

# The animal family's model composes its own polymorphic owner alongside it, so
# it is the composition every case here is measured against at the gate below.
# Authoring reaches no model, so these classes are queryable without one; what a
# model supplies is something to EXECUTE a query against, which is why every case
# here reaches the preflight rather than a connection.
assert _ANIMAL_MODEL is not None
_DOCUMENTS = read_models.DOCUMENT_MODEL


def preflighted(
    query: ObjectQuery[Any, Any], models: DomainModel = _ANIMAL_MODEL
) -> ObjectQuery[Any, Any]:
    """``query`` after the shared read preflight accepted it against ``models``,
    which defaults to the corpus animal model whose family every include/narrow
    case here traverses.

    Runs exactly what executing the query would run before any I/O, and answers
    the query itself so a case can go on to assert its canonical lowering. A
    rejection propagates.
    """
    preflight(object_query_node(query), model=model_of(models), form="graph")
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
    includes = canonical_query(query).includes
    assert includes == (
        IncludePath(segments=(IncludeSegment(rel="parallax.compatibility.SnapOrder.items"),)),
    )


def test_multi_hop_include_resolves_the_deeper_hop_against_the_model() -> None:
    query = sm.SnapOrder.where(sm.SnapOrder.all).include(sm.SnapOrder.items.statuses)
    includes = canonical_query(query).includes
    assert includes == (
        IncludePath(
            segments=(
                IncludeSegment(rel="parallax.compatibility.SnapOrder.items"),
                IncludeSegment(rel="parallax.compatibility.SnapOrderItem.statuses"),
            )
        ),
    )


def test_a_path_that_already_continued_cannot_continue_again() -> None:
    # A composed hop points at an Entity the path names no class for, so a third
    # hop has no owner to spell itself from.
    bare: RelationshipPath[sm.SnapOrder, Any] = RelationshipPath(
        segments=(IncludeSegment(rel="parallax.compatibility.SnapOrder.items"),), target=None
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
    includes = canonical_query(query).includes
    assert len(includes) == 2


def test_include_accumulation_canonicalizes_order_and_literal_duplicates() -> None:
    query = (
        sm.SnapOrder.where(sm.SnapOrder.all)
        .include(sm.SnapOrder.statuses, sm.SnapOrder.items)
        .include(sm.SnapOrder.items)
    )
    includes = canonical_query(query).includes
    assert includes == (
        IncludePath(segments=(IncludeSegment(rel="parallax.compatibility.SnapOrder.items"),)),
        IncludePath(segments=(IncludeSegment(rel="parallax.compatibility.SnapOrder.statuses"),)),
    )


def test_include_retains_only_the_maximal_equivalent_path() -> None:
    query = sm.SnapOrder.where(sm.SnapOrder.all).include(
        sm.SnapOrder.items,
        sm.SnapOrder.items.statuses,
    )
    includes = canonical_query(query).includes
    assert includes == (
        IncludePath(
            segments=(
                IncludeSegment(rel="parallax.compatibility.SnapOrder.items"),
                IncludeSegment(rel="parallax.compatibility.SnapOrderItem.statuses"),
            )
        ),
    )


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
    assert path.segments[-1].rel == "parallax.compatibility.Folder.documents"
    assert set(path.segments[-1].narrow_to) == {
        "parallax.compatibility.Invoice",
        "parallax.compatibility.Receipt",
    }


def test_include_of_a_narrowed_path_serializes_the_hop_narrow() -> None:
    query = im.Folder.where(im.Folder.all).include(im.Folder.documents.narrow(im.Invoice))
    includes = canonical_query(query).includes
    assert includes[0].segments[0].narrow_to == ("parallax.compatibility.Invoice",)


def test_include_canonicalization_keeps_broad_and_narrowed_paths_distinct() -> None:
    query = im.Folder.where(im.Folder.all).include(
        im.Folder.documents.narrow(im.Invoice),
        im.Folder.documents,
        im.Folder.documents.narrow(im.Invoice),
    )
    includes = canonical_query(query).includes
    assert includes == (
        IncludePath(segments=(IncludeSegment(rel="parallax.compatibility.Folder.documents"),)),
        IncludePath(
            segments=(
                IncludeSegment(
                    rel="parallax.compatibility.Folder.documents",
                    narrow_to=("parallax.compatibility.Invoice",),
                ),
            )
        ),
    )


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
    assert path.segments == (IncludeSegment(rel="parallax.compatibility.Animal.owner"),)
    assert path.source == "parallax.compatibility.Dog"
    includes = canonical_query(Animal.where(Animal.all).include(path)).includes
    assert includes[0].applies_to == ("parallax.compatibility.Dog",)


def test_a_subtype_declared_relationship_guards_the_path_root_the_same_way() -> None:
    # `handler` is declared BY `Hound`, so the path's relationship identity and its
    # access source name the same Entity. The guard follows from the source against
    # the QUERIED position, not from that comparison, so a subtype-declared path
    # rooted at the family root guards exactly as an inherited one does.
    path = Hound.handler
    assert path.segments == (IncludeSegment(rel="parallax.tests.include.Hound.handler"),)
    assert path.source == "parallax.tests.include.Hound"
    includes = canonical_query(Beast.where(Beast.all).include(path)).includes
    assert includes[0].applies_to == ("parallax.tests.include.Hound",)


def test_a_subtype_declared_relationship_queried_at_its_own_position_guards_nothing() -> None:
    # The same path rooted at `Hound` starts from every queried object already.
    includes = canonical_query(Hound.where(Hound.all).include(Hound.handler)).includes
    assert includes[0].applies_to is None


def test_reaching_a_relationship_through_its_declaring_class_guards_nothing() -> None:
    includes = canonical_query(Animal.where(Animal.all).include(Animal.owner)).includes
    assert includes[0].applies_to is None


def test_include_through_two_subtypes_authors_two_guarded_paths() -> None:
    includes = canonical_query(Animal.where(Animal.all).include(Dog.owner, Cat.owner)).includes
    assert includes == (
        IncludePath(
            segments=(IncludeSegment(rel="parallax.compatibility.Animal.owner"),),
            applies_to=("parallax.compatibility.Cat",),
        ),
        IncludePath(
            segments=(IncludeSegment(rel="parallax.compatibility.Animal.owner"),),
            applies_to=("parallax.compatibility.Dog",),
        ),
    )


def test_a_guarded_path_keeps_its_root_guard_through_deeper_and_narrowed_hops() -> None:
    # The guard qualifies the path, not a hop: continuing the path resolves the
    # deeper hop against the CURRENT target and leaves the root guard alone, and a
    # hop-level `.narrow()` adds its own segment narrow beside it.
    includes = canonical_query(
        Animal.where(Animal.all).include(Pet.owner.pets.narrow(Dog))
    ).includes
    assert includes == (
        IncludePath(
            segments=(
                IncludeSegment(rel="parallax.compatibility.Animal.owner"),
                IncludeSegment(
                    rel="parallax.compatibility.Person.pets",
                    narrow_to=("parallax.compatibility.Dog",),
                ),
            ),
            applies_to=("parallax.compatibility.Pet",),
        ),
    )


def test_a_root_guard_outside_the_queried_position_is_rejected_at_the_gate() -> None:
    # A read already narrowed to the Pet branch cannot guard a path to the sibling
    # WildBoar: the guard is clamped to the active position exactly as a
    # predicate-position narrow is. The suppression is the static half, which
    # `include`'s own parameter states — a Relationship Path is covariant in
    # its source, so a sibling's path never reaches this query's position, and an
    # ignore that goes idle fails `just python-typecheck`.
    with pytest.raises(ModelRejectedError) as exc:
        preflighted(Pet.where(Pet.all).include(WildBoar.owner))  # pyright: ignore[reportArgumentType]
    assert exc.value.rule == "narrow-outside-position"


def test_a_query_narrow_does_not_restrict_which_root_guards_are_legal() -> None:
    # `.narrow(...)` filters the RESULT while a guard selects sources, so legality
    # is measured against the queried POSITION. A guard disjoint from the narrowed
    # result is therefore accepted and simply admits no queried object — the same
    # observation as a guard no result row happens to match.
    includes = canonical_query(Animal.where(Animal.all).narrow(Cat).include(Dog.owner)).includes
    assert includes[0].applies_to == ("parallax.compatibility.Dog",)


# --------------------------------------------------------------------------- #
# Relationship .exists() / .not_exists() quantifiers.                                  #
# --------------------------------------------------------------------------- #
def test_any_with_no_predicates_is_a_bare_existence_test() -> None:
    predicate = sm.SnapOrder.items.exists()
    assert predicate.node == Exists(rel="parallax.compatibility.SnapOrder.items", op=None)


def test_any_with_predicates_conjoins_the_interior() -> None:
    predicate = sm.SnapOrder.items.exists(sm.SnapOrderItem.sku == "A")
    op = predicate.node
    assert isinstance(op, Exists)
    assert op.rel == "parallax.compatibility.SnapOrder.items"


def test_none_builds_not_exists() -> None:
    predicate = sm.SnapOrder.items.not_exists()
    assert predicate.node == NotExists(rel="parallax.compatibility.SnapOrder.items", op=None)


def test_any_none_on_a_multi_hop_path_is_rejected() -> None:
    with pytest.raises(QueryDefinitionError, match="single relationship hop") as caught:
        sm.SnapOrder.items.statuses.exists()
    assert caught.value.code == "query-path-invalid"


def test_a_quantifier_predicate_builds_a_query() -> None:
    # Order.items.exists(...) is a legal quantifier; the query builds cleanly.
    query = sm.SnapOrder.where(sm.SnapOrder.items.exists(sm.SnapOrderItem.sku == "A"))
    assert canonical_query(query) is not None


def test_narrow_inside_a_relationship_scope_must_name_the_target_exactly() -> None:
    # Folder.documents targets Document (the family root); narrowing to a
    # concrete subtype inside the hop's own scope is legal.
    query = im.Folder.where(
        im.Folder.documents.exists(im.Document.narrow(im.Invoice, where=im.Invoice.amount_due > 0))
    )
    assert canonical_query(query) is not None


# --------------------------------------------------------------------------- #
# Entity.narrow(...) constructor + relationship-scope exact-naming.            #
# --------------------------------------------------------------------------- #
def test_narrow_constructor_builds_the_canonical_node() -> None:
    predicate = im.Document.narrow(im.Invoice, im.Receipt)
    assert predicate.node == Narrow(
        to=("parallax.compatibility.Invoice", "parallax.compatibility.Receipt"),
        operand=All(),
    )


def test_narrow_alternatives_are_canonicalized_by_entity_identity() -> None:
    predicate = im.Document.narrow(im.Receipt, im.Invoice)
    assert predicate.node == Narrow(
        to=("parallax.compatibility.Invoice", "parallax.compatibility.Receipt"),
        operand=All(),
    )


def test_narrow_constructor_requires_at_least_one_subtype() -> None:
    with pytest.raises(QueryDefinitionError, match="at least one subtype") as caught:
        im.Document.narrow()
    assert caught.value.code == "query-path-invalid"


@pytest.mark.parametrize(
    "build",
    [
        lambda: im.Document.narrow(im.Invoice, im.Invoice),
        lambda: im.Document.where(im.Document.all).narrow(im.Invoice, im.Invoice),
        lambda: im.Folder.documents.narrow(im.Invoice, im.Invoice),
    ],
    ids=["predicate", "object-query", "relationship-path"],
)
def test_python_narrowing_rejects_an_exact_duplicate_at_construction(build: Any) -> None:
    with pytest.raises(QueryDefinitionError) as caught:
        build()
    assert caught.value.code == "query-path-invalid"


def test_model_aware_narrowing_rejects_overlapping_alternatives() -> None:
    query = im.Document.where(im.Document.narrow(im.FinancialDocument, im.Invoice))
    with pytest.raises(ModelRejectedError) as caught:
        preflighted(query, _DOCUMENTS)
    assert caught.value.rule == "subtype-selection-overlapping-alternatives"


def test_narrow_with_where_scopes_attribute_access_to_the_subtype() -> None:
    predicate = im.Document.narrow(im.Invoice, where=im.Invoice.amount_due > 100)
    op = predicate.node
    assert isinstance(op, Narrow)
    assert op.to == ("parallax.compatibility.Invoice",)
    assert op.operand == (im.Invoice.amount_due > 100).node


def test_narrow_or_composition_of_two_branches_validates_at_where_build() -> None:
    query = im.Document.where(
        im.Document.narrow(im.Invoice, where=im.Invoice.amount_due > 5)
        | im.Document.narrow(im.Receipt, where=im.Receipt.paid_amount > 5)
    )
    assert canonical_query(query) is not None


def test_narrow_broadening_outside_the_threaded_position_is_rejected() -> None:
    # FinancialDocument's effective set is {Invoice, Receipt}; nesting a
    # same-position narrow to Memo (outside it) must be rejected.
    with pytest.raises(ModelRejectedError) as caught:
        preflighted(im.FinancialDocument.where(im.FinancialDocument.narrow(im.Memo)), _DOCUMENTS)
    assert caught.value.rule == "narrow-outside-position"


# --------------------------------------------------------------------------- #
# The whole-query .narrow(...) clause: single-shot, and converging on the      #
# identical canonical node as the constructor form used as the whole filter.   #
# --------------------------------------------------------------------------- #
def test_query_level_narrow_fills_the_result_narrowing_clause() -> None:
    query = im.Document.where(im.Document.all).narrow(im.Invoice, im.Receipt)
    node = canonical_query(query)
    assert node.narrow_to == (
        "parallax.compatibility.Invoice",
        "parallax.compatibility.Receipt",
    )
    assert node.predicate == All()


def test_query_level_narrow_is_single_shot() -> None:
    query = im.Document.where(im.Document.all).narrow(im.Invoice)
    with pytest.raises(QueryDefinitionError, match="single-shot"):
        query.narrow(im.Receipt)


def test_the_clause_and_the_constructor_build_one_canonical_query() -> None:
    # Two spellings of one claim: narrowing the whole selection narrows the
    # RESULT, whichever clause states it. The constructor used as the whole
    # filter therefore fills `narrowTo` exactly as the clause does, and its own
    # scoped predicate becomes the query's predicate.
    via_clause = canonical_query(im.Document.where(im.Document.all).narrow(im.Invoice))
    via_constructor = canonical_query(im.Document.where(im.Document.narrow(im.Invoice)))
    assert via_clause == via_constructor
    assert via_clause.narrow_to == ("parallax.compatibility.Invoice",)
    assert via_clause.predicate == All()


def test_a_narrowing_reached_through_a_boolean_stays_a_filter() -> None:
    # The constructor is lifted only as the WHOLE filter. Combined with another
    # term it qualifies one operand of the selection, so the result position is
    # untouched and the narrowing stays exactly where it was authored.
    node = canonical_query(
        im.Document.where(im.Document.narrow(im.Invoice) | (im.Document.title == "x"))
    )
    assert node.narrow_to is None
    assert isinstance(node.predicate, Or)
    assert node.predicate.operands[0] == Narrow(
        to=("parallax.compatibility.Invoice",), operand=All()
    )


def test_subtype_attribute_outside_narrow_scope_is_rejected_at_the_gate() -> None:
    # A subtype's attribute reaches an ancestor position only where a narrowing
    # establishes its scope, and this query carries none at all. The suppression
    # is the static half: `Predicate` is contravariant, so a subtype's predicate
    # never reaches an ancestor's position, and an ignore that goes idle fails
    # `just python-typecheck`.
    with pytest.raises(ModelRejectedError) as caught:
        preflighted(im.Document.where(im.Invoice.amount_due > 3), _DOCUMENTS)  # pyright: ignore[reportArgumentType]
    assert caught.value.rule == "subtype-attribute-outside-narrow-scope"


def test_a_query_states_no_model_rule_until_it_reaches_a_model() -> None:
    # Authoring reaches no model, so a query carries the very predicate the
    # gated `Document.where(...)` above refuses. That is what lets the
    # result-shaping clauses be exercised with no whole model behind them, and
    # it is why the rule is stated where the model is certain.
    out_of_scope = im.Invoice.amount_due > 3
    query = build_object_query(EntityIdentity(_DOC_NS, "Document"), (out_of_scope,))
    assert canonical_query(query).predicate == out_of_scope.node
    assert canonical_query(query.limit(2)).limit == 2


def test_narrowing_last_is_refused_statically_and_only_statically() -> None:
    # No model-aware rule can refuse the clause-last spelling while accepting the
    # scoped constructor: result narrowing moves the position the predicate is
    # measured at, so both queries are validated against the narrowed set — and
    # both build the same canonical query.
    #
    # What refuses the clause-last spelling is the parameter: `Predicate[Invoice]`
    # never addresses a `Document` position, so the suppression below is
    # load-bearing and an ignore that goes idle fails `just python-typecheck`.
    # Narrowing FIRST is the spelling that states this query with the checker's
    # agreement.
    narrowed = im.Document.where(
        im.Invoice.amount_due > 3  # pyright: ignore[reportArgumentType]
    ).narrow(im.Invoice)
    scoped = im.Document.where(im.Document.narrow(im.Invoice, where=im.Invoice.amount_due > 3))
    preflighted(narrowed, _DOCUMENTS)
    preflighted(scoped, _DOCUMENTS)
    assert canonical_query(narrowed) == canonical_query(scoped)


# --------------------------------------------------------------------------- #
# .history() / .as_of_range() + .include(...): the snapshot-history-includes  #
# Feature is DEFERRED, not invalid (m-snapshot-read forbids any case mandating #
# its refusal), so the combination builds an ordinary Object Query in either     #
# call order and lowers to the canonical document the wire already defines.   #
# Its refusal is Snapshot's, at execution, and is pinned there                 #
# (test_snapshot_find.py / test_transaction_reads.py).                         #
# --------------------------------------------------------------------------- #
_WINDOW = (dt.datetime(2024, 1, 1, tzinfo=dt.UTC), dt.datetime(2024, 6, 1, tzinfo=dt.UTC))
_COVERAGES = (
    IncludePath(segments=(IncludeSegment(rel="parallax.compatibility.Policy.coverages"),)),
)


@pytest.mark.parametrize(
    "query",
    [
        Policy.where(Policy.all)
        .history(TX_TIME)
        .as_of(valid_time=LATEST)
        .include(Policy.coverages),
        Policy.where(Policy.all)
        .include(Policy.coverages)
        .history(TX_TIME)
        .as_of(valid_time=LATEST),
    ],
    ids=["history-then-include", "include-then-history"],
)
def test_history_with_includes_builds_in_either_order(query: ObjectQuery[Any, Any]) -> None:
    node = canonical_query(query)
    assert node.temporal == {
        "transaction-time": History(),
        "valid-time": AsOf("latest"),
    }
    assert node.includes == _COVERAGES


@pytest.mark.parametrize(
    "query",
    [
        Policy.where(Policy.all).as_of_range(valid_time=_WINDOW).include(Policy.coverages),
        Policy.where(Policy.all).include(Policy.coverages).as_of_range(valid_time=_WINDOW),
    ],
    ids=["range-then-include", "include-then-range"],
)
def test_as_of_range_with_includes_builds_in_either_order(query: ObjectQuery[Any, Any]) -> None:
    start, end = _WINDOW
    node = canonical_query(query)
    assert node.temporal == {
        "transaction-time": AsOf("latest"),
        "valid-time": AsOfRange(
            start=cast("str", encode_wire(TIMESTAMP, start)),
            end=cast("str", encode_wire(TIMESTAMP, end)),
        ),
    }
    assert node.includes == _COVERAGES


def test_a_deferred_combination_is_a_valid_query_the_gate_refuses_by_name() -> None:
    # The gate validates before it classifies, so reaching the deferral at all
    # proves the query is legal against the model: an invalid one would have
    # drawn `ModelRejectedError` one step earlier.
    query = (
        Policy.where(Policy.all).history(TX_TIME).as_of(valid_time=LATEST).include(Policy.coverages)
    )
    with pytest.raises(DeferredFeatureError) as caught:
        preflight(object_query_node(query), model=model_of(POLICY_MODEL), form="graph")
    assert caught.value.features == ("snapshot-history-includes",)


def test_a_narrow_clause_requires_at_least_one_subtype() -> None:
    # A segment records "no narrow" as an empty list, so accepting a narrow to
    # nothing would answer the un-narrowed query rather than refuse the request.
    with pytest.raises(QueryDefinitionError, match="at least one subtype") as caught:
        im.Document.where(im.Document.all).narrow()
    assert caught.value.code == "query-clause-invalid"
