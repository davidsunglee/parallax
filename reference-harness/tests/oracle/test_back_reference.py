"""Which level a path may not continue past, and what a level ending one attaches."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from reference_harness.case import Case, Model, load_model
from reference_harness.object_query_oracle import materialize
from reference_harness.object_query_oracle.includes import (
    execute_fetch_levels,
    fetch_steps,
    is_back_reference,
    refuse_path_past_back_reference,
)
from reference_harness.value_object_resolve import DEEP_FETCH_PAST_BACK_REFERENCE, RejectionError

from .conftest import ScriptedReads

_COMPATIBILITY_ROOT = Path(__file__).resolve().parents[3] / "core" / "compatibility"
_NAMESPACE = "parallax.compatibility"
_NARROWED_BACK_REFERENCE = "m-read-planning-033-a-narrowed-back-reference-reads-nothing-tpcs.yaml"


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


def _attached_to_a_concrete_root(
    concrete: str, narrow_to: list[str] | None, case: Case
) -> dict[Any, list[materialize.PublishedRow]]:
    """What the back-reference closing `Keeper.charges`, `Charge.keeper` attaches when
    the root is read at *concrete*, whose statement projects no carrier."""
    closing = {"rel": _rel("Charge.keeper")}
    if narrow_to is not None:
        closing["narrowTo"] = narrow_to
    query = {
        "target": _rel(concrete),
        "includes": [{"segments": [{"rel": _rel("Keeper.charges")}, closing]}],
    }
    case.raw["when"]["objectQuery"] = query
    case.raw["then"]["statements"][0]["sql"]["postgres"] = (
        f"select t0.id, t0.name from keeper_{concrete.lower()} t0"
    )
    steps = fetch_steps(case.model, query)
    executed = execute_fetch_levels(
        case,
        ScriptedReads(results=[[{"id": 11, "keeper_id": 1, "label": "north"}]]),
        "then.statements",
        query,
        steps,
        materialize.materialize_read(case, [{"id": 1, "name": "Rae"}]),
        [
            (
                "select t0.id, t0.keeper_id, t0.label from keeper_charge t0 "
                "where t0.keeper_id = any(cast(? as bigint[])) order by t0.id asc",
                [[1]],
            )
        ],
    )
    return executed.children_by_hop[steps[-1].hop_key]


def test_a_narrow_selects_a_concrete_root_by_the_concrete_it_was_read_at(
    damaged_case: Callable[[str], Case],
) -> None:
    attached = _attached_to_a_concrete_root(
        "Ranger", [_rel("Ranger"), _rel("Warden")], damaged_case(_NARROWED_BACK_REFERENCE)
    )
    assert attached == {1: [{"id": 1, "name": "Rae", "familyVariant": "Ranger"}]}


def test_a_narrow_leaves_out_a_concrete_root_of_another_concrete(
    damaged_case: Callable[[str], Case],
) -> None:
    attached = _attached_to_a_concrete_root(
        "Vet", [_rel("Ranger"), _rel("Warden")], damaged_case(_NARROWED_BACK_REFERENCE)
    )
    assert attached == {}


def test_a_broad_polymorphic_view_tags_a_concrete_root(
    damaged_case: Callable[[str], Case],
) -> None:
    attached = _attached_to_a_concrete_root("Ranger", None, damaged_case(_NARROWED_BACK_REFERENCE))
    assert attached == {1: [{"id": 1, "name": "Rae", "familyVariant": "Ranger"}]}
