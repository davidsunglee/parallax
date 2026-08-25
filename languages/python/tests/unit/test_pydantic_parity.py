"""Three arms that must agree: compact backing, ordinary backing, and plain Pydantic.

A published value keeps its declared members in one tuple rather than in the
instance dictionary Pydantic's compiled serializer reads, so the framework gives
every declared class a serialization that reaches them as attributes. Nothing
here asserts the shape of that schema. What it asserts is the only property the
seam exists to provide: that the output is what it always was.

Each shape is declared twice — once as a Parallax Entity or Value Object, once as
a hand-restated plain ``BaseModel`` with the same fields, defaults, and authored
extensions — and dumped three ways across the serialization option
cross-product. The third arm is what makes the comparison mean anything: a
``mode="serialization"`` divergence was invisible to a compact-versus-ordinary
diff, because both backings were equally wrong. The twins are hand-restated
rather than derived from ``__pydantic_fields__``, so a defect in the derivation
cannot make the diff pass vacuously.

Two documented options are known to diverge on compact backing alone and are
pinned as such rather than silently omitted; see the section at the end.
"""

from __future__ import annotations

import json
import re
import warnings
from dataclasses import dataclass
from functools import cached_property
from typing import Annotated, Any, cast

import pytest
from _compact_support import published
from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    PrivateAttr,
    SerializerFunctionWrapHandler,
    Tag,
    TypeAdapter,
    computed_field,
    field_serializer,
    model_serializer,
)

from parallax.core.entity import (
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    Entity,
    ValueObject,
    attr,
)
from parallax.core.metamodel import TablePerHierarchy

_NS = "parity"

# --------------------------------------------------------------------------- #
# The shapes, each declared twice
# --------------------------------------------------------------------------- #


class Geo(ValueObject):
    lat: Attr[float]
    lon: Attr[float | None]


class PlainGeo(BaseModel):
    model_config = ConfigDict(frozen=True)
    lat: float
    lon: float | None = None


class Address(ValueObject):
    city: Attr[str]
    geo: Attr[Geo | None]


class PlainAddress(BaseModel):
    model_config = ConfigDict(frozen=True)
    city: str
    geo: PlainGeo | None = None


class Note(ValueObject):
    body: Attr[str]


class PlainNote(BaseModel):
    model_config = ConfigDict(frozen=True)
    body: str


class Warehouse(Entity, table="warehouse", namespace=_NS):
    # Every member is required, so neither `exclude_unset` nor `exclude_defaults`
    # has anything to drop on this shape.
    id: Attr[int] = attr(primary_key=True)
    code: Attr[str]


class PlainWarehouse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: int
    code: str


