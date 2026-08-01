"""Typed query composition: each static rejection beside its runtime twin.

`reportUnnecessaryTypeIgnoreComment` is `"error"` (`pyrightconfig.json`), so a
rule-coded suppression asserts in both directions: the expression must produce
exactly that diagnostic, and an ignore that goes idle fails `just
python-typecheck`. That inversion is this repository's only way to assert a type
error, which is why a case below carries its suppression and its runtime
rejection in ONE test — static and runtime agreement proved by construction
rather than in two processes that never meet.

Two suppressions here have no runtime twin, and both are deliberate.
`test_a_subtype_spelling_of_an_inherited_member_is_narrower_than_the_model_is`
asserts a SUCCESSFUL serialization under a `reportArgumentType` ignore. The
parameter comes from the class an access went through and the wire keeps the
class that declares the member, so `Animal.where(Dog.name == …)` reads as
`Predicate[Dog]` statically while emitting the `Animal.name` every concrete
under `Animal` answers. No type the checker can see separates it from the
rejection that IS wanted — `Animal.where(Dog.bark_volume > …)`, where the member
really is the subtype's — so the parameter is strictly narrower than the model
there, and that test is where the asymmetry is recorded rather than discovered.
The second is `Entity.all`: an `all` node names no position on the wire, so
nothing downstream can tell `Dog.all` from `Animal.all` and the parameter is the
only place an unfiltered query written at the wrong position is refused.

Authoring reaches no model, so every runtime twin here runs the shared read gate
`preflight_find` — the seam `Database.find` and `Transaction.find` both call —
rather than expecting a rejection from `Entity.where`. That is where the
model-aware validator states these rules now, and it is what covers the wire path
and any untyped caller identically.

The mechanism under test is variance. `Predicate[E]` holds only a canonical
operation node, so `E` appears in no field and inference would read it as
bivariant; the checker-only phantom in `entity._expressions` puts `E` in an input
position and makes it contravariant. Contravariance IS the inheritance rule: an
ancestor's member addresses every descendant position, a descendant's member
addresses none of its ancestors'. Both directions are pinned here, because a
parameter that had come out invariant would pass the rejection half and fail the
acceptance half. Every other addressed value carries its own phantom and its own
case below: a Sort Key and an Assignment are contravariant for the same reason,
an `all` predicate likewise, and a Relationship Path is COVARIANT in both of its
parameters — a path rooted at a descendant is a legal include source of the
ancestor's query, and a path narrowed to a descendant target stands wherever the
broad hop does.

Where a claim is about a value's position rather than about a clause, the
position is spelled as an annotation — `key: SortKey[Cat | Dog] = …` — because
the query value that will carry a narrowed RESULT parameter is `FindQuery[E, S]`
and it does not exist yet. The annotation is exactly the parameter its
`order_by` will supply, and each is paired with the runtime twin the same
narrowing produces through the gate.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import PydanticUserError

from _support import snapshot_models
from _support.snapshot_models import (
    Animal,
    AnimalOwner,
    Cat,
    Dog,
    SnapOrder,
    SnapOrderStatus,
)
from parallax.core import (
    ONE_TO_MANY,
    ONE_TO_ONE,
    AbstractRoot,
    AllPredicate,
    Attr,
    ConcreteSubtype,
    DomainModel,
    Entity,
    EntityDefinitionError,
    Int32,
    ModelCopyError,
    OperationRejectedError,
    Predicate,
    QueryDefinitionError,
    Rel,
    RelationshipPath,
    SortKey,
    Statement,
    TablePerHierarchy,
    attr,
    rel,
)
from parallax.core.entity import AttributeAssignment
from parallax.core.entity._model import model_of
from parallax.core.op_algebra import All
from parallax.core.unit_work import (
    PredicateSelection,
    PredicateWrite,
    WriteAssignment,
    WriteInstructionError,
    validate_instruction,
)
from parallax.snapshot.handle._preflight import preflight_find

_ANIMALS = snapshot_models.ANIMAL_MODEL
_ORDERS = snapshot_models.SNAP_ORDERS_MODEL

_NS = "parallax.tests.typed"


# The shared animal fixture declares no relationship, so the Relationship Path
# cases need a family that does: one inherited relationship reachable through a
# subtype (the include-source claim), one to-many hop into a family (the hop
# narrow's bound), and all three declared relationship annotation shapes, so the
# element extraction is pinned on each.
class Badge(Entity, table="typed_badge", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    keeper_id: Attr[int]


class Beast(
    Entity,
    table="typed_beast",
    namespace=_NS,
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    keeper_id: Attr[int | None]
    name: Attr[str] = attr(max_length=32)
    keeper: Rel[Keeper | None] = rel(reverse_of="beasts")


class Hound(Beast, namespace=_NS, inheritance=ConcreteSubtype(tag_value="hound")):
    bay_volume: Attr[int | None] = attr(type=Int32)


class Feline(Beast, namespace=_NS, inheritance=ConcreteSubtype(tag_value="feline")):
    indoor: Attr[bool | None]


class Keeper(Entity, table="typed_keeper", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    beasts: Rel[tuple[Beast, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "keeper_id"))
    badge: Rel[Badge] = rel(cardinality=ONE_TO_ONE, join=("id", "keeper_id"), dependent=True)


_BESTIARY = DomainModel(Keeper, Badge, Beast, Hound, Feline)


def preflighted(statement: Statement, models: DomainModel = _ANIMALS) -> Statement:
    """``statement`` after the shared read preflight accepted it against ``models``,
    which defaults to the animal composition every composition case is written over.

    Runs exactly what executing the statement would run before any I/O, and
    answers the statement itself so a case can go on to assert its canonical
    lowering. A rejection propagates.
    """
    preflight_find(statement, model=model_of(models))
    return statement


# --------------------------------------------------------------------------- #
# Rejections: a predicate that does not address the queried position          #
# --------------------------------------------------------------------------- #


def test_a_subtype_predicate_never_addresses_an_ancestor_position() -> None:
    # `Predicate[Dog]` in an `Animal` position: the concrete subtype's member is
    # not available to every concrete the position resolves to, and narrowing is
    # the remedy the runtime rule names (see the narrow case below).
    with pytest.raises(OperationRejectedError) as caught:
        preflighted(Animal.where(Dog.bark_volume > 3))  # pyright: ignore[reportArgumentType]
    assert caught.value.rule == "subtype-attribute-outside-narrow-scope"


def test_an_unrelated_entitys_predicate_never_addresses_the_queried_position() -> None:
    # `Predicate[AnimalOwner]` in an `Animal` position. The two Entities share
    # one model and no inheritance family, so no narrow could rescue it — which
    # is exactly the distinction between this rule and the one above.
    with pytest.raises(OperationRejectedError) as caught:
        preflighted(Animal.where(AnimalOwner.name == "Ada"))  # pyright: ignore[reportArgumentType]
    assert caught.value.rule == "attribute-outside-active-position"


def test_an_unrelated_entitys_predicate_is_refused_from_the_other_side_too() -> None:
    # The same rule with the positions swapped, so neither direction is accepted
    # by an accident of which Entity happens to declare the member.
    with pytest.raises(OperationRejectedError) as caught:
        preflighted(AnimalOwner.where(Animal.name == "Ada"))  # pyright: ignore[reportArgumentType]
    assert caught.value.rule == "attribute-outside-active-position"


# --------------------------------------------------------------------------- #
# Acceptances: the direction contravariance must keep open                    #
# --------------------------------------------------------------------------- #


def test_an_ancestors_predicate_addresses_every_descendant_position() -> None:
    # The acceptance half of the same mechanism, and the case an INVARIANT
    # parameter would break: `Predicate[Animal]` lands in a `Dog` position
    # because a root-declared member is available to every concrete under it.
    assert preflighted(Dog.where(Animal.name == "Ada")).serialize() == {
        "eq": {"attr": "Animal.name", "value": "Ada"}
    }


def test_an_inherited_member_is_parameterized_by_the_class_it_is_reached_through() -> None:
    # `Dog.name` reaches `Animal`'s descriptor through `Dog`, so it yields a
    # `Dog`-positioned predicate while the wire keeps the DECLARING Entity — the
    # spelling that makes the reference applicable to every concrete under
    # `Animal`. The two are different questions and the two answers differ.
    assert preflighted(Dog.where(Dog.name == "Ada")).serialize() == {
        "eq": {"attr": "Animal.name", "value": "Ada"}
    }


def test_a_subtype_spelling_of_an_inherited_member_is_narrower_than_the_model_is() -> None:
    # The one composition the parameter refuses where the model accepts it, and
    # the reason is the same mechanism read from the other side: `Dog.name`
    # addresses `Dog` because that is the class it was reached through, while the
    # wire it builds spells the DECLARING `Animal.name`, which every concrete
    # under `Animal` answers. The remedy is to spell the member through the class
    # that declares it, and the suppression records the asymmetry rather than
    # leaving it to be discovered.
    assert preflighted(Animal.where(Dog.name == "Ada")).serialize() == {  # pyright: ignore[reportArgumentType]
        "eq": {"attr": "Animal.name", "value": "Ada"}
    }


def test_a_conjunction_addresses_the_position_both_of_its_operands_address() -> None:
    # An ancestor's term and a descendant's term compose, and the combination
    # lands in the descendant's query — the case a combinator demanding one
    # shared parameter would refuse for a reason no rule states.
    assert preflighted(Dog.where((Animal.name == "Ada") & (Dog.bark_volume > 3))).serialize() == {
        "and": {
            "operands": [
                {"eq": {"attr": "Animal.name", "value": "Ada"}},
                {"greaterThan": {"attr": "Dog.barkVolume", "value": 3}},
            ]
        }
    }


def test_a_mixed_conjunction_reads_the_same_in_the_other_operand_order() -> None:
    # The same combination with the NARROWER term on the left. A combinator
    # that took the left operand's position would accept exactly one of these
    # two spellings, so both orders are pinned: the position a combination
    # addresses is the meet, which no operand order can move.
    assert preflighted(Dog.where((Dog.bark_volume > 3) & (Animal.name == "Ada"))).serialize() == {
        "and": {
            "operands": [
                {"greaterThan": {"attr": "Dog.barkVolume", "value": 3}},
                {"eq": {"attr": "Animal.name", "value": "Ada"}},
            ]
        }
    }


def test_a_mixed_conjunction_never_launders_the_descendants_term_upward() -> None:
    # The rejection half of the meet, and the laundering a left-biased
    # combinator admits: the ancestor's term is on the LEFT, so reading the
    # combination as the left operand's position would let a `Dog` member into
    # an `Animal` query with no diagnostic at all.
    with pytest.raises(OperationRejectedError) as caught:
        preflighted(
            Animal.where(
                (Animal.name == "Ada") & (Dog.bark_volume > 3)  # pyright: ignore[reportArgumentType]
            )
        )
    assert caught.value.rule == "subtype-attribute-outside-narrow-scope"


def test_the_same_laundering_is_refused_in_the_other_operand_order_too() -> None:
    # Its commuted twin, refused identically — the property that makes the
    # rejection a rule about the terms rather than about which one was typed
    # first.
    with pytest.raises(OperationRejectedError) as caught:
        preflighted(
            Animal.where(
                (Dog.bark_volume > 3) & (Animal.name == "Ada")  # pyright: ignore[reportArgumentType]
            )
        )
    assert caught.value.rule == "subtype-attribute-outside-narrow-scope"


def test_a_disjunction_addresses_the_meet_in_either_operand_order() -> None:
    # `|` carries the identical parameter, so the acceptance half holds for it
    # in both orders too — the combinator, not the combination, is what the
    # position comes from.
    ancestor_first = preflighted(
        Dog.where((Animal.name == "Ada") | (Dog.bark_volume > 3))
    ).serialize()
    descendant_first = preflighted(
        Dog.where((Dog.bark_volume > 3) | (Animal.name == "Ada"))
    ).serialize()
    assert ancestor_first == {
        "or": {
            "operands": [
                {"eq": {"attr": "Animal.name", "value": "Ada"}},
                {"greaterThan": {"attr": "Dog.barkVolume", "value": 3}},
            ]
        }
    }
    assert descendant_first == {
        "or": {
            "operands": [
                {"greaterThan": {"attr": "Dog.barkVolume", "value": 3}},
                {"eq": {"attr": "Animal.name", "value": "Ada"}},
            ]
        }
    }


def test_a_disjunction_launders_no_more_than_a_conjunction_does() -> None:
    # And the rejection half for `|`, on the operand order a left-biased
    # combinator would have admitted.
    with pytest.raises(OperationRejectedError) as caught:
        preflighted(
            Animal.where(
                (Animal.name == "Ada") | (Dog.bark_volume > 3)  # pyright: ignore[reportArgumentType]
            )
        )
    assert caught.value.rule == "subtype-attribute-outside-narrow-scope"


def test_the_disjunctions_laundering_is_refused_in_the_other_operand_order_too() -> None:
    # `|`'s commuted rejection, the twin of the `&` pair above. Without it the
    # descendant-first `__or__` could broaden or turn left-biased while every
    # other cell in the table stayed green: the forward operator alone solves the
    # meet in THIS order, so this is the case that would survive losing the
    # reflected twin.
    with pytest.raises(OperationRejectedError) as caught:
        preflighted(
            Animal.where(
                (Dog.bark_volume > 3) | (Animal.name == "Ada")  # pyright: ignore[reportArgumentType]
            )
        )
    assert caught.value.rule == "subtype-attribute-outside-narrow-scope"


def test_a_conjunction_of_one_positions_terms_keeps_that_position() -> None:
    # The composition does not launder a subtype's terms into an ancestor
    # position: two `Dog` terms combine to a `Dog` predicate, which the `Animal`
    # query refuses statically and the validator refuses again.
    with pytest.raises(OperationRejectedError) as caught:
        preflighted(
            Animal.where(
                (Dog.bark_volume > 3) & (Dog.bark_volume < 9)  # pyright: ignore[reportArgumentType]
            )
        )
    assert caught.value.rule == "subtype-attribute-outside-narrow-scope"


def test_a_narrow_scope_is_how_a_descendants_member_reaches_an_ancestor_position() -> None:
    # The sanctioned spelling of the first rejection above: `narrow` takes the
    # subtype's predicate and answers one in the narrowing class's own position,
    # so this composes where the bare subtype predicate cannot.
    assert preflighted(Animal.where(Animal.narrow(Dog, where=Dog.bark_volume > 3))).serialize() == {
        "narrow": {
            "entity": "Animal",
            "to": ["Dog"],
            "operand": {"greaterThan": {"attr": "Dog.barkVolume", "value": 3}},
        }
    }


# --------------------------------------------------------------------------- #
# What the parameters deliberately do not judge                               #
# --------------------------------------------------------------------------- #


def test_a_comparison_literal_is_the_wire_value_rather_than_the_members_python_type() -> None:
    # `price` is declared `Attr[Decimal]` and the neutral contract spells its
    # comparison literal as a number, so a value parameter narrowed to the
    # member's Python type would refuse the canonical spelling. The value stays
    # the wire's, and no suppression belongs here.
    assert preflighted(SnapOrder.where(SnapOrder.price >= 600.00), _ORDERS).serialize() == {
        "greaterThanEquals": {"attr": "SnapOrder.price", "value": 600.00}
    }


def test_an_equality_literal_is_judged_by_the_model_rather_than_by_the_signature() -> None:
    # `__eq__` keeps `object` — narrowing it is a Liskov violation against
    # `object.__eq__` — so a mismatched literal is neither a static error nor an
    # authoring-time one on a flat attribute. Where the neutral contract states a
    # literal-type rule, the model-aware validator is what states it: the same
    # mismatch one value-object hop deeper is refused by name.
    assert preflighted(SnapOrder.where(SnapOrder.price == "abc"), _ORDERS).serialize() == {
        "eq": {"attr": "SnapOrder.price", "value": "abc"}
    }
    with pytest.raises(OperationRejectedError) as caught:
        preflighted(SnapOrderStatus.where(SnapOrderStatus.primary_tag.label == 42), _ORDERS)
    assert caught.value.rule == "nested-literal-type-mismatch"


def test_the_variance_phantom_exists_for_the_checker_alone() -> None:
    # Declared under `TYPE_CHECKING`, so it shapes inference and is absent from
    # every value that ships: nothing can call it, and no runtime behaviour turns
    # on a member whose only purpose is a variance answer. The reflected
    # combinators are the same kind of declaration — they exist so the checker
    # can solve the meet from the narrower operand — and Python never consults a
    # reflected operator whose left operand already defines the forward one, so
    # the tree a combination builds is always the left-to-right one.
    predicate: Predicate[Animal] = Predicate(All())
    assert not hasattr(predicate, "_addresses")
    assert not hasattr(predicate, "__rand__")
    assert not hasattr(predicate, "__ror__")


def test_every_addressed_value_carries_its_own_phantom_and_ships_none_of_them() -> None:
    # One claim, one phantom: a Sort Key, an Assignment, and an unfiltered query
    # are each contravariant on their own input position, and a Relationship Path
    # is covariant on its own two output positions. None of them exists at run
    # time, so no shipped value gains a member for a variance answer.
    key: SortKey[Animal] = Animal.name.asc()
    assignment: AttributeAssignment[Animal] = Animal.name.set("Ada")
    unfiltered: AllPredicate[Animal] = Animal.all
    path: RelationshipPath[Beast, Keeper] = Beast.keeper
    assert not hasattr(key, "_orders")
    assert not hasattr(assignment, "_assigns_to")
    assert not hasattr(unfiltered, "_addresses")
    assert not hasattr(path, "_starts_from")
    assert not hasattr(path, "_reaches")


# --------------------------------------------------------------------------- #
# Sort keys: contravariant, and measured against the result a narrow moved to  #
# --------------------------------------------------------------------------- #


def test_a_subtype_sort_key_never_orders_an_ancestor_result() -> None:
    # The annotation is the position `FindQuery.order_by` will supply over an
    # un-narrowed `Animal` result. The runtime twin is the same rule an order
    # key's attribute reference draws against the ordered rows' position.
    key: SortKey[Animal] = Dog.bark_volume.desc()  # pyright: ignore[reportAssignmentType]
    with pytest.raises(OperationRejectedError) as caught:
        preflighted(Animal.where().order_by(key))
    assert caught.value.rule == "subtype-attribute-outside-narrow-scope"


def test_an_unrelated_entitys_sort_key_never_orders_the_queried_result() -> None:
    # The non-family half of the same rule, which no narrow could rescue.
    key: SortKey[SnapOrder] = SnapOrderStatus.code.asc()  # pyright: ignore[reportAssignmentType]
    with pytest.raises(OperationRejectedError) as caught:
        preflighted(SnapOrder.where().order_by(key), _ORDERS)
    assert caught.value.rule == "attribute-outside-active-position"


def test_an_ancestors_sort_key_orders_a_union_narrowed_result() -> None:
    # Contravariance carries the union case for free: a root-declared member
    # applies to every concrete a two-subtype narrow leaves in the position, so
    # `SortKey[Animal]` lands in a `Cat | Dog` result and the validator agrees.
    key: SortKey[Cat | Dog] = Animal.name.asc()
    assert preflighted(Animal.where().narrow(Cat, Dog).order_by(key)).serialize() == {
        "orderBy": {
            "operand": {
                "narrow": {"entity": "Animal", "to": ["Cat", "Dog"], "operand": {"all": {}}}
            },
            "keys": [{"attr": "Animal.name", "direction": "asc"}],
        }
    }


def test_a_subtype_sort_key_never_orders_a_union_narrowed_result() -> None:
    # The rejection half of the union: `Cat | Dog` is not a subtype of `Dog`, so
    # a `Dog` member does not apply to every concrete still in the position —
    # exactly what the validator says of the same query.
    key: SortKey[Cat | Dog] = Dog.bark_volume.asc()  # pyright: ignore[reportAssignmentType]
    with pytest.raises(OperationRejectedError) as caught:
        preflighted(Animal.where().narrow(Cat, Dog).order_by(key))
    assert caught.value.rule == "subtype-attribute-outside-narrow-scope"


def test_a_sort_key_orders_the_result_a_single_subtype_narrow_moved_to() -> None:
    # And the acceptance a narrow to ONE subtype buys: the same key the
    # un-narrowed query refused is applicable once the result is `Dog`.
    key: SortKey[Dog] = Dog.bark_volume.desc()
    assert preflighted(Animal.where().narrow(Dog).order_by(key)).serialize() == {
        "orderBy": {
            "operand": {"narrow": {"entity": "Animal", "to": ["Dog"], "operand": {"all": {}}}},
            "keys": [{"attr": "Dog.barkVolume", "direction": "desc"}],
        }
    }


def test_null_placement_stays_on_the_sort_key_and_keeps_its_position() -> None:
    # Placement is authorable exactly where a direction is, so it answers a Sort
    # Key rather than the canonical node, and the single-shot rule stays the
    # canonical node's own.
    key: SortKey[Dog] = Dog.bark_volume.desc().nulls_first()
    assert preflighted(Animal.where().narrow(Dog).order_by(key)).serialize()["orderBy"] == {
        "operand": {"narrow": {"entity": "Animal", "to": ["Dog"], "operand": {"all": {}}}},
        "keys": [{"attr": "Dog.barkVolume", "direction": "desc", "nulls": "first"}],
    }
    with pytest.raises(QueryDefinitionError) as caught:
        key.nulls_last()
    assert caught.value.code == "query-expression-invalid"


# --------------------------------------------------------------------------- #
# Assignments: contravariant, and valued by the member's own declared type     #
# --------------------------------------------------------------------------- #


def test_a_foreign_assignment_never_targets_the_queried_position() -> None:
    # The annotation is the position a predicate-selected write's assignment
    # list is measured against. The runtime twin is the write boundary's own
    # member-name honesty gate, which resolves the assignment's owner prefix
    # against the target the selection names.
    assignment: AttributeAssignment[SnapOrder] = SnapOrderStatus.code.set("X-1")  # pyright: ignore[reportAssignmentType]
    write = PredicateWrite(
        mutation="update",
        target=PredicateSelection(entity="SnapOrder", predicate=All()),
        assignments=(WriteAssignment(attr=str(assignment.attr), value=assignment.value),),
    )
    with pytest.raises(WriteInstructionError, match="does not name a declared member"):
        validate_instruction(write, model_of(_ORDERS))


def test_an_assignment_value_is_the_members_own_declared_type() -> None:
    # The contrast with the comparison literal above: an assignment's value IS a
    # member value rather than a wire literal, so the parameter narrows to the
    # member's declared type and the same judgement runs anyway.
    with pytest.raises(ModelCopyError, match="does not match the declared type"):
        SnapOrder.price.set("abc")  # pyright: ignore[reportArgumentType]


# --------------------------------------------------------------------------- #
# `Entity.all`: a distinct type, on `Entity` rather than on its metaclass      #
# --------------------------------------------------------------------------- #


def test_an_unfiltered_query_written_at_another_position_is_refused_statically() -> None:
    # The second suppression with no runtime twin, and the module docstring
    # records why: an `all` node names no position, so nothing downstream can
    # tell these two apart — which is exactly why the parameter is the only
    # place the mistake is visible at all.
    assert preflighted(Animal.where(Dog.all)).serialize() == {"all": {}}  # pyright: ignore[reportArgumentType]


def test_an_unfiltered_query_is_the_whole_filter_and_composes_with_nothing() -> None:
    # No boolean operators on either side: nothing to solve for statically and
    # nothing to call at run time, so `all` cannot be quietly ANDed into a term.
    with pytest.raises(TypeError, match="unsupported operand"):
        _ = Animal.all & (Animal.name == "Ada")  # pyright: ignore[reportOperatorIssue, reportUnknownVariableType]
    with pytest.raises(TypeError, match="bad operand type"):
        _ = ~Animal.all  # pyright: ignore[reportOperatorIssue, reportUnknownVariableType]


def test_an_unfiltered_query_has_no_truth_value() -> None:
    # The same guard every expression here carries, so an accidental `and` /
    # `or` / `not` around it is caught rather than silently collapsing.
    with pytest.raises(TypeError, match="no truth value"):
        bool(Animal.all)


def test_the_unfiltered_query_survives_a_class_reached_through_a_type_parameter() -> None:
    # The whole reason the descriptor sits in `Entity`'s body rather than on
    # `EntityMeta`: a checker resolving `all` through `type[E]` reads the
    # metaclass declaration and applies no descriptor protocol to it, so a
    # metaclass spelling would answer `Animal` here and lose `E` entirely.
    def unfiltered[E: Entity](cls: type[E]) -> AllPredicate[E]:
        return cls.all

    dogs: AllPredicate[Dog] = unfiltered(Dog)
    assert preflighted(Dog.where(dogs)).serialize() == {"all": {}}
    assert (
        preflighted(Animal.where(Animal.all)).serialize() == preflighted(Animal.where()).serialize()
    )


def test_a_member_named_all_collides_with_the_query_root() -> None:
    # The runtime half: `all` is a reserved class-level name, reported against
    # the authored member the way every other reserved spelling is.
    with pytest.raises(EntityDefinitionError) as caught:

        class _Collides(Entity, table="collides", namespace=_NS):  # pyright: ignore[reportUnusedClass] - class creation itself is the rejection, so nothing binds
            id: Attr[int] = attr(primary_key=True)
            all: Attr[str]

    assert caught.value.code == "entity-reserved-member-name"


def test_a_declared_class_body_admits_no_stray_query_root_descriptor() -> None:
    # The `ignored_types` exemption that lets `Entity`'s own body bind the
    # descriptor reaches that framework root alone. A declared class body carries
    # members, so binding the same descriptor there under any other name is
    # refused as the unannotated attribute it is, rather than quietly becoming a
    # second, undeclared spelling of the query root.
    query_root = Entity.__dict__["all"]
    with pytest.raises(PydanticUserError, match="non-annotated attribute"):

        class _Stray(Entity, table="stray", namespace=_NS):  # pyright: ignore[reportUnusedClass] - class creation itself is the rejection, so nothing binds
            id: Attr[int] = attr(primary_key=True)
            everything = query_root


# --------------------------------------------------------------------------- #
# Relationship paths: covariant in the source they start from and the target   #
# they reach                                                                   #
# --------------------------------------------------------------------------- #


def test_a_descendants_path_is_a_legal_include_source_of_its_ancestors_query() -> None:
    # The annotation is the position `FindQuery.include` will supply. A path
    # rooted at a descendant starts from fewer queried objects, which is what the
    # path-ROOT guard says, so the query accepts it and the guard resolves inside
    # the position.
    source: RelationshipPath[Beast, Any] = Hound.keeper
    assert preflighted(Beast.where().include(source), _BESTIARY).serialize() == {
        "deepFetch": {
            "operand": {"all": {}},
            "paths": [
                {
                    "narrow": {"entity": "Beast", "to": ["Hound"]},
                    "segments": [{"rel": "Beast.keeper"}],
                }
            ],
        }
    }


def test_an_ancestors_path_is_not_an_include_source_of_a_descendants_query() -> None:
    # The other direction is a BROADENING guard, which the four-step narrow rule
    # refuses: the path would start from queried objects the position does not
    # contain.
    source: RelationshipPath[Hound, Any] = Beast.keeper  # pyright: ignore[reportAssignmentType]
    with pytest.raises(OperationRejectedError) as caught:
        preflighted(Hound.where().include(source), _BESTIARY)
    assert caught.value.rule == "narrow-outside-position"


def test_an_unrelated_entitys_path_is_never_an_include_source() -> None:
    # A sibling outside the position, refused by the same guard — the include
    # half of `Order.where(...).include(Customer.notes)`.
    source: RelationshipPath[Beast, Any] = Keeper.beasts  # pyright: ignore[reportAssignmentType]
    with pytest.raises(OperationRejectedError) as caught:
        preflighted(Beast.where().include(source), _BESTIARY)
    assert caught.value.rule == "narrow-outside-position"


def test_a_hop_narrowed_to_a_descendant_stands_where_the_broad_hop_does() -> None:
    # Covariance in the target: everything a narrowed hop reaches the broad hop
    # reaches too, so the narrowed path satisfies the broad position and the
    # broad one does not satisfy the narrowed position.
    narrowed: RelationshipPath[Keeper, Beast] = Keeper.beasts.narrow(Hound)
    broad: RelationshipPath[Keeper, Hound] = Keeper.beasts  # pyright: ignore[reportAssignmentType]
    assert preflighted(Keeper.where().include(narrowed), _BESTIARY).serialize() == {
        "deepFetch": {
            "operand": {"all": {}},
            "paths": [{"segments": [{"rel": "Keeper.beasts", "narrow": {"to": ["Hound"]}}]}],
        }
    }
    assert broad.segments[-1].narrow == ()


def test_a_hop_narrows_only_to_subtypes_of_what_it_points_at() -> None:
    # The static half of `narrow-outside-relationship-target`, carried by the
    # receiver's own target rather than by a type-parameter bound, which may not
    # itself be generic.
    with pytest.raises(OperationRejectedError) as caught:
        preflighted(
            Keeper.where().include(Keeper.beasts.narrow(Badge)),  # pyright: ignore[reportArgumentType]
            _BESTIARY,
        )
    assert caught.value.rule == "narrow-outside-relationship-target"


def test_a_path_reaches_the_element_type_of_every_declared_relationship_shape() -> None:
    # All three declared shapes resolve to the ELEMENT the hop reaches, because a
    # hop reaches related objects one at a time however many of them there are.
    # The collection case is the one that proves extraction happened rather than
    # the catch-all matching: the declared annotation itself is refused.
    to_many: RelationshipPath[Keeper, Beast] = Keeper.beasts
    optional: RelationshipPath[Beast, Keeper] = Beast.keeper
    exact: RelationshipPath[Keeper, Badge] = Keeper.badge
    unextracted: RelationshipPath[Keeper, tuple[Beast, ...]] = Keeper.beasts  # pyright: ignore[reportAssignmentType]
    assert [path.target for path in (to_many, optional, exact, unextracted)] == [
        f"{_NS}.Beast",
        f"{_NS}.Keeper",
        f"{_NS}.Badge",
        f"{_NS}.Beast",
    ]


# --------------------------------------------------------------------------- #
# What erases, and is therefore a runtime rejection alone                      #
# --------------------------------------------------------------------------- #


def test_a_relationship_hop_past_the_first_erases_and_the_gate_refuses_it() -> None:
    # A deeper hop is composed from a member name against a target the path
    # reaches no class for, so nothing about it is typed — no suppression belongs
    # on this line — and the model states the whole rule at the gate.
    with pytest.raises(ValueError, match="names no declared relationship on Beast"):
        preflighted(Keeper.where().include(Keeper.beasts.no_such_hop), _BESTIARY)


def test_an_authored_chain_stops_at_the_second_hop() -> None:
    # The consequence of the same erasure: a third hop has no owner to spell its
    # segment from, because what the second hop points at is a declaration fact
    # of an Entity the path reaches no class for. The path's target parameter
    # cannot supply it — a type parameter is checker-only, and this is run time —
    # so a longer traversal is authored as a path rooted where the deeper hop
    # starts.
    second = Keeper.beasts.keeper
    assert [segment.rel for segment in second.segments] == ["Keeper.beasts", "Beast.keeper"]
    assert second.target is None
    with pytest.raises(AttributeError, match="already continued past the hop"):
        _ = second.badge


def test_a_value_object_member_past_the_occurrence_erases() -> None:
    # The Value-Object twin of the hop erasure: the Entity survives the hop, so a
    # foreign-Entity nested predicate is still refused statically, while the
    # member's own existence is a model question the gate answers.
    with pytest.raises(OperationRejectedError) as caught:
        preflighted(
            SnapOrderStatus.where(SnapOrderStatus.primary_tag.no_such_member == "x"), _ORDERS
        )
    assert caught.value.rule == "nested-path-unknown-member"


def test_a_second_narrow_clause_is_refused_at_the_clause_alone() -> None:
    # A method cannot make its own second call illegal, so single-shot is a
    # clause fact checked where the clause is authored.
    with pytest.raises(ValueError, match="single-shot"):
        Animal.where().narrow(Dog).narrow(Cat)


def test_a_narrow_inside_a_quantifier_must_name_the_relationship_target_exactly() -> None:
    # `m-navigate`'s exact-naming rule. The quantifier's interior position is the
    # hop's target, and a narrow naming a BROADER position satisfies the
    # contravariant parameter while the rule refuses it: relationship scope does
    # not clamp.
    with pytest.raises(OperationRejectedError) as caught:
        preflighted(AnimalOwner.where(AnimalOwner.pets.any(Animal.narrow(Dog))))
    assert caught.value.rule == "narrow-outside-relationship-target"


def test_a_narrow_to_a_class_the_position_excludes_is_refused_at_the_gate() -> None:
    # `Entity.narrow`'s subtype list keeps only its runtime rejection: a type
    # parameter's bound may not itself be generic, so the narrowed subtypes
    # cannot be bounded by the narrowing position.
    with pytest.raises(OperationRejectedError) as caught:
        preflighted(Animal.where(Animal.narrow(AnimalOwner)))
    assert caught.value.rule == "narrow-outside-position"
