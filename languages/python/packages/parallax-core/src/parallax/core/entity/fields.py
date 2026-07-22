"""Field and relationship declaration metadata (``Field`` / ``Relationship``).

These constructors return spec objects the entity metaclass reads while building
the metamodel; they carry the descriptor facts a class cannot infer (neutral
type, physical column, primary-key and generation strategy, ordering) and are
stripped from the class body before Pydantic builds its validated fields.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, cast

from parallax.core.descriptor import (
    UNSET,
    OrderByTerm,
    PkGenerator,
    PkStrategy,
    RelationshipCardinality,
    RelationshipJoin,
)
from parallax.core.entity.errors import EntityDefinitionError

__all__ = [
    "Field",
    "FieldSpec",
    "Relationship",
    "RelationshipSpec",
    "ReverseRelationship",
    "ReverseRelationshipSpec",
]

# The `pkGenerator` shape (metamodel.schema.json `$defs/pkGenerator`): a bare
# strategy keyword, or a CLOSED object carrying a `strategy` plus these typed
# optional fields (`additionalProperties: false`). Bounds (`batchSize >= 1`,
# `incrementSize >= 1`) are domain rules the descriptor validator enforces on the
# compiled record; here we only reject the wrong SHAPE the typed record cannot hold.
_PK_STRATEGIES: frozenset[str] = frozenset({"none", "max", "sequence"})
_PK_OBJECT_FIELDS: frozenset[str] = frozenset(
    {"strategy", "sequenceName", "batchSize", "initialValue", "incrementSize"}
)


def _pk_generator(value: str | Mapping[str, object] | None) -> PkGenerator | None:
    """Build a :class:`PkGenerator` from a declared ``pk_generator`` spelling.

    A present field of the wrong type, an unknown key, or a bad strategy is a
    build-time definition error (the same surface a bad ``Field(type=...)``
    raises), never silently coerced to ``None`` or dropped — so a malformed
    declaration can never reach the exported descriptor (python.md §2).
    """
    if value is None:
        return None
    if isinstance(value, str):
        return PkGenerator(strategy=_pk_strategy(value))
    strategy = _pk_strategy(value.get("strategy"))
    unknown = set(value) - _PK_OBJECT_FIELDS
    if unknown:
        raise EntityDefinitionError(f"pk generator: unknown field(s) {sorted(unknown)}")
    return PkGenerator(
        strategy=strategy,
        sequence_name=_pk_str(value, "sequenceName"),
        batch_size=_pk_int(value, "batchSize"),
        initial_value=_pk_int(value, "initialValue"),
        increment_size=_pk_int(value, "incrementSize"),
    )


def _pk_strategy(value: object) -> PkStrategy:
    if not isinstance(value, str) or value not in _PK_STRATEGIES:
        raise EntityDefinitionError(f"unknown pk generator strategy: {value!r}")
    return cast("PkStrategy", value)


def _pk_str(mapping: Mapping[str, object], key: str) -> str | None:
    # An omitted optional key stays unset; a present key must carry the typed
    # value (schema types it `string`, no `null`), so a present `None` is a
    # malformed declaration that fails the isinstance check, not a silent drop.
    if key not in mapping:
        return None
    value = mapping[key]
    if not isinstance(value, str):
        raise EntityDefinitionError(
            f"pk generator: `{key}` must be a string, got {type(value).__name__}"
        )
    return value


def _pk_int(mapping: Mapping[str, object], key: str) -> int | None:
    # An omitted optional key stays unset; a present key must carry the typed
    # value (schema types it `integer`, no `null`), so a present `None` is a
    # malformed declaration that fails the isinstance check, not a silent drop.
    if key not in mapping:
        return None
    value = mapping[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise EntityDefinitionError(
            f"pk generator: `{key}` must be an integer, got {type(value).__name__}"
        )
    return value


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """The declared metadata of one entity attribute."""

    primary_key: bool = False
    name: str | None = None
    column: str | None = None
    type: str | None = None
    max_length: int | None = None
    nullable: bool = False
    read_only: bool = False
    optimistic_locking: bool = False
    pk_generator: PkGenerator | None = None
    default: object = UNSET


def Field(
    *,
    primary_key: bool = False,
    name: str | None = None,
    column: str | None = None,
    type: str | None = None,
    max_length: int | None = None,
    nullable: bool = False,
    read_only: bool = False,
    optimistic_locking: bool = False,
    pk_generator: str | Mapping[str, object] | None = None,
    default: object = UNSET,
) -> Any:
    """Declare an entity attribute's descriptor metadata."""
    return FieldSpec(
        primary_key=primary_key,
        name=name,
        column=column,
        type=type,
        max_length=max_length,
        nullable=nullable,
        read_only=read_only,
        optimistic_locking=optimistic_locking,
        pk_generator=_pk_generator(pk_generator),
        default=default,
    )


@dataclass(frozen=True, slots=True)
class RelationshipSpec:
    """The defining branch of a class-authored relationship declaration."""

    cardinality: RelationshipCardinality
    join: RelationshipJoin
    name: str | None = None
    dependent: bool = False
    order_by: tuple[OrderByTerm, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ReverseRelationshipSpec:
    """The reverse branch of a class-authored relationship declaration."""

    reverse_of: str
    name: str | None = None
    order_by: tuple[OrderByTerm, ...] = field(default_factory=tuple)


def Relationship(
    *,
    cardinality: RelationshipCardinality,
    join: RelationshipJoin,
    name: str | None = None,
    dependent: bool = False,
    order_by: Sequence[OrderByTerm] | None = None,
) -> Any:
    """Declare the defining branch of an entity relationship."""
    return RelationshipSpec(
        cardinality=cardinality,
        join=join,
        name=name,
        dependent=dependent,
        order_by=tuple(order_by) if order_by is not None else (),
    )


def ReverseRelationship(
    *,
    reverse_of: str,
    name: str | None = None,
    order_by: Sequence[OrderByTerm] | None = None,
) -> Any:
    """Declare a reverse direction without repeating association facts."""
    return ReverseRelationshipSpec(
        reverse_of=reverse_of,
        name=name,
        order_by=tuple(order_by) if order_by is not None else (),
    )
