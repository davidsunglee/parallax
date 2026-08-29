"""Instance-form reads through ``assert_case_read``: Includes, graphs, milestone sets.

The three eager terminals that publish a Snapshot Graph rather than rows. What
each proves is a different independent derivation over the same materialization
spine: a deep fetch derives the parent keys, tag values, and propagated as-of
coordinates every child level must carry; a milestone set derives which delivered
root each declared pin claims; a single-statement graph derives the composite a
Structured Column holds for its owner.

The rows a script hands back are PHYSICAL — raw discriminator columns, stored
documents, from/thru instants — and the case authors the LOGICAL graph, so every
test here is also a test that the oracle derives the second from the first.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from decimal import Decimal
from typing import Any, cast

import pytest

from reference_harness.case import Case
from reference_harness.case_assertions import CaseFailure
from reference_harness.object_query_oracle import assert_case_read
from reference_harness.object_query_oracle import materialize as oracle_materialize

from .conftest import ScriptedReads

CaseLoader = Callable[[str], Case]

_ORDERED_ITEMS = "m-deep-fetch-009-ordered-items-desc.yaml"
_EMPTY_ROOT = "m-deep-fetch-006-empty-root.yaml"
_NARROWED_PETS = "m-inheritance-065-tph-deepfetch-narrowed-pets-dog.yaml"
_BROAD_AND_NARROWED_PETS = "m-inheritance-068-tph-deepfetch-broad-and-redundant-narrow.yaml"
_GUARDED_BRANCHES = "m-inheritance-078-tph-deepfetch-guarded-branches-diverge.yaml"
_TEMPORAL_DEEP_FETCH = "m-navigate-012-deepfetch-temporal-both-latest.yaml"
_HISTORY_GRAPHS = "m-snapshot-read-013-history-edge-pinned-graphs.yaml"
_ABSTRACT_ROOT_GRAPH = "m-inheritance-106-tph-abstract-root-read-graph.yaml"
_VALUE_OBJECT_GRAPH = "m-value-object-023-graph-nested-materialization.yaml"
_FILTERED_VALUE_OBJECT_GRAPH = "m-value-object-024-graph-filtered-materialization.yaml"

_ORDER_ONE: list[dict[str, Any]] = [
    {
        "id": 1,
        "name": "Ada",
        "sku": "A-100",
        "qty": 5,
        "price": Decimal("10.50"),
        "active": True,
        "ordered_on": "2024-01-05",
    }
]

# `Order.items` declares `id desc`, so the child level must return 12 before 11.
_ORDER_ONE_ITEMS: list[dict[str, Any]] = [
    {"id": 12, "order_id": 1, "sku": "B-200", "quantity": 1, "shipped_on": "2024-02-15"},
    {"id": 11, "order_id": 1, "sku": "A-100", "quantity": 2, "shipped_on": None},
]

_PEOPLE: list[dict[str, Any]] = [
    {"id": 10, "name": "Alice"},
    {"id": 11, "name": "Bob"},
    {"id": 12, "name": "Carol"},
]

# The narrowed `pets[Dog]` level reads one concrete, so its shared-table read
# projects no tag column and its rows carry no variant.
_DOGS: list[dict[str, Any]] = [
    {"id": 1, "name": "Rex", "owner_id": 10, "license_id": "L-100", "bark_volume": 7},
    {"id": 2, "name": "Fido", "owner_id": 11, "license_id": "L-101", "bark_volume": 3},
]

# A polymorphic hop projects the raw `kind` column instead; `familyVariant` is
# materialized from the tag metadata map.
_PETS: list[dict[str, Any]] = [
    {
        "id": 1,
        "kind": "dog",
        "name": "Rex",
        "owner_id": 10,
        "license_id": "L-100",
        "indoor": None,
        "bark_volume": 7,
    },
    {
        "id": 2,
        "kind": "dog",
        "name": "Fido",
        "owner_id": 11,
        "license_id": "L-101",
        "indoor": None,
        "bark_volume": 3,
    },
    {
        "id": 3,
        "kind": "cat",
        "name": "Whiskers",
        "owner_id": 10,
        "license_id": "L-200",
        "indoor": True,
        "bark_volume": None,
    },
]

_FOREVER = "infinity"
_JANUARY = "2024-01-01T00:00:00+00:00"
_APRIL = "2024-04-01T00:00:00+00:00"
_JUNE = "2024-06-01T00:00:00+00:00"

_POLICIES: list[dict[str, Any]] = [
    {
        "id": 1,
        "name": "Auto",
        "from_z": _JANUARY,
        "thru_z": _FOREVER,
        "in_z": _JANUARY,
        "out_z": _FOREVER,
    },
    {
        "id": 2,
        "name": "Home",
        "from_z": _JANUARY,
        "thru_z": _FOREVER,
        "in_z": _JANUARY,
        "out_z": _FOREVER,
    },
]

_COVERAGES: list[dict[str, Any]] = [
    {
        "id": 10,
        "policy_id": 1,
        "amount": Decimal("700.00"),
        "from_z": _JUNE,
        "thru_z": _FOREVER,
        "in_z": _APRIL,
        "out_z": _FOREVER,
    },
    {
        "id": 20,
        "policy_id": 2,
        "amount": Decimal("300.00"),
        "from_z": _JANUARY,
        "thru_z": _FOREVER,
        "in_z": _JANUARY,
        "out_z": _FOREVER,
    },
]

# InvoiceLine 1000's two Transaction-Time milestones: the superseded 50.00 row
# [2024-01-01, 2024-04-01) and the current 75.00 row [2024-04-01, infinity).
_MILESTONES: list[dict[str, Any]] = [
    {
        "id": 1000,
        "invoice_id": 100,
        "amount": Decimal("50.00"),
        "in_z": _JANUARY,
        "out_z": _APRIL,
    },
    {
        "id": 1000,
        "invoice_id": 100,
        "amount": Decimal("75.00"),
        "in_z": _APRIL,
        "out_z": _FOREVER,
    },
]

_PAYMENTS: list[dict[str, Any]] = [
    {
        "id": 1,
        "kind": "card",
        "amount": Decimal("100.00"),
        "card_network": "Visa",
        "tendered": None,
    },
    {"id": 2, "kind": "card", "amount": Decimal("50.00"), "card_network": "Amex", "tendered": None},
    {
        "id": 3,
        "kind": "cash",
        "amount": Decimal("20.00"),
        "card_network": None,
        "tendered": Decimal("25.00"),
    },
]


def _customers(case: Case, dialect: str, ids: list[int]) -> list[dict[str, Any]]:
    """The Customer fixture rows as each driver hands the owner statement back.

    The golden projects ``t0.id, t0.name, <presence>, t0.address``. On Postgres the
    ``jsonb`` column arrives already parsed; on MariaDB the ``json`` column arrives
    as text — the same composite, so the materializer must be dialect-agnostic.
    """
    by_id = {row["id"]: row for row in case.model.entity("Customer").rows}
    rows: list[dict[str, Any]] = []
    for identifier in ids:
        fixture = by_id[identifier]
        address = fixture.get("address")
        if dialect == "mariadb" and address is not None:
            address = json.dumps(address)
        rows.append({"id": fixture["id"], "name": fixture["name"], "address": address})
    return rows


def _customer_identities(case: Case, ids: list[int]) -> list[dict[str, Any]]:
    """What the independent ``referenceSql`` oracle selects: the matched row set."""
    by_id = {row["id"]: row for row in case.model.entity("Customer").rows}
    return [
        {"id": by_id[identifier]["id"], "name": by_id[identifier]["name"]} for identifier in ids
    ]


# --- deep fetch --------------------------------------------------------------


def test_a_deep_fetch_assembles_the_authored_graph(corpus_case: CaseLoader) -> None:
    case = corpus_case(_ORDERED_ITEMS)
    reads = ScriptedReads(results=[_ORDER_ONE, _ORDER_ONE_ITEMS, _ORDER_ONE])

    assert_case_read(case, reads)

    assert reads.statements[:2] == case.golden_statements("postgres")


def test_the_child_level_is_keyed_by_the_gathered_parent_keys(corpus_case: CaseLoader) -> None:
    case = corpus_case(_ORDERED_ITEMS)
    reads = ScriptedReads(results=[_ORDER_ONE, _ORDER_ONE_ITEMS, _ORDER_ONE])

    assert_case_read(case, reads)

    assert reads.calls[1][1] == (1,)


def test_a_child_level_keyed_by_anything_else_is_refused(damaged_case: CaseLoader) -> None:
    case = damaged_case(_ORDERED_ITEMS)
    case.then["statements"][1]["binds"] = [2]
    reads = ScriptedReads(results=[_ORDER_ONE, _ORDER_ONE_ITEMS, _ORDER_ONE])

    with pytest.raises(CaseFailure, match="IN-list binds"):
        assert_case_read(case, reads)


def test_an_empty_root_elides_every_child_level(corpus_case: CaseLoader) -> None:
    case = corpus_case(_EMPTY_ROOT)
    reads = ScriptedReads(results=[[], []])

    assert_case_read(case, reads)

    # Two statements ran: the root, and the independent oracle the case authors
    # beside it. Neither of the two elided Include levels issued SQL.
    assert len(reads.calls) == 2
    assert not any("order_item" in statement for statement in reads.statements)


def test_a_child_statement_no_level_reached_is_refused(damaged_case: CaseLoader) -> None:
    case = damaged_case(_EMPTY_ROOT)
    case.then["statements"].append(
        {"sql": {"postgres": "select t0.id from order_item t0 where t0.order_id in (?)"}}
    )
    reads = ScriptedReads(results=[[], []])

    with pytest.raises(CaseFailure, match="unused deep-fetch child statement"):
        assert_case_read(case, reads)


def test_children_returned_out_of_the_declared_order_are_refused(
    corpus_case: CaseLoader,
) -> None:
    case = corpus_case(_ORDERED_ITEMS)
    ascending = list(reversed(_ORDER_ONE_ITEMS))
    reads = ScriptedReads(results=[_ORDER_ONE, ascending, _ORDER_ONE])

    with pytest.raises(CaseFailure, match="not in declared orderBy order"):
        assert_case_read(case, reads)


def test_an_orderby_key_the_child_did_not_project_is_refused(corpus_case: CaseLoader) -> None:
    case = corpus_case(_ORDERED_ITEMS)
    unprojected = [
        {key: value for key, value in row.items() if key != "id"} for row in _ORDER_ONE_ITEMS
    ]
    reads = ScriptedReads(results=[_ORDER_ONE, unprojected, _ORDER_ONE])

    with pytest.raises(CaseFailure, match="orderBy column"):
        assert_case_read(case, reads)


def test_a_narrowed_hop_attaches_under_its_derived_view_key(corpus_case: CaseLoader) -> None:
    case = corpus_case(_NARROWED_PETS)
    reads = ScriptedReads(results=[_PEOPLE, _DOGS, _PEOPLE])

    assert_case_read(case, reads)

    # The single-concrete narrow filters the shared table by the effective set's
    # tag value, appended after the IN-list of gathered owner ids.
    assert reads.calls[1][1] == (10, 11, 12, "dog")


def test_a_broad_and_a_redundantly_narrowed_hop_are_two_levels(corpus_case: CaseLoader) -> None:
    case = corpus_case(_BROAD_AND_NARROWED_PETS)
    reads = ScriptedReads(results=[_PEOPLE, _PETS, _PETS, _PEOPLE])

    assert_case_read(case, reads)

    assert len(reads.calls) == 4
    assert reads.calls[1][1] == reads.calls[2][1] == (10, 11, 12, "cat", "dog")


_ROOT_ANIMALS: list[dict[str, Any]] = [
    {
        "id": 1,
        "kind": "dog",
        "name": "Rex",
        "owner_id": 10,
        "license_id": "L-100",
        "indoor": None,
        "bark_volume": 7,
        "tusk_length": None,
    },
    {
        "id": 2,
        "kind": "dog",
        "name": "Fido",
        "owner_id": 11,
        "license_id": "L-101",
        "indoor": None,
        "bark_volume": 3,
        "tusk_length": None,
    },
    {
        "id": 3,
        "kind": "cat",
        "name": "Whiskers",
        "owner_id": 10,
        "license_id": "L-200",
        "indoor": True,
        "bark_volume": None,
        "tusk_length": None,
    },
    {
        "id": 4,
        "kind": "boar",
        "name": "Tusker",
        "owner_id": 12,
        "license_id": None,
        "indoor": None,
        "bark_volume": None,
        "tusk_length": Decimal("12.50"),
    },
    {
        "id": 5,
        "kind": "cat",
        "name": "Mittens",
        "owner_id": 12,
        "license_id": "L-300",
        "indoor": True,
        "bark_volume": None,
        "tusk_length": None,
    },
]

_ANIMAL_BY_ID = {row["id"]: row for row in _ROOT_ANIMALS}

_PETS_LEVEL_SQL = (
    "select t0.id, t0.kind, t0.name, t0.owner_id, t0.license_id, t0.indoor, "
    "t0.bark_volume from animal t0 where t0.owner_id in ({placeholders}) and "
    "t0.kind in (?, ?)"
)


def _pet_level_rows(*ids: int) -> list[dict[str, Any]]:
    """The `pets` level rows for *ids*, projected at Pet's own superset."""
    return [
        {key: value for key, value in _ANIMAL_BY_ID[identifier].items() if key != "tusk_length"}
        for identifier in ids
    ]


