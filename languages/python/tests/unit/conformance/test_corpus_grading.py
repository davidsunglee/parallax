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

from parallax.conformance import engine
from tests._support.case_corpus import case as corpus_case
from tests._support.corpus import CollectionKinds, case_document, compare_graph, compare_rows


def _authored_graph(case_id: str) -> tuple[dict[str, Any], CollectionKinds]:
    """One case's own authored `then.graph`, and the kinds its model declares."""
    case = corpus_case(case_id)
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
    expected, kinds = _authored_graph("m-read-planning-018")
    observed = copy.deepcopy(expected)
    customer = cast("dict[str, Any]", observed["Customer"][0])
    customer["locations"] = list(reversed(cast("list[Any]", customer["locations"])))
    compare_graph(observed, expected, kinds)


def test_a_child_level_value_object_many_compares_positionally() -> None:
    expected, kinds = _authored_graph("m-read-planning-018")
    observed = copy.deepcopy(expected)
    address = cast("dict[str, Any]", observed["Customer"][0]["address"])
    address["phones"] = list(reversed(cast("list[Any]", address["phones"])))
    with pytest.raises(AssertionError):
        compare_graph(observed, expected, kinds)


def test_one_node_grades_against_the_entity_it_names() -> None:
    case = corpus_case("m-value-object-023")
    kinds = CollectionKinds(engine.load_case_metamodel(case), "Customer")
    expected = cast("dict[str, Any]", case_document(case)["then"]["graph"]["Customer"][0])
    observed = copy.deepcopy(expected)
    address = cast("dict[str, Any]", observed["address"])
    address["phones"] = list(reversed(cast("list[Any]", address["phones"])))
    with pytest.raises(AssertionError):
        compare_graph(observed, expected, kinds)


def _authored_step_graph(case_id: str, step: int) -> tuple[dict[str, Any], CollectionKinds]:
    """One scenario step's own authored `expectGraph`, and the kinds its model
    declares — the per-step analogue of :func:`_authored_graph`."""
    case = corpus_case(case_id)
    steps = cast("list[dict[str, Any]]", case_document(case)["when"]["scenario"])
    graph = copy.deepcopy(cast("dict[str, Any]", steps[step]["expectGraph"]))
    return graph, CollectionKinds(engine.load_case_metamodel(case))


def test_a_step_graph_relationship_target_set_compares_as_a_multiset() -> None:
    # An `expectGraph` is `then.graph`'s own shape at a step, so its top-level key
    # is an Entity name and its value that Entity's result set — a multiset, like
    # every other entity collection, whatever the declared child ordering was.
    expected, kinds = _authored_step_graph("m-snapshot-read-016", 2)
    observed = {"OrderItem": list(reversed(cast("list[Any]", expected["OrderItem"])))}
    compare_graph(observed, expected, kinds)


def test_a_step_graph_rejects_a_corrupted_leaf() -> None:
    expected, kinds = _authored_step_graph("m-snapshot-read-016", 2)
    observed = copy.deepcopy(expected)
    cast("dict[str, Any]", observed["OrderItem"][0])["sku"] = "WRONG"
    with pytest.raises(AssertionError):
        compare_graph(observed, expected, kinds)


def test_a_step_graph_rejects_a_missing_node() -> None:
    # The survival claim is about CONTENTS, so a view that answered with one of the
    # two loaded items is as wrong as one that answered with the wrong values.
    expected, kinds = _authored_step_graph("m-snapshot-read-016", 2)
    observed = {"OrderItem": cast("list[Any]", expected["OrderItem"])[:1]}
    with pytest.raises(AssertionError):
        compare_graph(observed, expected, kinds)


def test_a_narrowed_view_node_losing_its_variant_fails_the_graph_grade() -> None:
    expected, kinds = _authored_graph("m-inheritance-065")
    observed = copy.deepcopy(expected)
    cast("dict[str, Any]", observed["Person"][0]["pets[Dog]"][0]).pop("_type")
    with pytest.raises(AssertionError):
        compare_graph(observed, expected, kinds)


