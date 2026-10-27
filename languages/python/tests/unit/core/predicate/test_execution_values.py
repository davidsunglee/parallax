from __future__ import annotations

from collections.abc import Mapping
from typing import Final

import pytest

from parallax.core._execution._read_query import resolve_read_query
from parallax.core.metamodel import Metamodel, TemporalDimension
from parallax.core.object_query import deserialize
from parallax.core.predicate._execution_values import (
    NO_EXECUTION_VALUE_SOURCES,
    ExecutionValueSource,
    ExecutionValueSources,
    predicate_operands,
    source_order,
    sourced_conjunction,
)
from parallax.core.predicate._resolved import (
    ResolvedAnd,
    ResolvedConstant,
    ResolvedGroup,
    ResolvedOr,
    ResolvedPredicate,
    deferred_membership,
)
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._corpus_model_support import target as corpus_target


def test_sources_order_by_category_then_position_with_valid_time_first() -> None:
    sources: list[ExecutionValueSource] = [
        ("keys",),
        ("limit",),
        ("paging", 1),
        ("temporal", TemporalDimension.TRANSACTION_TIME, "coordinate"),
        ("paging", 0),
        ("temporal", TemporalDimension.VALID_TIME, "start"),
        ("temporal", TemporalDimension.VALID_TIME, "end"),
        ("predicate", 2),
        ("predicate", 0),
    ]

    assert sorted(sources, key=source_order) == [
        ("predicate", 0),
        ("predicate", 2),
        ("temporal", TemporalDimension.VALID_TIME, "end"),
        ("temporal", TemporalDimension.VALID_TIME, "start"),
        ("temporal", TemporalDimension.TRANSACTION_TIME, "coordinate"),
        ("paging", 0),
        ("paging", 1),
        ("limit",),
        ("keys",),
    ]


_CUSTOMER = corpus_model("customer")
_ANIMAL = corpus_model("animal")


def _resolved(meta: Metamodel, target: str, predicate: Mapping[str, object]) -> ResolvedPredicate:
    document = {"target": target, "predicate": dict(predicate)}
    return resolve_read_query(deserialize(document), model=meta, form="graph").predicate


_EVERY_OPERAND_FORM: Final[dict[str, object]] = {
    "and": {
        "operands": [
            {"true": {}},
            {"eq": {"path": "Customer.name", "value": "a"}},
            {"between": {"path": "Customer.id", "lower": 1, "upper": 5}},
            {"isNull": {"path": "Customer.address.city"}},
            {
                "or": {
                    "operands": [
                        {"in": {"path": "Customer.id", "values": [7, 8, 9]}},
                        {
                            "not": {
                                "operand": {"startsWith": {"path": "Customer.name", "value": "b"}}
                            }
                        },
                    ]
                }
            },
            {
                "any": {
                    "path": "Customer.address.phones",
                    "where": {"eq": {"path": "type", "value": "home"}},
                }
            },
            {
                "any": {
                    "path": "Customer.locations",
                    "where": {"group": {"operand": {"eq": {"path": "label", "value": "depot"}}}},
                }
            },
            {"exists": {"path": "Customer.address.geo"}},
        ]
    }
}


def test_authored_operands_are_ordered_depth_first_and_sourced_at_their_occurrences() -> None:
    predicate = _resolved(_CUSTOMER, "Customer", _EVERY_OPERAND_FORM)

    assert list(predicate_operands(predicate)) == ["a", 1, 5, 7, 8, 9, "b", "home", "depot"]
    sources = ExecutionValueSources.authored(predicate)
    assert [sources.operand(path) for path in ((1,), (2,), (4, 0), (4, 1, 0))] == [
        ("predicate", 0),
        ("predicate", 1),
        ("predicate", 3),
        ("predicate", 6),
    ]
    assert sources.operand((2,), 1) == ("predicate", 2)
    assert [sources.operand((4, 0), index) for index in range(3)] == [
        ("predicate", 3),
        ("predicate", 4),
        ("predicate", 5),
    ]
    assert sources.operand((5, 0)) == ("predicate", 7)
    assert sources.operand((6, 0, 0)) == ("predicate", 8)
    for unsourced in ((), (0,), (3,), (4,), (4, 1), (5,), (6,), (6, 0), (7,)):
        assert sources.operand(unsourced) is None


