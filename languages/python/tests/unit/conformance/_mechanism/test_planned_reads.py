"""The compile lanes' planned read: production's own read over a database
holding no rows.

Docker-free.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from parallax.conformance import case_format
from parallax.conformance._lanes.reads import compile_read_case
from parallax.conformance._mechanism.envelope import EngineError


def _read_case(when: dict[str, object]) -> case_format.Case:
    return case_format.Case(
        path=Path("m-read-lock-999-synthetic.yaml"),
        case_id="m-read-lock-999",
        shape="read",
        tags=("m-read-lock", "slice-snapshot-1"),
        model="models/orders.yaml",
        document={"model": "models/orders.yaml", "when": when},
    )


def test_a_read_refused_inside_its_transaction_is_the_case_error() -> None:
    case = _read_case(
        {
            "uow": {"concurrency": "locking"},
            "objectQuery": {
                "target": "parallax.compatibility.Order",
                "predicate": {"eq": {"attr": "parallax.compatibility.Order.missing", "value": 1}},
            },
        }
    )
    with pytest.raises(EngineError, match=r"m-read-lock-999-synthetic\.yaml"):
        compile_read_case(case, "postgres")