def _pet_node(identifier: int, variant: str) -> dict[str, Any]:
    row = _ANIMAL_BY_ID[identifier]
    return {
        "id": row["id"],
        "name": row["name"],
        "ownerId": row["owner_id"],
        "licenseId": row["license_id"],
        "indoor": row["indoor"],
        "barkVolume": row["bark_volume"],
        "familyVariant": variant,
    }


def _root_node(identifier: int, variant: str, **views: Any) -> dict[str, Any]:
    row = _ANIMAL_BY_ID[identifier]
    return {
        "id": row["id"],
        "name": row["name"],
        "ownerId": row["owner_id"],
        "licenseId": row["license_id"],
        "indoor": row["indoor"],
        "barkVolume": row["bark_volume"],
        "tuskLength": row["tusk_length"],
        "familyVariant": variant,
        **views,
    }


def _both_guarded_branches_continue(case: Case) -> Case:
    """`m-inheritance-078` with BOTH guarded branches continuing into `pets`.

    The corpus carries the shape one branch deeper than the other; this legal
    variation of it walks the same relationship from two different parent hops, so
    what identifies a level is exercised at the segment's parent rather than only
    at the path's root guard.
    """
    case.object_query["includes"][0]["segments"].append(
        {"rel": "parallax.compatibility.Person.pets"}
    )
    case.then["statements"] = [
        {"sql": {"postgres": case.then["statements"][0]["sql"]["postgres"]}},
        {
            "sql": {"postgres": "select t0.id, t0.name from person t0 where t0.id in (?)"},
            "binds": [12],
        },
        {
            "sql": {"postgres": _PETS_LEVEL_SQL.format(placeholders="?")},
            "binds": [12, "cat", "dog"],
        },
        {
            "sql": {"postgres": "select t0.id, t0.name from person t0 where t0.id in (?, ?)"},
            "binds": [10, 11],
        },
        {
            "sql": {"postgres": _PETS_LEVEL_SQL.format(placeholders="?, ?")},
            "binds": [10, 11, "cat", "dog"],
        },
    ]
    case.then["roundTrips"] = 5
    case.then["graph"] = {
        "Animal": [
            _root_node(
                1,
                "Dog",
                owner={
                    "id": 10,
                    "name": "Alice",
                    "pets": [_pet_node(1, "Dog"), _pet_node(3, "Cat")],
                },
            ),
            _root_node(2, "Dog", owner={"id": 11, "name": "Bob", "pets": [_pet_node(2, "Dog")]}),
            _root_node(3, "Cat"),
            _root_node(
                4,
                "WildBoar",
                owner={"id": 12, "name": "Carol", "pets": [_pet_node(5, "Cat")]},
            ),
            _root_node(5, "Cat"),
        ]
    }
    return case


