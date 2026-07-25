"""``parse_type_spelling`` / ``format_type_spelling`` totality over the unbounded
``m-core`` decimal precision domain (m-descriptor "Type spellings").

``m-core`` places no upper bound on ``Decimal`` precision, so both directions
must be total for a parameter pair of any digit count, not merely the ones
CPython's int/str conversion guard (``sys.int_max_str_digits``) allows through
a single unbounded ``int()``/``str()`` call.
"""

from __future__ import annotations

import pytest

from parallax.core.base import Decimal
from parallax.core.descriptor.type_spelling import format_type_spelling, parse_type_spelling

pytestmark = pytest.mark.unit

# Comfortably above CPython's default int/str conversion guard
# (``sys.int_info.default_max_str_digits``, 4300), so a parameter pair this
# long only round-trips if the conversion is chunked rather than direct. Built
# by exponentiation, never by parsing a 5000-character literal, so the test
# itself does not trip the guard it is proving the production code avoids.
_HUGE_VALUE = 10**5000 - 1
_HUGE_DIGITS = "9" * 5000


def test_a_huge_precision_spelling_parses_to_its_structured_decimal() -> None:
    spelling = f"decimal({_HUGE_DIGITS},2)"
    assert parse_type_spelling(spelling) == Decimal(_HUGE_VALUE, 2)


def test_a_huge_precision_decimal_formats_to_its_canonical_spelling() -> None:
    neutral = Decimal(_HUGE_VALUE, 2)
    assert format_type_spelling(neutral) == f"decimal({_HUGE_DIGITS},2)"


def test_a_huge_precision_spelling_round_trips_through_parse_and_format() -> None:
    spelling = f"decimal({_HUGE_DIGITS},{_HUGE_DIGITS})"
    neutral = parse_type_spelling(spelling)
    assert neutral is not None
    assert format_type_spelling(neutral) == spelling


def test_a_huge_scale_still_enforces_the_scale_not_exceeding_precision_bound() -> None:
    spelling = f"decimal(1,{_HUGE_DIGITS})"
    assert parse_type_spelling(spelling) is None


def test_a_zero_scale_formats_to_the_single_digit_zero() -> None:
    # `scale` may be exactly 0 (unlike `precision`, which is always >= 1) —
    # the chunked int-to-digits conversion's own zero case.
    assert format_type_spelling(Decimal(_HUGE_VALUE, 0)) == f"decimal({_HUGE_DIGITS},0)"


@pytest.mark.parametrize("spelling", ["decimal(0,9)", "decimal(2,5)", "decimal(09,2)"])
def test_the_canonical_digit_and_bounds_rules_still_reject(spelling: str) -> None:
    assert parse_type_spelling(spelling) is None
