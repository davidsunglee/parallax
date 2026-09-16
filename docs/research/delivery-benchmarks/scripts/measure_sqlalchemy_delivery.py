from __future__ import annotations

import datetime as dt
import gc
import json
import platform
import statistics
import sys
import time
import tracemalloc
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from decimal import Decimal
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any, Final

PYTHON_ROOT: Final = Path(__file__).resolve().parents[4] / "languages" / "python"
sys.path.insert(0, str(PYTHON_ROOT))

import sqlalchemy  # noqa: E402
from psycopg.types.datetime import TimestamptzLoader  # noqa: E402
from sqlalchemy import (  # noqa: E402
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    create_engine,
    event,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402
from sqlalchemy.orm import (  # noqa: E402
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    selectinload,
)
from sqlalchemy.util import has_compiled_ext  # noqa: E402

from parallax.conformance.profile import profile_for  # noqa: E402
from parallax.conformance.story_models import ORDERS_MODEL, POSITION_MODEL  # noqa: E402
from parallax.core.entity._model import model_of  # noqa: E402
from tests._support.mirrored_models import DOCUMENT_LAYOUT_MODEL  # noqa: E402

ROOTS: Final = 200
FANOUT: Final = 4
PAGE_SIZES: Final = (1, 8, 32, 128)
WARMUPS: Final = 3
REPEATS: Final = 5


@dataclass(frozen=True)
class Timing:
    wall_ms: float
    cpu_ms: float
    first_ms: float
    roots_per_second: float
    cpu_share: float
    statements: int


@dataclass(frozen=True)
class Memory:
    retained_bytes: int
    peak_bytes: int
    transient_bytes: int


@dataclass(frozen=True)
class Reading:
    workload: str
    delivery: str
    page_size: int | None
    roots: int
    timing: Timing
    memory: Memory


class Base(DeclarativeBase):
    pass


class OrderItem(Base):
    __tablename__ = "order_item"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    sku: Mapped[str] = mapped_column(String)
    quantity: Mapped[int] = mapped_column(Integer)
    shipped_on: Mapped[dt.date] = mapped_column(Date)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    sku: Mapped[str] = mapped_column(String)
    qty: Mapped[int] = mapped_column(Integer)
    price: Mapped[Decimal] = mapped_column(Numeric)
    active: Mapped[bool] = mapped_column(Boolean)
    ordered_on: Mapped[dt.date] = mapped_column(Date)
    items: Mapped[list[OrderItem]] = relationship(
        OrderItem,
        lazy="raise",
        order_by=OrderItem.id,
        overlaps="items_by_ship_date",
    )
    items_by_ship_date: Mapped[list[OrderItem]] = relationship(
        OrderItem,
        lazy="raise",
        order_by=(OrderItem.shipped_on, OrderItem.id),
        overlaps="items",
        viewonly=True,
    )


class Trip(Base):
    __tablename__ = "trip"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    traveler_id: Mapped[int] = mapped_column(ForeignKey("traveler.id"))
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)


class Traveler(Base):
    __tablename__ = "traveler"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    trips: Mapped[list[Trip]] = relationship(Trip, lazy="raise", order_by=Trip.id)


class Ledger(Base):
    __tablename__ = "ledger"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)

    __mapper_args__ = {"version_id_col": version, "version_id_generator": False}


class Position(Base):
    __tablename__ = "position"

    id: Mapped[int] = mapped_column("pos_id", BigInteger, primary_key=True)
    account_number: Mapped[str] = mapped_column("acct_num", String)
    value: Mapped[Decimal] = mapped_column("val", Numeric)
    valid_start: Mapped[dt.datetime] = mapped_column("from_z", DateTime(timezone=True))
    valid_end: Mapped[dt.datetime] = mapped_column("thru_z", DateTime(timezone=True))
    tx_start: Mapped[dt.datetime] = mapped_column("in_z", DateTime(timezone=True))
    tx_end: Mapped[dt.datetime] = mapped_column("out_z", DateTime(timezone=True))


@dataclass(frozen=True)
class Workload:
    name: str
    statement: Any
    validate: Callable[[Sequence[object]], None]


class _Infinity:
    __slots__ = ()

    def __repr__(self) -> str:
        return "INFINITY"


INFINITY: Final = _Infinity()


class _InfinityTimestamptzLoader(TimestamptzLoader):
    def load(self, data: object) -> object:
        if bytes(data) == b"infinity":  # type: ignore[arg-type]
            return INFINITY
        return super().load(data)  # type: ignore[arg-type]


