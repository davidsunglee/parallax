"""Model-aware Object Query validator unit tests (m-object-query)."""

from __future__ import annotations

from typing import Any, cast

import pytest

from parallax.core.object_query import IncludeSegment
from parallax.core.object_query import validate as query_validation
from parallax.core.object_query._nodes import IncludePath
from parallax.core.predicate import root_position
from tests.unit._corpus_model_support import formed, records


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
            IncludePath(segments=(IncludeSegment(rel="Missing.items"),)),
            model,
            root_position(model, root),
        )


def test_include_validation_rejects_a_segment_disconnected_from_the_previous_target() -> None:
    model = _orders_model()
    root = _root(model, "Order")

    with pytest.raises(ValueError, match="does not resolve from the active Include Path position"):
        query_validation.validate_include_path(
            IncludePath(
                segments=(
                    IncludeSegment(rel="Order.items"),
                    IncludeSegment(rel="Order.statuses"),
                )
            ),
            model,
            root_position(model, root),
        )
