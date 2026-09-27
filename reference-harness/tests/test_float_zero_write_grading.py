"""Write grading observes the sign of a float zero at a declared float position.

The witnesses author negative zero and negative underflow at both float widths,
as scalar columns and as value-object leaves, and their goldens bind the positive
zero the canonical encoding produces. Every layer before the database compares
the write input's derived values with those binds, so an encoding that keeps the
negative sign must fail there rather than reach a provider.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from reference_harness import portable_literal
from reference_harness.case import load_case, load_model
from reference_harness.case_assertions import CaseFailure, write_value_equal
from reference_harness.case_runner import run_case
from reference_harness.document_codec import encode_document

_COMPATIBILITY_ROOT = Path(__file__).resolve().parents[2] / "core" / "compatibility"

_WITNESSES = (
    "m-core-009-float-negative-underflow-writes-positive-zero",
    "m-core-010-float-negative-zero-writes-positive-zero",
    "m-document-codec-015-write-insert-negative-underflow-leaf-stores-positive-zero",
    "m-document-codec-016-write-insert-negative-zero-leaf-stores-positive-zero",
)
_DIALECTS = ("postgres", "mariadb")


class _DatabaseReachedError(Exception):
    pass


class _UnreachableDb:
    """A provider whose every member signals that the runner reached the database."""

    def __init__(self, dialect: str) -> None:
        self.dialect = dialect

    def __getattr__(self, name: str) -> Any:
        raise _DatabaseReachedError(name)


def _witness(stem: str) -> Any:
    return load_case(_COMPATIBILITY_ROOT, _COMPATIBILITY_ROOT / "cases" / f"{stem}.yaml")


def _keeping_negative_float_zero(
    canonicalize: Callable[[Any, str], Any],
) -> Callable[[Any, str], Any]:
    def canonicalize_keeping_sign(value: Any, neutral_type: str) -> Any:
        encoded = canonicalize(value, neutral_type)
        if neutral_type in ("float32", "float64") and encoded == 0:
            return -0.0
        return encoded

    return canonicalize_keeping_sign


@pytest.mark.parametrize("dialect", _DIALECTS)
@pytest.mark.parametrize("stem", _WITNESSES)
def test_witness_passes_every_layer_before_the_database(stem: str, dialect: str) -> None:
    with pytest.raises(_DatabaseReachedError):
        run_case(_witness(stem), _UnreachableDb(dialect))


@pytest.mark.parametrize("dialect", _DIALECTS)
@pytest.mark.parametrize("stem", _WITNESSES)
def test_an_encoding_keeping_negative_zero_fails_before_the_database(
    stem: str, dialect: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        portable_literal,
        "canonicalize",
        _keeping_negative_float_zero(portable_literal.canonicalize),
    )
    with pytest.raises(CaseFailure, match="neutral write input value"):
        run_case(_witness(stem), _UnreachableDb(dialect))


def test_an_undeclared_document_key_compares_as_a_json_value() -> None:
    profile = (
        load_model(_COMPATIBILITY_ROOT, "models/document-codec.yaml")
        .entity("parallax.compatibility.Sample")
        .value_object_by_name("profile")
    )
    derived = encode_document(profile, {"ratio": -0.0, "note": -0.0})
    assert write_value_equal(derived, {"ratio": 0.0, "note": 0.0, "entries": []})
    assert not write_value_equal(derived, {"ratio": -0.0, "note": 0.0, "entries": []})