def _baseline_module() -> Any:
    path = Path(__file__).resolve().parent / "measure_parallax_delivery.py"
    spec = spec_from_file_location("cor_146_measure_delivery", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load the matched Parallax fixtures from {path}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class StatementCounter:
    def __init__(self) -> None:
        self._active: list[int] | None = None

    def install(self, engine: Any) -> None:
        @event.listens_for(engine, "before_cursor_execute")
        def count_statement(
            connection: object,
            cursor: object,
            statement: str,
            parameters: object,
            context: object,
            executemany: bool,
        ) -> None:
            del connection, cursor, statement, parameters, context, executemany
            if self._active is not None:
                self._active[0] += 1

    @contextmanager
    def counting(self) -> Iterator[list[int]]:
        if self._active is not None:
            raise RuntimeError("statement counting is already active")
        count = [0]
        self._active = count
        try:
            yield count
        finally:
            self._active = None


def _validate_conventional(roots: Sequence[object]) -> None:
    if len(roots) != ROOTS or any(len(root.items) != FANOUT for root in roots):  # type: ignore[attr-defined]
        raise AssertionError("conventional fan-out did not publish 200 complete roots")


def _validate_duplicate(roots: Sequence[object]) -> None:
    if len(roots) != ROOTS:
        raise AssertionError("duplicate include did not publish 200 roots")
    for root in roots:
        items = root.items  # type: ignore[attr-defined]
        ordered = root.items_by_ship_date  # type: ignore[attr-defined]
        if len(items) != FANOUT or len(ordered) != FANOUT:
            raise AssertionError("a duplicate-include root is incomplete")
        if any(left is not right for left, right in zip(items, ordered, strict=True)):
            raise AssertionError("SQLAlchemy did not identity-merge duplicate child rows")


def _validate_document(roots: Sequence[object]) -> None:
    if len(roots) != ROOTS:
        raise AssertionError("document-heavy did not publish 200 roots")
    for root in roots:
        if len(root.trips) != FANOUT or root.payload["address"]["geo"]["country"] != "NO":  # type: ignore[attr-defined,index]
            raise AssertionError("a document-heavy root is incomplete")


def _validate_versioned(roots: Sequence[object]) -> None:
    if len(roots) != ROOTS or any(root.version != 1 for root in roots):  # type: ignore[attr-defined]
        raise AssertionError("versioned document did not publish the expected values")


def _validate_bitemporal(roots: Sequence[object]) -> None:
    if len(roots) != ROOTS:
        raise AssertionError("bitemporal current did not publish 200 roots")
    if any(root.valid_end is not INFINITY or root.tx_end is not INFINITY for root in roots):  # type: ignore[attr-defined]
        raise AssertionError("native PostgreSQL infinity did not reach the comparator sentinel")


def _workloads() -> dict[str, Workload]:
    instant = dt.datetime(2026, 9, 11, tzinfo=dt.UTC)
    return {
        "conventional-fanout": Workload(
            "conventional-fanout",
            select(Order).options(selectinload(Order.items)).order_by(Order.id),
            _validate_conventional,
        ),
        "duplicate-include": Workload(
            "duplicate-include",
            select(Order)
            .options(selectinload(Order.items), selectinload(Order.items_by_ship_date))
            .order_by(Order.id),
            _validate_duplicate,
        ),
        "document-heavy": Workload(
            "document-heavy",
            select(Traveler).options(selectinload(Traveler.trips)).order_by(Traveler.id),
            _validate_document,
        ),
        "versioned-document": Workload(
            "versioned-document",
            select(Ledger).order_by(Ledger.id),
            _validate_versioned,
        ),
        "bitemporal-current": Workload(
            "bitemporal-current",
            select(Position)
            .where(
                Position.valid_start <= instant,
                Position.valid_end > instant,
                Position.tx_start <= instant,
                Position.tx_end > instant,
            )
            .order_by(Position.id),
            _validate_bitemporal,
        ),
    }


def _consume(
    engine: Any,
    workload: Workload,
    delivery: str,
    page_size: int | None,
    first: Callable[[], None] | None = None,
) -> tuple[object, int]:
    with Session(engine, expire_on_commit=False) as session:
        statement = workload.statement
        if delivery == "stream":
            if page_size is None:
                raise AssertionError("stream delivery requires a page size")
            statement = statement.execution_options(yield_per=page_size)
        result = session.execute(statement).scalars()
        if delivery == "eager":
            held = result.all()
            if first is not None:
                first()
            return held, len(held)
        count = 0
        held: object = None
        iterator = iter(result)
        try:
            held = next(iterator)
            count = 1
        except StopIteration:
            pass
        if first is not None:
            first()
        for held in iterator:
            count += 1
        return held, count


def _warm(engine: Any, workload: Workload, delivery: str, page_size: int | None) -> None:
    for _ in range(WARMUPS):
        held, count = _consume(engine, workload, delivery, page_size)
        if count != ROOTS or held is None:
            raise AssertionError((workload.name, delivery, page_size, count))


def _timing(
    engine: Any,
    counter: StatementCounter,
    workload: Workload,
    delivery: str,
    page_size: int | None,
) -> Timing:
    _warm(engine, workload, delivery, page_size)
    wall: list[float] = []
    cpu: list[float] = []
    first: list[float] = []
    statements: list[int] = []
    for _ in range(REPEATS):
        wall_start = time.perf_counter()
        cpu_start = time.process_time()
        first_at: list[float] = []
        with counter.counting() as statement_count:
            held, count = _consume(
                engine,
                workload,
                delivery,
                page_size,
                lambda: first_at.append(time.perf_counter()),
            )
        cpu_end = time.process_time()
        wall_end = time.perf_counter()
        if count != ROOTS or held is None or len(first_at) != 1:
            raise AssertionError((workload.name, delivery, page_size, count))
        wall.append(wall_end - wall_start)
        cpu.append(cpu_end - cpu_start)
        first.append(first_at[0] - wall_start)
        statements.append(statement_count[0])
    if len(set(statements)) != 1:
        raise AssertionError((workload.name, delivery, page_size, statements))
    wall_s = statistics.median(wall)
    cpu_s = statistics.median(cpu)
    return Timing(
        wall_ms=wall_s * 1_000,
        cpu_ms=cpu_s * 1_000,
        first_ms=statistics.median(first) * 1_000,
        roots_per_second=ROOTS / wall_s,
        cpu_share=cpu_s / wall_s,
        statements=statements[0],
    )


def _memory(
    engine: Any,
    workload: Workload,
    delivery: str,
    page_size: int | None,
) -> Memory:
    _warm(engine, workload, delivery, page_size)
    gc.collect()
    gc.collect()
    tracemalloc.start()
    try:
        floor, _ = tracemalloc.get_traced_memory()
        tracemalloc.reset_peak()
        held, count = _consume(engine, workload, delivery, page_size)
        gc.collect()
        gc.collect()
        current, peak = tracemalloc.get_traced_memory()
        if count != ROOTS or held is None:
            raise AssertionError((workload.name, delivery, page_size, count))
    finally:
        tracemalloc.stop()
    retained = current - floor
    return Memory(
        retained_bytes=retained,
        peak_bytes=peak - floor,
        transient_bytes=peak - current,
    )


def _reading(
    engine: Any,
    counter: StatementCounter,
    workload: Workload,
    delivery: str,
    page_size: int | None,
) -> Reading:
    return Reading(
        workload=workload.name,
        delivery=delivery,
        page_size=page_size,
        roots=ROOTS,
        timing=_timing(engine, counter, workload, delivery, page_size),
        memory=_memory(engine, workload, delivery, page_size),
    )


def _validate_once(engine: Any, workload: Workload) -> None:
    with Session(engine, expire_on_commit=False) as session:
        roots = session.execute(workload.statement).scalars().all()
        workload.validate(roots)


def _measure_group(
    engine: Any,
    counter: StatementCounter,
    workloads: Sequence[Workload],
) -> list[Reading]:
    readings: list[Reading] = []
    for workload in workloads:
        _validate_once(engine, workload)
        readings.append(_reading(engine, counter, workload, "eager", None))
        for page_size in PAGE_SIZES:
            readings.append(_reading(engine, counter, workload, "stream", page_size))
    return readings


def _engine(run: Any) -> tuple[Any, StatementCounter]:
    provisioner = run._provisioner
    conninfo = provisioner._conninfo
    url = conninfo.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(url, pool_size=5, max_overflow=0)

    @event.listens_for(engine, "connect")
    def install_infinity_loader(connection: Any, record: object) -> None:
        del record
        connection.adapters.register_loader("timestamptz", _InfinityTimestamptzLoader)

    counter = StatementCounter()
    counter.install(engine)
    return engine, counter


def main() -> None:
    baseline = _baseline_module()
    workloads = _workloads()
    readings: list[Reading] = []
    with profile_for("pg-full").provisioned() as run:
        engine, counter = _engine(run)
        try:
            run.reset(model_of(ORDERS_MODEL), baseline._orders_fixtures())
            readings.extend(
                _measure_group(
                    engine,
                    counter,
                    (
                        workloads["conventional-fanout"],
                        workloads["duplicate-include"],
                    ),
                )
            )
            run.reset(model_of(DOCUMENT_LAYOUT_MODEL), baseline._document_fixtures())
            readings.extend(
                _measure_group(
                    engine,
                    counter,
                    (
                        workloads["document-heavy"],
                        workloads["versioned-document"],
                    ),
                )
            )
            run.reset(model_of(POSITION_MODEL), baseline._position_fixtures())
            readings.extend(
                _measure_group(engine, counter, (workloads["bitemporal-current"],))
            )
        finally:
            engine.dispose()
    print(
        json.dumps(
            {
                "conditions": {
                    "python": platform.python_version(),
                    "platform": f"{sys.platform}/{platform.machine()}",
                    "sqlalchemy": sqlalchemy.__version__,
                    "sqlalchemy_compiled_extensions": has_compiled_ext(),
                    "postgres": "18.6 in Testcontainers",
                    "roots": ROOTS,
                    "fanout": FANOUT,
                    "page_sizes": PAGE_SIZES,
                    "warmups": WARMUPS,
                    "repeats": REPEATS,
                    "loader": "selectinload",
                    "memory_scope": "Python allocations traced around one Session and delivery",
                    "temporal_extension": "psycopg timestamptz infinity normalized to a comparator sentinel",
                },
                "readings": [asdict(reading) for reading in readings],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
