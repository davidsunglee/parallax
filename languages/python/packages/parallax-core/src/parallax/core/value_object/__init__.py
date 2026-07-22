"""``parallax.core.value_object`` enforcement scope (m-value-object).

The recursive embedded-composite model: a top-level value object and all its
nested value objects (to arbitrary depth) map to one ``json`` document column.
This scope resolves a dotted access path against the declared structure, reports
the leaf's neutral type for literal typing, and answers whether a path crosses a
``multiplicity: many`` member — the fact that decides core's flat **any-element**
vs terminated **same-element** semantics. ``m-value-object`` depends only on
``m-descriptor``.
"""

from __future__ import annotations

from collections.abc import Sequence

from parallax.core.descriptor import NestedValueObject, ValueObject, ValueObjectAttribute

__all__ = [
    "Container",
    "ValueObjectError",
    "crosses_many",
    "document_column",
    "leaf_type",
    "member",
    "resolve",
]

# A value-object container: the top-level document or any nested value object.
Container = ValueObject | NestedValueObject


class ValueObjectError(ValueError):
    """A value-object access path does not resolve against the declared structure."""


def document_column(vo: ValueObject) -> str:
    """The single structured-document column the whole composite is stored in."""
    return vo.storage_column


def member(container: Container, name: str) -> ValueObjectAttribute | NestedValueObject | None:
    """The direct child of ``container`` named ``name`` (attribute or nested VO)."""
    for attr in container.attributes:
        if attr.name == name:
            return attr
    for nested in container.value_objects:
        if nested.name == name:
            return nested
    return None


def resolve(vo: ValueObject, path: Sequence[str]) -> ValueObjectAttribute:
    """Resolve a dotted access ``path`` (element-relative) to its leaf attribute.

    Every non-final segment must name a nested value object; the final segment
    must name a scalar attribute. Raises :class:`ValueObjectError` on an unknown
    segment or a path that stops on a nested value object rather than a leaf.
    """
    if not path:
        raise ValueObjectError(f"{vo.name}: empty value-object access path")
    container: Container = vo
    for index, segment in enumerate(path):
        found = member(container, segment)
        if found is None:
            raise ValueObjectError(f"{vo.name}: unknown value-object segment {segment!r}")
        is_last = index == len(path) - 1
        if isinstance(found, ValueObjectAttribute):
            if not is_last:
                raise ValueObjectError(
                    f"{vo.name}: {segment!r} is a scalar attribute but the path continues past it"
                )
            return found
        if is_last:
            raise ValueObjectError(
                f"{vo.name}: path ends on nested value object {segment!r}, not a scalar leaf"
            )
        container = found
    raise ValueObjectError(f"{vo.name}: value-object path did not resolve")  # pragma: no cover


def leaf_type(vo: ValueObject, path: Sequence[str]) -> str:
    """The neutral type of the leaf attribute reached by ``path``."""
    return resolve(vo, path).type


def crosses_many(vo: ValueObject, path: Sequence[str]) -> bool:
    """Whether ``path`` traverses any ``multiplicity: many`` member.

    A flat predicate over such a path keeps core's **any-element** semantics
    (each predicate may be satisfied by a different element); a path confined to
    ``multiplicity: one`` members addresses a single embedded document.
    """
    if vo.multiplicity == "many":
        return True
    container: Container = vo
    for segment in path:
        found = member(container, segment)
        if isinstance(found, NestedValueObject):
            if found.multiplicity == "many":
                return True
            container = found
        else:
            break
    return False
