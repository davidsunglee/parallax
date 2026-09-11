"""The conformance engine's model facts: how a case's model reference is
resolved before anything is formed from it.

Docker-free.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from parallax.conformance import case_format
from parallax.conformance._mechanism import model_facts
from parallax.conformance._mechanism.envelope import EngineError


def _synthetic(document: dict[str, object]) -> case_format.Case:
    return case_format.Case(
        path=Path("m-predicate-999-synthetic.yaml"),
        case_id="m-predicate-999",
        shape="read",
        tags=("m-predicate", "slice-snapshot-1"),
        model="models/orders.yaml",
        document=document,
    )


def test_load_case_metamodel_rejects_a_non_string_model() -> None:
    case = _synthetic({"model": 42})
    with pytest.raises(EngineError, match="`model` must be a string"):
        model_facts.load_case_metamodel(case)
