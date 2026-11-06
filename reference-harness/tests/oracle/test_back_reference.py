"""Which level a path may not continue past, read from the model alone."""

from __future__ import annotations

from pathlib import Path

import pytest

from reference_harness.case import Model, load_model
from reference_harness.object_query_oracle.includes import (
    is_back_reference,
    refuse_path_past_back_reference,
)
from reference_harness.value_object_resolve import DEEP_FETCH_PAST_BACK_REFERENCE, RejectionError

_COMPATIBILITY_ROOT = Path(__file__).resolve().parents[3] / "core" / "compatibility"
_NAMESPACE = "parallax.compatibility"


def _model(name: str) -> Model:
    return load_model(_COMPATIBILITY_ROOT, f"models/{name}.yaml")


def _rel(reference: str) -> str:
    return f"{_NAMESPACE}.{reference}"


def _query(*segments: str) -> dict[str, object]:
    return {"includes": [{"segments": [{"rel": _rel(segment)} for segment in segments]}]}


def test_a_to_one_hop_reversing_its_arrival_is_a_back_reference() -> None:
    assert is_back_reference(_model("orders"), _rel("Order.items"), _rel("OrderItem.order"))


def test_a_hop_leaving_the_root_reverses_nothing() -> None:
    assert not is_back_reference(_model("orders"), None, _rel("OrderItem.order"))


def test_a_to_many_hop_reversing_its_arrival_still_reads() -> None:
    assert not is_back_reference(_model("orders"), _rel("OrderItem.order"), _rel("Order.items"))


def test_a_hop_reaching_the_family_through_another_association_still_reads() -> None:
    assert not is_back_reference(_model("animal"), _rel("Person.pets"), _rel("Animal.owner"))


def test_a_path_ending_at_a_back_reference_is_admitted() -> None:
    refuse_path_past_back_reference(_model("orders"), _query("Order.items", "OrderItem.order"))


def test_a_path_continuing_past_a_back_reference_is_refused() -> None:
    with pytest.raises(RejectionError) as refused:
        refuse_path_past_back_reference(
            _model("orders"), _query("Order.items", "OrderItem.order", "Order.items")
        )
    assert refused.value.rule == DEEP_FETCH_PAST_BACK_REFERENCE


def test_a_path_continuing_past_another_association_is_admitted() -> None:
    refuse_path_past_back_reference(
        _model("animal"), _query("Person.pets", "Animal.owner", "Person.pets")
    )