def test_two_parent_branches_reaching_one_relationship_are_two_levels(
    damaged_case: CaseLoader,
) -> None:
    """One relationship reached from two DIFFERENT parents is two hops.

    Each gathers its keys from its own branch's rows, so the two can share neither
    a statement nor a bucket of fetched children (`m-deep-fetch` branch
    provenance). The `pets` hop under the WildBoar branch's owner asks for Carol's
    pets alone and the one under the Dog branch's owners asks for Alice's and
    Bob's; a level identified without its parent would issue one statement for
    both and attach every fetched pet to every owner.
    """
    case = _both_guarded_branches_continue(damaged_case(_GUARDED_BRANCHES))
    reads = ScriptedReads(
        results=[
            _ROOT_ANIMALS,
            [{"id": 12, "name": "Carol"}],
            _pet_level_rows(5),
            [{"id": 10, "name": "Alice"}, {"id": 11, "name": "Bob"}],
            _pet_level_rows(1, 2, 3),
            _ROOT_ANIMALS,
        ]
    )

    assert_case_read(case, reads)

    assert len(reads.calls) == 6
    assert [binds for _sql, binds in reads.calls[1:5]] == [
        (12,),
        (12, "cat", "dog"),
        (10, 11),
        (10, 11, "cat", "dog"),
    ]


