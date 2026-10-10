"""What each expression family authors, and what selected-model binding makes
of the operations a dotted continuation defers to it.

Authoring reaches no model, so a continuation past a relationship keeps its
Python names and offers every candidate operation; the serving model's Entity
Classes resolve it when an operation binds the query.
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from parallax.core import (
    MANY_TO_ONE,
    ONE_TO_MANY,
    Attr,
    DomainModel,
    Entity,
    Int32,
    ModelRejectedError,
    QueryDefinitionError,
    Rel,
    ValueObject,
    attr,
    rel,
)
from parallax.core.predicate import Presence, Quantifier, serialize
from parallax.core.predicate._resolved import (
    RelatedObject,
    ResolvedComparison,
    ResolvedNarrow,
    ResolvedNullCheck,
    ResolvedPresence,
    ResolvedQuantifier,
    ResolvedStringMatch,
)
from tests._support.query_probes import predicate_node, typed_resolved

_NS = "expression.authoring"


class Note(ValueObject):
    words: Attr[tuple[str, ...]]


class Part(ValueObject):
    sku: Attr[str]
    note: Attr[Note | None]


class Address(ValueObject):
    city: Attr[str]


class Owner(Entity, table="ea_owner", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    manager_id: Attr[int | None]
    name: Attr[str | None] = attr(max_length=16)
    tags: Attr[tuple[str, ...]]
    address: Attr[Address | None]
    manager: Rel[Owner | None] = rel(cardinality=MANY_TO_ONE, join=("manager_id", "id"))
    baskets: Rel[tuple[Basket, ...]] = rel(reverse_of="owner")


class Basket(Entity, table="ea_basket", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    owner_id: Attr[int | None]
    holder_id: Attr[int | None]
    tags: Attr[tuple[str, ...]]
    marks: Attr[tuple[int, ...]] = attr(type=Int32)
    parts: Attr[tuple[Part, ...]]
    owner: Rel[Owner | None] = rel(cardinality=MANY_TO_ONE, join=("owner_id", "id"))


class Holder(Entity, table="ea_holder", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    baskets: Rel[tuple[Basket, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "holder_id"))


class Stranger(Entity, table="ea_stranger", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)


MODEL = DomainModel(Owner, Basket, Holder)
_BASKET = f"{_NS}.Basket"


def _resolved(query: Any) -> Any:
    return typed_resolved(query, MODEL).predicate


def _kind(predicate: Any) -> str:
    node = predicate_node(predicate)
    assert isinstance(node, Quantifier)
    return node.kind


def test_collections_quantify_and_refuse_whole_value_use() -> None:
    assert _kind(Basket.tags.all(Basket.tags.element == "a")) == "all"
    assert _kind(Basket.parts.all(Part.sku == "a")) == "all"
    assert _kind(Holder.baskets.all(Basket.id > 0)) == "all"
    for collection in (Basket.tags, Basket.parts):
        with pytest.raises(TypeError, match="no truth value"):
            bool(collection)
    with pytest.raises(QueryDefinitionError, match="many Value Object is not one scalar value"):
        _ = Basket.parts == ()
    with pytest.raises(QueryDefinitionError, match="a Value Object is not one scalar value"):
        _ = Part.note != None  # noqa: E711


def test_a_scalar_element_is_read_only_inside_its_own_collections_quantifier() -> None:
    with pytest.raises(QueryDefinitionError, match="read only inside") as unbound:
        Basket.where(Basket.tags.element == "a")
    assert unbound.value.code == "query-path-invalid"
    with pytest.raises(QueryDefinitionError, match="not an element of") as foreign:
        Basket.tags.any(Basket.marks.element == 1)
    assert foreign.value.code == "query-path-invalid"
    with pytest.raises(QueryDefinitionError, match="not an element of"):
        Basket.parts.any(cast("Any", Basket.tags.element == "a"))
    nested = Basket.tags.any(Basket.marks.any(Basket.marks.element == 1))
    assert isinstance(predicate_node(nested), Quantifier)


def test_a_scalar_element_resolves_inside_its_quantifier() -> None:
    resolved = _resolved(Basket.where(Basket.tags.any(Basket.tags.element.starts_with("a"))))
    assert isinstance(resolved, ResolvedQuantifier)
    assert isinstance(resolved.where, ResolvedStringMatch)


def test_a_string_pattern_is_admitted_as_a_string_literal() -> None:
    for known in (
        lambda: Owner.name.starts_with("\ud800"),
        lambda: Basket.tags.element.contains("\ud800"),
        lambda: Part.sku.like(cast("Any", 5)),
    ):
        with pytest.raises(QueryDefinitionError, match="developer-input rule violated"):
            known()
    deferred = Basket.where(Basket.owner.name.ends_with("\ud800"))
    with pytest.raises(QueryDefinitionError, match="developer-input rule violated"):
        _resolved(deferred)


def test_include_takes_only_include_paths() -> None:
    with pytest.raises(TypeError, match="is not an Include path"):
        Basket.where(Basket.all).include(Basket.tags)  # pyright: ignore[reportArgumentType]
    narrowed = Basket.owner.narrow(Owner)
    assert narrowed == Basket.owner.narrow(Owner)
    assert narrowed != object()
    assert hash(narrowed) == hash(Basket.owner.narrow(Owner))
    assert repr(narrowed).startswith("IncludePath(")
    with pytest.raises(AttributeError):
        _ = narrowed._hidden


def test_a_to_one_relationship_tests_presence() -> None:
    assert predicate_node(Basket.owner.not_exists()) == Presence("notExists", f"{_BASKET}.owner")


def test_a_deferred_continuation_offers_every_candidate_operation() -> None:
    deferred = Basket.owner.name
    with pytest.raises(AttributeError):
        _ = deferred._private
    assert repr(deferred) == f"DeferredExpr({_BASKET}.owner.name)"
    with pytest.raises(QueryDefinitionError, match="no canonical form"):
        predicate_node(Basket.owner.tags.any())


@pytest.mark.parametrize(
    ("predicate", "resolved_type"),
    [
        pytest.param(Basket.owner.name.is_null(), ResolvedNullCheck, id="is-null"),
        pytest.param(Basket.owner.name.is_not_null(), ResolvedNullCheck, id="is-not-null"),
        pytest.param(Basket.owner.name.like("A%"), ResolvedStringMatch, id="string"),
        pytest.param(Basket.owner.name == "Ada", ResolvedComparison, id="comparison"),
    ],
)
def test_a_deferred_scalar_operation_resolves_at_the_related_position(
    predicate: Any, resolved_type: type
) -> None:
    resolved = _resolved(Basket.where(predicate))
    assert isinstance(resolved, resolved_type)
    assert isinstance(resolved.position, RelatedObject)


@pytest.mark.parametrize(
    "predicate",
    [
        pytest.param(
            Basket.owner.tags.all(Basket.owner.tags.element == "a"), id="all-over-elements"
        ),
        pytest.param(Basket.owner.tags.none(), id="bare-none"),
        pytest.param(Basket.owner.tags.any(), id="bare-any"),
    ],
)
def test_a_deferred_quantifier_resolves_over_the_related_collection(predicate: Any) -> None:
    resolved = _resolved(Basket.where(predicate))
    assert isinstance(resolved, ResolvedQuantifier)
    assert isinstance(resolved.position, RelatedObject)


def test_deferred_presence_and_subtype_tests_resolve_at_the_reached_target() -> None:
    present = _resolved(Basket.where(Basket.owner.address.exists()))
    absent = _resolved(Basket.where(Basket.owner.manager.not_exists()))
    narrowed = _resolved(Basket.where(Basket.owner.manager.is_a(Owner)))
    assert isinstance(present, ResolvedPresence) and present.negated is False
    assert isinstance(absent, ResolvedPresence) and absent.negated is True
    assert isinstance(narrowed, ResolvedNarrow)
    assert isinstance(narrowed.target, RelatedObject)


def test_a_deferred_element_bound_to_a_relationship_is_outside_any_scalar_scope() -> None:
    query = Basket.where(Basket.owner.baskets.any(Basket.owner.baskets.element == 1))
    with pytest.raises(ModelRejectedError) as caught:
        _resolved(query)
    assert caught.value.rule == "predicate-subject-outside-scope"


def test_a_value_object_field_is_read_only_from_its_element() -> None:
    with pytest.raises(ModelRejectedError) as caught:
        _resolved(Basket.where(cast("Any", Part.sku == "a")))
    assert caught.value.rule == "predicate-subject-outside-scope"


def test_a_class_the_serving_model_does_not_compose_is_refused() -> None:
    query = Holder.where(Holder.baskets.any(cast("Any", Stranger.id == 1)))
    with pytest.raises(ValueError, match="names no declared entity"):
        _resolved(query)


def test_the_export_never_respells_another_class_as_the_bound_entity() -> None:
    # Inside `Holder.baskets` only `Basket` paths are relative; `Holder.id` there
    # would otherwise export as the basket's own `id`.
    outer = predicate_node(Holder.baskets.any(cast("Any", Holder.id == 1)))
    own = predicate_node(Holder.baskets.any(Basket.id == 1))
    assert serialize(outer)["any"]["where"] == {  # type: ignore[index] - the exported document's shape
        "eq": {"path": f"{_NS}.Holder.id", "value": 1}
    }
    assert serialize(own)["any"]["where"] == {"eq": {"path": "id", "value": 1}}  # type: ignore[index] - the exported document's shape
    with pytest.raises(ModelRejectedError):
        _resolved(Holder.where(Holder.baskets.any(cast("Any", Holder.id == 1))))


def test_a_target_local_narrow_exports_its_reached_entitys_paths_relative() -> None:
    narrowed = predicate_node(Basket.owner.is_a(Owner, where=Owner.name == "Ada"))
    assert serialize(narrowed) == {
        "narrow": {
            "path": f"{_BASKET}.owner",
            "to": [f"{_NS}.Owner"],
            "operand": {"eq": {"path": "name", "value": "Ada"}},
        }
    }
