"""The class-owned lifetime and exact-class boundary of edit resolution caches."""

from __future__ import annotations

import gc
import weakref
from collections.abc import Callable
from typing import Any, cast

import pytest
from pydantic import PrivateAttr

import parallax.core.internal.entity._entity as entity_frontend
import parallax.core.internal.entity._value_object as value_object_frontend
from parallax.core import (
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    Entity,
    TablePerHierarchy,
    ValueObject,
    attr,
)


class _EntityProbe(Entity, table="entity_probe", namespace="parallax.edit_resolution"):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str]


class _ValueObjectProbe(ValueObject):
    label: Attr[str]


class _EntityRoot(
    Entity,
    table="entity_root",
    namespace="parallax.edit_resolution",
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str]


class _EntityLeaf(
    _EntityRoot,
    namespace="parallax.edit_resolution",
    inheritance=ConcreteSubtype(tag_value="leaf"),
):
    detail: Attr[str]


class _OtherValueObjectProbe(ValueObject):
    detail: Attr[str]


class _InstanceStatePayload:
    pass


def test_each_frontend_builds_one_resolution_per_exact_class_after_warmup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entity_builds: list[type] = []
    value_object_builds: list[type] = []
    # Both frontends import their name merge rather than defining it, and
    # what `_resolution_of` calls is each module's own binding of it.
    original_wire_names_of = cast(
        "Callable[[type], object]", vars(entity_frontend)["wire_names_of"]
    )
    original_shape_of = cast("Callable[[type], object]", vars(value_object_frontend)["shape_of"])

    def counted_wire_names_of(cls: type) -> object:
        entity_builds.append(cls)
        return original_wire_names_of(cls)

    def counted_shape_of(cls: type) -> object:
        value_object_builds.append(cls)
        return original_shape_of(cls)

    monkeypatch.setattr(entity_frontend, "wire_names_of", counted_wire_names_of)
    monkeypatch.setattr(value_object_frontend, "shape_of", counted_shape_of)

    entity = _EntityProbe(id=1, label="a")
    value_object = _ValueObjectProbe(label="a")
    entity.edit(label="b").edit(label="c")
    value_object.edit().edit()

    assert entity_builds == [_EntityProbe]
    assert value_object_builds == [_ValueObjectProbe]


def test_entity_base_and_subclass_use_distinct_exact_class_resolutions() -> None:
    root = _EntityRoot.model_construct(id=1, label="root")
    leaf = _EntityLeaf.model_construct(id=2, label="leaf", detail="old")

    root.edit(label="changed")
    edited = leaf.edit(detail="new")

    assert edited.detail == "new"


def test_unrelated_value_object_classes_use_distinct_exact_class_resolutions() -> None:
    first = _ValueObjectProbe.model_construct(label="first")
    second = _OtherValueObjectProbe.model_construct(detail="old")

    first.edit(label="changed")
    edited = second.edit(detail="new")

    assert edited.detail == "new"


def _dynamic_entity_references() -> tuple[weakref.ReferenceType[Any], ...]:
    class DynamicEntity(Entity, table="dynamic_entity", namespace="parallax.edit_resolution"):
        id: Attr[int] = attr(primary_key=True)
        label: Attr[str]

    source = DynamicEntity(id=1, label="a")
    result = source.edit(label="b")
    return weakref.ref(DynamicEntity), weakref.ref(source), weakref.ref(result)


def _dynamic_value_object_references() -> tuple[weakref.ReferenceType[Any], ...]:
    class DynamicValueObject(ValueObject):
        label: Attr[str]

    source = DynamicValueObject(label="a")
    result = source.edit(label="b")
    return weakref.ref(DynamicValueObject), weakref.ref(source), weakref.ref(result)


@pytest.mark.parametrize(
    "references",
    [_dynamic_entity_references, _dynamic_value_object_references],
    ids=["entity", "value-object"],
)
def test_dynamic_classes_remain_collectible_after_resolution_cache_population(
    references: Callable[[], tuple[weakref.ReferenceType[Any], ...]],
) -> None:
    batches = [references() for _ in range(20)]

    gc.collect()
    gc.collect()

    assert all(reference() is None for batch in batches for reference in batch)


def _entity_class_with_discarded_instances() -> tuple[type, tuple[weakref.ReferenceType[Any], ...]]:
    class HeldEntity(Entity, table="held_entity", namespace="parallax.edit_resolution"):
        id: Attr[int] = attr(primary_key=True)
        label: Attr[str]
        _payload = PrivateAttr()

    source = HeldEntity(id=1, label="a")
    payload = _InstanceStatePayload()
    cast("Any", source)._payload = payload
    result = source.edit(label="b")
    return HeldEntity, (weakref.ref(source), weakref.ref(result), weakref.ref(payload))


def _value_object_class_with_discarded_instances() -> tuple[
    type, tuple[weakref.ReferenceType[Any], ...]
]:
    class HeldValueObject(ValueObject):
        label: Attr[str]
        _payload = PrivateAttr()

    source = HeldValueObject(label="a")
    payload = _InstanceStatePayload()
    cast("Any", source)._payload = payload
    result = source.edit(label="b")
    return HeldValueObject, (weakref.ref(source), weakref.ref(result), weakref.ref(payload))


@pytest.mark.parametrize(
    "build",
    [_entity_class_with_discarded_instances, _value_object_class_with_discarded_instances],
    ids=["entity", "value-object"],
)
def test_cached_resolution_retains_no_model_instance_or_instance_state(
    build: Callable[[], tuple[type, tuple[weakref.ReferenceType[Any], ...]]],
) -> None:
    _cls, references = build()

    gc.collect()
    gc.collect()

    assert all(reference() is None for reference in references)
