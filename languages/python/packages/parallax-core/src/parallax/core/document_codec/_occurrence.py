from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TypeVar, cast

from parallax.core.base import NeutralType
from parallax.core.document_codec._shape import Leaf, MemberShape, Occurrence
from parallax.core.metamodel import Multiplicity

Encoded = TypeVar("Encoded")


@dataclass(frozen=True, slots=True)
class OccurrenceCarrier:
    """How one occurrence storage form exposes ordered values and Many elements."""

    absent: object
    values: Callable[[object, MemberShape], Iterable[object]]
    elements: Callable[[object], Iterable[object]]


def encode_occurrence[Encoded](
    value: object,
    shape: MemberShape,
    multiplicity: Multiplicity,
    carrier: OccurrenceCarrier,
    *,
    encode_leaf: Callable[[NeutralType, object], Encoded],
    build_object: Callable[[Iterable[tuple[str, Encoded]]], Encoded],
    build_array: Callable[[Iterable[Encoded]], Encoded],
) -> Encoded:
    """Encode one occurrence directly into caller-owned final containers."""
    if multiplicity is Multiplicity.MANY:
        return build_array(
            _encode_object(
                element,
                shape,
                carrier,
                encode_leaf=encode_leaf,
                build_object=build_object,
                build_array=build_array,
            )
            for element in carrier.elements(value)
        )
    if value is None:
        return cast("Encoded", value)
    return _encode_object(
        value,
        shape,
        carrier,
        encode_leaf=encode_leaf,
        build_object=build_object,
        build_array=build_array,
    )


def _encode_object[Encoded](
    record: object,
    shape: MemberShape,
    carrier: OccurrenceCarrier,
    *,
    encode_leaf: Callable[[NeutralType, object], Encoded],
    build_object: Callable[[Iterable[tuple[str, Encoded]]], Encoded],
    build_array: Callable[[Iterable[Encoded]], Encoded],
) -> Encoded:
    def entries() -> Iterable[tuple[str, Encoded]]:
        values = iter(carrier.values(record, shape))
        for member, value in zip(shape.members, values, strict=True):
            if value is carrier.absent:
                if isinstance(member, Occurrence) and member.multiplicity is Multiplicity.MANY:
                    yield member.name, build_array(())
                continue
            if isinstance(member, Leaf):
                yield member.name, encode_leaf(member.type, value)
                continue
            yield (
                member.name,
                encode_occurrence(
                    value,
                    member.shape,
                    member.multiplicity,
                    carrier,
                    encode_leaf=encode_leaf,
                    build_object=build_object,
                    build_array=build_array,
                ),
            )

    return build_object(entries())
