"""Reads outside a writable attempt, eager and streamed, and what their results keep.

Each read delivers a whole subject, every root of which the read keeps:

* ``account``, the versioned non-temporal Column-layout account;
* ``charter`` (versioned, non-temporal), ``tt-charter``
  (Transaction-Time-Only), and ``bt-charter`` (bitemporal, read at one valid
  time): Relational Document Layout charters whose payloads nest value objects.

A read is ``standalone`` (``db.find`` or ``db.stream``, no transaction) or
``read-only`` (one ``db.read_only`` at the requested isolation, which a
standalone read ignores); Typed or Wire; and ``eager`` (the Snapshot and its
roots) or ``stream`` (every streamed root). Each cell is read in three passes,
after warm-up reads that fill the read plan cache:

* timed reads, untraced: the whole read, which an eager read's publication
  completes and a stream's last root ends, and a stream's first-root latency;
* traced reads: ``tracemalloc`` from a collected baseline gives the read's peak
  and, collected again with the result still held, the bytes the result keeps;
* one census: the gc-tracked objects the held result added, by type.
"""

import datetime as dt
import gc
import time
import tracemalloc
from collections import Counter
from collections.abc import Callable
from typing import Any

from _support import (
    EPOCH,
    INFINITY,
    NAMESPACE,
    Account,
    accounts,
    arguments,
    conditions,
    emit,
    observer,
    percentiles,
    pooled,
    provisioned,
    scoped,
)

from parallax.core import (
    Attr,
    Bitemporal,
    Document,
    DomainModel,
    Entity,
    Int32,
    TxTemporal,
    ValueObject,
    attr,
)


class Stop(ValueObject):
    port: Attr[str | None]
    berth: Attr[int | None]


class Route(ValueObject):
    name: Attr[str | None]
    stops: Attr[tuple[Stop, ...]]


class Charter(Entity, table="charter", namespace=NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)
    title: Attr[str | None] = attr(max_length=64)
    route: Attr[Route | None]
    legs: Attr[tuple[Stop, ...]]


