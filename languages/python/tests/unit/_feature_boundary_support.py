from __future__ import annotations

import hashlib
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, Protocol

from parallax.core import (
    MANY_TO_ONE,
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    DomainModel,
    Entity,
    Predicate,
    Rel,
    ValueObject,
    attr,
    rel,
)
from parallax.core.base import INT64, STRING, DocumentValue, NeutralType, PresentDocument
from parallax.core.base import Decimal as DecimalType
from parallax.core.dialect import POSTGRES
from parallax.core.document_codec import Leaf, decode_scalar_many_classified, encode_scalar_many
from parallax.core.entity._expressions import AuthoredQuery
from parallax.core.execution import prepare_model
from parallax.core.execution._preflight import preflight
from parallax.core.execution._publication import SelectedReadModel, read_projection
from parallax.core.execution._read_policy import interpreted
from parallax.core.metamodel import Multiplicity, TablePerConcreteSubtype
from parallax.core.object_query._fluent import typed_read_query
from parallax.core.object_query._resolved import ResolvedObjectQuery
from parallax.core.read_delivery._read_plan import ReadPlanCache

__all__ = ["CASES", "WINDOW_DESCRIPTIONS", "Case", "Driver", "driver_for", "workload_digest"]

_NAMESPACE: Final = "feature.boundary"


class Team(Entity, table="feature_team", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str]


