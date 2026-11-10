"""The high-water bound on decoding a bytes cell (`cost` class)."""

from __future__ import annotations

import sys
import tracemalloc
from collections.abc import Callable
from typing import Final

from parallax.core.internal.dialect import decode_bytes_cell
from tests.unit.memory_instruments import (
    Span,
    high_water,
    in_a_child_interpreter,
    serve_one_measurement,
)

_OCTETS: Final = 1 << 16


def _decoding(cell: str) -> Span:
    def decode(opened: Callable[[], None], closed: Callable[[], None]) -> None:
        opened()
        decoded = decode_bytes_cell(cell)
        closed()
        assert decoded == b"\xab" * _OCTETS

    return decode


@in_a_child_interpreter
def test_decoding_a_bytes_cell_rises_less_than_the_length_of_the_cell() -> None:
    cell = "ab" * _OCTETS
    tracemalloc.start()
    try:
        rise = high_water(_decoding(cell))
    finally:
        tracemalloc.stop()
    assert rise < len(cell)


if __name__ == "__main__":
    serve_one_measurement(sys.argv[1])
