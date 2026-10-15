from parallax.core import (
    ONE_TO_MANY,
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    Document,
    DomainModel,
    Entity,
    Rel,
    TablePerHierarchy,
    attr,
    rel,
)

_NS = "parallax.compatibility"

__all__ = ["COMPOSED_BEAST_DOCUMENT_READER", "Beast", "Fox", "Wolf"]


class Beast(
    Entity,
    table="beast_document",
    namespace=_NS,
    layout=Document(),
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=32)
    leader_id: Attr[int | None]
    followers: Rel[tuple["Beast", ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "leader_id"), order_by=("id",)
    )


class Fox(Beast, namespace=_NS, inheritance=ConcreteSubtype(tag_value="fox")):
    brush: Attr[str] = attr(max_length=16)


class Wolf(Beast, namespace=_NS, inheritance=ConcreteSubtype(tag_value="wolf")):
    howl: Attr[str] = attr(max_length=16)


COMPOSED_BEAST_DOCUMENT_READER = DomainModel(Beast, Fox, Wolf)
