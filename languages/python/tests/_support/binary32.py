"""Independent IEEE binary32 oracles: exact rational rounding, never a float parse."""

from __future__ import annotations

import math
import struct
from fractions import Fraction

_MOST_DIGITS = 9


def narrowed(value: float) -> float:
    """The binary32 value nearest the binary64 ``value``, widened exactly."""
    (result,) = struct.unpack("<f", struct.pack("<f", value))
    return result


def rounded_once(spelling: str) -> float:
    """The binary32 value nearest the exact decimal ``spelling``, ties to even."""
    exact = Fraction(spelling)
    if exact == 0:
        return -0.0 if spelling.startswith("-") else 0.0
    magnitude = abs(exact)
    exponent = magnitude.numerator.bit_length() - magnitude.denominator.bit_length()
    if magnitude < Fraction(2) ** exponent:
        exponent -= 1
    quantum = max(exponent, -126) - 23
    units = round(magnitude / Fraction(2) ** quantum)
    return math.copysign(math.ldexp(units, quantum), exact)


def shortest_spelling(value: float) -> str:
    """The fewest significant digits that round back to the binary32 ``value``."""
    assert narrowed(value) == value, f"{value!r} is not a binary32 value"
    for digits in range(1, _MOST_DIGITS + 1):
        spelling = f"{value:.{digits - 1}e}"
        if rounded_once(spelling) == value:
            return spelling
    raise AssertionError(f"no spelling of {value!r} within {_MOST_DIGITS} digits")
