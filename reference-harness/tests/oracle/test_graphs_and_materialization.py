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
from collections import Counter
from collections.abc import Callable
from dataclasses import replace
from decimal import Decimal
from typing import Any, cast

import pytest

from reference_harness.case import Case, Model, _load_yaml
from reference_harness.case_assertions import CaseFailure
from reference_harness.document_codec import ParsedJsonString
from reference_harness.object_query_oracle import assert_case_read, retained
from reference_harness.object_query_oracle import materialize as oracle_materialize
from reference_harness.temporality import derive_temporal_structure
from reference_harness.unit_work_scenario.observations import ScenarioRowObservations

from .conftest import ScriptedReads

CaseLoader = Callable[[str], Case]

_ORDERED_ITEMS = "m-snapshot-read-008-declared-child-ordering.yaml"
_EMPTY_ROOT = "m-snapshot-read-004-empty-root.yaml"
_NARROWED_PETS = "m-inheritance-065-tph-deepfetch-narrowed-pets-dog.yaml"
_BROAD_AND_NARROWED_PETS = "m-inheritance-068-tph-deepfetch-broad-and-redundant-narrow.yaml"
_PARTIAL_TPH_INCLUDE = "m-inheritance-148-partial-tph-broad-singleton-include-unknown-tag.yaml"
_PARTIAL_TPH_NARROWED_INCLUDE = "m-inheritance-149-partial-tph-narrowed-singleton-include.yaml"
_GUARDED_BRANCHES = "m-inheritance-078-tph-deepfetch-guarded-branches-diverge.yaml"
_TEMPORAL_DEEP_FETCH = "m-navigate-012-deepfetch-temporal-both-latest.yaml"
_HISTORY_GRAPHS = "m-snapshot-read-013-history-edge-pinned-graphs.yaml"
_ABSTRACT_ROOT_GRAPH = "m-inheritance-106-tph-abstract-root-read-graph.yaml"
_VALUE_OBJECT_GRAPH = "m-value-object-023-graph-nested-materialization.yaml"
_FILTERED_VALUE_OBJECT_GRAPH = "m-value-object-024-graph-filtered-materialization.yaml"
_COLLECTION_COLUMNS = "m-storage-layout-035-scalar-collection-read-layout-twin-columns.yaml"
_COLLECTION_DOCUMENT = "m-storage-layout-036-scalar-collection-read-layout-twin-document.yaml"
_COLLECTIONS = (
    "flags",
    "smalls",
    "counts",
    "ratios",
    "scores",
    "amounts",
    "tags",
    "blobs",
    "days",
    "clocks",
    "instants",
    "tokens",
)

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

_ORDER_ONE_TAGS: list[dict[str, Any]] = [
    {"id": 3, "order_id": 1, "label": "fragile", "priority": 5},
    {"id": 2, "order_id": 1, "label": "gift", "priority": 2},
    {"id": 1, "order_id": 1, "label": "urgent", "priority": 2},
]

_ORDERED_RESULTS = [_ORDER_ONE, _ORDER_ONE_ITEMS, _ORDER_ONE_ITEMS, _ORDER_ONE_TAGS, _ORDER_ONE]

_PEOPLE: list[dict[str, Any]] = [
    {"id": 10, "name": "Alice"},
    {"id": 11, "name": "Bob"},
    {"id": 12, "name": "Carol"},
]

# The narrowed `pets[Dog]` level reads one concrete, so its shared-table read
# projects no tag column and the hop itself names the variant.
_DOGS: list[dict[str, Any]] = [
    {"id": 1, "name": "Rex", "owner_id": 10, "license_id": "L-100", "bark_volume": 7},
    {"id": 2, "name": "Fido", "owner_id": 11, "license_id": "L-101", "bark_volume": 3},
]

# A polymorphic hop projects the raw `kind` column instead; `_type` is
# materialized from the tag metadata map.
_KEEPERS: list[dict[str, Any]] = [
    {"id": 10, "name": "Mowgli"},
    {"id": 11, "name": "Bagheera"},
    {"id": 12, "name": "Kaa"},
]
_KEPT_BEASTS: list[dict[str, Any]] = [
    {"id": 1, "kind": "wolf", "name": "Akela", "keeper_id": 10, "howl": "aroo"},
    {"id": 2, "kind": "bear", "name": "Baloo", "keeper_id": 11, "howl": None},
    {"id": 3, "kind": "wolf", "name": "Raksha", "keeper_id": 10, "howl": "yip"},
]
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
    reads = ScriptedReads(results=_ORDERED_RESULTS)

    assert_case_read(case, reads)

    assert reads.statements[:4] == case.golden_statements("postgres")


def test_the_child_level_is_keyed_by_the_gathered_parent_keys(corpus_case: CaseLoader) -> None:
    case = corpus_case(_ORDERED_ITEMS)
    reads = ScriptedReads(results=_ORDERED_RESULTS)

    assert_case_read(case, reads)

    assert reads.calls[1][1] == ([1],)


def test_a_child_level_keyed_by_anything_else_is_refused(damaged_case: CaseLoader) -> None:
    case = damaged_case(_ORDERED_ITEMS)
    case.then["statements"][1]["binds"] = {"postgres": [[2]], "mariadb": [2]}
    reads = ScriptedReads(results=_ORDERED_RESULTS)

    with pytest.raises(CaseFailure, match="key-set binds"):
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
    reads = ScriptedReads(
        results=[_ORDER_ONE, ascending, _ORDER_ONE_ITEMS, _ORDER_ONE_TAGS, _ORDER_ONE]
    )

    with pytest.raises(CaseFailure, match="not in declared orderBy order"):
        assert_case_read(case, reads)


def test_an_orderby_key_the_child_did_not_project_is_refused(corpus_case: CaseLoader) -> None:
    case = corpus_case(_ORDERED_ITEMS)
    unprojected = [
        {key: value for key, value in row.items() if key != "id"} for row in _ORDER_ONE_ITEMS
    ]
    reads = ScriptedReads(
        results=[_ORDER_ONE, unprojected, _ORDER_ONE_ITEMS, _ORDER_ONE_TAGS, _ORDER_ONE]
    )

    with pytest.raises(CaseFailure, match="orderBy column"):
        assert_case_read(case, reads)


def test_a_narrowed_hop_attaches_under_its_derived_view_key(corpus_case: CaseLoader) -> None:
    case = corpus_case(_NARROWED_PETS)
    reads = ScriptedReads(results=[_PEOPLE, _DOGS, _PEOPLE])

    assert_case_read(case, reads)

    # The single-concrete narrow filters the shared table by the effective set's
    # tag value, appended after the gathered-owner array.
    assert reads.calls[1][1] == ([10, 11, 12], "dog")


def test_a_broad_and_a_redundantly_narrowed_hop_are_two_levels(corpus_case: CaseLoader) -> None:
    case = corpus_case(_BROAD_AND_NARROWED_PETS)
    reads = ScriptedReads(results=[_PEOPLE, _PETS, _PETS, _PEOPLE])

    assert_case_read(case, reads)

    assert len(reads.calls) == 4
    assert reads.calls[1][1] == reads.calls[2][1] == ([10, 11, 12], "cat", "dog")


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
    "t0.bark_volume from animal t0 where t0.owner_id = any(cast(? as bigint[])) and "
    "t0.kind in (?, ?)"
)


_PEOPLE_LEVEL_SQL = "select t0.id, t0.name from person t0 where t0.id = any(cast(? as bigint[]))"


def _pet_level_rows(*ids: int) -> list[dict[str, Any]]:
    """The `pets` level rows for *ids*, projected at Pet's own superset."""
    return [
        {key: value for key, value in _ANIMAL_BY_ID[identifier].items() if key != "tusk_length"}
        for identifier in ids
    ]


_OWN_MEMBERS: dict[str, dict[str, str]] = {
    "Dog": {"licenseId": "license_id", "barkVolume": "bark_volume"},
    "Cat": {"licenseId": "license_id", "indoor": "indoor"},
    "WildBoar": {"tuskLength": "tusk_length"},
}


def _animal_node(identifier: int, variant: str, **views: Any) -> dict[str, Any]:
    """The per-variant node one Animal publishes, at whichever level reached it."""
    row = _ANIMAL_BY_ID[identifier]
    return {
        "id": row["id"],
        "name": row["name"],
        "ownerId": row["owner_id"],
        **{member: row[column] for member, column in _OWN_MEMBERS[variant].items()},
        "_type": f"parallax.compatibility.{variant}",
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
            "sql": {"postgres": _PEOPLE_LEVEL_SQL},
            "binds": [[12]],
        },
        {
            "sql": {"postgres": _PETS_LEVEL_SQL},
            "binds": [[12], "cat", "dog"],
        },
        {
            "sql": {"postgres": _PEOPLE_LEVEL_SQL},
            "binds": [[10, 11]],
        },
        {
            "sql": {"postgres": _PETS_LEVEL_SQL},
            "binds": [[10, 11], "cat", "dog"],
        },
    ]
    case.then["databaseCalls"] = 5
    case.then["graph"] = {
        "Animal": [
            _animal_node(
                1,
                "Dog",
                owner={
                    "id": 10,
                    "name": "Alice",
                    "pets": [_animal_node(1, "Dog"), _animal_node(3, "Cat")],
                },
            ),
            _animal_node(
                2, "Dog", owner={"id": 11, "name": "Bob", "pets": [_animal_node(2, "Dog")]}
            ),
            _animal_node(3, "Cat"),
            _animal_node(
                4,
                "WildBoar",
                owner={"id": 12, "name": "Carol", "pets": [_animal_node(5, "Cat")]},
            ),
            _animal_node(5, "Cat"),
        ]
    }
    return case