def test_a_polymorphic_hop_tag_value_naming_no_subtype_is_refused(
    corpus_case: CaseLoader,
) -> None:
    case = corpus_case(_BROAD_AND_NARROWED_PETS)
    stray = [dict(_PETS[0]) | {"kind": "sturgeon"}, *_PETS[1:]]
    reads = ScriptedReads(results=[_PEOPLE, stray, _PETS, _PEOPLE])

    with pytest.raises(CaseFailure, match="maps to no concrete subtype"):
        assert_case_read(case, reads)


def test_a_hop_that_drops_a_tag_bind_is_refused(damaged_case: CaseLoader) -> None:
    case = damaged_case(_BROAD_AND_NARROWED_PETS)
    case.then["statements"][1]["binds"] = [10, 11, 12, "cat"]
    reads = ScriptedReads(results=[_PEOPLE, _PETS, _PETS, _PEOPLE])

    with pytest.raises(CaseFailure, match="tag binds"):
        assert_case_read(case, reads)


def test_the_root_as_of_pin_propagates_to_a_temporal_child_level(
    corpus_case: CaseLoader,
) -> None:
    case = corpus_case(_TEMPORAL_DEEP_FETCH)
    reads = ScriptedReads(results=[_POLICIES, _COVERAGES])

    assert_case_read(case, reads)

    assert reads.calls[1][1] == (1, 2, _FOREVER, _FOREVER)


