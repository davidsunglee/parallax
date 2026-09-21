"""The before/after delivery controls the Snapshot reading child measures beside
its Budget Contract, geometry read, and read-plan cells.

Three families, one control matrix. The two provider-free catalog workloads are
read through the Typed lane as well as the Wire lane, eager and streamed, at
each memory scaling arm, so a Typed result that is never projected is priced
beside the direct Wire result of the same rows and the per-root slope is read
across arms rather than assumed. The guarded include workload reads
``models/animal.yaml``'s family through its class mirror under three group
widths — ``Dog.owner``, then ``Cat.owner`` beside it, then ``WildBoar.owner`` —
each continued by ``pets`` narrowed to ``Cat``, so the number of guarded
positions sharing one relationship key varies independently of the root count;
its read plan is compiled cold and hit warm, and its result is delivered through
both lanes at two root counts. The result-held family holds one eager Typed
result of a small and a larger class-backed model while the runtime still shares
its prepared model, and again after the root has closed and released every
other owner, so the metadata a result keeps alive is read apart from the
reference slots it holds.

Every address is spelled here once — the report expands the matrix from
:func:`control_cells` and the reading child parses one address back through
:func:`control_address` — so the two cannot drift.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal, cast

from parallax.conformance.animal_owner import ANIMAL_MODEL
from parallax.conformance.read_models import Animal, Cat, Dog, WildBoar
from parallax.conformance.story_models import ORDERS_MODEL, Order
from parallax.conformance.workloads import catalog
from parallax.core import DomainModel
from parallax.core.db_port import DocumentReadOrdinals, PipelineStatement, Row
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.object_query._fluent import ObjectQuery
from tests._support.db_port import ConnectsAsItself, projected_rows
from tests.unit import _structural_geometry_support as geometry_support

__all__ = [
    "CONTROL_GROUP",
    "CONTROL_PREFIX",
    "DELIVERY_PREFIX",
    "DELIVERY_WORKLOAD_IDS",
    "FORMS",
    "GUARDED_MODEL",
    "GUARDED_PREFIX",
    "GUARDED_ROOTS",
    "GUARD_WIDTHS",
    "HELD_LARGE_MODEL",
    "HELD_LARGE_QUERY",
    "HELD_MODELS",
    "HELD_ROOTS",
    "HELD_SMALL_WORKLOAD_ID",
    "HELD_STATES",
    "HELD_WORKLOAD",
    "LANES",
    "METRICS",
    "PAGE_SIZE",
    "TYPED_QUERIES",
    "WARM_PLAN_METRICS",
    "ControlAddress",
    "DeliveryControl",
    "Form",
    "GuardedPlanControl",
    "GuardedPort",
    "GuardedReadControl",
    "HeldControl",
    "HeldModel",
    "HeldState",
    "Lane",
    "control_address",
    "control_cells",
    "guarded_query",
    "held_large_port",
    "verify_typed_twins",
]

type Lane = Literal["wire", "typed"]
type Form = Literal["eager", "page32"]
type PlanPhase = Literal["cold", "warm"]
type HeldModel = Literal["small", "large"]
type HeldState = Literal["shared", "closed"]

CONTROL_GROUP: Final = "control"
CONTROL_PREFIX: Final = "control-"
DELIVERY_PREFIX: Final = "control-delivery-"
GUARDED_PREFIX: Final = "control-guarded-"
HELD_WORKLOAD: Final = "control-held"

LANES: Final[tuple[Lane, ...]] = ("wire", "typed")
FORMS: Final[tuple[Form, ...]] = ("eager", "page32")
PAGE_SIZE: Final = 32
METRICS: Final = ("elapsedUs", "peakKiB", "retainedKiB")
WARM_PLAN_METRICS: Final = ("elapsedUs", "retainedKiB")
"""A warm hit compiles nothing, so it has no high-water mark of its own to read."""

DELIVERY_WORKLOAD_IDS: Final = ("conventional-fanout", "duplicate-include")
"""The catalog workloads with a provider-free port and a class-backed model."""

TYPED_QUERIES: Final[Mapping[str, ObjectQuery[Any, Any]]] = {
    "conventional-fanout": Order.where(Order.all).include(Order.items),
    "duplicate-include": Order.where(Order.all).include(Order.items, Order.items_by_ship_date),
}
"""The Typed spelling of each delivery workload's fixture query, over the same
class mirror the Wire lane's provider-free reads are served under."""


