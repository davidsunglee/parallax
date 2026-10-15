"""``models/dormant-position-layout-twin-document.yaml``: the Relational
Document Layout twin of :mod:`parallax.conformance.dormant_position_models`."""

from parallax.core import (
    MANY_TO_ONE,
    ONE_TO_MANY,
    AbstractRoot,
    AbstractSubtype,
    Attr,
    ConcreteSubtype,
    Document,
    DomainModel,
    Entity,
    Int32,
    Rel,
    TablePerHierarchy,
    attr,
    rel,
)
from parallax.core.metamodel import TablePerConcreteSubtype

_NS = "parallax.compatibility"

__all__ = [
    "DORMANT_POSITION_DOCUMENT",
    "Concept",
    "Craft",
    "Gadget",
    "Prototype",
    "Sloop",
    "Widget",
    "Workbench",
]


class Workbench(Entity, table="dormant_workbench", namespace=_NS, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=32)
    prototype_id: Attr[int | None]
    concept_id: Attr[int | None]
    prototypes: Rel[tuple["Prototype", ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "workbench_id"), order_by=("id",)
    )
    prototype: Rel["Prototype | None"] = rel(cardinality=MANY_TO_ONE, join=("prototype_id", "id"))
    gadgets: Rel[tuple["Gadget", ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "workbench_id"), order_by=("id",)
    )
    concepts: Rel[tuple["Concept", ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "workbench_id"), order_by=("id",)
    )
    concept: Rel["Concept | None"] = rel(cardinality=MANY_TO_ONE, join=("concept_id", "id"))


class Gadget(
    Entity,
    table="dormant_gadget",
    namespace=_NS,
    layout=Document(),
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=32)
    workbench_id: Attr[int | None]


class Widget(Gadget, namespace=_NS, inheritance=ConcreteSubtype(tag_value="widget")):
    spin: Attr[int | None] = attr(type=Int32)


class Prototype(Gadget, namespace=_NS, inheritance=AbstractSubtype()):
    draft: Attr[str | None] = attr(max_length=16)
    workbenches: Rel[tuple[Workbench, ...]] = rel(reverse_of="prototype")


class Craft(
    Entity,
    namespace=_NS,
    layout=Document(),
    inheritance=AbstractRoot(TablePerConcreteSubtype()),
):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=32)
    workbench_id: Attr[int | None]


class Sloop(Craft, table="dormant_sloop", namespace=_NS, inheritance=ConcreteSubtype()):
    hull: Attr[str | None] = attr(max_length=16)


class Concept(Craft, namespace=_NS, inheritance=AbstractSubtype()):
    sketch: Attr[str | None] = attr(max_length=16)
    workbenches: Rel[tuple[Workbench, ...]] = rel(reverse_of="concept")


DORMANT_POSITION_DOCUMENT = DomainModel(Workbench, Gadget, Widget, Prototype, Craft, Sloop, Concept)