class TtCharter(TxTemporal, table="tt_charter", namespace=NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    title: Attr[str | None] = attr(max_length=64)
    route: Attr[Route | None]
    legs: Attr[tuple[Stop, ...]]


class BtCharter(Bitemporal, table="bt_charter", namespace=NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    title: Attr[str | None] = attr(max_length=64)
    route: Attr[Route | None]
    legs: Attr[tuple[Stop, ...]]


MODEL = DomainModel(Account, Charter, TtCharter, BtCharter)
VALID_AT = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
SUBJECTS = {
    "account": Account.where(Account.all),
    "charter": Charter.where(Charter.all),
    "tt-charter": TtCharter.where(TtCharter.all),
    "bt-charter": BtCharter.where(BtCharter.all).as_of(valid_time=VALID_AT),
}
PLACEMENTS = ("standalone", "read-only")
REPRESENTATIONS = ("typed", "wire")
DELIVERIES = ("eager", "stream")


def _payload(key: int) -> dict[str, object]:
    return {
        "id": key,
        "title": f"charter-{key}",
        "route": {
            "name": f"route-{key % 17}",
            "stops": [{"port": f"port-{key % 11 + n}", "berth": n} for n in range(3)],
        },
        "legs": [{"port": f"leg-{key % 13 + n}", "berth": n} for n in range(4)],
    }


def fixtures(roots: int) -> dict[str, list[dict[str, object]]]:
    keys = range(1, roots + 1)
    return {
        f"{NAMESPACE}.Account": accounts(roots),
        f"{NAMESPACE}.Charter": [{**_payload(key), "version": 1} for key in keys],
        f"{NAMESPACE}.TtCharter": [
            {**_payload(key), "txStart": EPOCH, "txEnd": INFINITY} for key in keys
        ],
        f"{NAMESPACE}.BtCharter": [
            {
                **_payload(key),
                "validStart": EPOCH,
                "validEnd": INFINITY,
                "txStart": EPOCH,
                "txEnd": INFINITY,
            }
            for key in keys
        ],
    }


Read = Callable[[], tuple[list[object], float | None]]


def _cell(
    db: Any,
    query: Any,
    *,
    placement: str,
    representation: str,
    delivery: str,
    page: int,
    isolation: str,
) -> Read:
    """One read of the cell: everything it delivered, held, and a stream's
    first-root latency."""

    def deliver(reader: Any) -> tuple[list[object], float | None]:
        surface = reader if representation == "typed" else reader.wire
        if delivery == "eager":
            snapshot = surface.find(query)
            return [snapshot, *snapshot.results()], None
        started = time.perf_counter()
        first: float | None = None
        held: list[object] = []
        with surface.stream(query, batch_size=page) as stream:
            for root in stream:
                if first is None:
                    first = time.perf_counter() - started
                held.append(root)
        return held, first

    if placement == "standalone":
        return lambda: deliver(db)
    return lambda: db.read_only(deliver, isolation=isolation)


def _timed(read: Read, samples: int) -> dict[str, object]:
    elapsed: list[float] = []
    first: list[float] = []
    for _ in range(samples):
        started = time.perf_counter()
        _held, first_root = read()
        elapsed.append(time.perf_counter() - started)
        if first_root is not None:
            first.append(first_root)
        del _held
    return {
        "elapsedS": elapsed,
        "elapsed": percentiles(elapsed),
        "firstRootS": first,
        "firstRoot": percentiles(first) if first else None,
    }


def _traced(read: Read, samples: int) -> dict[str, object]:
    peaks: list[int] = []
    held_bytes: list[int] = []
    for _ in range(samples):
        gc.collect()
        tracemalloc.start()
        held, _first = read()
        peaks.append(tracemalloc.get_traced_memory()[1])
        gc.collect()
        held_bytes.append(tracemalloc.get_traced_memory()[0])
        del held
        tracemalloc.stop()
    return {
        "peakBytes": peaks,
        "peak": percentiles([float(value) for value in peaks]),
        "heldBytes": held_bytes,
        "held": percentiles([float(value) for value in held_bytes]),
    }


def _live_types() -> Counter[str]:
    gc.collect()
    return Counter(f"{type(o).__module__}.{type(o).__qualname__}" for o in gc.get_objects())


def _census(read: Read) -> tuple[int, dict[str, int]]:
    before = _live_types()
    held, _first = read()
    added = _live_types() - before
    count = len(held)
    del held
    return count, dict(sorted(added.items()))


def main() -> None:
    args = arguments(__doc__ or "")
    if args.smoke:
        roots, page, warmups, timed, traced = 20, 5, 1, 2, 1
    else:
        roots, page, warmups, timed, traced = 2000, 500, 3, 15, 5
    runs: list[dict[str, object]] = []
    with provisioned(fixtures(roots), MODEL) as run, observer(run) as control:
        with scoped(pooled(run, 1), MODEL) as db:
            for subject, query in SUBJECTS.items():
                for placement in PLACEMENTS:
                    for representation in REPRESENTATIONS:
                        for delivery in DELIVERIES:
                            read = _cell(
                                db,
                                query,
                                placement=placement,
                                representation=representation,
                                delivery=delivery,
                                page=page,
                                isolation=args.isolation,
                            )
                            for _ in range(warmups):
                                read()
                            timing = _timed(read, timed)
                            memory = _traced(read, traced)
                            held, census = _census(read)
                            runs.append(
                                {
                                    "subject": subject,
                                    "placement": placement,
                                    "representation": representation,
                                    "delivery": delivery,
                                    "rootsDelivered": held - (delivery == "eager"),
                                    "timing": timing,
                                    "memory": memory,
                                    "census": census,
                                }
                            )
        report = {
            "driver": "read_retention",
            "conditions": conditions(
                control,
                args.isolation,
                roots=roots,
                pageSize=page,
                warmups=warmups,
                timedReads=timed,
                tracedReads=traced,
                subjects=tuple(SUBJECTS),
                placements=PLACEMENTS,
                representations=REPRESENTATIONS,
                deliveries=DELIVERIES,
                pool=1,
                held="an eager read holds its Snapshot and roots; a stream holds every root",
                memory=(
                    "tracemalloc per traced read from a collected baseline; the census counts "
                    "gc-tracked objects by type"
                ),
            ),
            "runs": runs,
        }
    emit(report, args.out)


if __name__ == "__main__":
    main()