def test_two_parent_branches_reaching_one_relationship_are_two_levels(
    damaged_case: CaseLoader,
) -> None:
    """One relationship reached from two DIFFERENT parents is two hops.

    Each gathers its keys from its own branch's rows, so the two can share neither
    a statement nor a bucket of fetched children (`m-read-planning` branch
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
        ([12],),
        ([12], "cat", "dog"),
        ([10, 11],),
        ([10, 11], "cat", "dog"),
    ]


@pytest.mark.parametrize(
    "padded",
    [
        pytest.param(lambda graph: graph["Animal"][0], id="root"),
        pytest.param(lambda graph: graph["Animal"][0]["owner"]["pets"][0], id="child"),
    ],
)
def test_a_node_padded_with_a_sibling_member_fails(
    padded: Callable[[dict[str, Any]], dict[str, Any]], damaged_case: CaseLoader
) -> None:
    """A `Dog` has no `indoor` key to be null, whichever level reached it."""
    case = _both_guarded_branches_continue(damaged_case(_GUARDED_BRANCHES))
    padded(case.then["graph"])["indoor"] = None
    reads = ScriptedReads(
        results=[
            _ROOT_ANIMALS,
            [{"id": 12, "name": "Carol"}],
            _pet_level_rows(5),
            [{"id": 10, "name": "Alice"}, {"id": 11, "name": "Bob"}],
            _pet_level_rows(1, 2, 3),
        ]
    )

    with pytest.raises(CaseFailure, match="assembled graph != then.graph"):
        assert_case_read(case, reads)


def test_an_unknown_child_tag_makes_the_root_reaching_it_unavailable(
    corpus_case: CaseLoader,
) -> None:
    # A root that reaches an unrepresentable child is unavailable itself and
    # carries the child's diagnosis; its siblings, including a loaded-empty one,
    # publish as ordinary.
    case = corpus_case(_PARTIAL_TPH_INCLUDE)
    reads = ScriptedReads(results=[_KEEPERS, _KEPT_BEASTS, _KEEPERS])

    assert_case_read(case, reads)

    assert reads.calls[1][1] == ([10, 11, 12],)


def test_equal_unknown_tag_diagnoses_collapse_within_a_root(corpus_case: CaseLoader) -> None:
    case = corpus_case(_PARTIAL_TPH_INCLUDE)
    second_bear = {"id": 4, "kind": "bear", "name": "Bhalu", "keeper_id": 11, "howl": None}
    reads = ScriptedReads(results=[_KEEPERS, [*_KEPT_BEASTS, second_bear], _KEEPERS])

    assert_case_read(case, reads)


def test_unknown_tag_diagnoses_with_different_stored_tags_stay_distinct(
    damaged_case: CaseLoader,
) -> None:
    case = damaged_case(_PARTIAL_TPH_INCLUDE)
    (entry,) = case.then["storedDataIssues"]
    entry["issues"] = [*entry["issues"], *entry["issues"]]
    lion = {"id": 4, "kind": "lion", "name": "Shere", "keeper_id": 11, "howl": None}
    reads = ScriptedReads(results=[_KEEPERS, [*_KEPT_BEASTS, lion], _KEEPERS])

    assert_case_read(case, reads)


def test_an_unknown_child_tag_is_never_dropped_from_a_published_root(
    corpus_case: CaseLoader,
) -> None:
    case = corpus_case(_BROAD_AND_NARROWED_PETS)
    stray = [dict(_PETS[0]) | {"kind": "sturgeon"}, *_PETS[1:]]
    reads = ScriptedReads(results=[_PEOPLE, stray, _PETS, _PEOPLE])

    with pytest.raises(CaseFailure, match="assembled graph != then.graph"):
        assert_case_read(case, reads)


def test_a_broad_singleton_hop_keeps_the_unguarded_root_target(
    damaged_case: CaseLoader,
) -> None:
    # The reader composes one Beast leaf, yet the broad hop is not retargeted to
    # it: a level authoring Wolf's tag guard binds more than the broad read does.
    case = damaged_case(_PARTIAL_TPH_INCLUDE)
    child = case.then["statements"][1]
    child["sql"]["postgres"] = child["sql"]["postgres"].replace(
        "= any(cast(? as bigint[]))", "= any(cast(? as bigint[])) and t0.kind = ?"
    )
    child["binds"]["postgres"] = [[10, 11, 12], "wolf"]

    with pytest.raises(CaseFailure, match=r"level 1 \(beasts\) as-of suffix \['wolf'\]"):
        assert_case_read(case, ScriptedReads(results=[_KEEPERS, _KEPT_BEASTS, _KEEPERS]))


@pytest.mark.parametrize("key_array", ["?", "cast(? as int[])"], ids=["uncast", "narrower-type"])
def test_a_postgres_level_casts_its_keys_to_the_key_type(
    damaged_case: CaseLoader, key_array: str
) -> None:
    case = damaged_case(_PARTIAL_TPH_INCLUDE)
    child = case.then["statements"][1]
    child["sql"]["postgres"] = child["sql"]["postgres"].replace(
        "= any(cast(? as bigint[]))", f"= any({key_array})"
    )

    with pytest.raises(CaseFailure, match=r"level 1 \(beasts\) does not compare its gathered keys"):
        assert_case_read(case, ScriptedReads(results=[_KEEPERS, _KEPT_BEASTS, _KEEPERS]))


@pytest.mark.parametrize(
    "membership",
    [
        "t0.keeper_id in (?, ?) and not ? is null",
        "t0.keeper_id in (?, ?, 12) and not ? is null",
    ],
    ids=["short-list", "literal-member"],
)
def test_a_mariadb_level_spending_a_key_outside_its_membership_is_refused(
    damaged_case: CaseLoader, membership: str
) -> None:
    case = damaged_case(_PARTIAL_TPH_INCLUDE)
    child = case.then["statements"][1]
    child["sql"]["mariadb"] = child["sql"]["mariadb"].replace(
        "t0.keeper_id in (?, ?, ?)", membership
    )

    with pytest.raises(CaseFailure, match=r"level 1 \(beasts\) does not compare its 3 gathered"):
        assert_case_read(
            case, ScriptedReads(dialect="mariadb", results=[_KEEPERS, _KEPT_BEASTS, _KEEPERS])
        )


def test_a_mariadb_level_keyed_by_another_column_is_refused(damaged_case: CaseLoader) -> None:
    case = damaged_case(_PARTIAL_TPH_INCLUDE)
    child = case.then["statements"][1]
    child["sql"]["mariadb"] = child["sql"]["mariadb"].replace(
        "t0.keeper_id in (?, ?, ?)", "t0.id in (?, ?, ?)"
    )

    with pytest.raises(CaseFailure, match=r"level 1 \(beasts\).*not keyed by 'keeper_id'"):
        assert_case_read(
            case, ScriptedReads(dialect="mariadb", results=[_KEEPERS, _KEPT_BEASTS, _KEEPERS])
        )


def test_a_narrowed_singleton_hop_keeps_its_guard_over_the_whole_composed_family(
    corpus_case: CaseLoader,
) -> None:
    case = corpus_case(_PARTIAL_TPH_NARROWED_INCLUDE)
    wolves = [
        {key: value for key, value in row.items() if key != "kind"}
        for row in _KEPT_BEASTS
        if row["kind"] == "wolf"
    ]
    reads = ScriptedReads(results=[_KEEPERS, wolves, _KEEPERS])

    assert_case_read(case, reads)

    assert reads.calls[1][1] == ([10, 11, 12], "wolf")


def test_a_hop_that_drops_a_tag_bind_is_refused(damaged_case: CaseLoader) -> None:
    case = damaged_case(_BROAD_AND_NARROWED_PETS)
    case.then["statements"][1]["binds"] = [[10, 11, 12], "cat"]
    reads = ScriptedReads(results=[_PEOPLE, _PETS, _PETS, _PEOPLE])

    with pytest.raises(CaseFailure, match="tag binds"):
        assert_case_read(case, reads)


def test_the_root_as_of_pin_propagates_to_a_temporal_child_level(
    corpus_case: CaseLoader,
) -> None:
    case = corpus_case(_TEMPORAL_DEEP_FETCH)
    reads = ScriptedReads(results=[_POLICIES, _COVERAGES])

    assert_case_read(case, reads)

    assert reads.calls[1][1] == ([1, 2], _FOREVER, _FOREVER)


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
    reads = ScriptedReads(
        results=[_ORDER_ONE, missing_child, _ORDER_ONE_ITEMS, _ORDER_ONE_TAGS, _ORDER_ONE]
    )

    with pytest.raises(CaseFailure, match="assembled graph != then.graph"):
        assert_case_read(case, reads)


def test_the_deep_fetch_reference_oracle_grades_the_root_rows(corpus_case: CaseLoader) -> None:
    case = corpus_case(_ORDERED_ITEMS)
    reads = ScriptedReads(
        results=[_ORDER_ONE, _ORDER_ONE_ITEMS, _ORDER_ONE_ITEMS, _ORDER_ONE_TAGS, []]
    )

    with pytest.raises(CaseFailure, match="referenceSql root rows"):
        assert_case_read(case, reads)


# --- milestone sets -----------------------------------------------------------


def test_a_milestone_set_partitions_its_rows_into_milestone_pinned_graphs(
    corpus_case: CaseLoader,
) -> None:
    case = corpus_case(_HISTORY_GRAPHS)
    reads = ScriptedReads(results=[_MILESTONES, _MILESTONES])

    assert_case_read(case, reads)

    # One Database Call returns the whole milestone set; the second call is the
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


# --- scalar collections in a flat assertion -----------------------------------


def _as_flat_assertion(case: Case, rows: list[dict[str, Any]]) -> Case:
    """*case* asserting *rows* through `then.rows` instead of `then.graph`."""
    del case.then["graph"]
    case.then["rows"] = rows
    return case


def test_a_flat_read_publishes_a_columns_collection_as_its_elements(
    damaged_case: CaseLoader,
) -> None:
    """MariaDB hands a structured Column back as JSON text, and the published row
    carries the decoded elements under either driver, so `then.rows` and the
    independent oracle both compare logical collections."""
    expected = {"id": 1, "tags": ["b", "a", "b"], "blobs": ["0aff", ""]}
    case = _as_flat_assertion(damaged_case(_COLLECTION_COLUMNS), [expected])
    stored = {"id": 1, "tags": json.dumps(["b", "a", "b"]), "blobs": ["0aff", ""]}
    reads = ScriptedReads("mariadb", results=[[stored]])

    assert_case_read(case, reads)

    (published,) = oracle_materialize.materialize_read(case, [stored])
    assert published["tags"] == ["b", "a", "b"]


def test_a_flat_read_publishes_an_omitted_document_collection_as_empty(
    damaged_case: CaseLoader,
) -> None:
    expected = {"id": 2, **{name: [] for name in _COLLECTIONS}} | {"tags": ["z"]}
    case = _as_flat_assertion(damaged_case(_COLLECTION_DOCUMENT), [expected])
    reads = ScriptedReads(results=[[{"id": 2, "payload": {"tags": ["z"], "flags": None}}]])

    assert_case_read(case, reads)


@pytest.mark.parametrize(
    ("name", "row", "judged"),
    [
        (_COLLECTION_COLUMNS, {"id": 1, "tags": '"b"'}, "b"),
        (_COLLECTION_COLUMNS, {"id": 1, "tags": ParsedJsonString('["b"]')}, '["b"]'),
        (_COLLECTION_COLUMNS, {"id": 1, "tags": ParsedJsonString("b, a")}, "b, a"),
        (_COLLECTION_DOCUMENT, {"id": 1, "payload": {"tags": ["b", None]}}, ["b", None]),
    ],
    ids=["columns-text", "columns-parsed-array-text", "columns-parsed-text", "document"],
)
def test_a_malformed_collection_leaves_its_published_row_unhydratable(
    corpus_case: CaseLoader, name: str, row: dict[str, Any], judged: Any
) -> None:
    case = corpus_case(name)

    (published,) = oracle_materialize.materialize_read(case, [row])

    assert published["tags"] == oracle_materialize.UnavailableLeaf(judged)
    assert oracle_materialize.is_unavailable(published)


_TPCS_FLAT_COLLECTIONS = (
    "m-inheritance-145-scalar-collection-tpcs-row-read-layout-twin-columns.yaml"
)


def _presence(*ordinals_and_values: tuple[int, bool]) -> dict[str, bool]:
    return {
        f"__parallax_document_presence_{ordinal}": value for ordinal, value in ordinals_and_values
    }


def test_a_flat_tpcs_read_projects_every_branch_collection(corpus_case: CaseLoader) -> None:
    """Each collection's presence cell is proven over the branches owning its
    Column, a typed `null` placeholder arm included, so none reaches the row."""
    reads = ScriptedReads(
        results=[
            [
                {"id": 1, "tags": ["t"], "bits": [8, 8], "blades": None}
                | _presence((1, True), (3, True), (5, False))
                | {"family_variant": "TagDrill"},
                {"id": 2, "tags": [], "bits": None, "blades": ["rip"]}
                | _presence((1, True), (3, False), (5, True))
                | {"family_variant": "TagSaw"},
            ]
        ]
    )

    assert_case_read(corpus_case(_TPCS_FLAT_COLLECTIONS), reads)


def test_a_flat_tpcs_read_dropping_its_collections_is_refused(
    damaged_case: CaseLoader,
) -> None:
    case = damaged_case(_TPCS_FLAT_COLLECTIONS)
    for dialect in ("postgres", "mariadb"):
        case.then["statements"][0]["sql"][dialect] = (
            "select u.id, u.family_variant from (select t0.id, 'TagDrill' family_variant "
            "from tag_drill t0 union all select t0.id, 'TagSaw' family_variant from tag_saw t0) "
            "u order by u.id asc"
        )
    case.then["rows"] = [{"id": 1, "_type": "parallax.compatibility.TagDrill"}]
    reads = ScriptedReads(results=[[{"id": 1, "family_variant": "TagDrill"}]])

    with pytest.raises(CaseFailure, match="tags"):
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
def test_a_filtered_value_object_read_still_materializes_in_one_database_call(
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
    rather than pinned and the result stated as one graph per milestone.
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
                        "_type": "parallax.compatibility.Bond",
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
                        "_type": "parallax.compatibility.Bond",
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


def test_an_abstract_target_milestone_set_publishes_type_not_the_raw_tag(
    damaged_case: CaseLoader,
) -> None:
    """A milestone is a whole object at an instant, so its roots are materialized.

    The golden projects the raw `kind` column and the whole concrete superset; each
    declared graph states the concrete instance the milestone stood at — its own
    branch's members and the `_type` derived from the tag map, with no
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
    anyway would carry the discriminator into the graph as if it were a member, and
    no authored node states that key.
    """
    case = corpus_case(_NARROWED_PETS)
    tagged = [row | {"kind": "dog"} for row in _DOGS]
    reads = ScriptedReads(results=[_PEOPLE, tagged])

    with pytest.raises(CaseFailure, match="assembled graph != then.graph"):
        assert_case_read(case, reads)


def test_a_narrowed_view_golden_omitting_its_variant_fails(damaged_case: CaseLoader) -> None:
    """A single-concrete view's node carries the tag its level never projected."""
    case = damaged_case(_NARROWED_PETS)
    del case.then["graph"]["Person"][0]["pets[Dog]"][0]["_type"]

    with pytest.raises(CaseFailure, match="assembled graph != then.graph"):
        assert_case_read(case, ScriptedReads(results=[_PEOPLE, _DOGS]))


