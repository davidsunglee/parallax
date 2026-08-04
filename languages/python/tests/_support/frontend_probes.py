"""Declaration probes on the live-annotation path.

This module deliberately omits ``from __future__ import annotations`` so the
engine sees real ``Attr[T]`` / ``Rel[T]`` objects and type inference runs against
the concrete inner type. ``frontend_probes_stringized`` is the twin covering the
same declarations on the stringized path, which is separate code.

Each ``define_*`` helper builds a declaration expected to fail; the trailing
``return`` keeps the class referenced for the type checker even though the engine
raises before it runs. Declaring inside a function also means re-invoking a
helper is itself the repeated-declaration case. Each ``accepted_*`` helper builds
a declaration expected to succeed, whose compiled facts the two paths must agree
on member for member.
"""

from decimal import Decimal
from typing import ClassVar, Optional

from parallax.core import MANY_TO_ONE, Attr, Entity, Rel, ValueObject, attr, index, rel
from parallax.core.base import Int32
from parallax.core.metamodel import MAX, AbstractRoot, TablePerConcreteSubtype


class Peer(Entity, table="peer"):
    """A well-formed declaration the rejection probes point at."""

    id: Attr[int] = attr(primary_key=True)


class Address(ValueObject):
    """A reusable shape the accepted probes name through a quoted annotation."""

    city: Attr[str]


class Tag(ValueObject):
    """A reusable shape reached through a Many occurrence."""

    label: Attr[str]


def define_header_unknown_option() -> type:
    """A Pydantic configuration keyword is not a class-header option."""

    class Bad(Entity, table="bad", frozen=True):
        id: Attr[int] = attr(primary_key=True)

    return Bad


def define_header_invalid_value() -> type:
    """A dotted ``name=`` cannot be an Entity name."""

    class Bad(Entity, table="bad", name="sales.Bad"):
        id: Attr[int] = attr(primary_key=True)

    return Bad


def define_inheritance_invalid_strategy() -> type:
    """A strategy's class object where its parameterless value belongs."""

    class Bad(
        Entity,
        table="bad",
        inheritance=AbstractRoot(TablePerConcreteSubtype),  # pyright: ignore[reportArgumentType] - probe passes a deliberately wrong inheritance argument type
    ):
        id: Attr[int] = attr(primary_key=True)

    return Bad


def define_header_missing_option() -> type:
    """A standalone Entity omitting ``table=``."""

    class Bad(Entity):
        id: Attr[int] = attr(primary_key=True)

    return Bad


def define_base_invalid() -> type:
    """A domain-Entity subclass omitting its inheritance role."""

    class Bad(Peer):
        label: Attr[str]

    return Bad


def define_annotation_invalid() -> type:
    """A bare Python annotation where ``Attr``/``Rel`` are the only spellings."""

    class Bad(Entity, table="bad"):
        id: Attr[int] = attr(primary_key=True)
        qty: int = 5

    return Bad


def define_annotation_unmapped_type() -> type:
    """An inner type with no Neutral Type."""

    class Widget:
        pass

    class Bad(Entity, table="bad"):
        id: Attr[int] = attr(primary_key=True)
        widget: Attr[Widget]

    return Bad


def define_member_value_invalid() -> type:
    """A bare value in the assignment slot of an ``Attr[T]`` member."""

    class Bad(Entity, table="bad"):
        id: Attr[int] = attr(primary_key=True)
        qty: Attr[int] = 5  # pyright: ignore[reportAssignmentType] - probe assigns a bare value into an Attr[T] slot

    return Bad


def define_relationship_without_rel() -> type:
    """A ``Rel[T]`` member with no ``rel(...)`` value."""

    class Bad(Entity, table="bad"):
        id: Attr[int] = attr(primary_key=True)
        peer: Rel[Peer]

    return Bad


def define_option_invalid_value() -> type:
    """An intrinsically invalid factory argument, rejected at the call."""

    class Bad(Entity, table="bad"):
        id: Attr[int] = attr(primary_key=True)
        label: Attr[str] = attr(max_length=0)

    return Bad


def define_empty_index() -> type:
    """An ``index(...)`` with no components, rejected at the call."""

    class Bad(Entity, table="bad", indices=(index("bad_idx"),)):
        id: Attr[int] = attr(primary_key=True)

    return Bad


def define_mixed_rel_forms() -> type:
    """The defining and reverse ``rel(...)`` forms mixed in one call."""

    class Bad(Entity, table="bad"):
        id: Attr[int] = attr(primary_key=True)
        peer: Rel[Peer] = rel(reverse_of="bad", cardinality=None, join=("id", "id"))

    return Bad


def define_option_context_invalid() -> type:
    """A generating strategy on a non-integer member."""

    class Bad(Entity, table="bad"):
        id: Attr[str] = attr(primary_key=MAX)

    return Bad


def define_decimal_without_precision() -> type:
    """A decimal member with no precision and scale."""

    class Bad(Entity, table="bad"):
        id: Attr[int] = attr(primary_key=True)
        amount: Attr[Decimal]

    return Bad


def define_narrowing_on_wrong_family() -> type:
    """An ``Int32`` narrowing under a non-integer annotation."""

    class Bad(Entity, table="bad"):
        id: Attr[int] = attr(primary_key=True)
        label: Attr[str] = attr(type=Int32)

    return Bad


