"""Production find executor unit tests (`parallax.snapshot.handle.find` /
`find_history`, COR-3 Phase 7 increment 5).

Exercises the ONE per-level loop against a fake, canned-response `m-db-port`
(no Docker): round-trip accounting (one statement per non-empty level), the
empty-level short-circuit (no child statement issued, gathered from `then`'s
own contract in `m-deep-fetch`), a back-reference level's zero-statement
resolution, `familyVariant` materialization flowing through the executor
(`m-sql` applied to child-level rows), and the milestone-set `find_history`
edge-grouping/ordering.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import cast

import pytest

from parallax.conformance import models
from parallax.core.base import INFINITY
from parallax.core.db_port import DbPort, Row
from parallax.core.dialect import POSTGRES
from parallax.core.op_algebra import deserialize
from parallax.snapshot import handle
from parallax.snapshot.materialize import Node

pytestmark = pytest.mark.unit

_MODELS = models.load_models()
ORDERS = _MODELS["orders"]
ANIMAL = _MODELS["animal"]
INVOICE = _MODELS["invoice"]

_UTC = dt.UTC


def _kids(node: Node, key: str) -> list[Node]:
    """A to-many relationship attachment, typed for test-side assertions."""
    return cast("list[Node]", node.fields[key])


def _kid(node: Node, key: str) -> Node | None:
    """A to-one relationship attachment, typed for test-side assertions."""
    return cast("Node | None", node.fields[key])


class QueuePort:
    """A fake `m-db-port` returning one canned response per `execute()` call,
    in call order — enough to drive the executor's own per-level loop without
    a real database."""

    def __init__(self, responses: Sequence[list[Row]]) -> None:
        self._responses = list(responses)
        self.executed: list[tuple[str, list[object]]] = []

    def execute(self, sql: str, binds: Sequence[object]) -> list[Row]:
        self.executed.append((sql, list(binds)))
        return self._responses.pop(0)

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:  # pragma: no cover
        raise NotImplementedError

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:  # pragma: no cover
        raise NotImplementedError


def test_find_issues_one_statement_per_non_empty_level() -> None:
    port = QueuePort(
        [
            [
                {
                    "id": 1,
                    "name": "Ada",
                    "sku": "A",
                    "qty": 1,
                    "price": Decimal("1"),
                    "active": True,
                    "ordered_on": dt.date(2024, 1, 1),
                }
            ],
            [{"id": 11, "order_id": 1, "sku": "x", "quantity": 1, "shipped_on": None}],
        ]
    )
    op = deserialize(
        {
            "deepFetch": {
                "operand": {"eq": {"attr": "Order.id", "value": 1}},
                "paths": [[{"rel": "Order.items"}]],
            }
        }
    )
    result = handle.find(op, ORDERS, POSTGRES, "Order", port)
    assert result.execution.round_trips == 2
    assert [n.fields["id"] for n in _kids(result.nodes[0], "items")] == [11]


def test_find_empty_root_short_circuits_with_no_child_statement() -> None:
    port = QueuePort([[]])
    op = deserialize(
        {
            "deepFetch": {
                "operand": {"eq": {"attr": "Order.id", "value": 999}},
                "paths": [[{"rel": "Order.items"}, {"rel": "OrderItem.statuses"}]],
            }
        }
    )
    result = handle.find(op, ORDERS, POSTGRES, "Order", port)
    assert result.execution.round_trips == 1
    assert result.nodes == ()
    assert len(port.executed) == 1


def test_find_empty_intermediate_level_suppresses_only_the_grandchild_statement() -> None:
    port = QueuePort(
        [
            [
                {
                    "id": 4,
                    "name": "Margaret",
                    "sku": None,
                    "qty": 20,
                    "price": Decimal("1"),
                    "active": True,
                    "ordered_on": dt.date(2024, 4, 20),
                }
            ],
            [],  # the items level executes and returns zero rows
        ]
    )
    op = deserialize(
        {
            "deepFetch": {
                "operand": {"eq": {"attr": "Order.id", "value": 4}},
                "paths": [[{"rel": "Order.items"}, {"rel": "OrderItem.statuses"}]],
            }
        }
    )
    result = handle.find(op, ORDERS, POSTGRES, "Order", port)
    assert result.execution.round_trips == 2
    assert result.nodes[0].fields["items"] == []


def test_find_back_reference_level_issues_no_additional_statement() -> None:
    port = QueuePort(
        [
            [
                {
                    "id": 1,
                    "name": "Ada",
                    "sku": "A",
                    "qty": 1,
                    "price": Decimal("1"),
                    "active": True,
                    "ordered_on": dt.date(2024, 1, 1),
                }
            ],
            [{"id": 11, "order_id": 1, "sku": "x", "quantity": 1, "shipped_on": None}],
        ]
    )
    op = deserialize(
        {
            "deepFetch": {
                "operand": {"eq": {"attr": "Order.id", "value": 1}},
                "paths": [[{"rel": "Order.items"}, {"rel": "OrderItem.order"}]],
            }
        }
    )
    result = handle.find(op, ORDERS, POSTGRES, "Order", port)
    assert result.execution.round_trips == 2  # the back-reference costs nothing
    item = _kids(result.nodes[0], "items")[0]
    assert _kid(item, "order") is result.nodes[0]


def test_find_materializes_family_variant_on_child_level_rows() -> None:
    port = QueuePort(
        [
            [{"id": 10, "name": "Alice"}],
            [
                {
                    "id": 1,
                    "name": "Rex",
                    "owner_id": 10,
                    "license_id": "L-100",
                    "indoor": None,
                    "bark_volume": 7,
                    "tusk_length": None,
                    "kind": "dog",
                }
            ],
        ]
    )
    op = deserialize(
        {
            "deepFetch": {
                "operand": {"eq": {"attr": "Person.id", "value": 10}},
                "paths": [[{"rel": "Person.animals"}]],
            }
        }
    )
    result = handle.find(op, ANIMAL, POSTGRES, "Person", port)
    animal = _kids(result.nodes[0], "animals")[0]
    assert animal.fields["familyVariant"] == "Dog"
    assert "kind" not in animal.fields


def test_find_history_groups_rows_into_chronologically_ordered_edge_pinned_graphs() -> None:
    port = QueuePort(
        [
            [
                {
                    "id": 1000,
                    "invoice_id": 100,
                    "amount": Decimal("75.00"),
                    "in_z": dt.datetime(2024, 4, 1, tzinfo=_UTC),
                    "out_z": INFINITY,
                },
                {
                    "id": 1000,
                    "invoice_id": 100,
                    "amount": Decimal("50.00"),
                    "in_z": dt.datetime(2024, 1, 1, tzinfo=_UTC),
                    "out_z": dt.datetime(2024, 4, 1, tzinfo=_UTC),
                },
            ]
        ]
    )
    op = deserialize(
        {
            "history": {
                "operand": {"eq": {"attr": "InvoiceLine.id", "value": 1000}},
                "asOfAttr": "InvoiceLine.processingDate",
            }
        }
    )
    result = handle.find_history(op, INVOICE, POSTGRES, "InvoiceLine", port)
    assert result.execution.round_trips == 1
    assert [g.pin["processingDate"] for g in result.graphs] == [
        dt.datetime(2024, 1, 1, tzinfo=_UTC),
        dt.datetime(2024, 4, 1, tzinfo=_UTC),
    ]
    assert [g.nodes[0].fields["amount"] for g in result.graphs] == [
        Decimal("50.00"),
        Decimal("75.00"),
    ]


def test_find_history_groups_two_distinct_rows_sharing_one_edge_into_one_graph() -> None:
    # Two DIFFERENT physical InvoiceLine rows (ids 1000 and 2000) sharing the
    # exact same processing edge (in_z) belong to the SAME milestone graph —
    # the "edge already seen" branch of the grouping loop (as opposed to the
    # "first row at this edge" branch the single-row-per-edge test above pins).
    port = QueuePort(
        [
            [
                {
                    "id": 1000,
                    "invoice_id": 100,
                    "amount": Decimal("50.00"),
                    "in_z": dt.datetime(2024, 1, 1, tzinfo=_UTC),
                    "out_z": dt.datetime(2024, 4, 1, tzinfo=_UTC),
                },
                {
                    "id": 2000,
                    "invoice_id": 100,
                    "amount": Decimal("25.00"),
                    "in_z": dt.datetime(2024, 1, 1, tzinfo=_UTC),
                    "out_z": dt.datetime(2024, 4, 1, tzinfo=_UTC),
                },
            ]
        ]
    )
    op = deserialize(
        {
            "history": {
                "operand": {"eq": {"attr": "InvoiceLine.invoiceId", "value": 100}},
                "asOfAttr": "InvoiceLine.processingDate",
            }
        }
    )
    result = handle.find_history(op, INVOICE, POSTGRES, "InvoiceLine", port)
    assert len(result.graphs) == 1
    assert [n.fields["id"] for n in result.graphs[0].nodes] == [1000, 2000]


def test_find_history_refuses_a_plan_carrying_deep_fetch_levels() -> None:
    policy = _MODELS["policy"]
    port = QueuePort([[]])
    op = deserialize(
        {
            "deepFetch": {
                "operand": {
                    "history": {"operand": {"all": {}}, "asOfAttr": "Policy.processingDate"}
                },
                "paths": [[{"rel": "Policy.coverages"}]],
            }
        }
    )
    with pytest.raises(ValueError, match="no deep-fetch levels"):
        handle.find_history(op, policy, POSTGRES, "Policy", port)
