"""Typed query composition: each static rejection beside its runtime twin.

`reportUnnecessaryTypeIgnoreComment` is `"error"` (`pyrightconfig.json`), so a
rule-coded suppression asserts in both directions: the expression must produce
exactly that diagnostic, and an ignore that goes idle fails `just
python-typecheck`. That inversion is this repository's only way to assert a type
error, which is why a case below carries its suppression and its runtime
rejection in ONE test — static and runtime agreement proved by construction
rather than in two processes that never meet.

Exactly one suppression here has no runtime twin, and it is deliberate:
`test_a_subtype_spelling_of_an_inherited_member_is_narrower_than_the_model_is`
asserts a SUCCESSFUL serialization under a `reportArgumentType` ignore. The
parameter comes from the class an access went through and the wire keeps the
class that declares the member, so `Animal.where(Dog.name == …)` reads as
`Predicate[Dog]` statically while emitting the `Animal.name` every concrete
under `Animal` answers. No type the checker can see separates it from the
rejection that IS wanted — `Animal.where(Dog.bark_volume > …)`, where the member
really is the subtype's — so the parameter is strictly narrower than the model
there, and that test is where the asymmetry is recorded rather than discovered.

The mechanism under test is variance. `Predicate[E]` holds only a canonical
operation node, so `E` appears in no field and inference would read it as
bivariant; the checker-only phantom in `entity._expressions` puts `E` in an input
position and makes it contravariant. Contravariance IS the inheritance rule: an
ancestor's member addresses every descendant position, a descendant's member
addresses none of its ancestors'. Both directions are pinned here, because a
parameter that had come out invariant would pass the rejection half and fail the
acceptance half.
"""

from __future__ import annotations

import pytest

from _support.snapshot_models import (
    Animal,
    AnimalOwner,
    Dog,
    SnapOrder,
    SnapOrderStatus,
)
from parallax.core import OperationRejectedError, Predicate
from parallax.core.op_algebra import All

# --------------------------------------------------------------------------- #
# Rejections: a predicate that does not address the queried position          #
# --------------------------------------------------------------------------- #


def test_a_subtype_predicate_never_addresses_an_ancestor_position() -> None:
    # `Predicate[Dog]` in an `Animal` position: the concrete subtype's member is
    # not available to every concrete the position resolves to, and narrowing is
    # the remedy the runtime rule names (see the narrow case below).
    with pytest.raises(OperationRejectedError) as caught:
        Animal.where(Dog.bark_volume > 3)  # pyright: ignore[reportArgumentType]
    assert caught.value.rule == "subtype-attribute-outside-narrow-scope"


def test_an_unrelated_entitys_predicate_never_addresses_the_queried_position() -> None:
    # `Predicate[AnimalOwner]` in an `Animal` position. The two Entities share
    # one model and no inheritance family, so no narrow could rescue it — which
    # is exactly the distinction between this rule and the one above.
    with pytest.raises(OperationRejectedError) as caught:
        Animal.where(AnimalOwner.name == "Ada")  # pyright: ignore[reportArgumentType]
    assert caught.value.rule == "attribute-outside-active-position"


def test_an_unrelated_entitys_predicate_is_refused_from_the_other_side_too() -> None:
    # The same rule with the positions swapped, so neither direction is accepted
    # by an accident of which Entity happens to declare the member.
    with pytest.raises(OperationRejectedError) as caught:
        AnimalOwner.where(Animal.name == "Ada")  # pyright: ignore[reportArgumentType]
    assert caught.value.rule == "attribute-outside-active-position"


# --------------------------------------------------------------------------- #
# Acceptances: the direction contravariance must keep open                    #
# --------------------------------------------------------------------------- #


def test_an_ancestors_predicate_addresses_every_descendant_position() -> None:
    # The acceptance half of the same mechanism, and the case an INVARIANT
    # parameter would break: `Predicate[Animal]` lands in a `Dog` position
    # because a root-declared member is available to every concrete under it.
    assert Dog.where(Animal.name == "Ada").serialize() == {
        "eq": {"attr": "Animal.name", "value": "Ada"}
    }


