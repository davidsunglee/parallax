"""Field and relationship declaration metadata (``Field`` / ``Relationship``).

These constructors return spec objects the entity metaclass reads while building
the metamodel; they carry the descriptor facts a class cannot infer (neutral
type, physical column, primary-key and generation strategy, ordering) and are
stripped from the class body before Pydantic builds its validated fields.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from parallax.core.descriptor import UNSET, OrderByTerm, PkGenerator

__all__ = ["Field", "FieldSpec", "Relationship", "RelationshipSpec"]


def _pk_generator(value: str | Mapping[str, object] | None) -> PkGenerator | None:
    if value is None:
        return None
    if isinstance(value, str):
        if value not in ("none", "max", "sequence"):
            raise ValueError(f"unknown pk generator strategy: {value!r}")
        return PkGenerator(strategy=value)
    strategy = value.get("strategy")
    if strategy not in ("none", "max", "sequence"):
        raise ValueError(f"unknown pk generator strategy: {strategy!r}")
    return PkGenerator(
        strategy=strategy,
        sequence_name=_opt_str(value.get("sequenceName")),
        batch_size=_opt_int(value.get("batchSize")),
        initial_value=_opt_int(value.get("initialValue")),
        increment_size=_opt_int(value.get("incrementSize")),
    )


def _opt_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _opt_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


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
    """The declared metadata of one entity relationship."""

    cardinality: Literal["one-to-one", "many-to-one", "one-to-many", "many-to-many"]
    join: str
    related_entity: str
    name: str | None = None
    reverse_name: str | None = None
    dependent: bool = False
    foreign_key: str | None = None
    order_by: tuple[OrderByTerm, ...] = field(default_factory=tuple)


def Relationship(
    *,
    cardinality: Literal["one-to-one", "many-to-one", "one-to-many", "many-to-many"],
    join: str,
    related_entity: str,
    name: str | None = None,
    reverse_name: str | None = None,
    dependent: bool = False,
    foreign_key: str | None = None,
    order_by: Sequence[OrderByTerm] | None = None,
) -> Any:
    """Declare an entity relationship's descriptor metadata.

    ``related_entity`` names the target entity explicitly; the ``Rel[T]`` type
    argument carries only the typed instance surface, not the metamodel identity.
    """
    return RelationshipSpec(
        cardinality=cardinality,
        join=join,
        related_entity=related_entity,
        name=name,
        reverse_name=reverse_name,
        dependent=dependent,
        foreign_key=foreign_key,
        order_by=tuple(order_by) if order_by is not None else (),
    )
