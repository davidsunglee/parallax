from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from types import TracebackType
from typing import Final, Self

from parallax.core._execution._unit_work.ranges import DeferredRange
from parallax.core._execution._unit_work.row_acquisition import (
    AcquireRows,
    CoverageReadKey,
    CoverageReadRequest,
    CoverageTerm,
    consume_completion,
    consume_coverage,
)
from parallax.core._execution._unit_work.strategy import AuditDecoration
from parallax.core._execution._unit_work.write_plan import WriteGroup
from parallax.core.internal.base import ManagedValue
from parallax.core.internal.planned_step.keys import ObjectStateKey
from parallax.core.internal.planned_step.payload import WritePayloadPreparer
from parallax.core.internal.planned_step.predecessor_rows import PredecessorRows
from parallax.core.internal.planned_step.steps import PlannedStep
from parallax.core.internal.planned_step.write_effects import BoundRange, TemporalWriteOwnership

__all__ = ["AcquisitionSpan", "SpanWriteGroups", "form_spans", "write_groups"]


_WRITES_PER_SPAN: Final = 32
"""The most deferred writes one acquisition span holds (`m-unit-work` *Shared
coverage acquisition*): how many objects' coverage can be read ahead of their
writes' turns. It bounds objects, not the parts or rows their reads return.
The ready writes of a span execute as one Write Group, so it is never more
than the Write Group bound."""

_PARTS_PER_READ: Final = 64
"""The most uncovered parts one coverage read names (`m-sql` *Requested
ranges*): each uncovered Valid-Time interval, and each Transaction-Time-Only
current row, is one. More parts are read by several reads, all before the
range binds. Past this many, one statement's cost grows faster than the round
trip a larger statement saves."""


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


def write_groups(
    span: AcquisitionSpan,
    *,
    acquire_rows: AcquireRows,
    current: Callable[[ObjectStateKey, int], bool],
    ownership: TemporalWriteOwnership,
    audit: AuditDecoration,
    payloads: WritePayloadPreparer,
) -> SpanWriteGroups:
    """The Write Groups ``span``'s deferred writes execute in, read through
    ``acquire_rows``, each retained starting row reused only while ``current``
    judges it current, and bound under ``ownership``, ``audit``, and
    ``payloads``."""
    return SpanWriteGroups(span, _Invocation(acquire_rows, current, ownership, audit, payloads))


@dataclass(frozen=True, slots=True)
class _Invocation:
    """What one :class:`SpanWriteGroups` reads, judges, and binds through."""

    acquire_rows: AcquireRows
    current: Callable[[ObjectStateKey, int], bool]
    ownership: TemporalWriteOwnership
    audit: AuditDecoration
    payloads: WritePayloadPreparer


@dataclass(slots=True)
class _RangeAcquisition:
    """One deferred range between its span's first advance and its binding:
    the coverage it needs read until packing takes it, whether every read
    naming its parts succeeded, and the rows it binds to — the retained
    starting rows it reuses, then the rows each of its coverage reads returned,
    in read order."""

    range: DeferredRange
    missing_term: CoverageTerm | None = None
    ready: bool = False
    rows: list[PredecessorRows] | None = None