@pytest.mark.parametrize("stated", ["Dog", "parallax.compatibility.Cat"])
def test_a_narrowed_view_golden_naming_the_wrong_type_fails(
    damaged_case: CaseLoader, stated: str
) -> None:
    case = damaged_case(_NARROWED_PETS)
    case.then["graph"]["Person"][0]["pets[Dog]"][0]["_type"] = stated

    with pytest.raises(CaseFailure, match="assembled graph != then.graph"):
        assert_case_read(case, ScriptedReads(results=[_PEOPLE, _DOGS]))


def test_a_golden_stating_a_type_on_a_node_outside_a_family_fails(
    damaged_case: CaseLoader,
) -> None:
    case = damaged_case(_NARROWED_PETS)
    case.then["graph"]["Person"][0]["_type"] = "parallax.compatibility.Person"

    with pytest.raises(CaseFailure, match="assembled graph != then.graph"):
        assert_case_read(case, ScriptedReads(results=[_PEOPLE, _DOGS]))


_VARIANT_OVERLAP = "m-inheritance-164-value-object-storage-column-family-graph.yaml"
_PROFILE_HOP = "m-inheritance-118-value-object-relationship-name-overlap-graph.yaml"
_SCENARIO_WITH_INCLUDES = "m-snapshot-read-026-multi-hop-access-drops-null-branches.yaml"
_PROFILE = {"label": "variant-profile"}
_STORED_PROFILE = json.dumps(_PROFILE)
_NOTE_NODE = {"id": 2, "profile": _PROFILE, "_type": "compatibility.overlap.VariantNote"}


def _concrete_note_read(case: Case) -> Case:
    """*case*, the abstract overlap read, retargeted at its one concrete."""
    case.when["objectQuery"]["target"] = "compatibility.overlap.VariantNote"
    case.then["statements"] = [
        {
            "sql": {
                "postgres": 'select t0.id, not t0."variantProfile" is null, t0."variantProfile" '
                "from variant_record t0 where t0.kind = ?"
            },
            "binds": ["note"],
        }
    ]
    del case.then["referenceSql"]
    case.then["graph"] = {"VariantNote": [_NOTE_NODE]}
    return case


def _with_note_hop(
    case: Case,
    target: str,
    *,
    narrow_to: list[str] | None = None,
    tag_column: bool = False,
    storage: Callable[[dict[str, Any]], None] = lambda _document: None,
) -> Case:
    """*case*, the ProfileOwner read, including a hop *target* over the overlap family."""
    segment: dict[str, Any] = {"rel": "compatibility.overlap.ProfileOwner.note"}
    if narrow_to is not None:
        segment["narrowTo"] = narrow_to

    def declare_hop(document: dict[str, Any]) -> None:
        _entity(document, "ProfileOwner")["relationships"].append(
            {
                "name": "note",
                "cardinality": "many-to-one",
                "join": {
                    "source": "targetId",
                    "target": {"entity": target, "attribute": "id"},
                },
            }
        )
        storage(document)

    case.when["objectQuery"]["includes"] = [{"segments": [segment]}]
    tag, tag_filter, tag_binds = (
        ("t0.kind, ", "", []) if tag_column else ("", " and t0.kind = ?", ["note"])
    )
    level = {
        "sql": {
            "postgres": f'select t0.id, {tag}not t0."variantProfile" is null, t0."variantProfile" '
            f"from variant_record t0 where t0.id = any(cast(? as bigint[])){tag_filter}"
        },
        "binds": {"postgres": [[2], *tag_binds]},
    }
    case.then["statements"] = [case.then["statements"][0], level]
    view = "note" if narrow_to is None else "note[VariantNote]"
    case.then["graph"] = {
        "ProfileOwner": [
            {
                "id": 1,
                "targetId": 2,
                "profile": {"label": "owner-profile"},
                view: _NOTE_NODE,
            }
        ]
    }
    return _with_descriptor_change(case, declare_hop)


