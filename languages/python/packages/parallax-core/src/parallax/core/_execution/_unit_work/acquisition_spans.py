from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Final

from parallax.core._execution._unit_work.ranges import DeferredRange
from parallax.core._execution._unit_work.row_acquisition import CoverageReadKey
from parallax.core.internal.base import ManagedValue

__all__ = ["AcquisitionSpan", "form_spans"]


_WRITES_PER_SPAN: Final = 32
"""The most deferred writes one acquisition span holds (`m-unit-work` *Shared
coverage acquisition*): how many objects' coverage can be read ahead of their
writes' turns. It bounds objects, not the parts or rows their reads return.
The ready writes of a span execute as one Write Group, so it is never more
than the Write Group bound."""


@dataclass(frozen=True, slots=True, init=False)
class AcquisitionSpan:
    """Consecutive deferred writes of one mutation phase, one or more, whose
    coverage is acquired together (`m-unit-work` *Shared coverage
    acquisition*): ``ranges`` share one read key and each names an object no
    other does. Each binds once the coverage it needs is read, and the leading
    ready writes of what remains execute and complete as one Write Group.

    Only :func:`form_spans` builds one."""

    ranges: tuple[DeferredRange, ...]

    @property
    def read_key(self) -> CoverageReadKey:
        """The read every range of the span shares."""
        return self.ranges[0].read_key


def form_spans(ranges: Iterable[DeferredRange]) -> Iterator[AcquisitionSpan]:
    """``ranges``, an unbroken run of consecutive deferred writes, as the
    acquisition spans they form, in order: each span ends at the bound, before
    a range whose read key differs from its own, or before a range of an
    object it already holds."""
    held: list[DeferredRange] = []
    objects: set[ManagedValue] = set()
    for deferred in ranges:
        if held and (
            len(held) == _WRITES_PER_SPAN
            or deferred.read_key != held[0].read_key
            or deferred.key_value in objects
        ):
            yield _span(tuple(held))
            held.clear()
            objects.clear()
        held.append(deferred)
        objects.add(deferred.key_value)
    if held:
        yield _span(tuple(held))


def _span(ranges: tuple[DeferredRange, ...]) -> AcquisitionSpan:
    span = object.__new__(AcquisitionSpan)
    object.__setattr__(span, "ranges", ranges)
    return span
