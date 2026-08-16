"""The graph comparator's collection kinds (`m-case-format` "Graph comparison
distinguishes collection kinds").

The run sweep and the API-suite story lane share one comparator
(`_support/corpus.py`), so which array it compares positionally is a grading
contract of its own: a Value Object `many` occurrence's element order is semantic
(`m-value-object`), while a root result set and a relationship collection are
multisets. Both are arrays of objects, and these cases hold the comparator to the
declaration rather than to the shape of the value.
"""

from __future__ import annotations

import copy
from typing import Any, cast

import pytest

from _support.corpus import CollectionKinds, case_document, compare_graph
from parallax.conformance import case_format, engine

_CASES = {c.case_id: c for c in case_format.load_cases()}


def _authored_graph(case_id: str) -> tuple[dict[str, Any], CollectionKinds]:
    """One case's own authored `then.graph`, and the kinds its model declares."""
    case = _CASES[case_id]
    graph = copy.deepcopy(cast("dict[str, Any]", case_document(case)["then"]["graph"]))
    return graph, CollectionKinds(engine.load_case_metamodel(case))


def test_a_value_object_many_compares_positionally() -> None:
    expected, kinds = _authored_graph("m-value-object-023")
    observed = copy.deepcopy(expected)
    address = cast("dict[str, Any]", observed["Customer"][0]["address"])
    address["phones"] = list(reversed(cast("list[Any]", address["phones"])))
    with pytest.raises(AssertionError):
        compare_graph(observed, expected, kinds)


def test_a_root_result_set_compares_as_a_multiset() -> None:
    expected, kinds = _authored_graph("m-value-object-023")
    observed = {"Customer": list(reversed(cast("list[Any]", expected["Customer"])))}
    compare_graph(observed, expected, kinds)


def test_a_relationship_collection_compares_as_a_multiset() -> None:
    expected, kinds = _authored_graph("m-deep-fetch-018")
    observed = copy.deepcopy(expected)
    customer = cast("dict[str, Any]", observed["Customer"][0])
    customer["locations"] = list(reversed(cast("list[Any]", customer["locations"])))
    compare_graph(observed, expected, kinds)


def test_a_child_level_value_object_many_compares_positionally() -> None:
    expected, kinds = _authored_graph("m-deep-fetch-018")
    observed = copy.deepcopy(expected)
    address = cast("dict[str, Any]", observed["Customer"][0]["address"])
    address["phones"] = list(reversed(cast("list[Any]", address["phones"])))
    with pytest.raises(AssertionError):
        compare_graph(observed, expected, kinds)


def test_one_node_grades_against_the_entity_it_names() -> None:
    case = _CASES["m-value-object-023"]
    kinds = CollectionKinds(engine.load_case_metamodel(case), "Customer")
    expected = cast("dict[str, Any]", case_document(case)["then"]["graph"]["Customer"][0])
    observed = copy.deepcopy(expected)
    address = cast("dict[str, Any]", observed["address"])
    address["phones"] = list(reversed(cast("list[Any]", address["phones"])))
    with pytest.raises(AssertionError):
        compare_graph(observed, expected, kinds)