def test_an_inherited_member_is_parameterized_by_the_class_it_is_reached_through() -> None:
    # `Dog.name` reaches `Animal`'s descriptor through `Dog`, so it yields a
    # `Dog`-positioned predicate while the wire keeps the DECLARING Entity — the
    # spelling that makes the reference applicable to every concrete under
    # `Animal`. The two are different questions and the two answers differ.
    assert Dog.where(Dog.name == "Ada").serialize() == {
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
    assert Animal.where(Dog.name == "Ada").serialize() == {  # pyright: ignore[reportArgumentType]
        "eq": {"attr": "Animal.name", "value": "Ada"}
    }


def test_a_conjunction_addresses_the_position_both_of_its_operands_address() -> None:
    # An ancestor's term and a descendant's term compose, and the combination
    # lands in the descendant's query — the case a combinator demanding one
    # shared parameter would refuse for a reason no rule states.
    assert Dog.where((Animal.name == "Ada") & (Dog.bark_volume > 3)).serialize() == {
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
    assert Dog.where((Dog.bark_volume > 3) & (Animal.name == "Ada")).serialize() == {
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
        Animal.where(
            (Animal.name == "Ada") & (Dog.bark_volume > 3)  # pyright: ignore[reportArgumentType]
        )
    assert caught.value.rule == "subtype-attribute-outside-narrow-scope"


def test_the_same_laundering_is_refused_in_the_other_operand_order_too() -> None:
    # Its commuted twin, refused identically — the property that makes the
    # rejection a rule about the terms rather than about which one was typed
    # first.
    with pytest.raises(OperationRejectedError) as caught:
        Animal.where(
            (Dog.bark_volume > 3) & (Animal.name == "Ada")  # pyright: ignore[reportArgumentType]
        )
    assert caught.value.rule == "subtype-attribute-outside-narrow-scope"


def test_a_disjunction_addresses_the_meet_in_either_operand_order() -> None:
    # `|` carries the identical parameter, so the acceptance half holds for it
    # in both orders too — the combinator, not the combination, is what the
    # position comes from.
    ancestor_first = Dog.where((Animal.name == "Ada") | (Dog.bark_volume > 3)).serialize()
    descendant_first = Dog.where((Dog.bark_volume > 3) | (Animal.name == "Ada")).serialize()
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
        Animal.where(
            (Animal.name == "Ada") | (Dog.bark_volume > 3)  # pyright: ignore[reportArgumentType]
        )
    assert caught.value.rule == "subtype-attribute-outside-narrow-scope"


def test_the_disjunctions_laundering_is_refused_in_the_other_operand_order_too() -> None:
    # `|`'s commuted rejection, the twin of the `&` pair above. Without it the
    # descendant-first `__or__` could broaden or turn left-biased while every
    # other cell in the table stayed green: the forward operator alone solves the
    # meet in THIS order, so this is the case that would survive losing the
    # reflected twin.
    with pytest.raises(OperationRejectedError) as caught:
        Animal.where(
            (Dog.bark_volume > 3) | (Animal.name == "Ada")  # pyright: ignore[reportArgumentType]
        )
    assert caught.value.rule == "subtype-attribute-outside-narrow-scope"


def test_a_conjunction_of_one_positions_terms_keeps_that_position() -> None:
    # The composition does not launder a subtype's terms into an ancestor
    # position: two `Dog` terms combine to a `Dog` predicate, which the `Animal`
    # query refuses statically and the validator refuses again.
    with pytest.raises(OperationRejectedError) as caught:
        Animal.where(
            (Dog.bark_volume > 3) & (Dog.bark_volume < 9)  # pyright: ignore[reportArgumentType]
        )
    assert caught.value.rule == "subtype-attribute-outside-narrow-scope"


def test_a_narrow_scope_is_how_a_descendants_member_reaches_an_ancestor_position() -> None:
    # The sanctioned spelling of the first rejection above: `narrow` takes the
    # subtype's predicate and answers one in the narrowing class's own position,
    # so this composes where the bare subtype predicate cannot.
    assert Animal.where(Animal.narrow(Dog, where=Dog.bark_volume > 3)).serialize() == {
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
    assert SnapOrder.where(SnapOrder.price >= 600.00).serialize() == {
        "greaterThanEquals": {"attr": "SnapOrder.price", "value": 600.00}
    }


def test_an_equality_literal_is_judged_by_the_model_rather_than_by_the_signature() -> None:
    # `__eq__` keeps `object` — narrowing it is a Liskov violation against
    # `object.__eq__` — so a mismatched literal is neither a static error nor an
    # authoring-time one on a flat attribute. Where the neutral contract states a
    # literal-type rule, the model-aware validator is what states it: the same
    # mismatch one value-object hop deeper is refused by name.
    assert SnapOrder.where(SnapOrder.price == "abc").serialize() == {
        "eq": {"attr": "SnapOrder.price", "value": "abc"}
    }
    with pytest.raises(OperationRejectedError) as caught:
        SnapOrderStatus.where(SnapOrderStatus.primary_tag.label == 42)
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