_OWNER_ROWS = [{"id": 1, "target_id": 10, "details": json.dumps({"label": "owner-profile"})}]


@pytest.mark.parametrize(
    ("target", "narrow_to", "tag_column"),
    [
        pytest.param("compatibility.overlap.VariantNote", None, False, id="concrete"),
        pytest.param("compatibility.overlap.VariantRecord", ["VariantNote"], False, id="narrowed"),
        pytest.param("compatibility.overlap.VariantRecord", None, True, id="polymorphic"),
    ],
)
def test_a_level_keeps_its_document_beside_its_variant(
    target: str, narrow_to: list[str] | None, tag_column: bool, damaged_case: CaseLoader
) -> None:
    case = _with_note_hop(
        damaged_case(_PROFILE_HOP), target, narrow_to=narrow_to, tag_column=tag_column
    )
    owners = [_OWNER_ROWS[0] | {"target_id": 2}]
    level = {"id": 2, "variantProfile": _STORED_PROFILE} | ({"kind": "note"} if tag_column else {})

    assert_case_read(case, ScriptedReads(results=[owners, [level], owners]))


def _table_per_concrete_subtype(document: dict[str, Any]) -> None:
    root = _entity(document, "VariantRecord")
    del root["table"]
    root["inheritance"] = {"role": "root", "strategy": "table-per-concrete-subtype"}
    for name, table in (("VariantNote", "variant_note"), ("VariantMemo", "variant_memo")):
        _entity(document, name)["table"] = table
        del _entity(document, name)["inheritance"]["tagValue"]


def test_a_union_level_keeps_its_document_beside_its_variant(damaged_case: CaseLoader) -> None:
    case = _with_note_hop(
        damaged_case(_PROFILE_HOP),
        "compatibility.overlap.VariantRecord",
        storage=_table_per_concrete_subtype,
    )
    branch = (
        'select t0.id, not t0."variantProfile" is null, t0."variantProfile", '
        "'{variant}' family_variant from {table} t0 where t0.id = any(cast(? as bigint[]))"
    )
    case.then["statements"][1] = {
        "sql": {
            "postgres": " union all ".join(
                branch.format(variant=variant, table=table)
                for variant, table in (
                    ("VariantMemo", "variant_memo"),
                    ("VariantNote", "variant_note"),
                )
            )
        },
        "binds": {"postgres": [[2], [2]]},
    }
    owners = [_OWNER_ROWS[0] | {"target_id": 2}]
    level = {"id": 2, "variantProfile": _STORED_PROFILE, "family_variant": "VariantNote"}

    assert_case_read(case, ScriptedReads(results=[owners, [level], owners]))


def _as_rows(case: Case, rows: list[dict[str, Any]]) -> Case:
    del case.then["graph"]
    case.then["rows"] = rows
    return case


def test_a_concrete_row_states_its_variant_and_leaves_the_document_out(
    damaged_case: CaseLoader,
) -> None:
    case = _as_rows(
        _concrete_note_read(damaged_case(_VARIANT_OVERLAP)),
        [{"id": 2, "_type": "compatibility.overlap.VariantNote"}],
    )

    assert_case_read(case, ScriptedReads(results=[[{"id": 2, "variantProfile": _STORED_PROFILE}]]))


def test_an_abstract_row_states_its_variant_and_leaves_the_document_out(
    damaged_case: CaseLoader,
) -> None:
    case = _as_rows(
        damaged_case(_VARIANT_OVERLAP), [{"id": 2, "_type": "compatibility.overlap.VariantNote"}]
    )
    stored = {"id": 2, "kind": "note", "variantProfile": _STORED_PROFILE}

    assert_case_read(case, ScriptedReads(results=[[stored], [{"id": 2, "kind": "note"}]]))


def _scenario_read_of_a_note_with_its_target(case: Case, model: Model) -> Case:
    """One Scenario read of a `VariantNote` whose document lies in a Column of another name."""

    def declare_hop(document: dict[str, Any]) -> None:
        root = _entity(document, "VariantRecord")
        root["valueObjects"][0]["column"] = "details"
        root["attributes"].append({"name": "targetId", "type": "int64"})
        _entity(document, "VariantNote")["relationships"] = [
            {
                "name": "target",
                "cardinality": "many-to-one",
                "join": {
                    "source": "targetId",
                    "target": {
                        "entity": "compatibility.overlap.ProfileTarget",
                        "attribute": "id",
                    },
                },
            }
        ]

    case.raw["when"]["scenario"] = [
        {
            "objectQuery": {
                "target": "compatibility.overlap.VariantNote",
                "predicate": {"true": {}},
                "includes": [{"segments": [{"rel": "compatibility.overlap.VariantNote.target"}]}],
            },
            "databaseCalls": 2,
            "statements": [
                {
                    "sql": {
                        "postgres": "select t0.id, t0.target_id, not t0.details is null, "
                        "t0.details from variant_record t0 where t0.kind = ?"
                    },
                    "binds": ["note"],
                },
                {
                    "sql": {
                        "postgres": "select t0.id from profile_target t0 "
                        "where t0.id = any(cast(? as bigint[]))"
                    },
                    "binds": [[10]],
                },
            ],
            "expectGraph": {
                "VariantNote": [
                    {
                        "id": 2,
                        "targetId": 10,
                        "profile": _PROFILE,
                        "_type": "compatibility.overlap.VariantNote",
                        "target": {"id": 10},
                    }
                ]
            },
        }
    ]
    return _with_descriptor_change(replace(case, model=model), declare_hop)


def test_a_scenario_graph_keeps_a_root_value_object_of_a_family(
    damaged_case: CaseLoader,
) -> None:
    """A step's graph is assembled from what it published, as a read case's is."""
    case = _scenario_read_of_a_note_with_its_target(
        damaged_case(_SCENARIO_WITH_INCLUDES), damaged_case(_VARIANT_OVERLAP).model
    )
    reads = ScriptedReads(
        results=[[{"id": 2, "target_id": 10, "details": _STORED_PROFILE}], [{"id": 10}]]
    )

    ScenarioRowObservations(case).assert_step(0, reads)


def test_a_concrete_read_keeps_its_document_beside_its_variant(damaged_case: CaseLoader) -> None:
    case = _concrete_note_read(damaged_case(_VARIANT_OVERLAP))

    assert_case_read(case, ScriptedReads(results=[[{"id": 2, "variantProfile": _STORED_PROFILE}]]))


def _scenario_row_read_of_a_note(case: Case, model: Model, row: dict[str, Any]) -> Case:
    """The Scenario read of a `VariantNote`, stating *row* rather than its graph."""
    read = _scenario_read_of_a_note_with_its_target(case, model)
    del read.raw["when"]["scenario"][0]["expectGraph"]
    read.raw["when"]["scenario"][0]["expectRows"] = [row]
    return read


_STORED_NOTE_READS = [[{"id": 2, "target_id": 10, "details": _STORED_PROFILE}], [{"id": 10}]]
_NOTE_ROW = {"id": 2, "target_id": 10, "_type": "compatibility.overlap.VariantNote"}


def test_a_step_row_spells_a_value_object_by_its_column(damaged_case: CaseLoader) -> None:
    case = _scenario_row_read_of_a_note(
        damaged_case(_SCENARIO_WITH_INCLUDES),
        damaged_case(_VARIANT_OVERLAP).model,
        _NOTE_ROW | {"details": _PROFILE},
    )

    ScenarioRowObservations(case).assert_step(0, ScriptedReads(results=_STORED_NOTE_READS))


def test_a_step_row_refuses_a_value_object_spelled_by_its_occurrence(
    damaged_case: CaseLoader,
) -> None:
    case = _scenario_row_read_of_a_note(
        damaged_case(_SCENARIO_WITH_INCLUDES),
        damaged_case(_VARIANT_OVERLAP).model,
        _NOTE_ROW | {"profile": _PROFILE},
    )

    with pytest.raises(CaseFailure, match="rows != expectRows"):
        ScenarioRowObservations(case).assert_step(0, ScriptedReads(results=_STORED_NOTE_READS))


_OWNER_PROFILE = {"label": "owner-profile"}
_OWNER_ROW = {"id": 1, "target_id": 10, "details": _OWNER_PROFILE}
_OWNER_NODE = {"id": 1, "targetId": 10, "profile": _OWNER_PROFILE}
_REPLACED_PROFILE = {"label": "replaced"}


def _owner_read(case: Case, model: Model, *later_steps: dict[str, Any]) -> Case:
    """A Scenario read of a `ProfileOwner`, then *later_steps*."""
    read = replace(case, model=model)
    read.raw["when"]["scenario"] = [
        {
            "objectQuery": {
                "target": "compatibility.overlap.ProfileOwner",
                "predicate": {"true": {}},
            },
            "databaseCalls": 1,
            "statements": [
                {
                    "sql": {
                        "postgres": "select t0.id, t0.target_id, not t0.details is null, "
                        "t0.details from profile_owner t0"
                    }
                }
            ],
        },
        *later_steps,
    ]
    return read


def _observe_every_step(case: Case, reads: ScriptedReads) -> None:
    observations = ScenarioRowObservations(case)
    for index in range(len(case.scenario)):
        observations.assert_step(index, reads)