def test_a_child_level_carrying_the_wrong_as_of_suffix_is_refused(
    damaged_case: CaseLoader,
) -> None:
    case = damaged_case(_TEMPORAL_DEEP_FETCH)
    case.then["statements"][1]["binds"][-1] = "2099-01-01T00:00:00+00:00"
    reads = ScriptedReads(results=[_POLICIES, _COVERAGES])

    with pytest.raises(CaseFailure, match="as-of suffix"):
        assert_case_read(case, reads)


def test_a_deep_fetch_graph_the_case_did_not_author_is_refused(corpus_case: CaseLoader) -> None:
    case = corpus_case(_ORDERED_ITEMS)
    missing_child = [_ORDER_ONE_ITEMS[0]]
    reads = ScriptedReads(results=[_ORDER_ONE, missing_child, _ORDER_ONE])

    with pytest.raises(CaseFailure, match="assembled graph != then.graph"):
        assert_case_read(case, reads)


def test_the_deep_fetch_reference_oracle_grades_the_root_rows(corpus_case: CaseLoader) -> None:
    case = corpus_case(_ORDERED_ITEMS)
    reads = ScriptedReads(results=[_ORDER_ONE, _ORDER_ONE_ITEMS, []])

    with pytest.raises(CaseFailure, match="referenceSql root rows"):
        assert_case_read(case, reads)


# --- milestone sets -----------------------------------------------------------


def test_a_milestone_set_partitions_its_rows_into_edge_pinned_graphs(
    corpus_case: CaseLoader,
) -> None:
    case = corpus_case(_HISTORY_GRAPHS)
    reads = ScriptedReads(results=[_MILESTONES, _MILESTONES])

    assert_case_read(case, reads)

    # One round trip returns the whole milestone set; the second call is the
    # independent oracle cross-checking it.
    assert len(reads.calls) == 2


