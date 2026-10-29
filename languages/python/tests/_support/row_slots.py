from __future__ import annotations

from collections.abc import Callable
from typing import cast

from parallax.core.write_plan.payload import RowSlots
from parallax.core.write_plan.steps import WriteRow

__all__ = ["observed_slots"]


class _ObservedSlots:
    __slots__ = ("_observe", "_slots")

    def __init__(self, slots: RowSlots, observe: Callable[[WriteRow], None]) -> None:
        self._slots = slots
        self._observe = observe

    def __getattr__(self, name: str) -> object:
        return getattr(self._slots, name)

    def cells(self, write_row: WriteRow) -> tuple[object, ...]:
        self._observe(write_row)
        return self._slots.cells(write_row)


def observed_slots(slots: RowSlots, observe: Callable[[WriteRow], None]) -> RowSlots:
    """``slots`` handing each row to ``observe`` before gathering its cells,
    so a test sees, and may refuse, every row lowering prepares."""
    return cast("RowSlots", _ObservedSlots(slots, observe))
