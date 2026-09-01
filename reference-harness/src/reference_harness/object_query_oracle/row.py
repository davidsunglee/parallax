"""Declared-type comparison for rows observed by the Object Query oracle."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from .. import portable_literal
from ..case import Entity, Model
from ..case_assertions import scalars_equal
from ..multiset import multiset_matches
from . import materialize


def _value_object_equal(left: Any, right: Any, declaration: dict[str, Any]) -> bool:
    def member_equal(left_member: Any, right_member: Any) -> bool:
        if not isinstance(left_member, Mapping) or not isinstance(right_member, Mapping):
            return False
        if left_member.keys() != right_member.keys():
            return False
        attributes = {item["name"]: item for item in declaration.get("attributes", [])}
        nested = {item["name"]: item for item in declaration.get("valueObjects", [])}
        for key in left_member:
            if key in nested:
                if not _value_object_equal(left_member[key], right_member[key], nested[key]):
                    return False
            elif left_member[key] is None or right_member[key] is None:
                if left_member[key] is not None or right_member[key] is not None:
                    return False
            elif key in attributes:
                if not portable_literal.values_equal(
                    left_member[key], right_member[key], attributes[key]["type"], None
                ):
                    return False
            elif not scalars_equal(left_member[key], right_member[key], None):
                return False
        return True

    if declaration.get("multiplicity", "one") == "many":
        if not isinstance(left, list) or not isinstance(right, list) or len(left) != len(right):
            return False
        return all(
            member_equal(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    if left is None or right is None:
        return left is None and right is None
    return member_equal(left, right)


def _attribute_for_key(model: Model, entity: Entity, key: str) -> dict[str, Any] | None:
    local = [
        attribute
        for attribute in entity.attributes
        if key in {attribute["name"], attribute["column"]}
    ]
    if len(local) == 1:
        return local[0]
    candidates = {
        (attribute["name"], attribute["column"], attribute["type"]): attribute
        for candidate in model.entities
        for attribute in candidate.attributes
        if key in {attribute["name"], attribute["column"]}
    }
    return next(iter(candidates.values())) if len(candidates) == 1 else None


def _row_matches(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    model: Model,
    entity: Entity,
    tolerance: Decimal | None,
) -> bool:
    if left.keys() != right.keys():
        return False
    concrete = materialize.variant_entity(model, entity, left)
    value_objects = {
        key: declaration
        for declaration in concrete.value_objects
        for key in (declaration["name"], declaration.get("column"))
        if key is not None
    }
    temporal_end_columns = {axis["end_column"] for axis in concrete.temporal_runtime_axes}
    for key in left:
        if key in value_objects:
            if not _value_object_equal(left[key], right[key], value_objects[key]):
                return False
            continue
        if left[key] is None or right[key] is None:
            if left[key] is not None or right[key] is not None:
                return False
            continue
        attribute = _attribute_for_key(model, concrete, key)
        if attribute is None:
            if not scalars_equal(left[key], right[key], tolerance):
                return False
            continue
        if attribute["column"] in temporal_end_columns and (
            left[key] == "infinity" or right[key] == "infinity"
        ):
            if left[key] != right[key]:
                return False
            continue
        if not portable_literal.values_equal(left[key], right[key], attribute["type"], tolerance):
            return False
    return True


def rows_equal(
    left: Sequence[Mapping[str, Any]],
    right: Sequence[Mapping[str, Any]],
    model: Model,
    entity: Entity,
    tolerance: Decimal | None = None,
    *,
    ordered: bool = False,
) -> bool:
    """Compare rows only after projecting leaves through their declared types."""
    if len(left) != len(right):
        return False

    def matches(item: Mapping[str, Any], candidate: Mapping[str, Any]) -> bool:
        return _row_matches(item, candidate, model, entity, tolerance)

    if ordered:
        return all(matches(item, candidate) for item, candidate in zip(left, right, strict=True))
    return multiset_matches(left, right, matches)