def test_a_concrete_read_row_losing_its_variant_fails_the_row_grade() -> None:
    expected = cast(
        "list[dict[str, Any]]", case_document(corpus_case("m-inheritance-001"))["then"]["rows"]
    )
    observed = copy.deepcopy(expected)
    observed[0].pop("_type")
    with pytest.raises(AssertionError):
        compare_rows(observed, expected)


@pytest.mark.parametrize("stated", ["Dog", "parallax.compatibility.Cat"])
def test_a_narrowed_view_node_naming_the_wrong_type_fails_the_graph_grade(stated: str) -> None:
    expected, kinds = _authored_graph("m-inheritance-065")
    observed = copy.deepcopy(expected)
    cast("dict[str, Any]", observed["Person"][0]["pets[Dog]"][0])["_type"] = stated
    with pytest.raises(AssertionError):
        compare_graph(observed, expected, kinds)


@pytest.mark.parametrize("stated", ["CardPayment", "parallax.compatibility.CashPayment"])
def test_a_concrete_read_row_naming_the_wrong_type_fails_the_row_grade(stated: str) -> None:
    expected = cast(
        "list[dict[str, Any]]", case_document(corpus_case("m-inheritance-001"))["then"]["rows"]
    )
    observed = copy.deepcopy(expected)
    observed[0]["_type"] = stated
    with pytest.raises(AssertionError):
        compare_rows(observed, expected)


def test_a_node_outside_a_family_gaining_a_type_fails_the_graph_grade() -> None:
    expected, kinds = _authored_graph("m-inheritance-065")
    observed = copy.deepcopy(expected)
    cast("dict[str, Any]", observed["Person"][0])["_type"] = "parallax.compatibility.Person"
    with pytest.raises(AssertionError):
        compare_graph(observed, expected, kinds)


def test_a_child_node_padded_with_a_sibling_member_fails_the_graph_grade() -> None:
    # A `Dog` has no `indoor` key to be null, at a child level as at a root.
    expected, kinds = _authored_graph("m-snapshot-read-012")
    observed = copy.deepcopy(expected)
    cast("dict[str, Any]", observed["Person"][0]["animals"][0])["indoor"] = None
    with pytest.raises(AssertionError):
        compare_graph(observed, expected, kinds)


def test_a_root_beside_includes_padded_with_a_sibling_member_fails_the_graph_grade() -> None:
    expected, kinds = _authored_graph("m-inheritance-076")
    observed = copy.deepcopy(expected)
    cast("dict[str, Any]", observed["Animal"][0])["indoor"] = None
    with pytest.raises(AssertionError):
        compare_graph(observed, expected, kinds)


def test_a_root_collection_compares_as_a_multiset() -> None:
    expected, kinds = _authored_graph("m-inheritance-076")
    observed = {"Animal": list(reversed(cast("list[Any]", expected["Animal"])))}
    compare_graph(observed, expected, kinds)


def test_a_run_returning_a_strict_subset_of_the_expected_rows_fails_the_row_grade() -> None:
    expected: list[dict[str, Any]] = [{"id": 1}, {"id": 2}]
    with pytest.raises(AssertionError, match=r"^row count: "):
        compare_rows(expected[:1], expected)


@pytest.mark.xfail(
    reason="_scalar_equal answers exact `==` before its bool rule, so `True` equals `1` "
    "against m-case-format's `true` is never `1`"
)
@pytest.mark.parametrize(
    ("observed", "expected"), [(True, 1), (1, True), (False, 0), (0, False), (True, 1.0)]
)
def test_a_boolean_never_equals_a_number_in_the_row_grade(
    observed: object, expected: object
) -> None:
    with pytest.raises(AssertionError, match=r"^observed row unmatched: "):
        compare_rows([{"flag": observed}], [{"flag": expected}])


def test_a_list_at_an_undeclared_position_refuses_to_choose_a_comparison_rule() -> None:
    expected, kinds = _authored_graph("m-value-object-023")
    cast("dict[str, Any]", expected["Customer"][0])["undeclared"] = [1, 2]
    with pytest.raises(AssertionError, match=r"\.undeclared: the model declares no collection"):
        compare_graph(copy.deepcopy(expected), expected, kinds)
