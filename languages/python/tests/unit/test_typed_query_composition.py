"""Typed query composition: each static rejection beside its runtime twin.

`reportUnnecessaryTypeIgnoreComment` is `"error"` (`pyrightconfig.json`), so a
rule-coded suppression asserts in both directions: the expression must produce
exactly that diagnostic, and an ignore that goes idle fails `just
python-typecheck`. That inversion is this repository's only way to assert a type
error, which is why a case below carries its suppression and its runtime
rejection in ONE test — static and runtime agreement proved by construction
rather than in two processes that never meet.

Some suppression families here have no runtime twin, and each is deliberate for
one reason: the composition the parameter refuses builds a VALID canonical
query, so the wire carries no record of the mistake and no preflight rule
could restate it. Which ones those are is settled by a test rather than by a
count — canonicalize the refused spelling and the accepted one, and they are one
document — and `python.md` §2 states that test, names the same families as
examples, and says plainly that the list is open. A case belongs here when it
fails that test; adding one is the obligation, not keeping a tally.

`test_a_subtype_spelling_of_an_inherited_member_is_narrower_than_the_model_is`
asserts a SUCCESSFUL serialization under a `reportArgumentType` ignore. The
parameter comes from the class an access went through and the wire keeps the
class that declares the member, so `Animal.where(Dog.name == …)` reads as
`Predicate[Dog]` statically while emitting the `Animal.name` every concrete
under `Animal` answers. No type the checker can see separates it from the
rejection that IS wanted — `Animal.where(Dog.bark_volume > …)`, where the member
really is the subtype's — so the parameter is strictly narrower than the model
there, and that test is where the asymmetry is recorded rather than discovered.
`test_one_identity_reached_through_two_classes_is_refused_statically_only` is
the same gap without inheritance: Entity Identity is unique per MODEL, so two
distinct classes may carry one Identity, and a member both declare lowers to one
attribute reference at one target. Another is `Entity.all`: an `all` node names
no position on the wire, so nothing downstream can tell `Dog.all` from
`Animal.all` and the parameter is the only place an unfiltered query written at
the wrong position is refused. Another is clause order — a `where` argument or a
sort key written before the `narrow` that scopes it — because an Object Query
retains clauses rather than wrapping them, so the refused spelling and the
sanctioned one lower to one query. Another is `ObjectQuery.narrow`'s
conservative variadic overload, which leaves the result parameter where it was
for any subtype list the fixed one-through-three overloads cannot read, while the
narrow it authors lowers exactly as the readable spelling's does — so a later
subtype key is refused statically and accepted by the gate.

The converse direction is open in the same way: a model-aware rule has no static
half when nothing the checker reads at the call site decides it, either because
the fact is the connected model's rather than the classes' or because no
parameter is free to carry it. Those cases sit in the last section below and
carry NO suppression, which asserts the checker's silence exactly as a
rule-coded ignore asserts its diagnostic, because an unsuppressed diagnostic
fails `just python-typecheck`.

Authoring reaches no model, so every runtime twin here runs the shared read gate
`preflight` — the seam `Database.find` and `Transaction.find` both call —
rather than expecting a rejection from `Entity.where`. That is where the
model-aware validator states these rules, and it is what covers the wire path
and any untyped caller identically.

The mechanism under test is variance. `Predicate[E]` holds only a canonical
Predicate node, so `E` appears in no field and inference would read it as
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
the query value that will carry a narrowed RESULT parameter is `ObjectQuery[E, S]`
and it does not exist yet. The annotation is exactly the parameter its
`order_by` will supply, and each is paired with the runtime twin the same
narrowing produces through the gate.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from pydantic import PydanticUserError

from _support import snapshot_models
from _support.query_probes import canonical_document, predicate_document
from _support.snapshot_models import (
    Animal,
    AnimalOwner,
    Cat,
    Dog,
    Pet,
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
    EditError,
    Entity,
    EntityDefinitionError,
    Int32,
    ModelRejectedError,
    ObjectQuery,
    Predicate,
    QueryDefinitionError,
    Rel,
    RelationshipPath,
    SortKey,
    TablePerHierarchy,
    attr,
    rel,
)
from parallax.core.entity import AttributeAssignment
from parallax.core.entity._model import model_of
from parallax.core.object_query._fluent import object_query_node
from parallax.core.predicate import All
from parallax.core.unit_work import (
    PredicateSelection,
    PredicateWrite,
    WriteAssignment,
    WriteInstructionError,
    prepare_typed_write,
)
from parallax.snapshot.handle._preflight import preflight

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


# Entity Identity is unique per MODEL — composing both of these raises
# `metamodel-duplicate-entity-identity` — and a class belongs to no model until
# it is composed, so one Identity reached through two distinct classes is a
# legal configuration rather than a declaration defect.
class TwinLeft(Entity, table="typed_twin", name="TypedTwin", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    left_only: Attr[str] = attr(max_length=8)


class TwinRight(Entity, table="typed_twin", name="TypedTwin", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    right_only: Attr[str] = attr(max_length=8)


_TWINS = DomainModel(TwinLeft)


# One local Entity name declared in two namespaces, which the Entity Identity
# rule permits because the qualified identities differ. Composing both into one
# model is legal too, and is what makes the bare name the wire spells answer two
# Entities instead of one.
class LeftShared(Entity, table="typed_left_shared", name="Shared", namespace=f"{_NS}.alpha"):
    id: Attr[int] = attr(primary_key=True)


class RightShared(Entity, table="typed_right_shared", name="Shared", namespace=f"{_NS}.beta"):
    id: Attr[int] = attr(primary_key=True)


_ONE_SHARED_NAME = DomainModel(LeftShared)
_TWO_SHARED_NAMES = DomainModel(LeftShared, RightShared)


def preflighted(
    query: ObjectQuery[Any, Any], models: DomainModel = _ANIMALS
) -> ObjectQuery[Any, Any]:
    """``query`` after the shared read preflight accepted it against ``models``,
    which defaults to the animal composition every composition case is written over.

    Runs exactly what executing the query would run before any I/O, and answers
    the query itself so a case can go on to assert its canonical lowering. A
    rejection propagates.
    """
    preflight(object_query_node(query), model=model_of(models), form="graph")
    return query


# --------------------------------------------------------------------------- #
# Rejections: a predicate that does not address the queried position          #
# --------------------------------------------------------------------------- #


def test_a_subtype_predicate_never_addresses_an_ancestor_position() -> None:
    # `Predicate[Dog]` in an `Animal` position: the concrete subtype's member is
    # not available to every concrete the position resolves to, and narrowing is
    # the remedy the runtime rule names (see the narrow case below).
    with pytest.raises(ModelRejectedError) as caught:
        preflighted(Animal.where(Dog.bark_volume > 3))  # pyright: ignore[reportArgumentType]
    assert caught.value.rule == "subtype-attribute-outside-narrow-scope"


def test_an_unrelated_entitys_predicate_never_addresses_the_queried_position() -> None:
    # `Predicate[AnimalOwner]` in an `Animal` position. The two Entities share
    # one model and no inheritance family, so no narrow could rescue it — which
    # is exactly the distinction between this rule and the one above.
    with pytest.raises(ModelRejectedError) as caught:
        preflighted(Animal.where(AnimalOwner.name == "Ada"))  # pyright: ignore[reportArgumentType]
    assert caught.value.rule == "attribute-outside-active-position"


def test_an_unrelated_entitys_predicate_is_refused_from_the_other_side_too() -> None:
    # The same rule with the positions swapped, so neither direction is accepted
    # by an accident of which Entity happens to declare the member.
    with pytest.raises(ModelRejectedError) as caught:
        preflighted(AnimalOwner.where(Animal.name == "Ada"))  # pyright: ignore[reportArgumentType]
    assert caught.value.rule == "attribute-outside-active-position"


# --------------------------------------------------------------------------- #
# Acceptances: the direction contravariance must keep open                    #
# --------------------------------------------------------------------------- #


def test_an_ancestors_predicate_addresses_every_descendant_position() -> None:
    # The acceptance half of the same mechanism, and the case an INVARIANT
    # parameter would break: `Predicate[Animal]` lands in a `Dog` position
    # because a root-declared member is available to every concrete under it.
    assert predicate_document(preflighted(Dog.where(Animal.name == "Ada"))) == {
        "eq": {"attr": "parallax.compatibility.Animal.name", "value": "Ada"}
    }


def test_an_inherited_member_is_parameterized_by_the_class_it_is_reached_through() -> None:
    # `Dog.name` reaches `Animal`'s descriptor through `Dog`, so it yields a
    # `Dog`-positioned predicate while the wire keeps the DECLARING Entity — the
    # spelling that makes the reference applicable to every concrete under
    # `Animal`. The two are different questions and the two answers differ.
    assert predicate_document(preflighted(Dog.where(Dog.name == "Ada"))) == {
        "eq": {"attr": "parallax.compatibility.Animal.name", "value": "Ada"}
    }


def test_a_subtype_spelling_of_an_inherited_member_is_narrower_than_the_model_is() -> None:
    # The one composition the parameter refuses where the model accepts it, and
    # the reason is the same mechanism read from the other side: `Dog.name`
    # addresses `Dog` because that is the class it was reached through, while the
    # wire it builds spells the DECLARING `Animal.name`, which every concrete
    # under `Animal` answers. The remedy is to spell the member through the class
    # that declares it, and the suppression records the asymmetry rather than
    # leaving it to be discovered.
    assert predicate_document(preflighted(Animal.where(Dog.name == "Ada"))) == {  # pyright: ignore[reportArgumentType]
        "eq": {"attr": "parallax.compatibility.Animal.name", "value": "Ada"}
    }


def test_one_identity_reached_through_two_classes_is_refused_statically_only() -> None:
    # The same class/Identity gap with no inheritance in it. `TwinLeft` and
    # `TwinRight` are nominally incompatible, so a term built from one is refused
    # at the other's position; the wire keeps the Identity and the declaring
    # member and never the class, so a member both declare lowers to one
    # attribute reference at one target. The refused spelling and the accepted
    # one are byte-identical documents, which is why this suppression has no
    # runtime twin: preflight is handed nothing that differs.
    foreign = TwinLeft.where(TwinRight.id == 1)  # pyright: ignore[reportArgumentType]
    native = TwinLeft.where(TwinLeft.id == 1)
    assert predicate_document(preflighted(foreign, _TWINS)) == {
        "eq": {"attr": "parallax.tests.typed.TypedTwin.id", "value": 1}
    }
    assert predicate_document(preflighted(native, _TWINS)) == predicate_document(foreign)


def test_a_conjunction_addresses_the_position_both_of_its_operands_address() -> None:
    # An ancestor's term and a descendant's term compose, and the combination
    # lands in the descendant's query — the case a combinator demanding one
    # shared parameter would refuse for a reason no rule states.
    assert predicate_document(
        preflighted(Dog.where((Animal.name == "Ada") & (Dog.bark_volume > 3)))
    ) == {
        "and": {
            "operands": [
                {"eq": {"attr": "parallax.compatibility.Animal.name", "value": "Ada"}},
                {"greaterThan": {"attr": "parallax.compatibility.Dog.barkVolume", "value": 3}},
            ]
        }
    }


def test_a_mixed_conjunction_reads_the_same_in_the_other_operand_order() -> None:
    # The same combination with the NARROWER term on the left. A combinator
    # that took the left operand's position would accept exactly one of these
    # two spellings, so both orders are pinned: the position a combination
    # addresses is the meet, which no operand order can move.
    assert predicate_document(
        preflighted(Dog.where((Dog.bark_volume > 3) & (Animal.name == "Ada")))
    ) == {
        "and": {
            "operands": [
                {"greaterThan": {"attr": "parallax.compatibility.Dog.barkVolume", "value": 3}},
                {"eq": {"attr": "parallax.compatibility.Animal.name", "value": "Ada"}},
            ]
        }
    }


def test_a_mixed_conjunction_never_launders_the_descendants_term_upward() -> None:
    # The rejection half of the meet, and the laundering a left-biased
    # combinator admits: the ancestor's term is on the LEFT, so reading the
    # combination as the left operand's position would let a `Dog` member into
    # an `Animal` query with no diagnostic at all.
    with pytest.raises(ModelRejectedError) as caught:
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
    with pytest.raises(ModelRejectedError) as caught:
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
    ancestor_first = predicate_document(
        preflighted(Dog.where((Animal.name == "Ada") | (Dog.bark_volume > 3)))
    )
    descendant_first = predicate_document(
        preflighted(Dog.where((Dog.bark_volume > 3) | (Animal.name == "Ada")))
    )
    assert ancestor_first == {
        "or": {
            "operands": [
                {"eq": {"attr": "parallax.compatibility.Animal.name", "value": "Ada"}},
                {"greaterThan": {"attr": "parallax.compatibility.Dog.barkVolume", "value": 3}},
            ]
        }
    }
    assert descendant_first == {
        "or": {
            "operands": [
                {"greaterThan": {"attr": "parallax.compatibility.Dog.barkVolume", "value": 3}},
                {"eq": {"attr": "parallax.compatibility.Animal.name", "value": "Ada"}},
            ]
        }
    }


def test_a_disjunction_launders_no_more_than_a_conjunction_does() -> None:
    # And the rejection half for `|`, on the operand order a left-biased
    # combinator would have admitted.
    with pytest.raises(ModelRejectedError) as caught:
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
    with pytest.raises(ModelRejectedError) as caught:
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
    with pytest.raises(ModelRejectedError) as caught:
        preflighted(
            Animal.where(
                (Dog.bark_volume > 3) & (Dog.bark_volume < 9)  # pyright: ignore[reportArgumentType]
            )
        )
    assert caught.value.rule == "subtype-attribute-outside-narrow-scope"


def test_a_narrow_scope_is_how_a_descendants_member_reaches_an_ancestor_position() -> None:
    # The sanctioned spelling of the first rejection above: `narrow` takes the
    # subtype's predicate and answers one in the narrowing class's own position,
    # so this composes where the bare subtype predicate cannot. A narrowing that
    # is the WHOLE filter narrows the result, so it lands in `narrowTo` and its
    # own scoped predicate is what the query filters by.
    assert canonical_document(
        preflighted(Animal.where(Animal.narrow(Dog, where=Dog.bark_volume > 3)))
    ) == {
        "target": "parallax.compatibility.Animal",
        "predicate": {"greaterThan": {"attr": "parallax.compatibility.Dog.barkVolume", "value": 3}},
        "narrowTo": ["parallax.compatibility.Dog"],
    }


def test_narrowing_after_the_predicate_is_refused_statically_and_only_statically() -> None:
    # The predicate twin of the sort key's clause-order rule below: the `where`
    # argument is measured at the position the query is at where the call is
    # written, so a subtype's bare predicate is refused there and the later
    # `narrow` never retroactively legalizes it. It has no runtime twin because
    # the clause order does not reach the wire — result narrowing is a clause of
    # the query the predicate is evaluated at, so the model-aware position the
    # predicate meets is the narrowed one either way. Narrowing FIRST is what
    # states the same query with the checker's agreement, and the two converge on
    # one canonical value.
    late_narrow = Animal.where(Dog.bark_volume > 3).narrow(Dog)  # pyright: ignore[reportArgumentType]
    narrow_first = Animal.where(Animal.narrow(Dog, where=Dog.bark_volume > 3))
    document = canonical_document(preflighted(late_narrow))
    assert document["narrowTo"] == ["parallax.compatibility.Dog"]
    assert document["predicate"] == {
        "greaterThan": {"attr": "parallax.compatibility.Dog.barkVolume", "value": 3}
    }
    assert canonical_document(preflighted(narrow_first)) == document


def test_a_narrowing_reached_through_a_boolean_stays_a_filter() -> None:
    # The other side of the lift: only the whole filter is whole-result
    # narrowing. Reached through a combinator, the same narrowing qualifies one
    # term of the selection and the result position stays where the query is —
    # so the query returns un-narrowed objects and carries no `narrowTo` at all.
    combined = Animal.where(Animal.narrow(Dog, where=Dog.bark_volume > 3) | (Animal.name == "Ada"))
    document = canonical_document(preflighted(combined))
    assert "narrowTo" not in document
    assert document["predicate"] == {
        "or": {
            "operands": [
                {
                    "narrow": {
                        "to": ["parallax.compatibility.Dog"],
                        "operand": {
                            "greaterThan": {
                                "attr": "parallax.compatibility.Dog.barkVolume",
                                "value": 3,
                            }
                        },
                    }
                },
                {"eq": {"attr": "parallax.compatibility.Animal.name", "value": "Ada"}},
            ]
        }
    }


# --------------------------------------------------------------------------- #
# What the parameters deliberately do not judge                               #
# --------------------------------------------------------------------------- #


def test_a_comparison_literal_is_encoded_to_canonical_wire_at_authoring() -> None:
    # A typed expression accepts the member's managed value and stores its
    # canonical serialized literal, so model-aware preflight decodes exactly
    # that value once rather than interpreting a Python float later.
    assert predicate_document(
        preflighted(SnapOrder.where(SnapOrder.price >= Decimal("600.00")), _ORDERS)
    ) == {
        "greaterThanEquals": {
            "attr": "parallax.compatibility.SnapOrder.price",
            "value": "600.00",
        }
    }


def test_an_equality_literal_is_judged_at_typed_authoring() -> None:
    # `__eq__` keeps `object` for Python's protocol, but the expression still
    # resolves its member metadata and rejects a value outside that managed
    # value space before constructing a serialized Predicate literal.
    with pytest.raises(QueryDefinitionError) as flat:
        _ = SnapOrder.price == "abc"
    assert flat.value.code == "query-expression-invalid"

    with pytest.raises(QueryDefinitionError) as nested:
        _ = SnapOrderStatus.primary_tag.label == 42
    assert nested.value.code == "query-expression-invalid"


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
    # The annotation is the position `ObjectQuery.order_by` will supply over an
    # un-narrowed `Animal` result. The runtime twin is the same rule an order
    # key's attribute reference draws against the ordered rows' position.
    key: SortKey[Animal] = Dog.bark_volume.desc()  # pyright: ignore[reportAssignmentType]
    with pytest.raises(ModelRejectedError) as caught:
        preflighted(Animal.where(Animal.all).order_by(key))
    assert caught.value.rule == "subtype-attribute-outside-narrow-scope"


def test_an_unrelated_entitys_sort_key_never_orders_the_queried_result() -> None:
    # The non-family half of the same rule, which no narrow could rescue.
    key: SortKey[SnapOrder] = SnapOrderStatus.code.asc()  # pyright: ignore[reportAssignmentType]
    with pytest.raises(ModelRejectedError) as caught:
        preflighted(SnapOrder.where(SnapOrder.all).order_by(key), _ORDERS)
    assert caught.value.rule == "attribute-outside-active-position"


def test_an_ancestors_sort_key_orders_a_union_narrowed_result() -> None:
    # Contravariance carries the union case for free: a root-declared member
    # applies to every concrete a two-subtype narrow leaves in the position, so
    # `SortKey[Animal]` lands in a `Cat | Dog` result and the validator agrees.
    key: SortKey[Cat | Dog] = Animal.name.asc()
    document = canonical_document(
        preflighted(Animal.where(Animal.all).narrow(Cat, Dog).order_by(key))
    )
    assert document["narrowTo"] == [
        "parallax.compatibility.Cat",
        "parallax.compatibility.Dog",
    ]
    assert document["orderBy"] == [
        {"attr": "parallax.compatibility.Animal.name", "direction": "asc"}
    ]


def test_a_subtype_sort_key_never_orders_a_union_narrowed_result() -> None:
    # The rejection half of the union: `Cat | Dog` is not a subtype of `Dog`, so
    # a `Dog` member does not apply to every concrete still in the position —
    # exactly what the validator says of the same query.
    key: SortKey[Cat | Dog] = Dog.bark_volume.asc()  # pyright: ignore[reportAssignmentType]
    with pytest.raises(ModelRejectedError) as caught:
        preflighted(Animal.where(Animal.all).narrow(Cat, Dog).order_by(key))
    assert caught.value.rule == "subtype-attribute-outside-narrow-scope"


def test_a_sort_key_orders_the_result_a_single_subtype_narrow_moved_to() -> None:
    # And the acceptance a narrow to ONE subtype buys: the same key the
    # un-narrowed query refused is applicable once the result is `Dog`.
    key: SortKey[Dog] = Dog.bark_volume.desc()
    document = canonical_document(preflighted(Animal.where(Animal.all).narrow(Dog).order_by(key)))
    assert document["narrowTo"] == ["parallax.compatibility.Dog"]
    assert document["orderBy"] == [
        {"attr": "parallax.compatibility.Dog.barkVolume", "direction": "desc"}
    ]


def test_null_placement_stays_on_the_sort_key_and_keeps_its_position() -> None:
    # Placement is authorable exactly where a direction is, so it answers a Sort
    # Key rather than the canonical node, and the single-shot rule stays the
    # canonical node's own.
    key: SortKey[Dog] = Dog.bark_volume.desc().nulls_first()
    document = canonical_document(preflighted(Animal.where(Animal.all).narrow(Dog).order_by(key)))
    assert document["orderBy"] == [
        {"attr": "parallax.compatibility.Dog.barkVolume", "direction": "desc", "nulls": "first"}
    ]
    with pytest.raises(QueryDefinitionError) as caught:
        key.nulls_last()
    assert caught.value.code == "query-expression-invalid"


# --------------------------------------------------------------------------- #
# What each `ObjectQuery.narrow` arity answers as the RESULT parameter, read     #
# through the sort keys the answered query does and does not admit — with no   #
# annotation anywhere, so the parameter is the one `narrow` produced rather    #
# than one the case declared. Each case carries its runtime twin.              #
# --------------------------------------------------------------------------- #


def test_narrowing_to_one_subtype_answers_that_subtype() -> None:
    admitted = Animal.where(Animal.all).narrow(Dog).order_by(Dog.bark_volume.desc())
    document = canonical_document(preflighted(admitted))
    assert document["narrowTo"] == ["parallax.compatibility.Dog"]
    assert document["orderBy"] == [
        {"attr": "parallax.compatibility.Dog.barkVolume", "direction": "desc"}
    ]
    # A sibling's key is refused by the answered parameter and by the gate: the
    # ordered rows are Dogs, and `Cat.indoor` applies to none of them.
    refused = Animal.where(Animal.all).narrow(Dog).order_by(Cat.indoor.asc())  # pyright: ignore[reportArgumentType]
    with pytest.raises(ModelRejectedError) as caught:
        preflighted(refused)
    assert caught.value.rule == "subtype-attribute-outside-narrow-scope"


def test_narrowing_to_two_subtypes_answers_their_union() -> None:
    admitted = Animal.where(Animal.all).narrow(Cat, Dog).order_by(Animal.name.asc())
    document = canonical_document(preflighted(admitted))
    assert document["narrowTo"] == [
        "parallax.compatibility.Cat",
        "parallax.compatibility.Dog",
    ]
    assert document["orderBy"] == [
        {"attr": "parallax.compatibility.Animal.name", "direction": "asc"}
    ]
    # `Cat | Dog` is not a subtype of `Dog`, so a Dog member does not apply to
    # every concrete the narrow left in the position — the union is what the
    # parameter answers, not the common base.
    refused = Animal.where(Animal.all).narrow(Cat, Dog).order_by(Dog.bark_volume.asc())  # pyright: ignore[reportArgumentType]
    with pytest.raises(ModelRejectedError) as caught:
        preflighted(refused)
    assert caught.value.rule == "subtype-attribute-outside-narrow-scope"


def test_the_variadic_narrow_tail_leaves_the_result_where_it_was() -> None:
    # A subtype list of indeterminate length reaches the variadic overload,
    # which moves nothing: the result stays `Animal`, so a root key is admitted
    # and a Dog key is refused STATICALLY even though the very same query is
    # legal — the widest honest answer a fixed overload set can give to a list
    # whose length it cannot see, which is why the suppression below has no
    # runtime twin to raise.
    subtypes: list[type[Entity]] = [Dog]
    admitted = Animal.where(Animal.all).narrow(*subtypes).order_by(Animal.name.asc())
    document = canonical_document(preflighted(admitted))
    assert document["narrowTo"] == ["parallax.compatibility.Dog"]
    assert document["orderBy"] == [
        {"attr": "parallax.compatibility.Animal.name", "direction": "asc"}
    ]
    conservative = Animal.where(Animal.all).narrow(*subtypes).order_by(Dog.bark_volume.desc())  # pyright: ignore[reportArgumentType]
    assert canonical_document(preflighted(conservative))["orderBy"] == [
        {"attr": "parallax.compatibility.Dog.barkVolume", "direction": "desc"}
    ]


def test_ordering_before_narrowing_is_refused_statically_and_only_statically() -> None:
    # The sort-key twin of the narrow clause's own no-retroactive-scope rule: an
    # Object Query retains clauses rather than wrapping them, so ordering-then-
    # narrowing and narrowing-then-ordering lower to ONE canonical query and
    # no model-aware rule can refuse one while accepting the other. What refuses
    # the wrong order is the result parameter the receiver carries when the call
    # is written, which is why the suppression below has no runtime twin.
    late_narrow = Animal.where(Animal.all).order_by(Dog.bark_volume.desc()).narrow(Dog)  # pyright: ignore[reportArgumentType]
    early_narrow = Animal.where(Animal.all).narrow(Dog).order_by(Dog.bark_volume.desc())
    assert canonical_document(preflighted(late_narrow)) == canonical_document(
        preflighted(early_narrow)
    )


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
        prepare_typed_write(write, model_of(_ORDERS))


def test_an_assignment_value_is_the_members_own_declared_type() -> None:
    # The contrast with the comparison literal above: an assignment's value IS a
    # member value rather than a wire literal, so the parameter narrows to the
    # member's declared type and the same judgement runs anyway.
    with pytest.raises(EditError, match="does not match the declared type"):
        SnapOrder.price.set("abc")  # pyright: ignore[reportArgumentType]


# --------------------------------------------------------------------------- #
# `Entity.all`: a distinct type, on `Entity` rather than on its metaclass      #
# --------------------------------------------------------------------------- #


def test_an_unfiltered_query_written_at_another_position_is_refused_statically() -> None:
    # The second suppression with no runtime twin, and the module docstring
    # records why: an `all` node names no position, so nothing downstream can
    # tell these two apart — which is exactly why the parameter is the only
    # place the mistake is visible at all.
    assert predicate_document(preflighted(Animal.where(Dog.all))) == {"all": {}}  # pyright: ignore[reportArgumentType]


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
    assert predicate_document(preflighted(Dog.where(dogs))) == {"all": {}}
    assert predicate_document(preflighted(Animal.where(Animal.all))) == predicate_document(
        preflighted(Animal.where(Animal.all))
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
    # The annotation is the position `ObjectQuery.include` will supply. A path
    # rooted at a descendant starts from fewer queried objects, which is what the
    # SOURCE guard says, so the query accepts it and the guard resolves inside
    # the position.
    source: RelationshipPath[Beast, Any] = Hound.keeper
    document = canonical_document(preflighted(Beast.where(Beast.all).include(source), _BESTIARY))
    assert document["includes"] == [
        {
            "appliesTo": ["parallax.tests.typed.Hound"],
            "segments": [{"rel": "parallax.tests.typed.Beast.keeper"}],
        }
    ]


def test_an_ancestors_path_is_not_an_include_source_of_a_descendants_query() -> None:
    # The other direction is a BROADENING guard, which the four-step narrow rule
    # refuses: the path would start from queried objects the position does not
    # contain.
    source: RelationshipPath[Hound, Any] = Beast.keeper  # pyright: ignore[reportAssignmentType]
    with pytest.raises(ModelRejectedError) as caught:
        preflighted(Hound.where(Hound.all).include(source), _BESTIARY)
    assert caught.value.rule == "narrow-outside-position"


def test_an_unrelated_entitys_path_is_never_an_include_source() -> None:
    # A sibling outside the position, refused by the same guard — the include
    # half of `Order.where(...).include(Customer.notes)`.
    source: RelationshipPath[Beast, Any] = Keeper.beasts  # pyright: ignore[reportAssignmentType]
    with pytest.raises(ModelRejectedError) as caught:
        preflighted(Beast.where(Beast.all).include(source), _BESTIARY)
    assert caught.value.rule == "narrow-outside-position"


def test_a_hop_narrowed_to_a_descendant_stands_where_the_broad_hop_does() -> None:
    # Covariance in the target: everything a narrowed hop reaches the broad hop
    # reaches too, so the narrowed path satisfies the broad position and the
    # broad one does not satisfy the narrowed position.
    narrowed: RelationshipPath[Keeper, Beast] = Keeper.beasts.narrow(Hound)
    broad: RelationshipPath[Keeper, Hound] = Keeper.beasts  # pyright: ignore[reportAssignmentType]
    document = canonical_document(
        preflighted(Keeper.where(Keeper.all).include(narrowed), _BESTIARY)
    )
    assert document["includes"] == [
        {
            "segments": [
                {
                    "rel": "parallax.tests.typed.Keeper.beasts",
                    "narrowTo": ["parallax.tests.typed.Hound"],
                }
            ]
        }
    ]
    assert broad.segments[-1].narrow_to == ()


def test_a_hop_narrows_only_to_subtypes_of_what_it_points_at() -> None:
    # The static half of `narrow-outside-relationship-target`, carried by the
    # receiver's own target rather than by a type-parameter bound, which may not
    # itself be generic.
    with pytest.raises(ModelRejectedError) as caught:
        preflighted(
            Keeper.where(Keeper.all).include(Keeper.beasts.narrow(Badge)),  # pyright: ignore[reportArgumentType]
            _BESTIARY,
        )
    assert caught.value.rule == "narrow-outside-relationship-target"


def test_a_quantifiers_interior_term_is_measured_against_the_hops_target() -> None:
    # The half of `narrow-outside-relationship-target` the quantifier's own
    # parameter DOES state: the interior position is what the hop points at, so a
    # narrow written at an unrelated Entity is refused where it is written and
    # again at the gate. Only the ANCESTOR direction escapes — contravariance
    # obliges the parameter to admit it — and the no-suppression case in the last
    # section is where that is pinned.
    with pytest.raises(ModelRejectedError) as caught:
        preflighted(
            Keeper.where(Keeper.badge.exists(Beast.narrow(Hound))),  # pyright: ignore[reportArgumentType]
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


def test_a_reference_names_the_namespace_its_own_class_declares() -> None:
    # The namespace is what does NOT erase: one expression, two models, one
    # answer. `LeftShared.id` serializes the exact identity of the class it was
    # authored through, so declaring the local name `Shared` a second time
    # changes nothing about what this query addresses — where a bare spelling
    # would have named both Entities and therefore neither.
    query = LeftShared.where(LeftShared.id == 1)
    expected = {"eq": {"attr": "parallax.tests.typed.alpha.Shared.id", "value": 1}}
    assert predicate_document(preflighted(query, _ONE_SHARED_NAME)) == expected
    assert predicate_document(preflighted(query, _TWO_SHARED_NAMES)) == expected


def test_a_relationship_hop_past_the_first_erases_and_the_gate_refuses_it() -> None:
    # A deeper hop is composed from a member name against a target the path
    # reaches no class for, so nothing about it is typed — no suppression belongs
    # on this line — and the model states the whole rule at the gate.
    with pytest.raises(ValueError, match="names no declared relationship on Beast"):
        preflighted(Keeper.where(Keeper.all).include(Keeper.beasts.no_such_hop), _BESTIARY)


def test_an_authored_chain_stops_at_the_second_hop() -> None:
    # The consequence of the same erasure: a third hop has no owner to spell its
    # segment from, because what the second hop points at is a declaration fact
    # of an Entity the path reaches no class for. The path's target parameter
    # cannot supply it — a type parameter is checker-only, and this is run time —
    # so a longer traversal is authored as a path rooted where the deeper hop
    # starts.
    second = Keeper.beasts.keeper
    assert [segment.rel for segment in second.segments] == [
        "parallax.tests.typed.Keeper.beasts",
        "parallax.tests.typed.Beast.keeper",
    ]
    assert second.target is None
    with pytest.raises(AttributeError, match="already continued past the hop"):
        _ = second.badge


def test_a_value_object_member_past_the_occurrence_erases() -> None:
    # The Value-Object twin of the hop erasure: the Entity survives the hop, so a
    # foreign-Entity nested predicate is still refused statically, while the
    # member's own existence is a model question the gate answers.
    with pytest.raises(ModelRejectedError) as caught:
        preflighted(
            SnapOrderStatus.where(SnapOrderStatus.primary_tag.no_such_member == "x"), _ORDERS
        )
    assert caught.value.rule == "nested-path-unknown-member"


def test_a_second_narrow_clause_is_refused_at_the_clause_alone() -> None:
    # A method cannot make its own second call illegal, so single-shot is a
    # clause fact checked where the clause is authored.
    with pytest.raises(ValueError, match="single-shot"):
        Animal.where(Animal.all).narrow(Dog).narrow(Cat)


def test_a_narrow_receiver_does_not_restate_the_relationship_position() -> None:
    # The quantifier supplies its relationship target as context. An ancestor
    # receiver only grants Python predicate scope; it contributes no wire field,
    # so both spellings lower identically and the same Dog selection is legal.
    through_target = AnimalOwner.where(AnimalOwner.pets.exists(Pet.narrow(Dog)))
    through_ancestor = AnimalOwner.where(AnimalOwner.pets.exists(Animal.narrow(Dog)))
    assert predicate_document(preflighted(through_ancestor)) == predicate_document(
        preflighted(through_target)
    )


def test_a_narrow_to_a_class_the_position_excludes_is_refused_at_the_gate() -> None:
    # `Entity.narrow`'s subtype list keeps only its runtime rejection: a type
    # parameter's bound may not itself be generic, so the narrowed subtypes
    # cannot be bounded by the narrowing position.
    with pytest.raises(ModelRejectedError) as caught:
        preflighted(Animal.where(Animal.narrow(AnimalOwner)))
    assert caught.value.rule == "narrow-outside-position"


def test_the_narrow_clause_erases_relatedness_for_the_same_reason() -> None:
    # The clause form keeps only the same runtime rejection, and no suppression
    # belongs on this line — the erasure is what makes it accepted statically.
    # The parameter a narrow solves from its subtypes is spent on what the
    # narrowing PRODUCES: `Entity.narrow`'s on the scoped `where=`, and the
    # clause's on the result the sort keys are then measured against. It cannot
    # also constrain what the narrowing starts FROM, because `type[...]` is
    # covariant — a parameter naming the position accepts a descendant and
    # refuses an unrelated class but cannot name the result, and one naming the
    # result carries it and accepts anything. A hop narrow escapes the trade
    # only because its bound sits on the RECEIVER (see the hop case above).
    with pytest.raises(ModelRejectedError) as caught:
        preflighted(Animal.where(Animal.all).narrow(AnimalOwner))
    assert caught.value.rule == "narrow-outside-position"
