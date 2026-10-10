"""Model-aware Object Query validator unit tests (m-object-query)."""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from typing import Any, cast

import pytest

from parallax.core.object_query import IncludeSegment, deserialize
from parallax.core.object_query import validate as query_validation
from parallax.core.object_query._nodes import IncludePathNode
from parallax.core.predicate import root_position
from tests.unit._corpus_model_support import formed, records
from tests.unit._corpus_model_support import model as corpus_model


def _orders_model() -> Any:
    return formed(records("orders"))


def _root(model: object, target: str) -> Any:
    return next(
        entity
        for entity in cast("Any", model).entities
        if target in (entity.identity.name, entity.identity.canonical)
    )


def test_include_validation_rejects_a_relationship_with_no_declaring_entity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _orders_model()
    root = _root(model, "Order")
    monkeypatch.setattr(
        query_validation,
        "relationship_target",
        lambda *_args, **_kwargs: root,  # pyright: ignore[reportUnknownArgumentType,reportUnknownLambdaType]
    )

    with pytest.raises(ValueError, match="no resolved relationship direction"):
        query_validation.validate_include_path(
            IncludePathNode(segments=(IncludeSegment(rel="Missing.items"),)),
            model,
            root_position(model, root),
        )


def test_include_validation_rejects_a_segment_disconnected_from_the_previous_target() -> None:
    model = _orders_model()
    root = _root(model, "Order")

    with pytest.raises(ValueError, match="does not resolve from the active Include Path position"):
        query_validation.validate_include_path(
            IncludePathNode(
                segments=(
                    IncludeSegment(rel="Order.items"),
                    IncludeSegment(rel="Order.statuses"),
                )
            ),
            model,
            root_position(model, root),
        )


_CANONICAL_MODULES = frozenset(
    {"parallax.core.predicate._nodes", "parallax.core.object_query._nodes"}
)
_RESOLVED_MODULES = frozenset(
    {"parallax.core.predicate._resolved", "parallax.core.object_query._resolved"}
)


def _within_resolved_products(value: object) -> Iterator[object]:
    """``value`` and everything reachable from it through resolved products,
    stopping at the accepted metadata they borrow."""
    yield value
    if isinstance(value, tuple):
        for item in cast("tuple[object, ...]", value):
            yield from _within_resolved_products(item)
    elif type(value).__module__ in _RESOLVED_MODULES and dataclasses.is_dataclass(value):
        for field in dataclasses.fields(value):
            yield from _within_resolved_products(getattr(value, field.name))


_RESOLVED_QUERIES: tuple[tuple[str, dict[str, object]], ...] = (
    (
        "customer",
        {
            "target": "Customer",
            "predicate": {
                "and": {
                    "operands": [
                        {
                            "any": {
                                "path": "Customer.address.phones",
                                "where": {"eq": {"path": "type", "value": "x"}},
                            }
                        },
                        {
                            "none": {
                                "path": "Customer.address.phones",
                                "where": {"isNotNull": {"path": "number"}},
                            }
                        },
                        {"not": {"operand": {"any": {"path": "Customer.locations"}}}},
                        {"startsWith": {"path": "Customer.name", "value": "A"}},
                    ]
                }
            },
            "orderBy": [{"attr": "Customer.name", "direction": "desc"}],
            "includes": [{"segments": [{"rel": "Customer.locations"}]}],
            "limit": 3,
        },
    ),
    (
        "animal",
        {
            "target": "Animal",
            "predicate": {
                "or": {
                    "operands": [
                        {"narrow": {"to": ["Dog"], "operand": {"true": {}}}},
                        {"group": {"operand": {"in": {"path": "Animal.id", "values": [1]}}}},
                    ]
                }
            },
            "narrowTo": ["Pet"],
        },
    ),
    (
        "balance",
        {
            "target": "Balance",
            "predicate": {"between": {"path": "Balance.id", "lower": 1, "upper": 2}},
            "temporal": {"transaction-time": {"asOf": "2024-06-15T00:00:00.000000Z"}},
        },
    ),
)


@pytest.mark.parametrize(
    ("stem", "document"),
    _RESOLVED_QUERIES,
    ids=["value-objects-and-relationships", "narrowing", "temporal"],
)
def test_a_resolved_query_retains_no_canonical_node(stem: str, document: dict[str, object]) -> None:
    model = corpus_model(stem)
    query = deserialize(document)
    resolved = query_validation.validate_object_query(_root(model, query.target.name), query, model)

    reached = tuple(_within_resolved_products(resolved))

    assert len(reached) > 1
    assert not [value for value in reached if type(value).__module__ in _CANONICAL_MODULES]
