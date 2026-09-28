"""Independent IEEE binary32 oracles: exact rational rounding, never a float parse."""

from __future__ import annotations

import functools
import math
import random
import struct
from fractions import Fraction

_MOST_DIGITS = 9
_RANDOM_WITNESSES = 1_000


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


@functools.cache
def rounding_witnesses() -> tuple[str, ...]:
    """Decimal spellings that grade a rule rounding text once to binary32.

    Each names a finite binary32 value: spellings whose binary64 parse lands
    exactly on a binary32 midpoint, in the normal and the subnormal range, the
    ends of both ranges and both zeros, and the shortest spellings of seeded
    random finite values.
    """
    generator = random.Random(188)
    random_values: list[float] = []
    while len(random_values) < _RANDOM_WITNESSES:
        (value,) = struct.unpack("<f", generator.getrandbits(32).to_bytes(4, "little"))
        if math.isfinite(value):
            random_values.append(value)
    edges = (math.ldexp(1, -149), math.ldexp(1, -126) - math.ldexp(1, -149), math.ldexp(1, -126))
    largest = math.ldexp(2**24 - 1, 104)
    return (
        "7.038531e-26",
        "-7.038531e-26",
        "7.0064923216240854e-46",
        "-7.0064923216240854e-46",
        "0",
        "-0",
        "0.0",
        "-0.0",
        *(shortest_spelling(sign * value) for value in (*edges, largest) for sign in (1, -1)),
        *(shortest_spelling(value) for value in random_values),
    )