def test_a_repeated_milestone_pin_is_refused(damaged_case: CaseLoader) -> None:
    case = damaged_case(_HISTORY_GRAPHS)
    case.then["graphs"].append(copy.deepcopy(case.then["graphs"][0]))
    reads = ScriptedReads(results=[_MILESTONES, _MILESTONES])

    with pytest.raises(CaseFailure, match="repeats the pin declared by"):
        assert_case_read(case, reads)


def test_a_milestone_claimed_by_no_pin_is_refused(damaged_case: CaseLoader) -> None:
    case = damaged_case(_HISTORY_GRAPHS)
    del case.then["graphs"][1]
    reads = ScriptedReads(results=[_MILESTONES, _MILESTONES])

    with pytest.raises(CaseFailure, match="matched no then.graphs pin"):
        assert_case_read(case, reads)


def test_a_pin_matching_no_milestone_is_refused(damaged_case: CaseLoader) -> None:
    case = damaged_case(_HISTORY_GRAPHS)
    case.then["graphs"][0]["pin"]["transaction-time"] = "2023-01-01T00:00:00+00:00"
    reads = ScriptedReads(results=[_MILESTONES, _MILESTONES])

    with pytest.raises(CaseFailure, match="matched no milestone row"):
        assert_case_read(case, reads)


def test_a_pin_naming_an_axis_the_root_does_not_declare_is_refused(
    damaged_case: CaseLoader,
) -> None:
    case = damaged_case(_HISTORY_GRAPHS)
    case.then["graphs"][0]["pin"] = {"valid-time": _JANUARY}
    reads = ScriptedReads(results=[_MILESTONES, _MILESTONES])

    with pytest.raises(CaseFailure, match="does not declare"):
        assert_case_read(case, reads)


def test_the_milestone_reference_oracle_cross_checks_the_whole_set(
    corpus_case: CaseLoader,
) -> None:
    case = corpus_case(_HISTORY_GRAPHS)
    reads = ScriptedReads(results=[_MILESTONES, _MILESTONES[:1]])

    with pytest.raises(CaseFailure, match="referenceSql rows != then.statements milestone rows"):
        assert_case_read(case, reads)


# --- single-statement graphs --------------------------------------------------


@pytest.mark.parametrize("dialect", ["postgres", "mariadb"])
def test_a_value_object_composite_materializes_from_one_statement(
    corpus_case: CaseLoader, dialect: str
) -> None:
    case = corpus_case(_VALUE_OBJECT_GRAPH)
    owners = list(range(1, 11))
    reads = ScriptedReads(
        dialect,
        results=[_customers(case, dialect, owners), _customer_identities(case, owners)],
    )

    assert_case_read(case, reads)

    assert len(reads.calls) == 2


@pytest.mark.parametrize("dialect", ["postgres", "mariadb"])
def test_a_filtered_value_object_read_still_materializes_in_one_round_trip(
    corpus_case: CaseLoader, dialect: str
) -> None:
    case = corpus_case(_FILTERED_VALUE_OBJECT_GRAPH)
    reads = ScriptedReads(
        dialect, results=[_customers(case, dialect, [1, 2]), _customer_identities(case, [1, 2])]
    )

    assert_case_read(case, reads)

    assert reads.calls[0][1] == tuple(case.statement_binds(0, dialect))


def test_a_stored_document_the_case_did_not_author_is_refused(corpus_case: CaseLoader) -> None:
    case = corpus_case(_FILTERED_VALUE_OBJECT_GRAPH)
    owners = _customers(case, "postgres", [1, 2])
    owners[0]["address"] = dict(owners[0]["address"]) | {"city": "WRONG"}
    reads = ScriptedReads(results=[owners, _customer_identities(case, [1, 2])])

    with pytest.raises(CaseFailure, match="materialized graph != then.graph"):
        assert_case_read(case, reads)


def test_element_order_inside_a_many_member_is_semantic(corpus_case: CaseLoader) -> None:
    case = corpus_case(_FILTERED_VALUE_OBJECT_GRAPH)
    owners = _customers(case, "postgres", [1, 2])
    address = dict(owners[0]["address"])
    address["phones"] = list(reversed(address["phones"]))
    owners[0]["address"] = address
    reads = ScriptedReads(results=[owners, _customer_identities(case, [1, 2])])

    with pytest.raises(CaseFailure, match="materialized graph != then.graph"):
        assert_case_read(case, reads)


