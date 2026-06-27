"""Unit tests for exact-Decimal row comparison + opt-in tolerance.

The harness must compare result rows WITHOUT routing numerics through ``float``:
a ``decimal(p,s)`` money column has to compare exactly to the cent, and the
type of a value must not depend on whether it happens to be whole. Inherently
inexact results (stddev / variance / some avg) cannot be authored exactly, so a
case MAY declare a ``tolerance`` and the comparison becomes ``abs(a-b) <= tol``
in Decimal space (the only cross-dialect-robust answer for irrationals).
"""

from __future__ import annotations

from decimal import Decimal

from reference_harness.case_runner import _rows_equal, _scalars_equal, _to_decimal


def test_distinct_high_precision_decimals_are_not_equal() -> None:
    # Two different cent amounts beyond float's ~15-16 significant digits. float()
    # collapses both to the SAME double; exact Decimal comparison must not.
    a = [{"amount": Decimal("1234567890123456.78")}]
    b = [{"amount": Decimal("1234567890123456.79")}]
    assert not _rows_equal(a, b)


def test_decimal_int_and_float_forms_compare_equal() -> None:
    # A whole-valued Decimal, an int, and a float spelling of the same number
    # are equal — without the value-dependent int/float type flip.
    assert _rows_equal([{"n": Decimal("2.0")}], [{"n": 2}])
    assert _rows_equal([{"n": 2}], [{"n": 2.0}])
    assert _rows_equal([{"p": Decimal("10.50")}], [{"p": 10.5}])


def test_yaml_float_normalizes_without_float_noise() -> None:
    # A DB-exact Decimal('0.1') must match a YAML float 0.1 (normalize via
    # Decimal(str(x)), not Decimal(float) which would inject float noise) ...
    assert _scalars_equal(Decimal("0.1"), 0.1, None)
    # ... but a genuinely different decimal must NOT match exactly.
    assert not _scalars_equal(Decimal("0.10000001"), 0.1, None)


def test_to_decimal_keeps_bool_and_none_out_of_numeric_space() -> None:
    assert _to_decimal(True) is True
    assert _to_decimal(None) is None
    assert _scalars_equal(True, True, None)
    assert not _scalars_equal(True, 1, None)  # bool is not coerced into 1


def test_tolerance_allows_inexact_match() -> None:
    actual = Decimal("1.5811388300841897")  # an irrational stddev as Postgres returns it
    authored = 1.5811388301  # the human-readable rounded value in the fixture
    assert not _scalars_equal(actual, authored, None)  # exact: they differ
    assert _scalars_equal(actual, authored, Decimal("1e-9"))  # tolerant: match


def test_tolerance_still_catches_real_differences() -> None:
    # A tolerant case does not become a free pass: integral columns stay
    # effectively exact (an off-by-one is ~1e9x the tolerance).
    assert not _scalars_equal(Decimal("2"), 3, Decimal("1e-9"))
    assert not _rows_equal([{"c": 5}], [{"c": 6}], tolerance=Decimal("1e-9"))


def test_order_insensitive_multiset() -> None:
    assert _rows_equal([{"id": 1}, {"id": 2}], [{"id": 2}, {"id": 1}])
    assert not _rows_equal([{"id": 1}], [{"id": 1}, {"id": 2}])
