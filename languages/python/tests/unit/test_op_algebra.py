"""Operation-algebra node + serde unit tests (m-op-algebra).

The serde round-trip contract (`serialize(deserialize(x)) == x`) is proven over
every operation the corpus authors — reads and scenario/coherence read steps —
so every node kind in the read algebra (identities, comparisons, string/null/
membership, boolean + group, result-shaping, narrow, the nested value-object
family, navigation, deep fetch, and the temporal wrappers) round-trips through
the canonical single-key encoding. Structural rejection branches are pinned too.
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from conftest import case_document
from parallax.conformance import case_format
from parallax.core import op_algebra
from parallax.core.op_algebra import OperationError

pytestmark = pytest.mark.unit


def _operations() -> list[tuple[str, dict[str, Any]]]:
    """Every authored operation in the read algebra (aggregation deferred, out of claim)."""
    found: list[tuple[str, dict[str, Any]]] = []
    for case in case_format.load_cases():
        when: Any = case_document(case).get("when") or {}
        operation: Any = when.get("operation")
        if isinstance(operation, dict) and not _has_group_by(operation):
            found.append((case.case_id, cast("dict[str, Any]", operation)))
        for key in ("scenario", "coherence"):
            steps: Any = when.get(key)
            if not isinstance(steps, list):
                continue
            for index, step in enumerate(cast("list[Any]", steps)):
                if not isinstance(step, dict):
                    continue
                inner: Any = cast("dict[str, Any]", step).get("find")
                if isinstance(inner, dict) and not _has_group_by(inner):
                    found.append((f"{case.case_id}/{key}/{index}", cast("dict[str, Any]", inner)))
    return found


def _has_group_by(operation: Any) -> bool:
    """Whether an operation tree uses the deferred aggregation node (out of claim)."""
    return "groupBy" in str(operation)


_OPERATIONS = _operations()


@pytest.mark.parametrize("case_id, doc", _OPERATIONS, ids=[c for c, _ in _OPERATIONS])
def test_operation_serde_round_trip(case_id: str, doc: dict[str, Any]) -> None:
    node = op_algebra.deserialize(doc)
    assert op_algebra.serialize(node) == doc


def test_node_round_trip_from_python() -> None:
    node = op_algebra.And(
        operands=(
            op_algebra.Comparison(op="eq", attr="Order.id", value=42),
            op_algebra.Not(operand=op_algebra.NullCheck(op="isNull", attr="Order.sku")),
        )
    )
    assert op_algebra.deserialize(op_algebra.serialize(node)) == node


def test_string_match_case_insensitive_default_omitted() -> None:
    node = op_algebra.StringMatch(op="like", attr="Order.name", value="ada")
    assert op_algebra.serialize(node) == {"like": {"attr": "Order.name", "value": "ada"}}
    node_ci = op_algebra.StringMatch(
        op="like", attr="Order.name", value="ada", case_insensitive=True
    )
    like_body = cast("dict[str, Any]", op_algebra.serialize(node_ci)["like"])
    assert like_body["caseInsensitive"] is True


def test_order_key_direction_is_always_emitted() -> None:
    # The corpus authors `direction` explicitly, so serialization emits it back.
    doc: dict[str, Any] = {
        "orderBy": {"operand": {"all": {}}, "keys": [{"attr": "Order.id", "direction": "asc"}]}
    }
    assert op_algebra.serialize(op_algebra.deserialize(doc)) == doc


@pytest.mark.parametrize(
    "doc, message",
    cast(
        "list[tuple[object, str]]",
        [
            (["not-a-mapping"], "must be a mapping"),
            ({"eq": {}, "notEq": {}}, "exactly one key"),
            ({"eq": "not-a-mapping"}, "body must be a mapping"),
            ({"mystery": {}}, "unknown operation node"),
            ({"eq": {"attr": 1, "value": 2}}, "must be a string"),
            ({"in": {"attr": "Order.id", "values": []}}, "non-empty list"),
            ({"and": {"operands": [{"all": {}}]}}, "at least two"),
            ({"limit": {"operand": {"all": {}}, "count": 0}}, "positive integer"),
            ({"orderBy": {"operand": {"all": {}}, "keys": []}}, "non-empty list"),
            ({"narrow": {"entity": "Animal", "to": [], "operand": {"all": {}}}}, "non-empty list"),
            ({"not": {}}, "missing `operand`"),
        ],
    ),
)
def test_deserialize_rejects_malformed(doc: object, message: str) -> None:
    with pytest.raises(OperationError, match=message):
        op_algebra.deserialize(doc)


def test_deserialize_rejects_non_scalar_value() -> None:
    with pytest.raises(OperationError, match="scalar literal"):
        op_algebra.deserialize({"eq": {"attr": "Order.id", "value": {"nested": 1}}})