def test_the_identity_oracle_pins_the_matched_row_set(corpus_case: CaseLoader) -> None:
    case = corpus_case(_FILTERED_VALUE_OBJECT_GRAPH)
    reads = ScriptedReads(
        results=[_customers(case, "postgres", [1, 2]), _customer_identities(case, [1])]
    )

    with pytest.raises(CaseFailure, match="referenceSql rows != golden rows"):
        assert_case_read(case, reads)


def test_an_instance_form_node_carries_only_its_own_branch(corpus_case: CaseLoader) -> None:
    case = corpus_case(_ABSTRACT_ROOT_GRAPH)
    reads = ScriptedReads(results=[_PAYMENTS])

    assert_case_read(case, reads)


def test_a_node_authored_with_a_sibling_branch_column_is_refused(
    damaged_case: CaseLoader,
) -> None:
    case = damaged_case(_ABSTRACT_ROOT_GRAPH)
    case.then["graph"]["Payment"][0]["tendered"] = None
    reads = ScriptedReads(results=[_PAYMENTS])

    with pytest.raises(CaseFailure, match="materialized graph != then.graph"):
        assert_case_read(case, reads)


# --- rows a graph is built from -----------------------------------------------

_TEMPORAL_ABSTRACT_READ = "m-inheritance-092-tph-temporal-abstract-read.yaml"

_JANUARY_INSTANT = "2024-01-01T00:00:00+00:00"
_JUNE_INSTANT = "2024-06-01T00:00:00+00:00"

# The shared `instrument` table carries the raw tag column `kind` alongside the
# concrete superset and the two rectangles' interval columns.
_INSTRUMENT_MILESTONES: list[dict[str, Any]] = [
    {
        "id": 1,
        "kind": "bond",
        "price": Decimal("100.00"),
        "coupon": Decimal("5.00"),
        "ticker": None,
        "from_z": _JANUARY_INSTANT,
        "thru_z": _JUNE_INSTANT,
        "in_z": _JANUARY_INSTANT,
        "out_z": "infinity",
    },
    {
        "id": 1,
        "kind": "bond",
        "price": Decimal("110.00"),
        "coupon": Decimal("5.00"),
        "ticker": None,
        "from_z": _JUNE_INSTANT,
        "thru_z": "infinity",
        "in_z": _JANUARY_INSTANT,
        "out_z": "infinity",
    },
]


def _as_a_milestone_set_read(case: Case) -> Case:
    """A shipped abstract-target temporal read restated as the milestone set it scans.

    The corpus authors no ``then.graphs`` over an inheritance family, so the pairing
    is fabricated in a private copy: the same family, the same golden projection —
    identity, raw tag, concrete superset, interval columns — with Valid Time scanned
    rather than pinned and the result stated as one edge-pinned graph per milestone.
    """
    case.raw["when"]["objectQuery"]["temporal"] = {
        "transaction-time": {"asOf": "latest"},
        "valid-time": {"history": {}},
    }
    del case.raw["then"]["rows"]
    case.raw["then"]["graphs"] = [
        {
            "pin": {"valid-time": _JANUARY_INSTANT},
            "graph": {
                "Instrument": [
                    {
                        "id": 1,
                        "price": Decimal("100.00"),
                        "coupon": Decimal("5.00"),
                        "familyVariant": "Bond",
                        "validStart": _JANUARY_INSTANT,
                        "validEnd": _JUNE_INSTANT,
                        "txStart": _JANUARY_INSTANT,
                        "txEnd": "infinity",
                    }
                ]
            },
        },
        {
            "pin": {"valid-time": _JUNE_INSTANT},
            "graph": {
                "Instrument": [
                    {
                        "id": 1,
                        "price": Decimal("110.00"),
                        "coupon": Decimal("5.00"),
                        "familyVariant": "Bond",
                        "validStart": _JUNE_INSTANT,
                        "validEnd": "infinity",
                        "txStart": _JANUARY_INSTANT,
                        "txEnd": "infinity",
                    }
                ]
            },
        },
    ]
    return case


