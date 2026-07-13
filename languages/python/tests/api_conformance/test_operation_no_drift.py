"""Operation no-drift guard (m-api-conformance).

Each idiomatic public-API statement the suite authors must serialize to the exact
``m-op-algebra`` operation the mirrored corpus case authors — the developer
surface cannot drift from the graded protocol. The builders here are the source of
truth for the ``api_suite.EXAMPLES`` snippets; the guard compares
``statement.serialize()`` to the case's ``when.operation``.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from example_models import Order

from conftest import case_document
from parallax.conformance import case_format
from parallax.core import Statement

pytestmark = pytest.mark.api_conformance

# case id -> the idiomatic statement that must serialize to the case's operation.
BUILDERS: dict[str, Callable[[], Statement]] = {
    "m-op-algebra-002": lambda: Order.where(Order.id == 42),
    "m-op-algebra-009": lambda: Order.where(Order.sku.is_null()),
    "m-op-algebra-011": lambda: Order.where(Order.sku.like("A-%")),
    "m-op-algebra-013": lambda: Order.where(Order.sku.starts_with("A-")),
    "m-op-algebra-018": lambda: Order.where(Order.id.in_([1, 2, 42])),
    "m-op-algebra-020": lambda: Order.where(Order.active.is_(True), Order.qty > 10),
    "m-op-algebra-021": lambda: Order.where((Order.qty < 10) | (Order.qty > 25)),
    "m-op-algebra-024": lambda: Order.where(
        (Order.qty >= 25) | (Order.qty <= 5), Order.active.is_(True)
    ),
    "m-op-algebra-025": lambda: Order.where(
        (Order.qty >= 25) | ((Order.qty <= 5) & Order.active.is_(True))
    ),
    "m-op-algebra-032": lambda: (
        Order.where().order_by(Order.active.desc(), Order.qty.asc()).limit(2)
    ),
}

_CASES = {c.case_id: c for c in case_format.load_cases()}


@pytest.mark.parametrize("case_id", sorted(BUILDERS), ids=sorted(BUILDERS))
def test_idiomatic_statement_serializes_to_the_corpus_operation(case_id: str) -> None:
    expected = case_document(_CASES[case_id])["when"]["operation"]
    assert BUILDERS[case_id]().serialize() == expected


def test_expression_rejects_bool_misuse() -> None:
    with pytest.raises(TypeError, match="no truth value"):
        bool(Order.id == 1)  # a Predicate has no truth value
    with pytest.raises(TypeError, match="no truth value"):
        bool(Order.sku)  # a bare AttributeExpr has no truth value