def test_narrowing_and_presence_operands_follow_their_one_slot() -> None:
    predicate = _resolved(
        _ANIMAL,
        "Animal",
        {
            "or": {
                "operands": [
                    {
                        "narrow": {
                            "to": ["Dog"],
                            "operand": {"eq": {"path": "Dog.name", "value": "rex"}},
                        }
                    },
                    {
                        "exists": {
                            "path": "Animal.owner",
                            "where": {"eq": {"path": "name", "value": "ada"}},
                        }
                    },
                ]
            }
        },
    )

    assert list(predicate_operands(predicate)) == ["rex", "ada"]
    sources = ExecutionValueSources.authored(predicate)
    assert (sources.operand((0, 0)), sources.operand((1, 0))) == (
        ("predicate", 0),
        ("predicate", 1),
    )


def test_repeated_uses_of_one_node_are_separate_occurrences() -> None:
    comparison = _resolved(_CUSTOMER, "Customer", {"eq": {"path": "Customer.name", "value": "a"}})
    repeated = ResolvedAnd((comparison, comparison))

    assert list(predicate_operands(repeated)) == ["a", "a"]
    sources = ExecutionValueSources.authored(repeated)
    assert (sources.operand((0,)), sources.operand((1,))) == (("predicate", 0), ("predicate", 1))


def test_sources_rerooted_within_an_occurrence_keep_only_what_lies_beneath_it() -> None:
    predicate = _resolved(_CUSTOMER, "Customer", _EVERY_OPERAND_FORM)
    sources = ExecutionValueSources.authored(predicate)

    within = sources.within((4,))

    assert (within.operand((0,)), within.operand((1, 0))) == (("predicate", 3), ("predicate", 6))
    assert within.operand(()) is None
    assert sources.within((7,)).operand(()) is None


def test_a_composed_conjunction_carries_each_terms_sources_where_it_placed_them() -> None:
    def comparison(value: str) -> ResolvedPredicate:
        return _resolved(_CUSTOMER, "Customer", {"eq": {"path": "Customer.name", "value": value}})

    conjunct = ResolvedAnd((comparison("a"), comparison("b")))
    alternative = ResolvedOr((comparison("c"), comparison("d")))
    generated = comparison("e")
    authored = ExecutionValueSources.authored

    flattened, flattened_sources = sourced_conjunction(
        (ResolvedConstant(True), NO_EXECUTION_VALUE_SOURCES),
        (conjunct, authored(conjunct)),
        (alternative, authored(alternative)),
        (generated, NO_EXECUTION_VALUE_SOURCES),
    )

    assert isinstance(flattened, ResolvedAnd)
    assert [type(operand).__name__ for operand in flattened.operands] == [
        "ResolvedComparison",
        "ResolvedComparison",
        "ResolvedGroup",
        "ResolvedComparison",
    ]
    assert [flattened_sources.operand(path) for path in ((0,), (1,), (2, 0, 0), (2, 0, 1))] == [
        ("predicate", 0),
        ("predicate", 1),
        ("predicate", 0),
        ("predicate", 1),
    ]
    assert flattened_sources.operand((3,)) is None

    alone, alone_sources = sourced_conjunction(
        (alternative, authored(alternative)), (ResolvedConstant(True), NO_EXECUTION_VALUE_SOURCES)
    )
    assert isinstance(alone, ResolvedGroup)
    assert (alone_sources.operand((0, 0)), alone_sources.operand((0, 1))) == (
        ("predicate", 0),
        ("predicate", 1),
    )
    single, single_sources = sourced_conjunction((generated, authored(generated)))
    assert single is generated
    assert single_sources.operand(()) == ("predicate", 0)


def test_a_gathered_key_set_and_a_null_check_defer_no_authored_operand() -> None:
    null_check = _resolved(_CUSTOMER, "Customer", {"isNull": {"path": "Customer.address.city"}})
    member = corpus_target(_CUSTOMER, "Customer").attribute("id")
    assert member is not None
    keyed = deferred_membership(member=member)
    predicate = ResolvedAnd((keyed, null_check))

    assert list(predicate_operands(predicate)) == []
    assert ExecutionValueSources.authored(predicate) == NO_EXECUTION_VALUE_SOURCES


def test_only_an_authored_occurrence_renders_several_operands() -> None:
    temporal: ExecutionValueSource = ("temporal", TemporalDimension.VALID_TIME, "coordinate")
    sources = ExecutionValueSources({(): temporal})

    assert sources.operand(()) == temporal
    with pytest.raises(ValueError, match="only an authored occurrence"):
        sources.operand((), 1)
