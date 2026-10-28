"""A declared class judges its edits and assignments with its own member
validation, before any model composes it.

Each class compiles the Typed lane of the authoring plans a write is prepared
through on first use, in their validation-only mode, so ``edit()`` and
``.set(...)`` reach the same verdict a write would without a prepared model.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from parallax.core import (
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    Entity,
    TablePerHierarchy,
    ValueObject,
    attr,
)
from parallax.core.base import NeutralType, ScalarConverter, typed_converter
from parallax.core.entity import EditError, EntityDefinitionError
from parallax.core.entity._declaration import member_validation

_NS = "member.validation"


class _Gauge(ValueObject):
    reading: Attr[Decimal] = attr(precision=4, scale=1)
    marks: Attr[tuple[int, ...]]


class _Meter(
    Entity,
    table="meter",
    namespace=_NS,
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    rate: Attr[Decimal] = attr(precision=4, scale=2)
    counts: Attr[tuple[int, ...]]
    gauge: Attr[_Gauge | None]


class _Thermometer(_Meter, namespace=_NS, inheritance=ConcreteSubtype(tag_value="thermo")):
    label: Attr[str | None]


_TOO_PRECISE = Decimal("1.234")
_OUT_OF_RANGE = 2**63


def _meter() -> _Thermometer:
    return _Thermometer(
        id=1, rate=Decimal("1.00"), counts=(1,), gauge=_Gauge(reading=Decimal("1.0"), marks=())
    )


def test_an_edit_judges_its_values_with_no_model_composing_its_class() -> None:
    with pytest.raises(EditError) as refused:
        _meter().edit(rate=_TOO_PRECISE, counts=(1, _OUT_OF_RANGE))

    assert {violation.member_name for violation in refused.value.violations} == {"rate", "counts"}


def test_an_assignment_judges_a_nested_value_with_no_model_composing_its_class() -> None:
    with pytest.raises(EditError, match=r"gauge\.reading"):
        _Meter.gauge.set(_Gauge.model_construct(reading=_TOO_PRECISE, marks=()))


def test_a_standalone_value_object_edit_judges_its_own_members() -> None:
    gauge = _Gauge(reading=Decimal("1.0"), marks=(1,))

    with pytest.raises(EditError, match=r"marks\[1\]"):
        gauge.edit(marks=(1, _OUT_OF_RANGE))
    assert gauge.edit(reading=Decimal("2.5")).reading == Decimal("2.5")


def test_an_inherited_member_is_judged_as_its_declaring_class_judges_it() -> None:
    for owner in (_Meter, _Thermometer):
        with pytest.raises(EditError) as refused:
            owner.rate.set(_TOO_PRECISE)
        (violation,) = refused.value.violations
        assert violation.message.endswith(
            "does not match the declared type Decimal(precision=4, scale=2)"
        )


def test_each_class_holds_one_validation_of_its_own() -> None:
    assert member_validation(_Meter) is member_validation(_Meter)
    assert member_validation(_Thermometer) is not member_validation(_Meter)
    assert member_validation(_Gauge) is member_validation(_Gauge)


def test_an_edit_judges_only_the_members_it_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    # A carried collection keeps its carrier check at reconstruction and is not
    # judged again, so an element constructed out of its value space is first
    # refused by the write that states it.
    carried = _Thermometer(id=1, rate=Decimal("1.00"), counts=(_OUT_OF_RANGE,), gauge=None)
    converted: list[object] = []

    def counting(declared: NeutralType) -> ScalarConverter:
        convert = typed_converter(declared)

        def counted(value: object) -> object:
            converted.append(value)
            return convert(value)

        return counted

    monkeypatch.setattr("parallax.core.entity._declaration.typed_converter", counting)
    validation = member_validation(_Thermometer)
    monkeypatch.setattr(validation, "_catalog", None)

    edited = carried.edit(label="probe")

    assert edited.counts == (_OUT_OF_RANGE,)
    assert converted == ["probe"]


def test_a_class_no_declaration_built_holds_no_member_validation() -> None:
    with pytest.raises(EntityDefinitionError, match="not a Parallax Entity or Value Object Class"):
        member_validation(object)