def verify_typed_twins() -> None:
    """That each Typed query canonicalizes to its workload's fixture query."""
    for workload_id, query in TYPED_QUERIES.items():
        catalog()[workload_id].validate_class_backed(ORDERS_MODEL, query)


GUARD_WIDTHS: Final = (1, 2, 3)
GUARDED_ROOTS: Final = (32, 256)
GUARDED_MODEL: Final = ANIMAL_MODEL
_GUARDED_SUBTYPES: Final[tuple[type[Animal], ...]] = (Dog, Cat, WildBoar)
_PERSONS_PER_ROOTS: Final = 4
_KINDS: Final = ("dog", "cat", "boar")


def guarded_query(width: int) -> ObjectQuery[Any, Any]:
    """Every animal, with the first ``width`` concrete subtypes each guarding an
    ``owner`` hop continued by ``pets`` narrowed to ``Cat``."""
    if width not in GUARD_WIDTHS:
        raise ValueError(f"{width} is not a guard width: {GUARD_WIDTHS}")
    return Animal.where(Animal.all).include(
        *(subtype.owner.pets.narrow(Cat) for subtype in _GUARDED_SUBTYPES[:width])
    )


def _animal_row(key: int, persons: int) -> dict[str, object]:
    kind = _KINDS[key % len(_KINDS)]
    return {
        "id": key,
        "kind": kind,
        "name": f"animal-{key:06d}",
        "owner_id": key % persons + 1,
        "license_id": None if kind == "boar" else f"L-{key:06d}",
        "indoor": True if kind == "cat" else None,
        "bark_volume": 3 if kind == "dog" else None,
        "tusk_length": None,
    }