def test_an_access_states_the_rows_of_its_source(damaged_case: CaseLoader) -> None:
    case = _owner_read(
        damaged_case(_SCENARIO_WITH_INCLUDES),
        damaged_case(_PROFILE_HOP).model,
        {"action": "access", "on": 0, "path": "details", "expectRows": [_OWNER_ROW]},
    )
    root = case.raw["when"]["scenario"][0]
    root["objectQuery"]["includes"] = [
        {"segments": [{"rel": "compatibility.overlap.ProfileOwner.details"}]}
    ]
    root["databaseCalls"] = 2
    root["statements"].append(
        {
            "sql": {
                "postgres": "select t0.id from profile_target t0 "
                "where t0.id = any(cast(? as bigint[]))"
            },
            "binds": [[10]],
        }
    )

    _observe_every_step(case, ScriptedReads(results=[_OWNER_ROWS, [{"id": 10}]]))


@pytest.mark.parametrize(
    ("assigned", "copy"),
    [
        pytest.param(
            {"profile": _REPLACED_PROFILE},
            {"id": 1, "targetId": 10, "profile": _REPLACED_PROFILE},
            id="occurrence",
        ),
        pytest.param(
            {"targetId": 11}, {"id": 1, "targetId": 11, "profile": _OWNER_PROFILE}, id="attribute"
        ),
    ],
)
def test_a_mutate_states_the_wire_value_of_its_copy(
    assigned: dict[str, Any], copy: dict[str, Any], damaged_case: CaseLoader
) -> None:
    case = _owner_read(
        damaged_case(_SCENARIO_WITH_INCLUDES),
        damaged_case(_PROFILE_HOP).model,
        {"action": "mutate", "on": 0, "set": assigned, "expectRows": [copy]},
    )

    _observe_every_step(case, ScriptedReads(results=[_OWNER_ROWS]))


def test_a_mutate_refuses_a_copy_spelled_by_its_columns(damaged_case: CaseLoader) -> None:
    case = _owner_read(
        damaged_case(_SCENARIO_WITH_INCLUDES),
        damaged_case(_PROFILE_HOP).model,
        {"action": "mutate", "on": 0, "set": {}, "expectRows": [_OWNER_ROW]},
    )

    with pytest.raises(CaseFailure, match="rows != expectRows"):
        _observe_every_step(case, ScriptedReads(results=[_OWNER_ROWS]))


def test_a_mutate_chain_states_the_copy_it_reached(damaged_case: CaseLoader) -> None:
    case = _owner_read(
        damaged_case(_SCENARIO_WITH_INCLUDES),
        damaged_case(_PROFILE_HOP).model,
        {"action": "mutate", "on": 0, "set": {"targetId": 11}},
        {
            "action": "mutate",
            "on": 1,
            "set": {"profile": _REPLACED_PROFILE},
            "expectRows": [{"id": 1, "targetId": 11, "profile": _REPLACED_PROFILE}],
        },
    )

    _observe_every_step(case, ScriptedReads(results=[_OWNER_ROWS]))


def test_an_access_of_a_mutate_states_the_copy(damaged_case: CaseLoader) -> None:
    copy = {"id": 1, "targetId": 11, "profile": _OWNER_PROFILE}
    case = _owner_read(
        damaged_case(_SCENARIO_WITH_INCLUDES),
        damaged_case(_PROFILE_HOP).model,
        {"action": "mutate", "on": 0, "set": {"targetId": 11}},
        {"action": "access", "on": 1, "path": "details", "expectRows": [copy]},
    )

    _observe_every_step(case, ScriptedReads(results=[_OWNER_ROWS]))


def test_a_mutate_of_a_family_row_states_its_occurrence(damaged_case: CaseLoader) -> None:
    note = _concrete_note_read(damaged_case(_VARIANT_OVERLAP))
    case = replace(damaged_case(_SCENARIO_WITH_INCLUDES), model=note.model)
    case.raw["when"]["scenario"] = [
        {
            "objectQuery": note.object_query,
            "databaseCalls": 1,
            "statements": note.then["statements"],
        },
        {
            "action": "mutate",
            "on": 0,
            "set": {"profile": _REPLACED_PROFILE},
            "expectRows": [_NOTE_NODE | {"profile": _REPLACED_PROFILE}],
        },
    ]

    _observe_every_step(
        case, ScriptedReads(results=[[{"id": 2, "variantProfile": _STORED_PROFILE}]])
    )


def test_a_mutate_of_an_abstract_row_copies_its_own_variant(damaged_case: CaseLoader) -> None:
    payments = damaged_case(_ABSTRACT_ROOT_GRAPH)
    case = replace(damaged_case(_SCENARIO_WITH_INCLUDES), model=payments.model)
    case.raw["when"]["scenario"] = [
        {
            "objectQuery": payments.object_query,
            "databaseCalls": 1,
            "statements": payments.then["statements"],
        },
        {
            "action": "mutate",
            "on": 0,
            "set": {"tendered": "30.00"},
            "expectRows": [
                {
                    "id": 3,
                    "amount": "20.00",
                    "tendered": "30.00",
                    "_type": "parallax.compatibility.CashPayment",
                }
            ],
        },
    ]

    _observe_every_step(case, ScriptedReads(results=[[_PAYMENTS[2]]]))


def test_a_copy_keeps_the_identity_of_its_source(damaged_case: CaseLoader) -> None:
    def rename_the_owner_key(document: dict[str, Any]) -> None:
        _entity(document, "ProfileOwner")["attributes"][0]["column"] = "owner_id"

    model = _with_descriptor_change(damaged_case(_PROFILE_HOP), rename_the_owner_key).model
    case = _owner_read(
        damaged_case(_SCENARIO_WITH_INCLUDES),
        model,
        {"action": "mutate", "on": 0, "set": {"targetId": 11}},
        {"action": "access", "on": 1, "path": "details", "sameObjectAs": 0},
    )
    case.raw["when"]["scenario"][0]["statements"][0]["sql"]["postgres"] = (
        "select t0.owner_id, t0.target_id, not t0.details is null, t0.details from profile_owner t0"
    )
    stored = {"owner_id": 1, "target_id": 10, "details": json.dumps(_OWNER_PROFILE)}

    _observe_every_step(case, ScriptedReads(results=[[stored]]))


def _count_document_decodes(monkeypatch: pytest.MonkeyPatch) -> Counter[Any]:
    decodes: Counter[Any] = Counter()
    decode_stored = oracle_materialize.decode_stored

    def counted(value: Any) -> Any:
        decodes[value] += 1
        return decode_stored(value)

    monkeypatch.setattr(oracle_materialize, "decode_stored", counted)
    return decodes


