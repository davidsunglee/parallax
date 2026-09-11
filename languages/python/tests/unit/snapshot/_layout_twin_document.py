"""The Relational Document Layout member of the classification layout twin.

Character-for-character its ``_layout_twin_columns`` sibling apart from the
root-owned ``layout=Document(...)`` each Entity declares. See that module for why
the pair is authored twice rather than parameterized.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

from parallax.core import (
    ONE_TO_MANY,
    Attr,
    Document,
    DomainModel,
    Entity,
    Rel,
    ValueObject,
    attr,
    rel,
)

__all__ = ["DOCUMENT_TWIN", "LayoutTwinChild", "LayoutTwinItem", "TwinProfile"]

_NAMESPACE = "parallax.compatibility"


class TwinProfile(ValueObject):
    """The occurrence both Entities embed, pairing a required scalar with a nullable one.

    ``street`` is required, so stored state that omits it is a violation;
    ``city`` is nullable, so a stored NULL beside it is a value the verdict must
    preserve. One occurrence therefore carries both halves of a classification.
    """

    street: Attr[str]
    city: Attr[str | None]


class LayoutTwinChild(
    Entity,
    table="layout_twin_child",
    namespace=_NAMESPACE,
    layout=Document(column="payload"),
):
    """The included Entity a twin read reaches through :attr:`LayoutTwinItem.children`.

    Both members declare this Entity name, namespace, table, and member set
    identically; only the root-owned layout differs.
    """

    id: Attr[int] = attr(primary_key=True)
    item_id: Attr[int]
    profile: Attr[TwinProfile | None]


class LayoutTwinItem(
    Entity,
    table="layout_twin",
    namespace=_NAMESPACE,
    layout=Document(column="payload"),
):
    """The queried root of a twin read, whose ``children`` is the requested include.

    Both members declare this Entity name, namespace, table, and member set
    identically; only the root-owned layout differs.
    """

    id: Attr[int] = attr(primary_key=True)
    profile: Attr[TwinProfile | None]
    children: Rel[tuple[LayoutTwinChild, ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "item_id")
    )


DOCUMENT_TWIN = DomainModel(LayoutTwinItem, LayoutTwinChild)
"""This member's model. Both members declare the same Entity names, so a read
must be issued through the classes of the model it connects."""