class Person(Entity, table="feature_person", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    team_id: Attr[int | None]
    labels: Attr[tuple[str, ...]]
    team: Rel[Team | None] = rel(cardinality=MANY_TO_ONE, join=("team_id", "id"))


class Vehicle(Entity, namespace=_NAMESPACE, inheritance=AbstractRoot(TablePerConcreteSubtype())):
    id: Attr[int] = attr(primary_key=True)


class Car(Vehicle, table="feature_car", namespace=_NAMESPACE, inheritance=ConcreteSubtype()):
    seats: Attr[int]


class Bike(Vehicle, table="feature_bike", namespace=_NAMESPACE, inheritance=ConcreteSubtype()):
    gears: Attr[int]


class Parcel(ValueObject):
    labels: Attr[tuple[str, ...]]


class Holder(Entity, table="feature_holder", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    owner_id: Attr[int | None]
    vehicle_id: Attr[int | None]
    labels: Attr[tuple[str, ...]]
    parcels: Attr[tuple[Parcel, ...]]
    owner: Rel[Person | None] = rel(cardinality=MANY_TO_ONE, join=("owner_id", "id"))
    vehicle: Rel[Vehicle | None] = rel(cardinality=MANY_TO_ONE, join=("vehicle_id", "id"))


_MODEL: Final = DomainModel(Team, Person, Vehicle, Car, Bike, Holder)
_SHAPES: Final = (
    "shallow-scalar",
    "scalar-any",
    "nested-all",
    "two-hop-to-one",
    "quantifier-through-to-one",
    "subtype-narrowing",
)
_TYPES: Final = ("integer", "string", "decimal")
_SIZES: Final = (0, 8, 128)
_NEUTRAL_TYPES: Final[Mapping[str, NeutralType]] = {
    "integer": INT64,
    "string": STRING,
    "decimal": DecimalType(12, 2),
}

WINDOW_DESCRIPTIONS: Final[Mapping[str, str]] = {
    "typed-predicate-binding": (
        "Typed interpretation and read preflight under a prepared model selection; "
        "query authoring and model preparation excluded."
    ),
    "typed-cold-plan": (
        "Typed interpretation, read preflight, and first ReadPlanCache planning with "
        "SQL compilation and literal binding; fresh cache construction excluded."
    ),
    "scalar-collection-encode": (
        "Production scalar-collection encoding from an existing managed tuple; "
        "input preparation excluded."
    ),
    "scalar-collection-decode": (
        "Production scalar-collection stored-data classification and decoding from "
        "an existing canonical array; input preparation excluded."
    ),
}


@dataclass(frozen=True, slots=True)
class Case:
    name: str
    window: str
    units: int = 1


CASES: Final[tuple[Case, ...]] = (
    *(
        Case(f"predicate.{shape}.{operation}", window)
        for shape in _SHAPES
        for operation, window in (
            ("binding", "typed-predicate-binding"),
            ("cold-plan", "typed-cold-plan"),
        )
    ),
    *(
        Case(f"scalar-collection.{scalar_type}.size-{size}.{operation}", window)
        for scalar_type in _TYPES
        for size in _SIZES
        for operation, window in (
            ("encode", "scalar-collection-encode"),
            ("decode", "scalar-collection-decode"),
        )
    ),
)


class Driver(Protocol):
    units: int

    def prepare(self) -> None: ...

    def run(self) -> object: ...


def _predicate(shape: str) -> Predicate[Any]:
    match shape:
        case "shallow-scalar":
            return Holder.id == 7
        case "scalar-any":
            return Holder.labels.any(Holder.labels.element == "urgent")
        case "nested-all":
            return Holder.parcels.all(Parcel.labels.any(Parcel.labels.element == "urgent"))
        case "two-hop-to-one":
            return Holder.owner.team.name == "operations"
        case "quantifier-through-to-one":
            return Holder.owner.labels.any(Holder.owner.labels.element == "urgent")
        case "subtype-narrowing":
            return Holder.vehicle.is_a(Car, where=Car.seats > 2)
        case _:
            raise KeyError(shape)


class _PredicateDriver:
    units: int = 1

    def __init__(self, shape: str, *, cold_plan: bool) -> None:
        self._query: AuthoredQuery = typed_read_query(Holder.where(_predicate(shape)))
        self._selected: SelectedReadModel = read_projection(
            prepare_model(_MODEL, edition="feature-boundary")
        )
        self._cold_plan = cold_plan
        self._cache = ReadPlanCache()

    def prepare(self) -> None:
        if self._cold_plan:
            self._cache = ReadPlanCache()

    def run(self) -> object:
        selected = self._selected
        checked: ResolvedObjectQuery = preflight(
            interpreted(selected, self._query), model=selected.model.meta, form="graph"
        )
        if not self._cold_plan:
            return checked
        return self._cache.plan(
            edition=selected.edition,
            model=selected.model,
            dialect=POSTGRES,
            query=checked,
            result_form="instance",
            preference=None,
        )


class _ScalarDriver:
    units: int = 1

    def __init__(self, scalar_type: str, size: int, *, encode: bool) -> None:
        self._type = _NEUTRAL_TYPES[scalar_type]
        self._leaf = Leaf("values", self._type, False, Multiplicity.MANY)
        self._encode = encode
        raw: list[DocumentValue]
        match scalar_type:
            case "integer":
                self._managed: tuple[object, ...] = tuple(index % 4 for index in range(size))
                raw = [index % 4 for index in range(size)]
            case "string":
                self._managed = tuple(f"value-{index % 4}" for index in range(size))
                raw = [f"value-{index % 4}" for index in range(size)]
            case "decimal":
                self._managed = tuple(Decimal(f"{index % 4}.25") for index in range(size))
                raw = [f"{index % 4}.25" for index in range(size)]
            case _:
                raise KeyError(scalar_type)
        self._stored = PresentDocument(raw)

    def prepare(self) -> None:
        pass

    def run(self) -> object:
        if self._encode:
            return encode_scalar_many(self._type, self._managed)
        return decode_scalar_many_classified(self._leaf, self._stored)


@contextmanager
def driver_for(name: str) -> Generator[Driver]:
    if name not in {case.name for case in CASES}:
        raise KeyError(name)
    parts = name.split(".")
    if parts[0] == "predicate":
        yield _PredicateDriver(parts[1], cold_plan=parts[2] == "cold-plan")
    else:
        yield _ScalarDriver(
            parts[1], int(parts[2].removeprefix("size-")), encode=parts[3] == "encode"
        )


def workload_digest() -> str:
    """Fingerprint the frozen workloads and their controls, excluding instruments."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