def test_a_read_step_decodes_each_stored_document_once(
    damaged_case: CaseLoader, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _owner_read(
        damaged_case(_SCENARIO_WITH_INCLUDES),
        damaged_case(_PROFILE_HOP).model,
        {"action": "mutate", "on": 0, "set": {}, "expectRows": [_OWNER_NODE]},
    )
    case.raw["when"]["scenario"][0]["expectRows"] = [_OWNER_ROW]
    decodes = _count_document_decodes(monkeypatch)

    _observe_every_step(case, ScriptedReads(results=[_OWNER_ROWS]))

    assert decodes == {_OWNER_ROWS[0]["details"]: 1}


def _streamed_owner_read(case: Case, model: Model, *later_steps: dict[str, Any]) -> Case:
    """The `ProfileOwner` read of :func:`_owner_read` as one short streamed page."""
    streamed = _owner_read(case, model, *later_steps)
    root = streamed.raw["when"]["scenario"][0]
    root["stream"] = {"batchSize": 2}
    root["statements"] = [
        {
            "sql": {
                "postgres": "select t0.id, t0.target_id, not t0.details is null, t0.details, "
                "t0.id parallax_seek_0 from profile_owner t0 order by t0.id asc limit ?"
            },
            "binds": [3],
        }
    ]
    return streamed


def test_a_streamed_step_decodes_each_stored_document_once(
    damaged_case: CaseLoader, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _streamed_owner_read(
        damaged_case(_SCENARIO_WITH_INCLUDES),
        damaged_case(_PROFILE_HOP).model,
        {"action": "mutate", "on": 0, "set": {}, "expectRows": [_OWNER_NODE]},
    )
    case.raw["when"]["scenario"][0]["expectRows"] = [_OWNER_ROW]
    decodes = _count_document_decodes(monkeypatch)

    _observe_every_step(case, ScriptedReads(results=[[_OWNER_ROWS[0] | {"parallax_seek_0": 1}]]))

    assert decodes == {_OWNER_ROWS[0]["details"]: 1}


def test_a_copy_of_a_streamed_root_carries_no_view_the_page_attached(
    damaged_case: CaseLoader,
) -> None:
    case = _streamed_owner_read(
        damaged_case(_SCENARIO_WITH_INCLUDES),
        damaged_case(_PROFILE_HOP).model,
        {"action": "mutate", "on": 0, "set": {}, "expectRows": [_OWNER_NODE]},
    )
    root = case.raw["when"]["scenario"][0]
    root["objectQuery"]["includes"] = [
        {"segments": [{"rel": "compatibility.overlap.ProfileOwner.details"}]}
    ]
    root["databaseCalls"] = 2
    root["statements"].append(
        {
            "sql": {
                "postgres": "select t0.id from profile_target t0 "
                "where t0.id = any(cast(? as bigint[]))"
            },
            "binds": [[10]],
        }
    )

    _observe_every_step(
        case,
        ScriptedReads(results=[[_OWNER_ROWS[0] | {"parallax_seek_0": 1}], [{"id": 10}]]),
    )


def test_a_position_that_decoded_nothing_states_what_it_published(
    damaged_case: CaseLoader,
) -> None:
    stored = {"id": 1, "target_id": 10, "details": json.dumps({"label": 7})}
    case = _owner_read(damaged_case(_SCENARIO_WITH_INCLUDES), damaged_case(_PROFILE_HOP).model)
    case.raw["when"]["scenario"][0]["expectRows"] = [stored]

    _observe_every_step(case, ScriptedReads(results=[[stored]]))


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
    reads = ScriptedReads(results=_ORDERED_RESULTS)

    with pytest.raises(CaseFailure, match="did not come through the materialization seam"):
        assert_case_read(case, reads)


def test_a_published_row_cannot_be_minted_by_holding_the_class() -> None:
    """Provenance is the derivation, so the class alone does not confer it.

    Standing in for a future path that would rather stamp a row than run the
    sequence: the constructor demands a token the materialization module keeps
    private, so a consumer that reached the class mints nothing.
    """
    with pytest.raises(CaseFailure, match="minted with a token this module keeps"):
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


def test_an_observation_refuses_rows_that_skipped_the_seam() -> None:
    """A retained observation holds what its step published, and refuses anything else.

    Standing in for a future path that assembles the materialization sequence
    itself: the observation refuses the rows at construction rather than retaining
    storage a later reuse, access, or identity check would be graded against.
    """
    unpublished = cast(oracle_materialize.PublishedRow, {"id": 1})

    with pytest.raises(TypeError, match="did not come through the publication seam"):
        retained.Observation(rows=[unpublished], nodes=[None], entity=None, includes=None)


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


_DORMANT_TPH_INCLUDE = "m-inheritance-160-dormant-tph-include-layout-twin-columns.yaml"
_WORKBENCHES: list[dict[str, Any]] = [
    {"id": 1, "name": "Bench", "prototype_id": 7, "concept_id": 8},
    {"id": 2, "name": "Shed", "prototype_id": 9, "concept_id": None},
]
_GADGETS: list[dict[str, Any]] = [
    {"id": 1, "kind": "widget", "label": "Cog", "workbench_id": 1, "spin": 3},
    {"id": 2, "kind": "widget", "label": "Gear", "workbench_id": 1, "spin": None},
]


def test_a_hop_to_a_position_with_no_concrete_issues_no_child_statement(
    corpus_case: CaseLoader,
) -> None:
    # Both workbenches gather a non-null key for the to-one and to-many hops to
    # the empty position, and the hop continued past the empty one has no parent
    # at all; only the live sibling hop reads.
    reads = ScriptedReads(results=[_WORKBENCHES, _GADGETS, _WORKBENCHES])

    assert_case_read(corpus_case(_DORMANT_TPH_INCLUDE), reads)

    assert len(reads.calls) == 3
    assert reads.calls[1][1] == ([1, 2],)


def test_a_child_statement_for_a_position_with_no_concrete_is_refused(
    damaged_case: CaseLoader,
) -> None:
    case = damaged_case(_DORMANT_TPH_INCLUDE)
    case.then["statements"].append(copy.deepcopy(case.then["statements"][1]))

    with pytest.raises(CaseFailure, match="1 unused deep-fetch child statement"):
        assert_case_read(case, ScriptedReads(results=[_WORKBENCHES, _GADGETS, _WORKBENCHES]))


# --- a table-per-concrete-subtype level ---------------------------------------


_THREE_HOP = "m-snapshot-read-051-three-hop-include.yaml"

_TICKETS: list[dict[str, Any]] = [
    {"id": 50, "parking_id": 30},
    {"id": 51, "parking_id": 31},
    {"id": 52, "parking_id": 32},
    {"id": 53, "parking_id": 33},
    {"id": 54, "parking_id": None},
]
_PARKINGS: list[dict[str, Any]] = [
    {"id": 30, "vehicle_id": 5},
    {"id": 31, "vehicle_id": 6},
    {"id": 32, "vehicle_id": None},
    {"id": 33, "vehicle_id": 7},
]
# The rows a `union all` returns are aligned to one superset, so each carries the
# sibling branch's column as the placeholder's NULL and names its own branch by literal.
_VEHICLES: list[dict[str, Any]] = [
    {
        "id": 6,
        "maker": "Trek",
        "dealer_id": 41,
        "gears": 21,
        "seats": None,
        "family_variant": "Bike",
    },
    {
        "id": 5,
        "maker": "Volvo",
        "dealer_id": 40,
        "gears": None,
        "seats": 4,
        "family_variant": "Car",
    },
    {
        "id": 7,
        "maker": "Saab",
        "dealer_id": None,
        "gears": None,
        "seats": None,
        "family_variant": "Car",
    },
]
_DEALERS: list[dict[str, Any]] = [{"id": 40, "name": "Nordic"}, {"id": 41, "name": "Velo"}]

_DIALECTS = ("postgres", "mariadb")


def _chain(vehicles: list[dict[str, Any]] = _VEHICLES) -> list[list[dict[str, Any]]]:
    """Every statement's answer in order, the independent root oracle last."""
    return [_TICKETS, _PARKINGS, vehicles, _DEALERS, _TICKETS]


def _vehicle_level(case: Case) -> dict[str, Any]:
    """The `union all` statement of the case's polymorphic hop, as its copy holds it."""
    return case.then["statements"][2]


def _with_vehicle_sql(case: Case, dialect: str, old: str, new: str, *, count: int = -1) -> Case:
    sql = _vehicle_level(case)["sql"]
    assert old in sql[dialect]
    sql[dialect] = sql[dialect].replace(old, new, count)
    return case


def _with_descriptor_change(case: Case, change: Callable[[dict[str, Any]], None]) -> Case:
    """*case* read against its model descriptor as *change* rewrites it.

    The corpus declares no model that varies this hop's position, and a variation the
    oracle must grade is no reason to add one.
    """
    document = _load_yaml(case.model.path)
    change(document)
    return replace(
        case,
        model=Model(
            path=case.model.path,
            descriptor=derive_temporal_structure(document),
            fixtures=dict(case.model.fixtures),
        ),
    )


def _entity(document: dict[str, Any], name: str) -> dict[str, Any]:
    return next(entity for entity in document["entities"] if entity["name"] == name)


@pytest.mark.parametrize("dialect", _DIALECTS)
def test_a_union_level_assembles_the_authored_graph_in_one_statement(
    corpus_case: CaseLoader, dialect: str
) -> None:
    case = corpus_case(_THREE_HOP)
    reads = ScriptedReads(dialect=dialect, results=_chain())

    assert_case_read(case, reads)

    assert reads.statements[:4] == case.golden_statements(dialect)
    assert len(reads.calls) == 5


@pytest.mark.parametrize(
    ("dialect", "expected"),
    [
        ("postgres", ([5, 6, 7], [5, 6, 7])),
        ("mariadb", (5, 6, 7, 5, 6, 7)),
    ],
)
def test_a_union_level_executes_the_gathered_keys_once_per_branch(
    corpus_case: CaseLoader, dialect: str, expected: tuple[Any, ...]
) -> None:
    reads = ScriptedReads(dialect=dialect, results=_chain())

    assert_case_read(corpus_case(_THREE_HOP), reads)

    assert reads.calls[2][1] == expected


@pytest.mark.parametrize(
    ("dialect", "binds"),
    [("postgres", [[7, 6, 5], [6, 5, 7]]), ("mariadb", [7, 6, 5, 6, 5, 7])],
)
def test_each_branch_compares_its_key_set_unordered(
    damaged_case: CaseLoader, dialect: str, binds: list[Any]
) -> None:
    case = damaged_case(_THREE_HOP)
    _vehicle_level(case)["binds"][dialect] = binds

    assert_case_read(case, ScriptedReads(dialect=dialect, results=_chain()))


@pytest.mark.parametrize(
    ("dialect", "binds"),
    [
        ("postgres", [[5, 6, 7], [5, 6]]),
        ("postgres", [[5, 6, 7], [5, 6, 8]]),
        ("postgres", [[5, 6], [5, 6, 7]]),
        ("mariadb", [5, 6, 7, 5, 6, 8]),
        ("mariadb", [5, 6, 5, 6, 7, 7]),
    ],
)
def test_a_branch_keyed_by_anything_else_is_refused(
    damaged_case: CaseLoader, dialect: str, binds: list[Any]
) -> None:
    case = damaged_case(_THREE_HOP)
    _vehicle_level(case)["binds"][dialect] = binds

    with pytest.raises(CaseFailure, match=r"level 2 \(vehicle\) key-set binds"):
        assert_case_read(case, ScriptedReads(dialect=dialect, results=_chain()))


@pytest.mark.parametrize(
    ("dialect", "binds"), [("postgres", [[5, 6, 7]]), ("mariadb", [5, 6, 7, 5, 6])]
)
def test_binds_that_cannot_cover_every_branch_are_refused(
    damaged_case: CaseLoader, dialect: str, binds: list[Any]
) -> None:
    case = damaged_case(_THREE_HOP)
    _vehicle_level(case)["binds"][dialect] = binds

    with pytest.raises(CaseFailure, match="one group per `union all` branch"):
        assert_case_read(case, ScriptedReads(dialect=dialect, results=_chain()))


def test_a_level_authoring_no_binds_at_all_is_refused(damaged_case: CaseLoader) -> None:
    case = damaged_case(_ORDERED_ITEMS)
    del case.then["statements"][1]["binds"]
    reads = ScriptedReads(results=_ORDERED_RESULTS)

    with pytest.raises(CaseFailure, match="key-set binds"):
        assert_case_read(case, reads)


def test_uneven_branch_placeholders_are_refused_though_the_flat_binds_match(
    damaged_case: CaseLoader,
) -> None:
    case = _with_vehicle_sql(
        damaged_case(_THREE_HOP),
        "mariadb",
        "traversal_bike t0 where t0.id in (?, ?, ?)",
        "traversal_bike t0 where t0.id in (?, ?)",
    )
    _with_vehicle_sql(
        case,
        "mariadb",
        "traversal_car t0 where t0.id in (?, ?, ?)",
        "traversal_car t0 where t0.id in (?, ?, ?, ?)",
    )

    with pytest.raises(CaseFailure, match=r"branch 0 \('Bike'\).*consumes 2 bind\(s\), expected 3"):
        assert_case_read(case, ScriptedReads(dialect="mariadb", results=_chain()))


@pytest.mark.parametrize(
    "membership",
    ["t0.id in (?, ?) and not ? is null", "t0.id in (?, ?, 7) and not ? is null"],
    ids=["short-list", "literal-member"],
)
def test_a_mariadb_branch_spending_a_key_outside_its_membership_is_refused(
    damaged_case: CaseLoader, membership: str
) -> None:
    case = _with_vehicle_sql(
        damaged_case(_THREE_HOP),
        "mariadb",
        "traversal_bike t0 where t0.id in (?, ?, ?)",
        f"traversal_bike t0 where {membership}",
    )

    with pytest.raises(CaseFailure, match=r"branch 0 \('Bike'\) does not compare its 3 gathered"):
        assert_case_read(case, ScriptedReads(dialect="mariadb", results=_chain()))


def test_a_branch_keyed_by_another_column_is_refused(damaged_case: CaseLoader) -> None:
    case = _with_vehicle_sql(
        damaged_case(_THREE_HOP),
        "mariadb",
        "traversal_car t0 where t0.id in",
        "traversal_car t0 where t0.dealer_id in",
    )

    with pytest.raises(CaseFailure, match=r"branch 1 \('Car'\).*not keyed by 'id'"):
        assert_case_read(case, ScriptedReads(dialect="mariadb", results=_chain()))


def test_a_mariadb_branch_comparing_one_key_by_equality_is_refused(
    damaged_case: CaseLoader,
) -> None:
    case = _with_vehicle_sql(
        damaged_case(_THREE_HOP),
        "mariadb",
        "traversal_car t0 where t0.id in (?, ?, ?)",
        "traversal_car t0 where t0.id = ?",
    )

    with pytest.raises(CaseFailure, match=r"branch 1 \('Car'\).*not keyed by 'id'"):
        assert_case_read(case, ScriptedReads(dialect="mariadb", results=_chain()))


def test_a_branch_with_no_key_membership_is_refused(damaged_case: CaseLoader) -> None:
    case = _with_vehicle_sql(
        damaged_case(_THREE_HOP),
        "postgres",
        " from traversal_car t0 where t0.id = any(cast(? as bigint[]))",
        " from traversal_car t0",
    )

    with pytest.raises(CaseFailure, match=r"branch 1 \('Car'\).*not keyed by 'id'"):
        assert_case_read(case, ScriptedReads(results=_chain()))


def test_one_postgres_branch_casting_its_keys_narrower_is_refused(
    damaged_case: CaseLoader,
) -> None:
    case = _with_vehicle_sql(
        damaged_case(_THREE_HOP),
        "postgres",
        "traversal_car t0 where t0.id = any(cast(? as bigint[]))",
        "traversal_car t0 where t0.id = any(cast(? as int[]))",
    )

    with pytest.raises(CaseFailure, match=r"branch 1 \('Car'\) does not compare its gathered"):
        assert_case_read(case, ScriptedReads(results=_chain()))


_BIKE_BRANCH = {
    "postgres": (
        "select t0.id, t0.maker, t0.dealer_id, t0.gears, cast(null as int) seats, "
        "'Bike' family_variant from traversal_bike t0 where t0.id = any(cast(? as bigint[]))"
    ),
    "mariadb": (
        "select t0.id, t0.maker, t0.dealer_id, t0.gears, cast(null as signed) seats, "
        "'Bike' family_variant from traversal_bike t0 where t0.id in (?, ?, ?)"
    ),
}
_PLACEHOLDER = {"postgres": "cast(null as int)", "mariadb": "cast(null as signed)"}


@pytest.mark.parametrize("dialect", _DIALECTS)
def test_a_level_dropping_a_branch_is_refused(damaged_case: CaseLoader, dialect: str) -> None:
    case = damaged_case(_THREE_HOP)
    _vehicle_level(case)["sql"][dialect] = _BIKE_BRANCH[dialect]

    with pytest.raises(CaseFailure, match="one bare `union all`"):
        assert_case_read(case, ScriptedReads(dialect=dialect, results=_chain()))


@pytest.mark.parametrize("dialect", _DIALECTS)
def test_a_level_repeating_a_branch_is_refused(damaged_case: CaseLoader, dialect: str) -> None:
    case = damaged_case(_THREE_HOP)
    sql = _vehicle_level(case)["sql"]
    sql[dialect] = f"{sql[dialect]} union all {_BIKE_BRANCH[dialect]}"

    with pytest.raises(CaseFailure, match=f"lowers to 2 .* the {dialect} golden has 3"):
        assert_case_read(case, ScriptedReads(dialect=dialect, results=_chain()))


@pytest.mark.parametrize("dialect", _DIALECTS)
def test_a_level_reading_its_branches_out_of_canonical_order_is_refused(
    damaged_case: CaseLoader, dialect: str
) -> None:
    case = damaged_case(_THREE_HOP)
    sql = _vehicle_level(case)["sql"]
    bike, car = sql[dialect].split(" union all ")
    sql[dialect] = f"{car} union all {bike}"

    with pytest.raises(CaseFailure, match="branch 0 must read from 'traversal_bike'"):
        assert_case_read(case, ScriptedReads(dialect=dialect, results=_chain()))


@pytest.mark.parametrize("dialect", _DIALECTS)
def test_a_level_branch_spelling_the_wrong_literal_is_refused(
    damaged_case: CaseLoader, dialect: str
) -> None:
    case = _with_vehicle_sql(
        damaged_case(_THREE_HOP), dialect, "'Car' family_variant", "'Bike' family_variant"
    )

    with pytest.raises(CaseFailure, match="family_variant literal 'Bike', expected .*'Car'"):
        assert_case_read(case, ScriptedReads(dialect=dialect, results=_chain()))


@pytest.mark.parametrize("dialect", _DIALECTS)
def test_a_level_branch_with_an_untyped_null_is_refused(
    damaged_case: CaseLoader, dialect: str
) -> None:
    case = _with_vehicle_sql(damaged_case(_THREE_HOP), dialect, _PLACEHOLDER[dialect], "null")

    with pytest.raises(CaseFailure, match="NON-applicable column"):
        assert_case_read(case, ScriptedReads(dialect=dialect, results=_chain()))


@pytest.mark.parametrize(
    ("dialect", "wrong"),
    [
        ("postgres", "cast(null as bigint)"),
        ("mariadb", "cast(null as char)"),
        ("mariadb", "cast(null as int)"),
    ],
)
def test_a_level_placeholder_in_another_type_is_refused(
    damaged_case: CaseLoader, dialect: str, wrong: str
) -> None:
    case = _with_vehicle_sql(damaged_case(_THREE_HOP), dialect, _PLACEHOLDER[dialect], wrong)

    with pytest.raises(CaseFailure, match="placeholder to"):
        assert_case_read(case, ScriptedReads(dialect=dialect, results=_chain()))


@pytest.mark.parametrize("dialect", _DIALECTS)
def test_a_level_projecting_off_the_position_layout_is_refused(
    damaged_case: CaseLoader, dialect: str
) -> None:
    case = _with_vehicle_sql(
        damaged_case(_THREE_HOP),
        dialect,
        f"t0.gears, {_PLACEHOLDER[dialect]} seats",
        f"{_PLACEHOLDER[dialect]} seats, t0.gears",
        count=1,
    )

    with pytest.raises(CaseFailure, match="not the stable superset"):
        assert_case_read(case, ScriptedReads(dialect=dialect, results=_chain()))


@pytest.mark.parametrize("dialect", _DIALECTS)
def test_a_level_deduplicating_its_union_is_refused(damaged_case: CaseLoader, dialect: str) -> None:
    case = _with_vehicle_sql(damaged_case(_THREE_HOP), dialect, " union all ", " union ")

    with pytest.raises(CaseFailure, match="union all"):
        assert_case_read(case, ScriptedReads(dialect=dialect, results=_chain()))


def test_a_wrapped_level_is_refused(damaged_case: CaseLoader) -> None:
    case = damaged_case(_THREE_HOP)
    sql = _vehicle_level(case)["sql"]
    sql["postgres"] = (
        "select u.id, u.maker, u.dealer_id, u.gears, u.seats, u.family_variant "
        f"from ({sql['postgres']}) u"
    )

    with pytest.raises(CaseFailure, match="one bare `union all`"):
        assert_case_read(case, ScriptedReads(results=_chain()))


def test_a_level_is_graded_when_its_branches_return_no_rows(damaged_case: CaseLoader) -> None:
    case = _with_vehicle_sql(
        damaged_case(_THREE_HOP), "postgres", "'Car' family_variant", "'Truck' family_variant"
    )

    with pytest.raises(CaseFailure, match="family_variant literal 'Truck'"):
        assert_case_read(case, ScriptedReads(results=[_TICKETS, _PARKINGS, [], _TICKETS]))


def test_a_rows_branch_literal_is_the_variant_it_publishes(corpus_case: CaseLoader) -> None:
    swapped = [row | {"family_variant": "Bike"} for row in _VEHICLES]

    with pytest.raises(CaseFailure, match="assembled graph != then.graph"):
        assert_case_read(corpus_case(_THREE_HOP), ScriptedReads(results=_chain(swapped)))


def test_a_literal_naming_no_branch_of_the_level_is_refused(corpus_case: CaseLoader) -> None:
    strays = [row | {"family_variant": "Truck"} for row in _VEHICLES]

    with pytest.raises(CaseFailure, match="literal 'Truck' names no branch"):
        assert_case_read(corpus_case(_THREE_HOP), ScriptedReads(results=_chain(strays)))


def test_a_level_row_carrying_no_literal_is_refused(corpus_case: CaseLoader) -> None:
    bare = [
        {key: value for key, value in row.items() if key != "family_variant"} for row in _VEHICLES
    ]

    with pytest.raises(CaseFailure, match=r"polymorphic hop vehicle does not project"):
        assert_case_read(corpus_case(_THREE_HOP), ScriptedReads(results=_chain(bare)))


def test_a_redundantly_narrowed_level_reads_the_same_union_under_its_view_key(
    damaged_case: CaseLoader,
) -> None:
    case = damaged_case(_THREE_HOP)
    segment = case.when["objectQuery"]["includes"][0]["segments"][1]
    segment["narrowTo"] = ["parallax.compatibility.Bike", "parallax.compatibility.Car"]
    for ticket in case.then["graph"]["Ticket"]:
        if ticket["parking"] is not None:
            parking = ticket["parking"]
            parking["vehicle[Bike,Car]"] = parking.pop("vehicle")
    reads = ScriptedReads(results=_chain())

    assert_case_read(case, reads)

    assert reads.calls[2][1] == ([5, 6, 7], [5, 6, 7])


def _vehicle_family_at_transaction_time(document: dict[str, Any]) -> None:
    _entity(document, "Vehicle")["temporality"] = "transaction-time"


@pytest.mark.parametrize(
    ("dialect", "keys", "executed"),
    [
        ("postgres", [[5, 6, 7]], ([5, 6, 7], "infinity", [5, 6, 7], "infinity")),
        ("mariadb", [5, 6, 7], (5, 6, 7, "infinity", 5, 6, 7, "infinity")),
    ],
)
def test_a_temporal_union_level_repeats_its_as_of_binds_per_branch(
    damaged_case: CaseLoader, dialect: str, keys: list[Any], executed: tuple[Any, ...]
) -> None:
    case = _with_descriptor_change(damaged_case(_THREE_HOP), _vehicle_family_at_transaction_time)
    level = _vehicle_level(case)
    level["sql"][dialect] = (
        level["sql"][dialect]
        .replace(" seats, 'Bike'", " seats, t0.in_z, t0.out_z, 'Bike'")
        .replace("t0.seats, 'Car'", "t0.seats, t0.in_z, t0.out_z, 'Car'")
        .replace(" union all ", " and t0.out_z = ? union all ")
        + " and t0.out_z = ?"
    )
    level["binds"][dialect] = [*keys, "infinity", *keys, "infinity"]
    vehicles = [row | {"in_z": _JANUARY, "out_z": _FOREVER} for row in _VEHICLES]
    for ticket in case.then["graph"]["Ticket"]:
        vehicle = (ticket["parking"] or {}).get("vehicle")
        if vehicle is not None:
            vehicle |= {"txStart": _JANUARY, "txEnd": "infinity"}
    reads = ScriptedReads(dialect=dialect, results=_chain(vehicles))

    assert_case_read(case, reads)

    assert reads.calls[2][1] == executed


def test_a_temporal_union_branch_carrying_the_wrong_as_of_bind_is_refused(
    damaged_case: CaseLoader,
) -> None:
    case = _with_descriptor_change(damaged_case(_THREE_HOP), _vehicle_family_at_transaction_time)
    _vehicle_level(case)["binds"]["postgres"] = [
        [5, 6, 7],
        "infinity",
        [5, 6, 7],
        _JANUARY,
    ]

    with pytest.raises(CaseFailure, match=r"level 2 \(vehicle\) as-of suffix"):
        assert_case_read(case, ScriptedReads(results=_chain()))


_TEMPORAL_UNION = "m-read-planning-028-temporal-union-level.yaml"
_ORDERED_UNION = "m-read-planning-029-ordered-temporal-union-level.yaml"
_DOCUMENT_KEY_UNION = "m-read-planning-030-ordered-union-level-document-key.yaml"
_INTERVAL = {"from_z": _JANUARY, "thru_z": _FOREVER, "in_z": _JANUARY, "out_z": _FOREVER}
_SHEETS: list[dict[str, Any]] = [
    {"id": 100, "name": "Retail", **_INTERVAL},
    {"id": 101, "name": "Business", **_INTERVAL},
]


def _sheet_rate(
    key: int, sheet: int, priority: int | None, tier: int | None, variant: str
) -> dict[str, Any]:
    return {
        "id": key,
        "sheet_id": sheet,
        "priority": priority,
        "tier": tier,
        "grade": None,
        "spread": None,
        **_INTERVAL,
        "family_variant": variant,
    }


_RANKED_RATES = [
    _sheet_rate(2, 100, 20, 1, "SheetLoan"),
    _sheet_rate(1, 100, 20, None, "SheetDeposit"),
    _sheet_rate(6, 101, 10, 1, "SheetDeposit"),
    _sheet_rate(4, 100, 10, None, "SheetLoan"),
    _sheet_rate(5, 101, None, 1, "SheetLoan"),
    _sheet_rate(3, 100, None, 2, "SheetDeposit"),
]


def _sheet_level(case: Case) -> dict[str, Any]:
    return case.then["statements"][1]


def _ranked_reads(dialect: str, rates: list[dict[str, Any]] = _RANKED_RATES) -> ScriptedReads:
    return ScriptedReads(dialect=dialect, results=[_SHEETS, rates])


@pytest.mark.parametrize("dialect", _DIALECTS)
def test_an_ordered_level_reading_a_bare_union_is_refused(
    damaged_case: CaseLoader, dialect: str
) -> None:
    case = damaged_case(_ORDERED_UNION)
    sql = _sheet_level(case)["sql"]
    sql[dialect] = sql[dialect].partition(" from (")[2].rpartition(") u order by ")[0]

    with pytest.raises(CaseFailure, match="wraps its `union all` as the derived table"):
        assert_case_read(case, _ranked_reads(dialect))


@pytest.mark.parametrize("dialect", _DIALECTS)
def test_an_ordered_level_hanging_its_order_on_the_union_is_refused(
    damaged_case: CaseLoader, dialect: str
) -> None:
    case = damaged_case(_ORDERED_UNION)
    sql = _sheet_level(case)["sql"]
    inner, _, order = sql[dialect].partition(" from (")[2].rpartition(") u order by ")
    sql[dialect] = f"{inner} order by {order.replace('u.', '')}"

    with pytest.raises(CaseFailure, match="wraps its `union all` as the derived table"):
        assert_case_read(case, _ranked_reads(dialect))


@pytest.mark.parametrize(
    ("dialect", "old", "new"),
    [
        ("postgres", "u.priority desc nulls last, ", "u.priority desc, "),
        ("postgres", ", u.id asc", ""),
        ("postgres", ", u.id asc", ", u.id desc"),
        ("mariadb", "u.tier is null, ", ""),
        ("mariadb", "u.priority desc, ", "u.tier asc, "),
    ],
)
def test_an_ordered_level_departing_from_its_declared_keys_is_refused(
    damaged_case: CaseLoader, dialect: str, old: str, new: str
) -> None:
    case = damaged_case(_ORDERED_UNION)
    sql = _sheet_level(case)["sql"]
    assert old in sql[dialect]
    sql[dialect] = sql[dialect].replace(old, new)

    with pytest.raises(CaseFailure, match="does not wrap its `union all`"):
        assert_case_read(case, _ranked_reads(dialect))


@pytest.mark.parametrize("dialect", _DIALECTS)
def test_an_ordered_level_answering_out_of_order_is_refused(
    corpus_case: CaseLoader, dialect: str
) -> None:
    rates = list(reversed(_RANKED_RATES))

    with pytest.raises(CaseFailure, match="not in declared orderBy order"):
        assert_case_read(corpus_case(_ORDERED_UNION), _ranked_reads(dialect, rates))


@pytest.mark.parametrize("dialect", _DIALECTS)
def test_an_unordered_level_carrying_a_wrap_is_refused(
    damaged_case: CaseLoader, dialect: str
) -> None:
    case = damaged_case(_TEMPORAL_UNION)
    sql = _sheet_level(case)["sql"]
    sql[dialect] = f"select u.id from ({sql[dialect]}) u order by u.id asc"

    with pytest.raises(CaseFailure, match="one bare `union all`"):
        assert_case_read(case, _ranked_reads(dialect))


@pytest.mark.parametrize(
    ("dialect", "authored"),
    [("postgres", ["tier", "priority"]), ("mariadb", ["$.priority", "$.tier", "$.priority"])],
)
def test_a_document_key_binding_another_members_path_is_refused(
    damaged_case: CaseLoader, dialect: str, authored: list[str]
) -> None:
    case = damaged_case(_DOCUMENT_KEY_UNION)
    binds = _sheet_level(case)["binds"][dialect]
    binds[-len(authored) :] = authored

    with pytest.raises(CaseFailure, match="outer wrap binds"):
        assert_case_read(case, _ranked_reads(dialect, []))


@pytest.mark.parametrize(("dialect", "dropped"), [("postgres", 2), ("mariadb", 3)])
def test_a_document_key_dropping_its_trailing_paths_is_refused(
    damaged_case: CaseLoader, dialect: str, dropped: int
) -> None:
    case = damaged_case(_DOCUMENT_KEY_UNION)
    del _sheet_level(case)["binds"][dialect][-dropped:]

    with pytest.raises(CaseFailure, match="do not split|as-of suffix|key-set binds"):
        assert_case_read(case, _ranked_reads(dialect, []))
