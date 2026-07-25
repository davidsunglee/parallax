"""Declaration probes on the stringized-annotation path.

The twin of ``frontend_probes``: identical rejections declared under
``from __future__ import annotations``, so the engine sees annotation *text* and
resolves it against the class body before module globals. The two paths are
separate code, so every code in the closed set is proved on both.
"""

from __future__ import annotations

from decimal import Decimal

from parallax.core import Attr, Entity, Rel, attr, index, rel
from parallax.core.base import Int32
from parallax.core.metamodel import MAX, AbstractRoot, TablePerConcreteSubtype


class Peer(Entity, table="peer"):
    """A well-formed declaration the rejection probes point at."""

    id: Attr[int] = attr(primary_key=True)


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
        inheritance=AbstractRoot(TablePerConcreteSubtype),  # pyright: ignore[reportArgumentType]
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
        qty: Attr[int] = 5

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
        identity: Attr[int] = attr(primary_key=True)

    return Bad


def define_reserved_temporal_name() -> type:
    """A member redeclaring a framework temporal name below a temporal root."""

    from parallax.core import TxTemporal

    class Bad(TxTemporal, table="bad"):
        id: Attr[int] = attr(primary_key=True)
        tx_start: Attr[int]

    return Bad


def define_canonical_name_collision() -> type:
    """Two members converting to one canonical name."""

    class Bad(Entity, table="bad"):
        order_id: Attr[int] = attr(primary_key=True)
        orderId: Attr[int]

    return Bad
