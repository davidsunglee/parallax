"""The Value Object class frontend (spec §2).

A Value Object Class extends :class:`ValueObject`, is inherently frozen, and uses
the same ``Attr[T]`` / ``attr(...)`` vocabulary Entity members use. It carries no
table, key, relationship, or identity, and it declares no class-header option at
all — a Value Object is reached only through the occurrences that contain it.

This module is a thin metaclass over the shared engine; every parsing rule,
reserved-name check, and payload construction lives there, so no second Value
Object parser exists.
"""

from __future__ import annotations

from typing import Any, cast

from pydantic import BaseModel
from pydantic._internal._model_construction import ModelMetaclass

from parallax.core.entity._declaration import (
    FRAMEWORK_MINT,
    DeclarationKind,
    ValueObjectShape,
    build_class,
    shape_of,
)
from parallax.core.entity._errors import EntityDefinitionError

__all__ = ["ValueObject", "ValueObjectMeta", "shape_of", "to_document", "wire_names_of"]


class ValueObjectMeta(ModelMetaclass):
    """The Value Object metaclass: the shared engine with no header vocabulary.

    The positionals are named ``cls_name``/``bases``/``ns`` and are
    positional-only for symmetry with the Entity metaclass, where ``name=`` and
    ``namespace=`` are header keywords that cannot also name a parameter.
    """

    def __new__(
        mcs,
        cls_name: str,
        bases: tuple[type, ...],
        ns: dict[str, Any],
        /,
        *,
        _mint: object | None = None,
        **unknown: object,
    ) -> type:
        if unknown:
            raise EntityDefinitionError(
                code="entity-header-unknown-option",
                message=(
                    f"{cls_name}: a Value Object declares no class-header option "
                    f"({', '.join(sorted(unknown))})"
                ),
            )
        return build_class(
            mcs,
            cls_name,
            bases,
            cast("dict[str, object]", ns),
            kind=DeclarationKind.VALUE_OBJECT,
            mint=_mint,
            axes=(),
            header=None,
        )


class ValueObject(BaseModel, metaclass=ValueObjectMeta, _mint=FRAMEWORK_MINT):
    """The frozen base every Parallax Value Object Class extends.

    Instances are the only legal value for a Value Object member: a caller never
    assigns a raw mapping where an occurrence is declared.
    """

    def __parallax_document__(self) -> dict[str, object]:
        """This value as its canonical nested document.

        Named for the capability rather than exported as a protocol import, so
        the operation-node layer can render a member without importing this
        frontend.
        """
        return _document(self)


def to_document(value: ValueObject | None) -> dict[str, object] | None:
    """Serialize a Value Object to its canonical nested document.

    ``None`` passes through unchanged (an absent occurrence). Filtered by
    Pydantic's ``model_fields_set``: a member the caller never populated is
    omitted rather than bound as an explicit null, which is the same
    explicit-versus-defaulted distinction a write row draws. A Many occurrence is
    the one exception — it is never nullable, and its empty default serializes as
    the empty array, the sole zero-element representation. Whether an omitted
    required member is a defect belongs to write validation, not to this
    serializer.
    """
    if value is None:
        return None
    return _document(value)


def _document(value: ValueObject) -> dict[str, object]:
    shape = shape_of(type(value))
    fields_set = value.model_fields_set
    document: dict[str, object] = {}
    for py_name, canonical in shape.py_to_name.items():
        if py_name not in fields_set and py_name not in shape.many_py:
            continue
        raw = getattr(value, py_name)
        if isinstance(raw, ValueObject):
            document[canonical] = _document(raw)
        elif isinstance(raw, tuple):
            items = cast("tuple[object, ...]", raw)
            document[canonical] = [
                _document(item) if isinstance(item, ValueObject) else item for item in items
            ]
        else:
            document[canonical] = raw
    return document


def wire_names_of(cls: type) -> ValueObjectShape:
    """``cls``'s member correspondences — what the frozen-node wrapper reads."""
    return shape_of(cls)
