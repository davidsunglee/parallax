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

from parallax.core.document_codec import (
    NULL,
    DocumentShape,
    Occurrence,
    Presence,
    Present,
    encode_document,
    encode_many,
    shape_of_declaration,
)
from parallax.core.entity._declaration import (
    FRAMEWORK_MINT,
    DeclarationKind,
    build_class,
    shape_of,
)
from parallax.core.entity._errors import EntityDefinitionError
from parallax.core.metamodel import Multiplicity

__all__ = ["ValueObject", "ValueObjectMeta", "shape_of", "to_document"]


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
        the member serializer behind write rows and assignments can render a
        member without importing this frontend.
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

    Every leaf is spelled by ``m-document-codec``, never by this frontend and never by
    handing a runtime value to a JSON serializer, which is what left a ``Decimal``,
    ``bytes``, ``date``, ``time``, ``datetime``, or ``UUID`` leaf with no storage form.
    """
    if value is None:
        return None
    return _document(value)


def _document(value: ValueObject) -> dict[str, object]:
    shape = shape_of_declaration(shape_of(type(value)).shape)
    return encode_document(shape, _presences(value, shape))


def _presences(value: ValueObject, shape: DocumentShape) -> dict[str, Presence]:
    """One presence per populated member, keyed by canonical name.

    An unpopulated member contributes no entry at all, so the codec classifies it
    ``Missing`` — which is what omits an unset optional inner member rather than
    writing an explicit null for it. A ``many`` occurrence is always contributed,
    because its empty default is a value (``[]``) rather than an absence.

    A nested occurrence's value is composed through the codec rather than assembled
    here: a ``one`` carries that occurrence's own encoded object and a ``many`` its
    ``encode_many`` array, so nothing in this frontend builds a JSON array or nests an
    object of its own. A scalar leaf passes through as its managed value, which the
    codec spells.
    """
    declared = shape_of(type(value))
    fields_set = value.model_fields_set
    presences: dict[str, Presence] = {}
    for py_name, canonical in declared.py_to_name.items():
        if py_name not in fields_set and py_name not in declared.many_py:
            continue
        raw = getattr(value, py_name)
        member = shape.member(canonical)
        if isinstance(member, Occurrence) and member.multiplicity is Multiplicity.MANY:
            elements = cast("tuple[ValueObject, ...]", raw)
            presences[canonical] = Present(
                encode_many(
                    member.shape, [_presences(element, member.shape) for element in elements]
                )
            )
        elif raw is None:
            presences[canonical] = NULL
        elif isinstance(member, Occurrence):
            presences[canonical] = Present(
                encode_document(member.shape, _presences(cast("ValueObject", raw), member.shape))
            )
        else:
            presences[canonical] = Present(raw)
    return presences