class Parcel(Entity, table="parcel", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    weight: Attr[float]
    label: Attr[str | None]
    note: Attr[str | None]


class PlainParcel(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: int
    weight: float
    label: str | None = None
    note: str | None = None


class Depot(Entity, table="depot", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    home: Attr[Address | None]
    notes: Attr[tuple[Note, ...]]


class PlainDepot(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: int
    home: PlainAddress | None = None
    notes: tuple[PlainNote, ...] = ()


class Meter(Entity, table="meter", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    reading: Attr[int]
    label: Attr[str | None]

    _seen = PrivateAttr(default=3)

    @computed_field
    @property
    def doubled(self) -> int:
        return self.reading * 2

    @cached_property
    def warmed(self) -> int:
        return self.reading + 1

    @field_serializer("label")
    def _rendered_label(self, value: str | None) -> str:
        return f"<{type(self).__name__}:{value}>"


class PlainMeter(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: int
    reading: int
    label: str | None = None

    _seen: int = PrivateAttr(default=3)

    @computed_field
    @property
    def doubled(self) -> int:
        return self.reading * 2

    @cached_property
    def warmed(self) -> int:
        return self.reading + 1

    @field_serializer("label")
    def _rendered_label(self, value: str | None) -> str:
        return f"<Meter:{value}>"


class Tally(Entity, table="tally", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    n: Attr[int | None]

    @model_serializer
    def _whole(self) -> dict[str, object]:
        return {"n": self.n, "seen_self": type(self) is Tally}


class PlainTally(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: int
    n: int | None = None

    @model_serializer
    def _whole(self) -> dict[str, object]:
        return {"n": self.n, "seen_self": True}


class Wrapped(Entity, table="wrapped", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    n: Attr[int | None]

    @model_serializer(mode="wrap")
    def _whole(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        rendered = dict(handler(self))
        rendered["seen_self"] = type(self) is Wrapped
        return rendered


class PlainWrapped(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: int
    n: int | None = None

    @model_serializer(mode="wrap")
    def _whole(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        rendered = dict(handler(self))
        rendered["seen_self"] = True
        return rendered


class Animal(
    Entity,
    table="animal",
    namespace=_NS,
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str]
    owner_id: Attr[int | None]
    home: Attr[Address | None]


class Cat(Animal, inheritance=ConcreteSubtype(tag_value="cat")):
    indoor: Attr[bool | None]
    perch: Attr[Address | None]


class PlainAnimal(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: int
    name: str
    owner_id: int | None = None
    home: PlainAddress | None = None


class PlainCat(PlainAnimal):
    indoor: bool | None = None
    perch: PlainAddress | None = None


class Holder(BaseModel):
    # A plain model an Entity nests inside, which is a different serializer path.
    model_config = ConfigDict(frozen=True)
    tag: str
    parcel: Parcel


class PlainHolder(BaseModel):
    model_config = ConfigDict(frozen=True)
    tag: str
    parcel: PlainParcel


class Circle(ValueObject):
    radius: Attr[float]


class Square(ValueObject):
    side: Attr[float | None]


class PlainCircle(BaseModel):
    model_config = ConfigDict(frozen=True)
    radius: float


class PlainSquare(BaseModel):
    model_config = ConfigDict(frozen=True)
    side: float | None = None


def _shape_tag(value: Any) -> str:
    """A callable discriminator, because a declared member is never a ``Literal``.

    Pydantic's tag-field discriminator needs a ``Literal`` or ``Enum`` member and
    the declaration grammar admits neither, so the union is discriminated the
    other documented way — which exercises the same tagged-union serializer.
    """
    return "square" if type(value).__name__.endswith("Square") else "circle"


# --------------------------------------------------------------------------- #
# The arms
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Arms:
    """One shape's three values, plus the adapters a container case needs."""

    name: str
    compact: Any
    ordinary: Any
    plain: Any


def _arms() -> list[Arms]:
    address = Address(city="Springfield", geo=Geo(lat=1.5))
    plain_address = PlainAddress(city="Springfield", geo=PlainGeo(lat=1.5))
    return [
        Arms(
            "all-required",
            published(Warehouse, id=7, code="WH"),
            Warehouse(id=7, code="WH"),
            PlainWarehouse(id=7, code="WH"),
        ),
        Arms(
            "partial-optional",
            published(Parcel, id=1, weight=2.5, label="x"),
            Parcel(id=1, weight=2.5, label="x"),
            PlainParcel(id=1, weight=2.5, label="x"),
        ),
        Arms(
            "every-position-carried",
            published(Parcel, id=1, weight=2.5, label="x", note=None),
            Parcel(id=1, weight=2.5, label="x", note=None),
            PlainParcel(id=1, weight=2.5, label="x", note=None),
        ),
        Arms(
            "nested-value-objects",
            published(
                Depot,
                id=3,
                home=published(Address, city="Springfield", geo=published(Geo, lat=1.5)),
                notes=(published(Note, body="a"), published(Note, body="b")),
            ),
            Depot(id=3, home=address, notes=(Note(body="a"), Note(body="b"))),
            PlainDepot(
                id=3,
                home=plain_address,
                notes=(PlainNote(body="a"), PlainNote(body="b")),
            ),
        ),
        Arms(
            "value-object-alone",
            published(Address, city="Springfield", geo=published(Geo, lat=1.5)),
            address,
            plain_address,
        ),
        Arms(
            "computed-private-and-cached",
            published(Meter, id=1, reading=5),
            Meter(id=1, reading=5),
            PlainMeter(id=1, reading=5),
        ),
        Arms(
            "authored-plain-model-serializer",
            published(Tally, id=1, n=2),
            Tally(id=1, n=2),
            PlainTally(id=1, n=2),
        ),
        Arms(
            "authored-wrap-model-serializer",
            published(Wrapped, id=1, n=2),
            Wrapped(id=1, n=2),
            PlainWrapped(id=1, n=2),
        ),
        Arms(
            "inherited-subtype",
            published(Cat, id=9, name="mog", indoor=True),
            Cat(id=9, name="mog", indoor=True),
            PlainCat(id=9, name="mog", indoor=True),
        ),
        Arms(
            "nested-in-a-plain-model",
            Holder(tag="t", parcel=published(Parcel, id=1, weight=2.5, label="x")),
            Holder(tag="t", parcel=Parcel(id=1, weight=2.5, label="x")),
            PlainHolder(tag="t", parcel=PlainParcel(id=1, weight=2.5, label="x")),
        ),
        Arms(
            "discriminated-union-member",
            published(Circle, radius=2.0),
            Circle(radius=2.0),
            PlainCircle(radius=2.0),
        ),
    ]


ARMS = {arm.name: arm for arm in _arms()}

# The serialization option cross-product every arm is required to agree on.
# `round_trip` and `exclude_computed_fields` are deliberately absent and are
# pinned separately at the end of this module.
OPTIONS: dict[str, dict[str, Any]] = {
    "default": {},
    "by-alias": {"by_alias": True},
    "exclude-none": {"exclude_none": True},
    "exclude-unset": {"exclude_unset": True},
    "exclude-defaults": {"exclude_defaults": True},
    "exclude-unset-and-none": {"exclude_unset": True, "exclude_none": True},
    "exclude-named": {"exclude": {"id"}},
    "include-named": {"include": {"id"}},
    "polymorphic": {"polymorphic_serialization": True},
    "serialize-as-any": {"serialize_as_any": True},
    "context": {"context": {"who": "test"}},
}


def _jsonable(value: Any) -> Any:
    """A comparable rendering of one dump, tuples and lists collapsed.

    ``model_dump`` keeps a tuple member a tuple while ``model_dump_json`` emits an
    array, and a Value Object twin declared with the same annotation agrees on
    both. Comparing through JSON is what lets one assertion cover both renderings
    without a per-shape exception.
    """
    return json.loads(json.dumps(value, default=str))


@pytest.mark.parametrize("shape", sorted(ARMS))
@pytest.mark.parametrize("option", sorted(OPTIONS))
def test_all_three_arms_dump_alike(shape: str, option: str) -> None:
    arm = ARMS[shape]
    kwargs = OPTIONS[option]
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        compact = arm.compact.model_dump(**kwargs)
        ordinary = arm.ordinary.model_dump(**kwargs)
        plain = arm.plain.model_dump(**kwargs)
    assert _jsonable(compact) == _jsonable(ordinary)
    assert _jsonable(compact) == _jsonable(plain)


@pytest.mark.parametrize("shape", sorted(ARMS))
@pytest.mark.parametrize("option", sorted(OPTIONS))
def test_all_three_arms_dump_json_alike(shape: str, option: str) -> None:
    arm = ARMS[shape]
    kwargs = OPTIONS[option]
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        compact = arm.compact.model_dump_json(**kwargs)
        ordinary = arm.ordinary.model_dump_json(**kwargs)
        plain = arm.plain.model_dump_json(**kwargs)
    assert compact == ordinary
    assert json.loads(compact) == json.loads(plain)


@pytest.mark.parametrize("option", sorted(OPTIONS))
def test_a_type_adapter_container_serializes_all_three_arms_alike(option: str) -> None:
    kwargs = OPTIONS[option]
    parallax: TypeAdapter[Any] = TypeAdapter(tuple[Parcel, ...])
    plain: TypeAdapter[Any] = TypeAdapter(tuple[PlainParcel, ...])
    compact = (published(Parcel, id=1, weight=2.5), published(Parcel, id=2, weight=1.0))
    ordinary = (Parcel(id=1, weight=2.5), Parcel(id=2, weight=1.0))
    twins = (PlainParcel(id=1, weight=2.5), PlainParcel(id=2, weight=1.0))
    assert parallax.dump_python(compact, **kwargs) == parallax.dump_python(ordinary, **kwargs)
    assert _jsonable(parallax.dump_python(compact, **kwargs)) == _jsonable(
        plain.dump_python(twins, **kwargs)
    )


@pytest.mark.parametrize("option", sorted(OPTIONS))
def test_a_type_adapter_union_serializes_all_three_arms_alike(option: str) -> None:
    kwargs = OPTIONS[option]
    parallax: TypeAdapter[Any] = TypeAdapter(Warehouse | Parcel)
    plain: TypeAdapter[Any] = TypeAdapter(PlainWarehouse | PlainParcel)
    assert parallax.dump_python(published(Parcel, id=1, weight=2.5), **kwargs) == (
        parallax.dump_python(Parcel(id=1, weight=2.5), **kwargs)
    )
    assert _jsonable(parallax.dump_python(published(Parcel, id=1, weight=2.5), **kwargs)) == (
        _jsonable(plain.dump_python(PlainParcel(id=1, weight=2.5), **kwargs))
    )


@pytest.mark.parametrize("option", sorted(OPTIONS))
def test_a_discriminated_union_serializes_all_three_arms_alike(option: str) -> None:
    kwargs = OPTIONS[option]
    parallax: TypeAdapter[Any] = TypeAdapter(
        Annotated[
            Annotated[Circle, Tag("circle")] | Annotated[Square, Tag("square")],
            Discriminator(_shape_tag),
        ]
    )
    plain: TypeAdapter[Any] = TypeAdapter(
        Annotated[
            Annotated[PlainCircle, Tag("circle")] | Annotated[PlainSquare, Tag("square")],
            Discriminator(_shape_tag),
        ]
    )
    compact = published(Square, side=3.0)
    ordinary = Square(side=3.0)
    assert parallax.dump_python(compact, **kwargs) == parallax.dump_python(ordinary, **kwargs)
    assert _jsonable(parallax.dump_python(compact, **kwargs)) == _jsonable(
        plain.dump_python(PlainSquare(side=3.0), **kwargs)
    )


def test_a_runtime_subtype_dumped_through_a_base_adapter_agrees_across_arms() -> None:
    # With `polymorphic_serialization` off, the BASE's schema serializes the
    # subtype, so a presence filter holding the base's ordinals would test them
    # against the subtype's row — which is why the filter resolves the plan from
    # the value rather than capturing it when the schema was built.
    parallax: TypeAdapter[Any] = TypeAdapter(Animal)
    compact = published(Cat, id=9, name="mog", indoor=True)
    ordinary = Cat(id=9, name="mog", indoor=True)
    matrix: tuple[dict[str, Any], ...] = (
        {},
        {"exclude_unset": True},
        {"polymorphic_serialization": True},
    )
    for kwargs in matrix:
        assert parallax.dump_python(compact, **kwargs) == parallax.dump_python(ordinary, **kwargs)


# --------------------------------------------------------------------------- #
# JSON Schema, which the seam must leave exactly as it found it
# --------------------------------------------------------------------------- #

_SCHEMA_PAIRS = {
    "warehouse": (Warehouse, PlainWarehouse),
    "parcel": (Parcel, PlainParcel),
    "depot": (Depot, PlainDepot),
    "address": (Address, PlainAddress),
    "meter": (Meter, PlainMeter),
    "cat": (Cat, PlainCat),
}


def _anonymized(schema: dict[str, Any]) -> Any:
    """One JSON Schema with every title and reference name folded away.

    A twin's class names differ by construction, so the comparable part is the
    structure: what is required, what each property is, and which mode produced
    it.
    """
    names = {cls.__name__ for pair in _SCHEMA_PAIRS.values() for cls in pair}
    names |= {"Geo", "PlainGeo", "Note", "PlainNote", "Address", "PlainAddress"}
    pattern = re.compile("|".join(sorted(names, key=len, reverse=True)))
    rendered = pattern.sub(
        lambda found: f"X{found.group().removeprefix('Plain')}",
        json.dumps(schema, sort_keys=True),
    )
    return json.loads(rendered)


@pytest.mark.parametrize("pair", sorted(_SCHEMA_PAIRS))
@pytest.mark.parametrize("mode", ["validation", "serialization"])
def test_json_schema_matches_a_plain_twin_in_both_modes(pair: str, mode: Any) -> None:
    parallax, plain = _SCHEMA_PAIRS[pair]
    assert _anonymized(parallax.model_json_schema(mode=mode)) == _anonymized(
        plain.model_json_schema(mode=mode)
    )


@pytest.mark.parametrize("mode", ["validation", "serialization"])
def test_type_adapter_json_schema_matches_a_plain_twin(mode: Any) -> None:
    parallax = TypeAdapter[Any](tuple[Parcel, ...]).json_schema(mode=mode)
    plain = TypeAdapter[Any](tuple[PlainParcel, ...]).json_schema(mode=mode)
    assert _anonymized(parallax) == _anonymized(plain)


def test_an_authored_json_schema_hook_still_runs() -> None:
    # The JSON-schema hook is owned but deliberately not reserved: an authored one
    # that delegates through `super()` composes with the framework's.
    class Annotated_(Entity, table="annotated", namespace=_NS):
        id: Attr[int] = attr(primary_key=True)

        @classmethod
        def __get_pydantic_json_schema__(cls, schema: Any, handler: Any) -> Any:
            rendered = dict(super().__get_pydantic_json_schema__(schema, handler))
            rendered["x-authored"] = True
            return rendered

    for mode in ("validation", "serialization"):
        assert Annotated_.model_json_schema(mode=mode)["x-authored"] is True


# --------------------------------------------------------------------------- #
# The object the seam serializes, and what it may not touch
# --------------------------------------------------------------------------- #


def test_an_authored_extension_receives_the_original_compact_object() -> None:
    seen: list[object] = []

    class Watched(Entity, table="watched", namespace=_NS):
        id: Attr[int] = attr(primary_key=True)
        label: Attr[str | None]

        @computed_field
        @property
        def echo(self) -> str:
            seen.append(self)
            return str(self.id)

        @field_serializer("label")
        def _label(self, value: str | None) -> str:
            seen.append(self)
            return f"[{value}]"

    value = published(Watched, id=4, label="x")
    assert value.model_dump() == {"id": 4, "label": "[x]", "echo": "4"}
    assert seen
    assert all(observed is value for observed in seen)


def test_serializing_a_compact_value_leaves_its_own_state_untouched() -> None:
    value = published(Parcel, id=1, weight=2.5, label="x")
    row = object.__getattribute__(value, "__parallax_compact__")
    fields_set = object.__getattribute__(value, "__pydantic_fields_set__")
    for kwargs in OPTIONS.values():
        value.model_dump(**kwargs)
        value.model_dump_json(**kwargs)
    assert object.__getattribute__(value, "__parallax_compact__") == row
    assert object.__getattribute__(value, "__pydantic_fields_set__") == fields_set
    assert not fields_set
    # Read last, because reading it is what would materialize it.
    assert value.__dict__ == {}


# --------------------------------------------------------------------------- #
# The Python behaviour an empty instance dictionary makes Parallax's to own
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("shape", sorted(ARMS))
def test_repr_str_equality_hashing_and_iteration_agree_across_arms(shape: str) -> None:
    arm = ARMS[shape]
    assert repr(arm.compact) == repr(arm.ordinary)
    assert str(arm.compact) == str(arm.ordinary)
    assert arm.compact == arm.ordinary
    assert arm.ordinary == arm.compact
    assert hash(arm.compact) == hash(arm.ordinary)
    assert dict(arm.compact) == dict(arm.ordinary)
    assert arm.compact.model_fields_set == arm.ordinary.model_fields_set


@pytest.mark.parametrize("shape", sorted(ARMS))
def test_iteration_exposes_declared_fields_and_nothing_else(shape: str) -> None:
    arm = ARMS[shape]
    for value in (arm.compact, arm.ordinary):
        assert set(dict(value)) == set(cast("Any", type(value)).__pydantic_fields__)


def test_iteration_exposes_no_relationship_sentinel_or_lifecycle_state() -> None:
    from parallax.core.entity import MANY_TO_ONE, Rel, rel
    from parallax.core.entity._declaration import LIFECYCLE_STATE_SLOT
    from parallax.core.entity._pydantic_storage import attach_instance_state

    class Bay(Entity, table="bay", namespace=_NS):
        id: Attr[int] = attr(primary_key=True)
        peer_id: Attr[int | None]
        peer: Rel[Bay | None] = rel(cardinality=MANY_TO_ONE, join=("peer_id", "id"))

    other = published(Bay, id=2)
    compact = published(Bay, {"peer": other}, id=1, peer_id=2)
    ordinary = Bay(id=1, peer_id=2)
    object.__setattr__(ordinary, "peer", other)
    attach_instance_state(ordinary, LIFECYCLE_STATE_SLOT, object())
    assert dict(compact) == {"id": 1, "peer_id": 2}
    assert dict(ordinary) == {"id": 1, "peer_id": 2}
    assert compact.peer is other
    assert compact.model_dump() == ordinary.model_dump() == {"id": 1, "peer_id": 2}


def test_a_value_differing_only_by_backing_compares_and_hashes_equal() -> None:
    compact = published(Parcel, id=1, weight=2.5, label="x")
    ordinary = Parcel(id=1, weight=2.5, label="x")
    assert compact == ordinary
    assert len({compact, ordinary}) == 1
    assert compact != published(Parcel, id=2, weight=2.5, label="x")
    assert compact != Warehouse(id=1, code="x")
    assert compact.__eq__(object()) is NotImplemented


def test_model_fields_set_is_a_fresh_snapshot_that_changes_nothing() -> None:
    value = published(Parcel, id=1, weight=2.5, label="x")
    first = value.model_fields_set
    assert first == {"id", "weight", "label"}
    assert value.model_fields_set is not first
    first.add("note")
    first.discard("label")
    assert value.model_fields_set == {"id", "weight", "label"}
    assert value.model_dump(exclude_unset=True) == {"id": 1, "weight": 2.5, "label": "x"}


def test_reading_an_absent_optional_member_never_consults_presence() -> None:
    # An absent position already holds the default Pydantic would have supplied,
    # which is what keeps a bitmap test off every ordinary member read.
    value = published(Parcel, id=1, weight=2.5)
    row = object.__getattribute__(value, "__parallax_compact__")
    assert value.label is None
    assert value.note is None
    assert row[0] == 0b0011
    assert row[3] is None
    assert row[4] is None
    assert "label" not in value.model_fields_set


def test_private_attribute_state_is_initialized_as_validation_would_have() -> None:
    compact = published(Meter, id=1, reading=5)
    ordinary = Meter(id=1, reading=5)
    assert cast("Any", compact)._seen == cast("Any", ordinary)._seen == 3
    assert compact.warmed == ordinary.warmed == 6


# --------------------------------------------------------------------------- #
# The two options a published value cannot answer, pinned rather than omitted
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("option", ["round_trip", "exclude_computed_fields"])
def test_neither_backing_answers_the_two_computed_field_skipping_options(option: str) -> None:
    # The residual, stated rather than discovered. pydantic-core skips computed
    # fields for both of these, on the ground that a computed field cannot be
    # validated back — and the framework's serialization restates every declared
    # field as a computed one, so neither option reaches a member. It reaches
    # neither backing, which is what keeps the two identical to each other; where
    # they both diverge is from a plain twin, and that is what this pins.
    kwargs: dict[str, Any] = {option: True}
    for value in (
        published(Parcel, id=1, weight=2.5, label="x"),
        Parcel(id=1, weight=2.5, label="x"),
        published(Meter, id=1, reading=5),
        Meter(id=1, reading=5),
    ):
        assert value.model_dump(**kwargs) == {}
    assert PlainParcel(id=1, weight=2.5, label="x").model_dump(**kwargs) != {}