class SpanWriteGroups:
    """The deferred writes of one acquisition span a flush binds from its
    turn, bound only as the flush asks for them: a scoped, single-pass
    iterator of the Write Groups they execute in, in order.

    The first advance takes the ranges from the span, keeping no reference to
    it, completes every retained starting row each range holds that is still
    current, and derives once the uncovered parts nothing each range holds
    covers. Those parts are packed, in range order — a Bitemporal range's in
    Valid-Time order, a Transaction-Time-Only range's one current row whole —
    into reads naming at most :data:`_PARTS_PER_READ` each, and a range is
    ready once the read naming its last part succeeded, whatever the reads
    returned; a range with no uncovered part is ready at once, but never binds
    ahead of an earlier range that is not. Each advance reads only while the
    next range is not ready, each read's rows sealed as Predecessor Rows of the
    object whose key each stored row holds while its resources are live. It
    then binds that range and every ready range following it, up to the first
    that is not, under the ownership as it stands then, and answers them as one
    Write Group. Binding reads nothing, nothing is bound ahead of the advance
    asking for it, and nothing is executed or published: the flush executes and
    completes each group before advancing.

    Exhausting the iterator, leaving its scope, or a failure of its own drops
    every row reference and dependency it still holds, without suppressing or
    replacing the failure; what a group carries keeps its own lifetime.
    """

    __slots__ = ("_acquisitions", "_by_key", "_invocation", "_reads", "_span")

    def __init__(self, span: AcquisitionSpan, invocation: _Invocation, /) -> None:
        self._span: AcquisitionSpan | None = span
        self._invocation: _Invocation | None = invocation
        self._acquisitions: deque[_RangeAcquisition] = deque()
        self._by_key: dict[ManagedValue, _RangeAcquisition] | None = None
        self._reads: Iterator[tuple[CoverageReadRequest, list[_RangeAcquisition]]] | None = None

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._release()

    def __iter__(self) -> Self:
        return self

    def __next__(self) -> WriteGroup:
        invocation = self._invocation
        if invocation is None:
            raise StopIteration
        try:
            return self._bind_next_group(invocation)
        except BaseException:
            self._release()
            raise

    def _bind_next_group(self, invocation: _Invocation) -> WriteGroup:
        if self._span is not None:
            self._prepare(invocation)
        acquisitions = self._acquisitions
        if not acquisitions:
            raise StopIteration
        while not acquisitions[0].ready:
            self._read(invocation)
        return WriteGroup.from_members(
            self._bind_ready(invocation), effect_shape=invocation.payloads.effect_shape
        )

    def _prepare(self, invocation: _Invocation) -> None:
        span = self._span
        assert span is not None  # prepared once, on the first advance
        self._span = None
        acquisitions = self._acquisitions
        for deferred in span.ranges:
            # Each range's completed rows are held only by its acquisition,
            # which a failure releases, never by a local a later completion's
            # failure frame would keep.
            acquisition = _RangeAcquisition(deferred)
            acquisitions.append(acquisition)
            _prepare_range(acquisition, invocation)
        if not all(acquisition.ready for acquisition in acquisitions):
            self._reads = _pack_reads(deque(acquisitions), span.read_key)

    def _read(self, invocation: _Invocation) -> None:
        reads = self._reads
        assert reads is not None  # a range not yet ready waits for a packed read
        by_key = self._by_key
        if by_key is None:
            by_key = self._by_key = {
                acquisition.range.key_value: acquisition for acquisition in self._acquisitions
            }
        request, finished = next(reads)
        _transfer(by_key, invocation.acquire_rows(request, consume_coverage))
        for acquisition in finished:
            acquisition.ready = True

    def _bind_ready(
        self, invocation: _Invocation
    ) -> Iterator[tuple[BoundRange, tuple[PlannedStep, ...]]]:
        acquisitions = self._acquisitions
        while acquisitions and acquisitions[0].ready:
            yield self._bind_head(invocation)

    def _bind_head(self, invocation: _Invocation) -> tuple[BoundRange, tuple[PlannedStep, ...]]:
        head = self._acquisitions[0]
        bound = head.range.bind(
            head.rows or (),
            ownership=invocation.ownership,
            audit=invocation.audit,
            payloads=invocation.payloads,
        )
        self._acquisitions.popleft()
        by_key = self._by_key
        if by_key is not None:
            del by_key[head.range.key_value]
        head.rows = None
        return bound, bound.steps

    def _release(self) -> None:
        for acquisition in self._acquisitions:
            acquisition.rows = acquisition.missing_term = None
        self._acquisitions.clear()
        self._by_key = None
        self._reads = None
        self._span = None
        self._invocation = None


def _prepare_range(acquisition: _RangeAcquisition, invocation: _Invocation) -> None:
    deferred = acquisition.range
    completion = deferred.take_retained_completion(invocation.current)
    reused = None if completion is None else invocation.acquire_rows(completion, consume_completion)
    if reused is not None:
        acquisition.rows = [reused]
    acquisition.missing_term = deferred.missing_term(reused)
    acquisition.ready = acquisition.missing_term is None


def _pack_reads(
    acquisitions: deque[_RangeAcquisition], read_key: CoverageReadKey
) -> Iterator[tuple[CoverageReadRequest, list[_RangeAcquisition]]]:
    """Reads by ``read_key`` of every uncovered part ``acquisitions`` still
    need, in order, each naming at most :data:`_PARTS_PER_READ` parts and
    beside the acquisitions whose last part it names. A term of one part is
    placed whole; an object whose Valid-Time windows do not fit what remains
    of one read continues in the next. Each term is released from its
    acquisition, and each acquisition from ``acquisitions``, as packing takes
    it."""
    terms: list[CoverageTerm] = []
    finished: list[_RangeAcquisition] = []
    room = _PARTS_PER_READ
    while acquisitions:
        acquisition = acquisitions.popleft()
        term, acquisition.missing_term = acquisition.missing_term, None
        if term is None:
            continue
        count = term.part_count
        first = 0
        while first < count:
            if not room:
                yield CoverageReadRequest(read_key, tuple(terms)), finished
                terms, finished, room = [], [], _PARTS_PER_READ
            taken = min(room, count - first)
            terms.append(term if taken == count else _parts(term, first, first + taken))
            first += taken
            room -= taken
        finished.append(acquisition)
    if terms:
        yield CoverageReadRequest(read_key, tuple(terms)), finished


def _parts(term: CoverageTerm, start: int, stop: int) -> CoverageTerm:
    windows = term.valid_time_windows
    assert windows is not None  # only a term of several parts is split, and those are windows
    return CoverageTerm(term.key_value, windows[start:stop])


def _transfer(
    by_key: dict[ManagedValue, _RangeAcquisition], evidence: dict[ManagedValue, PredecessorRows]
) -> None:
    """Hand each object's rows of one coverage read to its range's
    acquisition, taking each from ``evidence`` as it goes and dropping what is
    left however it leaves."""
    rows: PredecessorRows | None = None
    try:
        while evidence:
            key, rows = evidence.popitem()
            acquisition = by_key.get(key)
            assert acquisition is not None  # a coverage read returns only rows of objects it names
            if acquisition.rows is None:
                acquisition.rows = [rows]
            else:
                acquisition.rows.append(rows)
    finally:
        evidence.clear()
        del evidence, rows