class GuardedPort(ConnectsAsItself):
    """Provider-free rows for the guarded include workload: ``roots`` animals
    cycling through the three concretes, each owned by one of ``roots // 4``
    persons, whose cats are the pets the narrowed continuation delivers.

    Every statement composes its rows afresh and keeps none of them.
    """

    dialect: Dialect = POSTGRES
    __slots__ = ("_persons", "_roots")
    _roots: int
    _persons: int

    def __init__(self, roots: int) -> None:
        self._roots = roots
        self._persons = max(1, roots // _PERSONS_PER_ROOTS)

    def _animals(self) -> Iterator[dict[str, object]]:
        for key in range(1, self._roots + 1):
            yield _animal_row(key, self._persons)

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        if "from person t0" in sql:
            keys = sorted(cast("Sequence[int]", binds[0]))
            return projected_rows(
                sql, ({"id": key, "name": f"person-{key:06d}"} for key in keys), document_reads
            )
        if "t0.owner_id = any(" in sql:
            owners = frozenset(cast("Sequence[int]", binds[0]))
            return projected_rows(
                sql,
                (
                    row
                    for row in self._animals()
                    if row["kind"] == "cat" and row["owner_id"] in owners
                ),
                document_reads,
            )
        return projected_rows(sql, self._animals(), document_reads)

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        del sql, binds
        raise NotImplementedError

    def transaction[T](
        self,
        body: Callable[[Any], T],
        *,
        isolation: str | None = None,
    ) -> Any:
        del body, isolation
        raise NotImplementedError

    def execute_pipeline(self, statements: Sequence[PipelineStatement]) -> list[list[Row]]:
        return [
            self.execute(statement.sql, statement.binds, statement.document_reads)
            for statement in statements
        ]


HELD_MODELS: Final[tuple[HeldModel, ...]] = ("small", "large")
HELD_STATES: Final[tuple[HeldState, ...]] = ("shared", "closed")
HELD_ROOTS: Final = 32
HELD_SMALL_WORKLOAD_ID: Final = "conventional-fanout"
"""The small model is the orders catalog the delivery controls read; the larger
one is the whole geometry model, whose read delivers the shallow baseline."""
_HELD_LARGE_LEVEL: Final = geometry_support.level_named("depth-1")
HELD_LARGE_MODEL: Final[DomainModel] = geometry_support.MODEL
HELD_LARGE_QUERY: Final[ObjectQuery[Any, Any]] = geometry_support.read_query(
    _HELD_LARGE_LEVEL, "columns"
)


def held_large_port() -> geometry_support.GeometryPort:
    return geometry_support.GeometryPort(_HELD_LARGE_LEVEL, "columns", HELD_ROOTS)


@dataclass(frozen=True, slots=True)
class DeliveryControl:
    workload_id: str
    lane: Lane
    form: Form
    roots: int
    metric: str


@dataclass(frozen=True, slots=True)
class GuardedPlanControl:
    width: int
    phase: PlanPhase
    metric: str


@dataclass(frozen=True, slots=True)
class GuardedReadControl:
    width: int
    lane: Lane
    roots: int
    metric: str


@dataclass(frozen=True, slots=True)
class HeldControl:
    model: HeldModel
    state: HeldState


type ControlAddress = DeliveryControl | GuardedPlanControl | GuardedReadControl | HeldControl


def control_cells(delivery_roots: Sequence[int]) -> tuple[tuple[str, str], ...]:
    """Every (workload, cell) control address, delivery workloads first at
    each of ``delivery_roots``, then the guarded widths, then the held models."""
    cells: list[tuple[str, str]] = []
    for workload_id in DELIVERY_WORKLOAD_IDS:
        cells += [
            (f"{DELIVERY_PREFIX}{workload_id}", f"{lane}.{form}.roots{roots}.{metric}")
            for lane in LANES
            for form in FORMS
            for roots in delivery_roots
            for metric in METRICS
        ]
    for width in GUARD_WIDTHS:
        workload = f"{GUARDED_PREFIX}{width}"
        cells += [(workload, f"plan.cold.{metric}") for metric in METRICS]
        cells += [(workload, f"plan.warm.{metric}") for metric in WARM_PLAN_METRICS]
        cells += [
            (workload, f"{lane}.eager.roots{roots}.{metric}")
            for lane in LANES
            for roots in GUARDED_ROOTS
            for metric in METRICS
        ]
    cells += [
        (HELD_WORKLOAD, f"{model}.{state}.retainedKiB")
        for model in HELD_MODELS
        for state in HELD_STATES
    ]
    return tuple(cells)


def control_address(
    workload: str, path: str, delivery_roots: Sequence[int]
) -> ControlAddress | None:
    """The control one address names, or absence for any other address;
    ``ValueError`` for a control workload whose cell is not in the matrix."""
    if not workload.startswith(CONTROL_PREFIX):
        return None
    if (workload, path) not in control_cells(delivery_roots):
        raise ValueError(f"{workload}.{path} is not a control address")
    if workload == HELD_WORKLOAD:
        model, state, _metric = path.split(".")
        return HeldControl(cast("HeldModel", model), cast("HeldState", state))
    if workload.startswith(GUARDED_PREFIX):
        width = int(workload.removeprefix(GUARDED_PREFIX))
        head, second, *rest = path.split(".")
        if head == "plan":
            return GuardedPlanControl(width, cast("PlanPhase", second), rest[0])
        roots, metric = rest
        return GuardedReadControl(
            width, cast("Lane", head), int(roots.removeprefix("roots")), metric
        )
    lane, form, roots, metric = path.split(".")
    return DeliveryControl(
        workload.removeprefix(DELIVERY_PREFIX),
        cast("Lane", lane),
        cast("Form", form),
        int(roots.removeprefix("roots")),
        metric,
    )