def define_reserved_member_name() -> type:
    """A member reusing a reserved introspection name."""

    class Bad(Entity, table="bad"):
        identity: Attr[int] = attr(  # pyright: ignore[reportIncompatibleVariableOverride] - probe reuses the reserved base member name `identity`
            primary_key=True
        )

    return Bad


def define_reserved_query_root_name() -> type:
    """A member taking the class-level query-root name ``all``."""

    class Bad(Entity, table="bad"):
        id: Attr[int] = attr(primary_key=True)
        all: Attr[str]

    return Bad


def define_reserved_temporal_name() -> type:
    """A member redeclaring a framework temporal name below a temporal root."""

    from parallax.core import TxTemporal

    class Bad(TxTemporal, table="bad"):
        id: Attr[int] = attr(primary_key=True)
        tx_start: Attr[int]  # pyright: ignore[reportIncompatibleVariableOverride] - probe redeclares the framework temporal member `tx_start`

    return Bad


def define_reserved_canonical_temporal_name() -> type:
    """A member taking a framework temporal member's canonical name."""

    from parallax.core import TxTemporal

    class Bad(TxTemporal, table="bad"):
        id: Attr[int] = attr(primary_key=True)
        txStart: Attr[int]

    return Bad


def define_reserved_temporal_name_by_rename() -> type:
    """A member whose explicit `name=` renames it onto a framework temporal name."""

    from parallax.core import TxTemporal

    class Bad(TxTemporal, table="bad"):
        id: Attr[int] = attr(primary_key=True)
        opened: Attr[int] = attr(name="txStart")

    return Bad


def define_canonical_name_collision() -> type:
    """Two members converting to one canonical name."""

    class Bad(Entity, table="bad"):
        order_id: Attr[int] = attr(primary_key=True)
        orderId: Attr[int]

    return Bad


def define_class_var_reserved_name() -> type:
    """A class variable taking one of the nine declaration member names."""

    class Bad(Entity, table="bad"):
        identity: ClassVar[str] = "shadow"  # pyright: ignore[reportIncompatibleVariableOverride] - probe shadows the reserved member name `identity` with a ClassVar
        id: Attr[int] = attr(primary_key=True)

    return Bad


def define_shadowed_declaration_member() -> type:
    """A method taking one of the nine declaration member names."""

    class Bad(Entity, table="bad"):
        id: Attr[int] = attr(primary_key=True)

        def indices(self) -> tuple[()]:  # pyright: ignore[reportIncompatibleVariableOverride] - probe shadows the reserved member name `indices` with a method
            return ()

    return Bad


def define_wide_union_annotation() -> type:
    """A union that is not ``X | None``, which optionality alone may spell."""

    class Bad(Entity, table="bad"):
        id: Attr[int] = attr(primary_key=True)
        label: Attr[int | str]

    return Bad


def define_wide_union_relationship_target() -> type:
    """The same rule on a relationship target, which is read as a spelling."""

    class Bad(Entity, table="bad"):
        id: Attr[int] = attr(primary_key=True)
        peer_id: Attr[int]
        peer: Rel["Peer | Peer"] = rel(cardinality=MANY_TO_ONE, join=("peer_id", "id"))

    return Bad


def define_nullable_many_relationship() -> type:
    """A to-many relationship spelled ``| None``, which loaded-empty rules out."""

    class Bad(Entity, table="bad"):
        id: Attr[int] = attr(primary_key=True)
        peers: Rel[tuple[Peer, ...] | None] = rel(reverse_of="bad")

    return Bad


def accepted_relationship_targets() -> type:
    """Every relationship-target spelling the grammar admits as text.

    A bare name is Relative and a qualified one is Exact, on both paths: a
    spelling resolves against the model's candidate set, never against the module
    the class happens to be declared in. A qualified spelling is therefore not a
    resolvable Python name, and carries the suppressions that costs.
    """

    class Hop(Entity, table="hop"):
        id: Attr[int] = attr(primary_key=True)
        peer_id: Attr[int]
        bare: Rel["Peer"] = rel(cardinality=MANY_TO_ONE, join=("peer_id", "id"))
        qualified: Rel["ops.Peer"] = rel(  # type: ignore[name-defined]  # noqa: F821 - qualified target is a spelling, not a resolvable name
            cardinality=MANY_TO_ONE, join=("peer_id", "id")
        )
        union_optional: Rel["Peer | None"] = rel(cardinality=MANY_TO_ONE, join=("peer_id", "id"))
        alias_optional: Rel[Optional["Peer"]] = rel(cardinality=MANY_TO_ONE, join=("peer_id", "id"))
        many: Rel[tuple["Peer", ...]] = rel(reverse_of="bare")

    return Hop


def accepted_value_object_spellings() -> type:
    """Quoted Value Object occurrence spellings, which resolve on both paths."""

    class Holder(Entity, table="holder"):
        id: Attr[int] = attr(primary_key=True)
        home: Attr["Address | None"]
        tags: Attr[tuple["Tag", ...]]

    return Holder


def accepted_class_var() -> type:
    """A class variable is not a member declaration on either path."""

    class Marked(Entity, table="marked"):
        kind: ClassVar[str] = "marked"
        id: Attr[int] = attr(primary_key=True)

    return Marked