def test_an_abstract_target_milestone_set_publishes_familyVariant_not_the_raw_tag(
    damaged_case: CaseLoader,
) -> None:
    """A milestone is a whole object at an instant, so its roots are materialized.

    The golden projects the raw `kind` column and the whole concrete superset; each
    declared graph states the concrete instance the milestone stood at — its own
    branch's members and the `familyVariant` derived from the tag map, with no
    sibling branch's null padding and no storage column of any kind.
    """
    case = _as_a_milestone_set_read(damaged_case(_TEMPORAL_ABSTRACT_READ))
    reads = ScriptedReads(results=[_INSTRUMENT_MILESTONES, _INSTRUMENT_MILESTONES])

    assert_case_read(case, reads)

    assert len(reads.calls) == 2


def test_a_hop_child_row_still_carrying_the_shared_tag_column_is_refused(
    corpus_case: CaseLoader,
) -> None:
    """A row about to become a node is refused while it still names its branch physically.

    `pets[Dog]` narrows to one concrete, so its level reads the shared table under a
    tag equality and projects no tag column of its own. A level that projected one
    anyway would carry the discriminator into the graph as if it were a member, which
    is refused at the last step of the materialization sequence rather than compared.
    """
    case = corpus_case(_NARROWED_PETS)
    tagged = [row | {"kind": "dog"} for row in _DOGS]
    reads = ScriptedReads(results=[_PEOPLE, tagged])

    with pytest.raises(CaseFailure, match="still carries its branch carrier 'kind' and no derived"):
        assert_case_read(case, reads)


def test_a_graph_assembled_from_roots_that_skipped_the_seam_is_refused(
    corpus_case: CaseLoader, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The roots a graph is assembled from are the ones a read PUBLISHED.

    Standing in for a future path that assembles the materialization sequence
    itself: the seam is replaced by a pass-through, and the assembly refuses its
    rows rather than grading storage against the logical graph the case authored.
    """
    case = corpus_case(_ORDERED_ITEMS)
    monkeypatch.setattr(
        oracle_materialize,
        "materialize_read",
        lambda _read, rows: [dict(row) for row in rows],
    )
    reads = ScriptedReads(results=[_ORDER_ONE, _ORDER_ONE_ITEMS, _ORDER_ONE])

    with pytest.raises(CaseFailure, match="did not come through the materialization seam"):
        assert_case_read(case, reads)


def test_a_published_row_cannot_be_minted_by_holding_the_class() -> None:
    """Provenance is the derivation, so the class alone does not confer it.

    Standing in for a future path that would rather stamp a row than run the
    sequence: the constructor demands a token only the materialization entry
    points hold, so a consumer that reached the class mints nothing.
    """
    with pytest.raises(CaseFailure, match="minted by this module's materialization entry"):
        oracle_materialize.PublishedRow({"id": 1}, object())


def test_the_owner_node_decode_refuses_a_row_that_skipped_the_seam(
    corpus_case: CaseLoader,
) -> None:
    """A step after the sequence projects a published row; it does not publish one.

    A raw non-polymorphic row carries no branch carrier, so the carried-branch
    refusal beside this one has nothing to catch it by; what refuses it is that it
    never came through the seam at all, and so may still hold the storage document
    the fan-out would have taken out.
    """
    case = corpus_case(_ABSTRACT_ROOT_GRAPH)
    entity = case.model.entity(case.object_query["target"])
    row = cast(oracle_materialize.PublishedRow, {"id": 1, "kind": "dog"})

    with pytest.raises(CaseFailure, match="the owner-node decode projects a row"):
        oracle_materialize.materialize_variant_owner_node(case, entity, row)


def test_per_variant_narrowing_refuses_rows_that_skipped_the_seam(
    corpus_case: CaseLoader, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The narrowing an instance-form node shape needs also projects what was published."""
    case = corpus_case(_ABSTRACT_ROOT_GRAPH)
    monkeypatch.setattr(
        oracle_materialize,
        "materialize_read",
        lambda _read, rows, **_widened: [dict(row) for row in rows],
    )
    reads = ScriptedReads(results=[_PAYMENTS, _PAYMENTS])

    with pytest.raises(CaseFailure, match="per-variant column narrowing projects a row"):
        assert_case_read(case, reads)
